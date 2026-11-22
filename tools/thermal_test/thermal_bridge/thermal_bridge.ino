// thermal_bridge.ino — MLX90640 test bridge for a BARE Arduino UNO R3 (or UNO R4 WiFi, or any Wire board).
//
// Why a bridge: the MLX90640 needs ~3.5 kB of RAM for its calibration table plus one frame, and an UNO R3 has 2 kB,
// so no library can run the sensor on the R3 itself. Instead the Arduino forwards raw I2C reads/writes over USB
// serial and the PC (thermal_gui.py) does the calibration maths and draws the picture. Uses ~200 bytes of RAM.
//
// Wiring (Adafruit-pattern MLX90640 breakout, which has its own regulator and level shifting):
//   UNO R3:        VIN → 5V, GND → GND, SCL → A5, SDA → A4
//   UNO R4 WiFi:   VIN → 5V, GND → GND, SCL → SCL, SDA → SDA   (or plug a STEMMA QT cable into the Qwiic port and
//                  compile with USE_QWIIC 1 — the Qwiic port is Wire1)
//   Plain purple breakout with NO regulator: power it from 3.3V instead of 5V; the sketch turns the AVR's internal
//   5 V pull-ups off so the board's own 10 kΩ pull-ups to 3.3 V set the bus level.
//
// Protocol (binary, PC → Arduino):
//   'P'                                  → replies "OK"
//   'W' len bytes…                       → one I2C write of len bytes to 0x33; replies 1 status byte (0 = ok)
//   'R' addrH addrL nH nL                → reads n 16-bit words from register addr (auto-increment, 16 words per
//                                          transaction because the R3's Wire buffer is 32 bytes); replies 2n data
//                                          bytes then 1 status byte
#include <Wire.h>

#define USE_QWIIC 0
#if USE_QWIIC && defined(ARDUINO_UNOWIFIR4)
  #define BUS Wire1
#else
  #define BUS Wire
#endif

const uint8_t MLX = 0x33;
const uint8_t CHUNK = 16;                        // words per I2C transaction (32-byte Wire buffer on the R3)

static int rd() { while (!Serial.available()) {} return Serial.read(); }

void setup() {
  Serial.begin(115200);
  BUS.begin();
  BUS.setClock(400000);
#ifdef __AVR__
  digitalWrite(SDA, LOW); digitalWrite(SCL, LOW);   // disable the AVR's internal 5 V pull-ups (sensor is 3.3 V logic)
#endif
}

void loop() {
  if (!Serial.available()) return;
  int c = Serial.read();
  if (c == 'P') {
    Serial.write("OK", 2);
  } else if (c == 'W') {
    uint8_t n = rd();
    BUS.beginTransmission(MLX);
    for (uint8_t i = 0; i < n; i++) BUS.write((uint8_t)rd());
    uint8_t err = BUS.endTransmission();
    Serial.write(err);
  } else if (c == 'R') {
    uint16_t addr = ((uint16_t)rd() << 8) | rd();
    uint16_t nw = ((uint16_t)rd() << 8) | rd();
    uint8_t err = 0;
    while (nw) {
      uint8_t k = nw < CHUNK ? nw : CHUNK;
      BUS.beginTransmission(MLX);
      BUS.write((uint8_t)(addr >> 8)); BUS.write((uint8_t)(addr & 0xFF));
      if (BUS.endTransmission(false)) err = 1;                 // repeated start
      uint8_t got = BUS.requestFrom(MLX, (uint8_t)(k * 2));
      for (uint8_t i = 0; i < k * 2; i++) Serial.write(i < got ? (uint8_t)BUS.read() : (uint8_t)0);
      if (got < k * 2) err = 2;
      addr += k; nw -= k;
    }
    Serial.write(err);
  }
}
