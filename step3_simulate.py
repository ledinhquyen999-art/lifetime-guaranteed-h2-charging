"""
BƯỚC 3 – Mô phỏng thuật toán Lyapunov (bản sửa: trả trước lão hóa bật/tắt + Lyapunov có trọng số) cho 7 trạm tầng 1.

Chạy (đặt file trong DATN2026):
    python step3_simulate.py                       # mặc định: 7 ngày từ 2022-11-01, V = 1
    python step3_simulate.py --days 30 --start 2022-09-01
    python step3_simulate.py --days 0              # toàn bộ 6 tháng (lâu!)
Cần: pip install pyomo highspy   (có Gurobi thì: pip install gurobipy, script tự dùng)

Đọc : DATN2026/data_clean/tier1_inputs.csv, DATN2026/params/params_tier1.json (từ bước 1 và 2)
Ghi : DATN2026/results/step3_<tên lần chạy>/
        summary.txt        – TÓM TẮT + KẾT QUẢ KIỂM CHỨNG ĐỊNH LÝ  (GỬI FILE NÀY CHO CLAUDE)
        timeseries.csv     – mọi biến mỗi bước 5 phút
        fig_*.png          – hình kiểm tra

Phạm vi bản này (v1) – ghi rõ để không nhầm:
  * Giải P3 TẬP TRUNG mỗi bước (chưa ADMM). ADMM sẽ thêm ở bản sau và so với bản này để đo ε.
  * Lưới: giới hạn máy biến áp từng trạm + giới hạn chia sẻ; CHƯA có LinDistFlow IEEE 33 nút (bản sau).
  * Nhà máy dùng cùng đường cong H2 với bộ điều khiển (chưa có sai lệch mô hình; bản sau thêm đường phân cực đầy đủ).
  * Đường cong hiệu suất FC/EL là GIẢ ĐỊNH hợp lý, sẽ thay bằng số hiệu chỉnh từ FCLAB/Mendeley.
"""
import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyomo.environ as pyo

try:  # Windows: in tiếng Việt an toàn cả khi chạy ngầm (run_batch)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ============================================================== thư mục
PROJECT_DIR = Path(__file__).resolve().parent
if not PROJECT_DIR.exists():
    PROJECT_DIR = Path(__file__).resolve().parent

DT = 5 / 60          # giờ
LHV = 33.33          # kWh/kg
C_FIT = 0.453        # CNY/kWh – giá bán lại cho lưới (giá than chuẩn Quảng Đông) – CẦN XÁC MINH
C_BAT = 0.05         # CNY/kWh – hao mòn pin
P_SHARE = 300.0      # kW – giới hạn chia sẻ giữa hai trạm (giả định)
V_REF_MARGIN = 1.05  # trọng số w_B, w_H chọn để V_REF ≤ V_max với dư 5%
START_AMORT = 1.0    # đặt bằng --start_amort
C_OV = 5.0           # CNY/kWh – phạt nhập vượt giới hạn máy biến áp (tắc nghẽn), đặt bằng --c_ov

# Đường cong hiệu suất (GIẢ ĐỊNH, theo tỉ lệ công suất định mức)
FC_X, FC_ETA = [0.1, 0.3, 0.6, 1.0], [0.40, 0.50, 0.47, 0.40]       # hiệu suất hệ FC (LHV)
EL_X, EL_KWHKG = [0.1, 0.4, 1.0], [62.0, 53.0, 56.0]                # kWh điện / kg H2 (gồm phụ trợ)
E_CP = 2.5                                                          # kWh/kg máy nén – CẦN XÁC MINH
FC_CALIB_NOTE = ""
# ---- việc 2.7: bán H2 cho xe pin nhiên liệu (FCEV) – trạm sạc + trạm nạp hydro. Mặc định TẮT (= kết quả cũ y hệt).
H2_DEM_FRAC = 0.0  # nhu cầu H2/ngày của mỗi trạm H2 = tỉ lệ này × sản lượng EL định mức 24 h (đặt bằng --h2_demand_frac)
C_EXT = 40.0       # CNY/kg – giá H2 mua ngoài chở bằng xe bồn (bán tại chỗ = tránh được khoản này), --c_ext
FILL_KG = 5.0      # kg mỗi lần nạp (xe tải giao hàng nhẹ), --fill_kg
DISP = 2           # số lần nạp tối đa trong 5 phút (2 vòi) → rút tối đa DISP·FILL_KG kg/bước
H2_HOUR_SHAPE = [0.5, 0.3, 0.2, 0.2, 0.3, 0.8, 2.0, 3.5, 4.0, 3.0, 2.5, 2.5,   # dạng nhu cầu theo giờ (giả định: hai đỉnh sáng/chiều,
                 2.5, 2.3, 2.3, 2.5, 3.0, 3.8, 4.0, 3.2, 2.2, 1.5, 1.0, 0.7]  # giống đường cầu trạm xăng đội xe), chuẩn hóa tổng = 1
DEM_ON = False
# ---- việc 3.3b: điều khiển có tính lưới IEEE 33 nút (LinDistFlow). Mặc định TẮT (= kết quả cũ y hệt).
GRID_ON = False
VV_ON = False      # --volt_var: bộ biến đổi của pin và FC phát/hút công suất phản kháng Q để đỡ điện áp
S_OVER = 1.1       # công suất biểu kiến bộ biến đổi = 1,1 × công suất định mức (thông lệ chọn dư 10%)
C_Q = 0.005        # CNY/kvarh – chi phí nhỏ cho Q (tổn hao bộ biến đổi), tránh dùng Q vô ích
VV_FC_ALWAYS = True    # mặc định: bộ biến đổi FC phát Q cả khi FC tắt (STATCOM, giả thiết A8 – cần cho chứng minh); --vv_fc_gated: chỉ khi FC chạy
GRID = {}          # K (hệ số điện áp theo trflow từng trạm), vbase(t), ...
GRID_BUS_OF = {1589: 17, 1242: 32, 1093: 24, 1214: 21, 1061: 8, 1087: 13, 1229: 29}     # giống grid33_eval.py
GRID_BASE_SHAPE = [0.55, 0.50, 0.47, 0.45, 0.45, 0.48, 0.55, 0.65, 0.72, 0.75, 0.78, 0.80,
                   0.80, 0.78, 0.78, 0.80, 0.85, 0.92, 1.00, 1.00, 0.97, 0.90, 0.78, 0.65]


def grid_setup(index, stations, ev_scale, base_scale, pf, vmin, margin, c_v):
    """LinDistFlow cho case33bw: v_b = |V_b|² ≈ 1 − 2Σ_k (R_bk p_k + X_bk q_k) (p, q: MW, MVAr trên nền 1 MVA).
    Trả về: vbase[b, t] do phụ tải nền, K[b, i] = độ giảm v_b cho mỗi kW lấy từ lưới ở trạm i, ngưỡng v_min² có biên."""
    import pandapower.networks as pn
    net = pn.case33bw()
    nb = len(net.bus); Zb = (net.bus.vn_kv.iloc[0] * 1e3) ** 2 / 1e6
    ln = net.line[net.line.in_service]
    parent = -np.ones(nb, int); rr = np.zeros(nb); xx = np.zeros(nb)
    for _, l in ln.iterrows():
        parent[int(l.to_bus)] = int(l.from_bus)
        rr[int(l.to_bus)] = l.r_ohm_per_km * l.length_km / Zb; xx[int(l.to_bus)] = l.x_ohm_per_km * l.length_km / Zb
    path = []
    for b in range(nb):
        pth, k = set(), b
        while parent[k] >= 0:
            pth.add(k); k = parent[k]
        path.append(pth)
    R = np.array([[sum(rr[j] for j in path[a] & path[b]) for b in range(nb)] for a in range(nb)])
    X = np.array([[sum(xx[j] for j in path[a] & path[b]) for b in range(nb)] for a in range(nb)])
    P0 = np.zeros(nb); Q0 = np.zeros(nb)
    for _, r in net.load.iterrows():
        P0[int(r.bus)] += r.p_mw; Q0[int(r.bus)] += r.q_mvar
    shape = np.array(GRID_BASE_SHAPE)[index.hour.to_numpy()] * base_scale
    vbase = 1.0 - 2.0 * np.outer(R @ P0 + X @ Q0, shape)                     # (nb, T)
    tanphi = np.tan(np.arccos(pf))
    K = {i: 2.0 * (R[:, GRID_BUS_OF[i]] + tanphi * X[:, GRID_BUS_OF[i]]) * ev_scale / 1000.0 for i in stations}   # pu² mỗi kW
    Kq = {i: 2.0 * X[:, GRID_BUS_OF[i]] * ev_scale / 1000.0 for i in stations}                               # pu² mỗi kvar PHÁT ra
    return dict(vbase=vbase, K=K, Kq=Kq, tanphi=float(tanphi), v2min=(vmin + margin) ** 2, c_v=c_v, nb=nb,
                cmax_add=c_v * max(float(np.max(k)) for k in K.values()))     # CNY/kWh: chi phí biên lớn nhất do phạt điện áp




def h2_demand_series(station, index, frac, seed_base=2022):
    """Chuỗi nhu cầu H2 (kg mỗi bước 5 phút) cho một trạm: số xe đến ~ Poisson theo giờ, mỗi xe FILL_KG kg, tối đa DISP xe/bước.
    Hạt ngẫu nhiên cố định theo mã trạm → chạy lại ra y hệt; S1, S3, pin... dùng CÙNG một chuỗi."""
    if frac <= 0:
        return np.zeros(len(index))
    D_day = frac * station["el_kW"] * 24.0 / EL_KWHKG[-1]                      # kg/ngày
    w = np.array(H2_HOUR_SHAPE, float); w = w / w.sum()
    lam = D_day * w[index.hour] / 12.0 / FILL_KG                                 # số xe kỳ vọng mỗi bước
    rng = np.random.default_rng(seed_base + int(station["station_id"]))
    return np.minimum(rng.poisson(lam), DISP) * FILL_KG


# ---- việc 4.2: SAI LỆCH MÔ HÌNH. Mặc định TẮT (= kết quả cũ y hệt).
#   Nhà máy "thật": đường hiệu suất TRƠN (nội suy PCHIP qua các điểm hiệu chỉnh) tại mức lão hóa thật D, nhân thêm độ lệch b.
#   Bộ điều khiển: đường tuyến tính từng đoạn (K đoạn) tại mức lão hóa đo được lúc đầu ngày (A6) hoặc không bao giờ cập nhật.
PLANT_ON = False
PLANT = dict(bias=0.0, d0=0.0, update="daily", seg=0, robust=True)
CAL = {}           # bảng hiệu suất theo (x, D) đọc từ params/*_calibration.json


def _table(x, bol, eol, grid, tabD, sign):
    """Bảng hiệu suất theo D (hàng) × x (cột). Không có bảng D thì nội suy BOL→EOL; không có EOL thì giả định ±10% tại D = 1."""
    x, bol = np.array(x, float), np.array(bol, float)
    if grid is not None and tabD is not None:
        G, T = np.array(grid, float), np.array(tabD, float)
        for k in range(T.shape[1]):              # ô NaN (vượt công suất cực đại khi quá già) → lấy giá trị hữu hạn gần nhất
            col = pd.Series(T[:, k]).ffill().bfill().to_numpy(); T[:, k] = col
        return x, G, T
    eolv = np.array(eol, float) if eol is not None else bol * (1 - sign * 0.1)
    return x, np.array([0.0, 1.0]), np.vstack([bol, eolv])


def curve_at(name, D):
    """Giá trị đường cong tại các điểm x hiệu chỉnh, ở mức lão hóa D (FC: hiệu suất; EL: kWh/kg)."""
    x, G, T = CAL[name]
    D = min(max(D, G[0]), G[-1])
    return x, np.array([np.interp(D, G, T[:, k]) for k in range(T.shape[1])])


_PCHIP_CACHE = {}


def _pchip(name, D):
    key = (name, round(D, 4))
    f = _PCHIP_CACHE.get(key)
    if f is None:
        from scipy.interpolate import PchipInterpolator
        x, v = curve_at(name, D)
        f = (PchipInterpolator(x, v), x[0])
        if len(_PCHIP_CACHE) > 5000:
            _PCHIP_CACHE.clear()
        _PCHIP_CACHE[key] = f
    return f


