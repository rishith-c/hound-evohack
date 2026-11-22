/*
  r4_fetch.ino — the rover drive done the way Fetch's fetch_final.ino does it: AccelStepper, velocity mode,
  slew-limited targets, reversal through zero, runtime-tunable top rate ('k') and slew ('a'), single-key teleop,
  an onboard crab circle ('c'), and a watchdog on the Uno so nothing depends on the Pi or WiFi.

  Wheel ↔ shield axis AS WIRED: FL = Y (3,6)  FR = A (12,13)  BL = X (2,5)  BR = Z (4,7)   ENABLE D8 (LOW = on)

  SERIAL 115200 — every line is answered with one status JSON
    v <vx> <vy> <wz>   mm/s forward, mm/s left, rad/s counter-clockwise (what the Pi's r4.py / web.py send)
    f b l r q e s      forward back strafe-left strafe-right rotate-left rotate-right stop, at speedPct
    + -                speedPct ±10
    k <steps/s>        top wheel rate (Fetch: sweep this to find the quiet band)      a <steps/s²>  slew
    j <wheel 0-3> <dir ±1> <mm/s>   one wheel          c [radius_mm] [seconds]   crab circle, body heading fixed
    i <wheel>  invert (EEPROM)      m <8|16|32> microsteps (must match the caps)      e <0|1> hold drivers      ?  status
  Watchdog: v/j/keys stop after 400 ms of silence. Crab circle is self-contained and aborts on any byte.
*/
#include <AccelStepper.h>
#include <EEPROM.h>
#include <math.h>

enum { FL = 0, FR = 1, BL = 2, BR = 3 };
const char*   AXIS[4] = { "Y", "A", "X", "Z" };
AccelStepper st[4] = { AccelStepper(AccelStepper::DRIVER, 3, 6), AccelStepper(AccelStepper::DRIVER, 12, 13),
                       AccelStepper(AccelStepper::DRIVER, 2, 5), AccelStepper(AccelStepper::DRIVER, 4, 7) };
const int EN_PIN = 8;

const float WHEEL_D_MM = 80.0f; const int FULL_STEPS = 200;
const float LX_MM = 125.0f, LY_MM = 215.5f;         // half wheelbase, half track
const float V_MAX_MM = 800.0f;                      // physics ceiling (84 % of the 1.5 A corner speed)
const uint32_t WATCHDOG_MS = 400, IDLE_DISABLE_MS = 3000;

uint8_t microsteps = 32, inv[4] = {0,0,0,0}; bool holdEnable = false;
float MAX_SPS = 20000.0f;          // 'k' — AccelStepper ceiling per wheel; the achieved rate is measured and reported
float SLEW_SPS_PER_S = 0;          // 'a' — 0 = derive from ACCEL_MM_S2 at the current microsteps
const float ACCEL_MM_S2 = 600.0f;
int speedPct = 60;
float tgt[4] = {0,0,0,0}, cur[4] = {0,0,0,0};
uint32_t lastCmdMs = 0, lastMotionMs = 0, lastSlewUs = 0; bool wdTripped = false, vMode = false;
uint32_t stepCount[4] = {0,0,0,0}, achieved[4] = {0,0,0,0}, loops = 0, loopsPerS = 0;
char line[48]; byte lineLen = 0;

float spm()   { return FULL_STEPS * (float)microsteps / (3.14159265f * WHEEL_D_MM); }
float slew()  { return SLEW_SPS_PER_S > 0 ? SLEW_SPS_PER_S : ACCEL_MM_S2 * spm(); }
float capSps(){ float c = V_MAX_MM * spm(); return c < MAX_SPS ? c : MAX_SPS; }
float maxMm() { return capSps() / spm(); }
void kick()   { lastCmdMs = millis(); wdTripped = false; vMode = true; }

