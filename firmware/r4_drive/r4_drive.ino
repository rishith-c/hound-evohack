/*
  r4_drive.ino — Hound: UNO R4 WiFi + CNC Shield V3 + 4× DRV8825 → mecanum rover drive.

  What it does
    • Hosts its own WiFi access point with a one-page web GUI: drive buttons (forward,
      back, strafe, rotate), per-wheel jog buttons for direction tuning, per-wheel
      INVERT toggles saved to EEPROM, speed slider, driver enable, live status.
    • Same commands over USB serial at 115200 (this is what the Pi will use later).
    • Steps are generated in a 20 kHz timer interrupt with linear ramps, so a
      speed change never yanks a stepper from rest to full rate.
    • Watchdog: if no command arrives for 400 ms, all four targets go to zero.
      The GUI re-sends while a button is held, so letting go = stop.

  Wheel ↔ shield axis, AS WIRED ON THE BENCH TODAY:
      FL = Y axis   FR = A axis   BL = X axis   BR = Z axis
  (The design docs say X=FL, Y=FR, Z=RL, A=RR. Either is fine — change the two tables below.)

  Shield pins (CNC Shield V3): X step D2 dir D5 · Y step D3 dir D6 · Z step D4 dir D7 ·
  A step D12 dir D13 (needs the D12 and D13 jumpers on the A header) · ENABLE D8, LOW = on.

  Power-up order still applies: USB (this board) first, THEN the pack on VMOT.
*/

#include <WiFiS3.h>
#include <EEPROM.h>
#include "FspTimer.h"
#include <Wire.h>                  // PCA9685 servo board on the shield's SDA/SCL (A4/A5, 5 V I2C)

// ───────────────────────── access point ─────────────────────────
#define ENABLE_WIFI 0                        // 0 for the rover: the Pi drives it over USB and the radio would eat the Pi USB budget. 1 = bench GUI.
const char* AP_SSID = "hound";
const char* AP_PASS = "rover-1234";          // change it; WPA2 needs 8+ characters

// ───────────────────────── wheel ↔ axis ─────────────────────────
enum { FL = 0, FR = 1, BL = 2, BR = 3 };
const char*   WNAME[4]    = { "FL", "FR", "BL", "BR" };
const char*   AXIS[4]     = { "Y",  "A",  "X",  "Z"  };
const uint8_t STEP_PIN[4] = {  3,   12,    2,    4  };
const uint8_t DIR_PIN[4]  = {  6,   13,    5,    7  };
const uint8_t EN_PIN      = 8;

// ───────────────────────── geometry & limits ─────────────────────
const float   WHEEL_D_MM  = 80.0f;
const int     FULL_STEPS  = 200;
const float   LX_MM       = 125.0f;          // half wheelbase (axles at X ±125)
const float   LY_MM       = 215.5f;          // half track    (wheel centres at Y ±215.5)
const int32_t TICK_HZ     = 30000;           // step ISR rate → max 15 000 steps/s per axis (was 20 kHz; verify the ticks counter still tracks)
const int32_t MAX_RATE    = 13500;           // steps/s per axis: 90 % of what the ISR can pulse
const float   V_MAX_MM    = 800.0f;          // physics ceiling: 84 % of the 1.5 A corner speed (228 rpm = 955 mm/s at 10.5 V, drivetrain.py) — torque is still full here
const float   ACCEL_MM_S2 = 600.0f;          // ramp in mm/s² (0.6 m/s²; case-B torque margin stays > 1.6 at 5.2 kg)
const uint32_t WATCHDOG_TICKS = TICK_HZ * 4 / 10;   // 400 ms
const uint32_t IDLE_DISABLE_MS = 3000;       // drivers off after 3 s of zero velocity

uint8_t  microsteps = 32;                    // M0+M2 caps = 1/32; M2 alone = 1/16
float    kMaxSps    = 0;                     // 'k <steps/s>': runtime top wheel rate, 0 = firmware cap (Fetch: sweep it to find the quiet band)
float    aSlew      = 0;                     // 'a <steps/s²>': runtime slew, 0 = ACCEL_MM_S2
int      speedPct   = 78;                    // single-key teleop speed: 78 % of the 530 mm/s cap = 415 mm/s; '+' / '-' in steps of 10
bool     circleOn   = false; uint32_t circleT0 = 0; float circleR = 300, circleT = 8;
// ── pack voltage: 47k (VMOT) / 10k (GND) divider into A3, 5 V reference. Reads ~0 with no divider fitted → check bypassed.
const uint8_t VBAT_PIN = A3; const float VBAT_RATIO = 57.0f / 10.0f; const float VBAT_REF = 5.0f;
float    vbat = 0;                           // filtered pack volts (0 = no divider)
float    vcut = 0.0f;                        // 0 = lockout OFF. Fit the 47k/10k divider on A3, then 'V 10.5' (3.5 V/cell). A floating A3 must never lock the drive.                       // 'V <volts>': refuse to drive below this (3.5 V/cell); 0 disables
bool     lowVolt = false;
uint8_t  inv[4]     = { 0, 0, 0, 0 };        // per-wheel direction flip (EEPROM)
bool     holdEnable = false;                 // keep drivers energised while parked

