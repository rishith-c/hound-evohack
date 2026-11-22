#!/usr/bin/env python3
"""serial_probe.py — send raw lines to the R4 and print the interesting fields of each reply.
   sudo systemctl stop rover-web first (the service owns the port), then:  venv/bin/python serial_probe.py "v 100 0 0" "s"
"""
import re
import sys
import time

import serial

s = serial.Serial("/dev/ttyACM0", 115200, timeout=0.05)   # short timeout: keep the cadence under the R4's 400 ms watchdog
s.dtr = True
time.sleep(1.2)
s.read(4000)
FIELDS = r'"target":\[[^\]]*\]|"rate":\[[^\]]*\]|"achieved":\[[^\]]*\]|"k":[0-9.]*|"maxmm":[0-9.]*|"pct":[0-9]*|"args":\[[^\]]*\]|"error":"[^"]*"'
for c in (sys.argv[1:] or ["?"]):
    s.write((c + "\n").encode())
    time.sleep(0.3)
    lines = s.read(4000).decode(errors="replace").strip().split("\n")
    last = lines[-1] if lines else ""
    m = re.findall(FIELDS, last)
    print(f"{c:24s} -> {' '.join(m) if m else last[:200]}")
s.write(b"s\n")
s.close()
