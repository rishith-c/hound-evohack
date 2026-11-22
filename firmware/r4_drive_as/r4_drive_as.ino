/*
  r4_drive_as.ino — same rover drive as r4_drive, built on the AccelStepper library instead of a timer ISR.
  Same serial protocol, same wheel map (FL=Y, FR=A, BL=X, BR=Z), same status JSON (plus "achieved" = steps/s
  actually produced per wheel in the last second, so the two builds can be compared honestly).

  Velocity mode: each wheel is an AccelStepper(DRIVER) driven with setSpeed()/runSpeed(); the ramp (600 mm/s²)
  is applied here at 1 kHz because AccelStepper's own acceleration is for position moves, not velocity.
  Steps happen only when loop() calls runSpeed(), so serial work steals steps at high rates — that is the trade.
*/
#include <AccelStepper.h>
#include <EEPROM.h>

enum { FL = 0, FR = 1, BL = 2, BR = 3 };
const char*   AXIS[4]     = { "Y",  "A",  "X",  "Z"  };
const uint8_t STEP_PIN[4] = {  3,   12,    2,    4  };
const uint8_t DIR_PIN[4]  = {  6,   13,    5,    7  };
const uint8_t EN_PIN      = 8;

const float WHEEL_D_MM = 80.0f; const int FULL_STEPS = 200;
const float LX_MM = 125.0f, LY_MM = 215.5f;
const float V_MAX_MM = 800.0f;
const float ACCEL_MM_S2 = 600.0f;
const float MAX_RATE = 20000.0f;              // AccelStepper ceiling; what it really achieves is measured, see "achieved"
const uint32_t WATCHDOG_MS = 400, IDLE_DISABLE_MS = 3000;

AccelStepper st[4] = { AccelStepper(AccelStepper::DRIVER, 3, 6), AccelStepper(AccelStepper::DRIVER, 12, 13),
                       AccelStepper(AccelStepper::DRIVER, 2, 5), AccelStepper(AccelStepper::DRIVER, 4, 7) };

uint8_t microsteps = 32, inv[4] = {0, 0, 0, 0}; bool holdEnable = false;
float targetRate[4] = {0, 0, 0, 0}, curRate[4] = {0, 0, 0, 0};
uint32_t lastCmdMs = 0, lastMotionMs = 0; bool wdTripped = false;
uint32_t stepCount[4] = {0, 0, 0, 0}, achieved[4] = {0, 0, 0, 0}, loops = 0, loopsPerS = 0;

float stepsPerMm() { return FULL_STEPS * (float)microsteps / (3.14159265f * WHEEL_D_MM); }
float maxMm() { float m = MAX_RATE / stepsPerMm(); return m < V_MAX_MM ? m : V_MAX_MM; }
void kick() { lastCmdMs = millis(); wdTripped = false; }

void setVelocity(float vx, float vy, float wz) {
  const float k = LX_MM + LY_MM; float w[4] = { vx - vy - wz * k, vx + vy + wz * k, vx + vy - wz * k, vx - vy + wz * k };
  const float spm = stepsPerMm(), cap = maxMm() * spm; float scale = 1.0f;
  for (int i = 0; i < 4; i++) { float s = fabsf(w[i]) * spm; if (s > cap) { float f = cap / s; if (f < scale) scale = f; } }
  for (int i = 0; i < 4; i++) targetRate[i] = w[i] * spm * scale;
  kick();
}
void jog(int wheel, int dir, float mmps) {
  float r = mmps * stepsPerMm(), cap = maxMm() * stepsPerMm(); if (r > cap) r = cap;
  for (int i = 0; i < 4; i++) targetRate[i] = 0;
  if (wheel >= 0 && wheel < 4) targetRate[wheel] = dir < 0 ? -r : r;
  kick();
}
void stopAll() { for (int i = 0; i < 4; i++) targetRate[i] = 0; kick(); }

const int EE_MAGIC = 0x5A;
void loadSettings() { if (EEPROM.read(0) != EE_MAGIC) return; for (int i = 0; i < 4; i++) inv[i] = EEPROM.read(1 + i) ? 1 : 0; uint8_t m = EEPROM.read(5); if (m == 8 || m == 16 || m == 32) microsteps = m; }
void saveSettings() { EEPROM.write(0, EE_MAGIC); for (int i = 0; i < 4; i++) EEPROM.write(1 + i, inv[i]); EEPROM.write(5, microsteps); }

