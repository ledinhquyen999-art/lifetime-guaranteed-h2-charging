# -*- coding: utf-8 -*-
"""
VẼ HÌNH CHO BÀI BÁO (bản cuối) – chỉ đọc số liệu đã xuất, không chạy lại mô phỏng.
  Vào : results/paper_figures/data/*.csv   (do make_figures.py xuất)
        results/FINAL_summary.txt           (bảng so sánh, khiên, "giá không đủ")
  Ra  : results/paper_figures_final/figXX_*.pdf (vector, chèn LaTeX) và .png (600 dpi)
Chạy:   python hinh_bai.py            (sau khi đã chạy make_figures.py)

Quy ước chung cho mọi hình:
  • Khổ IEEE: 1 cột 3,5 in, 2 cột 7,16 in; chữ Times 8 pt (nhãn trục), 7 pt (số trục, chú giải).
  • Một bảng màu cho cả bài (an toàn cho người mù màu, in đen trắng vẫn phân biệt nhờ kiểu đường/điểm):
      đề xuất = đỏ son, chỉ pin = xanh đá, MPC = xanh lục lam, MPC biết trước = rỗng/gạch chéo cùng màu,
      Lyapunov bỏ lão hóa = tím, quy tắc = vàng hổ phách, cận/ngưỡng = xám đen nét đứt.
  • Tên trạm: Station 1–3 (có H2) = #1093, #1242, #1589; Station 4–7 = #1061, #1087, #1214, #1229.
"""
import argparse
import re
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter  # noqa: E402

HERE = Path(__file__).resolve().parent
ap = argparse.ArgumentParser()
ap.add_argument("--data", default=str(HERE / "results" / "paper_figures" / "data"))
ap.add_argument("--summary", default=str(HERE / "results" / "FINAL_summary.txt"))
ap.add_argument("--out", default=str(HERE / "results" / "paper_figures_final"))
ap.add_argument("--only", default="")
args = ap.parse_args()
DATA, OUT = Path(args.data), Path(args.out)
OUT.mkdir(parents=True, exist_ok=True)
for _f in list(OUT.rglob("*.pdf")) + list(OUT.rglob("*.png")):          # xóa hình bản cũ để khỏi lẫn
    _f.unlink()
SUMMARY = Path(args.summary).read_text(encoding="utf-8") if Path(args.summary).exists() else ""
ONLY = [s.strip() for s in args.only.split(",") if s.strip()]
want = lambda k: not ONLY or any(k.startswith(o) for o in ONLY)

# ------------------------------------------------------------------ phong cách
COL1, COL2 = 3.5, 7.16
plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "Times", "Nimbus Roman", "STIXGeneral", "DejaVu Serif"],
    "mathtext.fontset": "stix",
    "font.size": 8, "axes.labelsize": 8, "axes.titlesize": 8, "xtick.labelsize": 7, "ytick.labelsize": 7, "legend.fontsize": 7,
    "axes.linewidth": 0.55, "axes.edgecolor": "0.15", "axes.labelcolor": "0.1", "xtick.color": "0.15", "ytick.color": "0.15",
    "xtick.direction": "out", "ytick.direction": "out", "xtick.major.size": 3, "ytick.major.size": 3,
    "xtick.major.width": 0.6, "ytick.major.width": 0.6, "xtick.minor.size": 1.6, "ytick.minor.size": 1.6,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "axes.grid.axis": "y", "grid.color": "0.91", "grid.linewidth": 0.4,
    "lines.linewidth": 0.9, "lines.markersize": 3.4, "lines.solid_capstyle": "round", "lines.dash_capstyle": "round",
    "legend.frameon": False, "legend.handlelength": 1.8, "legend.borderaxespad": 0.2, "legend.columnspacing": 1.0, "legend.handletextpad": 0.5,
    "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none",
    "savefig.dpi": 600, "savefig.bbox": "tight", "savefig.pad_inches": 0.03,
    "axes.unicode_minus": True, "axes.axisbelow": True,
})
INK, MUTED, BOUND = "#1A1A1A", "#6B6B6B", "#3D3D3D"
C = dict(prop="#C8312B", bat="#2F4F7F", mpc="#1F7A70", mpcV="#0F4C4C", b0="#7A4E2D", rule="#D08C12", grey="#7F7F7F")
STC = ["#1F4E79", "#2E7D32", "#E07B24"]            # Station 1, 2, 3 (có H2): xanh đậm, xanh lá đậm, cam
STG = ["#5E5E5E", "#7A7A7A", "#969696", "#B0B0B0"]  # Station 4–7: các mức xám
STN = {1093: "Station 1", 1242: "Station 2", 1589: "Station 3", 1061: "Station 4", 1087: "Station 5", 1214: "Station 6", 1229: "Station 7"}
H2 = [1093, 1242, 1589]


def panel(ax, s):
    ax.set_title(s, loc="left", fontsize=8, fontweight="bold", pad=4)


PAPER = {"fig03_mechanism": "Fig2_mechanism", "fig05_multiyear": "Fig3_lifetime_guarantee", "fig10_price_shield": "Fig4_price_and_shield",
         "fig04_guarantee": "Fig5_cost_of_guarantee"}          # so sánh phương pháp và độ vững: trong bài là Bảng II–III; hình fig06/fig07 để đồ án


def save(fig, name):
    sub, nm = ("bai_bao", PAPER[name]) if name in PAPER else ("do_an", name)
    (OUT / sub).mkdir(parents=True, exist_ok=True)
    for ext in ("pdf", "png"):
        fig.savefig(OUT / sub / f"{nm}.{ext}")
    plt.close(fig)
    print(f"  ✓ {sub}/{nm}", flush=True)


def csv(name):
    f = DATA / f"{name}.csv"
    return pd.read_csv(f) if f.exists() else None


def skip(name, why):
    print(f"  – bỏ qua {name}: {why}", flush=True)


pctfmt = FuncFormatter(lambda v, _: f"{v:g}")

