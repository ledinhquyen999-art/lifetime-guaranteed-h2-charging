"""
HIỆU CHỈNH MÔ HÌNH PIN NHIÊN LIỆU (FC) TỪ DỮ LIỆU THẬT – IEEE PHM Data Challenge 2014 (FCLAB)
  FC1: stack 5 cell × 100 cm², chạy ổn định 0,70 A/cm² (70 A)          ~1150 h
  FC2: cùng loại stack, 70 A nhưng có gợn dòng (ripple) – tải "động"   ~1020 h
  Mỗi stack: đường phân cực (Pola) và phổ trở kháng (EIS 20/45/70 A) ở ~8 mốc thời gian.

Đặt file trong DATN2026 rồi chạy:   python calibrate_fc_ieee.py
  (lần đầu đọc Excel mất vài phút; lần sau dùng bản cache CSV nên nhanh)

Script này làm 5 việc:
  [1] Tốc độ sụt áp thật ở dòng định mức 70 A (μV/h/cell), tách phần MẤT VĨNH VIỄN và phần HỒI PHỤC ĐƯỢC
  [2] Đường phân cực V(J) mỗi mốc thời gian + khớp mô hình V = E0 − A·ln(1+J/j0) − R·J
  [3] EIS: điện trở ohm (tần số cao) và điện trở phân cực → cơ chế nào già đi
  [4] Đường hiệu suất HỆ FC η(x) theo tỉ lệ công suất x (thay số GIẢ ĐỊNH trong step3), lúc mới và lúc hết đời (D = 1)
  [5] Ghi params/fc_calibration.json để step3_simulate.py tự dùng

Ghi:  DATN2026/results/calib_fc_ieee/summary.txt   ← GỬI FILE NÀY CHO CLAUDE (kèm 4 hình .png nếu được)
      DATN2026/params/fc_calibration.json
      DATN2026/data_clean/fc_ieee/*.csv  (cache)
"""
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

PROJECT_DIR = Path(__file__).resolve().parent
if not PROJECT_DIR.exists():
    PROJECT_DIR = Path(__file__).resolve().parent
OUT = PROJECT_DIR / "results" / "calib_fc_ieee"; OUT.mkdir(parents=True, exist_ok=True)
CACHE = PROJECT_DIR / "data_clean" / "fc_ieee"; CACHE.mkdir(parents=True, exist_ok=True)
PARAMS = PROJECT_DIR / "params"; PARAMS.mkdir(parents=True, exist_ok=True)

N_CELL, AREA = 5, 100.0            # 5 cell, 100 cm² (mô tả bộ dữ liệu FCLAB)
I_NOM = 70.0                       # dòng định mức thí nghiệm (0,70 A/cm²)
E_LHV = 1.253                      # V – điện áp tương đương LHV của H2 (241,8 kJ/mol / 2F)
# ---- GIẢ ĐỊNH CẤP HỆ THỐNG (ghi rõ trong bài; chạy độ nhạy sau)
U_F = 0.95                         # hệ số sử dụng nhiên liệu khi có tuần hoàn anode/purge
AUX_FIXED = 0.02                   # phụ trợ cố định = 2% công suất định mức (điều khiển, quạt…)
AUX_PROP = 0.10                    # phụ trợ tỉ lệ = 10% công suất stack (máy nén khí, bơm…)
FC_X = [0.1, 0.25, 0.45, 0.7, 1.0] # các điểm tỉ lệ công suất HỆ (net) cho đường PWL trong step3
OLD_X, OLD_ETA = [0.1, 0.3, 0.6, 1.0], [0.40, 0.50, 0.47, 0.40]   # đường cũ đang giả định
L = []
log = lambda s="": (L.append(s), print(s))


# ============================================================== đọc file
def find(pattern):
    rx = re.compile(pattern, re.I)
    got = {}
    for p in PROJECT_DIR.rglob("*"):
        m = rx.fullmatch(p.name)
        if m and p.is_file():
            key = m.groups()[:-1]
            if key not in got or p.suffix.lower() == ".csv":     # trùng tên → ưu tiên csv (đọc nhanh)
                got[key] = p
    return got


