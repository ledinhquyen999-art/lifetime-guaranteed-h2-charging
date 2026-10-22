"""
BƯỚC 5 – Các phương pháp SO SÁNH (baseline) cho bài:
  --method rule : QUY TẮC ĐƠN GIẢN (rule-based) – cách vận hành "kỹ sư hay làm", không tối ưu
  --method mpc  : MPC (điều khiển dự báo) – mỗi giờ giải bài toán 24 giờ tới bằng DỰ BÁO, áp dụng giờ đầu, lặp lại
                   Dự báo: phụ tải = trung bình cùng giờ 7 ngày trước; PV = cùng giờ hôm qua; giá điện = biết trước (biểu giá).
                   Lão hóa được tính bằng GIÁ (μ·ΔD) trong hàm mục tiêu, như các MPC có tính lão hóa trong tài liệu;
                   thêm --mpc_life để có ràng buộc cứng ngân sách tuổi thọ. Có lớp điều chỉnh 5 phút khi sắp vượt MBA.

Cùng dữ liệu, cùng thiết bị (đã hiệu chỉnh FC/EL), cùng mô hình "vật lý" 5 phút, cùng cách tính chi phí và tuổi thọ như step3.
Đặt cùng thư mục với step3_simulate.py (DATN2026) rồi chạy:
    python step5_baselines.py --method rule --days 30
    python step5_baselines.py --method mpc  --days 30        (lâu hơn: ~720 bài toán MILP nhỏ, khoảng 15–60 phút)
Ghi: DATN2026/results/step3_<tag>/summary.txt   (cùng định dạng chỉ số với step3 để run_batch so sánh được)
"""
import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyomo.environ as pyo

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def _load_step3():
    here = Path(__file__).resolve().parent
    proj = Path(__file__).resolve().parent
    for d in (here, proj, Path.cwd()):
        for p in sorted(d.glob("step3_simulate*.py"), key=lambda p: p.stat().st_mtime, reverse=True) if d.exists() else []:
            if '"--h2_scale"' in p.read_text(encoding="utf-8", errors="ignore"):
                spec = importlib.util.spec_from_file_location("step3_simulate", p)
                mod = importlib.util.module_from_spec(spec); sys.modules["step3_simulate"] = mod; spec.loader.exec_module(mod)
                return mod
    raise SystemExit("Cần step3_simulate.py BẢN MỚI (có --h2_scale) trong DATN2026.")


s3 = _load_step3()
ap = argparse.ArgumentParser()
ap.add_argument("--method", required=True, choices=["rule", "mpc"])
ap.add_argument("--days", type=int, default=7)
ap.add_argument("--start", default="2022-11-01")
ap.add_argument("--tag", default=None)
ap.add_argument("--pv_scale", type=float, default=2.0)
ap.add_argument("--tr_frac", type=float, default=0.6)
ap.add_argument("--c_ov", type=float, default=5.0)
ap.add_argument("--export_frac", type=float, default=0.0)
ap.add_argument("--h2_scale", type=float, default=1.0)
ap.add_argument("--el_a0", type=float, default=None)
ap.add_argument("--no_fc_calib", action="store_true")
ap.add_argument("--no_el_calib", action="store_true")
ap.add_argument("--horizon", type=int, default=24, help="MPC: số giờ nhìn trước")
ap.add_argument("--mpc_gap", type=float, default=0.01)
ap.add_argument("--peak_margin", type=float, default=0.5, help="MPC: chừa bao nhiêu phần biên độ đỉnh 5 phút (0 = theo trung bình giờ, 1 = theo đỉnh)")
ap.add_argument("--oracle", action="store_true", help="MPC biết trước phụ tải và PV thật (dự báo hoàn hảo) – cận trên của MPC")
ap.add_argument("--mpc_life", action="store_true", help="MPC: thêm ràng buộc cứng ngân sách tuổi thọ (mặc định: chỉ có giá lão hóa μ·ΔD trong hàm mục tiêu, như MPC có tính lão hóa trong tài liệu)")
ap.add_argument("--mpc_time", type=float, default=20.0, help="giây tối đa mỗi lần giải MPC")
# các tham số dưới chỉ để giống chữ ký step3 khi run_batch truyền vào (không dùng)
ap.add_argument("--wz", type=float, default=1e10); ap.add_argument("--V", type=float, default=1.0)
args = ap.parse_args()

PROJECT_DIR, DT = s3.PROJECT_DIR, s3.DT
STEPS_H = int(round(1 / DT))                                   # 12 bước 5 phút / giờ
params = json.loads((PROJECT_DIR / "params" / "params_tier1.json").read_text(encoding="utf-8"))
s3.apply_fc_calibration(params, args)
if args.h2_scale != 1.0:
    for s_ in params["stations"]:
        if s_.get("has_h2"):
            for k in ("fc_kW", "el_kW", "tank_kg"):
                s_[k] *= args.h2_scale
