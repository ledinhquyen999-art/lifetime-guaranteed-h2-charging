"""
VIỆC 2.4 – KIỂM CHỨNG HỆ QUẢ 2 (sàn hiệu suất hydrogen theo thời gian) trên kết quả mô phỏng.

Không chạy mô phỏng mới: chỉ đọc timeseries.csv của các lần chạy đã có (thường là bộ 6 tháng của việc 2.3).
Đặt cùng thư mục với step3_simulate.py (DATN2026) rồi chạy:
    python check_corollary2.py                                   # mặc định đọc bộ 6 tháng batch_2022-09-01_181d
    python check_corollary2.py --batch batch_2022-11-01_30d       # hoặc bộ khác
    python check_corollary2.py --dirs "S3=h6_S3,B0=h6_B0"         # hoặc chỉ định thư mục results/step3_<tag>

Hệ quả 2 nói gì (viết gọn):
  D̄_t = D_1 + δ·(t−1) + Z_max   (đường lão hóa trên; Mệnh đề 2 ⇒ D_t ≤ D̄_t với MỌI chuỗi dữ liệu)
  hiệu suất giảm khi D tăng ⇒  η_FC(x, D_t) ≥ η_FC(x, D̄_t),   η_EL(x, D_t) ≥ η_EL(x, D̄_t),   η_vòng ≥ hàm của hai sàn.
Cách tính hiệu suất theo D: bảng η(x, D) từ HAI FILE HIỆU CHỈNH (đường phân cực đo thật, dời 0,1·V_định mức·D đúng như mô hình (13)–(14)).
  • Nếu file hiệu chỉnh có bảng "D_grid" (chạy lại calibrate_fc_ieee.py / calibrate_el.py bản mới): sàn lấy ở nút lưới NGAY TRÊN D̄
    → là cận dưới CHẶT về toán (chỉ dùng tính đơn điệu của bảng, script tự kiểm tra tính đơn điệu).
  • Nếu chưa có: nội suy tuyến tính giữa D = 0 và D = 1 (xấp xỉ, có ghi chú trong báo cáo).
Lưu ý mô hình: mô phỏng dùng đường hiệu suất lúc mới (BOL); ở đây ta quy mức lão hóa D_t của từng bước ra hiệu suất mà máy SẼ CÓ
ở mức lão hóa đó. Đây đúng là phát biểu của Hệ quả 2 (một bảo đảm về D, đổi sang đơn vị hiệu suất).

Ghi: DATN2026/results/corollary2_<tên bộ>/summary.txt + 2 hình   ← GỬI summary.txt (và 2 hình) CHO CLAUDE
"""
import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
HERE = Path(__file__).resolve().parent
PROJECT_DIR = Path(__file__).resolve().parent
if not PROJECT_DIR.exists():
    PROJECT_DIR = HERE
RES = PROJECT_DIR / "results"
DT = 5 / 60
LHV = 33.33
H2_ST = ("1093", "1242", "1589")

ap = argparse.ArgumentParser()
ap.add_argument("--batch", default="batch_2022-09-01_181d", help="tên bộ của run_batch.py (thư mục results/step3_<batch>_<kịch bản>)")
ap.add_argument("--dirs", default="", help='chỉ định trực tiếp: "nhãn=tag,nhãn=tag" (đọc results/step3_<tag>)')
ap.add_argument("--years", type=float, default=5.0, help="trục thời gian của hình tuổi thọ")
args = ap.parse_args()

# ------------------------------------------------------------------ các lần chạy
ORDER = ["S3", "B0_noAging", "B1_mpc_life", "B1_mpc_life_or", "B1_mpc", "B1_mpc_oracle", "B2_rule"]
NICE = {"S3": "Đề xuất (S3)", "B0_noAging": "Lyapunov không tính lão hóa (B0)", "B1_mpc": "MPC dự báo lịch sử",
        "B1_mpc_oracle": "MPC biết trước", "B1_mpc_life": "MPC lịch sử + ràng buộc tuổi thọ",
        "B1_mpc_life_or": "MPC biết trước + ràng buộc tuổi thọ", "B2_rule": "Quy tắc cắt đỉnh"}
runs = {}
if args.dirs:
    for kv in args.dirs.split(","):
        k, v = kv.split("=")
        runs[k.strip()] = RES / f"step3_{v.strip()}"
    name = "custom_" + "_".join(runs)
