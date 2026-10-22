# Reference results (English)

All numbers below are copied from `results_reference/FINAL_summary.txt`, the raw output of `reproduce_all.py` (generated 2026-10-19, main configuration `w_Z = 1e10`, `V = 1`). The raw log is in Vietnamese; this file gives every number used in the paper in English. A glossary of the Vietnamese terms in the raw outputs is at the end.

Data: 7 real fast-charging stations in Shenzhen (UrbanEV), 5-min steps; stations #1093, #1242 and #1589 have the H2 chain. Costs in CNY include stack-replacement cost (aging × stack price) and are **corrected for end-of-horizon storage** (energy left in battery/tank valued at the mean purchase price) unless stated otherwise.

## Method names: paper ↔ code

| Paper | Code tag / flag | Description |
|---|---|---|
| BAT | `S1`, `--no_h2` | Battery only (Lyapunov with battery queue) |
| PROP | `S3_wZ1e10` | Proposed controller, `w_Z = 1e10` |
| PROP′ | `S3_wZ3e8` | Proposed, `w_Z = 3e8` |
| LY-NA | `B0_noAging`, `--no_aging` | Full Lyapunov without aging (no μ, no Z queue) |
| RULE | `B2_rule` | Rule-based (surplus PV → EL, deficit → FC) |
| MPC | `B1_mpc` | 24-h MPC, forecast = 7-day same-hour mean |
| MPC* | `B1_mpc_oracle` | 24-h MPC with perfect load/PV forecast |
| MPC-L, MPC-L* | `B1_mpc_life`, `B1_mpc_life_or` | As above plus hard lifetime budget in the window |
| PPO | `drl_ppo.py` | PPO (Stable-Baselines3), no inter-station sharing |
| C* | `step4_cstar.py` | Clairvoyant LP lower bound (CPLEX) |
| BAT_ns, PROP_ns | `S1b`, `S3b`, `--no_share` | No inter-station sharing (for comparison with PPO) |

## 1. Method comparison – 30 days from 2022-11-01 (paper Table III)

C* = 581,403 CNY (LP relaxation, lower bound).

| Method | Cost (CNY) | vs BAT | Gap to C* | Overload (MWh) | vs BAT | FC life at observed rate (yr, worst station) | Guarantee |
|---|---:|---:|---:|---:|---:|---:|---|
| BAT | 711,323 | – | +22.3% | 73.4 | – | – | – |
| **PROP** | **679,847** | **−4.4%** | **+16.9%** | **59.7** | **−18.6%** | **6.6** | **≥ 4.92 yr** |
| PROP′ (`w_Z = 3e8`) | 676,952 | −4.8% | +16.4% | 58.1 | −20.8% | 5.8 | ≥ 2.42 yr |
| LY-NA | 1,010,228 | +42.0% | +73.8% | 52.4 | −28.6% | 0.2 | none |
| RULE | 836,716 | +17.6% | +43.9% | 60.0 | −18.2% | 1.3 | none |
| MPC | 735,328 | +3.4% | +26.5% | 57.2 | −22.1% | 1.2 | none |
| MPC* | 664,252 | −6.6% | +14.2% | 50.3 | −31.4% | 1.9 | none |
| MPC-L | 739,140 | +3.9% | +27.1% | 70.1 | −4.4% | 4.9 | in window only |
| MPC-L* | 685,342 | −3.7% | +17.9% | 63.5 | −13.5% | 4.9 | in window only |

No inter-station sharing (uncorrected cost, because the PPO environment has no sharing):

| Method | Cost (CNY) | vs BAT_ns | Overload (MWh) | vs BAT_ns | FC starts |
|---|---:|---:|---:|---:|---:|
| BAT_ns | 824,806 | – | 74.1 | – | – |
| PROP_ns | 786,414 | −4.7% | 60.4 | −18.5% | 81 |
| PPO (mean of 3 seeds) | 877,106 ± 34,436 | +6.3% | 83.9 | +13.2% | 5 |

PPO seeds 0/1/2: 924,825 / 844,823 / 861,670 CNY; trained on Sep–Oct 2022, model selected on the validation week 25–31 Oct 2022.

## 2. Price of the guarantee (paper Fig. 4a)

6 months (2022-09-01 → 2023-02-28). BAT: 3,786,973 CNY, overload 384.9 MWh.