if args.el_a0 is not None:
    params["aging_and_devices"]["el"]["a0_uV_per_h"] = args.el_a0
s3.C_OV = args.c_ov
ALL = pd.read_csv(PROJECT_DIR / "data_clean" / "tier1_inputs.csv", index_col=0, parse_dates=True)
if args.days > 0:
    t0 = pd.Timestamp(args.start)
    inputs = ALL.loc[t0: t0 + pd.Timedelta(days=args.days) - pd.Timedelta(minutes=5)]
else:                                                              # --days 0 = toàn bộ dữ liệu (giống step3)
    inputs = ALL
T = len(inputs)
st, c_max = s3.prepare(params, inputs, 1.0, 1e10, args.pv_scale, args.export_frac, 1.0, args.tr_frac, False)
I = sorted(st); H = [i for i in I if st[i]["h2"]]
pairs = [(a, b) for k, a in enumerate(I) for b in I[k + 1:]]
tag = args.tag or f"{'B2_rule' if args.method == 'rule' else ('B1_mpc_oracle' if args.oracle else 'B1_mpc')}_{args.start}_{args.days}d"
out = PROJECT_DIR / "results" / f"step3_{tag}"; out.mkdir(parents=True, exist_ok=True)
print(f"[*] {s3.FC_CALIB_NOTE}\n[*] Phương pháp: {args.method.upper()} | {T} bước | kết quả: {out}")


# ============================================================== mô hình vật lý 5 phút (dùng chung)
def h2_mass(segs, P, on):
    if not on or P <= 1e-9:
        return 0.0
    for lo, hi, sl, ic in segs:
        if P <= hi + 1e-9:
            return sl * max(P, lo) + ic
    lo, hi, sl, ic = segs[-1]
    return sl * hi + ic


def clamp_device(d, P, kind):
    lo = d[f"{kind}_seg"][0][0]; hi = d[f"P_{kind}"]
    if P < lo - 1e-9:
        return 0.0, 0
    return min(P, hi), 1


state = {"E": {i: st[i]["theta_B"] for i in I}, "M": {i: st[i]["theta_H"] for i in H},
         "ufp": {i: 0 for i in H}, "uep": {i: 0 for i in H}, "Pfp": {i: 0.0 for i in H},
         "Dfc": {i: 0.0 for i in H}, "Del": {i: 0.0 for i in H}}
rows = []


