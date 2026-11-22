#!/usr/bin/env python3
"""
rover3d.py — builds bom-site/rover3d/scene.json for the interactive 3D rover: every placement from assembly.json, the
real part artwork/pin positions from the Fritzing parts (fzpin.py), and every wire from the same net list as the wiring
sheets (bom-site/wiring/*.yml). Coordinates are the rover frame: +X forward, +Y left, +Z up, mm, origin chassis centre
on the floor. The page (bom-site/rover3d/index.html) converts to three.js (x, z, −y) itself.

    venv/bin/python rover3d.py
"""
import json
import math
import os

import yaml

ROOT = os.path.dirname(os.path.abspath(__file__))
A = json.load(open(os.path.join(ROOT, "assembly.json")))
PARTS = json.load(open(os.path.join(ROOT, "bom-site", "wiring", "parts", "parts_pins.json")))
NETD = json.load(open(os.path.join(ROOT, "wiring_diagrams.json")))
WDIR = os.path.join(ROOT, "bom-site", "wiring")
NET = {n: yaml.safe_load(open(os.path.join(WDIR, f"{n}.yml"))) for n in NETD["diagrams"]}
K = 25.4 / 120.0                       # Fritzing px (120 px/in) → mm
HEX = {"RD": "#e03131", "BK": "#1e1e1e", "YE": "#f5c400", "BU": "#1c7ed6", "GN": "#2f9e44", "WH": "#f1f3f5", "OG": "#f76707", "BN": "#8b5a2b", "VT": "#7048e8", "GY": "#868e96"}
RADIUS = {"14 AWG": 1.7, "22 AWG": 0.85, "24 AWG": 0.75, "26 AWG": 0.65, "28 AWG": 0.6}

by = {}
for p in A["parts"]:
    by.setdefault(p["id"], []).append(p)


def find(pid, inst_sub=None):
    for p in by.get(pid, []):
        if inst_sub is None or inst_sub in str(p.get("instance", "")):
            return p
    raise KeyError((pid, inst_sub))


DECK_TOP = 96.0
scene = dict(frame=A["frame"], parts=[], wires=[], sheets=list(NETD["diagrams"]), pins={})


def add(pid, label, kind, pos, size, **kw):
    d = dict(id=pid, label=label, kind=kind, pos=[round(float(v), 2) for v in pos], size=[round(float(v), 2) for v in size])
    d.update(kw); scene["parts"].append(d); return d


# ── textured boards: Fritzing art on a slab, real pins ─────────────────────────────────────────────────────
def rot2(u, v, yaw):
    c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    return u * c - v * s, u * s + v * c


def board(pid, label, key, centre, yaw=0.0, face="up", thick=1.6, pins=None, note=""):
    """key = Fritzing part; centre = (x, y, z) of the slab's centre. face: 'up' (component side +Z), '+x'/'-x' (vertical,
    component side toward ±X, image up = +Z), rotated by yaw about Z. pins = {label: connector id | (px, py)}."""
    P = PARTS[key]; L, W = P["w"] * K, P["h"] * K
    size = (L, W, thick) if face == "up" else (thick, L, W)
    d = add(pid, label, "board", centre, size, tex=f"tex/{key}.png", yaw=yaw, face=face, note=note)
    pins3 = {}
    for lab, ref in (pins or {}).items():
        px, py = (ref if isinstance(ref, tuple) else (P["pins"][ref]["x"], P["pins"][ref]["y"]))
        u, v = px * K - L / 2, W / 2 - py * K              # u along image x, v = image up
        if face == "up":
            dx, dy = rot2(u, v, yaw); pt = (centre[0] + dx, centre[1] + dy, centre[2] + thick / 2); n = (0, 0, 1)
        elif face == "+x":                                  # viewer in front: image right → +Y, up → +Z, normal +X
            dx, dy = rot2(thick / 2, u, yaw); pt = (centre[0] + dx, centre[1] + dy, centre[2] + v); n = rot2(1, 0, yaw) + (0,)
        else:                                               # face −X: image right → −Y
            dx, dy = rot2(-thick / 2, -u, yaw); pt = (centre[0] + dx, centre[1] + dy, centre[2] + v); n = rot2(-1, 0, yaw) + (0,)
        pins3[lab] = dict(p=[round(c, 2) for c in pt], n=[round(c, 3) for c in n])
    scene["pins"][pid] = pins3
    return d


