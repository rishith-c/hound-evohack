#!/usr/bin/env python3
"""
web.py — remote control for the rover, served from the Pi, reachable through a Cloudflare tunnel.

    venv/bin/python web.py                 # http://<pi>:8080/?k=<key>   (key printed at start, also in ~/rover/web.key)

Controls: hold-to-drive buttons (8 directions + rotate), keyboard (W A S D strafe, Q E rotate, arrows = diagonals,
space = stop), speed slider, crab-circle button, microstep selector (must match the caps under the drivers).
Safety: every drive command needs the key; if the browser stops sending for 0.6 s the rover stops; the R4 itself
stops 400 ms after the Pi goes quiet.
"""
import json
import math
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from r4 import R4

PORT = int(os.environ.get("ROVER_PORT", "8080"))
KEY_FILE = os.path.expanduser("~/rover/web.key")
K_MM = 125.0 + 215.5                 # half wheelbase + half track: wz = v / K_MM spins each wheel at v

if os.path.exists(KEY_FILE):
    KEY = open(KEY_FILE).read().strip()
else:
    KEY = secrets.token_urlsafe(9)
    open(KEY_FILE, "w").write(KEY)

r4 = R4()
TRIM_FILE = os.path.expanduser("~/rover/pan_trim")   # the pan's stop-pulse trim: the R4 forgets it on reset, so it lives here
if os.path.exists(TRIM_FILE):
    r4._send(f"T {int(open(TRIM_FILE).read().strip() or 0)}")
state ={"last_cmd": 0.0, "mode": "idle", "cmd": "stop", "circle": None, "t0": time.time()}
lock = threading.Lock()


def drive(vx, vy, wz, label):
    with lock:
        state["mode"] = "drive"; state["cmd"] = label; state["last_cmd"] = time.time()
    r4.velocity(vx, vy, wz)


def stop():
    with lock:
        state["mode"] = "idle"; state["cmd"] = "stop"; state["circle"] = None
    r4.stop()


def circle_thread(radius, v, laps, ccw):
    period = 2 * math.pi * radius / v
    t0 = time.time()
    with lock:
        state["mode"] = "circle"; state["cmd"] = f"crab circle r={radius:.0f} v={v:.0f}"; state["circle"] = t0
    while True:
        with lock:
            if state["circle"] != t0:
                return
        t = time.time() - t0
        if t >= period * laps:
            break
        th = 2 * math.pi * t / period * (1 if ccw else -1)
        r4.velocity(v * math.cos(th), v * math.sin(th), 0.0)
        time.sleep(0.05)
    stop()


def watchdog():
    while True:
        time.sleep(0.1)
        with lock:
            stale = state["mode"] == "drive" and time.time() - state["last_cmd"] > 0.6
        if stale:
            stop()


threading.Thread(target=watchdog, daemon=True).start()


# ── turret motion recorder: tilt and pan commands from the page are logged with their time and replayed here on the Pi
MOTIONS_FILE = os.path.expanduser("~/rover/motions.json")   # {label: [[t_s, kind, a, b], ...]}
try:
    motions = json.load(open(MOTIONS_FILE))
except (OSError, ValueError):
    motions = {}
rec = {"on": False, "t0": 0.0, "ev": []}
play = {"id": 0, "name": None}


def turret(kind, a=0, b=0):
    if kind == "tilt":
        r4.tilt(int(a))
    elif kind == "nudge":
        r4.nudge_pan(int(a), int(b))
    elif kind == "pan":
        r4.pan_stop()


def turret_cmd(kind, a=0, b=0):
    """A turret command from the page: do it, and log it while recording."""
    turret(kind, a, b)
    with lock:
        if rec["on"]:
            rec["ev"].append([round(time.time() - rec["t0"], 3), kind, a, b])


_save_lock = threading.Lock()


def save_motions():
    with _save_lock:                                  # snapshot and write in one piece, so an older snapshot never lands last
        with lock:
            text = json.dumps(motions)
        with open(MOTIONS_FILE, "w") as fh:
            fh.write(text)


def rec_start():
    with lock:
        rec.update(on=True, t0=time.time(), ev=[])
        if r4.status.get("tilton"):   # a held tilt is part of the pose: replay starts there. A limp tilt stays wherever it was put.
            rec["ev"].append([0.0, "tilt", int(r4.status.get("tilt", 92)), 0])
        rec["base"] = len(rec["ev"])  # a recording with nothing past the start pose is not saved


def rec_stop(name):
    with lock:
        if not rec["on"]:
            return
        rec["on"] = False
        ev = rec["ev"] if len(rec["ev"]) > rec["base"] else []
        name = (name or "").strip()[:40]
        if not name:
            n = 1
            while f"motion {n}" in motions:
                n += 1
            name = f"motion {n}"
        if ev:
            motions[name] = ev
    if ev:
        save_motions()


def play_thread(name, pid):
    t0 = time.time()
    for t, kind, a, b in motions.get(name, []):
        while time.time() - t0 < t:
            if play["id"] != pid:
                return
            time.sleep(0.01)
        if play["id"] != pid:
            return
        turret(kind, a, b)
    with lock:
        if play["id"] == pid:
            play["name"] = None


def play_start(name):
    with lock:
        play["id"] += 1; play["name"] = name; pid = play["id"]
    threading.Thread(target=play_thread, args=(name, pid), daemon=True).start()


def play_stop():
    with lock:
        play["id"] += 1; play["name"] = None
    r4.pan_stop()


VIEW_IDLE_S = 30                                # the live sensor views stop by themselves when no page has asked for this long
last_poll = {"t": time.time()}


def page_gone():
    return time.time() - last_poll["t"] > VIEW_IDLE_S


# ── senses check: sensing/bringup.py in its own process (GPIO, I2C and the camera are let go when it exits, and a
#    crash there cannot take the remote down). The motors are not touched. ────────────────────────────────────────────
SENSING = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sensing")     # deploy.sh puts sensing/ here
SENSES_TIMEOUT = 120
senses = {"running": False, "lines": []}


