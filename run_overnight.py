"""
CHẠY QUA ĐÊM (một lệnh): việc 3.3b (điều khiển có tính lưới) + việc 2.7 (bán H2 cho FCEV – quét bước đầu).
Đặt trong DATN2026 rồi chạy:
    python run_overnight.py                 # ~1,5–2,5 giờ trên laptop 4 nhân; tắt chế độ ngủ của máy
    python run_overnight.py --reuse         # lỡ tắt máy: chạy lại, phần nào xong rồi thì bỏ qua

Gồm:
  [A] 6 tháng, CÓ tính lưới 33 nút: S1 (không H2) và S3 (đề xuất)      → so với bản cũ (chưa tính lưới) trên trào lưu AC
  [B] 30 ngày, S3 có tính lưới với 3 mức phạt điện áp c_v = 3e4, 1e5, 3e5 + S1 có tính lưới → đường đánh đổi chi phí – điện áp
  [C] 30 ngày, so H2 với pin khi CÓ bán H2: (nhu cầu 1,0; H2 ngoài 40), (1,0; 60), (0,5; 60) CNY/kg
Cuối cùng: đánh giá AC trên lưới cho [A] (cùng 8 phương pháp cũ) và [B]; gom tóm tắt vào một file.
Ghi: results/overnight_summary.txt   ← SÁNG MAI GỬI FILE NÀY (và các hình trong results/grid33_*) CHO CLAUDE
"""
import argparse
import os
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
for f, key in (("step3_simulate.py", '"--grid33"'), ("grid33_eval.py", '"--add"'), ("run_battery_compare.py", '"--h2_demand_frac"')):
    if key not in (PROJECT_DIR / f).read_text(encoding="utf-8", errors="ignore"):
        raise SystemExit(f"Cần {f} BẢN MỚI trong DATN2026.")
try:
    import pandapower  # noqa
except ImportError:
    raise SystemExit("Cần: python -m pip install pandapower")

ap = argparse.ArgumentParser()
ap.add_argument("--wz", default="1e10", help="w_Z của S3 (cấu hình chính đã chốt: 1e10)")
ap.add_argument("--jobs", type=int, default=3)
ap.add_argument("--reuse", action="store_true")
ap.add_argument("--quick", action="store_true", help=argparse.SUPPRESS)   # chỉ để thử code: 2 ngày
args = ap.parse_args()
WZ = args.wz; SFX = "" if WZ == "3e8" else f"_wz{WZ}"      # tên kết quả cũ (3e8) giữ nguyên, bản mới thêm hậu tố
env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
LOG = RES / "overnight_logs"; LOG.mkdir(parents=True, exist_ok=True)
B6, B30 = "batch_2022-09-01_181d", "batch_2022-11-01_30d"
S3 = ["--wz", WZ, "--V", "1"]
S1 = ["--no_h2", "--wz", "1e10"]
sim = []   # (tag, args)
sim += [(f"{B6}_grid_S1", ["--days", "0"] + S1 + ["--grid33"]),
        (f"{B6}_grid_S3_wZ{WZ}", ["--days", "0"] + S3 + ["--grid33"])]
for cv in ("3e4", "1e5", "3e5"):
    sim.append((f"{B30}_grid_cv{cv}_S3{SFX}", ["--days", "30", "--start", "2022-11-01"] + S3 + ["--grid33", "--c_v", cv]))
sim.append((f"{B30}_grid_cv1e5_S1", ["--days", "30", "--start", "2022-11-01"] + S1 + ["--grid33", "--c_v", "1e5"]))
for tag, _ in [(f"{B30}_S1", 0), (f"{B30}_S3_wZ{WZ}", 0)]:          # bản chưa tính lưới 30 ngày để so (nếu chưa có)
    sim.append((tag, ["--days", "30", "--start", "2022-11-01"] + (S1 if tag.endswith("S1") else S3)))
if args.quick:
    sim = [(t.replace(B6, "q6").replace(B30, "q30"), [("2" if (x in ("0", "30") and k > 0 and o[k - 1] == "--days") else x) for k, x in enumerate(o)]) for t, o in sim]
    B6, B30 = "q6", "q30"
