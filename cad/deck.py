#!/usr/bin/env python3
"""
deck.py — the rover's electronics deck for the 350 × 390 2020 V-slot frame.

Outputs (cad/out/):
  deck_FL.stl deck_FR.stl deck_RL.stl deck_RR.stl   four quadrant tiles, 175 × 195 × 5, each fits an Ender 3 bed
  deck_full.dxf                                    the whole 350 × 390 deck as ONE flat plate (laser-cut / SendCutSend / drill template)
  deck_full.svg  deck_<Q>.svg                       1:1 drill templates (mm units) — print at 100 % and tape to a bought sheet

Geometry comes from assembly.py: rails 20 mm, side-rail top slot at Y = ±185, cross-rail top slot at X = ±165,
deck on the rail tops (Z 91..96). Frame axes: +X forward, +Y left; the deck's own Z is up.

Run:  ~/.venvs/cad/bin/python cad/deck.py
"""
from pathlib import Path
from build123d import *   # noqa: F401,F403

OUT = Path(__file__).parent / "out"; OUT.mkdir(exist_ok=True)

T      = 5.0          # tile thickness
LAP    = 15.0         # tongue / rebate width along the two centreline seams
HALF   = T / 2
TX, TY = 175.0, 195.0 # tile size (X × Y)

# ── hole catalogue in FRAME coordinates (x, y, kind) ────────────────────────
# kind: m5cb  = M5 through Ø5.5 + Ø9 counterbore 2 deep (deck → rail T-nut, M5×8)
#       m4    = M4 through Ø4.5 (radar post flange → rear cross rail, M4×12)
#       m3    = M3 through Ø3.4 (cradle, R4 bosses, lap seams)
#       m2    = M2 through Ø2.4 (Pi bosses)
#       slot  = 20 × 8 wire pass-through
#       tie   = 4 × 10 cable-tie slot
holes = []
def H(x, y, kind): holes.append((x, y, kind))

# deck → rails: 3 per tile along each side rail (Y ±185), 2 per tile along each cross rail (X ±165)
for sx in (1, -1):
    for sy in (1, -1):
        for x in (30, 87.5, 145):  H(sx * x, sy * 185, "m5cb")
        for y in (50, 130):        H(sx * 165, sy * y, "m5cb")
# lap seams: 3 × M3 per seam half, on the seam centreline
for s in (50, 100, 150):
    H(7.5, s, "m3"); H(7.5, -s, "m3")      # seam along X = 0 (holes at X 7.5, inside the 15 mm lap)
    H(s, 7.5, "m3"); H(-s, 7.5, "m3")      # seam along Y = 0
# battery cradle under the deck: 4 × M3×12 at X ±46, Y ±14
for sx in (1, -1):
    for sy in (1, -1): H(sx * 46, sy * 14, "m3")
# radar post flange: 2 × M4 at X −165, Y ±20 (rear cross rail top slot)
H(-165, 20, "m4"); H(-165, -20, "m4")
# UNO R4 + shield stack: board 68.6 × 53.3, lower-left corner at (−150, +60), USB-C toward −X
for dx, dy in ((13.97, 2.54), (15.24, 50.8), (66.04, 7.62), (66.04, 35.56)): H(-150 + dx, 60 + dy, "m3")
# Raspberry Pi 4: 85 × 56, ports toward −X, board spans X −150..−65, Y −116..−60; 58 × 49 pattern 3.5 in from the SD end
for dx in (3.5, 61.5):
    for dy in (3.5, 52.5): H(-65 - dx, -116 + dy, "m2")
# wire slots: beside each motor corner, and one for the pack lead at the rear centre
for sx in (1, -1):
    for sy in (1, -1): H(sx * 125, sy * 150, "slot")
H(-60, -30, "slot")
# cable-tie slot pairs (a tie goes down one, over the part, up the other)
for cx, cy, w in ((-44.5, 110.5, 40), (-44.5, 150, 40), (-100, -17.3, 50), (-29, -97.5, 50),
                  (-150, -165, 20), (-140, -132, 20)):
    H(cx - w / 2, cy, "tie"); H(cx + w / 2, cy, "tie")
for sx in (1, -1):
    for sy in (1, -1): H(sx * 40, sy * 25, "tie")          # power bank, centred on the origin

BOSS = {"m3": [(-150 + dx, 60 + dy, 10.0, 7.0) for dx, dy in ((13.97, 2.54), (15.24, 50.8), (66.04, 7.62), (66.04, 35.56))],
        "m2": [(-65 - dx, -116 + dy, 8.0, 6.0) for dx in (3.5, 61.5) for dy in (3.5, 52.5)]}   # (x, y, height, Ø)

DIA = {"m5cb": 5.5, "m4": 4.5, "m3": 3.4, "m2": 2.4}

