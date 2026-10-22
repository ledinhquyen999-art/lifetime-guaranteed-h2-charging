"""
ĐÁNH ĐỔI CHI PHÍ – TUỔI THỌ BẢO ĐẢM (hình chính cho đóng góp của bài).
Quét trọng số hàng đợi sức khỏe w_Z (và V) trên 30 ngày tháng 11/2022, thêm bản 6 tháng ở w_Z = 1e10.
Mỗi điểm báo: chi phí, vượt MBA (so S1), tuổi thọ FC QUAN SÁT (theo tốc độ già trong kỳ) và tuổi thọ FC BẢO ĐẢM theo Hệ quả 1:
    L_bảo đảm = L_mục tiêu × (1 − Z_max)      (Z_max lấy từ cận Bổ đề 3 in trong summary.txt)
Đặt cùng step3_simulate.py BẢN MỚI trong DATN2026 rồi chạy (có thể chạy cùng lúc với run_multiyear.py):
    python run_tradeoff.py           # ~1–1,5 giờ (2 cùng lúc)
    python run_tradeoff.py --reuse
Ghi: results/tradeoff_summary.txt   ← GỬI FILE NÀY CHO CLAUDE
"""
import argparse
import json
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
ap = argparse.ArgumentParser()
ap.add_argument("--jobs", type=int, default=2)
ap.add_argument("--reuse", action="store_true")
ap.add_argument("--days", default="30")
ap.add_argument("--no6m", action="store_true")
ap.add_argument("--six", default="3e8,1e9,3e9,1e10", help="các w_Z chạy cả 6 tháng (đường \"giá của bảo đảm\")")
args = ap.parse_args()
env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
LOG = RES / "tradeoff_logs"; LOG.mkdir(parents=True, exist_ok=True)
B = f"batch_2022-11-01_{args.days}d"
base = ["--days", args.days, "--start", "2022-11-01"]
GRID = [(wz, "1") for wz in ("1e8", "3e8", "1e9", "3e9", "1e10")] + [("1e10", v) for v in ("0.25", "0.5")]
tagof = lambda wz, v: f"{B}_S3_wZ{wz}" + ("" if v == "1" else f"_V{v}")
jobs = [(tagof(wz, v), base + ["--wz", wz, "--V", v]) for wz, v in GRID] + [(f"{B}_S1", base + ["--no_h2", "--wz", "1e10"])]
L6 = "batch_2022-09-01_181d"
if not args.no6m:
    SIX = args.six.split(",")
    jobs += [(f"{L6}_S3_wZ{w}", ["--days", "0", "--wz", w, "--V", "1"]) for w in SIX] + [(f"{L6}_S1", ["--days", "0", "--no_h2", "--wz", "1e10"])]
summ = lambda t: RES / f"step3_{t}" / "summary.txt"
# chạy lại cả S1 và w_Z = 3e8 (để mọi điểm cùng có chi phí HIỆU CHỈNH cuối kỳ); --reuse thì bỏ qua phần đã có dòng hiệu chỉnh
has_corr = lambda t: summ(t).exists() and "K2 hiệu chỉnh cuối kỳ" in summ(t).read_text(encoding="utf-8")
pending = [j for j in jobs if not (args.reuse and has_corr(j[0]))]
pending.sort(key=lambda j: 0 if j[0].startswith(L6) else 1)            # bản 6 tháng (lâu nhất) chạy trước
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
        print(f"  {'xong' if pr.returncode == 0 and summ(tag).exists() else 'LỖI (xem tradeoff_logs)'} {tag} sau {(time.time() - t0) / 60:.0f} phút", flush=True)

L_TARGET = json.loads((PROJECT_DIR / "params" / "params_tier1.json").read_text(encoding="utf-8"))["aging_and_devices"]["fc"]["life_target_h"] / 8760


