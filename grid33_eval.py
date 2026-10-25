"""
VIỆC 3.3–3.4 – ĐÁNH GIÁ TRÊN LƯỚI PHÂN PHỐI IEEE 33 NÚT (Baran & Wu 1989, bản pandapower case33bw).

Gắn 7 trạm sạc vào 7 nút của lưới 12,66 kV, cộng phụ tải nền của lưới, rồi giải TRÀO LƯU CÔNG SUẤT AC
(quét ngược–xuôi cho lưới hình tia, chạy cùng lúc mọi bước 5 phút) cho từng kịch bản đã mô phỏng.
Kiểm chứng: so với pandapower.runpp ở vài thời điểm (sai số điện áp in trong báo cáo).

Đặt trong DATN2026 rồi chạy (cần: pip install pandapower):
    python grid33_eval.py                                   # mặc định: bộ 6 tháng batch_2022-09-01_181d
    python grid33_eval.py --batch batch_2022-11-01_30d      # bộ khác
    python grid33_eval.py --ev_scale 0.5                    # độ nhạy: trạm sạc nhỏ hơn so với lưới

GIẢ ĐỊNH (ghi trong bài):
  • Vị trí trạm: trạm lớn ở cuối nhánh (yếu nhất): 1589→nút 17, 1242→32, 1093→24, 1214→21; trạm nhỏ: 1061→8, 1087→13, 1229→29.
  • Phụ tải nền: tải danh định case33bw (3,715 MW) × base_scale × dạng ngày dân cư (đỉnh 19–20 h). Mặc định base_scale = 0,55
    → không có trạm sạc thì điện áp thấp nhất 0,954 pu lúc cao điểm (lưới đủ, chưa vi phạm): mọi vi phạm là DO TRẠM SẠC.
  • Trạm sạc × ev_scale = 0,35 (mặc định): tổng đỉnh 7 trạm ≈ 1,5 MW ≈ 40% tải danh định của lưới.
  • Trạm sạc: công suất lấy từ lưới = trflow (luồng qua MBA của trạm) trong kết quả mô phỏng, hệ số công suất 0,98.
  • Giới hạn: điện áp [0,95 ; 1,05] pu; tải đường dây so với dòng ở tải thiết kế danh định của lưới (100% = dòng lúc tải danh định, không trạm sạc).
Ghi: results/grid33_<bộ>/summary.txt + fig_grid33.png
"""
import argparse
import json
import re
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

warnings.filterwarnings("ignore")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
try:
    import pandapower as pp
    import pandapower.networks as pn
except ImportError:
    raise SystemExit("Cần cài: python -m pip install pandapower")

HERE = Path(__file__).resolve().parent
PROJECT_DIR = Path(__file__).resolve().parent
if not PROJECT_DIR.exists():
    PROJECT_DIR = HERE
RES = PROJECT_DIR / "results"
DT = 5 / 60
BUS_OF = {1589: 17, 1242: 32, 1093: 24, 1214: 21, 1061: 8, 1087: 13, 1229: 29}
BASE_SHAPE = [0.55, 0.50, 0.47, 0.45, 0.45, 0.48, 0.55, 0.65, 0.72, 0.75, 0.78, 0.80,
              0.80, 0.78, 0.78, 0.80, 0.85, 0.92, 1.00, 1.00, 0.97, 0.90, 0.78, 0.65]   # dạng ngày dân cư (giả định)
ORDER = ["S1", "S3", "S1_grid", "S3_grid", "S1_vv", "S3_vv", "S3_vv_gated", "B0_noAging", "B2_rule", "B1_mpc", "B1_mpc_oracle", "B1_mpc_life", "B1_mpc_life_or"]
NICE = {"S1": "Không H2 (S1)", "S3": "Đề xuất (S3)", "S1_grid": "Không H2, có tính lưới", "S3_grid": "Đề xuất, có tính lưới", "S1_vv": "Không H2, lưới + volt–var", "S3_vv": "Đề xuất, lưới + volt–var", "S3_vv_gated": "Đề xuất, volt–var, FC chỉ khi chạy", "B0_noAging": "Lyapunov không lão hóa", "B2_rule": "Quy tắc",
        "B1_mpc": "MPC lịch sử", "B1_mpc_oracle": "MPC biết trước", "B1_mpc_life": "MPC lịch sử + tuổi thọ",
        "B1_mpc_life_or": "MPC biết trước + tuổi thọ"}

