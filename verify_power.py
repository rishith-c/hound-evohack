#!/usr/bin/env python3
"""
verify_power.py — DC simulation of Hound's simplified power tree (v3: one buck, no splices) as a resistive network,
solved by nodal analysis at the worst-case instant, plus the I2C pull-up rise-time check. Every number traces to a
datasheet (DS), a listing (LISTING), a measurement-class figure (MEAS) or an allocation (ALLOC) noted inline.

    python3 verify_power.py        # prints node voltages / margins and writes verify_power.json
"""
import json

# ── resistances (Ω) ──────────────────────────────────────────────────────────────────────────────────────────
OHM_PER_M = {14: 0.00828, 22: 0.0530, 24: 0.0842, 26: 0.134, 28: 0.213}     # copper 20 °C
R_PACK = 0.015           # HOOVO 3S 2200 80C internal (ALLOC, typical for 2.2 Ah 3S)
R_DEANS = 0.001 * 2      # two T-plug mates in the lead (DS-class contact resistance ≤ 1 mΩ each)
R_SCREW = 0.002          # 5.08 mm screw terminal contact (ALLOC)
R_USB_A = 0.030          # USB-A/C mated contact pair, VBUS+GND (ALLOC)


def wire(awg, m):        # out-and-back resistance of a two-conductor run
    return 2 * OHM_PER_M[awg] * m


# ── the worst-case instant: ramp burst + servo stall + WiFi burst, everything else at its peak ───────────────
I_MOT = 4.00             # 4× DRV8825 bus current, ramp burst (drivetrain.py)
V_SERVO, I_SERVO = 5.0, 2.1 + 2.1 + 0.2   # XL4015 at 5.0 V: pan + tilt MG996R both stalled (DS 2.5 A at 6 V, scaled) + fan 0.2
ETA = 0.85               # XL4015 efficiency (DS typical)
V_PACK_OC = 10.5         # pack floor, open circuit (3.5 V/cell)


def solve_pack(v_oc=V_PACK_OC):
    """Series chain: pack → Deans → 14 AWG 0.45 m → shield screw (node A). Motors draw at A. From A: 22 AWG 0.15 m →
    XL4015 IN (node B), which draws P_servo/(η·V_B) — solved by fixed point since the buck is a constant-power load."""
    r_lead = R_PACK + R_DEANS + wire(14, 0.45) + R_SCREW
    r_xl = R_SCREW + wire(22, 0.15) + R_SCREW
    v_b = v_oc
    for _ in range(50):
        i_xl = V_SERVO * I_SERVO / (ETA * v_b)
        v_a = v_oc - r_lead * (I_MOT + i_xl)
        v_b = v_a - r_xl * i_xl
    return dict(v_open=v_oc, i_lead=I_MOT + i_xl, v_shield_vmot=v_a, v_xl4015_in=v_b, i_xl4015_in=i_xl,
                drop_lead_mV=(v_oc - v_a) * 1000, drop_xl_branch_mV=(v_a - v_b) * 1000)


def solve_bank():
    """Bank (5.0 V no-load, 45 mΩ effective source, 3 A rated) → 22 AWG 0.2 m + USB-C → Pi input (node P).
    Pi draws 1.2 A; the downstream USB switch (50 mV) feeds the webcam (0.30 A), R4 (0.20) and the hub (0.10 + radars
    0.40 = 0.50) — the hub's own cable and the adapters' 5V pins each add contact and 28 AWG drops; the fan hangs
    on the 5 V header (0.20). ESP32 #3 sits on the bank's second port (0.50 A burst) and only loads the bank."""
    r_bank = 0.045                                            # ALLOC: a real 3 A bank holds ≥ 4.85 V at 3 A
    r_cable = wire(22, 0.20) + R_USB_A                         # SPEC: bank cable ≤ 0.2 m with 22 AWG (or heavier) power conductors
    loads_pi_side = 1.20 + 0.30 + 0.20 + 0.50 + 0.10         # Pi, webcam, R4, hub(+radars), 3.3 V loads seen at 5 V  (peaks)
    i_bank = loads_pi_side                                    # fan and ESP32 #3 are on the XL4015 rail now
    v_bank = 5.0 - r_bank * i_bank
    v_pi = v_bank - r_cable * loads_pi_side
    v_usb = v_pi - 0.05                                       # Pi 4 USB power switch, DS
    v_hub_in = v_usb - (wire(28, 0.30) + R_USB_A) * 0.50
    v_cp = v_hub_in - R_USB_A * 0.20                          # adapter socket, LD2450 branch 0.2 A
    v_ld2450 = v_cp - wire(26, 0.25) * 0.20                   # 4-wire lead to the radar
    v_cam = v_usb - (wire(28, 1.5) + R_USB_A) * 0.30
    v_fan = V_SERVO - wire(22, 0.12) * I_SERVO - wire(24, 0.20) * 0.20   # XL4015 → PCA terminal → ch-15 header → fan
    return dict(i_bank=i_bank, v_bank_loaded=v_bank, v_pi_in=v_pi, v_pi_usb=v_usb, v_hub_in=v_hub_in, v_ld2450=v_ld2450,
                v_webcam=v_cam, v_fan=v_fan, i_pi_usb=0.30 + 0.20 + 0.50, i_header=0.0)