// Fetch's mix, in this rover's sign convention (vy = left, wz = counter-clockwise)
void setVel(float vx, float vy, float wz) {
  const float k = LX_MM + LY_MM;
  float w[4] = { vx - vy - wz * k, vx + vy + wz * k, vx + vy - wz * k, vx - vy + wz * k };
  float s = spm(), cap = capSps(), mx = 0;
  for (int i = 0; i < 4; i++) { w[i] *= s; if (fabsf(w[i]) > mx) mx = fabsf(w[i]); }
  if (mx > cap) for (int i = 0; i < 4; i++) w[i] *= cap / mx;     // normalise, never clip one wheel (Fetch)
  for (int i = 0; i < 4; i++) tgt[i] = w[i];
  kick();
}
void jog(int wh, int dir, float mmps) { for (int i = 0; i < 4; i++) tgt[i] = 0; float r = mmps * spm(); if (r > capSps()) r = capSps(); if (wh >= 0 && wh < 4) tgt[wh] = dir < 0 ? -r : r; kick(); }
void stopAll() { for (int i = 0; i < 4; i++) tgt[i] = 0; lastCmdMs = millis(); wdTripped = false; vMode = false; }

// Fetch's applySlew: a reversal drops to zero first; slowing is instant; speeding up is rate-limited.
void applySlew() {
  uint32_t now = micros(); float dt = (now - lastSlewUs) / 1000000.0f; lastSlewUs = now;
  if (dt <= 0 || dt > 0.25f) dt = 0.001f;
  float step = slew() * dt; bool moving = false;
  for (int i = 0; i < 4; i++) {
    float t = tgt[i], c = cur[i];
    bool opposing = (t > 0 && c < 0) || (t < 0 && c > 0);
    if (opposing) c = 0;
    else if (fabsf(t) <= fabsf(c)) c = t;
    else if (t - c > step) c += step;
    else if (t - c < -step) c -= step;
    else c = t;
    if (c != cur[i]) { cur[i] = c; st[i].setSpeed(c); }
    if (c != 0) moving = true;
  }
  uint32_t ms = millis();
  if (moving) { lastMotionMs = ms; digitalWrite(EN_PIN, LOW); }
  else if (holdEnable) digitalWrite(EN_PIN, LOW);
  else if (ms - lastMotionMs > IDLE_DISABLE_MS) digitalWrite(EN_PIN, HIGH);
}
void runAll() { for (int i = 0; i < 4; i++) if (cur[i] != 0 && st[i].runSpeed()) stepCount[i]++; loops++; }

const int EE_MAGIC = 0x5A;
void loadSettings() { if (EEPROM.read(0) != EE_MAGIC) return; for (int i = 0; i < 4; i++) inv[i] = EEPROM.read(1+i) ? 1 : 0; uint8_t m = EEPROM.read(5); if (m == 8 || m == 16 || m == 32) microsteps = m; }
void saveSettings() { EEPROM.write(0, EE_MAGIC); for (int i = 0; i < 4; i++) EEPROM.write(1+i, inv[i]); EEPROM.write(5, microsteps); }

char jsonBuf[520];
void report() {
  snprintf(jsonBuf, sizeof(jsonBuf),
    "{\"map\":{\"FL\":\"%s\",\"FR\":\"%s\",\"BL\":\"%s\",\"BR\":\"%s\"},\"target\":[%ld,%ld,%ld,%ld],\"rate\":[%ld,%ld,%ld,%ld],"
    "\"achieved\":[%lu,%lu,%lu,%lu],\"loops\":%lu,\"inv\":[%d,%d,%d,%d],\"en\":%d,\"hold\":%d,\"wd\":%d,\"ms\":%d,\"spm\":%.2f,\"maxmm\":%.0f,"
    "\"k\":%.0f,\"a\":%.0f,\"pct\":%d,\"tmr\":1,\"ticks\":%lu,\"ip\":\"fetch-style\"}",
    AXIS[0], AXIS[1], AXIS[2], AXIS[3], (long)tgt[0], (long)tgt[1], (long)tgt[2], (long)tgt[3], (long)cur[0], (long)cur[1], (long)cur[2], (long)cur[3],
    (unsigned long)achieved[0], (unsigned long)achieved[1], (unsigned long)achieved[2], (unsigned long)achieved[3], (unsigned long)loopsPerS,
    inv[0], inv[1], inv[2], inv[3], digitalRead(EN_PIN) == LOW, holdEnable ? 1 : 0, wdTripped ? 1 : 0, microsteps, spm(), maxMm(), MAX_SPS, slew(), speedPct, (unsigned long)millis());
  Serial.println(jsonBuf);
}

