// Host stand-in for the UNO R4 WiFi library. The rover builds with ENABLE_WIFI 0, but the HTTP handler still compiles.
#pragma once
#include "Arduino.h"

#define WL_NO_MODULE 255
#define WL_AP_LISTENING 7

struct IPAddress {
  uint8_t a[4] = {0, 0, 0, 0};
  IPAddress() {}
  IPAddress(int w, int x, int y, int z) { a[0] = w; a[1] = x; a[2] = y; a[3] = z; }
  String toString() const { char b[20]; snprintf(b, sizeof b, "%d.%d.%d.%d", a[0], a[1], a[2], a[3]); return String(b); }
};
struct WiFiClient {
  explicit operator bool() const { return false; }
  void setTimeout(int) {}
  String readStringUntil(char) { return String(); }
  bool connected() { return false; }
  int available() { return 0; }
  void print(const char*) {}
  void println(const char*) {}
  void println(const String&) {}
  void stop() {}
};
struct WiFiServer {
  explicit WiFiServer(int) {}
  WiFiClient available() { return WiFiClient(); }
  void begin() {}
};
struct WiFiClass {
  int status() { return WL_NO_MODULE; }
  void config(IPAddress) {}
  int beginAP(const char*, const char*) { return 0; }
  IPAddress localIP() { return IPAddress(); }
};
extern WiFiClass WiFi;
