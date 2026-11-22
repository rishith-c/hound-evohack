#!/usr/bin/env python3
"""
dc_drive.py — could Hound run on cheap DC gearmotors instead of its four NEMA 17s, and what would it cost?

Same load model as drivetrain.py (its functions, its environment, the firmware's 0.6 m/s² starts), applied to a DC
build: the steppers, their steel brackets and the CNC shield stack come off, gearmotors + brackets + two TB6612FNG
go on. A brushed DC motor's torque falls linearly with speed, so each candidate is checked at the sagged pack
(10.5 V: speed and stall torque both ∝ V):

    n(T) = n0 · (1 − T/Ts)          I(T) = I0 + (Is − I0) · T/Ts

Acceptance (screening, same spirit as drivetrain.py):
    S1  level cruise holds the firmware's 530 mm/s top speed           n(T_cruise) ≥ rpm at 0.53 m/s
    S2  a start up the 5° ramp has the screening margin               Ts ≥ 1.25 · T_ramp_start
    S3  continuous duty inside the motor's rating                     T_cruise ≤ T_rated
    S4  the driver survives: TB6612FNG 1.2 A continuous, 3.2 A peak   I(T_ramp_start) ≤ 1.2 A,  Is(12.6 V) ≤ 3.2 A

Every motor number is DATASHEET (source in the table), every price LISTING (Amazon, 2026-09-25), masses ALLOCATED
unless the datasheet gives one. Run: python3 dc_drive.py
"""
import math

import drivetrain as d

V_SAG, V_FULL, V_REF = 10.5, 12.6, 12.0
KGCM = 0.0980665                     # N·m per kgf·cm
TB6612 = dict(i_cont=1.2, i_peak=3.2, v_max=13.5)          # DATASHEET (Toshiba TB6612FNG)

# name, wheel Ø m, supply V, n0 rpm, stall kg·cm, rated kg·cm, I0 A, Is A, motor kg, source
MOTORS = [
    ("TT 1:48 (6 V, via a buck)",   0.080, 6.0, 200, 0.80, None, 0.15, 1.5, 0.031, "adafruit.com/product/3777"),
    ("JGA25-370 12 V 1:35",         0.080, 12., 250, 3.80, 0.95, 0.05, 1.2, 0.100, "aslongdcmotor.com JGA25-370 table (stall '38' read as 3.8)"),
    ("JGA25-370 12 V 1:45",         0.080, 12., 188, 5.00, 1.26, 0.05, 1.2, 0.100, "aslongdcmotor.com JGA25-370 table"),
    ("JGA25-370 12 V 1:45, 97 mm",  0.097, 12., 188, 5.00, 1.26, 0.05, 1.2, 0.100, "same motor on the 97 mm wheel (4 mm coupling)"),
    ("JGB37-520 12 V 1:30",         0.080, 12., 200, 3.00, 0.75, 0.10, 1.2, 0.160, "precisionminidrives.com NFP-JGB37-520 table"),
    ("JGB37-520 12 V 1:56",         0.080, 12., 107, 4.80, 1.20, 0.10, 1.2, 0.160, "precisionminidrives.com NFP-JGB37-520 table"),
]
WHEEL_KG = {0.080: 0.150, 0.097: 0.200}       # per wheel + coupling: 80 mm kit weighs 1 lb for four (LISTING); 97 mm ALLOCATED
DC_BRACKET_KG, DC_CTRL_KG = 0.020, 0.040      # 25/37 mm L-bracket; UNO R4 (or the spare ESP32-S3) + two TB6612 (ALLOCATED)


def dc_mass(m_motor, wheel_d):
    drop = ("4x JK42HS40", "4x steel NEMA 17", "Uno + CNC Shield", "4x 80 mm mecanum")
    base = sum(m for n, m, _ in d.MASS_ITEMS if not n.startswith(drop))
    return (base + 4 * (m_motor + DC_BRACKET_KG + WHEEL_KG[wheel_d]) + DC_CTRL_KG) * (1 + d.FASTENER_ALLOWANCE)


def wheel_T(mass, wheel_d, crr, ramp, a):
    t, f = d.wheel_torque(mass, crr, ramp, a)             # drivetrain.py assumes 80 mm: scale the lever arm
    return t * wheel_d / d.WHEEL_D_M


