"""
VIỆC 2.5 – HÌNH ĐỊNH LÝ 1: khoảng cách tới tối ưu C* theo V, và cái giá phải trả khi tăng V.
Không mô phỏng mới: đọc kết quả quét V (việc 1.3) và C* (việc 1.5).
Đặt trong DATN2026 rồi chạy:
    python plot_theorem1.py                      # mặc định: 7 ngày từ 2022-11-01, w_Z = 3e8
    python plot_theorem1.py --wz 1e10            # nếu có quét V với w_Z khác

Cần có:
  results/step3_batch_<start>_<days>d_S3_wZ<..>_V<v>/   (run_batch.py --days 7 --wz 3e8 --V 0.1,0.25,0.5,1 --no_s1)
  results/cstar_<start>_<days>d/cstar.json              (step4_cstar.py --milp ...  → C* trong [cận dưới, cận trên])
  results/cstar_LP/cstar.json                            (tùy chọn: bản LP cũ, để so)

Định lý 1:  chi phí TB ≤ C* + (A+ε)/V + β_sw   → khoảng cách giảm khi V tăng (tới một sàn).
Bù lại (phía "O(V)"): Z_max tăng theo V → tuổi thọ BẢO ĐẢM L(1−Z_max) giảm (Hệ quả 1), bồn/pin lệch xa mức θ hơn.
Hình gồm 3 ô: (a) khoảng cách tới C*; (b) tuổi thọ FC bảo đảm và thực tế; (c) độ lệch bồn, pin khỏi θ.
Ghi: results/theorem1_<start>_<days>d/summary.txt + fig_theorem1.png   ← GỬI CHO CLAUDE
"""
import argparse
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
HERE = Path(__file__).resolve().parent
PROJECT_DIR = Path(__file__).resolve().parent
if not PROJECT_DIR.exists():
    PROJECT_DIR = HERE
RES = PROJECT_DIR / "results"
H2_ST = ("1093", "1242", "1589")

ap = argparse.ArgumentParser()
ap.add_argument("--start", default="2022-11-01")
ap.add_argument("--days", type=int, default=7)
ap.add_argument("--wz", default="1e10", help="w_Z của lần quét V (theo tên thư mục, ví dụ 3e8)")
args = ap.parse_args()
batch = f"batch_{args.start}_{args.days}d"
OUT = RES / (f"theorem1_{args.start}_{args.days}d" + ("" if args.wz == "3e8" else f"_wz{args.wz}"))
OUT.mkdir(parents=True, exist_ok=True)

# ------------------------------------------------------------------ đọc các lần quét V
runs = {}
for d in RES.glob(f"step3_{batch}_S3_wZ{args.wz}_V*"):
    m = re.search(r"_V([\d\.]+)$", d.name)
    if m and (d / "summary.txt").exists() and (d / "timeseries.csv").exists():
        runs[float(m.group(1))] = d
if len(runs) < 2:
    raise SystemExit(f"Cần ít nhất 2 giá trị V. Chạy trước:\n  python run_batch.py --days {args.days} --start {args.start} "
                     f"--wz {args.wz} --V 0.1,0.25,0.5,1 --no_s1")
Vs = sorted(runs)

params = json.loads((PROJECT_DIR / "params" / "params_tier1.json").read_text(encoding="utf-8"))
L_fc = params["aging_and_devices"]["fc"]["life_target_h"] / 8760


def grab(pat, s, default=float("nan")):
    m = re.search(pat, s)
    return float(m.group(1).replace(",", "")) if m else default


rows = []
for V in Vs:
    s = (runs[V] / "summary.txt").read_text(encoding="utf-8")
    r = dict(V=V, cost=grab(r"K2 – chi phí \(gồm giá lão hóa\): ([\d,\.]+) CNY", s),
             ov=grab(r"vượt giới hạn MBA ([\d\.]+) MWh", s), fails=s.count("KHÔNG ĐẠT"))
    ts = pd.read_csv(runs[V] / "timeseries.csv", index_col=0)
    for st in H2_ST:
        m = re.search(rf"\n\s+{st}: PV.*?pin ([\d\.]+) kWh.*?θ\^B=([\d\.]+) kWh.*?bồn ([\d\.]+) kg.*?θ\^H=([\d\.]+) kg.*?Z_max\(FC/EL\)=([\d\.]+)/([\d\.]+)", s)
        Ecap, thB, Mcap, thH, zf, ze = (float(x) for x in m.groups())
        r[f"zmax_{st}"] = zf
        r[f"zobs_{st}"] = grab(rf"Bổ đề 3 – trạm {st}: max Z_FC = ([\d\.e\+\-]+)", s)
        r[f"life_{st}"] = grab(rf"Trạm {st}:.*\n\s+K7 – tuổi thọ dự kiến theo tốc độ kỳ này: FC ([\d\.]+) năm", s)
        r[f"h2_{st}"] = grab(rf"Trạm {st}: H2 làm ra [\-\d\.]+ kg, dùng ([\d\.]+) kg", s)
        r[f"devH_{st}"] = float(np.mean(np.abs(ts[f"M_{st}"] - thH)) / Mcap)
        r[f"devB_{st}"] = float(np.mean(np.abs(ts[f"E_{st}"] - thB)) / Ecap)
    rows.append(r)
