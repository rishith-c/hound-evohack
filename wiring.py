#!/usr/bin/env python3
"""
wiring.py — the rover's electrical netlist and its checks. Source of truth for
every wire, rail, connector and signal; bom.json prose must agree with THIS.

Run:  python3 wiring.py        (exit 1 on any FAIL; writes wiring.json for build.py)

Every number below is either a datasheet figure (DS), a listing figure (LISTING),
an output of drivetrain.py (DT) or an allocation (ALLOC). Nothing is a guess.
"""
import json, sys

# ── Reference data ────────────────────────────────────────────────────────────
OHM_PER_M = {14: 0.00828, 16: 0.0132, 18: 0.0210, 20: 0.0333, 22: 0.0530, 24: 0.0842, 26: 0.134, 28: 0.213}  # copper, 20 °C
AMPACITY  = {14: 32, 16: 22, 18: 16, 20: 11, 22: 7, 24: 3.5, 26: 2.2, 28: 1.4}   # chassis wiring, short runs, free air
CONNECTOR_A = {"T-plug (Deans)": 50, "Wago 221-415": 32, "screw terminal 5.08": 10, "solder pad": 10, "Dupont 2.54": 2.0,
               "JST-XH 2.54": 3.0, "JST 1.25": 1.0, "USB-A": 1.5, "USB-C": 3.0, "header 2.54": 2.0}
V_DROP_MAX = 0.03           # 3 % of rail per segment
BUCK_EFF = 0.85             # XL4015 / LM2596 at these ratios, DS typical

# ── Rails ─────────────────────────────────────────────────────────────────────
# v_min is the worst case the loads see (pack sagged / buck ripple); v_max the best case (pack fresh).
RAILS = {
    "PACK":     dict(desc="HOOVO 3S 2200 mAh 80C, T-plug",        v_nom=11.1, v_min=10.5, v_max=12.6, i_cont=44.0, i_peak=100.0, src=None,
                     note="2200 mAh × 20C = 44 A continuous, taken as the honest figure, not 80C. (LISTING/ALLOC)"),
    "V_SERVO":  dict(desc="XL4015 trimmed to 5.0 V → PCA9685 V+ terminal (tilt ch 3, pan ch 2, fan on ch 15's V+/GND pins)", v_nom=5.0, v_min=4.85, v_max=5.15, i_cont=4.0, i_peak=5.0, src="PACK",
                     note="5 A module derated to 4 A continuous with the heatsink. 5.0 V instead of 6.0 V so a 5 V fan and the ESP32's 5V pin can share it: MG996R runs 4.8–7.2 V (DS), tilt load is tiny. (LISTING/DS)"),
    "V5_BANK2": dict(desc="second USB power bank → ESP32-S3 #3 USB-C", v_nom=5.0, v_min=4.75, v_max=5.25, i_cont=1.0, i_peak=2.0, src=None,
                     note="Any small bank (≥ 1 A). Its only load is the CSI node, so the rover's own power never touches it. (ALLOC)"),
    "V5_BANK":  dict(desc="USB power bank → Pi USB-C",            v_nom=5.0,  v_min=4.75, v_max=5.25, i_cont=3.0,  i_peak=3.0,   src=None,
                     note="Must be a genuine 5 V / 3 A bank; 2.4 A banks fail this file. (ALLOC)"),
    "V5_PI_USB":dict(desc="Pi 4 downstream USB (4 ports, shared)", v_nom=5.0,  v_min=4.75, v_max=5.25, i_cont=1.2,  i_peak=1.2,   src="V5_BANK",
                     note="Pi 4 shares 1.2 A across all four ports (DS). Pi 5 defaults to 0.6 A unless usb_max_current_enable=1."),
    "V3_PI":    dict(desc="Pi 3.3 V header pin",                  v_nom=3.3,  v_min=3.2,  v_max=3.4,  i_cont=0.5,  i_peak=0.8,   src="V5_BANK",
                     note="Pi 4 3.3 V rail budget for HATs/peripherals ≈ 0.5 A. (DS)"),
}

