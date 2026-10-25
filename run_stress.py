"""
THÍ NGHIỆM BẤT LỢI – bảo đảm tuổi thọ KHÔNG phụ thuộc việc đặt đúng giá lão hóa.

Câu hỏi phản biện: "trên dữ liệu này w_Z = 3e8 vẫn sống 6,3 năm, vậy hàng đợi Z để làm gì?"
Trả lời bằng thí nghiệm: bộ điều khiển dùng giá stack FC SAI (đánh giá thấp: ×0,3 và ×0 = bỏ hẳn giá lão hóa trong hàm mục tiêu).
  • w_Z = 1e6  ("chỉ dùng giá"): hàng đợi Z gần như không có tác dụng (Z_max ≫ 1, không có bảo đảm).
  • w_Z = 1e10 (đề xuất)       : Z_max không phụ thuộc giá μ (Bổ đề 3) → tuổi thọ bảo đảm ≥ 4,92 năm ở MỌI mức giá.
Kỳ vọng: giá càng sai, bản "chỉ dùng giá" càng làm FC già nhanh (có thể < 5 năm); bản đề xuất vẫn ≥ 4,92 năm.

Chi phí báo cáo được tính lại với GIÁ STACK THẬT (giá mà bộ điều khiển không biết):
    chi phí thật = K2 hiệu chỉnh cuối kỳ + Σ_trạm (1 − hệ số) · giá stack FC thật · P_FC · ΣΔD_FC
Mỗi kết quả so với BAT (chỉ pin) cùng kỳ.

Đặt cùng step3_simulate.py (bản có --fc_stack_mult) trong DATN2026 rồi chạy:
    python run_stress.py                 # 30 ngày, 5 lần mô phỏng mới (~30–50 phút, chạy 2 cùng lúc)
    python run_stress.py --six           # thêm 6 tháng cho cặp giá ×0 (lâu hơn nhiều, để chạy qua đêm)
    python run_stress.py --reuse         # chỉ đọc lại kết quả đã có, viết lại bảng
Ghi: results/stress_summary.txt
"""
import argparse
import json
import math
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
if '"--fc_stack_mult"' not in (PROJECT_DIR / "step3_simulate.py").read_text(encoding="utf-8", errors="ignore"):
    raise SystemExit("Cần step3_simulate.py bản có --fc_stack_mult trong DATN2026.")

ap = argparse.ArgumentParser()
ap.add_argument("--mults", default="1,0.3,0", help="hệ số nhân giá stack FC mà BỘ ĐIỀU KHIỂN dùng (1 = đúng giá)")
ap.add_argument("--wzs", default="1e6,1e10", help="w_Z: 1e6 = chỉ dùng giá (không bảo đảm), 1e10 = đề xuất")
ap.add_argument("--days", default="30")
ap.add_argument("--six", action="store_true", help="thêm 6 tháng (9/2022–2/2023) cho giá ×0 với cả hai w_Z")
ap.add_argument("--jobs", type=int, default=2)
ap.add_argument("--reuse", action="store_true", help="không chạy gì, chỉ đọc kết quả đã có")
args = ap.parse_args()

MULTS = [float(x) for x in args.mults.split(",")]
WZS = [w.strip() for w in args.wzs.split(",")]
env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
LOG = RES / "stress_logs"; LOG.mkdir(parents=True, exist_ok=True)
B30 = f"batch_2022-11-01_{args.days}d"
B6 = "batch_2022-09-01_181d"
base30 = ["--days", args.days, "--start", "2022-11-01"]
base6 = ["--days", "0", "--start", "2022-09-01"]

params = json.loads((PROJECT_DIR / "params" / "params_tier1.json").read_text(encoding="utf-8"))
MU_FC = params["aging_and_devices"]["fc"]["stack_cost_CNY_per_kW"]          # giá stack FC THẬT, CNY/kW
L_TARGET = params["aging_and_devices"]["fc"]["life_target_h"] / 8760.0         # năm


def tag_s3(B, m, wz):
    # cấu hình gốc (giá đúng, w_Z = 1e10) dùng lại kết quả đã có của các bảng khác
    return f"{B}_S3_wZ{wz}" if (m == 1.0 and wz == "1e10") else f"{B}_stress_mu{m:g}_wz{wz}"


