"""
BƯỚC 4 – Tính C*: chi phí tốt nhất khi BIẾT TRƯỚC toàn bộ tương lai (bài toán P1, mục 2 file Word).
Dùng để kiểm Định lý 1: thuật toán Lyapunov (step3) cách tối ưu bao xa, và khoảng cách giảm thế nào khi tăng V.

Đặt cùng thư mục với step3_simulate.py (DATN2026) rồi chạy:
    python step4_cstar.py --days 7                 # mặc định: nới lỏng LP → CẬN DƯỚI của C* (nhanh, vài phút)
    python step4_cstar.py --days 7 --milp --time_limit 1800   # giải nguyên MILP (lâu; tốt nhất với Gurobi)

Ý nghĩa hai chế độ:
  * LP (mặc định): cho phép bật/tắt "một phần" → chi phí ≤ C* thật. Khoảng cách đo so với số này là CẬN TRÊN
    của khoảng cách thật (bảo thủ: thuật toán thật còn gần tối ưu hơn con số báo cáo).
  * MILP: bật/tắt đúng 0/1. Bộ giải báo hai số: lời giải tốt nhất tìm được (≥ C*) và cận dưới (≤ C*).

Cùng mô hình, cùng chi phí với step3 (mua − bán + phạt vượt MBA + hao mòn pin + μ·ΔD đầy đủ), cùng trạng thái đầu (θ),
thêm hai ràng buộc công bằng: (i) tuổi thọ: ΣΔD ≤ δ·T cho mỗi máy (đúng P1);
(ii) cuối kỳ pin và bồn không thấp hơn đầu kỳ (không được "ăn" năng lượng dự trữ).

Ghi: DATN2026/results/cstar_<start>_<days>d[_noH2]/summary.txt + cstar.json   ← GỬI summary.txt CHO CLAUDE
"""
import argparse
import json
import re
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyomo.environ as pyo

import importlib.util
import sys