# ── Loads: what hangs on each rail ────────────────────────────────────────────
# (name, rail, vin_min, vin_max, i_avg, i_peak, connector, source-of-number)
LOADS = [
    ("4× DRV8825 + JK42HS40 motors (bus side)", "PACK",     8.2, 45.0, 1.96, 4.00, "screw terminal 5.08", "DT: 20.5 W at 10.5 V cruise; 4 A allocated for a ramp burst"),
    ("XL4015 input (second wires in the shield's power screws)", "PACK", 4.0, 38.0, None, None, "screw terminal 5.08", "LISTING; current computed from its load"),
    ("MG996R tilt servo on PCA9685 channel 3", "V_SERVO", 4.8, 7.2, 0.30, 2.10, "header 2.54", "DS: stall ≈ 2.5 A at 6 V → ~2.1 A at 5 V"),
    ("MG996R pan servo on PCA9685 channel 2", "V_SERVO", 4.8, 7.2, 0.30, 2.10, "header 2.54", "DS: same servo class; the Ceres pan unit worked in its demo (user), driven as angle or timed nudge"),
    ("40 mm 5 V fan on PCA9685 channel 15's V+/GND pins", "V_SERVO", 4.5, 5.5, 0.15, 0.20, "header 2.54", "LISTING: 5 V 0.15 A"),
    ("PCA9685 logic (VCC from the shield's 5V pin)", "V5_PI_USB", 2.3, 5.5, 0.01, 0.01, "header 2.54", "DS; rides on the R4's USB 5 V"),
    ("ESP32-S3 #3 CSI receiver (USB-C from its own power bank)", "V5_BANK2", 4.75, 5.25, 0.25, 0.50, "USB-C", "DS: WiFi bursts to ~500 mA; csi_rx_udp firmware"),
    ("Raspberry Pi 4 itself",                   "V5_BANK",  4.75, 5.25, 0.70, 1.20, "USB-C",              "DS: idle 0.6 A, loaded 1.2 A without USB peripherals"),
    ("Webcam (C920-class, 1080p)",              "V5_PI_USB",4.75, 5.25, 0.25, 0.30, "USB-A",              "MEASURED-class: a C920 draws ~240 mA; its 500 mA descriptor is the enumeration allowance, not draw (peak taken as 0.30 A)"),
    ("UNO R4 WiFi + shield logic",              "V5_PI_USB",4.75, 5.25, 0.15, 0.20, "USB-A",              "DS: radio off"),
    ("2× CP2102 USB-serial adapters + 4-port hub","V5_PI_USB",4.75, 5.25, 0.045, 0.075, "USB-A",           "DS: ~15 mA (25 mA peak) each + the hub's own ~15 mA"),
    ("LD2410C radar LEFT (VCC from its CP2102's 5V pin)", "V5_PI_USB", 4.5, 5.5, 0.08, 0.10, "JST 1.25", "DS: ≤ 80 mA"),
    ("LD2410C radar RIGHT (VCC from its CP2102's 5V pin)", "V5_PI_USB", 4.5, 5.5, 0.08, 0.10, "JST 1.25", "DS: ≤ 80 mA"),
    ("LD2450 radar (5V from the Pi header pin 4)", "V5_BANK", 4.5, 5.5, 0.10, 0.20, "header 2.54",        "DS: ≤ 200 mA. The header 5 V pins sit on the Pi's input net: this load is on the bank, outside the 1.2 A USB budget"),
    ("MLX90640 thermal array",                  "V3_PI",    3.0,  3.6,  0.023, 0.025, "header 2.54",      "DS: 23 mA"),
    ("VL53L1X ToF front",                       "V3_PI",    2.6,  3.6,  0.02, 0.04, "header 2.54",        "DS"),
    ("VL53L1X ToF rear",                        "V3_PI",    2.6,  3.6,  0.02, 0.04, "header 2.54",        "DS"),
    ("INMP441 microphone",                      "V3_PI",    1.8,  3.6,  0.0015, 0.002, "header 2.54",     "DS"),
    ("SCD41 CO2 (optional)",                    "V3_PI",    2.4,  5.5,  0.018, 0.205, "header 2.54",      "DS: 205 mA peak during a measurement"),
]

# ── Wire segments: (name, awg, length_m, connector at the far end) — current is derived from the loads
WIRES = [
    ("pack lead: HOOVO T-plug → OliRC extension (the pull-plug disconnect on the deck) → shield VMOT/GND terminal", 14, 0.45, "screw terminal 5.08", "PACK_TOTAL"),
    ("shield VMOT/GND screws (second wire) → XL4015 IN",             22, 0.15, "screw terminal 5.08", "XL_IN"),
    ("XL4015 OUT pads → PCA9685 V+ / GND screw terminal", 22, 0.15, "screw terminal 5.08", "RAIL:V_SERVO"),
    ("shield driver socket → 4-pin motor cable → motor (per phase)", 26, 0.40, "Dupont 2.54",      "PHASE"),
    ("bank → Pi USB-C cable (SPEC: ≤ 0.2 m, 22 AWG or heavier power conductors)", 22, 0.20, "USB-C", "RAIL:V5_BANK"),
    ("bank 2 → ESP32-S3 #3 USB-C",                                  28, 0.30, "USB-C",            "PACK_LOAD:ESP32-S3 #3 CSI receiver (USB-C from its own power bank)"),
    ("Pi USB-A → webcam (captive cable, 1.5 m)",                    28, 1.50, "USB-A",            "PACK_LOAD:Webcam (C920-class, 1080p)"),
    ("Pi USB-A → UNO R4 USB-C",                                     28, 0.30, "USB-A",            "PACK_LOAD:UNO R4 WiFi + shield logic"),
    ("Pi USB-A → hub → 2× CP2102 (the LD2410Cs' power rides on these)", 28, 0.30, "USB-A",         "HUB_TOTAL"),
    ("CP2102 +5V/GND/TXD/RXD → LD2410C (4 wires, 0.25 m)",           26, 0.25, "Dupont 2.54",      "PACK_LOAD:LD2410C radar LEFT (VCC from its CP2102's 5V pin)"),
    ("Pi header pins 4 (5V) / 34 (GND) / 8 (TXD) / 10 (RXD) → LD2450 (4 wires, 0.25 m)", 26, 0.25, "Dupont 2.54", "PACK_LOAD:LD2450 radar (5V from the Pi header pin 4)"),
]

