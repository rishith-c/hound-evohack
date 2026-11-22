#!/usr/bin/env python3
"""Where every part goes, in millimetres, and what holds it there.

Frame: origin at the chassis centre on the floor plane. +X forward, +Y rover
left, +Z up (same convention as the Ceres CAD). Every position is a part
CENTRE unless the note says otherwise. Dimensions marked VERIFY are nominal
for that class of part and must be checked with a caliper on receipt before
any hole is drilled — the listing did not publish them.

Emits assembly.json (for the site), assembly.csv, and prints the table plus
interference, clearance, CG and fastener-count checks.

    python3 assembly.py
"""

import csv
import json
import math

# ── Fixed dimensions ────────────────────────────────────────────────────────
RAIL = 20.0                 # 2020 profile                                  MEASURED
RAIL_LEN = 350.0            # all four rails                                 MEASURED (listing)
RAIL_Z0 = 71.0              # rail underside = shaft height 40 + bracket offset 31
NEMA = 42.3                 # NEMA 17 flange                                 MEASURED (drawing)
NEMA_LEN = 39.5             # body length                                    MEASURED (drawing)
NEMA_PITCH = 31.0           # bolt pattern                                   MEASURED (drawing)
SHAFT_D, SHAFT_LEN = 5.0, 22.0   # shaft length VERIFY                        drawing: 5 mm with flat
BRK_T = 3.0                 # Anndason steel                                 MEASURED (listing)
BRK_OFFSET = 31.0           # axle centre to foot outer face: drawing bore centre ≈30 from bend line + ~1.5 half-thickness   ±1.5 VERIFY on receipt
BRK_FOOT_W, BRK_FOOT_D = 50.0, 51.0   # Anndason drawing: plate 50 wide, foot 51 long   MEASURED (listing drawing)
WHEEL_D, WHEEL_W = 80.0, 31.0         # width VERIFY
COUPLER_LEN = 15.0                    # VERIFY
AXLE_X = 125.0              # wheelbase 250
AXLE_Z = WHEEL_D / 2
DECK_T = 5.0                # PETG deck tiles
DECK_Z0 = RAIL_Z0 + RAIL    # 91: deck sits on the rail tops
DECK_TOP = DECK_Z0 + DECK_T # 96

UNO = (68.6, 53.3, 12.0)
SHIELD_STACK_H = 45.0       # Uno + shield + DRV8825 with heatsinks           VERIFY
PI = (85.0, 56.0, 20.0)
PCA9685 = (62.0, 25.0, 12.0)
BUCK = (54.0, 23.0, 18.0)   # XL4015 module                                  VERIFY
ESP32 = (63.0, 25.4, 12.0)
LIPO = (75.0, 33.8, 26.4)   # HOOVO 2200 mAh 3S 80C shorty, listing dims      VERIFY
CRADLE_T = 3.0
CAM = (29.0, 94.0, 24.0)    # owned C920-class webcam: depth, width, height  VERIFY
TURRET_BASE = (100.0, 60.0, 6.0)      # Ceres pan base plate (rover_parts.py make_turret_pan_base)
TURRET_H = 110.0            # base top to camera centre                       VERIFY on the actual Ceres turret
LD2410C = (35.0, 7.0, 3.0)  # VERIFY
LD2450 = (43.0, 15.0, 3.0)  # VERIFY
TOF = (25.0, 11.0, 4.0)     # VL53L1X module                                 VERIFY
FAN = (40.0, 40.0, 10.0)    # MEASURED (listing)
POST = (40.0, 40.0, 200.0)  # PETG radar post
RADAR_Z = DECK_TOP + POST[2] + 4.0    # 300: antenna faces horizontal, forward

# ── Masses, kg, for CG (same figures as drivetrain.py) ─────────────────────
M = dict(motor=0.240, rail=0.350 * 0.50, wheel=0.150, bracket=0.113, corner=0.012,
         uno_stack=0.117, pi=0.070, lipo=0.140, buck=0.030, radar=0.010, esp32=0.015,
         cam=0.162, tof=0.005, deck=0.340, cradle=0.060, post=0.100, turret=0.250,
         pca=0.010, fan=0.030, strapwire=0.150)

parts = []

def add(pid, inst, name, x, y, z, l, w, h, orient, mounts_to, fasteners, torque, mass, verify="", note=""):
    parts.append(dict(id=pid, instance=inst, part=name, x=round(x, 1), y=round(y, 1), z=round(z, 1),
                      l=l, w=w, h=h, orientation=orient, mounts_to=mounts_to, fasteners=fasteners,
                      torque=torque, mass_kg=mass, verify=verify, note=note))

