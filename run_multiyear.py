"""
MÔ PHỎNG NHIỀU NĂM (Hệ quả 1–2): lặp 6 tháng dữ liệu thật 10 lần (≈ 5 năm = tuổi thọ mục tiêu của FC), nối tiếp trạng thái giữa các đoạn
(pin, bồn, hàng đợi, mức lão hóa D, bật/tắt). Nhà máy dùng đường hiệu suất trơn tại D thật, bộ điều khiển cập nhật đường cong mỗi ngày (A6)
→ hiệu suất GIẢM DẦN theo lão hóa đúng như ngoài thực tế. So:  S3 (đề xuất)  với  B0 (Lyapunov không tính lão hóa).
Kiểm: (1) D_FC(t) ≤ đường cận δ·t + Z_max ở MỌI thời điểm (Bổ đề 2–3, Mệnh đề 2);  (2) hiệu suất FC ≥ sàn của Hệ quả 2;
      (3) năm nào FC hết tuổi thọ (D = 1);  (4) chi phí từng năm.
Đặt cùng step3_simulate.py BẢN MỚI (có --state_in, --light) trong DATN2026 rồi chạy (TREO MÁY QUA ĐÊM, ~4–6 giờ):
    python run_multiyear.py              # S3 (w_Z = 1e10) 10 đoạn nối tiếp; B0 dùng lại bản đã chạy nếu có (B0 không phụ thuộc w_Z)
    python run_multiyear.py --reuse      # lỡ tắt máy: chạy lại, đoạn nào xong rồi thì bỏ qua (nối tiếp từ đoạn cuối đã xong)
    python run_multiyear.py --only_plot  # chỉ vẽ lại hình/tóm tắt từ các đoạn đã có
Ghi: results/multiyear/summary.txt và fig_multiyear.png
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

import numpy as np
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
OUT = RES / "multiyear"; OUT.mkdir(parents=True, exist_ok=True)
PY = sys.executable
if '"--state_in"' not in (PROJECT_DIR / "step3_simulate.py").read_text(encoding="utf-8", errors="ignore"):
    raise SystemExit("Cần step3_simulate.py BẢN MỚI (có --state_in) trong DATN2026.")

ap = argparse.ArgumentParser()
ap.add_argument("--chunks", type=int, default=10, help="số đoạn 6 tháng (10 ≈ 5 năm)")
ap.add_argument("--days", default="0", help=argparse.SUPPRESS)          # 0 = cả 6 tháng mỗi đoạn; số nhỏ chỉ để thử code
ap.add_argument("--reuse", action="store_true")
ap.add_argument("--only_plot", action="store_true")
ap.add_argument("--wz", default="1e10", help="trọng số hàng đợi sức khỏe của S3 (mặc định 1e10: bảo đảm tuổi thọ chặt)")
args = ap.parse_args()
env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
ap2 = argparse.ArgumentParser(add_help=False); ap2.add_argument("--wz", default="1e10")
WZ = ap2.parse_known_args()[0].wz          # w_Z = 1e10: Z_max ≈ 0,016 → tuổi thọ BẢO ĐẢM ≥ 98% mục tiêu (3e8 chỉ bảo đảm ~50%)
SC = {"S3": ["--wz", WZ, "--V", "1"], "B0": ["--no_aging", "--wz", WZ, "--V", "1"]}
SUF = "" if args.days == "0" else f"_t{args.days}"
# B0 bỏ hẳn lão hóa khỏi hàm mục tiêu → KHÔNG phụ thuộc w_Z. Nếu đã có đủ 10 đoạn B0 của lần chạy trước (bất kỳ w_Z nào) thì dùng lại, khỏi chạy lại.
WZTAG = {"S3": args.wz, "B0": args.wz}
_done = lambda w, sc: all((RES / f"step3_multiyear_wz{w}_{sc}_c{k:02d}{SUF}" / "summary.txt").exists() and
                          (OUT / f"state_wz{w}_{sc}_c{k:02d}{SUF}.json").exists() for k in range(args.chunks))
if not _done(args.wz, "B0"):
    for w in ("3e8", "1e9", "3e9", "1e10", "1e8"):
        if w != args.wz and _done(w, "B0"):
            WZTAG["B0"] = w
            print(f"[*] Dùng lại B0 đã chạy (w_Z = {w}) – B0 không phụ thuộc w_Z, chỉ cần chạy S3", flush=True)
            break
tag = lambda sc, k: f"multiyear_wz{WZTAG[sc]}_{sc}_c{k:02d}{SUF}"
state = lambda sc, k: OUT / f"state_wz{WZTAG[sc]}_{sc}_c{k:02d}{SUF}.json"
summ = lambda sc, k: RES / f"step3_{tag(sc, k)}" / "summary.txt"

if not args.only_plot:
    t_all = time.time()
    nxt = {sc: 0 for sc in SC}
    for sc in SC:
        if args.reuse or WZTAG[sc] != args.wz:
            while nxt[sc] < args.chunks and summ(sc, nxt[sc]).exists() and state(sc, nxt[sc]).exists():
                nxt[sc] += 1
    running = {}
    print(f"[*] {len(SC)} kịch bản × {args.chunks} đoạn nối tiếp; bắt đầu từ đoạn: {nxt}", flush=True)
    while any(nxt[sc] < args.chunks for sc in SC) or running:
        for sc in SC:
            if sc not in running and nxt[sc] < args.chunks:
                k = nxt[sc]
                cmd = [PY, str(PROJECT_DIR / "step3_simulate.py"), "--tag", tag(sc, k), "--days", args.days, "--plant", "--light",
                       "--state_out", str(state(sc, k))] + SC[sc] + (["--state_in", str(state(sc, k - 1))] if k > 0 else [])
                if args.days != "0":
                    cmd += ["--start", "2022-09-01"]
                lf = open(OUT / f"{tag(sc, k)}.log", "w", encoding="utf-8")
                running[sc] = (subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT, env=env), time.time(), lf, k)
                print(f"  bắt đầu {sc} đoạn {k + 1}/{args.chunks}", flush=True)
        time.sleep(10)
        for sc in list(running):
            pr, t0, lf, k = running[sc]
            if pr.poll() is None:
                continue
            lf.close(); del running[sc]
            okk = pr.returncode == 0 and summ(sc, k).exists() and state(sc, k).exists()
            print(f"  {'xong' if okk else 'LỖI (xem results/multiyear/*.log)'} {sc} đoạn {k + 1} sau {(time.time() - t0) / 60:.0f} phút "
                  f"(tổng {(time.time() - t_all) / 60:.0f} phút)", flush=True)
            nxt[sc] = k + 1 if okk else args.chunks          # lỗi thì dừng kịch bản đó

# ------------------------------------------------------------------ phân tích
sys.path.insert(0, str(PROJECT_DIR))
import step3_simulate as S  # noqa: E402

params = json.loads((PROJECT_DIR / "params" / "params_tier1.json").read_text(encoding="utf-8"))
S.apply_fc_calibration(params, Namespace(no_fc_calib=False, no_el_calib=False))
if "fc" not in S.CAL:
    S.CAL["fc"] = S._table(S.FC_X, S.FC_ETA, None, None, None, +1)
H = [int(s["station_id"]) for s in params["stations"] if s.get("has_h2")]
life_h = params["aging_and_devices"]["fc"]["life_target_h"]
X_EVAL = 0.45                                                    # điểm làm việc điển hình của FC khi đỡ lưới
eta_at = lambda D: float(S._pchip("fc", min(max(D, 0.0), 1.0))[0](X_EVAL))

data, zmax, costs, checks = {}, {}, {}, {}
for sc in SC:
    parts, cs, bad = [], [], 0
    for k in range(args.chunks):
        f = RES / f"step3_{tag(sc, k)}" / "timeseries.csv"
        if not f.exists():
            break
        cols = pd.read_csv(f, nrows=0).columns
        use = [cols[0]] + [c for c in cols if c.startswith("Dfc_") or c.startswith("Zfc_") or c == "cost"]
        d = pd.read_csv(f, usecols=use)
        d.index = np.arange(len(d)) + sum(len(p) for p in parts)
        parts.append(d.drop(columns=[cols[0]]))
        s = summ(sc, k).read_text(encoding="utf-8")
        cs.append(float(re.search(r"K2 – chi phí \(gồm giá lão hóa\): ([\d,]+) CNY", s).group(1).replace(",", "")))
        bad += ("KHÔNG ĐẠT" in s) and sc == "S3"
        if sc == "S3" and k == 0:
            for i in H:
                m = re.search(rf"Bổ đề 3 – trạm {i}: max Z_FC = [\d.e+-]+ \(≤ ([\d.e+-]+)", s)
                zmax[i] = float(m.group(1)) if m else float("nan")
    if parts:
        data[sc] = pd.concat(parts); costs[sc] = cs; checks[sc] = bad
if not data:
    raise SystemExit("Chưa có đoạn nào chạy xong.")

DT = S.DT
L = [f"MÔ PHỎNG NHIỀU NĂM – {args.chunks} đoạn × 6 tháng dữ liệu thật (2022-09 → 2023-02 lặp lại), nhà máy già dần, bộ điều khiển cập nhật mỗi ngày",
     f"Tuổi thọ mục tiêu FC {life_h / 8760:.0f} năm → δ = Δt/L; đường cận Mệnh đề 2: D̄(t) = δ·t + Z_max; sàn hiệu suất Hệ quả 2 tại x = {X_EVAL}", ""]
for sc, d in data.items():
    yrs = d.index.to_numpy() * DT / 8760.0
    L.append(f"=== {sc} ({'đề xuất' if sc == 'S3' else 'Lyapunov KHÔNG tính lão hóa'}): {len(costs[sc])} đoạn = {yrs[-1]:.2f} năm; "
             f"chi phí từng năm (CNY, 2 đoạn/năm): " + ", ".join(f"{sum(costs[sc][j:j + 2]):,.0f}" for j in range(0, len(costs[sc]) - 1, 2)))
    for i in H:
        Dp, Dc = d[f"Dfc_phys_{i}"].to_numpy(), d[f"Dfc_{i}"].to_numpy()
        delta = DT / life_h
        bound = delta * np.arange(len(Dc)) + zmax.get(i, np.nan)
        gap = np.nanmax(Dc - bound)
        eol = yrs[np.argmax(Dp >= 1.0)] if (Dp >= 1.0).any() else None
        eta0, etaE = eta_at(0.0), eta_at(Dp[-1])
        floor_ok = all(eta_at(Dp[j]) >= eta_at(bound[j]) - 1e-9 for j in range(0, len(Dp), 288))
        L.append(f"  trạm {i}: D_FC thật cuối kỳ {Dp[-1]:.3f} (D tính {Dc[-1]:.3f}) | max(D tính − đường cận) = {gap:+.4f} → "
                 f"{'ĐẠT (luôn dưới cận)' if gap <= 1e-9 else 'VƯỢT cận'} | hết tuổi thọ (D = 1): "
                 f"{'chưa, sau ' + format(yrs[-1], '.2f') + ' năm' if eol is None else 'năm thứ ' + format(eol, '.2f')} | "
                 f"η_FC({X_EVAL}) {eta0:.3f} → {etaE:.3f}, trên sàn Hệ quả 2: {'ĐẠT' if floor_ok else 'KHÔNG'}")
    if sc == "S3":
        L.append(f"  các kiểm tra lý thuyết trong từng đoạn: {'ĐẠT hết' if checks[sc] == 0 else str(checks[sc]) + ' đoạn có mục KHÔNG ĐẠT'}")
    L.append("")
(OUT / "summary.txt").write_text("\n".join(L), encoding="utf-8")
print("\n".join(L))
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.2))
    colors = dict(zip(H, ["tab:blue", "tab:orange", "tab:green"]))
    for sc, d in data.items():
        yrs = d.index.to_numpy() * DT / 8760.0
        for i in H:
            Dp = d[f"Dfc_phys_{i}"].to_numpy()
            if sc == "B0":                                   # B0: vẽ tới lúc hết tuổi thọ (D = 1), sau đó phải thay stack
                n = int(np.argmax(Dp >= 1.0)) + 1 if (Dp >= 1.0).any() else len(Dp)
                ax[0].plot(yrs[:n], Dp[:n], ls="--", color=colors.get(i), lw=1.2, label=f"B0 trạm {i}")
                if (Dp >= 1.0).any():
                    ax[0].plot(yrs[n - 1], 1.0, "x", color=colors.get(i), ms=7)
                ax[1].plot(yrs[:n:288], [eta_at(v) for v in Dp[:n:288]], ls="--", color=colors.get(i), lw=1.2)
                continue
            ax[0].plot(yrs, Dp, ls="-", color=colors.get(i), lw=1.4, label=f"S3 trạm {i}")
            ax[1].plot(yrs[::288], [eta_at(v) for v in Dp[::288]], ls="-", color=colors.get(i), lw=1.4, label=f"S3 trạm {i}")
            bnd = np.arange(len(Dp)) * DT / life_h + zmax.get(i, np.nan)       # đường cận RIÊNG từng trạm (Mệnh đề 2)
            ax[0].plot(yrs, bnd, ls=":", color=colors.get(i), lw=1.0)
            ax[1].plot(yrs[::288], [eta_at(v) for v in bnd[::288]], ls=":", color=colors.get(i), lw=1.0)
    if "B0" in data and any((data["B0"][f"Dfc_phys_{i}"].to_numpy() >= 1.0).any() for i in H):
        yb = data["B0"].index.to_numpy() * DT / 8760.0
        nrep = [int(np.floor(data["B0"][f"Dfc_phys_{i}"].to_numpy()[-1])) for i in H]
        eols = [yb[np.argmax(data["B0"][f"Dfc_phys_{i}"].to_numpy() >= 1.0)] for i in H if (data["B0"][f"Dfc_phys_{i}"].to_numpy() >= 1.0).any()]
        ax[0].text(0.98, 1.08, f"B0: hết tuổi thọ sau {min(eols):.2f}–{max(eols):.2f} năm → thay stack {min(nrep)}–{max(nrep)} lần / {yb[-1]:.0f} năm"
                   , ha="right", fontsize=7, transform=ax[0].get_yaxis_transform())
    ax[0].plot([], [], ls=":", color="k", lw=1.0, label="đường cận δt + Z_max (từng trạm)")
    ax[1].plot([], [], ls=":", color="k", lw=1.0, label="sàn Hệ quả 2 (từng trạm)")
    ax[0].axhline(1.0, color="r", ls="-", lw=0.8, alpha=0.6); ax[0].set_ylim(0, 1.2)
    ax[0].set_xlabel("năm"); ax[0].set_ylabel("mức lão hóa FC D (1 = hết tuổi thọ)"); ax[0].legend(fontsize=7, ncol=2)
    ax[1].set_xlabel("năm"); ax[1].set_ylabel(f"hiệu suất hệ FC tại x = {X_EVAL}"); ax[1].legend(fontsize=7, loc="lower left")
    ax[0].set_title("(a) Lão hóa FC theo thời gian"); ax[1].set_title("(b) Hiệu suất FC theo thời gian")
    fig.tight_layout(); fig.savefig(OUT / "fig_multiyear.png", dpi=150)
    print(f"\nĐã ghi: {OUT / 'summary.txt'}\n        {OUT / 'fig_multiyear.png'}")
except Exception as e:
    print("Không vẽ được hình:", e)
