"""
turret.py — the Ceres turret, driven by the UNO R4 over the same serial link as the wheels.

The R4 drives a PCA9685 on the CNC shield's I2C pins: tilt = positional MG996R on channel 3 (the firmware clamps
78–150°, the head meets the platform below that), pan = continuous-rotation MG996R on channel 2, moved only by timed
nudges. Nothing is driven at boot — the turret starts wherever it was set by hand.

    from r4 import R4; from turret import Turret
    t = Turret(R4())
    t.tilt(90)      # level
    t.tilt(80)      # look down a little
    t.relax()       # stop the pulses so the servos stop holding (no current, no heat)
"""


class Turret:
    TILT_MIN_DEG = 78
    TILT_MAX_DEG = 150
    PARK_DEG = 92

    def __init__(self, r4):
        self.r4 = r4
        self.angle = None

    def tilt(self, deg):
        deg = int(max(self.TILT_MIN_DEG, min(self.TILT_MAX_DEG, float(deg))))
        self.r4.tilt(deg)
        self.angle = deg
        return deg

    def nudge_pan(self, direction, ms=300):
        """Ceres pan: continuous-rotation, so only timed nudges (~20° per 300 ms). Keeps a net-nudge count as a rough bearing."""
        self.r4.nudge_pan(direction, ms)
        self.pan_steps = getattr(self, "pan_steps", 0) + (1 if direction > 0 else -1)
        return self.pan_steps

    def pan_stop(self):
        self.r4.pan_stop()

    def park(self):
        self.r4.pan_stop()
        return self.tilt(self.PARK_DEG)

    def relax(self):
        self.r4.tilt(-1); self.r4.pan(-1)

    def close(self):
        self.relax()
