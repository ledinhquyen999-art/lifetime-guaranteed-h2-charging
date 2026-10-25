"""
HIỆU CHỈNH MÁY ĐIỆN PHÂN (EL) TỪ DỮ LIỆU THẬT
  Nguyen et al., "Effect of current ripple frequency on the degradation of PEM electrolysers",
  J. Power Sources (dữ liệu Mendeley 93jz2rgy4d). 4 cell PEM chạy 1000 h, gợn 50%:
  PEM1 = 300 Hz, PEM2 = DC thuần (CHUẨN), PEM3 = 600 Hz, PEM4 = 1200 Hz.

Giải nén bộ dữ liệu vào bất kỳ thư mục nào trong DATN2026 rồi chạy:
    python calibrate_el.py            # kịch bản chính: tốc độ già a0 theo DOE (stack thương mại), đường kWh/kg từ dữ liệu
    python calibrate_el.py --a0 lab   # kịch bản lão hóa mạnh: a0 đo từ cell phòng thí nghiệm (cho phân tích độ nhạy)
  (script tự tìm Figure4_IV_curves_raw, Figure6_Normal_voltage_raw, Paper1_fit_4param.csv)

Làm 4 việc:
  [1] Tốc độ tăng điện áp khi chạy ổn định (μV/h) của từng cell, từ log điện áp liên tục
  [2] Đường phân cực qua 9 lần đo (Initial, Cycle1–8): điện áp ở dòng làm việc tăng bao nhiêu
  [3] Tham số mô hình 4 thông số của tác giả (R_mem, alpha, i_0, I_lim): cơ chế nào già
  [4] Đường tiêu thụ điện HỆ EL (kWh/kg H2) theo tỉ lệ công suất x → thay số GIẢ ĐỊNH trong step3

Ghi:  DATN2026/results/calib_el/summary.txt
      DATN2026/params/el_calibration.json      (step3 tự dùng)
"""
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PROJECT_DIR = Path(__file__).resolve().parent
if not PROJECT_DIR.exists():
    PROJECT_DIR = Path(__file__).resolve().parent
OUT = PROJECT_DIR / "results" / "calib_el"; OUT.mkdir(parents=True, exist_ok=True)
PARAMS = PROJECT_DIR / "params"; PARAMS.mkdir(parents=True, exist_ok=True)

A0_SOURCE = "lab" if "--a0" in sys.argv and sys.argv[sys.argv.index("--a0") + 1].lower() == "lab" else "doe"
CELLS = {"PEM1": "300 Hz", "PEM2": "DC (chuẩn)", "PEM3": "600 Hz", "PEM4": "1200 Hz"}
REF = "PEM2"
KWH_PER_KG_PER_V = 2 * 96485.33 / 2.01588e-3 / 3.6e6     # = 26.59 kWh/kg cho mỗi 1 V điện áp cell (η_F = 1)
# ---- GIẢ ĐỊNH CẤP HỆ THỐNG (ghi rõ trong bài, chạy độ nhạy sau)
ETA_F = 0.98          # hiệu suất Faraday
AUX_FIXED = 0.03      # phụ trợ cố định = 3% công suất định mức (điều khiển, bơm tuần hoàn nước...)
AUX_PROP = 0.08       # phụ trợ tỉ lệ = 8% công suất stack (chỉnh lưu, làm khô H2...) – KHÔNG gồm máy nén (step3 tính riêng)
EL_X = [0.1, 0.3, 0.6, 1.0]
OLD_X, OLD_K = [0.1, 0.4, 1.0], [62.0, 53.0, 56.0]
L = []
log = lambda s="": (L.append(s), print(s))


def find_one(name_regex, want_dir=False):
    rx = re.compile(name_regex, re.I)
    for p in PROJECT_DIR.rglob("*"):
        if rx.fullmatch(p.name) and (p.is_dir() if want_dir else p.is_file()):
            return p
    return None


iv_dir = find_one(r"Figure4_IV_curves_raw", want_dir=True)
nv_dir = find_one(r"Figure6_Normal_voltage_raw", want_dir=True)
fit_csv = find_one(r"Paper1_fit_4param\.csv")
if iv_dir is None or nv_dir is None:
    raise SystemExit(f"Không thấy Figure4_IV_curves_raw / Figure6_Normal_voltage_raw trong {PROJECT_DIR}. Giải nén bộ dữ liệu EL vào DATN2026.")
