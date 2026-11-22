"""Random people for the Wi-Fi network's training data, built in Blender.

    blender --background --python ml/blender/make_people.py -- --n 900 --seed 1

Builds the search scene (floor, the wall, ESP32 #2 at the doorway, HOUND's receiver), then one person at a time:
height 1.20-1.95 m, shoulders, chest depth and limb sizes from the height, standing or lying (a person trapped on the
floor), a random spot behind the wall and a random facing. Each body is made of real meshes (torso, head, arms, legs),
and the Wi-Fi simulator needs what a radio wave sees of it: the script samples points on the body's surface, area
weighted, with their outward normals and which part they are on. The torso points are the ones breathing moves.

Writes ml/data/people.json (geometry only, no signals) and renders the first 12 people to ml/data/previews/.
"""
import json
import math
import os
import random
import sys

import bpy
from mathutils import Euler, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
ML = os.path.dirname(HERE)
sys.path.insert(0, ML)
from geometry import REGION, RX, TX, WALL_Y, ZONES, zone_of  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
opt = {"--n": "900", "--seed": "1", "--points": "24", "--previews": "12",
       "--out": os.path.join(ML, "data", "people.json")}
for k, v in zip(argv[::2], argv[1::2]):
    opt[k] = v
N, SEED, POINTS, PREVIEWS, OUT = int(opt["--n"]), int(opt["--seed"]), int(opt["--points"]), int(opt["--previews"]), opt["--out"]
PREVIEW_DIR = os.path.join(os.path.dirname(OUT), "previews")
PARTS = ("torso", "head", "arm", "leg")


def clear():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    for block in (bpy.data.meshes, bpy.data.materials, bpy.data.cameras, bpy.data.lights):
        for b in list(block):
            block.remove(b)


def box(name, size, loc, color):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    o = bpy.context.active_object
    o.name, o.scale, o.color = name, size, color
    return o


def scene():
    clear()
    box("floor", (8, 8, 0.02), (0.25, 1.5, -0.01), (0.32, 0.32, 0.30, 1))
    box("wall", (6, 0.10, 2.4), (0.25, WALL_Y + 0.05, 1.2), (0.75, 0.74, 0.70, 1))
    box("tx_esp32", (0.06, 0.03, 0.10), TX, (0.91, 0.58, 0.23, 1))         # amber: the transmitter
    box("hound_rx", (0.30, 0.36, 0.20), (RX[0], RX[1] - 0.2, 0.10), (0.20, 0.22, 0.25, 1))
    box("rx_esp32", (0.06, 0.03, 0.10), RX, (0.91, 0.58, 0.23, 1))
    bpy.ops.object.camera_add(location=(0.25, -2.4, 3.4))
    cam = bpy.context.active_object
    cam.data.lens = 24
    cam.rotation_euler = (Vector((0.1, 1.6, 0.4)) - cam.location).to_track_quat("-Z", "Y").to_euler()
    s = bpy.context.scene
    s.camera = cam
    s.render.engine = "BLENDER_WORKBENCH"
    s.render.resolution_x, s.render.resolution_y = 480, 320
    s.display.shading.color_type = "OBJECT"
    s.display.shading.show_xray = True                               # see the person through the wall
    s.display.shading.xray_alpha = 0.3


def cylinder(r, length, loc, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=r, depth=length, location=loc, rotation=rot)
    return bpy.context.active_object


def ellipsoid(rx, ry, rz, loc):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=1, location=loc)
    o = bpy.context.active_object
    o.scale = (rx, ry, rz)
    return o


def person(rng):
    """One body at the origin, standing, facing -y (towards HOUND); returned as {part: [objects]} plus its sizes."""
    h = rng.uniform(1.20, 1.95)
    s = h / 1.75                                                      # sizes scale with height, with their own spread
    shoulder = 0.40 * s * rng.uniform(0.88, 1.12)
    chest = 0.24 * s * rng.uniform(0.85, 1.20)
    parts = {p: [] for p in PARTS}
    parts["torso"].append(ellipsoid(shoulder / 2, chest / 2, 0.17 * h, (0, 0, 0.62 * h)))
    parts["head"].append(ellipsoid(0.075 * s, 0.09 * s, 0.11 * s, (0, 0, 0.92 * h)))
    for side in (-1, 1):
        parts["arm"].append(cylinder(0.04 * s, 0.34 * h, (side * (shoulder / 2 + 0.045 * s), 0, 0.60 * h)))
        parts["leg"].append(cylinder(0.065 * s, 0.47 * h, (side * 0.09 * s, 0, 0.235 * h)))
    return parts, {"height": round(h, 3), "shoulder": round(shoulder, 3), "chest_depth": round(chest, 3)}