# ================================================================== Fig. 2 – hiệu chỉnh FC / EL
if want("fig02"):
    d = csv("fig02_calibration_curves")
    if d is None:
        skip("fig02", "thiếu data")
    else:
        fig, ax = plt.subplots(1, 2, figsize=(COL1, 1.75), gridspec_kw=dict(wspace=0.55))
        shades = ["#9CB8D8", "#4F7FB5", "#1F3F6E"]
        for D_, c in zip(("0", "0.5", "1"), shades):
            ax[0].plot(d.load_frac, d[f"fc_eta_pct_D{D_}"], c=c, lw=0.8)
            ax[1].plot(d.load_frac, d[f"el_kwh_per_kg_D{D_}"], c=c, lw=0.8)
        pts_fc = [(0.1, 47.77), (0.25, 51.13), (0.45, 50.45), (0.7, 48.57), (1.0, 45.59)]
        pts_el = [(0.1, 61.7), (0.3, 52.65), (0.6, 52.99), (1.0, 54.95)]
        ax[0].plot(*zip(*pts_fc), "o", ms=3.6, mfc="white", mec=INK, mew=0.9, zorder=5)
        ax[1].plot(*zip(*pts_el), "o", ms=3.6, mfc="white", mec=INK, mew=0.9, zorder=5)
        ax[0].set_xlabel("FC load $P/\\bar P$"); ax[0].set_ylabel("FC efficiency (%)")
        ax[1].set_xlabel("EL load $P/\\bar P$"); ax[1].set_ylabel("EL specific energy (kWh/kg)")
        for a in ax:
            a.set_xlim(0, 1.05); a.set_xticks([0, 0.5, 1])
        h = [Line2D([], [], c=c, lw=0.8, label=f"$D={D_}$") for D_, c in zip(("0", "0.5", "1"), shades)]
        h += [Line2D([], [], ls="none", marker="o", ms=3.6, mfc="white", mec=INK, mew=0.9, label="measured (calibration)")]
        fig.legend(handles=h, loc="lower center", bbox_to_anchor=(0.5, 0.98), ncol=4, fontsize=6.5, handlelength=1.4, columnspacing=0.9)
        panel(ax[0], "(a)"); panel(ax[1], "(b)")
        save(fig, "fig02_calibration")

# ================================================================== Fig. 3a – CƠ CHẾ (bài báo): Station 3, ngày nặng nhất
if want("fig03"):
    d = csv("fig03_mechanism_day")
    day = (DATA / "fig03_mechanism_day_date.txt").read_text(encoding="utf-8").strip() if (DATA / "fig03_mechanism_day_date.txt").exists() else ""
    if d is None:
        skip("fig03 (cơ chế)", "cần data mới của make_figures.py (fig03_mechanism_day.csv)")
    else:
        h = d.hour.to_numpy(); ptr = float(d.P_tr_kW.iloc[0]); sid = int(d.station_id.iloc[0])
        dt = 5 / 60; e1, e3 = d.ov_S1_kW.sum() * dt / 1e3, d.ov_S3_kW.sum() * dt / 1e3
        fig, ax = plt.subplots(3, 1, figsize=(COL1, 3.55), sharex=True, gridspec_kw=dict(hspace=0.14, height_ratios=[1.35, 1.0, 0.95]))
        a = ax[0]
        g1, g3 = d.grid_S1_kW.to_numpy(), d.grid_S3_kW.to_numpy()
        top3 = np.maximum(g3, ptr)
        a.fill_between(h, top3, np.maximum(g1, top3), where=g1 > top3, color=STC[1], alpha=0.30, lw=0, step=None, label="overload avoided by H$_2$")
        a.fill_between(h, ptr, top3, where=g3 > ptr, color=C["prop"], alpha=0.20, lw=0, label="overload remaining")
        a.plot(h, d.grid_S1_kW, c=C["bat"], lw=0.68, label=f"battery only ({e1:.2f} MWh above limit)")
        a.plot(h, d.grid_S3_kW, c=C["prop"], lw=1, label=f"proposed ({e3:.2f} MWh above limit)")
        a.axhline(ptr, c=INK, lw=0.7, ls=(0, (4, 2)), label="connection limit")
        a.text(0.015, 0.04, "$<0$: PV surplus sent to other stations", transform=a.transAxes, ha="left", va="bottom", fontsize=5.8, color=MUTED)
        a.set_ylabel("Net grid import (kW)"); a.set_ylim(min(-50, d[["grid_S1_kW", "grid_S3_kW"]].min().min() * 1.1), d.grid_S1_kW.max() * 1.12)
        hh, ll = a.get_legend_handles_labels()
        order = [ll.index(x) for x in ll if x.startswith("battery")] + [ll.index(x) for x in ll if x.startswith("proposed")] + \
                [ll.index("connection limit"), ll.index("overload avoided by H$_2$"), ll.index("overload remaining")]
        a.legend([hh[k] for k in order], [ll[k] for k in order], loc="lower left", bbox_to_anchor=(-0.02, 1.0), ncol=2, fontsize=6.2,
                 handlelength=1.6, labelspacing=0.25, columnspacing=0.9)
        b = ax[1]
        b.fill_between(h, 0, d.Pfc_kW, color=STC[2], alpha=0.85, lw=0, step="post", label="FC output")
        b.fill_between(h, 0, -d.Pel_kW, color=STC[1], alpha=0.85, lw=0, step="post", label="EL consumption (as $-$)")
        b.axhline(0, c=INK, lw=0.6)
        b.set_ylabel("H$_2$ chain (kW)"); b.legend(loc="upper center", ncol=2, fontsize=6.4, handlelength=1.3, columnspacing=1.0)
        lim = max(d.Pfc_kW.max(), d.Pel_kW.max()) * 1.25; b.set_ylim(-lim, lim)
        c = ax[2]
        c.plot(h, d.M_kg, c=STC[0], lw=0.96)
        c.axhline(float(d.M_min_kg.iloc[0]), c=STC[0], lw=0.64, ls=(0, (1, 1.4)))
        c.text(0.3, float(d.M_min_kg.iloc[0]) + 2, "tank minimum", ha="left", va="bottom", fontsize=6.2, color=STC[0])
        c.set_ylabel("H$_2$ tank (kg)", color=STC[0]); c.tick_params(axis="y", colors=STC[0])
        c.set_ylim(0, max(d.M_kg.max() * 1.25, float(d.M_min_kg.iloc[0]) * 3))
        z = c.twinx(); z.spines["right"].set_visible(True); z.grid(False)
        z.plot(h, 1e3 * d.Zfc, c=INK, lw=0.72, ls=(0, (5, 1.6)))
        z.set_ylabel("$Z$ ($\\times10^{-3}$)", color=INK); z.set_ylim(0, max(1e3 * d.Zfc.max() * 1.6, 0.1))
        c.text(0.3, c.get_ylim()[1] * 0.93, "tank (solid), $Z$ (dashed)", fontsize=6.2, color=MUTED, va="top")
        c.set_xlim(0, 24); c.set_xticks(range(0, 25, 4)); c.set_xlabel(f"Hour of {pd.Timestamp(day):%d %b %Y}, {STN.get(sid, sid)}" if day else "Hour")
        for k, a_ in enumerate(ax):
            a_.text(-0.2, 1.0, f"({'abc'[k]})", transform=a_.transAxes, fontsize=8, fontweight="bold", va="top", ha="right")
        fig.align_ylabels(ax)
        save(fig, "fig03_mechanism")

