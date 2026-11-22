#!/usr/bin/env python3
"""report.py — results.json → report.html (self-contained; inline SVG charts). Run after sim.py."""
import html
import json
import os

HERE = os.path.dirname(__file__)
R = json.load(open(os.path.join(HERE, "results.json")))
esc = html.escape
LABELS = ["PERSON VISIBLE", "RF CORROBORATED", "BREATHING-LIKE PERIODICITY", "RF ACTIVITY", "MACHINE-LIKE PERIODICITY", "NOTHING"]
COL = {"PERSON VISIBLE": "#2f7d4f", "RF CORROBORATED": "#2e5c8a", "BREATHING-LIKE PERIODICITY": "#7fb0e0",
       "RF ACTIVITY": "#c9c17a", "MACHINE-LIKE PERIODICITY": "#c9430a", "NOTHING": "#d5dce3"}


def stacked(scen: dict) -> str:
    rows = []
    y = 0
    for name, d in scen.items():
        x = 0; segs = []
        for L in LABELS:
            f = d["labels"].get(L, 0)
            if f:
                segs.append(f'<rect x="{x*520:.1f}" y="{y*26+4}" width="{f*520:.1f}" height="18" fill="{COL[L]}"><title>{esc(L)} {f:.0%}</title></rect>')
                x += f
        truth = "●" if d["truth"] == "person" else "○"
        rows.append(f'<text x="-8" y="{y*26+17}" text-anchor="end" font-size="12" fill="var(--ink)">{truth} {esc(name)}</text>' + "".join(segs)
                    + f'<text x="528" y="{y*26+17}" font-size="12" fill="var(--muted)">{d["person_reported"]:.0%}</text>')
        y += 1
    h = y * 26 + 8
    legend = "".join(f'<rect x="{i*150}" y="{h+6}" width="12" height="12" fill="{COL[L]}"/><text x="{i*150+16}" y="{h+17}" font-size="11" fill="var(--ink)">{esc(L.title())}</text>' for i, L in enumerate(LABELS[:4]))
    legend += "".join(f'<rect x="{(i)*150}" y="{h+26}" width="12" height="12" fill="{COL[L]}"/><text x="{(i)*150+16}" y="{h+37}" font-size="11" fill="var(--ink)">{esc(L.title())}</text>' for i, L in enumerate(LABELS[4:]))
    return f'<svg viewBox="-230 0 800 {h+46}" width="100%" style="max-width:820px;font-family:system-ui">' + "".join(rows) + f'<g>{legend}</g></svg>'


def roc(roc: dict) -> str:
    mnrs = [0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0]
    W, H = 520, 220
    xs = lambda m: 40 + (m / 6.0) * (W - 60)
    ys = lambda p: H - 30 - p * (H - 50)
    out = [f'<line x1="40" y1="{H-30}" x2="{W-20}" y2="{H-30}" stroke="var(--muted)"/><line x1="40" y1="20" x2="40" y2="{H-30}" stroke="var(--muted)"/>']
    for p in (0, 0.5, 1.0):
        out.append(f'<text x="34" y="{ys(p)+4}" text-anchor="end" font-size="11" fill="var(--muted)">{p:.0%}</text><line x1="40" y1="{ys(p)}" x2="{W-20}" y2="{ys(p)}" stroke="var(--line)" stroke-dasharray="3 3"/>')
    for m in mnrs:
        out.append(f'<text x="{xs(m)}" y="{H-14}" text-anchor="middle" font-size="11" fill="var(--muted)">{m}</text>')
    for dwell, colr in (("30", "#2e5c8a"), ("45", "#7fb0e0")):
        pts = " ".join(f"{xs(m):.1f},{ys(roc[dwell][str(m)]):.1f}" for m in mnrs)
        out.append(f'<polyline points="{pts}" fill="none" stroke="{colr}" stroke-width="2.5"/>')
        out.append(f'<text x="{xs(6.0)+4}" y="{ys(roc[dwell]["6.0"])+4}" font-size="11" fill="{colr}">{dwell} s</text>')
    out.append(f'<text x="{W/2}" y="{H-1}" text-anchor="middle" font-size="11" fill="var(--ink)">modulation-to-noise ratio of the gate energy</text>')
    return f'<svg viewBox="0 0 {W} {H}" width="100%" style="max-width:560px;font-family:system-ui">' + "".join(out) + "</svg>"


