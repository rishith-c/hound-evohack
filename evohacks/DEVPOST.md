# HOUND: EvoHacks 2 Devpost answers

Theme: Projects for Social Good. Deadline: Nov 22 2026, 12:00 pm PST.
Team: Rishith Chennupati, Junsu (Jun) Park, Mario.

---

## Project name

HOUND

## Tagline

A low-cost search-and-rescue rover that looks for people behind walls and under rubble, using Wi-Fi, radar and body heat.

---

## Inspiration

On 26 August 2026, the Bhote Koshi flood hit the Nepal–Tibet border. By 15 September, Nepal's disaster authority (NDRRMA) counted about 1,399 people dead and about 5,130 missing. Many of the missing were under mud, rock and collapsed buildings.

After a disaster like that, rescuers have to answer one question again and again: is anyone alive in there, and where? The usual tools are cameras on poles, search dogs, and listening devices. A camera can't see through a wall. A dog needs a trained handler and gets tired. A listening device needs the survivor to make noise. Through-wall radar exists, but the units rescue teams use cost thousands of dollars, so a volunteer fire department or a team in a poor region usually doesn't have one.

We wanted to see how much of that job a student-built rover made from cheap parts could do. That is HOUND. It is named after the rescue dog: it stops, goes quiet, and listens.

## What it does

HOUND is a small rover on mecanum wheels. A rescuer drives it from a laptop over Wi-Fi into a space that is not safe for people. When it stops, it uses several senses together to answer "is someone there?":

- **Wi-Fi sensing.** One ESP32-S3 sends Wi-Fi probes (100 a second) and a second ESP32-S3 on HOUND measures how each one arrives across 51 subcarriers. This is called channel state information (CSI). A person's body reflects and blocks part of the signal, and even breathing moves the chest enough to shift it. A small neural network on the Raspberry Pi reads a 10 second window and answers PERSON or NO ONE, and if someone is there, still or moving.
- **24 GHz radar.** An HLK-LD2450 tracks where a moving person is (x, y and speed). Two HLK-LD2410C radars give range and look for the slow repeating motion of breathing through drywall.
- **Thermal camera.** An MLX90640 (32 x 24 pixels) sees body heat once a person is in view.
- **Webcam and distance sensors.** A USB webcam shows the operator what HOUND sees. Two VL53L1X time-of-flight sensors measure distance to walls and obstacles.

All of this shows live on HOUND's web remote, next to the drive controls.

**New for EvoHacks: the rescue-team operator console.** During this event we designed a console for the person running a search. It is a concept with simulated readings, not yet connected to the real rover. It has:

- a map with satellite imagery of the search area;
- a simulated earthquake shake field and damage zones on the map, so the team can see which areas are likely worst hit;
- a route planner: the operator presses **Plan Route**, sees the proposed path on the map, and must **approve** it before the rover moves;
- sensor panels for the Wi-Fi network, radar and thermal readings, with a clear status for each.

We also added a new segment to our video that walks through this console.

## How we built it

**The rover.**
- Frame: aluminium extrusion with a foam-board deck.
- Drive: four NEMA 17 stepper motors on 80 mm mecanum wheels, so HOUND can drive forward, sideways, and turn in place. That helps in doorways and around debris.
- Motor control: an Arduino UNO R4 with a CNC shield and four DRV8825 drivers at 1/32 step. We picked DRV8825s over the cheaper A4988s because our torque check (`drivetrain.py`) showed the A4988s would stall on a 5 degree ramp. Top speed in the firmware is 530 mm/s.
- Safety: the Arduino stops the motors by itself 400 ms after the Pi goes quiet, so a dropped link can't leave the rover driving.
- Brain: a Raspberry Pi 4 runs the sensors, the neural network and the web remote. We drive from a laptop over Wi-Fi.
- Power: a 3S 2200 mAh LiPo. Every wire is listed and checked in `wiring.py`.

