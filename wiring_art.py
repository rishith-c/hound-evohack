#!/usr/bin/env python3
"""
wiring_art.py — Fritzing-style illustrated wiring for Hound, generated from the SAME net list as the WireViz sheets
(bom-site/wiring/*.yml) so every wire lands on a real pin. Part artwork = Fritzing breadboard SVGs pulled from the
open libraries (fritzing-parts, adafruit/Fritzing-Library, Protoneer, RafaGS, mkjanke) with pin positions read by
fzpin.py; parts no library has (fan, hub, webcam, bank, LD2450, CP2102 sticks, the Deans plug) are drawn here.

Wires are routed orthogonally as ribbons: every wire of a bundle runs in its own parallel track (7 px apart), bundles
get their own channels, so no two wires ever lie on top of each other. The script counts remaining crossings per sheet.

    venv/bin/python wiring_art.py     # → bom-site/wiring/art-*.svg/.png (one per diagram) + art-poster.svg/.png
"""
import base64
import json
import math
import os
import subprocess
from collections import defaultdict

import yaml

ROOT = os.path.dirname(os.path.abspath(__file__))
WDIR = os.path.join(ROOT, "bom-site", "wiring")
PARTS = json.load(open(os.path.join(WDIR, "parts", "parts_pins.json")))
DIAGRAMS = ["1-power", "2-drive", "3-turret", "4-pi-sensors", "5-radars-usb", "6-csi"]
NET = {n: yaml.safe_load(open(os.path.join(WDIR, f"{n}.yml"))) for n in DIAGRAMS}

HEX = {"RD": "#e03131", "BK": "#1e1e1e", "YE": "#f5c400", "BU": "#1c7ed6", "GN": "#2f9e44", "WH": "#f1f3f5", "OG": "#f76707", "BN": "#8b5a2b", "VT": "#7048e8", "GY": "#868e96"}
WIDTH = {"14 AWG": 7, "22 AWG": 4.2, "24 AWG": 3.6, "26 AWG": 3.0, "28 AWG": 2.6}
LANE = 7
ALIAS = {"coil A +": "A+", "coil A −": "A−", "coil B +": "B+", "coil B −": "B−", "USB-C: NEVER while 5V is fed": "USB-C (never with 5V)", "USB-C from any 5 V charger": "USB-C ← charger",
         "signal (orange)": "sig", "V+ (red)": "V+", "GND (brown)": "GND", "5V (red)": "5V", "GND (black)": "GND", "port 1: UNO R4": "R4", "port 2: CP2102 no.1": "CP1",
         "port 3: CP2102 no.2": "CP2", "port 4: free": "free", "USB 1: webcam": "webcam", "USB 2: hub": "hub", "USB-A out": "out", "upstream": "in", "5V (VIN)": "5V"}

S = {}


def part(cid, key, x, y, s=1.25, label=None, pins=None, **kw):
    S[cid] = dict(part=key, x=x, y=y, s=s, label=label if label is not None else cid, pins=pins or {}, **kw)


def own(cid, kind, x, y, label=None, pins=None, **kw):
    S[cid] = dict(own=kind, x=x, y=y, s=1.0, label=label if label is not None else cid, pins=pins or {}, **kw)


pi_pins = {lab: f"connector{int(lab.split()[0]) - 1}" for lab in NET["4-pi-sensors"]["connectors"]["PI"]["pinlabels"]}
MOT = {"coil A +": "connector0", "coil A −": "connector1", "coil B +": "connector2", "coil B −": "connector3"}
LD = {"1 TX": "connector0", "2 RX": "connector1", "3 OUT": "connector2", "4 GND": "connector3", "5 VCC": "connector4"}
BUCK = {"IN+": "connector0", "IN−": "connector1", "OUT+": "connector2", "OUT−": "connector3"}
CPP = {"5V": (30, -8), "3V3": (10, 118), "GND": (20, 118), "TXD": (30, 118), "RXD": (40, 118), "DTR": (50, 118)}

