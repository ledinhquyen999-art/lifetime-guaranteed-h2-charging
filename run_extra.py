# -*- coding: utf-8 -*-
"""
PHÉP THỬ BỔ SUNG CHO BÀI (6 tháng 9/2022 → 2/2023, cấu hình chính S3: w_Z = 1e10, V = 1, PV 1×, θ_Z = 0.02)
  1) Độ nhạy:  k_run = 8.5 µV/h  |  FC_KP = 1.72 (hệ số đường thật của Chen 2015)  |  PV 2× (cả S3 và S1)
  2) Quét vùng đệm θ_Z = 0, 0.005, 0.01, 0.05   (0.02 = cấu hình chính, lấy từ giai đoạn A)
  3) "Giá không đủ" dài hạn: stack kém bền (k_run = 8.5 µV/h), 2 năm = 4 đoạn 6 tháng nối tiếp,
     chỉ dùng giá (w_Z = 1e6) so với có hàng đợi (w_Z = 1e10); nhà máy già dần (--plant).
  4) "Giá không đủ" khi giá stack thấp hơn (× 0,6 – cận dưới độ nhạy giá stack): k_run 8,5, 6 tháng, chỉ giá so với hàng đợi.
  5) Cỡ chuỗi H2 × 2 và × 3 (FC, EL, bồn ở 3 trạm H2), 30 ngày 11/2022: kết quả bị chặn bởi phần cứng hay bởi thuật toán?
Chạy:  python run_extra.py            (≈ 5,5 giờ, 2 lần chạy cùng lúc; chạy lại thì tự bỏ qua phần đã xong)
       python run_extra.py --quick    (thử code: mỗi lần chạy 2 ngày)
Ghi :  results/extra_summary.txt
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
RES = HERE / "results"; LOG = RES / "extra_logs"; LOG.mkdir(parents=True, exist_ok=True)
ap = argparse.ArgumentParser()
ap.add_argument("--jobs", type=int, default=2)
ap.add_argument("--quick", action="store_true")
args = ap.parse_args()
DAYS = "2" if args.quick else "181"
SUF = "_q" if args.quick else ""
BASE = ["--days", DAYS, "--start", "2022-09-01", "--wz", "1e10"]
CLEAN = {k: v for k, v in os.environ.items() if k not in ("K_RUN_UV", "K_SS_UV", "K_HP_UV", "THETA_Z", "FC_KP")}

# (tag, env thêm, tham số, phụ thuộc)
JOBS = [
    ("ex_krun85_6m", {"K_RUN_UV": "8.5"}, BASE, None),
    ("ex_kp172_6m", {"FC_KP": "1.72"}, BASE, None),
    ("ex_pv2_S3_6m", {}, BASE + ["--pv_scale", "2"], None),
    ("ex_pv2_S1_6m", {}, BASE + ["--pv_scale", "2", "--no_h2"], None),
    ("ex_S1_6m", {}, BASE + ["--no_h2"], None),
    ("ex_S3_6m", {}, BASE, None),
] + [(f"ex_th{th}_6m", {"THETA_Z": th}, BASE, None) for th in ("0", "0.005", "0.01", "0.05")]
for w in ("1e6", "1e10"):
    for k in range(4):
        t = f"ex_kr85_wz{w}_c{k}"
        a = ["--days", DAYS, "--start", "2022-09-01", "--wz", w, "--plant", "--light", "--state_out", str(LOG / f"{t}{SUF}.json")]
        if k:
            a += ["--state_in", str(LOG / f"ex_kr85_wz{w}_c{k - 1}{SUF}.json")]
        JOBS.append((t, {"K_RUN_UV": "8.5"}, a, f"ex_kr85_wz{w}_c{k - 1}" if k else None))

for w in ("1e6", "1e10"):
    JOBS.append((f"ex_kr85m06_wz{w}_c0", {"K_RUN_UV": "8.5"}, ["--days", DAYS, "--start", "2022-09-01", "--wz", w, "--plant", "--light",
                                                             "--fc_stack_mult", "0.6"], None))
for k in ("2", "3"):
    JOBS.append((f"ex_h2x{k}_30d", {}, ["--days", "2" if args.quick else "30", "--start", "2022-11-01", "--wz", "1e10", "--h2_scale", k], None))
COVS = ("2", "3", "10")                                   # độ nhạy mức phạt vượt giới hạn (chính: 5 CNY/kWh)
for c in COVS:
    for nm, ex in (("S1", ["--no_h2"]), ("S3", ["--wz", "1e10"])):
        JOBS.append((f"ex_cov{c}_{nm}_30d", {}, ["--days", "2" if args.quick else "30", "--start", "2022-11-01", "--c_ov", c] + ex, None))
for am in ("1", "6", "72"):                               # chia giá bật máy trong hàm mục tiêu (chính: 24 bước)
    JOBS.append((f"ex_am{am}_30d", {}, ["--days", "2" if args.quick else "30", "--start", "2022-11-01", "--wz", "1e10", "--start_amort", am], None))
for al in ("0.25", "0.5", "0.75"):                        # MPC-V với dự báo tốt dần: (1−α)·thật + α·lịch sử
    JOBS.append((f"ex_mpcV_blend{al}_30d", {}, ["@step5", "--method", "mpc", "--mpc_borrow", "--fc_blend", al,
                                                "--days", "2" if args.quick else "30", "--start", "2022-11-01"], None))
done = lambda t: (RES / f"step3_{t}{SUF}" / "summary.txt").exists()
todo = [j for j in JOBS if not done(j[0])]
running = {}
t_all = time.time()
print(f"[*] {len(todo)} lần chạy còn thiếu / {len(JOBS)}", flush=True)
while todo or running:
    for j in list(todo):
        if len(running) >= args.jobs:
            break
        tag, env, a, dep = j
        if dep and not done(dep):
            continue
        cmd = ([sys.executable, str(HERE / "step5_baselines.py"), "--tag", tag + SUF] + a[1:]) if a and a[0] == "@step5" else \
              ([sys.executable, str(HERE / "step3_simulate.py"), "--tag", tag + SUF] + a)
        lf = open(LOG / f"{tag}{SUF}.log", "w", encoding="utf-8")
        running[tag] = (subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT, env=dict(CLEAN, PYTHONIOENCODING="utf-8", PYTHONUTF8="1", **env)), lf, time.time())
        todo.remove(j)
        print(f"  bắt đầu {tag}", flush=True)
    time.sleep(5)
    for tag in list(running):
        pr, lf, t0 = running[tag]
        if pr.poll() is None:
            continue
        lf.close(); del running[tag]
        print(f"  {'xong' if pr.returncode == 0 and done(tag) else 'LỖI (xem results/extra_logs)'} {tag} sau {(time.time() - t0) / 60:.0f} phút", flush=True)
        if pr.returncode != 0:
            todo = [j for j in todo if j[3] != tag]       # đoạn sau của chuỗi không chạy được nữa


# ------------------------------------------------------------------ tổng hợp
def g(tag):
    f = RES / f"step3_{tag}{SUF if tag.startswith('ex_') else ''}" / "summary.txt"
    if not f.exists():
        return None
    s = f.read_text(encoding="utf-8")
    num = lambda p: float(re.search(p, s).group(1).replace(",", "")) if re.search(p, s) else float("nan")
    zm = [float(x) for x in re.findall(r"Z_max\(FC/EL\)=([\d.]+)", s)]
    life = [float(x) for x in re.findall(r"tuổi thọ dự kiến theo tốc độ kỳ này: FC ([\d.]+|inf) năm", s) if x != "inf"]
    return dict(cost=num(r"K2 hiệu chỉnh cuối kỳ: ([\d,]+) CNY"), ov=num(r"vượt giới hạn MBA ([\d.]+) MWh"),
                zmax=max(zm) if zm else float("nan"), life=min(life) if life else float("nan"),
                ok="ĐẠT hết" if "KHÔNG ĐẠT" not in s else f"{s.count('KHÔNG ĐẠT')} KHÔNG ĐẠT")


L = ["PHÉP THỬ BỔ SUNG – 6 tháng 2022-09 → 2023-02 (cấu hình chính: PV 1×, θ_Z = 0.02, w_Z = 1e10)", ""]
s1, s3 = g("ex_S1_6m"), g("ex_S3_6m")
pct = lambda a, b: f"{100 * (a / b - 1):+6.1f}%" if a and b else "    —"
L.append(f"{'kịch bản':34}{'chi phí CNY':>13}{'so S1':>9}{'vượt MBA MWh':>14}{'so S1':>9}{'Z_max':>8}{'BẢO ĐẢM ≥ năm':>15}{'FC nhịp kỳ':>11}  lý thuyết")
rows = [("S1 – không H2", "ex_S1_6m", s1), ("S3 – CHÍNH (θ_Z = 0.02)", "ex_S3_6m", s1),
        ("k_run = 8,5 µV/h", "ex_krun85_6m", s1), ("FC_KP = 1,72 (Chen)", "ex_kp172_6m", s1),
        ("PV 2× – không H2", "ex_pv2_S1_6m", None), ("PV 2× – S3", "ex_pv2_S3_6m", g("ex_pv2_S1_6m"))] + \
       [(f"θ_Z = {th}", f"ex_th{th}_6m", s1) for th in ("0", "0.005", "0.01", "0.05")]
for lab, tag, ref in rows:
    r = g(tag)
    if not r:
        L.append(f"{lab:34}  (chưa có)"); continue
    gua = f"{5 * (1 - r['zmax']):.2f}" if r["zmax"] == r["zmax"] else "—"
    L.append(f"{lab:34}{r['cost']:>13,.0f}{pct(r['cost'], ref['cost']) if ref else '     —':>9}{r['ov']:>14.1f}"
             f"{pct(r['ov'], ref['ov']) if ref else '     —':>9}{r['zmax']:>8.4f}{gua:>15}{r['life']:>11.1f}  {r['ok']}")
s30 = g("batch_2022-11-01_30d_S1") if not args.quick else None
b30 = g("batch_2022-11-01_30d_S3_wZ1e10") if not args.quick else None
L += ["", "CỠ CHUỖI H2 – 30 ngày 11/2022 (so với S1 30 ngày, giai đoạn B):"]
for lab, tag in (("H2 × 1 (chính)", None), ("H2 × 2", "ex_h2x2_30d"), ("H2 × 3", "ex_h2x3_30d")):
    r = b30 if tag is None else g(tag)
    if r and s30:
        L.append(f"  {lab:16}{r['cost']:>13,.0f}{pct(r['cost'], s30['cost']):>9}{r['ov']:>10.1f} MWh{pct(r['ov'], s30['ov']):>9}  {r['ok']}")
    else:
        L.append(f"  {lab:16}(chưa có)")
L += ["", "MỨC PHẠT VƯỢT GIỚI HẠN c_ov – 30 ngày 11/2022, S3 so với S1 CÙNG mức phạt (chính: 5 CNY/kWh):"]
for c in ("2", "3", "5", "10"):
    r1 = s30 if c == "5" else g(f"ex_cov{c}_S1_30d")
    r3 = b30 if c == "5" else g(f"ex_cov{c}_S3_30d")
    if r1 and r3:
        L.append(f"  c_ov = {c:>2} CNY/kWh   S1 {r1['cost']:>11,.0f}   S3 {r3['cost']:>11,.0f}  chi phí {pct(r3['cost'], r1['cost'])}"
                 f"   vượt MBA {r1['ov']:6.1f} → {r3['ov']:6.1f} MWh ({pct(r3['ov'], r1['ov'])})  {r3['ok']}")
    else:
        L.append(f"  c_ov = {c:>2} CNY/kWh   (chưa có)")
L += ["", "CHIA GIÁ BẬT MÁY TRONG HÀM MỤC TIÊU (chỉ phần giá μ; hàng đợi Z luôn tính đủ) – 30 ngày 11/2022, so S1 30 ngày:"]
for am in ("1", "6", "24", "72"):
    r = b30 if am == "24" else g(f"ex_am{am}_30d")
    if r and s30:
        L.append(f"  chia {am:>2} bước{' (chính)' if am == '24' else '        '}  {r['cost']:>11,.0f}  chi phí {pct(r['cost'], s30['cost'])}  vượt MBA {r['ov']:6.1f} MWh ({pct(r['ov'], s30['ov'])})  {r['ok']}")
    else:
        L.append(f"  chia {am:>2} bước  (chưa có)")
L += ["", "CHẤT LƯỢNG DỰ BÁO MPC CẦN CÓ – MPC-V (cùng ngân sách tuổi thọ), dự báo = (1−α)·thật + α·lịch sử, 30 ngày 11/2022:"]
def naive_err():                                         # nMAE gộp 7 trạm của dự báo theo lịch sử (tb cùng giờ 7 ngày trước), giờ tới, 11/2022
    try:
        import pandas as pd
        d_ = pd.read_csv(HERE / "data_clean" / "tier1_inputs.csv", index_col=0, parse_dates=True).resample("1h").mean()
        cols = [c for c in d_.columns if c.startswith("load_")]
        fc = sum(d_[cols].shift(24 * k) for k in range(1, 8)) / 7
        m_ = (d_.index >= "2022-11-01") & (d_.index < "2022-12-01")
        return 100 * float((fc[m_] - d_[cols][m_]).abs().sum().sum() / d_[cols][m_].sum().sum())
    except Exception:
        return float("nan")
E1 = naive_err()
rows5 = [("α = 0 (biết trước, MPC-V*)", "batch_2022-11-01_30d_B1_mpc_borrow_or", 0.0)] + \
        [(f"α = {al}", f"ex_mpcV_blend{al}_30d", float(al)) for al in ("0.25", "0.5", "0.75")] + \
        [("α = 1 (lịch sử, MPC-V)", "batch_2022-11-01_30d_B1_mpc_borrow", 1.0)]
for lab, tag, al in rows5:
    r = g(tag)
    if r and s30 and b30:
        L.append(f"  {lab:28} nMAE phụ tải {al * E1:5.1f}%  chi phí {r['cost']:>11,.0f}  so S1 {pct(r['cost'], s30['cost'])}  so ĐỀ XUẤT {pct(r['cost'], b30['cost'])}  vượt MBA {r['ov']:6.1f} MWh")
    else:
        L.append(f"  {lab:28} (chưa có)")
L.append(f"  Đề xuất (không dự báo)        chi phí {b30['cost']:>11,.0f}" if b30 else "")
L += ["", "GIÁ KHÔNG ĐỦ – stack kém bền (k_run = 8,5 µV/h, mức DOE cho FC ô tô), 2 năm nối tiếp, nhà máy già dần:",
      f"{'':10}{'đoạn':>6}{'D_FC #1589 cuối đoạn':>22}{'Z max #1589':>13}"]
try:
    import pandas as pd
    for w, lab in (("1e6", "chỉ giá"), ("1e10", "hàng đợi")):
        for k in range(4):
            f = RES / f"step3_ex_kr85_wz{w}_c{k}{SUF}" / "timeseries.csv"
            if f.exists():
                df = pd.read_csv(f, index_col=0)
                L.append(f"{lab:10}{k + 1:>6}{df['Dfc_1589'].iloc[-1]:>22.4f}{df['Zfc_1589'].max():>13.4f}")
    L.append("  Giá stack FC × 0,6 (k_run 8,5), 6 tháng:")
    for w, lab in (("1e6", "chỉ giá"), ("1e10", "hàng đợi")):
        f = RES / f"step3_ex_kr85m06_wz{w}_c0{SUF}" / "timeseries.csv"
        if f.exists():
            df = pd.read_csv(f, index_col=0)
            L.append(f"{lab:10}{1:>6}{df['Dfc_1589'].iloc[-1]:>22.4f}{df['Zfc_1589'].max():>13.4f}")
    L.append("  Kế hoạch: D = 0,1 mỗi nửa năm (tuổi thọ 5 năm). Hàng đợi phải giữ D ≤ kế hoạch + Z_max (Z_max đã gồm θ_Z = 0,02; #1589: 0,0357); 'chỉ giá' thì không có bảo đảm.")
except Exception as e:
    L.append(f"  (không đọc được: {e})")
(RES / "extra_summary.txt").write_text("\n".join(L), encoding="utf-8")
print("\n".join(L))
print(f"\nXONG sau {(time.time() - t_all) / 3600:.1f} giờ → results/extra_summary.txt")