def _load_step3():
    """Tìm step3_simulate.py (cả bản tải về bị đổi tên kiểu 'step3_simulate (2).py') và nạp nó."""
    here = Path(__file__).resolve().parent
    proj = Path(__file__).resolve().parent
    cands = []
    for d in (here, proj, Path.cwd(), Path.home() / "Downloads"):
        if d.exists():
            cands += sorted(d.glob("step3_simulate*.py"), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in cands:
        src = p.read_text(encoding="utf-8", errors="ignore")
        if '"--init"' in src and "def apply_fc_calibration" in src:      # đúng bản mới
            spec = importlib.util.spec_from_file_location("step3_simulate", p)
            mod = importlib.util.module_from_spec(spec)
            sys.modules["step3_simulate"] = mod
            spec.loader.exec_module(mod)
            print(f"[*] Dùng mô hình từ: {p}")
            return mod
    raise SystemExit("Không thấy step3_simulate.py BẢN MỚI (có --init). Chép bản mới nhất vào DATN2026 rồi chạy lại.\n"
                     f"Đã tìm: {[str(c) for c in cands]}")


s3 = _load_step3()

ap = argparse.ArgumentParser()
ap.add_argument("--days", type=int, default=7)
ap.add_argument("--start", default="2022-11-01")
ap.add_argument("--milp", action="store_true", help="giải nguyên (0/1) thay vì nới lỏng LP")
ap.add_argument("--time_limit", type=float, default=1800, help="giây, cho chế độ MILP")
ap.add_argument("--mip_gap", type=float, default=0.005)
ap.add_argument("--solver", default="auto", choices=["auto", "gurobi", "cplex", "highs"])
ap.add_argument("--cplex_path", default=None, help="đường dẫn cplex.exe nếu không tự tìm thấy")
ap.add_argument("--low_mem", action="store_true", help="CPLEX tiết kiệm RAM: 2 luồng, ưu tiên bộ nhớ, ghi cây nhánh ra ổ đĩa (máy ≤ 8 GB)")
ap.add_argument("--threads", type=int, default=0, help="số luồng CPLEX (0 = tự chọn)")
ap.add_argument("--no_h2", action="store_true")
# phải giống step3 (mặc định giống hệt)
ap.add_argument("--pv_scale", type=float, default=2.0)
ap.add_argument("--tr_frac", type=float, default=0.6)
ap.add_argument("--c_ov", type=float, default=5.0)
ap.add_argument("--export_frac", type=float, default=0.0)
ap.add_argument("--no_fc_calib", action="store_true")
ap.add_argument("--no_el_calib", action="store_true")
args = ap.parse_args()

PROJECT_DIR = s3.PROJECT_DIR
DT = s3.DT
params = json.loads((PROJECT_DIR / "params" / "params_tier1.json").read_text(encoding="utf-8"))
s3.apply_fc_calibration(params, args)
s3.C_OV = args.c_ov
inputs = pd.read_csv(PROJECT_DIR / "data_clean" / "tier1_inputs.csv", index_col=0, parse_dates=True)
t0 = pd.Timestamp(args.start)
inputs = inputs.loc[t0: t0 + pd.Timedelta(days=args.days) - pd.Timedelta(minutes=5)]
T = len(inputs)
st, c_max = s3.prepare(params, inputs, 1.0, 1e10, args.pv_scale, args.export_frac, 1.0, args.tr_frac, args.no_h2)
I = sorted(st); H = [i for i in I if st[i]["h2"]]
pairs = [(a, b) for k, a in enumerate(I) for b in I[k + 1:]]
TT = list(range(T))
mode = "MILP" if args.milp else "LP"
tag = f"cstar_{args.start}_{args.days}d" + ("_noH2" if args.no_h2 else "")
out = PROJECT_DIR / "results" / tag
out.mkdir(parents=True, exist_ok=True)
print(f"[*] {s3.FC_CALIB_NOTE}\n[*] C* {mode}: {T} bước × {len(I)} trạm ({len(H)} có H2) → {out}")

# ---------------------------------------------------------------- dữ liệu
load = {(t, i): float(inputs[f"load_{i}"].iloc[t]) for t in TT for i in I}
pvav = {(t, i): float(inputs["pv_kw_per_kwp"].iloc[t]) * st[i]["pv_kWp"] for t in TT for i in I}
cb = {(t, i): float(inputs[f"price_{i}"].iloc[t]) for t in TT for i in I}
cs = {t: min(s3.C_FIT, min(float(inputs[f"price_{j}"].iloc[t]) for j in I)) for t in TT}
E1 = {i: st[i]["theta_B"] for i in I}
M1 = {i: st[i]["theta_H"] for i in H}

# ---------------------------------------------------------------- mô hình toàn chuỗi
tic = time.time()
m = pyo.ConcreteModel()
m.T, m.I, m.H = pyo.Set(initialize=TT), pyo.Set(initialize=I), pyo.Set(initialize=H)
m.PR = pyo.Set(initialize=pairs, dimen=2)
B01 = pyo.Binary if args.milp else pyo.UnitInterval
m.pv = pyo.Var(m.T, m.I, within=pyo.NonNegativeReals, bounds=lambda m, t, i: (0, pvav[t, i]))
m.buy = pyo.Var(m.T, m.I, within=pyo.NonNegativeReals)
m.ov = pyo.Var(m.T, m.I, bounds=lambda m, t, i: (0, st[i]["P_ov_max"]))
m.sell = pyo.Var(m.T, m.I, bounds=lambda m, t, i: (0, st[i]["P_export"]))
m.ch = pyo.Var(m.T, m.I, bounds=lambda m, t, i: (0, st[i]["P_bat"]))
m.dis = pyo.Var(m.T, m.I, bounds=lambda m, t, i: (0, st[i]["P_bat"]))
m.g = pyo.Var(m.T, m.PR, bounds=(-s3.P_SHARE, s3.P_SHARE))
m.E = pyo.Var(pyo.RangeSet(0, T), m.I, bounds=lambda m, t, i: (st[i]["E_min"], st[i]["E_max"]))

nseg_f = {i: len(st[i]["fc_seg"]) for i in H}; nseg_e = {i: len(st[i]["el_seg"]) for i in H}
SF = [(i, k) for i in H for k in range(nseg_f[i])]; SE = [(i, k) for i in H for k in range(nseg_e[i])]
m.SF, m.SE = pyo.Set(initialize=SF, dimen=2), pyo.Set(initialize=SE, dimen=2)
m.u_fc = pyo.Var(m.T, m.H, within=B01); m.u_el = pyo.Var(m.T, m.H, within=B01)
m.s_fc = pyo.Var(m.T, m.H, bounds=(0, 1)); m.s_el = pyo.Var(m.T, m.H, bounds=(0, 1))     # biến "bật máy"
m.yf = pyo.Var(m.T, m.SF, within=B01); m.pf = pyo.Var(m.T, m.SF, within=pyo.NonNegativeReals)
m.ye = pyo.Var(m.T, m.SE, within=B01); m.pe = pyo.Var(m.T, m.SE, within=pyo.NonNegativeReals)
m.z_lo = pyo.Var(m.T, m.H, within=B01)
m.hp = pyo.Var(m.T, m.H, bounds=(0, 1))
m.dP = pyo.Var(m.T, m.H, within=pyo.NonNegativeReals)
m.M = pyo.Var(pyo.RangeSet(0, T), m.H, bounds=lambda m, t, i: (st[i]["M_min"], st[i]["M_max"]))

P_fc = lambda m, t, i: sum(m.pf[t, i, k] for k in range(nseg_f[i]))
P_el = lambda m, t, i: sum(m.pe[t, i, k] for k in range(nseg_e[i]))
m_fc = lambda m, t, i: sum(st[i]["fc_seg"][k][2] * m.pf[t, i, k] + st[i]["fc_seg"][k][3] * m.yf[t, i, k] for k in range(nseg_f[i]))
m_el = lambda m, t, i: sum(st[i]["el_seg"][k][2] * m.pe[t, i, k] + st[i]["el_seg"][k][3] * m.ye[t, i, k] for k in range(nseg_e[i]))
m.c_yf = pyo.Constraint(m.T, m.H, rule=lambda m, t, i: sum(m.yf[t, i, k] for k in range(nseg_f[i])) == m.u_fc[t, i])
m.c_ye = pyo.Constraint(m.T, m.H, rule=lambda m, t, i: sum(m.ye[t, i, k] for k in range(nseg_e[i])) == m.u_el[t, i])
m.c_pf_lo = pyo.Constraint(m.T, m.SF, rule=lambda m, t, i, k: m.pf[t, i, k] >= st[i]["fc_seg"][k][0] * m.yf[t, i, k])
m.c_pf_hi = pyo.Constraint(m.T, m.SF, rule=lambda m, t, i, k: m.pf[t, i, k] <= st[i]["fc_seg"][k][1] * m.yf[t, i, k])
m.c_pe_lo = pyo.Constraint(m.T, m.SE, rule=lambda m, t, i, k: m.pe[t, i, k] >= st[i]["el_seg"][k][0] * m.ye[t, i, k])
m.c_pe_hi = pyo.Constraint(m.T, m.SE, rule=lambda m, t, i, k: m.pe[t, i, k] <= st[i]["el_seg"][k][1] * m.ye[t, i, k])
# bật máy: s_t ≥ u_t − u_{t−1} (máy tắt trước bước đầu, như step3)
m.c_sf = pyo.Constraint(m.T, m.H, rule=lambda m, t, i: m.s_fc[t, i] >= m.u_fc[t, i] - (m.u_fc[t - 1, i] if t > 0 else 0))
m.c_se = pyo.Constraint(m.T, m.H, rule=lambda m, t, i: m.s_el[t, i] >= m.u_el[t, i] - (m.u_el[t - 1, i] if t > 0 else 0))
# đổi tải (chỉ tính khi hai bước liên tiếp đều bật), tải thấp, tải cao – y như step3
BigM = {i: st[i]["P_fc"] for i in H}
def _dp(sign):
    def r(m, t, i):
        if t == 0:
            return pyo.Constraint.Skip
        diff = P_fc(m, t, i) - P_fc(m, t - 1, i)
        return m.dP[t, i] >= sign * diff - BigM[i] * (1 - m.u_fc[t, i]) - BigM[i] * (1 - m.u_fc[t - 1, i])
    return r
m.c_dP1 = pyo.Constraint(m.T, m.H, rule=_dp(1)); m.c_dP2 = pyo.Constraint(m.T, m.H, rule=_dp(-1))
m.c_lo1 = pyo.Constraint(m.T, m.H, rule=lambda m, t, i: m.z_lo[t, i] <= m.u_fc[t, i])
m.c_lo2 = pyo.Constraint(m.T, m.H, rule=lambda m, t, i: P_fc(m, t, i) >= st[i]["P_lo"] * (m.u_fc[t, i] - m.z_lo[t, i]))
m.c_hp = pyo.Constraint(m.T, m.H, rule=lambda m, t, i: m.hp[t, i] >= (P_fc(m, t, i) - st[i]["P_hi"]) / (st[i]["P_fc"] - st[i]["P_hi"]))
dD_fc = lambda m, t, i: (st[i]["fc_k_start"] * m.s_fc[t, i] + st[i]["fc_k_lc"] * m.dP[t, i]
                         + st[i]["fc_k_lo"] * m.z_lo[t, i] + st[i]["fc_k_hp"] * m.hp[t, i])
dD_el = lambda m, t, i: st[i]["el_k_start"] * m.s_el[t, i] + st[i]["el_k_a0"] * m.u_el[t, i]
# tuổi thọ (P1): tổng lão hóa ≤ ngân sách δ·T
m.c_life_fc = pyo.Constraint(m.H, rule=lambda m, i: sum(dD_fc(m, t, i) for t in TT) <= st[i]["delta_fc"] * T)
m.c_life_el = pyo.Constraint(m.H, rule=lambda m, i: sum(dD_el(m, t, i) for t in TT) <= st[i]["delta_el"] * T)

share_out = lambda m, t, i: sum(m.g[t, a, b] for (a, b) in pairs if a == i) - sum(m.g[t, a, b] for (a, b) in pairs if b == i)
def balance(m, t, i):
    fcP = P_fc(m, t, i) if i in H else 0.0
    elP = (P_el(m, t, i) + s3.E_CP * m_el(m, t, i) / DT) if i in H else 0.0
    return m.pv[t, i] + m.buy[t, i] + m.dis[t, i] + fcP == load[t, i] + m.sell[t, i] + m.ch[t, i] + elP + share_out(m, t, i)
m.c_bal = pyo.Constraint(m.T, m.I, rule=balance)
m.c_tr_hi = pyo.Constraint(m.T, m.I, rule=lambda m, t, i: m.buy[t, i] - m.sell[t, i] - share_out(m, t, i) <= st[i]["P_tr"] + m.ov[t, i])
m.c_tr_lo = pyo.Constraint(m.T, m.I, rule=lambda m, t, i: m.buy[t, i] - m.sell[t, i] - share_out(m, t, i) >= -st[i]["P_tr"])
m.c_E = pyo.Constraint(m.T, m.I, rule=lambda m, t, i: m.E[t + 1, i] == m.E[t, i] + (st[i]["eta_ch"] * m.ch[t, i] - m.dis[t, i] / st[i]["eta_dis"]) * DT)
m.c_E0 = pyo.Constraint(m.I, rule=lambda m, i: m.E[0, i] == E1[i])
m.c_ET = pyo.Constraint(m.I, rule=lambda m, i: m.E[T, i] >= E1[i])
m.c_M = pyo.Constraint(m.T, m.H, rule=lambda m, t, i: m.M[t + 1, i] == m.M[t, i] + m_el(m, t, i) - m_fc(m, t, i))
m.c_M0 = pyo.Constraint(m.H, rule=lambda m, i: m.M[0, i] == M1[i])
m.c_MT = pyo.Constraint(m.H, rule=lambda m, i: m.M[T, i] >= M1[i])

def cost_expr(m):
    c = 0
    for t in TT:
        for i in I:
            c += (cb[t, i] * m.buy[t, i] - cs[t] * m.sell[t, i] + s3.C_OV * m.ov[t, i] + s3.C_BAT * (m.ch[t, i] + m.dis[t, i])) * DT
            if i in H:
                c += st[i]["mu_fc"] * dD_fc(m, t, i) + st[i]["mu_el"] * dD_el(m, t, i)
    return c
m.obj = pyo.Objective(expr=cost_expr(m), sense=pyo.minimize)
print(f"[*] Dựng mô hình: {time.time() - tic:.0f} s", flush=True)

# ---------------------------------------------------------------- giải
def find_cplex():
    """Tìm cplex.exe: --cplex_path → PATH → thư mục cài đặt IBM mặc định."""
    import glob, shutil
    if args.cplex_path:
        return args.cplex_path if Path(args.cplex_path).exists() else None
    w = shutil.which("cplex")
    if w:
        return w
    pats = [r"C:\Program Files\IBM\ILOG\CPLEX_Studio*\cplex\bin\x64_win64\cplex.exe",
            r"C:\Program Files (x86)\IBM\ILOG\CPLEX_Studio*\cplex\bin\x64_win64\cplex.exe",
            str(Path.home() / "IBM" / "ILOG" / "CPLEX_Studio*" / "cplex" / "bin" / "x64_win64" / "cplex.exe"),
            "/opt/ibm/ILOG/CPLEX_Studio*/cplex/bin/x86-64_linux/cplex"]
    for pat in pats:
        hits = sorted(glob.glob(pat), reverse=True)        # bản mới nhất trước
        if hits:
            return hits[0]
    return None


def solve():
    order = {"auto": ["gurobi", "cplex", "highs"], "gurobi": ["gurobi"], "cplex": ["cplex"], "highs": ["highs"]}[args.solver]
    for name in order:
        if name == "gurobi":
            s = pyo.SolverFactory("gurobi_direct")
            if not s.available(exception_flag=False):
                continue
            s.options.update({"TimeLimit": args.time_limit, "MIPGap": args.mip_gap})
            r = s.solve(m, tee=True, load_solutions=True)
            lb = getattr(r.problem, "lower_bound", float("nan"))
            return "gurobi", r, lb
        if name == "cplex":
            exe = find_cplex()
            if exe is None:
                if args.solver == "cplex":
                    raise SystemExit("Không tìm thấy cplex.exe. Tìm nó bằng lệnh PowerShell:\n"
                                     "  Get-ChildItem 'C:\\Program Files\\IBM' -Recurse -Filter cplex.exe -ErrorAction SilentlyContinue | Select-Object FullName\n"
                                     "rồi chạy lại với --cplex_path \"<đường dẫn vừa tìm>\"")
                continue
            print(f"[*] CPLEX: {exe}", flush=True)
            s = pyo.SolverFactory("cplex", executable=exe)
            s.options["timelimit"] = args.time_limit
            if args.milp:
                s.options["mip_tolerances_mipgap"] = args.mip_gap
            import tempfile, shutil as _sh
            if args.threads > 0 or args.low_mem:
                s.options["threads"] = args.threads if args.threads > 0 else 2
            if args.low_mem:
                s.options["emphasis_memory"] = "y"               # CPLEX dùng ít RAM hơn (chậm hơn chút)
                s.options["workdir"] = tempfile.gettempdir()      # thư mục ghi file tạm (không có dấu cách)
                if args.milp:
                    s.options["mip_strategy_file"] = 3            # cây nhánh-cận ghi ra ổ đĩa, nén
                    s.options["workmem"] = 1024                   # MB RAM tối đa cho cây trước khi ghi ra đĩa
                else:
                    s.options["lpmethod"] = 4                     # LP: barrier (ít RAM, nhanh với bài lớn)
            log = Path(tempfile.gettempdir()) / f"cstar_cplex_{int(time.time())}.log"   # thư mục tạm KHÔNG có dấu cách (Pyomo lỗi với đường dẫn có dấu cách)
            try:
                r = s.solve(m, tee=True, load_solutions=True, logfile=str(log))
            except ValueError as e:
                txt_ = log.read_text(encoding="utf-8", errors="ignore") if log.exists() else ""
                if "Out of memory" in txt_ or "1001" in txt_:
                    raise SystemExit("\n[!] CPLEX HẾT RAM. Thử lại với --low_mem; nếu vẫn hết RAM thì giảm số ngày "
                                     "hoặc bỏ --milp (LP chỉ cho cận dưới, nhưng nhẹ hơn nhiều).")
                raise SystemExit(f"\n[!] CPLEX không trả lời giải: {e}. Xem nhật ký: {log}")
            try:
                _sh.copy(log, out / "cplex.log")
            except Exception:
                pass
            lb = float("nan")
            try:                                   # cận dưới: đọc từ nhật ký CPLEX
                txt = log.read_text(encoding="utf-8", errors="ignore")
                mm = re.findall(r"Current MIP best bound\s*=\s*([\-\d\.eE\+]+)", txt)
                if mm:
                    lb = float(mm[-1])
                elif args.milp and re.search(r"Integer optimal", txt):
                    lb = pyo.value(m.obj) * (1 - args.mip_gap)      # CPLEX dừng khi gap ≤ mip_gap ⇒ cận dưới an toàn
                elif not args.milp:
                    lb = pyo.value(m.obj)                            # LP giải tối ưu: cận dưới = giá trị
            except Exception:
                pass
            if not np.isfinite(lb):
                lb = getattr(r.problem, "lower_bound", float("nan"))
            return "cplex", r, float(lb)
        s = pyo.SolverFactory("appsi_highs")
        if not s.available(exception_flag=False):
            continue
        s.config.time_limit = args.time_limit
        s.config.mip_gap = args.mip_gap
        s.config.stream_solver = True
        s.config.load_solution = False
        r = s.solve(m)
        try:
            s.load_vars()
        except Exception:
            raise SystemExit(f"HiGHS không tìm được lời giải khả thi trong {args.time_limit:.0f} s ({r.termination_condition})")
        lb = getattr(r, "best_objective_bound", None)
        try:                                   # lấy trực tiếp từ HiGHS nếu appsi không trả
            info = s._solver_model.getInfo()
            lb = info.mip_dual_bound if args.milp else info.objective_function_value
        except Exception:
            pass
        return "highs", r, float(lb) if lb is not None else float("nan")
    raise SystemExit(f"Không có bộ giải cho lựa chọn --solver {args.solver} "
                     "(HiGHS: pip install highspy; CPLEX: thêm --cplex_path; Gurobi: cần license)")

tic = time.time()
sname, res, lb = solve()
sol_t = time.time() - tic
obj = pyo.value(m.obj)

# ---------------------------------------------------------------- báo cáo
ov_e = sum(pyo.value(m.ov[t, i]) for t in TT for i in I) * DT
load_e = sum(load.values()) * DT
L = [f"BƯỚC 4 – C* ({'không H2' if args.no_h2 else 'có H2'}) – {mode} – {T} bước ({args.days} ngày từ {args.start}) | bộ giải {sname} | {sol_t:.0f} s",
     s3.FC_CALIB_NOTE,
     f"Thiết lập giống step3: PV ×{args.pv_scale:g}, MBA = {args.tr_frac:g}×đỉnh, phạt vượt {args.c_ov:g} CNY/kWh, bán lưới ≤ {args.export_frac:g}·P_tr, bắt đầu ở θ",
     ""]
if args.milp:
    L.append(f"C* (lời giải tốt nhất tìm được, ≥ C* thật) = {obj:,.0f} CNY | cận dưới của bộ giải (≤ C* thật) = {lb:,.0f} CNY")
else:
    L.append(f"C*_LP (nới lỏng, ≤ C* thật) = {obj:,.0f} CNY   ← khoảng cách so với số này là CẬN TRÊN của khoảng cách thật")
L.append(f"  trên mỗi kWh sạc: {obj / load_e:.4f} CNY/kWh | vượt MBA: {ov_e / 1000:.2f} MWh")
for i in H:
    dfc = sum(pyo.value(dD_fc(m, t, i)) for t in TT); del_ = sum(pyo.value(dD_el(m, t, i)) for t in TT)
    mf = sum(pyo.value(m_fc(m, t, i)) for t in TT)
    L.append(f"  trạm {i}: H2 dùng {mf:.0f} kg | ΣΔD FC = {dfc:.3e} (ngân sách {st[i]['delta_fc'] * T:.3e}) | EL = {del_:.3e}")
txt = "\n".join(L)
(out / "summary.txt").write_text(txt, encoding="utf-8")
(out / "cstar.json").write_text(json.dumps({"mode": mode, "C_star": obj, "lower_bound": lb, "days": args.days,
                                            "start": args.start, "no_h2": args.no_h2, "overload_MWh": ov_e,
                                            "solver": sname, "seconds": sol_t}, indent=2), encoding="utf-8")
print("\n" + txt + f"\n\nĐã ghi: {out / 'summary.txt'}")