def table(headers, rows):
    return "<table><thead><tr>" + "".join(f"<th>{esc(h)}</th>" for h in headers) + "</tr></thead><tbody>" + "".join("<tr>" + "".join(f"<td>{esc(str(c))}</td>" for c in r) + "</tr>" for r in rows) + "</tbody></table>"


S = R["summary"]; fan = R["fan_discrimination"]; th = R["thermal_vs_range"]; m = R["mission"]
LOC = json.load(open(os.path.join(HERE, "localize_results.json")))
FR = json.load(open(os.path.join(HERE, "fresnel_results.json")))
page = f"""<title>Hound Sensing Simulation</title>
<style>
:root{{--ground:#F4F6F8;--surface:#fff;--ink:#17212B;--muted:#5B6B7A;--line:#D5DCE3;--accent:#2E5C8A}}
@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{--ground:#0F151B;--surface:#172029;--ink:#E6EBF0;--muted:#93A1AE;--line:#2A3641;--accent:#7FB0E0}}}}
:root[data-theme="dark"]{{--ground:#0F151B;--surface:#172029;--ink:#E6EBF0;--muted:#93A1AE;--line:#2A3641;--accent:#7FB0E0}}
body{{margin:0;background:var(--ground);color:var(--ink);font:16px/1.55 "Source Sans 3",system-ui,sans-serif}}main{{max-width:900px;margin:0 auto;padding:28px 20px 60px}}
h1{{font-size:30px;margin:0 0 4px}}h2{{font-size:20px;margin:32px 0 8px;border-bottom:1px solid var(--line);padding-bottom:4px}}p{{max-width:72ch}}
table{{border-collapse:collapse;font-size:14px;margin:10px 0}}th,td{{border:1px solid var(--line);padding:5px 9px;text-align:left}}th{{background:var(--surface)}}
.kpi{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:14px 0}}.kpi div{{background:var(--surface);border:1px solid var(--line);border-radius:6px;padding:10px 12px}}.kpi b{{display:block;font-size:26px;font-variant-numeric:tabular-nums}}.kpi span{{color:var(--muted);font-size:13px}}
.sub{{color:var(--muted)}}.warn{{border-left:4px solid #c9430a;padding:8px 12px;background:var(--surface)}}
</style>
<main>
<h1>Hound Sensing Simulation</h1>
<p class="sub">{R['n_per_scenario']} stations per scenario, calibrated on a separate set of the same size. Sensor models in models.py; every number tagged datasheet, paper, bench or allocated.</p>
<div class="kpi"><div><b>{S['false_alarm_rate_no_person']:.1%}</b><span>person reported with nobody there</span></div>
<div><b>{S['detection_visible']:.0%}</b><span>person found when visible</span></div>
<div><b>{S['detection_behind_drywall']:.0%}</b><span>person found behind drywall (2–4 m, allocated radar range law)</span></div></div>

<h2>What each station says, by scenario</h2>
<p>● a person is present · ○ nobody. Right-hand figure: how often a person is reported (the three strongest labels).</p>
{stacked(R['scenarios'])}
<p class="warn">The behind-wall numbers rest on one allocated quantity: how much the LD2410C's gate energy modulates with breathing at range, through a two-sided stud partition. The chart below turns that into a requirement the bench test can check.</p>

<h2>The breathing detector needs a modulation-to-noise ratio of about 3</h2>
<p>Probability that one window is classed breathing-like with confidence ≥ 5, versus the modulation amplitude in units of the noise floor. Below 1 it cannot see it; from 1.5 it works half the time; from 3 it works four times in five. A 15 s window never qualifies (200-sample minimum), which fixes the dwell at 30 s minimum. Empty-room false alarms in this sweep: {R['breathing_roc']['30']['false_alarm_empty']:.0%}.</p>
{roc(R['breathing_roc'])}
<p><b>Acceptance test for the radar height bench session:</b> measured swing of the best gate's static energy over 30 s, divided by its standard deviation in an empty room, at the intended station distance through a real partition. ≥ 3 passes. Between 1.5 and 3, stations move closer or repeat from a second angle. Below 1.5 the through-wall claim is withdrawn for that distance.</p>

<h2>A fan is more regular than a person</h2>
<p>Breath-to-breath intervals vary 8–15 % in adults; a motor's do not. The classifier calls a window machine-like when its autocorrelation stays above 0.85 at six periods and the interval variation is under 4 %, or the correlation exceeds 0.95.</p>
{table(["window", "none", "breathing-like", "machine-like"], [[k, f"{v['none']:.0%}", f"{v['breathing-like']:.0%}", f"{v['machine']:.0%}"] for k, v in fan.items()])}
<p>A fan in the same range gate as a person still wins when it is stronger (the 3 m + fan scenario above): the single-gate model cannot separate them. The real radar has nine gates, and the sequencer keeps the best gate, so a fan at a different distance separates. Untested.</p>

<h2>Thermal sees a person at every range in the room, and so does it see a laptop</h2>
{table(["posture"] + [f"{r} m" for r in (1, 2, 3, 4, 5, 6)], [[p] + [f"{th[p][str(r)]:.0%}" for r in (1, 2, 3, 4, 5, 6)] for p in ("stand", "lie")])}
<p>False positives on thermal alone: radiator {th['false_positive']['radiator']:.0%} (too hot, rejected), laptop {th['false_positive']['laptop']:.0%}, sunlit wall patch {th['false_positive']['sun']:.0%}. That is why thermal never yields PERSON VISIBLE on its own: the fusion needs the camera at the same bearing, and in the scenario chart the laptop and radiator rooms report nothing.</p>

<h2>Putting the person on the map: the rover is the rail</h2>
<p>Walleye moved one LD2410C along a rail and intersected its range circles. Hound's mecanum base strafes along the wall instead, stopping every 25 cm for a range reading, and its two LD2410Cs are toed out ±30° so the ratio of their energies gives a left/right bearing at every stop. Monte Carlo over random positions up to 4 m behind the wall, 150 trials each (localize.py):</p>
{table(["configuration", "median error", "90th pct", "along the wall", "depth"], [[k, f"{v['median_err_m']:.2f} m", f"{v['p90_err_m']:.2f} m", f"{v['median_along_wall_m']:.2f} m", f"{v['median_depth_m']:.2f} m"] for k, v in LOC.items() if ("5 stops" in k or "1 stop" in k)])}
<p>One stop with the toed-out pair already beats a single radar by an order of magnitude. Five stops in 0.2 m gate mode (the LD2410's fine-resolution setting) put the person within about 8 cm, better than the 10–13 cm MIT's WiTrack reached with a purpose-built radio. It costs 20 s of strafing per station.</p>

<h2>WiFi on purpose: the Fresnel dither</h2>
<p>WiFi breathing detection works or fails depending on where the person sits relative to the link's Fresnel zones, to within centimetres. A receiver that can move 3.1 cm, a quarter wavelength, walks every point in the room a quarter of the way through its zone, so four stops guarantee one in quadrature. Random person 0.8–3.5 m behind the wall, transmitter dropped 1.5 m along it (fresnel.py):</p>
{table(["receiver", "detection probability"], [["static", f"{FR['detection_probability']['static']:.0%}"], ["4-step dither", f"{FR['detection_probability']['dither4']:.0%}"], ["8-step dither", f"{FR['detection_probability']['dither8']:.0%}"]])}
<p>{esc(FR['rule'])}</p>

<h2>Mission</h2>
<p>{m['rooms']} rooms, {m['stations']} stations of {m['station_s']} s plus {m['travel_m']} m of driving at 0.4 m/s: <b>{m['total_min']} min</b> of a {m['pack_min']} min pack. Repeating every through-wall station from a second angle doubles the station time and still fits.</p>

<h2>What the simulation cannot tell you</h2>
<p>The radar range law (allocated), the CSI wire format of the RuView nodes, whether a household fan shares the person's gate, camera performance in the actual light, and the MLX90640's real noise on the rover's power. Every one has a line in the runbook. The code that ran here (vitals.py, detectors.py, fusion.py, station.py) is the code that will run on the Pi.</p>
</main>"""
open(os.path.join(HERE, "report.html"), "w").write(page)
print("report.html written")