# ── Frame ───────────────────────────────────────────────────────────────────
RAIL_ZC = RAIL_Z0 + RAIL / 2
SIDE_Y = 175.0 + RAIL / 2            # 185: inner face at 175, outer at 195
CROSS_X = 155.0 + RAIL / 2           # 165: inner face at 155, outer at 175
for inst, y in (("left", SIDE_Y), ("right", -SIDE_Y)):
    add("RAIL", f"side {inst}", "2020 V-slot rail 350 mm, along X", 0, y, RAIL_ZC, RAIL_LEN, RAIL, RAIL,
        "long axis X", "corner brackets at both ends", "—", "—", M["rail"],
        note="Outer face at Y = ±195. Ends at X = ±175.")
for inst, x in (("front", CROSS_X), ("rear", -CROSS_X)):
    add("RAIL", f"cross {inst}", "2020 V-slot rail 350 mm, along Y", x, 0, RAIL_ZC, RAIL, RAIL_LEN, RAIL,
        "long axis Y", "butts against inner faces of the side rails", "—", "—", M["rail"],
        note="Spans Y −175..+175 exactly between the side rails. Outer face at X = ±175.")
# ONE bracket per corner. A 20 mm-tall 2020 inner corner has room for exactly one
# 17×20 bracket on the inner faces; the earlier "one top, one bottom" put two in
# the same 20 mm and the top one would have sat under the deck tile. The deck
# tiles, bolted to all four rails' top slots, are the second shear plane.
for cx in (CROSS_X, -CROSS_X):
    for sy in (SIDE_Y, -SIDE_Y):
        add("CNR", f"{'front' if cx > 0 else 'rear'}-{'left' if sy > 0 else 'right'}",
            "2020 corner bracket 17×20, black", cx - math.copysign(RAIL / 2 + 8.5, cx),
            sy - math.copysign(RAIL / 2 + 8.5, sy), RAIL_ZC, 17, 17, 20,
            "inside corner, on the two inner-face slots",
            "side rail + cross rail", "2× M5×8 hex + 2× M5 T-nut", "3.0 N·m (do not exceed on 2020 T-nuts)",
            M["corner"], note="One per corner, 4 total. Slide its two T-nuts in before the corner closes.")

# ── Drivetrain ──────────────────────────────────────────────────────────────
HAND = {"FL": "left-hand", "FR": "right-hand", "RL": "right-hand", "RR": "left-hand"}
for inst, sx, sy in (("FL", 1, 1), ("FR", 1, -1), ("RL", -1, 1), ("RR", -1, -1)):
    x = sx * AXLE_X
    outer = sy * 195.0                          # side-rail outer face
    leg_y = outer - sy * BRK_T / 2              # 3 mm leg just inboard of the outer face, under the rail
    motor_face_y = outer - sy * BRK_T           # motor flange against the leg's inboard side
    motor_c_y = motor_face_y - sy * NEMA_LEN / 2
    add("BRK", inst, "Steel NEMA 17 L-bracket, inverted under rail", x, outer - sy * BRK_FOOT_D / 2,
        RAIL_Z0 - BRK_T / 2, BRK_FOOT_W, BRK_FOOT_D, BRK_T,
        "foot flat against rail underside, leg hanging down flush with rail outer face",
        f"side rail {'left' if sy > 0 else 'right'} underside", "2× M4×10 hex + 2× M4 T-nut (bottom slot) — the foot slots are 4.3 mm wide: M4 only, M5 will not pass",
        "2.0 N·m", M["bracket"], verify="drawing: slots 4.3×34 at 25.73 pitch, starting 8 mm from the bend — the rail's bottom slot centre is 10 mm from the outer face, so each screw lands at the INNER END of its foot slot; if it does not reach, slide the bracket 1–2 mm inboard. Bore Ø22 nominal vs Ø22 boss: check it slips on; sand if tight",
        note=f"Leg centre Y = {leg_y:+.1f}; axle hole centre at Z = {AXLE_Z:.0f}.")
    add("MOT", f"{inst} (motor {['FL','FR','RL','RR'].index(inst)+1})", "JK42HS40-1704-13A NEMA 17",
        x, motor_c_y, AXLE_Z, NEMA, NEMA_LEN, NEMA, f"shaft along Y pointing {'+Y' if sy > 0 else '−Y'} (outboard)",
        f"bracket {inst} leg, inboard side", "4× M3×6 socket head through leg into flange (NEMA 17 tapped holes are ~4.5 mm deep: 3 mm plate + 6 mm screw = 3 mm engagement; an M3×8 bottoms out before it clamps — do not use the bracket's screws if they are 8 mm without a washer)", "0.8 N·m (aluminium threads)",
        M["motor"], note=f"Flange face at Y = {motor_face_y:+.1f}; body bottom at Z = {AXLE_Z - NEMA/2:.1f} (ground clearance). Leads exit inboard.")
    # Wheel inner face 5 mm outboard of the bracket leg: as close to the motor bearing as
    # the coupler allows. Every extra millimetre of overhang multiplies the bearing load.
    wheel_c_y = outer + sy * (5.0 + WHEEL_W / 2)
    add("WHL", f"{inst} ({HAND[inst]})", f"80 mm mecanum wheel, {HAND[inst]}", x, wheel_c_y, AXLE_Z,
        WHEEL_D, WHEEL_W, WHEEL_D, "axis Y; handedness by TEST, not by diagram: drive all four forward on the bench — straight means right; if it crabs or spins, swap the two wheels on one axle",
        f"5 mm coupler on motor {inst} shaft", "coupler grub screw on the shaft flat + blue threadlocker; wheel to coupler per kit hardware",
        "1.5 N·m grub", M["wheel"], verify="wheel width and coupler length",
        note=f"Inner face Y = {wheel_c_y - sy*WHEEL_W/2:+.1f}. Track = {2*abs(wheel_c_y):.0f} mm.")