# ── Signals: (driver, pin(s), V_out_high, receiver, pin(s), V_in_max, V_ih_min, bus)
SIGNALS = [
    ("UNO R4 (5 V logic)", "D2/D5 D3/D6 D4/D7 D12/D13 STEP/DIR, D8 EN", 5.0, "DRV8825 ×4", "STEP DIR nENABLE", 5.25, 2.2, "R4"),
    ("LD2410C left TX (3.3 V)", "TX", 3.3, "CP2102 #1", "RXD (3.3 V logic)", 3.6, 2.0, "USB"),
    ("CP2102 #1 TXD", "TXD", 3.3, "LD2410C left", "RX", 3.6, 2.0, "USB"),
    ("LD2410C right TX (3.3 V)", "TX", 3.3, "CP2102 #2", "RXD", 3.6, 2.0, "USB"),
    ("CP2102 #2 TXD", "TXD", 3.3, "LD2410C right", "RX", 3.6, 2.0, "USB"),
    ("LD2450 TX (3.3 V)", "TX", 3.3, "Pi BCM 15 (UART0 RXD, header pin 10)", "RXD", 3.6, 2.0, "UART"),
    ("Pi BCM 14 (UART0 TXD, header pin 8)", "TXD", 3.3, "LD2450", "RX", 3.6, 2.0, "UART"),
    ("Pi I2C-1 (BCM 2/3, pull-ups 3.3 V)", "SDA/SCL", 3.3, "MLX90640 0x33, VL53L1X 0x29→0x30, SCD41 0x62", "SDA/SCL", 3.6, 2.3, "I2C1"),
    ("UNO R4 Wire (A4/A5 on the shield's SDA/SCL comms header, 5 V I2C, PCA9685's own 10 kΩ pull-ups)", "SDA/SCL", 5.0, "PCA9685 0x40", "SDA/SCL", 5.5, 3.0, "R4I2C"),
    ("PCA9685 (VCC 5 V) channels 3 / 2", "PWM3 PWM2", 5.0, "MG996R tilt / pan servos", "signal", 5.5, 2.4, "PCA"),
    ("Pi BCM 22 / 27", "XSHUT out", 3.3, "VL53L1X front / rear", "XSHUT (pull-up to VIN = 3.3)", 3.6, 1.2, "GPIO"),
    ("Pi I2S (BCM 18/19/20)", "BCLK/LRCLK/DIN", 3.3, "INMP441", "SCK/WS/SD", 3.6, 2.3, "I2S"),
    ("Pi ↔ UNO R4", "USB CDC", 5.0, "UNO R4", "USB", 5.25, 0, "USB"),
    ("Pi ↔ 2× CP2102", "USB → /dev/serial/by-path (by hub socket: cheap CP2102s share serial 0001, so by-id shows one)", 5.0, "LD2410C left/right at 256000 baud", "USB", 5.25, 0, "USB"),
    ("ESP32-S3 #2 csi_tx, OFF the rover 3 m along the wall on any USB 5 V: 100 Hz ESP-NOW probes, channel 6", "radio", 0, "ESP32-S3 #3 csi_rx_udp on the rover: CSI of every probe → UDP to the Pi hotspot (channel 6) port 5005", "wlan0", 0, 0, "WIFI"),
]

PI_BCM = {"I2C1 SDA": 2, "I2C1 SCL": 3, "UART0 TXD → LD2450 RX": 14, "UART0 RXD ← LD2450 TX": 15, "I2S BCLK": 18, "I2S LRCLK": 19, "I2S DIN": 20, "XSHUT front": 22, "XSHUT rear": 27}
R4_PINS = {"X STEP": 2, "Y STEP": 3, "Z STEP": 4, "X DIR": 5, "Y DIR": 6, "Z DIR": 7, "ENABLE": 8, "A STEP (jumper SpnEn)": 12, "A DIR (jumper SpnDir)": 13,
           "I2C SDA → PCA9685 (shield comms header)": 18, "I2C SCL → PCA9685 (shield comms header)": 19}
