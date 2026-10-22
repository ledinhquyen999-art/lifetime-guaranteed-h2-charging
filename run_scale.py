"""
VIỆC 4.3 – MỞ RỘNG 20 / 35 / 50 ĐIỂM SẠC (dữ liệu vùng TAZ 5 phút của UrbanEV, xem build_scale_inputs.py).
Kiểm: thời gian giải mỗi bước tăng thế nào theo N; các bảo đảm (bồn, pin, tuổi thọ) có còn đúng; H2 còn giảm quá tải/chi phí không;
ADMM ở mạng lớn (mỗi điểm chỉ chia sẻ với 3 điểm gần nhất).
Đặt build_scale_inputs.py, run_scale.py, step3_simulate.py BẢN MỚI (có --inputs, --share_k) trong DATN2026 rồi chạy:
    python build_scale_inputs.py      # một lần, vài giây – tạo data_clean/scale{N}_inputs.csv, params/params_scale{N}.json
    python run_scale.py               # ~1–1,5 giờ, chạy 2 cùng lúc
    python run_scale.py --reuse       # phần nào xong rồi thì bỏ qua
Ghi: results/scale_summary.txt   ← GỬI FILE NÀY CHO CLAUDE
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
if '"--share_k"' not in (PROJECT_DIR / "step3_simulate.py").read_text(encoding="utf-8", errors="ignore"):
    raise SystemExit("Cần step3_simulate.py BẢN MỚI (có --share_k) trong DATN2026.")

ap = argparse.ArgumentParser()
ap.add_argument("--wz", default="1e10", help="w_Z của S3 (cấu hình chính đã chốt: 1e10)")
ap.add_argument("--jobs", type=int, default=2)
ap.add_argument("--reuse", action="store_true")
ap.add_argument("--sizes", default="20,35,50")
ap.add_argument("--days", default="30")
ap.add_argument("--admm_days", default="2")
args = ap.parse_args()
WZ = args.wz; SFX = "" if WZ == "3e8" else f"_wz{WZ}"      # tên kết quả cũ (3e8) giữ nguyên, bản mới thêm hậu tố
sizes = [int(x) for x in args.sizes.split(",")]
for N in sizes:
    if not (PROJECT_DIR / "data_clean" / f"scale{N}_inputs.csv").exists():
        raise SystemExit(f"Thiếu data_clean/scale{N}_inputs.csv – chạy build_scale_inputs.py trước.")
env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
LOG = RES / "scale_logs"; LOG.mkdir(parents=True, exist_ok=True)
base = ["--start", "2022-11-01"]
jobs = []
for N in sizes:
    net = ["--inputs", f"scale{N}_inputs.csv", "--params", f"params_scale{N}.json", "--share_k", "3"]
    jobs.append((f"scale{N}_{args.days}d_S3{SFX}", ["--days", args.days] + base + ["--wz", WZ, "--V", "1"] + net))
    jobs.append((f"scale{N}_{args.days}d_S1", ["--days", args.days] + base + ["--no_h2", "--wz", "1e10"] + net))
    jobs.append((f"scale{N}_{args.admm_days}d_S3{SFX}", ["--days", args.admm_days] + base + ["--wz", WZ, "--V", "1"] + net))
    jobs.append((f"scale{N}_{args.admm_days}d_admm30{SFX}", ["--days", args.admm_days] + base + ["--wz", WZ, "--V", "1", "--admm", "30"] + net))
summ = lambda tag: RES / f"step3_{tag}" / "summary.txt"
# chỉ dùng lại kết quả đã có dòng chi phí HIỆU CHỈNH cuối kỳ (để mọi so sánh cùng một cách tính)
has_corr = lambda t: summ(t).exists() and "K2 hiệu chỉnh cuối kỳ" in summ(t).read_text(encoding="utf-8")
pending = [j for j in jobs if not (args.reuse and has_corr(j[0]))]
pending.sort(key=lambda j: -int(j[0].split("scale")[1].split("_")[0]) - (100 if "admm" in j[0] else 0))   # lâu trước
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
        print(f"  {'xong' if pr.returncode == 0 and summ(tag).exists() else 'LỖI (xem scale_logs)'} {tag} sau {(time.time() - t0) / 60:.0f} phút "
              f"(tổng {(time.time() - t_all) / 60:.0f} phút)", flush=True)


def P(tag):
    f = summ(tag)
    if not f.exists():
        return None
    s = f.read_text(encoding="utf-8")
    g = lambda pat, d=float("nan"): (float(re.search(pat, s).group(1).replace(",", "")) if re.search(pat, s) else d)
    lf = [float(x) for x in re.findall(r"tuổi thọ dự kiến theo tốc độ kỳ này: FC ([\d.]+|inf) năm", s)]
    return dict(cost=(lambda c, r: c if c == c else r)(g(r"K2 hiệu chỉnh cuối kỳ: ([\d,]+) CNY"), g(r"K2 – chi phí \(gồm giá lão hóa\): ([\d,]+) CNY")), ov=g(r"vượt giới hạn MBA ([\d.]+) MWh"),
                t=g(r"Thời gian giải: TB ([\d.]+) s/bước"), tmax=g(r"Thời gian giải: TB [\d.]+ s/bước, max ([\d.]+) s"),
                life=min(lf) if lf else float("nan"), ok="KHÔNG ĐẠT" not in s,
                conv=g(r"hội tụ \(lệch chia sẻ ≤ [\d.]+ kW\) ở ([\d.]+)%"), its=g(r"số vòng TB ([\d.]+)"),
                tadmm=g(r"song song thì ≈ ([\d.]+) s/bước"), epr=g(r"so với \|J\*\| TB [\d.e+]+: ([-\d.]+)%"), txt=s)


L = [f"VIỆC 4.3 – MỞ RỘNG MẠNG – {args.days} ngày từ 2022-11-01 (ADMM: {args.admm_days} ngày) – xong sau {(time.time() - t_all) / 60:.0f} phút", "",
     f"{'N':>4}{'giải s/bước TB':>16}{'max':>7}{'chi phí S3':>13}{'so S1':>8}{'vượt MBA S3':>13}{'so S1':>8}{'FC ≥ năm':>10}  lý thuyết S3"]
for N in sizes:
    a, b = P(f"scale{N}_{args.days}d_S3{SFX}"), P(f"scale{N}_{args.days}d_S1")
    if not a or not b:
        L.append(f"{N:>4}  (chưa đủ kết quả)"); continue
    L.append(f"{N:>4}{a['t']:>16.3f}{a['tmax']:>7.2f}{a['cost']:>13,.0f}{100 * (a['cost'] / b['cost'] - 1):>7.1f}%{a['ov']:>13.1f}"
             f"{100 * (a['ov'] / b['ov'] - 1) if b['ov'] > 0 else float('nan'):>7.1f}%{a['life']:>10.1f}  {'ĐẠT hết' if a['ok'] else 'CÓ MỤC KHÔNG ĐẠT'}")
L += ["", f"ADMM ({args.admm_days} ngày, tối đa 30 vòng, ρ = 1e-3, mỗi điểm chia sẻ với 3 điểm gần nhất):",
      f"{'N':>4}{'chi phí so tập trung':>22}{'hội tụ %':>10}{'vòng TB':>9}{'ε/|J*| %':>10}{'s/bước song song':>18}  lý thuyết"]
for N in sizes:
    c, a = P(f"scale{N}_{args.admm_days}d_S3{SFX}"), P(f"scale{N}_{args.admm_days}d_admm30{SFX}")
    if not c or not a:
        L.append(f"{N:>4}  (chưa đủ kết quả)"); continue
    L.append(f"{N:>4}{100 * (a['cost'] / c['cost'] - 1):>21.2f}%{a['conv']:>10.1f}{a['its']:>9.1f}{a['epr']:>10.3f}{a['tadmm']:>18.2f}  "
             f"{'ĐẠT hết' if a['ok'] else 'CÓ MỤC KHÔNG ĐẠT'}")
L += ["", "So với 7 trạm thật (đã có): giải tập trung ~0,02 s/bước; S3 so S1 30 ngày: chi phí −5,0%, vượt MBA −20,8%.",
      "Lưu ý: mỗi điểm sạc của mạng lớn là một VÙNG giao thông (gộp nhiều trạm) – dữ liệu 5 phút đã làm sạch của UrbanEV (Dryad, zone-cleaned-aggregated);",
      "dùng để kiểm khả năng mở rộng, không thay kết quả chính trên 7 trạm thật.", ""]
for N in sizes:
    a = P(f"scale{N}_{args.days}d_S3{SFX}")
    if a:
        L.append(f"######## N = {N}, S3")
        L += [x for x in a["txt"].splitlines() if any(k in x for k in ("MẠNG KHÁC", "KHÔNG ĐẠT", "K2 –", "K6 –", "Thời gian giải", "Bổ đề 1"))]
        L.append("")
(RES / f"scale_summary{SFX}.txt").write_text("\n".join(L), encoding="utf-8")
print("\n".join(L[:20]))
print(f"\nXONG. Gửi Claude: {RES / f'scale_summary{SFX}.txt'}")