def apply_step(t, r, cmd):
    """cmd[i] = dict(fc, el, ch, dis, share_out). Thực thi 1 bước 5 phút với số liệu THẬT; trả về các đại lượng."""
    row = {"time": inputs.index[t]}; cost = 0.0
    cs = min(s3.C_FIT, min(float(r[f"price_{j}"]) for j in I))
    for i in I:
        d = st[i]; c = cmd[i]
        load = float(r[f"load_{i}"]); pv_av = float(r["pv_kw_per_kwp"]) * d["pv_kWp"]; cb = float(r[f"price_{i}"])
        E = state["E"][i]
        ch = min(max(c.get("ch", 0.0), 0.0), d["P_bat"], max(0.0, (d["E_max"] - E) / (d["eta_ch"] * DT)))
        dis = min(max(c.get("dis", 0.0), 0.0), d["P_bat"], max(0.0, (E - d["E_min"]) * d["eta_dis"] / DT))
        if ch > 0 and dis > 0:
            ch, dis = (ch - dis, 0.0) if ch > dis else (0.0, dis - ch)
        Pf = Pe = mf = me = Pcp = 0.0; ufc = uel = 0
        if d["h2"]:
            M = state["M"][i]
            Pf, ufc = clamp_device(d, c.get("fc", 0.0), "fc")
            mf = h2_mass(d["fc_seg"], Pf, ufc)
            if ufc and M - mf < d["M_min"]:                      # an toàn bồn (S2)
                Pf, ufc, mf = 0.0, 0, 0.0
            Pe, uel = clamp_device(d, c.get("el", 0.0), "el")
            me = h2_mass(d["el_seg"], Pe, uel)
            if uel and M - mf + me > d["M_max"]:                 # an toàn bồn (S3)
                Pe, uel, me = 0.0, 0, 0.0
            Pcp = s3.E_CP * me / DT
        so = c.get("share_out", 0.0)
        net = load + ch + Pe + Pcp + so - dis - Pf
        pv = min(pv_av, max(net, 0.0))
        buy = max(net - pv_av, 0.0); sell = 0.0
        trflow = buy - sell - so
        ov = max(trflow - d["P_tr"], 0.0)
        ci = (cb * buy - cs * sell + s3.C_OV * ov + s3.C_BAT * (ch + dis)) * DT
        state["E"][i] = E + (d["eta_ch"] * ch - dis / d["eta_dis"]) * DT
        row.update({f"load_{i}": load, f"pvav_{i}": pv_av, f"pv_{i}": pv, f"buy_{i}": buy, f"sell_{i}": sell, f"ov_{i}": ov,
                    f"trflow_{i}": trflow, f"ch_{i}": ch, f"dis_{i}": dis, f"E_{i}": E})
        if d["h2"]:
            ufp, uep, Pfp = state["ufp"][i], state["uep"][i], state["Pfp"][i]
            dDf = (d["fc_k_start"] * ufc * (1 - ufp) + d["fc_k_lc"] * (abs(Pf - Pfp) if ufc and ufp else 0.0)
                   + d["fc_k_lo"] * (1 if ufc and Pf < d["P_lo"] else 0) + d["fc_k_hp"] * max(0.0, (Pf - d["P_hi"]) / (d["P_fc"] - d["P_hi"])) * ufc)
            dDe = d["el_k_start"] * uel * (1 - uep) + d["el_k_a0"] * uel
            ci += d["mu_fc"] * dDf + d["mu_el"] * dDe
            row.update({f"ufc_{i}": ufc, f"uel_{i}": uel, f"Pfc_{i}": Pf, f"Pel_{i}": Pe, f"Pcp_{i}": Pcp, f"mfc_{i}": mf, f"mel_{i}": me,
                        f"M_{i}": state["M"][i], f"Dfc_{i}": state["Dfc"][i], f"Del_{i}": state["Del"][i]})
            state["M"][i] += me - mf; state["Dfc"][i] += dDf; state["Del"][i] += dDe
            state["ufp"][i], state["uep"][i], state["Pfp"][i] = ufc, uel, Pf
        cost += ci
    row["cost"] = cost
    rows.append(row)


# ============================================================== B2: QUY TẮC ĐƠN GIẢN
def rule_controller():
    fc_level = {i: 0.0 for i in H}; el_level = {i: 0.0 for i in H}; hold = {i: 0 for i in H}
    for t, (ts, r) in enumerate(inputs.iterrows()):
        prices = [float(r[f"price_{i}"]) for i in I]
        cmd = {}
        for i in I:
            d = st[i]; load = float(r[f"load_{i}"]); pv = float(r["pv_kw_per_kwp"]) * d["pv_kWp"]
            price = float(r[f"price_{i}"]); pmin, pmax = ALL[f"price_{i}"].min(), ALL[f"price_{i}"].max()
            valley, peak = price <= pmin + 1e-6, price >= pmax - 1e-6
            c = {"ch": 0.0, "dis": 0.0, "fc": 0.0, "el": 0.0}
            resid = load - pv                                            # >0: thiếu, <0: thừa PV
            E = state["E"][i]
            dis_av = min(d["P_bat"], max(0.0, (E - d["E_min"]) * d["eta_dis"] / DT))     # pin còn xả được bao nhiêu
            ch_av = min(d["P_bat"], max(0.0, (d["E_max"] - E) / (d["eta_ch"] * DT)))     # còn sạc được bao nhiêu
            # 1) Pin – ƯU TIÊN CẮT ĐỈNH (cách vận hành phổ biến ở trạm sạc có lưới nghẽn):
            #    xả CHỈ khi sắp vượt MBA; sạc bằng PV thừa, hoặc từ lưới khi MBA còn nhiều chỗ (< 70%) và không phải giờ cao điểm
            if resid > d["P_tr"]:
                c["dis"] = min(resid - d["P_tr"], dis_av); resid -= c["dis"]
            elif resid < 0:
                c["ch"] = min(-resid, ch_av); resid += c["ch"]
            elif not peak and resid < 0.7 * d["P_tr"]:
                c["ch"] = min(ch_av, 0.7 * d["P_tr"] - resid); resid += c["ch"]
            if d["h2"]:
                M = state["M"][i]
                el_lo, fc_lo = d["el_seg"][0][0], d["fc_seg"][0][0]
                # 2) EL: quyết định theo từng GIỜ (giữ nguyên công suất cả giờ, tránh bật/tắt liên tục):
                #    chạy bằng PV còn thừa, hoặc ngoài giờ cao điểm khi MBA còn chỗ (< 80%); dừng khi bồn ≥ 90%
                if t % STEPS_H == 0:
                    lvl = 0.0
                    if M < d["M_min"] + 0.9 * (d["M_max"] - d["M_min"]):
                        if -resid >= el_lo:
                            lvl = min(d["P_el"], -resid)
                        elif not peak and 0.8 * d["P_tr"] - resid >= el_lo:
                            lvl = min(d["P_el"], 0.8 * d["P_tr"] - resid)
                    el_level[i] = lvl
                c["el"] = el_level[i]
                # 3) FC: bật khi sắp vượt MBA, công suất làm tròn lên bậc 25% định mức và GIỮ ít nhất 1 giờ
                need = resid + c["el"] - d["P_tr"]
                if need > 0 and M > d["M_min"] + 2 * d["m_fc_max"] and (hold[i] == 0 or need > fc_level[i]):
                    step_ = 0.25 * d["P_fc"]
                    fc_level[i] = min(d["P_fc"], max(fc_lo, np.ceil(need / step_) * step_)); hold[i] = STEPS_H
                elif hold[i] > 0:
                    hold[i] -= 1
                else:
                    fc_level[i] = 0.0
                c["fc"] = fc_level[i]
            cmd[i] = c
        apply_step(t, r, cmd)
        if (t + 1) % 288 == 0:
            print(f"  ngày {(t + 1) // 288}", flush=True)