df = pd.DataFrame(rows).set_index("V")

# ------------------------------------------------------------------ C*
cj = RES / f"cstar_{args.start}_{args.days}d" / "cstar.json"
if not cj.exists():
    raise SystemExit(f"Thiếu {cj}. Chạy step4_cstar.py --days {args.days} --start {args.start} --milp ... trước.")
c = json.loads(cj.read_text(encoding="utf-8"))
if c["mode"] == "MILP":
    c_ub, c_lb = c["C_star"], c["lower_bound"]
else:
    c_ub, c_lb = float("nan"), c["C_star"]
lp = RES / "cstar_LP" / "cstar.json"
c_lp = json.loads(lp.read_text(encoding="utf-8"))["C_star"] if lp.exists() else float("nan")
df["gap_lo"] = 100 * (df["cost"] / c_ub - 1)     # khoảng cách tối thiểu (so với lời giải tốt nhất ≥ C*)
df["gap_hi"] = 100 * (df["cost"] / c_lb - 1)     # khoảng cách tối đa (so với cận dưới ≤ C*)
df["h2"] = sum(df[f"h2_{st}"] for st in H2_ST)
df["zmax_worst"] = df[[f"zmax_{st}" for st in H2_ST]].max(axis=1)
df["life_guar"] = L_fc * (1 - df["zmax_worst"])
df["life_real"] = df[[f"life_{st}" for st in H2_ST]].min(axis=1)

# ------------------------------------------------------------------ báo cáo
L = [f"VIỆC 2.5 – ĐỊNH LÝ 1 – {args.days} ngày từ {args.start}, w_Z = {args.wz}",
     f"C* ({c['mode']}, {c.get('solver', '')}): " + (f"nằm trong [{c_lb:,.0f} ; {c_ub:,.0f}] CNY (gap bộ giải {100 * (c_ub / c_lb - 1):.2f}%)"
                                                     if c["mode"] == "MILP" else f"C*_LP = {c_lb:,.0f} CNY (cận dưới)")
     + (f" | bản LP cũ: {c_lp:,.0f} CNY ({100 * (c_lb / c_lp - 1):+.2f}% so với cận dưới MILP)" if np.isfinite(c_lp) and c["mode"] == "MILP" else ""),
     "",
     f"{'V':>6}{'chi phí CNY':>14}{'cách C* (%)':>18}{'vượt MBA':>10}{'H2 dùng':>9}{'Z_max FC':>10}{'max Z thực':>12}"
     f"{'tuổi thọ FC':>13}{'tuổi thọ FC':>13}{'lệch bồn':>10}{'lệch pin':>10}  lý thuyết",
     f"{'':>6}{'':>14}{'[thấp ; cao]':>18}{'MWh':>10}{'kg':>9}{'(xấu nhất)':>10}{'(xấu nhất)':>12}"
     f"{'bảo đảm (n)':>13}{'thực tế (n)':>13}{'TB/cỡ':>10}{'TB/cỡ':>10}"]
for V, r in df.iterrows():
    zobs = max(r[f"zobs_{st}"] for st in H2_ST)
    L.append(f"{V:>6g}{r['cost']:>14,.0f}{'[' + format(r['gap_lo'], '.1f') + ' ; ' + format(r['gap_hi'], '.1f') + ']':>18}"
             f"{r['ov']:>10.2f}{r['h2']:>9.0f}{r['zmax_worst']:>10.3f}{zobs:>12.2e}{r['life_guar']:>13.2f}{r['life_real']:>13.1f}"
             f"{np.mean([r[f'devH_{st}'] for st in H2_ST]):>10.3f}{np.mean([r[f'devB_{st}'] for st in H2_ST]):>10.3f}"
             f"  {'ĐẠT hết' if r['fails'] == 0 else str(int(r['fails'])) + ' KHÔNG ĐẠT'}")