// ───────────────────────── ISR state ─────────────────────────────
volatile int32_t  targetRate[4];             // signed steps/s
volatile int32_t  curRate[4];
volatile uint32_t acc[4];
volatile uint8_t  pulseHigh[4];
volatile uint32_t wdTicks    = 0;
volatile bool     wdTripped  = false;
volatile bool     anyMotion  = false;
volatile uint32_t isrTicks   = 0;
volatile float    tVx = 0, tVy = 0, tWz = 0;  // target body velocity (mm/s, mm/s, rad/s) — ramped as ONE vector
volatile float    cVx = 0, cVy = 0, cWz = 0;  // current body velocity
volatile bool     bodyMode  = false;          // true: wheels follow the body vector; false: per-wheel targets (jog)
volatile float    spmNow    = 25.46f;         // steps/mm cached for the ISR
volatile int32_t  accelSteps = 15000;         // steps/s², recomputed from ACCEL_MM_S2 whenever microsteps change
bool timerOk = false;

static const uint32_t ACC_PER_STEP_PER_SEC = (uint32_t)(4294967296.0 / TICK_HZ);   // 214748

FspTimer stepTimer;
// ── pan/tilt: PCA9685 (0x40) on the CNC shield's SDA/SCL comms header, driven by the R4.
// Channels: TILT = channel 3 (positional MG996R, floor ~62–70°), PAN = channel 2 (continuous).
// Servo power (V+ terminal) comes from the XL4015 at 5.0 V; the fan sits on channel 15's V+/GND pins. 50 Hz, 500–2500 µs.
const uint8_t PCA = 0x40; const uint8_t TILT_CH = 3, PAN_CH = 2;   // tilt moved to ch 3 (user, 2026-09-24), pan ch 2
bool showOn = false; uint32_t showT0 = 0, showLastNudge = 0; uint8_t showStep = 0;   // Ceres turret_duet "kinematic show"
// The turret's zero is wherever it was hand-set: no pose is forced at boot, and a show comes back to where it began.
const int PAN_SIGN = -1;          // this pan servo turns right for pulses below 1500 (user, 2026-09-24): dir +1 = right everywhere
int panTrim = 0;                  // µs added to the pan's stop pulse (1500): trims out a left/right imbalance so timed turns net to zero
float panPos = 0, showPanStart = 0;   // net pan travel since boot in eased-nudge ms (+ = right); 0 = the hand-set start
int showTiltStart = -1;           // tilt before the show (-1 = limp), put back when it stops
uint32_t panHoldUntil = 0;        // 'H' test: hold the stop pulse; a pan that creeps now needs trim
const int SHOW_U_MS = 250, SHOW_TURNS = 4;   // expanding pan sweep: each turn ends SHOW_U_MS of travel further out than the last, on the other side
int panDir = 1; uint32_t panT0 = 0, panMs = 300;                 // current nudge, eased: pulse = 1500 ± 250·sin(π·t/T), then cut
const int TILT_MIN = 78, TILT_MAX = 150, TILT_PARK = 92;   // degrees; the head hammers the platform below ~75° on this build
const int PAN_L_US = 1250, PAN_R_US = 1750, PAN_NUDGE_MS = 300;   // Ceres turret_duet.ino: the pan is CONTINUOUS-ROTATION — timed nudges only, then cut the pulse (coast to stop)
int tiltDeg = TILT_PARK, panDeg = 0; bool tiltOn = false, panOn = false, pcaOk = false; uint32_t panStopAt = 0, pcaRetryAt = 0;
uint8_t i2cFound[8]; uint8_t i2cN = 0;
void i2cScan() {                              // which addresses answer on the shield's SDA/SCL (for the status line)
  i2cN = 0;
  for (uint8_t a = 0x08; a < 0x78 && i2cN < 8; a++) { Wire.beginTransmission(a); if (Wire.endTransmission() == 0) i2cFound[i2cN++] = a; }
}
void pcaWrite(uint8_t reg, uint8_t val) { Wire.beginTransmission(PCA); Wire.write(reg); Wire.write(val); Wire.endTransmission(); }
bool pcaInit() {
  Wire.begin(); Wire.setClock(100000);
  i2cScan();
  Wire.beginTransmission(PCA); if (Wire.endTransmission() != 0) return false;
  pcaWrite(0x00, 0x10);            // MODE1: sleep (prescale is only writable asleep)
  pcaWrite(0xFE, 121);             // prescale: 25 MHz / (4096 × 50 Hz) − 1
  pcaWrite(0x00, 0x00); delay(5);
  pcaWrite(0x00, 0xA1);            // restart, auto-increment, all-call
  return true;
}
void pcaPulse(uint8_t ch, int us) {           // us = 0 → channel fully off (servo limp)
  uint16_t off = us <= 0 ? 0 : (uint16_t)((uint32_t)us * 4096UL / 20000UL);
  Wire.beginTransmission(PCA); Wire.write(0x06 + 4 * ch);
  Wire.write(0); Wire.write(0); Wire.write(off & 0xFF); Wire.write(us <= 0 ? 0x10 : (off >> 8));   // ON=0, OFF=count (or full-off bit)
  Wire.endTransmission();
}
static int usFor(int deg) { return 600 + 10 * deg; }         // Ceres tilt mapping: 600 + 10 µs/°, 1500 = level
void setTilt(int deg) {                       // -1 = release
  if (deg < 0) { pcaPulse(TILT_CH, 0); tiltOn = false; return; }
  tiltDeg = deg < TILT_MIN ? TILT_MIN : deg > TILT_MAX ? TILT_MAX : deg;
  pcaPulse(TILT_CH, usFor(tiltDeg)); tiltOn = true;
}
void panStop() {                              // no pulse = the continuous servo coasts to a stop
  if (panStopAt) { float f = (millis() - panT0) / (float)panMs; if (f > 1) f = 1; panPos += panDir * (float)panMs * 0.5f * (1 - cosf(PI * f)); }   // float: int × uint32_t would wrap a left turn to +4.3e9   // share of the eased nudge done
  pcaPulse(PAN_CH, 0); panOn = false; panStopAt = 0; panHoldUntil = 0;
}
void nudgePan(int dir, int ms) {              // Ceres-style nudge, eased (kinematic): ramps up to 1250/1750 µs and back over ms, then pulse off
  if (panStopAt || panHoldUntil) panStop();   // book the travel of a nudge cut short
  panDir = dir < 0 ? -1 : 1; panMs = (ms > 0 && ms < 3000) ? ms : PAN_NUDGE_MS; panT0 = millis();
  panOn = true; panDeg += panDir;                              // panDeg counts net nudges
  panStopAt = panT0 + panMs;
  pcaPulse(PAN_CH, 1500 + panTrim);
}
void panTick() {                              // called every 20 ms while a nudge runs
  if (!panStopAt) return;
  float f = (millis() - panT0) / (float)panMs; if (f > 1) f = 1;
  pcaPulse(PAN_CH, 1500 + panTrim + PAN_SIGN * panDir * (int)(250.0f * sinf(PI * f)));
}
void setPan(int) { panStop(); }               // any 'p' just stops the pan — angles mean nothing to a continuous servo

