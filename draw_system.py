"""
BẢN NHÁP Hình 1 – sơ đồ hệ thống (vector). Tự vẽ hoàn toàn (không dùng ảnh có bản quyền).
    python draw_system.py      → results/paper_figures/fig01_system_draft.pdf / .svg / .png
Mở .svg bằng Inkscape (miễn phí) hoặc draw.io để chỉnh chữ, màu, vị trí (chữ trong .svg vẫn là chữ, sửa được).
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch, Polygon, Rectangle  # noqa: E402

HERE = Path(__file__).resolve().parent
PROJECT_DIR = Path(__file__).resolve().parent
if not PROJECT_DIR.exists():
    PROJECT_DIR = HERE
OUT = PROJECT_DIR / "results" / "paper_figures"
OUT.mkdir(parents=True, exist_ok=True)
plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman", "Times", "Nimbus Roman", "STIXGeneral", "DejaVu Serif"],
                     "mathtext.fontset": "stix", "font.size": 7, "pdf.fonttype": 42, "svg.fonttype": "none"})
ELEC, H2C, QC, CTRL, ACC, INK = "#0072B2", "#009E73", "#E69F00", "0.45", "#D55E00", "0.15"

fig = plt.figure(figsize=(7.16, 3.3))
ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, 21.7); ax.set_ylim(0, 10); ax.axis("off")


def box(x, y, w, h, txt, ec=INK, fc="white", lw=0.8, fs=7, r=0.15, **kw):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0.02,rounding_size={r}", ec=ec, fc=fc, lw=lw))
    ax.text(x + w / 2, y + h / 2, txt, ha="center", va="center", fontsize=fs, color=INK, **kw)


def arrow(p, q, c=ELEC, lw=1.2, ls="-", both=False, rad=0.0):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle="<|-|>" if both else "-|>", mutation_scale=6, color=c, lw=lw, ls=ls,
                                 connectionstyle=f"arc3,rad={rad}", shrinkA=0, shrinkB=0))


# ---------------------------------------------------------------- (b) bộ điều khiển (dải trên cùng)
ax.add_patch(FancyBboxPatch((0.15, 7.35), 21.35, 2.4, boxstyle="round,pad=0.02,rounding_size=0.25", ec=INK, fc="white", lw=0.8))
ax.text(0.35, 9.55, "(a) Online degradation-aware Lyapunov controller (every 5 min, no forecasts)", fontsize=7.5, fontweight="bold", va="top")
qs = [("$B_i$", "battery", ELEC), ("$H_i$", "H$_2$ tank", H2C), ("$Z_i$", "FC/EL health", ACC)]
for k, (q, d, c) in enumerate(qs):
    x0 = 0.6 + 1.7 * k
    for j in range(4):
        on = j < 2 + (k == 2)
        ax.add_patch(Rectangle((x0 + 0.22 * j, 8.0), 0.2, 0.5, fc=c if on else "white", ec=c, lw=0.7))
    ax.text(x0 + 0.42, 8.65, q, ha="center", fontsize=8, color=INK)
    ax.text(x0 + 0.42, 7.8, d, ha="center", va="top", fontsize=6.0, color=INK)
ax.text(2.3, 9.05, "virtual queues", ha="center", fontsize=5.8, color="0.4", style="italic")
arrow((5.55, 8.25), (6.15, 8.25), c=CTRL, lw=0.9)
box(6.15, 7.6, 7.45, 1.3, "min  drift $\\Delta L(\\Theta_t)$ + $V\\cdot$cost$_t$  —  per-slot MILP (centralized or ADMM)\n"
    "s.t. safety locks, LinDistFlow voltage limits, volt–var", fs=6.3)
ax.text(17.05, 8.55, "Guarantees for ANY data sequence", ha="center", fontsize=6.6, color=ACC, fontweight="bold")
ax.text(17.05, 7.9, "tank & battery limits  •  FC life $\\geq L(1-Z_{\\max})$\nefficiency floor  •  cost gap $O(1/V)$", ha="center", va="center", fontsize=6.4, color=ACC)
arrow((13.6, 8.25), (14.0, 8.25), c=ACC, lw=0.9)

# ---------------------------------------------------------------- (a) một trạm có H2
ax.add_patch(FancyBboxPatch((0.15, 0.25), 11.0, 6.75, boxstyle="round,pad=0.02,rounding_size=0.25", ec="0.6", fc="#F7F7F7", lw=0.6, ls="--"))
ax.text(0.35, 6.85, "(b) H$_2$-integrated EV fast-charging station $i$", fontsize=7.5, fontweight="bold", va="top")
arrow((4.0, 7.35), (4.0, 7.0), c=CTRL, lw=0.9, ls="--"); ax.text(4.15, 7.17, "set-points", fontsize=5.8, color=CTRL, va="center")
arrow((7.0, 7.0), (7.0, 7.35), c=CTRL, lw=0.9, ls="--"); ax.text(7.15, 7.17, "measurements $E, M, D, P^{\\rm EV}$", fontsize=5.8, color=CTRL, va="center")
for k in range(3):                                   # cột điện đơn giản
    ax.plot([0.75 + 0.18 * k, 0.75 + 0.18 * k], [3.0, 4.6], c=INK, lw=0.6)
ax.plot([0.55, 1.3], [4.4, 4.4], c=INK, lw=0.6); ax.plot([0.6, 1.25], [4.0, 4.0], c=INK, lw=0.6)
ax.text(0.95, 2.7, "utility\ngrid", ha="center", va="top", fontsize=6.3)
ax.add_patch(Circle((2.15, 3.75), 0.3, fc="white", ec=INK, lw=0.8)); ax.add_patch(Circle((2.53, 3.75), 0.3, fc="white", ec=INK, lw=0.8))
ax.text(2.34, 3.2, "transformer\n$P^{\\rm tr}_{i}\\leq\\bar P^{\\rm tr}_{i}$", ha="center", va="top", fontsize=6.0)
arrow((1.35, 3.75), (1.85, 3.75), both=True)
ax.add_patch(Rectangle((3.3, 0.9), 0.16, 5.4, fc=ELEC, ec="none")); ax.text(3.38, 0.62, "AC bus", ha="center", fontsize=6.0)
arrow((2.83, 3.75), (3.3, 3.75), both=True)
# PV
ax.add_patch(Polygon([[4.2, 5.55], [5.3, 5.55], [5.6, 6.2], [4.5, 6.2]], closed=True, fc="#DCEAF7", ec=ELEC, lw=0.8))
for t in (0.33, 0.66):
    ax.plot([4.2 + 1.1 * t, 4.5 + 1.1 * t], [5.55, 6.2], c=ELEC, lw=0.4)
ax.text(5.75, 5.9, "PV", va="center", fontsize=6.3)
arrow((4.25, 5.85), (3.46, 5.85))
# pin
box(4.1, 3.95, 1.6, 0.75, "battery\n$E_i$", ec=ELEC, fs=6.2); arrow((3.46, 4.32), (4.1, 4.32), both=True)
arrow((5.7, 4.5), (6.3, 4.5), c=QC, lw=1.0); ax.text(6.36, 4.5, "$Q$", va="center", fontsize=6.3)
# trụ sạc + xe
box(4.1, 2.55, 1.6, 0.75, "DC fast\nchargers", ec=ELEC, fs=6.2); arrow((3.46, 2.92), (4.1, 2.92))
car = Polygon([[6.1, 2.65], [7.35, 2.65], [7.35, 2.95], [7.05, 3.25], [6.4, 3.25], [6.15, 2.95]], closed=True, fc="white", ec=INK, lw=0.7)
ax.add_patch(car); ax.add_patch(Circle((6.4, 2.62), 0.11, fc=INK)); ax.add_patch(Circle((7.05, 2.62), 0.11, fc=INK))
ax.text(6.75, 2.38, "EV load $P^{\\rm EV}_{i}$", ha="center", va="top", fontsize=6.0); arrow((5.7, 2.92), (6.1, 2.92))
# EL – máy nén – bồn – FC – vòi
box(4.1, 1.05, 1.6, 0.8, "electrolyzer\n(EL)", ec=H2C, fs=6.2); arrow((3.46, 1.45), (4.1, 1.45))
box(6.05, 1.05, 1.45, 0.8, "compressor", ec=H2C, fs=6.2); arrow((5.7, 1.45), (6.05, 1.45), c=H2C)
ax.add_patch(FancyBboxPatch((7.85, 0.95), 1.45, 1.0, boxstyle="round,pad=0.02,rounding_size=0.42", fc="#E3F4EE", ec=H2C, lw=0.9))
ax.text(8.575, 1.45, "H$_2$ tank\n$M_i$", ha="center", va="center", fontsize=6.2)
arrow((7.5, 1.45), (7.85, 1.45), c=H2C)
box(7.85, 3.95, 1.45, 0.8, "fuel cell (FC)\n+ inverter", ec=H2C, fs=6.2); arrow((8.575, 1.95), (8.575, 3.95), c=H2C)
ax.plot([8.575, 8.575, 3.46], [4.75, 5.15, 5.15], c=ELEC, lw=1.2); arrow((3.9, 5.15), (3.46, 5.15))
box(9.55, 1.05, 1.45, 0.8, "dispenser\n(FCEV sales)", ec=H2C, fs=6.2); arrow((9.3, 1.45), (9.55, 1.45), c=H2C)
arrow((9.3, 4.55), (9.9, 4.55), c=QC, lw=1.0); ax.text(9.95, 4.55, "$Q$ (volt–var)", va="center", fontsize=6.0)
ax.add_patch(FancyBboxPatch((9.5, 2.55), 1.5, 0.9, boxstyle="round,pad=0.02,rounding_size=0.12", fc="#FBE3D6", ec=ACC, lw=1.1))
ax.text(10.25, 3.0, "degradation $D_i$\n→ queue $Z_i$", ha="center", va="center", fontsize=6.0)
ax.plot([9.3, 9.5], [4.1, 3.3], c=ACC, lw=0.9, ls=":")

# ---------------------------------------------------------------- (c) mạng 7 trạm trên lưới 33 nút
ax.add_patch(FancyBboxPatch((11.55, 0.25), 9.95, 6.75, boxstyle="round,pad=0.02,rounding_size=0.25", ec="0.6", fc="#F7F7F7", lw=0.6, ls="--"))
ax.text(11.75, 6.85, "(c) 7 real Shenzhen stations on the IEEE 33-bus feeder", fontsize=7.5, fontweight="bold", va="top")
arrow((16.5, 7.35), (16.5, 7.0), c=CTRL, lw=0.9, ls="--", both=True)
sx, sy, X0, Y0 = 0.52, 0.95, 12.15, 4.0
pos = {b: (b, 0) for b in range(18)}
pos.update({18 + k: (1 + k + 1, -1) for k in range(4)}); pos.update({22 + k: (2 + k + 1, 1) for k in range(3)})
pos.update({25 + k: (5 + k + 1, -2) for k in range(8)})
P = {b: (X0 + sx * x, Y0 + sy * y) for b, (x, y) in pos.items()}
edges = [(b, b + 1) for b in range(17)] + [(1, 18), (18, 19), (19, 20), (20, 21), (2, 22), (22, 23), (23, 24), (5, 25)] + [(25 + k, 26 + k) for k in range(7)]
for u, v in edges:
    ax.plot([P[u][0], P[v][0]], [P[u][1], P[v][1]], c="0.35", lw=0.9)
for b, (x, y) in P.items():
    ax.add_patch(Circle((x, y), 0.06, fc="0.35", ec="none"))
ax.add_patch(Rectangle((P[0][0] - 0.3, P[0][1] - 0.2), 0.25, 0.4, fc="white", ec=INK, lw=0.8)); ax.text(P[0][0] - 0.18, P[0][1] + 0.32, "substation", ha="center", fontsize=5.8)
BUS_OF = {1589: 17, 1242: 32, 1093: 24, 1214: 21, 1061: 8, 1087: 13, 1229: 29}
H2S = {1589, 1242, 1093}
for st, b in BUS_OF.items():
    x, y = P[b]
    if st in H2S:
        ax.add_patch(Polygon([[x, y + 0.45], [x - 0.24, y + 0.07], [x + 0.24, y + 0.07]], closed=True, fc=H2C, ec=INK, lw=0.6))
    else:
        ax.add_patch(Rectangle((x - 0.17, y + 0.08), 0.34, 0.3, fc=ELEC, ec=INK, lw=0.6))
    ax.text(x, y + 0.55, f"#{st}", ha="center", fontsize=5.6)
for a_, b_ in ((1589, 1087), (1242, 1229), (1061, 1087)):    # minh họa chia sẻ công suất giữa các trạm
    arrow((P[BUS_OF[a_]][0], P[BUS_OF[a_]][1] + 0.75), (P[BUS_OF[b_]][0], P[BUS_OF[b_]][1] + 0.75), c=ACC, lw=0.7, ls=":", both=True, rad=0.25)
ax.add_patch(Polygon([[12.15, 1.62], [12.0, 1.38], [12.3, 1.38]], closed=True, fc=H2C, ec=INK, lw=0.5)); ax.text(12.45, 1.48, "station with H$_2$ (FC, EL, tank)", va="center", fontsize=5.8)
ax.add_patch(Rectangle((16.4, 1.37), 0.25, 0.22, fc=ELEC, ec=INK, lw=0.5)); ax.text(16.75, 1.48, "station with battery only", va="center", fontsize=5.8)
items = [(ELEC, "-", "electric power"), (H2C, "-", "hydrogen"), (QC, "-", "reactive power"), (CTRL, "--", "measurement / control"), (ACC, ":", "inter-station sharing")]
for k, (c, ls, t) in enumerate(items):
    xx, yy = 12.0 + 3.2 * (k % 3), 0.95 - 0.42 * (k // 3)
    ax.plot([xx, xx + 0.45], [yy, yy], c=c, ls=ls, lw=1.2); ax.text(xx + 0.55, yy, t, va="center", fontsize=5.8)

for ext in ("pdf", "svg", "png"):
    fig.savefig(OUT / f"fig01_system_draft.{ext}", dpi=600 if ext == "png" else None, bbox_inches="tight", pad_inches=0.02)
print("Đã ghi:", OUT / "fig01_system_draft.pdf", "(+ .svg để chỉnh, .png)")