# ── Deck ────────────────────────────────────────────────────────────────────
# Four quadrant tiles, not two: a 390 mm tile fits no common print bed (220–256 mm).
# Each tile is 170 × 195 with a 15 mm tongue on its centreline edges that laps the
# neighbour's rebate, joined by M3×8 + nut, so the seams carry no rail.
# 175 long, not 170: the cross-rail top slot is at X ±165 and a 9 mm M5 counterbore
# centred there needs 4.5 mm of tile beyond it. 170 left 0.5 mm and broke out.
for inst, x, y in (("front-left tile", 87.5, 97.5), ("front-right tile", 87.5, -97.5),
                   ("rear-left tile", -87.5, 97.5), ("rear-right tile", -87.5, -97.5)):
    add("PETG", inst, "Printed deck tile 175×195×5, half-thickness lap (15 mm tongue / rebate) on the centreline edges", x, y, DECK_Z0 + DECK_T / 2, 175, 195, DECK_T,
        "flat on rail tops", "one side rail + one cross rail", "3× M5×8 + M5 T-nut into the side-rail top slot, 2× into the cross-rail top slot (corner kit) at 1.5 N·m — 3 mm of PLA under the head crushes at the 3.0 the corners take; 3× M3×8 + nut per lap seam",
        "1.5 N·m on the M5 (PLA under the head); 1.0 N·m on the M3 seam nuts", M["deck"] / 4, note="Fits a 220 mm bed. Laps are half thickness so the top stays flush; tongues face +X and +Y. Print flat, 4 perimeters, 20% infill (~80 g each — the mass budget depends on it). Wire pass-through slots 20×8 mm beside each motor corner and at the rear centre for the pack lead — the tiles cover the whole frame and every under-deck wire has to come up somewhere.")

# ── Battery, slung under the deck ───────────────────────────────────────────
cradle_z = DECK_Z0 - (LIPO[2] + 2 * CRADLE_T) / 2
add("PETG", "battery cradle", f"PETG cradle {LIPO[0]+8:.0f}×{LIPO[1]+6:.0f}×{LIPO[2]+6:.0f}", 0, 0, cradle_z,
    LIPO[0] + 8, LIPO[1] + 6, LIPO[2] + 2 * CRADLE_T, "hangs from deck underside, open at both ends for the strap",
    "deck underside", "4× M3×12 through deck + 4× M3 nut (M3 kit), at X ±46, Y ±14 — 179 g hangs on them", "1.0 N·m", M["cradle"],
    note=f"Cradle bottom at Z = {cradle_z - (LIPO[2]+2*CRADLE_T)/2:.0f}: 61 mm ground clearance, above the 18.9 mm motor bottoms.")
