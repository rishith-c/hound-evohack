> **Current design revision:** The September 5 BOM now uses fixed sensors and four drive motors. The linear-rail CAD below is superseded and is not fabrication-ready for the current configuration. See [current BOM](../shopping/AMAZON-BOM.md).

> **September 2026 shopping revision:** This CAD predates the new 80 mm wheels and 132 mm battery. It is not fabrication-ready for the selected BOM. Only five motors and a Raspberry Pi are confirmed retained; the older inventory table below is historical. See [current shopping draft](../shopping/AMAZON-BOM.md).

# Mecanum human-presence rover — hackathon CAD concept

This package contains editable 3D CAD for the user's clarified demonstration: a rover moving on mostly intact floors beside rubble. It is **not build-approved or validated for locating people beneath rubble**. No hardware, motor, sensing, navigation or rescue test has been performed.

## Files

- `rover.step`: assembled concept with labelled components.
- `rover_exploded.step`: exploded assembly for review.
- `rover.py`: shared parametric build123d source; units mm, +X forward, +Y left, +Z up.
- `parts/`: nine custom-part designs, each with STEP, STL and a small Python generator. The STL files are geometry exports, not approved print instructions.
- `cad-verification.json`: actual limited geometry test results, with the physical build gate separately marked NOT PASSED.
- `inspection.json`: CAD-tool topology, plane and positioning inspection.
- `CAD_BRIEF.md`: assumptions, calculations and catalogue search provenance.
- PNG files: actual CAD snapshots, not image-generated illustrations.

To regenerate without the local CAD tools, install `requirements.txt` in a Python virtual environment, edit the named parameters in `rover.py`, and run `python export_all.py`. Run `python verify_cad.py` afterward for the limited geometry checks. This does not run hardware or sensing tests.

## Assembly layout

Four 350 mm 2020 rails form the frame. Four owned JK42HS40-1704-13A motors directly drive four illustrative 100 mm mecanum wheels; opposite diagonals use the same roller handedness. Contact-centre wheelbase is 250 mm and track is 480 mm. The assembly is 350 ×512 ×277 mm; see the verification report for actual bounds. Wheels use independently rotating 45° rollers with modelled axle and support representations. Their final manufacturer, load rating and hub mounting pattern are not selected.

The fifth motor drives a transverse timing belt. The sensor carriage translates through a 200 mm baseline on a 300 mm guide. Two LD2410C reservations face forward with an open antenna face. Two mast columns support the bridge. The battery sits low on the deck; the Pi, two ESP32-S3 boards, Uno, shield, four A4988s, TB6600 and regulated-power reservations are labelled. A fan is reserved over the shield. The deck uses four 170 mm tiles and a centre joiner.

No mast, battery or board position here establishes electromagnetic compatibility, mechanical strength or usable sensor accuracy. The battery envelope is only **110 ×40 ×30 mm** until the actual pack is measured. Electronics envelopes, strap clearances, mounting-hole patterns and connectors must be checked against the owned boards. Wheel-to-hub interfaces, retained nuts, bearing side loads, bridge fasteners, wire routing and other assembly hardware remain incomplete.

## What changed from the first calculation

The first report assessed four conventional wheels skidding laterally during turns. Mecanum wheels change that contact model. Its 0.408 N·m scrub result does not apply unchanged to the new wheel arrangement. This concept targets slow indoor demonstration motion, provisionally 0.1 m/s, and does not claim a 10° climbing capability.

The preliminary 6 kg level-floor screening requires 0.102 N·m per motor with an assumed 0.65 loss factor, or **0.153 N·m measured running torque** for a 1.5 torque ratio. The CAD brief shows that arithmetic. That mass remains an allocation and must be reconciled with selected wheel masses, actual print infill, guide hardware and battery. No speed–torque test exists for the motors on the 11.1 V battery, so the operating point has not converged. The nominal bracket bending calculation is limited to a simple rectangular section and cannot approve the bracket or printed layer orientation.

## Owned and still needed