# ================================================================== Fig. 3b – BẢN ĐỒ NHIỆT 7 trạm × 7 ngày (đồ án)
if want("fig03"):
    d = csv("fig03_heatmap_7days")
    if d is None:
        skip("fig03 (bản đồ nhiệt)", "cần data mới của make_figures.py (fig03_heatmap_7days.csv)")
    else:
        from matplotlib.colors import ListedColormap, BoundaryNorm
        t = pd.to_datetime(d.time); ids = [1093, 1242, 1589, 1061, 1087, 1214, 1229]
        bounds = [0, 0.2, 0.4, 0.6, 0.8, 1.0, 1.2, 1.4, 1.6, 2.0]
        cols = ["#F3F6FA", "#D3DFEC", "#A9C0D9", "#6F93BC", "#2F5F94", "#F6C3A8", "#EC8A63", "#D24A35", "#9E1B1B"]
        cmap = ListedColormap(cols); cmap.set_under(cols[0]); cmap.set_over(cols[-1]); norm = BoundaryNorm(bounds, cmap.N)
        fig, ax = plt.subplots(2, 1, figsize=(COL2, 2.95), sharex=True, gridspec_kw=dict(hspace=0.30))
        for a, sc, ttl in ((ax[0], "S1", "(a) battery only (no H$_2$)"), (ax[1], "S3", "(b) proposed")):
            M = np.vstack([d[f"{sc}_{i}"].clip(lower=0).to_numpy() for i in ids])
            im = a.imshow(M, aspect="auto", cmap=cmap, norm=norm, interpolation="nearest", extent=(0, len(t), len(ids), 0))
            a.set_yticks(np.arange(len(ids)) + 0.5); a.set_yticklabels([STN[i] for i in ids], fontsize=6.6)
            a.axhline(3, c="white", lw=0.96)
            a.grid(False); a.tick_params(axis="y", length=0)
            for s_ in ("left", "bottom"):
                a.spines[s_].set_visible(False)
            e = sum(d[f"{sc}_ovMWh_{i}"].sum() for i in ids)
            a.set_title(f"{ttl}   —   energy above limit: {e:.1f} MWh", loc="left", fontsize=8, fontweight="bold", pad=3)
            for k in range(1, 7):
                a.axvline(24 * k, c="white", lw=0.7)
        days = [t.iloc[0] + pd.Timedelta(days=k) for k in range(7)]
        ax[1].set_xticks([12 + 24 * k for k in range(7)]); ax[1].set_xticklabels([f"{x:%a %d %b}" for x in days], fontsize=6.6)
        ax[1].tick_params(axis="x", length=0)
        cb = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.012, extend="max", ticks=[0, 0.5, 1.0, 1.5, 2.0])
        cb.set_label("Grid import / connection limit\n(hourly mean)", fontsize=7); cb.ax.tick_params(labelsize=6.5); cb.outline.set_linewidth(0.6)
        cb.ax.axhline(1.0, c=INK, lw=0.64)
        save(fig, "fig03_heatmap_stations")