log("HIỆU CHỈNH EL – Nguyen et al. (J. Power Sources), Mendeley 93jz2rgy4d – 4 cell PEM, 1000 h, gợn 50%")
log(f"Giả định cấp hệ thống: η_F = {ETA_F}, phụ trợ = {AUX_FIXED:.0%}·P_định mức + {AUX_PROP:.0%}·P_stack (máy nén tính riêng trong step3)")
log(f"Dữ liệu: {iv_dir}\n        {nv_dir}\n")


# ============================================================== khớp đường phân cực trơn: V = a + b·ln(I) + R·I
def fit_smooth(I, V):
    m = I >= 0.05
    X = np.column_stack([np.ones(m.sum()), np.log(I[m]), I[m]])
    coef, *_ = np.linalg.lstsq(X, V[m], rcond=None)
    rmse = float(np.sqrt(np.mean((X @ coef - V[m]) ** 2)))
    f = lambda i: coef[0] + coef[1] * np.log(np.maximum(i, 1e-4)) + coef[2] * i
    return f, coef, rmse


def num(df, col):
    return pd.to_numeric(df[col], errors="coerce")


# ============================================================== [1] log điện áp liên tục
def load_normal(cell):
    f = next(iter(sorted(nv_dir.rglob(f"{cell}_Normal_voltage*.csv"))), None)
    if f is None:
        return None
    cache = OUT / f"_cache_{cell}_hourly.csv"
    if cache.exists():
        return pd.read_csv(cache)
    d = pd.read_csv(f)
    d.columns = [c.strip() for c in d.columns]
    I, V = num(d, "current_A"), num(d, "voltage_V")
    ts = d["timestamp"]
    t = pd.to_datetime(ts, errors="coerce")
    if t.notna().mean() > 0.9:
        th = (t - t.dropna().iloc[0]).dt.total_seconds() / 3600
    else:                                              # dạng số (giây)
        x = pd.to_numeric(ts, errors="coerce")
        th = (x - x.dropna().iloc[0]) / 3600
    g = pd.DataFrame({"t_h": th, "I": I, "V": V}).dropna()
    I_op = float(g.loc[g["I"] > 0.5 * g["I"].max(), "I"].median())
    g = g[(g["I"] - I_op).abs() <= 0.05 * I_op]
    h = g.groupby(np.floor(g["t_h"])).agg(V=("V", "mean"), I=("I", "mean"), n=("V", "size")).reset_index()
    h = h[h["n"] >= 10]
    h["I_op"] = I_op
    h.to_csv(cache, index=False)
    return h


log("[1] LOG ĐIỆN ÁP LIÊN TỤC (~300 h đầu, ở dòng làm việc) – gồm cả phần TĂNG RỒI HỒI PHỤC sau mỗi lần dừng đo")
decay = {}
for c, desc in CELLS.items():
    h = load_normal(c)
    if h is None or len(h) < 10:
        log(f"  {c}: không có/thiếu log"); continue
    r = np.polyfit(h["t_h"], h["V"], 1)[0] * 1e6
    decay[c] = dict(rate=r, I_op=float(h["I_op"].iloc[0]), hours=float(h["t_h"].max()), V0=float(h["V"].iloc[:5].mean()),
                    V1=float(h["V"].iloc[-5:].mean()), t=h["t_h"].values, v=h["V"].values)
    log(f"  {c} ({desc:<10}): I_làm việc = {decay[c]['I_op']:.2f} A | {decay[c]['hours']:.0f} h log | "
        f"V {decay[c]['V0']:.4f} → {decay[c]['V1']:.4f} V | tăng {r:+.1f} μV/h")
if REF in decay:
    for c in decay:
        if c != REF:
            log(f"       {c}/{REF} = {decay[c]['rate'] / decay[REF]['rate']:.2f} (300 h đầu – chưa dùng để kết luận, xem [2])")

# ============================================================== [2] đường phân cực
def load_iv(cell):
    out = {}
    for f in sorted(iv_dir.rglob(f"{cell}_*.csv")):
        m = re.search(r"_(Initial|Cycle(\d+))\.csv$", f.name, re.I)
        if not m:
            continue
        k = 0 if m.group(1).lower() == "initial" else int(m.group(2))
        d = pd.read_csv(f); d.columns = [c.strip() for c in d.columns]
        d = pd.DataFrame({"I": num(d, "current_A"), "V": num(d, "voltage_V"), "s": num(d, "step_index")}).dropna()
        d = d[d["s"] > 0].groupby("s")[["I", "V"]].median().sort_values("I")   # trung vị: bỏ gai lúc chuyển bậc
        d = d[d["I"] > 1e-3]
        if len(d) >= 4:
            out[k] = (d["I"].values, d["V"].values)
    return out


