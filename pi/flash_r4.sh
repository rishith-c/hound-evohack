#!/bin/sh
# flash_r4.sh — compile the R4 firmware on this Mac, ship the binary to the Pi, and let the
# Pi upload it to the R4 over the Pi's own USB cable. No need to move the R4 to the Mac.
#   pi/flash_r4.sh              flashes firmware/r4_drive
#   pi/flash_r4.sh all_forward  flashes a different sketch folder under firmware/
set -e
SKETCH="${1:-r4_drive}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PI="${PI_HOST:-$(sh "$ROOT/pi/find_pi.sh")}"      # the Pi's address moves: found by its MAC unless PI_HOST is set
FQBN=arduino:renesas_uno:unor4wifi

arduino-cli compile --fqbn "$FQBN" --export-binaries "$ROOT/firmware/$SKETCH" | grep -E "Sketch uses|error" || true
BIN="$ROOT/firmware/$SKETCH/build/arduino.renesas_uno.unor4wifi/$SKETCH.ino.bin"
[ -f "$BIN" ] || { echo "no binary at $BIN"; exit 1; }

command rsync -az "$BIN" "$PI:rover/$SKETCH.ino.bin"
command ssh "$PI" "export PATH=\$HOME/.local/bin:\$PATH; \
  P=\$(readlink -f /dev/serial/by-id/*Arduino* 2>/dev/null | head -1); [ -n \"\$P\" ] || P=\$(ls /dev/ttyACM* 2>/dev/null | head -1); \
  [ -n \"\$P\" ] || { echo 'no R4 on the Pi USB'; exit 1; }; \
  sudo systemctl stop rover-web 2>/dev/null; sleep 1; \
  echo flashing \$P; arduino-cli upload -p \"\$P\" --fqbn $FQBN --input-file rover/$SKETCH.ino.bin 2>&1 | grep -E 'Done|error|fail' | tail -1; \
  sleep 2; sudo systemctl start rover-web 2>/dev/null; echo 'rover-web restarted'"