# ================================================================== Fig. 4 – CÁI GIÁ CỦA BẢO ĐẢM: w_Z, θ_Z, V
if want("fig04"):
    g, v = csv("fig04_guarantee_30days"), csv("fig04_guarantee_Vsweep")
    th = [(float(t), float(c.replace(",", "")), float(sv), float(ov), float(gl))
          for t, c, sv, ov, gl in re.findall(r"θ_Z = ([\d.]+)\s+([\d,]+)\s+([-+][\d.]+)%\s+[\d.]+\s+([-+][\d.]+)%\s+[\d.]+\s+([\d.]+)", SUMMARY)]
    m0 = re.search(r"S3 – CHÍNH \(θ_Z = ([\d.]+)\)\s+([\d,]+)\s+([-+][\d.]+)%\s+[\d.]+\s+([-+][\d.]+)%\s+[\d.]+\s+([\d.]+)", SUMMARY)
    if m0:
        th.append((float(m0.group(1)), float(m0.group(2).replace(",", "")), float(m0.group(3)), float(m0.group(4)), float(m0.group(5))))
    th = sorted(set(th))
    if g is None or v is None or len(th) < 3:
        skip("fig04", "thiếu data (fig04_*.csv hoặc quét θ_Z trong FINAL_summary)")
    else:
        fig, ax = plt.subplots(1, 3, figsize=(COL2, 1.95), gridspec_kw=dict(wspace=0.42, width_ratios=[1, 1, 1]))
        # (a) w_Z đặt mức tuổi thọ bảo đảm; quyết định (và chi phí) không đổi
        a = ax[0]; wz = g.wz.astype(float).to_numpy()
        a.axhline(5, c=BOUND, ls=(0, (1, 1.5)), lw=0.7); a.text(wz.min() * 0.75, 5.15, "target 5 yr", fontsize=6.2, color=BOUND, va="bottom")
        lp = np.clip(g.life.to_numpy(), 0, None)              # cận âm = không bảo đảm được gì → vẽ ở 0, ghi "none"
        a.plot(wz, lp, "-o", c=C["prop"], mfc="white", mew=0.9)
        for x, y, y0 in zip(wz, lp, g.life):
            off, ha, va = ((0, 5), "center", "bottom") if 0 < y < 3 else (((0, -6), "center", "top") if y >= 3 else ((6, 0), "left", "center"))
            a.annotate(f"{y0:.2f}" if y0 > 0 else "none", (x, y), xytext=off, textcoords="offset points", ha=ha, va=va, fontsize=6.0, color=INK)
        a.set_xscale("log"); a.set_xlim(wz.min() * 0.55, wz.max() * 1.9); a.set_ylim(-0.3, 6.2)
        a.set_xlabel("Health-queue weight $w_Z$"); a.set_ylabel("Guaranteed FC lifetime (yr)")
        a.text(0.97, 0.05, f"same decisions at every $w_Z$:\ncost $-${g.save.iloc[0]:.1f}%, overload $-${g.ovred.iloc[0]:.1f}%",
               transform=a.transAxes, ha="right", va="bottom", fontsize=6.0, color=INK)
        # (b) vùng đệm θ_Z: tiết kiệm 6 tháng; nhãn = tuổi thọ bảo đảm
        b = ax[1]; tz = np.array([t[0] for t in th]); sv = np.array([-t[2] for t in th]); gl = np.array([t[4] for t in th])
        xs = np.arange(len(tz))
        b.plot(xs, sv, "-o", c=C["prop"], mfc="white", mew=0.9)
        for x, y, l in zip(xs, sv, gl):
            b.annotate(f"{l:.2f} yr", (x, y), xytext=(7, -2) if x == 0 else (0, 5), textcoords="offset points", ha="left" if x == 0 else "center",
                       va="center" if x == 0 else "bottom", fontsize=6.0, color=MUTED, bbox=dict(fc="white", ec="none", pad=0.3), zorder=4)
        b.set_ylim(0, max(sv) * 1.35); b.set_ylabel("Cost reduction, 6 months (%)")
        b.set_xticks(xs); b.set_xticklabels([f"{t:g}" for t in tz]); b.set_xlabel("Buffer $\\theta_Z$")
        k02 = int(np.argmin(np.abs(tz - 0.02)))
        b.axvline(xs[k02], c="0.6", lw=0.5, ls=(0, (1, 1.6))); b.text(xs[k02] - 0.08, 0.25, "used", ha="right", va="bottom", fontsize=6.0, color=MUTED)
        b.text(0.03, 0.97, "labels: guaranteed lifetime", transform=b.transAxes, ha="left", va="top", fontsize=6.0, color=MUTED)
        # (c) Định lý 1: khoảng cách tới C* theo V
        c = ax[2]; V = v.V.to_numpy(); mid = (v.gap_lo + v.gap_hi) / 2
        c.errorbar(V, mid, yerr=[mid - v.gap_lo, v.gap_hi - mid], fmt="-o", c=C["prop"], mfc="white", mew=0.9, capsize=1.8, elinewidth=0.6)
        c.set_xscale("log"); c.set_xticks(V); c.set_xticklabels([f"{x:g}" for x in V]); c.xaxis.set_minor_formatter(NullFormatter())
        c.set_xlim(V.min() * 0.72, V.max() * 1.35); c.set_ylim(0, max(v.gap_hi) * 1.15)
        c.set_xlabel("Lyapunov parameter $V$"); c.set_ylabel("Gap to clairvoyant $C^\\star$, 7 days (%)")
        for x, y, l in zip(V, v.gap_hi, v.life):
            c.annotate(f"{l:.2f} yr", (x, y), xytext=(5, 3), textcoords="offset points", ha="left", va="bottom", fontsize=6.0, color=MUTED)
        for k, a_ in enumerate(ax):
            panel(a_, f"({'abc'[k]})")
        save(fig, "fig04_guarantee")