ap = argparse.ArgumentParser()
ap.add_argument("--batch", default="batch_2022-09-01_181d")
ap.add_argument("--s3", default="S3_wZ1e10", help="trong bộ --batch, lần chạy nào là 'Đề xuất (S3)' (tránh lấy nhầm w_Z khác)")
ap.add_argument("--dirs", default="", help='hoặc chỉ định: "nhãn=tag,nhãn=tag" (results/step3_<tag>)')
ap.add_argument("--add", default="", help='thêm vào bộ --batch: "nhãn=tag,..." (ví dụ các lần chạy có tính lưới)')
ap.add_argument("--name", default="", help="tên thư mục kết quả (mặc định theo --batch)")
ap.add_argument("--base_scale", type=float, default=0.55, help="phụ tải nền = tải danh định × hệ số này × dạng ngày (0,55: không trạm sạc thì V ≥ 0,954 pu)")
ap.add_argument("--ev_scale", type=float, default=0.35, help="nhân công suất trạm sạc khi gắn vào lưới (phải giống step3 --ev_scale)")
ap.add_argument("--pf", type=float, default=0.98, help="hệ số công suất trạm sạc")
ap.add_argument("--vmin", type=float, default=0.95)
args = ap.parse_args()

# ------------------------------------------------------------------ lưới
net = pn.case33bw()
nb = len(net.bus)
lines = net.line[net.line.in_service].copy()
Vbase = net.bus.vn_kv.iloc[0] * 1e3
Sbase = 1e6
Zb = Vbase ** 2 / Sbase
z = ((lines.r_ohm_per_km + 1j * lines.x_ohm_per_km) * lines.length_km).to_numpy() / Zb
fb, tb = lines.from_bus.to_numpy(), lines.to_bus.to_numpy()
parent = -np.ones(nb, int); zpar = np.zeros(nb, complex)
for f, t_, zz in zip(fb, tb, z):
    parent[t_] = f; zpar[t_] = zz
depth = np.zeros(nb, int)
for b in range(1, nb):
    k, dd = b, 0
    while parent[k] >= 0:
        k = parent[k]; dd += 1
    depth[b] = dd
order = np.argsort(-depth)                    # lá trước, gốc sau
P0 = np.zeros(nb); Q0 = np.zeros(nb)
for _, r in net.load.iterrows():
    P0[int(r.bus)] += r.p_mw; Q0[int(r.bus)] += r.q_mvar


def bfs(P, Q, iters=30, tol=1e-9):
    """Quét ngược–xuôi cho lưới hình tia. P, Q: (nb, T) MW, MVAr (tải dương). Trả về V (pu, phức) và dòng nhánh (pu)."""
    S = (P + 1j * Q)
    V = np.ones_like(S)
    for _ in range(iters):
        I = np.conj(S / V)
        J = I.copy()
        for b in order:                       # cộng dồn dòng từ lá về gốc
            if parent[b] > 0:
                J[parent[b]] += J[b]
        Vn = V.copy(); Vn[0] = 1.0
        for b in np.argsort(depth):           # đi từ gốc ra lá
            if b > 0:
                Vn[b] = Vn[parent[b]] - zpar[b] * J[b]
        if np.max(np.abs(Vn - V)) < tol:
            V = Vn; break
        V = Vn
    I = np.conj(S / V); J = I.copy()
    for b in order:
        if parent[b] > 0:
            J[parent[b]] += J[b]
    return V, J                               # J[b] = dòng trên nhánh (parent[b] → b)


# kiểm chứng với pandapower ở tải danh định
Vt, _ = bfs(P0[:, None], Q0[:, None])
pp.runpp(net, numba=False)
err_val = float(np.max(np.abs(np.abs(Vt[:, 0]) - net.res_bus.vm_pu.to_numpy())))
# dòng thiết kế của mỗi nhánh = dòng lúc tải danh định (không có trạm sạc)
_, Jn = bfs(P0[:, None], Q0[:, None]); I_design = np.abs(Jn[:, 0]); I_design[0] = np.nan

# ------------------------------------------------------------------ kịch bản
runs = {}
if args.dirs:
    for kv in args.dirs.split(","):
        k, v = kv.split("="); runs[k.strip()] = RES / f"step3_{v.strip()}"
    name = "custom"
else:
    name = args.batch
    for d in sorted(RES.glob(f"step3_{args.batch}_*")):
        lab = d.name[len(f"step3_{args.batch}_"):]
        if lab.startswith("S3_") and "_V" not in lab and "dem" not in lab:
            if lab != args.s3:
                continue                       # bộ có nhiều w_Z: chỉ lấy đúng cấu hình chính
            lab = "S3"
        lab = lab + "_grid" if args.batch.endswith("_grid") and not lab.endswith("_grid") else lab
        if (d / "timeseries.csv").exists() and (lab in ORDER):
            runs[lab] = d