def evaluate(m):
    name, wd, v_nom, n0, ts, tr, i0, is_, mk, src = m
    sag = (V_SAG / V_REF) if v_nom == 12. else 1.0          # a 6 V motor sits behind a buck: no sag
    n0s, tss = n0 * sag, ts * KGCM * sag
    mass = dc_mass(mk, wd)
    t_cruise = wheel_T(mass, wd, d.CRR_MECANUM_CARPET, 0, 0)
    t_strafe = wheel_T(mass, wd, d.CRR_MECANUM_STRAFE, 0, d.A_FW_ACCEL)
    t_ramp = wheel_T(mass, wd, d.CRR_MECANUM_CARPET, d.RAMP_DEG, d.A_FW_ACCEL)
    need_rpm = d.V_FW_MAX / (math.pi * wd) * 60
    n_cruise = max(0.0, n0s * (1 - t_cruise / tss))
    i_at = lambda t: i0 + (is_ * sag - i0) * min(1.0, t / tss)
    checks = {
        "S1 top speed": (n_cruise >= need_rpm, f"{n_cruise:.0f} rpm vs {need_rpm:.0f} → {n_cruise / 60 * math.pi * wd:.2f} m/s"),
        "S2 ramp start": (tss >= 1.25 * t_ramp, f"stall {tss / t_ramp:.2f} × the ramp start"),
        "S3 continuous": (tr is None or t_cruise <= tr * KGCM, f"cruise {t_cruise / KGCM:.2f} of {'?' if tr is None else tr} kg·cm rated"),
        "S4 driver": (i_at(t_ramp) <= TB6612["i_cont"] and is_ * (V_FULL / V_REF if v_nom == 12. else 1) <= TB6612["i_peak"],
                      f"{i_at(t_ramp):.2f} A at the ramp start, {is_ * (V_FULL / V_REF if v_nom == 12. else 1):.1f} A stall"),
    }
    pack_a = 4 * i_at(t_cruise) * (v_nom / d.V_BUS_LOADED if v_nom != 12. else 1)
    return dict(name=name, mass=mass, t_cruise=t_cruise, t_strafe=t_strafe, t_ramp=t_ramp, checks=checks,
                ok=all(c[0] for c in checks.values()), pack_a=pack_a, src=src)


# ── prices, Amazon, 2026-09-25 (LISTING) ─────────────────────────────────────────────────────────────────────
STEPPER_NEW = [("5× NEMA 17 0.41 N·m 1.5 A (JK42HS40 class)", "B0FHHY2D7B", 43.19), ("CNC Shield V3 + 4× DRV8825", "B0B24YS695", 15.99),
               ("Anndason 6× steel NEMA 17 brackets", "B073QW9RPZ", 16.99), ("80 mm mecanum × 4 + 5 mm couplings", "B0DWSWQV4T", 29.99),
               ("2× 40 mm 5 V fans (driver cooling)", "B0DY6GQMJX", 5.99)]
DC_NEW = [("4× JGA25-370 12 V encoder gearmotor ('170 RPM_12V' variant, torque unpublished)", "B0H5TP3KQL", 4 * 10.56),
          ("3× TB6612FNG dual driver (two used)", "B0BLRSWTLM", 7.82),
          ("6× 25 mm gearbox bracket, 33 × 26 × 33 mm, M3 (four used)", "B07HHY2BJN", 9.59),   # B0DCZVTYMY said 540/555 motors
          ("97 mm mecanum × 4 + 4 mm couplings", "B0F9TK5FSW", 40.99)]
LISTING_N0 = 170                  # the cheapest listing's '170 RPM_12V' variant: no-load at 12 V, torque not published
# All on Prime, shipped by Amazon (arrive 2026-09-27/28 as checked): the motor comes WITH its 25 mm bracket (and a 65 mm
# wheel that goes unused), so no bracket pack. 200 rpm needs less stall torque than 170 (min_stall_for).
DC_PRIME = [("4× JGA25-371 12 V 200 rpm encoder gearmotor + bracket (Emoshayoga 'Speed 200')", "B0H2JP84J7", 4 * 20.39),
            ("3× TB6612FNG dual driver (two used)", "B0BLRSWTLM", 7.82),
            ("97 mm mecanum × 4 + 4 mm couplings", "B0F9TK5FSW", 40.99)]
PRIME_N0 = 200
# UNDER $100, keeping the 80 mm mecanum wheels Hound already has (their couplings are 5 mm, for the NEMA 17 shafts; a
# JGA25's shaft is 4 mm): swap in 4 mm rigid flange couplings, the same generic part with a smaller bore — compare the
# flange holes with the old coupling before fitting. On 80 mm wheels the 200 rpm motor needs ≥ 3.4 kg·cm (min_stall_for).
DC_UNDER_100 = [("4× JGA25-371 12 V 200 rpm encoder gearmotor + bracket (Emoshayoga 'Speed 200')", "B0H2JP84J7", 4 * 20.39),
                ("3× TB6612FNG dual driver (two used)", "B0BLRSWTLM", 7.82),
                ("4× 4 mm rigid flange coupling (for the owned 80 mm wheels)", "B0FKMPNVR5", 3.99)]


def min_stall_for(n0, wheel_d, m_motor=0.100):
    """Smallest 12 V stall torque (kg·cm) at which a motor with this no-load speed passes S1 and S2 on this wheel."""
    sag = V_SAG / V_REF
    mass = dc_mass(m_motor, wheel_d)
    tc = wheel_T(mass, wheel_d, d.CRR_MECANUM_CARPET, 0, 0); tr = wheel_T(mass, wheel_d, d.CRR_MECANUM_CARPET, d.RAMP_DEG, d.A_FW_ACCEL)
    need = d.V_FW_MAX / (math.pi * wheel_d) * 60
    if n0 * sag <= need:
        return None
    s1 = tc / (1 - need / (n0 * sag)); s2 = 1.25 * tr
    return max(s1, s2) / sag / KGCM