char jsonBuf[480];
const char* statusJson() {
  snprintf(jsonBuf, sizeof(jsonBuf),
    "{\"map\":{\"FL\":\"%s\",\"FR\":\"%s\",\"BL\":\"%s\",\"BR\":\"%s\"},\"target\":[%ld,%ld,%ld,%ld],\"rate\":[%ld,%ld,%ld,%ld],"
    "\"achieved\":[%lu,%lu,%lu,%lu],\"loops\":%lu,\"inv\":[%d,%d,%d,%d],\"en\":%d,\"hold\":%d,\"wd\":%d,\"ms\":%d,\"spm\":%.2f,\"maxmm\":%.0f,"
    "\"tmr\":1,\"ticks\":%lu,\"ip\":\"accelstepper\"}",
    AXIS[0], AXIS[1], AXIS[2], AXIS[3], (long)targetRate[0], (long)targetRate[1], (long)targetRate[2], (long)targetRate[3],
    (long)curRate[0], (long)curRate[1], (long)curRate[2], (long)curRate[3], (unsigned long)achieved[0], (unsigned long)achieved[1],
    (unsigned long)achieved[2], (unsigned long)achieved[3], (unsigned long)loopsPerS, inv[0], inv[1], inv[2], inv[3],
    digitalRead(EN_PIN) == LOW, holdEnable ? 1 : 0, wdTripped ? 1 : 0, microsteps, stepsPerMm(), maxMm(), (unsigned long)millis());
  return jsonBuf;
}

void handleSerial() {
  static String line;
  while (Serial.available()) {
    char ch = Serial.read(); if (ch == '\r') continue;
    if (ch != '\n') { if (line.length() < 60) line += ch; continue; }
    line.trim();
    if (line.length()) {
      char cmd = line[0]; char* p = (char*)line.c_str() + 1; float a = strtof(p, &p), b = strtof(p, &p), d = strtof(p, &p);
      switch (cmd) {
        case 'v': setVelocity(a, b, d); break;
        case 'j': jog((int)a, (int)b, d); break;
        case 's': stopAll(); break;
        case 'i': if (a >= 0 && a < 4) { inv[(int)a] ^= 1; saveSettings(); } break;
        case 'e': holdEnable = a > 0.5f; break;
        case 'm': if (a == 8 || a == 16 || a == 32) { microsteps = (uint8_t)a; saveSettings(); } break;
        default: break;
      }
      Serial.println(statusJson());
    }
    line = "";
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(EN_PIN, OUTPUT); digitalWrite(EN_PIN, HIGH);
  loadSettings();
  for (int i = 0; i < 4; i++) { st[i].setMaxSpeed(MAX_RATE); st[i].setMinPulseWidth(3); st[i].setPinsInverted(inv[i] != 0, false, false); }
  Serial.println("{\"build\":\"accelstepper\",\"link\":\"usb serial 115200\"}");
}

void loop() {
  static uint32_t lastSlewMs = 0, lastSecMs = 0;
  uint32_t now = millis();
  handleSerial();

  if (now - lastCmdMs > WATCHDOG_MS) { bool had = false; for (int i = 0; i < 4; i++) { if (targetRate[i] != 0) had = true; targetRate[i] = 0; } if (had) wdTripped = true; }

  if (now != lastSlewMs) {                       // 1 kHz ramp
    float d = ACCEL_MM_S2 * stepsPerMm() / 1000.0f * (float)(now - lastSlewMs); lastSlewMs = now;
    bool moving = false;
    for (int i = 0; i < 4; i++) {
      float t = targetRate[i], c = curRate[i];
      if (c < t) { c += d; if (c > t) c = t; } else if (c > t) { c -= d; if (c < t) c = t; }
      if (c != curRate[i]) { curRate[i] = c; st[i].setSpeed(c); }
      if (c != 0) moving = true;
    }
    if (moving) { lastMotionMs = now; digitalWrite(EN_PIN, LOW); }
    else if (holdEnable) digitalWrite(EN_PIN, LOW);
    else if (now - lastMotionMs > IDLE_DISABLE_MS) digitalWrite(EN_PIN, HIGH);
  }

  for (int i = 0; i < 4; i++) if (curRate[i] != 0 && st[i].runSpeed()) stepCount[i]++;
  loops++;
  if (now - lastSecMs >= 1000) { lastSecMs = now; for (int i = 0; i < 4; i++) { achieved[i] = stepCount[i]; stepCount[i] = 0; } loopsPerS = loops; loops = 0; }
}