part("M_BL", "stepper", 330, 60, 0.8, "BL — NEMA 17 (axis X)", MOT, label_pos="top")
part("M_FL", "stepper", 1080, 60, 0.8, "FL — NEMA 17 (axis Y)", MOT, label_pos="top")
part("M_BR", "stepper", 330, 640, 0.8, "BR — NEMA 17 (axis Z)", MOT)
part("M_FR", "stepper", 1080, 640, 0.8, "FR — NEMA 17 (axis A)", MOT)
part("MLX", "mlx90640", 1560, 70, 1.25, "MLX90640 thermal (I2C-1)", {"VIN 3V3": "connector31", "GND": "connector33", "SCL": "connector34", "SDA": "connector35"}, label_pos="top")
part("TOF_F", "vl53l1x", 1760, 70, 1.25, "VL53L1X ToF FRONT (→0x30)", {"VIN 3V3": "connector29", "GND": "connector30", "SDA": "connector32", "SCL": "connector31", "XSHUT": "connector34"}, label_pos="top")
part("TOF_R", "vl53l1x", 1960, 70, 1.25, "VL53L1X ToF REAR (0x29)", {"VIN 3V3": "connector29", "GND": "connector30", "SDA": "connector32", "SCL": "connector31", "XSHUT": "connector34"}, label_pos="top")
part("MIC", "i2smic", 2160, 90, 1.25, "INMP441 mic (Adafruit art)", {"VDD 3V3": "connector17", "GND": "connector18", "SCK": "connector19", "WS": "connector21", "SD": "connector20", "L/R": "connector22"}, label_pos="top")
part("PACK", "lipo", 40, 60, 0.5, "HOOVO 3S 2200 mAh (T-plug)", {"V+": "connector1", "GND": "connector2"}, label_pos="top")
own("PLUG", "deans", 170, 80, "Deans pull-plug = E-STOP", {"pack +": (0, 18), "pack −": (0, 42), "rover +": (110, 18), "rover −": (110, 42)})
part("XL4015", "lm2596", 60, 760, 1.1, "XL4015 buck → 5.0 V (drawn as the LM2596 module)", BUCK)
part("R4", "uno", 632, 394, 1.25, "", {})
part("SHIELD", "cnc", 620, 380, 1.25, "CNC Shield v3 + DRV8825 ×4, on the UNO R4 WiFi (drawn as an Uno)", {})
part("PI", "pi4", 1500, 380, 1.25, "Raspberry Pi 4", pi_pins)
own("CAM", "webcam", 2100, 400, "Webcam (turret)", {"USB-A": (0, 40)})
own("HUB", "hub", 2100, 560, "4-port USB hub", {"upstream": (0, 30), "port 1: UNO R4": (150, 12), "port 2: CP2102 no.1": (150, 26), "port 3: CP2102 no.2": (150, 40), "port 4: free": (150, 54)})
own("CP1", "cp2102", 2350, 380, "CP2102 no.1", CPP); own("CP2", "cp2102", 2460, 380, "CP2102 no.2", CPP)
own("BANK", "bank", 1300, 690, "USB power bank 5 V / 3 A", {"USB-A out": (170, 35)})
part("PCA", "pca9685", 330, 960, 1.25, "PCA9685 servo driver (on the shield's I2C)", {})
own("FAN", "fan", 800, 1180, "40 mm 5 V fan", {"5V (red)": (0, 30), "GND (black)": (0, 50)})
part("ESP3", "esp32c3", 2100, 830, 0.9, "ESP32-S3 no.3 csi_rx_udp (drawn as a C3 devkit)", {"USB-C": (60, 207)})
own("BANK2", "bank2", 2250, 1080, "second power bank — ESP32 only", {"USB-A out": (0, 35)})
part("ESP2", "esp32c3", 2350, 830, 0.9, "ESP32-S3 no.2 csi_tx — OFF the rover", {"USB-C from any 5 V charger": (60, 207)}, ghost=True)
part("TILT", "servo", 300, 1180, 1.25, "MG996R TILT servo", {"signal (orange)": "connector2", "V+ (red)": "connector1", "GND (brown)": "connector0"})
part("PAN", "servo", 60, 1180, 1.25, "MG996R PAN servo", {"signal (orange)": "connector2", "V+ (red)": "connector1", "GND (brown)": "connector0"})
part("LDL", "ld2410", 2350, 620, 1.25, "LD2410C LEFT (+30°)", LD); part("LDR", "ld2410", 2520, 620, 1.25, "LD2410C RIGHT (−30°)", LD)
own("LD2450", "ld2450", 2690, 620, "LD2450 (on the Pi UART)", {"5V": (30, 0), "GND": (50, 0), "TX": (70, 0), "RX": (90, 0)})
own("PI_MINI", "pi_mini", 0, 0, "Raspberry Pi 4 (power in)", {"USB-C": (0, 34)})
own("R4_MINI", "r4_mini", 0, 0, "UNO R4 WiFi (under the shield)", {"USB-C": (130, 34)})