void stepIsr(timer_callback_args_t*) {
  static uint16_t slewDiv = 0;
  isrTicks++;

  if (++wdTicks > WATCHDOG_TICKS) {
    bool had = false;
    for (int i = 0; i < 4; i++) { if (targetRate[i]) had = true; targetRate[i] = 0; }
    if (tVx != 0 || tVy != 0 || tWz != 0) had = true;
    tVx = tVy = tWz = 0;
    if (had) wdTripped = true;
    wdTicks = WATCHDOG_TICKS;
  }

  if (++slewDiv >= TICK_HZ / 1000) {          // 1 kHz ramp update
    slewDiv = 0;
    bool moving = false;
    if (bodyMode) {
      // Ramp the BODY velocity as one vector, then derive all four wheels from it: the mix is exact at every
      // instant, so a strafe never starts as a turn. Decel is 3× accel so STOP is quick without skipping.
      const float k = LX_MM + LY_MM;
      const float aMm = accelSteps / spmNow / 1000.0f;       // mm/s per ms
      float* cur[3] = { (float*)&cVx, (float*)&cVy, (float*)&cWz };
      float  tgt[3] = { tVx, tVy, tWz * k };                  // rotation handled as rim mm/s so one limit fits all
      float  now[3] = { cVx, cVy, cWz * k };
      for (int j = 0; j < 3; j++) {
        float t = tgt[j], c = now[j];
        float lim = ((t >= 0 ? t : -t) < (c >= 0 ? c : -c)) ? 3 * aMm : aMm;   // slowing: 3×
        if (c < t) { c += lim; if (c > t) c = t; } else if (c > t) { c -= lim; if (c < t) c = t; }
        now[j] = c;
      }
      cVx = now[0]; cVy = now[1]; cWz = now[2] / k;
      float w[4] = { cVx - cVy - now[2], cVx + cVy + now[2], cVx + cVy - now[2], cVx - cVy + now[2] };
      for (int i = 0; i < 4; i++) { curRate[i] = (int32_t)(w[i] * spmNow); if (curRate[i]) moving = true; }
    } else {
      const int32_t d = accelSteps / 1000;
      for (int i = 0; i < 4; i++) {
        int32_t t = targetRate[i], c = curRate[i];
        bool opposing = (t > 0 && c < 0) || (t < 0 && c > 0);
        if (opposing) c = 0;
        else if ((t >= 0 ? t : -t) <= (c >= 0 ? c : -c)) c = t;
        else if (c < t) { c += d; if (c > t) c = t; }
        else { c -= d; if (c < t) c = t; }
        curRate[i] = c;
        if (c) moving = true;
      }
    }
    anyMotion = moving;
  }

  for (int i = 0; i < 4; i++) {
    if (pulseHigh[i]) { digitalWrite(STEP_PIN[i], LOW); pulseHigh[i] = 0; }
    int32_t r = curRate[i];
    if (r == 0) continue;
    uint32_t inc = (uint32_t)(r < 0 ? -r : r) * ACC_PER_STEP_PER_SEC;
    uint32_t a = acc[i] + inc;
    if (a < acc[i]) {                          // 32-bit wrap = one step
      bool fwd = (r > 0) != (inv[i] != 0);
      digitalWrite(DIR_PIN[i], fwd ? HIGH : LOW);   // DRV8825 wants DIR ≥ 650 ns before STEP; digitalWrite is slower than that
      digitalWrite(STEP_PIN[i], HIGH);
      pulseHigh[i] = 1;                        // goes LOW next tick (50 µs ≥ 1.9 µs minimum)
    }
    acc[i] = a;
  }
}

