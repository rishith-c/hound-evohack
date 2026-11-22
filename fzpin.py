#!/usr/bin/env python3
"""
fzpin.py — read a Fritzing part (its .fzp + breadboard .svg, as fetched into bom-site/wiring/parts/) and return the
part's size in canvas pixels plus the absolute (x, y) of every connector's terminal, resolving SVG transforms.
Fritzing draws wires to the connector's terminalId (or the centre of its svgId element) — this does the same.

    python3 fzpin.py            # prints a summary for every part in bom-site/wiring/parts and writes parts_pins.json
"""
import json
import math
import os
import re
import sys
import xml.etree.ElementTree as ET

PX_PER_IN = 120.0
HERE = os.path.dirname(os.path.abspath(__file__))
PARTS = os.path.join(HERE, "bom-site", "wiring", "parts")


def _len_in(v: str, default_dpi=90.0) -> float:
    """SVG length → inches. Unitless/px follow Fritzing's 90-dpi convention unless the file says 72 (Illustrator)."""
    m = re.match(r"\s*([-\d.eE+]+)\s*([a-z%]*)", v)
    x, u = float(m.group(1)), m.group(2)
    return {"in": x, "mm": x / 25.4, "cm": x / 2.54, "pt": x / 72.0, "pc": x / 6.0}.get(u, x / default_dpi)


def _mat(*a):  # (a b c d e f) column-major like SVG
    return tuple(a)


def _mul(m, n):
    a, b, c, d, e, f = m; A, B, C, D, E, F = n
    return (a * A + c * B, b * A + d * B, a * C + c * D, b * C + d * D, a * E + c * F + e, b * E + d * F + f)


def _apply(m, x, y):
    a, b, c, d, e, f = m
    return a * x + c * y + e, b * x + d * y + f


def _parse_transform(s):
    m = (1, 0, 0, 1, 0, 0)
    for name, args in re.findall(r"(matrix|translate|scale|rotate|skewX|skewY)\s*\(([^)]*)\)", s or ""):
        v = [float(x) for x in re.findall(r"[-+]?[\d.]+(?:e[-+]?\d+)?", args)]
        if name == "matrix" and len(v) == 6: t = tuple(v)
        elif name == "translate": t = (1, 0, 0, 1, v[0], v[1] if len(v) > 1 else 0)
        elif name == "scale": t = (v[0], 0, 0, v[1] if len(v) > 1 else v[0], 0, 0)
        elif name == "rotate":
            r = math.radians(v[0]); cs, sn = math.cos(r), math.sin(r)
            t = (cs, sn, -sn, cs, 0, 0)
            if len(v) == 3:
                t = _mul(_mul((1, 0, 0, 1, v[1], v[2]), t), (1, 0, 0, 1, -v[1], -v[2]))
        elif name == "skewX": t = (1, 0, math.tan(math.radians(v[0])), 1, 0, 0)
        elif name == "skewY": t = (1, math.tan(math.radians(v[0])), 0, 1, 0, 0)
        else: continue
        m = _mul(m, t)
    return m


_NUM = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def _path_points(d):
    """Every point a path visits (end points and control points): plenty for a pad's bbox."""
    toks = re.findall(r"[MmZzLlHhVvCcSsQqTtAa]|" + _NUM.pattern, d)
    pts, i, cmd, cur, start = [], 0, None, (0.0, 0.0), (0.0, 0.0)
    def num():
        nonlocal i
        v = float(toks[i]); i += 1; return v
    while i < len(toks):
        if re.match(r"[A-Za-z]", toks[i]): cmd = toks[i]; i += 1
        if cmd in "Zz": cur = start; continue
        rel = cmd.islower(); c = cmd.upper()
        try:
            if c == "M":
                x, y = num(), num(); cur = (cur[0] + x, cur[1] + y) if rel else (x, y); start = cur; pts.append(cur); cmd = "l" if rel else "L"
            elif c == "L":
                x, y = num(), num(); cur = (cur[0] + x, cur[1] + y) if rel else (x, y); pts.append(cur)
            elif c == "H":
                x = num(); cur = (cur[0] + x if rel else x, cur[1]); pts.append(cur)
            elif c == "V":
                y = num(); cur = (cur[0], cur[1] + y if rel else y); pts.append(cur)
            elif c == "C":
                p = [num() for _ in range(6)]
                for k in range(0, 6, 2):
                    q = (cur[0] + p[k], cur[1] + p[k + 1]) if rel else (p[k], p[k + 1]); pts.append(q)
                cur = q
            elif c in "SQ":
                p = [num() for _ in range(4)]
                for k in range(0, 4, 2):
                    q = (cur[0] + p[k], cur[1] + p[k + 1]) if rel else (p[k], p[k + 1]); pts.append(q)
                cur = q
            elif c == "T":
                x, y = num(), num(); cur = (cur[0] + x, cur[1] + y) if rel else (x, y); pts.append(cur)
            elif c == "A":
                p = [num() for _ in range(7)]; cur = (cur[0] + p[5], cur[1] + p[6]) if rel else (p[5], p[6]); pts.append(cur)
        except (IndexError, ValueError):
            break
    return pts