HOSTPINS = {
    "SHIELD_PWR": ("SHIELD", {"VMOT": "connector30", "GND": "connector29"}),
    "SHIELD_CTRL": ("SHIELD", {}), "DRV": ("SHIELD", {}),
    "SHIELD_I2C": ("SHIELD", {"A4 SDA": "connector74", "A5 SCL": "connector72", "5V": "connector75", "GND": "connector76"}),
    "X_MOT": ("SHIELD", {"2B": "connector37", "2A": "connector38", "1A": "connector39", "1B": "connector40"}),
    "Y_MOT": ("SHIELD", {"2B": "connector57", "2A": "connector58", "1A": "connector59", "1B": "connector60"}),
    "Z_MOT": ("SHIELD", {"2B": "connector47", "2A": "connector48", "1A": "connector49", "1B": "connector50"}),
    "A_MOT": ("SHIELD", {"2B": "connector67", "2A": "connector68", "1A": "connector69", "1B": "connector70"}),
    "R4_USB": ("R4", {"USB-C": (14, 44)}),
    "PI_USB": ("PI", {"USB 1: webcam": (410, 118), "USB 2: hub": (410, 150), "USB 3: free": (410, 208), "USB 4: free": (410, 242)}),
    "PI_PWR": ("PI", {"USB-C": (55, 268)}),
    "SHIELD_I2C": ("SHIELD", {"SDA": "connector74", "SCL": "connector72", "5V": "connector75", "GND": "connector76"}),
    "PCA_LOGIC": ("PCA", {"GND": "connector42", "OE": "connector41", "SCL": "connector40", "SDA": "connector39", "VCC": "connector38", "V+": "connector37"}),
    "PCA_PWR": ("PCA", {"V+": "connector7", "GND": "connector8"}),
    "PCA_CH3": ("PCA", {"PWM": "connector25", "V+": "connector26", "GND": "connector27"}),
    "PCA_CH2": ("PCA", {"PWM": "connector28", "V+": "connector29", "GND": "connector30"}),
    "PCA_CH15": ("PCA", {"PWM": "connector49", "V+": "connector50", "GND": "connector51"}),
}
SUBST = {"1-power": {"PI_PWR": "PI_MINI"}, "5-radars-usb": {"R4_USB": "R4_MINI"}}
DIR = {"X_MOT": (-1, 0), "Z_MOT": (-1, 0), "Y_MOT": (1, 0), "A_MOT": (1, 0), "SHIELD_PWR": (-1, 0), "SHIELD_I2C": (1, 0),
       "SHIELD_I2C": (1, 0), "PCA_LOGIC": (-1, 0), "PCA_PWR": (0, -1), "PCA_CH3": (0, 1), "PCA_CH2": (0, 1), "PCA_CH15": (0, 1), "PI": (0, -1), "PI_USB": (1, 0), "PI_PWR": (0, 1)}

LAYOUT = {
    "1-power": {"PACK": (40, 60), "PLUG": (190, 80), "SHIELD": (380, 40), "R4": (392, 54), "XL4015": (60, 420), "BANK": (900, 60), "PI_MINI": (1160, 60)},
    "2-drive": {"M_BL": (60, 40), "M_BR": (60, 560), "SHIELD": (520, 300), "R4": (532, 314), "M_FL": (1120, 40), "M_FR": (1120, 560)},
    "3-turret": {"SHIELD": (40, 40), "R4": (52, 54), "PCA": (560, 120), "XL4015": (1000, 100), "PAN": (560, 420), "TILT": (780, 420), "FAN": (1040, 440)},
    "4-pi-sensors": {"MLX": (60, 40), "TOF_F": (260, 40), "TOF_R": (460, 40), "MIC": (660, 60), "LD2450": (900, 80), "PI": (200, 340)},
    "5-radars-usb": {"R4_MINI": (40, 60), "PI": (40, 300), "CAM": (700, 60), "HUB": (700, 300), "CP1": (950, 60), "CP2": (1060, 60), "LDL": (950, 520), "LDR": (1120, 520)},
    "6-csi": {"ESP3": (300, 40), "BANK2": (420, 300), "ESP2": (700, 40)},
}