def read_any(p):
    if p.suffix.lower() == ".csv":
        for sep, dec in ((";", ","), (",", "."), ("\t", ",")):
            try:
                df = pd.read_csv(p, sep=sep, decimal=dec, encoding="utf-8-sig")
                if df.shape[1] > 1:
                    return df
            except Exception:
                continue
        raise ValueError(f"không đọc được {p}")
    sheets = pd.read_excel(p, sheet_name=None, header=None)
    parts, cols = [], None
    for _, sh in sheets.items():
        sh = sh.dropna(how="all")
        if sh.empty:
            continue
        first = str(sh.iloc[0, 0])
        if not re.match(r"^-?[\d.,eE+]+$", first.strip()):       # dòng đầu là tiêu đề
            cols = [str(c) for c in sh.iloc[0]]
            sh = sh.iloc[1:]
        sh = sh.iloc[:, :len(cols)]
        sh.columns = cols[:sh.shape[1]]
        parts.append(sh)
    df = pd.concat(parts, ignore_index=True)
    return df.apply(pd.to_numeric, errors="coerce")


def col(df, prefix):
    for c in df.columns:
        if str(c).strip().lower().startswith(prefix.lower()):
            return c
    raise KeyError(f"không thấy cột bắt đầu bằng '{prefix}' trong {list(df.columns)[:10]}")


def load_ageing(fc):
    cache = CACHE / f"{fc}_ageing.csv"
    if cache.exists():
        return pd.read_csv(cache)
    files = {k: v for k, v in find(r"(FC[12])_Ageing_part(\d+)\.(xlsx|xls|csv)").items() if k[0] == fc}
    if not files:
        raise SystemExit(f"Không thấy file {fc}_Ageing_part*.xlsx/csv trong {PROJECT_DIR}")
    parts = []
    for k in sorted(files, key=lambda k: int(k[1])):
        print(f"   đọc {files[k].name} ...", flush=True)
        d = read_any(files[k])
        parts.append(pd.DataFrame({"t_h": d[col(d, "Time")], "U_stack": d[col(d, "Utot")], "I": d[col(d, "I (A)")]}))
    df = pd.concat(parts).dropna().sort_values("t_h").drop_duplicates("t_h").reset_index(drop=True)
    df.to_csv(cache, index=False)
    return df


def load_pola(fc):
    cache = CACHE / f"{fc}_pola.csv"
    if cache.exists():
        return pd.read_csv(cache)
    files = {k: v for k, v in find(r"(FC[12])_Pola_T(\d+)\.(xlsx|xls|csv)").items() if k[0] == fc}
    parts = []
    for k, p in files.items():
        d = read_any(p)
        parts.append(pd.DataFrame({"T_h": int(k[1]), "I": d[col(d, "I (A)")], "U_stack": d[col(d, "Ustack")]}).dropna())
    df = pd.concat(parts, ignore_index=True)
    df.to_csv(cache, index=False)
    return df


def load_eis(fc):
    cache = CACHE / f"{fc}_eis.csv"
    if cache.exists():
        return pd.read_csv(cache)
    files = {k: v for k, v in find(r"(FC[12])_EIS(\d+)A_(pre|post)pola_T(\d+)\.(xlsx|xls|csv)").items() if k[0] == fc}
    parts = []
    for k, p in files.items():
        try:
            d = read_any(p)
            if d.shape[1] < 3:
                raise ValueError(f"chỉ có {d.shape[1]} cột")
            parts.append(pd.DataFrame({"I": int(k[1]), "when": k[2], "T_h": int(k[3]),
                                       "f": pd.to_numeric(d.iloc[:, 0], errors="coerce"),
                                       "Zre": pd.to_numeric(d.iloc[:, 1], errors="coerce"),
                                       "Zim": pd.to_numeric(d.iloc[:, 2], errors="coerce")}).dropna())
        except Exception as e:
            log(f"  (bỏ file EIS {p.name}: {e})")
    df = pd.concat(parts, ignore_index=True)
    df.to_csv(cache, index=False)
    return df