add("LIPO", "—", "HOOVO 3S 2200 mAh 80C shorty, T-plug (Deans)", 0, 0, cradle_z, *LIPO, "long axis X, T-plug lead exits −X (rear)",
    "battery cradle", "printed retaining bar + 2 cable ties", "hand-tight", M["lipo"],
    note="Lowest heavy part → h_CG. Balance lead tucked beside the pack; the cell alarm is optional.")
add("PETG", "cradle retaining bar", "printed bar 140×12×6 across the cradle mouth", 0, 0, cradle_z - (LIPO[2] + 2 * CRADLE_T) / 2 + 3, 140, 12, 6,
    "spans the open bottom of the cradle", "cradle side walls, two printed hooks", "2× cable ties through printed slots", "hand-tight", 0.01,
    note="Replaces a bought strap. Print two.")

# ── Electronics on deck top (Z = 96) ────────────────────────────────────────
def on_deck(pid, inst, name, dims, x, y, mounts, fast, torque, mass, verify="", note=""):
    add(pid, inst, name, x, y, DECK_TOP + dims[2] / 2 + 10.0, *dims, "flat on 10 mm standoffs", mounts, fast, torque, mass, verify, note)

on_deck("UNO", "—", "UNO R4 WiFi + DRV8825 CNC Shield stack", (UNO[0], UNO[1], SHIELD_STACK_H), -115.7, 86.7,
        "deck top, rear-left", "printed 10 mm bosses on the deck tile + 4× M3×20 + nut through the R4's 3.2 mm holes (bosses 10 + tile 5 + nut) — a top-heavy driver stack should not hang on cable ties", "hand-tight",
        M["uno_stack"], verify="stack height with heatsinks",
        note="Board spans X −150..−81.4, Y +60..+113.3. Motor leads reach all four sockets from inboard. USB-C faces −X. Jumpers: D12 + D13 on the A header, caps on MS1 + MS3 under each driver (1/32), EN/GND open. Drivers in with EN on EN. Servos run from the PCA9685 on the shield's SDA/SCL comms header (wiring sheet 3).")
on_deck("FAN", "—", "40×40×10 5 V fan over the drivers", FAN, -115.7, 86.7, "printed PETG bridge over the shield",
        "printed bridge on 2× M3×8 into deck bosses; fan held to the bridge by 2 cable ties", "hand-tight", M["fan"],
        note=f"Blows down onto the four DRV8825 heatsinks. Fan face at Z ≈ {DECK_TOP + 10 + SHIELD_STACK_H + 8:.0f}.")
on_deck("PI", "—", "Raspberry Pi", PI, -107.5, -88.0, "deck top, rear-right",
        "printed 8 mm bosses on the deck tile (58×49 pattern) + 4× M2×20 + nut (bosses 8 + tile 5 + PCB 1.6 + nut 1.6 = 16.2; the M2×16 first specified had 1 mm left for board and nut)", "hand-tight", M["pi"],
        note="Spans X −150..−65, Y −116..−60. USB ports face −X (rear). Powered from the USB bank on USB-C; the fallback is a buck at 5.10 V on PHYSICAL header pins 2/4 (+) and 6 (−), never with the bank connected too.")
on_deck("BANK", "→ Pi", "USB power bank, compact (owned)", (100.0, 60.0, 15.0), 0.0, 0.0, "deck top, centre, over the LiPo cradle",
        "printed lip on the deck tile + 2 cable ties through printed slots", "hand-tight", 0.130, verify="WEIGH IT: ≤ 130 g, footprint",
        note="USB-C to the Pi. Must deliver 5 V at 3 A. Centred to keep the CG on the axis.")
on_deck("XL4015", "→ servo + fan 5.0 V", "HiLetgo XL4015 5 A buck (owned)", BUCK, -44.5, 110.5, "deck top, ahead of the R4",
        "printed bosses + 2 cable ties", "hand-tight", M["buck"], note="Trim to 5.0 V unloaded. IN from the shield's VMOT/GND screws (second wire each); OUT pads → the PCA9685's V+/GND terminal, which feeds both servos and the fan.")
on_deck("T-plug", "e-stop", "T-plug mating pair on the deck top, rear edge", (30.0, 16.0, 12.0), -140.0, -132.0, "deck top, rear edge beside the Pi",
        "printed saddle + 1 cable tie on the fixed half", "hand-tight", 0.010, note="The pack lead comes up through the rear slot to here. One-handed disconnect from above = the emergency stop.")