def senses_thread():
    try:
        p = subprocess.Popen([sys.executable, "-u", os.path.join(SENSING, "bringup.py"), "--seconds", "3"], cwd=SENSING,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        killer = threading.Timer(SENSES_TIMEOUT, p.kill); killer.start()
        for line in p.stdout:
            with lock:
                senses["lines"].append(line.rstrip())
        p.wait(); killer.cancel()
        if p.returncode < 0:
            with lock:
                senses["lines"].append(f"FAIL  senses  stopped after {SENSES_TIMEOUT} s")
    except Exception as e:
        with lock:
            senses["lines"].append(f"FAIL  senses  {e.__class__.__name__}: {e}")
    with lock:
        senses["running"] = False


def senses_start():
    with lock:
        if senses["running"]:
            return
        senses.update(running=True, lines=[])
    radar_stop(wait=True)                      # bringup reads the LD2450's port too: two readers would split its frames
    thermal_stop(wait=True)                    # ...and the thermal array's I2C address: interleaved transactions corrupt a frame
    cam_stop(wait=True)                        # ...and the webcam: only one program can hold the device
    wifi_stop(wait=True)                       # ...and UDP 5005 for the Wi-Fi CSI
    threading.Thread(target=senses_thread, daemon=True).start()


# ── radar view: the LD2450's moving targets, live, only while the page asks for it (it holds the port meanwhile) ─────
RADARS_JSON = os.path.expanduser("~/rover/radars.json")
radar = {"on": False, "id": 0, "targets": [], "fps": 0.0, "err": ""}


def radar_port():
    try:
        return json.load(open(RADARS_JSON)).get("ld2450", "/dev/ttyAMA0")
    except (OSError, ValueError):
        return "/dev/ttyAMA0"


def radar_thread(rid, opener=None):
    try:
        if SENSING not in sys.path:
            sys.path.insert(0, SENSING)
        import ld2450
        if opener is None:
            import serial
            opener = lambda port: serial.Serial(port, 256000, timeout=0.1)
        ser = opener(radar_port())
    except Exception as e:
        with lock:
            if radar["id"] == rid:
                radar.update(on=False, err=f"{radar_port()}: {e.__class__.__name__}: {e} — wired, and enable_gpio_uart.sh run?")
        return
    rd, n, t0 = ld2450.FrameReader(), 0, time.time()
    try:
        while True:
            with lock:
                if radar["id"] != rid:
                    break
            if page_gone():
                break
            frames = rd.feed(ser.read(256))
            n += len(frames)
            with lock:
                if frames:
                    radar["targets"] = [{k: t[k] for k in ("x_mm", "y_mm", "speed_cms")} for t in frames[-1]]
                if time.time() - t0 >= 1.0:
                    radar["fps"], n, t0 = round(n / (time.time() - t0), 1), 0, time.time()
    except Exception as e:
        with lock:
            radar["err"] = f"{e.__class__.__name__}: {e}"
    finally:
        ser.close()
        with lock:
            if radar["id"] == rid:
                radar.update(on=False, targets=[])


def radar_start(opener=None):
    with lock:
        if radar["on"] or senses["running"]:   # a senses check is reading that port: wait for it
            return
        radar["id"] += 1; radar.update(on=True, targets=[], fps=0.0, err=""); rid = radar["id"]
    threading.Thread(target=radar_thread, args=(rid, opener), daemon=True).start()


def radar_stop(wait=False):
    with lock:
        was = radar["on"]
        radar["id"] += 1; radar.update(on=False, targets=[])
    if was and wait:
        time.sleep(0.3)                        # the reader notices within one 0.1 s read and closes the port


# ── thermal view: the MLX90640 (I2C 0x33), live, only while the page asks for it ─────────────────────────────────────────
thermal = {"on": False, "id": 0, "frame": None, "fps": 0.0, "err": ""}
_mlx = {}                                      # the driver object is kept between on/off: opening the bus again is slow


def _open_mlx():
    if "dev" not in _mlx:
        import adafruit_mlx90640, board, busio
        i2c = busio.I2C(board.SCL, board.SDA, frequency=400000)
        m = adafruit_mlx90640.MLX90640(i2c)
        m.refresh_rate = adafruit_mlx90640.RefreshRate.REFRESH_4_HZ
        _mlx["dev"] = m
    return _mlx["dev"]


def thermal_thread(tid, opener=None):
    try:
        mlx = (opener or _open_mlx)()
    except Exception as e:
        with lock:
            if thermal["id"] == tid:
                thermal.update(on=False, err=f"{e.__class__.__name__}: {e} — wired to Pi pins 1/3/5/9? (VCC 3V3, SDA, SCL, GND)")
        return
    n, t0, bad = 0, time.time(), 0
    while True:
        with lock:
            if thermal["id"] != tid:
                break
        if page_gone():
            break
        buf = [0.0] * 768
        try:
            mlx.getFrame(buf)
            bad = 0
        except (RuntimeError, ValueError, OSError):      # a frame that changed mid-read: the driver raises, try the next
            bad += 1
            if bad >= 10:
                with lock:
                    if thermal["id"] == tid:
                        thermal.update(on=False, err="10 bad reads in a row — re-seat the thermal lead (SDA/SCL), keep it short")
                break
            continue
        n += 1
        with lock:
            if thermal["id"] != tid:
                break
            thermal["frame"] = [int(round(v * 10)) for v in buf]          # tenths of a degree C: a third the size of floats
            if time.time() - t0 >= 1.0:
                thermal["fps"], n, t0 = round(n / (time.time() - t0), 1), 0, time.time()
    with lock:
        if thermal["id"] == tid:
            thermal.update(on=False, frame=None)


def thermal_start(opener=None):
    with lock:
        if thermal["on"] or senses["running"]:  # a senses check is reading that address: wait for it
            return
        thermal["id"] += 1; thermal.update(on=True, frame=None, fps=0.0, err=""); tid = thermal["id"]
    threading.Thread(target=thermal_thread, args=(tid, opener), daemon=True).start()


def thermal_stop(wait=False):
    with lock:
        was = thermal["on"]
        thermal["id"] += 1; thermal.update(on=False, frame=None)
    if was and wait:
        time.sleep(0.6)                        # a frame read takes up to ~0.5 s; the reader leaves at its next check


# ── webcam view: the USB webcam's own MJPEG stream (ffmpeg copies it, no re-encode), live, only while the page asks ─────
cam = {"on": False, "id": 0, "jpg": None, "fps": 0.0, "err": ""}


def cam_device():
    import glob
    found = sorted(glob.glob("/dev/v4l/by-id/usb-*-video-index0"))    # the USB webcam, not the Pi's codec nodes
    return found[0] if found else "/dev/video0"


def cam_thread(cid):
    dev = cam_device()
    try:
        p = subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "v4l2", "-input_format", "mjpeg",
                              "-video_size", "1280x720", "-framerate", "30", "-i", dev, "-c:v", "copy", "-f", "mjpeg", "-"],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except Exception as e:
        with lock:
            if cam["id"] == cid:
                cam.update(on=False, err=f"{dev}: {e.__class__.__name__}: {e}")
        return
    buf, n, t0 = b"", 0, time.time()
    try:
        while True:
            with lock:
                if cam["id"] != cid:
                    break
            if page_gone():
                break
            chunk = p.stdout.read1(65536)
            if not chunk:
                err = p.stderr.read().decode(errors="replace").strip().splitlines()
                with lock:
                    cam["err"] = f"{dev}: " + (err[-1] if err else "stream ended") + " — webcam plugged in?"
                break
            buf += chunk
            while True:                                    # whole JPEGs: FFD8 … FFD9 (FF inside the data is stuffed)
                s = buf.find(b"\xff\xd8")
                e = buf.find(b"\xff\xd9", s + 2) if s >= 0 else -1
                if e < 0:
                    buf = buf[s:] if s >= 0 else buf[-1:]      # keep a partial picture; drop bytes before any start
                    break
                n += 1
                with lock:
                    cam["jpg"] = buf[s:e + 2]
                    if time.time() - t0 >= 1.0:
                        cam["fps"], n, t0 = round(n / (time.time() - t0), 1), 0, time.time()
                buf = buf[e + 2:]
    finally:
        p.kill(); p.wait()
        with lock:
            if cam["id"] == cid:
                cam.update(on=False, jpg=None)