def own_svg(kind):
    if kind == "deans":
        return ('<rect x="8" y="4" width="46" height="52" rx="5" fill="#c0392b" stroke="#6b1a12" stroke-width="2"/><rect x="56" y="4" width="46" height="52" rx="5" fill="#c0392b" stroke="#6b1a12" stroke-width="2"/>'
                '<rect x="46" y="12" width="18" height="10" fill="#d4a017"/><rect x="50" y="36" width="10" height="12" fill="#d4a017"/>'
                '<rect x="-8" y="14" width="16" height="8" fill="#e03131"/><rect x="-8" y="38" width="16" height="8" fill="#1e1e1e"/><rect x="102" y="14" width="16" height="8" fill="#e03131"/><rect x="102" y="38" width="16" height="8" fill="#1e1e1e"/>'
                '<text x="55" y="70" font-size="9" text-anchor="middle" fill="#333" font-family="Helvetica,Arial">pull apart = off</text>', 110, 72)
    if kind == "fan":
        blades = "".join(f'<path d="M40 40 L{40 + 30 * math.cos(a):.1f} {40 + 30 * math.sin(a):.1f} A30 30 0 0 1 {40 + 30 * math.cos(a + 0.8):.1f} {40 + 30 * math.sin(a + 0.8):.1f} Z" fill="#777"/>' for a in (0, 1.57, 3.14, 4.71))
        return ('<rect width="80" height="80" rx="8" fill="#222" stroke="#000" stroke-width="2"/><circle cx="40" cy="40" r="34" fill="#333"/><circle cx="40" cy="40" r="10" fill="#555"/>' + blades
                + '<rect x="-14" y="26" width="14" height="8" fill="#e03131"/><rect x="-14" y="46" width="14" height="8" fill="#1e1e1e"/>', 80, 80)
    if kind == "hub":
        return ('<rect width="150" height="66" rx="8" fill="#2b2b2b" stroke="#000" stroke-width="2"/><rect x="-10" y="22" width="14" height="16" fill="#888"/>'
                + "".join(f'<rect x="138" y="{6 + i * 14}" width="14" height="10" fill="#ccc" stroke="#555"/>' for i in range(4))
                + '<text x="70" y="38" font-size="11" text-anchor="middle" fill="#ddd" font-family="Helvetica,Arial">USB hub</text>', 150, 66)
    if kind == "webcam":
        return ('<rect x="0" y="20" width="120" height="40" rx="14" fill="#1f1f1f" stroke="#000" stroke-width="2"/><circle cx="60" cy="40" r="15" fill="#0b2a44" stroke="#4a90d9" stroke-width="2"/>'
                '<circle cx="60" cy="40" r="6" fill="#1a6fc4"/><rect x="50" y="60" width="20" height="14" fill="#333"/><rect x="-8" y="34" width="10" height="12" fill="#888"/>', 120, 80)
    if kind == "bank":
        return ('<rect width="170" height="70" rx="12" fill="#5c636a" stroke="#222" stroke-width="2"/><rect x="168" y="26" width="10" height="18" fill="#ccc" stroke="#555"/>'
                '<path d="M40 14 L24 40 H38 L32 58 L58 30 H42 Z" fill="#ffd43b"/><text x="100" y="42" font-size="12" fill="#fff" font-family="Helvetica,Arial">5 V · 3 A</text>', 170, 70)
    if kind == "ld2450":
        return ('<rect width="120" height="70" rx="4" fill="#1d4f91" stroke="#0b2a4a" stroke-width="2"/>'
                '<rect x="10" y="12" width="22" height="16" fill="#d4a017"/><rect x="49" y="12" width="22" height="16" fill="#d4a017"/><rect x="88" y="12" width="22" height="16" fill="#d4a017"/>'
                '<rect x="46" y="40" width="28" height="20" fill="#111"/><text x="60" y="68" font-size="9" text-anchor="middle" fill="#fff" font-family="Helvetica,Arial">HLK-LD2450</text>'
                + "".join(f'<rect x="{x - 3}" y="-8" width="6" height="10" fill="#ccc" stroke="#555"/>' for x in (30, 50, 70, 90)), 120, 70)
    if kind == "cp2102":
        return ('<rect x="18" y="-10" width="24" height="26" rx="3" fill="#bbb" stroke="#555" stroke-width="2"/><rect width="60" height="110" rx="5" fill="#c0392b" stroke="#6b1a12" stroke-width="2"/>'
                '<rect x="18" y="40" width="24" height="24" fill="#222"/><text x="30" y="34" font-size="8" text-anchor="middle" fill="#fff" font-family="Helvetica,Arial">CP2102</text>'
                + "".join(f'<rect x="{x - 3}" y="108" width="6" height="10" fill="#ccc" stroke="#555"/>' for x in (10, 20, 30, 40, 50)), 60, 118)
    if kind == "bank2":
        return ('<rect width="170" height="70" rx="12" fill="#5c636a" stroke="#222" stroke-width="2"/><rect x="-8" y="26" width="10" height="18" fill="#ccc" stroke="#555"/>'
                '<path d="M120 14 L104 40 H118 L112 58 L138 30 H122 Z" fill="#ffd43b"/><text x="60" y="42" font-size="12" fill="#fff" font-family="Helvetica,Arial">5 V · 1 A</text>', 170, 70)
    if kind == "pi_mini":
        return ('<rect width="130" height="70" rx="6" fill="#2e7d32" stroke="#1b4d1e" stroke-width="2"/><rect x="-8" y="26" width="10" height="16" fill="#ccc" stroke="#555"/>'
                '<text x="70" y="40" font-size="11" text-anchor="middle" fill="#fff" font-family="Helvetica,Arial">Pi 4 · USB-C in</text>', 130, 70)
    if kind == "r4_mini":
        return ('<rect width="130" height="70" rx="6" fill="#0b7285" stroke="#083e4a" stroke-width="2"/><rect x="128" y="26" width="10" height="16" fill="#ccc" stroke="#555"/>'
                '<text x="65" y="40" font-size="11" text-anchor="middle" fill="#fff" font-family="Helvetica,Arial">UNO R4 · USB-C</text>', 130, 70)
    raise KeyError(kind)


