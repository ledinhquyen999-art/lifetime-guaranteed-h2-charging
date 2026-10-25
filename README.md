# Lifetime-guaranteed online control of fast-charging stations with a hydrogen chain

Code and parameters for the paper

> D. Q. Le and M. Q. Duong, "Lifetime-guaranteed online control of fast-charging stations with a hydrogen chain under grid-connection limits," submitted to *IEEE Transactions on Smart Grid*, 2026.

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23643447.svg)](https://doi.org/10.5281/zenodo.23643447)

Software DOI: this release (v1.1) 10.5281/zenodo.23643447; all versions 10.5281/zenodo.23575343.

Corresponding author: Minh Quan Duong, The University of Danang – University of Science and Technology (dmquan@dut.udn.vn).

The controller is a Lyapunov drift-plus-penalty policy. It runs a fuel cell (FC), an electrolyzer (EL), an H<sub>2</sub> tank and a battery at fast-charging stations whose grid connection is smaller than their peak load. A health queue gives a lifetime guarantee that holds on **every data sequence**, with no forecasts: the stack lasts at least L(1 − Z<sub>max</sub>). The same queue can wrap any other controller, such as a trained DRL policy, as a safety shield.

## What is reproduced

`python reproduce_all.py` regenerates every number, figure and table of the paper from the raw data (about 25 h on a laptop; it can be resumed).

| Output | Content |
|---|---|
| `results/FINAL_summary.txt` | All numbers quoted in the paper; every lemma, proposition and corollary is checked numerically in each run |
| `results/paper_figures_final/bai_bao/` | Paper figures Fig. 1–5 (PDF vector + PNG 600 dpi; Fig. 1 also SVG) |
| `results/paper_figures_final/do_an/` | Additional figures (thesis) |
| `results/paper_tables/` | LaTeX tables (booktabs) |

## Data

All sources are public:

- **EV charging, 7 stations, Shenzhen, 5-min, 1 Sep 2022 – 28 Feb 2023:** UrbanEV (Li et al., *Sci. Data* 12:523, 2025; Dryad doi:10.5061/dryad.np5hqc04z).
- **Weather:** Open-Meteo historical API (ERA5 reanalysis; Zippenfenig, Zenodo doi:10.5281/zenodo.8112599).
- **FC calibration:** IEEE PHM Data Challenge 2014 (dataUBFC doi:10.25666/DATAUBFC-2021-07-19).
- **EL calibration:** Nguyen et al., Mendeley Data doi:10.17632/93jz2rgy4d.1.

The processed inputs used for the paper (`tier1_inputs.csv`, `scale20/35/50_inputs.csv`) are in `data_clean/`. The raw files are not redistributed. To rebuild the inputs from them, run `prepare_urbanev.py` and then `build_scale_inputs.py`. Do **not** re-run `calibrate_fc_ieee.py` unless you want to re-fit the efficiency curves; aging parameters are taken from the literature (see `NGUON_THONG_SO.txt`).

## Reference results

`results_reference/FINAL_summary.txt` and `results_reference/extra_summary.txt` are the raw outputs of the run used for the paper (25 Oct 2026). `RESULTS.md` lists the numbers quoted in the paper in English.

## Installation

Python 3.12 (tested on Windows 11 and Linux).

```
python -m pip install -r requirements.txt
```

The per-slot problems are solved with HiGHS. The 7-day clairvoyant MILP benchmark C* uses CPLEX if it is installed and falls back to HiGHS otherwise.

## Quick check (1 minute)

```
python step3_simulate.py --days 1 --tag check
```

`results/step3_check/summary.txt` must report `K2 hiệu chỉnh cuối kỳ: 16,111 CNY` and `ĐẠT` (pass) for every theoretical check.

## Main scripts

| Script | Role |
|---|---|
| `step3_simulate.py` | Proposed controller (S3), battery only (S1), Lyapunov without aging (B0); all theoretical checks |
| `step5_baselines.py` | MPC with forecasts or perfect 24-h knowledge, aging-budget MPC, rule-based |
| `step4_cstar.py` | Clairvoyant benchmark C* (MILP / LP) |
| `drl_ppo.py`, `run_drl.py` | PPO baseline and the health-queue shield |
| `run_extra.py` | Sensitivity of aging parameters, buffer θ<sub>Z</sub>, "price is not enough" (2 years), H<sub>2</sub> size ×2/×3, overload penalty, start-up price spread, forecast quality needed by MPC |
| `run_multiyear.py` | 5-year simulation with an aging plant |
| `grid33_eval.py`, `run_voltvar.py` | IEEE 33-bus AC evaluation, volt–var |
| `run_admm.py`, `run_scale.py` | Distributed ADMM, 20/35/50 charging nodes |
| `make_figures.py` → `hinh_bai.py`, `draw_system.py`, `bang_bai.py` | Figure data → figures (Fig. 2–5 and thesis figures); system diagram (Fig. 1); tables |

Comments and console messages are in Vietnamese; variable names follow the paper.

## Final configuration

w<sub>Z</sub> = 10<sup>10</sup>, V = 1, θ<sub>Z</sub> = 0.02, PV = 1× mean load, connection limit = 0.6 × the station's peak 5-min load over the data period, overload penalty 5 CNY/kWh (sensitivity 2, 3, 10 in `run_extra.py`), target lifetime 5 years.

FC aging parameters (Chen et al., *Appl. Energy* 2015; DOE Program Record 20001): start–stop 13.79 µV per cycle (prepaid at start-up), load change 0.0042 µV/kW, low power 8.662 µV/h, high power 10 µV/h, running 1.7 µV/h. EL aging: 4.8 µV/h (DOE) and 11.6 µV per shutdown (Rakousky et al., *J. Power Sources* 2017).

All sources are listed in `NGUON_THONG_SO.txt`.

## License and citation

MIT License (see `LICENSE`). Please cite the paper; see `CITATION.cff`. Changes since v1.0 are listed in `CHANGELOG.md`.