else:
    name = args.batch
    for d in sorted(RES.glob(f"step3_{args.batch}_*")):
        lab = d.name[len(f"step3_{args.batch}_"):]
        if lab != "S1" and (d / "timeseries.csv").exists():
            runs[lab] = d
if not runs:
    raise SystemExit(f"Không thấy kết quả nào cho {args.batch}. Chạy việc 2.3 trước (run_batch.py --days 0 ...).")
ref = next((k for k in runs if k.startswith("S3")), None)
if ref is None:
    raise SystemExit("Cần ít nhất một lần chạy S3 (đề xuất) – Z_max lấy từ đó.")
key = lambda k: (ORDER.index("S3") if k.startswith("S3") else ORDER.index(k) if k in ORDER else 99, k)
runs = dict(sorted(runs.items(), key=lambda kv: key(kv[0])))
nice = lambda k: (NICE["S3"] + (f" {k[2:]}" if k != "S3" else "")) if k.startswith("S3") else NICE.get(k, k)
OUT = RES / f"corollary2_{name}"
OUT.mkdir(parents=True, exist_ok=True)

# ------------------------------------------------------------------ thông số
params = json.loads((PROJECT_DIR / "params" / "params_tier1.json").read_text(encoding="utf-8"))
A = params["aging_and_devices"]
delta = {"fc": DT / A["fc"]["life_target_h"], "el": DT / A["el"]["life_target_h"]}
L_years = {x: A[x]["life_target_h"] / 8760 for x in ("fc", "el")}
e_cp = A["tank"]["e_cp_kWh_per_kg"]
NOTES = []


def load_table(fname, kx, k0, keol, kD):
    f = PROJECT_DIR / "params" / fname
    if not f.exists():
        raise SystemExit(f"Thiếu params/{fname} – chạy bước hiệu chỉnh trước.")
    c = json.loads(f.read_text(encoding="utf-8"))
    X = np.array(c[kx], float)
    if kD in c and "D_grid" in c:
        G = np.array(c["D_grid"], float); T = np.array(c[kD], float); exact = True
    else:
        G = np.array([0.0, 1.0]); T = np.array([c[k0], c[keol]], float); exact = False
        NOTES.append(f"{fname}: chưa có bảng D_grid → nội suy tuyến tính giữa D=0 và D=1 (XẤP XỈ). "
                     f"Chạy lại {'calibrate_fc_ieee.py' if 'fc' in fname else 'calibrate_el.py'} bản mới để có sàn chặt.")
    return X, G, T, exact


FX, FG, FT, f_exact = load_table("fc_calibration.json", "fc_x", "fc_eta_sys", "fc_eta_sys_eol", "fc_eta_sys_D")
EX, EG, ET, e_exact = load_table("el_calibration.json", "el_x", "el_kwh_per_kg", "el_kwh_per_kg_eol", "el_kwh_per_kg_D")
# kiểm tra đơn điệu – điều kiện để sàn là cận dưới đúng
ok_mono_fc = bool(np.all(np.diff(FT, axis=0)[np.isfinite(np.diff(FT, axis=0))] < 0))
ok_mono_el = bool(np.all(np.diff(ET, axis=0)[np.isfinite(np.diff(ET, axis=0))] > 0))


def _row(T, X, x):
    """nội suy theo x cho mọi hàng D (x là mảng)."""
    return np.stack([np.interp(x, X, r) for r in T])          # shape (nD, len(x))


def table_at(T, X, G, x, D):
    """giá trị 'thật' tại (x, D): song tuyến tính; D > 1 → nan (ngoài mô hình, máy đã hết đời)."""
    x = np.clip(np.atleast_1d(np.asarray(x, float)), X[0], X[-1]); D = np.atleast_1d(np.asarray(D, float))
    R = _row(T, X, x)
    k = np.clip(np.searchsorted(G, D, side="right") - 1, 0, len(G) - 2)
    w = (D - G[k]) / (G[k + 1] - G[k])
    n = np.arange(len(x))
    v = (1 - w) * R[k, n] + w * R[k + 1, n]
    return np.where((D >= -1e-12) & (D <= 1 + 1e-12), v, np.nan)


