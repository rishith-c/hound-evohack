#!/usr/bin/env python3
"""
wiring_page.py — builds bom-site/wiring.html and bom-site/wiring/gpt-prompt.txt from wiring_diagrams.json (the net list the
diagrams were rendered from) and wiring.json (wiring.py's checks). Run after wiring_diagrams.py.
"""
import html
import json
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
D = json.load(open(os.path.join(ROOT, "wiring_diagrams.json")))
Wj = json.load(open(os.path.join(ROOT, "wiring.json")))
VP = json.load(open(os.path.join(ROOT, "verify_power.json")))
AM = json.load(open(os.path.join(ROOT, "bom-site", "wiring", "art-metrics.json")))
YML = {n: open(os.path.join(ROOT, "bom-site", "wiring", f"{n}.yml")).read() for n in D["diagrams"]}
import yaml
DOCS = {n: yaml.safe_load(YML[n]) for n in D["diagrams"]}

TITLES = {n: DOCS[n]["metadata"]["title"] for n in D["diagrams"]}
import re as _re
def inline_svg(path, prefix):
    """Inline an SVG sheet: strip the XML prolog, namespace its ids, point part artwork at wiring/parts/, size to the box."""
    t = open(path, encoding="utf-8").read()
    t = _re.sub(r"<\?xml[^>]*\?>\s*", "", t); t = _re.sub(r"<!DOCTYPE[^>]*>\s*", "", t)
    t = t.replace('href="parts/', 'href="wiring/parts/')
    t = _re.sub(r'\bid="([^"]+)"', lambda m: f'id="{prefix}-{m.group(1)}"', t)
    t = _re.sub(r'href="#([^"]+)"', lambda m: f'href="#{prefix}-{m.group(1)}"', t)
    t = _re.sub(r'url\(#([^)]+)\)', lambda m: f'url(#{prefix}-{m.group(1)})', t)
    t = _re.sub(r'<svg\b([^>]*?)\swidth="[^"]*"', r'<svg\1', t, count=1); t = _re.sub(r'<svg\b([^>]*?)\sheight="[^"]*"', r'<svg\1', t, count=1)
    t = t.replace("<svg", '<svg class="sheet" preserveAspectRatio="xMidYMid meet"', 1)
    return t
def viewer(svg_path, prefix, caption):
    return (f'<figure class="viewer"><div class="tools"><button data-z="in" title="zoom in">+</button><button data-z="out" title="zoom out">−</button>'
            f'<button data-z="reset" title="fit">fit</button><button data-z="full" title="full screen">⤢</button><span class="hint">drag to pan · wheel or pinch to zoom · double-click to fit</span></div>'
            f'<div class="vp">{inline_svg(svg_path, prefix)}</div><figcaption>{caption}</figcaption></figure>')
WD = os.path.join(ROOT, "bom-site", "wiring")
E = html.escape


def conn_rows(name):
    doc = DOCS[name]; rows = []
    for row in D["connections"][name]:
        (a, ap), (w, wi), (b, bp) = row[0], row[1], row[-1]
        cab = doc["cables"][w]; col = cab["colors"][int(wi) - 1]
        rows.append((a, ap, w, wi, col, cab["gauge"], b, bp))
    return rows


COL = {"RD": "red", "BK": "black", "YE": "yellow", "BU": "blue", "GN": "green", "WH": "white", "OG": "orange", "BN": "brown", "VT": "violet", "GY": "grey"}