def sprite_box(cid, pos):
    s = S[cid]; x, y = pos.get(cid, (s["x"], s["y"]))
    if "part" in s:
        p = PARTS[s["part"]]; w, h = p["w"] * s["s"], p["h"] * s["s"]
    else:
        _, w, h = own_svg(s["own"])
    return x, y, w, h


def host_of(cid, subst):
    if cid in subst: return subst[cid], S[subst[cid]]["pins"]
    if cid in HOSTPINS: return HOSTPINS[cid]
    return cid, S[cid]["pins"]


def pin_xy(cid, lab, pos, subst):
    host, pins = host_of(cid, subst)
    s = S[host]; ref = pins[lab]
    if isinstance(ref, tuple):
        lx, ly = ref[0] * (s["s"] if "part" in s else 1), ref[1] * (s["s"] if "part" in s else 1)
    else:
        p = PARTS[s["part"]]["pins"][ref]; lx, ly = p["x"] * s["s"], p["y"] * s["s"]
    bx, by, bw, bh = sprite_box(host, pos)
    d = DIR.get(cid) or min((lx, (-1, 0)), (bw - lx, (1, 0)), (ly, (0, -1)), (bh - ly, (0, 1)), key=lambda t: t[0])[1]
    return (bx + lx, by + ly, d, host)


