"""
VIỆC 3.5 – VOLT–VAR: bộ biến đổi của pin và FC phát công suất phản kháng Q để đỡ điện áp lưới 33 nút.
Đặt trong DATN2026 (cùng step3_simulate.py và grid33_eval.py BẢN MỚI) rồi chạy:
    python run_voltvar.py              # 6 tháng, S1 và S3 có volt–var, chạy song song 2 cái; ~ vài giờ, tắt chế độ ngủ
    python run_voltvar.py --reuse      # lỡ tắt máy: phần nào xong rồi thì bỏ qua
Cần sẵn (đã có từ lần chạy qua đêm): results/step3_batch_2022-09-01_181d_grid_S1 và ..._grid_S3_wZ{WZ}
Ghi: results/voltvar_summary.txt   ← GỬI FILE NÀY CHO CLAUDE
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
for f, key in (("step3_simulate.py", '"--volt_var"'), ("grid33_eval.py", 'q_')):
    if key not in (PROJECT_DIR / f).read_text(encoding="utf-8", errors="ignore"):
        raise SystemExit(f"Cần {f} BẢN MỚI (có volt–var) trong DATN2026.")

ap = argparse.ArgumentParser()
ap.add_argument("--wz", default="1e10", help="w_Z của S3 (cấu hình chính đã chốt: 1e10)")
ap.add_argument("--jobs", type=int, default=2)
ap.add_argument("--reuse", action="store_true")
ap.add_argument("--days", default="0", help="0 = cả 6 tháng")
args = ap.parse_args()
WZ = args.wz; SFX = "" if WZ == "3e8" else f"_wz{WZ}"      # tên kết quả cũ (3e8) giữ nguyên, bản mới thêm hậu tố
env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
LOG = RES / "voltvar_logs"; LOG.mkdir(parents=True, exist_ok=True)
B = "batch_2022-09-01_181d" if args.days == "0" else f"vvtest_{args.days}d"
base = ["--days", args.days] + ([] if args.days == "0" else ["--start", "2022-11-01"])
sim = [(f"{B}_vv_S1", base + ["--no_h2", "--wz", "1e10", "--volt_var"]),
       (f"{B}_vv_S3_wZ{WZ}", base + ["--wz", WZ, "--V", "1", "--volt_var"])]
if args.days != "0":   # bản thử ngắn: chạy luôn bản lưới không volt–var để so
    sim += [(f"{B}_grid_S1", base + ["--no_h2", "--wz", "1e10", "--grid33"]),
            (f"{B}_grid_S3_wZ{WZ}", base + ["--wz", WZ, "--V", "1", "--grid33"])]
summ = lambda tag: RES / f"step3_{tag}" / "summary.txt"
pending = [j for j in sim if not (args.reuse and summ(j[0]).exists())]
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
        print(f"  {'xong' if pr.returncode == 0 and summ(tag).exists() else 'LỖI (xem voltvar_logs)'} {tag} sau {(time.time() - t0) / 60:.0f} phút", flush=True)

need = [f"{B}_grid_S1", f"{B}_grid_S3_wZ{WZ}"]
miss = [t for t in need if not summ(t).exists()]
if miss:
    print("THIẾU bản lưới không volt–var:", miss, "– chạy run_overnight.py trước.")
add = f"S1_grid={B}_grid_S1,S3_grid={B}_grid_S3_wZ{WZ},S1_vv={B}_vv_S1,S3_vv={B}_vv_S3_wZ{WZ}"
name = ("6thang_vv" if args.days == "0" else f"{args.days}ngay_vv") + SFX
cmd = [PY, str(PROJECT_DIR / "grid33_eval.py")] + (["--batch", B, "--add", add] if args.days == "0" else ["--dirs", add]) + ["--name", name]
print("\n=== đánh giá AC:", " ".join(cmd[2:]), flush=True)
with open(LOG / "grid_eval.log", "w", encoding="utf-8") as lf:
    r = subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT, env=env)
print("    xong" if r.returncode == 0 else f"    LỖI – xem {LOG / 'grid_eval.log'}", flush=True)

L = [f"VIỆC 3.5 – VOLT–VAR – xong sau {(time.time() - t_all) / 60:.0f} phút", ""]
f = RES / f"grid33_{name}" / "summary.txt"
L += [f"######## grid33_{name}", f.read_text(encoding="utf-8") if f.exists() else "(không có – xem voltvar_logs)", ""]
for tag in need + [t for t, _ in sim if "_vv_" in t]:
    f = summ(tag)
    if f.exists():
        s = f.read_text(encoding="utf-8")
        L.append(f"######## {tag}")
        L += [x for x in s.splitlines() if any(k in x for k in ("KHÔNG ĐẠT", "K2 –", "K6 –", "K11", "K7 –", "VOLT"))]
        L += [f"  lý thuyết: {'ĐẠT hết' if 'KHÔNG ĐẠT' not in s else 'CÓ MỤC KHÔNG ĐẠT'}", ""]
(RES / f"voltvar_summary{SFX}.txt").write_text("\n".join(L), encoding="utf-8")
print(f"\nXONG. Gửi Claude: {RES / f'voltvar_summary{SFX}.txt'}")
