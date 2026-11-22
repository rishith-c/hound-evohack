// Host stand-in for the I2C bus: the test decides who answers and records every PCA9685 channel write.
#pragma once
#include "Arduino.h"

struct TwoWire {
  uint8_t addr = 0;
  std::vector<uint8_t> buf;
  void begin() {}
  void setClock(uint32_t) {}
  void beginTransmission(uint8_t a) { addr = a; buf.clear(); }
  size_t write(uint8_t b) { buf.push_back(b); return 1; }
  uint8_t endTransmission(bool stop = true);              // defined by the test
};
extern TwoWire Wire;
