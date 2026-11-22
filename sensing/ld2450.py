"""HLK-LD2450 protocol — the tracking radar that reports real x/y.

One transmitter, two receivers. The second receiver is what buys bearing,
so unlike the LD2410 this part can put a dot on a map. It only tracks
*moving* targets though, so a motionless person fades off it.

Wire format (256000 baud, 8N1, ~10 frames/s):

  AA FF 03 00 | target1 (8) | target2 (8) | target3 (8) | 55 CC     = 30 bytes

Each target, little-endian:

  [0:2]  x, mm
  [2:4]  y, mm       positive = in front of the sensor
  [4:6]  speed, cm/s  positive = receding
  [6:8]  distance resolution, mm (unsigned)

Sign is NOT two's complement. Bit 15 is a sign flag: set means positive,
clear means negative, and the magnitude is the low 15 bits. Decoding these
as plain int16 puts every real target behind the sensor.
"""

import struct

HEAD = b"\xaa\xff\x03\x00"
TAIL = b"\x55\xcc"
FRAME_LEN = 30


def _coord(raw: int) -> int:
    return (raw & 0x7FFF) if (raw & 0x8000) else -(raw & 0x7FFF)


def parse_frame(f: bytes) -> list[dict] | None:
    """Parse one 30-byte frame into a list of up to 3 targets."""
    if len(f) != FRAME_LEN or not f.startswith(HEAD) or not f.endswith(TAIL):
        return None
    out = []
    for i in range(3):
        x_r, y_r, s_r, res = struct.unpack_from("<HHHH", f, 4 + i * 8)
        if x_r == 0 and y_r == 0 and s_r == 0:
            continue                      # empty slot, not a target at the origin
        x, y = _coord(x_r), _coord(y_r)
        out.append(
            {
                "id": i,
                "x_mm": x,
                "y_mm": y,
                "speed_cms": _coord(s_r),
                "res_mm": res,
                "range_mm": int((x * x + y * y) ** 0.5),
            }
        )
    return out


class FrameReader:
    """Feed it bytes, get back target lists. Resyncs on garbage."""

    MAX_BUF = 4096

    def __init__(self):
        self.buf = bytearray()
        self.dropped = 0

    def feed(self, data: bytes) -> list[list[dict]]:
        self.buf.extend(data)
        if len(self.buf) > self.MAX_BUF:
            del self.buf[: -self.MAX_BUF]
            self.dropped += 1

        frames = []
        while True:
            i = self.buf.find(HEAD)
            if i < 0:
                if len(self.buf) > 3:
                    del self.buf[:-3]
                break
            if i:
                del self.buf[:i]
            if len(self.buf) < FRAME_LEN:
                break

            frame = bytes(self.buf[:FRAME_LEN])
            targets = parse_frame(frame)
            if targets is None:
                del self.buf[:4]           # bad tail, that header was noise
                self.dropped += 1
                continue
            del self.buf[:FRAME_LEN]
            frames.append(targets)
        return frames