def opts_s3(base, m, wz):
    o = base + ["--wz", wz, "--V", "1"]
    return o + (["--fc_stack_mult", f"{m:g}"] if m != 1.0 else [])


jobs = [(f"{B30}_S1", base30 + ["--no_h2", "--wz", "1e10"])]
cases30 = [(m, wz) for wz in WZS for m in MULTS]
jobs += [(tag_s3(B30, m, wz), opts_s3(base30, m, wz)) for m, wz in cases30]
cases6 = []
if args.six:
    cases6 = [(1.0, "1e10"), (0.0, WZS[0]), (0.0, WZS[-1])]
    jobs.append((f"{B6}_S1", base6 + ["--no_h2", "--wz", "1e10"]))
    jobs += [(tag_s3(B6, m, wz), opts_s3(base6, m, wz)) for m, wz in cases6]

summ = lambda t: RES / f"step3_{t}" / "summary.txt"
has_corr = lambda t: summ(t).exists() and "K2 hiệu chỉnh cuối kỳ" in summ(t).read_text(encoding="utf-8")
pending = [] if args.reuse else [j for j in jobs if not has_corr(j[0])]
t_all = time.time()
print(f"{len(pending)} lần mô phỏng mới, chạy {args.jobs} cùng lúc", flush=True)
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
        print(f"  {'xong' if pr.returncode == 0 and summ(tag).exists() else 'LỖI (xem results/stress_logs)'} {tag} sau {(time.time() - t0) / 60:.0f} phút", flush=True)

NUM = r"([-+]?[\d.]+(?:e[-+]?\d+)?|inf|nan)"


def P(tag, mult=1.0):
    """Đọc summary.txt; chi phí tính lại với giá stack FC THẬT."""
    f = summ(tag)
    if not f.exists():
        return None
    s = f.read_text(encoding="utf-8")
    g = lambda pat: (float(re.search(pat, s).group(1).replace(",", "")) if re.search(pat, s) else float("nan"))
    cost = g(r"K2 hiệu chỉnh cuối kỳ: ([\d,]+) CNY")
    if cost != cost:
        cost = g(r"K2 – chi phí \(gồm giá lão hóa\): ([\d,]+) CNY")
    st = {}
    for mm in re.finditer(r"^\s+(\S+): PV .*?\| FC ([\d.]+) kW, EL ([\d.]+) kW.*?Z_max\(FC/EL\)=" + NUM + "/" + NUM, s, re.M):
        st[mm.group(1)] = dict(Pfc=float(mm.group(2)), zmax=float(mm.group(4)))
    for mm in re.finditer(r"Bổ đề 2 – trạm (\S+): ΣΔD_FC = " + NUM, s):
        if mm.group(1) in st:
            st[mm.group(1)]["dD"] = float(mm.group(2))
    for mm in re.finditer(r"Bổ đề 3 – trạm (\S+): max Z_FC = " + NUM, s):
        if mm.group(1) in st:
            st[mm.group(1)]["zobs"] = float(mm.group(2))
    for mm in re.finditer(r"Trạm (\S+): H2 làm ra .*?bật (\d+) lần \|.*?\n\s+K7 – tuổi thọ dự kiến theo tốc độ kỳ này: FC " + NUM + " năm", s):
        if mm.group(1) in st:
            st[mm.group(1)]["starts"] = int(mm.group(2)); st[mm.group(1)]["life"] = float(mm.group(3))
    extra = sum((1.0 - mult) * MU_FC * d["Pfc"] * d.get("dD", 0.0) for d in st.values())
    lives = [d["life"] for d in st.values() if "life" in d]
    zmax = max((d["zmax"] for d in st.values()), default=float("nan"))
    return dict(cost_true=cost + extra, extra=extra, ov=g(r"vượt giới hạn MBA ([\d.]+) MWh"),
                life=min(lives) if lives else float("nan"), starts=sum(d.get("starts", 0) for d in st.values()),
                zmax=zmax, guar=L_TARGET * (1.0 - zmax), zobs=max((d.get("zobs", 0.0) for d in st.values()), default=0.0),
                ok="KHÔNG ĐẠT" not in s)


