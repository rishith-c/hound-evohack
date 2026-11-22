#!/bin/sh
# enable_gpio_uart.sh — run ON THE PI, once, for the LD2450 on the Pi's own UART (header pins 8 TXD / 10 RXD).
#   The PL011 UART is moved off Bluetooth onto GPIO 14/15 (nothing on the rover uses Bluetooth) and the serial
#   login console is taken off it, so the radar gets a clean port: /dev/ttyAMA0 at 256000 baud.
#   Idempotent; config.txt and cmdline.txt are backed up first. It does NOT reboot — do that yourself, and note
#   the remote gets a new Cloudflare link afterwards (sh ~/rover/tunnel_url.sh).
#     sh pi/enable_gpio_uart.sh          (copied over by pi/deploy.sh as ~/rover/enable_gpio_uart.sh)
set -e
BOOT=/boot/firmware; [ -f "$BOOT/config.txt" ] || BOOT=/boot
CFG="$BOOT/config.txt"; CMD="$BOOT/cmdline.txt"
[ -f "$CFG" ] && [ -f "$CMD" ] || { echo "no config.txt/cmdline.txt under /boot/firmware or /boot"; exit 1; }
STAMP=$(date +%Y%m%d-%H%M%S)
sudo cp "$CFG" "$CFG.bak-$STAMP"; sudo cp "$CMD" "$CMD.bak-$STAMP"

# lines appended after a [pi5] / [cm4] … section would apply to that board only: re-open [all] first if needed
if ! grep -q '^enable_uart=1' "$CFG" || ! grep -q '^dtoverlay=disable-bt' "$CFG"; then
  [ "$(grep -E '^\[' "$CFG" | tail -1)" = "[all]" ] || echo '[all]' | sudo tee -a "$CFG" >/dev/null
fi
grep -q '^enable_uart=1' "$CFG" || echo 'enable_uart=1' | sudo tee -a "$CFG" >/dev/null
grep -q '^dtoverlay=disable-bt' "$CFG" || echo 'dtoverlay=disable-bt' | sudo tee -a "$CFG" >/dev/null
# no login console on the radar's UART (cmdline.txt is one line)
sudo sed -i -E 's/(^| )console=(serial0|ttyAMA0|ttyS0),[0-9]+( |$)/\1/g; s/ +$//' "$CMD"
sudo systemctl disable hciuart >/dev/null 2>&1 || true
sudo systemctl disable serial-getty@ttyAMA0.service serial-getty@serial0.service >/dev/null 2>&1 || true   # a getty enabled by hand
id -nG | tr ' ' '\n' | grep -qx dialout || sudo usermod -aG dialout "$(whoami)"

# point station.py at it (other entries — the two CP2102s — are kept)
python3 - <<'PY'
import json, os
p = os.path.expanduser("~/rover/radars.json")
d = json.load(open(p)) if os.path.exists(p) else {}
d["ld2450"] = "/dev/ttyAMA0"
json.dump(d, open(p, "w"), indent=1)
print("~/rover/radars.json:", d)
PY
echo "config: $(grep -E '^(enable_uart|dtoverlay=disable-bt)' "$CFG" | tr '\n' ' ')"
echo "cmdline: $(cat "$CMD")"
echo "Done. Reboot to apply: sudo reboot   (backups: $CFG.bak-$STAMP, $CMD.bak-$STAMP)"
