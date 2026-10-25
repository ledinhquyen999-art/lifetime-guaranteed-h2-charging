# Reference results (v1.1, run of 25 Oct 2026)

Every number below is taken from `results_reference/FINAL_summary.txt` and `results_reference/extra_summary.txt`, the raw output of `reproduce_all.py` and `run_extra.py`. The raw logs are in Vietnamese; this file gives the numbers in English.

Main configuration: w<sub>Z</sub> = 10<sup>10</sup>, V = 1, θ<sub>Z</sub> = 0.02, PV = 1× mean load, connection limit = 0.6 × station peak, overload penalty 5 CNY/kWh, target stack life 5 years. Costs (CNY) include stack aging at the stack price and are corrected for the energy left in battery and tank at the end of the period, unless stated otherwise. Station names: Station 1 = #1093, 2 = #1242, 3 = #1589 (with H<sub>2</sub> chain); 4 = #1061, 5 = #1087, 6 = #1214, 7 = #1229.

## Method names: paper ↔ code

| Paper | Code tag | Description |
|---|---|---|
| Battery only | `S1`, `--no_h2` | Lyapunov controller, battery only |
| Proposed | `S3_wZ1e10` | Proposed controller |
| Lyapunov without aging | `B0_noAging` | No aging price, no health queue |
| Rule-based | `B2_rule` | Surplus PV → EL, deficit → FC |
| MPC | `B1_mpc` | 24-h MPC, load forecast = 7-day same-hour mean, PV = yesterday |
| MPC\* | `B1_mpc_oracle` | 24-h MPC with perfect load/PV knowledge |
| MPC, aging budget δt (\*) | `B1_mpc_life`, `B1_mpc_life_or` | Cumulative aging budget in each 24-h plan |
| MPC, aging budget δt + Z<sub>max</sub> (\*) | `B1_mpc_borrow`, `B1_mpc_borrow_or` | Same aging budget as the proposal |
| PPO | `drl_ppo.py` | PPO (Stable-Baselines3), no inter-station sharing |
| C\* | `step4_cstar.py` | Clairvoyant LP lower bound |

## Main comparison, 30 days from 1 Nov 2022

| Method | Cost | vs battery only | Above limit (MWh) |
|---|---|---|---|
| Battery only | 777,270 | – | 74.8 |
| **Proposed** | **749,447** | **−3.6%** | **57.2** |
| MPC | 786,813 | +1.2% | 61.6 |
| MPC, budget δt + Z<sub>max</sub> | 785,642 | +1.1% | 61.4 |
| Lyapunov without aging | 852,617 | +9.7% | 54.4 |
| Rule-based | 900,635 | +15.9% | 65.8 |
| MPC\* | 726,954 | −6.5% | 53.4 |
| MPC\*, budget δt + Z<sub>max</sub> | 726,762 | −6.5% | 53.5 |
| C\* (LP lower bound) | 666,205 | −14.3% | 43.8 |

The proposal achieves 82% of the overload reduction of MPC\*.

## Six months (Sep 2022 – Feb 2023)

Battery only 4,197,969 CNY, 393.8 MWh; proposed 4,039,635 CNY (−3.8%), 297.0 MWh (−24.6%). Z<sub>max</sub> = 0.0357 at Station 3, so the guaranteed FC life is 5(1 − 0.0357) = 4.82 years.

## Five years (aging plant, controller updated daily)

FC degradation after 4.96 years: 0.363 / 0.604 / 0.572 (Stations 1/2/3), always below the guaranteed path. Lyapunov without aging reaches end of life after 0.60–0.66 years.

## Health-queue weight and buffer

- w<sub>Z</sub> = 10<sup>8</sup> … 10<sup>10</sup> (30 days): identical decisions and cost (−3.6%); guaranteed life: none, 2.32, 4.13, 4.64, 4.82 years.
- θ<sub>Z</sub> (6 months): 0 → −1.2%; 0.005 → −3.8%; 0.01, 0.02, 0.05 → −3.8%. Largest observed Z: 0.0086.
- Gap to the 7-day clairvoyant C\* (corrected cost): V = 0.1: 43.3–43.8%; 0.25: 25.2–25.6%; 0.5: 16.7–17.1%; 1: 8.4–8.7%.

## Price is not enough (k<sub>run</sub> = 8.5 µV/h, 2 years)

Peak health queue at Station 3: aging price only 0.0266, 0.0351, 0.0369, 0.0356 (exceeds Z<sub>max</sub> = 0.0357); health queue 0.0203 throughout.

## Shield around PPO (k<sub>run</sub> = 8.5 µV/h, 120 unseen days)

Worst FC degradation divided by its guaranteed bound δt + Z<sub>max</sub>: seed 0: 28 → 0.993 with the shield; seed 1: 2.74 → 0.998; seed 2: 0.41 → 0.41; proposal (no sharing): 0.85.

## Sensitivity (30 days, vs battery only: cost / energy above limit)

- Overload penalty 2 / 3 / 10 CNY/kWh: +0.5% / +0.2% / −11.3%; −3.1% / −11.8% / −27.9%.
- Start-up price spread N<sub>s</sub> = 1 / 6 / 24 / 72: −0.8% / −3.2% / −3.6% / −3.1%.
- Connection limit 0.5 / 0.7 / 0.8 × peak: −3.1% / −3.9% / −2.1%; −15.8% / −39.3% / −57.4%.
- PV × 2 / × 3: −5.9% / −8.5%.
- H<sub>2</sub> chain × 2 / × 3: −3.0% / +2.8%; −38.1% / −42.8%.
- MPC with the same aging budget and better forecasts (hourly station-level load nMAE): 10.4% → 739,535; 20.9% → 753,152; 31.3% → 769,938; 41.8% (history-based) → 785,642. Break-even with the proposal at about 18%.
- Model mismatch M1–M7: cost within −2.4% … +2.1%; tank always at least 12.8 kg above its minimum.
- Scale: N = 20 / 35 / 50 charging nodes: overload −29.9% / −30.8% / −31.1%; 30 / 54 / 83 ms per step.

All theoretical checks (every lemma, proposition and corollary) pass in all 84 runs of the main configuration.
