"""
VIỆC 4.4 – ĐỘ NHẠY THEO CÁC THÔNG SỐ CÒN LÀ GIẢ ĐỊNH (30 ngày từ 2022-11-01, mỗi lần đổi MỘT thông số).
Khoảng đổi lấy theo nguồn (ghi trong bài):
  điện máy nén   2,0 / [2,5] / 3,2 kWh/kg  – DOE Hydrogen Program Record #9013 (2009): thực tế 2–3 kWh/kg (350 bar), 2,7–3,2 (700 bar)
  giá stack FC   × 0,6 / [1] / × 1,3       – hệ FC Trung Quốc ≈ 3.000 CNY/kW (CAST, 6/2026), stack chiếm khoảng 40–60%
  giá stack EL   × 0,3 / [1]               – EL kiềm Trung Quốc 500–1.100 USD/kW cả hệ, stack 15–20% (IEA, 10/2026)
  giới hạn chia sẻ 150 / [300] / 600 kW     – giả định đường dây giữa hai trạm
  hao mòn pin    0,02 / [0,05] / 0,10 CNY/kWh – giả định
Mỗi điểm chạy S3; với chia sẻ và hao mòn pin chạy thêm S1 (vì S1 cũng đổi theo).
Đặt cùng step3_simulate.py BẢN MỚI (có --e_cp) trong DATN2026 rồi chạy:
    python run_sens44.py            # ~30–45 phút, chạy 2 cùng lúc
    python run_sens44.py --reuse
Ghi: results/sens44_summary.txt   ← GỬI FILE NÀY CHO CLAUDE
"""
import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
HERE = Path(__file__).resolve().parent
PROJECT_DIR = Path(__file__).resolve().parent
if not PROJECT_DIR.exists():
    PROJECT_DIR = HERE
RES = PROJECT_DIR / "results"
PY = sys.executable
if '"--e_cp"' not in (PROJECT_DIR / "step3_simulate.py").read_text(encoding="utf-8", errors="ignore"):
    raise SystemExit("Cần step3_simulate.py BẢN MỚI (có --e_cp) trong DATN2026.")
ap = argparse.ArgumentParser()
ap.add_argument("--wz", default="1e10", help="w_Z của S3 (cấu hình chính đã chốt: 1e10)")
ap.add_argument("--jobs", type=int, default=2)
ap.add_argument("--reuse", action="store_true")
ap.add_argument("--days", default="30")
args = ap.parse_args()
WZ = args.wz; SFX = "" if WZ == "3e8" else f"_wz{WZ}"
env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
LOG = RES / "sens44_logs"; LOG.mkdir(parents=True, exist_ok=True)
B = f"batch_2022-11-01_{args.days}d"
S3 = ["--wz", WZ, "--V", "1"]; S1 = ["--no_h2", "--wz", "1e10"]
base = ["--days", args.days, "--start", "2022-11-01"]
GRID = [  # (nhóm, nhãn giá trị, tùy chọn, chạy cả S1?)
    ("điện máy nén kWh/kg", "2,0", ["--e_cp", "2.0"], False), ("điện máy nén kWh/kg", "3,2", ["--e_cp", "3.2"], False),
    ("giá stack FC", "× 0,6", ["--fc_stack_mult", "0.6"], False), ("giá stack FC", "× 1,3", ["--fc_stack_mult", "1.3"], False),
    ("giá stack EL", "× 0,3", ["--el_stack_mult", "0.3"], False),
    ("giới hạn chia sẻ kW", "150", ["--p_share", "150"], True), ("giới hạn chia sẻ kW", "600", ["--p_share", "600"], True),
    ("hao mòn pin CNY/kWh", "0,02", ["--c_bat", "0.02"], True), ("hao mòn pin CNY/kWh", "0,10", ["--c_bat", "0.10"], True),
    # giả định lưới/nguồn (phản biện hay hỏi): MBA to/nhỏ hơn, PV ít/nhiều hơn – S1 phải chạy lại cùng giả định
    ("MBA (× đỉnh tải)", "0,5", ["--tr_frac", "0.5"], True), ("MBA (× đỉnh tải)", "0,7", ["--tr_frac", "0.7"], True),
    ("MBA (× đỉnh tải)", "0,8", ["--tr_frac", "0.8"], True),
    ("quy mô PV", "× 1", ["--pv_scale", "1"], True), ("quy mô PV", "× 3", ["--pv_scale", "3"], True),
]
tagof = lambda opt, kind: f"{B}_sens44_{'_'.join(x.strip('-') for x in opt)}_{kind}" + (SFX if kind == "S3" else "")
jobs = [(f"{B}_S3_wZ{WZ}", base + S3), (f"{B}_S1", base + S1)]
for g, v, opt, both in GRID:
    jobs.append((tagof(opt, "S3"), base + S3 + opt))
    if both:
        jobs.append((tagof(opt, "S1"), base + S1 + opt))
