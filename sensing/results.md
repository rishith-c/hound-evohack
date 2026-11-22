# Sensing simulation results

120 trials per scenario (fresh trials after calibration).

| scenario | truth | person reported | labels |
|---|---|---|---|
| empty room | no person | 0% | NOTHING 100% |
| empty room + fan | no person | 2% | MACHINE-LIKE PERIODICITY 66%, NOTHING 28%, RF ACTIVITY 4%, BREATHING-LIKE PERIODICITY 2% |
| empty room + HVAC rumble | no person | 0% | NOTHING 100% |
| hot radiator, visible | no person | 0% | NOTHING 100% |
| warm laptop, visible | no person | 0% | NOTHING 100% |
| sunlit wall patch, visible | no person | 0% | NOTHING 100% |
| person visible 2 m standing | person | 100% | PERSON VISIBLE 100% |
| person visible 4 m lying | person | 100% | PERSON VISIBLE 100% |
| person visible, dark | person | 97% | PERSON VISIBLE 88%, BREATHING-LIKE PERIODICITY 5%, RF CORROBORATED 3%, NOTHING 3% |
| behind drywall 2 m standing | person | 49% | BREATHING-LIKE PERIODICITY 42%, NOTHING 26%, RF ACTIVITY 23%, RF CORROBORATED 8%, MACHINE-LIKE PERIODICITY 2% |
| behind drywall 3 m sitting | person | 12% | NOTHING 71%, RF ACTIVITY 18%, BREATHING-LIKE PERIODICITY 10%, RF CORROBORATED 2% |
| behind drywall 4 m lying | person | 1% | NOTHING 88%, RF ACTIVITY 11%, BREATHING-LIKE PERIODICITY 1% |
| behind drywall 3 m + fan | person | 34% | MACHINE-LIKE PERIODICITY 34%, BREATHING-LIKE PERIODICITY 27%, NOTHING 18%, RF ACTIVITY 14%, RF CORROBORATED 8% |
| behind drywall, CSI uncal. | person | 16% | NOTHING 62%, RF ACTIVITY 22%, BREATHING-LIKE PERIODICITY 15%, RF CORROBORATED 1% |

False alarm (person reported with nobody there): **0.4%** · detection behind drywall: **22%** · visible: **99%**

## Breathing detector vs modulation-to-noise ratio (P of breathing-like, conf ≥ 5)

| dwell s | MNR 0.5 | MNR 1.0 | MNR 1.5 | MNR 2.0 | MNR 3.0 | MNR 4.0 | MNR 6.0 | false alarm, empty |
|---|---|---|---|---|---|---|---|---|
| 15 | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 0% |
| 30 | 0% | 38% | 62% | 65% | 85% | 82% | 75% | 0% |
| 45 | 2% | 45% | 65% | 83% | 83% | 82% | 87% | 0% |

## Fan discrimination (regularity test)

| window | none | breathing-like | machine |
|---|---|---|---|
| fan only | 0% | 15% | 85% |
| person only | 0% | 99% | 1% |
| person + fan | 10% | 90% | 0% |

## Thermal blob detection vs range (P score ≥ 0.5)

| posture | 1 m | 2 m | 3 m | 4 m | 5 m | 6 m |
|---|---|---|---|---|---|---|
| stand | 100% | 100% | 100% | 100% | 100% | 100% |
| lie | 100% | 100% | 100% | 100% | 100% | 100% |
| false positives | radiator 0%, laptop 52%, sun 100% |

## Mission: 4 rooms, 9 stations × 60 s + 36 m travel → **10.5 min** of a 43 min pack (fits)
