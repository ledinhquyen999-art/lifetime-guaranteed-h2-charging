"""
HÌNH VÀ BẢNG CHO BÀI BÁO (IEEE Trans. Smart Grid) – vẽ từ results/ đã khóa (FINAL_summary.txt), không mô phỏng lại gì.
Đặt trong DATN2026 rồi chạy:
    python make_figures.py                 # tất cả hình + bảng (~1–3 phút)
    python make_figures.py --only fig05    # một hình
    python make_figures.py --usetex        # chữ bằng LaTeX thật (cần MiKTeX/TeX Live); mặc định dùng phông Times + STIX (giống hệt IEEE)
Ghi vào results/paper_figures/:
    figXX_*.pdf  (vector, nhúng phông – dùng trong LaTeX)   figXX_*.png (600 dpi – dùng trong Word/slide đồ án)
    data/figXX_*.csv (số liệu đúng của từng hình – tạp chí hay yêu cầu, và để tự kiểm)
    tab_*.tex (bảng LaTeX dạng booktabs)    README.txt (danh sách, hình nào cho mục nào)
Quy ước trình bày (chuẩn IEEE): rộng 1 cột = 3,5 in, 2 cột = 7,16 in; chữ 8 pt (trục, chú thích 7 pt); không tiêu đề trong hình
(tiêu đề nằm ở caption LaTeX); ô con đánh (a), (b); mỗi phương pháp MỘT màu + MỘT kiểu điểm cố định trong mọi hình;
bảng màu an toàn cho người mù màu (Okabe–Ito) + kiểu điểm/nét khác nhau → in trắng đen vẫn phân biệt được.
"""
import argparse
import json
import re
import sys
from argparse import Namespace
from pathlib import Path

import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

HERE = Path(__file__).resolve().parent
PROJECT_DIR = Path(__file__).resolve().parent
if not PROJECT_DIR.exists():
    PROJECT_DIR = HERE
RES = PROJECT_DIR / "results"

ap = argparse.ArgumentParser()
ap.add_argument("--wz", default="1e10", help="w_Z cấu hình chính")
ap.add_argument("--only", default="", help="ví dụ fig03,fig05,tab (mặc định: tất cả)")
ap.add_argument("--usetex", action="store_true")
ap.add_argument("--out", default="paper_figures")
ap.add_argument("--b30", default="batch_2022-11-01_30d")
ap.add_argument("--b7", default="batch_2022-11-01_7d")
ap.add_argument("--b6", default="batch_2022-09-01_181d")
ap.add_argument("--my_suffix", default="", help=argparse.SUPPRESS)      # chỉ để thử code với mô phỏng nhiều năm ngắn
ap.add_argument("--chunks", type=int, default=10, help=argparse.SUPPRESS)
args = ap.parse_args()
WZ = args.wz
SFX = "" if WZ == "3e8" else f"_wz{WZ}"
B30, B7, B6 = args.b30, args.b7, args.b6
OUT = RES / args.out
DATA = OUT / "data"
DATA.mkdir(parents=True, exist_ok=True)
ONLY = [s.strip() for s in args.only.split(",") if s.strip()]
want = lambda key: not ONLY or any(key.startswith(o) for o in ONLY)

# ============================================================================ phong cách chung
COL1, COL2 = 3.5, 7.16                       # in (IEEE)
plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "Times", "Nimbus Roman", "STIXGeneral", "DejaVu Serif"],
    "mathtext.fontset": "stix",
    "font.size": 8, "axes.labelsize": 8, "axes.titlesize": 8,
    "xtick.labelsize": 7, "ytick.labelsize": 7, "legend.fontsize": 7,
    "axes.linewidth": 0.6, "lines.linewidth": 1.1, "lines.markersize": 4,
    "xtick.direction": "in", "ytick.direction": "in", "xtick.major.size": 2.5, "ytick.major.size": 2.5,
    "xtick.major.width": 0.6, "ytick.major.width": 0.6, "xtick.minor.visible": False,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": "0.90", "grid.linewidth": 0.4,
    "legend.frameon": False, "legend.handlelength": 1.6, "legend.borderaxespad": 0.3, "legend.columnspacing": 1.0,
    "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none",
    "savefig.dpi": 600, "savefig.bbox": "tight", "savefig.pad_inches": 0.02,
    "axes.unicode_minus": True,
})
if args.usetex:
    plt.rcParams.update({"text.usetex": True, "font.family": "serif", "text.latex.preamble": r"\usepackage{newtxtext,newtxmath}"})

# mỗi phương pháp: màu (Okabe–Ito, đã kiểm mù màu bằng validator; cặp sát nhau có thêm kiểu điểm khác nhau), kiểu điểm, rỗng/đặc, nhãn
M = {
    "S3":     dict(c="#D55E00", m="o", fill=True, lab="Proposed (guaranteed)"),
    "S1":     dict(c="#0072B2", m="s", fill=True, lab="Battery only (no H$_2$)"),
    "B0":     dict(c="#CC79A7", m="v", fill=True, lab="Lyapunov w/o aging"),
    "rule":   dict(c="#E69F00", m="D", fill=True, lab="Rule-based"),
    "mpc":    dict(c="#009E73", m="^", fill=True, lab="MPC (forecast)"),
    "mpc_or": dict(c="#009E73", m="^", fill=False, lab="MPC (perfect 24 h)"),
    "mpcL":   dict(c="#56B4E9", m=">", fill=True, lab="MPC + life constr."),
    "mpcL_or": dict(c="#56B4E9", m=">", fill=False, lab="MPC + life, perfect 24 h"),
}
ST_C = ["#0072B2", "#E69F00", "#009E73"]     # 3 trạm có H2
INK, MUTED = "0.15", "0.45"
PANEL = dict(fontsize=8, fontweight="bold", va="top", ha="left")


def panel(ax, s, *_, **__):
    """Nhãn ô con kiểu IEEE: chữ đậm, sát góc trái phía trên khung (không đè nhãn trục)."""
    ax.set_title(s, loc="left", fontsize=8, fontweight="bold", pad=3)


def save(fig, name, frames=None):
    for ext in ("pdf", "png"):
        fig.savefig(OUT / f"{name}.{ext}")
    plt.close(fig)
    for k, df in (frames or {}).items():
        df.to_csv(DATA / f"{name}_{k}.csv", index=True, float_format="%.6g")
    print(f"  ✓ {name}.pdf / .png", flush=True)


def skip(name, why):
    print(f"  – bỏ qua {name}: {why}", flush=True)


# ============================================================================ đọc kết quả
sys.path.insert(0, str(PROJECT_DIR))
import step3_simulate as S  # noqa: E402