def table_floor(T, X, G, x, Dbar, exact):
    """sàn tại (x, D̄): nút lưới NGAY TRÊN D̄ (cận dưới chặt nhờ đơn điệu); bảng 2 nút → nội suy (xấp xỉ)."""
    if not exact:
        return table_at(T, X, G, x, Dbar)
    x = np.clip(np.atleast_1d(np.asarray(x, float)), X[0], X[-1]); Dbar = np.atleast_1d(np.asarray(Dbar, float))
    R = _row(T, X, x)
    k = np.clip(np.searchsorted(G, Dbar - 1e-12, side="left"), 0, len(G) - 1)
    v = R[k, np.arange(len(x))]
    return np.where(Dbar <= 1 + 1e-12, v, np.nan)


eta_fc = lambda x, D: table_at(FT, FX, FG, x, D)
eta_fc_floor = lambda x, Db: table_floor(FT, FX, FG, x, Db, f_exact)
kwh_el = lambda x, D: table_at(ET, EX, EG, x, D)
kwh_el_ceil = lambda x, Db: table_floor(ET, EX, EG, x, Db, e_exact)          # kWh/kg lớn nhất có thể ⇒ hiệu suất EL thấp nhất
eta_rt = lambda ef, k: ef * LHV / (k + e_cp)                               # điện FC ra / (điện EL + máy nén) cho 1 kg H2

# ------------------------------------------------------------------ Z_max của lần chạy đề xuất
s_ref = (runs[ref] / "summary.txt").read_text(encoding="utf-8")
Zmax = {}
for st in H2_ST:
    m = re.search(rf"\n\s+{st}:.*Z_max\(FC/EL\)=([\d\.]+)/([\d\.]+)", s_ref)
    if not m:
        raise SystemExit(f"Không đọc được Z_max của trạm {st} trong {runs[ref] / 'summary.txt'}")
    Zmax[st] = {"fc": float(m.group(1)) + 5e-5, "el": float(m.group(2)) + 5e-5}   # summary làm tròn 4 số → cộng nửa đơn vị cho chắc
hdr = re.search(r"V = ([\d\.e\+\-]+) \| w_Z = ([\d\.e\+\-]+)", s_ref)

# ------------------------------------------------------------------ đọc chuỗi thời gian
data = {}
for lab, d in runs.items():
    cols = pd.read_csv(d / "timeseries.csv", nrows=0).columns
    want = [cols[0]] + [c for c in cols if any(c == f"{p}_{st}" for st in H2_ST for p in ("Dfc", "Del", "Dfc_phys", "Del_phys", "Pfc", "Pel", "ufc", "uel"))]
    df = pd.read_csv(d / "timeseries.csv", usecols=want, index_col=0, parse_dates=True)
    if not any(c.startswith("Dfc_") for c in df.columns):
        NOTES.append(f"{lab}: timeseries.csv không có cột lão hóa D (bản step5 cũ) → bỏ qua. Chạy lại bằng step5_baselines.py bản mới.")
        continue
    data[lab] = df
P_fc = {}; P_el = {}
for m in re.finditer(r"\n\s+(\d+): PV.*?FC ([\d\.]+) kW, EL ([\d\.]+) kW", s_ref):
    P_fc[m.group(1)], P_el[m.group(1)] = float(m.group(2)), float(m.group(3))

# ------------------------------------------------------------------ kiểm chứng
L = [f"VIỆC 2.4 – KIỂM CHỨNG HỆ QUẢ 2 (sàn hiệu suất H2) – bộ: {name}",
     f"Z_max lấy từ lần chạy đề xuất '{ref}' ({'V = ' + hdr.group(1) + ', w_Z = ' + hdr.group(2) if hdr else ''}); "
     f"δ_FC = Δt/{A['fc']['life_target_h']:.0f} h, δ_EL = Δt/{A['el']['life_target_h']:.0f} h; máy nén {e_cp} kWh/kg; D_1 = 0 (máy mới).",
     f"Bảng hiệu suất theo D: FC {'CHẶT (lưới ' + str(len(FG)) + ' mức D)' if f_exact else 'XẤP XỈ'}, "
     f"EL {'CHẶT (lưới ' + str(len(EG)) + ' mức D)' if e_exact else 'XẤP XỈ'}; đơn điệu theo D: FC {'ĐẠT' if ok_mono_fc else 'KHÔNG ĐẠT'}, EL {'ĐẠT' if ok_mono_el else 'KHÔNG ĐẠT'}"]