# ============================================================== [1] tốc độ sụt áp ở 70 A
def decay_analysis(fc, ag, break_times=None):
    ag = ag.copy()
    ag["V"] = ag["U_stack"] / N_CELL
    nom = (ag["I"] - I_NOM).abs() <= 5.0                   # ±5 A: chứa cả gợn dòng của FC2
    dt = ag["t_h"].diff().fillna(0)
    # một "lần gián đoạn" = chuỗi điểm lệch 70 A kéo dài ≥ 0,05 h (dừng máy / đo phân cực / EIS)
    # hoặc mất số liệu > 0,1 h. Điểm lệch lẻ tẻ (nhiễu, gợn) chỉ bị loại, không cắt đoạn.
    off = ~nom
    run_id = (off != off.shift(fill_value=False)).cumsum()
    run_dur = ag.groupby(run_id)["t_h"].transform(lambda x: x.iloc[-1] - x.iloc[0] + 30 / 3600)
    long_off = off & (run_dur >= 0.05)
    brk = long_off | (dt > 0.1)
    seg_id = brk.cumsum()
    ag["seg"] = np.where(nom, seg_id, -1)
    n_stop = int((brk & ~brk.shift(fill_value=False)).sum())
    # trung vị theo giờ ở 70 A
    hr = ag[nom].groupby(np.floor(ag.loc[nom, "t_h"]))["V"].agg(["median", "size"])
    hr = hr[hr["size"] >= 20]
    th, vh = hr.index.values.astype(float), hr["median"].values
    r_total = -np.polyfit(th, vh, 1)[0] * 1e6
    # Log lão hóa liền mạch (không thấy chỗ dừng) → dùng các mốc đo phân cực (tên file Pola_T###) làm điểm gián đoạn.
    # Ở mỗi mốc, tìm trong ±12 h giờ có điện áp NHẢY LÊN mạnh nhất (hồi phục sau khi dừng để đo).
    segs, jumps = [], []
    bt = [b for b in (break_times or []) if b > 0]
    cuts = [th[0]]
    for b0 in bt:
        w = np.where((th >= b0 - 12) & (th <= b0 + 12))[0]
        if len(w) < 4:
            continue
        dv = np.diff(vh[w])
        k = w[int(np.argmax(dv)) + 1]                      # giờ đầu tiên sau cú nhảy
        before = vh[max(k - 3, 0):k].mean(); after = vh[k:k + 3].mean()
        jumps.append(dict(t=th[k], jump_mV=1e3 * (after - before)))
        cuts.append(th[k])
    cuts.append(th[-1] + 1)
    for c0, c1 in zip(cuts[:-1], cuts[1:]):
        m = (th >= c0) & (th < c1)
        if m.sum() < 8:
            continue
        segs.append(dict(t_start=c0, t_end=th[m][-1], V_start=vh[m][1:4].mean(), V_end=vh[m][-3:].mean()))
    segs = pd.DataFrame(segs, columns=["t_start", "t_end", "V_start", "V_end"])
    jumps = pd.DataFrame(jumps, columns=["t", "jump_mV"])
    # MẤT VĨNH VIỄN: xu hướng điện áp ĐẦU mỗi đoạn (ngay sau khi đã hồi phục)
    r_irr = -np.polyfit(segs["t_start"], segs["V_start"], 1)[0] * 1e6 if len(segs) >= 3 else float("nan")
    dur = segs["t_end"] - segs["t_start"]
    r_rev = float(np.average((segs["V_start"] - segs["V_end"]) / dur * 1e6, weights=dur)) if len(segs) else float("nan")
    if len(jumps):
        log(f"  {fc}: điện áp hồi phục sau mỗi lần dừng đo (mV/cell): " + ", ".join(f"{j.t:.0f} h: {j.jump_mV:+.1f}" for j in jumps.itertuples()))
    log(f"  {fc}: {ag['t_h'].iloc[-1]:.0f} h dữ liệu, {len(ag):,} dòng | V(70 A) đầu = {vh[:5].mean():.4f} V/cell, cuối = {vh[-5:].mean():.4f} V/cell")
    log(f"       số lần rời 70 A trong log: {n_stop} | số đoạn giữa các lần đo phân cực: {len(segs)}")
    log(f"       sụt áp TỔNG (hồi quy cả quá trình)       : {r_total:6.1f} μV/h/cell")
    log(f"       sụt áp MẤT VĨNH VIỄN (đầu mỗi đoạn)       : {r_irr:6.1f} μV/h/cell")
    log(f"       hồi phục TB mỗi lần dừng: {jumps['jump_mV'].mean() if len(jumps) else float('nan'):.1f} mV/cell")
    log(f"       sụt áp trong một đoạn (gồm phần hồi phục) : {r_rev:6.1f} μV/h/cell  → phần hồi phục được ≈ {r_rev - r_irr:5.1f} μV/h")
    return dict(t=th, v=vh, segs=segs, r_total=r_total, r_irr=r_irr, r_seg=r_rev, n_stop=n_stop,
                V0=float(vh[:5].mean()), hours=float(ag["t_h"].iloc[-1]))


