// Host test of firmware/r4_drive, compiled from arduino-cli's own preprocessed sketch (R4_SKETCH) against the stand-ins
// in shim/. The firmware is driven only the way the Pi drives it — serial command lines — and observed through what
// reaches the PCA9685 (every channel write is recorded) and its status JSON. Run by tests/test_firmware.py.
#include "Arduino.h"
#include "Wire.h"
#include "EEPROM.h"
#include "WiFiS3.h"

uint32_t fake_ms = 0;
int pin_state[64];
FakeSerial Serial;
TwoWire Wire;
FakeEEPROM EEPROM;
WiFiClass WiFi;

struct Pulse { uint32_t t; int ch; int us; };
std::vector<Pulse> pulses;
bool pca_present = true;

uint8_t TwoWire::endTransmission(bool) {
  if (addr == 0x40 && buf.size() == 5 && buf[0] >= 6 && buf[0] < 6 + 4 * 16) {
    int off = buf[3] | ((buf[4] & 0x0F) << 8);
    pulses.push_back({fake_ms, (buf[0] - 6) / 4, (buf[4] & 0x10) ? 0 : (int)lround(off * 20000.0 / 4096.0)});
  }
  return ((addr == 0x40 || addr == 0x70) && pca_present) ? 0 : 2;
}

#include R4_SKETCH

// ── harness ───────────────────────────────────────────────────────────────────────────────────────────────────
static int failures = 0, checks = 0;
#define CHECK(cond, ...) do { checks++; if (!(cond)) { failures++; printf("FAIL %s:%d  " #cond "  ", __FILE__, __LINE__); printf(__VA_ARGS__); printf("\n"); } } while (0)

static void run_ms(uint32_t ms, bool isr = false) {        // loop() every ms; the 30 kHz step ISR too when asked
  for (uint32_t i = 0; i < ms; i++) {
    fake_ms++;
    if (isr) for (int k = 0; k < TICK_HZ / 1000; k++) stepIsr(nullptr);
    loop();
  }
}
static void send(const char* line);
static void drive_ms(uint32_t ms, const char* cmd) {        // the Pi's keepalive: re-send the command every 100 ms
  for (uint32_t t = 0; t < ms; t += 100) { send(cmd); run_ms(ms - t < 100 ? ms - t : 100, true); }
}
static void send(const char* line) { for (const char* p = line; *p; p++) Serial.in.push_back(*p); Serial.in.push_back('\n'); loop(); }
static std::vector<Pulse> on(int ch, uint32_t from = 0) { std::vector<Pulse> v; for (auto& p : pulses) if (p.ch == ch && p.t >= from) v.push_back(p); return v; }
static int last_us(int ch) { auto v = on(ch); return v.empty() ? -1 : v.back().us; }
static bool near(float a, float b, float tol) { return fabsf(a - b) <= tol; }
static const int US_TOL = 6;                               // the PCA9685's 4.9 µs count, both ways

// Pan travel is booked as eased-nudge milliseconds; returns panPos once any running nudge has finished.
static float settle_pan() { for (int i = 0; i < 4000 && (panStopAt || panHoldUntil); i++) run_ms(1); return panPos; }

