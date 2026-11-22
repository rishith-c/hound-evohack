# How it has been done before, and what each result changed in this design

Read 2026-09-16. Each entry: what the paper or project established, and the design decision it drove.

## Radar vital signs through walls

- **Through-the-wall heart-beat detection with a single-channel 24 GHz CW radar** (PMC10847523): 95 % heart-rate
  accuracy at 20–100 cm through wood and brick, one channel, arctangent demodulation. *Established:* 24 GHz
  penetrates a residential wall with a usable vital-sign signal at short range. *Drove:* keeping the LD2410C as the
  primary through-wall sense, and the 2 m first station distance in the runbook.
- **Radar-based simultaneous presence detection and breathing-rate estimation** (PMC8159106): presence and rate are
  two estimators on the same slow-time signal, with presence far more robust than rate. *Drove:* the hidden track
  scores presence (mean gate energy) and periodicity separately; presence alone yields RF ACTIVITY, never a person.
- **Radar-based monitoring of respiratory rate during sleep** (Springer 2025): best at 0° and ~1 m; performance falls
  with angle and distance. *Drove:* the 20° rotation sweep to put the target near boresight, and the honest "±20°
  bearing" claim.
- **UWB impulse radar through-wall vital signs** (PMC6127280) and **experimental through-wall respiration with IR-UWB**
  (arXiv 2012.11044): wall clutter is static and can be removed by subtracting the slow mean; respiration survives
  one wall, weakens with two. *Drove:* detrend + band-pass before any periodicity measure; scope = one drywall
  partition, concrete excluded.
- **Vital-sign detection and radar self-motion cancellation** (ResearchGate 348643650) and **airborne UWB life sensing**
  (MDPI s25175232): platform motion overwhelms the physiological signal; every moving-platform system either
  cancels motion with a reference sensor or stops. *Drove:* stop-and-dwell as a hard rule; no RF window is trusted
  while any motor or servo moves; a 5 s settle after stopping.
- **Robot-mounted SFCW radar for emergency person localisation** (arXiv 2305.15795) and **robot-mounted UWB victim
  dataset** (Sci. Data 2026): a semi-autonomous rover moving between measurement positions, odometry for
  repeatability, dwell per position. *Drove:* the station protocol (settle, dwell, sweep, report) and logging every
  station as a record so the calibration can be re-learned from real data.

## WiFi CSI

- **WiFi CSI-based long-range through-wall HAR with the ESP32** (Computer Vision Systems 2023, TU Wien): ESP32-S3 CSI
  detects activity through a wall at range with a directional antenna; amplitude only. *Drove:* CSI as a
  through-wall PRESENCE sense with no range, amplitude-only processing (ESP32 CSI phase is unusable across packets).
- **Presence detection with Wi-Fi using ESP32** (IEEE 10459433): variance of subcarrier amplitude against an
  empty-room baseline is the workable presence statistic. *Drove:* CSI presence = variance ratio vs an empty-room
  calibration; without that calibration CSI reports change, not presence (the simulation confirms it adds nothing
  uncalibrated).
- **wifi-ghost** (GitHub): ESP32 + Pi aggregator claiming respiration from CSI. *Drove:* running the same periodicity
  estimator on the best subcarrier, and treating CSI periodicity as a second, weaker vote that can corroborate radar.
- **RuView / ESP32 realtime sensing** (GitHub RS2002, RuView firmware on the owned nodes): nodes are receivers of the
  access point's frames. *Drove:* the two spare ESP32s live OFF the rover as receivers; the Pi hotspot on the rover
  is the transmitter; two bistatic links through two walls.

## Thermal

- **Person detection using an ultra-low-resolution thermal imager on a low-cost MCU** (arXiv 2212.08415) and
  **MLX90640 moving-object occupancy estimation** (ScienceDirect 2021): a 32×24 array detects people reliably to
  several metres by temperature band and connected-region size; false targets are hot appliances and sunlit
  patches. *Drove:* the warm-band (room + 2.5 °C to 38.5 °C) connected-blob detector with size and aspect
  plausibility, and the rule that thermal alone never yields PERSON VISIBLE (a laptop is indistinguishable from a
  lying person at 4 m in 32×24 pixels; the simulation shows 45 % laptop false positives on thermal alone).
