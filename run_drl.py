"""
VIỆC 4.1 – SO VỚI DRL (PPO): 3 hạt giống PPO + S3b (đề xuất, không chia sẻ) trên cùng 30 ngày tháng 11/2022.
Cần (một lần):  python -m pip install stable-baselines3 gymnasium
Đặt drl_ppo.py, run_drl.py, step3_simulate.py BẢN MỚI (có --no_share) trong DATN2026 rồi chạy (SAU khi run_admm.py xong):
    python run_drl.py              # ~1–1,5 giờ (3 hạt giống chạy song song, mỗi cái 1 luồng)
    python run_drl.py --reuse      # phần nào xong rồi thì bỏ qua
Ghi: results/drl_summary.txt   ← GỬI FILE NÀY CHO CLAUDE
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
if '"--no_share"' not in (PROJECT_DIR / "step3_simulate.py").read_text(encoding="utf-8", errors="ignore"):
    raise SystemExit("Cần step3_simulate.py BẢN MỚI (có --no_share) trong DATN2026.")
try:
    import stable_baselines3  # noqa
    import gymnasium  # noqa
except ImportError:
    raise SystemExit("Cần cài:  python -m pip install stable-baselines3 gymnasium")

ap = argparse.ArgumentParser()
ap.add_argument("--wz", default="1e10", help="w_Z của S3 (cấu hình chính đã chốt: 1e10)")
ap.add_argument("--jobs", type=int, default=3)
ap.add_argument("--reuse", action="store_true")
ap.add_argument("--seeds", default="0,1,2")
ap.add_argument("--steps", default="3000000")
args = ap.parse_args()
WZ = args.wz; SFX = "" if WZ == "3e8" else f"_wz{WZ}"      # tên kết quả cũ (3e8) giữ nguyên, bản mới thêm hậu tố
env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1")
LOG = RES / "drl_logs"; LOG.mkdir(parents=True, exist_ok=True)
B = "batch_2022-11-01_30d"
seeds = [int(s) for s in args.seeds.split(",")]
jobs = [(f"step3_{B}_S3b_noshare{SFX}", [str(PROJECT_DIR / "step3_simulate.py"), "--tag", f"{B}_S3b_noshare{SFX}", "--days", "30",
                                    "--start", "2022-11-01", "--wz", WZ, "--V", "1", "--no_share"]),
        (f"step3_{B}_S1b_noshare", [str(PROJECT_DIR / "step3_simulate.py"), "--tag", f"{B}_S1b_noshare", "--days", "30",
                                    "--start", "2022-11-01", "--no_h2", "--wz", "1e10", "--no_share"])]
jobs = [(f"drl_ppo_s{s}", [str(PROJECT_DIR / "drl_ppo.py"), "--seed", str(s), "--steps", args.steps]) for s in seeds] + jobs   # DRL lâu → chạy trước
done_ = lambda d: (RES / d / "summary.txt").exists()
pending = [j for j in jobs if not (args.reuse and done_(j[0]))]
t_all = time.time()
print(f"{len(pending)} việc, chạy {args.jobs} cùng lúc (DRL in tiến độ mỗi 250.000 bước vào drl_logs)", flush=True)
running = {}
while pending or running:
    while pending and len(running) < args.jobs:
        d, cmd = pending.pop(0)
        lf = open(LOG / f"{d}.log", "w", encoding="utf-8")
        running[d] = (subprocess.Popen([PY] + cmd, stdout=lf, stderr=subprocess.STDOUT, env=env), time.time(), lf)
        print(f"  bắt đầu {d}", flush=True)
    time.sleep(10)
    for d in list(running):
        pr, t0, lf = running[d]
        if pr.poll() is None:
            continue
        lf.close(); del running[d]
        print(f"  {'xong' if pr.returncode == 0 and done_(d) else 'LỖI (xem drl_logs)'} {d} sau {(time.time() - t0) / 60:.0f} phút "
              f"(tổng {(time.time() - t_all) / 60:.0f} phút)", flush=True)


def step3_row(d):
    f = RES / d / "summary.txt"
    if not f.exists():
        return None
    s = f.read_text(encoding="utf-8")
    c = re.search(r"K2 – chi phí \(gồm giá lão hóa\): ([\d,]+) CNY", s)
    o = re.search(r"vượt giới hạn MBA ([\d.]+) MWh", s)
    lf = [float(x) for x in re.findall(r"tuổi thọ dự kiến theo tốc độ kỳ này: FC ([\d.]+|inf) năm", s) if x != "inf"]
    starts = [int(x) for x in re.findall(r"FC chạy [\d.]+% thời gian, bật (\d+) lần", s)]
    return dict(cost=float(c.group(1).replace(",", "")) if c else float("nan"), ov=float(o.group(1)) if o else float("nan"),
                life=min(lf) if lf else float("nan"), starts=sum(starts) if starts else float("nan"), ok="KHÔNG ĐẠT" not in s)


def drl_row(d):
    f = RES / d / "summary.txt"
    if not f.exists():
        return None
    s = f.read_text(encoding="utf-8")
    c = re.search(r"K2 – chi phí \(gồm giá lão hóa\): ([\d,]+) CNY", s)
    o = re.search(r"vượt giới hạn MBA: ([\d.]+) MWh", s)
    lf = [float(x) for x in re.findall(r"\d+: ([\d.]+|inf) năm", s.split("| EL")[0])]       # inf = không dùng FC
    st_ = [int(x) for x in re.findall(r"\d+: (\d+)", s.split("số lần bật FC:")[1].split("|")[0])] if "số lần bật FC:" in s else []
    return dict(cost=float(c.group(1).replace(",", "")) if c else float("nan"), ov=float(o.group(1)) if o else float("nan"),
                life=min(lf) if lf else float("nan"), starts=sum(st_) if st_ else float("nan"), ok=None, txt=s)


rows = [("Không H2 (S1)", step3_row(f"step3_{B}_S1")), ("Đề xuất (S3)", step3_row(f"step3_{B}_S3_wZ{WZ}")),
        ("S1b không H2, k. chia sẻ", step3_row(f"step3_{B}_S1b_noshare")), ("S3b không chia sẻ", step3_row(f"step3_{B}_S3b_noshare{SFX}"))]
drl = [(f"PPO hạt {s}", drl_row(f"drl_ppo_s{s}")) for s in seeds]
rows += drl
L = [f"VIỆC 4.1 – DRL (PPO) so với đề xuất – 30 ngày từ 2022-11-01 (PPO học trên 9–10/2022) – xong sau {(time.time() - t_all) / 60:.0f} phút", "",
     f"{'':22}{'chi phí CNY':>13}{'so S3b':>9}{'vượt MBA MWh':>14}{'FC sống ≥ năm':>15}{'số lần bật FC':>15}"]
ref = rows[3][1]["cost"] if rows[3][1] else float("nan")
for lab, r in rows:
    if r is None:
        L.append(f"{lab:22}(chưa có)"); continue
    L.append(f"{lab:22}{r['cost']:>13,.0f}{100 * (r['cost'] / ref - 1):>8.1f}%{r['ov']:>14.1f}{r['life']:>15.1f}{r['starts']:>15.0f}")
ok = [r for _, r in drl if r]
if ok:
    import statistics as stt
    cs = [r["cost"] for r in ok]; lf = [r["life"] for r in ok]
    L.append(f"{'PPO trung bình':22}{stt.mean(cs):>13,.0f}{100 * (stt.mean(cs) / ref - 1):>8.1f}%{stt.mean([r['ov'] for r in ok]):>14.1f}"
             f"{stt.mean(lf):>15.1f}{stt.mean([r['starts'] for r in ok]):>15.0f}   (độ lệch chuẩn chi phí {stt.pstdev(cs):,.0f})")
L += ["", "So công bằng: PPO không có chia sẻ giữa các trạm → so với S3b (đề xuất) và S1b (chỉ pin); S1, S3 (có chia sẻ) để tham khảo.",
      "Mô hình PPO chọn theo tập kiểm định 25–31/10 (không nhìn tháng 11); đường học trong từng khối cho thấy các mốc PPO có dùng FC.",
      "Cùng thông số, cùng mô hình H2 và lão hóa, cùng cách tính K2 (đã kiểm: phát lại quyết định của S3b trong môi trường DRL ra đúng chi phí).", ""]
for lab, r in drl:
    if r:
        L += [f"######## {lab}", r["txt"], ""]
(RES / f"drl_summary{SFX}.txt").write_text("\n".join(L), encoding="utf-8")
print("\n".join(L[:12]))
print(f"\nXONG. Gửi Claude: {RES / f'drl_summary{SFX}.txt'}")
