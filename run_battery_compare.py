"""
VIỆC 2.6 – H2 SO VỚI PIN LỚN HƠN: "Sao không bỏ tiền H2 ra mua thêm pin?"

Cách làm (không phụ thuộc giá nào):
  1) Chạy S1 (không H2) nhưng pin ở 3 trạm H2 (1093, 1242, 1589) lớn gấp m lần, m = 1,5 / 2 / 3 / 5 / 7.
     Cùng thuật toán Lyapunov, cùng dữ liệu, giữ tỉ lệ pin 2 giờ (kW = kWh/2).
  2) Tìm lượng pin THÊM cần có để giảm vượt tải BẰNG đề xuất H2 (S3) → "pin hòa vốn" (kWh).
  3) So vốn: H2 rẻ hơn pin ⇔ vốn H2 < (pin hòa vốn) × giá pin. Bảng tính với giá thấp / cơ sở / cao có nguồn.

Đặt trong DATN2026 rồi chạy (6 tháng, 3 lần chạy song song, khoảng 1 giờ trên laptop 4 nhân):
    python run_battery_compare.py
    python run_battery_compare.py --days 30 --start 2022-11-01     # thử nhanh 30 ngày (~5 phút)
S1 và S3 lấy lại từ việc 2.3 (batch_<start>_<days>d) nếu đã có, không chạy lại.
Ghi: results/battery_compare_<start>_<days>d/summary.txt + fig_battery_compare.png   ← GỬI CHO CLAUDE
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
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
STEP3 = PROJECT_DIR / "step3_simulate.py"
if not STEP3.exists() or '"--bat_scale_h2"' not in STEP3.read_text(encoding="utf-8", errors="ignore"):
    raise SystemExit("Cần step3_simulate.py BẢN MỚI (có --bat_scale_h2) trong DATN2026.")

# Giá vốn (CNY) – nguồn ghi trong báo cáo; cơ sở = số thị trường TQ gần kỳ dữ liệu nhất
PRICE = {   # (thấp, cơ sở, cao)
    "fc_kW":   (2500, 3756, 5578),   # Sino-Synergy: 5578 (2022), 3756 (5 tháng đầu 2023); dự báo F&S 2025: 2500
    "el_kW":   (2200, 6000, 11000),  # kiềm TQ ≈ $303/kW (2021) ≈ 2200; PEM phương Tây ≈ €1400/kW ≈ 11000; cơ sở PEM TQ: giả định
    "tank_kg": (3500, 5000, 7000),   # bồn + máy nén cố định, giả định (≈ $500–1000/kg) – xác minh ở việc 4.4
    "bat_kWh": (540, 627, 1000),     # CNESA 4/2024: hệ 2 giờ TB 0,627 CNY/Wh, thấp nhất 0,54; trạm thương mại nhỏ đắt hơn → 1000
}

ap = argparse.ArgumentParser()
ap.add_argument("--days", type=int, default=0, help="0 = toàn bộ 6 tháng")
ap.add_argument("--start", default="2022-09-01")
ap.add_argument("--m", default="1.5,2,3,5,7", help="hệ số nhân pin ở trạm H2")
ap.add_argument("--wz", default="1e10", help="w_Z của S3 để so")
ap.add_argument("--jobs", type=int, default=3)
ap.add_argument("--h2_demand_frac", default="0", help="việc 2.7: bật bán H2 cho FCEV (ví dụ 0.5); 0 = tắt")
ap.add_argument("--c_ext", default="40", help="giá H2 mua ngoài CNY/kg")
args = ap.parse_args()
if args.days <= 0:
    import pandas as pd
    ix = pd.read_csv(PROJECT_DIR / "data_clean" / "tier1_inputs.csv", usecols=[0], index_col=0, parse_dates=True).index
    start, days, days_arg = str(ix[0].date()), int(round((ix[-1] - ix[0]).total_seconds() / 86400 + 1 / 288)), "0"
else:
    start, days, days_arg = args.start, args.days, str(args.days)
batch = f"batch_{start}_{days}d"
DEM = float(args.h2_demand_frac) > 0
sfx = f"_dem{args.h2_demand_frac}_c{args.c_ext}" if DEM else ""
dem_opt = ["--h2_demand_frac", args.h2_demand_frac, "--c_ext", args.c_ext] if DEM else []
OUT = RES / (f"battery_compare_{start}_{days}d{sfx}" + ("" if args.wz == "3e8" else f"_wz{args.wz}"))
OUT.mkdir(parents=True, exist_ok=True)
params = json.loads((PROJECT_DIR / "params" / "params_tier1.json").read_text(encoding="utf-8"))
H2ST = [s for s in params["stations"] if s.get("has_h2")]
bat0 = sum(s["bat_kWh"] for s in H2ST)

summ = lambda tag: RES / f"step3_{tag}" / "summary.txt"
jobs = [("S1", f"{batch}_S1{sfx}", ["--no_h2", "--wz", "1e10"] + dem_opt),
        ("S3", f"{batch}_S3_wZ{args.wz}{sfx}", ["--wz", args.wz, "--V", "1"] + dem_opt)]
for m in args.m.split(","):
    jobs.append((f"pin×{m}", f"{batch}_BAT{m}{sfx}", ["--no_h2", "--wz", "1e10", "--bat_scale_h2", m] + dem_opt))
env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
pending = [j for j in jobs if not summ(j[1]).exists()]
for j in jobs:
    if j not in pending:
        print(f"[dùng lại] {j[0]}: {summ(j[1])}")
running, t_all = {}, time.time()
logdir = OUT / "logs"; logdir.mkdir(exist_ok=True)
while pending or running:
    while pending and len(running) < max(1, args.jobs):
        name, tag, opt = pending.pop(0)
        cmd = [sys.executable, str(STEP3), "--days", days_arg, "--start", start, "--tag", tag] + opt
        lf = open(logdir / f"{tag}.log", "w", encoding="utf-8")
        print(f"=== bắt đầu {name}", flush=True)
        running[name] = (subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT, env=env), time.time(), lf, tag)
    time.sleep(5)
    for name in list(running):
        pr, t0, lf, tag = running[name]
        if pr.poll() is None:
            continue
        lf.close(); del running[name]
        ok = pr.returncode == 0 and summ(tag).exists()
        print(f"    {name}: {'xong' if ok else 'LỖI – xem ' + str(logdir / (tag + '.log'))} sau {(time.time() - t0) / 60:.1f} phút "
              f"(tổng {(time.time() - t_all) / 60:.0f} phút, còn {len(pending) + len(running)} việc)", flush=True)


def grab(pat, s):
    m = re.search(pat, s)
    return float(m.group(1).replace(",", "")) if m else float("nan")


R = {}
for name, tag, _ in jobs:
    if not summ(tag).exists():
        continue
    s = summ(tag).read_text(encoding="utf-8")
    lives = [float(x) for x in re.findall(r"tuổi thọ dự kiến theo tốc độ kỳ này: FC ([\d\.]+) năm", s)]
    R[name] = dict(cost=grab(r"K2 – chi phí \(gồm giá lão hóa\): ([\d,\.]+) CNY", s), ov=grab(r"vượt giới hạn MBA ([\d\.]+) MWh", s),
                   life=min(lives) if lives else float("nan"))
if "S1" not in R or "S3" not in R:
    raise SystemExit("Thiếu S1 hoặc S3 – xem logs.")
s1, s3 = R["S1"], R["S3"]
red = lambda r: 100 * (1 - r["ov"] / s1["ov"])
ms = [float(m) for m in args.m.split(",") if f"pin×{m}" in R]
extra = [(m - 1) * bat0 for m in ms]
red_b = [red(R[f"pin×{m:g}"]) if f"pin×{m:g}" in R else red(R[f"pin×{m}"]) for m in ms]
cost_b = [R[f"pin×{m:g}"]["cost"] for m in ms]

# pin hòa vốn: nội suy lượng pin thêm để giảm vượt tải bằng S3
xs, ys = [0.0] + extra, [0.0] + red_b
target = red(s3)
be = float("nan")
for k in range(len(xs) - 1):
    if ys[k] <= target <= ys[k + 1]:
        be = xs[k] + (target - ys[k]) * (xs[k + 1] - xs[k]) / (ys[k + 1] - ys[k]); break

capex = lambda col: sum(s["fc_kW"] * PRICE["fc_kW"][col] + s["el_kW"] * PRICE["el_kW"][col] + s["tank_kg"] * PRICE["tank_kg"][col] for s in H2ST)
L = [f"VIỆC 2.6 – H2 SO VỚI PIN LỚN HƠN – {days} ngày từ {start}"
     + (f" | CÓ BÁN H2 CHO FCEV (nhu cầu {args.h2_demand_frac} × sản lượng EL, H2 ngoài {args.c_ext} CNY/kg; S1 và pin phải MUA NGOÀI toàn bộ H2)" if DEM else ""),
     f"Pin hiện có ở 3 trạm H2: {bat0:.0f} kWh. H2 ở 3 trạm: FC {sum(s['fc_kW'] for s in H2ST):.0f} kW, EL {sum(s['el_kW'] for s in H2ST):.0f} kW, "
     f"bồn {sum(s['tank_kg'] for s in H2ST):.0f} kg.", "",
     f"{'kịch bản':<12}{'pin thêm kWh':>14}{'vượt MBA MWh':>14}{'giảm so S1':>12}{'chi phí CNY':>14}{'so S1':>9}{'FC thấp nhất':>14}",
     f"{'S1':<12}{0:>14.0f}{s1['ov']:>14.2f}{0:>11.1f}%{s1['cost']:>14,.0f}{0:>8.1f}%{'—':>14}",
     f"{'S3 (H2)':<12}{0:>14.0f}{s3['ov']:>14.2f}{red(s3):>11.1f}%{s3['cost']:>14,.0f}{100 * (s3['cost'] / s1['cost'] - 1):>8.1f}%{s3['life']:>12.1f} n"]
for m, e, rb, cb in zip(ms, extra, red_b, cost_b):
    L.append(f"{'pin ×' + format(m, 'g'):<12}{e:>14.0f}{R[f'pin×{m:g}']['ov']:>14.2f}{rb:>11.1f}%{cb:>14,.0f}{100 * (cb / s1['cost'] - 1):>8.1f}%{'—':>14}")
L += ["",
      f"PIN HÒA VỐN: cần thêm ≈ {be:,.0f} kWh pin (pin × {1 + be / bat0:.2f}) để giảm vượt tải bằng H2 ({target:.1f}%)." if np.isfinite(be)
      else f"PIN HÒA VỐN: ngoài dải đã thử (pin ×{max(ms):g} giảm {max(red_b):.1f}% so với H2 {target:.1f}%) – thêm m lớn hơn vào --m.",
      "",
      "SO VỐN ĐẦU TƯ (H2 rẻ hơn ⇔ vốn H2 < pin hòa vốn × giá pin):",
      f"{'':<28}{'thấp':>14}{'cơ sở':>14}{'cao':>14}",
      f"{'vốn H2 (FC+EL+bồn), CNY':<28}" + "".join(f"{capex(c):>14,.0f}" for c in range(3)),
      f"{'giá pin, CNY/kWh':<28}" + "".join(f"{PRICE['bat_kWh'][c]:>14,.0f}" for c in range(3)),
      f"{'pin cùng vốn H2, kWh':<28}" + "".join(f"{capex(c) / PRICE['bat_kWh'][c]:>14,.0f}" for c in range(3))]
if np.isfinite(be):
    L.append(f"{'vốn pin hòa vốn, CNY':<28}" + "".join(f"{be * PRICE['bat_kWh'][c]:>14,.0f}" for c in range(3)))
    L.append("  (cột 'thấp' = giá H2 thấp & pin thấp; muốn xét trường hợp xấu nhất cho H2: vốn H2 cao so với pin thấp)")
    L.append(f"  Trường hợp tốt nhất cho H2: vốn H2 thấp {capex(0):,.0f} so với pin đắt {be * PRICE['bat_kWh'][2]:,.0f} CNY → "
             f"{'H2 RẺ HƠN' if capex(0) < be * PRICE['bat_kWh'][2] else 'pin vẫn rẻ hơn'}")
    L.append(f"  Trường hợp xấu nhất cho H2: vốn H2 cao {capex(2):,.0f} so với pin rẻ {be * PRICE['bat_kWh'][0]:,.0f} CNY → "
             f"{'H2 RẺ HƠN' if capex(2) < be * PRICE['bat_kWh'][0] else 'pin rẻ hơn'}")
capex_fc = lambda col: sum(s["fc_kW"] * PRICE["fc_kW"][col] for s in H2ST)
yr = 365.0 / days
sav = lambda r: (s1["cost"] - r["cost"]) * yr                      # tiết kiệm chi phí vận hành mỗi năm so với S1
L += ["",
      "GÓC NHÌN 2 – TRẠM ĐÃ CÓ EL + BỒN (để bán H2 cho FCEV), CHỈ XÉT KHOẢN ĐẦU TƯ THÊM FC để đỡ lưới:",
      f"{'vốn FC thêm, CNY':<28}" + "".join(f"{capex_fc(c):>14,.0f}" for c in range(3))]
if np.isfinite(be):
    L.append(f"{'vốn pin hòa vốn, CNY':<28}" + "".join(f"{be * PRICE['bat_kWh'][c]:>14,.0f}" for c in range(3)))
    L.append("  → FC chỉ cạnh tranh được với pin khi trạm đã có EL + bồn cho việc bán H2; so cùng cột giá.")
L += ["",
      f"TIẾT KIỆM VẬN HÀNH MỖI NĂM so với S1 (quy đổi từ {days} ngày): H2 (S3) {sav(s3):,.0f} CNY/năm"
      + "".join(f" | pin×{m:g} {sav(R[f'pin×{m:g}']):,.0f}" for m in ms),
      f"HOÀN VỐN ĐƠN GIẢN (năm, giá cơ sở): H2 toàn bộ {capex(1) / max(sav(s3), 1e-9):.1f} | chỉ FC {capex_fc(1) / max(sav(s3), 1e-9):.1f}"
      + "".join(f" | pin×{m:g} {(m - 1) * bat0 * PRICE['bat_kWh'][1] / max(sav(R[f'pin×{m:g}']), 1e-9):.1f}" for m in ms),
      "  (hoàn vốn = vốn / tiết kiệm mỗi năm; chưa chiết khấu, chưa tính thay stack – chỉ để so tương đối)"]
L += ["",
      "NGUỒN GIÁ: FC – Sino-Synergy IPO (5.578 CNY/kW 2022; 3.756 CNY/kW 5 tháng đầu 2023), dự báo Frost & Sullivan 2.500 CNY/kW (2025);",
      "  EL – pv magazine 3/2024: hệ kiềm TQ ≈ $303/kW (2021), PEM phương Tây ≈ €1.400/kW; giá PEM TQ cơ sở 6.000 CNY/kW là GIẢ ĐỊNH;",
      "  pin – CNESA qua EnergyTrend 6/2024: hệ lưu trữ 2 giờ TB 0,627 CNY/Wh (thấp nhất 0,54); bồn+máy nén: GIẢ ĐỊNH, xác minh ở việc 4.4.",
      "  H2 mua ngoài: bán lẻ TQ 2024 ≈ 35 CNY/kg (trạm Sany tự sản xuất) đến ≈ 75 CNY/kg (thông thường); Quảng Đông đặt mục tiêu < 30 CNY/kg năm 2025.",
      "LƯU Ý: so vốn ban đầu, chưa tính tuổi thọ khác nhau (stack FC thay sau ~5 năm, pin LFP ~10 năm) – nếu tính hằng năm, H2 còn bất lợi hơn."]
txt = "\n".join(L)
(OUT / "summary.txt").write_text(txt, encoding="utf-8")

fig, ax = plt.subplots(1, 2, figsize=(12, 4.2))
ax[0].plot(xs, ys, "o-", c="tab:gray", label="chỉ thêm pin (không H2)")
ax[0].axhline(target, c="tab:blue", ls="--", label=f"H2 – đề xuất S3 ({target:.1f}%)")
if np.isfinite(be):
    ax[0].axvline(be, c="tab:blue", ls=":", lw=1); ax[0].annotate(f"pin hòa vốn ≈ {be:,.0f} kWh", (be, target), textcoords="offset points", xytext=(8, -14), fontsize=8)
for c, col, lab in ((0, "tab:green", "thấp"), (1, "k", "cơ sở"), (2, "tab:red", "cao")):
    ax[0].axvline(capex(c) / PRICE["bat_kWh"][c], c=col, alpha=.4, lw=3, label=f"pin cùng vốn H2 (giá {lab})")
ax[0].set_xlabel("pin THÊM ở 3 trạm H2 (kWh)"); ax[0].set_ylabel("vượt MBA giảm so với S1 (%)"); ax[0].grid(alpha=.3); ax[0].legend(fontsize=7)
ax[0].set_title("(a) Cần bao nhiêu pin để bằng H2?")
ax[1].plot(xs, [s1["cost"] / 1e3] + [c / 1e3 for c in cost_b], "o-", c="tab:gray", label="chỉ thêm pin")
ax[1].axhline(s3["cost"] / 1e3, c="tab:blue", ls="--", label="H2 – đề xuất S3")
ax[1].set_xlabel("pin THÊM ở 3 trạm H2 (kWh)"); ax[1].set_ylabel("chi phí vận hành (nghìn CNY)"); ax[1].grid(alpha=.3); ax[1].legend(fontsize=7)
ax[1].set_title("(b) Chi phí vận hành (chưa gồm vốn)")
fig.suptitle(f"Việc 2.6 – H2 so với pin lớn hơn ({days} ngày từ {start})"); fig.tight_layout()
fig.savefig(OUT / "fig_battery_compare.png", dpi=150); plt.close(fig)
print("\n" + txt + f"\n\nĐã ghi: {OUT / 'summary.txt'}\n        {OUT / 'fig_battery_compare.png'}")