def place(parts, x, y, yaw, lying, chest):
    """Stand the body at (x, y) facing yaw, or lay it on its back on the floor."""
    bpy.ops.object.empty_add(location=(0, 0, 0))
    root = bpy.context.active_object
    for objs in parts.values():
        for o in objs:
            o.parent = root
    if lying:
        root.rotation_euler = Euler((-math.pi / 2, 0, yaw), "ZXY")      # feet towards -y before the yaw, face up
        root.location = (x, y, chest / 2 + 0.02)
    else:
        root.rotation_euler = (0, 0, yaw)
        root.location = (x, y, 0)
    bpy.context.view_layer.update()
    t = parts["torso"][0].matrix_world @ Vector((0, 0, 0))            # the torso, not the feet, goes on (x, y)
    root.location.x += x - t.x
    root.location.y += y - t.y
    bpy.context.view_layer.update()
    return root


def surface_points(parts, n, rng):
    """n points on the body's surface, area weighted: (world point, outward normal, area each stands for, part)."""
    tris = []
    deps = bpy.context.evaluated_depsgraph_get()
    for part, objs in parts.items():
        for o in objs:
            ev = o.evaluated_get(deps)
            m = ev.to_mesh()
            m.calc_loop_triangles()
            W = o.matrix_world
            centre = W @ Vector((0, 0, 0))
            for t in m.loop_triangles:
                a, b, c = (W @ m.vertices[i].co for i in t.vertices)
                nrm = (b - a).cross(c - a)
                area = nrm.length / 2
                if area < 1e-9:
                    continue
                nrm.normalize()
                if nrm.dot((a + b + c) / 3 - centre) < 0:            # outward
                    nrm = -nrm
                tris.append((area, a, b, c, nrm, part))
            ev.to_mesh_clear()
    total = sum(t[0] for t in tris)
    picks = rng.choices(tris, weights=[t[0] for t in tris], k=n)
    out = []
    for area, a, b, c, nrm, part in picks:
        u, v = rng.random(), rng.random()
        if u + v > 1:
            u, v = 1 - u, 1 - v
        p = a + (b - a) * u + (c - a) * v
        out.append((p, nrm, total / n, part))
    return out, total


def render(path):
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


def main():
    rng = random.Random(SEED)
    scene()
    os.makedirs(PREVIEW_DIR, exist_ok=True)
    people = []
    (x0, x1), (y0, y1) = REGION
    for i in range(N):
        parts, size = person(rng)
        lying = rng.random() < 0.30
        x, y, yaw = rng.uniform(x0, x1), rng.uniform(y0, y1), rng.uniform(-math.pi, math.pi)
        root = place(parts, x, y, yaw, lying, size["chest_depth"])
        for objs in parts.values():
            for o in objs:
                o.color = (0.95, 0.74, 0.58, 1)
        pts, area = surface_points(parts, POINTS, rng)
        torso = parts["torso"][0].matrix_world @ Vector((0, 0, 0))
        people.append({
            "id": i, "posture": "lying" if lying else "standing", **size, "x": round(x, 4), "y": round(y, 4),
            "yaw": round(yaw, 4), "zone": ZONES[zone_of(x)], "body_area_m2": round(area, 4),
            "torso_centre": [round(torso.x, 4), round(torso.y, 4), round(torso.z, 4)],
            # [dx, dy, z, nx, ny, nz, area_m2, part]: dx, dy from (x, y), so the simulator can walk the body
            "points": [[round(p.x - x, 4), round(p.y - y, 4), round(p.z, 4), round(nv.x, 4), round(nv.y, 4), round(nv.z, 4),
                        round(a, 5), PARTS.index(part)] for p, nv, a, part in pts]})
        if i < PREVIEWS:
            render(os.path.join(PREVIEW_DIR, f"person_{i:02d}.png"))
        for objs in parts.values():
            for o in objs:
                bpy.data.objects.remove(o, do_unlink=True)
        bpy.data.objects.remove(root, do_unlink=True)
        for m in [m for m in bpy.data.meshes if m.users == 0]:
            bpy.data.meshes.remove(m)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump({"seed": SEED, "points_per_person": POINTS, "parts": PARTS, "tx": TX, "rx": RX, "wall_y": WALL_Y,
               "people": people}, open(OUT, "w"), separators=(",", ":"))
    counts = {k: sum(p["posture"] == k for p in people) for k in ("standing", "lying")}
    zones = {z: sum(p["zone"] == z for p in people) for z in ZONES}
    print(f"wrote {OUT}: {N} people {counts} zones {zones}; previews of the first {min(N, PREVIEWS)} in {PREVIEW_DIR}")


main()
