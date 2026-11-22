#!/usr/bin/env python3
"""Emit CHATGPT-CHECK.md: a copy-paste prompt asking another model to re-check the build."""
import json
bom = json.load(open("bom-site/bom.json")); asm = json.load(open("assembly.json")); dt = json.load(open("drivetrain.json"))
items = bom["items"]; p = bom["prose"]
own = [i for i in items if i["status"] == "owned"]; buy = [i for i in items if i["status"] == "buy"]; opt = [i for i in items if i["status"] == "optional"]
L = []
L.append("I am building an indoor search rover for a hackathon. SCOPE: it must find a person behind DRYWALL (stud walls, interior doors) in a normal building on flat floors. Concrete, rubble, stairs and outdoor terrain are explicitly out of scope. Please do an adversarial verification of this design: find anything that will NOT physically fit, NOT electrically connect, or NOT work as claimed for that scope. Be specific and cite which two parts conflict. A previous reviewer already found and fixed the faults listed near the end under 'Already found and fixed' — do not repeat those; hunt for what they missed. Do not pad; if a section checks out, say so in one line.\n")
L.append("## Goal\nA 350 x 390 mm four-wheel mecanum rover on four owned NEMA 17 steppers, a pan/tilt turret carrying a webcam and a thermal array, three 24 GHz radars on a bar on a rear post (two LD2410Cs toed out for left/right, an LD2450 between them), two ToF obstacle sensors, all run by a Raspberry Pi with an Arduino UNO R4 WiFi doing the step generation. Purpose: drive into a room and find people (thermal + camera in line of sight, radar behind doors/walls).\n")
L.append("## What I already own (not buying)")
for i in own: L.append(f"- {i['qty']}x {i['item']} — {i.get('note','')}")
L.append("\n## What I am buying (exact Amazon listings)")
for i in buy: L.append(f"- {i['qty']}x {i['item']} — ${i['qty']*i['price']:.2f} — https://www.amazon.com/dp/{i['asin']} — {i.get('note','')}")
L.append(f"\nBuy total: ${sum(i['qty']*i['price'] for i in buy):.2f}")
L.append("\n## Optional, not in the first order")
for i in opt: L.append(f"- {i['item']} — " + (f"https://www.amazon.com/dp/{i['asin']} — " if i.get('asin') else "") + f"{i.get('note','')}")
L.append("\n## The design, in numbers")
L.append("Frame: +X forward, +Y left, +Z up, origin at chassis centre on the floor, all mm. " + " ".join(p["fit"]))
fr = asm["frame"]
L.append(f"\nEnvelope {fr['envelope'][0]} x {fr['envelope'][1]} x {fr['envelope'][2]} mm, track {fr['track']:.0f}, wheelbase {fr['wheelbase']:.0f}, CG z = {fr['cg'][2]:.0f} mm, ground clearance {fr['ground_clearance']:.1f} mm, tip angles {fr['tip_pitch_deg']}/{fr['tip_roll_deg']} deg, {len(fr['collisions'])} bounding-box collisions in the placement check.")
L.append("\nKey placements (part centre x, y, z mm; fastener):")
for pp in asm["parts"]:
    if pp["id"] in ("MOT","WHL","BRK","LIPO","BANK","UNO","PI","PT","CAM","THERM","LD2410C","LD2450","TOF","XL4015","PCA") and "spare" not in pp["instance"]:
        L.append(f"- {pp['id']} {pp['instance']}: ({pp['x']:+.0f}, {pp['y']:+.0f}, {pp['z']:.0f}) — {pp['fasteners']}")