def route(wires, boxes):
    groups = defaultdict(list)
    for i, (A, B) in enumerate(wires):
        groups[(A[3], A[2], B[3], B[2])].append(i)
    out = [None] * len(wires)
    used_v, used_h = [], []

    def free(coord, lo, hi, half, used):
        return all(abs(c - coord) >= half + w + 8 or hi < l or lo > h for c, l, h, w in used)

    def pick(coord, lo, hi, half, used):
        for k in range(0, 40):
            for sgn in (1, -1):
                c = coord + sgn * k * 14
                if free(c, lo, hi, half, used):
                    used.append((c, lo, hi, half)); return c
        return coord

    for key, idx in groups.items():
        hA, dA, hB, dB = key
        n = len(idx)
        nA = (-dA[1], dA[0]); nB = (-dB[1], dB[0])
        alongA = lambda i: wires[i][0][0] * nA[0] + wires[i][0][1] * nA[1]
        alongB = lambda i: wires[i][1][0] * nB[0] + wires[i][1][1] * nB[1]
        spreadA = max(alongA(i) for i in idx) - min(alongA(i) for i in idx); spreadB = max(alongB(i) for i in idx) - min(alongB(i) for i in idx)
        idx.sort(key=alongB if spreadB > spreadA else alongA)
        pinsA = [wires[i][0] for i in idx]; pinsB = [wires[i][1] for i in idx]
        cA = (sum(p[0] for p in pinsA) / n, sum(p[1] for p in pinsA) / n)
        cB = (sum(p[0] for p in pinsB) / n, sum(p[1] for p in pinsB) / n)

        def port(c, d, host):
            bx, by, bw, bh = boxes[host]
            px = bx + bw + 22 + 3 * n if d[0] > 0 else bx - 22 - 3 * n if d[0] < 0 else c[0]
            py = by + bh + 22 + 3 * n if d[1] > 0 else by - 22 - 3 * n if d[1] < 0 else c[1]
            return (px, py)
        pA, pB = port(cA, dA, hA), port(cB, dB, hB)
        half = LANE * (n - 1) / 2
        if dA[0] and dB[0]:
            facing = dA[0] * (pB[0] - pA[0]) > 0 and dB[0] * (pA[0] - pB[0]) > 0
            xc = (pA[0] + pB[0]) / 2 if facing else (max(pA[0], pB[0]) + 40 if dA[0] > 0 else min(pA[0], pB[0]) - 40)
            xc = pick(xc, min(pA[1], pB[1]), max(pA[1], pB[1]), half, used_v)
            centre = [pA, (xc, pA[1]), (xc, pB[1]), pB]
        elif dA[1] and dB[1]:
            facing = dA[1] * (pB[1] - pA[1]) > 0 and dB[1] * (pA[1] - pB[1]) > 0
            yc = (pA[1] + pB[1]) / 2 if facing else (max(pA[1], pB[1]) + 40 if dA[1] > 0 else min(pA[1], pB[1]) - 40)
            yc = pick(yc, min(pA[0], pB[0]), max(pA[0], pB[0]), half, used_h)
            centre = [pA, (pA[0], yc), (pB[0], yc), pB]
        elif dA[0]:
            if (pB[0] - pA[0]) * dA[0] > 0 and (pA[1] - pB[1]) * dB[1] > 0:
                centre = [pA, (pB[0], pA[1]), pB]
            else:
                xj = pick(pA[0] + dA[0] * 40, min(pA[1], pB[1]), max(pA[1], pB[1]), half, used_v)
                yj = pick(pB[1] + dB[1] * 40, min(pA[0], pB[0]), max(pA[0], pB[0]), half, used_h)
                centre = [pA, (xj, pA[1]), (xj, yj), (pB[0], yj), pB]
        else:
            if (pB[1] - pA[1]) * dA[1] > 0 and (pA[0] - pB[0]) * dB[0] > 0:
                centre = [pA, (pA[0], pB[1]), pB]
            else:
                yj = pick(pA[1] + dA[1] * 40, min(pA[0], pB[0]), max(pA[0], pB[0]), half, used_h)
                xj = pick(pB[0] + dB[0] * 40, min(pA[1], pB[1]), max(pA[1], pB[1]), half, used_v)
                centre = [pA, (pA[0], yj), (xj, yj), (xj, pB[1]), pB]
        cl = [centre[0]]
        for p in centre[1:]:
            if abs(p[0] - cl[-1][0]) > 0.5 or abs(p[1] - cl[-1][1]) > 0.5: cl.append(p)
        segs = [(cl[i], cl[i + 1]) for i in range(len(cl) - 1)]
        for r, i in enumerate(idx):
            o = (r - (n - 1) / 2) * LANE
            offs = []
            for (p, q) in segs:
                ux, uy = q[0] - p[0], q[1] - p[1]; L = math.hypot(ux, uy); ux, uy = ux / L, uy / L
                nx, ny = -uy, ux
                offs.append(((p[0] + o * nx, p[1] + o * ny), (q[0] + o * nx, q[1] + o * ny)))
            pts = [offs[0][0]]
            for k in range(len(offs) - 1):
                a, b = offs[k], offs[k + 1]
                horiz_a = abs(a[1][1] - a[0][1]) < 0.5
                pts.append((b[0][0], a[0][1]) if horiz_a else (a[0][0], b[0][1]))
            pts.append(offs[-1][1])
            A, B = wires[i]
            sA = 12 + 5 * r; sB = 12 + 5 * (n - 1 - r)
            qa1 = (A[0] + dA[0] * sA, A[1] + dA[1] * sA)
            qa2 = (qa1[0] + (pts[0][0] - qa1[0]) * abs(nA[0]), qa1[1] + (pts[0][1] - qa1[1]) * abs(nA[1]))
            qb1 = (B[0] + dB[0] * sB, B[1] + dB[1] * sB)
            qb2 = (qb1[0] + (pts[-1][0] - qb1[0]) * abs(nB[0]), qb1[1] + (pts[-1][1] - qb1[1]) * abs(nB[1]))
            out[i] = [(A[0], A[1]), qa1, qa2] + pts + [qb2, qb1, (B[0], B[1])]
    return out