def plant_mass(name, P, Pbar, D):
    """Khối lượng H2 THẬT trong một bước (kg): FC tiêu thụ / EL sản xuất, theo đường trơn PCHIP tại D, kèm độ lệch b (bất lợi cho bồn)."""
    if P <= 1e-9:
        return 0.0
    f, x0 = _pchip(name, D)
    val = float(f(min(max(P / Pbar, x0), 1.0)))
    if name == "fc":
        return P * DT / (val * LHV) * (1 + PLANT["bias"])
    return P * DT / val * (1 - PLANT["bias"])


def ctrl_points(name, D, Pbar):
    """Điểm gãy (kW) và khối lượng (kg/bước) cho đường tuyến tính từng đoạn của BỘ ĐIỀU KHIỂN."""
    from scipy.interpolate import PchipInterpolator
    x, v = curve_at(name, D)
    xs = list(x) if PLANT["seg"] <= 0 else list(np.linspace(x[0], 1.0, PLANT["seg"] + 1))
    vv = PchipInterpolator(x, v)(xs)
    ms = [xx * Pbar * DT / ((e * LHV) if name == "fc" else e) for xx, e in zip(xs, vv)]
    return xs, ms


# ---- việc 3.1–3.2: ADMM phân tán (mục 4 của file lý thuyết). Mặc định TẮT (= giải tập trung như cũ).
ADMM_TAN = [0.0, 0.5, 1.5, 4.0, 10.0, 25.0, 60.0, 150.0, 300.0, 600.0]   # kW – điểm tiếp tuyến xấp xỉ hạng phạt ρ/2·(x − y)² (tuyến tính hóa, giữ MILP)


SHARE_K = 0       # --share_k: chỉ chia sẻ với K điểm gần nhất (0 = mọi cặp, như 7 trạm)


NO_AGING = False   # --no_aging: baseline "Lyapunov không tính lão hóa" (kiểu Yan & Chen): bỏ μ·ΔD và w_Z·Z·ΔD khỏi hàm mục tiêu


# ============================================================== chuẩn bị thông số
def pwl(xs, ms, Pbar):
    """Đường H2 tuyến tính từng đoạn: trả về list (lo, hi, slope, intercept) theo kW, m tính bằng kg/bước."""
    segs = []
    for k in range(len(xs) - 1):
        lo, hi = xs[k] * Pbar, xs[k + 1] * Pbar
        slope = (ms[k + 1] - ms[k]) / (hi - lo)
        segs.append((lo, hi, slope, ms[k] - slope * lo))
    return segs


def prepare(params, inputs, V, w_Z, pv_scale=1.0, export_frac=1.0, V_REF=1.0, tr_frac=0.6, no_h2=False):
    assert V <= V_REF + 1e-12, "V phải ≤ V_REF (trọng số được chọn cho V_REF)"
    A = params["aging_and_devices"]
    fc, el, bat, tank = A["fc"], A["el"], A["bat"], A["tank"]
    st = {}
    price_cols = [c for c in inputs.columns if c.startswith("price_")]
    c_max = float(inputs[price_cols].max().max()) + C_OV        # c̄ = c_buy_max + c_ov (giả thiết A3 mới)
    if GRID_ON:
        c_max += GRID["cmax_add"]                                  # + chi phí biên lớn nhất của phạt điện áp (A3 vẫn đúng)
    for s in params["stations"]:
        i = int(s["station_id"])
        d = {"id": i, "h2": bool(s["has_h2"]) and not no_h2, "pv_kWp": s["pv_kWp"] * pv_scale, "lat": s.get("lat"), "lon": s.get("lon")}
        d["E_cap"] = s["bat_kWh"]; d["P_bat"] = s["bat_kW"]
        d["E_min"], d["E_max"] = bat["soc_min"] * d["E_cap"], bat["soc_max"] * d["E_cap"]
        d["eta_ch"], d["eta_dis"] = bat["eta_ch"], bat["eta_dis"]
        peak = float(inputs[f"load_{i}"].max())
        d["P_tr"] = max(tr_frac * peak, 10.0)          # giới hạn máy biến áp (lưới nghẽn khi tr_frac < 1); ≥ 10 kW phòng điểm không có tải
        d["P_export"] = export_frac * d["P_tr"]
        d["P_ov_max"] = peak + d["P_bat"] + (s.get("fc_kW") or 0.0)   # đủ lớn để A3 luôn đúng
        # ---- pin: trọng số và mức tham chiếu (Mệnh đề 1)
        slack_B = (d["E_max"] - d["E_min"]) - d["eta_ch"] * d["P_bat"] * DT - d["P_bat"] * DT / d["eta_dis"]
        d["w_B"] = V_REF_MARGIN * V_REF * d["eta_dis"] * c_max / slack_B
        G_dis = d["eta_dis"] * V * c_max / d["w_B"]
        lo_B = d["E_min"] + d["P_bat"] * DT / d["eta_dis"] + G_dis
        hi_B = d["E_max"] - d["eta_ch"] * d["P_bat"] * DT
        assert lo_B <= hi_B, f"Khoảng θ^B rỗng ở trạm {i}"
        d["theta_B"] = 0.5 * (lo_B + hi_B)
        d["dE_max"] = max(d["eta_ch"] * d["P_bat"], d["P_bat"] / d["eta_dis"]) * DT
        if d["h2"]:
            d["P_fc"], d["P_el"] = s["fc_kW"], s["el_kW"]
            d["n_mod"] = d["P_fc"] / fc["module_kW"]
            if PLANT_ON:     # bộ điều khiển dùng đường K đoạn lấy từ đường trơn: tại D đo được (daily) hoặc đường máy mới D = 0 (none)
                Dc = PLANT["d0"] if PLANT["update"] == "daily" else 0.0
                fx, fc_m = ctrl_points("fc", Dc, d["P_fc"]); ex, el_m = ctrl_points("el", Dc, d["P_el"])
            else:
                fx, ex = FC_X, EL_X
                fc_m = [x * d["P_fc"] * DT / (eta * LHV) for x, eta in zip(FC_X, FC_ETA)]
                el_m = [x * d["P_el"] * DT / k for x, k in zip(EL_X, EL_KWHKG)]
            d["fc_x"], d["el_x"] = fx, ex
            d["fc_seg"], d["el_seg"] = pwl(fx, fc_m, d["P_fc"]), pwl(ex, el_m, d["P_el"])
            grid = np.linspace(fx[0], 1, 400) * d["P_fc"]
            mfc = np.interp(grid, [x * d["P_fc"] for x in fx], fc_m)
            d["eta_peak"] = float(np.max(grid * DT / (mfc * LHV)))     # D chỉ tăng → hiệu suất đỉnh lúc đầu là lớn nhất (Γ an toàn)
            d["m_fc_max"], d["m_el_max"], d["m_el_min"] = fc_m[-1], el_m[-1], el_m[0]
            if PLANT_ON and PLANT["robust"]:   # mục 1b, điểm 2: chặn lấy giá trị LỚN HƠN giữa hai mô hình, cho cả đời máy (D đến 1)
                d["m_fc_max"] = max(fc_m[-1], plant_mass("fc", d["P_fc"], d["P_fc"], 1.0), plant_mass("fc", d["P_fc"], d["P_fc"], PLANT["d0"]))
                d["m_el_max"] = max(el_m[-1], plant_mass("el", d["P_el"], d["P_el"], 0.0), plant_mass("el", d["P_el"], d["P_el"], PLANT["d0"]))
            d["M_cap"] = s["tank_kg"]
            d["M_min"], d["M_max"] = tank["fill_min"] * d["M_cap"], tank["fill_max"] * d["M_cap"]
            d["s_max"] = DISP * FILL_KG if DEM_ON else 0.0                  # rút tối đa mỗi bước do bán H2
            room = d["M_max"] - d["M_min"] - d["m_fc_max"] - d["s_max"] - d["m_el_max"]
            val_kg = max(d["eta_peak"] * LHV * c_max, C_EXT if DEM_ON else 0.0)   # giá trị lớn nhất của 1 kg rút ra
            d["w_H"] = V_REF_MARGIN * V_REF * val_kg / room
            G_fc = val_kg * V / d["w_H"]                                     # = max(Γ^fc, Γ^bán)
            lo_H, hi_H = d["M_min"] + d["m_fc_max"] + d["s_max"] + G_fc, d["M_max"] - d["m_el_max"]
            assert lo_H <= hi_H, f"Khoảng θ^H rỗng ở trạm {i}"
            d["theta_H"] = 0.5 * (lo_H + hi_H)
            d["H_max"] = d["M_max"] - d["M_min"]
            d["dM_max"] = max(d["m_fc_max"] + d["s_max"], d["m_el_max"])
            # ---- lão hóa (đơn vị D)
            Vf, Ve = 0.1 * fc["V_rated_cell_uV"], 0.1 * el["V_rated_cell_uV"]
            d["fc_k_start"] = 2 * fc["k_ss_uV"] / Vf          # trả trước khi bật
            d["fc_k_stop_phys"] = fc["k_ss_uV"] / Vf          # chỉ dùng cho lão hóa thật (Bổ đề 0)
            d["fc_k_lc"] = fc["k_lc_uV_per_kW"] / d["n_mod"] / Vf   # trên mỗi kW thay đổi tổng
            d["fc_k_lo"] = fc["k_lo_uV_per_h"] * DT / Vf
            d["fc_k_hp"] = fc["k_hp_uV_per_h"] * DT / Vf
            d["P_lo"], d["P_hi"] = fc["P_lo_frac"] * d["P_fc"], fc["P_hi_frac"] * d["P_fc"]
            d["el_k_a0"] = el["a0_uV_per_h"] * DT / Ve
            d["el_k_start"] = el["a_sd_uV"] / Ve
            d["delta_fc"] = DT / fc["life_target_h"]; d["delta_el"] = DT / el["life_target_h"]
            d["mu_fc"] = fc["stack_cost_CNY_per_kW"] * d["P_fc"]; d["mu_el"] = el["stack_cost_CNY_per_kW"] * d["P_el"]
            d["dD_fc_max"] = max(d["fc_k_start"], d["fc_k_lc"] * (1 - d["fc_x"][0]) * d["P_fc"]) + max(d["fc_k_lo"], d["fc_k_hp"])
            d["dD_el_max"] = d["el_k_start"] + d["el_k_a0"]
            d["kC_fc"], d["kC_el"] = c_max * d["P_fc"] * DT, 0.0
            d["kQ_fc"] = d["w_H"] * d["H_max"] * d["m_fc_max"]
            d["kQ_el"] = d["w_H"] * d["H_max"] * d["m_el_max"]
            d["Zmax_fc"] = (V * d["kC_fc"] + d["kQ_fc"]) / (w_Z * d["delta_fc"]) + d["dD_fc_max"]
            d["Zmax_el"] = (V * d["kC_el"] + d["kQ_el"]) / (w_Z * d["delta_el"]) + d["dD_el_max"]
        st[i] = d
    return st, c_max