# ============================================================== B1: MPC (giờ, 24 h tới)
def segs_hourly(xs, ys, Pbar, kind):
    """Đoạn tuyến tính cho bước 1 giờ: kg/giờ theo kW."""
    ms = [x * Pbar * 1.0 / (eta * s3.LHV) for x, eta in zip(xs, ys)] if kind == "fc" else [x * Pbar * 1.0 / k for x, k in zip(xs, ys)]
    return s3.pwl(xs, ms, Pbar)


n_fail = [0]


def rt_adjust(i, r, p):
    """Lớp điều chỉnh thời gian thực của MPC (5 phút, số liệu thật): kế hoạch giờ không thấy được đỉnh 5 phút,
    nên khi sắp vượt MBA thì xả thêm pin → tăng FC (nếu đang bật, không bật thêm) → giảm EL; khi thừa PV thì sạc thêm."""
    d = st[i]; q = dict(p)
    load = float(r[f"load_{i}"]); pv = float(r["pv_kw_per_kwp"]) * d["pv_kWp"]; E = state["E"][i]
    dis_av = min(d["P_bat"], max(0.0, (E - d["E_min"]) * d["eta_dis"] / DT))
    ch_av = min(d["P_bat"], max(0.0, (d["E_max"] - E) / (d["eta_ch"] * DT)))
    el_extra = q.get("el", 0.0) * (1 + s3.E_CP / 50.0)               # EL + máy nén (xấp xỉ)
    imp = load - pv + q.get("ch", 0.0) - q.get("dis", 0.0) + el_extra - q.get("fc", 0.0)   # luồng qua MBA (không gồm phần chia sẻ, giống step3)
    over = imp - d["P_tr"]
    if over > 0:
        cut = min(over, q.get("ch", 0.0)); q["ch"] = q.get("ch", 0.0) - cut; over -= cut
        add = min(over, max(0.0, dis_av - q.get("dis", 0.0))); q["dis"] = q.get("dis", 0.0) + add; over -= add
        if d["h2"] and q.get("fc", 0.0) > 0:
            add = min(over, d["P_fc"] - q["fc"]); q["fc"] += add; over -= add
        if d["h2"] and over > 0 and q.get("el", 0.0) > 0:
            q["el"] = 0.0
    elif imp < 0:
        cut = min(-imp, q.get("dis", 0.0)); q["dis"] = q.get("dis", 0.0) - cut; imp += cut
        add = min(-imp, max(0.0, ch_av - q.get("ch", 0.0))); q["ch"] = q.get("ch", 0.0) + add
    q["_need"] = load - pv + q.get("ch", 0.0) - q.get("dis", 0.0) + q.get("el", 0.0) * (1 + s3.E_CP / 50.0) - q.get("fc", 0.0)
    return q


def rt_share(qs):
    """Chia sẻ thời gian thực: trạm nhận chỉ nhận tối đa phần nó thực sự cần; trạm gửi giảm theo cùng tỉ lệ (luôn cân bằng)."""
    recv = {i: min(-q["share_out"], max(0.0, q["_need"])) for i, q in qs.items() if q.get("share_out", 0.0) < 0}
    send = {i: q["share_out"] for i, q in qs.items() if q.get("share_out", 0.0) > 0}
    tot_r, tot_s = sum(recv.values()), sum(send.values())
    k = min(1.0, tot_r / tot_s) if tot_s > 1e-9 else 0.0
    if tot_s > 1e-9 and tot_r > tot_s:
        recv = {i: v * tot_s / tot_r for i, v in recv.items()}
    for i, q in qs.items():
        q["share_out"] = send[i] * k if i in send else (-recv[i] if i in recv else 0.0)
        q.pop("_need", None)
    return qs