**The Wi-Fi neural network (`ml/`).**
1. **Training people in Blender.** We had no real recordings, so a Blender script builds 900 people, 1.20 to 1.95 m tall, 70% standing and 30% lying down, at random spots behind a wall. It samples 24 points on each body, and the torso points breathe.
2. **Simulating the signal.** `simulate_csi.py` works out the Wi-Fi channel at channel 6's real frequencies: the direct path, 3 to 8 room echoes, and each body point as a reflector through the wall. People breathe 7 to 30 times a minute with a heartbeat, or walk at 0.3 to 1.0 m/s. A third of the empty rooms have an oscillating fan. Then it adds the ESP32's own faults: gain jumps, drift, noise, lost packets and timing jitter.
3. **The network.** A 1-D convolutional network written from scratch in NumPy: three convolution layers (52 to 24 to 24 to 24 channels, 9 taps), pooling, mean and max over time, a dense layer, and two output heads (person, and still/moving). It has 23,372 parameters. We wrote every gradient by hand and test each one against finite differences. We used NumPy instead of PyTorch because the Pi already has NumPy and PyTorch is a 700 MB install.
4. **Training.** We split the data by person, not by window, so the test set only has people the network never saw. The PERSON threshold is set so at most about 10% of empty rooms raise an alarm.

**Sensor fusion (`sensing/`).** The radars, thermal camera and webcam are combined with a Bayesian fusion step. Its labels run from NOTHING to PERSON VISIBLE. We deliberately never use the word "alive", because a radar measures repeating motion, not life.

**The operator console (built during EvoHacks).** A web page with a satellite map, a simulated shake field and damage zones, the Plan Route button with operator approval, and sensor panels fed by simulated readings.

**The film.** We built a 3D model of the rover in Blender for the assembly and sensing shots, and filmed the real rover driving and a real wall test.

## Challenges we ran into

- **No real data.** We could not record people under real rubble, so we built a simulator. Our first simulator was too clean. A network trained on clean signals and tested on messy ones called 81% of empty rooms a person. Adding the ESP32's real faults to the simulator fixed most of that.
- **The network cheated.** Early on it learned "fan means empty room" instead of "no person means empty room". Class-balanced training and a calibrated alarm level fixed it.
- **A still person is very hard.** Breathing changes the signal by about 0.05 to 0.4%, and the ESP32's own noise is about 0.5%. The signal is smaller than the noise.
- **Wi-Fi can't tell where someone is.** We tried training a left / centre / right head. It scored 30.1%, where guessing is 33%. So position comes from the LD2450 radar, which measures x and y directly.
- **Hardware breaks.** A solder joint on the radar broke before we filmed, which limited what we could show live.

## Accomplishments that we're proud of

- We built and drove a working mecanum rover with sensors, a web remote and a fail-safe stop.
- We wrote a neural network from scratch, with hand-written gradients that are tested, small enough to run on a Raspberry Pi.
- On simulated test data, from people the network never trained on (955 ten-second windows):
  - a **moving** person behind the wall is found **86.9%** of the time;
  - when someone is there, it tells **still from moving 91.5%** of the time;
  - an empty room with a fan is wrongly called a person **7.9%** of the time;
  - one reading takes about **1.1 ms** on a laptop (the Pi 4 has not been timed yet).
- We are honest about the weak spot: a **still** person, breathing only, is found just **21.4%** of the time in simulation (25.5% standing, 12.4% lying down).
- The repo has 78 automated tests, covering the firmware, the remote, the network and the wiring.

## What we learned

- A simulator has to be messy to be useful. Clean training data gave a network that looked good and failed on realistic signals.
- A good-looking accuracy number can hide a cheat. We only caught the "fan means empty" shortcut by breaking results down by case.
- No single sensor is enough. Wi-Fi is good at "is someone moving here", radar is good at "where", and thermal is good at confirming once the person is in view. That is why HOUND uses all three.
- For a rescue tool, the operator has to stay in charge. That is why the console plans a route but waits for a person to approve it before the rover moves.

## What's next for HOUND

1. **Real recordings.** The tools are already built: `ml/record.py` records labelled data on HOUND (empty, still, moving) and `ml/finetune.py` fine-tunes the network on it. No real recordings exist yet. This is the most important next step, and until it is done none of our numbers say anything about real-world accuracy.
2. **Still people.** Improve detection of a person who is only breathing, for example by moving the receiver a quarter wavelength at a time between listening stops.
3. **Fix and re-test the radar,** then repeat the wall test with every sensor reading live.
4. **Connect the console to the real rover,** so the map, route planner and sensor panels show live data instead of simulated readings.
5. **Accessibility in the console (planned):** full keyboard control and a high-contrast mode.
6. **Talk to real rescue teams.** We have not worked with any search-and-rescue team yet. We want to show HOUND to a local fire department and learn what they actually need.
7. Test through concrete and with more than one person. So far the simulation covers one person and one drywall wall.