# ============================================================== [2] đường phân cực
def bin_curve(g):
    g = g[g["I"] > 0.3].copy()
    g["Ib"] = (g["I"] / 2).round() * 2                      # gom theo bậc 2 A
    b = g.groupby("Ib").agg(I=("I", "median"), U=("U_stack", "median"))   # dùng dòng thật (trung vị) làm hoành độ
    return b["I"].values.astype(float), b["U"].values / N_CELL


def fit_pola(I, V):
    J = I / AREA
    best = None
    for j0 in np.logspace(-5, -1, 81):
        X = np.column_stack([np.ones_like(J), -np.log1p(J / j0), -J])
        coef, *_ = np.linalg.lstsq(X, V, rcond=None)
        rmse = float(np.sqrt(np.mean((X @ coef - V) ** 2)))
        if coef[1] > 0 and coef[2] > 0 and (best is None or rmse < best[0]):
            best = (rmse, j0, coef)
    rmse, j0, (E0, A, R) = best
    return dict(E0=E0, A=A, R=R, j0=j0, rmse=rmse)


def pola_analysis(fc, po):
    curves, rows = {}, []
    for T, g in sorted(po.groupby("T_h")):
        I, V = bin_curve(g)
        curves[T] = (I, V)
        f = fit_pola(I, V)
        v = {c: float(np.interp(c, I, V)) for c in (20, 45, 70, 100)}
        rows.append(dict(T_h=T, **{f"V@{c}A": v[c] for c in v}, **f))
    tab = pd.DataFrame(rows).sort_values("T_h")
    log(f"  {fc}: {len(tab)} đường phân cực ở T = {list(tab['T_h'])} h")
    log("       T(h)   V@20A   V@45A   V@70A  V@100A |   E0      A(Tafel)  R(Ω·cm²)  sai số khớp")
    for _, r in tab.iterrows():
        log(f"       {r['T_h']:4.0f}  {r['V@20A']:.4f}  {r['V@45A']:.4f}  {r['V@70A']:.4f}  {r['V@100A']:.4f} | {r['E0']:.4f}  {r['A']:.4f}   {r['R']:.4f}    {1e3 * r['rmse']:.1f} mV")
    rates = {c: -np.polyfit(tab["T_h"], tab[f"V@{c}A"], 1)[0] * 1e6 for c in (20, 45, 70, 100)}
    log("       tốc độ sụt áp theo đường phân cực (μV/h/cell): " + ", ".join(f"{c} A: {r:.1f}" for c, r in rates.items()))
    return curves, tab, rates


# ============================================================== [3] EIS
def eis_analysis(fc, ei):
    rows = []
    for (I, when, T), g in ei.groupby(["I", "when", "T_h"]):
        g = g.sort_values("f", ascending=False)
        if len(g) < 10:
            log(f"  (bỏ EIS {fc} {I} A {when} T{T}: chỉ {len(g)} điểm)"); continue
        hf = g[g["f"] >= 100]
        # điện trở ohm: phần thực tại điểm Zim đổi dấu ở tần số cao (nội suy), nếu không có thì Zre nhỏ nhất
        s = np.sign(hf["Zim"].values)
        idx = np.where(np.diff(s) != 0)[0]
        if len(idx):
            k = idx[0]; z1, z2 = hf["Zim"].values[k], hf["Zim"].values[k + 1]
            r1, r2 = hf["Zre"].values[k], hf["Zre"].values[k + 1]
            R_hf = r1 + (r2 - r1) * (0 - z1) / (z2 - z1)
        else:
            R_hf = float(hf["Zre"].min())
        R_lf = float(g.sort_values("f")["Zre"].iloc[:3].mean())
        asr = AREA / N_CELL                                   # Ω stack → Ω·cm² mỗi cell
        rows.append(dict(I=I, when=when, T_h=T, R_ohm=R_hf * asr, R_pol=(R_lf - R_hf) * asr))
    tab = pd.DataFrame(rows).sort_values(["I", "when", "T_h"])
    for I in sorted(tab["I"].unique()):
        t = tab[(tab["I"] == I) & (tab["when"] == "post")]
        if len(t) >= 2:
            d_ohm = 100 * (t["R_ohm"].iloc[-1] / t["R_ohm"].iloc[0] - 1)
            d_pol = 100 * (t["R_pol"].iloc[-1] / t["R_pol"].iloc[0] - 1)
            log(f"  {fc} EIS {I} A: R_ohm {t['R_ohm'].iloc[0]:.4f} → {t['R_ohm'].iloc[-1]:.4f} Ω·cm² ({d_ohm:+.0f}%), "
                f"R_pol {t['R_pol'].iloc[0]:.4f} → {t['R_pol'].iloc[-1]:.4f} Ω·cm² ({d_pol:+.0f}%)")
    pre = tab[(tab["I"] == 70) & (tab["when"] == "pre")].set_index("T_h")
    post = tab[(tab["I"] == 70) & (tab["when"] == "post")].set_index("T_h")
    common = pre.index.intersection(post.index)
    if len(common):
        dp = (post.loc[common, "R_pol"] - pre.loc[common, "R_pol"]).mean()
        log(f"  {fc} EIS 70 A trước/sau đo phân cực: R_pol thay đổi TB {dp:+.4f} Ω·cm² (âm = đo phân cực làm hồi phục)")
    return tab