for kv in [x for x in args.add.split(",") if x.strip()]:
    k, v = kv.split("="); runs[k.strip()] = RES / f"step3_{v.strip()}"
if args.name:
    name = args.name
if not runs:
    raise SystemExit(f"Không thấy kết quả cho {args.batch}.")
runs = dict(sorted(runs.items(), key=lambda kv: ORDER.index(kv[0]) if kv[0] in ORDER else 99))
sfx = "" if (args.ev_scale == 0.35 and args.base_scale == 0.55) else f"_ev{args.ev_scale:g}_base{args.base_scale:g}"
OUT = RES / f"grid33_{name}{sfx}"
OUT.mkdir(parents=True, exist_ok=True)
tanphi = np.tan(np.arccos(args.pf))

res, prof = {}, {}
for lab, d in runs.items():
    t0 = time.time()
    cols = pd.read_csv(d / "timeseries.csv", nrows=0).columns
    use = [cols[0]] + [c for c in cols if c.startswith("trflow_") or c.startswith("q_")]
    df = pd.read_csv(d / "timeseries.csv", usecols=use, index_col=0, parse_dates=True)
    qcols = [c for c in df.columns if c.startswith("q_")]
    dq = df[qcols].copy(); df = df[[c for c in df.columns if c.startswith("trflow_")]]
    T = len(df)
    shape = np.array(BASE_SHAPE)[df.index.hour.to_numpy()]
    P = np.outer(P0, shape) * args.base_scale
    Q = np.outer(Q0, shape) * args.base_scale
    for c in df.columns:
        st = int(c.split("_")[1]); b = BUS_OF[st]
        p = df[c].to_numpy() / 1000.0 * args.ev_scale            # MW
        P[b] += p; Q[b] += np.maximum(p, 0) * tanphi
        if f"q_{st}" in dq:                                       # volt–var: Q bộ biến đổi phát lên lưới
            Q[b] -= dq[f"q_{st}"].to_numpy() / 1000.0 * args.ev_scale
    V, J = bfs(P, Q)
    Vm = np.abs(V)
    vmin_t = Vm.min(axis=0)
    under = Vm < args.vmin
    load_pct = 100 * np.abs(J[1:]) / I_design[1:, None]
    loss = np.real(np.sum(np.abs(J[1:]) ** 2 * np.real(zpar[1:, None]), axis=0)) * Sbase / 1e6      # MW
    feeder = np.real(V[0] * np.conj(J[np.where(parent == 0)[0]].sum(axis=0)))                          # MW từ trạm biến áp nguồn
    res[lab] = dict(T=T, vmin=float(vmin_t.min()), h_under=float(under.any(axis=0).sum() * DT),
                    bus_h_under=float(under.sum() * DT), vdef=float(np.maximum(args.vmin - Vm, 0).sum() * DT),
                    h_under93=float((Vm < 0.93).any(axis=0).sum() * DT),
                    load_max=float(np.nanmax(load_pct)), h_over=float((load_pct > 100).any(axis=0).sum() * DT),
                    loss_mwh=float(loss.sum() * DT), feeder_peak=float(feeder.max()), sec=time.time() - t0)
    prof[lab] = pd.Series(vmin_t, index=df.index)
    print(f"  {lab}: {T} bước, {time.time() - t0:.1f} s", flush=True)

# kiểm chứng thêm: một thời điểm nặng nhất của S1 so với pandapower
chk = ""
if "S1" in runs:
    lab = "S1"; d = runs[lab]
    cols = pd.read_csv(d / "timeseries.csv", nrows=0).columns
    df = pd.read_csv(d / "timeseries.csv", usecols=[cols[0]] + [c for c in cols if c.startswith("trflow_")], index_col=0, parse_dates=True)
    k = int(np.argmin(prof[lab].to_numpy()))
    h = df.index[k].hour
    net2 = pn.case33bw()
    net2.load.p_mw *= args.base_scale * BASE_SHAPE[h]; net2.load.q_mvar *= args.base_scale * BASE_SHAPE[h]
    for c in df.columns:
        st = int(c.split("_")[1]); p = df[c].iloc[k] / 1000 * args.ev_scale
        pp.create_load(net2, BUS_OF[st], p_mw=p, q_mvar=max(p, 0) * tanphi)
    pp.runpp(net2, numba=False)
    chk = f"; lúc nặng nhất của S1 ({df.index[k]}): V_min tự giải {prof[lab].iloc[k]:.4f} so với pandapower {net2.res_bus.vm_pu.min():.4f}"