# ============================================================== mô hình P3 (dựng một lần, cập nhật tham số mỗi bước)
def build_model(st, V, w_Z, admm_rho=None):
    """admm_rho = None: bài P3 tập trung. admm_rho = ρ: N bài con của các trạm GHÉP CẠNH NHAU (tách rời hoàn toàn – không có ràng buộc
    hay biến chung), mỗi trạm có bản sao riêng x[i, j] của điện chia cho trạm j, cộng hạng ADMM λ·x + ρ/2·(x − y)². Giải khối tách rời này
    một lần cho cùng nghiệm như giải từng trạm riêng (song song); chỉ khác là không đo được thời gian của từng trạm."""
    m = pyo.ConcreteModel()
    I = sorted(st); H = [i for i in I if st[i]["h2"]]
    pairs = [(a, b) for k, a in enumerate(I) for b in I[k + 1:]]
    if SHARE_K > 0 and all(st[i].get("lat") is not None for i in I):     # mạng lớn: chỉ chia sẻ với K điểm gần nhất (đường dây gần)
        keep = set()
        for a in I:
            dist = sorted((math.hypot(st[a]["lat"] - st[b]["lat"], (st[a]["lon"] - st[b]["lon"]) * math.cos(math.radians(st[a]["lat"]))), b) for b in I if b != a)
            for _, b in dist[:SHARE_K]:
                keep.add((min(a, b), max(a, b)))
        pairs = [pr for pr in pairs if pr in keep]
    m.I, m.H = pyo.Set(initialize=I), pyo.Set(initialize=H)
    m.PR = pyo.Set(initialize=pairs, dimen=2)
    mp = lambda: pyo.Param(m.I, mutable=True, initialize=0.0)
    m.Pload, m.pv_av, m.cb, m.cs, m.B, m.E0 = mp(), mp(), mp(), mp(), mp(), mp()
    mh = lambda v=0.0: pyo.Param(m.H, mutable=True, initialize=v)
    m.Hq, m.Zf, m.Ze, m.u_fc_prev, m.u_el_prev, m.P_fc_prev = mh(), mh(), mh(), mh(), mh(), mh()
    m.allow_fc, m.allow_el = mh(1.0), mh(1.0)
    m.dem, m.allow_s = mh(0.0), mh(1.0)

    m.pv = pyo.Var(m.I, within=pyo.NonNegativeReals)
    m.buy = pyo.Var(m.I, within=pyo.NonNegativeReals, bounds=lambda m, i: (0, st[i]["P_tr"] + st[i]["P_ov_max"] + P_SHARE * len(I)))
    m.ov = pyo.Var(m.I, within=pyo.NonNegativeReals, bounds=lambda m, i: (0, st[i]["P_ov_max"]))
    m.sell = pyo.Var(m.I, within=pyo.NonNegativeReals, bounds=lambda m, i: (0, st[i]["P_export"]))
    m.ch = pyo.Var(m.I, bounds=lambda m, i: (0, st[i]["P_bat"]))
    m.dis = pyo.Var(m.I, bounds=lambda m, i: (0, st[i]["P_bat"]))
    m.g = pyo.Var(m.PR, bounds=(-P_SHARE, P_SHARE))      # g[a,b] = điện a chuyển cho b
    if admm_rho is not None:
        m.OP = pyo.Set(initialize=[(a, b) for (a, b) in pairs] + [(b, a) for (a, b) in pairs], dimen=2)   # chỉ các cặp được chia sẻ
        m.x = pyo.Var(m.OP, bounds=(-P_SHARE, P_SHARE))       # bản sao của trạm a: điện a chuyển cho b
        m.lam = pyo.Param(m.OP, mutable=True, initialize=0.0); m.yc = pyo.Param(m.OP, mutable=True, initialize=0.0)
        m.wpx = pyo.Var(m.OP, within=pyo.NonNegativeReals)
        m.KT = pyo.Set(initialize=sorted(set([-d for d in ADMM_TAN] + ADMM_TAN)))
        m.c_prox = pyo.Constraint(m.OP, m.KT, rule=lambda m, a, b, d: m.wpx[a, b] >= admm_rho * d * (m.x[a, b] - m.yc[a, b]) - 0.5 * admm_rho * d * d)
        for (a, b) in pairs:
            m.g[a, b].fix(0.0)                                  # không dùng trong bài con
    m.c_pv = pyo.Constraint(m.I, rule=lambda m, i: m.pv[i] <= m.pv_av[i])

    # --- H2
    m.u_fc = pyo.Var(m.H, within=pyo.Binary); m.u_el = pyo.Var(m.H, within=pyo.Binary)
    m.P_fc = pyo.Var(m.H, within=pyo.NonNegativeReals); m.P_el = pyo.Var(m.H, within=pyo.NonNegativeReals)
    SF = [(i, k) for i in H for k in range(len(st[i]["fc_seg"]))]
    SE = [(i, k) for i in H for k in range(len(st[i]["el_seg"]))]
    m.SF, m.SE = pyo.Set(initialize=SF, dimen=2), pyo.Set(initialize=SE, dimen=2)
    m.yf = pyo.Var(m.SF, within=pyo.Binary); m.pf = pyo.Var(m.SF, within=pyo.NonNegativeReals)
    m.ye = pyo.Var(m.SE, within=pyo.Binary); m.pe = pyo.Var(m.SE, within=pyo.NonNegativeReals)
    m.c_yf = pyo.Constraint(m.H, rule=lambda m, i: sum(m.yf[i, k] for k in range(len(st[i]["fc_seg"]))) == m.u_fc[i])
    m.c_ye = pyo.Constraint(m.H, rule=lambda m, i: sum(m.ye[i, k] for k in range(len(st[i]["el_seg"]))) == m.u_el[i])
    m.c_pf_lo = pyo.Constraint(m.SF, rule=lambda m, i, k: m.pf[i, k] >= st[i]["fc_seg"][k][0] * m.yf[i, k])
    m.c_pf_hi = pyo.Constraint(m.SF, rule=lambda m, i, k: m.pf[i, k] <= st[i]["fc_seg"][k][1] * m.yf[i, k])
    m.c_pe_lo = pyo.Constraint(m.SE, rule=lambda m, i, k: m.pe[i, k] >= st[i]["el_seg"][k][0] * m.ye[i, k])
    m.c_pe_hi = pyo.Constraint(m.SE, rule=lambda m, i, k: m.pe[i, k] <= st[i]["el_seg"][k][1] * m.ye[i, k])
    m.c_Pf = pyo.Constraint(m.H, rule=lambda m, i: m.P_fc[i] == sum(m.pf[i, k] for k in range(len(st[i]["fc_seg"]))))
    m.c_Pe = pyo.Constraint(m.H, rule=lambda m, i: m.P_el[i] == sum(m.pe[i, k] for k in range(len(st[i]["el_seg"]))))
    if PLANT_ON:    # hệ số đường cong là tham số đổi được (cập nhật mỗi ngày theo lão hóa đo được – A6)
        m.fsl = pyo.Param(m.SF, mutable=True, initialize=lambda m, i, k: st[i]["fc_seg"][k][2])
        m.fic = pyo.Param(m.SF, mutable=True, initialize=lambda m, i, k: st[i]["fc_seg"][k][3])
        m.esl = pyo.Param(m.SE, mutable=True, initialize=lambda m, i, k: st[i]["el_seg"][k][2])
        m.eic = pyo.Param(m.SE, mutable=True, initialize=lambda m, i, k: st[i]["el_seg"][k][3])
        m.m_fc = pyo.Expression(m.H, rule=lambda m, i: sum(m.fsl[i, k] * m.pf[i, k] + m.fic[i, k] * m.yf[i, k] for k in range(len(st[i]["fc_seg"]))))
        m.m_el = pyo.Expression(m.H, rule=lambda m, i: sum(m.esl[i, k] * m.pe[i, k] + m.eic[i, k] * m.ye[i, k] for k in range(len(st[i]["el_seg"]))))
    else:
        m.m_fc = pyo.Expression(m.H, rule=lambda m, i: sum(st[i]["fc_seg"][k][2] * m.pf[i, k] + st[i]["fc_seg"][k][3] * m.yf[i, k] for k in range(len(st[i]["fc_seg"]))))
        m.m_el = pyo.Expression(m.H, rule=lambda m, i: sum(st[i]["el_seg"][k][2] * m.pe[i, k] + st[i]["el_seg"][k][3] * m.ye[i, k] for k in range(len(st[i]["el_seg"]))))
    m.P_cp = pyo.Expression(m.H, rule=lambda m, i: E_CP * m.m_el[i] / DT)
    if DEM_ON:      # bán H2 tại chỗ: s ≤ nhu cầu bước này; khóa khi bồn gần cạn (S2')
        m.s = pyo.Var(m.H, within=pyo.NonNegativeReals)
        m.c_sale = pyo.Constraint(m.H, rule=lambda m, i: m.s[i] <= m.dem[i] * m.allow_s[i])
    # khóa thiết bị (S2), (S3)
    m.c_lock_fc = pyo.Constraint(m.H, rule=lambda m, i: m.u_fc[i] <= m.allow_fc[i])
    m.c_lock_el = pyo.Constraint(m.H, rule=lambda m, i: m.u_el[i] <= m.allow_el[i])
    # lão hóa FC: đổi tải (chỉ khi bước trước và bước này đều bật), tải thấp, tải cao
    m.dP = pyo.Var(m.H, within=pyo.NonNegativeReals)
    BigM = lambda i: st[i]["P_fc"]
    m.c_dP1 = pyo.Constraint(m.H, rule=lambda m, i: m.dP[i] >= m.P_fc[i] - m.P_fc_prev[i] - BigM(i) * (1 - m.u_fc[i]) - BigM(i) * (1 - m.u_fc_prev[i]))
    m.c_dP2 = pyo.Constraint(m.H, rule=lambda m, i: m.dP[i] >= m.P_fc_prev[i] - m.P_fc[i] - BigM(i) * (1 - m.u_fc[i]) - BigM(i) * (1 - m.u_fc_prev[i]))
    m.z_lo = pyo.Var(m.H, within=pyo.Binary)
    m.c_lo1 = pyo.Constraint(m.H, rule=lambda m, i: m.z_lo[i] <= m.u_fc[i])
    m.c_lo2 = pyo.Constraint(m.H, rule=lambda m, i: m.P_fc[i] >= st[i]["P_lo"] * (m.u_fc[i] - m.z_lo[i]))
    m.hp = pyo.Var(m.H, bounds=(0, 1))
    m.c_hp = pyo.Constraint(m.H, rule=lambda m, i: m.hp[i] >= (m.P_fc[i] - st[i]["P_hi"]) / (st[i]["P_fc"] - st[i]["P_hi"]))
    m.dD_fc = pyo.Expression(m.H, rule=lambda m, i: st[i]["fc_k_start"] * m.u_fc[i] * (1 - m.u_fc_prev[i]) + st[i]["fc_k_lc"] * m.dP[i]
                             + st[i]["fc_k_lo"] * m.z_lo[i] + st[i]["fc_k_hp"] * m.hp[i])
    m.dD_el = pyo.Expression(m.H, rule=lambda m, i: st[i]["el_k_start"] * m.u_el[i] * (1 - m.u_el_prev[i]) + st[i]["el_k_a0"] * m.u_el[i])

    # --- cân bằng công suất (1)
    def share_out(m, i):
        if admm_rho is not None:
            return sum(m.x[a, b] for (a, b) in m.OP if a == i)
        return sum(m.g[a, b] for (a, b) in pairs if a == i) - sum(m.g[a, b] for (a, b) in pairs if b == i)
    def balance(m, i):
        fcP = m.P_fc[i] if i in H else 0.0
        elP = (m.P_el[i] + m.P_cp[i]) if i in H else 0.0
        return m.pv[i] + m.buy[i] + m.dis[i] + fcP == m.Pload[i] + m.sell[i] + m.ch[i] + elP + share_out(m, i)
    m.c_bal = pyo.Constraint(m.I, rule=balance)
    # máy biến áp: luồng ròng qua MBA (mua − bán − chuyển cho trạm khác) ≤ P_tr + phần vượt có phạt
    m.c_tr_hi = pyo.Constraint(m.I, rule=lambda m, i: m.buy[i] - m.sell[i] - share_out(m, i) <= st[i]["P_tr"] + m.ov[i])
    m.c_tr_lo = pyo.Constraint(m.I, rule=lambda m, i: m.buy[i] - m.sell[i] - share_out(m, i) >= -st[i]["P_tr"])
    if GRID_ON:     # điện áp LinDistFlow: u ≥ v_min² − v_b ở MỌI nút b; phạt u (độ thiếu áp lớn nhất)
        m.NB = pyo.RangeSet(0, GRID["nb"] - 1)
        m.vbase = pyo.Param(m.NB, mutable=True, initialize=1.0)
        m.u_v = pyo.Var(within=pyo.NonNegativeReals)
        if VV_ON:   # Q của bộ biến đổi: q = q⁺ − q⁻; (P, Q) nằm trong bát giác nội tiếp đường tròn S (tuyến tính, an toàn)
            Sb = {i: S_OVER * st[i]["P_bat"] for i in I}
            m.qbp = pyo.Var(m.I, within=pyo.NonNegativeReals); m.qbn = pyo.Var(m.I, within=pyo.NonNegativeReals)
            m.K8 = pyo.RangeSet(0, 7)
            # dùng (xả + sạc) ≥ |xả − sạc|: chặt hơn một chút, nhưng bớt xả/bớt sạc thì (P, Q) vẫn trong bát giác (cần cho Mệnh đề 1)
            m.c_qb = pyo.Constraint(m.I, m.K8, rule=lambda m, i, k: math.cos(math.pi * k / 4) * (m.dis[i] + m.ch[i])
                                    + math.sin(math.pi * k / 4) * (m.qbp[i] - m.qbn[i]) <= Sb[i] * math.cos(math.pi / 8))
            m.qfp = pyo.Var(m.H, within=pyo.NonNegativeReals); m.qfn = pyo.Var(m.H, within=pyo.NonNegativeReals)
            m.c_qf = pyo.Constraint(m.H, m.K8, rule=lambda m, i, k: math.cos(math.pi * k / 4) * m.P_fc[i]
                                    + math.sin(math.pi * k / 4) * (m.qfp[i] - m.qfn[i]) <= S_OVER * st[i]["P_fc"] * math.cos(math.pi / 8))
            if not VV_FC_ALWAYS:   # FC tắt thì bộ biến đổi FC không có nguồn DC → không phát/hút Q
                m.c_qf_on = pyo.Constraint(m.H, rule=lambda m, i: m.qfp[i] + m.qfn[i] <= S_OVER * st[i]["P_fc"] * m.u_fc[i])
            m.q_inj = pyo.Expression(m.I, rule=lambda m, i: m.qbp[i] - m.qbn[i] + ((m.qfp[i] - m.qfn[i]) if i in H else 0.0))
            # MBA trạm: Q đi qua MBA = tanφ·P_qua_MBA − q_inj. Giữ |Q_MBA| ≤ tanφ·(P_tr + phần vượt/phần ngược) – tức volt–var
            # KHÔNG làm MBA nặng hơn mức Q mà chính phụ tải ở cosφ thiết kế đã gây ra lúc đầy tải. q = 0 luôn thỏa (không mất khả thi).
            tp = GRID["tanphi"]
            m.c_qtr1 = pyo.Constraint(m.I, rule=lambda m, i: tp * (m.buy[i] - m.sell[i] - share_out(m, i)) - m.q_inj[i] <= tp * (st[i]["P_tr"] + m.ov[i]))
            m.c_qtr2 = pyo.Constraint(m.I, rule=lambda m, i: m.q_inj[i] <= tp * (m.buy[i] - m.sell[i] - share_out(m, i) + st[i]["P_tr"]))   # P_MBA ≥ −P_tr (c_tr_lo) nên q = 0 luôn thỏa
        m.c_volt = pyo.Constraint(m.NB, rule=lambda m, b: m.u_v >= GRID["v2min"] - (m.vbase[b] - sum(
            GRID["K"][i][b] * (m.buy[i] - m.sell[i] - share_out(m, i)) - (GRID["Kq"][i][b] * m.q_inj[i] if VV_ON else 0.0) for i in I)))
    # --- pin (S1) và ΔE
    m.dE = pyo.Expression(m.I, rule=lambda m, i: (st[i]["eta_ch"] * m.ch[i] - m.dis[i] / st[i]["eta_dis"]) * DT)
    m.c_S1lo = pyo.Constraint(m.I, rule=lambda m, i: m.E0[i] + m.dE[i] >= st[i]["E_min"])
    m.c_S1hi = pyo.Constraint(m.I, rule=lambda m, i: m.E0[i] + m.dE[i] <= st[i]["E_max"])

    # --- hàm mục tiêu J_t
    def obj(m):
        J = V * GRID["c_v"] * m.u_v * DT if GRID_ON else 0
        if admm_rho is not None:
            J += sum(m.lam[a, b] * m.x[a, b] + m.wpx[a, b] for (a, b) in m.OP)
        if GRID_ON and VV_ON:
            J += V * C_Q * DT * (sum(m.qbp[i] + m.qbn[i] for i in I) + sum(m.qfp[i] + m.qfn[i] for i in H))
        for i in I:
            d = st[i]
            J += V * ((m.cb[i] * m.buy[i] - m.cs[i] * m.sell[i] + C_OV * m.ov[i] + C_BAT * (m.ch[i] + m.dis[i])) * DT)
            J += d["w_B"] * m.B[i] * m.dE[i]
            if i in H:
                # giá lão hóa: phần bật máy chia đều cho số bước chạy dự kiến (tham số thiết kế của μ, không ảnh hưởng bảo đảm)
                amort_fc = (1.0 / START_AMORT - 1.0) * d["fc_k_start"] * m.u_fc[i] * (1 - m.u_fc_prev[i])
                amort_el = (1.0 / START_AMORT - 1.0) * d["el_k_start"] * m.u_el[i] * (1 - m.u_el_prev[i])
                if not NO_AGING:
                    J += V * (d["mu_fc"] * (m.dD_fc[i] + amort_fc) + d["mu_el"] * (m.dD_el[i] + amort_el))
                J += d["w_H"] * m.Hq[i] * (m.m_el[i] - m.m_fc[i] - (m.s[i] if DEM_ON else 0.0))
                if DEM_ON:
                    J -= V * C_EXT * m.s[i]                       # mỗi kg bán tại chỗ = bớt 1 kg mua ngoài
                if not NO_AGING:
                    J += w_Z * (m.Zf[i] * m.dD_fc[i] + m.Ze[i] * m.dD_el[i])
        return J
    m.obj = pyo.Objective(rule=obj, sense=pyo.minimize)
    return m