# ============================================================== [4] đường hiệu suất hệ thống
def system_eta(I, V, P_rated_gross, dV=0.0):
    """η_sys tại các x_net trong FC_X. dV: sụt áp đều mọi dòng (mô phỏng D>0)."""
    Ig = np.linspace(max(I.min(), 0.5), I.max(), 2000)
    Vg = np.interp(Ig, I, V) - dV
    Ps = Vg * Ig                                            # W mỗi cell
    Pn = Ps * (1 - AUX_PROP) - AUX_FIXED * P_rated_gross
    Pn_rated = P_rated_gross * (1 - AUX_PROP - AUX_FIXED)
    eta_stack = U_F * Vg / E_LHV
    eta_sys = eta_stack * np.where(Ps > 0, Pn / Ps, 0)
    xs = Pn / Pn_rated
    ok = np.maximum.accumulate(xs) == xs                    # phần P tăng theo I
    out = []
    for x in FC_X:
        if x > xs[ok].max() + 1e-9:
            out.append(float("nan"))
        else:
            out.append(float(np.interp(x, xs[ok], eta_sys[ok])))
    return out, xs[ok], eta_sys[ok]


# ============================================================== chạy
log("HIỆU CHỈNH FC TỪ IEEE PHM DATA CHALLENGE 2014 (FCLAB) – stack 5 cell × 100 cm², định mức 70 A (0,70 A/cm²)")
log(f"Giả định cấp hệ thống: U_f = {U_F}, phụ trợ = {AUX_FIXED:.0%}·P_định mức + {AUX_PROP:.0%}·P_stack, E_LHV = {E_LHV} V\n")
res = {}
log("[1] TỐC ĐỘ SỤT ÁP Ở 70 A (log lão hóa)")
for fc in ("FC1", "FC2"):
    po_T = sorted(load_pola(fc)["T_h"].unique())
    res[fc] = {"decay": decay_analysis(fc, load_ageing(fc), break_times=po_T)}
log("\n[2] ĐƯỜNG PHÂN CỰC")
for fc in ("FC1", "FC2"):
    res[fc]["curves"], res[fc]["pola"], res[fc]["pola_rates"] = pola_analysis(fc, load_pola(fc))
log("\n[3] PHỔ TRỞ KHÁNG (EIS) – điện trở mỗi cell")
for fc in ("FC1", "FC2"):
    try:
        res[fc]["eis"] = eis_analysis(fc, load_eis(fc))
    except Exception as e:
        log(f"  {fc}: bỏ qua EIS ({e})"); res[fc]["eis"] = None