# Khoảng cách giữa hai lần đo phân cực: tìm chỗ điện áp TỤT trong log (máy dừng để đo → hồi phục)
gaps = []
for c, d in decay.items():
    t, v = d["t"], d["v"]
    br = [t[k + 1] for k in range(len(t) - 1) if (v[k + 1] - v[k] < -0.004) or (t[k + 1] - t[k] > 1.5)]
    br = [b for j, b in enumerate(br) if j == 0 or b - br[j - 1] > 24]
    if len(br) >= 1:
        gaps += list(np.diff([0.0] + br))
T_CYC = float(np.median(gaps)) if gaps else 1000 / 8
if not (60 <= T_CYC <= 200):
    T_CYC = 1000 / 8
log(f"\n  Khoảng giữa hai lần đo phân cực (từ chỗ điện áp tụt/hồi phục trong log) ≈ {T_CYC:.0f} h → Cycle k ở ≈ k·{T_CYC:.0f} h")
log("  (Log liên tục chỉ có ~300 h vì giới hạn 1.048.575 dòng của Excel; tốc độ dài hạn lấy từ 9 đường phân cực bên dưới.)")

log("\n[2] ĐƯỜNG PHÂN CỰC (9 lần đo: Initial, Cycle1–8) – tốc độ dài hạn ~1000 h")
iv = {c: load_iv(c) for c in CELLS}
ivrate = {}
for c, curves in iv.items():
    if not curves:
        log(f"  {c}: không có file IV"); continue
    I_ref = decay.get(c, {}).get("I_op") or max(curves[0][0])
    ks = sorted(curves)
    vs = np.array([float(fit_smooth(*curves[k])[0](I_ref)) for k in ks])
    tk = np.array(ks, float) * T_CYC
    r_all = np.polyfit(tk, vs, 1)[0] * 1e6
    m = tk > 0
    r_post = np.polyfit(tk[m], vs[m], 1)[0] * 1e6 if m.sum() >= 3 else float("nan")
    ivrate[c] = dict(all=r_all, post=r_post, breakin=1e3 * (vs[1] - vs[0]) if len(vs) > 1 else float("nan"))
    log(f"  {c} ({CELLS[c]:<10}): V tại {I_ref:.2f} A = " + " ".join(f"{v:.3f}" for v in vs)
        + f" | tổng {1e3 * (vs[-1] - vs[0]):+.0f} mV | cả quá trình {r_all:.0f} μV/h | sau chạy rà (bỏ Initial→C1) {r_post:.0f} μV/h")
if REF in ivrate:
    log("  So với DC (sau chạy rà): " + ", ".join(f"{c}/{REF} = {ivrate[c]['post'] / ivrate[REF]['post']:.2f}"
                                             for c in ivrate if c != REF))

# ============================================================== [3] tham số 4 thông số
if fit_csv is not None:
    log("\n[3] THAM SỐ MÔ HÌNH CỦA TÁC GIẢ (đầu → cuối chiến dịch)")
    fp = pd.read_csv(fit_csv); fp.columns = [c.strip() for c in fp.columns]
    for c in CELLS:
        s = fp[fp["PEM"].astype(str).str.upper().str.replace(" ", "") == c]
        if len(s) < 2:
            continue
        a, b = s.iloc[0], s.iloc[-1]
        parts = []
        for k in ("R_mem", "alpha", "i_0", "I_lim"):
            if k in s.columns:
                x0, x1 = float(a[k]), float(b[k])
                parts.append(f"{k} {x0:.4g} → {x1:.4g} ({100 * (x1 / x0 - 1):+.0f}%)" if x0 else f"{k} {x0:.4g} → {x1:.4g}")
        log(f"  {c}: " + " | ".join(parts))
else:
    log("\n[3] (không thấy Paper1_fit_4param.csv – bỏ qua)")

# ============================================================== [4] đường tiêu thụ điện hệ EL
def sys_kwhkg(I, V, I_rated, dV=0.0):
    f, _, _ = fit_smooth(I, V)                       # dùng đường KHỚP TRƠN (dữ liệu đo có gai lúc chuyển bậc dòng)
    Ig = np.linspace(max(I.min(), 0.05, 0.02 * I_rated), I_rated, 2000)
    Vg = f(Ig) + dV
    Ps = Vg * Ig
    P_rated = float(f(I_rated) + dV) * I_rated
    Paux = AUX_FIXED * P_rated + AUX_PROP * Ps
    x = (Ps + Paux) / (P_rated * (1 + AUX_PROP) + AUX_FIXED * P_rated)     # tỉ lệ công suất điện HỆ
    kwh = KWH_PER_KG_PER_V * Vg / ETA_F * (Ps + Paux) / Ps                 # kWh điện hệ / kg H2
    return x, kwh