---

## Fit to the prompt: why this is social good

HOUND exists for one job: helping people find survivors after a disaster. The users we have in mind are urban search-and-rescue teams, volunteer and under-funded fire departments, and rescuers in disaster regions like the Nepal flood area, where an expensive through-wall radar is out of reach. The whole design follows from that: cheap, common parts (ESP32 boards, a Raspberry Pi, hobby radars), a rover that keeps rescuers out of unsafe spaces, and a console that keeps the human in control. The social-good goal isn't added on at the end. It is the reason every part is there.

## Problem and impact

- **Problem:** after a collapse, rescuers don't know where survivors are, and the tools that see through walls are expensive.
- **Current approach:** cameras (can't see through walls), dogs (need handlers and rest), listening devices (need the survivor to make noise), and through-wall radar (costs thousands of dollars).
- **What HOUND adds:** a low-cost rover that combines Wi-Fi sensing, radar and thermal, so a team can check a space before sending a person in, and focus digging where a sensor points.
- **Evidence so far:** the simulated test results above, and a real wall test in our video with HOUND on one side of a wall and Rishith on the other. We are clear that the neural network numbers come from simulation only. They are a starting point, not proof that HOUND works in a real collapse.

## Appropriate use of technology

- **Why Wi-Fi, radar and thermal together:** each one covers the others' gaps. Wi-Fi works through walls but can't locate someone. Radar locates a moving person but struggles with someone perfectly still. Thermal confirms a person but needs a line of sight. Together they give a more useful answer than any one alone.
- **Why a small network on the Pi:** the rover must work where there is no internet, so everything runs on board. A 23,372-parameter network runs in about a millisecond and needs no GPU.
- **AI limitations, stated plainly:**
  - The network was trained only on synthetic data made in Blender and a simulator. There are no real-world recordings yet.
  - It is weak on still people: 21.4% found in simulation.
  - It needs real data before anyone should trust it in a rescue.
  - The 1.8 m survivor position in the video's collapsed-building scene is from our 3D scene, not a measurement.
- **Human in the loop:** the console plans a route but never moves the rover until the operator approves it, and the sensor fusion reports "person visible", never "alive".

## Usability and accessibility

- The operator console puts the map, the route, and each sensor's status on one screen, so the operator doesn't have to switch between windows during a search.
- Motion only happens after an explicit approval step (Plan Route, then Approve).
- Each sensor panel shows a clear status in plain words.
- The existing web remote already has a hold-to-drive pad and W A S D / Q E keyboard driving, a speed slider, and a "check senses" button that gives a PASS / WARN / FAIL line for each sensor with the likely fault.
- Planned, not done yet: full keyboard control of the console and a high-contrast mode.

---

## What we built during EvoHacks 2

- The rescue-team operator console concept: the satellite map, the simulated earthquake shake field and damage zones, the route planner with Plan Route and operator approval, and the sensor panels. It runs on simulated readings and is not yet connected to the rover.
- A new segment in the video showing the console.

---

## Built with

esp32-s3, wi-fi-csi, raspberry-pi, arduino, python, numpy, neural-networks, cnn, blender, hlk-ld2450, hlk-ld2410c, 24ghz-radar, mlx90640, thermal-imaging, vl53l1x, nema17, drv8825, mecanum-wheels, sensor-fusion, html, javascript

---

## Try it / how to evaluate

- **Repo:** https://github.com/rishith-c/hound-evohack
- **Video:** [VIDEO LINK]

You need Python 3 with NumPy and pytest.

Run all the tests (78, about 25 seconds):

```bash
python3 -m pytest tests
```

See the Wi-Fi network work without the rover. This starts the remote on a stub and sends it simulated people as real ESP32 packets:

```bash
python3 tests/remote_stub.py          # then open http://localhost:8099/?k=dev
python3 ml/replay.py --kind moving    # in a second terminal; or --kind still, --kind empty
```

Rebuild the network from scratch (about 2 minutes, needs Blender for step 1):

```bash
blender --background --python ml/blender/make_people.py -- --n 900 --seed 1
python3 ml/simulate_csi.py
python3 ml/train.py
python3 ml/evaluate.py     # writes ml/results/synthetic.md
```

The full simulated results are in `ml/results/synthetic.md`. `ml/results/real.md` confirms there are no real recordings yet.
