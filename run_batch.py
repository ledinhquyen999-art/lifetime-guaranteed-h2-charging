"""
Chạy nhiều kịch bản step3 liền một lượt rồi gom thành MỘT bảng so sánh.
Đặt cùng thư mục với step3_simulate.py (DATN2026) rồi chạy:   python run_batch.py
  (mặc định 7 ngày từ 2022-11-01; đổi bằng --days, --start)

Các kịch bản:
  S1          : không hydrogen (chỉ PV + pin)                → mốc so sánh "không có H2"
  S3_wZ1e10   : đề xuất, w_Z = 1e10 (giữ tuổi thọ rất chặt)
  S3_wZ3e9    : đề xuất, w_Z = 3e9
  S3_wZ1e9    : đề xuất, w_Z = 1e9
  S3_wZ3e8    : đề xuất, w_Z = 3e8 (nới tuổi thọ, ưu tiên đỡ lưới)
  → w_Z nhỏ: FC được bật nhiều hơn khi lưới quá tải, đổi lại già nhanh hơn. Bảng cho thấy đường đánh đổi này.

Ghi: DATN2026/results/batch_<start>_<days>d/compare.txt   ← GỬI FILE NÀY CHO CLAUDE

VIỆC 2.3 – chạy đủ 6 tháng (toàn bộ dữ liệu 01/09/2022 – 28/02/2023), mọi phương pháp, chạy song song 3 việc:
    python run_batch.py --days 0 --wz 3e8 --all --jobs 3
  --days 0 : toàn bộ dữ liệu;  --all : thêm B0, quy tắc, 4 bản MPC;  --jobs : số lần chạy cùng lúc
  --reuse  : lần chạy nào đã có summary.txt thì dùng lại (khi lỡ tắt máy giữa chừng, chạy lại đúng lệnh cũ + --reuse)
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
# Ưu tiên bản step3 trong DATN2026; kiểm tra đúng phiên bản mới (có --init và bảng vượt tải theo trạm)
STEP3 = next((p for p in (PROJECT_DIR / "step3_simulate.py", HERE / "step3_simulate.py") if p.exists()), None)
if STEP3 is None:
    raise SystemExit("Không thấy step3_simulate.py trong DATN2026")
_src = STEP3.read_text(encoding="utf-8", errors="ignore")
if '"--init"' not in _src or "theo từng trạm" not in _src:
    raise SystemExit(f"{STEP3} là bản CŨ. Chép bản step3_simulate.py mới nhất (có --init) vào DATN2026 rồi chạy lại.")
print(f"[*] Dùng: {STEP3}")

ap = argparse.ArgumentParser()
ap.add_argument("--days", type=int, default=7)
ap.add_argument("--start", default="2022-11-01")
ap.add_argument("--wz", default="1e10,3e9,1e9,3e8", help="danh sách w_Z, cách nhau bằng dấu phẩy")
ap.add_argument("--V", default="1", help="danh sách V (≤ 1), ví dụ 0.1,0.25,0.5,1 để kiểm Định lý 1")
ap.add_argument("--no_s1", action="store_true", help="bỏ kịch bản S1 (không H2)")
ap.add_argument("--with_noaging", action="store_true", help="thêm baseline B0: Lyapunov KHÔNG tính lão hóa (kiểu Yan & Chen)")
ap.add_argument("--with_rule", action="store_true", help="thêm baseline B2: quy tắc đơn giản (step5_baselines.py)")
ap.add_argument("--with_mpc", action="store_true", help="thêm baseline B1: MPC 24 h, dự báo theo lịch sử")
ap.add_argument("--with_mpc_oracle", action="store_true", help="thêm baseline B1*: MPC 24 h, dự báo hoàn hảo")
ap.add_argument("--with_mpc_life", action="store_true", help="thêm MPC dự báo lịch sử + ràng buộc cứng tuổi thọ")
ap.add_argument("--with_mpc_life_oracle", action="store_true", help="thêm MPC biết trước + ràng buộc cứng tuổi thọ")
ap.add_argument("--all", action="store_true", help="bật mọi baseline: B0, quy tắc, MPC (4 bản)")
ap.add_argument("--jobs", type=int, default=1, help="số lần chạy song song (máy 4 nhân: 3)")
ap.add_argument("--reuse", action="store_true", help="dùng lại kết quả đã có (summary.txt) thay vì chạy lại")
ap.add_argument("--extra", default="", help="tham số thêm cho mọi lần chạy, ví dụ \"--tr_frac 0.7\"")
args = ap.parse_args()
if args.all:
    args.with_noaging = args.with_rule = args.with_mpc = args.with_mpc_oracle = True
    args.with_mpc_life = args.with_mpc_life_oracle = True
if args.days <= 0:      # toàn bộ dữ liệu: step3/step5 tự lấy hết; đặt nhãn theo ngày đầu và số ngày thật
    import pandas as _pd
    _ix = _pd.read_csv(PROJECT_DIR / "data_clean" / "tier1_inputs.csv", usecols=[0], index_col=0, parse_dates=True).index
    args.start, args.days, FULL = str(_ix[0].date()), int(round((_ix[-1] - _ix[0]).total_seconds() / 86400 + 1 / 288)), True
else:
    FULL = False

Vs = args.V.split(",")
runs = ([] if args.no_s1 else [("S1", ["--no_h2", "--wz", "1e10"])]) + [
    (f"S3_wZ{float(w):.0e}".replace("e+0", "e").replace("e+", "e") + (f"_V{v}" if len(Vs) > 1 else ""), ["--wz", w, "--V", v])
    for w in args.wz.split(",") for v in Vs]
if args.with_noaging:
    runs.insert(1 if not args.no_s1 else 0, ("B0_noAging", ["--no_aging", "--wz", args.wz.split(",")[0], "--V", Vs[-1]]))
if args.with_rule:
    runs.append(("B2_rule", ["@step5", "--method", "rule"]))
if args.with_mpc:
    runs.append(("B1_mpc", ["@step5", "--method", "mpc"]))
if args.with_mpc_oracle:
    runs.append(("B1_mpc_oracle", ["@step5", "--method", "mpc", "--oracle"]))
if args.with_mpc_life:
    runs.append(("B1_mpc_life", ["@step5", "--method", "mpc", "--mpc_life"]))
if args.with_mpc_life_oracle:
    runs.append(("B1_mpc_life_or", ["@step5", "--method", "mpc", "--oracle", "--mpc_life"]))
STEP5 = next((p for p in (PROJECT_DIR / "step5_baselines.py", HERE / "step5_baselines.py") if p.exists()), None)
if any(o and o[0] == "@step5" for _, o in runs) and STEP5 is None:
    raise SystemExit("Thiếu step5_baselines.py trong DATN2026")
batch = f"batch_{args.start}_{args.days}d"
out = PROJECT_DIR / "results" / batch
out.mkdir(parents=True, exist_ok=True)


def grab(pat, txt, cast=float, default=float("nan")):
    m = re.search(pat, txt)
    if not m:
        return default
    return cast(m.group(1).replace(",", ""))


def parse(name, s):
    fails = s.count("KHÔNG ĐẠT")
    row = dict(name=name,
               theory=("không bảo đảm" if "BƯỚC 5" in s else ("ĐẠT hết" if fails == 0 else f"{fails} mục KHÔNG ĐẠT")),
               cost=grab(r"K2 – chi phí \(gồm giá lão hóa\): ([\d,\.]+) CNY", s),
               cost_kwh=grab(r"trên mỗi kWh sạc: ([\d\.]+)", s),
               ov=grab(r"vượt giới hạn MBA ([\d\.]+) MWh", s),
               ov_h=grab(r"MWh \([\d\.]+% điện sạc\), ([\d\.]+) giờ có vượt", s),
               pen=grab(r"chi phí phạt vượt tải: ([\d,]+) CNY", s),
               buy=grab(r"mua lưới: ([\d,\.]+) MWh", s))
    for st in ("1093", "1242", "1589"):
        row[f"ovst_{st}"] = grab(rf"\n\s+{st}(?: \(H2\))?\s*:\s+([\d\.]+) \|", s)
        m = re.search(rf"{st} \(H2\):\s+[\d\.]+ \|\s+[\d\.]+ h \|\s+\d+% \| ([\d\.]+)", s)
        row[f"fcov_{st}"] = float(m.group(1)) if m else float("nan")
        row[f"life_{st}"] = grab(rf"Trạm {st}:.*\n\s+K7 – tuổi thọ dự kiến theo tốc độ kỳ này: FC ([\d\.inf]+) năm", s,
                                 cast=lambda x: float("inf") if x == "inf" else float(x))
        row[f"h2_{st}"] = grab(rf"Trạm {st}: H2 làm ra [\-\d\.]+ kg, dùng ([\d\.]+) kg", s)
    return row


env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")   # Windows: tránh lỗi in tiếng Việt khi chạy ngầm
jobs = []          # (name, tag, cmd)
for name, opt in runs:
    tag = f"{batch}_{name}"
    script = STEP3
    if opt and opt[0] == "@step5":
        script, opt = STEP5, opt[1:]
    days_arg = "0" if FULL else str(args.days)
    cmd = [sys.executable, str(script), "--days", days_arg, "--start", args.start, "--tag", tag] + opt + args.extra.split()
    jobs.append((name, tag, cmd))

summ_of = lambda tag: PROJECT_DIR / "results" / f"step3_{tag}" / "summary.txt"
logdir = out / "logs"; logdir.mkdir(exist_ok=True)
pending = [j for j in jobs if not (args.reuse and summ_of(j[1]).exists())]
for name, tag, _ in jobs:
    if (name, tag, _) not in pending:
        print(f"[dùng lại] {name}: {summ_of(tag)}")
running = {}       # name -> (Popen, t0, logfile)
errs = {}
t_all = time.time()
while pending or running:
    while pending and len(running) < max(1, args.jobs):
        name, tag, cmd = pending.pop(0)
        summ_of(tag).unlink(missing_ok=True)          # tránh đọc nhầm kết quả cũ nếu lần này lỗi
        lf = open(logdir / f"{name}.log", "w", encoding="utf-8")
        print(f"\n=== bắt đầu {name}: {' '.join(cmd[2:])}", flush=True)
        running[name] = (subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT, env=env), time.time(), lf, tag)
    time.sleep(5)
    for name in list(running):
        pr, t0, lf, tag = running[name]
        if pr.poll() is None:
            continue
        lf.close(); del running[name]
        if pr.returncode != 0 or not summ_of(tag).exists():
            tail = (logdir / f"{name}.log").read_text(encoding="utf-8", errors="ignore").strip().splitlines()
            errs[name] = tail[-1] if tail else "?"
            print(f"    {name}: LỖI sau {time.time() - t0:.0f} s – xem {logdir / (name + '.log')}", flush=True)
        else:
            print(f"    {name}: xong sau {(time.time() - t0) / 60:.1f} phút (đã chạy tổng {(time.time() - t_all) / 60:.0f} phút, còn {len(pending) + len(running)} việc)", flush=True)

rows = []
for name, tag, _ in jobs:
    if name in errs:
        rows.append(dict(name=name, error=errs[name])); continue
    if not summ_of(tag).exists():
        rows.append(dict(name=name, error="không có summary.txt")); continue
    rows.append(parse(name, summ_of(tag).read_text(encoding="utf-8")))

L = [f"SO SÁNH KỊCH BẢN – {args.days} ngày từ {args.start} {args.extra}", ""]
L.append(f"{'kịch bản':<15}{'lý thuyết':<16}{'chi phí CNY':>13}{'CNY/kWh':>9}{'vượt MBA MWh':>14}{'giờ vượt':>10}{'phạt CNY':>11}{'mua lưới MWh':>14}")
for r in rows:
    if "error" in r:
        L.append(f"{r['name']:<15}LỖI: {r['error']}"); continue
    L.append(f"{r['name']:<15}{r['theory']:<16}{r['cost']:>13,.0f}{r['cost_kwh']:>9.4f}{r['ov']:>14.2f}{r['ov_h']:>10.1f}{r['pen']:>11,.0f}{r['buy']:>14.1f}")
L.append("")
L.append("Trạm có H2: vượt MBA (MWh) | FC phát lúc đang vượt (MWh) | H2 dùng (kg) | tuổi thọ FC dự kiến (năm)")
for r in rows:
    if "error" in r or r["name"] == "S1":
        if r["name"] == "S1" and "error" not in r:
            L.append(f"  {r['name']:<15} " + "  ".join(f"{st}: vượt {r[f'ovst_{st}']:.2f}" for st in ("1093", "1242", "1589")))
        continue
    L.append(f"  {r['name']:<15} " + "  ".join(
        f"{st}: {r[f'ovst_{st}']:.2f} | {r[f'fcov_{st}']:.2f} | {r[f'h2_{st}']:.0f} kg | {r[f'life_{st}']:.1f} n" for st in ("1093", "1242", "1589")))
base = next((r for r in rows if r["name"] == "S1" and "error" not in r), None)
if base:
    L.append("\nSO VỚI S1 (không H2):")
    for r in rows:
        if r is base or "error" in r:
            continue
        L.append(f"  {r['name']:<15} vượt MBA giảm {100 * (1 - r['ov'] / base['ov']):5.1f}% | chi phí {100 * (r['cost'] / base['cost'] - 1):+5.1f}%")
# ---- so với C* (nếu đã chạy step4_cstar.py cùng số ngày/ngày bắt đầu)
import json as _json
for suffix, label in (("", "có H2"), ("_noH2", "không H2")):
    f = PROJECT_DIR / "results" / f"cstar_{args.start}_{args.days}d{suffix}" / "cstar.json"
    if not f.exists():
        continue
    cj = _json.loads(f.read_text(encoding="utf-8"))
    L.append(f"\nSO VỚI C* ({label}, {cj['mode']}): C* = {cj['C_star']:,.0f} CNY"
             + (" (nới lỏng LP: khoảng cách dưới đây là CẬN TRÊN)" if cj["mode"] == "LP" else f", cận dưới {cj['lower_bound']:,.0f}"))
    for r in rows:
        if "error" in r or (r["name"] == "S1") != (suffix == "_noH2"):
            continue
        L.append(f"  {r['name']:<16} chi phí {r['cost']:>11,.0f} | cách C*: {100 * (r['cost'] / cj['C_star'] - 1):5.1f}%")
# ---- theo từng tháng (kiểm tra kết luận có đúng ở MỌI tháng không, không chỉ tính gộp)
if args.days >= 45:
    import pandas as pd
    mon = {}
    for name, tag, _ in jobs:
        f = summ_of(tag).parent / "timeseries.csv"
        if name in errs or not f.exists():
            continue
        cols = pd.read_csv(f, nrows=0).columns
        use = [cols[0]] + [c for c in cols if c.startswith("ov_") or c == "cost"]
        d = pd.read_csv(f, usecols=use, index_col=0, parse_dates=True)
        g = d.resample("MS").sum()
        mon[name] = (g[[c for c in g.columns if c.startswith("ov_")]].sum(axis=1) * (5 / 60) / 1000, g["cost"])
    if "S1" in mon:
        months = mon["S1"][0].index
        L.append("\nTHEO THÁNG – vượt MBA (MWh) và [giảm so với S1]:")
        L.append(f"{'kịch bản':<16}" + "".join(f"{m.strftime('%m/%Y'):>17}" for m in months))
        for name, (ov, c) in mon.items():
            L.append(f"{name:<16}" + "".join(
                f"{ov.get(m, float('nan')):>9.2f}" + (f" [{100 * (1 - ov.get(m, float('nan')) / mon['S1'][0][m]):4.0f}%]" if name != "S1" and mon['S1'][0][m] > 0 else " " * 8)
                for m in months))
        L.append("\nTHEO THÁNG – chi phí (nghìn CNY):")
        for name, (ov, c) in mon.items():
            L.append(f"{name:<16}" + "".join(f"{c.get(m, float('nan')) / 1000:>17.1f}" for m in months))
txt = "\n".join(L)
(out / "compare.txt").write_text(txt, encoding="utf-8")
print("\n" + txt + f"\n\nĐã ghi: {out / 'compare.txt'}")