bool startTimer() {
  uint8_t type = GPT_TIMER;
  int8_t ch = FspTimer::get_available_timer(type);
  if (ch < 0) ch = FspTimer::get_available_timer(type, true);
  if (ch < 0) return false;
  stepTimer.begin(TIMER_MODE_PERIODIC, type, ch, (float)TICK_HZ, 0.0f, stepIsr);
  stepTimer.setup_overflow_irq();
  stepTimer.open();
  stepTimer.start();
  return true;
}

// ───────────────────────── motion commands ───────────────────────
float stepsPerMm() { return FULL_STEPS * (float)microsteps / (3.14159265f * WHEEL_D_MM); }
float capSps()      { float c = MAX_RATE; if (kMaxSps > 0 && kMaxSps < c) c = kMaxSps; float p = V_MAX_MM * stepsPerMm(); return p < c ? p : c; }
float maxMm()       { return capSps() / stepsPerMm(); }
void  updateAccel() { int32_t a = (int32_t)(aSlew > 0 ? aSlew : ACCEL_MM_S2 * stepsPerMm()); if (a < 1000) a = 1000; accelSteps = a; }

void kick() { wdTicks = 0; wdTripped = false; }
void readVbat() {
  static uint32_t last = 0; if (millis() - last < 50) return; last = millis();
  float v = analogRead(VBAT_PIN) * (VBAT_REF / 1023.0f) * VBAT_RATIO;
  vbat = vbat == 0 ? v : 0.9f * vbat + 0.1f * v;
  bool present = vbat > 5.0f;                // a pack is connected and the divider exists
  lowVolt = present && vcut > 0 && vbat < vcut;
}

// vx forward mm/s, vy left mm/s, wz counter-clockwise rad/s
void setVelocity(float vx, float vy, float wz) {
  const float k = LX_MM + LY_MM;
  float w[4];
  w[FL] = vx - vy - wz * k;
  w[FR] = vx + vy + wz * k;
  w[BL] = vx + vy - wz * k;
  w[BR] = vx - vy + wz * k;
  const float spm = stepsPerMm();
  const float cap = capSps();                  // steps/s: the lowest of the ISR budget, the physics ceiling and 'k'
  float scale = 1.0f;
  for (int i = 0; i < 4; i++) {
    float s = fabsf(w[i]) * spm;
    if (s > cap) { float f = cap / s; if (f < scale) scale = f; }
  }
  if (lowVolt) { vx = vy = wz = 0; for (int i = 0; i < 4; i++) w[i] = 0; }   // pack below the cutoff: the only command that works is stop
  for (int i = 0; i < 4; i++) targetRate[i] = (int32_t)(w[i] * spm * scale);   // reported as "target"
  spmNow = spm;
  tVx = vx * scale; tVy = vy * scale; tWz = wz * scale;
  bodyMode = true;
  kick();
}

void jog(int wheel, int dir, float mmps) {
  float r = mmps * stepsPerMm();
  const float cap = capSps();
  if (r > cap) r = cap;
  for (int i = 0; i < 4; i++) targetRate[i] = 0;
  if (wheel >= 0 && wheel < 4) targetRate[wheel] = (int32_t)(dir < 0 ? -r : r);
  tVx = tVy = tWz = 0; bodyMode = false;
  kick();
}

void stopAll() { for (int i = 0; i < 4; i++) targetRate[i] = 0; tVx = tVy = tWz = 0; kick(); }

// ───────────────────────── EEPROM ────────────────────────────────
const int EE_MAGIC = 0x5A;
void loadSettings() {
  if (EEPROM.read(0) != EE_MAGIC) return;
  for (int i = 0; i < 4; i++) inv[i] = EEPROM.read(1 + i) ? 1 : 0;
  uint8_t ms = EEPROM.read(5);
  if (ms == 16 || ms == 32 || ms == 8) microsteps = ms;
}
void saveSettings() {
  EEPROM.write(0, EE_MAGIC);
  for (int i = 0; i < 4; i++) EEPROM.write(1 + i, inv[i]);
  EEPROM.write(5, microsteps);
}

