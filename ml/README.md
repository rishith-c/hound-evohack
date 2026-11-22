# ml/: HOUND's Wi-Fi neural network

ESP32 #2 sends 100 Wi-Fi probes a second, and ESP32 #3 on HOUND's mast measures how each one arrives on 51 subcarriers. A person behind the wall reflects part of that signal, and their breathing and walking change it. This folder trains a small neural network on that signal. It answers two questions: **is someone there?** and **are they still or moving?** It is trained on people built in Blender, it runs live on the rover's control page, and it can be fine-tuned on recordings made with the rover.

Every result below comes from running the code in this folder. All of them are from **simulation**: no real recordings have been made yet (`results/real.md`).

## How it works

| Step | File | What it does |
|---|---|---|
| 1. People | `blender/make_people.py` | Builds the scene in Blender: the wall, ESP32 #2 at the doorway, HOUND's receiver. Then it builds 900 people: 1.20–1.95 m tall, with body sizes from their height, 70 % standing and 30 % lying on the floor, at random spots and facing random ways. For each body it samples 24 points on the surface, weighted by area, with their normals and the part they are on. The torso points are the ones that breathe. Writes `data/people.json` and `data/previews/`. |
| 2. Signals | `simulate_csi.py` | Calculates the channel on each subcarrier at channel 6's real frequencies: the direct path, 3–8 room reflections, and every body point as its own reflector, crossing the wall (`sensing/fresnel.py`'s physics and constants). Breathing is 7–30 breaths/min and 4–12 mm, uneven, with a heartbeat. People walk at 0.3–1.0 m/s. A person lying down moves an arm or a leg. A third of the empty rooms have an oscillating desk fan. Then it adds what the ESP32 does to the signal: AGC steps, slow drift, int8 I/Q with about 1 % noise per packet, 2–15 % of packets lost, bursts of loss, and timing jitter. |
| 3. Windows | `csi_window.py` | The same code for simulation, recording and live use. It removes the AGC steps, then cuts 10 s into 20 bins per second (mean of each bin's packets), plus a motion row: how much the packets inside each bin differ. Walking makes a flicker of about 16 Hz that 20 bins/s would otherwise average away. Each subcarrier then becomes % change from its own mean. Input: 52 × 200. |
| 4. Network | `net.py` | A 1-D CNN in NumPy: three convolutions (52→24→24→24, 9 taps), pooling, mean and max over time, a dense layer, and two heads (person, moving). It has 23,372 parameters. Every gradient is written out by hand and checked against finite differences in `tests/test_ml.py`. NumPy is used because the Pi 4 already has it; PyTorch would be a 700 MB install. |
| 5. Training | `train.py` | Split by person, never by window: 70 / 15 / 15 %. Uses Adam, class-balanced loss, time-reversal augmentation, and early stopping on validation loss. The PERSON threshold is set on validation so that at most 10 % of empty rooms raise an alarm. |
| 6. Results | `evaluate.py` | Writes `results/synthetic.md` from the test people. |
| 7. Real data | `record.py`, `finetune.py` | Records labelled packets on the rover (`empty`, `still`, `moving`). Fine-tunes the network, splitting by recording, and compares both models on recordings neither has seen (`results/real.md`). |
| 8. Live | `infer.py`, `pi/rover/web.py` | The remote's **Wi-Fi neural network** view: 51 bars, then PERSON / NO ONE and still / moving. It needs 10 s of packets. It pauses while HOUND drives, because a moving receiver is a different link, and starts over when HOUND stops. |
| — | `replay.py` | Sends simulated people as real `csi_rx_udp` packets to UDP 5005. The live view and the recorder can then be run without the rover. |

## Results (simulation, `results/synthetic.md`)

Test set: 955 windows of 10 s, from Blender people and rooms the network never trained on. The PERSON threshold gives 11 % false alarms in empty rooms.

| | |
|---|---|
| A **moving** person behind the wall is found | **86.9 %** |
| Still or moving, when someone is there | **91.5 %** |
| An empty room with an oscillating fan is called a person | 7.9 % |
| A **still** person, breathing only, is found | 21.4 % (standing 25.5 %, lying 12.4 %) |
| One reading (10 s window + network) on a laptop | 1.1 ms; the Pi 4 has not been timed yet (`infer.py --bench`) |

What the experiments showed:

- **The simulator has to be messy.** The same network trained on clean simulated signals (no ESP32 faults) and tested on the messy ones calls 81 % of empty rooms a person, and its still/moving answer is a coin toss (48 %). See `results/synthetic.md`, second section.
- **A still person through a wall is the hard case.** Breathing changes the signal by about 0.05–0.4 %, and the ESP32's own noise is about 0.5 % per bin. This is the problem `sensing/fresnel.py`'s dither exists for: moving the receiver λ/4 at a time until some stop puts the person in quadrature.
- **Breathing rate is not shown live.** It is within 3 breaths/min in only 41 % of the still people found, and how clear the rhythm looks does not predict when it is right.
- **Left / centre / right does not work from Wi-Fi amplitude.** A network trained with a zone head (`train.py --zone`) scores 30.1 %, where chance is 33 %. Two quick exploratory tries, not kept in the repo (a fixed room with an empty-room baseline, and three listening stops along the wall), also stayed at chance. The body's echo arrives only about 10 ns after the direct path, so it hardly changes across 16 MHz, and its phase changes every few centimetres. **Position comes from the LD2450 radar**, which measures x and y directly.

## Run it

```bash
blender --background --python ml/blender/make_people.py -- --n 900 --seed 1   # people.json + previews (~1 min)
python ml/simulate_csi.py                                                     # data/synth.npz (~15 s, 12 cores)
python ml/train.py                                                            # models/csi_nn.npz (~25 s)
python ml/evaluate.py                                                         # results/synthetic.md
python ml/simulate_csi.py --clean --out ml/data/synth_clean.npz && python ml/train.py --data ml/data/synth_clean.npz --out ml/models/csi_nn_clean.npz --log ml/results/train_log_clean.json && python ml/evaluate.py --model ml/models/csi_nn_clean.npz --name "trained on clean simulation (no ESP32 faults), tested on the messy test set"
python ml/train.py --zone --out ml/models/csi_nn_zone.npz --log ml/results/train_log_zone.json && python ml/evaluate.py --model ml/models/csi_nn_zone.npz --name "with a left / centre / right head"
```

These need a Python with NumPy. Blender's own Python runs step 1. The `--clean` and `--zone` runs append their sections to `results/synthetic.md`, so run them after `evaluate.py`.

**On the rover:** `pi/deploy.sh` copies `ml/` to `~/rover/ml/` (recordings on the Pi are kept). The view starts by itself when the remote page opens. To record, stop the view or the remote first, because only one program can listen on UDP 5005:

```bash
cd ~/rover && venv/bin/python ml/record.py --label empty --seconds 60     # then still and moving, 3+ of each
venv/bin/python ml/infer.py --bench                                       # time one reading on the Pi
```

Then copy them back with `rsync -a <pi>:rover/ml/data/real/ ml/data/real/`, run `python ml/finetune.py`, and deploy again. The remote uses `models/csi_nn_real.npz` once it exists.

**Without the rover:** `python3 tests/remote_stub.py`, using a Python with NumPy, and in another terminal `python ml/replay.py --kind moving` (or `still`, `empty`).

## Limits

- Everything above is simulation. The simulator's physics follows `sensing/fresnel.py`. Its ESP32 faults are estimates (marked in the code), not measurements of HOUND's boards.
- One person, one drywall partition, and a receiver and transmitter on channel 6 (the Pi's hotspot). It has not been tried through concrete or with two people.
- HOUND must be stopped. The view throws away its 10 s whenever the wheels turn.
- `ml/data/*.npz` and `ml/data/real/` are not in git: the first is rebuilt in 15 s, and the second stays on the machine that recorded it.