L += [f"  ! {n}" for n in NOTES]
L.append("")
L.append("[1] SÀN BẢO ĐẢM (không phụ thuộc dữ liệu) tại điểm định mức x = 1 – dùng được cho mọi thuật toán thỏa Mệnh đề 2 với Z_max này")
L.append(f"    hiệu suất lúc mới: FC {eta_fc(1, 0)[0]:.4f}, EL {LHV / kwh_el(1, 0)[0]:.4f} ({kwh_el(1, 0)[0]:.2f} kWh/kg), vòng H2 {eta_rt(eta_fc(1, 0), kwh_el(1, 0))[0]:.4f}")
for st in H2_ST:
    zf, ze = Zmax[st]["fc"], Zmax[st]["el"]
    L.append(f"  Trạm {st}: Z_max FC = {zf:.4f}, EL = {ze:.4f} → Hệ quả 1: tuổi thọ bảo đảm ≥ FC {L_years['fc'] * (1 - zf):.2f} năm, EL {L_years['el'] * (1 - ze):.2f} năm")
    s = "    năm:            " + "".join(f"{y:>8.1f}" for y in (0, 0.5, 1, 2, 3, 4, 5))
    L.append(s)
    for lab_, fun in (("sàn η_FC  ", lambda y: eta_fc_floor(1, zf + y * 8760 / DT * delta["fc"])[0]),
                      ("sàn η_EL  ", lambda y: LHV / kwh_el_ceil(1, ze + y * 8760 / DT * delta["el"])[0]),
                      ("sàn η_vòng", lambda y: eta_rt(eta_fc_floor(1, zf + y * 8760 / DT * delta["fc"]),
                                                      kwh_el_ceil(1, ze + y * 8760 / DT * delta["el"]))[0])):
        L.append(f"    {lab_}      " + "".join(f"{v:>8.4f}" if np.isfinite(v) else f"{'—':>8}" for v in (fun(y) for y in (0, 0.5, 1, 2, 3, 4, 5))))
L.append("    ('—' = D̄ > 1: sau mốc tuổi thọ bảo đảm của Hệ quả 1, sàn không còn nghĩa – nhất quán với Hệ quả 1)")

L.append("\n[2] KIỂM CHỨNG TRÊN MÔ PHỎNG – mọi bước 5 phút t: D_t ≤ D̄_t ? và hiệu suất ở mức lão hóa D_t có nằm trên sàn không")
L.append("    a) tại điểm định mức x = 1;  b) tại ĐIỂM LÀM VIỆC THẬT x_t = P_t/P_định mức ở các bước máy đang chạy")
L.append(f"    {'lần chạy':<34}{'trạm':>6}{'máy':>5}{'max(D−D̄)':>11}{'D cuối':>9}{'D̄ cuối':>9}{'bước dưới sàn (a)':>19}{'(b)':>9}{'hết đời (D>1)':>16}{'η giảm':>9}")
res = {}
for lab, df in data.items():
    T = len(df); k = np.arange(T)
    for st in H2_ST:
        for x, col, Pcol, Pnom in (("fc", f"Dfc_{st}", f"Pfc_{st}", P_fc.get(st)), ("el", f"Del_{st}", f"Pel_{st}", P_el.get(st))):
            if col not in df:
                continue
            D = df[col].to_numpy(float)
            Dbar = Zmax[st][x] + delta[x] * k                         # D_1 = 0, t−1 = k
            gap = float(np.max(D - Dbar))
            if x == "fc":
                act_r, flo_r = eta_fc(np.ones(T), D), eta_fc_floor(np.ones(T), Dbar)
            else:
                act_r, flo_r = LHV / kwh_el(np.ones(T), D), LHV / kwh_el_ceil(np.ones(T), Dbar)
            valid = np.isfinite(flo_r)
            below_a = int(np.sum(valid & ~(np.nan_to_num(act_r, nan=-1) >= flo_r - 1e-12)))
            on = (df[Pcol].to_numpy(float) > 1e-6) if (Pcol in df and Pnom) else np.zeros(T, bool)
            below_b, n_on = 0, int(on.sum())
            if n_on:
                xo = df[Pcol].to_numpy(float)[on] / Pnom
                if x == "fc":
                    a_b, f_b = eta_fc(xo, D[on]), eta_fc_floor(xo, Dbar[on])
                else:
                    a_b, f_b = LHV / kwh_el(xo, D[on]), LHV / kwh_el_ceil(xo, Dbar[on])
                below_b = int(np.sum(np.isfinite(f_b) & ~(np.nan_to_num(a_b, nan=-1) >= f_b - 1e-12)))
            eol = np.argmax(D > 1) if np.any(D > 1) else None
            eol_txt = f"ngày {eol * DT / 24:.0f}" if eol is not None else "không"
            drop = (act_r[0] - act_r[-1]) if np.isfinite(act_r[-1]) else float("nan")
            res[lab, st, x] = dict(D=D, Dbar=Dbar, act=act_r, flo=flo_r, gap=gap, below_a=below_a, below_b=below_b, n_on=n_on,
                                   eol=eol, rate=D[-1] / (T * DT / 8760) if T else np.nan)
            L.append(f"    {nice(lab)[:33]:<34}{st:>6}{x.upper():>5}{gap:>11.4f}{D[-1]:>9.4f}{Dbar[-1]:>9.4f}"
                     f"{below_a:>13d}/{T:<5d}{below_b:>5d}/{n_on:<5d}{eol_txt:>14}" + (f"{100 * drop:>8.2f}đ" if np.isfinite(drop) else f"{'hết đời':>9}"))