def simple_pins(pid, pins):
    """pins = {label: ((x, y, z), (nx, ny, nz))} absolute."""
    scene["pins"][pid] = {lab: dict(p=[round(c, 2) for c in p], n=list(n)) for lab, (p, n) in pins.items()}


# ── frame ──────────────────────────────────────────────────────────────────────────────────────────────────
for r in by["RAIL"]:
    along = "x" if "X" in r["orientation"] else "y"
    add("RAIL", f"2020 rail ({r['instance']})", "rail", (r["x"], r["y"], r["z"]), (r["l"], r["w"], r["h"]), along=along)
for c in by["CNR"]:
    add("CNR", "corner bracket", "box", (c["x"], c["y"], c["z"]), (c["l"], c["w"], c["h"]), color="#9aa0a6")
for b in by["BRK"]:
    add("BRK", "motor bracket", "box", (b["x"], b["y"], b["z"]), (b["l"], b["w"], b["h"]), color="#5c636a")
for p in by["PETG"]:
    inst = str(p.get("instance", "")); name = p.get("part", "")
    if "tile" in name.lower() or "deck" in name.lower():
        tile = {"front-left": "deck_FL", "front-right": "deck_FR", "rear-left": "deck_RL", "rear-right": "deck_RR"}
        key = next((v for k, v in tile.items() if k in inst.lower()), None)
        if key:
            add("DECK", f"deck tile {inst}", "stl", (p["x"], p["y"], p["z"]), (p["l"], p["w"], p["h"]), model=f"../cad/{key}.stl", color="#d9d2c5"); continue
    add("PETG", f"{name} ({inst})", "box", (p["x"], p["y"], p["z"]), (p["l"], p["w"], p["h"]), color="#d9d2c5", note=p.get("note", ""))

# ── drivetrain ─────────────────────────────────────────────────────────────────────────────────────────────
for m in by["MOT"]:
    wheel = "FL" if (m["x"] > 0 and m["y"] > 0) else "FR" if (m["x"] > 0) else "BL" if m["y"] > 0 else "BR"
    axis = {"FL": "Y", "FR": "A", "BL": "X", "BR": "Z"}[wheel]
    side = 1 if m["y"] > 0 else -1
    add(f"M_{wheel}", f"{wheel} motor — NEMA 17 (axis {axis})", "stl", (m["x"], m["y"], m["z"]), (m["l"], m["w"], m["h"]), model="models/nema17.stl", color="#8d939a", shaft=[0, side, 0])
    # 4 coil pins on the motor's inboard (rear) face, 4 mm apart along X, 8 mm below the axle
    x0 = m["x"]; yb = m["y"] - side * 21.0; z0 = m["z"] - 8
    simple_pins(f"M_{wheel}", {lab: ((x0 + (i - 1.5) * 4.0, yb, z0), (0, -side, 0)) for i, lab in enumerate(("coil A +", "coil A −", "coil B +", "coil B −"))})
for w in by["WHL"]:
    wheel = "FL" if (w["x"] > 0 and w["y"] > 0) else "FR" if (w["x"] > 0) else "BL" if w["y"] > 0 else "BR"
    add(f"W_{wheel}", f"{wheel} mecanum wheel ({'left' if 'left-hand' in str(w.get('instance', '')) else 'right'}-hand)", "mecanum", (w["x"], w["y"], w["z"]), (w["l"], w["w"], w["h"]), hand="L" if "left-hand" in str(w.get("instance", "")) else "R", color="#2b2b2b")

