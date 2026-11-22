#!/usr/bin/env python3
"""Mecanum drivetrain sizing: can four JK42HS40-1704-13A steppers carry the rover?

Written out explicitly because no aeromech calculator covers a ground
drivetrain. Every input is labelled MEASURED (from a datasheet or listing),
ALLOCATED (a design budget to be replaced by a weighed part), or ASSUMED (an
engineering coefficient that must be tested). Acceptance: every margin ratio
>= MARGIN_REQUIRED with the load case that produced it.

    python3 drivetrain.py            # prints the report
    python3 drivetrain.py --json     # emits drivetrain.json for the BOM site
"""

import json
import math
import sys

# ── Motor: JKONGMOTOR drawing JK42HS40-1704-13A, spec rows 4–9 ──────── MEASURED
T_HOLD_NM = 4.2 * 0.0980665          # 4.2 kgf·cm holding torque → 0.4119 N·m
I_RATED_A = 1.7                      # peak per phase
R_OHM = 1.5                          # per phase at 20 °C
L_H = 2.3e-3                         # per phase
MOTOR_MASS_KG = 0.240
FULL_STEPS_PER_REV = 200

# ── Wheel and geometry ──────────────────────────────────────────────────────
WHEEL_D_M = 0.080                    # SmaringRobot 80 mm mecanum        MEASURED (listing)
WHEEL_R_M = WHEEL_D_M / 2
MECANUM_FACTOR = math.sqrt(2)        # roller axis at 45°: only F/√2 of each wheel's
                                     # tangential force acts along the travel direction
ETA_MECH = 0.85                      # roller bearings + coupling loss            ASSUMED
WHEELBASE_M = 0.25                   # axles at X ±125 mm                     from assembly.py / firmware LX_MM
TRACK_M = 0.431                      # wheel centres at Y ±215.5 mm           from assembly.py / firmware LY_MM
H_CG_M = 0.10                        # CG height with the battery low on the deck           ALLOCATED
# Rotating inertia per wheel, accelerated with the rover: the wheel + coupling taken as a thin ring at the
# roller radius (its mass sits in the rollers — the conservative shape), plus the motor rotor.
J_WHEEL = 0.150 * WHEEL_R_M ** 2     # 0.150 kg ring at r                                    ASSUMED shape
J_ROTOR = 54e-7                      # 54 g·cm², typical 40 mm-long NEMA 17 rotor             ASSUMED (not on the drawing)
# Traction: a free roller transmits force only along its own axle, so each wheel's ground force is
# F_body·√2/4 and must stay under μ·N on the least-loaded wheel after weight transfer.
MU_ROLLER = {"rubber-faced rollers": 0.50, "hard plastic rollers, smooth floor": 0.30}   # ASSUMED — measure (tilt test)

# ── Environment ─────────────────────────────────────────────────────────────
G = 9.81
CRR_MECANUM_CARPET = 0.12            # plain wheel ~0.08; rollers add friction     ASSUMED
CRR_MECANUM_STRAFE = 0.15            # rollers rolling perpendicular               ASSUMED
RAMP_DEG = 5.0                       # ADA 1:12 = 4.76°, rounded up
A_CRUISE = 0.10                      # m/s²
A_RESPONSIVE = 0.30                  # m/s²
V_CRUISE = 0.10                      # m/s
V_MAX = 0.30                         # m/s
V_BUS_LOADED = 10.5                  # 3S at 3.5 V/cell under load                ASSUMED

# ── Firmware r4_drive (drive code unchanged since tag v1.0-best-drive) ─────────── FIRMWARE
A_FW_ACCEL = 0.60                    # ACCEL_MM_S2: the body-vector ramp while speeding up
A_FW_DECEL = 1.80                    # 3 × ACCEL_MM_S2 while slowing: every stop and direction change
V_FW_DEFAULT = 0.415                 # remote default (speedPct 78)
V_FW_MAX = 0.530                     # MAX_RATE 13 500 steps/s ÷ 25.46 steps/mm at 1/32
MICROSTEPS_FW = 32                   # caps on MS1 + MS3
TICK_HZ_FW = 30000                   # step ISR; a step needs two ticks → 15 000 steps/s per axis
MAX_RATE_FW = 13500

# ── Stepper dynamic torque ─────────────────────────────────────────────────
# Pull-out torque at low speed is below holding torque: microstepping torque
# ripple, detent torque, resonance. Published NEMA 17 curves sit at 0.70–0.85
# of holding torque below ~100 rpm. 0.70 is the conservative end.   ASSUMED
K_DYN = 0.70