L.append("    max(D−D̄) ≤ 0 nghĩa là Hệ quả 2 ĐÚNG ở mọi bước. 'η giảm' = điểm phần trăm hiệu suất định mức mất đi trong kỳ chạy.")
L.append("    Với các phương pháp khác, D̄ là đường của đề xuất – chúng KHÔNG được bảo đảm nằm dưới đường này (không có hàng đợi sức khỏe).")

verdict = []
for lab in data:
    if lab.startswith("S3"):
        bad = [(st, x) for (l, st, x), r in res.items() if l == lab and (r["gap"] > 1e-9 or r["below_a"] or r["below_b"])]
        verdict.append(f"  {nice(lab)}: Hệ quả 2 {'ĐẠT ở mọi bước, mọi trạm, cả FC và EL' if not bad else 'KHÔNG ĐẠT tại ' + str(bad)}")
    else:
        bad = [(st, x.upper()) for (l, st, x), r in res.items() if l == lab and (r["gap"] > 1e-9)]
        eol = [(st, x.upper(), f"ngày {r['eol'] * DT / 24:.0f}") for (l, st, x), r in res.items() if l == lab and r["eol"] is not None]
        verdict.append(f"  {nice(lab)}: " + ("vượt đường lão hóa trên của đề xuất tại " + ", ".join(f"{a}-{b}" for a, b in bad) if bad
                                            else "nằm dưới đường D̄ trong kỳ này (nhưng KHÔNG có bảo đảm cho chuỗi dữ liệu khác)")
                       + ("; hết đời (D>1) tại " + ", ".join(f"{a}-{b} {c}" for a, b, c in eol) if eol else ""))
L.append("\n[3] KẾT LUẬN")
L += verdict

# ------------------------------------------------------------------ hình 1: trong kỳ chạy
colors = {"S3": "tab:blue", "B0_noAging": "tab:red", "B1_mpc": "tab:orange", "B1_mpc_oracle": "tab:brown",
          "B1_mpc_life": "tab:green", "B1_mpc_life_or": "tab:olive", "B2_rule": "tab:purple"}
col_of = lambda lab: colors["S3"] if lab.startswith("S3") else colors.get(lab, "gray")
fig, ax = plt.subplots(3, 3, figsize=(15, 10), sharex=True)
for r, st in enumerate(H2_ST):
    idx = None
    for lab in data:
        if (lab, st, "fc") not in res:
            continue
        a = res[lab, st, "fc"]; e = res[lab, st, "el"]; idx = data[lab].index
        lw = 2.2 if lab.startswith("S3") else 1.1
        ax[r, 0].plot(idx, 100 * a["act"], c=col_of(lab), lw=lw, label=nice(lab))
        ax[r, 1].plot(idx, 100 * e["act"], c=col_of(lab), lw=lw)
        ax[r, 2].plot(idx, 100 * eta_rt(a["act"], LHV / e["act"]), c=col_of(lab), lw=lw)
        for c_, rr in ((0, a), (1, e)):
            if rr["eol"] is not None:
                ax[r, c_].plot(idx[rr["eol"]], 100 * np.nanmin(rr["act"]), "x", c=col_of(lab), ms=10, mew=2)
    ref_fc, ref_el = res[ref, st, "fc"], res[ref, st, "el"]
    ix = data[ref].index
    plan_fc = eta_fc(np.ones(len(ix)), delta["fc"] * np.arange(len(ix)))
    plan_el = LHV / kwh_el(np.ones(len(ix)), delta["el"] * np.arange(len(ix)))
    ax[r, 0].plot(ix, 100 * ref_fc["flo"], "k-", lw=1.6, label="sàn Hệ quả 2 (D̄ = δt + Z_max)")
    ax[r, 0].plot(ix, 100 * plan_fc, "k:", lw=1.2, label="kế hoạch (D = δt)")
    ax[r, 1].plot(ix, 100 * ref_el["flo"], "k-", lw=1.6); ax[r, 1].plot(ix, 100 * plan_el, "k:", lw=1.2)
    ax[r, 2].plot(ix, 100 * eta_rt(ref_fc["flo"], LHV / ref_el["flo"]), "k-", lw=1.6)
    ax[r, 2].plot(ix, 100 * eta_rt(plan_fc, LHV / plan_el), "k:", lw=1.2)
    ax[r, 0].set_ylabel(f"Trạm {st}\nhiệu suất (%)")
    for c_ in range(3):
        ax[r, c_].grid(alpha=.3)