# ── electronics on the deck ────────────────────────────────────────────────────────────────────────────────
u = find("UNO"); z0 = u["z"] - u["h"] / 2                   # bottom of the stack
board("R4", "UNO R4 WiFi (drawn as an Uno)", "uno", (u["x"], u["y"], z0 + 10 + 0.8), yaw=0, pins={"USB-C": (14, 44)}, note=u.get("note", ""))
sh = board("SHIELD", "CNC Shield v3 + DRV8825 ×4", "cnc", (u["x"] + 2, u["y"], z0 + 10 + 15 + 0.8), yaw=0, note="Stacked on the R4. " + u.get("note", ""),
           pins={"VMOT": "connector30", "GND": "connector29", "Z+ signal": "connector79", "Z+ GND": "connector80",
                 "X 2B": "connector37", "X 2A": "connector38", "X 1A": "connector39", "X 1B": "connector40",
                 "Y 2B": "connector57", "Y 2A": "connector58", "Y 1A": "connector59", "Y 1B": "connector60",
                 "SDA": "connector74", "SCL": "connector72", "5V": "connector75", "GND c": "connector76",
                 "Z 2B": "connector47", "Z 2A": "connector48", "Z 1A": "connector49", "Z 1B": "connector50",
                 "A 2B": "connector67", "A 2A": "connector68", "A 1A": "connector69", "A 1B": "connector70"})
for ax, (px, py) in {"X": (104, 68), "Y": (205, 68), "Z": (104, 180), "A": (205, 180)}.items():
    board(f"DRV_{ax}", f"DRV8825 ({ax})", "drv8825", (sh["pos"][0] + (px * K - sh["size"][0] / 2), sh["pos"][1] + (sh["size"][1] / 2 - py * K), sh["pos"][2] + 11), yaw=90, thick=1.2)
pi = find("PI")
board("PI", "Raspberry Pi 4", "pi4", (pi["x"], pi["y"], pi["z"] - pi["h"] / 2 + 8 + 0.8), yaw=180, note=pi.get("note", ""),
      pins={**{f"{i + 1}": f"connector{i}" for i in range(40)}, "USB 1: webcam": (410, 118), "USB 2: hub": (410, 150), "USB 3: free": (410, 208), "USB 4: free": (410, 242), "USB-C": (55, 268)})
xl = find("XL4015")
board("XL4015", "XL4015 buck → 5.0 V (drawn as the LM2596 module)", "lm2596", (xl["x"], xl["y"], xl["z"] - xl["h"] / 2 + 6 + 0.8), yaw=0,
      pins={"IN+": "connector0", "IN−": "connector1", "OUT+": "connector2", "OUT−": "connector3"}, note=xl.get("note", ""))
e3 = find("ESP32", "#3")
board("ESP3", "ESP32-S3 no.3 csi_rx_udp (drawn as a C3 devkit)", "esp32c3", (e3["x"], e3["y"], e3["z"] - e3["h"] / 2 + 6 + 0.8), yaw=-90, pins={"USB-C": (60, 207)}, note=e3.get("note", ""))
th = find("THERM")
board("MLX", "MLX90640 thermal array", "mlx90640", (th["x"], th["y"], th["z"]), face="+x", pins={"VIN 3V3": "connector31", "GND": "connector33", "SCL": "connector34", "SDA": "connector35"}, note=th.get("note", ""))
for r in by["LD2410C"]:
    left = r["y"] > 0
    board("LDL" if left else "LDR", f"LD2410C {'LEFT' if left else 'RIGHT'}", "ld2410", (r["x"], r["y"], r["z"]), face="+x", yaw=30 if left else -30,
          pins={"1 TX": "connector0", "2 RX": "connector1", "3 OUT": "connector2", "4 GND": "connector3", "5 VCC": "connector4"}, note=r.get("note", ""))