R4_RESERVED_BY_SHIELD = {9: "X limit", 10: "Y limit", 11: "Z limit", 14: "A0 abort", 15: "A1 hold", 16: "A2 resume", 17: "A3 coolant (free: no divider fitted, vcut stays 0)"}
ESP1_GPIO = {}   # ESP32 #1 is now the spare: the radars reach the Pi through two CP2102 adapters and the Pi's own UART
ESP32S3_AVOID = {0: "strap", 3: "strap", 45: "strap", 46: "strap", 19: "USB D-", 20: "USB D+", 43: "UART0 TX (console)", 44: "UART0 RX (console)"}
I2C_BUSES = {
    "I2C1": [("MLX90640", 0x33, 400), ("VL53L1X front (re-addressed)", 0x30, 400), ("VL53L1X rear", 0x29, 400), ("SCD41 (optional)", 0x62, 100)],
    "R4 Wire": [("PCA9685", 0x40, 400)],
}

# ── Checks ────────────────────────────────────────────────────────────────────
R = []                      # (level, id, text)
def out(level, cid, text): R.append((level, cid, text))
PASS, WARN, FAIL, VERIFY, PROC = "PASS", "WARN", "FAIL", "VERIFY", "PROCEDURE"

loads_on = lambda rail: [l for l in LOADS if l[1] == rail and l[4] is not None]
def rail_sum(rail, k):      # k = 4 avg, 5 peak
    return sum(l[k] for l in loads_on(rail))

# 1. buck input currents, computed from their output loads
def buck_in(rail_out, k, v_in):
    return RAILS[rail_out]["v_nom"] * rail_sum(rail_out, k) / (BUCK_EFF * v_in)
XL_IN_AVG,  XL_IN_PK  = buck_in("V_SERVO", 4, RAILS["PACK"]["v_nom"]), buck_in("V_SERVO", 5, RAILS["PACK"]["v_min"])
MOT = next(l for l in LOADS if l[0].startswith("4× DRV8825"))
PACK_AVG = MOT[4] + XL_IN_AVG
PACK_PK  = MOT[5] + XL_IN_PK
PI3_AVG_AT5 = rail_sum("V3_PI", 4) * 3.3 / (0.9 * 5.0);  PI3_PK_AT5 = rail_sum("V3_PI", 5) * 3.3 / (0.9 * 5.0)
BANK_AVG = rail_sum("V5_BANK", 4) + rail_sum("V5_PI_USB", 4) + PI3_AVG_AT5
BANK_PK  = rail_sum("V5_BANK", 5) + rail_sum("V5_PI_USB", 5) + PI3_PK_AT5

HUB_LOADS = [l for l in LOADS if "CP2102" in l[0] or l[0].startswith("LD2410C")]
CURRENT = {"PACK_TOTAL": (PACK_AVG, PACK_PK), "XL_IN": (XL_IN_AVG, XL_IN_PK),
           "RAIL:V_SERVO": (rail_sum("V_SERVO", 4), rail_sum("V_SERVO", 5)),
           "HUB_TOTAL": (sum(l[4] for l in HUB_LOADS), sum(l[5] for l in HUB_LOADS)),
           "RAIL:V5_BANK": (BANK_AVG, BANK_PK), "PHASE": (1.5 * 0.71, 1.5),
           "PACK:4× DRV8825 + JK42HS40 motors (bus side)": (MOT[4], MOT[5])}
for l in LOADS: CURRENT[f"PACK_LOAD:{l[0]}"] = (l[4] or 0, l[5] or 0)

# 2. every load inside its rail's voltage window (worst case both ends)
for name, rail, vmin, vmax, ia, ip, conn, src in LOADS:
    r = RAILS[rail]
    if r["v_min"] < vmin or r["v_max"] > vmax:
        out(FAIL, "V-window", f"{name}: rail {rail} spans {r['v_min']}–{r['v_max']} V but the part accepts {vmin}–{vmax} V ({src})")
    else:
        out(PASS, "V-window", f"{name}: {r['v_min']}–{r['v_max']} V inside {vmin}–{vmax} V")

# 3. rail current budgets
budget = {"PACK": (PACK_AVG, PACK_PK), "V_SERVO": (rail_sum("V_SERVO", 4), rail_sum("V_SERVO", 5)), "V5_BANK2": (rail_sum("V5_BANK2", 4), rail_sum("V5_BANK2", 5)),
          "V5_BANK": (BANK_AVG, BANK_PK),
          "V5_PI_USB": (rail_sum("V5_PI_USB", 4), rail_sum("V5_PI_USB", 5)), "V3_PI": (rail_sum("V3_PI", 4), rail_sum("V3_PI", 5))}