void crabCircle(float radius_mm, float seconds) {          // Fetch's crab circle, body heading fixed, eased in and out
  delay(5); while (Serial.available()) Serial.read();
  float V = 2 * M_PI * radius_mm / seconds; if (V > maxMm() * 0.7071f) V = maxMm() * 0.7071f;   // keep the diagonal pair inside the cap
  const float ramp_s = 0.8f; uint32_t t0 = micros();
  while ((micros() - t0) < (uint32_t)(seconds * 1e6f)) {
    float t = (micros() - t0) / 1e6f, ang = 2 * M_PI * t / seconds;
    float ramp = fminf(1.0f, fminf(t / ramp_s, (seconds - t) / ramp_s)); if (ramp < 0) ramp = 0;
    setVel(V * ramp * cosf(ang), V * ramp * sinf(ang), 0);
    uint32_t slice = millis(); while (millis() - slice < 5) { applySlew(); runAll(); }
    if (Serial.available()) break;                          // any byte aborts; loop() parses it so STOP works
  }
  stopAll();
}

void handleLine() {
  line[lineLen] = 0; char c = line[0]; char* p = line + 1;
  float a = strtof(p, &p), b = strtof(p, &p), d = strtof(p, &p);        // newlib-nano: no %f in scanf
  float s = speedPct / 100.0f * maxMm(), wz = s / (LX_MM + LY_MM);
  switch (c) {
    case 'v': setVel(a, b, d); break;
    case 'f': setVel( s, 0, 0); break;   case 'b': setVel(-s, 0, 0); break;
    case 'l': setVel(0,  s, 0); break;   case 'r': setVel(0, -s, 0); break;
    case 'q': setVel(0, 0,  wz); break;  case 'e': if (lineLen == 1) { setVel(0, 0, -wz); } else { holdEnable = a > 0.5f; } break;
    case 's': stopAll(); break;
    case '+': speedPct = speedPct + 10 > 100 ? 100 : speedPct + 10; break;
    case '-': speedPct = speedPct - 10 < 10 ? 10 : speedPct - 10; break;
    case 'k': if (a >= 60 && a <= 40000) MAX_SPS = a; break;
    case 'a': if (a >= 300 && a <= 200000) SLEW_SPS_PER_S = a; break;
    case 'j': jog((int)a, (int)b, d); break;
    case 'i': if (a >= 0 && a < 4) { inv[(int)a] ^= 1; st[(int)a].setPinsInverted(inv[(int)a] != 0, false, false); saveSettings(); } break;
    case 'm': if (a == 8 || a == 16 || a == 32) { microsteps = (uint8_t)a; saveSettings(); } break;
    case 'c': report(); crabCircle(a > 0 ? a : 300.0f, b > 0 ? b : 8.0f); break;
    default: break;
  }
  report();
}

void setup() {
  Serial.begin(115200);
  pinMode(EN_PIN, OUTPUT); digitalWrite(EN_PIN, HIGH);
  loadSettings();
  for (int i = 0; i < 4; i++) { st[i].setMaxSpeed(40000); st[i].setMinPulseWidth(2); st[i].setPinsInverted(inv[i] != 0, false, false); }
  Serial.println("{\"build\":\"fetch-style accelstepper\",\"link\":\"usb serial 115200\"}");
}

void loop() {
  static uint32_t lastSecMs = 0;
  while (Serial.available()) {
    char ch = Serial.read(); if (ch == '\r') continue;
    if (ch == '\n') { if (lineLen) handleLine(); lineLen = 0; }
    else if (lineLen < sizeof(line) - 1) line[lineLen++] = ch;
  }
  if (vMode && millis() - lastCmdMs > WATCHDOG_MS) { bool had = false; for (int i = 0; i < 4; i++) { if (tgt[i] != 0) had = true; tgt[i] = 0; } if (had) wdTripped = true; vMode = false; }
  applySlew(); runAll();
  if (millis() - lastSecMs >= 1000) { lastSecMs = millis(); for (int i = 0; i < 4; i++) { achieved[i] = stepCount[i]; stepCount[i] = 0; } loopsPerS = loops; loops = 0; }
}
