# Indoor search rover — practical BOM

**Recommended purchases: $219.79 USD before tax/shipping. Optional (battery ecosystem, extra senses, tools): $283.11.** Superseded detail: the live list at https://rover-amazon-bom.vercel.app and `../bom-site/bom.json` are the source of truth (adds the DROK 5 V buck and an M2 kit, drops the power bank and the hacksaw, and ties every part to a position from `../assembly.py`). This includes four obstacle sensors, camera, a new motor battery, charger and charging leads. Omit any equivalents you already own. Prices were observed September 4–5, 2026; stock and checkout prices can change. This is the preferred hackathon configuration, with physical validation still outstanding.

## The design I would build

Four independently driven 80 mm mecanum wheels, a low 2020 frame, fixed forward-facing radar mounts, a camera and four short-range obstacle sensors. Use your LiPo for motor power and your power bank for logic. The fifth motor and TB6600 stay spare. No linear rail, belt, sweep switches, tall gantry, or additional radar/ESP32 purchase.

The first working milestone is a camera-guided rover that moves slowly, stops, lets vibration settle, and reports radar evidence. Then add a bounded indoor route using known visual markers and obstacle-stop logic. Four range sensors are useful for guarding forward/reverse/sideways motion, but do not provide complete obstacle or stair coverage. The BOM does not include ready-to-run navigation or detection software.

LD2410C is the primary presence sensor, including stationary/micro-moving presence. LD2450 adds positions and speeds of moving targets; it is not the primary detector for an immobile person. Neither outputs heartbeat measurements. The second LD2410C is spare. Start with one radar powered; test the two radar types separately, then test simultaneous operation for interference before enabling both. Keep antenna faces unobstructed by metal.

A linear slide is not required for presence sensing. Rotate the rover between stationary scans if another view is useful. Different readings alone do not establish accurate triangulation. This is an indoor search demonstration; these sensors are not validated here for finding a motionless person behind concrete, rubble, fire or smoke. No detection must never be interpreted as proof that nobody is present.

## Already owned — no purchase required

| Item | Quantity | Use |
|---|---:|---|
| JK42HS40-1704-13A motors | 5 | Four drive wheels; fifth spare |
| Raspberry Pi | 1 | Video, interface, sensor processing; model still unknown |
| Power bank | 1 | Logic power; verify model, ports and combined output |
| HLK-LD2450 | 1 | Fixed moving-target tracker; no heartbeat output |
| HLK-LD2410C | 2 | One primary stationary/moving presence sensor; second spare |
| ESP32-S3 | 3 | One sensor interface; two available for optional CSI experiments |
| CP2102 USB-UART adapter | 1 | Bench configuration or one radar-to-Pi link; verify 3.3 V UART levels |
| TB6600 | 1 | Spare; no fifth axis in this design |
| Dupont leads and 22 AWG wire | Existing stock | Signals and suitable low-current connections |
| Three-pin switch | 1 | Motor switch candidate; DC rating and pinout unverified |

## Buy list

Check items when you have the full listed quantity. The website saves selections in your browser.