def i2c_rise(r_pullup, c_bus_pf):
    """0.3→0.7 Vdd rise time of an RC bus = 0.8473·R·C; limits from the I2C spec: 1000 ns (100 kHz), 300 ns (400 kHz),
    120 ns (1 MHz)."""
    t = 0.8473 * r_pullup * c_bus_pf * 1e-12
    return dict(r=r_pullup, c_pf=c_bus_pf, t_rise_ns=t * 1e9, ok_100k=t <= 1000e-9, ok_400k=t <= 300e-9, ok_1M=t <= 120e-9,
                i_sink_mA=3.3 / r_pullup * 1000)


if __name__ == "__main__":
    P = solve_pack(); B = solve_bank()
    checks = []
    def chk(name, val, lim, unit="V", higher_is_ok=True):
        ok = val >= lim if higher_is_ok else val <= lim
        checks.append(dict(name=name, value=round(val, 3), limit=lim, unit=unit, ok=ok))
        print(f"  {'PASS' if ok else 'FAIL':4s} {name:62s} {val:6.3f} {unit}  (limit {'≥' if higher_is_ok else '≤'} {lim})")
    print("PACK SIDE — worst case: 4 A motor burst + servo stall, pack at its 10.5 V floor")
    chk("VMOT at the shield terminal vs DRV8825 UVLO 8.2 V (DS) + 1 V margin", P["v_shield_vmot"], 9.2)
    chk("XL4015 input vs 5.0 V out + 1.0 V dropout (DS)", P["v_xl4015_in"], 6.0)
    chk("pack lead current vs 14 AWG / Deans 50 A", P["i_lead"], 20.0, "A", False)
    chk("lead drop (pack → shield) as a fraction of 10.5 V", P["drop_lead_mV"] / 10500, 0.03, "", False)
    print("BANK SIDE — worst case: every Pi-side load at its peak at the same instant")
    chk("bank current vs 3.0 A rating", B["i_bank"], 3.0, "A", False)
    chk("Pi input vs its 4.63 V under-voltage warning + 0.1 V", B["v_pi_in"], 4.73)
    chk("Pi USB total vs the 1.2 A shared limit (Pi docs)", B["i_pi_usb"], 1.2, "A", False)
    chk("XL4015 output (both servos stalled + fan, momentary) vs its 5 A peak rating", I_SERVO, 5.0, "A", False)
    chk("LD2450 supply at the radar vs its 5 V ±10 % floor (DS 4.5 V)", B["v_ld2450"], 4.5)
    chk("webcam supply on its captive 1.5 m cable vs the ~4.4 V most cameras still run at (USB spec floor is 4.75: run 720p if it drops out)", B["v_webcam"], 4.4)
    chk("fan supply on the XL4015 rail during a servo stall vs 4.5 V", B["v_fan"], 4.5)
    print("I2C — i2c3 (BCM 4/5) with the MLX90640 breakout's own 10 kΩ pull-ups, ~60 pF of bus (0.35 m of wire + two boards, ALLOC)")
    for r in (10000, 4700, 2200):
        i = i2c_rise(r, 60)
        print(f"  {r:5d} Ω: rise {i['t_rise_ns']:.0f} ns → 100 kHz {'ok' if i['ok_100k'] else 'NO'}, 400 kHz {'ok' if i['ok_400k'] else 'NO'}, 1 MHz {'ok' if i['ok_1M'] else 'NO'}; sink {i['i_sink_mA']:.1f} mA")
    i1 = i2c_rise(1800 * 10000 / (1800 + 10000 * 1 / 3), 80)   # Pi 1.8 kΩ ∥ PCA9685 10 kΩ ∥ two ToF 10 kΩ, 80 pF
    print(f"  I2C-1 (Pi 1.8 kΩ ∥ three 10 kΩ boards ≈ {i1['r']:.0f} Ω, 80 pF): rise {i1['t_rise_ns']:.0f} ns → 400 kHz {'ok' if i1['ok_400k'] else 'NO'}; sink {i1['i_sink_mA']:.1f} mA (Pi pins sink 3 mA min: {'ok' if i1['i_sink_mA'] <= 3.0 else 'HIGH'})")
    print(f"\n  pack: {P['i_lead']:.2f} A in the lead, VMOT {P['v_shield_vmot']:.2f} V, XL4015 in {P['v_xl4015_in']:.2f} V   bank: {B['i_bank']:.2f} A, Pi {B['v_pi_in']:.2f} V")
    json.dump(dict(pack=P, bank=B, checks=checks, i2c3={r: i2c_rise(r, 60) for r in (10000, 4700, 2200)}, i2c1=i1), open("verify_power.json", "w"), indent=1)
    print(f"  {sum(1 for c in checks if not c['ok'])} FAIL of {len(checks)} checks")