def mpc_controller():
    N = args.horizon
    HF = {i: segs_hourly(s3.FC_X, s3.FC_ETA, st[i]["P_fc"], "fc") for i in H}
    HE = {i: segs_hourly(s3.EL_X, s3.EL_KWHKG, st[i]["P_el"], "el") for i in H}
    hourly = ALL.resample("1h").mean()
    hourly_pk = ALL[[f"load_{i}" for i in I]].resample("1h").max()          # đỉnh 5 phút trong mỗi giờ
    solver = pyo.SolverFactory("appsi_highs")
    solver.config.time_limit = args.mpc_time; solver.config.mip_gap = args.mpc_gap; solver.config.load_solution = True
    solve_times = []
    t = 0
    n_fail[0] = 0
    while t < T:
        now = inputs.index[t]
        hrs = pd.date_range(now.floor("1h"), periods=N, freq="1h")
        # dự báo
        Lh, Lpk, PVh, Ch = {}, {}, {}, {}
        for k, h in enumerate(hrs):
            past = [h - pd.Timedelta(days=dd) for dd in range(1, 8)]
            for i in I:
                if args.oracle:     # dự báo HOÀN HẢO (biết trước phụ tải/PV thật) – cận trên của MPC
                    Lh[k, i] = float(hourly[f"load_{i}"].get(h, np.nan)); Lpk[k, i] = float(hourly_pk[f"load_{i}"].get(h, np.nan))
                else:
                    Lh[k, i] = float(np.nanmean([hourly[f"load_{i}"].get(p, np.nan) for p in past]))
                    Lpk[k, i] = float(np.nanmean([hourly_pk[f"load_{i}"].get(p, np.nan) for p in past]))
                if not np.isfinite(Lh[k, i]):
                    # chưa có lịch sử (những ngày đầu dữ liệu): chỉ dùng số liệu ĐÃ BIẾT tới lúc này (không nhìn trước)
                    seen = ALL[f"load_{i}"].loc[:now]
                    Lh[k, i] = float(seen.mean()); Lpk[k, i] = float(seen.max())
                Ch[k, i] = float(hourly[f"price_{i}"].get(h, hourly[f"price_{i}"].get(h - pd.Timedelta(days=1), 1.0)))
            PVh[k] = float(hourly["pv_kw_per_kwp"].get(h if args.oracle else h - pd.Timedelta(days=1), 0.0))
        m = pyo.ConcreteModel()
        K = range(N)
        m.buy = pyo.Var(K, I, within=pyo.NonNegativeReals); m.ov = pyo.Var(K, I, within=pyo.NonNegativeReals)
        m.pv = pyo.Var(K, I, within=pyo.NonNegativeReals)
        m.ch = pyo.Var(K, I, bounds=lambda m, k, i: (0, st[i]["P_bat"])); m.dis = pyo.Var(K, I, bounds=lambda m, k, i: (0, st[i]["P_bat"]))
        m.E = pyo.Var(range(N + 1), I, bounds=lambda m, k, i: (st[i]["E_min"], st[i]["E_max"]))
        m.g = pyo.Var(K, pairs, bounds=(-s3.P_SHARE, s3.P_SHARE))
        m.c = pyo.ConstraintList()
        obj = 0
        for i in I:
            d = st[i]
            m.c.add(m.E[0, i] == state["E"][i])
            m.c.add(m.E[N, i] >= min(state["E"][i], d["theta_B"]))
        if H:
            m.ufc = pyo.Var(K, H, within=pyo.Binary); m.uel = pyo.Var(K, H, within=pyo.Binary)
            m.sfc = pyo.Var(K, H, bounds=(0, 1)); m.sel = pyo.Var(K, H, bounds=(0, 1))
            SF = [(i, s) for i in H for s in range(len(HF[i]))]; SE = [(i, s) for i in H for s in range(len(HE[i]))]
            m.yf = pyo.Var(K, SF, within=pyo.Binary); m.pf = pyo.Var(K, SF, within=pyo.NonNegativeReals)
            m.ye = pyo.Var(K, SE, within=pyo.Binary); m.pe = pyo.Var(K, SE, within=pyo.NonNegativeReals)
            m.dP = pyo.Var(K, H, within=pyo.NonNegativeReals); m.zlo = pyo.Var(K, H, within=pyo.Binary); m.hp = pyo.Var(K, H, bounds=(0, 1))
            m.M = pyo.Var(range(N + 1), H, bounds=lambda m, k, i: (st[i]["M_min"], st[i]["M_max"]))
        Pf = lambda k, i: sum(m.pf[k, i, s] for s in range(len(HF[i])))
        Pe = lambda k, i: sum(m.pe[k, i, s] for s in range(len(HE[i])))
        mf = lambda k, i: sum(HF[i][s][2] * m.pf[k, i, s] + HF[i][s][3] * m.yf[k, i, s] for s in range(len(HF[i])))
        me = lambda k, i: sum(HE[i][s][2] * m.pe[k, i, s] + HE[i][s][3] * m.ye[k, i, s] for s in range(len(HE[i])))
        for i in H:
            d = st[i]
            m.c.add(m.M[0, i] == state["M"][i]); m.c.add(m.M[N, i] >= min(state["M"][i], d["theta_H"]))
            dDf_sum = dDe_sum = 0
            for k in K:
                m.c.add(sum(m.yf[k, i, s] for s in range(len(HF[i]))) == m.ufc[k, i])
                m.c.add(sum(m.ye[k, i, s] for s in range(len(HE[i]))) == m.uel[k, i])
                for s in range(len(HF[i])):
                    m.c.add(m.pf[k, i, s] >= HF[i][s][0] * m.yf[k, i, s]); m.c.add(m.pf[k, i, s] <= HF[i][s][1] * m.yf[k, i, s])
                for s in range(len(HE[i])):
                    m.c.add(m.pe[k, i, s] >= HE[i][s][0] * m.ye[k, i, s]); m.c.add(m.pe[k, i, s] <= HE[i][s][1] * m.ye[k, i, s])
                up = m.ufc[k - 1, i] if k else state["ufp"][i]; upe = m.uel[k - 1, i] if k else state["uep"][i]
                Pprev = Pf(k - 1, i) if k else state["Pfp"][i]
                m.c.add(m.sfc[k, i] >= m.ufc[k, i] - up); m.c.add(m.sel[k, i] >= m.uel[k, i] - upe)
                BM = d["P_fc"]
                m.c.add(m.dP[k, i] >= Pf(k, i) - Pprev - BM * (1 - m.ufc[k, i]) - BM * (1 - up))
                m.c.add(m.dP[k, i] >= Pprev - Pf(k, i) - BM * (1 - m.ufc[k, i]) - BM * (1 - up))
                m.c.add(m.zlo[k, i] <= m.ufc[k, i]); m.c.add(Pf(k, i) >= d["P_lo"] * (m.ufc[k, i] - m.zlo[k, i]))
                m.c.add(m.hp[k, i] >= (Pf(k, i) - d["P_hi"]) / (d["P_fc"] - d["P_hi"]))
                m.c.add(m.M[k + 1, i] == m.M[k, i] + me(k, i) - mf(k, i))
                dDf = (d["fc_k_start"] * m.sfc[k, i] + d["fc_k_lc"] * m.dP[k, i]
                       + STEPS_H * (d["fc_k_lo"] * m.zlo[k, i] + d["fc_k_hp"] * m.hp[k, i]))
                dDe = d["el_k_start"] * m.sel[k, i] + STEPS_H * d["el_k_a0"] * m.uel[k, i]
                dDf_sum += dDf; dDe_sum += dDe
                obj += d["mu_fc"] * dDf + d["mu_el"] * dDe
            # tuổi thọ: lão hóa 24 h tới ≤ ngân sách còn lại đến cuối tầm nhìn
            if args.mpc_life:   # tùy chọn: ràng buộc cứng ngân sách tuổi thọ (không cho "vay trước" như hàng đợi Z)
                m.c.add(dDf_sum <= max(0.0, d["delta_fc"] * (t + N * STEPS_H) - state["Dfc"][i]))
                m.c.add(dDe_sum <= max(0.0, d["delta_el"] * (t + N * STEPS_H) - state["Del"][i]))
        for k in K:
            cs = min(s3.C_FIT, min(Ch[k, j] for j in I))
            for i in I:
                d = st[i]
                so = sum(m.g[k, a, b] for (a, b) in pairs if a == i) - sum(m.g[k, a, b] for (a, b) in pairs if b == i)
                fcP = Pf(k, i) if i in H else 0.0
                elP = (Pe(k, i) + s3.E_CP * me(k, i)) if i in H else 0.0       # hourly: kg/h × kWh/kg = kW
                m.c.add(m.pv[k, i] <= PVh[k] * d["pv_kWp"])
                m.c.add(m.pv[k, i] + m.buy[k, i] + m.dis[k, i] + fcP == Lh[k, i] + m.ch[k, i] + elP + so)
                # MBA: ràng buộc theo ĐỈNH 5 phút dự báo trong giờ (kế hoạch giờ phải chừa chỗ cho đỉnh)
                m.c.add(m.buy[k, i] + args.peak_margin * max(0.0, Lpk[k, i] - Lh[k, i]) - so <= d["P_tr"] + m.ov[k, i])
                m.c.add(m.E[k + 1, i] == m.E[k, i] + d["eta_ch"] * m.ch[k, i] - m.dis[k, i] / d["eta_dis"])
                obj += Ch[k, i] * m.buy[k, i] + s3.C_OV * m.ov[k, i] + s3.C_BAT * (m.ch[k, i] + m.dis[k, i])
        m.obj = pyo.Objective(expr=obj, sense=pyo.minimize)
        s0 = time.time()
        try:
            solver.solve(m); okk = True
        except Exception as e:                       # không tìm được lời giải trong thời gian cho phép → giữ an toàn (tắt H2, không sạc/xả)
            okk = False; n_fail[0] += 1
        solve_times.append(time.time() - s0)
        # áp dụng kế hoạch giờ đầu cho 12 bước 5 phút
        plan = {}
        for i in I:
            if okk:
                p = {"ch": pyo.value(m.ch[0, i]), "dis": pyo.value(m.dis[0, i]),
                     "share_out": sum(pyo.value(m.g[0, a, b]) for (a, b) in pairs if a == i) - sum(pyo.value(m.g[0, a, b]) for (a, b) in pairs if b == i)}
                if i in H:
                    p["fc"] = pyo.value(Pf(0, i)) if round(pyo.value(m.ufc[0, i])) else 0.0
                    p["el"] = pyo.value(Pe(0, i)) if round(pyo.value(m.uel[0, i])) else 0.0
            else:
                p = {"ch": 0.0, "dis": 0.0, "share_out": 0.0, "fc": 0.0, "el": 0.0}
            plan[i] = p
        tot_so = sum(plan[i]["share_out"] for i in I)                        # chia sẻ phải cân bằng
        for i in I:
            plan[i]["share_out"] -= tot_so / len(I)
        for _ in range(STEPS_H):
            if t >= T:
                break
            r = inputs.iloc[t]
            apply_step(t, r, rt_share({i: rt_adjust(i, r, plan[i]) for i in I}))
            t += 1
        if t % 288 == 0:
            print(f"  ngày {t // 288}: giải TB {np.mean(solve_times):.1f} s/lần", flush=True)
    return solve_times


