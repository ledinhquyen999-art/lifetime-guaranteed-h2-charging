"""
TÁI TẠO TOÀN BỘ KẾT QUẢ CỦA BÀI với cấu hình đã chốt (S3: w_Z = 1e10, V = 1) – MỘT LỆNH, TREO MÁY QUA ĐÊM.
Mọi con số trong bài báo / đồ án lấy từ file tổng hợp cuối cùng:  results/FINAL_summary.txt

Đặt trong DATN2026 cùng các file BẢN MỚI: step3_simulate.py, step5_baselines.py, run_tradeoff.py, run_batch.py, plot_theorem1.py,
run_battery_compare.py, run_overnight.py, run_voltvar.py, run_mismatch.py, run_admm.py, run_scale.py, run_sens44.py, run_drl.py,
run_multiyear.py, grid33_eval.py, drl_ppo.py  rồi chạy:
    python reproduce_all.py               # ~8–10 giờ; phần nào đã có thì dùng lại (baseline, PPO, S1, nhiều năm...)
    python reproduce_all.py               # lỡ tắt máy: chạy lại đúng lệnh này, giai đoạn nào xong rồi thì bỏ qua
    python reproduce_all.py --only_summary   # chỉ gom lại file tổng hợp từ kết quả đã có
    python reproduce_all.py --stages G,H  # chỉ chạy một số giai đoạn

Nguyên tắc:
  * Mọi lần chạy của ĐỀ XUẤT (S3) dùng w_Z = 1e10 – kết quả mới có hậu tố _wz1e10 / wZ1e10, KHÔNG ghi đè kết quả cũ (3e8).
  * Baseline không phụ thuộc w_Z (S1, B0, quy tắc, MPC ×4, pin lớn, PPO, C*) → dùng lại, không chạy lại.
  * Chi phí so sánh = K2 HIỆU CHỈNH cuối kỳ (trừ năng lượng pin/bồn còn lại so với đầu kỳ, quy theo giá mua TB).
    Kết quả cũ chưa có dòng này thì tính lại từ timeseries.csv (dòng đầu/cuối) – không cần chạy lại.
  * C* (biết trước tương lai) có ràng buộc cuối kỳ ≥ đầu kỳ → so với chi phí HIỆU CHỈNH là công bằng.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from argparse import Namespace
from pathlib import Path

import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
HERE = Path(__file__).resolve().parent
PROJECT_DIR = Path(__file__).resolve().parent
if not PROJECT_DIR.exists():
    PROJECT_DIR = HERE
RES = PROJECT_DIR / "results"
OUT = RES / "reproduce"; OUT.mkdir(parents=True, exist_ok=True)
PY = sys.executable
env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")

ap = argparse.ArgumentParser()
ap.add_argument("--wz", default="1e10")
ap.add_argument("--stages", default="", help="chỉ chạy các giai đoạn này, ví dụ A,B,G (mặc định: tất cả)")
ap.add_argument("--only_summary", action="store_true")
ap.add_argument("--force", action="store_true", help="chạy lại cả giai đoạn đã đánh dấu xong (các runner vẫn dùng lại phần đã có)")
args = ap.parse_args()
WZ = args.wz
SFX = "" if WZ == "3e8" else f"_wz{WZ}"

# (mã, mô tả, lệnh, file tóm tắt của giai đoạn, dùng trong bài/đồ án)
STAGES = [
    ("A", "Đánh đổi chi phí – tuổi thọ bảo đảm (30 ngày quét w_Z, V; 6 tháng 3e8/1e9/3e9/1e10)",
     ["run_tradeoff.py", "--reuse"], "tradeoff_summary.txt"),
    ("B", "So sánh với baseline – 30 ngày (S1, B0, quy tắc, MPC ×4)",
     ["run_batch.py", "--days", "30", "--wz", WZ, "--all", "--reuse", "--jobs", "2"], "batch_2022-11-01_30d/compare.txt"),
    ("C", "Định lý 1 – quét V (7 ngày) so với C*",
     ["run_batch.py", "--days", "7", "--wz", WZ, "--V", "0.1,0.25,0.5,1", "--no_s1", "--reuse", "--jobs", "2"], None),
    ("C2", "Định lý 1 – hình và bảng", ["plot_theorem1.py", "--wz", WZ], f"theorem1_2022-11-01_7d{SFX}/summary.txt"),
    ("D", "H2 so với pin lớn hơn – 30 ngày, không bán H2",
     ["run_battery_compare.py", "--days", "30", "--start", "2022-11-01", "--wz", WZ, "--jobs", "2"],
     f"battery_compare_2022-11-01_30d{SFX}/summary.txt"),
    ("E", "Lưới 33 nút (6 tháng + quét c_v 30 ngày) và bán H2 cho FCEV",
     ["run_overnight.py", "--wz", WZ, "--reuse", "--jobs", "2"], f"overnight_summary{SFX}.txt"),
    ("F", "Volt–var (6 tháng)", ["run_voltvar.py", "--wz", WZ, "--reuse"], f"voltvar_summary{SFX}.txt"),
    ("G", "Sai lệch mô hình M1–M9 (30 ngày) + M1 6 tháng", ["run_mismatch.py", "--wz", WZ, "--reuse"], f"mismatch_summary{SFX}.txt"),
    ("H", "ADMM phân tán (7 ngày)", ["run_admm.py", "--wz", WZ, "--reuse"], f"admm_summary{SFX}.txt"),
    ("I", "Mở rộng 20/35/50 điểm sạc", ["run_scale.py", "--wz", WZ, "--reuse"], f"scale_summary{SFX}.txt"),
    ("J", "Độ nhạy giả định (giá thiết bị, chia sẻ, pin, MBA, PV)", ["run_sens44.py", "--wz", WZ, "--reuse"], f"sens44_summary{SFX}.txt"),
    ("K", "DRL (PPO) so với đề xuất không chia sẻ", ["run_drl.py", "--wz", WZ, "--reuse", "--jobs", "2"], f"drl_summary{SFX}.txt"),
    ("L", "Mô phỏng 5 năm (Hệ quả 1–2)", ["run_multiyear.py", "--wz", WZ, "--reuse"], "multiyear/summary.txt"),
]
need = sorted({c[0] for _, _, c, _ in STAGES} | {"step3_simulate.py", "step5_baselines.py", "grid33_eval.py", "drl_ppo.py"})
miss = [f for f in need if not (PROJECT_DIR / f).exists()]
if miss:
    raise SystemExit(f"Thiếu trong DATN2026: {miss}")
if '"--wz"' not in (PROJECT_DIR / "run_sens44.py").read_text(encoding="utf-8", errors="ignore"):
    raise SystemExit("Các file run_*.py trong DATN2026 còn là BẢN CŨ (chưa có --wz) – chép đè bản mới rồi chạy lại.")

sel = [s.strip() for s in args.stages.split(",") if s.strip()]
t_all = time.time()
status = {}
if not args.only_summary:
    for code, desc, cmd, _ in STAGES:
        if sel and code not in sel and code.rstrip("2") not in sel:
            continue
        mark = OUT / f"stage_{code}{SFX}.done"
        if mark.exists() and not args.force:
            print(f"[{code}] đã xong trước đó – bỏ qua ({desc})", flush=True)
            status[code] = "xong (lần trước)"
            continue
        print(f"\n[{code}] {desc}\n    {' '.join(cmd)}   (log: results/reproduce/stage_{code}.log)", flush=True)
        t0 = time.time()
        with open(OUT / f"stage_{code}.log", "w", encoding="utf-8") as lf:
            pr = subprocess.Popen([PY, str(PROJECT_DIR / cmd[0])] + cmd[1:], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  env=env, cwd=str(PROJECT_DIR), text=True, encoding="utf-8", errors="replace")
            for line in pr.stdout:                       # ghi log đầy đủ, in ra màn hình các dòng tiến độ
                lf.write(line); lf.flush()
                if any(k in line for k in ("bắt đầu", "xong", "LỖI", "Lỗi", "Traceback", "Error")):
                    print("    " + line.rstrip()[:160], flush=True)
            pr.wait()
        ok = pr.returncode == 0
        status[code] = f"{'xong' if ok else 'LỖI'} sau {(time.time() - t0) / 60:.0f} phút"
        print(f"[{code}] {status[code]} (tổng {(time.time() - t_all) / 3600:.1f} giờ)", flush=True)
        if ok:
            mark.write_text(time.strftime("%Y-%m-%d %H:%M"), encoding="utf-8")

# ====================================================================== TỔNG HỢP
sys.path.insert(0, str(PROJECT_DIR))
import step3_simulate as S  # noqa: E402

params = json.loads((PROJECT_DIR / "params" / "params_tier1.json").read_text(encoding="utf-8"))
S.apply_fc_calibration(params, Namespace(no_fc_calib=False, no_el_calib=False))
ALLIN = pd.read_csv(PROJECT_DIR / "data_clean" / "tier1_inputs.csv", index_col=0, parse_dates=True)
PCOL = [c for c in ALLIN.columns if c.startswith("price_")]
_ST = {}


def num(pat, s):
    m = re.search(pat, s)
    return float(m.group(1).replace(",", "")) if m else float("nan")


def stations(t0, t1):
    key = (t0, t1)
    if key not in _ST:
        ev = ALLIN.loc[t0:t1]
        st, _ = S.prepare(params, ev, 1.0, 1e10, pv_scale=2.0, export_frac=0.0, V_REF=1.0, tr_frac=0.6, no_h2=False)
        _ST[key] = (st, float(ev[PCOL].to_numpy().mean()))
    return _ST[key]


def result(tag):
    """Chỉ số của một lần chạy (7 trạm thật). cost = K2 hiệu chỉnh cuối kỳ (tính lại từ timeseries nếu summary chưa có)."""
    d = RES / f"step3_{tag}"
    f = d / "summary.txt"
    if not f.exists():
        return None
    s = f.read_text(encoding="utf-8")
    raw = num(r"K2 – chi phí \(gồm giá lão hóa\): ([\d,]+) CNY", s)
    cor = num(r"K2 hiệu chỉnh cuối kỳ: ([\d,]+) CNY", s)
    how = "summary"
    if cor != cor and (d / "timeseries.csv").exists():
        cols = pd.read_csv(d / "timeseries.csv", nrows=0).columns
        use = [cols[0]] + [c for c in cols if c.startswith("E_") or c.startswith("M_")]
        ts = pd.read_csv(d / "timeseries.csv", usecols=use, index_col=0, parse_dates=True)
        st, pb = stations(ts.index[0], ts.index[-1])
        vE = sum((ts[f"E_{i}"].iloc[-1] - ts[f"E_{i}"].iloc[0]) * st[i]["eta_dis"] for i in st if f"E_{i}" in ts)
        vM = sum((ts[f"M_{i}"].iloc[-1] - ts[f"M_{i}"].iloc[0]) * st[i]["eta_peak"] * S.LHV for i in st if f"M_{i}" in ts)
        cor, how = raw - pb * (vE + vM), "timeseries"          # mức cuối lấy ở bước cuối cùng (lệch ≤ 1 bước 5 phút, < 0,01%)
    lf = [float(x) for x in re.findall(r"tuổi thọ dự kiến theo tốc độ kỳ này: FC ([\d.]+|inf) năm", s)]
    zm = [float(x) for x in re.findall(r"Bổ đề 3 – trạm \d+: max Z_FC = [\d.e+-]+ \(≤ ([\d.e+-]+)", s)]
    return dict(raw=raw, cost=cor if cor == cor else raw, how=how, ov=num(r"vượt giới hạn MBA ([\d.]+) MWh", s),
                life=min(lf) if lf else float("nan"), zmax=max(zm) if zm else float("nan"),
                theory=("không có bảo đảm" if "BƯỚC 5" in s else ("ĐẠT hết" if "KHÔNG ĐẠT" not in s else f"{s.count('KHÔNG ĐẠT')} mục KHÔNG ĐẠT")),
                t=num(r"Thời gian giải: TB ([\d.]+) s/bước", s))


def cstar(name):
    f = RES / name / "cstar.json"
    if not f.exists():
        return None
    j = json.loads(f.read_text(encoding="utf-8"))
    return j.get("lower_bound") or j["C_star"], j["C_star"], j.get("mode", "?")


L_TARGET = params["aging_and_devices"]["fc"]["life_target_h"] / 8760
B30, B6 = "batch_2022-11-01_30d", "batch_2022-09-01_181d"
L = ["=" * 118, f"TỔNG HỢP CUỐI CÙNG – cấu hình chính S3: w_Z = {WZ}, V = 1 – tạo lúc {time.strftime('%Y-%m-%d %H:%M')}", "=" * 118, ""]
if status:
    L += ["Trạng thái các giai đoạn lần chạy này: " + "; ".join(f"{k}: {v}" for k, v in status.items()), ""]

# ---------------- Bảng 1: so sánh chính 30 ngày
cs = cstar("cstar_2022-11-01_30d")
L += ["BẢNG 1 – SO SÁNH CHÍNH, 30 ngày từ 2022-11-01 (7 trạm thật, 3 trạm có H2). Chi phí = K2 hiệu chỉnh cuối kỳ.",
      (f"C* (biết trước tương lai, {cs[2]}): ≥ {cs[0]:,.0f} CNY (cận dưới), lời giải tốt nhất {cs[1]:,.0f} CNY → khoảng cách tính theo cận dưới (bảo thủ)"
       if cs else "C* 30 ngày: chưa có results/cstar_2022-11-01_30d/cstar.json"), "",
      f"{'phương pháp':36}{'chi phí CNY':>13}{'(K2 thô)':>12}{'so S1':>8}{'cách C*':>9}{'vượt MBA MWh':>14}{'so S1':>8}{'FC ≥ năm':>10}  lý thuyết"]
ROWS1 = [("S1 – không H2", f"{B30}_S1"), (f"S3 – ĐỀ XUẤT (w_Z = {WZ})", f"{B30}_S3_wZ{WZ}"),
         ("S3 – w_Z = 3e8 (ưu tiên chi phí)", f"{B30}_S3_wZ3e8"), ("B0 – Lyapunov không tính lão hóa", f"{B30}_B0_noAging"),
         ("B2 – quy tắc", f"{B30}_B2_rule"), ("B1 – MPC 24 h (dự báo)", f"{B30}_B1_mpc"), ("B1* – MPC 24 h biết trước", f"{B30}_B1_mpc_oracle"),
         ("B1L – MPC + ràng buộc tuổi thọ", f"{B30}_B1_mpc_life"), ("B1L* – MPC biết trước + tuổi thọ", f"{B30}_B1_mpc_life_or")]
s1 = result(f"{B30}_S1")
for lab, tag in ROWS1:
    r = result(tag)
    if not r:
        L.append(f"{lab:36}  (chưa có: step3_{tag})"); continue
    vs = f"{100 * (r['cost'] / s1['cost'] - 1):+7.1f}%" if s1 else "     —"
    ov = f"{100 * (r['ov'] / s1['ov'] - 1):+7.1f}%" if s1 and lab[:2] != "S1" else "     —"
    gap = f"{100 * (r['cost'] / cs[0] - 1):+8.1f}%" if cs else "      —"
    L.append(f"{lab:36}{r['cost']:>13,.0f}{r['raw']:>12,.0f}{vs:>8}{gap:>9}{r['ov']:>14.1f}{ov:>8}{r['life']:>10.1f}  {r['theory']}"
             + ("  [hiệu chỉnh tính từ timeseries]" if r["how"] == "timeseries" else ""))
L += ["  'FC ≥ năm' = tuổi thọ FC thấp nhất trong 3 trạm theo tốc độ già của kỳ; mục tiêu 5 năm.", ""]

# ---------------- Bảng 2: giá của bảo đảm (6 tháng)
L += [f"BẢNG 2 – GIÁ CỦA BẢO ĐẢM TUỔI THỌ, 6 tháng 2022-09 → 2023-02 (Hệ quả 1: FC bảo đảm ≥ {L_TARGET:.0f}·(1 − Z_max) năm cho MỌI chuỗi dữ liệu)", "",
      f"{'cấu hình':26}{'chi phí CNY':>13}{'so S1':>8}{'vượt MBA MWh':>14}{'so S1':>8}{'Z_max':>9}{'FC BẢO ĐẢM ≥':>14}{'FC quan sát':>13}  lý thuyết"]
s16 = result(f"{B6}_S1")
for w in ["S1", "3e8", "1e9", "3e9", "1e10"]:
    r = s16 if w == "S1" else result(f"{B6}_S3_wZ{w}")
    lab = "S1 – không H2" if w == "S1" else f"S3, w_Z = {w}" + ("  ← CHÍNH" if w == WZ else "")
    if not r:
        L.append(f"{lab:26}  (chưa có)"); continue
    if w == "S1":
        L.append(f"{lab:26}{r['cost']:>13,.0f}{'—':>8}{r['ov']:>14.1f}{'—':>8}"); continue
    L.append(f"{lab:26}{r['cost']:>13,.0f}{100 * (r['cost'] / s16['cost'] - 1):>+7.1f}%{r['ov']:>14.1f}{100 * (r['ov'] / s16['ov'] - 1):>+7.1f}%"
             f"{r['zmax']:>9.4f}{L_TARGET * (1 - r['zmax']):>11.2f} năm{r['life']:>9.1f} năm  {r['theory']}")
L.append("")

# ---------------- kiểm tra lý thuyết trên MỌI lần chạy S3 mới
bad = []
for d in sorted(RES.glob("step3_*")):
    if not (d / "summary.txt").exists() or not (f"wZ{WZ}" in d.name or d.name.endswith(SFX) or f"{SFX}_" in d.name):
        continue
    s = (d / "summary.txt").read_text(encoding="utf-8")
    if "--no_aging" in s or "B0" in d.name or "BƯỚC 5" in s:
        continue
    if "KHÔNG ĐẠT" in s:
        bad.append(f"{d.name}: " + "; ".join(x.strip()[:110] for x in s.splitlines() if "KHÔNG ĐẠT" in x)[:400])
n_new = sum(1 for d in RES.glob("step3_*") if (d / "summary.txt").exists() and (f"wZ{WZ}" in d.name or SFX in d.name))
L += [f"KIỂM TRA LÝ THUYẾT trên {n_new} lần chạy dùng w_Z = {WZ} (mọi bổ đề, mệnh đề, hệ quả in trong từng summary): "
      + ("ĐẠT HẾT" if not bad else f"{len(bad)} lần chạy có mục KHÔNG ĐẠT (mục M8/M9 là đối chứng cố ý, xem phần sai lệch mô hình):")]
L += ["  " + b for b in bad] + [""]

# ---------------- các tóm tắt chi tiết
for code, desc, _, fsum in STAGES:
    if not fsum:
        continue
    f = RES / fsum
    L += ["#" * 118, f"[{code}] {desc}   ← results/{fsum}", "#" * 118,
          f.read_text(encoding="utf-8").rstrip() if f.exists() else "(chưa có – xem results/reproduce/stage_" + code + ".log)", ""]
(RES / "FINAL_summary.txt").write_text("\n".join(L), encoding="utf-8")
print("\n".join(L[:45]))
print(f"\nXONG sau {(time.time() - t_all) / 3600:.1f} giờ. Gửi Claude: {RES / 'FINAL_summary.txt'}  (và results/multiyear/fig_multiyear.png)")