ax[0, 0].set_title("FC tại công suất định mức"); ax[0, 1].set_title("Điện phân (EL) tại công suất định mức")
ax[0, 2].set_title("Cả chuỗi H2 (điện → H2 → điện, gồm máy nén)")
ax[0, 0].legend(fontsize=7, loc="lower left")
fig.suptitle("Hệ quả 2 – hiệu suất ở mức lão hóa thực tế so với sàn bảo đảm (× = máy hết đời, D > 1)")
fig.autofmt_xdate(); fig.tight_layout(); fig.savefig(OUT / "fig_corollary2_run.png", dpi=150); plt.close(fig)

# ------------------------------------------------------------------ hình 2: cả đời máy (sàn bảo đảm + ngoại suy)
yrs = np.linspace(0, args.years, 600)
steps = yrs * 8760 / DT
fig, ax = plt.subplots(2, 3, figsize=(15, 7.5), sharex=True)
for c_, st in enumerate(H2_ST):
    for r, x in enumerate(("fc", "el")):
        f_act = (lambda D: 100 * eta_fc(np.ones(len(D)), D)) if x == "fc" else (lambda D: 100 * LHV / kwh_el(np.ones(len(D)), D))
        f_flo = (lambda Db: 100 * eta_fc_floor(np.ones(len(Db)), Db)) if x == "fc" else (lambda Db: 100 * LHV / kwh_el_ceil(np.ones(len(Db)), Db))
        Dbar = Zmax[st][x] + delta[x] * steps
        ax[r, c_].plot(yrs, f_flo(Dbar), "k-", lw=1.8, label="sàn bảo đảm (Hệ quả 2)")
        ax[r, c_].plot(yrs, f_act(delta[x] * steps), "k:", lw=1.2, label="kế hoạch (D = δt)")
        ax[r, c_].axvline(L_years[x] * (1 - Zmax[st][x]), c="k", ls="--", lw=.8)
        for lab in data:
            if (lab, st, x) not in res:
                continue
            rr = res[lab, st, x]
            ax[r, c_].plot(yrs, f_act(rr["rate"] * yrs), c=col_of(lab), lw=2.2 if lab.startswith("S3") else 1.1,
                           ls="-" if lab.startswith("S3") else "--", label=nice(lab) + " (ngoại suy)")
        ax[r, c_].set_title(f"Trạm {st} – {'FC' if x == 'fc' else 'EL'}"); ax[r, c_].grid(alpha=.3)
        if c_ == 0:
            ax[r, c_].set_ylabel("hiệu suất định mức (%)")
    ax[1, c_].set_xlabel("năm vận hành")
ax[0, 0].legend(fontsize=7, loc="lower left")
fig.suptitle("Sàn hiệu suất bảo đảm suốt đời máy (đường liền đen) – vạch đứt: tuổi thọ bảo đảm L(1−Z_max) của Hệ quả 1\n"
             "các đường màu: ngoại suy theo tốc độ già trung bình của kỳ mô phỏng (minh họa, không phải bảo đảm)", fontsize=10)
fig.tight_layout(); fig.savefig(OUT / "fig_corollary2_lifetime.png", dpi=150); plt.close(fig)

txt = "\n".join(L)
(OUT / "summary.txt").write_text(txt, encoding="utf-8")
print(txt + f"\n\nĐã ghi: {OUT / 'summary.txt'}\n        {OUT / 'fig_corollary2_run.png'}\n        {OUT / 'fig_corollary2_lifetime.png'}")