def get_solver(pref):
    order = {"auto": ["appsi_gurobi", "appsi_highs"], "gurobi": ["appsi_gurobi"], "highs": ["appsi_highs"]}[pref]
    for name in order:
        try:
            s = pyo.SolverFactory(name)
            if s.available(exception_flag=False):
                if name == "appsi_highs":
                    s.config.load_solution = True
                    s.highs_options = {"mip_rel_gap": 1e-6, "output_flag": False}
                return name, s
        except Exception:
            continue
    raise SystemExit("Không tìm thấy bộ giải. Cài: pip install highspy   (hoặc gurobipy nếu có giấy phép)")


# ============================================================== vòng mô phỏng
def apply_fc_calibration(params, args):
    """Nếu có params/fc_calibration.json (từ calibrate_fc_ieee.py) thì thay đường hiệu suất FC và hệ số lão hóa bằng số đo thật."""
    global FC_X, FC_ETA, FC_CALIB_NOTE
    f = PROJECT_DIR / "params" / "fc_calibration.json"
    if args.no_fc_calib or not f.exists():
        FC_CALIB_NOTE = "FC: đường hiệu suất + hệ số lão hóa GIẢ ĐỊNH (chưa hiệu chỉnh)"
        apply_el_calibration(params, args)
        return
    cal = json.loads(f.read_text(encoding="utf-8"))
    FC_X, FC_ETA = list(cal["fc_x"]), list(cal["fc_eta_sys"])
    CAL["fc"] = _table(cal["fc_x"], cal["fc_eta_sys"], cal.get("fc_eta_sys_eol"), cal.get("D_grid"), cal.get("fc_eta_sys_D"), +1)
    fc = params["aging_and_devices"]["fc"]
    old = {k: fc.get(k) for k in cal["aging_update"]}
    fc.update(cal["aging_update"])
    FC_CALIB_NOTE = (f"FC HIỆU CHỈNH từ dữ liệu thật ({cal['source'][:45]}…): η(x={FC_X}) = {FC_ETA}; "
                     + ", ".join(f"{k}: {old[k]} → {v}" for k, v in cal["aging_update"].items()))
    apply_el_calibration(params, args)


def apply_el_calibration(params, args):
    """Nếu có params/el_calibration.json (từ calibrate_el.py) thì thay đường kWh/kg và hệ số lão hóa EL bằng số đo thật."""
    global EL_X, EL_KWHKG, FC_CALIB_NOTE
    f = PROJECT_DIR / "params" / "el_calibration.json"
    if getattr(args, "no_el_calib", False) or not f.exists():
        FC_CALIB_NOTE += "\nEL: đường kWh/kg + hệ số lão hóa GIẢ ĐỊNH (chưa hiệu chỉnh)"
        return
    cal = json.loads(f.read_text(encoding="utf-8"))
    EL_X, EL_KWHKG = list(cal["el_x"]), list(cal["el_kwh_per_kg"])
    CAL["el"] = _table(cal["el_x"], cal["el_kwh_per_kg"], cal.get("el_kwh_per_kg_eol"), cal.get("D_grid"), cal.get("el_kwh_per_kg_D"), -1)
    el = params["aging_and_devices"]["el"]
    old = {k: el.get(k) for k in cal["aging_update"]}
    el.update(cal["aging_update"])
    FC_CALIB_NOTE += (f"\nEL HIỆU CHỈNH từ dữ liệu thật ({cal['source'][:40]}…): kWh/kg(x={EL_X}) = {EL_KWHKG}; "
                      + ", ".join(f"{k}: {old[k]} → {v}" for k, v in cal["aging_update"].items()))