for rail, (ia, ip) in budget.items():
    r = RAILS[rail]; ua, up = ia / r["i_cont"], ip / r["i_peak"]
    lvl = FAIL if up > 1.0 or ua > 1.0 else (WARN if up > 0.85 else PASS)
    out(lvl, "I-budget", f"{rail} ({r['desc']}): avg {ia:.2f} A of {r['i_cont']} A ({ua:.0%}), peak {ip:.2f} A of {r['i_peak']} A ({up:.0%})")
out(PASS if RAILS["PACK"]["v_min"] >= RAILS["V_SERVO"]["v_nom"] + 1.0 else FAIL, "dropout", f"XL4015 needs Vin ≥ {RAILS['V_SERVO']['v_nom'] + 1.0} V; pack minimum {RAILS['PACK']['v_min']} V")
hours = 2.2 * 0.8 / PACK_AVG
out(PASS if hours * 60 >= 30 else WARN, "endurance", f"pack draw avg {PACK_AVG:.2f} A, peak {PACK_PK:.2f} A → {hours*60:.0f} min per 2200 mAh pack (80 % usable)")

# 4. wire ampacity, voltage drop, connector rating
for name, awg, length, conn, key in WIRES:
    ia, ip = CURRENT[key]
    v_ref = RAILS["PACK"]["v_nom"] if key.startswith(("PACK_TOTAL", "XL_IN")) else (6.0 if "SERVO" in key else 5.0)
    if key == "PHASE": v_ref = RAILS["PACK"]["v_nom"]
    drop = ip * OHM_PER_M[awg] * length * 2            # out and back
    amp = AMPACITY[awg]; cr = CONNECTOR_A[conn]
    lvl = PASS
    if ip > amp or ip > cr: lvl = FAIL
    elif ip > 0.8 * amp or ip > 0.8 * cr or drop > V_DROP_MAX * v_ref: lvl = WARN
    out(lvl, "wire", f"{name}: {awg} AWG × {length} m, peak {ip:.2f} A (ampacity {amp} A, {conn} {cr} A), round-trip drop {drop*1000:.0f} mV = {drop/v_ref:.1%}")

# 5. logic levels
for drv, dp, vo, rcv, rp, vmax, vih, bus in SIGNALS:
    if bus == "WIFI": out(PASS, "level", f"{drv} → {rcv}: radio link, no wire"); continue
    if vo > vmax: out(FAIL, "level", f"{drv} {dp} drives {vo} V into {rcv} {rp} rated {vmax} V max")
    elif vo < vih: out(FAIL, "level", f"{drv} {dp} high {vo} V below {rcv} V_IH {vih} V")
    else: out(PASS, "level", f"{drv} {dp} → {rcv} {rp}: {vo} V out, {vih}–{vmax} V accepted")

# 6. pin uniqueness
def unique(name, table, avoid=None):
    seen = {}
    for k, v in table.items():
        if v in seen: out(FAIL, "pins", f"{name}: pin {v} used by both '{seen[v]}' and '{k}'")
        seen[v] = k
        if avoid and v in avoid: out(FAIL, "pins", f"{name}: pin {v} ('{k}') is {avoid[v]}")
    out(PASS, "pins", f"{name}: {len(table)} pins, all distinct" + (f", none on {sorted(avoid)}" if avoid else ""))
unique("Pi BCM", PI_BCM); unique("UNO R4 / shield", R4_PINS, R4_RESERVED_BY_SHIELD)

# 7. I2C addresses and bus speed
for bus, devs in I2C_BUSES.items():
    addrs = [a for _, a, _ in devs]
    dup = {a for a in addrs if addrs.count(a) > 1}
    if dup: out(FAIL, "i2c", f"{bus}: address clash at {[hex(a) for a in dup]}")
    speed = min(s for _, _, s in devs)
    out(PASS, "i2c", f"{bus}: {', '.join(f'{n} {hex(a)}' for n, a, _ in devs)} — no clashes; bus speed limited to {speed} kHz by the slowest part")
out(VERIFY, "i2c", "Before connecting SDA/SCL: power each I2C module alone and meter SDA to GND — it must read ≤ 3.3 V. A module whose pull-ups go to 5 V goes on 3.3 V power or not on the Pi.")

# 8. USB port count and Pi 5 caveat
usb_loads = [l for l in loads_on("V5_PI_USB") if l[6] == "USB-A"]
out(PASS if len(usb_loads) <= 4 else FAIL, "usb", f"Pi USB: {len(usb_loads)} plugs in 4 ports ({', '.join(l[0].split(' (')[0] for l in usb_loads)}); the LD2410Cs ride the hub")
out(WARN, "usb", "Pi 5 only: default 600 mA USB cap → set usb_max_current_enable=1, or use the Pi 4 this file assumes.")

# 9. grounds: attachment points between the bank island (Pi, R4 logic, PCA9685 logic, radars) and the pack ground
branches = {"shield GND screw (pack −; the R4's USB GND ties it to the Pi)": 0.0,
            "servo/fan return at the XL4015 OUT− pad (via IN− from the shield GND screw)": XL_IN_PK * OHM_PER_M[22] * 0.15}