def cam_start():
    with lock:
        if cam["on"] or senses["running"]:     # a senses check is using the camera: wait for it
            return
        cam["id"] += 1; cam.update(on=True, jpg=None, fps=0.0, err=""); cid = cam["id"]
    threading.Thread(target=cam_thread, args=(cid,), daemon=True).start()


def cam_stop(wait=False):
    with lock:
        was = cam["on"]
        cam["id"] += 1; cam.update(on=False, jpg=None)
    if was and wait:
        time.sleep(0.5)                        # ffmpeg is killed at the reader's next frame and lets go of the device


# ── Wi-Fi neural network view: ESP32 #3's CSI packets (UDP 5005) through ml/infer.py, only while the page asks ───────
ML = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ml")           # deploy.sh puts ml/ here
CSI_PORT = 5005
wifi = {"on": False, "id": 0, "bars": None, "pps": 0, "read": None, "paused": False, "model": "", "err": ""}


def driving():
    """HOUND is moving (commanded, or the wheels still ramping down): the receiver is moving, so the link is."""
    with lock:
        mode = state["mode"]
    return mode != "idle" or any(r4.status.get("rate") or [])


def _open_csi():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", CSI_PORT))
    s.settimeout(0.1)
    return s


def wifi_thread(wid, opener=None):
    try:
        if ML not in sys.path:
            sys.path.insert(0, ML)
        from infer import LiveNet                      # also puts sensing/ on the path
        from csi import parse_udp
        live = LiveNet()
        sock = (opener or _open_csi)()
    except Exception as e:
        with lock:
            if wifi["id"] == wid:
                wifi.update(on=False, err=f"Wi-Fi view: {e.__class__.__name__}: {e}")
        return
    with lock:
        wifi["model"] = os.path.basename(live.path)
    last = 0.0
    try:
        while True:
            with lock:
                if wifi["id"] != wid:
                    break
            if page_gone():
                break
            try:
                data = sock.recv(4096)
            except socket.timeout:
                data = None
            now = time.time()
            rec = parse_udp(data) if data else None
            if rec is not None:
                live.push(now, rec["amp"])
            if now - last >= 0.5:                      # two readings a second
                last = now
                b = live.bars(now)
                moving = driving()
                if moving:
                    live.reset()                       # only trusted once HOUND has stopped: 10 s of a still receiver
                r = None if moving else live.read(now)
                with lock:
                    wifi.update(pps=live.pps(now) if not moving else 0, paused=moving, read=r,
                                bars=None if b is None else [round(float(v), 1) for v in b])
    except Exception as e:
        with lock:
            wifi["err"] = f"{e.__class__.__name__}: {e}"
    finally:
        sock.close()
        with lock:
            if wifi["id"] == wid:
                wifi.update(on=False, bars=None, read=None)


def wifi_start(opener=None):
    with lock:
        if wifi["on"] or senses["running"]:    # a senses check is listening on 5005: wait for it
            return
        wifi["id"] += 1; wifi.update(on=True, bars=None, read=None, pps=0, paused=False, err=""); wid = wifi["id"]
    threading.Thread(target=wifi_thread, args=(wid, opener), daemon=True).start()


def wifi_stop(wait=False):
    with lock:
        was = wifi["on"]
        wifi["id"] += 1; wifi.update(on=False, bars=None, read=None)
    if was and wait:
        time.sleep(0.3)                        # the reader notices within one 0.1 s receive and closes the port


def status():
    s = dict(r4.status)
    with lock:
        s.update(mode=state["mode"], cmd=state["cmd"], uptime=round(time.time() - state["t0"]), port=r4.port)
        s.update(rec=rec["on"], rec_n=len(rec["ev"]), playing=play["name"], motions={k: (v[-1][0] if v else 0) for k, v in motions.items()})
        s["senses_running"] = senses["running"]
        if thermal["on"] or thermal["err"]:
            s["thermal"] = {"on": thermal["on"], "frame": thermal["frame"], "fps": thermal["fps"], "err": thermal["err"]}
        if radar["on"] or radar["err"]:
            s["radar"] = {"on": radar["on"], "targets": list(radar["targets"]), "fps": radar["fps"], "err": radar["err"]}
        if cam["on"] or cam["err"]:
            s["cam"] = {"on": cam["on"], "fps": cam["fps"], "err": cam["err"]}
        if wifi["on"] or wifi["err"]:
            s["wifi"] = {k: wifi[k] for k in ("on", "bars", "pps", "read", "paused", "model", "err")}
    return s