| `w_Z` | Cost (CNY) | vs BAT | Overload (MWh) | vs BAT | FC Z_max | Guaranteed FC life L(1−Z_max) | Observed FC life |
|---|---:|---:|---:|---:|---:|---:|---:|
| 3e8 | 3,536,533 | −6.6% | 298.0 | −22.6% | 0.5161 | 2.42 yr | 6.3 yr |
| 1e9 | 3,576,921 | −5.5% | 311.8 | −19.0% | 0.1557 | 4.22 yr | 6.8 yr |
| 3e9 | 3,600,306 | −4.9% | 318.5 | −17.2% | 0.0527 | 4.74 yr | 7.1 yr |
| **1e10** | **3,603,105** | **−4.9%** | **319.4** | **−17.0%** | **0.0167** | **4.92 yr** | **7.3 yr** |

30 days (from 2022-11-01), `V = 1`: cost vs BAT −4.7% (`w_Z = 1e8`, Z_max = 1.546, no guarantee), −4.8% (3e8), −4.5% (1e9), −4.6% (3e9), −4.4% (1e10). With `w_Z = 1e10`: `V = 0.25` → +12.6%, `V = 0.5` → +5.7% vs BAT.

## 3. Optimality gap vs. V (paper Fig. 4b, Theorem 1)

7 days from 2022-11-01, `w_Z = 1e10`. C* (MILP, CPLEX) ∈ [154,433; 155,366] CNY (solver gap 0.60%); the LP value 154,290 is 0.09% below the MILP lower bound.

| V | Cost (CNY) | Gap to C* [low; high] | Guaranteed FC life |
|---:|---:|---|---:|
| 0.1 | 208,625 | [34.3%; 35.1%] | 4.95 yr |
| 0.25 | 197,085 | [26.9%; 27.6%] | 4.94 yr |
| 0.5 | 186,584 | [20.1%; 20.8%] | 4.93 yr |
| 1 | 167,167 | [7.6%; 8.2%] | 4.92 yr |

## 4. Five-year simulation (paper Fig. 5)

10 × the 6-month data (4.96 yr), plant ages with the smooth (PCHIP) efficiency curves at the true D, controller updates its curves daily.

| | #1093 | #1242 | #1589 |
|---|---:|---:|---:|
| PROP: FC degradation D after 4.96 yr | 0.289 | 0.368 | 0.678 |
| PROP: min. distance below the Prop. 2 bound | 0.0076 | 0.0075 | 0.0176 |
| PROP: FC efficiency at 45% load (start → end) | 50.4% → 49.0% | 50.4% → 48.6% | 50.4% → 47.1% |
| LY-NA: end of life (D = 1) reached after | 0.22 yr | 0.22 yr | 0.19 yr |

Annual cost: PROP 7.21–7.25 × 10⁶ CNY/yr; LY-NA 11.40–11.52 × 10⁶ CNY/yr (21–26 stack replacements per station), so PROP is about 37% cheaper per year. All efficiency values stay above the Corollary 2 floor.

## 5. Model mismatch (paper Fig. 6b) – 30 days

Plant: smooth PCHIP curves at the true D. Cost change is relative to the exact-model run (678,245 CNY, uncorrected).

| Case | Controller model | Cost change | e^M FC / EL (% of m_max) | Min. tank margin to bottom / top (kg) |
|---|---|---:|---|---|
| M1 | calibration points, daily update | −0.06% | 0.6 / 0.7 | 15.3 / 1.35 |
| M2 | 2 segments | +0.98% | 1.2 / 1.0 | 16.4 / 1.35 |
| M3 | 1 segment | +0.89% | 3.9 / 2.7 | 15.5 / 1.35 |
| M4 | plant half-aged (D = 0.5), controller uses new curves | +1.00% | 6.3 / 4.8 | 14.1 / 1.35 |
| M5 | as M4, daily update | +1.29% | 0.8 / 0.7 | 14.5 / 1.35 |
| M6 | plant biased +10% (more H2 per kWh FC, less from EL) | +1.87% | 7.9 / 10.0 | 14.3 / 1.35 |
| M7 | plant biased −10% | −1.85% | 9.6 / 9.1 | 18.0 / 1.36 |

M1 over 6 months: +0.06%. All theoretical checks pass in every case.

