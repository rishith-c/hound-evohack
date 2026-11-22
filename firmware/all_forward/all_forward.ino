/*
  all_forward.ino — the simplest possible test: every wheel rolls forward, forever.
  UNO R4 WiFi + CNC Shield V3 + 4× DRV8825.  No WiFi, no GUI.
  Wheel ↔ axis as wired today: FL = Y, FR = A, BL = X, BR = Z.
  USB first, THEN the pack on VMOT. Wheels up on a box.
  Watch each wheel: any that rolls backward gets its DIR flipped in DIR_LEVEL below.
*/
#include "FspTimer.h"

const uint8_t STEP_PIN[4] = { 3, 12, 2, 4 };   // FL(Y) FR(A) BL(X) BR(Z)
const uint8_t DIR_PIN[4]  = { 6, 13, 5, 7 };
const uint8_t DIR_LEVEL[4] = { HIGH, HIGH, LOW, HIGH };   // FL, FR, BL, BR    // FL and BL flipped after the first bench run   // flip to LOW for any wheel that runs backward
const uint8_t EN_PIN = 8;

const int32_t TICK_HZ = 20000;
const int32_t TARGET  = 1600;     // steps/s ≈ 63 mm/s at 1/32 (0.25 wheel rev/s); 125 mm/s at 1/16
const int32_t ACCEL   = 4000;     // steps/s²: reaches TARGET in 0.4 s

volatile int32_t rate = 0;
volatile uint32_t acc = 0;
volatile uint8_t high = 0;
FspTimer t;

void isr(timer_callback_args_t*) {
  static uint16_t ms = 0;
  if (++ms >= TICK_HZ / 1000) { ms = 0; if (rate < TARGET) { rate += ACCEL / 1000; if (rate > TARGET) rate = TARGET; } }
  if (high) { for (int i = 0; i < 4; i++) digitalWrite(STEP_PIN[i], LOW); high = 0; }
  uint32_t a = acc + (uint32_t)rate * (uint32_t)(4294967296.0 / TICK_HZ);
  if (a < acc) { for (int i = 0; i < 4; i++) digitalWrite(STEP_PIN[i], HIGH); high = 1; }
  acc = a;
}

void setup() {
  Serial.begin(115200);
  for (int i = 0; i < 4; i++) {
    pinMode(STEP_PIN[i], OUTPUT); digitalWrite(STEP_PIN[i], LOW);
    pinMode(DIR_PIN[i], OUTPUT);  digitalWrite(DIR_PIN[i], DIR_LEVEL[i]);
  }
  pinMode(EN_PIN, OUTPUT); digitalWrite(EN_PIN, LOW);      // drivers ON
  uint8_t type = GPT_TIMER;
  int8_t ch = FspTimer::get_available_timer(type);
  if (ch < 0) ch = FspTimer::get_available_timer(type, true);
  t.begin(TIMER_MODE_PERIODIC, type, ch, (float)TICK_HZ, 0.0f, isr);
  t.setup_overflow_irq(); t.open(); t.start();
}

void loop() {
  Serial.print("build 5 · rate "); Serial.print(rate); Serial.print(" steps/s · DIR FL(D6)="); Serial.print(DIR_LEVEL[0] ? "HIGH" : "LOW");
  Serial.print(" FR(D13)="); Serial.print(DIR_LEVEL[1] ? "HIGH" : "LOW"); Serial.print(" BL(D5)="); Serial.print(DIR_LEVEL[2] ? "HIGH" : "LOW");
  Serial.print(" BR(D7)="); Serial.println(DIR_LEVEL[3] ? "HIGH" : "LOW");
  delay(1000);
}