def metrics(polys):
    segs = []
    for w, pl in enumerate(polys):
        for k in range(len(pl) - 1):
            a, b = pl[k], pl[k + 1]
            if abs(a[0] - b[0]) < 0.5 and abs(a[1] - b[1]) < 0.5: continue
            segs.append((w, a, b, 2 <= k < len(pl) - 3))
    cross = overlap = 0
    for i in range(len(segs)):
        w1, a1, b1, mid1 = segs[i]
        for j in range(i + 1, len(segs)):
            w2, a2, b2, mid2 = segs[j]
            if w1 == w2: continue
            h1, h2 = abs(a1[1] - b1[1]) < 0.5, abs(a2[1] - b2[1]) < 0.5
            if h1 != h2:
                H, V = (segs[i], segs[j]) if h1 else (segs[j], segs[i])
                y = H[1][1]; x = V[1][0]
                if min(H[1][0], H[2][0]) + 1 < x < max(H[1][0], H[2][0]) - 1 and min(V[1][1], V[2][1]) + 1 < y < max(V[1][1], V[2][1]) - 1:
                    cross += 1
            elif mid1 and mid2:
                if h1 and abs(a1[1] - a2[1]) < 2 and min(max(a1[0], b1[0]), max(a2[0], b2[0])) - max(min(a1[0], b1[0]), min(a2[0], b2[0])) > 6: overlap += 1
                if not h1 and abs(a1[0] - a2[0]) < 2 and min(max(a1[1], b1[1]), max(a2[1], b2[1])) - max(min(a1[1], b1[1]), min(a2[1], b2[1])) > 6: overlap += 1
    return cross, overlap


def esc(t):
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def draw_sprite(cid, pos, defs, embed):
    s = S[cid]; x, y, w, h = sprite_box(cid, pos); out = []
    if s.get("ghost"):
        out.append(f'<rect x="{x - 8}" y="{y - 8}" width="{w + 16}" height="{h + 16}" rx="10" fill="none" stroke="#999" stroke-dasharray="8 6" stroke-width="2"/>')
    if "part" in s:
        key = s["part"]
        if key not in defs:
            p = PARTS[key]
            href = ("data:image/svg+xml;base64," + base64.b64encode(open(os.path.join(WDIR, "parts", key + ".svg"), "rb").read()).decode()) if embed else f"parts/{key}.svg"
            defs[key] = f'<image id="img-{key}" href="{href}" width="{p["w"]}" height="{p["h"]}"/>'
        op = ' opacity="0.45"' if s.get("ghost") else ""
        out.append(f'<use href="#img-{key}" transform="translate({x} {y}) scale({s["s"]})"{op}/>')
    else:
        art, _, _ = own_svg(s["own"])
        out.append(f'<g transform="translate({x} {y})">{art}</g>')
    if s["label"]:
        ly = y - 10 if s.get("label_pos") == "top" else y + h + 22
        out.append(f'<text x="{x + w / 2:.0f}" y="{ly:.0f}" font-size="14" font-weight="bold" text-anchor="middle" fill="#222" font-family="Helvetica,Arial" paint-order="stroke" stroke="#fff" stroke-width="4">{esc(s["label"])}</text>')
    return "".join(out)


def pin_tag(x, y, d, text):
    text = ALIAS.get(text, text)
    st = 'font-size="10" font-family="Menlo,monospace" fill="#111" paint-order="stroke" stroke="#fff" stroke-width="3"'
    if d[1] < 0:
        return f'<text transform="rotate(-90 {x:.0f} {y - 12:.0f})" x="{x:.0f}" y="{y - 12 + 3.5:.0f}" text-anchor="start" {st}>{esc(text)}</text>'
    if d[1] > 0:
        return f'<text transform="rotate(90 {x:.0f} {y + 12:.0f})" x="{x:.0f}" y="{y + 12 + 3.5:.0f}" text-anchor="start" {st}>{esc(text)}</text>'
    ox = x + d[0] * 14; anchor = "end" if d[0] < 0 else "start"
    return f'<text x="{ox:.0f}" y="{y + 4:.0f}" text-anchor="{anchor}" {st}>{esc(text)}</text>'