on_deck("ESP32", "#3 CSI receiver", "ESP32-S3 DevKitC", ESP32, 60.0, 120.0, "deck top, front-left, antenna toward +X, nothing metal within 20 mm",
        "printed bosses + 2 cable ties through printed slots", "hand-tight", M["esp32"], verify="devkit hole positions",
        note="csi_rx_udp firmware: USB-C from its own small power bank beside it, streams CSI to the Pi hotspot on channel 6. ESP32 #2 (csi_tx) is dropped on a 10 cm stand as far along the wall as the room allows.")
on_deck("PCA", "→ pan/tilt", "PCA9685 servo driver (Ceres)", PCA9685, 30.0, -75.0, "deck top, front-right, beside the turret base",
        "printed bosses + 2× M2 + nut", "hand-tight", M["pca"], note="V+ terminal from the XL4015 at 5.0 V; I2C from the CNC shield's comms header (5 V). Tilt ch 3, pan ch 2 (continuous, timed nudges), fan on ch 15's V+/GND pins.")
on_deck("BANK2", "→ ESP32 #3", "small USB power bank (ESP32 only)", (90.0, 26.0, 26.0), 60.0, 165.0, "deck top, front-left, outboard of ESP32 #3",
        "velcro strap", "hand-tight", 0.090, verify="any ≥ 1 A bank; weigh it",
        note="Its only load is the CSI node; nothing else plugs into it.")
on_deck("HUB", "→ Pi USB", "4-port USB hub", (60.0, 30.0, 12.0), -95.0, -165.0, "deck top, rear-right corner",
        "velcro", "hand-tight", 0.030, note="R4 + the two CP2102 adapters; port 4 free. 0.3 m cable to the Pi.")
on_deck("CP2102", "×2 → LD2410Cs", "two CP2102 USB-UART sticks in the hub", (40.0, 55.0, 10.0), -30.0, -160.0, "deck top, rear edge",
        "cable tie", "hand-tight", 0.020, note="Four wires each to an LD2410C: +5V, GND, TXD, RXD (3V3 stays empty). Label LEFT / RIGHT. The LD2450 needs no adapter: it goes straight onto the Pi header (pins 4, 34, 10, 8).")

# ── Turret (Ceres pan/tilt) at the front centre ─────────────────────────────
TX = 110.0
add("PT", "base", "Ceres pan/tilt turret base plate 100×60×6", TX, 0, DECK_TOP + TURRET_BASE[2] / 2, *TURRET_BASE,
    "flat on deck; pan stage free — the Ceres pan servo (PCA9685 ch 2) is continuous-rotation: the firmware turns it by timed nudges and it cannot hold or report an angle, so its zero is wherever it was set by hand", "front-left/right tiles across the seam",
    "4× M3×16 through base (6 mm) + deck (5 mm) + 4× M3 nut (M3 kit)", "1.0 N·m", M["turret"],
    verify="hole positions on the actual Ceres base", note="Spans X +60..+160, Y −30..+30. Tilt servo cable to PCA9685 ch 3, pan servo to ch 2.")
CAM_Z = DECK_TOP + TURRET_BASE[2] + TURRET_H
add("CAM", "on tilt bracket", "Owned USB webcam (C920-class)", TX, 0, CAM_Z, *CAM,
    "lens forward (+X) at tilt = 0", "turret tilt bracket — the Ceres clamp it was built for", "Ceres camera clamp; 2 cable ties as backup", "hand-tight",
    M["cam"], verify="camera mass ≤ 170 g and clamp fit", note=f"Lens centre Z ≈ {CAM_Z:.0f}. USB to Pi. Clear of the radar line of sight at Z 300.")
add("THERM", "above the camera", "MLX90640-D55 thermal array, 55° FoV", TX + 4, 0, CAM_Z + CAM[2] / 2 + 4 + 2, 26, 18, 8,
    "boresight parallel to the camera, +X at tilt = 0", "printed PETG/PLA saddle on top of the camera clamp", "2× M2 + nut through the saddle", "hand-tight",
    0.005, verify="breakout hole spacing", note="I2C 0x33 on the Pi's SECOND I2C bus (hardware i2c3 on BCM 4/5: dtoverlay=i2c3,pins_4_5, 400 kHz) so the 1 MHz thermal reads never stall the ToF/servo bus. 55° FoV: a person at 4 m fills ~6 pixels tall, a warm blob ~10 °C above the room. Ribbon runs with the camera USB through the tilt axis.")