PARAMS = json.loads((PROJECT_DIR / "params" / "params_tier1.json").read_text(encoding="utf-8"))
S.apply_fc_calibration(PARAMS, Namespace(no_fc_calib=False, no_el_calib=False))
for nm, x, v, sg in (("fc", S.FC_X, S.FC_ETA, +1), ("el", S.EL_X, S.EL_KWHKG, -1)):
    if nm not in S.CAL:
        S.CAL[nm] = S._table(x, v, None, None, None, sg)
H2 = [int(s["station_id"]) for s in PARAMS["stations"] if s.get("has_h2")]
L_TARGET = PARAMS["aging_and_devices"]["fc"]["life_target_h"] / 8760
ALLIN = pd.read_csv(PROJECT_DIR / "data_clean" / "tier1_inputs.csv", index_col=0, parse_dates=True)
PCOL = [c for c in ALLIN.columns if c.startswith("price_")]
_ST = {}


def num(pat, s, d=float("nan")):
    m = re.search(pat, s)
    return float(m.group(1).replace(",", "")) if m else d


def _stations(t0, t1):
    if (t0, t1) not in _ST:
        ev = ALLIN.loc[t0:t1]
        st, _ = S.prepare(PARAMS, ev, 1.0, 1e10, pv_scale=2.0, export_frac=0.0, V_REF=1.0, tr_frac=0.6, no_h2=False)
        _ST[(t0, t1)] = (st, float(ev[PCOL].to_numpy().mean()))
    return _ST[(t0, t1)]


def R(tag, tier1=True):
    """Chỉ số một lần chạy. cost = K2 HIỆU CHỈNH cuối kỳ (giống FINAL_summary)."""
    d = RES / f"step3_{tag}"
    f = d / "summary.txt"
    if not f.exists():
        return None
    s = f.read_text(encoding="utf-8")
    raw = num(r"K2 – chi phí \(gồm giá lão hóa\): ([\d,]+) CNY", s)
    cor = num(r"K2 hiệu chỉnh cuối kỳ: ([\d,]+) CNY", s)
    if cor != cor and tier1 and (d / "timeseries.csv").exists():
        cols = pd.read_csv(d / "timeseries.csv", nrows=0).columns
        ts = pd.read_csv(d / "timeseries.csv", usecols=[cols[0]] + [c for c in cols if c[:2] in ("E_", "M_")], index_col=0, parse_dates=True)
        st, pb = _stations(ts.index[0], ts.index[-1])
        vE = sum((ts[f"E_{i}"].iloc[-1] - ts[f"E_{i}"].iloc[0]) * st[i]["eta_dis"] for i in st if f"E_{i}" in ts)
        vM = sum((ts[f"M_{i}"].iloc[-1] - ts[f"M_{i}"].iloc[0]) * st[i]["eta_peak"] * S.LHV for i in st if f"M_{i}" in ts)
        cor = raw - pb * (vE + vM)
    lf = [float(x) for x in re.findall(r"tuổi thọ dự kiến theo tốc độ kỳ này: FC ([\d.]+|inf) năm", s)]
    zm = [float(x) for x in re.findall(r"Bổ đề 3 – trạm \d+: max Z_FC = [\d.e+-]+ \(≤ ([\d.e+-]+)", s)]
    return dict(cost=cor if cor == cor else raw, raw=raw, ov=num(r"vượt giới hạn MBA ([\d.]+) MWh", s),
                life=min(lf) if lf else float("inf"), zmax=max(zm) if zm else float("nan"),
                t=num(r"Thời gian giải: TB ([\d.]+) s/bước", s), tmax=num(r"Thời gian giải: TB [\d.]+ s/bước, max ([\d.]+) s", s),
                ok="KHÔNG ĐẠT" not in s, txt=s)


def ts(tag, cols_pred=None):
    f = RES / f"step3_{tag}" / "timeseries.csv"
    if not f.exists():
        return None
    cols = pd.read_csv(f, nrows=0).columns
    use = [cols[0]] + [c for c in cols if cols_pred is None or cols_pred(c)]
    return pd.read_csv(f, usecols=use, index_col=0, parse_dates=True)


def cstar(name):
    f = RES / name / "cstar.json"
    if not f.exists():
        return None
    j = json.loads(f.read_text(encoding="utf-8"))
    return j["C_star"], (j.get("lower_bound") or j["C_star"]), j.get("mode", "?")


eta_fc = lambda D, x: np.asarray(S._pchip("fc", float(min(max(D, 0.0), 1.0)))[0](x))
kwh_el = lambda D, x: np.asarray(S._pchip("el", float(min(max(D, 0.0), 1.0)))[0](x))
kfmt = FuncFormatter(lambda v, _: f"{v / 1e3:,.0f}")
print(f"[*] w_Z = {WZ}; đọc từ {RES}; ghi vào {OUT}", flush=True)

# ============================================================================ Fig. 2 – hiệu chỉnh FC / EL
if want("fig02"):
    fig, ax = plt.subplots(1, 2, figsize=(COL1, 1.55), gridspec_kw=dict(wspace=0.55))
    x = np.linspace(0.1, 1.0, 200)
    blues = ["#9ECAE1", "#4292C6", "#08519C"]          # tuần tự một màu: D tăng → đậm hơn
    rows = {}
    for D, c in zip((0.0, 0.5, 1.0), blues):
        ax[0].plot(x, 100 * eta_fc(D, x), c=c, lw=1.1, label=f"$D={D:g}$")
        ax[1].plot(x, kwh_el(D, x), c=c, lw=1.1, label=f"$D={D:g}$")
        rows[f"fc_eta_pct_D{D:g}"] = 100 * eta_fc(D, x); rows[f"el_kwh_per_kg_D{D:g}"] = kwh_el(D, x)
    xf, vf = S.curve_at("fc", 0.0); xe, ve = S.curve_at("el", 0.0)
    ax[0].plot(xf, 100 * vf, "o", ms=3, mfc="white", mec=blues[2], mew=0.8, label="calibration")
    ax[1].plot(xe, ve, "o", ms=3, mfc="white", mec=blues[2], mew=0.8)
    ax[0].set_xlabel("FC load $P/\\bar P$"); ax[0].set_ylabel("FC system efficiency (%)")
    ax[1].set_xlabel("EL load $P/\\bar P$"); ax[1].set_ylabel("EL energy (kWh/kg)")
    ax[0].legend(loc="lower center", ncol=1, fontsize=6, handlelength=1.2)
    panel(ax[0], "(a)", -0.38); panel(ax[1], "(b)", -0.38)
    save(fig, "fig02_calibration", {"curves": pd.DataFrame(rows, index=pd.Index(x, name="load_frac"))})