# ================================================================== Fig. 5 – 5 năm
if want("fig05"):
    d, cal = csv("fig05_multiyear_degradation"), csv("fig02_calibration_curves")
    if d is None or cal is None:
        skip("fig05", "thiếu data")
    else:
        # hiệu suất tại x = 0,45 theo D: nội suy tuyến tính giữa đường D = 0 / 0,5 / 1 (đúng mô hình bộ điều khiển dùng)
        r = cal.iloc[(cal.load_frac - 0.45).abs().argmin()]
        eD = np.array([r["fc_eta_pct_D0"], r["fc_eta_pct_D0.5"], r["fc_eta_pct_D1"]])
        eta = lambda D: np.interp(np.clip(D, 0, 1), [0, 0.5, 1], eD)
        y = d.year.to_numpy()
        fig, ax = plt.subplots(1, 2, figsize=(COL2, 2.25), gridspec_kw=dict(wspace=0.28))
        eol = []
        for i, c in zip(H2, STC):
            ax[0].plot(y, d[f"D_S3_{i}"], c=c, lw=0.88)
            ax[0].plot(y, d[f"bound_{i}"], c=c, lw=0.7, ls=(0, (1, 1.4)))
            eS = d[f"eta_S3_{i}"].to_numpy() if f"eta_S3_{i}" in d else eta(d[f"D_S3_{i}"].to_numpy())       # ưu tiên số của make_figures (PCHIP)
            eB = d[f"eta_bound_{i}"].to_numpy() if f"eta_bound_{i}" in d else eta(d[f"bound_{i}"].to_numpy())
            ax[1].plot(y, eS, c=c, lw=0.88)
            ax[1].plot(y, eB, c=c, lw=0.7, ls=(0, (1, 1.4)))
            if f"D_B0_{i}" in d:
                D0 = d[f"D_B0_{i}"].to_numpy(); n = int(np.argmax(D0 >= 1)) + 1 if (D0 >= 1).any() else len(D0)
                ax[0].plot(y[:n], D0[:n], c=c, lw=0.64, ls=(0, (4, 2)))
                ax[1].plot(y[:n], d[f"eta_B0_{i}"].to_numpy()[:n] if f"eta_B0_{i}" in d else eta(D0[:n]), c=c, lw=0.64, ls=(0, (4, 2)))
                if n < len(D0):
                    ye = float(np.interp(1.0, D0[n - 2:n], y[n - 2:n])) if n >= 2 else float(y[n - 1])   # điểm cắt D = 1 (nội suy, khớp summary 5 phút)
                    ax[0].plot(ye, 1, "x", c=c, ms=4, mew=0.9); eol.append(ye)
        a = ax[0]
        a.axhline(1, c=BOUND, lw=0.64); a.text(4.95, 1.02, "end of life ($D=1$)", ha="right", va="bottom", fontsize=6.5, color=BOUND)
        if eol:
            a.annotate(f"Lyapunov without aging:\nend of life after {min(eol):.2f}–{max(eol):.2f} yr", (max(eol), 1.0),
                       xytext=(1.05, 0.80), fontsize=6.5, color=INK, va="center",
                       arrowprops=dict(arrowstyle="-", lw=0.6, color=MUTED, shrinkB=3))
        a.set_ylim(0, 1.15); a.set_xlim(0, 5); a.set_xlabel("Year"); a.set_ylabel("FC degradation $D$")
        b = ax[1]
        b.set_xlim(0, 5); b.set_ylim(eD[2] - 0.4, eD[0] + 0.3); b.set_xlabel("Year"); b.set_ylabel("FC efficiency at 45% load (%)")
        Hs = [Line2D([], [], c=c, lw=0.88, label=STN[i]) for i, c in zip(H2, STC)]
        Hk = [Line2D([], [], c="0.25", lw=0.88, label="proposed"),
              Line2D([], [], c="0.25", lw=0.7, ls=(0, (1, 1.4)), label="guaranteed bound (D) / floor (efficiency)")]
        if eol:
            Hk.append(Line2D([], [], c="0.25", lw=0.64, ls=(0, (4, 2)), label="Lyapunov without aging"))
        fig.legend(handles=Hs + Hk, loc="lower center", bbox_to_anchor=(0.5, 0.99), ncol=6, fontsize=6.5, handlelength=2.0, columnspacing=1.1)
        panel(a, "(a)"); panel(b, "(b)")
        save(fig, "fig05_multiyear")

# ================================================================== đọc Bảng 1 từ FINAL_summary
def table1():
    rows = {}
    pat = {"S1": r"S1 – không H2", "S3": r"S3 – ĐỀ XUẤT", "B0": r"B0 – Lyapunov không tính lão hóa", "rule": r"B2 – quy tắc",
           "mpc": r"B1 – MPC 24 h \(dự báo\)", "mpc_or": r"B1\* – MPC 24 h biết trước", "mpcL": r"B1L – MPC \+ ràng buộc tuổi thọ",
           "mpcL_or": r"B1L\* – MPC biết trước \+ tuổi thọ", "mpcV": r"B1V – MPC được vay", "mpcV_or": r"B1V\* – MPC được vay, biết trước"}
    for k, p in pat.items():
        m = re.search(p + r"[^\n]*?\s([\d,]{6,})\s+[\d,]{6,}\s+[-+][\d.]+%\s+[-+][\d.]+%\s+([\d.]+)", SUMMARY)
        if m:
            rows[k] = dict(cost=float(m.group(1).replace(",", "")), ov=float(m.group(2)))
    cs = re.search(r"C\* \(biết trước tương lai, LP\): ≥ ([\d,]+)", SUMMARY)
    return rows, (float(cs.group(1).replace(",", "")) if cs else None)


