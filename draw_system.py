"""
Hình 1 của bài báo – sơ đồ hệ thống và bộ điều khiển (vẽ hoàn toàn bằng code, vector).
    python draw_system.py   → results/paper_figures_final/bai_bao/Fig1_system.pdf / .png / .svg
(a) một trạm sạc có chuỗi H2; (b) bộ điều khiển trực tuyến với ba hàng đợi; (c) khiên bọc bộ điều khiển bất kỳ.
File .svg giữ chữ là chữ – mở bằng Inkscape hoặc draw.io nếu cần chỉnh tay.
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Polygon  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = HERE / "results" / "paper_figures_final" / "bai_bao"
OUT.mkdir(parents=True, exist_ok=True)
plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman", "Times", "Nimbus Roman", "STIXGeneral", "DejaVu Serif"],
                     "mathtext.fontset": "stix", "font.size": 7, "pdf.fonttype": 42, "svg.fonttype": "none"})
ELEC, H2C, CTRL, PROP, INK, GREY = "#1F4E79", "#2E7D32", "#E07B24", "#C8312B", "0.15", "0.55"
LW = 0.8

fig = plt.figure(figsize=(7.16, 2.75))
ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, 28.6); ax.set_ylim(0, 11); ax.axis("off")


def box(x, y, w, h, txt, ec=INK, fc="white", lw=LW, fs=6.8, r=0.18, ls="-", color=INK, **kw):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0.02,rounding_size={r}", ec=ec, fc=fc, lw=lw, ls=ls))
    if txt:
        ax.text(x + w / 2, y + h / 2, txt, ha="center", va="center", fontsize=fs, color=color, linespacing=1.15, **kw)


def arrow(p, q, c=ELEC, lw=1.0, ls="-", both=False, ms=6):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle="<|-|>" if both else "-|>", mutation_scale=ms, lw=lw, color=c, ls=ls,
                                 shrinkA=0, shrinkB=0, joinstyle="miter", capstyle="butt"))


def panel(x, y, w, h, title):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.25", ec=GREY, fc="none", lw=0.6, ls=(0, (4, 2))))
    ax.text(x + 0.25, y + h - 0.3, title, ha="left", va="top", fontsize=7.6, fontweight="bold", color=INK)


# ------------------------------------------------------------------ (a) trạm sạc i
panel(0.15, 0.15, 13.4, 10.7, "(a) Fast-charging station $i$ with an H$_2$ chain")
BUSX, BY0, BY1 = 4.55, 1.0, 8.9
ax.plot([BUSX, BUSX], [BY0, BY1], color=ELEC, lw=3.2, solid_capstyle="butt")
ax.text(BUSX, BY0 - 0.25, "AC bus", ha="center", va="top", fontsize=6.5, color=INK)
# lưới + giới hạn đấu nối
box(0.5, 4.3, 2.3, 1.5, "utility\ngrid", ec=ELEC)
arrow((2.8, 5.05), (BUSX - 0.05, 5.05), both=True)
ax.text(3.65, 5.35, "connection", ha="center", va="bottom", fontsize=6.2, color=INK)
ax.text(3.65, 4.75, r"$P^{\rm tr}_i\leq\overline{P}^{\rm tr}_i$", ha="center", va="top", fontsize=6.6, color=INK)
ax.text(3.6, 4.15, "excess: $c^{\\rm ov}$", ha="center", va="top", fontsize=5.9, color=GREY)
# sang trạm khác
arrow((2.8, 2.15), (BUSX - 0.05, 2.15), c=CTRL, ls=(0, (2, 1.5)), both=True)
box(0.5, 1.45, 2.3, 1.4, "other\nstations", ec=CTRL, ls=(0, (2, 1.5)))
ax.text(3.65, 2.45, "sharing", ha="center", va="bottom", fontsize=6.0, color=CTRL)
# PV
ax.add_patch(Polygon([[5.5, 8.4], [7.4, 8.4], [7.0, 9.4], [5.1, 9.4]], closed=True, ec=ELEC, fc="white", lw=LW))
for k in (1, 2):
    ax.plot([5.1 + 0.63 * k + 0.4 * (1 - k / 3), 5.5 + 0.63 * k], [9.4, 8.4], color=ELEC, lw=0.5)
ax.text(7.6, 8.9, "PV", ha="left", va="center", fontsize=6.8)
arrow((5.3, 8.9), (BUSX + 0.05, 8.9))
# pin
box(5.3, 6.7, 2.4, 1.15, "battery $E_i$", ec=ELEC)
arrow((BUSX + 0.05, 7.27), (5.3, 7.27), both=True)
# bộ sạc
box(5.3, 4.95, 2.4, 1.15, "DC chargers", ec=ELEC)
arrow((BUSX + 0.05, 5.52), (5.3, 5.52))
ax.text(7.95, 5.52, "EV load $P^{\\rm EV}_{i,t}$", ha="left", va="center", fontsize=6.4)
# chuỗi H2
box(5.3, 1.2, 2.4, 1.15, "electrolyzer\n" + r"aging $D^{\rm el}_i$", ec=H2C, fs=6.4)
box(8.25, 1.2, 2.3, 1.15, "compressor", ec=H2C)
box(11.0, 1.2, 2.2, 1.15, "tank $M_i$", ec=H2C, fc="#EAF4EA")
box(11.0, 3.35, 2.2, 1.15, "fuel cell\n" + r"aging $D^{\rm fc}_i$", ec=H2C, fs=6.4)
arrow((BUSX + 0.05, 1.77), (5.3, 1.77))
arrow((7.7, 1.77), (8.25, 1.77), c=H2C)
arrow((10.55, 1.77), (11.0, 1.77), c=H2C)
arrow((12.1, 2.35), (12.1, 3.35), c=H2C)
ax.plot([11.0, 5.0], [3.92, 3.92], color=ELEC, lw=1.0)
arrow((5.0, 3.92), (BUSX + 0.05, 3.92))
ax.text(9.0, 8.3, "seven real stations (Shenzhen);\nH$_2$ chain at Stations 1–3;\nbattery and PV at all stations", ha="left", va="center",
        fontsize=6.2, color=GREY, linespacing=1.3)
# chú thích dòng năng lượng
ly = 0.62
for x0, c, lab, ls in ((5.3, ELEC, "electricity", "-"), (8.15, H2C, "hydrogen", "-"), (10.65, CTRL, "sharing", (0, (2, 1.5)))):
    ax.plot([x0, x0 + 0.7], [ly, ly], color=c, lw=1.0, ls=ls); ax.text(x0 + 0.85, ly, lab, va="center", fontsize=6.2)

# ------------------------------------------------------------------ (b) bộ điều khiển
panel(13.85, 4.0, 14.6, 6.85, "(b) Proposed controller (every 5 min, no forecasts)")
qx, qy = 14.4, 7.55
for k, (sym, lab, c) in enumerate(((r"$B_i$", "battery", ELEC), (r"$H_i$", "tank", H2C), (r"$\hat Z_i$", "stack health", PROP))):
    x = qx + 1.75 * k
    ax.add_patch(FancyBboxPatch((x, qy), 1.25, 0.75, boxstyle="square,pad=0", ec=c, fc="white", lw=LW))
    ax.add_patch(FancyBboxPatch((x, qy), 1.25 * (0.75 - 0.2 * k), 0.75, boxstyle="square,pad=0", ec="none", fc=c, alpha=0.85))
    ax.text(x + 0.62, qy + 1.05, sym, ha="center", va="bottom", fontsize=7.4)
    ax.text(x + 0.62, qy - 0.15, lab, ha="center", va="top", fontsize=6.0)
ax.text(qx + 2.6, 9.65, "virtual queues", ha="center", va="bottom", fontsize=6.2, color=GREY, style="italic")
arrow((19.6, 7.52), (20.25, 7.52), c=INK, lw=0.8)
box(20.25, 6.45, 3.95, 2.15, "per-slot MILP\n$\\min\\; V\\cdot$cost $+$ drift\nstart-up aging prepaid\n(Lemma 1)", ec=INK, fs=6.4)
arrow((24.2, 7.52), (24.75, 7.52), c=PROP, lw=0.8)
box(24.75, 5.95, 3.45, 3.15, "", ec=PROP, fc="#FBEAE9")
ax.text(26.47, 8.75, "on every data path:", ha="center", va="center", fontsize=6.3, color=PROP, style="italic")
ax.text(26.47, 7.55, "tank, battery\nwithin limits\n$D_{i,t}\\leq\\delta t+Z_{\\max}$\nlife $\\geq L(1-Z_{\\max})$", ha="center", va="center",
        fontsize=6.4, color=INK, linespacing=1.2)
ax.text(14.4, 5.0, "$\\hat Z_i=\\max\\{Z_i-\\theta_Z,0\\}$: no effect while aging stays within the buffer $\\theta_Z$ of plan",
        ha="left", va="center", fontsize=6.1, color=INK)
ax.text(14.4, 4.45, "measured $E_i$, $M_i$, $D_i$ update the queues each slot", ha="left", va="center", fontsize=6.1, color=GREY)

# ------------------------------------------------------------------ (c) khiên
panel(13.85, 0.15, 14.6, 3.6, "(c) Health-queue shield around any controller")
box(14.4, 0.6, 3.6, 1.6, "any controller $\\pi$\n(MPC, DRL, operator)", ec=GREY, fs=6.4)
arrow((18.0, 1.4), (18.7, 1.4), c=INK, lw=0.8)
box(18.7, 0.6, 5.0, 1.6, "if $Z^x_{i,t}\\geq Z_{\\max}-\\Delta D_{\\max}$:\nswitch device $x$ off", ec=PROP, fs=6.4)
arrow((23.7, 1.4), (24.4, 1.4), c=INK, lw=0.8)
box(24.4, 0.6, 3.8, 1.6, "same lifetime\nguarantee, no\nretraining", ec=PROP, fc="#FBEAE9", fs=6.4)

for ext in ("pdf", "png", "svg"):
    fig.savefig(OUT / f"Fig1_system.{ext}", dpi=600 if ext == "png" else None, bbox_inches="tight", pad_inches=0.02)
print("  ✓ bai_bao/Fig1_system")