# ── Driver current capability (Pololu carrier guidance) ─────────────────────
DRIVERS = {
    "A4988, no cooling":            1.0,
    "A4988, heatsink + fan":        1.2,   # conservative; Pololu says ~1 A bare, more with cooling
    "DRV8825, no cooling":          1.5,
    "DRV8825, heatsink + fan":      1.7,   # carrier allows 2.2 A cooled; motor caps it at 1.7
}

# ── Acceptance ───────────────────────────────────────────────────────────────
MARGIN_REQUIRED = 1.25               # screening FoS on an unmeasured running torque

# ── Mass budget, kg ─────────────────────────────────────────────────────────
MASS_ITEMS = [
    # (name, kg, tag)
    ("4x JK42HS40 motors",                     4 * MOTOR_MASS_KG, "MEASURED"),
    ("4x 350 mm 2020 V-slot @ 0.50 kg/m",      4 * 0.350 * 0.50,  "ALLOCATED"),
    ("4x 80 mm mecanum wheel + 5 mm coupling", 4 * 0.150,         "ALLOCATED"),
    ("4x steel NEMA 17 bracket",               4 * 0.113,         "MEASURED"),   # listing: 1.5 lb per 6 = 113 g each
    ("Pan/tilt turret: 2x MG996R-class servo + bracket + PCA9685", 0.250, "ALLOCATED"),  # field-triage-rover hardware
    ("XL4015 5 A buck (owned): 5.0 V servo + fan rail", 0.030,     "ALLOCATED"),
    ("USB power bank for Pi, compact 5000 mAh — WEIGH IT", 0.130, "ALLOCATED"),
    ("8x 2020 corner bracket + T-nuts",        8 * 0.012,         "ALLOCATED"),
    ("Uno + CNC Shield + 4 drivers + fan",     0.117,             "ALLOCATED"),
    ("Raspberry Pi + case",                    0.070,             "ALLOCATED"),
    ("HOOVO 3S 2200 mAh 80C shorty LiPo",       0.140,             "ALLOCATED"),  # listing says 138 g; VERIFY on receipt
    ("2x LD2410C + LD2450 + ESP32-S3 #3 CSI node", 0.060,          "ALLOCATED"),  # assembly.py: 0.045
    ("Second USB bank (ESP32 #3 only) — WEIGH IT", 0.090,           "ALLOCATED"),  # assembly.py
    ("4-port USB hub + 2x CP2102",             0.050,             "ALLOCATED"),  # assembly.py: 0.030 + 0.020
    ("Owned USB webcam (C920-class)",          0.162,             "ALLOCATED"),  # Ceres DESIGN.md envelope
    ("2x VL53L1X",                             0.010,             "ALLOCATED"),
    ("MLX90640 thermal + SCD41 CO2 + INMP441 mic", 0.025,         "ALLOCATED"),
    ("Printed parts: 4 tiles, cradle, post, bridge, clips, lock", 0.550, "ALLOCATED"),  # 4×80 g tiles at 20% infill
    ("Cable ties, tape",                       0.030,             "ALLOCATED"),
    ("22 AWG wiring + connectors",             0.080,             "ALLOCATED"),
]
FASTENER_ALLOWANCE = 0.15
MASS_CEILING_KG = 6.0                # sensitivity case from the earlier study


def design_mass():
    sub = sum(m for _, m, _ in MASS_ITEMS)
    return sub, sub * (1 + FASTENER_ALLOWANCE)


def inertia_torque(accel):
    """Torque per wheel to spin the wheel and rotor up or down with the rover: J·α, α = a / r."""
    return (J_WHEEL + J_ROTOR) * accel / WHEEL_R_M


def wheel_torque(mass, crr, ramp_deg, accel):
    """Required tangential torque per wheel, N·m, driving (uphill, speeding up) on four mecanum wheels."""
    th = math.radians(ramp_deg)
    f_total = mass * G * (crr * math.cos(th) + math.sin(th)) + mass * accel
    return f_total * WHEEL_R_M * MECANUM_FACTOR / (4 * ETA_MECH) + inertia_torque(accel), f_total