# ── the GPT prompt, generated from the same data ─────────────────────────────────────────────────────────────
P = []
P.append("""You are an electronics documentation engineer. Produce the complete wiring diagram set for "Hound", an indoor search rover (Raspberry Pi 4 + Arduino UNO R4 WiFi + CNC Shield v3 + 4× DRV8825 + 4× NEMA 17 mecanum drive, 3S LiPo, ONE buck converter (XL4015 at 5.0 V) feeding a PCA9685 servo board that the R4 drives over the CNC shield's I2C pins (tilt servo ch 3, pan servo ch 2, fan on ch 15), an ESP32-S3 WiFi-CSI node on its own small power bank, MLX90640 thermal array, 2× VL53L1X ToF, INMP441 mic, 2× HLK-LD2410C radars on CP2102 USB-UART adapters, an HLK-LD2450 radar on the Pi's own UART, webcam).

HARD RULES — read before drawing anything
1. Use ONLY the connectors, pins and wires listed below. Every pin name is taken from a datasheet or the board silkscreen. Do not add, rename, merge or "helpfully" reroute anything. If something looks wrong, say so in a note; do not fix it silently.
2. Every wire is drawn with BOTH ends labelled "CONNECTOR:pin", its colour and its gauge, exactly as listed.
3. Colour the rails consistently: 11.1 V pack = red, 5.0 V servo rail (XL4015) = orange, 5.0 V logic rail = yellow, 3.3 V = violet, GND = black, signals = blue/green/white as listed.
4. Do NOT produce pin-level diagrams with an image generator: generated images get pin labels wrong. Produce them as code: a WireViz YAML file per diagram (https://github.com/wireviz/WireViz, `pip install wireviz`, needs Graphviz) rendered with Python, or hand-written SVG. An image generator may be used ONLY for a block-level overview picture with no pin text.
5. Six diagrams, landscape, one per section below, named exactly as the section headings. Each diagram gets a notes box with the section's NOTES.
6. Before you hand anything over, run the SELF-CHECK at the end and print its results.
""")
for n in D["diagrams"]:
    doc = DOCS[n]
    P.append(f"\n=== DIAGRAM {n}: {TITLES[n]} ===\n")
    P.append("CONNECTORS (pin order is the physical order on the part):")
    for cname, c in doc["connectors"].items():
        P.append(f"  {cname} — {c['type']}")
        P.append("     pins: " + " | ".join(str(p) for p in c["pinlabels"]))
        if c.get("notes"): P.append("     NOTES: " + c["notes"])
    P.append("WIRES:")
    for wname, w in doc["cables"].items():
        P.append(f"  {wname}: {w['gauge']}, {w['length']} m, conductors {', '.join(COL[c] for c in w['colors'])}" + (f" — {w['notes']}" if w.get("notes") else ""))
    P.append("CONNECTIONS (from → wire#/colour → to):")
    for a, ap, w, wi, col, g, b, bp in conn_rows(n):
        P.append(f"  {a}:{ap}  →  {w} #{wi} {COL[col]}  →  {b}:{bp}")

P.append("\n=== PROCEDURES AND WARNINGS (print these on the sheet; they come from the electrical model wiring.py) ===")
for c in Wj["checks"]:
    if c["level"] in ("PROCEDURE", "VERIFY", "WARN"):
        P.append(f"  [{c['level']}] {c['text']}")

P.append("""
=== DECISION ALREADY MADE: which bus drives the PCA9685 ===
The PCA9685 hangs on the CNC shield's SDA/SCL comms header (R4 A4/A5, 5 V I2C, VCC from the shield's 5V pin) and is driven by the R4 (firmware 't <deg>' for tilt; pan is a continuous-rotation servo driven only by 'n dir ms' eased timed nudges then pulse off, as in Ceres's turret_duet.ino; nothing is driven at boot). XL4015 OUT → its V+ terminal. Tilt servo on channel 3, pan on channel 2, fan on channel 15's V+/GND pins. It must never also touch the Pi's SDA/SCL. Draw sheet 3 exactly so.

=== SELF-CHECK (run it, print PASS/FAIL per line) ===
1. Every CONNECTOR:pin used in CONNECTIONS exists in that connector's pin list.
2. Each LD2410C has exactly ONE GND wire, to its own CP2102's GND, and its VCC from that adapter's +5V pin (never its 3V3 pin). The LD2450 has one GND wire, to Pi pin 34, and its 5V from Pi pin 4.
3. Pi pin 4 is the only header pin that carries 5 V (the LD2450's supply). Every signal pin used on the header — I2C, I2S, XSHUT and the UART pins 8/10 — is 3.3 V.
4. The MLX90640 and the two VL53L1X share I2C-1 (BCM 2/3). Addresses: 0x33, 0x29, 0x30 — no clash.
5. Motor bus: the Deans plug → SHIELD_PWR VMOT/GND, 14 AWG, with the 1000 µF cap noted, stripe to GND; the XL4015's 22 AWG input shares the same two screws.
6. XL4015 OUT− goes to the PCA9685's GND terminal; the buck's negative is common with the shield GND, so the R4's I2C and the servo rail share a reference.
7. The E-STOP is the Deans pull-plug on the deck, between the pack and the shield terminal; the Pi is on the USB bank, not on the pack.
8. There is no voltage divider: A3 stays free, so the firmware's low-voltage cut stays off (vcut 0).
9. ESP32-S3 no.3 is powered only through its USB-C, from its own small bank; nothing on the rover is wired to it.
10. The shield's four motor headers map X=BL, Y=FL, Z=BR, A=FR; each motor's coil pairs are found with a meter, colours are indicative only.
11. Power-up order is printed: bank → Pi → R4 (USB) → then the pack.
""")
PROMPT = "\n".join(P)
open(os.path.join(ROOT, "bom-site", "wiring", "gpt-prompt.txt"), "w").write(PROMPT)

