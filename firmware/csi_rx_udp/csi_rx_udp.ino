/*
  csi_rx_udp.ino — Hound CSI receiver node (ESP32-S3). Walleye's csi_rx, minus the serial cable.

  Listens for the 100 Hz ESP-NOW probe frames that Walleye's csi_tx sends on channel 6, captures the CSI of
  every one, and forwards it as UDP to the Pi's hotspot (which must ALSO be on channel 6, since an ESP32 has
  one radio: station association and ESP-NOW reception share the channel).

  Only csi_tx's frames count. The radio reports CSI for every frame it hears — the hotspot's beacons, its
  traffic to this node, a neighbour's network on channel 6 — and each is a different radio path; mixed into
  one stream they bury the room's signal. Walleye's csi_rx has the transmitter's MAC pasted in; this one
  learns it from the first ESP-NOW packet shaped like csi_tx's (5 bytes: id u8, count u32) and prints it.

  Packet (little-endian, one per probe frame):
      'H' 'C' | node u8 | seq u16 | rssi i8 | n u8 | n × (imag i8, real i8)
  n = 128: the LLTF block only (64 subcarriers, always first in the buffer). An HT packet brings 256+ bytes
  (LLTF + HT-LTF), which a u8 length cannot carry — it used to wrap to 0 and send an empty packet. The Pi keeps
  the 52 used subcarriers' amplitudes (ESP32 CSI phase is unusable across packets).

  Provision: fill SSID/PASS/SINK below, set NODE_ID (1 = on the rover, 2/3 = dropped in the room), flash with
      arduino-cli compile --fqbn esp32:esp32:esp32s3 firmware/csi_rx_udp && arduino-cli upload -p <port> ...
  The hotspot password never goes in a repo: read it into the build from a local, git-ignored secrets.h.
*/
#include <WiFi.h>
#include <WiFiUdp.h>
#include <esp_wifi.h>
#include <esp_now.h>
#if __has_include("secrets.h")
#include "secrets.h"                // #define HOUND_SSID "…"  #define HOUND_PASS "…"  #define HOUND_SINK "192.168.4.1"
#else
#define HOUND_SSID "hound-pi"
#define HOUND_PASS "changeme-in-secrets-h"
#define HOUND_SINK "10.42.0.1"
#endif
#define NODE_ID   1
#define CHANNEL   6
#define SINK_PORT 5005

WiFiUDP udp;
static volatile uint32_t rxCount = 0, txCount = 0;
static uint16_t seq = 0;

// Ring of captured CSI so the WiFi-task callback never blocks on the network stack
struct Slot { uint8_t used; int8_t rssi; uint8_t len; int8_t csi[128]; };
static Slot ring[8]; static volatile uint8_t wr = 0, rd = 0;

// Learned from csi_tx's first probe. Both callbacks run in the WiFi task, so no lock is needed.
static uint8_t txMac[6]; static volatile bool txKnown = false;

static void on_espnow(const esp_now_recv_info_t* r, const uint8_t*, int len) {
  if (!txKnown && len == 5) { memcpy(txMac, r->src_addr, 6); txKnown = true; }
}

static void IRAM_ATTR csi_cb(void*, wifi_csi_info_t* info) {
  if (!info || !info->buf || info->len <= 0) return;
  if (!txKnown || memcmp(info->mac, txMac, 6) != 0) return;   // not csi_tx: another radio path
  uint8_t next = (wr + 1) & 7;
  if (next == rd) return;                     // full: drop, never stall the radio task
  Slot& s = ring[wr];
  s.rssi = info->rx_ctrl.rssi;
  s.len = info->len > 128 ? 128 : info->len;      // the LLTF block; 256 would wrap the u8 length to 0
  memcpy(s.csi, info->buf, s.len);
  if (info->first_word_invalid) memset(s.csi, 0, 4);         // the radio flags these 4 bytes as garbage: a steady 0, not noise
  s.used = 1; wr = next; rxCount++;
}

void setup() {
  Serial.begin(115200);
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);   // the S3 core defaults to modem sleep: asleep between the AP's beacons, deaf to most probes
  WiFi.begin(HOUND_SSID, HOUND_PASS);
  uint32_t t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 15000) delay(100);
  Serial.printf("wifi %s ch %d ip %s\n", WiFi.status() == WL_CONNECTED ? "up" : "DOWN", WiFi.channel(), WiFi.localIP().toString().c_str());
  if (WiFi.channel() != CHANNEL) Serial.printf("WARNING: hotspot is on channel %d, csi_tx sends on %d — set the hotspot to %d\n", WiFi.channel(), CHANNEL, CHANNEL);

  esp_now_init();                              // ESP-NOW receive coexists with STA on the same channel
  esp_now_register_recv_cb(on_espnow);
  wifi_csi_config_t cfg = {};
  cfg.lltf_en = true; cfg.htltf_en = true; cfg.stbc_htltf2_en = false; cfg.ltf_merge_en = true;
  cfg.channel_filter_en = false; cfg.manu_scale = false; cfg.shift = false;
  esp_wifi_set_csi_config(&cfg);
  esp_wifi_set_csi_rx_cb(csi_cb, nullptr);
  esp_wifi_set_csi(true);
  udp.begin(SINK_PORT);
}

void loop() {
  static uint32_t lastReport = 0;
  while (rd != wr) {
    Slot& s = ring[rd];
    uint8_t hdr[7] = { 'H', 'C', NODE_ID, (uint8_t)(seq & 0xff), (uint8_t)(seq >> 8), (uint8_t)s.rssi, s.len };
    seq++;
    if (WiFi.status() == WL_CONNECTED) {
      udp.beginPacket(HOUND_SINK, SINK_PORT); udp.write(hdr, 7); udp.write((const uint8_t*)s.csi, s.len); udp.endPacket(); txCount++;
    }
    s.used = 0; rd = (rd + 1) & 7;
  }
  if (millis() - lastReport > 5000) {
    lastReport = millis();
    Serial.printf("node %d: csi rx %lu, udp tx %lu, wifi %s, csi_tx %s", NODE_ID, (unsigned long)rxCount, (unsigned long)txCount,
                  WiFi.status() == WL_CONNECTED ? "up" : "down", txKnown ? "" : "NOT HEARD (is ESP32 #2 on, and on this channel?)");
    if (txKnown) Serial.printf("%02X:%02X:%02X:%02X:%02X:%02X", txMac[0], txMac[1], txMac[2], txMac[3], txMac[4], txMac[5]);
    Serial.println();
    if (WiFi.status() != WL_CONNECTED) WiFi.reconnect();
  }
  delay(1);
}
