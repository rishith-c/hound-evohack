# Wi-Fi network: results on simulated people

Written by `ml/evaluate.py` on 2026-11-15 from `ml/data/synth.npz` (simulator seed 7) and `ml/models/csi_nn.npz`. Every number below is from simulation: the Blender people of `ml/data/people.json` in the simulator of `ml/simulate_csi.py`. None is from the rover; real recordings go in `ml/results/real.md`.

Network: 23372 parameters, heads person, moving. Trained 2026-11-15 on 4384 windows (validation 961, test 955; split by person), best epoch 10 of 16, 23 s on a laptop CPU. One window takes 0.1 ms here.

## Main model

Test set: 955 windows of 10 s, from people and empty rooms the network never saw in training.

### Is someone there?

The rover says PERSON when the network's P(person) is above 0.53, a threshold set on the validation set so that at most 10 % of empty rooms (fans included) raise a false alarm.

Accuracy 59.3 %.

| true \ said | no one | person |
|---|---|---|
| no one | 240 | 30 |
| person | 359 | 326 |

| case | result |
|---|---|
| empty room called empty | 88.9 % |
| empty room with an oscillating fan called a person (false alarm) | 7.9 % |
| empty room without a fan called a person (false alarm) | 13.0 % |
| moving person found | 86.9 % |
| still person (breathing only) found | 21.4 % |
| still person standing found | 25.5 % |
| still person lying on the floor found | 12.4 % |
| still person 0.5-1.4 m behind the wall found (144 windows) | 28.5 % |
| still person 1.4-2.3 m behind the wall found (105 windows) | 19.0 % |
| still person 2.3-3.3 m behind the wall found (162 windows) | 16.7 % |

### Still or moving? (windows with a person)

Accuracy 91.5 %.

| true \ said | still | moving |
|---|---|---|
| still | 396 | 15 |
| moving | 43 | 231 |

### Breathing rate (signal processing on the same window, for still people the network found)

75 windows: median error 6.1 breaths/min, within 3 breaths/min in 41.3 %. The quarter of windows with the clearest rhythm do no better (42.1 % within 3), so the clarity cannot tell a right rate from a wrong one. The live view therefore shows no breathing rate.

## Model: trained on clean simulation (no ESP32 faults), tested on the messy test set (ml/models/csi_nn_clean.npz)

Test set: 955 windows of 10 s, from people and empty rooms the network never saw in training.

### Is someone there?

The rover says PERSON when the network's P(person) is above 0.07, a threshold set on the validation set so that at most 10 % of empty rooms (fans included) raise a false alarm.

Accuracy 75.6 %.

| true \ said | no one | person |
|---|---|---|
| no one | 52 | 218 |
| person | 15 | 670 |

| case | result |
|---|---|
| empty room called empty | 19.3 % |
| empty room with an oscillating fan called a person (false alarm) | 53.5 % |
| empty room without a fan called a person (false alarm) | 97.0 % |
| moving person found | 98.2 % |
| still person (breathing only) found | 97.6 % |
| still person standing found | 97.9 % |
| still person lying on the floor found | 96.9 % |
| still person 0.5-1.4 m behind the wall found (144 windows) | 95.1 % |
| still person 1.4-2.3 m behind the wall found (105 windows) | 99.0 % |
| still person 2.3-3.3 m behind the wall found (162 windows) | 98.8 % |

### Still or moving? (windows with a person)

Accuracy 48.0 %.

| true \ said | still | moving |
|---|---|---|
| still | 67 | 344 |
| moving | 12 | 262 |


## Model: with a left / centre / right head (ml/models/csi_nn_zone.npz)

Test set: 955 windows of 10 s, from people and empty rooms the network never saw in training.

### Is someone there?

The rover says PERSON when the network's P(person) is above 0.61, a threshold set on the validation set so that at most 10 % of empty rooms (fans included) raise a false alarm.

Accuracy 57.0 %.

| true \ said | no one | person |
|---|---|---|
| no one | 244 | 26 |
| person | 385 | 300 |

| case | result |
|---|---|
| empty room called empty | 90.4 % |
| empty room with an oscillating fan called a person (false alarm) | 1.0 % |
| empty room without a fan called a person (false alarm) | 14.8 % |
| moving person found | 86.9 % |
| still person (breathing only) found | 15.1 % |
| still person standing found | 17.0 % |
| still person lying on the floor found | 10.9 % |
| still person 0.5-1.4 m behind the wall found (144 windows) | 18.1 % |
| still person 1.4-2.3 m behind the wall found (105 windows) | 11.4 % |
| still person 2.3-3.3 m behind the wall found (162 windows) | 14.8 % |

### Still or moving? (windows with a person)

Accuracy 87.6 %.

| true \ said | still | moving |
|---|---|---|
| still | 366 | 45 |
| moving | 40 | 234 |

### Left, centre or right? (windows with a person)

Accuracy 30.1 % (chance is about 33 %).

| true \ said | left | centre | right |
|---|---|---|---|
| left | 66 | 79 | 92 |
| centre | 62 | 64 | 89 |
| right | 66 | 91 | 76 |