summ = lambda t: RES / f"step3_{t}" / "summary.txt"
# chỉ dùng lại kết quả đã có dòng chi phí HIỆU CHỈNH cuối kỳ (để mọi so sánh cùng một cách tính)
has_corr = lambda t: summ(t).exists() and "K2 hiệu chỉnh cuối kỳ" in summ(t).read_text(encoding="utf-8")
pending = [j for j in jobs if not (has_corr(j[0]) and (args.reuse or "_sens44_" not in j[0]))]
t_all = time.time()
print(f"{len(pending)} lần mô phỏng, chạy {args.jobs} cùng lúc", flush=True)
running = {}
while pending or running:
    while pending and len(running) < args.jobs:
        tag, opt = pending.pop(0)
        lf = open(LOG / f"{tag}.log", "w", encoding="utf-8")
        running[tag] = (subprocess.Popen([PY, str(PROJECT_DIR / "step3_simulate.py"), "--tag", tag] + opt,
                                         stdout=lf, stderr=subprocess.STDOUT, env=env), time.time(), lf)
        print(f"  bắt đầu {tag}", flush=True)
    time.sleep(10)
    for tag in list(running):
        pr, t0, lf = running[tag]
        if pr.poll() is None:
            continue
        lf.close(); del running[tag]
        print(f"  {'xong' if pr.returncode == 0 and summ(tag).exists() else 'LỖI (xem sens44_logs)'} {tag} sau {(time.time() - t0) / 60:.0f} phút", flush=True)


def P(tag):
    f = summ(tag)
    if not f.exists():
        return None
    s = f.read_text(encoding="utf-8")
    g = lambda pat: (float(re.search(pat, s).group(1).replace(",", "")) if re.search(pat, s) else float("nan"))
    lf = [float(x) for x in re.findall(r"tuổi thọ dự kiến theo tốc độ kỳ này: FC ([\d.]+|inf) năm", s)]
    return dict(cost=(lambda c, r: c if c == c else r)(g(r"K2 hiệu chỉnh cuối kỳ: ([\d,]+) CNY"), g(r"K2 – chi phí \(gồm giá lão hóa\): ([\d,]+) CNY")), ov=g(r"vượt giới hạn MBA ([\d.]+) MWh"),
                life=min(lf) if lf else float("nan"), ok="KHÔNG ĐẠT" not in s)


b3, b1 = P(f"{B}_S3_wZ{WZ}"), P(f"{B}_S1")
L = [f"VIỆC 4.4 – ĐỘ NHẠY THÔNG SỐ GIẢ ĐỊNH – S3 w_Z = {WZ} – {args.days} ngày từ 2022-11-01 – xong sau {(time.time() - t_all) / 60:.0f} phút", "",
     f"{'thông số':24}{'giá trị':>9}{'chi phí S3':>13}{'so S3 gốc':>11}{'S3 so S1':>10}{'vượt MBA so S1':>16}{'FC ≥ năm':>10}  lý thuyết"]
if b3 and b1:
    L.append(f"{'(cấu hình gốc)':24}{'':>9}{b3['cost']:>13,.0f}{0:>10.2f}%{100 * (b3['cost'] / b1['cost'] - 1):>9.1f}%"
             f"{100 * (b3['ov'] / b1['ov'] - 1):>15.1f}%{b3['life']:>10.1f}  {'ĐẠT hết' if b3['ok'] else 'CÓ MỤC KHÔNG ĐẠT'}")
for g, v, opt, both in GRID:
    a = P(tagof(opt, "S3")); s1 = P(tagof(opt, "S1")) if both else b1
    if not a or not s1 or not b3:
        L.append(f"{g:24}{v:>9}  (chưa có)"); continue
    L.append(f"{g:24}{v:>9}{a['cost']:>13,.0f}{100 * (a['cost'] / b3['cost'] - 1):>10.2f}%{100 * (a['cost'] / s1['cost'] - 1):>9.1f}%"
             f"{100 * (a['ov'] / s1['ov'] - 1):>15.1f}%{a['life']:>10.1f}  {'ĐẠT hết' if a['ok'] else 'CÓ MỤC KHÔNG ĐẠT'}")
L += ["", "Đọc: kết luận vững nếu cột 'S3 so S1' và 'vượt MBA so S1' giữ dấu âm và FC ≥ 5 năm ở mọi dòng.",
      "Nguồn khoảng đổi: DOE Hydrogen Program Record #9013; CAST (SMM 11/6/2026); IEA commentary 15/10/2026 (xem đầu file run_sens44.py)."]
(RES / f"sens44_summary{SFX}.txt").write_text("\n".join(L), encoding="utf-8")
print("\n".join(L))
print(f"\nXONG. Gửi Claude: {RES / f'sens44_summary{SFX}.txt'}")