def brake_torque(mass, crr, ramp_deg, decel):
    """Required braking torque per wheel, N·m, stopping at `decel` while pointing DOWN a ramp of `ramp_deg`.
    Rolling resistance and the mechanical losses help a stop, so η multiplies here instead of dividing."""
    th = math.radians(ramp_deg)
    f_total = max(0.0, mass * decel + mass * G * math.sin(th) - mass * G * crr * math.cos(th))
    return f_total * WHEEL_R_M * MECANUM_FACTOR * ETA_MECH / 4 + inertia_torque(decel), f_total


def traction_margin(mass, accel, mu, lateral=False, ramp_deg=0.0):
    """μ·N on the least-loaded wheel ÷ the ground force each wheel must carry (F_body·√2/4), for a pure
    speed change at `accel` (no help from rolling resistance — the conservative side). Weight moves across the
    wheelbase (forward/back) or the track (strafe) by m·a·h/L; on a ramp the uphill wheels also unload."""
    th = math.radians(ramp_deg)
    base = TRACK_M if lateral else WHEELBASE_M
    n_min = mass * G * math.cos(th) / 4 - mass * accel * H_CG_M / (2 * base) - mass * G * math.sin(th) * H_CG_M / (2 * WHEELBASE_M)
    f_wheel = (mass * accel + mass * G * math.sin(th)) * MECANUM_FACTOR / 4
    return mu * n_min / f_wheel, n_min, f_wheel


def available_torque(i_set):
    return T_HOLD_NM * (i_set / I_RATED_A) * K_DYN


def corner_rpm(i_set):
    """Full-torque step rate limit: current must swing -I→+I in half a step, dI/dt = V/L."""
    f_full = V_BUS_LOADED / (4 * L_H * i_set)          # full steps/s
    return f_full / FULL_STEPS_PER_REV * 60


def rpm_at(v):
    return v / (math.pi * WHEEL_D_M) * 60


def step_rate(v, microsteps):
    return FULL_STEPS_PER_REV * microsteps * rpm_at(v) / 60


def power(i_set, t_wheel, v, driver_r_on=0.64):
    """Bus power, W: copper + mechanical + driver conduction. Driver R = A4988 src+sink."""
    copper = 4 * R_OHM * i_set ** 2
    omega = v / WHEEL_R_M
    mech = 4 * t_wheel * omega
    driver = 4 * driver_r_on * i_set ** 2
    return copper + mech + driver, copper, mech, driver