// ───────────────────────── status JSON ───────────────────────────
char jsonBuf[480];
const char* i2cList() { static char b[40]; int n = 0; b[0] = 0; for (uint8_t i = 0; i < i2cN && n < 34; i++) n += snprintf(b + n, sizeof(b) - n, "%s0x%02X", i ? " " : "", i2cFound[i]); return b; }
const char* statusJson() {
  int en = digitalRead(EN_PIN) == LOW;
  snprintf(jsonBuf, sizeof(jsonBuf),
    "{\"map\":{\"FL\":\"%s\",\"FR\":\"%s\",\"BL\":\"%s\",\"BR\":\"%s\"},"
    "\"target\":[%ld,%ld,%ld,%ld],\"rate\":[%ld,%ld,%ld,%ld],\"inv\":[%d,%d,%d,%d],"
    "\"en\":%d,\"hold\":%d,\"wd\":%d,\"ms\":%d,\"spm\":%.2f,\"maxmm\":%.0f,\"k\":%.0f,\"a\":%ld,\"pct\":%d,\"circle\":%d,\"vbat\":%.2f,\"vcut\":%.1f,\"lv\":%d,\"tmr\":%d,\"ticks\":%lu,\"tilt\":%d,\"tilton\":%d,\"pan\":%d,\"panon\":%d,\"ptrim\":%d,\"ppos\":%.0f,\"pca\":%d,\"show\":%d,\"i2c\":\"%s\",\"ip\":\"%s\"}",
    AXIS[0], AXIS[1], AXIS[2], AXIS[3],
    (long)targetRate[0], (long)targetRate[1], (long)targetRate[2], (long)targetRate[3],
    (long)curRate[0], (long)curRate[1], (long)curRate[2], (long)curRate[3],
    inv[0], inv[1], inv[2], inv[3], en, holdEnable ? 1 : 0, wdTripped ? 1 : 0, microsteps,
    stepsPerMm(), maxMm(), capSps(), (long)accelSteps, speedPct, circleOn ? 1 : 0, vbat, vcut, lowVolt ? 1 : 0, timerOk ? 1 : 0, (unsigned long)isrTicks, tiltDeg, tiltOn ? 1 : 0, panDeg, panOn ? 1 : 0, panTrim, panPos, pcaOk ? 1 : 0, showOn ? 1 : 0, i2cList(), ENABLE_WIFI ? WiFi.localIP().toString().c_str() : "off");
  return jsonBuf;
}