log("\n[4] ĐƯỜNG TIÊU THỤ ĐIỆN HỆ EL (kWh/kg H2, chưa gồm máy nén) – cell chuẩn " + REF)
if REF not in iv or 0 not in iv[REF]:
    raise SystemExit(f"Thiếu đường phân cực Initial của {REF}")
I0, V0c = iv[REF][0]
I_rated = min(decay.get(REF, {}).get("I_op", max(I0)), max(I0))
f0, coef0, rmse0 = fit_smooth(I0, V0c)
V_rated0 = float(f0(I_rated))
log(f"  khớp V = a + b·ln(I) + R·I cho {REF} Initial: a = {coef0[0]:.4f}, b = {coef0[1]:.4f}, R = {coef0[2]:.4f} Ω, sai số {1e3 * rmse0:.1f} mV")
xb, kb = sys_kwhkg(I0, V0c, I_rated)
xe, ke = sys_kwhkg(I0, V0c, I_rated, dV=0.1 * V_rated0)          # D = 1: điện áp tăng 10%
last = max(iv[REF]); xl, kl = sys_kwhkg(*iv[REF][last], I_rated)
k_bol = [float(np.interp(x, xb, kb)) for x in EL_X]
k_eol = [float(np.interp(x, xe, ke)) for x in EL_X]
k_end = [float(np.interp(x, xl, kl)) for x in EL_X]
D_GRID = [round(0.05 * k, 2) for k in range(21)]                            # bảng kWh/kg(x, D) cho Hệ quả 2 (việc 2.4)
k_D = []
for D in D_GRID:
    xd, kd = sys_kwhkg(I0, V0c, I_rated, dV=0.1 * V_rated0 * D)
    k_D.append([round(float(np.interp(x, xd, kd)), 4) for x in EL_X])
log(f"  Dòng định mức = dòng làm việc trong thí nghiệm = {I_rated:.2f} A | V cell định mức lúc mới = {V_rated0:.4f} V"
    f" → D = 1 khi tăng {100 * V_rated0:.0f} mV (10%)")
log("   x (tỉ lệ công suất hệ)   : " + "  ".join(f"{x:5.2f}" for x in EL_X))
log("   kWh/kg – lúc mới (D=0)   : " + "  ".join(f"{k:5.1f}" for k in k_bol))
log(f"   kWh/kg – sau Cycle{last}      : " + "  ".join(f"{k:5.1f}" for k in k_end))
log("   kWh/kg – hết đời (D=1)   : " + "  ".join(f"{k:5.1f}" for k in k_eol))
log(f"   (đường GIẢ ĐỊNH cũ: x={OLD_X} → {OLD_K} kWh/kg)")
pk = int(np.argmin(kb)); log(f"   tốt nhất {kb[pk]:.1f} kWh/kg tại x = {xb[pk]:.2f}  (hiệu suất LHV ≈ {33.33 / kb[pk]:.3f})")

log("\n[5] HỆ SỐ LÃO HÓA EL ĐƯA VÀO MÔ HÌNH")
a0_lab = ivrate.get(REF, {}).get("post", float("nan"))
if not np.isfinite(a0_lab):
    a0_lab = decay[REF]["rate"] if REF in decay else float("nan")
A0_DOE = 4.8
a0 = a0_lab if A0_SOURCE == "lab" else A0_DOE
log(f"  a0 đo được (cell DC, sau chạy rà) = {a0_lab:.1f} μV/h | DOE 2022 (stack thương mại) = {A0_DOE} μV/h")
log(f"  → ĐƯA VÀO MÔ HÌNH: a0 = {a0:.1f} μV/h  (nguồn: {'phòng thí nghiệm – kịch bản lão hóa mạnh' if A0_SOURCE == 'lab' else 'DOE – kịch bản chính; số phòng thí nghiệm dùng cho độ nhạy: --a0 lab'})")
log("  a_sd (mỗi lần tắt máy): GIỮ 10,4 μV theo NREL (bộ dữ liệu này không có chu kỳ bật/tắt)")
if np.isfinite(a0) and a0 > 0:
    log(f"  → chạy liên tục với a0 này: D = 1 sau ≈ {0.1 * V_rated0 * 1e6 / a0:,.0f} h"
        + (f"; với số phòng thí nghiệm chỉ ≈ {0.1 * V_rated0 * 1e6 / a0_lab:,.0f} h" if A0_SOURCE != "lab" and a0_lab > 0 else ""))