# ============================================================== chạy + báo cáo (cùng định dạng chỉ số với step3)
tic = time.time()
solve_times = mpc_controller() if args.method == "mpc" else (rule_controller() or [0.0])
df = pd.DataFrame(rows).set_index("time")
df.round(6).to_csv(out / "timeseries.csv")
name = ("B1 – MPC 24 h, DỰ BÁO HOÀN HẢO" if args.oracle else "B1 – MPC 24 h, dự báo theo lịch sử") if args.method == "mpc" else "B2 – QUY TẮC ĐƠN GIẢN"
L = [f"BƯỚC 5 – {name} – {T} bước ({T * DT / 24:.1f} ngày) từ {df.index[0]} | PV ×{args.pv_scale:g} | MBA = {args.tr_frac:g}×đỉnh | phạt vượt {args.c_ov:g} CNY/kWh | cỡ H2 ×{args.h2_scale:g}",
     s3.FC_CALIB_NOTE, f"Thời gian chạy: {time.time() - tic:.0f} s" + (f" | MPC giải TB {np.mean(solve_times):.2f} s/lần, {n_fail[0]} lần không giải được" if args.method == "mpc" else ""), "",
     "KIỂM TRA AN TOÀN (baseline không có bảo đảm lý thuyết; chỉ kiểm giới hạn vật lý)"]