# ── Radar post, rear centre, looking forward over the turret ────────────────
PX = -CROSS_X
add("PETG", "radar post", "Printed post 40×40×200 U-channel + separate 60×60×6 flange plate (2× M3×10 + nut) — printed flat, the flange would otherwise stand vertical and need supports", PX, 0, DECK_TOP + POST[2] / 2, *POST,
    "vertical, on the rear cross rail through the deck; PRINT IT FLAT as a 3-wall U-channel, open side rearward as the cable run — a 200 mm upright needs 200 mm of Z that small printers lack", "rear tile → rear cross rail top slot",
    "2× M4×12 (T-nut kit) through flange + deck into 2× M4 T-nuts in the rear rail top slot, at Y ±20; flange and tile counterbored to 3 mm each", "2.0 N·m", M["post"],
    note="Hollow 3 mm walls, print upright. Cable channel down the +X face for the two radar leads.")
add("PETG", "radar bar", "PETG radar bar 120×20×8 on the post top", PX, 0, DECK_TOP + POST[2] + 4, 120, 20, 8,
    "horizontal, antenna faces toward +X", "radar post top", "2× M3×10 + M3 nut through the post wall (no heat-set inserts on the list)", "hand-tight", 0.02)
add("LD2410C", "#1 (left)", "HLK-LD2410C radar", PX + 6, 50, RADAR_Z, *LD2410C, "antenna face +X toed out 30° to the LEFT (yaw +30°), horizontal",
    "radar bar, Y +50, on a printed 30° wedge", "2× M2 or a printed clip; nothing metal within 10 mm of the antenna face", "hand-tight", M["radar"],
    verify="PCB 35×7", note=f"Boresight Z = {RADAR_Z:.0f}, passes over the camera (top ≈ {DECK_TOP + TURRET_BASE[2] + TURRET_H + 10:.0f}). Walleye found floor-level radar sees nothing — this height is a compromise to TEST.")
add("LD2450", "—", "HLK-LD2450 radar", PX + 6, 0, RADAR_Z, *LD2450, "antenna face +X, straight ahead, horizontal", "radar bar, Y 0 (centre)",
    "2× M2 or printed clip", "hand-tight", M["radar"], verify="PCB 43×15",
    note="Between the two LD2410Cs, 50 mm from each. Its own ±60° field gives x/y of anything that moves; bench-test whether it reports a still, breathing person. Power one radar at a time first, then all three, and watch for mutual interference. Wired straight to the Pi header's UART (pins 4, 34, 10, 8) — no adapter.")
add("LD2410C", "#2 (right)", "HLK-LD2410C radar", PX + 6, -50, RADAR_Z, *LD2410C, "antenna face +X toed out 30° to the RIGHT (yaw −30°), horizontal",
    "radar bar, Y −50, on a mirrored printed 30° wedge", "2× M2 or a printed clip; nothing metal within 10 mm of the antenna face", "hand-tight", M["radar"],
    verify="PCB 35×7", note="The pair is an amplitude-comparison direction finder: log(E_left / E_right) at the breathing gate gives bearing (localize.py). Both in 0.2 m gate mode.")
add("MIC", "—", "INMP441 I2S microphone", PX + POST[0] / 2 + 3, 0, DECK_TOP + 120, 14, 12, 3, "port facing +X, on the post's front face below the bar",
    "radar post, FRONT face, 120 mm up", "1× M2 + nut (or VHB)", "hand-tight", 0.002, verify="board hole",
    note="I2S to Pi GPIO 18/19/20. Stop-and-listen: motors and fan off, ENABLE low, then 3 s capture. Voice/knock energy only — one mic gives no bearing.")
add("CO2", "—", "SCD41 CO2 sensor", PX - POST[0] / 2 - 4, 0, DECK_TOP + 150, 8, 24, 20, "sensing face −X (rear), in free air",
    "radar post, LEFT face, 150 mm up (the rear face is the open side of the U-channel)", "printed saddle + 2× M2 + nut", "hand-tight", 0.005, verify="breakout hole spacing",
    note="I2C 0x62 on the main bus. Rear face keeps it out of the driver-fan exhaust. Reads a room in minutes, not seconds: park at a closed door and wait.")