log("\n[4] ĐƯỜNG HIỆU SUẤT HỆ FC (thay đường giả định trong step3)")
c1 = res["FC1"]["curves"]; T_first, T_last = min(c1), max(c1)
I0, V0c = c1[T_first]
V_rated0 = float(np.interp(I_NOM, I0, V0c))
P_rated = V_rated0 * I_NOM
eta_bol, xb, eb = system_eta(I0, V0c, P_rated)
eta_eol, xe, ee = system_eta(I0, V0c, P_rated, dV=0.1 * V_rated0)       # D = 1: sụt 10% điện áp định mức
I1, V1c = c1[T_last]
eta_end, xn, en = system_eta(I1, V1c, P_rated)
D_GRID = [round(0.05 * k, 2) for k in range(21)]                           # bảng η(x, D) cho Hệ quả 2 (việc 2.4)
eta_D = [[round(e, 5) for e in system_eta(I0, V0c, P_rated, dV=0.1 * V_rated0 * D)[0]] for D in D_GRID]
log(f"  V_cell định mức (70 A, FC1 T={T_first} h) = {V_rated0:.4f} V  →  D = 1 khi sụt {100 * V_rated0:.1f} mV (10%)")
log("   x (tỉ lệ công suất hệ) : " + "  ".join(f"{x:5.2f}" for x in FC_X))
log("   η hệ – lúc mới (D=0)   : " + "  ".join(f"{e:5.3f}" for e in eta_bol))
log(f"   η hệ – FC1 sau {T_last} h  : " + "  ".join(f"{e:5.3f}" for e in eta_end))
log("   η hệ – hết đời (D=1)   : " + "  ".join(f"{e:5.3f}" for e in eta_eol))
log("   (đường GIẢ ĐỊNH cũ     : x=" + ",".join(map(str, OLD_X)) + " → η=" + ",".join(map(str, OLD_ETA)) + ")")
pk = int(np.argmax(eb)); log(f"   η đỉnh = {eb[pk]:.3f} tại x = {xb[pk]:.2f}")

log("\n[5] HỆ SỐ LÃO HÓA ĐƯA VÀO MÔ HÌNH (đơn vị μV/cell)")
d1, d2 = res["FC1"]["decay"], res["FC2"]["decay"]
k_hp = d1["r_irr"] if np.isfinite(d1["r_irr"]) else d1["r_total"]
ratio = d2["r_total"] / d1["r_total"]
log(f"  k_hp (chạy công suất cao, ổn định) = {k_hp:.1f} μV/h  ← FC1, phần mất vĩnh viễn   (Chen 2015 dùng 10 μV/h)")
log(f"  Hệ số 'tải động' FC2/FC1 = {ratio:.2f}  → dùng cho phân tích độ nhạy (gợn dòng tần số cao làm già nhanh hơn)")
log("  k_ss, k_lc, k_lo: GIỮ theo Chen, Pei & Song 2015 (bộ IEEE không có chu kỳ bật/tắt hay tải thấp có chủ đích)")
life_h = 0.1 * V_rated0 * 1e6 / k_hp
log(f"  → nếu chạy liên tục ở định mức: D = 1 sau ≈ {life_h:,.0f} h. Stack phòng thí nghiệm già nhanh hơn stack thương mại tĩnh tại;")
log("    trong bài ghi rõ đây là kịch bản BẢO THỦ (lão hóa mạnh) – kết luận về điều khiển càng chắc nếu đúng ở kịch bản này.")

calib = {
    "source": "IEEE PHM Data Challenge 2014, FCLAB Research Federation (FC1 steady, FC2 ripple); 5-cell 100 cm2 PEMFC, nominal 0.70 A/cm2",
    "assumptions": {"U_f": U_F, "aux_fixed_frac": AUX_FIXED, "aux_prop_frac": AUX_PROP, "E_LHV_V": E_LHV},
    "fc_x": FC_X, "fc_eta_sys": [round(e, 4) for e in eta_bol], "fc_eta_sys_eol": [round(e, 4) for e in eta_eol],
    "D_grid": D_GRID, "fc_eta_sys_D": eta_D,
    "aging_update": {"V_rated_cell_uV": round(V_rated0 * 1e6, 1), "k_hp_uV_per_h": round(float(k_hp), 2)},
    "diagnostics": {fc: {"r_total_uV_h": round(float(res[fc]["decay"]["r_total"]), 2),
                         "r_irreversible_uV_h": round(float(res[fc]["decay"]["r_irr"]), 2),
                         "r_within_segment_uV_h": round(float(res[fc]["decay"]["r_seg"]), 2),
                         "pola_rates_uV_h": {str(k): round(float(v), 2) for k, v in res[fc]["pola_rates"].items()},
                         "hours": round(res[fc]["decay"]["hours"], 1)} for fc in ("FC1", "FC2")},
    "dynamic_stress_ratio_FC2_over_FC1": round(float(ratio), 3),
}
(PARAMS / "fc_calibration.json").write_text(json.dumps(calib, indent=2, ensure_ascii=False), encoding="utf-8")