summ = lambda tag: RES / f"step3_{tag}" / "summary.txt"
pending = [j for j in sim if not (args.reuse and summ(j[0]).exists())]
pending = [j for j in pending if not (j[0] in (f"{B30}_S1", f"{B30}_S3_wZ{WZ}") and summ(j[0]).exists())]   # bản cũ đã có thì dùng lại
t_all = time.time()
print(f"[A+B] {len(pending)} lần mô phỏng, chạy {args.jobs} cùng lúc", flush=True)
running = {}
while pending or running:
    while pending and len(running) < args.jobs:
        tag, opt = pending.pop(0)
        lf = open(LOG / f"{tag}.log", "w", encoding="utf-8")
        running[tag] = (subprocess.Popen([PY, str(PROJECT_DIR / "step3_simulate.py"), "--tag", tag] + opt, stdout=lf, stderr=subprocess.STDOUT, env=env), time.time(), lf)
        print(f"  bắt đầu {tag}", flush=True)
    time.sleep(10)
    for tag in list(running):
        pr, t0, lf = running[tag]
        if pr.poll() is None:
            continue
        lf.close(); del running[tag]
        print(f"  {'xong' if pr.returncode == 0 and summ(tag).exists() else 'LỖI (xem overnight_logs)'} {tag} sau {(time.time() - t0) / 60:.0f} phút "
              f"(tổng {(time.time() - t_all) / 60:.0f} phút)", flush=True)


def run(cmd, logname):
    print(f"\n=== {' '.join(cmd[1:])}", flush=True)
    with open(LOG / logname, "w", encoding="utf-8") as lf:
        r = subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT, env=env)
    print(f"    {'xong' if r.returncode == 0 else 'LỖI – xem ' + str(LOG / logname)}", flush=True)


# [C] H2 so với pin khi có bán H2 (30 ngày; dùng lại S1/pin nếu đã có)
for f, c in (("1.0", "40"), ("1.0", "60"), ("0.5", "60")):
    run([PY, str(PROJECT_DIR / "run_battery_compare.py"), "--days", "2" if args.quick else "30", "--start", "2022-11-01", "--jobs", str(args.jobs),
         "--h2_demand_frac", f, "--c_ext", c, "--wz", WZ], f"battery_dem{f}_c{c}.log")
# đánh giá AC trên lưới
run([PY, str(PROJECT_DIR / "grid33_eval.py"), "--batch", B6, "--add", f"S1_grid={B6}_grid_S1,S3_grid={B6}_grid_S3_wZ{WZ}", "--name", "6thang" + SFX], "grid_6m.log")
run([PY, str(PROJECT_DIR / "grid33_eval.py"), "--dirs",
     f"S1={B30}_S1,S3={B30}_S3_wZ{WZ},S1_grid={B30}_grid_cv1e5_S1,S3_grid_cv3e4={B30}_grid_cv3e4_S3{SFX},"
     f"S3_grid={B30}_grid_cv1e5_S3{SFX},S3_grid_cv3e5={B30}_grid_cv3e5_S3{SFX}", "--name", "30ngay_cv" + SFX], "grid_30d.log")

# gom tóm tắt
L = [f"TÓM TẮT CHẠY QUA ĐÊM – xong sau {(time.time() - t_all) / 60:.0f} phút", ""]
for d in ["grid33_6thang" + SFX, "grid33_30ngay_cv" + SFX]:
    f = RES / d / "summary.txt"
    L += [f"######## {d}", f.read_text(encoding="utf-8") if f.exists() else "(không có – xem overnight_logs)", ""]
for tag in [f"{B6}_grid_S1", f"{B6}_grid_S3_wZ{WZ}"] + [f"{B30}_grid_cv{c}_S3{SFX}" for c in ("3e4", "1e5", "3e5")]:
    f = summ(tag)
    if f.exists():
        s = f.read_text(encoding="utf-8").splitlines()
        L.append(f"######## {tag}")
        L += [x for x in s if any(k in x for k in ("KHÔNG ĐẠT", "K2 –", "K6 –", "K11", "K7 –"))] or ["(không có dòng chỉ số)"]
        L.append(f"  lý thuyết: {'ĐẠT hết' if 'KHÔNG ĐẠT' not in f.read_text(encoding='utf-8') else 'CÓ MỤC KHÔNG ĐẠT'}")
        L.append("")
for f, c in (("1.0", "40"), ("1.0", "60"), ("0.5", "60")):
    p = RES / f"battery_compare_2022-11-01_{'2' if args.quick else '30'}d_dem{f}_c{c}{SFX}" / "summary.txt"
    L += [f"######## H2 so với pin – nhu cầu {f}, H2 ngoài {c} CNY/kg", p.read_text(encoding="utf-8") if p.exists() else "(không có)", ""]
(RES / f"overnight_summary{SFX}.txt").write_text("\n".join(L), encoding="utf-8")
print(f"\nXONG. Gửi Claude: {RES / f'overnight_summary{SFX}.txt'}")