def render(name, diagrams, layout=None, embed=False, title=None):
    pos = dict(layout or {})
    subst = {} if layout is None else {k: v for d in diagrams for k, v in SUBST.get(d, {}).items()}
    sprites, wires, meta, tags = set(), [], [], []
    for dn in diagrams:
        doc = NET[dn]
        for cid in doc["connectors"]:
            sprites.add(host_of(cid, subst)[0])
        for row in doc["connections"]:
            (a, pa), (w, wi), (b, pb) = [(list(h)[0], list(h.values())[0][0]) for h in (row[0], row[1], row[-1])]
            cab = doc["cables"][w]
            A, B = pin_xy(a, pa, pos, subst), pin_xy(b, pb, pos, subst)
            wires.append((A, B)); meta.append((HEX[cab["colors"][int(wi) - 1]], WIDTH.get(cab["gauge"], 3)))
            tags.append((A, pa)); tags.append((B, pb))
    if "SHIELD" in sprites: sprites.add("R4")
    boxes = {c: sprite_box(c, pos) for c in sorted(sprites)}
    polys = route(wires, boxes)
    cross, overlap = metrics(polys)
    x0 = min(b[0] for b in boxes.values()) - 90; y0 = min(b[1] for b in boxes.values()) - 110
    x1 = max(b[0] + b[2] for b in boxes.values()) + 90; y1 = max(b[1] + b[3] for b in boxes.values()) + 60
    for pl in polys:
        for p in pl:
            x0, y0, x1, y1 = min(x0, p[0] - 30), min(y0, p[1] - 30), max(x1, p[0] + 30), max(y1, p[1] + 30)
    y0 -= 70                                                   # a band for the title that no ribbon can enter
    defs = {}
    body = [draw_sprite(c, pos, defs, embed) for c in sorted(sprites, key=lambda c: (0 if c == "R4" else 1, c))]   # deterministic: R4 under the shield, then by name
    wire_svg = ""
    for pl, (col, wd) in zip(polys, meta):
        d = "M" + " L".join(f"{p[0]:.1f} {p[1]:.1f}" for p in pl)
        wire_svg += f'<path d="{d}" fill="none" stroke="#222" stroke-width="{wd + 2.2}" stroke-linejoin="round" stroke-linecap="round" opacity="0.9"/><path d="{d}" fill="none" stroke="{col}" stroke-width="{wd}" stroke-linejoin="round" stroke-linecap="round"/>'
    dots = "".join(f'<circle cx="{p[0]:.1f}" cy="{p[1]:.1f}" r="4" fill="#ddd" stroke="#222" stroke-width="1.5"/>' for p, _ in tags)
    seen = set(); tag_svg = ""
    for (x, y, d, h), lab in tags:
        if (round(x), round(y)) in seen: continue
        seen.add((round(x), round(y))); tag_svg += pin_tag(x, y, d, lab)
    W, H = x1 - x0, y1 - y0
    ttl = title or NET[diagrams[0]]["metadata"]["title"]
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="{x0:.0f} {y0:.0f} {W:.0f} {H:.0f}" width="{W:.0f}" height="{H:.0f}">'
           f'<defs>{"".join(defs.values())}</defs><rect x="{x0:.0f}" y="{y0:.0f}" width="{W:.0f}" height="{H:.0f}" fill="#ffffff"/>'
           f'<text x="{x0 + 24:.0f}" y="{y0 + 34:.0f}" font-size="22" font-weight="bold" font-family="Helvetica,Arial" fill="#222">{esc(ttl)}</text>'
           f'<text x="{x0 + 24:.0f}" y="{y0 + 54:.0f}" font-size="12" font-family="Helvetica,Arial" fill="#555">Part artwork: Fritzing open libraries. Wires and pin tags: generated from the net list, cross-checked against wiring.py. {len(wires)} wires, {cross} crossings, {overlap} overlaps.</text>'
           + "".join(body) + wire_svg + dots + tag_svg + "</svg>")
    path = os.path.join(WDIR, f"{name}.svg")
    open(path, "w").write(svg)
    return path, len(wires), len(sprites), cross, overlap


if __name__ == "__main__":
    made = []; report = {}
    for dn in DIAGRAMS:
        p, nw, ns, cr, ov = render(f"art-{dn}", [dn], layout=LAYOUT[dn]); made.append(p); report[dn] = dict(wires=nw, parts=ns, crossings=cr, overlaps=ov)
        print(f"  art-{dn}: {ns} parts, {nw} wires, {cr} crossings, {ov} overlaps")
    p, nw, ns, cr, ov = render("art-poster", DIAGRAMS, title="Hound — everything wired (as built)"); made.append(p)
    report["poster"] = dict(wires=nw, parts=ns, crossings=cr, overlaps=ov)
    print(f"  art-poster: {ns} parts, {nw} wires, {cr} crossings, {ov} overlaps")
    render("art-poster-standalone", DIAGRAMS, embed=True, title="Hound — everything wired (as built)")
    json.dump(report, open(os.path.join(WDIR, "art-metrics.json"), "w"), indent=1)
    for p in made:
        png = p[:-4] + ".png"
        r = subprocess.run(["rsvg-convert", "-o", png, p], capture_output=True, text=True, cwd=WDIR)
        if r.returncode: print(f"  {os.path.basename(png)}: {r.stderr[:200]}")
