#!/usr/bin/env python3
"""
wiring_diagrams.py — Hound harness diagrams (v3.1: one buck, no splices, no resistor boards), generated from one net
list, rendered with WireViz + Graphviz, and cross-checked against wiring.py so a diagram can never disagree with the
electrical model.

    venv/bin/python wiring_diagrams.py            # writes bom-site/wiring/*.yml, *.svg, *.png and wiring_diagrams.json

Every connector pin below comes from a datasheet or the board silkscreen (source in the connector's notes). Every wire
comes from wiring.py's WIRES / LOADS / SIGNALS tables. The cross-check at the bottom fails the build if a load, a
signal link, or a pin in wiring.py has no wire here — or if this file invents one that wiring.py does not know.
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from contextlib import redirect_stdout

import yaml

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "bom-site", "wiring")
os.makedirs(OUT, exist_ok=True)

# ── the truth: wiring.py's tables ────────────────────────────────────────────────────────────────────────────
os.chdir(ROOT)
src = open(os.path.join(ROOT, "wiring.py")).read().replace("sys.exit(1 if counts[FAIL] else 0)", "")
W = {"__file__": os.path.join(ROOT, "wiring.py"), "__name__": "wiring_model"}
with redirect_stdout(io.StringIO()):
    exec(compile(src, "wiring.py", "exec"), W)
if W["counts"][W["FAIL"]]:
    sys.exit("wiring.py reports a FAIL — fix the model before drawing it")
LOADS, WIRES, SIGNALS, PI_BCM, R4_PINS = W["LOADS"], W["WIRES"], W["SIGNALS"], W["PI_BCM"], W["R4_PINS"]


def C(type_, pins, notes=None, **kw):
    d = dict(type=type_, pinlabels=list(pins))
    if notes: d["notes"] = notes
    d.update(kw); return d


def B(gauge, length, colors, notes=None):
    d = dict(gauge=f"{gauge} AWG", length=length, colors=list(colors), category="bundle")
    if notes: d["notes"] = notes
    return d


def link(*hops):
    return [{name: [pin]} for name, pin in hops]


# ── shared connectors (pin order = silkscreen / datasheet order) ─────────────────────────────────────────────
XL4015 = C("HiLetgo XL4015 5 A buck — trim OUT to 5.0 V", ["IN+", "IN−", "OUT+", "OUT−"],
           "HiLetgo board: four big solder pads, IN+/IN− at the coil end, OUT+/OUT− at the other — tin them and solder the 22 AWG wires (no screw terminals). Set 5.00 V on the meter with nothing on OUT (pot turns counter-clockwise to lower). 4 A continuous, 5 A peak. OUT goes to the PCA9685 terminal, which distributes it to both servos and the fan. 5.0 V (not 6) so the fan can share this rail; the MG996R runs 4.8–7.2 V.")
PCA_PWR = C("PCA9685 servo-power screw terminal", ["V+", "GND"], "The big 2-pin terminal = the 5.0 V rail in from the XL4015. Every channel header's middle (V+) and bottom (GND) pin is bussed to it.")
PCA_LOGIC = C("PCA9685 logic header (6 pins, either end)", ["GND", "OE", "SCL", "SDA", "VCC", "V+"],
              "Adafruit-pattern silkscreen: GND OE SCL SDA VCC V+. OE left open. VCC = 5 V from the shield, so the board's I2C pull-ups sit at 5 V — correct for the R4, and why this board must NOT also touch the Pi's SDA/SCL. Address 0x40.")
PCA_CH3 = C("PCA9685 channel 3 — TILT", ["PWM", "V+", "GND"], "Rows: PWM (top), V+ (middle), GND (bottom). Tilt servo plugs straight on, brown/black to the GND row.")
PCA_CH2 = C("PCA9685 channel 2 — PAN", ["PWM", "V+", "GND"], "Pan servo (continuous-rotation) plugs straight on, brown/black to the GND row (channel 2, as the Ceres sketch had it).")
PCA_CH15 = C("PCA9685 channel 15 — used as a 5 V tap", ["PWM", "V+", "GND"], "Only V+ and GND are used: the fan's red to V+, black to GND. PWM pin stays empty.")
TILT = C("MG996R TILT servo (positional, 180°)", ["signal (orange)", "V+ (red)", "GND (brown)"], "Plugs onto channel 3. Limits 78–150° in the firmware ('t 90'), mapping 600 + 10 µs/°. Must be the 180° MG996R: a 360° one cannot hold the camera. Not driven at boot: it starts where it was set by hand.")
PAN = C("MG996R PAN servo (continuous-rotation)", ["signal (orange)", "V+ (red)", "GND (brown)"], "Plugs onto channel 2. It cannot hold an angle: the firmware only nudges it, eased timed turns, then pulse cut; 'p' stops. This one turns right below 1500 µs (PAN_SIGN −1). Stop-pulse trim 'T' is set once with the remote's hold-still test.")
FAN = C("40 mm 5 V fan on the driver heatsinks", ["5V (red)", "GND (black)"], "5 V 0.15 A (listing). Plugs onto channel 15's V+/GND pins.")
SHIELD_I2C = C("CNC Shield v3 — SDA/SCL/5V/GND on its comms header (= R4 A4/A5, 5 V logic)", ["SDA", "SCL", "5V", "GND"],
               "A4/A5 are the R4's primary I2C ('Wire'), 5 V logic. Four Dupont wires to the PCA9685 logic header. NOT the R4's Qwiic socket (that is Wire1, 3.3 V).")


def CP(n, role):
    return C(f"CP2102 USB-UART no.{n} → {role}", ["3V3", "5V", "GND", "TXD", "RXD", "DTR"],
             "3.3 V-logic adapter (meter TXD at idle: 3.3 V). Four wires to the radar: +5V → VCC (the 3V3 pin stays empty), GND → GND, TXD → radar RX, RXD → radar TX. The 5V pin is USB power passed through (≤ 500 mA). Label the adapter body: " + role + ".")


LD2410 = lambda side, toe: C(f"HLK-LD2410C {side} (toed {toe})", ["1 TX", "2 RX", "3 OUT", "4 GND", "5 VCC"],
                             "Pins per Hi-Link manual table 1: 1 UART_Tx, 2 UART_Rx, 3 OUT, 4 GND, 5 VCC (5–12 V, 5 V advised). IO 3.3 V, 256000 baud. OUT unused.")
LD2450 = C("HLK-LD2450 (centre, x/y tracker)", ["5V", "GND", "TX", "RX"], "Silkscreen 5V GND TX RX; 5 V supply, 3.3 V UART, 256000 baud. No adapter: straight onto the Pi header — the Pi's own UART (/dev/ttyAMA0 once pi/enable_gpio_uart.sh has run). Powered OFF by default: same 24 GHz band as the LD2410Cs, interference untested.")

PI_HDR = C("Raspberry Pi 4 — 40-pin header (used pins only)",
           ["1 3V3", "3 SDA1 BCM2", "4 5V", "5 SCL1 BCM3", "8 BCM14 UART-TXD", "9 GND", "10 BCM15 UART-RXD", "12 BCM18 I2S-BCLK", "13 BCM27 XSHUT-rear",
            "14 GND", "15 BCM22 XSHUT-front", "17 3V3", "20 GND", "30 GND", "34 GND", "35 BCM19 I2S-LRCLK", "38 BCM20 I2S-DIN", "39 GND"],
           "Physical pin numbers (odd = inner row from the SD-card end). One I2C bus (pins 3/5) for thermal + both ToFs; three boards share it, so chain through their second headers or a mini breadboard — one female per Pi pin. Pins 4/8/10/34 = the LD2450: 5 V on pin 4 only, never on 8 or 10.")


def shield_motor_header(axis, wheel, step, dir_):
    return C(f"CNC Shield v3 — {axis} driver motor header ({wheel})", ["2B", "2A", "1A", "1B"],
             f"4-pin male header beside the {axis} socket. Driver STEP = D{step}, DIR = D{dir_}, EN = D8 shared. Firmware map: {wheel} = {axis}.")


def motor(wheel, axis):
    return C(f"JK42HS40 NEMA 17 — {wheel} (axis {axis})", ["coil A +", "coil A −", "coil B +", "coil B −"],
             "Find the pairs with the meter: the two leads that read ~1.5–2 Ω are ONE coil. Lead colours vary between batches — the meter, not the colour, decides.")


# ── the diagrams ─────────────────────────────────────────────────────────────────────────────────────────────
D = {}

D["1-power"] = dict(
    metadata=dict(title="Hound 1 — power: pack → shield → one buck (servo + fan, sheet 3); Pi on its bank"),
    connectors=dict(
        PACK=C("HOOVO 3S 2200 mAh 80C LiPo — T-plug (Deans)", ["V+", "GND"], "11.1 V nominal, 12.6 V full, 10.5 V floor. No divider, no alarm: 30-minute timer, then meter it. A pack that reads 6–7 V is dead: never charge it."),
        PLUG=C("Deans pull-plug on the deck (OliRC 14 AWG extension) = the E-STOP", ["pack +", "pack −", "rover +", "rover −"], "The mating pair sits at the deck's rear corner where a hand can reach it. Pulling it apart kills everything on the pack side; the Pi keeps running on the bank."),
        SHIELD_PWR=C("CNC Shield v3 — power screw terminal (the only pack splice)", ["VMOT", "GND"], "Two wires per screw: the 14 AWG pack lead and the 22 AWG XL4015 input wire, twisted together before insertion, tug-tested. 1000 µF 25 V electrolytic across VMOT/GND at the terminal, stripe (−) to GND."),
        XL4015=XL4015,
        BANK=C("USB power bank 5 V / 3 A (logic island)", ["USB-A out"], "Genuine 3 A bank. Cable ≤ 0.2 m with 22 AWG or heavier power conductors (a short '3 A fast-charge' cable). Powers ONLY the Pi; the Pi powers the R4, the hub, the adapters, the radars and the webcam."),
        PI_PWR=C("Raspberry Pi 4 — USB-C power in", ["USB-C"], "Under-voltage warning at 4.63 V. Early Pi 4 (rev 1.1) needs an A-to-C or non-e-marked cable."),
    ),
    cables=dict(
        W_PACK=B(14, 0.15, ["RD", "BK"], "HOOVO T-plug → the deck plug (pack half of the OliRC extension)"),
        W_LEAD=B(14, 0.30, ["RD", "BK"], "deck plug → shield terminal (rover half of the OliRC extension)"),
        W_XL_IN=B(22, 0.15, ["RD", "BK"], "second wire in each shield power screw"),
        W_BANK=B(22, 0.20, ["RD"], "USB-A → USB-C, ≤ 0.2 m"),
    ),
    connections=[
        link(("PACK", "V+"), ("W_PACK", 1), ("PLUG", "pack +")),
        link(("PACK", "GND"), ("W_PACK", 2), ("PLUG", "pack −")),
        link(("PLUG", "rover +"), ("W_LEAD", 1), ("SHIELD_PWR", "VMOT")),
        link(("PLUG", "rover −"), ("W_LEAD", 2), ("SHIELD_PWR", "GND")),
        link(("SHIELD_PWR", "VMOT"), ("W_XL_IN", 1), ("XL4015", "IN+")),
        link(("SHIELD_PWR", "GND"), ("W_XL_IN", 2), ("XL4015", "IN−")),
        link(("BANK", "USB-A out"), ("W_BANK", 1), ("PI_PWR", "USB-C")),
    ],
)

D["2-drive"] = dict(
    metadata=dict(title="Hound 2 — UNO R4 WiFi + CNC Shield v3 + DRV8825 ×4 + NEMA 17 ×4 (frozen v1.0 drive)"),
    connectors=dict(
        R4=C("Arduino UNO R4 WiFi — under the shield (stacked, no wires)", ["D2 X STEP", "D5 X DIR", "D3 Y STEP", "D6 Y DIR", "D4 Z STEP", "D7 Z DIR", "D12 A STEP", "D13 A DIR", "D8 EN (all four)", "A4 SDA → PCA9685", "A5 SCL → PCA9685", "USB-C → Pi hub"],
             "Stack the shield on the R4; the pins listed are what the shield takes. Firmware r4_drive v1.0-best-drive: 30 kHz step ISR, 1/32, 415 mm/s. Logic 5 V. USB from the Pi hub; ENABLE_WIFI 0."),
        SHIELD_CTRL=C("CNC Shield v3 — jumpers (no wires)", ["A-axis jumper D12", "A-axis jumper D13", "MS1 cap ×4", "MS2 (open) ×4", "MS3 cap ×4"],
                      "AS BUILT: caps on MS1 + MS3 under every driver = 1/32 (M0+M2 high, M1 low — Pololu table), MS2 open. Two jumpers on the A header = D12/D13 drive the A axis. No EN pull-up: the pack is unplugged whenever the R4 is being flashed or reset."),
        DRV=C("DRV8825 ×4 in sockets X Y Z A (plug-in, no wires)", ["EN pin over the socket's EN label", "Vref 0.75 V = 1.5 A (I = 2·Vref on Pololu-pattern carriers)", "heatsink on"],
              "Orientation: the driver's EN pin over the socket's EN label; trimpot toward the power terminal on Pololu layouts, clones vary — go by the label. Backwards = dead driver. Set Vref with motors UNPLUGGED, meter black on the shield GND pin, red on the trimpot screw."),
        X_MOT=shield_motor_header("X", "BL", 2, 5), Y_MOT=shield_motor_header("Y", "FL", 3, 6), Z_MOT=shield_motor_header("Z", "BR", 4, 7), A_MOT=shield_motor_header("A", "FR", 12, 13),
        M_BL=motor("BL back-left", "X"), M_FL=motor("FL front-left", "Y"), M_BR=motor("BR back-right", "Z"), M_FR=motor("FR front-right", "A"),
    ),
    cables={f"W_{w}": B(26, 0.40, ["RD", "BU", "GN", "BK"], "4-pin Dupont, 1.5 A per phase (2 A contacts): any pin that warms in the wheels-up test gets re-crimped") for w in ("BL", "FL", "BR", "FR")},
    connections=[
        row for hdr, m, w in (("X_MOT", "M_BL", "W_BL"), ("Y_MOT", "M_FL", "W_FL"), ("Z_MOT", "M_BR", "W_BR"), ("A_MOT", "M_FR", "W_FR"))
        for row in (link((hdr, "2B"), (w, 1), (m, "coil B +")), link((hdr, "2A"), (w, 2), (m, "coil B −")),
                    link((hdr, "1A"), (w, 3), (m, "coil A +")), link((hdr, "1B"), (w, 4), (m, "coil A −")))
    ],
)

D["3-turret"] = dict(
    metadata=dict(title="Hound 3 — turret: PCA9685 on the CNC Shield's I2C pins, tilt ch 3, pan ch 2, fan on ch 15, powered by the XL4015"),
    connectors=dict(SHIELD_I2C=SHIELD_I2C, PCA_LOGIC=PCA_LOGIC, PCA_PWR=PCA_PWR, XL4015=XL4015, PCA_CH3=PCA_CH3, TILT=TILT, PCA_CH2=PCA_CH2, PAN=PAN, PCA_CH15=PCA_CH15, FAN=FAN),
    cables=dict(
        W_I2C=B(24, 0.15, ["BK", "YE", "BU", "RD"], "GND, SCL (yellow), SDA (blue), 5V (red) — Dupont"),
        W_SERVO=B(22, 0.15, ["RD", "BK"], "5.0 V rail: XL4015 OUT pads → the PCA9685 terminal"),
        W_PAN=B(22, 0.30, ["OG", "RD", "BN"], "the servo's own lead"),
        W_TILT=B(22, 0.30, ["OG", "RD", "BN"], "the servo's own lead"),
        W_FAN=B(24, 0.20, ["RD", "BK"], "Dupont onto the channel-15 header"),
    ),
    connections=[
        link(("SHIELD_I2C", "GND"), ("W_I2C", 1), ("PCA_LOGIC", "GND")),
        link(("SHIELD_I2C", "SCL"), ("W_I2C", 2), ("PCA_LOGIC", "SCL")),
        link(("SHIELD_I2C", "SDA"), ("W_I2C", 3), ("PCA_LOGIC", "SDA")),
        link(("SHIELD_I2C", "5V"), ("W_I2C", 4), ("PCA_LOGIC", "VCC")),
        link(("XL4015", "OUT+"), ("W_SERVO", 1), ("PCA_PWR", "V+")),
        link(("XL4015", "OUT−"), ("W_SERVO", 2), ("PCA_PWR", "GND")),
        link(("PCA_CH3", "PWM"), ("W_TILT", 1), ("TILT", "signal (orange)")),
        link(("PCA_CH3", "V+"), ("W_TILT", 2), ("TILT", "V+ (red)")),
        link(("PCA_CH3", "GND"), ("W_TILT", 3), ("TILT", "GND (brown)")),
        link(("PCA_CH2", "PWM"), ("W_PAN", 1), ("PAN", "signal (orange)")),
        link(("PCA_CH2", "V+"), ("W_PAN", 2), ("PAN", "V+ (red)")),
        link(("PCA_CH2", "GND"), ("W_PAN", 3), ("PAN", "GND (brown)")),
        link(("PCA_CH15", "V+"), ("W_FAN", 1), ("FAN", "5V (red)")),
        link(("PCA_CH15", "GND"), ("W_FAN", 2), ("FAN", "GND (black)")),
    ],
)

D["4-pi-sensors"] = dict(
    metadata=dict(title="Hound 4 — Pi 40-pin header: thermal + ToF ×2 (I2C-1), microphone (I2S), LD2450 radar (UART)"),
    connectors=dict(
        PI=PI_HDR,
        MLX=C("MLX90640 thermal array breakout (0x33)", ["VIN 3V3", "GND", "SCL", "SDA"], "On I2C-1 with the two ToFs (no address clash: 0x33 / 0x29 / 0x30). 400 kHz gives 8 fps; station.py uses 4. Rides beside the webcam on the tilt bracket."),
        TOF_F=C("VL53L1X ToF FRONT (0x29 → re-addressed 0x30 by XSHUT)", ["VIN 3V3", "GND", "SDA", "SCL", "XSHUT"], "Both ToFs share I2C-1 and boot at 0x29. At every start sensing/tof.py holds BOTH XSHUT low, wakes FRONT alone and moves it to 0x30, then wakes REAR (0x29). Waking both before the change would move both."),
        TOF_R=C("VL53L1X ToF REAR (0x29)", ["VIN 3V3", "GND", "SDA", "SCL", "XSHUT"], "XSHUT on BCM 27 so the Pi can reset it independently."),
        MIC=C("INMP441 I2S microphone", ["VDD 3V3", "GND", "SCK", "WS", "SD", "L/R"], "L/R tied to GND = left channel. On the post front face, 120 mm up (assembly.py)."),
        LD2450=LD2450,
    ),
    cables=dict(
        W_MLX=B(26, 0.35, ["RD", "BK", "YE", "BU"], "to the turret: leave a service loop for tilt"),
        W_TOF_F=B(26, 0.25, ["RD", "BK", "BU", "YE", "WH"]),
        W_TOF_R=B(26, 0.35, ["RD", "BK", "BU", "YE", "WH"]),
        W_MIC=B(26, 0.25, ["RD", "BK", "GN", "OG", "VT", "BK"]),
        W_LD2450=B(26, 0.25, ["RD", "BK", "GN", "WH"], "5V, GND, radar TX → Pi RXD, radar RX ← Pi TXD — one 4-wire Dupont lead"),
    ),
    connections=[
        link(("PI", "1 3V3"), ("W_MLX", 1), ("MLX", "VIN 3V3")),
        link(("PI", "9 GND"), ("W_MLX", 2), ("MLX", "GND")),
        link(("PI", "5 SCL1 BCM3"), ("W_MLX", 3), ("MLX", "SCL")),
        link(("PI", "3 SDA1 BCM2"), ("W_MLX", 4), ("MLX", "SDA")),
        link(("PI", "17 3V3"), ("W_TOF_F", 1), ("TOF_F", "VIN 3V3")),
        link(("PI", "14 GND"), ("W_TOF_F", 2), ("TOF_F", "GND")),
        link(("PI", "3 SDA1 BCM2"), ("W_TOF_F", 3), ("TOF_F", "SDA")),
        link(("PI", "5 SCL1 BCM3"), ("W_TOF_F", 4), ("TOF_F", "SCL")),
        link(("PI", "15 BCM22 XSHUT-front"), ("W_TOF_F", 5), ("TOF_F", "XSHUT")),
        link(("PI", "17 3V3"), ("W_TOF_R", 1), ("TOF_R", "VIN 3V3")),
        link(("PI", "20 GND"), ("W_TOF_R", 2), ("TOF_R", "GND")),
        link(("PI", "3 SDA1 BCM2"), ("W_TOF_R", 3), ("TOF_R", "SDA")),
        link(("PI", "5 SCL1 BCM3"), ("W_TOF_R", 4), ("TOF_R", "SCL")),
        link(("PI", "13 BCM27 XSHUT-rear"), ("W_TOF_R", 5), ("TOF_R", "XSHUT")),
        link(("PI", "17 3V3"), ("W_MIC", 1), ("MIC", "VDD 3V3")),
        link(("PI", "39 GND"), ("W_MIC", 2), ("MIC", "GND")),
        link(("PI", "12 BCM18 I2S-BCLK"), ("W_MIC", 3), ("MIC", "SCK")),
        link(("PI", "35 BCM19 I2S-LRCLK"), ("W_MIC", 4), ("MIC", "WS")),
        link(("PI", "38 BCM20 I2S-DIN"), ("W_MIC", 5), ("MIC", "SD")),
        link(("PI", "30 GND"), ("W_MIC", 6), ("MIC", "L/R")),
        link(("PI", "4 5V"), ("W_LD2450", 1), ("LD2450", "5V")),
        link(("PI", "34 GND"), ("W_LD2450", 2), ("LD2450", "GND")),
        link(("LD2450", "TX"), ("W_LD2450", 3), ("PI", "10 BCM15 UART-RXD")),
        link(("LD2450", "RX"), ("W_LD2450", 4), ("PI", "8 BCM14 UART-TXD")),
    ],
)

D["5-radars-usb"] = dict(
    metadata=dict(title="Hound 5 — LD2410C radars: four wires each to their own CP2102, and the USB tree (the LD2450 is on sheet 4)"),
    connectors=dict(
        PI_USB=C("Raspberry Pi 4 — USB-A ports", ["USB 1: webcam", "USB 2: hub", "USB 3: free", "USB 4: free"], "1.2 A shared across all four ports; peak here 0.8 A (webcam 0.3, R4 0.2, hub + two adapters + two LD2410Cs 0.28). Webcam on its own port, everything else through the hub."),
        HUB=C("4-port USB hub (unpowered)", ["upstream", "port 1: UNO R4", "port 2: CP2102 no.1", "port 3: CP2102 no.2", "port 4: free"]),
        CAM=C("Webcam (C920-class) — captive 1.5 m cable", ["USB-A"], "On the turret beside the thermal array. If it drops out at 1080p, run 720p."),
        R4_USB=C("UNO R4 WiFi — USB-C", ["USB-C"], "USB CDC serial to the Pi: /dev/serial/by-id/*Arduino*"),
        CP1=CP(1, "LD2410C LEFT"), CP2=CP(2, "LD2410C RIGHT"),
        LDL=LD2410("LEFT", "+30° out, deck Y +50"), LDR=LD2410("RIGHT", "−30° out, deck Y −50"),
    ),
    cables=dict(
        W_CAM=B(28, 1.50, ["WH"], "captive"), W_HUB=B(28, 0.30, ["WH"]), W_R4=B(28, 0.30, ["WH"], "USB-A → USB-C"),
        W_CPA=B(28, 0.15, ["WH"]), W_CPB=B(28, 0.15, ["WH"]),
        W_LDL=B(26, 0.25, ["GN", "WH", "BK", "RD"], "TX, RX, GND, VCC — one 4-wire Dupont lead per radar"),
        W_LDR=B(26, 0.25, ["GN", "WH", "BK", "RD"]),
    ),
    connections=[
        link(("PI_USB", "USB 1: webcam"), ("W_CAM", 1), ("CAM", "USB-A")),
        link(("PI_USB", "USB 2: hub"), ("W_HUB", 1), ("HUB", "upstream")),
        link(("HUB", "port 1: UNO R4"), ("W_R4", 1), ("R4_USB", "USB-C")),
        link(("HUB", "port 2: CP2102 no.1"), ("W_CPA", 1), ("CP1", "5V")),
        link(("HUB", "port 3: CP2102 no.2"), ("W_CPB", 1), ("CP2", "5V")),
    ] + [
        row for cp, ld, w, vcc, gnd, tx, rx in (
            ("CP1", "LDL", "W_LDL", "5 VCC", "4 GND", "1 TX", "2 RX"),
            ("CP2", "LDR", "W_LDR", "5 VCC", "4 GND", "1 TX", "2 RX"))
        for row in (link((ld, tx), (w, 1), (cp, "RXD")), link((ld, rx), (w, 2), (cp, "TXD")),
                    link((cp, "GND"), (w, 3), (ld, gnd)), link((cp, "5V"), (w, 4), (ld, vcc)))
    ],
)

D["6-csi"] = dict(
    metadata=dict(title="Hound 6 — WiFi CSI nodes: ESP32-S3 no.3 on the rover on its own power bank, no.2 off the rover"),
    connectors=dict(
        ESP3=C("ESP32-S3 DevKitC no.3 — csi_rx_udp, ON the rover", ["USB-C"], "Powered by its own small bank strapped next to it: nothing else plugs into the devkit. Joins the Pi hotspot (channel 6) and streams the CSI of every probe to the Pi, UDP 5005. secrets.h holds the hotspot name and password (git-ignored)."),
        BANK2=C("Second USB power bank (any, ≥ 1 A) — ESP32 no.3 only", ["USB-A out"], "Velcro it to the deck beside the devkit. It never touches the rover's electronics."),
        ESP2=C("ESP32-S3 DevKitC no.2 — csi_tx, OFF the rover", ["USB-C from any 5 V charger"], "Dropped ~3 m along the wall. 100 Hz ESP-NOW probes on channel 6. Radio link only — no wire to the rover."),
    ),
    cables=dict(W_ESP=B(28, 0.30, ["WH"], "any short USB-A → USB-C cable")),
    connections=[
        link(("BANK2", "USB-A out"), ("W_ESP", 1), ("ESP3", "USB-C")),
    ],
)

# ── render ───────────────────────────────────────────────────────────────────────────────────────────────────
WV = os.path.join(os.path.dirname(sys.executable), "wireviz")
for name, doc in D.items():
    doc.setdefault("options", {})["bgcolor"] = "#ffffff"
    path = os.path.join(OUT, f"{name}.yml")
    with open(path, "w") as f:
        yaml.safe_dump(doc, f, allow_unicode=True, sort_keys=False, width=200)
    r = subprocess.run([WV, "-f", "sp", "-o", OUT, path], capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"wireviz failed on {name}:\n{r.stdout}\n{r.stderr}")
    print(f"  rendered {name}")

# ── cross-check against wiring.py ────────────────────────────────────────────────────────────────────────────
edges = set()
for name, doc in D.items():
    for row in doc["connections"]:
        ends = [(list(h)[0], list(h.values())[0][0]) for h in row]
        a, b = ends[0], ends[-1]
        edges.add((a[0], b[0])); edges.add((b[0], a[0]))
        edges.add(((a[0], a[1]), (b[0], b[1]))); edges.add(((b[0], b[1]), (a[0], a[1])))

problems = []
def need(cond, msg):
    if not cond: problems.append(msg)

RAIL_SRC = {"PACK": {"PACK", "PLUG", "SHIELD_PWR"}, "V_SERVO": {"XL4015", "PCA_PWR", "PCA_CH3", "PCA_CH2", "PCA_CH15"},
            "V5_BANK": {"BANK", "PI"}, "V5_BANK2": {"BANK2"}, "V5_PI_USB": {"PI_USB", "HUB", "CP1", "CP2", "SHIELD_I2C"}, "V3_PI": {"PI"}}
LOAD_CONN = {"4× DRV8825": "SHIELD_PWR", "XL4015": "XL4015", "MG996R tilt": "TILT", "MG996R pan": "PAN", "40 mm": "FAN", "PCA9685 logic": "PCA_LOGIC", "ESP32-S3 #3": "ESP3",
             "Raspberry Pi 4": "PI_PWR", "Webcam": "CAM", "UNO R4": "R4_USB", "2× CP2102": "HUB",
             "LD2410C radar LEFT": "LDL", "LD2410C radar RIGHT": "LDR", "LD2450": "LD2450",
             "MLX90640": "MLX", "VL53L1X ToF front": "TOF_F", "VL53L1X ToF rear": "TOF_R", "INMP441": "MIC", "SCD41": None}
for load in LOADS:
    name, rail = load[0], load[1]
    key = next((k for k in sorted(LOAD_CONN, key=len, reverse=True) if name.startswith(k)), None)
    need(key is not None, f"load not mapped to a connector: {name}")
    if key is None or LOAD_CONN[key] is None: continue
    conn = LOAD_CONN[key]
    need(any((src, conn) in edges for src in RAIL_SRC[rail]), f"{name}: no feed from rail {rail} ({sorted(RAIL_SRC[rail])}) in any diagram")

SIG_CONN = {"UNO R4 (5 V logic)": "X_MOT", "DRV8825 ×4": "M_BL", "LD2410C left TX": "LDL", "CP2102 #1": "CP1", "LD2410C left": "LDL",
            "LD2410C right TX": "LDR", "CP2102 #2": "CP2", "LD2410C right": "LDR", "LD2450 TX": "LD2450", "Pi BCM 15": "PI", "Pi BCM 14": "PI", "LD2450": "LD2450",
            "Pi I2C-1": "PI", "MLX90640 0x33": "MLX", "UNO R4 Wire": "SHIELD_I2C", "PCA9685 0x40": "PCA_LOGIC", "PCA9685 (VCC 5 V) channels": "PCA_CH3", "MG996R tilt / pan servos": "TILT", "Pi BCM 22 / 27": "PI", "VL53L1X front / rear": "TOF_F",
            "Pi I2S": "PI", "INMP441": "MIC", "Pi ↔ UNO R4": "HUB", "UNO R4": "R4_USB", "Pi ↔ 2× CP2102": "HUB", "LD2410C left/right at 256000 baud": "CP1"}
def sc(s):
    return next((v for k, v in sorted(SIG_CONN.items(), key=lambda kv: -len(kv[0])) if s.startswith(k)), None)
for drv, dp, vo, rcv, rp, vmax, vih, bus in SIGNALS:
    if bus == "WIFI": continue
    a, b = sc(drv), sc(rcv)
    need(a and b, f"signal not mapped: {drv} → {rcv}")
    if a and b: need((a, b) in edges, f"signal has no wire in the diagrams: {drv} [{a}] → {rcv} [{b}]")

used_bcm = set()
for lab in PI_HDR["pinlabels"]:
    for tok in lab.split():
        if tok.startswith("BCM"): used_bcm.add(int(tok[3:]))
need(used_bcm == set(PI_BCM.values()), f"Pi BCM pins differ: diagrams {sorted(used_bcm)} vs wiring.py {sorted(PI_BCM.values())}")

r4_lab = " ".join(D["2-drive"]["connectors"]["R4"]["pinlabels"])
for k, v in R4_PINS.items():
    tag = f"A{v - 14} " if v >= 14 else f"D{v} "
    need(tag in r4_lab, f"R4 pin {tag.strip()} ({k}) missing from the drive diagram")

gnd_of = {}
for name, doc in D.items():
    for row in doc["connections"]:
        for h in (row[0], row[-1]):
            c, p = list(h)[0], list(h.values())[0][0]
            if c in doc["connectors"] and isinstance(p, str) and ("GND" in p or p.endswith("−") or p == "L/R"):
                gnd_of.setdefault(c, []).append((name, p))
for c in ("LDL", "LDR", "LD2450"):
    need(len(gnd_of.get(c, [])) == 1, f"{c} needs exactly one GND wire (to its adapter or the Pi header), has {len(gnd_of.get(c, []))}")
for c in ("MLX", "TOF_F", "TOF_R", "MIC", "FAN", "TILT", "PAN", "PCA_LOGIC", "PCA_PWR", "XL4015", "SHIELD_PWR", "PLUG"):
    need(c in gnd_of, f"{c} has no GND wire")

I2C = W["I2C_BUSES"]
for bus, devs in I2C.items():
    addrs = [a for _, a, _ in devs]
    need(len(addrs) == len(set(addrs)), f"{bus}: duplicate I2C address")
need((("PI", "3 SDA1 BCM2"), ("MLX", "SDA")) in edges, "MLX90640 must hang on I2C-1 (BCM 2/3), as wiring.py says")
need((("SHIELD_I2C", "SDA"), ("PCA_LOGIC", "SDA")) in edges and (("PCA_CH3", "PWM"), ("TILT", "signal (orange)")) in edges and (("PCA_CH2", "PWM"), ("PAN", "signal (orange)")) in edges, "the PCA9685 must hang on the shield's SDA/SCL with tilt on ch 3 and pan on ch 2")
need((("SHIELD_PWR", "VMOT"), ("XL4015", "IN+")) in edges and (("PLUG", "rover +"), ("SHIELD_PWR", "VMOT")) in edges, "the shield terminal must be the single pack splice")

print("\nCROSS-CHECK vs wiring.py:", "OK — every load fed, every signal wired, pins match" if not problems else f"{len(problems)} problem(s)")
for p in problems: print("  ✗", p)

json.dump(dict(diagrams=list(D), connectors={k: v for d in D.values() for k, v in d["connectors"].items()},
               connections={n: [[(list(h)[0], list(h.values())[0][0]) for h in row] for row in d["connections"]] for n, d in D.items()},
               problems=problems), open(os.path.join(ROOT, "wiring_diagrams.json"), "w"), indent=1, ensure_ascii=False)
sys.exit(1 if problems else 0)