mono = bool(np.all(np.diff(df["cost"].to_numpy()) < 0))
L += ["",
      "Đọc bảng:",
      f"  • Chi phí giảm {'đều' if mono else 'KHÔNG đều'} khi V tăng: từ {df['cost'].iloc[0]:,.0f} (V={Vs[0]:g}) xuống {df['cost'].iloc[-1]:,.0f} (V={Vs[-1]:g}) CNY "
      f"→ khoảng cách tới C* từ {df['gap_hi'].iloc[0]:.1f}% xuống {df['gap_hi'].iloc[-1]:.1f}% (cận cao). Đúng chiều của Định lý 1 (số hạng (A+ε)/V).",
      f"  • Cái giá: Z_max (xấu nhất) tăng từ {df['zmax_worst'].iloc[0]:.3f} lên {df['zmax_worst'].iloc[-1]:.3f} → tuổi thọ FC BẢO ĐẢM (Hệ quả 1) giảm từ "
      f"{df['life_guar'].iloc[0]:.2f} xuống {df['life_guar'].iloc[-1]:.2f} năm; bồn/pin lệch khỏi θ nhiều hơn (dùng kho tích cực hơn).",
      "  • Hằng số của Định lý 1 rất lỏng (đã nói trong file lý thuyết) nên hình dùng KHOẢNG CÁCH ĐO ĐƯỢC, không vẽ đường cận A/V.",
      "  • 'max Z thực' nhỏ hơn Z_max nhiều bậc: bảo đảm tuổi thọ là cho trường hợp xấu nhất; thực tế còn rất xa giới hạn.",
      "  • Tuổi thọ 'thực tế' là ngoại suy theo tốc độ già của kỳ chạy ngắn (chứa cả phần Z/T) – chỉ để tham khảo."]

# ------------------------------------------------------------------ hình
fig, ax = plt.subplots(1, 3, figsize=(15, 4.4))
x = df.index.to_numpy()
ax[0].fill_between(x, df["gap_lo"], df["gap_hi"], color="tab:blue", alpha=.25, label="khoảng cách thật nằm trong dải")
ax[0].plot(x, df["gap_hi"], "o-", c="tab:blue", label="so với cận dưới C* (cao nhất)")
if np.isfinite(c_ub):
    ax[0].plot(x, df["gap_lo"], "s--", c="tab:blue", ms=4, label="so với lời giải C* tốt nhất (thấp nhất)")
ax[0].set_xscale("log"); ax[0].set_xticks(x); ax[0].set_xticklabels([f"{v:g}" for v in x])
ax[0].set_xlabel("V"); ax[0].set_ylabel("chi phí cao hơn C* (%)"); ax[0].set_title("(a) Khoảng cách tới tối ưu C*")
ax[0].grid(alpha=.3); ax[0].legend(fontsize=7)
ax[1].plot(x, df["life_guar"], "o-", c="k", label="bảo đảm L(1−Z_max) – Hệ quả 1")
ax[1].plot(x, df["life_real"], "^-", c="tab:green", label="thực tế (ngoại suy kỳ chạy)")
ax[1].axhline(L_fc, c="gray", ls=":", label=f"mục tiêu {L_fc:g} năm")
ax[1].set_xscale("log"); ax[1].set_xticks(x); ax[1].set_xticklabels([f"{v:g}" for v in x])
ax[1].set_xlabel("V"); ax[1].set_ylabel("tuổi thọ FC thấp nhất (năm)"); ax[1].set_title("(b) Cái giá: bảo đảm tuổi thọ yếu đi")
ax[1].grid(alpha=.3); ax[1].legend(fontsize=7)
for st, mk in zip(H2_ST, "osd"):
    ax[2].plot(x, 100 * df[f"devH_{st}"], mk + "-", label=f"bồn {st}")
ax[2].plot(x, 100 * np.mean([df[f"devB_{st}"] for st in H2_ST], axis=0), "x--", c="gray", label="pin (TB 3 trạm)")
ax[2].set_xscale("log"); ax[2].set_xticks(x); ax[2].set_xticklabels([f"{v:g}" for v in x])
ax[2].set_xlabel("V"); ax[2].set_ylabel("lệch TB khỏi θ (% dung lượng)"); ax[2].set_title("(c) Kho được dùng tích cực hơn khi V tăng")
ax[2].grid(alpha=.3); ax[2].legend(fontsize=7)
fig.suptitle(f"Định lý 1 – đánh đổi chi phí – tuổi thọ theo V ({args.days} ngày từ {args.start}, w_Z = {args.wz})")
fig.tight_layout(); fig.savefig(OUT / "fig_theorem1.png", dpi=150); plt.close(fig)

txt = "\n".join(L)
(OUT / "summary.txt").write_text(txt, encoding="utf-8")
print(txt + f"\n\nĐã ghi: {OUT / 'summary.txt'}\n        {OUT / 'fig_theorem1.png'}")