dv = max(branches.values()) - min(branches.values()); i_circ = dv / 0.4
out(PASS if dv < 0.1 else FAIL, "ground", f"star = the shield's GND screw (pack −, XL4015 IN− and the motor return all land there). Peak drop per branch: " + ", ".join(f"{k} {v*1000:.0f} mV" for k, v in branches.items()) +
    f" → ≤ {dv*1000:.0f} mV between attachment points, ~{i_circ*1000:.0f} mA circulating through USB grounds (limit 100 mV)")
out(PROC, "ground", "Servo/fan return: XL4015 OUT−, which is the same node as IN− (a buck shares its negative) and so the shield GND screw — the D11 signal is referenced to it automatically. The LD2410Cs return through their adapters (USB side), the LD2450 through the Pi header's pin 34. Pack current never flows through a board GND pin or a USB cable.")

# 10. things a checker cannot check but a build must do
out(PROC, "sequence", "Power-up: bank → Pi → R4 (USB) FIRST, then the pack at the T-plug. Power-down and BEFORE every flash/reset of the R4: pull the pack plug first. Reason: DRV8825 nENABLE has a pull-down, so while the R4 is dead or resetting all four drivers sit at full holding current (no pull-up resistor fitted — by choice; the plug order replaces it).")
out(PROC, "vref", "Read the sense resistor on one driver: R100 → Vref = 0.75 V for 1.5 A; R200 → 1.50 V. Set all four with the multimeter, motors unplugged, before any motor is connected.")
out(PROC, "microstep", "AS BUILT (v1.0 best drive): DRV8825 1/32 = M0 + M2 → caps on MS1 and MS3 under each driver, MS2 open (eight caps), plus the D12 and D13 jumpers on the A header = ten jumpers total. Caps go on before the drivers. 1/16 (one cap, MS3 only, firmware m 16) is the faster alternative — a drive-setting change, ask first.")
out(PROC, "phases", "Motor coil pairs by multimeter: the two leads that show ~2 Ω are one coil. A coil split across the 2B/2A–1A/1B header halves makes a motor buzz and not turn.")
out(WARN, "protection", "No fuse, no cell alarm, no voltage divider (all declined for simplicity): nothing stops the pack from over-discharging. Rule: a full pack (12.6 V) gives ~45 min of driving — set a 30-minute timer, then meter the pack; stop at 11.1 V, never below 10.5 V. A pack that reads 6–7 V is dead (pack A).")
out(WARN, "connector", f"Motor phases run 1.5 A through Dupont 2.54 contacts rated {CONNECTOR_A['Dupont 2.54']} A — inside rating but the crimp quality is the margin. A contact that heats in the wheels-up test gets re-crimped or soldered.")
out(VERIFY, "bank", "Load-test the bank at 2.5 A for 60 s with the meter on the Pi's 5 V pin: below 4.8 V the bank is not a 3 A bank.")
out(PROC, "csi-nodes", "CSI v2: ESP32 #2 runs csi_tx OFF the rover (dropped as far along the wall as the room allows, any USB 5 V, channel 6, 100 Hz probes). ESP32 #3 runs csi_rx_udp ON the rover from its OWN small power bank on its USB-C — nothing else plugs into it, no wire touches the rover's electronics. It streams the CSI of every probe to the Pi hotspot (channel 6), UDP port 5005. ESP32 #1 is the spare.")
out(PASS, "bulk-cap", "1000 µF 25 V across VMOT at the shield terminal (consumables) — protects the drivers from the pack lead's inductance on connect.")

# 11. voltage chain: bank → cable → Pi → USB port → the farthest device (webcam on its captive 1.5 m cable)
V_BANK_LOADED = 4.90                                      # requirement on the bank at 2.5 A (VERIFY 'bank')
drop_bank_cable = BANK_PK * OHM_PER_M[22] * 0.20 * 2 + BANK_PK * 0.03
v_pi = V_BANK_LOADED - drop_bank_cable
v_port = v_pi - 0.05                                      # Pi 4 USB power switch
cam = next(l for l in LOADS if l[0].startswith("Webcam"))
v_cam = v_port - cam[5] * OHM_PER_M[28] * 1.5 * 2
v_cam_typ = v_port - cam[4] * OHM_PER_M[28] * 1.5 * 2
out(PASS if v_pi > 4.63 + 0.10 else FAIL, "V-chain", f"Pi input {v_pi:.2f} V from a bank holding {V_BANK_LOADED} V under load through a 22 AWG × 0.2 m cable (+30 mΩ of USB contacts); the Pi's under-voltage warning is 4.63 V")
out(WARN if v_cam < 4.75 else PASS, "V-chain", f"webcam sees {v_cam:.2f} V at its 500 mA descriptor ({v_cam_typ:.2f} V at a typical 250 mA) through its own captive 1.5 m cable; USB floor 4.75 V, most cameras run to ~4.4 V. If it drops out at 1080p, run 720p — its cable cannot be shortened")
bad = BANK_PK * OHM_PER_M[28] * 1.0 * 2
out(WARN, "V-chain", f"A 1 m 28 AWG phone cable to the Pi would drop {bad:.2f} V → {V_BANK_LOADED - bad:.2f} V at the Pi = brownout. The bank cable is a spec: ≤ 0.2 m with 22 AWG or heavier power conductors (a short '3 A fast-charge' cable)")