PAGE = r"""<!doctype html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Hound remote</title><style>
body{margin:0;background:#0f151b;color:#e6ebf0;font:16px system-ui,sans-serif}main{max-width:760px;margin:0 auto;padding:14px}
h1{font-size:18px;margin:0 0 10px;color:#93a1ae;font-weight:600}
.pad{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:10px 0}
button{font:inherit;font-size:17px;padding:20px 6px;border:1px solid #2a3641;border-radius:8px;background:#172029;color:#e6ebf0;touch-action:none;user-select:none;cursor:pointer}
button:active,button.on{background:#2e5c8a;border-color:#7fb0e0}button.stop{background:#8a1f1f;border-color:#ff8a4c;font-weight:700}
.row{display:flex;gap:14px;align-items:center;flex-wrap:wrap;margin:10px 0;font-size:14px}label{display:flex;gap:8px;align-items:center}
input[type=range]{width:200px;max-width:36vw}label small{white-space:nowrap}select,input[type=number]{font:inherit;background:#172029;color:#e6ebf0;border:1px solid #2a3641;border-radius:4px;padding:4px}
.w{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin:8px 0}.w div{background:#172029;border-radius:6px;padding:6px;text-align:center;font-family:ui-monospace,monospace;font-size:13px}
.w b{display:block;font-size:15px;color:#93a1ae}#st{font-family:ui-monospace,monospace;font-size:12px;color:#93a1ae;white-space:pre-wrap}
.mt{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin:8px 0}.mt div{background:#172029;border-radius:6px;padding:6px;text-align:center}.mt b{display:block;font-size:15px;color:#93a1ae;margin-bottom:6px}.mt small{display:block;color:#93a1ae;font-size:12px;font-family:ui-monospace,monospace}.mt button{width:100%;padding:12px 4px;font-size:15px;margin:2px 0}.mt button.inv{font-size:12px;padding:6px 4px;color:#93a1ae}
#tall{padding:8px 14px;font-size:14px}#tst{font-size:13px;color:#93a1ae}
.warn{color:#ff8a4c;font-size:13px}kbd{background:#2a3641;border-radius:3px;padding:0 5px;font-family:ui-monospace,monospace}
</style></head><body><main>
<h1>Hound remote</h1>
<div class=row>
 <label>speed <input id=sp type=range min=20 max=530 value=415> <span id=spv>415</span> mm/s</label>
 <label>microsteps <select id=ms><option>16<option selected>32</select></label>
 <label><input id=hold type=checkbox> hold drivers</label>
 <label>tilt <small style="color:#93a1ae">▼ down</small><input id=tilt type=range min=78 max=150 value=92><small style="color:#93a1ae">up ▲</small> <span id=tiltv>92</span>° <button id=tiltoff style="padding:4px 8px;font-size:12px">release</button></label>
 <label><button id=show style="padding:6px 12px">▶ Ceres show</button></label>
 <label>pan <button id=nudgeL style="padding:6px 12px">◀ left</button><button id=panStop style="padding:6px 12px">■</button><button id=nudgeR style="padding:6px 12px">right ▶</button> <span id=panv style="color:#93a1ae;font-size:12px">hold to keep turning · 300 ms nudges (Ceres)</span></label>
 <label>pan trim <button id=trm style="padding:4px 10px">−</button> <span id=ptv>0</span> µs <button id=trp style="padding:4px 10px">+</button> <button id=still style="padding:4px 8px;font-size:12px">test: hold still 3 s</button> <span style="color:#93a1ae;font-size:12px">creeps right → +, creeps left → −</span></label>
 <span id=lat></span>
</div>
<h1 style="margin-top:12px">Record motions</h1>
<div class=row>
 <button id=rec style="padding:6px 12px">● record</button>
 <input id=rname maxlength=40 placeholder="label, e.g. nod" style="font:inherit;background:#172029;color:#e6ebf0;border:1px solid #2a3641;border-radius:4px;padding:4px;width:160px">
 <span id=recst style="color:#93a1ae;font-size:12px">records the tilt slider and pan buttons, with timing</span>
</div>
<div class=row id=mlist></div>
<div class=pad>
 <button data-v="1,1,0">◤ fwd-left</button><button data-v="1,0,0">▲ forward</button><button data-v="1,-1,0">◥ fwd-right</button>
 <button data-v="0,1,0">◀ strafe L</button><button class=stop id=stop>STOP</button><button data-v="0,-1,0">strafe R ▶</button>
 <button data-v="-1,1,0">◣ back-left</button><button data-v="-1,0,0">▼ back</button><button data-v="-1,-1,0">◢ back-right</button>
 <button data-v="0,0,1">⟲ rotate L</button><button id=circle>◯ crab circle</button><button data-v="0,0,-1">rotate R ⟳</button>
</div>
<div class=row>
 <label>circle radius <input id=cr type=number value=150 min=50 max=600 step=10> mm</label>
 <label>laps <input id=cl type=number value=1 min=1 max=10 step=1></label>
 <label><input id=ccw type=checkbox checked> counter-clockwise</label>
</div>
<div class=w id=wheels></div>
<h1 style="margin-top:16px">Motor test</h1>
<div class=row><label>test speed <input id=js type=number value=120 min=20 max=530 step=10> mm/s</label><button id=tall>▶ run all four (fwd 1.5 s each)</button><span id=tst></span></div>
<div class=mt id=motors></div>
<h1 style="margin-top:16px">Senses</h1>
<div class=row><button id=sns style="padding:6px 12px">▶ check senses</button><span style="color:#93a1ae;font-size:12px">radars, Wi-Fi CSI, thermal, ToFs, camera, I2C · about 20 s · motors not touched</span></div>
<pre id=snsout style="font:12px ui-monospace,monospace;white-space:pre-wrap;margin:4px 0"></pre>
<h1 style="margin-top:16px">Webcam view</h1>
<div class=row><button id=cmb style="padding:6px 12px">▶ webcam live</button><span id=cmst style="color:#93a1ae;font-size:12px">USB webcam, 1280×720</span></div>
<img id=cmi alt="" style="width:640px;max-width:100%;background:#172029;border-radius:8px;display:none">
<h1 style="margin-top:16px">Thermal view</h1>
<div class=row><button id=thb style="padding:6px 12px">▶ thermal live</button><button id=thr style="padding:6px 12px">⟳ rotate</button><span id=thst style="color:#93a1ae;font-size:12px">MLX90640, 32×24 pixels, 55° wide · bright = warm · a person reads ~28–36 °C</span></div>
<canvas id=thc width=320 height=240 style="width:320px;max-width:100%;background:#172029;border-radius:8px;display:none;image-rendering:pixelated"></canvas>
<h1 style="margin-top:16px">Radar view</h1>
<div class=row><button id=rdr style="padding:6px 12px">▶ LD2450 live</button><span id=rdst style="color:#93a1ae;font-size:12px">up to 3 moving people, x/y from the rear radar · 6 m fan</span></div>
<canvas id=rdc width=320 height=180 style="width:320px;max-width:100%;background:#172029;border-radius:8px;display:none"></canvas>
<h1 style="margin-top:16px">Wi-Fi neural network</h1>
<div class=row><button id=wfb style="padding:6px 12px">▶ Wi-Fi network live</button><span id=wfst style="color:#93a1ae;font-size:12px">ESP32 #3's 51 subcarriers, read by the network trained on Blender people · needs 10 s · only while HOUND is stopped</span></div>
<div id=wfv style="display:none"><canvas id=wfc width=306 height=90 style="width:306px;max-width:100%;background:#172029;border-radius:8px"></canvas>
<div id=wfr style="font-size:20px;font-weight:600;margin:6px 0"></div><div id=wfp style="font:12px ui-monospace,monospace;color:#93a1ae"></div></div>
<p id=st>connecting…</p>
<p class=warn id=note></p>
<p style="font-size:13px;color:#93a1ae">Keys: <kbd>W</kbd><kbd>S</kbd> forward/back · <kbd>A</kbd><kbd>D</kbd> strafe · <kbd>Q</kbd><kbd>E</kbd> rotate · arrows = diagonals · <kbd>space</kbd> stop. Hold to move; release stops. Going faster than the slider allows means moving the caps under the drivers to M2 only (1/16) and picking 16 above.</p>
</main><script>
const K=new URLSearchParams(location.search).get('k')||'';const W=['FL','FR','BL','BR'];const DRV=['Y','A','X','Z'];
let cur=null,curJ=null,timer=null,lastT=0;
const api=(p)=>fetch('/api/'+p+(p.includes('?')?'&':'?')+'k='+encodeURIComponent(K)).then(r=>r.json()).then(show).catch(()=>{document.getElementById('st').textContent='no link';});
const v=()=>+document.getElementById('sp').value;
function send(){if(!cur)return;const s=v();const t=performance.now();
 api(`v?vx=${cur[0]*s}&vy=${cur[1]*s}&wz=${cur[2]*s/340.5}`).then(()=>{document.getElementById('lat').textContent='round trip '+Math.round(performance.now()-t)+' ms';});}
function start(c){cur=c;send();clearInterval(timer);timer=setInterval(send,120);}
function stop(){cur=null;curJ=null;clearInterval(timer);api('stop');}
const js=()=>+document.getElementById('js').value;
function sendJ(){if(!curJ)return;api(`jog?w=${curJ[0]}&d=${curJ[1]}&s=${js()}`);}
function startJ(j){cur=null;curJ=j;sendJ();clearInterval(timer);timer=setInterval(sendJ,120);}
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function testAll(){const b=document.getElementById('tall'),o=document.getElementById('tst');b.disabled=true;
 for(let i=0;i<4;i++){o.textContent='running '+W[i]+' (driver '+DRV[i]+') forward…';const t0=performance.now();
  while(performance.now()-t0<1500){await api(`jog?w=${i}&d=1&s=${js()}`);await sleep(120);}await api('stop');await sleep(500);}
 o.textContent='done — order was FL, FR, BL, BR; each should have rolled forward';b.disabled=false;}
function bind(b,c){b.addEventListener('pointerdown',e=>{e.preventDefault();b.classList.add('on');start(c);});
 ['pointerup','pointerleave','pointercancel'].forEach(ev=>b.addEventListener(ev,()=>{b.classList.remove('on');if(cur)stop();}));}
document.querySelectorAll('button[data-v]').forEach(b=>bind(b,b.dataset.v.split(',').map(Number)));
document.getElementById('stop').addEventListener('pointerdown',stop);
const mo=document.getElementById('motors');W.forEach((n,i)=>{const d=document.createElement('div');
 d.innerHTML='<b>'+n+'</b><small>driver '+DRV[i]+' <span id=mi'+i+'></span></small><button data-j="'+i+',1">▲ fwd</button><button data-j="'+i+',-1">▼ back</button><button class=inv data-i='+i+'>flip direction</button>';mo.append(d);});
document.querySelectorAll('button[data-j]').forEach(b=>{const j=b.dataset.j.split(',').map(Number);
 b.addEventListener('pointerdown',e=>{e.preventDefault();b.classList.add('on');startJ(j);});
 ['pointerup','pointerleave','pointercancel'].forEach(ev=>b.addEventListener(ev,()=>{b.classList.remove('on');if(curJ)stop();}));});
document.querySelectorAll('button.inv').forEach(b=>b.addEventListener('click',()=>{const i=+b.dataset.i;if(confirm('Flip '+W[i]+' (driver '+DRV[i]+') direction? Saved on the R4.'))api('set?inv='+i);}));
document.getElementById('tall').addEventListener('click',testAll);
document.getElementById('circle').addEventListener('click',()=>api(`circle?r=${document.getElementById('cr').value}&v=${v()}&laps=${document.getElementById('cl').value}&ccw=${document.getElementById('ccw').checked?1:0}`));
document.getElementById('sp').oninput=e=>document.getElementById('spv').textContent=e.target.value;
document.getElementById('ms').onchange=e=>api('set?ms='+e.target.value);
document.getElementById('hold').onchange=e=>api('set?hold='+(e.target.checked?1:0));
let tiltT=0;document.getElementById('tilt').oninput=e=>{document.getElementById('tiltv').textContent=e.target.value;const t=performance.now();if(t-tiltT>80){tiltT=t;api('set?tilt='+e.target.value);}};   // follows the drag live (and gets recorded)
document.getElementById('tilt').onchange=e=>api('set?tilt='+e.target.value);
let recOn=false,mSig='';const recB=document.getElementById('rec'),ml=document.getElementById('mlist');
recB.onclick=()=>{if(!recOn)api('rec?on=1');else{api('rec?on=0&name='+encodeURIComponent(document.getElementById('rname').value));document.getElementById('rname').value='';}};
ml.onclick=e=>{const b=e.target.closest('button');if(!b)return;const n=b.dataset.n;
 if(b.dataset.a==='play')api('play?name='+encodeURIComponent(n));else if(b.dataset.a==='stop')api('play?stop=1');else if(b.dataset.a==='del'&&confirm('Delete "'+n+'"?'))api('motion?del='+encodeURIComponent(n));};
function showRec(s){recOn=!!s.rec;recB.textContent=recOn?'■ stop & save':'● record';recB.classList.toggle('on',recOn);
 document.getElementById('recst').textContent=recOn?'recording… '+(s.rec_n||0)+' moves':'records the tilt slider and pan buttons, with timing';
 const sig=JSON.stringify([s.motions,s.playing]);if(sig===mSig)return;mSig=sig;ml.textContent='';
 Object.entries(s.motions||{}).forEach(([n,d])=>{const w=document.createElement('span');w.style.cssText='display:inline-flex;gap:6px;align-items:center;background:#172029;border-radius:6px;padding:4px 8px';
  const b=document.createElement('b');b.textContent=n;const t=document.createElement('small');t.style.color='#93a1ae';t.textContent=(+d).toFixed(1)+' s';
  const on=s.playing===n,p=document.createElement('button');p.style.cssText='padding:4px 10px;font-size:13px';p.dataset.a=on?'stop':'play';p.dataset.n=n;p.textContent=on?'■ stop':'▶ play';
  const x=document.createElement('button');x.style.cssText='padding:4px 8px;font-size:12px;color:#93a1ae';x.dataset.a='del';x.dataset.n=n;x.textContent='✕';
  w.append(b,t,p,x);ml.append(w);});}
document.getElementById('tiltoff').onclick=()=>api('set?tilt=-1');
let panTimer=null;function panHold(b,dir){b.addEventListener('pointerdown',e=>{e.preventDefault();b.classList.add('on');api('set?nudge='+dir+'&ms=300');clearInterval(panTimer);panTimer=setInterval(()=>api('set?nudge='+dir+'&ms=300'),320);});
 ['pointerup','pointerleave','pointercancel'].forEach(ev=>b.addEventListener(ev,()=>{b.classList.remove('on');clearInterval(panTimer);panTimer=null;}));}
panHold(document.getElementById('nudgeL'),-1);panHold(document.getElementById('nudgeR'),1);
document.getElementById('panStop').onclick=()=>{clearInterval(panTimer);api('set?pan=0');};
let ptrim=0,ptrimSeen=false;const setTrim=v=>{ptrim=Math.max(-150,Math.min(150,v));document.getElementById('ptv').textContent=ptrim;api('set?ptrim='+ptrim);};
document.getElementById('trm').onclick=()=>setTrim(ptrim-5);document.getElementById('trp').onclick=()=>setTrim(ptrim+5);
document.getElementById('still').onclick=()=>api('set?still=3000');
let showOn=false,showT=-1e9;const showLabel=()=>{document.getElementById('show').textContent=showOn?'■ stop show':'▶ Ceres show';};
document.getElementById('show').onclick=()=>{showOn=!showOn;showT=performance.now();showLabel();api('set?show='+(showOn?1:0));};   // the R4 ignores K 1 while a show runs: the label follows its status, not the tap count
const keys={w:[1,0,0],s:[-1,0,0],a:[0,1,0],d:[0,-1,0],q:[0,0,1],e:[0,0,-1],arrowup:[1,1,0],arrowright:[1,-1,0],arrowdown:[-1,-1,0],arrowleft:[-1,1,0]};
let held=null;
window.addEventListener('keydown',e=>{const k=e.key.toLowerCase();if(k===' '){e.preventDefault();held=null;stop();return;}
 if(keys[k]&&held!==k){e.preventDefault();held=k;start(keys[k]);}});
window.addEventListener('keyup',e=>{const k=e.key.toLowerCase();if(held===k){held=null;stop();}});
const wh=document.getElementById('wheels');W.forEach((n,i)=>{const d=document.createElement('div');d.innerHTML='<b>'+n+' · '+DRV[i]+'</b><span id=r'+i+'>0</span>';wh.append(d);});
function show(s){if(!s||!s.rate)return;W.forEach((n,i)=>{const r=s.rate[i];document.getElementById('r'+i).textContent=(r>0?'▲ ':r<0?'▼ ':'· ')+Math.abs(r);document.getElementById('mi'+i).textContent=s.inv&&s.inv[i]?'· flipped':'';});
 document.getElementById('ms').value=s.ms;document.getElementById('sp').max=Math.floor(s.maxmm||190);
 if(s.show!=null&&performance.now()-showT>1500){showOn=!!s.show;showLabel();}   // resync from the R4 (after a reload, or from another phone)
 if(s.ptrim!=null&&!ptrimSeen){ptrimSeen=true;ptrim=s.ptrim;document.getElementById('ptv').textContent=ptrim;}
 document.getElementById('st').textContent=`${s.mode} · ${s.cmd} · pack ${s.vbat>5?s.vbat.toFixed(1)+' V'+(s.lv?' LOW — DRIVE LOCKED':''):'n/a'} · drivers ${s.en?'ON':'off'} · ${s.spm} steps/mm · max ${Math.floor(s.maxmm)} mm/s · R4 ${s.port||''} · pi up ${s.uptime}s`;
 document.getElementById('note').textContent=s.wd?'R4 watchdog tripped (link went quiet) — it stopped itself':'';
 showRec(s);drawThermal(s.thermal);drawRadar(s.radar);drawWifi(s.wifi);showCam(s.cam);autoStart(s);}
// Webcam: the next picture is asked for only when the last one has arrived, so a slow link shows fewer frames, never a backlog.
const cmb=document.getElementById('cmb'),cmi=document.getElementById('cmi'),cmst=document.getElementById('cmst');let cmOn=false,cmT=-1e9,cmN=0,cmN0=0,cmT0=performance.now();
function nextCam(){if(!cmOn)return;cmi.src='/api/cam.jpg?k='+encodeURIComponent(K)+'&t='+Date.now();}
cmi.onload=()=>{cmN++;setTimeout(nextCam,30);};cmi.onerror=()=>setTimeout(nextCam,400);
function showCam(c){const on=!!(c&&c.on);if(performance.now()-cmT>1500&&cmOn!==on){cmOn=on;cmb.textContent=on?'■ stop webcam':'▶ webcam live';cmi.style.display=on?'':'none';if(on)nextCam();}
 if(c&&c.err){cmst.textContent=c.err;cmst.style.color='#ff8a4c';return;}
 if(!on)return;const t=performance.now();if(t-cmT0>=1000){cmN0=Math.round((cmN)*1000/(t-cmT0));cmN=0;cmT0=t;}
 cmst.style.color='#93a1ae';cmst.textContent='camera '+c.fps+' frames/s · shown here '+cmN0+' frames/s';}
cmb.onclick=()=>{cmOn=!cmOn;cmT=performance.now();cmb.textContent=cmOn?'■ stop webcam':'▶ webcam live';cmi.style.display=cmOn?'':'none';api('cam?on='+(cmOn?1:0)).then(()=>{if(cmOn)setTimeout(nextCam,400);});};
const sns=document.getElementById('sns'),snsout=document.getElementById('snsout');let snsT=null;
function showSns(j){const s=j.senses;if(!s)return;
 snsout.innerHTML=s.lines.map(l=>{const c=/^PASS/.test(l)?'#7fd18b':/^WARN/.test(l)?'#ffcf5c':/^FAIL/.test(l)?'#ff8a4c':'#93a1ae';
  return '<span style="color:'+c+'">'+l.replace(/&/g,'&amp;').replace(/</g,'&lt;')+'</span>';}).join('\n');
 sns.textContent=s.running?'… checking':'▶ check senses';sns.disabled=s.running;if(!s.running&&snsT){clearInterval(snsT);snsT=null;}}
const thb=document.getElementById('thb'),thc=document.getElementById('thc'),thst=document.getElementById('thst');let thOn=false,thT=-1e9;
const IRON=[[0,0,0],[40,0,90],[150,0,120],[230,60,20],[255,170,0],[255,245,170],[255,255,255]];
function iron(t){const x=Math.max(0,Math.min(1,t))*(IRON.length-1),i=Math.min(IRON.length-2,Math.floor(x)),f=x-i;return IRON[i].map((v,k)=>Math.round(v+(IRON[i+1][k]-v)*f));}
// Both live views start by themselves: when the page opens, and again after a senses check that had to stop them.
// A view the person turned off stays off until the page is reloaded; one that reported an error is tried at most 3 times.
const auto={th:{off:false,tries:0},rd:{off:false,tries:0},wf:{off:false,tries:0}};let sensesWas=false;
function autoStart(s){const busy=!!s.senses_running;
 if(sensesWas&&!busy){auto.th.tries=0;auto.rd.tries=0;auto.wf.tries=0;}sensesWas=busy;if(busy)return;
 [['th',s.thermal,()=>!thOn,'thermal'],['rd',s.radar,()=>!rdOn,'radar'],['wf',s.wifi,()=>!wfOn,'wifi']].forEach(([k,st,idle,ep])=>{
  const a=auto[k];if(a.off||!idle()||a.tries>=3||(st&&st.on))return;
  if(performance.now()-(k==='th'?thT:k==='rd'?rdT:wfT)<1500)return;a.tries++;
  if(k==='th'){thOn=true;thT=performance.now();thb.textContent='■ stop thermal';thc.style.display='';}else if(k==='rd'){rdOn=true;rdT=performance.now();rdr.textContent='■ stop radar';rdc.style.display='';}else{wfOn=true;wfT=performance.now();wfb.textContent='■ stop Wi-Fi';wfv.style.display='';}
  api(ep+'?on=1');});}
// The camera sits on its side: rotate the 32x24 image in 90-degree steps (0, 90 cw, 180, 270 cw), remembered in this browser.
let thRot=1;try{const v=parseInt(localStorage.getItem('thRot'));if(v>=0&&v<=3)thRot=v;}catch(e){}
function thermalSrc(x,y){   // source index in the 24-row x 32-column frame for output pixel (x, y)
 if(thRot===0)return y*32+x;
 if(thRot===1)return (23-x)*32+y;
 if(thRot===2)return (23-y)*32+(31-x);
 return x*32+(31-y);}
document.getElementById('thr').onclick=()=>{thRot=(thRot+1)%4;try{localStorage.setItem('thRot',thRot);}catch(e){}if(lastThermal)drawThermal(lastThermal);};
let lastThermal=null;
function drawThermal(r){lastThermal=r;const on=!!(r&&r.on);if(performance.now()-thT>1500){thOn=on;thb.textContent=on?'■ stop thermal':'▶ thermal live';}
 thc.style.display=thOn?'':'none';if(r&&r.err){thst.textContent=r.err;thst.style.color='#ff8a4c';}
 if(!on||!r.frame)return;thst.style.color='#93a1ae';
 const f=r.frame.map(v=>v/10),lo=Math.min(...f),hi=Math.max(...f),span=Math.max(hi-lo,6),base=lo,g=thc.getContext('2d'),c=10;
 const tall=thRot%2===1,OW=tall?24:32,OH=tall?32:24;if(thc.width!==OW*c){thc.width=OW*c;thc.height=OH*c;thc.style.width=(OW*c)+'px';}
 let hx=0,hy=0;const hot=f.indexOf(hi);
 for(let y=0;y<OH;y++)for(let x=0;x<OW;x++){const si=thermalSrc(x,y);const v=f[si];const[R,G,B]=iron((v-base)/span);g.fillStyle='rgb('+R+','+G+','+B+')';g.fillRect(x*c,y*c,c,c);if(si===hot){hx=x*c+c/2;hy=y*c+c/2;}}
 g.strokeStyle='#7fd18b';g.lineWidth=2;g.beginPath();g.arc(hx,hy,9,0,7);g.stroke();
 const med=[...f].sort((a,b)=>a-b)[384],warm=f.filter(v=>v>med+2.5&&v<38.5).length;
 thst.textContent='hottest '+hi.toFixed(1)+' °C (circled) · coolest '+lo.toFixed(1)+' · room ~'+med.toFixed(1)+' · '+warm+' warm pixels · '+r.fps+' frames/s';}
thb.onclick=()=>{auto.th.off=thOn;thOn=!thOn;thT=performance.now();thb.textContent=thOn?'■ stop thermal':'▶ thermal live';thc.style.display=thOn?'':'none';api('thermal?on='+(thOn?1:0));};
const rdr=document.getElementById('rdr'),rdc=document.getElementById('rdc'),rdst=document.getElementById('rdst');let rdOn=false,rdT=-1e9;
function drawRadar(r){const on=!!(r&&r.on);if(performance.now()-rdT>1500){rdOn=on;rdr.textContent=on?'■ stop radar':'▶ LD2450 live';}
 rdc.style.display=rdOn?'':'none';if(r&&r.err){rdst.textContent=r.err;rdst.style.color='#ff8a4c';}
 if(!on)return;rdst.style.color='#93a1ae';rdst.textContent=(r.targets.length?r.targets.map(t=>(t.x_mm/1000).toFixed(1)+' m, '+(t.y_mm/1000).toFixed(1)+' m ahead, '+Math.abs(t.speed_cms)+' cm/s').join(' · '):'nothing moving')+' · '+r.fps+' frames/s';
 const g=rdc.getContext('2d'),W=rdc.width,H=rdc.height,cx=W/2,sc=(H-10)/6000;g.clearRect(0,0,W,H);g.strokeStyle='#2a3641';
 for(let m=2000;m<=6000;m+=2000){g.beginPath();g.arc(cx,H-4,m*sc,Math.PI*1.167,Math.PI*1.833);g.stroke();}
 [-60,60].forEach(a=>{const r=a*Math.PI/180;g.beginPath();g.moveTo(cx,H-4);g.lineTo(cx+Math.sin(r)*6000*sc,H-4-Math.cos(r)*6000*sc);g.stroke();});
 r.targets.forEach(t=>{g.fillStyle='#7fd18b';g.beginPath();g.arc(cx+t.x_mm*sc,H-4-t.y_mm*sc,6,0,7);g.fill();});}
rdr.onclick=()=>{auto.rd.off=rdOn;rdOn=!rdOn;rdT=performance.now();rdr.textContent=rdOn?'■ stop radar':'▶ LD2450 live';rdc.style.display=rdOn?'':'none';api('radar?on='+(rdOn?1:0));};
// Wi-Fi neural network: the 51 subcarriers as bars, then what the network says about them.
const wfb=document.getElementById('wfb'),wfv=document.getElementById('wfv'),wfc=document.getElementById('wfc'),wfst=document.getElementById('wfst'),wfr=document.getElementById('wfr'),wfp=document.getElementById('wfp');let wfOn=false,wfT=-1e9;
function drawWifi(w){const on=!!(w&&w.on);if(performance.now()-wfT>1500){wfOn=on;wfb.textContent=on?'■ stop Wi-Fi':'▶ Wi-Fi network live';}
 wfv.style.display=wfOn?'':'none';if(w&&w.err){wfst.textContent=w.err;wfst.style.color='#ff8a4c';}
 if(!on)return;wfst.style.color='#93a1ae';
 const g=wfc.getContext('2d'),W=wfc.width,H=wfc.height;g.clearRect(0,0,W,H);
 if(w.bars){const mx=Math.max(...w.bars,1);w.bars.forEach((v,i)=>{const h=(H-6)*v/mx;g.fillStyle='#7fb0e0';g.fillRect(i*6+1,H-h,4,h);});}
 const r=w.read;
 if(w.paused){wfr.textContent='HOUND is driving';wfr.style.color='#93a1ae';wfp.textContent='the network listens again once HOUND stops (10 s)';}
 else if(!r||!r.ready){wfr.textContent='listening…';wfr.style.color='#93a1ae';wfp.textContent=(r?r.heard_s:0)+' of 10 s heard';}
 else{wfr.textContent=r.is_person?'PERSON · '+(r.moving>=0.5?'moving':'still'):'NO ONE';wfr.style.color=r.is_person?'#ffcf5c':'#e6ebf0';
  wfp.textContent='P(person) '+r.person.toFixed(2)+' · says PERSON above '+r.threshold.toFixed(2)+' · P(moving) '+r.moving.toFixed(2);}
 wfst.textContent=w.pps+' packets/s · '+w.model+(w.pps<50&&!w.paused?' · under 50/s: ESP32 #3 on the hotspot, ESP32 #2 sending?':'');}
wfb.onclick=()=>{auto.wf.off=wfOn;wfOn=!wfOn;wfT=performance.now();wfb.textContent=wfOn?'■ stop Wi-Fi':'▶ Wi-Fi network live';wfv.style.display=wfOn?'':'none';api('wifi?on='+(wfOn?1:0));};
const snsGet=(go)=>fetch('/api/senses?'+(go?'go=1&':'')+'k='+encodeURIComponent(K)).then(r=>r.json()).then(showSns).catch(()=>{});
sns.onclick=()=>{snsGet(true);if(!snsT)snsT=setInterval(()=>snsGet(false),1000);};
setInterval(()=>{if(!cur&&!curJ)api('status');},700);api('status');
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _json(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        u = urlparse(self.path); q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if u.path in ("/", "/index.html"):
            b = PAGE.encode(); self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b); return
        if not u.path.startswith("/api/"):
            self._json({"error": "not found"}, 404); return
        if q.get("k") != KEY:
            self._json({"error": "bad key"}, 403); return
        last_poll["t"] = time.time()
        f = lambda k, d=0.0: float(q.get(k, d))
        ep = u.path[5:]
        if ep == "cam.jpg":
            with lock:
                jpg = cam["jpg"]
            if not jpg:
                self._json({"error": "no picture yet"}, 503); return
            self.send_response(200); self.send_header("Content-Type", "image/jpeg"); self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(jpg))); self.end_headers(); self.wfile.write(jpg); return
        try:
            if ep == "status":
                pass
            elif ep == "v":
                drive(f("vx"), f("vy"), f("wz"), f"v {f('vx'):.0f} {f('vy'):.0f} {f('wz'):.3f}")
            elif ep == "stop":
                stop()
            elif ep == "circle":
                stop()
                threading.Thread(target=circle_thread, args=(max(50.0, f("r", 150)), max(20.0, f("v", 80)), max(1, int(f("laps", 1))), q.get("ccw", "1") == "1"), daemon=True).start()
            elif ep == "set":
                if "ms" in q and q["ms"] in ("8", "16", "32"):
                    r4._send(f"m {q['ms']}")
                if "hold" in q:
                    r4.hold_enable(q["hold"] == "1")
                if "tilt" in q:
                    turret_cmd("tilt", int(float(q["tilt"])))
                if "pan" in q:
                    turret_cmd("pan")
                if "show" in q:
                    r4._send(f"K {1 if q['show'] == '1' else 0}")
                if "nudge" in q:
                    turret_cmd("nudge", int(q["nudge"]), int(float(q.get("ms", 300))))
                if "ptrim" in q:
                    v = max(-150, min(150, int(float(q["ptrim"]))))
                    r4._send(f"T {v}")
                    open(TRIM_FILE, "w").write(str(v))
                if "still" in q:
                    r4._send(f"H {int(float(q['still']))}")
                if q.get("inv") in ("0", "1", "2", "3"):
                    r4._send(f"i {q['inv']}")
            elif ep == "rec":
                if q.get("on") == "1":
                    rec_start()
                else:
                    rec_stop(q.get("name"))
            elif ep == "play":
                if q.get("name") in motions:
                    play_start(q["name"])
                else:
                    play_stop()
            elif ep == "motion":
                with lock:
                    motions.pop(q.get("del", ""), None)
                save_motions()
            elif ep == "thermal":
                thermal_start() if q.get("on") == "1" else thermal_stop(wait=True)
            elif ep == "radar":
                radar_start() if q.get("on") == "1" else radar_stop(wait=True)   # port closed before a quick re-start
            elif ep == "cam":
                cam_start() if q.get("on") == "1" else cam_stop(wait=True)
            elif ep == "wifi":
                wifi_start() if q.get("on") == "1" else wifi_stop(wait=True)       # port closed before a quick re-start
            elif ep == "senses":
                if q.get("go") == "1":
                    senses_start()
                with lock:
                    snap = {"running": senses["running"], "lines": list(senses["lines"])}
                self._json({**status(), "senses": snap}); return
            elif ep == "jog":
                r4.jog(int(f("w")), int(f("d", 1)), f("s", 60))
                with lock:
                    state["mode"] = "drive"; state["cmd"] = "jog"; state["last_cmd"] = time.time()
            else:
                self._json({"error": "unknown"}, 404); return
        except Exception as e:  # never let a bad request take the server down
            self._json({"error": str(e)}, 500); return
        self._json(status())


if __name__ == "__main__":
    print(f"Hound remote on port {PORT}, key {KEY}  →  http://<host>:{PORT}/?k={KEY}", flush=True)
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), H)
    try:
        srv.serve_forever()
    finally:
        r4.close()