def run(args):
    global P_SHARE, E_CP, C_BAT
    if args.no_share:        # S3b: không chia sẻ giữa các trạm (để so công bằng với DRL, vốn không có chia sẻ)
        P_SHARE = 0.0
    sens = []                # việc 4.4: độ nhạy theo các thông số còn là giả định
    if args.p_share is not None and not args.no_share:
        P_SHARE = args.p_share; sens.append(f"giới hạn chia sẻ {P_SHARE:g} kW")
    if args.e_cp is not None:
        E_CP = args.e_cp; sens.append(f"điện máy nén {E_CP:g} kWh/kg")
    if args.c_bat is not None:
        C_BAT = args.c_bat; sens.append(f"hao mòn pin {C_BAT:g} CNY/kWh")
    params = json.loads((PROJECT_DIR / "params" / args.params).read_text(encoding="utf-8"))
    apply_fc_calibration(params, args)
    if args.fc_stack_mult != 1.0:
        params["aging_and_devices"]["fc"]["stack_cost_CNY_per_kW"] *= args.fc_stack_mult
        sens.append(f"giá stack FC × {args.fc_stack_mult:g} = {params['aging_and_devices']['fc']['stack_cost_CNY_per_kW']:,.0f} CNY/kW")
    if args.el_stack_mult != 1.0:
        params["aging_and_devices"]["el"]["stack_cost_CNY_per_kW"] *= args.el_stack_mult
        sens.append(f"giá stack EL × {args.el_stack_mult:g} = {params['aging_and_devices']['el']['stack_cost_CNY_per_kW']:,.0f} CNY/kW")
    global SHARE_K
    SHARE_K = args.share_k
    global FC_CALIB_NOTE
    # ---- độ nhạy (1.8): cỡ thiết bị H2 và tốc độ già EL
    if args.h2_scale != 1.0:
        for s_ in params["stations"]:
            if s_.get("has_h2"):
                for k in ("fc_kW", "el_kW", "tank_kg"):
                    s_[k] = s_[k] * args.h2_scale
        FC_CALIB_NOTE += f"\nĐỘ NHẠY: cỡ FC, EL, bồn ở mọi trạm H2 × {args.h2_scale:g}"
    if getattr(args, "bat_scale_h2", 1.0) != 1.0:      # việc 2.6: thay H2 bằng pin lớn hơn ở đúng các trạm H2
        for s_ in params["stations"]:
            if s_.get("has_h2"):
                s_["bat_kWh"] = s_["bat_kWh"] * args.bat_scale_h2
                s_["bat_kW"] = s_["bat_kW"] * args.bat_scale_h2
        FC_CALIB_NOTE += f"\nSO VỚI PIN: pin ở các trạm H2 (1093, 1242, 1589) × {args.bat_scale_h2:g} (giữ tỉ lệ 2 giờ)"
    if args.el_scale != 1.0:
        for s_ in params["stations"]:
            if s_.get("has_h2"):
                s_["el_kW"] = s_["el_kW"] * args.el_scale
        FC_CALIB_NOTE += f"\nĐỘ NHẠY: chỉ cỡ EL × {args.el_scale:g}"
    if args.el_a0 is not None:
        params["aging_and_devices"]["el"]["a0_uV_per_h"] = args.el_a0
        FC_CALIB_NOTE += f"\nĐỘ NHẠY: tốc độ già EL a0 = {args.el_a0:g} μV/h"
    if args.no_share:
        FC_CALIB_NOTE += "\nKHÔNG CHIA SẺ giữa các trạm (S3b)"
    if sens:
        FC_CALIB_NOTE += "\nĐỘ NHẠY 4.4: " + "; ".join(sens)
    print("[*] " + FC_CALIB_NOTE)
    inputs = pd.read_csv(PROJECT_DIR / "data_clean" / args.inputs, index_col=0, parse_dates=True)
    if args.inputs != "tier1_inputs.csv" or args.params != "params_tier1.json":
        FC_CALIB_NOTE += f"\nMẠNG KHÁC (việc 4.3): dữ liệu {args.inputs}, thông số {args.params}, {len(params['stations'])} điểm sạc" + (
            f", chia sẻ chỉ với {SHARE_K} điểm gần nhất" if SHARE_K > 0 else ", chia sẻ giữa mọi cặp")
    if args.days > 0:
        t0 = pd.Timestamp(args.start)
        inputs = inputs.loc[t0: t0 + pd.Timedelta(days=args.days) - pd.Timedelta(minutes=5)]
    T = len(inputs)
    global START_AMORT, C_OV, NO_AGING, H2_DEM_FRAC, C_EXT, FILL_KG, DISP, DEM_ON, GRID_ON, GRID, VV_ON, VV_FC_ALWAYS
    START_AMORT, C_OV, NO_AGING = args.start_amort, args.c_ov, args.no_aging
    H2_DEM_FRAC, C_EXT, FILL_KG, DISP = args.h2_demand_frac, args.c_ext, args.fill_kg, args.disp
    DEM_ON = H2_DEM_FRAC > 0
    GRID_ON = bool(args.grid33) or bool(args.volt_var)
    VV_ON = bool(args.volt_var)
    VV_FC_ALWAYS = not bool(args.vv_fc_gated)
    if GRID_ON:
        GRID = grid_setup(inputs.index, [int(s_["station_id"]) for s_ in params["stations"]], args.ev_scale, args.base_scale,
                          args.pf, args.vmin, args.v_margin, args.c_v)
        FC_CALIB_NOTE += (f"\nĐIỀU KHIỂN CÓ TÍNH LƯỚI 33 NÚT (LinDistFlow): trạm sạc × {args.ev_scale:g}, phụ tải nền × {args.base_scale:g}, "
                          f"v_min điều khiển = {args.vmin + args.v_margin:.3f} pu, phạt {args.c_v:g} CNY/(pu²·h) "
                          f"→ chi phí biên điện áp lớn nhất {GRID['cmax_add']:.2f} CNY/kWh (đã cộng vào c̄)"
                          + (f" | VOLT–VAR: bộ biến đổi pin + FC phát/hút Q, S = {S_OVER:g}×P định mức, chi phí Q {C_Q:g} CNY/kvarh, "
                             f"FC phát Q {'cả khi tắt (STATCOM)' if VV_FC_ALWAYS else 'chỉ khi đang chạy'}, |Q qua MBA| ≤ tanφ·P_MBA" if VV_ON else ""))
    DEM = {int(s_["station_id"]): h2_demand_series(s_, inputs.index, H2_DEM_FRAC) for s_ in params["stations"] if s_.get("has_h2")} if DEM_ON else {}
    if DEM_ON:
        FC_CALIB_NOTE += (f"\nBÁN H2 CHO FCEV: nhu cầu = {H2_DEM_FRAC:g} × sản lượng EL định mức/ngày, xe {FILL_KG:g} kg, ≤ {DISP} xe/5 phút; "
                          f"H2 mua ngoài {C_EXT:g} CNY/kg | nhu cầu kỳ này: " + ", ".join(f"{k}: {v.sum():.0f} kg" for k, v in DEM.items()))
    global PLANT_ON
    PLANT_ON = bool(args.plant)
    if PLANT_ON:
        CAL.setdefault("fc", _table(FC_X, FC_ETA, None, None, None, +1)); CAL.setdefault("el", _table(EL_X, EL_KWHKG, None, None, None, -1))
        PLANT.update(bias=args.mm_bias, d0=args.mm_d0, update=args.mm_update, seg=args.mm_seg, robust=not args.mm_nominal)
        FC_CALIB_NOTE += (f"\nSAI LỆCH MÔ HÌNH (việc 4.2): nhà máy = đường trơn PCHIP tại D thật (bảng D: {'có' if len(CAL['fc'][1]) > 2 else 'KHÔNG – nội suy BOL→EOL'}), "
                          f"độ lệch thêm {PLANT['bias']:+.0%} (dương: FC tốn hơn, EL ra ít hơn; âm: ngược lại); D ban đầu {PLANT['d0']:g}; bộ điều khiển "
                          f"{'các điểm hiệu chỉnh' if PLANT['seg'] <= 0 else str(PLANT['seg']) + ' đoạn đều'}, cập nhật theo lão hóa: {PLANT['update']}; "
                          f"chặn m_max: {'GIÁ TRỊ LỚN HƠN giữa hai mô hình (mục 1b)' if PLANT['robust'] else 'chỉ theo bộ điều khiển (KHÔNG an toàn – để đối chứng)'}")
    st, c_max = prepare(params, inputs, args.V, args.wz, args.pv_scale, args.export_frac, args.vref, args.tr_frac, args.no_h2)
    I = sorted(st); H = [i for i in I if st[i]["h2"]]
    m = build_model(st, args.V, args.wz)
    ADMM = args.admm > 0
    if ADMM:
        if GRID_ON:
            raise SystemExit("ADMM hiện chỉ cho bài không tính lưới (bỏ --grid33/--volt_var).")
        rho = args.admm_rho
        mD = build_model(st, args.V, args.wz, admm_rho=rho)
        _, solverD = get_solver(args.solver)
        OPS = list(mD.OP)
        lam = {e: 0.0 for e in OPS}; yv = {e: 0.0 for e in OPS}
        FIXV = ["u_fc", "u_el", "yf", "pf", "ye", "pe", "ch", "dis"] + (["s"] if DEM_ON else [])
        admm_log = []
        FC_CALIB_NOTE += (f"\nADMM PHÂN TÁN (việc 3.1–3.2): tối đa {args.admm} vòng/bước, ρ = {rho:g}, dừng khi lệch chia sẻ ≤ {args.admm_tol:g} kW; "
                          f"hạng ρ/2·(x−y)² xấp xỉ bằng {2 * len(ADMM_TAN) - 1} tiếp tuyến; sửa lệch: lấy phía nhỏ hơn (Yan & Chen) rồi chỉ chỉnh mua/bán lưới")
    sname, solver = get_solver(args.solver)
    tag = args.tag or f"{'S1noH2' if args.no_h2 else 'S3'}_V{args.V:g}_pv{args.pv_scale:g}_tr{args.tr_frac:g}_cov{args.c_ov:g}_am{args.start_amort:g}_{args.start}_{args.days}d"
    out = PROJECT_DIR / "results" / f"step3_{tag}"
    out.mkdir(parents=True, exist_ok=True)
    print(f"[*] Bộ giải: {sname} | {T} bước | kết quả: {out}")

    # trạng thái ban đầu
    if args.init == "theta":     # bắt đầu ở mức tham chiếu θ (vận hành ổn định, không có giai đoạn "nạp đầy" ban đầu)
        E = {i: st[i]["theta_B"] for i in I}
        M = {i: st[i]["theta_H"] for i in H}
    else:                        # bắt đầu ở giữa dải
        E = {i: 0.5 * (st[i]["E_min"] + st[i]["E_max"]) for i in I}
        M = {i: 0.5 * (st[i]["M_min"] + st[i]["M_max"]) for i in H}
    Zf = {i: 0.0 for i in H}; Ze = {i: 0.0 for i in H}
    Dfc = {i: 0.0 for i in H}; Del = {i: 0.0 for i in H}; Dfc_ph = {i: 0.0 for i in H}; Del_ph = {i: 0.0 for i in H}
    ufp = {i: 0 for i in H}; uep = {i: 0 for i in H}; Pfp = {i: 0.0 for i in H}
    if args.state_in:      # mô phỏng nhiều năm: nối tiếp trạng thái cuối của đoạn trước (pin, bồn, hàng đợi, mức lão hóa, bật/tắt)
        S_ = json.loads(Path(args.state_in).read_text(encoding="utf-8"))
        for name, dct in (("E", E), ("M", M), ("Zf", Zf), ("Ze", Ze), ("Dfc", Dfc), ("Del", Del), ("Dfc_ph", Dfc_ph),
                          ("Del_ph", Del_ph), ("ufp", ufp), ("uep", uep), ("Pfp", Pfp)):
            for k, v in S_[name].items():
                if int(k) in dct:
                    dct[int(k)] = v
        FC_CALIB_NOTE += f"\nNỐI TIẾP trạng thái từ {Path(args.state_in).name}: D_FC thật đầu đoạn = " + ", ".join(f"{i}: {Dfc_ph[i]:.4f}" for i in H)
    A_const = 0.5 * sum(st[i]["w_B"] * st[i]["dE_max"] ** 2 for i in I) + 0.5 * sum(
        st[i]["w_H"] * st[i]["dM_max"] ** 2 + args.wz * (max(st[i]["dD_fc_max"], st[i]["delta_fc"]) ** 2 + max(st[i]["dD_el_max"], st[i]["delta_el"]) ** 2) for i in H)

    def lyap():
        return 0.5 * (sum(st[i]["w_B"] * (E[i] - st[i]["theta_B"]) ** 2 for i in I)
                      + sum(st[i]["w_H"] * (M[i] - st[i]["theta_H"]) ** 2 + args.wz * (Zf[i] ** 2 + Ze[i] ** 2) for i in H))

    rows, solve_times, lemma1_viol = [], [], []
    tic = time.time()
    emax = {i: [0.0, 0.0] for i in H}      # sai số khối lượng lớn nhất mỗi bước (FC, EL) – e^M đo được
    for t, (ts, r) in enumerate(inputs.iterrows()):
        for mm in ([m, mD] if ADMM else [m]):
            if PLANT_ON and PLANT["update"] == "daily" and t % 288 == 0 and (t > 0 or args.state_in):   # A6: cập nhật đường cong theo D đo được
                for i in H:
                    _, fm = ctrl_points("fc", PLANT["d0"] + Dfc_ph[i], st[i]["P_fc"]); _, em = ctrl_points("el", PLANT["d0"] + Del_ph[i], st[i]["P_el"])
                    for k, sg in enumerate(pwl(st[i]["fc_x"], fm, st[i]["P_fc"])):
                        mm.fsl[i, k] = sg[2]; mm.fic[i, k] = sg[3]
                    for k, sg in enumerate(pwl(st[i]["el_x"], em, st[i]["P_el"])):
                        mm.esl[i, k] = sg[2]; mm.eic[i, k] = sg[3]
            for i in I:
                mm.Pload[i] = float(r[f"load_{i}"]); mm.pv_av[i] = float(r["pv_kw_per_kwp"]) * st[i]["pv_kWp"]
                cb = float(r[f"price_{i}"]); mm.cb[i] = cb; mm.cs[i] = min(C_FIT, min(float(r[f"price_{j}"]) for j in I))
                mm.B[i] = E[i] - st[i]["theta_B"]; mm.E0[i] = E[i]
            for i in H:
                mm.Hq[i] = M[i] - st[i]["theta_H"]; mm.Zf[i] = Zf[i]; mm.Ze[i] = Ze[i]
                mm.u_fc_prev[i] = ufp[i]; mm.u_el_prev[i] = uep[i]; mm.P_fc_prev[i] = Pfp[i]
                mm.allow_fc[i] = 0.0 if M[i] < st[i]["M_min"] + st[i]["m_fc_max"] else 1.0   # (S2)
                mm.allow_el[i] = 0.0 if M[i] > st[i]["M_max"] - st[i]["m_el_max"] else 1.0   # (S3)
                if DEM_ON:
                    mm.dem[i] = float(DEM[i][t])
                    mm.allow_s[i] = 0.0 if M[i] < st[i]["M_min"] + st[i]["m_fc_max"] + st[i]["s_max"] else 1.0   # (S2')
            if GRID_ON:
                for b in range(GRID["nb"]):
                    mm.vbase[b] = float(GRID["vbase"][b, t])
        s0 = time.time()
        if ADMM:
            for vn in FIXV + ["g"]:                                 # bước trước đã khóa → mở ra để giải bài tập trung tham chiếu
                for v in getattr(m, vn).values():
                    if v.fixed:
                        v.unfix()
        res = solver.solve(m)
        tc = str(res.solver.termination_condition).split(".")[-1]
        if tc != "optimal":
            raise SystemExit(f"Bước {t} ({ts}): bộ giải báo {tc}")
        if ADMM:
            J_star = pyo.value(m.obj); t_c = time.time() - s0; s1 = time.time()
            it, conv = 0, False
            for it in range(1, args.admm + 1):
                for e in OPS:
                    mD.lam[e] = lam[e]; mD.yc[e] = yv[e]
                rD = solverD.solve(mD)
                if str(rD.solver.termination_condition).split(".")[-1] != "optimal":
                    raise SystemExit(f"Bước {t}: bài con ADMM không giải được")
                xv = {e: pyo.value(mD.x[e]) for e in OPS}
                yold = dict(yv)
                for (a, b) in m.PR:                                  # điều phối viên: nghiệm đóng (52) của Yan & Chen
                    ya = 0.5 * ((xv[a, b] - xv[b, a]) + (lam[a, b] - lam[b, a]) / rho)
                    yv[a, b], yv[b, a] = ya, -ya
                for e in OPS:
                    lam[e] += rho * (xv[e] - yv[e])
                r_pri = max(abs(xv[a, b] + xv[b, a]) for (a, b) in m.PR)
                r_dua = max(abs(yv[e] - yold[e]) for e in OPS)
                if r_pri <= args.admm_tol and r_dua <= args.admm_tol:
                    conv = True
                    break
            # sửa lệch (a): lấy phía nhỏ hơn; (b): khóa EL, FC, pin, bán H2 theo bài con, chỉ chỉnh mua/bán/cắt PV
            for (a, b) in m.PR:
                pa, pb = xv[a, b], -xv[b, a]
                m.g[a, b].fix(np.sign(pa) * min(abs(pa), abs(pb)) if pa * pb > 0 else 0.0)
            for vn in FIXV:
                for idx, v in getattr(m, vn).items():
                    val = pyo.value(getattr(mD, vn)[idx])
                    if v.is_binary():
                        val = round(val)
                    else:
                        lb, ub = v.bounds
                        val = max(lb if lb is not None else -np.inf, min(ub if ub is not None else np.inf, val))
                    v.fix(val)
            def try_solve():
                try:
                    return str(solver.solve(m).solver.termination_condition).split(".")[-1] == "optimal"
                except RuntimeError:          # appsi báo lỗi khi không khả thi
                    return False
            level = "b"
            # thứ tự sửa lệch: (b) chỉ mua/bán → điều phối viên chọn lại chia sẻ → thêm pin → thêm công suất FC/EL (giữ bật/tắt)
            # → giải lại tập trung (tính là thất bại của ADMM)
            for nxt, free in (("chia_se", ("g",)), ("pin", ("ch", "dis")), ("cong_suat", ("pf", "pe") + (("s",) if DEM_ON else ())),
                              ("tap_trung", ("u_fc", "u_el", "yf", "ye"))):
                if try_solve():
                    break
                level = nxt
                for vn in free:
                    for v in getattr(m, vn).values():
                        v.unfix()
            else:
                if not try_solve():
                    raise SystemExit(f"Bước {t}: sửa lệch ADMM không khả thi")
            eps = pyo.value(m.obj) - J_star
            admm_log.append((it, conv, max(r_pri, 0.0), eps, J_star, level, time.time() - s1, t_c))
        solve_times.append(time.time() - s0)

        L0 = lyap()
        rhs = A_const
        row = {"time": ts, "obj": pyo.value(m.obj)}
        cost = 0.0
        for i in I:
            dE = pyo.value(m.dE[i]); B = E[i] - st[i]["theta_B"]
            rhs += st[i]["w_B"] * B * dE
            buy, sell = pyo.value(m.buy[i]), pyo.value(m.sell[i])
            ov = pyo.value(m.ov[i])
            c_i = (pyo.value(m.cb[i]) * buy - pyo.value(m.cs[i]) * sell + C_OV * ov + C_BAT * (pyo.value(m.ch[i]) + pyo.value(m.dis[i]))) * DT
            shout = sum(pyo.value(m.g[a, b]) for (a, b) in m.PR if a == i) - sum(pyo.value(m.g[a, b]) for (a, b) in m.PR if b == i)
            row[f"ov_{i}"] = ov; row[f"trflow_{i}"] = buy - sell - shout; row[f"share_out_{i}"] = shout
            row.update({f"buy_{i}": buy, f"sell_{i}": sell, f"pv_{i}": pyo.value(m.pv[i]), f"pvav_{i}": pyo.value(m.pv_av[i]),
                        f"ch_{i}": pyo.value(m.ch[i]), f"dis_{i}": pyo.value(m.dis[i]), f"E_{i}": E[i], f"load_{i}": pyo.value(m.Pload[i])})
            E[i] = E[i] + dE
            if i in H:
                d = st[i]
                ufc, uel = round(pyo.value(m.u_fc[i])), round(pyo.value(m.u_el[i]))
                Pf, Pe = pyo.value(m.P_fc[i]), pyo.value(m.P_el[i])
                mf, me = pyo.value(m.m_fc[i]), pyo.value(m.m_el[i])
                if PLANT_ON:    # nhà máy thật: khối lượng theo đường trơn tại D thật; bồn và hàng đợi dùng giá trị ĐO ĐƯỢC
                    mf_c, me_c = mf, me
                    mf = plant_mass("fc", Pf, d["P_fc"], PLANT["d0"] + Dfc_ph[i]) if ufc else 0.0
                    me = plant_mass("el", Pe, d["P_el"], PLANT["d0"] + Del_ph[i]) if uel else 0.0
                    emax[i][0] = max(emax[i][0], abs(mf - mf_c)); emax[i][1] = max(emax[i][1], abs(me - me_c))
                    row.update({f"mfc_ctrl_{i}": mf_c, f"mel_ctrl_{i}": me_c})
                    c_i += pyo.value(m.cb[i]) * E_CP * (me - me_c)       # máy nén nén lượng H2 THẬT: phần điện chênh mua/bớt mua từ lưới
                dDf, dDe = pyo.value(m.dD_fc[i]), pyo.value(m.dD_el[i])
                Hq = M[i] - d["theta_H"]
                sl = pyo.value(m.s[i]) if DEM_ON else 0.0
                rhs += d["w_H"] * Hq * (me - mf - sl) + args.wz * (Zf[i] * (dDf - d["delta_fc"]) + Ze[i] * (dDe - d["delta_el"]))
                c_i += d["mu_fc"] * dDf + d["mu_el"] * dDe
                if DEM_ON:
                    c_i += C_EXT * (float(DEM[i][t]) - sl)          # phần nhu cầu phải mua ngoài
                    row.update({f"h2dem_{i}": float(DEM[i][t]), f"h2sale_{i}": sl})
                # lão hóa thật (Bổ đề 0): FC k_ss lúc bật và lúc tắt; EL a_sd lúc tắt
                ph_fc = dDf - d["fc_k_start"] * ufc * (1 - ufp[i]) + d["fc_k_stop_phys"] * (ufc * (1 - ufp[i]) + ufp[i] * (1 - ufc))
                ph_el = dDe - d["el_k_start"] * uel * (1 - uep[i]) + d["el_k_start"] * uep[i] * (1 - uel)
                row.update({f"ufc_{i}": ufc, f"uel_{i}": uel, f"Pfc_{i}": Pf, f"Pel_{i}": Pe, f"mfc_{i}": mf, f"mel_{i}": me,
                            f"Pcp_{i}": pyo.value(m.P_cp[i]), f"M_{i}": M[i], f"Zfc_{i}": Zf[i], f"Zel_{i}": Ze[i],
                            f"Dfc_{i}": Dfc[i], f"Del_{i}": Del[i], f"Dfc_phys_{i}": Dfc_ph[i], f"Del_phys_{i}": Del_ph[i],
                            f"dDfc_{i}": dDf, f"dDel_{i}": dDe})
                M[i] += me - mf - sl
                Dfc[i] += dDf; Del[i] += dDe; Dfc_ph[i] += ph_fc; Del_ph[i] += ph_el
                Zf[i] = max(Zf[i] + dDf - d["delta_fc"], 0.0); Ze[i] = max(Ze[i] + dDe - d["delta_el"], 0.0)
                ufp[i], uep[i], Pfp[i] = ufc, uel, Pf
            if DEM_ON and i in DEM and i not in H:              # trạm có nhu cầu H2 nhưng không có H2 tại chỗ (S1, pin…): mua ngoài toàn bộ
                c_i += C_EXT * float(DEM[i][t]); row[f"h2dem_{i}"] = float(DEM[i][t]); row[f"h2sale_{i}"] = 0.0
            cost += c_i
        if GRID_ON:
            uv = pyo.value(m.u_v)
            row["u_v"] = uv; row["vpen"] = GRID["c_v"] * uv * DT      # ghi riêng, KHÔNG cộng vào K2 (để so được với bản cũ)
            if VV_ON:
                for i in I:
                    row[f"q_{i}"] = pyo.value(m.q_inj[i])                # kvar PHÁT lên lưới (âm = hút)
        row["cost"] = cost
        if ADMM:
            it, conv, rp, eps, Js, level, tA, tC = admm_log[-1]
            row.update({"admm_iter": it, "admm_conv": int(conv), "admm_res": rp, "admm_eps": eps, "J_star": Js, "admm_repair": level})
        L1 = lyap()
        lemma1_viol.append(L1 - L0 - rhs)          # Bổ đề 1: phải ≤ 0
        row["lemma1_slack"] = L1 - L0 - rhs
        rows.append(row)
        if (t + 1) % 288 == 0:
            print(f"  ngày {(t + 1) // 288}: {time.time() - tic:.0f} s, giải TB {np.mean(solve_times):.3f} s/bước")

    df = pd.DataFrame(rows).set_index("time")
    if args.light:          # mô phỏng nhiều năm: chỉ ghi các cột cần cho phân tích lão hóa (file nhỏ hơn ~10 lần)
        keep = [c for c in df.columns if c.split("_")[0] in ("Dfc", "Del", "Zfc", "Zel", "M", "ufc", "uel", "Pfc", "Pel", "cost", "ov")]
        df[keep].round(7).to_csv(out / "timeseries.csv")
    else:
        df.round(6).to_csv(out / "timeseries.csv")
    args._emax, args._Mend = emax, dict(M)
    args._pbar = float(inputs[[c for c in inputs.columns if c.startswith("price_")]].to_numpy().mean())   # giá mua TB kỳ này
    args._admm = admm_log if ADMM else None
    if args.state_out:
        Path(args.state_out).write_text(json.dumps({n: {str(k): float(v) for k, v in d.items()} for n, d in (
            ("E", E), ("M", M), ("Zf", Zf), ("Ze", Ze), ("Dfc", Dfc), ("Del", Del), ("Dfc_ph", Dfc_ph), ("Del_ph", Del_ph),
            ("ufp", ufp), ("uep", uep), ("Pfp", Pfp))}), encoding="utf-8")
    report(df, st, I, H, args, sname, solve_times, lemma1_viol, out, T, Zf, Ze, Dfc, Del, Dfc_ph, Del_ph, E, M, c_max)


