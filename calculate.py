"""Reproduce Stage 1 screening arithmetic; this is not a design verification gate."""

import json
import math

RAIL_LENGTH_M = 0.350
RADIUS_M = 0.040
WHEELBASE_M = 0.350
TRACK_M = 0.420
RPM = 60
HOLDING_TORQUE_NM = 0.400
TRIAL_DYNAMIC_TORQUE_NM = 0.200  # Sensitivity input only: NOT measured or guaranteed.

# Name, allocated mass (kg), assumed height above floor (m).
items = [
    ("drive motors", 4 * 0.240, 0.040),
    ("sweep motor", 0.240, 0.300),
    ("rails", 4 * RAIL_LENGTH_M * 0.500, 0.070),
    ("wheels", 4 * 0.100, 0.040),
    ("hubs", 4 * 0.025, 0.040),
    ("mounts", 4 * 0.050, 0.060),
    ("gussets", 4 * 0.015, 0.070),
    ("tray", 0.150, 0.090),
    ("cradle", 0.070, 0.040),
    ("mast", 0.100, 0.220),
    ("sweep hardware", 0.250, 0.300),
    ("Uno", 0.025, 0.100),
    ("shield", 0.040, 0.120),
    ("drivers", 4 * 0.003, 0.130),
    ("TB6600", 0.200, 0.090),
    ("cooling", 0.040, 0.120),
    ("power hardware", 0.100, 0.070),
    ("low payload", 0.500, 0.100),
    ("head", 0.200, 0.350),
    ("battery", 0.500, 0.040),
]
subtotal = sum(m for _, m, _ in items)
items.append(("fasteners and wiring allowance", subtotal * 0.15, 0.100))
mass = sum(m for _, m, _ in items)
weight = mass * 9.81
theta = math.radians(10)
roll = 0.08 * weight * RADIUS_M / 4
scrub = 0.8 * weight * WHEELBASE_M * RADIUS_M / (4 * TRACK_M)
torques = {
    "roll": roll,
    "grade": weight * math.sin(theta) * RADIUS_M / 4,
    "acceleration": mass * 0.3 * RADIUS_M / 4,
    "combined": (weight * math.sin(theta) + 0.08 * weight * math.cos(theta)
                 + mass * 0.3) * RADIUS_M / 4,
    "scrub_only": scrub,
    "turn_including_roll": scrub + roll,
}
vertical_moment = sum(m * z for _, m, z in items)
cg = vertical_moment / mass
shift = 0.250 * 0.100 / mass
copper_cold_w = (4 + 2) * 1.7**2 * 1.5
copper_hot_w = copper_cold_w * (1 + 0.00393 * (80 - 20))
operating_w = copper_hot_w + 10 + 4 * HOLDING_TORQUE_NM * 2 * math.pi * RPM / 60 + 2 + 25 / 0.90
reserved_w = 1.25 * operating_w

print(json.dumps({
    "status": "SCREENING ONLY: running torque unknown; no build approval",
    "subtotal_kg": subtotal,
    "mass_kg": mass,
    "normal_load_per_wheel_N": weight / 4,
    "torques_Nm_per_wheel": torques,
    "trial_dynamic_ratios_NOT_verified": {k: TRIAL_DYNAMIC_TORQUE_NM / t for k, t in torques.items()},
    "holding_torque_comparison_NOT_running": {k: HOLDING_TORQUE_NM / t for k, t in torques.items()},
    "holding_turn_safety_margin": HOLDING_TORQUE_NM / torques["turn_including_roll"] - 1,
    "commanded_speed_m_s": 2 * math.pi * RADIUS_M * RPM / 60,
    "four_wheel_step_sum": {str(u): 4 * 200 * u * RPM / 60 for u in (1, 4, 8, 16)},
    "cg_vertical_moment_kg_m": vertical_moment,
    "cg_height_m": cg,
    "cg_sweep_shift_m": shift,
    "pitch_tip_degrees": math.degrees(math.atan(WHEELBASE_M / 2 / cg)),
    "roll_tip_degrees": math.degrees(math.atan((TRACK_M / 2 - shift) / cg)),
    "pitch_moment_ratio_at_10_degrees": WHEELBASE_M / 2 / (cg * math.tan(theta)),
    "cold_copper_allowance_w": copper_cold_w,
    "copper_at_assumed_80C_w": copper_hot_w,
    "operating_allocation_w": operating_w,
    "supply_with_reserve_w": reserved_w,
    "current_at_11_1V_A": reserved_w / 11.1,
    "current_at_9_6V_A": reserved_w / 9.6,
    "runtime_minutes_per_Ah_at_operating_allocation": 60 * 0.8 * 11.1 / operating_w,
}, indent=2))
