// Host stand-in for the Arduino core, just enough to compile firmware/r4_drive unmodified and drive it from a test.
// Time is a fake millisecond clock the test advances; Serial is a queue the test writes command lines into.
#pragma once
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <string>
#include <vector>

#define HIGH 1
#define LOW 0
#define OUTPUT 1
#define INPUT 0
#define A3 17
#ifndef PI
#define PI 3.14159265358979f
#endif
typedef uint8_t byte;

extern uint32_t fake_ms;
extern int pin_state[64];
inline uint32_t millis() { return fake_ms; }
inline void delay(uint32_t ms) { fake_ms += ms; }
inline void pinMode(int, int) {}
inline void digitalWrite(int p, int v) { pin_state[p & 63] = v; }
inline int digitalRead(int p) { return pin_state[p & 63]; }
inline int analogRead(int) { return 0; }                 // no divider fitted: vbat reads 0, the low-voltage cut stays off

class String {
 public:
  std::string s;
  String() {}
  String(const char* c) : s(c ? c : "") {}
  String(const std::string& x) : s(x) {}
  String(char c) : s(1, c) {}
  unsigned length() const { return (unsigned)s.size(); }
  const char* c_str() const { return s.c_str(); }
  char operator[](unsigned i) const { return i < s.size() ? s[i] : 0; }
  String& operator+=(char c) { s += c; return *this; }
  String& operator+=(const char* c) { s += c; return *this; }
  friend String operator+(const String& a, const char* b) { return String(a.s + b); }
  friend String operator+(const String& a, const String& b) { return String(a.s + b.s); }
  bool operator==(const char* c) const { return s == c; }
  void trim() {
    size_t a = s.find_first_not_of(" \t\r\n"), b = s.find_last_not_of(" \t\r\n");
    s = a == std::string::npos ? "" : s.substr(a, b - a + 1);
  }
  int indexOf(char c, unsigned from = 0) const { size_t p = s.find(c, from); return p == std::string::npos ? -1 : (int)p; }
  int indexOf(const String& t, unsigned from = 0) const { size_t p = s.find(t.s, from); return p == std::string::npos ? -1 : (int)p; }
  String substring(unsigned a, unsigned b) const { return a >= s.size() ? String() : String(s.substr(a, b > a ? b - a : 0)); }
  String substring(unsigned a) const { return a >= s.size() ? String() : String(s.substr(a)); }
  bool startsWith(const char* p) const { return s.rfind(p, 0) == 0; }
  float toFloat() const { return strtof(s.c_str(), nullptr); }
};

struct FakeSerial {
  std::deque<char> in;
  std::string out;
  void begin(long) {}
  int available() { return (int)in.size(); }
  int read() { if (in.empty()) return -1; char c = in.front(); in.pop_front(); return c; }
  void print(const char* t) { out += t; }
  void print(const String& t) { out += t.s; }
  void println(const char* t) { out += t; out += "\n"; }
  void println(const String& t) { out += t.s; out += "\n"; }
  void println() { out += "\n"; }
};
extern FakeSerial Serial;
