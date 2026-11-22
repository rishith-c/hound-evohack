"""
tof.py — the two VL53L1X distance sensors (front and rear) on the Pi's I2C-1, with the thermal array.

Both boot at 0x29, so one has to move before they can share the bus. The address change is a write to 0x29: if both
sensors are powered when it is sent, BOTH move. So only one may be awake at that moment:

    both XSHUT low  →  release FRONT (alone at 0x29)  →  FRONT to 0x30  →  release REAR (boots at 0x29)

XSHUT: FRONT on BCM 22 (header pin 15), REAR on BCM 27 (pin 13) — wiring.py PI_BCM. The sensors forget the new address
at every power-down, so this runs at every start-up.

    from tof import init_tofs, read_mm
    front, rear = init_tofs()
    print(read_mm(front), read_mm(rear))       # millimetres, or None
"""
import time

FRONT_XSHUT, REAR_XSHUT = 22, 27
DEFAULT_ADDR, FRONT_ADDR = 0x29, 0x30


def _blinka_pin(bcm):
    import board, digitalio
    p = digitalio.DigitalInOut(getattr(board, f"D{bcm}"))
    p.direction = digitalio.Direction.OUTPUT
    return p


def init_tofs(i2c=None, pin=None, sensor=None, sleep=time.sleep):
    """Bring both up in the one safe order; returns (front, rear). i2c / pin / sensor are injectable for tests."""
    if i2c is None:
        import board, busio
        i2c = busio.I2C(board.SCL, board.SDA, frequency=400000)
    if sensor is None:
        import adafruit_vl53l1x
        sensor = adafruit_vl53l1x.VL53L1X
    pin = pin or _blinka_pin
    front_x, rear_x = pin(FRONT_XSHUT), pin(REAR_XSHUT)
    front_x.value = False; rear_x.value = False; sleep(0.01)      # both asleep
    front_x.value = True; sleep(0.01)                             # FRONT alone at 0x29
    front = sensor(i2c, address=DEFAULT_ADDR)
    front.set_address(FRONT_ADDR)
    rear_x.value = True; sleep(0.01)                              # REAR boots at 0x29, alone there now
    rear = sensor(i2c, address=DEFAULT_ADDR)
    return front, rear


def read_mm(s, timeout=0.5, sleep=time.sleep):
    """One ranging: millimetres, or None if it did not answer in time."""
    s.start_ranging()
    t0 = time.monotonic()
    while not s.data_ready:
        if time.monotonic() - t0 > timeout:
            s.stop_ranging()
            return None
        sleep(0.005)
    d = s.distance                                               # cm, or None when the target is out of range
    s.clear_interrupt(); s.stop_ranging()
    return None if d is None else int(round(d * 10))