int main() {
  setup();
  // 1. Nothing is driven at boot: the turret starts where it was set by hand.
  CHECK(pcaOk, "the servo board should answer at 0x40");
  CHECK(on(TILT_CH).empty() && on(PAN_CH).empty(), "boot sent %zu tilt / %zu pan pulses", on(TILT_CH).size(), on(PAN_CH).size());

  // 2. A right nudge: eased pulses on one side of the stop pulse, then cut; travel booked as +300.
  uint32_t t0 = fake_ms;
  send("n 1 300"); run_ms(400);
  auto n = on(PAN_CH, t0);
  int lo = 5000, hi = 0; for (auto& p : n) if (p.us) { lo = p.us < lo ? p.us : lo; hi = p.us > hi ? p.us : hi; }
  CHECK(!n.empty() && n.back().us == 0, "a nudge must end with the pulse cut");
  CHECK(PAN_SIGN * (lo - 1500) >= 0 && PAN_SIGN * (hi - 1500) >= 0, "a right nudge drove %d–%d µs: both must sit on the PAN_SIGN side of 1500", lo, hi);
  CHECK(near(PAN_SIGN < 0 ? lo : hi, 1500 + PAN_SIGN * 250, 12), "peak of the eased nudge %d", PAN_SIGN < 0 ? lo : hi);
  CHECK(near(panPos, 300, 1), "panPos %.1f after +300", panPos);

  // 3. The same nudge left returns the books to zero.
  send("n -1 300"); CHECK(near(settle_pan(), 0, 1), "panPos %.1f after -300", panPos);

  // 4. A nudge cut short by another is booked by the share of the eased profile actually done (half the time = half).
  send("n 1 1000"); run_ms(500); send("n -1 300");
  CHECK(near(settle_pan(), 500 - 300, 8), "interrupted nudge booked %.1f, want 200", panPos);
  send("n -1 200"); settle_pan();                           // back to 0

  // 5. Trim moves the stop pulse; the hold test holds it, then cuts it.
  send("T 20"); send("H 1000");
  CHECK(near(last_us(PAN_CH), 1520, US_TOL), "hold pulse %d, want 1520", last_us(PAN_CH));
  run_ms(1100); CHECK(last_us(PAN_CH) == 0, "hold must end with the pulse cut");
  send("T 0");

  // 6. The show about a held tilt of 100°: pan turns +1U, -2U, +3U, -4U, 0 (U = 250 ms) at the tilt's middle crossings;
  //    tilt swings +20/-16° about 100 and never leaves 78-150.
  send("t 100"); CHECK(near(last_us(TILT_CH), 1600, US_TOL), "t 100 → %d µs", last_us(TILT_CH));
  float start = panPos; std::vector<float> ends; uint32_t s0 = fake_ms;
  send("K 1");
  bool was = false;
  for (int i = 0; i < 20000 && ends.size() < 6; i++) { run_ms(1); bool now = panStopAt != 0; if (was && !now) ends.push_back(panPos - start); was = now; }
  float want[6] = {250, -500, 750, -1000, 0, 250};
  CHECK(ends.size() == 6, "only %zu turns in 20 s", ends.size());
  for (size_t i = 0; i < ends.size(); i++) CHECK(near(ends[i], want[i], 2), "turn %zu ends at %.1f, want %.0f", i + 1, ends[i], want[i]);
  int tmin = 5000, tmax = 0; for (auto& p : on(TILT_CH, s0)) if (p.us) { tmin = p.us < tmin ? p.us : tmin; tmax = p.us > tmax ? p.us : tmax; }
  CHECK(tmin >= 600 + 10 * TILT_MIN - US_TOL && tmax <= 600 + 10 * TILT_MAX + US_TOL, "tilt %d–%d µs outside the limits", tmin, tmax);
  CHECK(near(tmax, 600 + 10 * 120, 12) && near(tmin, 600 + 10 * 84, 12), "tilt swing %d–%d µs, want 1440–1800", tmin, tmax);

  // 7. Stopping mid-show puts the pan back where the show started and the tilt back to 100°.
  run_ms(900);
  send("K 0"); settle_pan();
  CHECK(near(panPos, start, 3), "after K 0 the pan is %.1f from its start", panPos - start);
  CHECK(near(last_us(TILT_CH), 1600, US_TOL), "tilt after the show %d µs, want 1600", last_us(TILT_CH));

  // 8. A show started from a limp tilt swings about 96° and leaves the tilt limp again.
  send("t -1"); CHECK(last_us(TILT_CH) == 0, "t -1 must release the tilt");
  uint32_t s1 = fake_ms; send("K 1"); run_ms(5000); send("K 0"); settle_pan();
  int m0 = 5000, m1 = 0; for (auto& p : on(TILT_CH, s1)) if (p.us) { m0 = p.us < m0 ? p.us : m0; m1 = p.us > m1 ? p.us : m1; }
  CHECK(near(m1, 600 + 10 * 116, 12) && near(m0, 600 + 10 * 80, 12), "limp-start swing %d–%d µs, want 1400–1760", m0, m1);
  CHECK(last_us(TILT_CH) == 0, "a limp tilt must be left limp, got %d µs", last_us(TILT_CH));

  // 9. Drive (frozen v1.0 behaviour): body ramp 600 mm/s² up and 3× down, and the 400 ms watchdog.
  drive_ms(100, "v 300 0 0");
  CHECK(near(cVx, 60, 3), "after 100 ms speeding up cVx = %.1f mm/s, want 60", cVx);
  drive_ms(500, "v 300 0 0");
  CHECK(near(cVx, 300, 1), "cruise cVx = %.1f", cVx);
  send("v 0 0 0"); run_ms(50, true);
  CHECK(near(cVx, 300 - 1.8f * 50, 3), "after 50 ms slowing cVx = %.1f mm/s, want 210", cVx);
  send("v 200 0 0"); run_ms(300, true);
  CHECK(!wdTripped, "watchdog tripped early");
  run_ms(150, true);                                                   // 450 ms since the last command
  CHECK(wdTripped && tVx == 0, "the R4 must stop itself 400 ms after the Pi goes quiet");

  // 11. The rest of the frozen drive's commands: jog one wheel, invert (saved, survives a reset), microsteps keep the
  //     ramp in mm/s², and any drive command cancels the crab circle.
  send("s"); run_ms(700, true);
  send("j 1 1 60");
  CHECK(!bodyMode && near(targetRate[FR], 60 * stepsPerMm(), 1) && targetRate[FL] == 0 && targetRate[BL] == 0 && targetRate[BR] == 0,
        "jog FR: targets %d %d %d %d", (int)targetRate[0], (int)targetRate[1], (int)targetRate[2], (int)targetRate[3]);
  send("j 2 1 60"); run_ms(50, true);
  CHECK(pin_state[DIR_PIN[BL]] == HIGH, "BL forward drives DIR high");
  send("i 2"); send("j 2 1 60"); run_ms(50, true);
  CHECK(inv[BL] == 1 && pin_state[DIR_PIN[BL]] == LOW, "an inverted BL drives DIR low for the same command");
  CHECK(EEPROM.m[0] == EE_MAGIC && EEPROM.m[1 + BL] == 1, "invert must be saved to EEPROM");
  inv[BL] = 0; loadSettings(); CHECK(inv[BL] == 1, "invert survives a reset");
  send("i 2"); CHECK(inv[BL] == 0, "i toggles back");
  send("s"); run_ms(700, true);
  send("m 16");
  CHECK(microsteps == 16 && near(stepsPerMm(), 200 * 16 / (3.14159265f * 80), 0.01f), "m 16 → %.2f steps/mm", stepsPerMm());
  CHECK(near(accelSteps / stepsPerMm(), ACCEL_MM_S2, 1), "the ramp stays %.0f mm/s² at 1/16", accelSteps / stepsPerMm());
  send("m 32"); CHECK(microsteps == 32 && EEPROM.m[5] == 32, "back to 1/32, saved");
  send("c 300 8"); run_ms(200, false);
  CHECK(circleOn && (tVx != 0 || tVy != 0), "the crab circle drives the body vector");
  send("s"); CHECK(!circleOn, "any drive command cancels the circle");
  run_ms(700, true);

  // 10. The status JSON the Pi parses must never be truncated by jsonBuf: typical, then every field at its widest.
  printf("STATUS %s\n", statusJson());
  i2cN = 8; for (int i = 0; i < 8; i++) i2cFound[i] = 0x40 + i;
  for (int i = 0; i < 4; i++) { targetRate[i] = -MAX_RATE; curRate[i] = -MAX_RATE; inv[i] = 1; }
  isrTicks = 4294967295u; panPos = -9.99e8f; panDeg = -32768; panTrim = -150; tiltDeg = 150; vbat = 12.6f; vcut = 10.5f;
  accelSteps = 400000; kMaxSps = 40000; speedPct = 100;
  const char* j = statusJson();
  CHECK(strlen(j) < sizeof(jsonBuf) - 1 && j[strlen(j) - 1] == '}', "worst-case status is %zu of %zu bytes — truncated", strlen(j), sizeof(jsonBuf));
  printf("STATUS %s\n", j);

  printf("%d checks, %d failed\n", checks, failures);
  return failures ? 1 : 0;
}