# ── the page ─────────────────────────────────────────────────────────────────────────────────────────────────
CSS = """
body{margin:0;font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif;color:#1b2430;background:#f6f7f9}
main{max-width:1180px;margin:0 auto;padding:24px 16px 60px}
h1{font-size:28px;margin:0 0 6px}h2{font-size:20px;margin:36px 0 8px;border-bottom:2px solid #d8dde3;padding-bottom:4px}h3{font-size:16px;margin:18px 0 6px}
p,li{max-width:900px}.lead{font-size:17px;color:#3a4652}
.box{background:#fff;border:1px solid #d8dde3;border-radius:8px;padding:14px 16px;margin:12px 0}
.ok{border-left:5px solid #2f9e44}.warn{border-left:5px solid #e67700}.bad{border-left:5px solid #c92a2a}.alt{border-left:5px solid #7048e8}
figure{margin:12px 0;background:#fff;border:1px solid #d8dde3;border-radius:8px;padding:8px;overflow:auto}
figure img{display:block;width:100%;height:auto;min-width:900px}.two figure img{min-width:0}figcaption{font-size:13px;color:#5a6672;padding:6px 4px 0}
table{border-collapse:collapse;width:100%;font-size:13px;background:#fff}th,td{border:1px solid #d8dde3;padding:4px 6px;text-align:left;vertical-align:top}th{background:#eef1f4}
td.c{font-family:ui-monospace,Menlo,monospace;white-space:nowrap}.sw{display:inline-block;width:12px;height:12px;border:1px solid #888;vertical-align:middle;margin-right:4px}
pre{background:#101820;color:#e6ebf0;padding:14px;border-radius:8px;overflow:auto;font-size:12px;max-height:520px}
code{font-family:ui-monospace,Menlo,monospace;background:#e9edf1;padding:0 4px;border-radius:3px}
button{font:inherit;padding:8px 14px;border:1px solid #2a3641;border-radius:6px;background:#172029;color:#fff;cursor:pointer}
details summary{cursor:pointer;font-weight:600;margin:8px 0}
.two{display:grid;grid-template-columns:1fr 1fr;gap:12px}@media(max-width:800px){.two{grid-template-columns:1fr}}
.viewer{padding:0;overflow:hidden}.viewer .vp{height:72vh;min-height:420px;background:#fff;cursor:grab;touch-action:none;overflow:hidden;position:relative}.viewer .vp.drag{cursor:grabbing}
.viewer svg.sheet{width:100%;height:100%;display:block;user-select:none}.viewer .tools{display:flex;gap:6px;align-items:center;padding:6px 8px;background:#eef1f4;border-bottom:1px solid #d8dde3}
.viewer .tools button{padding:4px 10px;font-size:14px;line-height:1.2}.viewer .hint{font-size:12px;color:#5a6672;margin-left:8px}.viewer figcaption{padding:6px 10px 8px}
.viewer:fullscreen{background:#fff}.viewer:fullscreen .vp{height:calc(100vh - 80px)}
"""
SWATCH = {"RD": "#e03131", "BK": "#111", "YE": "#ffd43b", "BU": "#1c7ed6", "GN": "#2f9e44", "WH": "#fff", "OG": "#f76707", "BN": "#8b5a2b", "VT": "#7048e8", "GY": "#868e96"}

def table(name):
    r = ["<table><tr><th>from</th><th>wire</th><th>colour</th><th>gauge</th><th>to</th></tr>"]
    for a, ap, w, wi, col, g, b, bp in conn_rows(name):
        r.append(f"<tr><td class=c>{E(a)}:{E(str(ap))}</td><td class=c>{E(w)} #{wi}</td><td><span class=sw style='background:{SWATCH[col]}'></span>{COL[col]}</td><td>{E(g)}</td><td class=c>{E(b)}:{E(str(bp))}</td></tr>")
    return "".join(r) + "</table>"