L.append(f"\nDrivetrain sizing at {dt['design_mass_kg']:.2f} kg design mass, 80 mm mecanum wheels, direct drive, JK42HS40-1704-13A (0.41 N-m holding, 1.7 A, 1.5 ohm, 2.3 mH): required torque per wheel — " + "; ".join(f"{k}: {v['torque_design_Nm']:.3f} N-m" for k, v in dt["cases"].items()) + ". Available = holding x (I/1.7) x 0.70 (assumed low-speed factor). Margins at 1.5 A on DRV8825: " + ", ".join(f"{v['margins_design'][2]:.2f} ramp" for k, v in dt["drivers"].items() if "DRV8825, no" in k) + f" (acceptance 1.25). As built the governing case is {dt['as_built']['worst_case']} at {dt['as_built']['worst_margin']:.2f}; level floors pass (worst {dt['as_built']['level_worst_case']} at {dt['as_built']['level_worst_margin']:.2f}). The firmware runs 1/32 microstepping, up to 13,500 steps/s per wheel (530 mm/s) inside a 30 kHz step ISR, body-vector ramps of 0.6 m/s² up and 1.8 m/s² down, and a 400 ms watchdog. Traction at the 1.8 m/s² stops: " + ", ".join(f"{k} {v:.2f}" for k, v in dt["traction"].items()) + ".")
L.append("\n## Multimodal detection plan")
for x in p["fusion"]: L.append(f"- {x}")
L.append("\n## Electrical and interfaces as designed")
for m in p["mesh"]: L.append(f"- {m}")
L.append("\n## Power and connections")
for m in p["power"]: L.append(f"- {m}")
L.append("\n## Pin map")
for m in p["pins"]: L.append(f"- {m}")
L.append("\n## Open design question for you")
L.append("The radar sits at Z = 300 mm. Earlier measurements on the same LD2410C (project Walleye) found floor-level radar effectively blind through drywall and chest height reliable. Raising the printed post from 200 to 400 mm puts the radar at ~500 mm for about +50 g, which costs margin on the 5-degree ramp start that already governs (above) — irrelevant on flat floors, which is the scope. Should the post be 400 mm? Is there a better height or placement for a 24 GHz 1T1R module on a 350 x 390 mm rover, given the pan/tilt turret 270 mm ahead of it?")
L.append("\n## Already found and fixed — do not repeat these")
for r in p["review"]: L.append(f"- {r}")
L.append("\n## What I want from you")
L.append("1. Mechanical: walk every interface and say whether the two parts actually mate (bore vs shaft, bolt pattern vs holes, screw length vs stack, slot vs T-nut, print-bed fit). Flag anything nominal that could be wrong on the real part.\n2. Electrical: every connection — voltage windows, current budgets (Pi USB ports, the servo rail, the Pi's bank), logic levels, I2C addresses and bus speeds, grounds and ground loops, power-up order.\n3. Firmware: an Arduino UNO R4 WiFi (Renesas RA4M1, 48 MHz) already generates four independent step streams of up to 13,500 pulses/s each at 1/32 microstepping from a 30 kHz timer ISR, with body-vector ramps, a serial command link and a 400 ms watchdog, and drives the PCA9685 turret over I2C from the main loop. What in that is fragile (I2C blocking the loop, ISR jitter, EEPROM writes), and what would you test first?\n4. Sensor physics for DRYWALL: with a 24 GHz 1T1R LD2410C at 300 mm height reading per-gate energies, a 30 s dwell, and breathing extracted by autocorrelation in 0.13-0.60 Hz, what range and reliability should I expect through one layer of 12.7 mm drywall with a person standing, sitting, and lying? What will produce false positives in a normal building?\n5. Fusion: is the 0-3 scoring table sane? What weighting or veto rule would you add so a fan, a curtain, or a radiator does not become a 'person'?\n6. Build day: what is missing from the buy list and the owned list that I will discover I need?\n7. Rank the three most likely reasons this rover does not move on the first try, and the three most likely reasons it drives fine but reports no person through the drywall.\n8. Finally: list any fault you found that is NOT already in the 'Already found and fixed' section, in order of severity, one line each.")
wr = json.load(open("wiring.json")); ws = wr["summary"]; wc = ws["counts"]
L += ["", "## Wiring, checked by wiring.py (the netlist as code — treat it as the source of truth over the prose)",
      f"{ws['n_loads']} loads on six rails, {ws['n_wires']} wire segments, {ws['n_signals']} signal links; checks: voltage windows, rail current budgets, wire ampacity and drop, connector ratings, logic levels, pin uniqueness, I2C addresses, USB budget, bank→Pi→webcam voltage chain, ground-loop drops. Result: {wc['FAIL']} FAIL, {wc['WARN']} WARN, {wc['VERIFY']} VERIFY, {wc['PROCEDURE']} PROCEDURE, {wc['PASS']} PASS.",
      f"Pack {ws['pack_avg']} A avg / {ws['pack_peak']} A peak ({ws['minutes']} min per 2200 mAh pack); bank {ws['bank_avg']} / {ws['bank_peak']} A; Pi USB {ws['pi_usb_peak']} A of 1.2 A; Pi input {ws['v_pi']} V; webcam {ws['v_cam']} V worst case.",
      "Rails (from wiring.py): " + " ".join(f"{r['id']} {r['v_min']}–{r['v_max']} V ({r['desc']}) → " + (", ".join(l["name"].split(" (")[0] for l in wr["loads"] if l["rail"] == r["id"]) or "its downstream rails") + "." for r in wr["rails"]),
      "Non-PASS findings, all already folded into the design (please try to break them):"] + [f"- {k['level']}: {k['text']}" for k in wr["checks"] if k["level"] != "PASS"] + [
      "Same ask as above for this section: find what the checker cannot see — a wrong datasheet number, a connector gender, a rail I forgot, a ground path I mis-drew."]
open("CHATGPT-CHECK.md", "w").write("\n".join(L)); print(f"CHATGPT-CHECK.md: {len(L)} lines, {sum(len(x) for x in L)} chars")