base = res.get("S1")
L = [f"VIỆC 3.3–3.4 – LƯỚI IEEE 33 NÚT – bộ {name} | phụ tải nền × {args.base_scale:g}, trạm sạc × {args.ev_scale:g}, cosφ = {args.pf:g}",
     f"Kiểm chứng bộ giải trào lưu: sai số điện áp so với pandapower ở tải danh định = {err_val:.1e} pu{chk}",
     "Vị trí trạm: " + ", ".join(f"{k}→nút {v}" for k, v in BUS_OF.items()), "",
     f"{'kịch bản':<26}{'V thấp nhất':>12}{'giờ có nút <0,95':>18}{'nút·giờ <0,95':>15}{'giờ <0,93':>11}{'thiếu áp ∑':>12}"
     f"{'tải dây max':>12}{'giờ quá tải dây':>16}{'tổn thất MWh':>14}{'đỉnh nguồn MW':>15}",
     f"{'':<26}{'(pu)':>12}{'':>18}{'':>15}{'':>11}{'(pu·h)':>12}{'(%)':>12}{'':>16}{'':>14}{'':>15}"]
for lab, r in res.items():
    L.append(f"{NICE.get(lab, lab):<26}{r['vmin']:>12.4f}{r['h_under']:>18.1f}{r['bus_h_under']:>15.1f}{r['h_under93']:>11.1f}{r['vdef']:>12.2f}"
             f"{r['load_max']:>12.0f}{r['h_over']:>16.1f}{r['loss_mwh']:>14.1f}{r['feeder_peak']:>15.2f}")
if base:
    L.append("\nSO VỚI KHÔNG H2 (S1):")
    for lab, r in res.items():
        if lab == "S1":
            continue
        f = lambda k: 100 * (1 - r[k] / base[k]) if base[k] > 0 else float("nan")
        L.append(f"  {NICE.get(lab, lab):<26} giờ thiếu áp giảm {f('h_under'):5.1f}% | thiếu áp ∑ giảm {f('vdef'):5.1f}% | "
                 f"giờ quá tải dây giảm {f('h_over'):5.1f}% | tổn thất giảm {f('loss_mwh'):5.1f}%")
L += ["", "Ghi chú: kịch bản tên có \"_grid\" = bộ điều khiển CÓ tính điện áp lưới (step3 --grid33, LinDistFlow); còn lại chỉ giữ giới hạn MBA từng trạm.",
      "Đánh giá ở đây là trào lưu AC đầy đủ (chính xác hơn LinDistFlow mà bộ điều khiển dùng)."]
txt = "\n".join(L)
(OUT / "summary.txt").write_text(txt, encoding="utf-8")
pd.DataFrame(prof).to_csv(OUT / "vmin_profiles.csv", float_format="%.5f")     # cho make_figures.py (điện áp thấp nhất mỗi bước)
(OUT / "metrics.json").write_text(json.dumps({NICE.get(k, k): v for k, v in res.items()} | {"_labels": {k: NICE.get(k, k) for k in res}},
                                             ensure_ascii=False, indent=1), encoding="utf-8")

fig, ax = plt.subplots(1, 2, figsize=(13, 4.3))
for lab, s in prof.items():
    hp = s.groupby(s.index.hour).mean()
    ax[0].plot(hp.index, hp.values, lw=2.2 if lab == "S3" else 1.2, label=NICE.get(lab, lab))
    v = np.sort(s.to_numpy())
    ax[1].plot(v, np.arange(1, len(v) + 1) / len(v), lw=2.2 if lab == "S3" else 1.2, label=NICE.get(lab, lab))
ax[0].axhline(args.vmin, c="k", ls=":"); ax[0].set_xlabel("giờ trong ngày"); ax[0].set_ylabel("điện áp thấp nhất trên lưới (pu), TB theo giờ")
ax[0].set_title("(a) Điện áp thấp nhất theo giờ"); ax[0].grid(alpha=.3); ax[0].legend(fontsize=7)
ax[1].axvline(args.vmin, c="k", ls=":"); ax[1].set_xlabel("điện áp thấp nhất trên lưới (pu)"); ax[1].set_ylabel("tỉ lệ thời gian ≤ giá trị")
ax[1].set_title("(b) Phân bố điện áp thấp nhất"); ax[1].grid(alpha=.3)
fig.suptitle(f"Lưới IEEE 33 nút – {name}"); fig.tight_layout(); fig.savefig(OUT / "fig_grid33.png", dpi=150); plt.close(fig)
print("\n" + txt + f"\n\nĐã ghi: {OUT / 'summary.txt'}\n        {OUT / 'fig_grid33.png'}")