def pins(name):
    r = []
    for cname, c in DOCS[name]["connectors"].items():
        r.append(f"<tr><td class=c>{E(cname)}</td><td>{E(c['type'])}</td><td class=c>{E(' | '.join(str(p) for p in c['pinlabels']))}</td><td>{E(c.get('notes',''))}</td></tr>")
    return "<table><tr><th>id</th><th>part</th><th>pins (physical order)</th><th>notes</th></tr>" + "".join(r) + "</table>"

procs = "".join(f"<li><b>{E(c['id'])}</b> — {E(c['text'])}</li>" for c in Wj["checks"] if c["level"] == "PROCEDURE")
verifs = "".join(f"<li><b>{E(c['id'])}</b> — {E(c['text'])}</li>" for c in Wj["checks"] if c["level"] in ("VERIFY", "WARN"))
S = Wj["summary"]; cnt = S["counts"]

figs = []
for n in D["diagrams"]:
    cls = " class=alt" if n.startswith("3b") else ""
    figs.append(f"""
<h3 id="{n}">{E(TITLES[n])}</h3>
{viewer(os.path.join(WD, f"{n}.svg"), f"w{n.replace('-', '')}", f'Harness sheet. Source: <a href="wiring/{n}.yml">{n}.yml</a> · <a href="wiring/{n}.png">PNG</a> · <a href="wiring/{n}.svg" download>SVG</a>')}
<details><summary>Connections ({len(D['connections'][n])} wires)</summary>{table(n)}</details>
<details><summary>Connector pin lists and notes</summary>{pins(n)}</details>""")

