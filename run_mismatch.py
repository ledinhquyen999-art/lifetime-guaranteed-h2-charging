"""
VIỆC 4.2 – SAI LỆCH MÔ HÌNH: bộ điều khiển dùng đường hiệu suất H2 xấp xỉ, còn "máy thật" chạy theo đường trơn tại mức lão hóa thật.
Kiểm chứng: bồn H2 vẫn trong giới hạn (Mệnh đề 1, ý 2), các kiểm tra lý thuyết vẫn đạt, chi phí tăng bao nhiêu.
Đặt trong DATN2026 (cùng step3_simulate.py BẢN MỚI có --plant) rồi chạy:
    python run_mismatch.py              # 9 lần × 30 ngày + 1 lần × 6 tháng, ~1 giờ, chạy 2 cùng lúc
    python run_mismatch.py --reuse      # lỡ tắt máy: phần nào xong rồi thì bỏ qua
Ghi: results/mismatch_summary.txt   ← GỬI FILE NÀY CHO CLAUDE
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
if '"--plant"' not in (PROJECT_DIR / "step3_simulate.py").read_text(encoding="utf-8", errors="ignore"):
    raise SystemExit("Cần step3_simulate.py BẢN MỚI (có --plant) trong DATN2026.")

ap = argparse.ArgumentParser()
ap.add_argument("--wz", default="1e10", help="w_Z của S3 (cấu hình chính đã chốt: 1e10)")
ap.add_argument("--jobs", type=int, default=2)
ap.add_argument("--reuse", action="store_true")
ap.add_argument("--days", default="30", help=argparse.SUPPRESS)      # chỉ để thử code
ap.add_argument("--no6m", action="store_true", help="bỏ lần chạy 6 tháng")
args = ap.parse_args()
WZ = args.wz; SFX = "" if WZ == "3e8" else f"_wz{WZ}"      # tên kết quả cũ (3e8) giữ nguyên, bản mới thêm hậu tố
env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
LOG = RES / "mismatch_logs"; LOG.mkdir(parents=True, exist_ok=True)
B = f"batch_2022-11-01_{args.days}d"
S3 = ["--wz", WZ, "--V", "1"]
base = ["--days", args.days, "--start", "2022-11-01"] + S3
SC = [  # (nhãn, tag, tùy chọn thêm, giải thích)
    ("Lý tưởng", f"{B}_S3_wZ{WZ}", [], "máy thật = mô hình bộ điều khiển (kết quả cũ)"),
    ("M1", f"{B}_mm_M1{SFX}", ["--plant"], "đường trơn thật; bộ điều khiển dùng các điểm hiệu chỉnh, cập nhật mỗi ngày"),
    ("M2", f"{B}_mm_M2{SFX}", ["--plant", "--mm_seg", "2"], "bộ điều khiển chỉ 2 đoạn"),
    ("M3", f"{B}_mm_M3{SFX}", ["--plant", "--mm_seg", "1"], "bộ điều khiển chỉ 1 đoạn (hiệu suất gần như hằng số)"),
    ("M4", f"{B}_mm_M4{SFX}", ["--plant", "--mm_d0", "0.5", "--mm_update", "none"], "máy đã già nửa đời, bộ điều khiển vẫn dùng đường máy mới"),
    ("M5", f"{B}_mm_M5{SFX}", ["--plant", "--mm_d0", "0.5"], "máy đã già nửa đời, bộ điều khiển cập nhật theo lão hóa đo được"),
    ("M6", f"{B}_mm_M6{SFX}", ["--plant", "--mm_bias", "0.1"], "lệch +10%: FC tốn hơn, EL ra ít hơn (dồn bồn về đáy)"),
    ("M7", f"{B}_mm_M7{SFX}", ["--plant", "--mm_bias", "-0.1"], "lệch −10%: FC tốn ít hơn, EL ra nhiều hơn (dồn bồn lên đỉnh)"),
    ("M8", f"{B}_mm_M8{SFX}", ["--plant", "--mm_bias", "0.1", "--mm_nominal"], "như M6 nhưng KHÔNG nới chặn m_max (đối chứng)"),
    ("M9", f"{B}_mm_M9{SFX}", ["--plant", "--mm_bias", "-0.1", "--mm_nominal"], "như M7 nhưng KHÔNG nới chặn m_max (đối chứng)"),
]
LONG = [("Lý tưởng 6T", f"batch_2022-09-01_181d_S3_wZ{WZ}", ["--days", "0"] + S3, "6 tháng, kết quả cũ"),
        ("M1 6T", f"batch_2022-09-01_181d_mm_M1{SFX}", ["--days", "0"] + S3 + ["--plant"], "6 tháng, như M1")]
jobs = [(t, base + o) for _, t, o, _ in SC] + ([] if args.no6m else [(t, o) for _, t, o, _ in LONG])
summ = lambda tag: RES / f"step3_{tag}" / "summary.txt"
pending = [j for j in jobs if not (summ(j[0]).exists() and (args.reuse or "_mm_" not in j[0]))]   # bản lý tưởng đã có thì dùng lại
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
        print(f"  {'xong' if pr.returncode == 0 and summ(tag).exists() else 'LỖI (xem mismatch_logs)'} {tag} sau {(time.time() - t0) / 60:.0f} phút "
              f"(tổng {(time.time() - t_all) / 60:.0f} phút)", flush=True)


def parse(tag):
    f = summ(tag)
    if not f.exists():
        return None
    s = f.read_text(encoding="utf-8")
    r = {"txt": s}
    m = re.search(r"K2 – chi phí \(gồm giá lão hóa\): ([\d,]+) CNY", s); r["cost"] = float(m.group(1).replace(",", "")) if m else float("nan")
    r["ok"] = "KHÔNG ĐẠT" not in s
    eF = [float(x) for x in re.findall(r"e\^M đo được FC [\d.]+ / EL [\d.]+ kg/bước \(= ([\d.]+)%", s)]
    eE = [float(x) for x in re.findall(r"e\^M đo được FC [\d.]+ / EL [\d.]+ kg/bước \(= [\d.]+% / ([\d.]+)%", s)]
    r["eF"], r["eE"] = (max(eF) if eF else 0.0), (max(eE) if eE else 0.0)
    tanks = re.findall(r"Mệnh đề 1 – bồn \d+: M ∈ \[([-\d.]+), ([-\d.]+)\] kg so với \[([-\d.]+), ([-\d.]+)\]", s)
    r["gap_lo"] = min(float(a) - float(c) for a, b, c, d in tanks) if tanks else float("nan")
    r["gap_hi"] = min(float(d) - float(b) for a, b, c, d in tanks) if tanks else float("nan")
    lf = re.findall(r"tuổi thọ dự kiến theo tốc độ kỳ này: FC ([\d.]+) năm", s)
    r["life"] = min(float(x) for x in lf) if lf else float("nan")
    return r


L = [f"VIỆC 4.2 – SAI LỆCH MÔ HÌNH – {args.days} ngày từ 2022-11-01 (S3, w_Z = {WZ}, V = 1) – xong sau {(time.time() - t_all) / 60:.0f} phút", ""]
hdr = f"{'':12}{'chi phí CNY':>12}{'so lý tưởng':>13}{'e^M FC':>8}{'e^M EL':>8}{'cách đáy kg':>12}{'cách đỉnh kg':>13}{'FC ≥ năm':>9}  lý thuyết  | kịch bản"
for title, rows in (("30 NGÀY", SC), ("6 THÁNG", [] if args.no6m else LONG)):
    if not rows:
        continue
    L += [f"=== {title}", hdr]
    ref = parse(rows[0][1])
    for lab, tag, _, desc in rows:
        r = parse(tag)
        if r is None:
            L.append(f"{lab:12}(chưa có – xem mismatch_logs)  | {desc}"); continue
        d = (100 * (r["cost"] / ref["cost"] - 1)) if ref else float("nan")
        L.append(f"{lab:12}{r['cost']:>12,.0f}{d:>12.2f}%{r['eF']:>7.1f}%{r['eE']:>7.1f}%{r['gap_lo']:>12.2f}{r['gap_hi']:>13.2f}{r['life']:>9.1f}  "
                 f"{'ĐẠT hết' if r['ok'] else 'CÓ MỤC KHÔNG ĐẠT':9}  | {desc}")
    L.append("")
L += ["Cột: e^M = sai số khối lượng H2 lớn nhất mỗi bước giữa bộ điều khiển và máy thật (% của m_max, lấy trạm lớn nhất);",
      "cách đáy/đỉnh = khoảng cách nhỏ nhất của bồn tới giới hạn trên mọi trạm (phải ≥ 0, Mệnh đề 1 ý 2); FC ≥ năm = tuổi thọ dự kiến FC thấp nhất.", ""]
for lab, tag, _, _ in SC[1:] + ([] if args.no6m else LONG[1:]):
    r = parse(tag)
    if r:
        L.append(f"######## {lab} ({tag})")
        L += [x for x in r["txt"].splitlines() if any(k in x for k in ("SAI LỆCH MÔ HÌNH", "K12", "e^M đo được", "KHÔNG ĐẠT", "Bổ đề 1"))]
        L.append("")
(RES / f"mismatch_summary{SFX}.txt").write_text("\n".join(L), encoding="utf-8")
print("\n".join(L[:30]))
print(f"\nXONG. Gửi Claude: {RES / f'mismatch_summary{SFX}.txt'}")