# ============================================================================ Fig. 3 – một ngày vận hành
if want("fig03"):
    s3t, s1t = f"{B30}_S3_wZ{WZ}", f"{B30}_S1"
    a, b = ts(s3t), ts(s1t)
    if a is None or b is None:
        skip("fig03", f"thiếu step3_{s3t} hoặc step3_{s1t}")
    else:
        i = max(H2, key=lambda k: b[f"ov_{k}"].sum())                       # trạm H2 quá tải nhiều nhất
        day = b[f"ov_{i}"].groupby(b.index.date).sum().idxmax()             # ngày S1 quá tải nặng nhất
        sl = slice(pd.Timestamp(day), pd.Timestamp(day) + pd.Timedelta(hours=23, minutes=55))
        A, Bd = a.loc[sl], b.loc[sl]
        sm = lambda v: v.rolling(3, center=True, min_periods=1).mean()          # trung bình trượt 15 phút cho dễ đọc (ghi trong caption)
        hrs = (A.index - A.index[0]).total_seconds() / 3600
        ovm = (a[f"trflow_{i}"] - a[f"ov_{i}"])[a[f"ov_{i}"] > 1e-6]
        Ptr = float(ovm.median()) if len(ovm) else float(a[f"trflow_{i}"].quantile(0.95))
        fig, ax = plt.subplots(4, 1, figsize=(COL1, 4.4), sharex=True, gridspec_kw=dict(hspace=0.32, height_ratios=[1.3, 1, 0.75, 0.65]))
        ax[0].fill_between(hrs, 0, sm(A[f"load_{i}"]), color="0.87", lw=0, label="EV load")
        ax[0].plot(hrs, sm(Bd[f"trflow_{i}"]), c=M["S1"]["c"], lw=0.9, label="battery only")
        ax[0].plot(hrs, sm(A[f"trflow_{i}"]), c=M["S3"]["c"], lw=1.2, label="proposed")
        ax[0].axhline(Ptr, c=INK, ls="--", lw=0.7, label="transformer limit")
        ax[0].set_ylabel("Transformer flow (kW)")
        ax[0].legend(loc="lower left", bbox_to_anchor=(0.0, 1.10), ncol=4, fontsize=6, handlelength=1.3, columnspacing=0.8)
        ax[1].plot(hrs, sm(A[f"Pfc_{i}"]), c="#D55E00", lw=1.1, label="FC")
        ax[1].plot(hrs, -sm(A[f"Pel_{i}"]), c="#0072B2", lw=1.1, label="EL (as −)")
        ax[1].plot(hrs, sm(A[f"dis_{i}"] - A[f"ch_{i}"]), c="0.5", lw=0.8, label="battery (dis. +)")
        ax[1].axhline(0, c="0.6", lw=0.5); ax[1].set_ylabel("Power (kW)")
        ax[1].legend(loc="lower left", bbox_to_anchor=(0.12, 0.98), ncol=3, fontsize=6, handlelength=1.3, columnspacing=0.8)
        ax[2].plot(hrs, A[f"M_{i}"], c="#009E73", lw=1.1); ax[2].set_ylabel("H$_2$ tank (kg)")
        ax[3].plot(hrs, 1e3 * A[f"Zfc_{i}"], c="#CC79A7", lw=1.1); ax[3].set_ylabel("$Z^{\\rm FC}$ ($\\times10^{-3}$)")
        ax[3].set_xlabel(f"Hour of {pd.Timestamp(day):%d %b %Y} (station #{i})"); ax[3].set_xlim(0, 24); ax[3].set_xticks(range(0, 25, 4))
        for k, s_ in enumerate("abcd"):
            panel(ax[k], f"({s_})")
        fig.align_ylabels(ax)
        out = pd.DataFrame({"hour": hrs, "load_kW": A[f"load_{i}"].values, "grid_S1_kW": Bd[f"trflow_{i}"].values,
                            "grid_S3_kW": A[f"trflow_{i}"].values, "P_tr_kW": Ptr, "Pfc_kW": A[f"Pfc_{i}"].values,
                            "Pel_kW": A[f"Pel_{i}"].values, "bat_net_kW": (A[f"dis_{i}"] - A[f"ch_{i}"]).values,
                            "M_kg": A[f"M_{i}"].values, "Zfc": A[f"Zfc_{i}"].values})
        save(fig, "fig03_operation_day", {"series": out.set_index("hour")})