vp_rows = "".join(f"<tr><td>{E(c['name'])}</td><td class=c>{c['value']} {c['unit']}</td><td class=c>{'≥' if c['name'].startswith(('VMOT','XL4015 input','Pi input','LD2450','webcam','fan')) else '≤'} {c['limit']} {c['unit']}</td><td>{'PASS' if c['ok'] else 'FAIL'}</td></tr>" for c in VP["checks"])
am_rows = ", ".join(f"{k}: {v['wires']} wires, {v['crossings']} crossings, {v['overlaps']} overlaps" for k, v in AM.items())
poster_view = viewer(os.path.join(WD, "art-poster.svg"), "poster", 'Everything on one sheet, as built. <a href="wiring/art-poster-standalone.svg" download>Download the standalone SVG</a> (all artwork embedded) · <a href="wiring/art-poster.png">PNG</a>.')
art_figs = "".join(f'<h3 id="art-{n}">{E(TITLES[n])}</h3>' + viewer(os.path.join(WD, f"art-{n}.svg"), f"a{n.replace('-', '')}", f'{"ALTERNATIVE — not wired. " if n.startswith("3b") else ""}Vector sheet; <a href="wiring/art-{n}.png">PNG</a> · <a href="wiring/art-{n}.svg" download>SVG</a>.') for n in D["diagrams"])
page = f"""<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Hound wiring</title><style>{CSS}</style></head><body><main>
<h1>Hound — wiring</h1>
<p class=lead>Seven harness diagrams generated from one net list, rendered with <a href="https://github.com/wireviz/WireViz">WireViz</a> (open source, Python + Graphviz), and cross-checked by script against the electrical model <code>wiring.py</code>: every load is fed from the rail the model says, every signal link has a wire, the Pi and R4 pins match. The model itself: <b>{cnt['FAIL']} FAIL · {cnt['WARN']} WARN · {cnt['VERIFY']} VERIFY · {cnt['PROCEDURE']} PROCEDURE · {cnt['PASS']} PASS</b>; pack {S['pack_avg']} A avg / {S['pack_peak']} A peak, bank {S['bank_avg']} A avg / {S['bank_peak']} A peak, Pi USB {S['pi_usb_peak']} A of 1.2.</p>

<div class="box ok"><b>The PCA9685 goes on the CNC shield, not the Pi.</b> The shield's comms header breaks out the R4's A4/A5, its 5 V I2C bus, plus 5V and GND: four Dupont wires to the PCA9685's logic header. The XL4015 feeds the board's V+ terminal at 5.0 V; the tilt servo plugs onto channel 0, pan onto channel 2 (the Ceres order), and the fan takes 5 V from channel 15's V+/GND pins, so nothing on the servo side is soldered. The R4 drives the board (5 V PWM to the servos): tilt is positional, <code>t &lt;deg&gt;</code> 65–150 with Ceres's own 600 + 10 µs/° mapping; the Ceres pan servo is continuous-rotation and gets exactly what Ceres gave it, <code>n dir ms</code> = 1250 or 1750 µs for 300 ms then the pulse is cut (about 20° a nudge), and <code>p</code> stops it. The status reports <code>pca</code> = 1 when the board answers. Keep the PCA9685 off the Pi's SDA/SCL: its pull-ups sit at 5 V. One board fewer, no I2C wires between the Pi and the turret, and the thermal array moves onto the Pi's ordinary I2C bus with the ToFs, so the i2c3 overlay and its pull-up question disappear too.</div>

<div class=box><b>The power scheme, simplified (v3.1).</b> No lever nuts, no resistor boards, one buck. Pack → Deans pull-plug on the deck (that plug is the e-stop) → the CNC shield's VMOT/GND screw terminal with the 1000 µF cap. The same two screws take a second, thinner wire each to the XL4015 (set to <b>5.0 V</b>), whose output goes into the PCA9685's V+/GND terminal. The tilt servo sits on channel 0; the fan plugs onto channel 15's V+ and GND pins, because every channel header carries the rail. The Pi runs on its 3 A bank and powers the R4, the hub, the webcam and, through the CP2102 adapters' 5V pins, the three radars (four wires each). The ESP32-S3 CSI node has its own small bank. Thermal, ToF ×2, mic and the PCA9685 logic hang on the Pi's 3.3 V header. No pack voltage divider and no alarm: 30-minute timer, then meter the pack.</div>

<div class="box ok"><b>Walk around it in 3D:</b> <a href="rover3d/">rover3d/</a> — every part where the placement model puts it, every wire from this net list as a tube from pin to pin, real board artwork on the boards. Orbit, fly with W A S D, click a part to see its wires, unplug it, lift the whole deck.</div>
<h2>Illustrated (Fritzing style)</h2>
<p>The same net list drawn the way a Fritzing breadboard view looks: real part artwork from the open Fritzing libraries (<a href="https://github.com/fritzing/fritzing-parts">fritzing-parts</a>, <a href="https://github.com/adafruit/Fritzing-Library">Adafruit</a>, <a href="https://github.com/Protoneer/Fritzing_Parts">Protoneer's CNC Shield</a>, <a href="https://github.com/RafaGS/Fritzing">RafaGS's LD2410C</a>; CC-BY-SA), pin positions read from the parts' own connector definitions, wires routed by <code>wiring_art.py</code> from the net list. Parts no library has (the Deans plug, fan, hub, webcam, banks, LD2450, CP2102 sticks) are drawn by hand. Wires run in separated parallel tracks with square corners; the router never lets two wires overlap and reports the crossings it could not avoid. Stand-ins are labelled: the R4 is drawn as an Uno, both bucks as the LM2596 module, the ESP32-S3 as a C3 devkit, the INMP441 as Adafruit's I2S mic. Click any picture for full size.</p>
{poster_view}
{art_figs}

<h2>Harness sheets (WireViz)</h2>
<p>Left-to-right: source → wire (colour, gauge, length) → destination. Every pin name is the part's own silkscreen or datasheet name.</p>
{''.join(figs)}

<h2>Build procedures (from wiring.py)</h2><ul>{procs}</ul>
<h2>Verify before power (VERIFY / WARN)</h2><ul>{verifs}</ul>

<h2>Verification</h2>
<div class="box ok"><b>Electrical model (wiring.py):</b> {cnt['FAIL']} FAIL · {cnt['WARN']} WARN · {cnt['VERIFY']} VERIFY · {cnt['PROCEDURE']} PROCEDURE · {cnt['PASS']} PASS. Pack {S['pack_avg']} A avg / {S['pack_peak']} A peak → {S['minutes']} min per pack; bank {S['bank_avg']} A avg / {S['bank_peak']} A peak of 3.0; Pi USB {S['pi_usb_peak']} A of 1.2. <b>Diagrams vs model:</b> {'every load fed from the rail the model names, every signal link wired, Pi and R4 pin sets identical' if not D['problems'] else 'PROBLEMS: ' + '; '.join(D['problems'])}.</div>
<h3>DC simulation of the power tree at the worst instant (verify_power.py)</h3>
<p>Nodal solve with the pack at its 10.5 V floor, a 4 A motor burst, the servo stalled and every Pi-side load at peak at the same moment. Wire, connector and pack resistances from copper tables and datasheets.</p>
<table><tr><th>check</th><th>value</th><th>limit</th><th></th></tr>{vp_rows}</table>
<p>I2C: the MLX90640 breakout's own 10 kΩ pull-ups give a {VP['i2c3']['10000']['t_rise_ns']:.0f} ns rise on i2c3 → 100 kHz only; station.py runs the array at 4 fps, which 100 kHz supports. For 400 kHz (8 fps) add 4.7 kΩ; for 1 MHz 2.2 kΩ. I2C-1 (Pi 1.8 kΩ in parallel with three boards) rises in {VP['i2c1']['t_rise_ns']:.0f} ns → 400 kHz fine, {VP['i2c1']['i_sink_mA']:.1f} mA sink.</p>
<h3>Facts checked against sources</h3>
<ul>
<li>DRV8825 1/32 step = MODE0 high, MODE1 low, MODE2 high → caps on MS1 + MS3, as built. Current limit = 2 × Vref on Pololu-pattern carriers → 0.75 V = 1.5 A. Motor supply 8.2–45 V. <a href="https://www.pololu.com/product/2133">Pololu</a></li>
<li>Raspberry Pi 4: 1.2 A shared across the four USB ports; the docs allot 0.6 A to header loads out of a 3 A supply. <a href="https://support.thepihut.com/hc/en-us/articles/360015272218-How-much-current-can-I-draw-from-a-Raspberry-Pi-USB-port">Pi Hut</a>, <a href="https://github.com/raspberrypi/documentation/blob/master/documentation/asciidoc/computers/raspberry-pi/usb-bus-on-raspberry-pi.adoc">Pi docs</a></li>
<li>CP2102 adapters pass USB 5 V through their 5V pin (≤ 500 mA) and drive TX/RX at 3.3 V; 300 bps–1.5 Mbps covers 256000 baud. Their 3V3 pin is a small regulator output: it stays empty. <a href="https://www.kiwi-electronics.com/en/usb-to-ttl-serial-cable-cp2102-381">Kiwi Electronics</a></li>
<li>MG996R-class servos accept a 3.3 V PWM signal from a PCA9685 on a Pi; the signal line carries no power. <a href="https://forums.adafruit.com/viewtopic.php?t=202397">Adafruit forum</a>, <a href="https://componentindex.net/components/mg996r/">ComponentIndex</a></li>
<li>UNO R4 WiFi: A4/A5 are the primary I2C (Wire), 5 V logic; the Qwiic socket is Wire1 at 3.3 V. <a href="https://www.hackster.io/sensirion-software/two-separate-i2c-buses-on-arduino-uno-r4-ae55fc">Hackster</a>, <a href="https://docs.arduino.cc/tutorials/uno-r4-wifi/cheat-sheet">Arduino docs</a></li>
<li>HLK-LD2410C pins 1–5 = TX, RX, OUT, GND, VCC (5–12 V, 5 V advised), IO 3.3 V, 256000 baud. <a href="https://naylampmechatronics.com/img/cms/001080/HLK-LD2410C_datasheet.pdf">Hi-Link manual</a>. HLK-LD2450: 5V, GND, TX, RX; its 3.3 V UART goes straight onto the Pi's GPIO 14/15 (PL011 once Bluetooth is moved off it). <a href="https://www.espboards.dev/sensors/ld2450/">espboards</a></li>
</ul>
<h3>Functional checks run today</h3>
<ul>
<li>Drive firmware r4_drive (v1.0 drive + turret) compiles for the UNO R4 WiFi (88 kB, 33 % of flash); its drive code is unchanged since the v1.0-best-drive tag.</li>
<li>drivetrain.py verdict unchanged: four motors carry the 5.13 kg rover at DRV8825 1.5 A; the 5° ramp is the governing case.</li>
<li>The sensing sequencer runs end to end in simulation (station.py --sim) and produces its sentence.</li>
<li>The remote (drive, motor test, turret, pan trim, motion recorder) answered through the Cloudflare tunnel on 2026-09-24; its recorder was tested against a stub R4 before deploy.</li>
<li>Illustrated sheets: wires per sheet, and the crossings the router could not avoid (no two wires overlap): {am_rows}.</li>
</ul>
<div class="box warn"><b>Still to verify on the bench:</b> each I2C board powered alone must show ≤ 3.3 V on SDA; the tilt servo stops dead at a slider angle (it must be the 180° MG996R — a 360° one keeps turning); the pan's hold-still test (trim set once); the bank must hold ≥ 4.8 V at 2.5 A; the CP2102 adapters' silkscreen order (varies by vendor — wire by label, not position); which boards have a second header for chaining 3V3/SDA/SCL.</div>

<h2>Finish checklist</h2>
<ol>
<li><b>Set the buck.</b> Solder 22 AWG leads to the HiLetgo XL4015 pads. Feed IN+/IN− from the pack (nothing on OUT), meter OUT, turn the pot counter-clockwise until it reads 5.00 V. Unplug.</li>
<li><b>Set the four drivers.</b> Motors unplugged, R4 on USB, pack on. Meter black on the shield GND pin, red on each trimpot screw: 0.75 V. Caps under the drivers on MS1 and MS3 (1/32), D12/D13 jumpers on the A header.</li>
<li><b>Pack side.</b> Pack → Deans plug → shield VMOT/GND, 1000 µF across the terminal (stripe to GND). Twist the XL4015's 22 AWG input wires with the pack leads in the same two screws, tug-test. XL4015 OUT+/OUT− → the PCA9685's V+/GND terminal. Four Dupont wires from the shield's comms header (SDA, SCL, 5V, GND) to the PCA9685 logic header. Tilt servo onto channel 3, pan onto channel 2 (brown to the board edge), fan red/black onto channel 15's V+/GND pins.</li>
<li><b>Pi side.</b> Short 22 AWG cable bank → Pi USB-C. Webcam → Pi USB. Hub → Pi USB; R4 and the two CP2102 adapters into the hub. Each LD2410C: VCC → adapter +5V (not 3V3), GND → GND, TX → RXD, RX → TXD.</li>
<li><b>Pi header.</b> MLX90640 and both ToFs on SDA pin 3 / SCL pin 5, 3V3 from pins 1/17, XSHUT on 15 and 13. Mic on 12/35/38. LD2450: 5V → pin 4, GND → pin 34, its TX → pin 10, its RX → pin 8, then run <code>pi/enable_gpio_uart.sh</code> once. Chain 3V3, SDA and SCL through the boards' second headers or a mini breadboard: one female per Pi pin.</li>
<li><b>ESP32 no.3</b> on its own small bank, USB-C only, velcroed next to it. ESP32 no.2 on any charger off the rover.</li>
<li><b>Power-up order, every time:</b> bank → Pi → R4 (USB) → then the pack. Pack unplugged whenever the R4 is flashed or reset.</li>
<li><b>First light.</b> On the Pi: <code>i2cdetect -y 1</code> shows 0x33 and 0x29 (0x30 after the front ToF is re-addressed); <code>ls /dev/serial/by-id</code> lists the R4, <code>ls /dev/serial/by-path</code> the two adapters (by-id may show one: cheap CP2102s share a serial number), and <code>/dev/ttyAMA0</code> is the LD2450; the ESP32 joins the hotspot. The remote's status line shows the PCA9685 answering; the tilt slider moves the tilt servo and it stays put; hold the pan ◀ ▶ buttons to nudge the pan (it is continuous-rotation, so it has no angle), then run the hold-still test and trim until it does not creep.</li>
<li><b>Wheels up.</b> Open the remote, run "all four" in the motor test panel, then each wheel forward and back. Any motor pin that warms gets re-crimped.</li>
<li><b>On the floor.</b> Forward, back, strafes, rotate, crab circle from the remote at 415 mm/s.</li>
<li><b>First station.</b> <code>station.py --sim</code>, then a real station: stop, settle 5 s, listen 60 s, sweep, sentence.</li>
<li><b>Pack rule.</b> 30-minute timer from a full pack, then meter: stop at 11.1 V. Never charge a pack that reads under 9 V.</li>
</ol>

<h2>Open-source tools for this kind of diagram</h2>
<ul>
<li><a href="https://github.com/wireviz/WireViz">WireViz</a> — what this page uses: YAML in, harness diagram + BOM out; exact by construction. Needs Graphviz.</li>
<li><a href="https://fritzing.org/">Fritzing</a> — breadboard-style pictures of Arduino/Pi builds; good for a photo-like view, weak for pin-accurate harnesses.</li>
<li><a href="https://www.kicad.org/">KiCad</a> — full schematic capture; overkill for wiring, right if this ever becomes a PCB.</li>
<li><a href="https://schemdraw.readthedocs.io/">schemdraw</a> — Python schematic drawing, pure code, no Graphviz.</li>
</ul>

<h2>Or: the prompt for GPT</h2>
<p>Everything above, as one self-contained brief generated from the same net list (so it cannot drift from the diagrams). It tells GPT to produce WireViz YAML or SVG by code, not an image-generator picture, because generated images get pin text wrong. <a href="wiring/gpt-prompt.txt" download>Download gpt-prompt.txt</a> · <button onclick="navigator.clipboard.writeText(document.getElementById('pr').textContent).then(()=>this.textContent='copied')">copy prompt</button></p>
<pre id=pr>{E(PROMPT)}</pre>
</main>
<script>
document.querySelectorAll('.viewer').forEach(fig=>{{
 const vp=fig.querySelector('.vp'),svg=fig.querySelector('svg.sheet');if(!svg)return;
 const vb0=svg.getAttribute('viewBox').split(/[\\s,]+/).map(Number);let vb=vb0.slice();
 const apply=()=>svg.setAttribute('viewBox',vb.map(v=>v.toFixed(1)).join(' '));
 const pt=(cx,cy)=>{{const r=vp.getBoundingClientRect();const sx=vb[2]/r.width,sy=vb[3]/r.height,s=Math.max(sx,sy);
   const ox=(r.width-vb[2]/s)/2,oy=(r.height-vb[3]/s)/2;return [vb[0]+(cx-r.left-ox)*s,vb[1]+(cy-r.top-oy)*s,s];}};
 const zoomAt=(cx,cy,f)=>{{const [px,py]=pt(cx,cy);const w=Math.min(Math.max(vb[2]/f,vb0[2]/40),vb0[2]*4);const k=w/vb[2];
   vb=[px-(px-vb[0])*k,py-(py-vb[1])*k,w,vb[3]*k];apply();}};
 vp.addEventListener('wheel',e=>{{e.preventDefault();zoomAt(e.clientX,e.clientY,e.deltaY<0?1.15:1/1.15);}},{{passive:false}});
 let drag=null,pinch=null;
 vp.addEventListener('pointerdown',e=>{{vp.setPointerCapture(e.pointerId);drag={{x:e.clientX,y:e.clientY,vb:vb.slice()}};vp.classList.add('drag');}});
 vp.addEventListener('pointermove',e=>{{if(!drag||pinch)return;const s=pt(0,0)[2];vb[0]=drag.vb[0]-(e.clientX-drag.x)*s;vb[1]=drag.vb[1]-(e.clientY-drag.y)*s;apply();}});
 ['pointerup','pointercancel'].forEach(ev=>vp.addEventListener(ev,()=>{{drag=null;vp.classList.remove('drag');}}));
 vp.addEventListener('touchstart',e=>{{if(e.touches.length===2){{pinch={{d:Math.hypot(e.touches[0].clientX-e.touches[1].clientX,e.touches[0].clientY-e.touches[1].clientY)}};}}}},{{passive:true}});
 vp.addEventListener('touchmove',e=>{{if(pinch&&e.touches.length===2){{e.preventDefault();const d=Math.hypot(e.touches[0].clientX-e.touches[1].clientX,e.touches[0].clientY-e.touches[1].clientY);
   zoomAt((e.touches[0].clientX+e.touches[1].clientX)/2,(e.touches[0].clientY+e.touches[1].clientY)/2,d/pinch.d);pinch.d=d;}}}},{{passive:false}});
 vp.addEventListener('touchend',e=>{{if(e.touches.length<2)pinch=null;}});
 vp.addEventListener('dblclick',()=>{{vb=vb0.slice();apply();}});
 fig.querySelectorAll('.tools button').forEach(b=>b.addEventListener('click',()=>{{const r=vp.getBoundingClientRect();const cx=r.left+r.width/2,cy=r.top+r.height/2;
   if(b.dataset.z==='in')zoomAt(cx,cy,1.3);else if(b.dataset.z==='out')zoomAt(cx,cy,1/1.3);else if(b.dataset.z==='reset'){{vb=vb0.slice();apply();}}
   else if(b.dataset.z==='full'){{document.fullscreenElement?document.exitFullscreen():fig.requestFullscreen();}}}}));
}});
</script></body></html>"""
open(os.path.join(ROOT, "bom-site", "wiring.html"), "w").write(page)
print(f"wiring.html ({len(page)//1024} kB) and gpt-prompt.txt ({len(PROMPT)//1024} kB) written")