# ── VL53L1X obstacle sensors on the four rail outer faces ───────────────────
# Module stands on edge: its 4 mm thickness lies along the facing axis, the 25 mm
# length runs along the rail. Sits 2 mm proud of the rail face inside a printed clip.
# Front and rear only: one 2-pack. Sideways moves are made only after the camera has
# seen that side clear — the two side sensors were the first thing cut for cost.
for inst, x, y, face, dims in (("front", 175 + 2 + TOF[2] / 2, 0, "+X", (TOF[2], TOF[0], TOF[1])),
                               ("rear", -(175 + 2 + TOF[2] / 2), 0, "−X", (TOF[2], TOF[0], TOF[1]))):
    add("TOF", inst, "VL53L1X ToF module", x, y, RAIL_ZC, *dims, f"on edge, emitter facing {face}, recessed 2 mm inside a printed bumper lip — it is the first thing to touch a wall",
        f"printed clip in the {inst} rail outer slot", "1× M5×8 + M5 T-nut (clip) + 2× M2 (module)", "hand-tight", M["tof"],
        verify="module hole spacing", note=f"XSHUT → Pi BCM GPIO {dict(front=22, rear=27)[inst]} (GPIO 4/5 are the thermal array's I2C bus). Both share I2C 0x29 until re-addressed at boot.")

# ── Wiring ──────────────────────────────────────────────────────────────────
add("WIRE22", "power", "22 AWG (owned): pack → shield VMOT, → XL4015 IN (6 V servo rail)", -60, 40, DECK_TOP, 0, 0, 0,
    "—", "pack connector at the battery (rear)", "cable ties every 60 mm to the deck; tape or heat-shrink every joint", "—", M["strapwire"] / 3,
    note="~250 mm each run; 22 AWG is rated 7 A against a 4 A burst. Single common ground at the shield GND terminal. No fuse — by your call; the connector is the disconnect, so keep the pack leads short, sleeved and never resting on a rail edge.")
add("WIRE22", "signals", "22 AWG / Dupont: 4× motor 4-wire → shield sockets; I2C to 2× ToF + PCA9685 + SCD41; radar UARTs → 2× CP2102 + the Pi header", -80, 0, DECK_TOP, 0, 0, 0,
    "—", "—", "cable mounts on deck underside for motor leads", "—", M["strapwire"] / 3,
    verify="motor lead length — never documented; the FR motor needs ~400 mm to the shield, so expect to extend with 22 AWG and crimp 4-pin Dupont housings", note="Motor order at the shield, as the firmware maps them (verified 2026-09-09): X=BL, Y=FL, Z=BR, A=FR (D12/D13 jumpers fitted). Shared ENABLE on D8.")

# ── Checks ──────────────────────────────────────────────────────────────────
def box(p):
    return (p["x"] - p["l"] / 2, p["x"] + p["l"] / 2, p["y"] - p["w"] / 2, p["y"] + p["w"] / 2, p["z"] - p["h"] / 2, p["z"] + p["h"] / 2)

def overlap(a, b):
    A, B = box(a), box(b)
    return all(A[i] < B[i + 1] - 0.01 and B[i] < A[i + 1] - 0.01 for i in (0, 2, 4))

rigid = [p for p in parts if p["l"] > 0 and p["id"] not in ("STRAP", "CNR") and "spare" not in p["instance"]]
skip_pairs = {("LIPO", "PETG"), ("PETG", "LIPO"), ("FAN", "UNO"), ("UNO", "FAN"), ("CAM", "PT"), ("PT", "CAM"),
              ("LD2410C", "PETG"), ("LD2450", "PETG"), ("PETG", "LD2410C"), ("PETG", "LD2450"),
              ("MIC", "PETG"), ("PETG", "MIC"), ("THERM", "CAM"), ("CAM", "THERM")}  # by design mounted on / nested in
collisions = []
for i, a in enumerate(rigid):
    for b in rigid[i + 1:]:
        if (a["id"], b["id"]) in skip_pairs or a["id"] == b["id"] == "PETG":
            continue
        if overlap(a, b):
            collisions.append(f'{a["id"]} {a["instance"]}  ×  {b["id"]} {b["instance"]}')

mass = sum(p["mass_kg"] for p in parts)
cg = [sum(p[k] * p["mass_kg"] for p in parts) / mass for k in ("x", "y", "z")]
ground_min = min((box(p)[4], p["id"], p["instance"]) for p in rigid if p["mass_kg"] > 0 and p["id"] != "WHL")  # wheels touch the floor by definition
L, B = 2 * AXLE_X, 2 * abs(next(p["y"] for p in parts if p["id"] == "WHL"))
tip_pitch = math.degrees(math.atan((L / 2) / cg[2]))
tip_roll = math.degrees(math.atan((B / 2) / cg[2]))