mic = find("MIC")
board("MIC", "INMP441 mic (Adafruit art)", "i2smic", (mic["x"], mic["y"], mic["z"]), face="+x", pins={"VDD 3V3": "connector17", "GND": "connector18", "SCK": "connector19", "WS": "connector21", "SD": "connector20", "L/R": "connector22"})
for t in by["TOF"]:
    front = t["x"] > 0
    board("TOF_F" if front else "TOF_R", f"VL53L1X ToF {'FRONT' if front else 'REAR'}", "vl53l1x", (t["x"], t["y"], t["z"]), face="+x" if front else "-x",
          pins={"VIN 3V3": "connector29", "GND": "connector30", "SDA": "connector32", "SCL": "connector31", "XSHUT": "connector34"}, note=t.get("note", ""))

# plain parts with hand-placed pins
ld = find("LD2450")
add("LD2450", "LD2450 radar (on the Pi UART)", "box", (ld["x"], ld["y"], ld["z"]), (ld["l"], ld["w"], ld["h"]), color="#1d4f91", note=ld.get("note", ""))
simple_pins("LD2450", {lab: ((ld["x"] + 2, ld["y"] + (i - 1.5) * 3.0, ld["z"] - ld["h"] / 2 - 1), (1, 0, 0)) for i, lab in enumerate(("5V", "GND", "TX", "RX"))})
lp = find("LIPO")
add("PACK", "HOOVO 3S 2200 mAh LiPo", "box", (lp["x"], lp["y"], lp["z"]), (lp["l"], lp["w"], lp["h"]), color="#f5c400", note=lp.get("note", ""))
simple_pins("PACK", {"V+": ((lp["x"] - lp["l"] / 2, lp["y"] + 4, lp["z"]), (-1, 0, 0)), "GND": ((lp["x"] - lp["l"] / 2, lp["y"] - 4, lp["z"]), (-1, 0, 0))})
tp = find("T-plug")
add("PLUG", "Deans pull-plug = E-STOP", "box", (tp["x"], tp["y"], tp["z"]), (tp["l"], tp["w"], tp["h"]), color="#c0392b", note=tp.get("note", ""))
simple_pins("PLUG", {"pack +": ((tp["x"] - tp["l"] / 2, tp["y"] + 3, tp["z"]), (-1, 0, 0)), "pack −": ((tp["x"] - tp["l"] / 2, tp["y"] - 3, tp["z"]), (-1, 0, 0)),
                     "rover +": ((tp["x"] + tp["l"] / 2, tp["y"] + 3, tp["z"]), (1, 0, 0)), "rover −": ((tp["x"] + tp["l"] / 2, tp["y"] - 3, tp["z"]), (1, 0, 0))})
bk = find("BANK")
add("BANK", "USB power bank 5 V / 3 A", "box", (bk["x"], bk["y"], bk["z"]), (bk["l"], bk["w"], bk["h"]), color="#5c636a", rounded=True, note=bk.get("note", ""))
simple_pins("BANK", {"USB-A out": ((bk["x"] - bk["l"] / 2, bk["y"], bk["z"]), (-1, 0, 0))})
b2 = find("BANK2")
add("BANK2", "second power bank — ESP32 only", "box", (b2["x"], b2["y"], b2["z"]), (b2["l"], b2["w"], b2["h"]), color="#5c636a", rounded=True, note=b2.get("note", ""))
simple_pins("BANK2", {"USB-A out": ((b2["x"] + b2["l"] / 2, b2["y"], b2["z"]), (1, 0, 0))})
hb = find("HUB")
add("HUB", "4-port USB hub", "box", (hb["x"], hb["y"], hb["z"]), (hb["l"], hb["w"], hb["h"]), color="#2b2b2b", note=hb.get("note", ""))
simple_pins("HUB", {"upstream": ((hb["x"] - hb["l"] / 2, hb["y"], hb["z"]), (-1, 0, 0)),
                    **{lab: ((hb["x"] + hb["l"] / 2, hb["y"] + (1.5 - i) * 7.0, hb["z"]), (1, 0, 0)) for i, lab in enumerate(("port 1: UNO R4", "port 2: CP2102 no.1", "port 3: CP2102 no.2", "port 4: free"))}})