def main():
    stepper_m = d.design_mass()[1]
    print(f"\nDC DRIVE STUDY — Hound at the firmware's ramps (starts {d.A_FW_ACCEL} m/s²), pack sagged to {V_SAG} V")
    print("=" * 100)
    print(f"Stepper build today: {stepper_m:.2f} kg, motors draw ~1.96 A from the pack whenever energised, at any speed or load"
          f" (drivetrain.py, 1.5 A/phase); the R4 releases them 3 s after a stop unless 'hold' is on\n")
    rows = [evaluate(m) for m in MOTORS]
    for r in rows:
        print(f"{'PASS' if r['ok'] else 'FAIL'}  {r['name']:30s} {r['mass']:.2f} kg   cruise {r['t_cruise'] / KGCM:.2f} · strafe start "
              f"{r['t_strafe'] / KGCM:.2f} · ramp start {r['t_ramp'] / KGCM:.2f} kg·cm   pack ~{r['pack_a']:.2f} A cruising")
        for k, (ok, txt) in r["checks"].items():
            print(f"        {'ok ' if ok else 'NO '} {k:14s} {txt}")
        print(f"        source: {r['src']}")
    tot = lambda items: sum(p for _, _, p in items)
    print(f"\nCOST, a new build's drivetrain (Amazon 2026-09-25):")
    print(f"  steppers (as Hound is built)       ${tot(STEPPER_NEW):7.2f}   " + " + ".join(f"{n.split(' (')[0]} ${p:.2f}" for n, _, p in STEPPER_NEW))
    print(f"  DC + encoders, cheapest listings   ${tot(DC_NEW):7.2f}   " + " + ".join(f"{n.split(' (')[0]} ${p:.2f}" for n, _, p in DC_NEW))
    print(f"  DC + encoders, all on Prime        ${tot(DC_PRIME):7.2f}   " + " + ".join(f"{n.split(' (')[0]} ${p:.2f}" for n, _, p in DC_PRIME))
    print(f"  the Prime {PRIME_N0} rpm motor on 97 mm wheels passes only if its 12 V stall torque is ≥ {min_stall_for(PRIME_N0, 0.097):.1f} kg·cm")
    print(f"  UNDER $100, owned 80 mm wheels  ${tot(DC_UNDER_100):7.2f}   " + " + ".join(f"{n.split(' (')[0]} ${p:.2f}" for n, _, p in DC_UNDER_100))
    print(f"  ... where the {PRIME_N0} rpm motor needs ≥ {min_stall_for(PRIME_N0, 0.080):.1f} kg·cm stall at 12 V; all on Prime")
    for wd in (0.080, 0.097):
        need = min_stall_for(LISTING_N0, wd)
        print(f"  the listing's {LISTING_N0} rpm motor on {wd * 1000:.0f} mm wheels passes only if its 12 V stall torque is "
              + ("never (too slow)" if need is None else f"≥ {need:.1f} kg·cm") )
    print(f"  No listing found publishes per-variant torque: bench-check one motor before buying four — no-load rpm at 12 V")
    print(f"  from its encoder, and the rpm with a known load (a string round the shaft lifting a weight: T = m·g·r).")
    print(f"  Hound as it stands                 $   0.00   the steppers, drivers and wheels are owned")
    print(f"\nFITTING THE DC PARTS TO HOUND (assembly.json):")
    print(f"  the 25 mm brackets' feet have 3.5 mm (M3) holes; drill them to 4.3 mm and they take the M4 T-nuts and M4×10")
    print(f"  screws Hound already holds (30 spare). Under the rails there is only the four brackets and the battery cradle")
    print(f"  (|x| ≤ 42, |y| ≤ 20 mm), so a ~75 mm gearmotor reaching inboard from each corner leaves ~230 mm between the")
    print(f"  left and right motors; on 97 mm wheels its underside sits ~36 mm up, against 18.9 mm for the NEMA 17s now.")
    print(f"  The spare ESP32-S3 is the controller (its PCNT units count all four encoders in hardware); the pack feeds the")
    print(f"  TB6612s' VM directly (12.6 V full < 13.5 V). Firmware for it is NOT written: closed-loop wheel speed is needed.")
    print(f"\nNOT ANALYSED: gearbox backlash and wear, encoder resolution for the speed loop (11 PPR × 45 = 495 counts/rev,")
    print(f"  ×4 quadrature = 1980), motor heating over a mission, the firmware a DC drive needs (closed-loop wheel speed),")
    print(f"  and whether a seller's variant matches the datasheet — measure no-load rpm and stall current on arrival.\n")


if __name__ == "__main__":
    main()