# ================================================================== Fig. 6 – so sánh phương pháp
if want("fig06"):
    T, cstar = table1()
    if len(T) < 5:
        skip("fig06", "không đọc được Bảng 1 trong FINAL_summary.txt")
    else:
        LAB = {"S3": "Proposed", "mpcV": "MPC, aging budget $\\delta t+Z_{\\max}$", "mpc": "MPC", "mpcL": "MPC, aging budget $\\delta t$", "S1": "Battery only (no H$_2$)",
               "B0": "Lyapunov without aging", "rule": "Rule-based", "mpcV_or": "MPC, aging budget $\\delta t+Z_{\\max}$$^\\star$",
               "mpc_or": "MPC$^\\star$", "mpcL_or": "MPC, aging budget $\\delta t$$^\\star$"}
        COLK = {"S3": C["prop"], "S1": C["bat"], "B0": C["b0"], "rule": C["rule"], "mpc": C["mpc"], "mpc_or": C["mpc"],
                "mpcL": C["mpc"], "mpcL_or": C["mpc"], "mpcV": C["mpcV"], "mpcV_or": C["mpcV"]}
        MK = {"S3": "o", "S1": "s", "B0": "v", "rule": "D", "mpc": "^", "mpc_or": "^", "mpcL": ">", "mpcL_or": ">", "mpcV": "<", "mpcV_or": "<"}
        GUAR = {"S3", "mpcV", "mpcV_or"}
        CL = [k for k in ("mpcV_or", "mpc_or", "mpcL_or") if k in T]
        ON = [k for k in ("S3", "mpcV", "mpc", "mpcL", "S1", "B0", "rule") if k in T]
        order = ON + CL
        n = len(order); yv = np.arange(n)[::-1]
        c3 = T["S3"]["cost"]
        fig, ax = plt.subplots(1, 2, figsize=(COL2, 0.235 * n + 0.65), sharey=True, gridspec_kw=dict(wspace=0.06, width_ratios=[1.3, 1]))
        for yy, k in zip(yv, order):
            cl = k in CL; c = COLK[k]
            ax[0].plot([T[k]["cost"] / 1e3], [yy], MK[k], ms=4.8 if k == "S3" else 5.2, mfc=("white" if cl else c), mec=c, mew=0.9, zorder=3)
            ax[0].hlines(yy, 0, T[k]["cost"] / 1e3, colors="0.88", lw=0.6, zorder=1)
            if k != "S3":
                ax[0].text(T[k]["cost"] / 1e3 + 7, yy, f"{100 * (T[k]['cost'] / c3 - 1):+.1f}%".replace("-", "−"), va="center", fontsize=6.4, color=INK)
            ax[1].barh(yy, T[k]["ov"], height=0.62, color=("white" if cl else c), edgecolor=c, lw=0.7, hatch=("//////" if cl else None))
            ax[1].text(T[k]["ov"] + 1.2, yy, "proven lifetime guarantee" if k == "S3" else "", va="center", fontsize=6.2, color=C["prop"])
        if CL:
            sep = yv[len(ON) - 1] - 0.5
            for a in ax:
                a.axhline(sep, c="0.55", lw=0.6, ls=(0, (3, 2)))
            ax[1].text(0.99, (sep + 0.5) / (n), "clairvoyant (knows next 24 h)", transform=ax[1].get_yaxis_transform(), ha="right",
                       va="bottom", fontsize=6.2, color=MUTED) if False else None
        lo = 0.93 * min([T[k]["cost"] for k in order] + ([cstar] if cstar else [])) / 1e3
        ax[0].set_xlim(lo, max(T[k]["cost"] for k in order) / 1e3 * 1.075)
        if cstar:
            ax[0].axvline(cstar / 1e3, c=BOUND, ls=(0, (3, 2)), lw=0.64)
            ax[0].text(cstar / 1e3 + 2, yv[-1] - 0.45, "$C^\\star$ bound", fontsize=6.3, color=BOUND, va="center")
        ax[0].set_yticks(yv); ax[0].set_yticklabels([LAB[k] for k in order])
        for t_, k in zip(ax[0].get_yticklabels(), order):
            if k == "S3":
                t_.set_fontweight("bold"); t_.set_color(C["prop"])
        ax[0].set_ylim(yv[-1] - 0.75, yv[0] + 0.6)
        ax[1].set_xlim(0, max(T[k]["ov"] for k in order) * 1.32)
        ax[0].set_xlabel("Operating cost, 30 days ($10^3$ CNY); labels: change vs. proposed"); ax[1].set_xlabel("Energy above connection limit, 30 days (MWh)")
        for a in ax:
            a.grid(axis="y", visible=False); a.grid(axis="x", visible=True); a.tick_params(axis="y", length=0)
        fig.text(0.995, -0.01, "$^\\star$ knows the next 24 h exactly (not implementable); dashed line separates it from online methods",
                 ha="right", va="top", fontsize=6.2, color=MUTED)
        panel(ax[0], "(a)"); panel(ax[1], "(b)")
        save(fig, "fig06_methods")

# ================================================================== Fig. 7 – độ bền
if want("fig07"):
    s, m = csv("fig07_robustness_sensitivity"), csv("fig07_robustness_mismatch")
    if s is None or m is None:
        skip("fig07", "thiếu data")
    else:
        ren = {"baseline assumptions": "Baseline", "transformer 0.5×peak": "Connection limit 0.5×peak", "transformer 0.7×peak": "Connection limit 0.7×peak",
               "transformer 0.8×peak": "Connection limit 0.8×peak", "connection 0.5×peak": "Connection limit 0.5×peak",
               "connection 0.7×peak": "Connection limit 0.7×peak", "connection 0.8×peak": "Connection limit 0.8×peak"}
        lab = [ren.get(x, x[0].upper() + x[1:]) for x in s.case]
        n = len(s); yv = np.arange(n)[::-1]
        fig = plt.figure(figsize=(COL2, 2.75))
        gs = fig.add_gridspec(1, 3, width_ratios=[1, 1, 1.15], wspace=0.08)
        a1 = fig.add_subplot(gs[0]); a2 = fig.add_subplot(gs[1], sharey=a1)
        gs2 = gs[2].subgridspec(1, 1); a3 = fig.add_subplot(gs2[0])
        for yy, (_, r) in zip(yv, s.iterrows()):
            base = r.case.startswith("baseline")
            a1.barh(yy, r.save, height=0.6, color=C["prop"], alpha=1.0 if base else 0.72, ec=INK if base else "none", lw=0.64)
            a2.barh(yy, r.ovred, height=0.6, color=C["bat"], alpha=1.0 if base else 0.72, ec=INK if base else "none", lw=0.64)
            a1.text(r.save + 0.15, yy, f"{r.save:.1f}", va="center", fontsize=6, color=INK)
            a2.text(r.ovred + 0.8, yy, f"{r.ovred:.0f}", va="center", fontsize=6, color=INK)
        a1.set_yticks(yv); a1.set_yticklabels(lab, fontsize=6.6)
        plt.setp(a2.get_yticklabels(), visible=False)
        a1.get_yticklabels()[0].set_fontweight("bold")
        a1.set_xlim(0, s.save.max() * 1.25); a2.set_xlim(0, s.ovred.max() * 1.18)
        a1.set_xlabel("Cost reduction (%)"); a2.set_xlabel("Reduction of energy above limit (%)")
        for a in (a1, a2):
            a.grid(axis="y", visible=False); a.grid(axis="x", visible=True); a.tick_params(axis="y", length=0); a.set_ylim(-0.6, n - 0.4)
        a1.set_title("(a) sensitivity, relative to battery only", loc="left", fontsize=8, fontweight="bold", pad=4)
        MREN = {"M1 smooth plant": "M1 smooth true curves", "M2 2-segment": "M2 2-segment model", "M3 1-segment": "M3 1-segment model",
                "M4 aged, no update": "M4 aged stack, no update", "M5 aged, daily update": "M5 aged stack, daily update",
                "M6 bias +10%": "M6 efficiency bias +10%", "M7 bias −10%": "M7 efficiency bias −10%"}
        mm = m.iloc[::-1].reset_index(drop=True); ym = np.arange(len(mm))
        a3.barh(ym, mm.dcost, height=0.55, color=[C["mpc"] if v < 0 else C["grey"] for v in mm.dcost], lw=0)
        a3.axvline(0, c=BOUND, lw=0.7)
        for yy, (_, r) in zip(ym, mm.iterrows()):
            a3.text(max(r.dcost, 0) + 0.15, yy, f"{r.tank_gap:.0f} kg", va="center", fontsize=6.2, color=MUTED)
        a3.set_yticks(ym); a3.set_yticklabels([MREN.get(x, x) for x in mm.case], fontsize=6.6)
        a3.yaxis.tick_right(); a3.spines["right"].set_visible(True); a3.spines["left"].set_visible(False); a3.tick_params(axis="y", length=0)
        a3.set_xlim(min(mm.dcost.min() * 1.25, -0.5), max(mm.dcost.max(), 0) + 1.6)
        a3.text(0.99, 1.0, "labels: min. tank margin", transform=a3.transAxes, ha="right", va="bottom", fontsize=6.2, color=MUTED)
        a3.set_xlabel("Cost change vs. exact model (%)"); a3.grid(axis="y", visible=False); a3.grid(axis="x", visible=True)
        a3.set_title("(b) model mismatch", loc="left", fontsize=8, fontweight="bold", pad=4)
        save(fig, "fig07_robustness")