// ───────────────────────── web page ──────────────────────────────
static const char PAGE[] =
"<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
"<title>rover drive</title><style>"
"body{font:16px system-ui;margin:0;background:#fff;color:#111}main{max-width:720px;margin:0 auto;padding:16px}"
"h1{font-size:20px;margin:0 0 8px}.g{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:10px 0}"
"button{font:inherit;font-size:16px;padding:16px 8px;border:1px solid #888;border-radius:6px;background:#f5f5f5;touch-action:none;user-select:none}"
"button:active,button.on{background:#cde}button.stop{background:#e33;color:#fff;border-color:#a00}"
".w{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.w div{border:1px solid #ccc;border-radius:6px;padding:8px;text-align:center}"
".w b{display:block;font-size:18px}.w small{color:#666}.w .r{font-family:ui-monospace,monospace;font-size:14px;margin:6px 0}"
".row{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin:10px 0}label{display:flex;gap:6px;align-items:center}"
"#st{font-family:ui-monospace,monospace;font-size:13px;color:#444;white-space:pre-wrap}.tip{background:#f3f6fa;border-left:4px solid #369;padding:8px 12px;font-size:14px}"
"</style></head><body><main>"
"<h1>rover drive</h1>"
"<div class=row><label>speed <input id=sp type=range min=20 max=190 value=80> <span id=spv>80</span> mm/s</label>"
"<label><input id=hold type=checkbox> hold drivers on</label>"
"<label>microsteps <select id=ms><option>16<option selected>32</select></label></div>"
"<div class=g>"
"<button data-v='0,0,1'>rotate ⟲</button><button data-v='1,0,0'>forward ▲</button><button data-v='0,0,-1'>rotate ⟳</button>"
"<button data-v='0,1,0'>strafe ◀</button><button class=stop id=stop>STOP</button><button data-v='0,-1,0'>strafe ▶</button>"
"<button data-v='1,1,0'>diag ◤</button><button data-v='-1,0,0'>back ▼</button><button data-v='1,-1,0'>diag ◥</button>"
"</div>"
"<div class=w id=wheels></div>"
"<div class=tip><b>Direction tuning.</b> Hold <b>FL ▲</b>: the front-left wheel must roll the rover forward. If it rolls the other way, tap <b>invert</b> under FL. "
"Do all four. Then hold <b>forward</b>: all four roll forward. Hold <b>strafe ◀</b>: FL back, FR forward, BL forward, BR back. If forward is right but strafe is wrong, two wheels of one side are swapped left/right-hand.</div>"
"<p id=st>connecting…</p>"
"</main><script>"
"const W=['FL','FR','BL','BR'];let timer=null,cur=null;"
"function q(p){return fetch(p).then(r=>r.json()).then(show).catch(()=>{});}"
"function v(){return +document.getElementById('sp').value;}"
"function send(){if(cur===null)return;"
" if(cur.jog)q('/jog?w='+cur.jog[0]+'&d='+cur.jog[1]+'&s='+v());"
" else{const s=v();const k=340.5;q('/v?vx='+(cur.v[0]*s)+'&vy='+(cur.v[1]*s)+'&wz='+(cur.v[2]*s/k));}}"
"function start(c){cur=c;send();clearInterval(timer);timer=setInterval(send,150);}"
"function stop(){cur=null;clearInterval(timer);q('/stop');}"
"function bind(b,c){b.addEventListener('pointerdown',e=>{e.preventDefault();b.classList.add('on');start(c);});"
" ['pointerup','pointerleave','pointercancel'].forEach(ev=>b.addEventListener(ev,()=>{b.classList.remove('on');if(cur)stop();}));}"
"document.querySelectorAll('button[data-v]').forEach(b=>bind(b,{v:b.dataset.v.split(',').map(Number)}));"
"document.getElementById('stop').addEventListener('pointerdown',stop);"
"const wh=document.getElementById('wheels');W.forEach((n,i)=>{const d=document.createElement('div');"
" d.innerHTML='<b>'+n+'</b><small id=ax'+i+'></small><div class=r id=r'+i+'>0</div>';"
" const up=document.createElement('button');up.textContent=n+' ▲';bind(up,{jog:[i,1]});"
" const dn=document.createElement('button');dn.textContent=n+' ▼';bind(dn,{jog:[i,-1]});"
" const iv=document.createElement('button');iv.textContent='invert';iv.id='inv'+i;iv.style.marginTop='6px';"
" iv.addEventListener('click',()=>q('/inv?w='+i));d.append(up,dn,iv);wh.append(d);});"
"document.getElementById('sp').oninput=e=>document.getElementById('spv').textContent=e.target.value;"
"document.getElementById('hold').onchange=e=>q('/en?v='+(e.target.checked?1:0));"
"document.getElementById('ms').onchange=e=>q('/ms?v='+e.target.value);"
"function show(s){W.forEach((n,i)=>{document.getElementById('ax'+i).textContent='axis '+s.map[n];"
" const r=s.rate[i];document.getElementById('r'+i).textContent=(r>0?'▲ ':r<0?'▼ ':'· ')+Math.abs(r)+' st/s';"
" document.getElementById('inv'+i).classList.toggle('on',!!s.inv[i]);});"
" document.getElementById('ms').value=s.ms;document.getElementById('sp').max=Math.floor(s.maxmm);"
" document.getElementById('st').textContent='drivers '+(s.en?'ON':'off')+(s.hold?' (hold)':'')+' · '+s.spm+' steps/mm · max '+Math.floor(s.maxmm)+' mm/s · watchdog '+(s.wd?'TRIPPED':'ok')+' · '+s.ip;}"
"setInterval(()=>{if(cur===null)q('/status');},500);q('/status');"
"</script></body></html>";

// ───────────────────────── HTTP ──────────────────────────────────
WiFiServer server(80);

float qf(const String& path, const char* key, float def) {
  int i = path.indexOf(String("?") + key + "="); if (i < 0) i = path.indexOf(String("&") + key + "=");
  if (i < 0) return def;
  i = path.indexOf('=', i) + 1;
  int e = path.indexOf('&', i); if (e < 0) e = path.length();
  return path.substring(i, e).toFloat();
}

void sendJson(WiFiClient& c) {
  c.println("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nCache-Control: no-store\r\nConnection: close\r\n");
  c.println(statusJson());
}

bool route(const String& path) {           // shared by HTTP and serial; true = handled
  if (path.startsWith("/v?"))        { setVelocity(qf(path, "vx", 0), qf(path, "vy", 0), qf(path, "wz", 0)); return true; }
  if (path.startsWith("/jog?"))      { jog((int)qf(path, "w", -1), (int)qf(path, "d", 1), qf(path, "s", 50)); return true; }
  if (path.startsWith("/stop"))      { stopAll(); return true; }
  if (path.startsWith("/inv?"))      { int w = (int)qf(path, "w", -1); if (w >= 0 && w < 4) { inv[w] ^= 1; saveSettings(); } return true; }
  if (path.startsWith("/en?"))       { holdEnable = qf(path, "v", 0) > 0.5f; return true; }
  if (path.startsWith("/ms?"))       { int m = (int)qf(path, "v", 32); if (m == 8 || m == 16 || m == 32) { microsteps = m; updateAccel(); saveSettings(); } return true; }
  if (path.startsWith("/status"))    { return true; }
  return false;
}

