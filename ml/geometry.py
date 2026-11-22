"""The search scene the Wi-Fi network is trained for, in one place (plain Python: Blender imports it too).

Same layout as sensing/fresnel.py's Monte Carlo: the transmitter (ESP32 #2) is dropped at the doorway, HOUND's
receiver (ESP32 #3, on the mast) sits 1.5 m along the wall, and the person is somewhere behind the wall. Metres;
x along the wall, y away from HOUND through the wall, z up.
"""
TX = (-1.5, 0.0, 0.80)            # ESP32 #2 on the floor stand at the doorway, antenna 0.8 m up (ALLOC)
RX = (0.0, 0.0, 0.45)             # ESP32 #3 on HOUND's mast (ALLOC: mast height)
WALL_Y = 0.3                      # the partition HOUND looks through
REGION = ((-1.0, 1.5), (0.8, 3.5))  # where a person can be: x range, y range (fresnel.monte_carlo)
ZONES = ("left", "centre", "right")


def zone_of(x):
    """Left / centre / right third of the searched region, seen from HOUND looking through the wall."""
    (x0, x1), _ = REGION
    return min(2, max(0, int(3 * (x - x0) / (x1 - x0))))