# ── one tile ────────────────────────────────────────────────────────────────
def tile(sx, sy):
    """Quadrant tile for signs (sx, sy). Tongues (lower half) face +X and +Y; rebates (upper half) on the other tiles."""
    x0, x1 = (0, TX) if sx > 0 else (-TX, 0)
    y0, y1 = (0, TY) if sy > 0 else (-TY, 0)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    body = Pos(cx, cy, T / 2) * Box(TX, TY, T)

    # X = 0 seam.  Rear tiles (sx<0) carry the tongue: lower half from X 0..15.  Front tiles take the rebate.
    if sx < 0:
        ys = (LAP, TY) if sy > 0 else (-TY, LAP)          # rear-left tongue starts above the corner square; rear-right includes it
        body += Pos(LAP / 2, (ys[0] + ys[1]) / 2, HALF / 2) * Box(LAP, ys[1] - ys[0], HALF)
    else:
        body -= Pos(LAP / 2, cy, HALF / 2) * Box(LAP, TY, HALF)              # remove lower half over X 0..15
    # Y = 0 seam.  Right tiles (sy<0) carry the tongue: lower half from Y 0..15.  Left tiles take the rebate.
    if sy < 0:
        xs = (LAP, TX) if sx > 0 else (-TX, LAP)          # front-right tongue starts past the corner square; rear-right includes it
        body += Pos((xs[0] + xs[1]) / 2, LAP / 2, HALF / 2) * Box(xs[1] - xs[0], LAP, HALF)
    else:
        body -= Pos(cx, LAP / 2, HALF / 2) * Box(TX, LAP, HALF)

    # bosses first (so holes go through them)
    for kind, lst in BOSS.items():
        for bx, by, bh, bd in lst:
            if x0 - LAP <= bx <= x1 + LAP and y0 - LAP <= by <= y1 + LAP and inside(bx, by, x0, x1, y0, y1):
                body += Pos(bx, by, T + bh / 2) * Cylinder(bd / 2, bh)

    for hx, hy, kind in holes:
        if not inside(hx, hy, x0, x1, y0, y1): continue
        if kind == "slot":
            body -= Pos(hx, hy, T / 2) * Box(20, 8, T + 30)
        elif kind == "tie":
            body -= Pos(hx, hy, T / 2) * Box(4, 10, T + 30)
        else:
            body -= Pos(hx, hy, T / 2 + 10) * Cylinder(DIA[kind] / 2, T + 60)
            if kind == "m5cb":
                body -= Pos(hx, hy, T - 1.0) * Cylinder(4.5, 2.0)              # Ø9 counterbore, 2 mm deep from the top
    return body

def inside(x, y, x0, x1, y0, y1):
    """Which tile a hole belongs to. A hole inside a lap zone (0..15 along a seam) pierces BOTH overlapping tiles:
    the positive-side tile covers it as part of its body (rebate), the negative-side tile through its tongue."""
    in_x = (x0 - 1e-6 <= x <= x1 + 1e-6) if x1 != 0 else (x0 - 1e-6 <= x <= LAP + 1e-6)
    in_y = (y0 - 1e-6 <= y <= y1 + 1e-6) if y1 != 0 else (y0 - 1e-6 <= y <= LAP + 1e-6)
    return in_x and in_y

# ── build all four ──────────────────────────────────────────────────────────
names = {(1, 1): "FL", (1, -1): "FR", (-1, 1): "RL", (-1, -1): "RR"}
tiles = {}
for (sx, sy), n in names.items():
    t = tile(sx, sy)
    tiles[n] = t
    bb = t.bounding_box()
    x0, x1 = (0, TX) if sx > 0 else (-TX, 0); y0, y1 = (0, TY) if sy > 0 else (-TY, 0)
    kinds = {}
    for hx, hy, k in holes:
        if inside(hx, hy, x0, x1, y0, y1): kinds[k] = kinds.get(k, 0) + 1
    print(f"   valid={t.is_valid} holes={kinds}")
    print(f"{n}: {bb.size.X:.1f} × {bb.size.Y:.1f} × {bb.size.Z:.1f} mm, volume {t.volume/1000:.0f} cm³ (~{t.volume/1000*1.24*0.45:.0f} g PLA at 4 walls / 20 %)")
    # move to the print origin (flat, Z up) and export
    export_stl(t.moved(Location((-bb.min.X, -bb.min.Y, 0))), str(OUT / f"deck_{n}.stl"))

# ── the whole deck as one flat plate: DXF + SVG templates ───────────────────
with BuildSketch() as sk:
    Rectangle(350, 390)
    for hx, hy, kind in holes:
        with Locations((hx, hy)):
            if kind == "slot":   Rectangle(20, 8, mode=Mode.SUBTRACT)
            elif kind == "tie":  Rectangle(4, 10, mode=Mode.SUBTRACT)
            else:                Circle(DIA[kind] / 2, mode=Mode.SUBTRACT)
full = sk.sketch
dxf = ExportDXF(unit=Unit.MM); dxf.add_layer("deck"); dxf.add_shape(full, layer="deck"); dxf.write(str(OUT / "deck_full.dxf"))
svg = ExportSVG(unit=Unit.MM, scale=1.0); svg.add_layer("deck"); svg.add_shape(full, layer="deck"); svg.write(str(OUT / "deck_full.svg"))
for (sx, sy), n in names.items():
    x0, x1 = (0, TX) if sx > 0 else (-TX, 0); y0, y1 = (0, TY) if sy > 0 else (-TY, 0)
    with BuildSketch() as q:
        with Locations(((x0 + x1) / 2, (y0 + y1) / 2)): Rectangle(TX, TY)
        for hx, hy, kind in holes:
            if not (x0 <= hx <= x1 and y0 <= hy <= y1): continue
            with Locations((hx, hy)):
                if kind == "slot":   Rectangle(20, 8, mode=Mode.SUBTRACT)
                elif kind == "tie":  Rectangle(4, 10, mode=Mode.SUBTRACT)
                else:                Circle(DIA[kind] / 2, mode=Mode.SUBTRACT)
    s = ExportSVG(unit=Unit.MM, scale=1.0); s.add_layer("deck"); s.add_shape(q.sketch, layer="deck"); s.write(str(OUT / f"deck_{n}.svg"))
print("holes:", len(holes), "· wrote", sorted(p.name for p in OUT.iterdir()))