void handleHttp() {
  WiFiClient c = server.available();
  if (!c) return;
  c.setTimeout(100);
  String req = c.readStringUntil('\n');
  while (c.connected() && c.available()) { String h = c.readStringUntil('\n'); if (h.length() <= 1) break; }
  int s1 = req.indexOf(' '), s2 = req.indexOf(' ', s1 + 1);
  String path = (s1 > 0 && s2 > s1) ? req.substring(s1 + 1, s2) : "/";
  if (path == "/" || path.startsWith("/index")) {
    c.println("HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nConnection: close\r\n");
    c.print(PAGE);
  } else if (route(path)) {
    sendJson(c);
  } else {
    c.println("HTTP/1.1 404 Not Found\r\nConnection: close\r\n");
  }
  delay(1);
  c.stop();
}

// ───────────────────────── serial (Pi later) ─────────────────────
//   v <vx> <vy> <wz>   mm/s mm/s rad/s      j <wheel 0-3> <dir ±1> <mm/s>
//   s                  stop                 i <wheel>   toggle invert
//   e <0|1>            hold enable          m <8|16|32> microsteps        ?  status
void handleSerial() {
  static String line;
  while (Serial.available()) {
    char ch = Serial.read();
    if (ch == '\r') continue;
    if (ch != '\n') { if (line.length() < 60) line += ch; continue; }
    line.trim();
    if (line.length()) {
      char cmd = line[0]; float a = 0, b = 0, d = 0;
      char* p = (char*)line.c_str() + 1;          // newlib-nano has no float scanf: parse by hand
      a = strtof(p, &p); b = strtof(p, &p); d = strtof(p, &p);
      float sp = speedPct / 100.0f * maxMm(), wr = sp / (LX_MM + LY_MM);
      if (cmd != 'c' && cmd != '?') circleOn = false;      // any drive command cancels the circle; a status query does not
      switch (cmd) {
        case 'v': setVelocity(a, b, d); break;
        case 'f': setVelocity( sp, 0, 0); break;   case 'b': setVelocity(-sp, 0, 0); break;
        case 'l': setVelocity(0,  sp, 0); break;   case 'r': setVelocity(0, -sp, 0); break;
        case 'q': setVelocity(0, 0,  wr); break;
        case 'e': if (line.length() == 1) setVelocity(0, 0, -wr); else holdEnable = a > 0.5f; break;
        case '+': speedPct = speedPct + 10 > 100 ? 100 : speedPct + 10; break;
        case '-': speedPct = speedPct - 10 < 10 ? 10 : speedPct - 10; break;
        case 'k': kMaxSps = (a >= 60 && a <= 40000) ? a : 0; break;
        case 'V': vcut = (a >= 0 && a <= 12.0f) ? a : 0.0f; break;   // 'V <volts>' — 'b' is taken by back
        case 't': setTilt(line.length() == 1 ? TILT_PARK : (int)a); break;   // 't 90' tilt degrees, 't -1' release, bare 't' = park
        case 'I': pcaOk = pcaInit(); if (pcaOk && tiltOn) setTilt(tiltDeg); break;   // re-probe the servo board now (re-asserts only a commanded tilt)
        case 'K':                                                               // 'K 1' Ceres kinematic show, 'K 0' stop: back to the pose it started from
          if (a > 0.5f && !showOn) { showOn = true; showT0 = millis(); showLastNudge = 0; showStep = 0; showPanStart = panPos; showTiltStart = tiltOn ? tiltDeg : -1; }
          else if (a <= 0.5f && showOn) {
            showOn = false; panStop();
            float back = showPanStart - panPos; if (fabsf(back) > 20) nudgePan(back > 0 ? 1 : -1, (int)fminf(fabsf(back), 2999));
            setTilt(showTiltStart);
          }
          break;
        case 'T': panTrim = a < -150 ? -150 : a > 150 ? 150 : (int)a; break;   // 'T <µs>' pan stop-pulse trim
        case 'H': panStop(); pcaPulse(PAN_CH, 1500 + panTrim); panOn = true; panHoldUntil = millis() + ((a > 0 && a < 10000) ? (uint32_t)a : 3000); break;   // 'H <ms>' hold the stop pulse: does it creep?
        case 'p': setPan(0); break;                                                // any 'p' = stop the pan (continuous servo)      // 'p 90' pan degrees (or speed for a continuous servo), 'p -1' release
        case 'n': nudgePan((int)a, (int)b); break;                              // 'n -1 300' / 'n 1 300': continuous-rotation nudge left/right for ms
        case 'a': aSlew = (a >= 300 && a <= 400000) ? a : 0; updateAccel(); break;
        case 'c': circleR = a > 0 ? a : 300.0f; circleT = b > 0 ? b : 8.0f; circleT0 = millis(); circleOn = true; kick(); break;
        case 'j': jog((int)a, (int)b, d); break;
        case 's': stopAll(); break;
        case 'i': if (a >= 0 && a < 4) { inv[(int)a] ^= 1; saveSettings(); } break;
        case 'm': if (a == 8 || a == 16 || a == 32) { microsteps = (uint8_t)a; updateAccel(); saveSettings(); } break;
        default: break;
      }
      Serial.println(statusJson());
    }
    line = "";
  }
}