cp = find("CP2102")
for i, cid in enumerate(("CP1", "CP2")):
    cx, cy = cp["x"] + (i - 0.5) * 20.0, cp["y"]
    add(cid, f"CP2102 no.{i + 1}", "box", (cx, cy, cp["z"]), (16, 50, 8), color="#c0392b", note=cp.get("note", ""))
    simple_pins(cid, {"5V": ((cx, cy - 25, cp["z"]), (0, -1, 0)), **{lab: ((cx + (j - 2) * 2.5, cy + 25, cp["z"]), (0, 1, 0)) for j, lab in enumerate(("3V3", "GND", "TXD", "RXD", "DTR"))}})
fa = find("FAN")
add("FAN", "40 mm 5 V fan", "stl", (fa["x"], fa["y"], fa["z"]), (fa["l"], fa["w"], fa["h"]), model="models/fan40.stl", color="#222222", note=fa.get("note", ""))
simple_pins("FAN", {"5V (red)": ((fa["x"] - 18, fa["y"] + 18, fa["z"]), (-1, 0, 0)), "GND (black)": ((fa["x"] - 18, fa["y"] + 14, fa["z"]), (-1, 0, 0))})
pt = find("PT")
tz = pt["z"] + pt["h"] / 2 + 18
add("PT", "Ceres turret base", "box", (pt["x"], pt["y"], pt["z"]), (pt["l"], pt["w"], pt["h"]), color="#d9d2c5")
pc = find("PCA")
board("PCA", "PCA9685 servo driver", "pca9685", (pc["x"], pc["y"], pc["z"] - pc["h"] / 2 + 6 + 0.8), yaw=0, note=pc.get("note", ""),
      pins={"GND": "connector42", "OE": "connector41", "SCL": "connector40", "SDA": "connector39", "VCC": "connector38", "V+": "connector7", "GND T": "connector8",
            "ch3 PWM": "connector25", "ch3 V+": "connector26", "ch3 GND": "connector27", "ch2 PWM": "connector28", "ch2 V+": "connector29", "ch2 GND": "connector30", "ch15 V+": "connector50", "ch15 GND": "connector51"})
add("PAN", "MG996R pan servo (drawn as a Futaba S3003)", "stl", (pt["x"], pt["y"], pt["z"] + pt["h"] / 2 + 12), (40, 20, 36), model="models/servo.stl", color="#1f1f1f")
simple_pins("PAN", {"signal (orange)": ((pt["x"] - 20, pt["y"] + 4, pt["z"] + 8), (-1, 0, 0)), "V+ (red)": ((pt["x"] - 20, pt["y"], pt["z"] + 8), (-1, 0, 0)), "GND (brown)": ((pt["x"] - 20, pt["y"] - 4, pt["z"] + 8), (-1, 0, 0))})
tz += 30
add("TILT", "MG996R tilt servo (drawn as a Futaba S3003)", "stl", (pt["x"], pt["y"], tz), (40, 20, 36), model="models/servo.stl", color="#1f1f1f")
simple_pins("TILT", {"signal (orange)": ((pt["x"] - 20, pt["y"] + 4, tz - 10), (-1, 0, 0)), "V+ (red)": ((pt["x"] - 20, pt["y"], tz - 10), (-1, 0, 0)), "GND (brown)": ((pt["x"] - 20, pt["y"] - 4, tz - 10), (-1, 0, 0))})
cam = find("CAM")
add("CAM", "Webcam (turret)", "box", (cam["x"], cam["y"], cam["z"]), (cam["l"], cam["w"], cam["h"]), color="#1f1f1f", note=cam.get("note", ""))
simple_pins("CAM", {"USB-A": ((cam["x"] - cam["l"] / 2, cam["y"], cam["z"]), (-1, 0, 0))})
add("ESP2", "ESP32-S3 no.2 csi_tx — OFF the rover (shown 0.5 m behind)", "box", (-520, 250, 12), (25, 44, 8), color="#444444", ghost=True)
co2 = find("CO2")
add("CO2", "SCD41 CO2 (optional)", "box", (co2["x"], co2["y"], co2["z"]), (co2["l"], co2["w"], co2["h"]), color="#888888", ghost=True)