calib = {
    "source": "Nguyen et al., J. Power Sources – Mendeley 93jz2rgy4d (4 PEM cells, 1000 h, PEM2 = DC reference)",
    "assumptions": {"eta_F": ETA_F, "aux_fixed_frac": AUX_FIXED, "aux_prop_frac": AUX_PROP},
    "el_x": EL_X, "el_kwh_per_kg": [round(k, 2) for k in k_bol], "el_kwh_per_kg_eol": [round(k, 2) for k in k_eol],
    "D_grid": D_GRID, "el_kwh_per_kg_D": k_D,
    "aging_update": {"V_rated_cell_uV": round(V_rated0 * 1e6, 1), "a0_uV_per_h": round(float(a0), 2)},
    "a0_source": A0_SOURCE, "a0_lab_uV_per_h": round(float(a0_lab), 2), "a0_doe_uV_per_h": A0_DOE,
    "iv_rates_uV_h": {c: {k: round(float(v), 2) for k, v in r.items()} for c, r in ivrate.items()}, "cycle_interval_h": round(T_CYC, 1),
    "diagnostics": {c: {"rate_uV_h": round(float(d["rate"]), 2), "I_op_A": round(d["I_op"], 3), "hours": round(d["hours"], 1)}
                    for c, d in decay.items()},
}
(PARAMS / "el_calibration.json").write_text(json.dumps(calib, indent=2, ensure_ascii=False), encoding="utf-8")

# ============================================================== hình
plt.rcParams.update({"font.size": 9})
cols = {"PEM1": "tab:orange", "PEM2": "tab:blue", "PEM3": "tab:green", "PEM4": "tab:red"}
fig, ax = plt.subplots(figsize=(7, 3.8))
for c, d in decay.items():
    ax.plot(d["t"], d["v"], ".", ms=2, color=cols[c], alpha=.6, label=f"{c} {CELLS[c]}: {d['rate']:+.0f} μV/h")
ax.set_xlabel("thời gian (h)"); ax.set_ylabel("V cell ở dòng làm việc (V)"); ax.grid(alpha=.3); ax.legend(fontsize=7)
fig.tight_layout(); fig.savefig(OUT / "fig_el_voltage_rise.png", dpi=150); plt.close(fig)

fig, axs = plt.subplots(1, 4, figsize=(13, 3.4), sharey=True)
for a, c in zip(axs, CELLS):
    cm = plt.cm.viridis(np.linspace(0, 1, max(len(iv[c]), 1)))
    for col, k in zip(cm, sorted(iv[c])):
        a.plot(*iv[c][k], color=col, lw=1, label="Initial" if k == 0 else f"C{k}")
    a.set_title(f"{c} – {CELLS[c]}"); a.set_xlabel("I (A)"); a.grid(alpha=.3)
axs[0].set_ylabel("V cell (V)"); axs[0].legend(fontsize=6)
fig.tight_layout(); fig.savefig(OUT / "fig_el_polarization.png", dpi=150); plt.close(fig)

fig, ax = plt.subplots(figsize=(6, 3.8))
ax.plot(xb, kb, "-", color="tab:green", label="đo được – lúc mới (D=0)")
ax.plot(xl, kl, "-", color="tab:orange", label=f"đo được – sau Cycle{last}")
ax.plot(xe, ke, "--", color="tab:red", label="hết đời (D=1)")
ax.plot(EL_X, k_bol, "o", color="tab:green", label="điểm PWL đưa vào step3")
ax.plot(OLD_X, OLD_K, "s:", color="gray", label="đường giả định cũ")
ax.set_xlim(0, 1.05); ax.set_ylim(40, 90); ax.set_xlabel("tỉ lệ công suất hệ x"); ax.set_ylabel("kWh điện / kg H2")
ax.grid(alpha=.3); ax.legend(fontsize=7)
fig.tight_layout(); fig.savefig(OUT / "fig_el_consumption.png", dpi=150); plt.close(fig)

(OUT / "summary.txt").write_text("\n".join(L), encoding="utf-8")
print(f"\nĐã ghi: {OUT / 'summary.txt'}\n        {PARAMS / 'el_calibration.json'}\n        3 hình .png trong {OUT}")