| Item / exact Amazon listing | Buy packs | Per pack | Line total |
|---|---:|---:|---:|
| [ELEGOO Uno R3 with USB cable](https://www.amazon.com/dp/B01EWOE0UU) | 1 | $16.99 | $16.99 |
| [CNC Shield V3 kit with four DRV8825 drivers and heatsinks](https://www.amazon.com/dp/B0B24YS695) | 1 | $15.99 | $15.99 |
| [SmaringRobot four 80 mm mecanum wheels with 5 mm couplings](https://www.amazon.com/dp/B0DWSWQV4T) | 1 | $29.99 | $29.99 |
| [VICHSAMWY four 350 mm 2020 V-slot rails](https://www.amazon.com/dp/B099M9DMSL) | 1 | $16.59 | $16.59 |
| [TOCLUX 20 corner brackets with M5 screws and T-nuts](https://www.amazon.com/dp/B0F1B85397) | 1 | $14.99 | $14.99 |
| [Anndason six steel NEMA17 brackets with screws](https://www.amazon.com/dp/B073QW9RPZ) | 1 | $16.99 | $16.99 |
| [Bemaka 2020 M3 M4 M5 T-nut kit with M4 x10 and x12 screws](https://www.amazon.com/dp/B0FQ55VFDK) | 1 | $13.99 | $13.99 |
| [Fgruh 750-piece M3 screw nut washer assortment](https://www.amazon.com/dp/B0FGV5FCBN) | 1 | $9.99 | $9.99 |
| [COMRUN M2.5 nylon standoff kit](https://www.amazon.com/dp/B0CKBWQSNY) | 1 | $9.99 | $9.99 |
| [OVERTURE black PETG 1 kg 1.75 mm](https://www.amazon.com/dp/B07PGYHYV8) | 1 | $14.69 | $14.69 |
| [MEIVIFPV five 20 x 250 mm battery straps](https://www.amazon.com/dp/B0GH8CGW2T) | 1 | $9.99 | $9.99 |
| [DWEII two VL53L1X distance modules](https://www.amazon.com/dp/B09V4DS888) | 2 | $14.99 | $29.98 |
| [ELP USBFHD01M-L28 USB UVC camera 2.8 mm](https://www.amazon.com/dp/B00KA80N9U) | 1 | $22.49 | $22.49 |
| [Kingston Canvas Select Plus 64 GB microSD SDCS2/64GB A1](https://www.amazon.com/dp/B07YGZQ4H8) | 1 | $17.99 | $17.99 |
| [Zeee 3S 11.1 V 5200 mAh XT60 soft battery](https://www.amazon.com/dp/B0972RKJDS) | 1 | $34.99 | $34.99 |
| [SKYRC B6AC Neo AC/DC balance charger 60 W AC](https://www.amazon.com/dp/B0CV64ZB2L) | 1 | $53.00 | $53.00 |
| [LINSYRC two XT60 male-to-female 30 cm 14 AWG charging extensions](https://www.amazon.com/dp/B09CT5VGPW) | 1 | $7.99 | $7.99 |
| [Tenergy 7 x 9 inch LiPo charging bag](https://www.amazon.com/dp/B08QCMMGJT) | 1 | $8.99 | $8.99 |
| [AOICRIE two 1S-8S cell voltage alarms](https://www.amazon.com/dp/B07VR4SV8C) | 1 | $6.59 | $6.59 |
| [Padarsey two pairs XT60 14 AWG pigtails](https://www.amazon.com/dp/B07BF8154S) | 1 | $6.99 | $6.99 |
| [XINWANG 18 AWG silicone wire six colors 5 m each](https://www.amazon.com/dp/B0B15CH937) | 1 | $17.89 | $17.89 |
| [etguuds two USB-A to USB-C 6 ft cables](https://www.amazon.com/dp/B07Z1TQYDN) | 1 | $7.99 | $7.99 |
| [Ginsco 580 heat-shrink assortment](https://www.amazon.com/dp/B01MFA3OFA) | 1 | $7.99 | $7.99 |
| [ALLWIN 100 cable mounts and 100 cable ties](https://www.amazon.com/dp/B0F9T5G2J5) | 1 | $6.99 | $6.99 |
| [SIXQJZML two 40 x40 x10 mm 5 V 0.15 A fans](https://www.amazon.com/dp/B0DY6GQMJX) | 1 | $5.99 | $5.99 |
| [Bicmice US non-polarized IEC C7 mains cord 6 ft; omit if correct cord included](https://www.amazon.com/dp/B08N42RQF6) | 1 | $6.99 | $6.99 |

The six-pack of steel brackets supplies four wheel mounts and two spares. The fan pack supplies one driver fan and a spare. The mixed T-nut kit supplies M4 rail fasteners and M3/M5 hardware; the M3 assortment is retained for short motor screws and deck fittings. PETG is for the deck, sensor/electronics mounts and battery retention; printer access is assumed. The four frame rails are all 350 mm, so no additional gantry stock is needed.

The charger now uses an XT60 extension, not the old banana-plug lead. Its manual includes an AC cord, but a US C7 cord is budgeted because the Amazon listing does not consistently establish plug region; subtract $6.99 if the supplied cord is correct. The 3S pack's balance plug must also connect correctly. The official charger supports 1–6S LiPo and 60 W AC charging. An initial 2.6 A setting is 0.5C for 5200 mAh and 32.76 W at 12.6 V; follow the actual pack and charger instructions.

No extra wall-plug adapter is needed for the basic rover. Wi-Fi CSI is optional development using the two remaining ESP32s. A controlled experiment may use a stationary transmitter powered from an existing suitable USB source and a rover receiver; this does not establish through-rubble detection.

## Power and connections

- LiPo -> suitable battery overcurrent protection -> verified DC-rated switch -> shield VMOT -> four A4988 drivers -> four motors.
- Power bank -> Pi power input. Pi USB-A -> included USB-A-to-B cable -> selected Uno USB-B for logic power and serial.
- Pi -> camera by USB. One ESP32-S3 can bridge radar UART data to the Pi; the CP2102 is useful for bench setup or a single direct UART link.
- Radars require their specified 5 V supply and 3.3 V UART signaling. Check the CP2102 board's actual I/O voltage; a selectable power-output pin does not necessarily change UART levels. Do not power radars from a weak 3.3 V adapter regulator.
- Four VL53L1X modules share I2C only after individual XSHUT control assigns unique addresses at boot. Keep Pi-side signaling at 3.3 V.
- Keep signal grounds correctly referenced, including the Uno/shield motor-supply reference. Never put LiPo voltage on a logic rail or connect two independent 5 V outputs together.

The Pi model and bank rating are still needed to finish the power design. Budgeting every sensor, fan and ESP32 through Pi USB without checking its aggregate peripheral limit is not acceptable. The active-radar supply requirement alone exceeds 200 mA for LD2450; each selected fan adds 150 mA at 5 V. Use only a verified bank output/distribution arrangement, with enough simultaneous current for the Pi and peripherals. No claim of power-bank runtime is made.

The bulk fuse/capacitor purchase packs remain removed as requested. Suitable battery overcurrent protection is still unresolved, and existing shield/driver supply capacitance must be checked. These are unpriced completion requirements, not a claim that the circuit can omit them. The owned switch must have an adequate DC rating; three pins alone do not establish its wiring or rating.

## Motor and frame fit

The steel bracket drawing has 4.3 mm base slots: use M4, not M5, to attach it to the 2020 rail. Mount wheel brackets inverted on the rail underside, with two M4 T-nuts per bracket (eight total). The kit has twenty M4 x10 screws and forty M4 T-nuts. Check screw protrusion, engagement and bottoming on the real extrusion before tightening.

The bracket's nominal axle-to-foot offset is 31 mm. With 80 mm wheels: shaft height =40 mm, rail underside =40+31=71 mm, rail top =91 mm. The motor bottom is nominally 40−42.3/2=18.85 mm above the floor. Four 350 mm rails in the proposed butt-jointed arrangement produce a 350 x390 mm frame. Bracket holes match the 31 mm motor pitch and M3 threads; a 3 mm bracket with M3 x6 screws gives nominal 3 mm engagement. Actual pilot clearance, wheel hub offset and motor/frame interference still need verification.

Use the purchased 5 mm wheel couplings; do not print a substitute load-bearing wheel hub. No radial load rating for the motor bearings or selected wheel set has been established. The old CAD contains a linear rail, different battery and different brackets and must not be used as fabrication instructions for this revision.

## Compute before claiming it works

Screening load case: 6 kg total mass ceiling, level floor, 0.1 m/s travel, 0.1 m/s² acceleration, assumed rolling coefficient 0.08 and effective drive efficiency 0.65. Mass is an allocation, not a measured result.

Required force =6×9.81×0.08 +6×0.1 =5.3088 N. Per-wheel torque =5.3088×0.04/(4×0.65)=0.08167 N·m. With a 1.5 allowance, each motor must demonstrate at least 0.12251 N·m at 23.87 rpm on the actual battery and driver settings. Published holding torque does not prove this operating point. Lateral mecanum resistance must also be tested; this straight-travel calculation does not establish a turning or strafing margin.

At 1/8 microstepping, 0.1 m/s requires about 637 pulses/s per wheel, or 2,546 across four equal-speed motors. Use a timed four-axis custom controller with acceleration limits, shared enable and communication timeout; ordinary three-axis GRBL is unsuitable. These rates are targets for a firmware timing test, not a measured Uno benchmark. Clamp combined translation/rotation commands to the tested maximum wheel rate.

Start near 1.0 A peak current on A4988 with heatsinks and the added fan, then test temperature and missed steps under load. Vref =8×I×actual sense resistance: 0.400 V for R050, 0.544 V for R068 or 0.800 V for R100 at 1 A. Do not set 1.7 A just because it is the motor rating. Fan inclusion does not prove adequate cooling.

Before calling the rover working: test all four wheel directions with wheels raised; loaded forward, reverse, strafe and turning; stop/watchdog behavior; sustained power and temperature; stationary/moving person and empty-room sensor trials; radar mutual interference; and marked-route obstacle stops. These tests have not been performed.

## Optional workshop tools — only if unavailable

| Item / exact Amazon listing | Buy packs | Per pack | Line total |
|---|---:|---:|---:|
| [Westinghouse MM600V15 multimeter](https://www.amazon.com/dp/B0DYJ465TC) | 1 | $34.89 | $34.89 |
| [Jiavarry 150 mm caliper](https://www.amazon.com/dp/B08Y8M54M9) | 1 | $21.98 | $21.98 |
| [Q-MING soldering iron kit](https://www.amazon.com/dp/B087767KNW) | 1 | $12.59 | $12.59 |
| [WORKPRO 12 inch hacksaw](https://www.amazon.com/dp/B09WYHPHTC) | 1 | $18.73 | $18.73 |
| [AMTOVL metric hex keys](https://www.amazon.com/dp/B0CJBRYQF3) | 1 | $9.99 | $9.99 |
| [DOWELL wire strippers](https://www.amazon.com/dp/B08Y6GDS61) | 1 | $9.99 | $9.99 |
| [MEIYA hanging scale](https://www.amazon.com/dp/B0GGHDNZWJ) | 1 | $7.99 | $7.99 |

## What I did NOT analyze

Final mass/CG, structural joint strength and slip, fatigue, buckling, impact/drop, vibration, dynamic stability, motor-bearing side loads, measured speed–torque curves, thermal equilibrium, battery sag and endurance, power-bank compatibility, full obstacle coverage, wireless reliability, or detection through rubble. No physical verification gate has passed.

Sources: [motor drawing](https://static.jkongmotor.com/JK42HS40-1704-13A-aidlnBprKrkloSRilikkrllkn.pdf), [LD2410C manufacturer](https://www.hlktech.com/en/Goods-239.html), [Hi-Link module selection](https://www.hlktech.com/NewsInfo-276.html), [Espressif CSI](https://docs.espressif.com/projects/esp-techpedia/en/latest/esp-friends/solution-introduction/esp-csi/esp-csi-solution.html), [A4988 current/cooling](https://www.pololu.com/product/1182), [SKYRC B6AC Neo manual](https://www.skyrc.com/download/100200%20B6ACneo%20Instruction%20Manual%20V1.3.pdf).