# 12. things that turn a PASS into a FAIL if someone forgets them
out(PASS, "usb", "The two LD2410Cs are powered through their CP2102 adapters (80 + 80 mA on the hub), the LD2450 (200 mA) from the Pi header's 5 V pin, outside the USB budget; the webcam keeps its own port; ESP32 #3 is on its own bank, not on the Pi, the main bank or the servo rail")
out(WARN, "enable", "No EN pull-up fitted: during an R4 reset (~1 s at boot, every sketch upload) all four drivers are ENABLED at full holding current. Harmless for a second; NOT harmless if you flash repeatedly with the pack plugged in (drivers heat). So: pack unplugged whenever the USB cable is doing anything but driving.")
out(VERIFY, "i2c1", "One I2C bus for everything: the Pi's 1.8 kΩ pull-ups plus the boards' own 10 kΩ. i2cdetect -y 1 must show 0x33 (thermal) and 0x29 (rear ToF); the front ToF appears at 0x30 only after sensing/tof.py re-addresses it (both XSHUT low, FRONT alone → 0x30, then REAR). If the SCD41 is fitted the bus drops to 100 kHz — fine for 4 fps thermal.")
out(PROC, "servos", "PCA9685 on the CNC shield's comms header: shield SDA → PCA SDA, SCL → SCL, 5V → VCC, GND → GND (5 V I2C from the R4). XL4015 OUT+/OUT− → the PCA9685's V+/GND screw terminal. TILT servo on channel 3 (positional MG996R), PAN servo on channel 2 (continuous-rotation); brown toward the board edge = GND row. Fan red/black onto channel 15's V+ and GND pins. Firmware: nothing is driven at boot — the turret starts wherever it was set by hand. Tilt 't <deg>' 78–150 (600 + 10 µs/°), 't -1' = limp; pan only by timed eased nudges 'n -1 300' / 'n 1 300' (this servo turns right below 1500 µs, so PAN_SIGN = −1), 'p' = stop, 'T <µs>' trims the stop pulse (saved on the Pi, set with the remote's hold-still test), 'H <ms>' holds the stop pulse; 'K 1' runs the show about the start pose and 'K 0' returns to it. Status 'pca' = 1 when the board answers.")
out(WARN, "connector", f"Both servos stalling together = {rail_sum('V_SERVO', 5):.1f} A on the XL4015 (5 A peak, 4 A continuous) and 2.1 A per PCA9685 channel header (rated {CONNECTOR_A['header 2.54']} A): momentary by nature; keep stalls short with the firmware limits (tilt 78–150°) and release the servos ('t -1', 'p -1') between stations")
out(PASS, "splice", "No lever nuts, no resistor boards, one buck at 5.0 V: pack → shield terminal → (second wires) XL4015 → PCA9685 V+ terminal; servos and fan plug onto the PCA9685's headers; the PCA9685 is driven by the R4 over the shield's SDA/SCL pins; the LD2410Cs from their USB adapters, the LD2450 from the Pi header; the ESP32 from its own bank; everything else from the Pi")