# ── wires from the net list ────────────────────────────────────────────────────────────────────────────────
ALIAS = {   # net-list connector id → (scene part, pin label mapping)
    "SHIELD_PWR": ("SHIELD", {}), "SHIELD_I2C": ("SHIELD", {"GND": "GND c"}),
    "PCA_LOGIC": ("PCA", {}), "PCA_PWR": ("PCA", {"GND": "GND T"}), "PCA_CH3": ("PCA", {"PWM": "ch3 PWM", "V+": "ch3 V+", "GND": "ch3 GND"}),
    "PCA_CH2": ("PCA", {"PWM": "ch2 PWM", "V+": "ch2 V+", "GND": "ch2 GND"}), "PCA_CH15": ("PCA", {"V+": "ch15 V+", "GND": "ch15 GND"}),
    "X_MOT": ("SHIELD", {"2B": "X 2B", "2A": "X 2A", "1A": "X 1A", "1B": "X 1B"}), "Y_MOT": ("SHIELD", {"2B": "Y 2B", "2A": "Y 2A", "1A": "Y 1A", "1B": "Y 1B"}),
    "Z_MOT": ("SHIELD", {"2B": "Z 2B", "2A": "Z 2A", "1A": "Z 1A", "1B": "Z 1B"}), "A_MOT": ("SHIELD", {"2B": "A 2B", "2A": "A 2A", "1A": "A 1A", "1B": "A 1B"}),
    "R4_USB": ("R4", {}), "PI_USB": ("PI", {}), "PI_PWR": ("PI", {}), "PI": ("PI", "pinnum"),
}
missing = []
for sheet, rows in NETD["connections"].items():
    doc = NET[sheet]
    for row in rows:
        (a, pa), (w, wi), (b, pb) = row[0], row[1], row[-1]
        cab = doc["cables"][w]; col = HEX[cab["colors"][int(wi) - 1]]; rad = RADIUS.get(cab["gauge"], 0.7)
        ends = []
        for cid, lab in ((a, pa), (b, pb)):
            part, mp = ALIAS.get(cid, (cid, {}))
            key = lab.split()[0] if mp == "pinnum" else (mp.get(lab, lab) if isinstance(mp, dict) else lab)
            pin = scene["pins"].get(part, {}).get(key)
            if pin is None: missing.append(f"{sheet}: {cid}:{lab} → {part}:{key}"); break
            ends.append((part, key, pin))
        if len(ends) == 2:
            scene["wires"].append(dict(sheet=sheet, a=ends[0][2]["p"], na=ends[0][2]["n"], b=ends[1][2]["p"], nb=ends[1][2]["n"], color=col, r=rad,
                                       fa=f"{a}:{pa}", fb=f"{b}:{pb}", pa=ends[0][0], pb=ends[1][0], gauge=cab["gauge"]))

out = os.path.join(ROOT, "bom-site", "rover3d", "scene.json")
json.dump(scene, open(out, "w"), separators=(",", ":"))
print(f"scene: {len(scene['parts'])} parts, {len(scene['wires'])} wires, {sum(len(v) for v in scene['pins'].values())} pins → {out} ({os.path.getsize(out)//1024} kB)")
if missing:
    print("UNMAPPED pins:"); [print("  ", m) for m in missing]
