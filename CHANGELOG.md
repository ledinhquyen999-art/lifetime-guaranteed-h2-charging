# Changelog

## v1.1 (October 2026) – version used for the IEEE TSG submission

### Model and parameters

- FC aging parameters now come only from cited sources:
  - start–stop 13.79 µV/cycle (Chen 2015, Table 1);
  - load change 0.0042 µV/kW. The value 1.79 µV/kW used in v1.0 had no source.
  - high-power 10 µV/h (Chen 2015). v1.0 used a fitted value of 22.77 µV/h.
  - running 1.7 µV/h (DOE Program Record 20001).
- EL shutdown aging 11.6 µV per shutdown (Rakousky 2017, Table 2).
- PV size changed from 2× to 1× mean load (main case); 2× and 3× are now sensitivity cases.
- Buffered health queue: Ẑ = max(Z − θ<sub>Z</sub>, 0) with θ<sub>Z</sub> = 0.02. Z<sub>max</sub> includes θ<sub>Z</sub>.
- `calibrate_fc_ieee.py` no longer overwrites the high-power aging rate. The fitted value is kept for reference only.

### New experiments

- MPC that may borrow the same aging allowance as the proposal (MPC-V, MPC-V*).
- C*-V clairvoyant LP benchmark.
- "Price is not enough": 2 years with a less durable stack, and a ×0.6 stack price.
- Sweep of the buffer θ<sub>Z</sub>.
- H<sub>2</sub> chain size ×2 and ×3.
- Health-queue shield wrapped around trained PPO policies, at standard and at stressed aging.
- Overload penalty 2, 3 and 10 CNY/kWh.
- Start-up price spread in the objective (1, 6, 72 slots; main 24).
- MPC with the same aging budget and forecasts of increasing quality (`step5_baselines.py --fc_blend`), with the realized forecast error logged.

### Outputs

- New figure pipeline: `make_figures.py` exports figure data, `hinh_bai.py` draws the paper and thesis figures, and `bang_bai.py` writes the LaTeX tables.
- `draw_system.py` draws the system diagram (Fig. 1) as PDF, PNG and editable SVG.
- `reproduce_all.py` runs all of them at the end.
- Fig. 3 marks end of life at the exact crossing of D = 1; Fig. 4(b) shows degradation relative to each station's own bound.
- `results_reference/` and `RESULTS.md` updated to this run; `CITATION.cff` lists both authors.

### Fixes

- `cstar.json`: the field `overload_MWh` is now in MWh (it was in kWh).
- `run_scale.py` no longer prints a hard-coded comparison from an older run.
- Comments clarified: the borrowing allowance of MPC-V equals Z<sub>max</sub>, which already includes θ<sub>Z</sub>.