- **Autonomous thermal-vision robot for victim recognition in SAR** (PMC8588524): thermal + CNN on a quadruped;
  thermal is the sense that works in dark and smoke. *Drove:* thermal on the tilt turret beside the camera, and the
  bearing association between the two.

## Fusion

- **Human detection in marine SAR: multi-modal early fusion** (Ocean Engineering 2025): fusing thermal with a second
  modality raised precision and recall over either alone. *Drove:* two senses per track, and requiring both optical
  senses at one bearing for the strongest visible label.
- **Closed-loop Bayesian semantic data fusion for target search** (arXiv 1806.00727) and **multi-agent active search
  with detection and location uncertainty** (arXiv 2203.04524): log-odds accumulation of heterogeneous observations
  with calibrated likelihoods; the search decides where to look next from the posterior. *Drove:* log-odds fusion
  with likelihood-ratio tables learned from data (simulated now, logged stations later), the 10 % prior per station,
  and "worth a second station from another angle" as an output.
- **Radar–camera fusion survey** (arXiv 2410.19872): late fusion with association is the robust choice when the
  sensors see different physics. *Drove:* the two-track design — RF senses never fused with optical ones into one
  number, because nothing optical can veto something behind a wall.

## Second pass (2026-09-17): what through-wall WiFi actually is, and what the kit can do

- **Wi-Vi** (Adib & Katabi, MIT 2013) and **WiTrack / RF-Capture / RF-Pose**: the "see through walls with WiFi"
  results everyone cites. Wi-Vi needs two transmit antennas driving inverse signals so static reflections cancel;
  WiTrack is an FMCW radio; RF-Capture used ~20 antennas. None runs on an ESP32, and none is what a government
  through-wall unit uses (those are UWB impulse radars, the Xaver class). *Drove:* honesty about what WiFi does
  here — presence and breathing on a link, not imaging — and putting the mapping job on the 24 GHz radars, which
  ARE small FMCW radios.
- **Espressif esp-csi / esp-radar** (github.com/espressif/esp-csi): vendor-supported presence and motion detection
  on the ESP32-S3 from CSI, with on-device training and a web monitor. *Drove:* running the vendor firmware on the
  two dropped nodes as an independent presence vote, alongside the raw-CSI receiver.
- **Wang et al., UbiComp 2016** ("Do user location and body orientation matter?") and **Zhang et al., IMWUT 2018**
  (Fresnel diffraction model): WiFi respiration sensing is a function of the person's position within the link's
  Fresnel zones; a quarter-wavelength shift flips it between detectable and invisible. *Drove:* the Fresnel dither —
  the rover moves its receiver by λ/4 four times per station, which the simulation shows doubles detection.
- **TU Wien 2023** (ESP32-S3 through-wall activity recognition with a directional antenna): the ESP32-S3 is
  enough hardware for through-wall CSI at range when the antenna is directional. *Drove:* a biquad antenna as the
  one CSI upgrade worth its cost, if CSI ever becomes the bottleneck.
- **WiFi DensePose / RuView** (2026): commodity-router pose estimation exists but needs many CSI-capable nodes and
  a trained model; not a 6-hour build. *Drove:* nothing beyond what the RuView firmware already gives.
- **Hi-Link LD2410 user manual**: distance-gate resolution is configurable, 0.75 m or 0.2 m (command 0x00AA); the
  LD2450 tracks micro-motion of a body, not only walking. *Drove:* 0.2 m gates for the strafe-aperture
  localisation (median error 8 cm in simulation), and a bench test of whether the LD2450 reports a still,
  breathing person's bearing.

## What nobody had measured that this design needs

1. Modulation-to-noise ratio of the LD2410C's 0–100 static-gate energy versus range through a two-sided stud
   partition. Every through-wall number in the simulation hangs on it (allocated: MNR 6 at 1.5 m, falling as
   1/r², halved by the wall). The runbook's height test at 300/500/1000 mm measures it.
2. The RuView node's CSI wire format (listen.py --hexdump).
3. Whether a household fan lands in the same 0.75 m gate as the person. In the same gate a stronger fan masks the
   person; in a different gate they separate. The single-gate simulation cannot say.