## 6. Sensitivity – 30 days (paper Fig. 6a)

PROP vs BAT re-run under the same assumption.

| Parameter | Value | Cost vs BAT | Overload vs BAT | FC life (yr) |
|---|---|---:|---:|---:|
| baseline | – | −4.4% | −18.6% | 6.6 |
| compressor energy | 2.0 / 3.2 kWh/kg | −4.3% / −4.5% | −18.1% / −19.0% | 6.6 |
| FC stack price | ×0.6 / ×1.3 | −4.3% / −3.7% | −15.9% / −16.8% | 6.3 / 6.6 |
| EL stack price | ×0.3 | −5.1% | −18.0% | 6.6 |
| sharing limit | 150 / 600 kW | −4.7% / −4.6% | −19.2% / −19.2% | 6.6 |
| battery wear | 0.02 / 0.10 CNY/kWh | −4.1% / −4.3% | −17.5% / −17.9% | 6.6 |
| transformer limit | 0.5 / 0.7 / 0.8 × peak | −4.3% / −3.9% / −0.8% | −13.7% / −24.9% / −19.4% | 6.6 / 6.6 / 7.5 |
| PV size | ×1 / ×3 | −2.3% / −6.3% | −16.8% / −19.1% | 6.6 |

## 7. Distributed ADMM

7 days, 7 stations (cost relative to the centralized solve, 169,151 CNY):

| ℓ_max | ρ | Cost vs centralized | Steps converged (≤ 2 kW mismatch) | Mean iterations | Mean ε / abs(J*) | Max ε |
|---:|---:|---:|---:|---:|---:|---:|
| 3 | 1e-3 | +1.06% | 13.0% | 2.8 | 2.71% | 80.7 |
| 10 | 1e-3 | +0.90% | 40.8% | 7.6 | 0.93% | 32.0 |
| 30 | 1e-3 | +0.27% | 88.8% | 13.0 | 0.53% | 9.5 |
| 30 | 3e-4 | +0.03% | 82.4% | 14.9 | 0.34% | 8.2 |
| 30 | 3e-3 | +0.83% | 95.2% | 8.4 | 1.58% | 18.4 |

The largest ε (80.7, in units of J) raises the FC Z_max by at most ε/(w_Z δ) = 0.004, i.e. ≤ 0.02 yr of guaranteed life.

Larger networks (2 days, ℓ_max = 30, ρ = 1e-3): cost vs centralized −0.64% / +0.99% / +2.09% for N = 20 / 35 / 50.

## 8. Scale-up – 30 days (paper Fig. 7b, c)

Charging nodes = UrbanEV traffic zones; 30% largest nodes have H2; each node shares with its 3 nearest nodes.

| N | Mean / max solve time per 5-min step | Cost vs BAT | Overload vs BAT | FC life (yr) |
|---:|---|---:|---:|---:|
| 20 | 0.030 / 0.13 s | −1.0% | −15.4% | 6.5 |
| 35 | 0.051 / 0.23 s | −2.3% | −15.5% | 6.6 |
| 50 | 0.072 / 0.31 s | −2.7% | −18.8% | 6.6 |

## 9. IEEE 33-bus feeder, AC power flow – 6 months (paper Fig. 7a)

Base load × 0.55, charging stations × 0.35, pf 0.98. Power-flow solver checked against pandapower (error 3.2e-9 p.u.).

| Configuration | Hours with a bus < 0.95 p.u. | Undervoltage sum (p.u.·h) | Line-overload hours | Losses (MWh) |
|---|---:|---:|---:|---:|
| BAT, no grid awareness | 2176.2 | 58.49 | 3549.1 | 218.6 |
| PROP, grid-aware (LinDistFlow penalty) | 1968.1 (−9.6%) | 54.05 (−7.6%) | 3604.8 | 218.3 |
| BAT, grid-aware + volt–var | 980.1 (−55.0%) | 19.76 (−66.2%) | 3615.2 | 199.7 |
| PROP, grid-aware + volt–var | 910.2 (−58.2%) | 15.94 (−72.7%) | 3699.6 (+4.2%) | 199.3 (−8.8%) |

## 10. H2 chain vs. a larger battery – 30 days (paper Fig. 8)

