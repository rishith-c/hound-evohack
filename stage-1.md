# Rover drivetrain — Stage 1 feasibility review

Status: FAIL for the provisional full-size direct-drive carpet-turning case; other gates remain unverified. No geometry, images, purchases, or print files released.

This is a calculated screening point, not a converged design or a claim that every arrangement using these parts is impossible. Mass allocations, wheel positions, friction, and actual running torque need verification. A result barely below unity is still a failure under the specified screening model.

## Confirmed inventory and corrections

Latest user clarification: five JK42HS40-1704-13A motors, four A4988 modules in a CNC Shield V3, one TB6600 external driver, approximately four 300–400 mm 2020 rails, and an 11.1 V gel-blaster battery. Arduino Uno ownership is assumed from the brief. Battery capacity, chemistry, discharge rating, connector rating, and mass remain unconfirmed.

The [exact JKONGMOTOR drawing, page 1, specifications rows 4–9](https://static.jkongmotor.com/JK42HS40-1704-13A-aidlnBprKrkloSRilikkrllkn.pdf) specifies 1.7 A **peak** per phase, 1.5 Ω ±10% at 20°C, 2.3 mH ±20%, 4.2 kgf·cm holding torque, and 0.24 kg. Conversion: 4.2 × 0.0980665 = 0.4119 N·m. Retain the requested conservative **0.40 N·m holding torque** throughout; do not treat it as running torque. The drawing confirms a 5 mm shaft with a flat, 31 mm mounting pitch, and a 39.5 ±1 mm body.

## Assumptions

- Four independently driven wheels, one motor per wheel, direct drive. Fifth motor drives a horizontal sweep through the TB6600.
- Rail length parameter `rail_length_m = 0.350`; permitted inventory range 0.300–0.400 m.
- Trial wheel diameter 0.080 m, radius r = 0.040 m. Trial contact-center wheelbase L = 0.350 m and track B = 0.420 m. Track and wheelbase are analytical assumptions, not measurements inferred directly from rail length.
- Gravity g = 9.81 m/s²; carpet Crr = 0.08; lateral scrub coefficient μ = 0.8; incline 10°; translational acceleration 0.3 m/s².
- Equal wheel loads for torque screening, all wheels touching a rigid plane. Real load transfer, uneven floors, tire compliance, and rotational inertia are excluded.
- Trial motor speed 60 rpm. The actual supply is the user's nominal 11.1 V battery. If it is a conventional 3S LiPo, full charge is 12.6 V; chemistry must be confirmed. Calculations also examine 9.6 V under load as an electrical sizing scenario, **not** an approved battery discharge cutoff.
- Sensor function is accepted as a user-supplied subsystem; this report does not validate through-wall detection or rescue suitability.

## 1. Mass and CG budget

Except the motor specification and Uno mass, these are explicit design allocations, not measured component masses. They must eventually be replaced with weighed parts and CAD-derived printed-part masses. The 0.5 kg battery allowance remains from the brief.

| Component | Mass arithmetic, kg | Assumed CG height above floor, m |
|---|---:|---:|
| Four drive motors | 4 × 0.240 = 0.960 | 0.040 |
| Sweep motor | 1 × 0.240 = 0.240 | 0.300 |
| Four extrusion rails | 4 × 0.350 × 0.500 = 0.700 | 0.070 |
| Wheels/tires | 4 × 0.100 = 0.400 | 0.040 |
| Wheel hubs | 4 × 0.025 = 0.100 | 0.040 |
| Motor mounts | 4 × 0.050 = 0.200 | 0.060 |
| Corner gussets | 4 × 0.015 = 0.060 | 0.070 |
| Electronics tray | 0.150 | 0.090 |
| Battery cradle | 0.070 | 0.040 |
| Mast | 0.100 | 0.220 |
| Sweep guide, belt, pulleys, carriage | 0.250 | 0.300 |
| Uno | 0.025 | 0.100 |
| CNC Shield | 0.040 | 0.120 |
| A4988 modules | 4 × 0.003 = 0.012 | 0.130 |
| TB6600 enclosure/driver | 0.200 | 0.090 |
| Fan and heatsinks | 0.040 | 0.120 |
| Converter, fuse, switch, power hardware | 0.100 | 0.070 |
| Payload electronics below mast | 0.500 | 0.100 |
| Moving sensor head | 0.200 | 0.350 |
| Battery | 0.500 | 0.040 |
| Subtotal | **4.84700** | — |
| Fasteners, wiring, allowance | 0.15 × 4.847 = **0.72705** | 0.100 |
| Total | 1.15 × 4.847 = **5.57405** | calculated below |

The payload rows total the brief's 0.700 kg; the sweep motor is counted only once. Sweep hardware includes an additional guide provision, rather than assuming a fifth frame extrusion is already owned.

The rail allowance of 0.500 kg/m is intentionally above the 0.4627 kg/m example in [Maker Store's catalogue, printed page 03 / PDF page 6](https://www.makerstore.com.au/wp-content/uploads/filebase/Catalogues/2024%20-%20Extrusion%20Catalogue%20-%20Maker%20Store.pdf). It does not identify the user's rail profile.

With all other allocations fixed: m(ℓ) = 1.15 × (4.147 + 2ℓ) kg. At ℓ = 0.300/0.350/0.400 m: m = 5.45905/5.57405/5.68905 kg. Wheel positions must be recomputed separately if rail lengths change. The original “about 5 kg” is plausible as an early estimate, but this complete budget is **about 5.6 kg**.

## 2. Wheel loads and required torque

Weight W = mg = 5.57405 × 9.81 = 54.68143 N. Equal normal load N = W/4 = 13.67036 N per wheel.

Rolling alone: Frr = Crr W = 0.08 × 54.68143 = 4.37451 N. Trr = Frr r/4 = 4.37451 × 0.04/4 = **0.04375 N·m/wheel**.

Grade alone: Fg = W sin(10°) = 9.49533 N. Tg = Fg r/4 = **0.09495 N·m/wheel**.

Acceleration alone, excluding wheel/rotor inertia: Fa = ma = 5.57405 × 0.3 = 1.67222 N. Ta = Fa r/4 = **0.01672 N·m/wheel**.

Combined climbing and acceleration: T = [W sin(10°) + 0.08 W cos(10°) + ma]r/4 = **0.15476 N·m/wheel**. All three loads must be added for this simultaneous case.

### Turning in place — governing case

Use the requested quasi-static lateral scrub screening model. Each of all four tires produces lateral resistance μN at longitudinal lever arm L/2:

M_scrub = 4(μW/4)(L/2) = μWL/2 = 0.8 × 54.68143 × 0.350/2 = **7.65540 N·m of yaw resistance**.

Each wheel applies longitudinal force F at lateral lever arm B/2. Four wheels generate M_drive = 4F(B/2) = 2BF. Therefore:

F = M_scrub/(2B) = 7.65540/(2 × 0.420) = 9.11357 N/wheel.

T_scrub = Fr = μWLr/(4B) = **0.36454 N·m/wheel**.

Include rolling resistance while turning: T_turn = 0.36454 + 0.04375 = **0.40829 N·m/wheel**. Angular acceleration and contact-patch torsion would add further loads.

This model treats prescribed lateral scrub and rolling resistance separately; it is a screening approximation, not a solved combined-slip tire model. Do not simultaneously interpret μN lateral resistance and another μN longitudinal force as independently available traction. Actual scrub torque must be measured on the intended tires and carpet. The small nominal holding-torque shortfall is sensitive to mass and friction uncertainty, but cannot be declared a pass.

### Torque margins

Margin ratio M = available / required; required threshold M ≥ 1.00. Corresponding safety margin MS = M − 1. A 0.20 N·m dynamic value below is **only a sensitivity input**, not a motor specification, prediction, or guaranteed lower bound.

| Load case | Required N·m/wheel | M if measured running torque were 0.20 N·m | Optimistic ratio using 0.40 N·m holding torque |
|---|---:|---:|---:|
| Rolling on carpet | 0.04375 | 4.57 | 9.14 |
| 10° gravity load alone | 0.09495 | 2.11 | 4.21 |
| 0.3 m/s² acceleration alone | 0.01672 | 11.96 | 23.92 |
| All three combined | 0.15476 | 1.29 | 2.58 |
| Lateral scrub alone | 0.36454 | 0.55 — FAIL | 1.10 |
| Scrub plus rolling | **0.40829** | **0.49 — FAIL** | **0.98 — FAIL** |

Even granting all the holding torque, MS_turn = 0.40/0.40829 − 1 = **−0.0203**. No operational torque margin is verified because a matching speed–torque curve or measurement is missing.

### Three low-cost changes to investigate

These are options ranked by likely fabrication effort, not priced quotations or authorized alterations to the fixed architecture.

1. **Move wheel mounts inward along the frame, reducing wheelbase while retaining track.** With a measured 0.20 N·m available, L/B ≤ [4T/(Wr) − Crr]/μ = 0.35719; at B = 0.420 m, L ≤ **0.1500 m** just reaches M = 1. This retains the same motors and direct drive, but requires a new stability check and leaves little reserve. Frame length and wheelbase need not be identical.
2. **Use smaller wheels, if clearance permits.** Holding all other assumptions fixed, D_max = 80 × 0.20/0.40829 = **39.19 mm** for M = 1. A 42.3 mm square motor centered on that axle would intersect the floor even before a bracket is added. Therefore the wheel-only fix is **rejected for this 0.20 N·m scenario**. Even 80 mm wheels leave only 40 − 42.3/2 = **18.85 mm** under an unrotated motor body, before bracket clearance; rubble capability is unverified.
3. **Add belt reduction using the same motors.** For assumed transmission efficiency η = 0.90, 3:1 needs T_motor = 0.40829/(3 × 0.90) = **0.15122 N·m**. At 0.20 N·m measured motor torque, the wheel margin would be 1.32; 2:1 would only give 0.88 and fails. This changes the specified direct drive and adds mass. To preserve the trial road speed, 3:1 requires 180 rpm, where torque must be measured again. At 60 motor rpm, speed instead falls to 0.0838 m/s. This is not a verified fix yet.

Avoiding stationary turns and using broad arcs is a no-hardware operating option, but it does not satisfy the requested turn-in-place requirement. No option here is silently substituted into the fixed brief.

## 3. Speed–torque operating point

At 60 rpm and 80 mm wheels, v = πD × rpm/60 = π × 0.080 × 60/60 = **0.2513 m/s**. This is a commanded trial speed, **not a verified top speed**.

The exact motor drawing contains no speed–torque curve. Therefore usable dynamic torque at 60 rpm on the user's nominal 11.1 V battery is **unknown**. Inductance and resistance alone cannot establish pull-out torque, resonance losses, or starting margin. The winding electrical time constant is L/R = 0.0023/1.5 = **1.53 ms**, but it is not a torque curve.

Before release, measure sustainable shaft torque at the selected current, microstepping, RPM and lowest allowed loaded battery voltage, including acceleration and warm motors. Convert measured tangential force with T = F × lever radius. At a 40 mm radius, the current turn case requires F = 0.40829/0.040 = **10.21 N per wheel** with zero reserve. Testing should use an instrumented motor fixture and guarding, not a hand-held shaft load.

## 4. Arduino step rate

The [Uno Rev3 runs at 16 MHz](https://store.arduino.cc/products/arduino-uno-rev3). It has no universal fixed “aggregate steps/s” figure independent of firmware. Simultaneous axes can share timer events, and library overhead matters.

Per wheel: f_step = 200 × microsteps × rpm/60. At 60 rpm:

| Microsteps/full step | Per-wheel steps/s | Four-wheel sum |
|---|---:|---:|
| 1 | 200 | 800 |
| 4 | 800 | 3,200 |
| 8 | 1,600 | 6,400 |
| 16 | 3,200 | 12,800 |

Choose **1/4 stepping provisionally**, leaving timing headroom. A candidate fixed 10 kHz interrupt scheduler has 16,000,000/10,000 = **1,600 CPU cycles per tick**. Alternating set/clear scheduling supports at most 5,000 pulses/s per axis, giving a per-axis scheduling ratio of 5,000/800 = **6.25**. This is an architectural capacity calculation, not a measured firmware benchmark: compile, time the worst-case interrupt, and scope all four outputs while communications run before declaring it confirmed. Port writes are needed for predictable timing; do not assume a blocking per-motor loop meets the same budget.

For a provisional 20-tooth, 2 mm-pitch sweep pulley at 20 mm/s and 1/4 stepping: 40 mm/rev; f_sweep = (20/40) × 200 × 4 = **400 steps/s**. Wheel plus sweep sum = **3,600 steps/s**. Pulley, sweep speed and guide loads are not yet selected. Stopping to scan can further simplify scheduling.

The original V3 pin allocation in the brief can support independent A motion only when its jumpers connect D12/D13; verify the actual clone. All four wheel drivers share D8 enable. The shield's sockets are separate drivers; the TB6600 is a fifth, external axis. Its pulse/enable electrical interface and spare-pin assignment await its actual model. No GRBL firmware is assumed.

## 5. Power and heat with the owned drivers and battery

### Phase current is not battery current

Five times 1.7 A = **8.5 A as the sum of five peak phase-current ratings**. Ten phases each simultaneously at 1.7 A would sum to 17 A, but this is not normal sinusoidal microstepping and is **not** the battery-current requirement. Chopper drivers convert voltage/current.

For sinusoidal phase currents IA = Ipk sinθ and IB = Ipk cosθ:

P_copper,motor = R(IA² + IB²) = RIpk² = 1.5 × 1.7² = **4.335 W** at 20°C.

Five motors at that excitation: **21.675 W** of winding heat. Four A4988 drive motors contribute 17.340 W. Conservatively allow the unknown TB6600 excitation up to two phases at 1.7 A: **8.670 W**, giving **26.010 W** total cold copper heating. Verify its peak/RMS DIP table; never select 4 A simply because the enclosure supports it.

For a stated hypothetical 80°C winding temperature, using copper α = 0.00393/K: R80 = 1.5[1 + 0.00393(80 − 20)] = **1.8537 Ω**. The conservative copper allowance becomes 26.010 × 1.2358 = **32.143 W**. This is a temperature-conditioned heat calculation, not a predicted motor temperature or an approved operating temperature.

The [A4988 datasheet electrical characteristics, page 4](https://www.allegromicro.com/-/media/files/datasheets/a4988-datasheet.pdf) lists typical source/sink resistance of 0.320 Ω each. Approximate conduction loss per carrier at Ipk = 1.7 A: (0.320 + 0.320) × 1.7² = **1.850 W**; four carriers ≈ **7.398 W**, before switching, sense-resistor and other losses. Actual hot resistance and clone PCB heat transfer must be checked.

### Preliminary supply allocation

Use explicit, unmeasured allocations of 10 W for all driver losses, fan and control overhead; 25 W for Pi plus sensor electronics; and 90% efficiency for their converter. The Pi model and peripherals must fit that 25 W allocation or the budget changes.

Upper mechanical reservation at the trial drive speed: 4Tω = 4 × 0.40 × (2π × 60/60) = **10.053 W**. This is a power reservation, not a claim that 0.40 N·m is available at 60 rpm. Allocate another 2 W for sweep motion.

P_bus = 32.143 + 10 + 10.053 + 2 + 25/0.90 = **81.974 W**.

With 25% electrical reserve: P_supply = 1.25 × 81.974 = **102.468 W**.

At 11.1 V: I = 102.468/11.1 = **9.23 A**. At the 9.6 V sizing scenario: I = **10.67 A**. A regulated **12 V, 10 A bench supply** would satisfy this provisional steady allocation (120/102.468 = **1.17**), subject to its transient behavior; it is not required as a replacement for the owned battery. Battery, connector, wiring, fuse and cutoff remain unsized until labels and sag are known. The 10 W loss allocation must be validated and increased if measured losses exceed it.

For battery capacity Q in Ah and a credible continuous discharge rating C: nominal rated current is CQ amps. Require at least CQ ≥ **10.67 A** for this allocation, and check measured sag and connector limits independently. Example only: 1.2 Ah would require C ≥ 10.67/1.2 = **8.90 C**. Do not infer the user's battery is 1.2 Ah.

With an assumed 80% usable energy, runtime at the 81.974 W operating allocation is t = 60 × 0.8 × 11.1Q/81.974 = **6.50Q minutes**. At the entire reserved 102.468 W it becomes **5.20Q minutes**. Actual duty-cycle power and battery capacity are unknown, so neither is a runtime promise.

An 11.1 V nominal pack can operate A4988 motor power within its specified voltage range. Supply the Pi from an appropriately rated regulated 5 V converter, not directly from this pack. Some external TB6600 products accept 9–42 V, as shown by [DFRobot's own unit](https://wiki.dfrobot.com/dri0043/); that specification does not identify the user's unit, so check its label and minimum input voltage before connecting it.

### Current adjustment and cooling

Keep the owned A4988 modules for evaluation. A verified 1.7 A continuous setting is not established for unidentified carriers. [Pololu's A4988 guidance](https://www.pololu.com/product/1182) gives approximately 1 A/phase without added cooling and specifies Vref = 8 Imax Rs. At the requested 1.7 A, specify heatsinks **and forced airflow** for this crowded shield, then thermally test; these measures do not guarantee an unknown clone will sustain the current. Begin unloaded characterization at no more than a verified 1.0 A current limit, lowering further if needed.

| Sense resistor | Vref at 1.0 A peak | Vref at 1.7 A peak, only after thermal validation |
|---|---:|---:|
| R050: 0.050 Ω | 8 × 1.0 × 0.050 = 0.400 V | 0.680 V |
| R068: 0.068 Ω | 0.544 V | 0.9248 V |
| R100: 0.100 Ω | 0.800 V | 1.360 V |

Identify actual sense resistors before setting Vref. Do not use a DRV8825 formula on an A4988. In full-step mode the phase measurement is approximately 0.707 × the configured peak limit; do not raise the limit to force 1.7 A in each full-step phase.

If torque scaled linearly with current, an optimistic 1.0 A holding estimate would be 0.40 × 1.0/1.7 = **0.2353 N·m**, giving only 0.2353/0.40829 = **0.576** for turning. This approximation is not a measured motor curve, but shows why lowering current is not a drivetrain torque fix.

For comparison only, [Pololu's DRV8825 carrier](https://www.pololu.com/product/2133/) supports approximately 1.5 A without additional cooling, with higher current requiring cooling. At Rs = 0.100 Ω, Vref = 5RsI = 0.850 V for 1.7 A. That is an optional future change, not a substitution in this review.

Insufficient cooling can trigger driver thermal shutdown, causing lost torque, lost steps, and unintended steering; overcurrent can damage drivers or overheat windings. Junction and winding temperatures remain unknown because thermal resistance, airflow, enclosure and ambient temperature are unknown. There is no passed thermal margin.

## 6. Static stability

Use the mass/height table, with a centered payload and battery. Sum of vertical first moments, including the 0.72705 kg allowance at 0.100 m, is **0.560265 kg·m**.

hCG = Σ(mizi)/Σmi = 0.560265/5.57405 = **0.100513 m**.

The mast and sweep are explicitly included: the fifth motor and sweep guide are at 0.300 m, and the sensor head at 0.350 m. They are not placed at floor level in the calculation.

Assume the 0.200 kg head plus 0.050 kg of the budgeted carriage moves ±0.100 m laterally. Maximum CG shift is Δy = 0.250 × 0.100/5.57405 = **0.004485 m**.

Pitch tipping angle = atan[(L/2)/hCG] = atan(0.175/0.100513) = **60.13°**.

Worst sweep-position lateral tipping angle = atan[(B/2 − Δy)/hCG] = atan[(0.210 − 0.004485)/0.100513] = **63.94°**.

At 10° longitudinal tilt, static restoring/overturning moment ratio = (L/2)/(hCG tan10°) = **9.87**. This is a conditional static pass for the assumed centered geometry, not a claim of traversability at the tip angles. Traction, motor torque and obstacles can prevent motion far earlier. Shortening wheelbase requires recalculation; actual head position, sweep travel and measured CG may change these figures.

## Design gate

| Check | Margin / evidence | Gate |
|---|---|---|
| Five motor inventory | 5 owned / 5 needed = 1.00 | Count confirmed |
| Mass | 5.574 kg allocated; actual masses unknown | Provisional |
| Straight combined load | 1.29 at hypothetical 0.20 N·m | Unverified dynamic torque |
| Turning, scrub only | 0.55 at hypothetical 0.20 N·m | FAIL in sensitivity case |
| Turning including rolling | 0.98 even using 0.40 N·m holding; MS −0.0203 | FAIL screening |
| Lower-current 1 A turning | 0.576 using optimistic linear holding estimate | FAIL screening |
| Speed/top speed | 0.2513 m/s commanded, torque curve absent | Unverified |
| Step scheduling at 1/4 step | 6.25 per-axis pulse-capacity ratio for proposed scheduler | Firmware timing unverified |
| Driver phase-current capability | Requested 1.7 A vs unknown cooled carrier capability | Unverified |
| Driver/motor temperature | Loss calculations only; no measured temperatures | Unverified |
| Battery current and endurance | 10.67 A at 9.6 V sizing point; Q and C unknown | Unverified |
| Bench supply option | 120/102.468 = 1.17 allocation ratio | Conditional only |
| Longitudinal static tip at 10° | Restoring/overturning = 9.87 | Conditional pass |
| Wheel bearing/shaft side loads | N = 13.67 N; scrub lateral load μN = 10.94 N per wheel | Exact motor bearing limits unverified |
| Mounts, hubs, fasteners, frame joints | No structural design or dimensions released | Unverified |
| Sweep force, accuracy and repeatability | Moving mass provision only | Unverified |

What fails first in this screening: wheel motors lose synchronism or fail to initiate a carpet turn before the chosen torque requirement is met. Driver overheating could reduce torque earlier. Unknown shaft side-load capacity is another unresolved direct-drive constraint. A guessed 0.40 N·m jam-bending calculation alone would not verify wheel support, lateral loads, bolt joints, or fatigue.

Next input: battery mAh, C rating, chemistry, A4988 sense resistors, exact rail lengths and component masses. Next engineering evidence: sustainable motor torque at selected RPM/current/loaded voltage, tire scrub measurement, and cooled driver temperatures. Recompute the geometry choices from those results before selecting a design for approval.

The user's brief requires approval before drawing. The applied [aero-mechatronics skill](/Users/rishith/.agents/skills/aero-mechatronics/SKILL.md) also states: “No geometry before a converged design point.” This failed screening point is not ready for that approval. Stages 2–4 remain gated; no images, build123d parts, STL files, final wiring, or final firmware are presented as build-ready.

## What I did NOT analyze

Fatigue; buckling; impact/drop; obstacle collision; vibration and resonance; dynamic stability while turning; wheel and rotor rotational inertia; uneven terrain and wheel unloading; tire combined-slip behavior and carpet variability; full shaft/bearing radial and axial load ratings; bracket bending, joint slip, hub retention and printed anisotropy; FDM creep and temperature-dependent strength; long-run motor thermal derating; battery sag under stall, aging and charge/discharge protection; regenerative bus transients; exact wire/fuse/connector ratings; thermal airflow; waterproofing, conductive dust, active-fire heat or hazardous atmospheres; sweep transmission loads, guide deflection, homing and baseline accuracy; stopping and rollback on power loss; firmware timing and fail-safe verification; radio interference and through-wall human-detection performance. The computed study does not establish readiness for deployment in a damaged or burning building.