def main(emit_json=False):
    sub, m_design = design_mass()
    cases = {
        "A  level cruise, a=0.1":        (CRR_MECANUM_CARPET, 0.0,      A_CRUISE),
        "B  level responsive, a=0.3":    (CRR_MECANUM_CARPET, 0.0,      A_RESPONSIVE),
        "C  5° ramp, a=0.3":             (CRR_MECANUM_CARPET, RAMP_DEG, A_RESPONSIVE),
        "D  strafe on carpet, a=0.3":    (CRR_MECANUM_STRAFE, 0.0,      A_RESPONSIVE),
    }
    fw_cases = {   # what the firmware actually commands: every start at 0.6 m/s², every stop at 1.8 m/s²
        "E  level start, fw a=0.6":      ("drive", CRR_MECANUM_CARPET, 0.0,      A_FW_ACCEL),
        "F  strafe start, fw a=0.6":     ("drive", CRR_MECANUM_STRAFE, 0.0,      A_FW_ACCEL),
        "G  5° ramp start, fw a=0.6":    ("drive", CRR_MECANUM_CARPET, RAMP_DEG, A_FW_ACCEL),
        "H  level stop, fw a=1.8":       ("brake", CRR_MECANUM_CARPET, 0.0,      A_FW_DECEL),
        "I  5° downhill stop, fw a=1.8": ("brake", CRR_MECANUM_CARPET, RAMP_DEG, A_FW_DECEL),
        "J  strafe stop, fw a=1.8":      ("brake", CRR_MECANUM_STRAFE, 0.0,      A_FW_DECEL),
    }
    out = {"design_mass_kg": round(m_design, 3), "subtotal_kg": round(sub, 3),
           "margin_required": MARGIN_REQUIRED, "cases": {}, "drivers": {}}

    print(f"\nMECANUM DRIVETRAIN — four JK42HS40-1704-13A, direct drive, 80 mm wheels")
    print(f"{'='*78}")
    print(f"\nMASS BUDGET")
    for name, m, tag in MASS_ITEMS:
        print(f"  {name:44s} {m:6.3f} kg  {tag}")
    print(f"  {'fasteners + wiring allowance 15%':44s} {sub*FASTENER_ALLOWANCE:6.3f} kg  ALLOCATED")
    print(f"  {'DESIGN MASS':44s} {m_design:6.3f} kg")
    print(f"  {'ceiling for sensitivity':44s} {MASS_CEILING_KG:6.3f} kg")

    print(f"\nREQUIRED TORQUE PER WHEEL   (T = F · r · √2 / (4 · η) + J·a/r,  η = {ETA_MECH},  J = wheel ring + rotor {J_WHEEL + J_ROTOR:.2e} kg·m²)")
    print(f"  {'load case':32s} {'F total N':>10s} {'T @ design':>11s} {'T @ 6 kg':>10s}")
    req = {}
    for name, (crr, ramp, a) in cases.items():
        t, f = wheel_torque(m_design, crr, ramp, a)
        t6, _ = wheel_torque(MASS_CEILING_KG, crr, ramp, a)
        req[name] = (t, t6)
        out["cases"][name.strip()] = {"force_N": round(f, 2), "torque_design_Nm": round(t, 4),
                                      "torque_6kg_Nm": round(t6, 4)}
        print(f"  {name:32s} {f:10.2f} {t:11.4f} {t6:10.4f}")
    print(f"  firmware ramps (braking: T = F · r · √2 · η / 4 + J·a/r — losses help a stop):")
    for name, (kind, crr, ramp, a) in fw_cases.items():
        fn = wheel_torque if kind == "drive" else brake_torque
        t, f = fn(m_design, crr, ramp, a)
        t6, _ = fn(MASS_CEILING_KG, crr, ramp, a)
        req[name] = (t, t6)
        out["cases"][name.strip()] = {"force_N": round(f, 2), "torque_design_Nm": round(t, 4),
                                      "torque_6kg_Nm": round(t6, 4)}
        print(f"  {name:32s} {f:10.2f} {t:11.4f} {t6:10.4f}")

    print(f"\nAVAILABLE TORQUE   (T_hold {T_HOLD_NM:.4f} N·m × I/{I_RATED_A} × k_dyn {K_DYN})")
    print(f"  {'driver / current setting':32s} {'I A':>5s} {'T avail':>8s}  margins A / B / C / D at design mass   verdict")
    governing = None
    for drv, i_set in DRIVERS.items():
        t_av = available_torque(i_set)
        margins = [t_av / req[c][0] for c in cases]
        margins6 = [t_av / req[c][1] for c in cases]
        fw = [t_av / req[c][0] for c in fw_cases]
        fw6 = [t_av / req[c][1] for c in fw_cases]
        worst = min(margins + fw)
        ok = worst >= MARGIN_REQUIRED
        out["drivers"][drv] = {"i_set_A": i_set, "t_avail_Nm": round(t_av, 4),
                               "margins_design": [round(x, 2) for x in margins],
                               "margins_6kg": [round(x, 2) for x in margins6],
                               "margins_firmware": dict(zip((c.split()[0] for c in fw_cases), (round(x, 2) for x in fw))),
                               "pass": ok}
        ms = " / ".join(f"{x:4.2f}" for x in margins)
        fs = " / ".join(f"{x:4.2f}" for x in fw)
        print(f"  {drv:32s} {i_set:5.2f} {t_av:8.4f}  {ms}   {'PASS' if ok else 'FAIL'}"
              f"   (6 kg worst {min(margins6 + fw6):.2f})")
        print(f"  {'':32s} {'':5s} {'':8s}  firmware E / F / G / H / I / J: {fs}")
        if ok and governing is None:
            governing = drv

    print(f"\nSPEED–TORQUE VALIDITY   (k_dyn assumes operation well below the corner speed)")
    for i_set in (1.0, 1.5, 1.7):
        print(f"  I = {i_set:.1f} A: full-current corner {corner_rpm(i_set):6.0f} rpm"
              f"   vs operating {rpm_at(V_CRUISE):.0f}–{rpm_at(V_FW_MAX):.0f} rpm (firmware cap {V_FW_MAX} m/s)"
              f"   ratio ≥ {corner_rpm(i_set)/rpm_at(V_FW_MAX):.1f}")
    ke = T_HOLD_NM / I_RATED_A
    print(f"  back-EMF at {V_FW_MAX} m/s: {ke * V_FW_MAX / WHEEL_R_M:.2f} V of {V_BUS_LOADED} V bus — negligible")

    cap = TICK_HZ_FW // 2
    print(f"\nSTEP RATE   (1/{MICROSTEPS_FW} — caps on MS1 + MS3 — {TICK_HZ_FW // 1000} kHz step ISR → {cap} steps/s per axis, firmware cap {MAX_RATE_FW})")
    for v in (V_CRUISE, V_FW_DEFAULT, V_FW_MAX):
        s = step_rate(v, MICROSTEPS_FW)
        print(f"  {v:.3f} m/s = {rpm_at(v):5.1f} rpm → {s:6.0f} steps/s per wheel, {4*s:6.0f} total"
              f"   {'OK' if s <= MAX_RATE_FW else 'EXCEEDS'} ({s / cap:.0%} of the ISR's {cap})")

    print(f"\nTRACTION   (per-wheel ground force F·√2/4 vs μ·N on the least-loaded wheel; weight transfer m·a·h/L,")
    print(f"  h = {H_CG_M} m, wheelbase {WHEELBASE_M} m, track {TRACK_M} m; margin required {MARGIN_REQUIRED})")
    t_cases = (("start, forward", A_FW_ACCEL, False, 0.0), ("stop, forward", A_FW_DECEL, False, 0.0),
               ("stop, strafe", A_FW_DECEL, True, 0.0), ("stop, 5° downhill", A_FW_DECEL, False, RAMP_DEG))
    out["traction"] = {}
    for mu_name, mu in MU_ROLLER.items():
        row = []
        for tn, a, lat, rd in t_cases:
            m, n_min, fw_ = traction_margin(m_design, a, mu, lat, rd)
            row.append(m); out["traction"][f"{tn}, μ {mu}"] = round(m, 2)
        print(f"  μ {mu:.2f} {mu_name:36s} " + "  ".join(f"{tn} {m:4.2f}{'' if m >= MARGIN_REQUIRED else (' FAIL' if m < 1 else ' LOW')}" for (tn, *_), m in zip(t_cases, row)))
    mu_need = max(traction_margin(m_design, a, 1.0, lat, rd)[2] / traction_margin(m_design, a, 1.0, lat, rd)[1] for _, a, lat, rd in t_cases)
    print(f"  μ needed with no margin at the worst of these: {mu_need:.2f}. Below it the wheels slide on every stop, and")
    print(f"  unevenly (different loads and roller wear), which turns a stop into a yaw or a sideways slip.")

    print(f"\nPOWER AND ENDURANCE   (HOOVO 3S 2200 mAh shorty, 80% usable, bus {V_BUS_LOADED} V)")
    for i_set in (1.0, 1.5):
        t_b = req["B  level responsive, a=0.3"][0]
        p, cu, me, dr = power(i_set, t_b, V_CRUISE)
        i_bus = p / V_BUS_LOADED
        hours = 2.2 * 0.8 / i_bus
        print(f"  I = {i_set:.1f} A: copper {cu:5.1f} W + mech {me:4.1f} W + driver {dr:4.1f} W"
              f" = {p:5.1f} W → {i_bus:4.2f} A → {hours:4.1f} h motors only")
    print(f"  Holding at rest draws the copper + driver terms with zero motion. Cut ENABLE (D8)")
    print(f"  when parked; mecanum wheels on a level floor do not roll away.")

    print(f"\nSHAFT RADIAL LOAD   (NEMA 17 typical rating 28 N at 20 mm from the flange — ASSUMED, unverified for this motor)")
    n_static = m_design * G / 4
    overhang = 23.5                       # wheel centre to flange face, mm (bracket leg 3 + 5 clearance + half wheel)
    lever = overhang / 20.0               # rating is quoted at 20 mm; load scales with the lever
    for dyn, case in ((1.5, "indoor floors, small bumps"), (2.0, "kerbs, thresholds")):
        n = dyn * n_static * lever
        print(f"  static {n_static:.1f} N/wheel at {overhang:.1f} mm overhang; ×{dyn} {case:26s} = {n:.1f} N-equivalent"
              f"   margin {28/n:.2f}  {'PASS' if 28/n >= 1.0 else 'FAIL'}")
    print(f"  ← thinnest margin in the design. Indoor floors pass; a 20 mm threshold does not. Keep the wheel tight to the leg.")
    print(f"  Mount the wheel as close to the motor face as the coupling allows.")

    print(f"\nSTATIC STABILITY   (h_CG ≈ {H_CG_M} m with battery on the deck — ALLOCATED)")
    h = H_CG_M
    print(f"  pitch tip {math.degrees(math.atan((WHEELBASE_M/2)/h)):.0f}°,"
          f"  roll tip {math.degrees(math.atan((TRACK_M/2)/h)):.0f}°   PASS")

    print(f"\n{'='*78}")
    print(f"VERDICT")
    AS_BUILT = "DRV8825, no cooling"          # Vref 0.75 V = 1.5 A (the fan is there for margin, not for current)
    t_av = available_torque(DRIVERS[AS_BUILT])
    allc = list(cases) + list(fw_cases)
    marg = {c: t_av / req[c][0] for c in allc}
    worst = min(marg, key=marg.get)
    level = {c: m for c, m in marg.items() if "ramp" not in c and "downhill" not in c}
    lw = min(level, key=level.get)
    def mass_for(case, i_set, target=MARGIN_REQUIRED):
        crr, ramp, a = cases[case] if case in cases else fw_cases[case][1:]
        lo, hi = 1.0, 10.0
        for _ in range(60):
            mid = (lo + hi) / 2
            (lo, hi) = (mid, hi) if available_torque(i_set) / wheel_torque(mid, crr, ramp, a)[0] >= target else (lo, mid)
        return lo
    print(f"  As built ({AS_BUILT}, {DRIVERS[AS_BUILT]} A) at the design mass {m_design:.2f} kg:")
    print(f"  every level-floor case passes — worst {lw.split()[0]} ({lw[3:].strip()}) at {level[lw]:.2f}.")
    fails = [c for c in allc if marg[c] < MARGIN_REQUIRED]
    if fails:
        print(f"  Below the {MARGIN_REQUIRED} screening margin: " + ", ".join(f"{c.split()[0]} {marg[c]:.2f}" for c in fails)
              + f" — the 5° ramp starts. {worst.split()[0]} governs" + (" and is still ≥ 1.0: it should climb, with no reserve for the unmeasured k_dyn." if marg[worst] >= 1.0 else ": it stalls."))
        for i_set in (DRIVERS[AS_BUILT], 1.7):
            print(f"  {worst.split()[0]} reaches {MARGIN_REQUIRED} at ≤ {mass_for(worst, i_set):.2f} kg at {i_set} A.")
    else:
        print(f"  Every case passes; {worst.split()[0]} governs at {marg[worst]:.2f}.")
    print(f"  Most of the mass is ALLOCATED, not weighed: weighing the rover moves this verdict more than any other number.")
    lvl_mu = MU_ROLLER["hard plastic rollers, smooth floor"]
    fm = traction_margin(m_design, A_FW_DECEL, lvl_mu)[0]
    print(f"  Traction: the firmware stops at {A_FW_DECEL} m/s². Rubber-faced rollers (μ 0.5) hold a level stop with")
    print(f"  {traction_margin(m_design, A_FW_DECEL, 0.5)[0]:.2f}; hard rollers on a smooth floor (μ {lvl_mu}) sit at {fm:.2f} — the wheels slide at")
    print(f"  every stop. That fits the end-of-move veer reported on 2026-09-24; it does not prove it.")

    print(f"\n  What fails first: a start up a 5° carpet ramp at the firmware's {A_FW_ACCEL} m/s². The motors stall")
    print(f"  silently — steppers do not slow down, they stop and lose position with no error.")
    print(f"  Next, in order: weigh the rover; measure μ (tilt a board under it until it slides, μ = tan θ);")
    print(f"  measure pull-out torque at 24 rpm, 1.5 A, on the real battery with a lever arm and the hanging")
    print(f"  scale. Those three numbers retire the allocations, MU_ROLLER and K_DYN.")

    print(f"\nNOT ANALYSED: fatigue, buckling, impact, vibration, roller wear, uneven floors,")
    print(f"  wheel unloading beyond rigid weight transfer, combined-slip mecanum behaviour (which way a sliding")
    print(f"  stop veers), thermal equilibrium of motors or drivers, battery sag under stall, firmware timing.")
    print(f"  None of this is a substitute for the three measurements above.\n")

    governing = next((d for d, v in out["drivers"].items() if v["pass"]), None)
    out["as_built"] = {"setting": AS_BUILT, "worst_case": worst.strip(), "worst_margin": round(marg[worst], 2),
                       "level_worst_case": lw.strip(), "level_worst_margin": round(level[lw], 2)}
    out["governing_setting"] = governing
    out["governing_case"] = worst.strip()
    if emit_json:
        with open("drivetrain.json", "w") as f:
            json.dump(out, f, indent=1)
        print("wrote drivetrain.json", file=sys.stderr)


if __name__ == "__main__":
    main(emit_json="--json" in sys.argv)