Without H2 sales: PROP reduces overload by 18.6%; the same reduction needs about 1,820 kWh of extra battery (×1.96 of the existing 1,890 kWh at the three H2 stations), i.e. 0.98–1.82 × 10⁶ CNY at 540–1000 CNY/kWh, versus 3.06–9.35 × 10⁶ CNY for the full H2 system and 1.13–2.51 × 10⁶ CNY for the FC alone.

With H2 sales to FCEVs (demand = rated EL output, external H2 price 60 CNY/kg; configurations without H2 buy all H2 externally): PROP cost −5.4% and overload −14.3% vs BAT; break-even extra battery 1,376 kWh.

## 12. Mis-priced aging: the health queue vs. the aging price alone (paper Table IV)

The controller uses a wrong FC stack price in its objective (×1 = correct, ×0.3, ×0 = aging price ignored); reported cost uses the true price. `w_Z = 1e6` makes the health queue practically inactive (Z_max ≫ 1, no guarantee) = "aging price only". Output of `run_stress.py --six` (`results_reference/stress_summary.txt`).

| Horizon | `w_Z` | Stack price used | Cost vs BAT | Overload vs BAT | FC starts (3 stations) | Observed FC life | Guaranteed |
|---|---:|---|---:|---:|---:|---:|---:|
| 30 days | 1e6 | correct | −4.5% | −23.5% | 156 | 2.5 yr | none |
| 30 days | 1e6 | ×0.3 | −4.0% | −24.4% | 183 | 2.4 yr | none |
| 30 days | 1e6 | ×0 | −3.3% | −24.5% | 191 | 2.2 yr | none |
| 30 days | 1e10 | correct | −4.4% | −18.6% | 77 | 6.6 yr | 4.92 yr |
| 30 days | 1e10 | ×0.3 | −4.0% | −17.0% | 82 | 6.3 yr | 4.92 yr |
| 30 days | 1e10 | ×0 | +2.1% | −0.5% | 93 | 4.9 yr | 4.92 yr |
| 6 months | 1e10 | correct | −4.9% | −17.0% | 333 | 7.3 yr | 4.92 yr |
| 6 months | 1e6 | ×0 | −4.6% | −23.7% | 703 | 2.7 yr | none |
| 6 months | 1e10 | ×0 | +1.6% | −3.2% | 529 | 5.0 yr | 4.92 yr |

On a finite horizon of T steps, Proposition 2 allows aging above the target rate by Z_max/T, so the worst observed life it permits is 2.48 yr (30 days) and 4.28 yr (6 months); all `w_Z = 1e10` runs are above it.

## 11. Theory checks

Every run checks Lemmas 1–3, Propositions 1–2 and Corollaries 1–2 at every 5-min step. All 76 runs with `w_Z = 1e10` pass (`ĐẠT hết`).

## Glossary of Vietnamese terms in the raw outputs

| Vietnamese | English |
|---|---|
| ĐẠT / KHÔNG ĐẠT / ĐẠT hết | pass / fail / all pass |
| Bổ đề, Mệnh đề, Hệ quả, Định lý | Lemma, Proposition, Corollary, Theorem |
| chi phí; K2 hiệu chỉnh cuối kỳ | cost; cost corrected for end-of-horizon storage |
| vượt MBA (vượt giới hạn máy biến áp) | transformer overload |
| giờ vượt; tải MBA lớn nhất | overload hours; peak transformer loading |
| bồn; cách đáy / cách đỉnh | H2 tank; margin to lower / upper limit |
| pin | battery |
| tuổi thọ (dự kiến / bảo đảm / quan sát) | lifetime (projected / guaranteed / observed) |
| lão hóa; hàng đợi sức khỏe | degradation (aging); health queue Z |
| bật (FC bật n lần) | start-up (number of FC starts) |
| sai lệch mô hình | model mismatch |
| độ nhạy | sensitivity |
| lưới; nút; thiếu áp; tổn thất; quá tải dây | grid; bus; undervoltage; losses; line overload |
| mở rộng | scale-up |
| hội tụ; vòng | converged; iterations |
| so với; giảm; tăng | relative to; decrease; increase |
| năm; ngày; tháng | year; day; month |
| trạm; điểm sạc | station; charging node |
| không H2; đề xuất; quy tắc; biết trước | battery only; proposed; rule-based; perfect foresight |
