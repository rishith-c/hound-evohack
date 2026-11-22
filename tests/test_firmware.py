"""Compile firmware/r4_drive exactly as arduino-cli preprocesses it, against tests/firmware/shim, and run the C++ test
that drives it by serial commands (turret: boot, nudges, trim, hold, show, return to start; drive: ramps, watchdog)."""
import os
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.join(ROOT, "tests", "firmware")


@pytest.mark.skipif(not (shutil.which("arduino-cli") and (shutil.which("clang++") or shutil.which("g++"))),
                    reason="needs arduino-cli (to preprocess the sketch) and a C++ compiler")
def test_r4_drive_on_the_host(tmp_path):
    pre = subprocess.run(["arduino-cli", "compile", "--fqbn", "arduino:renesas_uno:unor4wifi", "--preprocess",
                          os.path.join(ROOT, "firmware", "r4_drive")], capture_output=True, text=True)
    assert pre.returncode == 0, pre.stderr[-2000:]
    sketch = tmp_path / "r4_drive.ino.cpp"; sketch.write_text(pre.stdout)
    exe = tmp_path / "r4_test"
    cxx = shutil.which("clang++") or shutil.which("g++")
    cc = subprocess.run([cxx, "-std=c++17", "-O1", "-w", "-I", os.path.join(HERE, "shim"), f'-DR4_SKETCH="{sketch}"',
                         os.path.join(HERE, "test_r4_drive.cpp"), "-o", str(exe)], capture_output=True, text=True)
    assert cc.returncode == 0, cc.stderr[-4000:]
    run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=120)
    print(run.stdout)
    assert run.returncode == 0, run.stdout[-4000:]
    import json
    lines = [l[7:] for l in run.stdout.splitlines() if l.startswith("STATUS ")]
    assert len(lines) == 2
    for line in lines:                                       # what r4.py does with each status line
        s = json.loads(line)
        assert {"rate", "tilt", "pca", "show", "ptrim", "ppos", "wd"} <= set(s)
