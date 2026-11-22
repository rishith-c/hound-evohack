# MLX90640 thermal test rig (bare Arduino UNO R3 or R4)

An UNO R3 has 2 kB of RAM; the MLX90640 needs about 3.5 kB for its calibration table and one frame, so no Arduino
library can run the sensor on an R3. This rig makes the Arduino a dumb I2C-to-serial bridge and does the maths and
the picture on the PC. The same sketch runs on the UNO R4 WiFi (there it is just faster).

## Wire it

Adafruit-pattern MLX90640 breakout (has its own regulator and level shifter):

| breakout | UNO R3 | UNO R4 WiFi |
|---|---|---|
| VIN | 5V | 5V |
| GND | GND | GND |
| SCL | A5 | SCL |
| SDA | A4 | SDA |

Plain purple breakout with no regulator: power it from **3.3V** instead of 5V. The sketch switches off the R3's
internal 5 V pull-ups so the board's own 10 kΩ pull-ups to 3.3 V set the bus level.

On the R4 WiFi you can also plug a STEMMA QT cable into the Qwiic port and set `USE_QWIIC 1` in the sketch.

## Flash

Arduino IDE: open `thermal_bridge/thermal_bridge.ino`, pick the board and port, Upload. Or:

```bash
arduino-cli compile -u -p /dev/cu.usbmodem101 --fqbn arduino:avr:uno tools/thermal_test/thermal_bridge
```

(`arduino:renesas_uno:unor4wifi` for the R4.)

## Run the GUI

Use a Python with Tk 8.6 (python.org 3.11/3.12: `/usr/local/bin/python3`). Apple's built-in `/usr/bin/python3` ships Tk 8.5, which draws a blank white window on current macOS.

```bash
pip install pyserial numpy pillow adafruit-circuitpython-mlx90640
python3 tools/thermal_test/thermal_gui.py
```

It picks the first Arduino-looking serial port; pass `--port /dev/cu.usbmodem…` to choose. `--demo` shows a
synthetic warm person with no hardware. `--rate 8` for 8 Hz (needs the R4's native USB; the R3 at 115200 baud
manages about 2 frames per second, which is the 4 Hz setting).

What you get: 32×24 image scaled up with a choice of colour maps, auto or fixed temperature range, smooth or
blocky pixels, mirror (the sensor is mirrored when it faces you), freeze, hottest and coldest pixel crosshairs
with temperatures, the temperature under the mouse, a colour bar, a history strip of max and mean, save PNG, save CSV.

## What to look for

A person 2 m away reads about 8–10 °C above the room in a 3×5-pixel blob. A laptop or lamp is hotter and rounder.
If everything reads the same and the frame rate is 0, check the port; if the image is noise, the sensor is on 5 V
logic without level shifting (use 3.3V).