for i in I:
    e = df[f"E_{i}"]
    L.append(f"  pin {i}: E ∈ [{e.min():.2f}, {e.max():.2f}] so với [{st[i]['E_min']:.1f}, {st[i]['E_max']:.1f}]")
for i in H:
    mm = df[f"M_{i}"]
    L.append(f"  bồn {i}: M ∈ [{mm.min():.3f}, {mm.max():.3f}] kg so với [{st[i]['M_min']:.2f}, {st[i]['M_max']:.2f}]")
L.append("\nCHỈ SỐ (mục 9 file Word)")
tot_cost = df["cost"].sum(); load_e = sum(df[f"load_{i}"].sum() for i in I) * DT
buy_e = sum(df[f"buy_{i}"].sum() for i in I) * DT
pv_av = sum(df[f"pvav_{i}"].sum() for i in I) * DT; pv_use = sum(df[f"pv_{i}"].sum() for i in I) * DT
L.append(f"  K2 – chi phí (gồm giá lão hóa): {tot_cost:,.0f} CNY | trên mỗi kWh sạc: {tot_cost / load_e:.4f} CNY/kWh")
pb = float(inputs[[c for c in inputs.columns if c.startswith("price_")]].to_numpy().mean())        # cùng cách hiệu chỉnh với step3
vE = sum((state["E"][i] - float(df[f"E_{i}"].iloc[0])) * st[i]["eta_dis"] for i in I)
vM = sum((state["M"][i] - float(df[f"M_{i}"].iloc[0])) * st[i]["eta_peak"] * s3.LHV for i in H)
L.append(f"  K2 hiệu chỉnh cuối kỳ: {tot_cost - pb * (vE + vM):,.0f} CNY (pin cuối − đầu: {vE:+,.0f} kWh, bồn cuối − đầu: {vM:+,.0f} kWh điện "
         f"lấy lại được, tính giá TB {pb:.3f} CNY/kWh; chênh {100 * pb * (vE + vM) / max(tot_cost, 1e-9):+.2f}% so với K2)")