fast = {"M5 T-nut": 8 + 20 + 2, "M5×8 (corner kit)": 8 + 20 + 2, "M4 T-nut": 8 + 2, "M4×10 / ×12 (T-nut kit)": 8 + 2,
        "M3×6 (motor, supplied with brackets)": 16, "M3 ×8/×12/×16 + nut (M3 kit)": 12 + 4 + 4 + 2 + 2, "M2 + nut": 4 + 4 + 2 + 2 + 4 + 1 + 2, "cable ties": 2 + 2 + 2 + 2 + 2 + 2 + 20}
kits = {"M5 T-nut": "corner kit 40 + T-nut kit", "M4 T-nut": "T-nut kit 40", "M4×10": "T-nut kit 20", "M3": "750-pc M3 kit", "M2.5": "COMRUN standoff kit"}

# ── Output ──────────────────────────────────────────────────────────────────
print(f"\nASSEMBLY — origin chassis centre on the floor; +X forward, +Y left, +Z up; mm\n{'='*100}")
print(f"{'id':8s} {'instance':22s} {'x':>7s} {'y':>7s} {'z':>7s}  fasteners")
for p in parts:
    print(f"{p['id']:8s} {p['instance'][:22]:22s} {p['x']:7.1f} {p['y']:7.1f} {p['z']:7.1f}  {p['fasteners'][:60]}")
print(f"\nCHECKS")
print(f"  parts placed                 {len(parts)}")
print(f"  AABB collisions              {len(collisions)}  {'PASS' if not collisions else 'FAIL: ' + '; '.join(collisions)}")
print(f"  lowest point                 Z = {ground_min[0]:.1f} mm  ({ground_min[1]} {ground_min[2]})  → ground clearance")
print(f"  frame envelope               350 × 390 × {RADAR_Z + 4:.0f} mm  (X × Y × Z incl. radar bar); overall width over the wheels {2*(abs(next(p['y'] for p in parts if p['id']=='WHL')) + WHEEL_W/2):.0f} mm")
print(f"  track / wheelbase            {B:.0f} / {L:.0f} mm")
print(f"  CG                           x {cg[0]:+.1f}  y {cg[1]:+.1f}  z {cg[2]:.1f} mm   (placed mass {mass:.2f} kg)")
print(f"  static tip angles            pitch {tip_pitch:.0f}°   roll {tip_roll:.0f}°   PASS")
print(f"  fasteners                    " + ", ".join(f"{k} {v}" for k, v in fast.items()))
print(f"  kit coverage                 M5×8 {fast['M5×8 (corner kit)']} of 40; M5 T-nut {fast['M5 T-nut']} of 40+; M4 T-nut {fast['M4 T-nut']} of 40; M3 {fast['M3 ×8/×12/×16 + nut (M3 kit)']} of 750; M2 {fast['M2 + nut']} of 645; ties {fast['cable ties']} of 100  PASS")
print(f"\nVERIFY ON RECEIPT (caliper, before drilling): " + "; ".join(sorted({p['verify'] for p in parts if p['verify']})))
print(f"\nNOT CHECKED: fastener pull-out in PETG, deck deflection under the turret, cable strain relief, servo torque with the ELP camera,")
print(f"  radar detection at Z = {RADAR_Z:.0f} mm (Walleye measured floor-level radar as blind — test before trusting), wheel roller clearance to the bracket foot.\n")

json.dump(dict(frame=dict(origin="chassis centre on floor", axes="+X forward, +Y left, +Z up", units="mm",
                          envelope=[350, 390, round(RADAR_Z + 4)], overall_width_with_wheels=round(2 * (abs(next(p["y"] for p in parts if p["id"] == "WHL")) + WHEEL_W / 2)), track=B, wheelbase=L, cg=[round(c, 1) for c in cg],
                          ground_clearance=ground_min[0], tip_pitch_deg=round(tip_pitch), tip_roll_deg=round(tip_roll),
                          collisions=collisions),
               parts=parts), open("assembly.json", "w"), indent=1)
with open("assembly.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(parts[0].keys()))
    w.writeheader(); w.writerows(parts)
print("wrote assembly.json, assembly.csv")
