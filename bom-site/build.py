#!/usr/bin/env python3
"""Build the BOM site: one list of everything on the rover, each part tied to
its computed position, plus the full placement table.

Reads bom.json (items + prose), ../assembly.json (positions and fasteners from
assembly.py) and ../drivetrain.json (margins from drivetrain.py). Writes
index.html, bom.csv, and copies assembly.csv alongside. Style is the original
ChatGPT-authored page (dpl_7Uxg94gpHed7fCG2Yc6mctUCd4LA), kept verbatim.

    python3 build.py
"""

import csv
import html
import json
import shutil
from collections import OrderedDict

BOM = json.load(open("bom.json"))
ASM = json.load(open("../assembly.json"))
DT = json.load(open("../drivetrain.json"))
WR = json.load(open("../wiring.json"))
meta, prose, items = BOM["meta"], BOM["prose"], BOM["items"]
shutil.copy("../assembly.csv", "assembly.csv")

placed = {}
for p in ASM["parts"]:
    placed.setdefault(p["id"], []).append(p)

def esc(x):
    return html.escape(str(x))

def money(x):
    return f"${x:.2f}"

def line_total(it):
    return it["qty"] * it["price"] if it["status"] != "owned" else 0.0

def where(it):
    ps = [p for p in placed.get(it["id"], []) if p["l"] or p["id"] == "WIRE22"]
    if not ps:
        return "—"
    cells = [f'{p["instance"]} ({p["x"]:+.0f}, {p["y"]:+.0f}, {p["z"]:.0f})' if p["instance"] != "—"
             else f'({p["x"]:+.0f}, {p["y"]:+.0f}, {p["z"]:.0f})' for p in ps[:4]]
    more = f" +{len(ps)-4} more" if len(ps) > 4 else ""
    return "; ".join(cells) + more

def fastening(it):
    ps = placed.get(it["id"], [])
    fs = OrderedDict((p["fasteners"], None) for p in ps if p["fasteners"] not in ("—", ""))
    return "; ".join(list(fs)[:2]) if fs else "—"

buy_total = sum(line_total(i) for i in items if i["status"] == "buy")
opt_total = sum(line_total(i) for i in items if i["status"] == "optional")
owned_n = sum(1 for i in items if i["status"] == "owned")
buy_n = sum(1 for i in items if i["status"] == "buy")
opt_groups = OrderedDict()
for i in items:
    if i["status"] == "optional":
        g = opt_groups.setdefault(i["group"], [0, 0.0]); g[0] += 1; g[1] += line_total(i)
grand_total = buy_total + opt_total