L.append(f"  Điện sạc xe: {load_e / 1000:,.1f} MWh | mua lưới: {buy_e / 1000:,.1f} MWh | bán lưới: 0.0 MWh")
L.append(f"  K5 – cắt PV: {100 * (1 - pv_use / max(pv_av, 1e-9)):.2f}% (PV khả dụng {pv_av / 1000:,.1f} MWh)")
ov_e = sum(df[f"ov_{i}"].sum() for i in I) * DT
ov_steps = int((sum(df[f"ov_{i}"] for i in I) > 1e-6).sum())
peak_util = max((df[f"trflow_{i}"] / st[i]["P_tr"]).max() for i in I)
L.append(f"  K6 – lưới: vượt giới hạn MBA {ov_e / 1000:,.2f} MWh ({100 * ov_e / load_e:.2f}% điện sạc), {ov_steps * DT:.1f} giờ có vượt; tải MBA lớn nhất {100 * peak_util:.0f}% định mức")
L.append(f"       chi phí phạt vượt tải: {s3.C_OV * ov_e:,.0f} CNY")
L.append("       theo từng trạm (vượt MWh | giờ vượt | tải MBA lớn nhất | FC phát lúc đang vượt MWh):")
for i in I:
    ovi = df[f"ov_{i}"]; hot = ovi > 1e-6
    fc_hot = (df[f"Pfc_{i}"][hot].sum() * DT / 1000) if st[i]["h2"] else float("nan")
    L.append(f"         {i}{' (H2)' if st[i]['h2'] else '     '}: {ovi.sum() * DT / 1000:6.2f} | {hot.sum() * DT:5.1f} h | "
             f"{100 * (df[f'trflow_{i}'] / st[i]['P_tr']).max():4.0f}% | {fc_hot:.2f}")
for i in H:
    mf, me = df[f"mfc_{i}"].sum(), df[f"mel_{i}"].sum()
    efc = df[f"Pfc_{i}"].sum() * DT; eel = (df[f"Pel_{i}"].sum() + df[f"Pcp_{i}"].sum()) * DT
    rt = (me / mf) * efc / eel if mf > 1e-9 and eel > 1e-9 else float("nan")
    n_fc = int((df[f"ufc_{i}"].diff().fillna(df[f"ufc_{i}"]) == 1).sum()); n_el = int((df[f"uel_{i}"].diff().fillna(df[f"uel_{i}"]) == 1).sum())
    Df, De = state["Dfc"][i], state["Del"][i]
    life_fc = T * DT / Df / 8760 if Df > 0 else float("inf"); life_el = T * DT / De / 8760 if De > 0 else float("inf")
    L.append(f"  Trạm {i}: H2 làm ra {me:.1f} kg, dùng {mf:.1f} kg | FC chạy {100 * df[f'ufc_{i}'].mean():.1f}% thời gian, bật {n_fc} lần |"
             f" EL chạy {100 * df[f'uel_{i}'].mean():.1f}%, bật {n_el} lần | hiệu suất vòng thực K3 = {rt:.3f}")
    L.append(f"           K7 – tuổi thọ dự kiến theo tốc độ kỳ này: FC {life_fc:.1f} năm, EL {life_el:.1f} năm (mục tiêu 5 năm)")
txt = "\n".join(L)
(out / "summary.txt").write_text(txt, encoding="utf-8")
print(txt + f"\n\nĐã ghi: {out / 'summary.txt'}")
