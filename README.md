# Lifetime-Guaranteed Online Control of Hydrogen-Integrated EV Fast-Charging Stations

Code and processed data for the paper

> L. D. Quyen *et al.*, "Lifetime-Guaranteed Online Control of Hydrogen-Integrated EV Fast-Charging Stations under Distribution Congestion," submitted to *IEEE Transactions on Smart Grid*, 2026.

The controller is a prediction-free Lyapunov drift-plus-penalty scheme with virtual queues for the battery (B), the H2 tank (H) and the fuel-cell/electrolyzer health (Z). Start/stop degradation is prepaid at start-up, so switching a device off never ages it. This gives per-sample-path guarantees (no statistical assumptions) on tank and battery safety, a minimum stack lifetime L(1 − Z_max) and an efficiency floor, plus an O(1/V) optimality gap under i.i.d. data. The per-slot problem is a small MILP, solved centrally or by ADMM.

## Repository layout

| Path | Content |
|---|---|
| `step3_simulate.py` | Proposed controller (PROP), battery-only (BAT) and aging-unaware Lyapunov (LY-NA); plant model, ADMM, LinDistFlow voltage penalty, volt–var |
| `step4_cstar.py` | Clairvoyant benchmark C* (LP/MILP; CPLEX, Gurobi or HiGHS) |
| `step5_baselines.py` | Rule-based and four MPC baselines (forecast / perfect 24 h, with / without lifetime constraint) |
| `drl_ppo.py`, `run_drl.py` | PPO baseline (Stable-Baselines3) |
| `grid33_eval.py` | AC power-flow evaluation on the IEEE 33-bus feeder |
| `run_*.py` | Experiment runners (see table below) |
| `reproduce_all.py` | Runs every experiment of the paper and writes `results/FINAL_summary.txt` |
| `make_figures.py`, `draw_system.py` | All figures and tables of the paper → `results/paper_figures/` |
| `calibrate_fc_ieee.py`, `calibrate_el.py` | FC/EL efficiency and aging calibration from public measurement data |
| `prepare_urbanev.py`, `build_scale_inputs.py` | Build the 5-min input files from the UrbanEV dataset |
| `step2_check_theory.py`, `check_corollary2.py` | Stand-alone numerical checks of the theoretical results |
| `params/` | Station parameters and FC/EL calibration (JSON) |
| `data_clean/` | Processed 5-min inputs: 7 real stations (`tier1_inputs.csv`) and 20/35/50-node networks |
| `RESULTS.md` | All numbers of the paper in English, method-name mapping, glossary |
| `results_reference/` | Raw reference outputs: `FINAL_summary.txt` (from `reproduce_all.py`), `stress_summary.txt` (from `run_stress.py --six`) |

## Paper ↔ code

| Paper item | Script (stage of `reproduce_all.py`) |
|---|---|
| Table III (methods, 30 days), PPO rows | `run_batch.py`, `step4_cstar.py`, `step5_baselines.py` (B); `run_drl.py` (K) |
| Fig. 4 (price of guarantee, gap vs. V) | `run_tradeoff.py` (A), `plot_theorem1.py` (C) |
| Fig. 5 (5-year simulation) | `run_multiyear.py` (L) |
| Fig. 6 (sensitivity, model mismatch) | `run_sens44.py` (J), `run_mismatch.py` (G) |
| ADMM results | `run_admm.py` (H) |
| Fig. 7 (33-bus feeder, scale-up) | `run_overnight.py` (E), `run_voltvar.py` (F), `grid33_eval.py`, `run_scale.py` (I) |
| Fig. 8 (H2 vs. larger battery) | `run_battery_compare.py` (D) |
| Table IV (mis-priced aging) | `run_stress.py --six` (run separately) |
| Fig. 2 (calibration) | `calibrate_fc_ieee.py`, `calibrate_el.py` |

## Reproduce

Tested with Python 3.12 on Windows (Intel i5-1135G7 laptop, 8 GB RAM).

```bash
pip install -r requirements.txt
python reproduce_all.py            # all experiments; resumes if interrupted
python make_figures.py             # figures and LaTeX tables -> results/paper_figures/
python step3_simulate.py --days 1  # quick check (about 1 minute)
```

`reproduce_all.py --stages A,B` runs selected stages only; `--only_summary` rebuilds `results/FINAL_summary.txt` from existing results. The per-slot problem uses HiGHS by default, so no commercial solver is needed. C* was solved with CPLEX 22.2; `step4_cstar.py` falls back to HiGHS if CPLEX/Gurobi are not installed (slower, same LP).

Every run writes `results/step3_<tag>/summary.txt`, which checks each theoretical result (Lemmas 1–3, Propositions 1–2, Corollaries 1–2) at every time step and prints `ĐẠT` (pass) or `KHÔNG ĐẠT` (fail).

**Language.** Code comments and the raw console/summary outputs are in Vietnamese (the authors' working language). Every number reported in the paper is given in English in [`RESULTS.md`](RESULTS.md), which also maps the paper's method names to the code tags and contains a glossary of the Vietnamese terms that appear in the outputs (e.g. `ĐẠT` = pass, `KHÔNG ĐẠT` = fail). Variable names follow the paper's notation.

## Data sources and licenses

- EV charging load and prices: UrbanEV (H. Li *et al.*, *Sci. Data* 12, 523, 2025; Dryad doi:10.5061/dryad.np5hqc04z). The processed files in `data_clean/` are derived from it.
- FC degradation: IEEE PHM 2014 Data Challenge (FCLAB). EL: Mendeley Data doi:10.17632/93jz2rgy4d. Only the derived calibration (`params/*_calibration.json`) is included; download the raw data from the original sources to rerun the calibration scripts.
- Solar irradiance: <!-- TODO: NASA POWER / Open-Meteo, as cited in the paper -->

Please cite the original datasets when using them.

## Citation

See `CITATION.cff`. <!-- TODO: add the BibTeX entry and DOI after acceptance -->

## License

Code: MIT (see `LICENSE`). Processed data follow the licenses of the original datasets.