// ───────────────────────── setup / loop ──────────────────────────
void setup() {
  for (int i = 0; i < 4; i++) { pinMode(STEP_PIN[i], OUTPUT); pinMode(DIR_PIN[i], OUTPUT); digitalWrite(STEP_PIN[i], LOW); }
  pinMode(EN_PIN, OUTPUT); digitalWrite(EN_PIN, HIGH);          // drivers OFF until commanded
  pinMode(VBAT_PIN, INPUT);
  pcaOk = pcaInit();                                            // 50 Hz frame, no pulse until a command: both servos stay where they were hand-set
  Serial.begin(115200);
  loadSettings();
  updateAccel();
  timerOk = startTimer();
  if (!timerOk) Serial.println("{\"error\":\"no free GPT timer\"}");

#if ENABLE_WIFI
  if (WiFi.status() == WL_NO_MODULE) { Serial.println("{\"error\":\"no WiFi module\"}"); }
  else {
    WiFi.config(IPAddress(192, 168, 4, 1));
    if (WiFi.beginAP(AP_SSID, AP_PASS) != WL_AP_LISTENING) Serial.println("{\"error\":\"beginAP failed\"}");
    else { server.begin(); Serial.print("{\"ap\":\""); Serial.print(AP_SSID); Serial.print("\",\"url\":\"http://"); Serial.print(WiFi.localIP()); Serial.println("/\"}"); }
  }
#else
  Serial.println("{\"wifi\":\"off\",\"link\":\"usb serial 115200\"}");
#endif
}

void runCircle() {
  if (!circleOn) return;
  float t = (millis() - circleT0) / 1000.0f;
  if (t >= circleT) { circleOn = false; stopAll(); return; }
  float V = 2 * 3.14159265f * circleR / circleT, vmax = maxMm() * 0.7071f; if (V > vmax) V = vmax;
  float ramp = t / 0.8f; float tail = (circleT - t) / 0.8f; if (tail < ramp) ramp = tail; if (ramp > 1) ramp = 1; if (ramp < 0) ramp = 0;
  float ang = 2 * 3.14159265f * t / circleT;
  setVelocity(V * ramp * cosf(ang), V * ramp * sinf(ang), 0);
}

void loop() {
  { static uint32_t lastPan = 0; if (panStopAt && millis() - lastPan >= 20) { lastPan = millis(); panTick(); } }
  if (panStopAt && (int32_t)(millis() - panStopAt) >= 0) panStop();                   // end of a nudge: cut the pulse
  if (panHoldUntil && (int32_t)(millis() - panHoldUntil) >= 0) panStop();             // end of an 'H' hold test
  if (!pcaOk && (int32_t)(millis() - pcaRetryAt) >= 0) { pcaRetryAt = millis() + 2000; pcaOk = pcaInit(); if (pcaOk && tiltOn) setTilt(tiltDeg); }   // hot-plugged board: keep probing; re-assert only a commanded tilt
  if (showOn && pcaOk) {                                     // Ceres show: tilt swings about where it started, a pan turn each time the tilt passes its middle
    static uint32_t lastStep = 0; uint32_t now = millis();
    if (now - lastStep >= 20) { lastStep = now;
      float t = (now - showT0) / 1000.0f; float sn = sinf(2 * PI * t / 5.0f);
      float mid = showTiltStart >= 0 ? showTiltStart : 96.0f;                 // a limp tilt can't report its hand-set angle: 96° only then
      float swing = mid + (sn > 0 ? 20.0f : 16.0f) * sn;                     // +20 / −16° about the middle: more up, less down
      float tilt = swing < TILT_MIN ? TILT_MIN : swing > TILT_MAX ? TILT_MAX : swing;   // never below the floor — it hammered the platform at 70
      pcaPulse(TILT_CH, (int)(600.0f + tilt * 10.0f)); tiltDeg = (int)tilt; tiltOn = true;
      if (!panStopAt && fabsf(swing - mid) < 8.0f && now - showLastNudge > 1500) {   // expanding sweep: out to +1U, −2U, +3U, −4U (turns of 1, 3, 5, 7 U), then back to the start
        int k = showStep + 1;
        if (k <= SHOW_TURNS) nudgePan(k % 2 ? 1 : -1, (2 * k - 1) * SHOW_U_MS);
        else { nudgePan(SHOW_TURNS % 2 ? -1 : 1, SHOW_TURNS * SHOW_U_MS); k = 0; }
        showStep = k; showLastNudge = now; }
    }
  }
  static uint32_t lastMotionMs = 0;
  readVbat();
  if (lowVolt && anyMotion) stopAll();
  runCircle();
#if ENABLE_WIFI
  handleHttp();
#endif
  handleSerial();

  bool moving = anyMotion;
  if (moving) { lastMotionMs = millis(); digitalWrite(EN_PIN, LOW); }
  else if (holdEnable) digitalWrite(EN_PIN, LOW);
  else if (millis() - lastMotionMs > IDLE_DISABLE_MS) digitalWrite(EN_PIN, HIGH);
}