def table(B, cases, title, days):
    b1 = P(f"{B}_S1")
    Ty = days / 365.0
    out = [title, "",
           f"{'w_Z':>6} {'giá stack FC':>13} {'chi phí THẬT':>14} {'so BAT':>8} {'vượt MBA':>9} {'so BAT':>8} {'số lần':>7} {'FC sống':>8} {'sàn kỳ này':>11} {'FC BẢO ĐẢM':>11}  lý thuyết",
           f"{'':>6} {'bộ ĐK dùng':>13} {'CNY':>14} {'':>8} {'MWh':>9} {'':>8} {'bật FC':>7} {'(năm)':>8} {'(năm)':>11} {'L(1−Zmax)':>11}"]
    if not b1:
        out.append("  (thiếu kết quả BAT – chạy lại không có --reuse)")
        return out
    out.append(f"{'BAT':>6} {'—':>13} {b1['cost_true']:>14,.0f} {'—':>8} {b1['ov']:>9.2f} {'—':>8}")
    for m, wz in cases:
        r = P(tag_s3(B, m, wz), m)
        lab = f"× {m:g}" + (" (đúng)" if m == 1.0 else "")
        if not r:
            out.append(f"{wz:>6} {lab:>13}  (chưa có)"); continue
        guar = f"{r['guar']:.2f} năm" if r["zmax"] < 1 else "không có"
        floor = f"{Ty / (Ty / L_TARGET + r['zmax']):.2f}" if r["zmax"] < 1 else "không có"
        out.append(f"{wz:>6} {lab:>13} {r['cost_true']:>14,.0f} {100 * (r['cost_true'] / b1['cost_true'] - 1):>7.1f}% {r['ov']:>9.2f} "
                   f"{100 * (r['ov'] / b1['ov'] - 1):>7.1f}% {r['starts']:>7d} {r['life']:>8.2f} {floor:>11} {guar:>11}  "
                   f"{'ĐẠT hết' if r['ok'] else 'CÓ MỤC KHÔNG ĐẠT'}")
    return out


L = [f"THÍ NGHIỆM BẤT LỢI – giá stack FC trong hàm mục tiêu bị đánh giá thấp – xong sau {(time.time() - t_all) / 60:.0f} phút",
     f"Giá stack FC thật {MU_FC:,.0f} CNY/kW; tuổi thọ mục tiêu {L_TARGET:.1f} năm. 'FC sống' = tuổi thọ FC thấp nhất 3 trạm theo tốc độ già của kỳ.",
     "Chi phí THẬT = K2 hiệu chỉnh cuối kỳ + phần giá lão hóa FC mà bộ điều khiển bỏ sót, tính theo giá thật.", ""]
L += table(B30, cases30, f"=== {args.days} NGÀY từ 2022-11-01", float(args.days))
if args.six:
    L += [""] + table(B6, cases6, "=== 6 THÁNG 2022-09 → 2023-02", 181.0)
L += ["", "Đọc:",
      "  • Hàng w_Z = 1e6: 'chỉ dùng giá'. Nếu giá sai làm 'FC sống' < 5 năm → giá lão hóa một mình KHÔNG giữ được tuổi thọ.",
      "  • Hàng w_Z = 1e10: 'FC BẢO ĐẢM' phải giữ nguyên ở mọi mức giá (Z_max không phụ thuộc μ) và 'FC sống' ≥ 'sàn kỳ này'.",
      "  • 'sàn kỳ này' = tốc độ già xấu nhất Mệnh đề 2 cho phép TRONG KỲ NGẮN (δT + Z_max): kỳ càng dài càng tiến tới 'FC BẢO ĐẢM'.",
      "    Vì vậy trên 30 ngày, 'FC sống' của bản đề xuất có thể < 5 năm mà vẫn đúng lý thuyết; muốn thấy rõ dùng --six (6 tháng).",
      "  • Đây là thông điệp chính cho bài: bảo đảm tuổi thọ không phụ thuộc việc đặt đúng giá lão hóa, vốn rất bất định."]
(RES / "stress_summary.txt").write_text("\n".join(L), encoding="utf-8")
print("\n".join(L))
print(f"\nXONG. Kết quả: {RES / 'stress_summary.txt'}")