# ============================================================== hình
plt.rcParams.update({"font.size": 9})
fig, ax = plt.subplots(1, 2, figsize=(10, 3.8), sharey=True)
for a, fc in zip(ax, ("FC1", "FC2")):
    cs = res[fc]["curves"]; cmap = plt.cm.viridis(np.linspace(0, 1, len(cs)))
    for c, T in zip(cmap, sorted(cs)):
        a.plot(cs[T][0] / AREA, cs[T][1], color=c, lw=1.2, label=f"{T} h")
    a.set_title(f"{fc} – đường phân cực"); a.set_xlabel("J (A/cm²)"); a.grid(alpha=.3); a.legend(fontsize=7)
ax[0].set_ylabel("V cell (V)")
fig.tight_layout(); fig.savefig(OUT / "fig_ieee_polarization.png", dpi=150); plt.close(fig)

fig, ax = plt.subplots(figsize=(7, 3.8))
for fc, c in (("FC1", "tab:blue"), ("FC2", "tab:red")):
    d = res[fc]["decay"]
    ax.plot(d["t"], d["v"], ".", ms=2, color=c, alpha=.5, label=f"{fc} trung vị mỗi giờ ở 70 A")
    if len(d["segs"]):
        ax.plot(d["segs"]["t_start"], d["segs"]["V_start"], "o", color=c, mfc="none", label=f"{fc} đầu mỗi đoạn (sau hồi phục)")
    ax.plot(d["t"], np.polyval(np.polyfit(d["t"], d["v"], 1), d["t"]), "-", color=c, lw=1,
            label=f"{fc} tổng {d['r_total']:.0f} μV/h, vĩnh viễn {d['r_irr']:.0f} μV/h")
ax.set_xlabel("thời gian (h)"); ax.set_ylabel("V cell ở 70 A (V)"); ax.grid(alpha=.3); ax.legend(fontsize=7)
fig.tight_layout(); fig.savefig(OUT / "fig_ieee_voltage_decay.png", dpi=150); plt.close(fig)

fig, ax = plt.subplots(1, 2, figsize=(10, 3.6))
for fc, c in (("FC1", "tab:blue"), ("FC2", "tab:red")):
    t = res[fc]["eis"]
    if t is None:
        continue
    for I, ls in ((20, ":"), (45, "--"), (70, "-")):
        s = t[(t["I"] == I) & (t["when"] == "post")]
        ax[0].plot(s["T_h"], s["R_ohm"], ls, marker="o", ms=3, color=c, label=f"{fc} {I} A")
        ax[1].plot(s["T_h"], s["R_pol"], ls, marker="o", ms=3, color=c, label=f"{fc} {I} A")
ax[0].set_title("Điện trở ohm (tần số cao)"); ax[1].set_title("Điện trở phân cực (thấp − cao)")
for a in ax:
    a.set_xlabel("thời gian (h)"); a.set_ylabel("Ω·cm² mỗi cell"); a.grid(alpha=.3); a.legend(fontsize=6, ncol=2)
fig.tight_layout(); fig.savefig(OUT / "fig_ieee_eis.png", dpi=150); plt.close(fig)

fig, ax = plt.subplots(figsize=(6, 3.8))
ax.plot(xb, eb, "-", color="tab:green", label="đo được – lúc mới (D=0)")
ax.plot(xn, en, "-", color="tab:orange", label=f"đo được – FC1 sau {T_last} h")
ax.plot(xe, ee, "--", color="tab:red", label="hết đời (D=1, sụt 10%)")
ax.plot(FC_X, eta_bol, "o", color="tab:green", label="điểm PWL đưa vào step3")
ax.plot(OLD_X, OLD_ETA, "s:", color="gray", label="đường giả định cũ")
ax.set_xlim(0, 1.05); ax.set_ylim(0.30, 0.56); ax.set_xlabel("tỉ lệ công suất hệ x"); ax.set_ylabel("hiệu suất hệ FC (LHV)")
ax.grid(alpha=.3); ax.legend(fontsize=7)
fig.tight_layout(); fig.savefig(OUT / "fig_fc_efficiency.png", dpi=150); plt.close(fig)

(OUT / "summary.txt").write_text("\n".join(L), encoding="utf-8")
print(f"\nĐã ghi: {OUT / 'summary.txt'}\n        {PARAMS / 'fc_calibration.json'}\n        4 hình .png trong {OUT}")