# ============================================================== báo cáo + kiểm chứng
def report(df, st, I, H, args, sname, solve_times, lemma1_viol, out, T, Zf, Ze, Dfc, Del, Dfc_ph, Del_ph, E, M, c_max):
    L = []
    ok = lambda b: "ĐẠT" if b else "KHÔNG ĐẠT"
    L.append(f"BƯỚC 3 – {'S1 (không H2)' if args.no_h2 else ('B0 (Lyapunov KHÔNG tính lão hóa)' if args.no_aging else 'S3 (đề xuất)')} – {T} bước ({T * DT / 24:.1f} ngày) từ {df.index[0]} | V = {args.V} | w_Z = {args.wz:.0e} | PV ×{args.pv_scale:g} | MBA = {args.tr_frac:g}×đỉnh | phạt vượt {args.c_ov:g} CNY/kWh | chia giá bật máy {args.start_amort:g} bước | bán lưới ≤ {args.export_frac:g}·P_tr | mức ban đầu: {args.init} | bộ giải: {sname}")
    L.append(FC_CALIB_NOTE)
    L.append(f"Thời gian giải: TB {np.mean(solve_times):.3f} s/bước, max {np.max(solve_times):.3f} s (bước thật dài 300 s)\n")
    if getattr(args, "_admm", None):
        A = args._admm
        its = np.array([a[0] for a in A]); cv = np.array([a[1] for a in A]); eps = np.array([a[3] for a in A]); Js = np.array([a[4] for a in A])
        tA = np.array([a[6] for a in A]); nrep = sum(a[5] != "b" for a in A)
        L.append(f"K8 – ADMM: hội tụ (lệch chia sẻ ≤ {args.admm_tol:g} kW) ở {100 * cv.mean():.1f}% số bước; số vòng TB {its.mean():.1f}, trung vị {np.median(its):.0f}, max {its.max()}; "
                 f"thời gian ADMM TB {tA.mean():.2f} s/bước (cả 7 trạm giải chung; song song thì ≈ {tA.mean() / len(I):.2f} s/bước)")
        L.append(f"     sai số tối ưu đo được ε_t = J(ũ) − min P3: TB {eps.mean():.4g}, trung vị {np.median(eps):.4g}, max {eps.max():.4g} (đơn vị J) | "
                 f"so với |J*| TB {np.mean(np.abs(Js)):.4g}: {100 * eps.mean() / max(np.mean(np.abs(Js)), 1e-12):.3f}% | "
                 f"ε = 0 (đúng tối ưu) ở {100 * np.mean(eps <= 1e-6 * np.maximum(1, np.abs(Js))):.1f}% số bước | sửa lệch phải nới thêm: " + ", ".join(f"{k} {sum(x[5] == k for x in A)} bước" for k in ("chia_se", "pin", "cong_suat", "tap_trung")) + "\n")
    L.append("THÔNG SỐ CHÍNH MỖI TRẠM")
    for i in I:
        d = st[i]
        s = f"  {i}: PV {d['pv_kWp']:.0f} kWp, MBA {d['P_tr']:.0f} kW, pin {d['E_cap']:.0f} kWh/{d['P_bat']:.0f} kW, w_B={d['w_B']:.3g}, θ^B={d['theta_B']:.1f} kWh"
        if d["h2"]:
            s += (f" | FC {d['P_fc']:.0f} kW, EL {d['P_el']:.0f} kW, bồn {d['M_cap']:.0f} kg, w_H={d['w_H']:.3g}, θ^H={d['theta_H']:.1f} kg,"
                  f" η_peak={d['eta_peak']:.3f}, Z_max(FC/EL)={d['Zmax_fc']:.4f}/{d['Zmax_el']:.4f}")
        L.append(s)
    L.append("\nKIỂM CHỨNG LÝ THUYẾT")
    v1 = max(lemma1_viol)
    L.append(f"  Bổ đề 1 (L_t+1 − L_t ≤ A + ...): vi phạm lớn nhất = {v1:.3e}  → {ok(v1 <= 1e-6 * max(1, abs(np.mean(lemma1_viol))))}")
    for i in I:
        e = df[f"E_{i}"]
        L.append(f"  Mệnh đề 1 – pin {i}: E ∈ [{e.min():.2f}, {e.max():.2f}] so với giới hạn [{st[i]['E_min']:.1f}, {st[i]['E_max']:.1f}]  → {ok(e.min() >= st[i]['E_min'] - 1e-6 and e.max() <= st[i]['E_max'] + 1e-6)}")
    for i in H:
        d = st[i]; mm = pd.concat([df[f"M_{i}"], pd.Series([args._Mend[i]])])     # gồm cả mức bồn cuối kỳ
        L.append(f"  Mệnh đề 1 – bồn {i}: M ∈ [{mm.min():.3f}, {mm.max():.3f}] kg so với [{d['M_min']:.2f}, {d['M_max']:.2f}]  → {ok(mm.min() >= d['M_min'] - 1e-6 and mm.max() <= d['M_max'] + 1e-6)}")
        zf, ze = max(df[f"Zfc_{i}"].max(), Zf[i]), max(df[f"Zel_{i}"].max(), Ze[i])
        if NO_AGING:
            L.append(f"  Bổ đề 3 – trạm {i}: không áp dụng (baseline không có hàng đợi sức khỏe) | max Z_FC = {zf:.3e} (cận của bản đề xuất {d['Zmax_fc']:.3e}), max Z_EL = {ze:.3e}")
        else:
            L.append(f"  Bổ đề 3 – trạm {i}: max Z_FC = {zf:.3e} (≤ {d['Zmax_fc']:.3e}: {ok(zf <= d['Zmax_fc'])}),  max Z_EL = {ze:.3e} (≤ {d['Zmax_el']:.3e}: {ok(ze <= d['Zmax_el'])})")
        tol = lambda v: 1e-12 + 1e-9 * abs(v)          # sai số làm tròn số thực (tương đối) – tổng của hàng chục nghìn bước
        # trong đoạn này (đoạn nối tiếp: trừ mức đầu đoạn; Bổ đề 2 cho đoạn: ΣΔD ≤ δT + Z_cuối − Z_đầu)
        f0, e0 = float(df[f"Dfc_{i}"].iloc[0]), float(df[f"Del_{i}"].iloc[0]); zf0, ze0 = float(df[f"Zfc_{i}"].iloc[0]), float(df[f"Zel_{i}"].iloc[0])
        sf, se = Dfc[i] - f0, Del[i] - e0
        rf, re_ = d["delta_fc"] * T + Zf[i] - zf0, d["delta_el"] * T + Ze[i] - ze0
        b2f = sf <= rf + tol(Dfc[i]); b2e = se <= re_ + tol(Del[i])
        L.append(f"  Bổ đề 2 – trạm {i}: ΣΔD_FC = {sf:.3e} ≤ δT + Z = {rf:.3e}: {ok(b2f)};  EL: {se:.3e} ≤ {re_:.3e}: {ok(b2e)}")
        L.append(f"  Bổ đề 0 – trạm {i}: lão hóa thật ≤ lão hóa tính: FC {Dfc_ph[i]:.3e} ≤ {Dfc[i]:.3e}: {ok(Dfc_ph[i] <= Dfc[i] + tol(Dfc[i]))};  EL {Del_ph[i]:.3e} ≤ {Del[i]:.3e}: {ok(Del_ph[i] <= Del[i] + tol(Del[i]))}")

    L.append("\nCHỈ SỐ (mục 9 file Word)")
    tot_cost = df["cost"].sum()
    load_e = sum(df[f"load_{i}"].sum() for i in I) * DT
    buy_e = sum(df[f"buy_{i}"].sum() for i in I) * DT; sell_e = sum(df[f"sell_{i}"].sum() for i in I) * DT
    pv_av = sum(df[f"pvav_{i}"].sum() for i in I) * DT; pv_use = sum(df[f"pv_{i}"].sum() for i in I) * DT
    L.append(f"  K2 – chi phí (gồm giá lão hóa): {tot_cost:,.0f} CNY | trên mỗi kWh sạc: {tot_cost / load_e:.4f} CNY/kWh")
    # K1/K2 hiệu chỉnh cuối kỳ: năng lượng còn "cất" trong pin, bồn so với đầu kỳ, quy ra tiền theo giá mua TB (mức lấy lại được)
    pb = getattr(args, "_pbar", 0.0)
    vE = sum((E[i] - float(df[f"E_{i}"].iloc[0])) * st[i]["eta_dis"] for i in I)
    vM = sum((args._Mend[i] - float(df[f"M_{i}"].iloc[0])) * st[i]["eta_peak"] * LHV for i in H)
    L.append(f"  K2 hiệu chỉnh cuối kỳ: {tot_cost - pb * (vE + vM):,.0f} CNY (pin cuối − đầu: {vE:+,.0f} kWh, bồn cuối − đầu: {vM:+,.0f} kWh điện "
             f"lấy lại được, tính giá TB {pb:.3f} CNY/kWh; chênh {100 * pb * (vE + vM) / max(tot_cost, 1e-9):+.2f}% so với K2)")
    L.append(f"  Điện sạc xe: {load_e / 1000:,.1f} MWh | mua lưới: {buy_e / 1000:,.1f} MWh | bán lưới: {sell_e / 1000:,.1f} MWh")
    L.append(f"  K5 – cắt PV: {100 * (1 - pv_use / max(pv_av, 1e-9)):.2f}% (PV khả dụng {pv_av / 1000:,.1f} MWh)")
    ov_e = sum(df[f"ov_{i}"].sum() for i in I) * DT
    ov_steps = int((sum(df[f"ov_{i}"] for i in I) > 1e-6).sum())
    peak_util = max((df[f"trflow_{i}"] / st[i]["P_tr"]).max() for i in I)
    L.append(f"  K6 – lưới: vượt giới hạn MBA {ov_e / 1000:,.2f} MWh ({100 * ov_e / load_e:.2f}% điện sạc), {ov_steps * DT:.1f} giờ có vượt; tải MBA lớn nhất {100 * peak_util:.0f}% định mức")
    L.append(f"       chi phí phạt vượt tải: {C_OV * ov_e:,.0f} CNY")
    L.append("       theo từng trạm (vượt MWh | giờ vượt | tải MBA lớn nhất | FC phát lúc đang vượt MWh):")
    for i in I:
        ovi = df[f"ov_{i}"]; hot = ovi > 1e-6
        fc_hot = (df[f"Pfc_{i}"][hot].sum() * DT / 1000) if st[i]["h2"] else float("nan")
        L.append(f"         {i}{' (H2)' if st[i]['h2'] else '     '}: {ovi.sum() * DT / 1000:6.2f} | {hot.sum() * DT:5.1f} h | "
                 f"{100 * (df[f'trflow_{i}'] / st[i]['P_tr']).max():4.0f}% | {fc_hot:.2f}")
    for i in H:
        d = st[i]
        mf, me = df[f"mfc_{i}"].sum(), df[f"mel_{i}"].sum()
        efc = df[f"Pfc_{i}"].sum() * DT; eel = (df[f"Pel_{i}"].sum() + df[f"Pcp_{i}"].sum()) * DT
        rt = (me / mf) * efc / eel if mf > 1e-9 and eel > 1e-9 else float("nan")
        n_fc = int((df[f"ufc_{i}"].diff().fillna(df[f"ufc_{i}"]) == 1).sum()); n_el = int((df[f"uel_{i}"].diff().fillna(df[f"uel_{i}"]) == 1).sum())
        dfs, des = Dfc[i] - float(df[f"Dfc_{i}"].iloc[0]), Del[i] - float(df[f"Del_{i}"].iloc[0])
        life_fc = T * DT / dfs / 8760 if dfs > 0 else float("inf"); life_el = T * DT / des / 8760 if des > 0 else float("inf")
        L.append(f"  Trạm {i}: H2 làm ra {me:.1f} kg, dùng {mf:.1f} kg | FC chạy {100 * df[f'ufc_{i}'].mean():.1f}% thời gian, bật {n_fc} lần |"
                 f" EL chạy {100 * df[f'uel_{i}'].mean():.1f}%, bật {n_el} lần | hiệu suất vòng thực K3 = {rt:.3f}")
        L.append(f"           K7 – tuổi thọ dự kiến theo tốc độ kỳ này: FC {life_fc:.1f} năm, EL {life_el:.1f} năm (mục tiêu 5 năm)")
    pct = lambda a, b: f"{100 * (a / b - 1):+.1f}%" if b > 1e-6 else "—"
    if PLANT_ON:
        L.append(f"  K12 – SAI LỆCH MÔ HÌNH (việc 4.2): bộ điều khiển {'các điểm hiệu chỉnh' if PLANT['seg'] <= 0 else str(PLANT['seg']) + ' đoạn'}, "
                 f"cập nhật {PLANT['update']}, D ban đầu {PLANT['d0']:g}, độ lệch {PLANT['bias']:+.0%}, chặn m_max {'an toàn' if PLANT['robust'] else 'danh định'}")
        for i in H:
            d = st[i]
            sf, se = df[f"mfc_{i}"].sum(), df[f"mel_{i}"].sum()
            cf, ce = df[f"mfc_ctrl_{i}"].sum(), df[f"mel_ctrl_{i}"].sum()
            mm = pd.concat([df[f"M_{i}"], pd.Series([args._Mend[i]])])
            L.append(f"         trạm {i}: e^M đo được FC {args._emax[i][0]:.4f} / EL {args._emax[i][1]:.4f} kg/bước "
                     f"(= {100 * args._emax[i][0] / d['m_fc_max']:.1f}% / {100 * args._emax[i][1] / d['m_el_max']:.1f}% của m_max) | "
                     f"H2 FC dùng thật {sf:.1f} so với dự đoán {cf:.1f} kg ({pct(sf, cf)}), EL làm ra thật {se:.1f} so với {ce:.1f} kg "
                     f"({pct(se, ce)}) | khoảng cách nhỏ nhất tới đáy bồn {mm.min() - d['M_min']:.3f} kg, tới đỉnh {d['M_max'] - mm.max():.3f} kg")
    if "u_v" in df.columns:
        uv = df["u_v"]
        L.append(f"  K11 – ĐIỆN ÁP (LinDistFlow, trong bộ điều khiển): {(uv > 1e-9).sum() * DT:.1f} giờ dự báo thiếu áp (< v_min điều khiển), "
                 f"thiếu áp lớn nhất {uv.max():.4f} pu², phạt {df['vpen'].sum():,.0f} CNY (KHÔNG gồm trong K2) – đánh giá AC thật bằng grid33_eval.py")
    dem_cols = [c for c in df.columns if c.startswith("h2dem_")]
    if dem_cols:
        L.append(f"  K10 – BÁN H2 CHO FCEV (giá H2 mua ngoài {C_EXT:g} CNY/kg):")
        tot_d = tot_s = 0.0
        for c in dem_cols:
            i = c.split("_")[1]
            dd, ss = df[c].sum(), df[f"h2sale_{i}"].sum(); tot_d += dd; tot_s += ss
            L.append(f"         trạm {i}: nhu cầu {dd:,.0f} kg | bán từ H2 tự làm {ss:,.0f} kg ({100 * ss / max(dd, 1e-9):.0f}%) | mua ngoài {dd - ss:,.0f} kg = {C_EXT * (dd - ss):,.0f} CNY")
        L.append(f"         tổng: nhu cầu {tot_d:,.0f} kg, tự đáp ứng {100 * tot_s / max(tot_d, 1e-9):.0f}%, tiền mua H2 ngoài {C_EXT * (tot_d - tot_s):,.0f} CNY (đã gồm trong K2)")
    txt = "\n".join(L)
    (out / "summary.txt").write_text(txt, encoding="utf-8")
    print(txt)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(len(H), 2, figsize=(12, 3 * len(H)), squeeze=False)
        for r, i in enumerate(H):
            d = st[i]
            ax[r, 0].plot(df.index, df[f"M_{i}"], lw=0.8); ax[r, 0].axhline(d["M_min"], c="r", ls="--"); ax[r, 0].axhline(d["M_max"], c="r", ls="--")
            ax[r, 0].axhline(d["theta_H"], c="gray", ls=":"); ax[r, 0].set_title(f"Bồn H2 trạm {i} (kg)")
            ax[r, 1].plot(df.index, df[f"E_{i}"], lw=0.8); ax[r, 1].axhline(d["E_min"], c="r", ls="--"); ax[r, 1].axhline(d["E_max"], c="r", ls="--")
            ax[r, 1].axhline(d["theta_B"], c="gray", ls=":"); ax[r, 1].set_title(f"Pin trạm {i} (kWh)")
        plt.tight_layout(); plt.savefig(out / "fig_prop1_tank_battery.png", dpi=100); plt.close()
        fig, ax = plt.subplots(len(H), 1, figsize=(12, 2.6 * len(H)), squeeze=False)
        for r, i in enumerate(H):
            d = st[i]
            ax[r, 0].plot(df.index, df[f"Dfc_{i}"], label="D_FC (tính)"); ax[r, 0].plot(df.index, df[f"Dfc_phys_{i}"], ls="--", label="D_FC (thật)")
            ax[r, 0].plot(df.index, d["delta_fc"] * np.arange(1, len(df) + 1), c="k", ls=":", label="kế hoạch δt")
            ax[r, 0].plot(df.index, df[f"Del_{i}"], label="D_EL"); ax[r, 0].set_title(f"Lão hóa tích lũy trạm {i}"); ax[r, 0].legend(fontsize=7)
        plt.tight_layout(); plt.savefig(out / "fig_prop2_aging.png", dpi=100); plt.close()
    except Exception as e:
        print("(Không vẽ được hình:", e, ")")
    print(f"\nĐã ghi: {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7, help="số ngày mô phỏng (0 = toàn bộ)")
    ap.add_argument("--start", default="2022-11-01")
    ap.add_argument("--V", type=float, default=1.0)
    ap.add_argument("--wz", type=float, default=1e10)
    ap.add_argument("--solver", default="highs", choices=["auto", "gurobi", "highs"], help="mặc định HiGHS để mọi kết quả cùng một bộ giải (có cài gurobipy cũng không tự đổi)")
    ap.add_argument("--tag", default=None)
    ap.add_argument("--pv_scale", type=float, default=2.0, help="nhân cỡ PV (1 = PV bằng phụ tải TB)")
    ap.add_argument("--tr_frac", type=float, default=0.6, help="giới hạn máy biến áp = tr_frac × phụ tải đỉnh của trạm")
    ap.add_argument("--c_ov", type=float, default=5.0, help="phạt nhập vượt giới hạn MBA (CNY/kWh)")
    ap.add_argument("--h2_scale", type=float, default=1.0, help="độ nhạy: nhân cỡ FC, EL, bồn ở các trạm H2")
    ap.add_argument("--el_scale", type=float, default=1.0, help="độ nhạy: nhân riêng cỡ máy điện phân EL")
    ap.add_argument("--grid33", action="store_true", help="việc 3.3b: điều khiển có tính điện áp lưới IEEE 33 nút (LinDistFlow)")
    ap.add_argument("--ev_scale", type=float, default=0.35, help="lưới 33 nút: nhân công suất trạm sạc (giống grid33_eval.py)")
    ap.add_argument("--base_scale", type=float, default=0.55, help="lưới 33 nút: phụ tải nền × hệ số (0,55 = lớn nhất mà lưới KHÔNG trạm sạc vẫn ≥ 0,95 pu)")
    ap.add_argument("--pf", type=float, default=0.98)
    ap.add_argument("--vmin", type=float, default=0.95)
    ap.add_argument("--v_margin", type=float, default=0.01, help="biên an toàn vì LinDistFlow bỏ qua tổn thất (lạc quan)")
    ap.add_argument("--light", action="store_true", help="chỉ ghi các cột lão hóa/bồn/chi phí vào timeseries.csv")
    ap.add_argument("--state_in", default=None, help="mô phỏng nhiều năm: file trạng thái đầu đoạn (json)")
    ap.add_argument("--state_out", default=None, help="mô phỏng nhiều năm: ghi trạng thái cuối đoạn (json)")
    ap.add_argument("--e_cp", type=float, default=None, help="việc 4.4: điện máy nén kWh/kg (mặc định 2,5)")
    ap.add_argument("--c_bat", type=float, default=None, help="việc 4.4: hao mòn pin CNY/kWh (mặc định 0,05)")
    ap.add_argument("--p_share", type=float, default=None, help="việc 4.4: giới hạn chia sẻ mỗi cặp, kW (mặc định 300)")
    ap.add_argument("--fc_stack_mult", type=float, default=1.0, help="việc 4.4: nhân giá thay stack FC")
    ap.add_argument("--el_stack_mult", type=float, default=1.0, help="việc 4.4: nhân giá thay stack EL")
    ap.add_argument("--inputs", default="tier1_inputs.csv", help="file dữ liệu trong data_clean (việc 4.3: scale50_inputs.csv)")
    ap.add_argument("--params", default="params_tier1.json", help="file thông số trong params (việc 4.3: params_scale50.json)")
    ap.add_argument("--share_k", type=int, default=0, help="chỉ chia sẻ với K điểm gần nhất (0 = mọi cặp)")
    ap.add_argument("--no_share", action="store_true", help="không cho các trạm chia sẻ điện (kịch bản S3b)")
    ap.add_argument("--admm", type=int, default=0, help="việc 3.1–3.2: số vòng ADMM tối đa mỗi bước (0 = giải tập trung như cũ)")
    ap.add_argument("--admm_rho", type=float, default=1e-3, help="hệ số phạt ρ của ADMM (đơn vị J/kW²)")
    ap.add_argument("--admm_tol", type=float, default=2.0, help="dừng khi lệch chia sẻ hai phía và thay đổi y đều ≤ tol (kW)")
    ap.add_argument("--plant", action="store_true", help="việc 4.2: nhà máy dùng đường hiệu suất trơn tại D thật, khác mô hình của bộ điều khiển")
    ap.add_argument("--mm_seg", type=int, default=0, help="số đoạn của đường tuyến tính trong bộ điều khiển (0 = các điểm hiệu chỉnh)")
    ap.add_argument("--mm_update", choices=["daily", "none"], default="daily", help="bộ điều khiển cập nhật đường cong theo lão hóa đo được mỗi ngày (A6) hay không")
    ap.add_argument("--mm_d0", type=float, default=0.0, help="mức lão hóa ban đầu của FC và EL (0 = máy mới)")
    ap.add_argument("--mm_bias", type=float, default=0.0, help="độ lệch thêm của nhà máy: dương = FC tốn H2 hơn, EL làm ra ít hơn (dồn bồn về đáy); âm = ngược lại (dồn bồn lên đỉnh)")
    ap.add_argument("--mm_nominal", action="store_true", help="ĐỐI CHỨNG: chặn m_max chỉ theo bộ điều khiển (không lấy giá trị lớn hơn giữa hai mô hình)")
    ap.add_argument("--volt_var", action="store_true", help="bộ biến đổi pin + FC phát Q đỡ điện áp (tự bật --grid33)")
    ap.add_argument("--vv_fc_gated", action="store_true", help="độ nhạy: bộ biến đổi FC chỉ phát Q khi FC đang chạy (không STATCOM)")
    ap.add_argument("--c_v", type=float, default=1e5, help="phạt thiếu áp, CNY/(pu²·h) – mặc định ≈ ngang phạt vượt MBA ở nút yếu nhất")
    ap.add_argument("--h2_demand_frac", type=float, default=0.0, help="việc 2.7: nhu cầu H2 của xe FCEV = tỉ lệ × sản lượng EL định mức/ngày (0 = tắt)")
    ap.add_argument("--c_ext", type=float, default=40.0, help="giá H2 mua ngoài (CNY/kg)")
    ap.add_argument("--fill_kg", type=float, default=5.0, help="kg mỗi lần nạp xe")
    ap.add_argument("--disp", type=int, default=2, help="số lần nạp tối đa mỗi 5 phút")
    ap.add_argument("--bat_scale_h2", type=float, default=1.0, help="việc 2.6: nhân cỡ pin (kWh và kW) ở các trạm H2; dùng cùng --no_h2")
    ap.add_argument("--el_a0", type=float, default=None, help="độ nhạy: ghi đè tốc độ già EL (μV/h), ví dụ 74.3 = số phòng thí nghiệm")
    ap.add_argument("--no_aging", action="store_true", help="baseline: Lyapunov KHÔNG tính lão hóa (bỏ μ và hàng đợi sức khỏe khỏi hàm mục tiêu)")
    ap.add_argument("--no_h2", action="store_true", help="bỏ hydrogen ở mọi trạm (kịch bản S1: chỉ PV + pin)")
    ap.add_argument("--start_amort", type=float, default=24.0, help="chia giá lão hóa bật máy cho số bước này trong hàm mục tiêu (1 = không chia)")
    ap.add_argument("--vref", type=float, default=1.0, help="V tham chiếu để chọn trọng số w_B, w_H (V ≤ vref)")
    ap.add_argument("--init", default="theta", choices=["theta", "mid"], help="mức pin/bồn ban đầu: θ (mặc định) hay giữa dải")
    ap.add_argument("--no_el_calib", action="store_true", help="bỏ qua params/el_calibration.json, dùng đường EL giả định cũ")
    ap.add_argument("--no_fc_calib", action="store_true", help="bỏ qua params/fc_calibration.json, dùng đường FC giả định cũ")
    ap.add_argument("--export_frac", type=float, default=0.0, help="giới hạn bán ngược lên lưới, tỉ lệ công suất máy biến áp (0 = cấm bán)")
    run(ap.parse_args())