def P(tag):
    f = summ(tag)
    if not f.exists():
        return None
    s = f.read_text(encoding="utf-8")
    g = lambda pat: (float(re.search(pat, s).group(1).replace(",", "")) if re.search(pat, s) else float("nan"))
    lf = [float(x) for x in re.findall(r"tuổi thọ dự kiến theo tốc độ kỳ này: FC ([\d.]+|inf) năm", s)]
    zm = [float(x) for x in re.findall(r"Bổ đề 3 – trạm \d+: max Z_FC = [\d.e+-]+ \(≤ ([\d.e+-]+)", s)]
    raw = g(r"K2 – chi phí \(gồm giá lão hóa\): ([\d,]+) CNY"); cor = g(r"K2 hiệu chỉnh cuối kỳ: ([\d,]+) CNY")
    return dict(cost=cor if cor == cor else raw, raw=raw, ov=g(r"vượt giới hạn MBA ([\d.]+) MWh"),
                life=min(lf) if lf else float("nan"), zmax=max(zm) if zm else float("nan"), ok="KHÔNG ĐẠT" not in s)


s1 = P(f"{B}_S1")
L = [f"ĐÁNH ĐỔI CHI PHÍ – TUỔI THỌ BẢO ĐẢM – {args.days} ngày từ 2022-11-01 – tuổi thọ mục tiêu FC {L_TARGET:.0f} năm – xong sau {(time.time() - t_all) / 60:.0f} phút", "",
     f"{'w_Z':>6}{'V':>6}{'chi phí CNY':>13}{'so S1':>8}{'vượt MBA so S1':>16}{'Z_max (cận)':>13}{'FC BẢO ĐẢM ≥ năm':>19}{'FC quan sát':>13}  lý thuyết"]
for wz, v in GRID:
    r = P(tagof(wz, v))
    if not r or not s1:
        L.append(f"{wz:>6}{v:>6}  (chưa có)"); continue
    L.append(f"{wz:>6}{v:>6}{r['cost']:>13,.0f}{100 * (r['cost'] / s1['cost'] - 1):>7.1f}%{100 * (r['ov'] / s1['ov'] - 1):>15.1f}%"
             f"{r['zmax']:>13.4f}{L_TARGET * (1 - r['zmax']):>19.2f}{r['life']:>13.1f}  {'ĐẠT hết' if r['ok'] else 'CÓ MỤC KHÔNG ĐẠT'}")
if not args.no6m:
    c = P(f"{L6}_S1")
    L += ["", "6 THÁNG (2022-09 → 2023-02), V = 1 – đường \"giá của bảo đảm\":"]
    for lab, r in [("không H2 (S1)", c)] + [(f"w_Z = {w}" + (" (CẤU HÌNH CHÍNH)" if w == "1e10" else ""), P(f"{L6}_S3_wZ{w}")) for w in SIX]:
        if r and lab.startswith("không"):
            L.append(f"  {lab:28} chi phí {r['cost']:,.0f} CNY | vượt MBA {r['ov']:.1f} MWh")
        elif r:
            so = f" | so S1: chi phí {100 * (r['cost'] / c['cost'] - 1):+.1f}%, vượt MBA {100 * (r['ov'] / c['ov'] - 1):+.1f}%" if c else ""
            L.append(f"  {lab:28} chi phí {r['cost']:,.0f} CNY | vượt MBA {r['ov']:.1f} MWh{so} | Z_max {r['zmax']:.4f} → FC BẢO ĐẢM ≥ "
                     f"{L_TARGET * (1 - r['zmax']):.2f} năm | FC quan sát {r['life']:.1f} năm | {'ĐẠT hết' if r['ok'] else 'CÓ MỤC KHÔNG ĐẠT'}")
        else:
            L.append(f"  {lab:28} (chưa có)")
L += ["", "Chi phí = K2 HIỆU CHỈNH cuối kỳ (trừ phần năng lượng pin, bồn còn lại/đã tiêu so với đầu kỳ) khi có; bản cũ chưa có dòng này thì dùng K2 thô.",
      "Đọc: tuổi thọ BẢO ĐẢM là cận dưới chứng minh được cho MỌI chuỗi dữ liệu (Hệ quả 1); tuổi thọ quan sát là tốc độ già thực tế trong kỳ.",
      "Nếu chi phí ở w_Z lớn gần bằng w_Z = 3e8 thì nên đổi cấu hình chính sang w_Z lớn: bảo đảm gần đủ 5 năm mà gần như không tốn thêm."]
(RES / "tradeoff_summary.txt").write_text("\n".join(L), encoding="utf-8")
print("\n".join(L))
print(f"\nXONG. Gửi Claude: {RES / 'tradeoff_summary.txt'}")
