"""HLK-LD2410C protocol: frame parsing and configuration commands.

Wire format (256000 baud, 8N1):

  data frame     F4 F3 F2 F1 | len u16le | payload | F8 F7 F6 F5
  command frame  FD FC FB FA | len u16le | payload | 04 03 02 01

Engineering-mode payload:

  [0]      0x01 engineering, 0x02 basic
  [1]      0xAA
  [2]      target state (0 none, 1 moving, 2 static, 3 both)
  [3:5]    moving distance, cm
  [5]      moving energy 0-100
  [6:8]    static distance, cm
  [8]      static energy 0-100
  [9:11]   detection distance, cm
  [11]     max moving gate N
  [12]     max static gate M
  [13:]    N+1 moving gate energies, then M+1 static gate energies
  [...]    optional light-sensor byte and OUT byte (LD2410B/C)
  tail     0x55 0x00

Gate size is 0.75 m, so gate g spans 0.75*g to 0.75*(g+1) metres.
"""

import struct

DATA_HEAD = b"\xf4\xf3\xf2\xf1"
DATA_TAIL = b"\xf8\xf7\xf6\xf5"
CMD_HEAD = b"\xfd\xfc\xfb\xfa"
CMD_TAIL = b"\x04\x03\x02\x01"

GATE_M = 0.75  # metres per range gate

STATES = {0: "none", 1: "moving", 2: "static", 3: "both"}


def command(word: int, value: bytes = b"") -> bytes:
    """Build a command frame. `word` is the 16-bit command, LE."""
    body = struct.pack("<H", word) + value
    return CMD_HEAD + struct.pack("<H", len(body)) + body + CMD_TAIL


ENABLE_CONFIG = command(0x00FF, b"\x01\x00")
END_CONFIG = command(0x00FE)
ENG_ON = command(0x0062)
ENG_OFF = command(0x0063)


def parse_payload(p: bytes) -> dict | None:
    """Parse one data-frame payload. Returns None if it isn't a valid report."""
    if len(p) < 13 or p[1] != 0xAA:
        return None

    engineering = p[0] == 0x01
    out = {
        "engineering": engineering,
        "state": STATES.get(p[2], f"?{p[2]}"),
        "moving_cm": struct.unpack_from("<H", p, 3)[0],
        "moving_energy": p[5],
        "static_cm": struct.unpack_from("<H", p, 6)[0],
        "static_energy": p[8],
        "detect_cm": struct.unpack_from("<H", p, 9)[0],
        "moving_gates": [],
        "static_gates": [],
        "light": None,
    }

    if not engineering:
        return out

    n_mov, n_sta = p[11], p[12]
    # Sanity-check the gate counts before trusting them as slice lengths.
    if n_mov > 8 or n_sta > 8:
        return out
    i = 13
    if len(p) < i + (n_mov + 1) + (n_sta + 1):
        return out

    out["moving_gates"] = list(p[i : i + n_mov + 1])
    i += n_mov + 1
    out["static_gates"] = list(p[i : i + n_sta + 1])
    i += n_sta + 1

    # Light sensor and OUT byte are present on the B/C variants, absent on some
    # firmware revisions -- take them only if the bytes are actually there. The
    # payload also carries the 55 00 tail, so "there" means 4 bytes, not 2.
    if len(p) >= i + 4:
        out["light"] = p[i]
    return out


class FrameReader:
    """Feed it bytes, get back parsed reports. Resyncs on garbage."""

    MAX_BUF = 4096

    def __init__(self):
        self.buf = bytearray()
        self.dropped = 0

    def feed(self, data: bytes) -> list[dict]:
        self.buf.extend(data)
        if len(self.buf) > self.MAX_BUF:
            del self.buf[: -self.MAX_BUF]
            self.dropped += 1

        reports = []
        while True:
            i = self.buf.find(DATA_HEAD)
            if i < 0:
                # Keep the last 3 bytes: a header may be split across reads.
                if len(self.buf) > 3:
                    del self.buf[:-3]
                break
            if i:
                del self.buf[:i]
            if len(self.buf) < 6:
                break

            n = struct.unpack_from("<H", self.buf, 4)[0]
            end = 6 + n + 4
            if n > 128:  # implausible length, this header was noise
                del self.buf[:4]
                self.dropped += 1
                continue
            if len(self.buf) < end:
                break

            frame = bytes(self.buf[:end])
            del self.buf[:end]
            if frame[-4:] != DATA_TAIL:
                self.dropped += 1
                continue

            r = parse_payload(frame[6 : 6 + n])
            if r:
                reports.append(r)
            else:
                self.dropped += 1
        return reports


def find_port() -> str | None:
    """Best guess at the CP2102's device path.

    On macOS always open /dev/cu.*, never /dev/tty.* -- the tty node asserts
    DCD and open() blocks forever on a USB adapter with no modem lines.
    """
    import sys as _sys

    from serial.tools import list_ports

    darwin = _sys.platform == "darwin"

    def usable(dev):
        if "bluetooth" in dev.lower():
            return False
        return not (darwin and "/tty." in dev)

    ports = [p for p in list_ports.comports() if usable(p.device)]
    for p in ports:
        blob = f"{p.description} {p.manufacturer or ''} {p.device}".lower()
        if "cp210" in blob or "slab" in blob or "usbserial" in blob:
            return p.device
    return ports[0].device if ports else None


def find_ports() -> list[str]:
    """Every attached USB-UART adapter, so one radar or several both work."""
    import sys as _sys

    from serial.tools import list_ports

    darwin = _sys.platform == "darwin"
    out = []
    for p in list_ports.comports():
        dev = p.device
        if "bluetooth" in dev.lower() or (darwin and "/tty." in dev):
            continue
        blob = f"{p.description} {p.manufacturer or ''} {dev}".lower()
        if "cp210" in blob or "slab" in blob or "usbserial" in blob:
            out.append(dev)
    return out