# 13. pass 3 — the paths a schematic hides
radar_ret = sum(l[4] for l in LOADS if l[0].startswith("LD24"))
hub_radar = sum(l[4] for l in LOADS if l[0].startswith("LD2410C"))
out(PROC, "radar-power", f"Each LD2410C is a 4-wire job to its own CP2102: VCC → the adapter's +5V pin (never 3V3 — too weak, and the radar needs 5 V), GND → GND, TX → RXD, RX → TXD. They add {hub_radar*1000:.0f} mA to the Pi's USB budget (checked above). The adapter must be a 3.3 V-logic type: meter its TXD pin at idle — 3.3 V, not 5 V. The LD2450 ({(radar_ret - hub_radar)*1000:.0f} mA) takes no adapter: 5V → Pi pin 4, GND → pin 34 (pin 6 also works — any Pi GND pin), TX → pin 10, RX → pin 8")
out(PROC, "uart", "The LD2450 on the Pi's own UART, once: raspi-config nonint do_serial_cons 1 (no login console on it), do_serial_hw 0, add dtoverlay=disable-bt to /boot/firmware/config.txt, systemctl disable hciuart, reboot (pi/enable_gpio_uart.sh). It then reads as /dev/ttyAMA0 at 256000 baud: put that path in ~/rover/radars.json as \"ld2450\". Nothing on the rover uses Bluetooth. Never land a 5 V wire on pins 8/10")
out(VERIFY, "tilt-servo", "The tilt servo must be a 180° (positional) MG996R: with the remote, set a tilt and let go — it must stop dead. A 360° servo keeps turning under a tilt command (it reads the pulse as speed), cannot hold the camera, and winds one way under the show. TowerPro sells both with the same case")
out(PROC, "i2c-chain", "The Pi header has two 3V3 pins and one SDA/SCL pair, but four boards want 3V3 and three want SDA/SCL — one Dupont female per pin. Chain through the boards' second header/STEMMA port (Adafruit-pattern MLX/ToF boards have one), or use a mini breadboard as the 3V3/SDA/SCL splitter. Never force two females onto one pin.")
out(PROC, "pack-splice", "The shield's VMOT/GND screw terminal is the only pack splice: the 14 AWG pack lead and the 22 AWG XL4015 input wire share each screw (2.4 mm² total, inside the 5.08 mm terminal's range). Strip 7 mm, twist the two conductors together before inserting, tug-test both.")
out(PROC, "driver-orient", "DRV8825 into the shield socket with its EN pin over the socket's EN label (the trimpot ends up toward the shield's power terminal on genuine Pololu layouts; clones vary — go by the label). Backwards = dead driver on power-up, no warning")
out(PROC, "cap-polarity", "1000 µF electrolytic across VMOT: stripe = negative, to the GND terminal. Reversed, it vents on the first power-up")
out(VERIFY, "bank-cable", "If the bank's output is USB-C and the Pi 4 is an early board (pre-2020, rev 1.1), an e-marked C-to-C cable will not power it — use an A-to-C cable or a plain C-to-C. Later Pi 4s and all Pi 5s are fine")
out(PROC, "fan", "The 40 mm 5 V fan plugs onto the PCA9685's channel-15 header: red → the middle (V+) pin, black → the bottom (GND) pin. The XL4015 is set to 5.0 V for exactly this; the tilt servo is fine at 5 V.")

# ── Report ────────────────────────────────────────────────────────────────────
order = {FAIL: 0, WARN: 1, VERIFY: 2, PROC: 3, PASS: 4}
counts = {k: sum(1 for l, _, _ in R if l == k) for k in order}
print(f"WIRING CHECK — {len(LOADS)} loads, {len(WIRES)} wire segments, {len(SIGNALS)} signal links\n{'='*100}")
for lvl, cid, text in sorted(R, key=lambda r: (order[r[0]], r[1])):
    print(f"  {lvl:9s} {cid:10s} {text}")
print(f"\n  {counts[FAIL]} FAIL · {counts[WARN]} WARN · {counts[VERIFY]} VERIFY · {counts[PROC]} PROCEDURE · {counts[PASS]} PASS")
print(f"  pack: {PACK_AVG:.2f} A avg / {PACK_PK:.2f} A peak · bank: {BANK_AVG:.2f} A avg / {BANK_PK:.2f} A peak · Pi USB: {budget['V5_PI_USB'][1]:.2f} A peak of 1.2")

json.dump(dict(
    rails=[dict(id=k, **v) for k, v in RAILS.items()],
    loads=[dict(name=n, rail=r, vin=[a, b], i_avg=ia, i_peak=ip, connector=c, source=s) for n, r, a, b, ia, ip, c, s in LOADS],
    wires=[dict(name=n, awg=a, length_m=l, connector=c, i_avg=round(CURRENT[k][0], 2), i_peak=round(CURRENT[k][1], 2)) for n, a, l, c, k in WIRES],
    signals=[dict(driver=d, pins=dp, v_out=vo, receiver=r, rpins=rp, v_in_max=vm, v_ih=vih, bus=b) for d, dp, vo, r, rp, vm, vih, b in SIGNALS],
    checks=[dict(level=l, id=c, text=t) for l, c, t in sorted(R, key=lambda r: (order[r[0]], r[1]))],
    summary=dict(pack_avg=round(PACK_AVG, 2), pack_peak=round(PACK_PK, 2), bank_avg=round(BANK_AVG, 2), bank_peak=round(BANK_PK, 2),
                 pi_usb_peak=round(budget["V5_PI_USB"][1], 2), minutes=round(hours * 60), v_pi=round(v_pi, 2), v_cam=round(v_cam, 2),
                 n_loads=len(LOADS), n_wires=len(WIRES), n_signals=len(SIGNALS), counts=counts),
), open("wiring.json", "w"), indent=1, ensure_ascii=False)
sys.exit(1 if counts[FAIL] else 0)