# ── CSV ─────────────────────────────────────────────────────────────────────
with open("bom.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["group", "status", "id", "item", "qty", "each_usd", "line_usd", "asin", "url", "where_xyz_mm", "fastening", "note"])
    for it in items:
        w.writerow([it["group"], it["status"], it["id"], it["item"], it["qty"],
                    f'{it.get("price", 0):.2f}' if it["status"] != "owned" else "",
                    f'{line_total(it):.2f}' if it["status"] != "owned" else "",
                    it.get("asin", ""), f'https://www.amazon.com/dp/{it["asin"]}' if it.get("asin") and it["asin"] != "TBD" else "",
                    where(it), fastening(it), it.get("note", "")])

# ── The one big list ────────────────────────────────────────────────────────
rows = []
for it in items:
    owned = it["status"] == "owned"
    name = (f'<a target="_blank" rel="noopener noreferrer" href="https://www.amazon.com/dp/{esc(it["asin"])}">{esc(it["item"])}</a>'
            if it.get("asin") and it["asin"] != "TBD" else esc(it["item"]))
    if it.get("asin") == "TBD":
        name += ' <em>(listing to confirm)</em>'
    note = f'<div class="note">{esc(it["note"])}</div>' if it.get("note") else ""
    grp = f'<div class="grp">{esc(it["group"])}</div>'
    each = "owned" if owned else money(it["price"])
    line = "owned" if owned else money(line_total(it))
    tag = ' <span class="tag">optional</span>' if it["status"] == "optional" else ""
    rows.append(
        f'<tr{" class=owned" if owned else ""}>\n'
        f'<td class="have-cell"><input type="checkbox" data-item="{esc(it["id"])}" data-owned="{int(owned)}" '
        f'aria-label="I have all required quantities of {esc(it["item"])}"></td>'
        f'<td>{name}{tag}{grp}{note}</td>\n'
        f'<td align="right">{esc(it["qty"])}</td>\n<td align="right">{each}</td>\n<td align="right">{line}</td>\n'
        f'<td class="where">{esc(where(it))}</td>\n<td class="where">{esc(fastening(it))}</td>\n</tr>')

big_table = f"""<div class="table-wrap"><table>
<thead>
<tr>
<th class="have-cell" scope="col">I have this</th><th>Item / exact Amazon listing</th>
<th align="right">Qty</th>
<th align="right">Each</th>
<th align="right">Line</th>
<th>Where it goes (x, y, z mm)</th>
<th>Fastening</th>
</tr>
</thead>
<tbody>
{"".join(rows)}
<tr><th colspan="4">Buy</th><th align="right">{money(buy_total)}</th><th colspan="2">Optional {money(opt_total)} · {owned_n} items already owned</th></tr>
</tbody></table></div>"""

# ── Placement table ─────────────────────────────────────────────────────────
asm_rows = "".join(
    f'<tr>\n<td><code>{esc(p["id"])}</code></td><td>{esc(p["instance"])}</td><td>{esc(p["part"])}</td>'
    f'<td align="right">{p["x"]:+.1f}</td><td align="right">{p["y"]:+.1f}</td><td align="right">{p["z"]:.1f}</td>'
    f'<td>{esc(p["orientation"])}</td><td>{esc(p["mounts_to"])}</td><td>{esc(p["fasteners"])}</td>'
    f'<td>{esc(p["torque"])}</td><td>{esc(p["verify"]) or "—"}</td>\n</tr>\n'
    for p in ASM["parts"])
fr = ASM["frame"]
asm_summary = (f'Origin at the chassis centre on the floor; +X forward, +Y rover left, +Z up; all positions are part centres. '
               f'Envelope {fr["envelope"][0]} × {fr["envelope"][1]} × {fr["envelope"][2]} mm, track {fr["track"]:.0f} mm, wheelbase {fr["wheelbase"]:.0f} mm. '
               f'Centre of gravity at x {fr["cg"][0]:+.1f}, y {fr["cg"][1]:+.1f}, z {fr["cg"][2]:.1f} mm — the battery under the deck is what keeps it that low. '
               f'Ground clearance {fr["ground_clearance"]:.1f} mm (motor bodies). Static tip angles {fr["tip_pitch_deg"]}° pitch, {fr["tip_roll_deg"]}° roll. '
               f'{"No" if not fr["collisions"] else len(fr["collisions"])} bounding-box collisions between rigid parts. '
               f'Every dimension marked VERIFY is nominal for its class of part and must be measured with a caliper before a hole is drilled.')

# ── Torque table ────────────────────────────────────────────────────────────
m_rows = "".join(
    f'<tr>\n<td>{esc(k)}</td><td align="right">{v["t_avail_Nm"]:.3f} N·m</td>'
    f'<td align="right">{v["margins_firmware"]["E"]:.2f}</td><td align="right">{v["margins_firmware"]["F"]:.2f}</td>'
    f'<td align="right">{v["margins_firmware"]["G"]:.2f}</td><td align="right">{min(v["margins_firmware"][c] for c in "HIJ"):.2f}</td>'
    f'<td>{"PASS" if v["pass"] else ("FAIL " + ", ".join(n for n, c in (("level", "E"), ("strafe", "F"), ("ramp", "G")) if v["margins_firmware"][c] < DT["margin_required"])).strip()}</td>\n</tr>\n'
    for k, v in DT["drivers"].items())

def paras(lines):
    return "\n".join(f"<p>{esc(p)}</p>" for p in lines)

def bullets(lines):
    return "<ul>\n" + "\n".join(f"<li>{esc(p)}</li>" for p in lines) + "\n</ul>"

def numbered(lines):
    return "<ol>\n" + "\n".join(f"<li>{esc(p)}</li>" for p in lines) + "\n</ol>"


# ── Wiring tables (from wiring.py) ──────────────────────────────────────────
_ws = WR["summary"]; _c = _ws["counts"]
fmt = lambda v, p: "" if v is None else f"{v:.{p}f}"
wiring_intro = (f'wiring.py is the netlist as code: {_ws["n_loads"]} loads on six rails, {_ws["n_wires"]} wire segments and {_ws["n_signals"]} signal links, '
                f'checked for voltage windows, current budgets, wire ampacity and drop, connector ratings, logic levels, pin conflicts, I2C addresses, USB budget, '
                f'the voltage chain from the bank to the webcam, and ground-loop drops. Result: {_c["FAIL"]} FAIL, {_c["WARN"]} WARN, {_c["VERIFY"]} VERIFY, '
                f'{_c["PROCEDURE"]} PROCEDURE, {_c["PASS"]} PASS. Pack draw {_ws["pack_avg"]} A average, {_ws["pack_peak"]} A peak ({_ws["minutes"]} min per 2200 mAh pack); '
                f'bank {_ws["bank_avg"]} A average, {_ws["bank_peak"]} A peak; Pi USB {_ws["pi_usb_peak"]} A of 1.2 A peak; Pi input {_ws["v_pi"]} V and webcam {_ws["v_cam"]} V worst case. '
                f'The pin map and power sections above were corrected to match this file; where they disagree, this table wins.')
wiring_checks = "".join(f'<tr><td class="lvl-{esc(c["level"])}">{esc(c["level"])}</td><td><code>{esc(c["id"])}</code></td><td>{esc(c["text"])}</td></tr>\n' for c in WR["checks"])
wiring_wires = "".join(f'<tr><td>{esc(w["name"])}</td><td align="right">{w["awg"]}</td><td align="right">{w["length_m"]:.2f}</td><td align="right">{fmt(w["i_avg"], 2)}</td><td align="right">{fmt(w["i_peak"], 2)}</td><td>{esc(w["connector"])}</td></tr>\n' for w in WR["wires"])
wiring_loads = "".join(f'<tr><td>{esc(l["name"])}</td><td><code>{esc(l["rail"])}</code></td><td align="right">{l["vin"][0]}–{l["vin"][1]} V</td><td align="right">{fmt(l["i_avg"], 3)}</td><td align="right">{fmt(l["i_peak"], 2)}</td><td class="note">{esc(l["source"])}</td></tr>\n' for l in WR["loads"])
wiring_html = f"""<h2>Wiring, checked</h2>
<p>{esc(wiring_intro)}</p>
<div class="table-wrap"><table><thead><tr><th>Level</th><th>Check</th><th>Finding</th></tr></thead><tbody>
{wiring_checks}</tbody></table></div>
<p>Every wire segment, with the current it actually carries:</p>
<div class="table-wrap"><table><thead><tr><th>Segment</th><th align="right">AWG</th><th align="right">m</th><th align="right">A avg</th><th align="right">A peak</th><th>Ends in</th></tr></thead><tbody>
{wiring_wires}</tbody></table></div>
<p>Every load, the rail it hangs on, and where its numbers come from:</p>
<div class="table-wrap"><table><thead><tr><th>Load</th><th>Rail</th><th align="right">Accepts</th><th align="right">A avg</th><th align="right">A peak</th><th>Source</th></tr></thead><tbody>
{wiring_loads}</tbody></table></div>
"""

page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Hound BOM</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#fff;color:#202124;font:16px/1.65 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}main{{max-width:1180px;margin:48px auto;padding:0 24px 60px}}h1{{font-size:30px;line-height:1.25}}h2{{font-size:22px;margin-top:36px}}a{{color:#165bc4;text-underline-offset:3px}}table{{border-collapse:collapse;width:100%;font-size:14px;margin:20px 0}}th,td{{padding:10px 12px;border:1px solid #ddd;text-align:left;vertical-align:top}}th{{background:#f5f6f7}}code{{background:#f3f4f5;padding:2px 4px;border-radius:3px}}.table-wrap{{overflow-x:auto}}p{{margin:16px 0}}ol li,ul li{{margin:6px 0}}.note{{font-size:13px;color:#555;margin-top:4px}}.where{{font-size:13px;white-space:nowrap}}td.where{{white-space:normal;min-width:180px}}tr.group th{{background:#e9ecef;font-weight:600}}.tag{{font-size:12px;color:#555;border:1px solid #ccc;border-radius:3px;padding:0 5px;margin-left:6px}}.grp{{font-size:12px;color:#777;margin-top:2px;text-transform:uppercase;letter-spacing:.03em}}table.totals{{font-size:16px}}table.totals tr.big td{{font-size:20px;padding:14px 12px;background:#f5f6f7}}em{{color:#8a4b00;font-style:normal;font-size:13px}}@media(max-width:600px){{main{{margin:28px auto;padding:0 16px 36px}}h1{{font-size:26px}}table{{min-width:620px}}}}@media print{{main{{max-width:none;margin:0;padding:0}}a{{color:inherit}}}}
.lvl-FAIL{{color:#b00020;font-weight:600}}.lvl-WARN{{color:#8a4b00;font-weight:600}}.lvl-VERIFY{{color:#1a5fb4;font-weight:600}}.lvl-PROCEDURE{{color:#333;font-weight:600}}.lvl-PASS{{color:#2a7a2a}}
input[type="checkbox"]{{width:20px;height:20px;accent-color:#165bc4;cursor:pointer}}.have-cell{{text-align:center;white-space:nowrap}}tr.owned td{{background:#eff8f0}}#checklist-note{{font-size:14px;color:#555}}
</style></head><body><main><h1>{esc(meta["title"])}</h1>
<p class="note"><a href="manual.html">Assembly manual</a> · <a href="wiring.html">Wiring diagrams</a> · <a href="rover3d/">3D rover</a> · <a href="sensing/report.html">Sensing simulation</a> · <a href="sensing/RESEARCH.md">Prior art</a> · <a href="CHATGPT-CHECK.md">Verification prompt</a> · <a href="bom.csv">bom.csv</a> · <a href="assembly.csv">assembly.csv</a></p>
<p><strong>Buy: {money(buy_total)} USD before tax/shipping. Optional (battery ecosystem, extra senses, tools): {money(opt_total)}. Already owned: {owned_n} items.</strong> {esc(meta["intro"])}</p>
<p><a href="bom.csv" download>Download the BOM as CSV</a> · <a href="assembly.csv" download>Download every placement as CSV</a> · <a href="drivetrain.txt">Read the full drivetrain calculation</a></p>
<h2>The design I would build</h2>
{paras(prose["design"])}
<h2>Can four motors carry it?</h2>
<p>Design mass {DT["design_mass_kg"]:.2f} kg. Ten load cases, including the firmware's own ramps — every start at 0.6 m/s², every stop at 1.8 m/s² — with margins against a 1.25 screening factor. As built ({esc(DT["as_built"]["setting"])}, 1.5 A) every level-floor case passes, worst {DT["as_built"]["level_worst_margin"]:.2f} (a strafe start); a start up a 5° carpet ramp governs at {DT["as_built"]["worst_margin"]:.2f}. {("Lowest passing setting: <strong>" + esc(DT["governing_setting"]) + "</strong>.") if DT["governing_setting"] else "No current setting passes the ramp case at this mass — and most of the mass is allocated, not weighed, so weighing the rover is the next step."} Traction at the 1.8 m/s² stops is in <a href="drivetrain.txt">drivetrain.txt</a>.</p>
<div class="table-wrap"><table>
<thead>
<tr>
<th>Driver / current setting</th>
<th align="right">Torque available</th>
<th align="right">Level start</th>
<th align="right">Strafe start</th>
<th align="right">5° ramp start</th>
<th align="right">Stops</th>
<th>Verdict</th>
</tr>
</thead>
<tbody>
{m_rows}</tbody></table></div>
<p>{esc(meta["margin_note"])}</p>
<h2>Buy list — everything on the rover</h2>
<p id="checklist-note" role="status">Selections are saved in this browser only.</p>
<p>Owned items start ticked. Tick a bought item when you have the full listed quantity. Positions are part centres in millimetres from the chassis centre on the floor (+X forward, +Y left, +Z up); the full table with orientation and torque is below.</p>
{big_table}
<h2>Where every part goes</h2>
<p>{asm_summary}</p>
<div class="table-wrap"><table>
<thead>
<tr>
<th>ID</th><th>Instance</th><th>Part</th><th align="right">x</th><th align="right">y</th><th align="right">z</th><th>Orientation</th><th>Mounts to</th><th>Fasteners</th><th>Torque</th><th>Verify on receipt</th>
</tr>
</thead>
<tbody>
{asm_rows}</tbody></table></div>
<h2>Power and connections</h2>
{bullets(prose["power"])}
{paras(prose["power_after"])}
{wiring_html}
<h2>Motor and frame fit</h2>
{paras(prose["fit"])}
<h2>Compute before claiming it works</h2>
{paras(prose["compute"])}
<h2>Multimodal detection — four physics, one answer</h2>
{paras(prose["fusion"])}
<h2>Does it all mesh? Every interface, checked</h2>
{bullets(prose["mesh"])}
<h2>Pin map</h2>
{bullets(prose["pins"])}
<h2>Build order</h2>
{numbered(prose["build"])}
<h2>Caught in review</h2>
<p>Mistakes found and fixed while checking this design, kept here so the reasoning survives.</p>
{bullets(prose["review"])}
<h2>Total cost</h2>
<div class="table-wrap"><table class="totals">
<thead>
<tr><th>What</th><th align="right">Lines</th><th align="right">Cost</th></tr>
</thead>
<tbody>
<tr class="big"><td><strong>Required — the rover does not work without these</strong></td><td align="right">{buy_n}</td><td align="right"><strong>{money(buy_total)}</strong></td></tr>
{"".join(f'<tr><td>Optional: {esc(g)}</td><td align="right">{n}</td><td align="right">{money(t)}</td></tr>' for g, (n, t) in opt_groups.items())}
<tr><td>All optional together</td><td align="right">{sum(n for n, _ in opt_groups.values())}</td><td align="right">{money(opt_total)}</td></tr>
<tr><td>Already owned</td><td align="right">{owned_n}</td><td align="right">$0.00</td></tr>
<tr class="big"><td><strong>Everything, if you buy it all</strong></td><td align="right">{buy_n + sum(n for n, _ in opt_groups.values())}</td><td align="right"><strong>{money(grand_total)}</strong></td></tr>
</tbody></table></div>
<p>Before tax and shipping, Amazon US prices observed {esc(meta["price_date"])}. The required figure assumes your gel-blaster pack, its charger, your webcam, the UNO R4, the Ceres turret and the 22 AWG wire all check out. If the pack is the first thing that fails, add the battery group: {money(buy_total + opt_groups.get("Only if the gel-blaster pack falls short", [0, 0.0])[1])}.</p>
<h2>What I did NOT analyze</h2>
<p>{esc(meta["not_analysed"])}</p>
<p>Sources: <a target="_blank" rel="noopener noreferrer" href="https://static.jkongmotor.com/JK42HS40-1704-13A-aidlnBprKrkloSRilikkrllkn.pdf">motor drawing</a>, <a target="_blank" rel="noopener noreferrer" href="https://www.pololu.com/product/2133">DRV8825 current/cooling</a>, <a target="_blank" rel="noopener noreferrer" href="https://www.pololu.com/product/1182">A4988 current/cooling</a>, <a target="_blank" rel="noopener noreferrer" href="https://www.hlktech.com/en/Goods-239.html">LD2410C manufacturer</a>, <a target="_blank" rel="noopener noreferrer" href="https://www.skyrc.com/download/100200%20B6ACneo%20Instruction%20Manual%20V1.3.pdf">SKYRC B6AC Neo manual</a>, <a href="drivetrain.txt">drivetrain.txt</a> and <a href="assembly.csv">assembly.csv</a> (all arithmetic and positions).</p>
</main><script>
const note = document.getElementById('checklist-note');
const prefix = 'rover-bom-owned-v3:';
for (const checkbox of document.querySelectorAll('input[data-item]')) {{
  const key = prefix + checkbox.dataset.item;
  const paint = () => checkbox.closest('tr').classList.toggle('owned', checkbox.checked);
  try {{ const s = localStorage.getItem(key); checkbox.checked = s === null ? checkbox.dataset.owned === '1' : s === 'true'; }}
  catch {{ checkbox.checked = checkbox.dataset.owned === '1'; note.textContent = 'Browser storage is unavailable; selections will last only until this page closes.'; }}
  paint();
  checkbox.addEventListener('change', () => {{
    paint();
    try {{ localStorage.setItem(key, String(checkbox.checked)); }}
    catch {{ note.textContent = 'Selections could not be saved in this browser. Keep this page open to retain them.'; }}
  }});
}}
</script></body></html>
"""
open("index.html", "w").write(page)
print(f"index.html, bom.csv, assembly.csv written — buy {money(buy_total)}, optional {money(opt_total)}, {owned_n} owned, {len(ASM['parts'])} placements")