# ============================================================================ Fig. 4 – giá của bảo đảm + Định lý 1
if want("fig04"):
    rows6, rows30 = [], []
    s16, s130 = R(f"{B6}_S1"), R(f"{B30}_S1")
    for w in ("3e8", "1e9", "3e9", "1e10"):
        r = R(f"{B6}_S3_wZ{w}")
        if r and s16:
            rows6.append(dict(wz=w, life=L_TARGET * (1 - r["zmax"]), save=100 * (1 - r["cost"] / s16["cost"]), ovred=100 * (1 - r["ov"] / s16["ov"])))
    for w in ("1e8", "3e8", "1e9", "3e9", "1e10"):
        r = R(f"{B30}_S3_wZ{w}")
        if r and s130:
            rows30.append(dict(wz=w, life=L_TARGET * (1 - r["zmax"]), save=100 * (1 - r["cost"] / s130["cost"]), ovred=100 * (1 - r["ov"] / s130["ov"])))
    vr = []
    cs7 = cstar("cstar_2022-11-01_7d")
    for d in sorted(RES.glob(f"step3_{B7}_S3_wZ{WZ}_V*")):
        mv = re.search(r"_V([\d.]+)$", d.name)
        r = R(d.name[len("step3_"):])
        if mv and r and cs7:
            vr.append(dict(V=float(mv.group(1)), cost=r["cost"], gap_lo=100 * (r["cost"] / cs7[0] - 1), gap_hi=100 * (r["cost"] / cs7[1] - 1),
                           life=L_TARGET * (1 - r["zmax"])))
    if not rows6 and not rows30:
        skip("fig04", "thiếu các lần chạy quét w_Z (run_tradeoff.py)")
    else:
        fig, ax = plt.subplots(1, 2, figsize=(COL2, 2.05), gridspec_kw=dict(wspace=0.32, width_ratios=[1.15, 1]))
        d6, d30 = pd.DataFrame(rows6), pd.DataFrame(rows30)
        ax[0].axvline(L_TARGET, c=INK, ls=":", lw=0.8); ax[0].text(L_TARGET, 0.2, f" target {L_TARGET:g} yr", rotation=90, va="bottom", ha="right", fontsize=6.5, color=INK)
        ax[0].axvspan(-0.5, 0, color="0.93", lw=0)
        if len(d30):
            g = d30["life"] > 0
            ax[0].plot(d30.life[g], d30.save[g], ls="--", c=M["S3"]["c"], lw=0.8, marker="o", mfc="white", mec=M["S3"]["c"], label="30 days (Nov. 2022)")
            for _, r in d30[~g].iterrows():
                ax[0].plot(-0.25, r.save, marker="o", mfc="white", mec=M["S3"]["c"], ls="none")
                mant, ex = r.wz.split("e")
                ax[0].annotate("$w_Z=" + mant + r"{\times}10^{" + ex + "}$:\nno guarantee", (-0.25, r.save), xytext=(0.25, r.save + 1.0), fontsize=6, color=INK,
                               arrowprops=dict(arrowstyle="-", lw=0.5, color="0.5"))
        if len(d6):
            ax[0].plot(d6.life, d6.save, ls="-", c=M["S3"]["c"], lw=1.3, marker="o", label="6 months (Sep.–Feb.)")
            OFF = {"3e8": (4, 3), "1e9": (4, 4), "3e9": (-50, -9), "1e10": (2, 6)}
            for _, r in d6.iterrows():
                mant, ex = f"{float(r.wz):.0e}".split("e")
                ax[0].annotate(f"$w_Z={mant}{{\\times}}10^{{{int(ex)}}}$", (r.life, r.save), xytext=OFF.get(r.wz, (3, 4)),
                               textcoords="offset points", fontsize=6.2)
        ax[0].set_xlabel("Guaranteed FC lifetime $L(1-Z_{\\max})$ (yr)"); ax[0].set_ylabel("Cost reduction vs. battery only (%)")
        ax[0].set_xlim(-0.5, L_TARGET + 0.3); ax[0].set_ylim(0, None)
        ax[0].legend(loc="lower left", fontsize=6.5)
        panel(ax[0], "(a)", -0.13)
        if vr:
            dv = pd.DataFrame(vr).sort_values("V")
            mid = (dv.gap_lo + dv.gap_hi) / 2
            ax[1].plot(dv.V, mid, "-", c=M["S3"]["c"], lw=0.9)
            ax[1].errorbar(dv.V, mid, yerr=[mid - dv.gap_lo, dv.gap_hi - mid], fmt="o", c=M["S3"]["c"], ms=4, capsize=2, lw=0.9,
                           label="proposed (range: $C^*$ MILP bounds)")
            for _, r in dv.iterrows():
                ax[1].annotate(f"{r.life:.2f} yr", (r.V, r.gap_hi), xytext=(0, 4), textcoords="offset points", ha="center", fontsize=5.8, color=MUTED)
            ax[1].text(0.98, 0.70, "labels: guaranteed FC lifetime", transform=ax[1].transAxes, ha="right", fontsize=5.8, color=MUTED)
            ax[1].set_xscale("log"); ax[1].set_xlim(dv.V.min() * 0.72, dv.V.max() * 1.35); ax[1].set_xticks(dv.V); ax[1].set_xticklabels([f"{v:g}" for v in dv.V])
            ax[1].set_xlabel("Lyapunov trade-off parameter $V$"); ax[1].set_ylabel("Gap to clairvoyant $C^*$ (%)")
            ax[1].set_ylim(0, dv.gap_hi.max() * 1.18); ax[1].legend(loc="upper right", fontsize=6.5)
            panel(ax[1], "(b)", -0.15)
            dv.to_csv(DATA / "fig04_guarantee_Vsweep.csv", index=False)
        else:
            ax[1].set_axis_off(); skip("fig04(b)", f"thiếu quét V 7 ngày hoặc cstar_2022-11-01_7d")
        save(fig, "fig04_guarantee", {"6months": d6, "30days": d30})