| Item | Quantity | Status |
|---|---:|---|
| JK42HS40-1704-13A motors | 5 | Owned, user confirmed |
| 2020 extrusion rails | 4 | Owned provisionally; measure actual lengths |
| CNC Shield V3 | 1 | Owned |
| A4988 modules | 4 | Owned; sense resistors/current/cooling unverified |
| TB6600 external driver | 1 | Owned; exact model and input-current convention unknown |
| 11.1 V battery | 1 | Owned; size, mass, mAh, C rating and chemistry unknown |
| Arduino Uno | 1 | Assumed owned from original brief |
| Pi, ESP32-S3, LD2410C | 1, 2, 2 | Existing payload per brief; exact board formats unconfirmed |
| Matching mecanum wheel set | 2 left + 2 right | Needed; nominal 100 mm, actual interface TBD |
| Wheel hubs | 4 | Custom concept; match final purchased wheels |
| Motor brackets | 4 | Custom concept |
| Deck tiles and centre joiner | 4 + 1 | Custom concept |
| Battery cradle and electronics tray | 1 + 1 | Custom concept |
| Corner gussets | 4 | Custom concept |
| Mast columns and sensor carriage | 2 + 1 | Custom concept |
| 300 mm guide and carriage | 1 set | Needed; MGN12-size reservation, actual catalogue part TBD |
| 20T GT2 drive pulley and idler | 1 each | Needed; drive bore 5 mm; bearings/retention TBD |
| Open GT2 belt and carriage clamp hardware | 1 set | Needed; pitch 2 mm, width 6 mm reservation |
| Bridge plate, motor support, idler support | 1 each | Custom parts represented in assembly; material/joints unverified |
| Sweep home/end switches | 2 | Needed |
| Fan, heatsinks, fan supports | 1 + 4 + 4 | Needed unless already available |
| Regulated 5 V supply, distribution, fuse, switch/cutoff | 1 set | Needed; size after battery and Pi model confirmation |
| Fasteners, straps, nuts, spacers, cable protection | As required | Final quantities await fit and structural checks |

## Integration that still has to be implemented

Use the Pi for the user interface and sensor processing. Use the Uno for timed motor pulses, acceleration limits, communication timeout and stop behavior. The four shield axes must remain independent. The original V3 pin map is:

| Wheel / axis | STEP | DIR |
|---|---|---|
| Front left / X | D2 | D5 |
| Front right / Y | D3 | D6 |
| Rear left / Z | D4 | D7 |
| Rear right / A | D12 | D13 |

All four share D8 enable; verify the shield's A-axis jumper routing. The TB6600 requires another STEP/DIR interface and a homing input; its optocoupler input requirements must be checked before assigning connections. No ready-to-run firmware or complete wiring diagram is included in this CAD package. The battery does not connect directly to the Pi's 5 V rail.

For the conventional X roller layout and correctly chosen positive wheel directions, the planned kinematic mapping is:

```
k = (wheelbase + track)/2 = 0.365 m
omega_FL = (vx - vy - k*wz)/0.050
omega_FR = (vx + vy + k*wz)/0.050
omega_RL = (vx + vy - k*wz)/0.050
omega_RR = (vx - vy + k*wz)/0.050
```

Wheel angular rates are rad/s. Verify actual motor polarity and roller handedness with wheels lifted before floor testing. Command signs alone do not prove wheel odometry, because wheel slip and missed steps can occur.

For the demonstration, stop the rover, allow vibration to settle, home the carriage, sweep through known positions, and record each sensor output with a timestamp and sweep coordinate. Report “presence detected” with the sensor evidence; “no detection” must not be interpreted as “no person present.” Motion and repeated range readings alone do not establish a unique person's location.

The [LD2410C manufacturer](https://www.hlktech.com/en/Goods-239.html) describes indoor presence sensing with a stated 0.75 m distance resolution and up to 6 m sensing distance. Those specifications do not validate detection through concrete or rubble. A 200 mm sweep does not by itself supply the missing angular resolution or target association. Treat WiFi CSI performance as the existing payload's experimental result, not as something created or verified by these CAD files. Autonomous navigation also requires validated obstacle sensing/localization and software; it has not been implemented here.

## Before fabrication or claiming a working demonstration

1. Measure the owned battery, rails, boards and motor shafts; select a wheel set and guide, then update the model and interfaces.
2. Confirm current settings from A4988 sense resistors, cooled driver operation, battery current/sag/cutoff and regulated Pi power. Measure motor torque at the intended loaded battery voltage and speed.
3. Complete bracket/joint, wheel-shaft/bearing and bridge calculations, then perform full interference and FDM checks. The present tests cover selected pairs, not every component or fastener.
4. Validate forward/backward, lateral and yaw motion at low speed; verify stop and communication-loss behavior. Home the sweep and measure repeatability independently of commanded steps.
5. Demonstrate detection with consenting participants in an accessible, controlled setup and a separate ground-truth record. Record false positives, missed detections and location error for each tested obstruction. Do not put anyone under rubble for testing.

Suggested future print orientations: deck/joiner/tray/gussets/cradle broad base down; hub flange down; motor bracket broad exterior face down; mast on its side; carriage orientation to be resolved from load and overhang checks. These are review proposals, not a support-free printing claim. Material, layer height, infill, layer strength, overhangs, nut retention and dimensional tolerances are not released. The source includes 3.2 mm M3 and 5.2 mm M5 nominal clearance holes as requested; actual printer fit must be checked.

## What I did NOT analyze

Fatigue; buckling; impact/drop; vibration; dynamic stability while turning; long-run motor thermal derating; battery sag under stall; full tire contact/traction; wheel bearing and shaft capacity; bracket/joint and hot-FDM strength; complete collision/fastener/access checking; printability; wiring or firmware execution; EMI; sweep accuracy; autonomous navigation; through-wall/rubble detection; false-negative rates; active-fire, dust, water or disaster-site operation.
