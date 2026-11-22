#!/bin/sh
# deploy.sh — push the Pi-side code to the Pi over the LAN.
#   pi/deploy.sh                 rsync pi/rover/ → ~/rover/, sensing/ → ~/rover/sensing/ and ml/ → ~/rover/ml/ on the Pi
#   pi/deploy.sh --setup         also run setup_pi.sh there (first time; installs libs + arduino-cli)
#   pi/deploy.sh --demo [arg]    then run demo.py on the Pi
# Host: $PI_HOST, else pi/find_pi.sh finds the Pi on this network.
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
PI="${PI_HOST:-$(sh "$DIR/find_pi.sh")}"           # the Pi's address moves: found by its MAC unless PI_HOST is set

command rsync -az --delete --exclude venv --exclude '__pycache__' --exclude web.key --exclude pan_trim --exclude motions.json --exclude tunnel_url.sh --exclude radars.json --exclude stations.jsonl --exclude 'MobileNetSSD*' --exclude sensing --exclude ml "$DIR/rover/" "$PI:rover/"
command rsync -az "$DIR/setup_pi.sh" "$DIR/enable_gpio_uart.sh" "$PI:rover/"
command rsync -az --delete --exclude '__pycache__' "$DIR/../sensing/" "$PI:rover/sensing/"   # station.py, radar_check.py and their models
command rsync -az --delete --exclude '__pycache__' --exclude 'data/*.npz' --exclude 'data/real/' "$DIR/../ml/" "$PI:rover/ml/"   # the Wi-Fi network; the Pi's recordings stay

case "$1" in
  --setup) command ssh "$PI" 'sh rover/setup_pi.sh' ;;
  --demo)  shift; command ssh -t "$PI" "cd rover && venv/bin/python demo.py $*" ;;
  *)       command ssh "$PI" 'echo deployed to $(hostname): && ls rover' ;;
esac