# ============================================================================ Fig. 5 – 5 năm
if want("fig05"):
    def chunks(w, sc):
        out, k = [], 0
        while k < args.chunks:
            t = f"multiyear_wz{w}_{sc}_c{k:02d}{args.my_suffix}"
            f = RES / f"step3_{t}" / "timeseries.csv"
            if not f.exists():
                break
            cols = pd.read_csv(f, nrows=0).columns
            d = pd.read_csv(f, usecols=[c for c in cols if c.startswith("Dfc_phys_")])
            out.append(d); k += 1
        return (pd.concat(out, ignore_index=True), k) if out else (None, 0)
    s3, n3 = chunks(WZ, "S3")
    b0, nb = None, 0
    for w in [WZ, "3e8", "1e9", "3e9", "1e10", "1e8"]:
        b0, nb = chunks(w, "B0")
        if b0 is not None:
            break
    if s3 is None:
        skip("fig05", "thiếu mô phỏng nhiều năm (run_multiyear.py)")
    else:
        s0 = (RES / f"step3_multiyear_wz{WZ}_S3_c00{args.my_suffix}" / "summary.txt").read_text(encoding="utf-8")
        zmax = {i: num(rf"Bổ đề 3 – trạm {i}: max Z_FC = [\d.e+-]+ \(≤ ([\d.e+-]+)", s0) for i in H2}
        DT, life_h = S.DT, PARAMS["aging_and_devices"]["fc"]["life_target_h"]
        step = max(1, int(round(24 / DT)))                         # mỗi ngày một điểm (đủ mịn, file nhẹ)
        y3 = np.arange(len(s3)) * DT / 8760
        fig, ax = plt.subplots(1, 2, figsize=(COL2, 2.2), gridspec_kw=dict(wspace=0.3))
        out = {"year": y3[::step]}
        for i, c in zip(H2, ST_C):
            D = s3[f"Dfc_phys_{i}"].to_numpy()
            bnd = np.arange(len(D)) * DT / life_h + zmax[i]
            ax[0].plot(y3[::step], D[::step], c=c, lw=1.3, label=f"#{i}")
            ax[0].plot(y3[::step], bnd[::step], c=c, lw=0.8, ls=":")
            ax[1].plot(y3[::step], 100 * np.array([eta_fc(v, 0.45) for v in D[::step]]), c=c, lw=1.3)
            ax[1].plot(y3[::step], 100 * np.array([eta_fc(v, 0.45) for v in bnd[::step]]), c=c, lw=0.8, ls=":")
            out[f"D_S3_{i}"] = D[::step]; out[f"bound_{i}"] = bnd[::step]
        eols = []
        if b0 is not None:
            yb = np.arange(len(b0)) * DT / 8760
            for i, c in zip(H2, ST_C):
                D = b0[f"Dfc_phys_{i}"].to_numpy()
                n = int(np.argmax(D >= 1.0)) + 1 if (D >= 1.0).any() else len(D)
                ax[0].plot(yb[:n], D[:n], c=c, lw=0.9, ls="--")
                if (D >= 1.0).any():
                    ax[0].plot(yb[n - 1], 1.0, marker="x", c=c, ms=5, mew=1.0); eols.append(yb[n - 1])
                ax[1].plot(yb[:n:max(1, step // 12)], 100 * np.array([eta_fc(v, 0.45) for v in D[:n:max(1, step // 12)]]), c=c, lw=0.9, ls="--")
            nrep = [int(np.floor(b0[f"Dfc_phys_{i}"].to_numpy()[-1])) for i in H2]
            if eols:
                ax[0].annotate(f"Lyapunov w/o aging: end of life after {min(eols):.2f}–{max(eols):.2f} yr\n"
                               f"({min(nrep)}–{max(nrep)} stack replacements in {yb[-1]:.0f} yr)",
                               (max(eols), 1.0), xytext=(0.9, 1.07), fontsize=6.3, color=INK, va="bottom",
                               arrowprops=dict(arrowstyle="-", lw=0.5, color="0.5"))
        ax[0].axhline(1.0, c="0.35", lw=0.6); ax[0].text(y3[-1] * 0.5, 1.01, "end of life ($D=1$)", ha="center", va="bottom", fontsize=6.3, color=INK)
        ax[0].set_ylim(0, 1.25); ax[0].set_xlim(0, y3[-1] * 1.01)
        ax[0].set_xlabel("Year"); ax[0].set_ylabel("FC degradation $D$")
        h = [Line2D([], [], c=c, lw=1.3, label=f"station #{i}") for i, c in zip(H2, ST_C)]
        h += [Line2D([], [], c="0.3", lw=1.3, label="proposed"), Line2D([], [], c="0.3", lw=0.8, ls=":", label="bound $\\delta t+Z_{\\max}$ (Prop. 2)"),
              Line2D([], [], c="0.3", lw=0.9, ls="--", label="Lyapunov w/o aging")]
        ax[0].legend(handles=h, loc="center right", fontsize=6, ncol=1, bbox_to_anchor=(1.0, 0.42))
        ax[1].set_xlabel("Year"); ax[1].set_ylabel("FC efficiency at $x=0.45$ (%)"); ax[1].set_xlim(0, y3[-1] * 1.01)
        lo = min(100 * eta_fc(1.0, 0.45) - 0.2, ax[1].get_ylim()[0])
        ax[1].set_ylim(lo, 100 * eta_fc(0.0, 0.45) + 0.3)
        ax[1].legend(handles=[Line2D([], [], c="0.3", lw=1.3, label="proposed"), Line2D([], [], c="0.3", lw=0.8, ls=":", label="floor (Cor. 2)"),
                              Line2D([], [], c="0.3", lw=0.9, ls="--", label="Lyapunov w/o aging")], loc="upper right", fontsize=6)
        panel(ax[0], "(a)", -0.12); panel(ax[1], "(b)", -0.13)
        save(fig, "fig05_multiyear", {"degradation": pd.DataFrame(out).set_index("year")})

# ============================================================================ Fig. 6 – so sánh phương pháp (chi phí – quá tải)
METHODS = [("S1", f"{B30}_S1"), ("S3", f"{B30}_S3_wZ{WZ}"), ("B0", f"{B30}_B0_noAging"), ("rule", f"{B30}_B2_rule"),
           ("mpc", f"{B30}_B1_mpc"), ("mpc_or", f"{B30}_B1_mpc_oracle"), ("mpcL", f"{B30}_B1_mpc_life"), ("mpcL_or", f"{B30}_B1_mpc_life_or")]
if want("fig06"):
    rows = []
    for k, t in METHODS:
        r = R(t)
        if r:
            rows.append(dict(key=k, method=M[k]["lab"], cost=r["cost"], ov=r["ov"], life=r["life"]))
    if len(rows) < 2:
        skip("fig06", "thiếu các lần chạy 30 ngày")
    else:
        dfm = pd.DataFrame(rows).set_index("key")
        cs = cstar("cstar_2022-11-01_30d")
        fig, ax = plt.subplots(figsize=(COL1, 3.0))
        ymax = 880e3
        ax.set_xlim(dfm.ov.min() - 3, dfm.ov.max() + 4)
        for k, r in dfm.iterrows():
            st = M[k]; hollow = r.life < L_TARGET or k == "B0"
            if r.cost > ymax:                                        # ngoài khung: mũi tên ở mép trên
                ax.plot(r.ov, ymax, marker="^", ms=6, mfc=st["c"], mec=st["c"], clip_on=False, ls="none", zorder=5)
                ax.text(r.ov + 0.8, ymax * 0.988, f"{st['lab']}: {r.cost / 1e3:,.0f}k CNY (off scale), {r.life:.1f} yr",
                        ha="left", va="center", fontsize=6, color=INK)
                continue
            ax.plot(r.ov, r.cost, st["m"], ms=6 if k == "S3" else 5, mfc=("white" if not st["fill"] else st["c"]), mec=st["c"], mew=1.0, ls="none")
            lt = "∞" if not np.isfinite(r.life) else f"{r.life:.1f}"
            ax.annotate(f"{lt} yr" if k != "S1" else "", (r.ov, r.cost), xytext=(5, -6), textcoords="offset points", fontsize=6, color=MUTED)
        if cs:
            ax.axhline(cs[1], c=INK, ls="--", lw=0.7)
            ax.text(dfm.ov.max() + 3.5, cs[1], "clairvoyant $C^*$ (LP bound)", ha="right", va="bottom", fontsize=6.3, color=INK)
        ax.yaxis.set_major_formatter(kfmt)
        ax.set_xlabel("Transformer overload energy (MWh, 30 days)"); ax.set_ylabel("Operating cost ($10^3$ CNY, 30 days)")
        ax.set_ylim(min([cs[1]] if cs else [] + [dfm.cost.min()]) * 0.96, ymax)
        h = [Line2D([], [], marker=M[k]["m"], ls="none", mfc=(M[k]["c"] if M[k]["fill"] else "white"), mec=M[k]["c"], ms=5, label=M[k]["lab"]) for k in dfm.index]
        ax.legend(handles=h, loc="upper center", fontsize=6, ncol=2, bbox_to_anchor=(0.45, -0.2), columnspacing=0.8, handletextpad=0.3)
        ax.text(0.99, 0.02, "labels: FC lifetime at observed wear rate", transform=ax.transAxes, ha="right", fontsize=5.8, color=MUTED)
        save(fig, "fig06_methods", {"methods": dfm})

# ============================================================================ Fig. 7 – độ bền (độ nhạy + sai lệch mô hình)
SENS = [("compressor 2.0 kWh/kg", ["--e_cp", "2.0"], False), ("compressor 3.2 kWh/kg", ["--e_cp", "3.2"], False),
        ("FC stack cost ×0.6", ["--fc_stack_mult", "0.6"], False), ("FC stack cost ×1.3", ["--fc_stack_mult", "1.3"], False),
        ("EL stack cost ×0.3", ["--el_stack_mult", "0.3"], False),
        ("sharing limit 150 kW", ["--p_share", "150"], True), ("sharing limit 600 kW", ["--p_share", "600"], True),
        ("battery wear 0.02 CNY/kWh", ["--c_bat", "0.02"], True), ("battery wear 0.10 CNY/kWh", ["--c_bat", "0.10"], True),
        ("transformer 0.5×peak", ["--tr_frac", "0.5"], True), ("transformer 0.7×peak", ["--tr_frac", "0.7"], True),
        ("transformer 0.8×peak", ["--tr_frac", "0.8"], True), ("PV ×1", ["--pv_scale", "1"], True), ("PV ×3", ["--pv_scale", "3"], True)]
sens_tag = lambda opt, kind: f"{B30}_sens44_{'_'.join(x.strip('-') for x in opt)}_{kind}" + (SFX if kind == "S3" else "")
MM = [("M1 smooth plant", "M1"), ("M2 2-segment", "M2"), ("M3 1-segment", "M3"), ("M4 aged, no update", "M4"),
      ("M5 aged, daily update", "M5"), ("M6 bias +10%", "M6"), ("M7 bias −10%", "M7")]
if want("fig07"):
    b3, b1 = R(f"{B30}_S3_wZ{WZ}"), R(f"{B30}_S1")
    srows = []
    if b3 and b1:
        srows.append(dict(case="baseline assumptions", save=100 * (1 - b3["cost"] / b1["cost"]), ovred=100 * (1 - b3["ov"] / b1["ov"]), life=b3["life"]))
    for lab, opt, both in SENS:
        a = R(sens_tag(opt, "S3"), tier1=False); s1 = R(sens_tag(opt, "S1"), tier1=False) if both else b1
        if a and s1:
            srows.append(dict(case=lab, save=100 * (1 - a["cost"] / s1["cost"]), ovred=100 * (1 - a["ov"] / s1["ov"]), life=a["life"]))
    mrows = []
    ideal = R(f"{B30}_S3_wZ{WZ}")
    for lab, k in MM:
        r = R(f"{B30}_mm_{k}{SFX}", tier1=False)
        if r and ideal:
            gaps = [float(x) for x in re.findall(r"khoảng cách nhỏ nhất tới đáy bồn ([\d.]+) kg", r["txt"])]
            mrows.append(dict(case=lab, dcost=100 * (r["cost"] / ideal["cost"] - 1), tank_gap=min(gaps) if gaps else np.nan, ok=r["ok"]))
    if len(srows) < 2 and not mrows:
        skip("fig07", "thiếu kết quả độ nhạy / sai lệch mô hình")
    else:
        fig, ax = plt.subplots(1, 2, figsize=(COL2, 2.6), gridspec_kw=dict(wspace=0.85, width_ratios=[1.35, 1]))
        if len(srows) >= 2:
            ds = pd.DataFrame(srows)
            y = np.arange(len(ds))[::-1]
            ax[0].barh(y + 0.19, ds.save, height=0.36, color=M["S3"]["c"], label="cost reduction")
            ax[0].barh(y - 0.19, ds.ovred, height=0.36, color="#0072B2", label="overload reduction")
            ax[0].set_yticks(y); ax[0].set_yticklabels(ds.case, fontsize=6.3)
            ax[0].axvline(0, c="0.4", lw=0.6); ax[0].grid(axis="y", visible=False)
            ax[0].set_xlabel("Reduction vs. battery only (%)")
            ax[0].legend(loc="lower left", bbox_to_anchor=(0.25, 1.0), ncol=2, fontsize=6, handlelength=1.2)
            ax[0].get_yticklabels()[0].set_fontweight("bold")
            panel(ax[0], "(a)", -0.62, 1.03)
        if mrows:
            dm = pd.DataFrame(mrows)
            y = np.arange(len(dm))[::-1]
            ax[1].barh(y, dm.dcost, height=0.55, color=["#999999" if v >= 0 else "#56B4E9" for v in dm.dcost])
            for yy, r in zip(y, dm.itertuples()):
                ax[1].text(max(r.dcost, 0) + 0.15, yy, f"tank ≥ {r.tank_gap:.0f} kg", va="center", fontsize=5.8, color=MUTED)
            ax[1].set_yticks(y); ax[1].set_yticklabels(dm.case, fontsize=6.3)
            ax[1].axvline(0, c="0.4", lw=0.6); ax[1].grid(axis="y", visible=False)
            ax[1].set_xlabel("Cost change vs. exact model (%)")
            ax[1].set_xlim(min(dm.dcost.min() - 0.5, -0.5), dm.dcost.max() + 2.6)
            panel(ax[1], "(b)", -0.62, 1.03)
        save(fig, "fig07_robustness", {"sensitivity": pd.DataFrame(srows), "mismatch": pd.DataFrame(mrows)})

# ============================================================================ Fig. 8 – lưới 33 nút + mở rộng
if want("fig08"):
    gdir = RES / f"grid33_6thang_vv{SFX}"
    prof = pd.read_csv(gdir / "vmin_profiles.csv", index_col=0, parse_dates=True) if (gdir / "vmin_profiles.csv").exists() else None
    srow = []
    m7, s7 = R(f"{B30}_S3_wZ{WZ}"), R(f"{B30}_S1")
    if m7 and s7:
        srow.append(dict(N=7, t=m7["t"], tmax=m7["tmax"], save=100 * (1 - m7["cost"] / s7["cost"]), ovred=100 * (1 - m7["ov"] / s7["ov"])))
    for N in (20, 35, 50):
        a, b = R(f"scale{N}_30d_S3{SFX}", tier1=False), R(f"scale{N}_30d_S1", tier1=False)
        if a and b:
            srow.append(dict(N=N, t=a["t"], tmax=a["tmax"], save=100 * (1 - a["cost"] / b["cost"]), ovred=100 * (1 - a["ov"] / b["ov"])))
    if prof is None and len(srow) < 2:
        skip("fig08", f"thiếu {gdir}/vmin_profiles.csv (chạy lại: reproduce_all.py --stages F --force) và kết quả mở rộng")
    else:
        fig, ax = plt.subplots(1, 3, figsize=(COL2, 2.0), gridspec_kw=dict(wspace=0.42, width_ratios=[1.3, 1, 1]))
        if prof is not None:
            SHOW = [("S1", "no H$_2$", "#0072B2", "-", 0.9), ("S3_grid", "proposed, grid-aware", "#D55E00", "-", 0.9),
                    ("S1_vv", "no H$_2$ + volt–var", "#0072B2", "--", 1.2), ("S3_vv", "proposed + volt–var", "#D55E00", "--", 1.4)]
            hp = {}
            for k, lab, c, ls, lw in SHOW:
                if k in prof:
                    h = prof[k].groupby(prof.index.hour).mean()
                    hp[k] = h
                    ax[0].plot(h.index, h.values, c=c, ls=ls, lw=lw, label=lab)
            ax[0].axhline(0.95, c=INK, ls=":", lw=0.7); ax[0].text(0.3, 0.9503, "0.95 p.u.", fontsize=6.3, color=INK, va="bottom")
            ax[0].set_xlim(0, 23); ax[0].set_xticks(range(0, 24, 6)); ax[0].set_xlabel("Hour of day")
            ax[0].set_ylabel("Min. bus voltage (p.u.), mean"); ax[0].legend(loc="lower left", fontsize=5.8)
            panel(ax[0], "(a)", -0.27)
            pd.DataFrame(hp).to_csv(DATA / "fig08_grid_hourly_vmin.csv")
        else:
            ax[0].set_axis_off(); skip("fig08(a)", f"thiếu {gdir}/vmin_profiles.csv")
        if len(srow) >= 2:
            dsx = pd.DataFrame(srow)
            ax[1].plot(dsx.N, 1e3 * dsx.t, "o-", c="#555555", lw=1.0, label="mean")
            ax[1].plot(dsx.N, 1e3 * dsx.tmax, "s--", c="#555555", mfc="white", lw=0.8, label="max")
            ax[1].set_xlabel("Number of charging nodes $N$"); ax[1].set_ylabel("Solve time per 5-min step (ms)")
            ax[1].set_xticks(dsx.N); ax[1].legend(loc="upper left", fontsize=6); ax[1].set_ylim(0, None)
            ax[2].plot(dsx.N, dsx.save, "o-", c=M["S3"]["c"], label="cost")
            ax[2].plot(dsx.N, dsx.ovred, "s-", c="#0072B2", label="overload")
            ax[2].set_xlabel("Number of charging nodes $N$"); ax[2].set_ylabel("Reduction vs. battery only (%)")
            ax[2].set_xticks(dsx.N); ax[2].set_ylim(0, None); ax[2].legend(loc="center right", fontsize=6)
            panel(ax[1], "(b)", -0.27); panel(ax[2], "(c)", -0.27)
            dsx.to_csv(DATA / "fig08_scale.csv", index=False)
        save(fig, "fig08_grid_scale")

# ============================================================================ Fig. 9 – H2 so với pin lớn hơn
if want("fig09"):
    s1, s3 = R(f"{B30}_S1"), R(f"{B30}_S3_wZ{WZ}")
    bat0 = sum(s["bat_kWh"] for s in PARAMS["stations"] if s.get("has_h2"))
    pts = [(0.0, 0.0)]
    for m in ("1.5", "2", "3", "5", "7"):
        r = R(f"{B30}_BAT{m}")
        if r and s1:
            pts.append(((float(m) - 1) * bat0, 100 * (1 - r["ov"] / s1["ov"])))
    if len(pts) < 3 or not s3:
        skip("fig09", "thiếu các lần chạy pin lớn (run_battery_compare.py)")
    else:
        dp = pd.DataFrame(pts, columns=["added_kWh", "ovred"])
        h2 = 100 * (1 - s3["ov"] / s1["ov"])
        be = float(np.interp(h2, dp.ovred, dp.added_kWh))
        fig, ax = plt.subplots(figsize=(COL1, 2.0))
        ax.plot(dp.added_kWh, dp.ovred, "s-", c=M["S1"]["c"], lw=1.0, ms=4, label="larger battery (no H$_2$)")
        ax.plot(0, h2, marker="*", c=M["S3"]["c"], ms=10, ls="none", label="H$_2$ chain, proposed")
        ax.plot([0, be], [h2, h2], c=M["S3"]["c"], ls=":", lw=0.8); ax.plot([be, be], [0, h2], c=M["S3"]["c"], ls=":", lw=0.8)
        ax.annotate(f"break-even ≈ {be:,.0f} kWh", (be, h2), xytext=(be + 600, h2 - 9), fontsize=6.5, color=INK,
                    arrowprops=dict(arrowstyle="-", lw=0.5, color="0.5"))
        ax.set_xlabel("Battery capacity added at H$_2$ stations (kWh)"); ax.set_ylabel("Overload reduction vs. base (%)")
        ax.set_xlim(-300, None); ax.set_ylim(0, 100); ax.legend(loc="lower right", fontsize=6.5)
        save(fig, "fig09_battery_vs_h2", {"battery": dp.set_index("added_kWh")})

# ============================================================================ BẢNG LaTeX
if want("tab"):
    cs = cstar("cstar_2022-11-01_30d")
    s1, s16 = R(f"{B30}_S1"), R(f"{B6}_S1")
    G = {"S3": r"\checkmark", "S1": "--", "B0": r"$\times$", "rule": r"$\times$", "mpc": r"$\times$", "mpc_or": r"$\times$",
         "mpcL": "soft", "mpcL_or": "soft"}
    T6 = {"S1": f"{B6}_S1", "S3": f"{B6}_S3_wZ{WZ}", "B0": f"{B6}_B0_noAging", "rule": f"{B6}_B2_rule", "mpc": f"{B6}_B1_mpc",
          "mpc_or": f"{B6}_B1_mpc_oracle", "mpcL": f"{B6}_B1_mpc_life", "mpcL_or": f"{B6}_B1_mpc_life_or"}
    L = [r"% Bảng II – sinh tự động bởi make_figures.py (chi phí = K2 hiệu chỉnh cuối kỳ)",
         r"\begin{table}[t]\centering\caption{Comparison of control methods (7 real stations, 3 with H$_2$).}\label{tab:methods}",
         r"\setlength{\tabcolsep}{3pt}\footnotesize",
         r"\begin{tabular}{lrrrrrc}\toprule",
         r" & \multicolumn{4}{c}{30 days (Nov.\ 2022)} & 6 months & \\ \cmidrule(lr){2-5}\cmidrule(lr){6-6}",
         r"Method & Cost & $\Delta$ & Gap to & Overl. & $\Delta$ & Life \\",
         r" & (k CNY) & cost & $C^*$ & $\Delta$ & cost & guar. \\ \midrule"]
    for k, t in METHODS:
        r = R(t)
        if not r:
            continue
        r6 = R(T6[k])
        d6 = f"{100 * (r6['cost'] / s16['cost'] - 1):+.1f}\\%" if (r6 and s16 and k != "S1") else "--"
        dc = f"{100 * (r['cost'] / s1['cost'] - 1):+.1f}\\%" if k != "S1" else "--"
        dov = f"{100 * (r['ov'] / s1['ov'] - 1):+.1f}\\%" if k != "S1" else f"{r['ov']:.1f} MWh"
        gap = f"{100 * (r['cost'] / cs[1] - 1):.1f}\\%" if cs else "--"
        name = M[k]["lab"].replace("H$_2$", "H$_2$")
        bold = (lambda s: r"\textbf{" + s + "}") if k == "S3" else (lambda s: s)
        cst = f"{r['cost'] / 1e3:,.1f}"
        L.append(f"{bold(name)} & {bold(cst)} & {bold(dc)} & {gap} & {dov} & {d6} & {G[k]} \\\\")
    drl = RES / f"drl_summary{SFX}.txt"
    if drl.exists():
        s = drl.read_text(encoding="utf-8")
        s3b = num(r"S3b không chia sẻ\s+([\d,]+)", s); s1b = num(r"S1b không H2, k\. chia sẻ\s+([\d,]+)", s)
        ppo = num(r"PPO trung bình\s+([\d,]+)", s); sd = num(r"độ lệch chuẩn chi phí ([\d,]+)", s)
        L += [r"\midrule \multicolumn{7}{l}{\emph{Without inter-station sharing (raw cost):}} \\",
              f"Battery only & {s1b / 1e3:,.1f} & -- & & & & -- \\\\",
              f"Proposed & {s3b / 1e3:,.1f} & {100 * (s3b / s1b - 1):+.1f}\\% & & & & \\checkmark \\\\",
              f"PPO (3 seeds) & {ppo / 1e3:,.1f}$\\pm${sd / 1e3:.1f} & {100 * (ppo / s1b - 1):+.1f}\\% & & & & $\\times$ \\\\"]
    L += [r"\bottomrule\end{tabular}",
          r"\\[2pt]\parbox{\columnwidth}{\scriptsize $\Delta$: relative to battery only. Gap to the clairvoyant $C^*$ (LP lower bound, so an upper bound on the true gap). "
          r"Life guar.: provable FC lifetime guarantee; ``soft'': hard lifetime budget inside a 24-h horizon only, no guarantee beyond it.}",
          r"\end{table}"]
    (OUT / "tab_methods.tex").write_text("\n".join(L), encoding="utf-8")
    # Bảng III – độ bền
    L = [r"% Bảng III – sinh tự động bởi make_figures.py",
         r"\begin{table}[t]\centering\caption{Robustness of the proposed controller (30 days unless noted).}\label{tab:robust}",
         r"\setlength{\tabcolsep}{3pt}\footnotesize\begin{tabular}{llrrc}\toprule",
         r"Group & Case & $\Delta$ cost & Key metric & Guar. \\ \midrule"]
    ideal = R(f"{B30}_S3_wZ{WZ}")
    CK = lambda ok: r"\checkmark" if ok else r"$\times$"
    for lab, k in MM:
        r = R(f"{B30}_mm_{k}{SFX}", tier1=False)
        if r and ideal:
            gaps = [float(x) for x in re.findall(r"khoảng cách nhỏ nhất tới đáy bồn ([\d.]+) kg", r["txt"])]
            L.append(f"Model mismatch & {lab} & {100 * (r['cost'] / ideal['cost'] - 1):+.2f}\\% & tank margin {min(gaps):.0f} kg & {CK(r['ok'])} \\\\")
    L.append(r"\midrule")
    for lab, opt, both in SENS:
        a = R(sens_tag(opt, "S3"), tier1=False); s1_ = R(sens_tag(opt, "S1"), tier1=False) if both else R(f"{B30}_S1")
        if a and s1_:
            L.append(f"Assumption & {lab} & {100 * (a['cost'] / s1_['cost'] - 1):+.1f}\\% & overload {100 * (a['ov'] / s1_['ov'] - 1):+.1f}\\% & "
                     f"{CK(a['ok'])} \\\\")
    L.append(r"\midrule")
    cen = R(f"{B7}_S3_wZ{WZ}")
    for lab, t in (("$k{=}3$, $\\rho{=}10^{-3}$", "admm_k3_r1e-3"), ("$k{=}10$, $\\rho{=}10^{-3}$", "admm_k10_r1e-3"),
                   ("$k{=}30$, $\\rho{=}10^{-3}$", "admm_k30_r1e-3"), ("$k{=}30$, $\\rho{=}3{\\times}10^{-4}$", "admm_k30_r3e-4")):
        r = R(f"{B7}_{t}{SFX}", tier1=False)
        if r and cen:
            conv = num(r"hội tụ \(lệch chia sẻ ≤ [\d.]+ kW\) ở ([\d.]+)%", r["txt"])
            L.append(f"ADMM (7 d) & {lab} & {100 * (r['cost'] / cen['cost'] - 1):+.2f}\\% & converged {conv:.0f}\\% & "
                     f"{CK(r['ok'])} \\\\")
    L.append(r"\midrule")
    for N in (20, 35, 50):
        a, b = R(f"scale{N}_30d_S3{SFX}", tier1=False), R(f"scale{N}_30d_S1", tier1=False)
        if a and b:
            L.append(f"Scale-up & $N={N}$ & {100 * (a['cost'] / b['cost'] - 1):+.1f}\\% & {1e3 * a['t']:.0f} ms/step & {CK(a['ok'])} \\\\")
    L += [r"\bottomrule\end{tabular}",
          r"\\[2pt]\parbox{\columnwidth}{\scriptsize $\Delta$ cost: mismatch vs.\ exact model; assumption \& scale-up vs.\ battery only under the same assumption; "
          r"ADMM vs.\ centralized. Guar.: every bound of Props.~1--2 and Lemma~3 verified at every step.}", r"\end{table}"]
    (OUT / "tab_robust.tex").write_text("\n".join(L), encoding="utf-8")
    print("  ✓ tab_methods.tex, tab_robust.tex", flush=True)

(OUT / "README.txt").write_text("""HÌNH CHO BÀI (vector .pdf cho LaTeX, .png 600 dpi cho Word/slide). Số liệu từng hình: data/.
fig01  sơ đồ hệ thống – bản nháp riêng (draw_system.py), chỉnh tay trong Inkscape/draw.io
fig02_calibration     (1 cột)  Mục II – đường hiệu suất FC và điện năng EL theo tải ở D = 0 / 0,5 / 1 (từ dữ liệu IEEE PHM 2014, Mendeley)
fig03_operation_day   (1 cột)  Mục VI – một ngày quá tải nặng nhất: lưới, FC/EL/pin, bồn, hàng đợi Z
fig04_guarantee       (2 cột)  Mục VI – (a) giá của bảo đảm theo w_Z; (b) Định lý 1: khoảng cách tới C* theo V
fig05_multiyear       (2 cột)  Mục VI – 5 năm: lão hóa + hiệu suất, đường cận Mệnh đề 2 / sàn Hệ quả 2, so với Lyapunov không lão hóa
fig06_methods         (1 cột)  Mục VI – chi phí so với quá tải của mọi phương pháp, nhãn = tuổi thọ FC
fig07_robustness      (2 cột)  Mục VI – (a) độ nhạy giả định; (b) sai lệch mô hình
fig08_grid_scale      (2 cột)  Mục VI – (a) điện áp lưới 33 nút; (b) thời gian giải theo N; (c) lợi ích theo N
fig09_battery_vs_h2   (1 cột)  Thảo luận – H2 so với pin lớn hơn (điểm hòa vốn)
tab_methods.tex (Bảng II), tab_robust.tex (Bảng III) – \\usepackage{booktabs}
Bài 10 trang: dùng fig01, fig04, fig05, fig06 hoặc fig03, fig08; đồ án dùng tất cả.
""", encoding="utf-8")
print(f"\nXONG → {OUT}", flush=True)