def _shape_points(el):
    tag = el.tag.split("}")[-1]; g = lambda k, d="0": float(el.get(k, d) or d)
    if tag == "rect":
        x, y, w, h = g("x"), g("y"), g("width"), g("height"); return [(x, y), (x + w, y), (x, y + h), (x + w, y + h)]
    if tag == "circle":
        cx, cy, r = g("cx"), g("cy"), g("r"); return [(cx - r, cy - r), (cx + r, cy + r)]
    if tag == "ellipse":
        cx, cy, rx, ry = g("cx"), g("cy"), g("rx"), g("ry"); return [(cx - rx, cy - ry), (cx + rx, cy + ry)]
    if tag == "line":
        return [(g("x1"), g("y1")), (g("x2"), g("y2"))]
    if tag in ("polygon", "polyline"):
        v = [float(x) for x in _NUM.findall(el.get("points", ""))]; return list(zip(v[::2], v[1::2]))
    if tag == "path":
        return _path_points(el.get("d", ""))
    return []


def load_part(key):
    fzp = open(os.path.join(PARTS, key + ".fzp"), encoding="utf-8", errors="replace").read()
    svg_path = os.path.join(PARTS, key + ".svg")
    root = ET.parse(svg_path).getroot()
    w_in = _len_in(root.get("width", "1in")); h_in = _len_in(root.get("height", "1in"))
    vb = [float(x) for x in _NUM.findall(root.get("viewBox", ""))] or [0, 0, w_in * 90, h_in * 90]
    W, H = w_in * PX_PER_IN, h_in * PX_PER_IN
    base = (W / vb[2], 0, 0, H / vb[3], -vb[0] * W / vb[2], -vb[1] * H / vb[3])   # user units → canvas px

    # connector id → (name, svgId/terminalId)
    want = {}
    for m in re.finditer(r'<connector\b([^>]*)>(.*?)</connector>', fzp, re.S):
        attrs, body = m.group(1), m.group(2)
        cid = re.search(r'id="([^"]+)"', attrs); name = re.search(r'name="([^"]*)"', attrs)
        bb = re.search(r'<breadboardView>(.*?)</breadboardView>', body, re.S)
        if not (cid and bb): continue
        term = re.search(r'terminalId="([^"]+)"', bb.group(1)); sid = re.search(r'svgId="([^"]+)"', bb.group(1))
        ids = [x.group(1) for x in (term, sid) if x]
        want[cid.group(1)] = (name.group(1) if name else cid.group(1), ids)

    # walk the tree with transforms; record bbox of every element by id
    boxes = {}
    def walk(el, m):
        m = _mul(m, _parse_transform(el.get("transform")))
        pts = [_apply(m, x, y) for x, y in _shape_points(el)]
        for ch in el:
            walk(ch, m)
        eid = el.get("id")
        if eid:
            allp = pts + [p for ch in el for p in boxes.get("__sub__" + str(id(ch)), [])]
            if allp:
                xs, ys = [p[0] for p in allp], [p[1] for p in allp]
                boxes[eid] = (min(xs), min(ys), max(xs), max(ys))
        boxes["__sub__" + str(id(el))] = pts + [p for ch in el for p in boxes.get("__sub__" + str(id(ch)), [])]
    walk(root, base)

    pins = {}
    for cid, (name, ids) in want.items():
        for sid in ids:
            if sid in boxes:
                x0, y0, x1, y1 = boxes[sid]; pins[cid] = dict(name=name, x=round((x0 + x1) / 2, 1), y=round((y0 + y1) / 2, 1)); break
    return dict(key=key, w=round(W, 1), h=round(H, 1), pins=pins, missing=[c for c in want if c not in pins])


if __name__ == "__main__":
    out = {}
    for f in sorted(os.listdir(PARTS)):
        if f.endswith(".fzp") and os.path.exists(os.path.join(PARTS, f[:-4] + ".svg")):
            p = load_part(f[:-4]); out[p["key"]] = p
            xs = [v["x"] for v in p["pins"].values()]; ys = [v["y"] for v in p["pins"].values()]
            print(f"{p['key']:9s} {p['w']:6.0f}×{p['h']:<6.0f} px  pins {len(p['pins']):3d} found, {len(p['missing'])} missing"
                  + (f"  x {min(xs):.0f}–{max(xs):.0f} y {min(ys):.0f}–{max(ys):.0f}" if xs else "") + (f"  missing: {p['missing'][:6]}" if p["missing"] else ""))
    json.dump(out, open(os.path.join(HERE, "bom-site", "wiring", "parts", "parts_pins.json"), "w"), indent=0)