# ================================================================== Fig. 8 – lưới 33 nút + mở rộng
if want("fig08"):
    v, sc = csv("fig08_grid_hourly_vmin"), csv("fig08_scale")
    if v is None or sc is None:
        skip("fig08", "thiếu data")
    else:
        fig, ax = plt.subplots(1, 3, figsize=(COL2, 1.95), gridspec_kw=dict(wspace=0.42, width_ratios=[1.35, 1, 1]))
        a = ax[0]; hh = np.append(v.time.to_numpy(), 24)
        ext = lambda col: np.append(v[col].to_numpy(), v[col].iloc[0])
        a.plot(hh, ext("S1"), c=C["bat"], lw=0.68, label="no H$_2$")
        a.plot(hh, ext("S3_grid"), c=C["prop"], lw=0.84, label="proposed, grid-aware")
        a.plot(hh, ext("S1_vv"), c=C["bat"], lw=0.68, ls=(0, (4, 1.8)), label="no H$_2$ + volt–var")
        a.plot(hh, ext("S3_vv"), c=C["prop"], lw=0.84, ls=(0, (4, 1.8)), label="proposed + volt–var")
        a.axhline(0.95, c=BOUND, lw=0.64, ls=(0, (1, 1.4))); a.text(10.3, 0.9497, "0.95 p.u.", fontsize=6.3, color=BOUND, va="top")
        a.set_xlim(0, 24); a.set_xticks(range(0, 25, 6)); a.set_xlabel("Hour of day"); a.set_ylabel("Lowest bus voltage, mean (p.u.)")
        a.legend(loc="lower left", fontsize=6.2, handlelength=2.0, labelspacing=0.25)
        b = ax[1]
        b.plot(sc.N, 1e3 * sc.t, "-o", c=INK, ms=3.3, lw=0.72, label="mean")
        b.plot(sc.N, 1e3 * sc.tmax, "--s", c=MUTED, mfc="white", ms=3.3, lw=0.64, label="max")
        b.set_xticks(sc.N); b.set_xlabel("Charging nodes $N$"); b.set_ylabel("Solve time per step (ms)"); b.set_ylim(0, None)
        b.legend(loc="upper left", fontsize=6.3)
        c = ax[2]
        c.plot(sc.N, sc.ovred, "-s", c=C["bat"], ms=3.4, label="overload")
        c.plot(sc.N, sc.save, "-o", c=C["prop"], ms=3.4, label="cost")
        c.set_xticks(sc.N); c.set_xlabel("Charging nodes $N$"); c.set_ylabel("Reduction vs. battery only (%)"); c.set_ylim(0, max(sc.ovred) * 1.2)
        c.legend(loc="center right", fontsize=6.3)
        panel(a, "(a)"); panel(b, "(b)"); panel(c, "(c)")
        save(fig, "fig08_grid_scale")

# ================================================================== Fig. 9 – H2 so với pin lớn hơn
if want("fig09"):
    bt = csv("fig09_battery_vs_h2_battery")
    if bt is None:
        skip("fig09", "thiếu data")
    else:
        mh = re.search(r"S3 \(H2\)\s+0\s+[\d.]+\s+([\d.]+)%", SUMMARY)
        h2 = float(mh.group(1)) if mh else 23.5
        be = float(np.interp(h2, bt.ovred, bt.added_kWh))
        fig, ax = plt.subplots(figsize=(COL1, 1.95))
        ax.plot(bt.added_kWh / 1e3, bt.ovred, "-s", c=C["bat"], ms=3.4, label="larger battery, no H$_2$")
        ax.plot([0], [h2], "*", c=C["prop"], ms=8, mec="white", mew=0.5, zorder=5, label="H$_2$ chain, proposed")
        ax.plot([0, be / 1e3], [h2, h2], c=C["prop"], lw=0.64, ls=(0, (1, 1.4)))
        ax.plot([be / 1e3, be / 1e3], [0, h2], c=C["prop"], lw=0.64, ls=(0, (1, 1.4)))
        ax.annotate(f"same overload cut with\n+{be / 1e3:.1f} MWh of battery", (be / 1e3, h2), xytext=(4.6, 10), fontsize=6.4, color=INK,
                    arrowprops=dict(arrowstyle="-", lw=0.6, color=MUTED, shrinkB=2))
        ax.set_xlabel("Battery added at Stations 1–3 (MWh)"); ax.set_ylabel("Overload reduction (%)")
        ax.set_xlim(-0.4, bt.added_kWh.max() / 1e3 * 1.04); ax.set_ylim(0, 90)
        ax.legend(loc="upper left", fontsize=6.4)
        save(fig, "fig09_battery_vs_h2")

