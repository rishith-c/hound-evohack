#pragma once
#include "Arduino.h"

struct FakeEEPROM {
  uint8_t m[1024] = {0};
  uint8_t read(int a) { return m[a & 1023]; }
  void write(int a, uint8_t v) { m[a & 1023] = v; }
};
extern FakeEEPROM EEPROM;
