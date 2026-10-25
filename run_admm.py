"""
VIỆC 3.1–3.2 – ADMM PHÂN TÁN: mỗi trạm tự giải bài của mình, chỉ trao đổi điện chia sẻ với điều phối viên.
Đo: số vòng, tỉ lệ hội tụ, sai số tối ưu ε_t = J(ũ) − min P3 (đưa vào Định lý 1), chi phí so với giải tập trung,
và kiểm tra các bảo đảm lý thuyết (Mệnh đề 1, 2) vẫn đúng với lời giải gần đúng.
Đặt trong DATN2026 (cùng step3_simulate.py BẢN MỚI có --admm) rồi chạy (SAU khi run_mismatch.py xong):
    python run_admm.py             # 7 ngày: 3 mức số vòng k_s × ρ = 1e-3, thêm 2 mức ρ; ~1–1,5 giờ, chạy 2 cùng lúc
    python run_admm.py --reuse     # lỡ tắt máy: phần nào xong rồi thì bỏ qua
Ghi: results/admm_summary.txt
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
if '"--admm"' not in (PROJECT_DIR / "step3_simulate.py").read_text(encoding="utf-8", errors="ignore"):
    raise SystemExit("Cần step3_simulate.py BẢN MỚI (có --admm) trong DATN2026.")

ap = argparse.ArgumentParser()
ap.add_argument("--wz", default="1e10", help="w_Z của S3 (cấu hình chính đã chốt: 1e10)")
ap.add_argument("--jobs", type=int, default=2)
ap.add_argument("--reuse", action="store_true")
ap.add_argument("--days", default="7", help=argparse.SUPPRESS)
args = ap.parse_args()
WZ = args.wz; SFX = "" if WZ == "3e8" else f"_wz{WZ}"      # tên kết quả cũ (3e8) giữ nguyên, bản mới thêm hậu tố
env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
LOG = RES / "admm_logs"; LOG.mkdir(parents=True, exist_ok=True)
B = f"batch_2022-11-01_{args.days}d"
base = ["--days", args.days, "--start", "2022-11-01", "--wz", WZ, "--V", "1"]
SC = [  # (nhãn, tag, tùy chọn)
    ("Tập trung", f"{B}_S3_wZ{WZ}", []),
    ("k=3, ρ=1e-3", f"{B}_admm_k3_r1e-3{SFX}", ["--admm", "3", "--admm_rho", "1e-3"]),
    ("k=10, ρ=1e-3", f"{B}_admm_k10_r1e-3{SFX}", ["--admm", "10", "--admm_rho", "1e-3"]),
    ("k=30, ρ=1e-3", f"{B}_admm_k30_r1e-3{SFX}", ["--admm", "30", "--admm_rho", "1e-3"]),
    ("k=30, ρ=3e-4", f"{B}_admm_k30_r3e-4{SFX}", ["--admm", "30", "--admm_rho", "3e-4"]),
    ("k=30, ρ=3e-3", f"{B}_admm_k30_r3e-3{SFX}", ["--admm", "30", "--admm_rho", "3e-3"]),
]
summ = lambda tag: RES / f"step3_{tag}" / "summary.txt"
jobs = [(t, base + o) for _, t, o in SC]
pending = [j for j in jobs if not (summ(j[0]).exists() and (args.reuse or "_admm_" not in j[0]))]
pending.sort(key=lambda j: -int(j[1][j[1].index("--admm") + 1]) if "--admm" in j[1] else 0)   # chạy bản lâu trước
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
    time.sleep(5)
    for tag in list(running):
        pr, t0, lf = running[tag]
        if pr.poll() is None:
            continue
        lf.close(); del running[tag]
        print(f"  {'xong' if pr.returncode == 0 and summ(tag).exists() else 'LỖI (xem admm_logs)'} {tag} sau {(time.time() - t0) / 60:.0f} phút "
              f"(tổng {(time.time() - t_all) / 60:.0f} phút)", flush=True)


def num(pat, s, default=float("nan")):
    m = re.search(pat, s)
    return float(m.group(1).replace(",", "")) if m else default


L = [f"VIỆC 3.1–3.2 – ADMM – {args.days} ngày từ 2022-11-01 (S3, w_Z = {WZ}, V = 1) – xong sau {(time.time() - t_all) / 60:.0f} phút", "",
     f"{'':14}{'chi phí CNY':>12}{'so tập trung':>13}{'hội tụ %':>9}{'vòng TB':>8}{'ε TB':>8}{'ε/|J*| %':>9}{'s/bước':>8}{'FC ≥ năm':>9}  lý thuyết"]
ref = None
for lab, tag, _ in SC:
    f = summ(tag)
    if not f.exists():
        L.append(f"{lab:14}(chưa có – xem admm_logs)"); continue
    s = f.read_text(encoding="utf-8")
    c = num(r"K2 – chi phí \(gồm giá lão hóa\): ([\d,]+) CNY", s)
    ref = c if ref is None else ref
    conv = num(r"hội tụ \(lệch chia sẻ ≤ [\d.]+ kW\) ở ([\d.]+)%", s)
    its = num(r"số vòng TB ([\d.]+)", s)
    eps = num(r"ε_t = J\(ũ\) − min P3: TB ([-\d.e]+)", s)
    epr = num(r"so với \|J\*\| TB [\d.e+]+: ([-\d.]+)%", s)
    tps = num(r"thời gian ADMM TB ([\d.]+) s/bước", s, num(r"Thời gian giải: TB ([\d.]+) s/bước", s))
    lf = re.findall(r"tuổi thọ dự kiến theo tốc độ kỳ này: FC ([\d.]+) năm", s)
    life = min(float(x) for x in lf) if lf else float("nan")
    L.append(f"{lab:14}{c:>12,.0f}{100 * (c / ref - 1):>12.2f}%{conv:>9.1f}{its:>8.1f}{eps:>8.3f}{epr:>9.3f}{tps:>8.2f}{life:>9.1f}  "
             f"{'ĐẠT hết' if 'KHÔNG ĐẠT' not in s else 'CÓ MỤC KHÔNG ĐẠT'}")
L += ["", "Cột: hội tụ % = số bước ADMM đạt lệch chia sẻ ≤ 2 kW trước khi hết vòng; ε = J(ũ) − min P3 đo mỗi bước (đơn vị của J);",
      "s/bước = thời gian ADMM khi 7 trạm giải chung trên laptop (song song thật thì chia khoảng 7).", ""]
for lab, tag, _ in SC[1:]:
    f = summ(tag)
    if f.exists():
        s = f.read_text(encoding="utf-8").splitlines()
        L.append(f"######## {lab} ({tag})")
        L += [x for x in s if any(k in x for k in ("K8 –", "ε_t", "KHÔNG ĐẠT", "Bổ đề 1", "K6 –"))]
        L.append("")
(RES / f"admm_summary{SFX}.txt").write_text("\n".join(L), encoding="utf-8")
print("\n".join(L[:12]))
print(f"\nXONG. Kết quả: {RES / f'admm_summary{SFX}.txt'}")