# ================================================================== Fig. 10 – giá không đủ + khiên cho học sâu
if want("fig10"):
    po = [(int(k), float(d_), float(z)) for k, d_, z in re.findall(r"chỉ giá\s+(\d)\s+([\d.]+)\s+([\d.]+)", SUMMARY)][:4]
    qu = [(int(k), float(d_), float(z)) for k, d_, z in re.findall(r"hàng đợi\s+(\d)\s+([\d.]+)\s+([\d.]+)", SUMMARY)][:4]
    sh = re.findall(r"PPO hạt (\d)\s+([\d,]+)\s+([\d.]+)\s+([\d./]+)\s+([\d.]+)\s+([\d.]+)\s+không\n\s+\+ khiên\s+([\d,]+)\s+([\d.]+)\s+([\d./]+)\s+([\d.]+)", SUMMARY)
    pr = re.search(r"đề xuất S3b\s+([\d,]+)\s+([\d.]+)\s+([\d./]+)\s+([\d.]+)", SUMMARY)
    if len(po) < 2 or not sh:
        skip("fig10", "không đọc được phần 'giá không đủ' / 'khiên' trong FINAL_summary.txt")
    else:
        fig, ax = plt.subplots(1, 2, figsize=(COL2, 2.05), gridspec_kw=dict(wspace=0.34, width_ratios=[1, 1.15]))
        a = ax[0]
        yrs = [0.5 * k for k, _, _ in po]
        a.plot([0] + yrs, [0] + [z for *_, z in po], "-o", c=C["rule"], mfc="white", mew=0.9, label="aging price only")
        a.plot([0] + [0.5 * k for k, _, _ in qu], [0] + [z for *_, z in qu], "-o", c=C["prop"], label="proposed (health queue)")
        a.axhline(0.02, c=BOUND, lw=0.64, ls=(0, (1, 1.4))); a.text(0.05, 0.0205, "buffer $\\theta_Z$", fontsize=6.3, color=BOUND, va="bottom")
        a.axhline(0.0357, c=BOUND, lw=0.64, ls=(0, (4, 2))); a.text(0.05, 0.0362, "guarantee level $Z_{\\max}$", fontsize=6.3, color=BOUND, va="bottom")
        a.set_xlim(0, 2.1); a.set_ylim(0, 0.045); a.set_xticks([0, 0.5, 1, 1.5, 2])
        a.set_xlabel("Year (less durable stack, $k^{\\rm run}=8.5\\,\\mu$V/h)"); a.set_ylabel("Peak health queue $Z$, Station 3")
        a.legend(loc="lower right", fontsize=6.4)
        b = ax[1]
        plan = float(re.search(r"Kế hoạch D sau 120 ngày = ([\d,]+)", SUMMARY).group(1).replace(",", ".")) if re.search(r"Kế hoạch D sau 120 ngày = ([\d,]+)", SUMMARY) else 0.0657
        mz = re.search(r"Z FC lớn nhất / Z_max: \d+: [\d.]+/([\d.]+), \d+: [\d.]+/([\d.]+), \d+: [\d.]+/([\d.]+)", SUMMARY)
        zmx = [float(v_) for v_ in mz.groups()] if mz else [0.0357] * 3          # Z_max từng trạm (thứ tự Trạm 1/2/3)
        bnd = [plan + z_ for z_ in zmx]                                          # cận δt + Z_max của từng trạm
        rat = lambda dl: max(float(v_) / bb for v_, bb in zip(dl.split("/"), bnd))   # trạm xấu nhất, tính theo cận của chính trạm đó
        lab, dmax, dsh = [], [], []
        for s_, c0, o0, dl0, z0, zm, c1, o1, dl1, z1 in sh:
            lab.append(f"PPO seed {s_}"); dmax.append(rat(dl0)); dsh.append(rat(dl1))
        x = np.arange(len(lab)); w = 0.36
        b.bar(x - w / 2, dmax, w, color="#B9B9B9", lw=0, label="PPO alone")
        b.bar(x + w / 2, dsh, w, color=C["prop"], lw=0, label="PPO + health-queue shield")
        if pr:
            b.axhline(rat(pr.group(3)), c=C["prop"], lw=0.7, ls=(0, (4, 2)), label="proposed (no sharing, as PPO)")
        b.axhline(1.0, c=BOUND, lw=0.64, ls=(0, (1, 1.4)), label="guaranteed bound $\\delta t+Z_{\\max}$")
        b.set_xlim(-0.6, len(lab) - 0.4)
        b.set_yscale("log"); b.set_ylim(0.1, 300)
        b.set_xticks(x); b.set_xticklabels(lab); b.set_ylabel("Worst FC degradation / bound, 120 days")
        b.yaxis.set_major_formatter(FuncFormatter(lambda v_, _: f"{v_:g}"))
        for xx, v0, v1 in zip(x, dmax, dsh):
            for xv, vv in ((xx - w / 2, v0), (xx + w / 2, v1)):
                b.text(xv, vv * 1.15, (f"{vv:.3f}" if 0.95 <= vv < 1 else f"{vv:.2f}") if vv < 10 else f"{vv:.0f}", ha="center", va="bottom", fontsize=6.1, color=INK,
                       bbox=dict(fc="white", ec="none", pad=0.4, alpha=0.9))
        b.legend(loc="upper right", fontsize=6.4)
        panel(a, "(a)"); panel(b, "(b)")
        save(fig, "fig10_price_shield")

print(f"XONG → {OUT}")
