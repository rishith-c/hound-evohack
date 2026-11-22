#!/bin/sh
# find_pi.sh — print the rover Pi as user@address. Its DHCP address moves (.68, .73, …) and rishithc.local does not
# resolve on this network, so: mDNS if it answers, else ping the /24 once and look for the Pi's MAC in the ARP table.
#   sh pi/find_pi.sh [mac]      (deploy.sh and flash_r4.sh call it when PI_HOST is not set)
MAC="${1:-2c:cf:67:48:fd:92}"      # the rover's Pi 4
USER_AT="rishithc@"
if ip=$(dscacheutil -q host -a name rishithc.local 2>/dev/null | awk '/ip_address/{print $2; exit}') && [ -n "$ip" ]; then
  echo "$USER_AT$ip"; exit 0
fi
me=$(ipconfig getifaddr en0 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}')
[ -n "$me" ] || { echo "find_pi: no network address on this machine" >&2; exit 1; }
net=${me%.*}
i=1; while [ $i -le 254 ]; do ping -c 1 -t 1 "$net.$i" >/dev/null 2>&1 & i=$((i + 1)); done; wait
ip=$(arp -an | awk -v m="$MAC" 'tolower($4) == m {gsub(/[()]/, "", $2); print $2; exit}')
[ -n "$ip" ] && { echo "$USER_AT$ip"; exit 0; }
echo "find_pi: $MAC not on $net.0/24 — is the Pi on (green LED), and on this Wi-Fi?" >&2; exit 1
