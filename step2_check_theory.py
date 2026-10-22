"""
BƯỚC 2 – Kiểm tra bằng số các điều kiện của định lý với thiết bị và dữ liệu thật (7 trạm tầng 1).

Chạy: đặt file trong thư mục DATN2026 rồi bấm Run (hoặc: python step2_check_theory.py)
Đọc : DATN2026/data_clean/tier1_inputs.csv  (nếu không có, dùng số liệu tóm tắt đã chạy ở bước 1)
Ghi : DATN2026/params/params_tier1.json      (bộ thông số thiết bị, có nguồn)
      DATN2026/results/step2_report.txt      (báo cáo – GỬI FILE NÀY CHO CLAUDE)

Script tính cho HAI phiên bản lý thuyết:
  (I)  Bản hiện tại trong file Word: lão hóa bật/tắt tính lúc xảy ra (FC: lúc bật và lúc tắt; EL: lúc tắt).
  (II) Bản sửa đề xuất: lão hóa bật/tắt "trả trước" lúc BẬT (FC: 2·k_ss khi bật, 0 khi tắt; EL: a_sd khi bật),
       và hàm Lyapunov có trọng số w_B, w_H, w_Z cho từng loại hàng đợi.
Mục đích: cho thấy bản (I) có khoảng θ^H rỗng với mọi V > 0 (nên phải sửa), còn bản (II) khả thi.
"""
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

# ------------------------------------------------------------------ thư mục
PROJECT_DIR = Path(__file__).resolve().parent
if not PROJECT_DIR.exists():                 # chạy ở máy khác: dùng thư mục chứa script
    PROJECT_DIR = Path(__file__).resolve().parent
OUT_PARAMS = PROJECT_DIR / "params"
OUT_RES = PROJECT_DIR / "results"
OUT_PARAMS.mkdir(parents=True, exist_ok=True)
OUT_RES.mkdir(parents=True, exist_ok=True)

DT_H = 5 / 60
LHV = 33.33                                   # kWh/kg H2
STATIONS = [1061, 1087, 1093, 1214, 1229, 1242, 1589]
H2_STATIONS = [1093, 1242, 1589]              # 3 trạm lớn nhất có hydrogen; 4 trạm còn lại PV + pin
FALLBACK_MEAN_KW = {1061: 49.8, 1087: 102.5, 1093: 234.6, 1214: 40.9, 1229: 76.0, 1242: 223.4, 1589: 483.3}
FALLBACK_PRICE_MAX = 1.43

# ------------------------------------------------------------------ hệ số lão hóa và thiết bị (có nguồn)
AGING = {
    "fc": {
        "V_rated_cell_uV": 0.70e6,            # điện áp cell định mức (giả định 0,70 V); D=1 khi giảm 10%
        "k_ss_uV": 13.79,                     # mỗi lần bật hoặc tắt – Chen, Pei, Song, Applied Energy 142 (2015) 154–163
        "k_lc_uV_per_kW": 1.79,               # mỗi kW thay đổi tải trên một stack – cùng nguồn
        "k_lo_uV_per_h": 8.66,                # chạy tải thấp (< 20% định mức) – cùng nguồn
        "k_hp_uV_per_h": 10.0,                # chạy tải cao (> 80% định mức) – cùng nguồn
        "module_kW": 50.0,                    # hệ FC gồm các module 50 kW chạy chia đều (giả định)
        "P_lo_frac": 0.2, "P_hi_frac": 0.8, "P_min_frac": 0.1,
        "eta_peak": 0.50,                     # hiệu suất hệ thống đỉnh (LHV) – giả định, sẽ thay bằng đường phân cực FCLAB
        "stack_cost_CNY_per_kW": 2000.0,      # chi phí thay stack – GIẢ ĐỊNH, cần xác minh
        "life_target_h": 5 * 8760,            # tuổi thọ mục tiêu theo thời gian lịch
    },
    "el": {
        "V_rated_cell_uV": 1.90e6,            # 1,9 V/cell tại 2 A/cm² – DOE Technical Targets PEM Electrolysis (2022 status)
        "a0_uV_per_h": 4.8,                   # 4,8 mV/kh – DOE (2022 status)
        "a_sd_uV": 10.4,                      # mỗi chu kỳ tắt máy có ngắt nước – NREL/TP-5900-87375 (2024)
        "P_min_frac": 0.1,
        "kWh_per_kg": 55.0,                   # 51 kWh/kg ở stack (DOE 2022) + phụ trợ – giả định 55 cho cả hệ
        "stack_cost_CNY_per_kW": 3150.0,      # 450 USD/kW (DOE 2022 status) × 7,0 – cần xác minh tỉ giá/phạm vi
        "life_target_h": 5 * 8760,
    },
    "bat": {"eta_ch": 0.95, "eta_dis": 0.95, "soc_min": 0.1, "soc_max": 0.9, "c_bat_CNY_per_kWh": 0.05},
    "tank": {"fill_min": 0.10, "fill_max": 0.95, "e_cp_kWh_per_kg": 2.5},   # máy nén – giả định, cần nguồn
}


def size_station(sid, mean_kw):
    """Quy tắc chọn cỡ (ghi rõ trong bài): PV = 1,0 × phụ tải TB; pin = 2 h phụ tải TB, công suất 0,5C;
    trạm có H2: FC = 0,5 × phụ tải TB (bội số module 50 kW), EL = 0,5 × PV (bội số 50 kW), bồn đủ 8 h FC định mức."""
    r50 = lambda x: max(50.0, 50.0 * round(x / 50.0))
    r10 = lambda x: max(10.0, 10.0 * round(x / 10.0))
    pv = r10(mean_kw)
    e_bat = r10(2 * mean_kw)
    s = {"station_id": sid, "pv_kWp": pv, "bat_kWh": e_bat, "bat_kW": e_bat / 2, "has_h2": sid in H2_STATIONS}
    if s["has_h2"]:
        s["fc_kW"] = r50(0.5 * mean_kw)
        s["el_kW"] = r50(0.5 * pv)
        cap = s["fc_kW"] * 8 / (AGING["fc"]["eta_peak"] * LHV)
        s["tank_kg"] = float(10 * math.ceil(cap / 0.85 / 10))
    return s


def derived(s, c_max, mu_scale=1.0):
    """Các đại lượng một bước cho một trạm (đơn vị gốc: kWh, kg, D không thứ nguyên)."""
    a, b, t = AGING, AGING["bat"], AGING["tank"]
    d = {}
    d["dE_max"] = max(b["eta_ch"] * s["bat_kW"], s["bat_kW"] / b["eta_dis"]) * DT_H
    d["E_range"] = (b["soc_max"] - b["soc_min"]) * s["bat_kWh"]
    d["E_slack_B"] = d["E_range"] - b["eta_ch"] * s["bat_kW"] * DT_H - s["bat_kW"] * DT_H / b["eta_dis"]
    if not s["has_h2"]:
        return d
    fc, el = a["fc"], a["el"]
    d["m_fc_max"] = s["fc_kW"] * DT_H / (fc["eta_peak"] * LHV)          # cận trên (hiệu suất đỉnh cho ít H2 nhất; dùng đỉnh là bảo thủ cho Γ)
    d["m_fc_max"] *= 1.25                                                # hiệu suất ở tải đầy thấp hơn đỉnh ~20%: tăng 25% cho chắc
    d["m_el_max"] = s["el_kW"] * DT_H / el["kWh_per_kg"]
    d["m_el_min"] = el["P_min_frac"] * d["m_el_max"]
    d["H_range"] = (t["fill_max"] - t["fill_min"]) * s["tank_kg"]
    d["dM_max"] = max(d["m_fc_max"], d["m_el_max"])
    n_mod = s["fc_kW"] / fc["module_kW"]
    Vfc, Vel = 0.1 * fc["V_rated_cell_uV"], 0.1 * el["V_rated_cell_uV"]   # μV tương ứng D = 1
    dP_max_mod = (1 - fc["P_min_frac"]) * s["fc_kW"] / n_mod
    # FC: phần không phụ thuộc bước trước (tối đa một trong hai vùng tải thấp/cao)
    d["fc_dD0_max"] = max(fc["k_lo_uV_per_h"], fc["k_hp_uV_per_h"]) * DT_H / Vfc
    # bản (I): bật hoặc tắt k_ss; đổi tải tối đa
    d["fc_dDsw_max_I"] = max(fc["k_ss_uV"], fc["k_lc_uV_per_kW"] * dP_max_mod) / Vfc
    # bản (II): trả trước 2·k_ss lúc bật, tắt = 0
    d["fc_dDsw_max_II"] = max(2 * fc["k_ss_uV"], fc["k_lc_uV_per_kW"] * dP_max_mod) / Vfc
    d["el_dD0_max"] = el["a0_uV_per_h"] * DT_H / Vel
    d["el_dDsw_max"] = el["a_sd_uV"] / Vel
    d["delta_fc"] = DT_H / fc["life_target_h"]
    d["delta_el"] = DT_H / el["life_target_h"]
    d["mu_fc"] = mu_scale * fc["stack_cost_CNY_per_kW"] * s["fc_kW"]      # CNY cho D = 1 (thay stack)
    d["mu_el"] = mu_scale * el["stack_cost_CNY_per_kW"] * s["el_kW"]
    d["kC_fc"] = c_max * s["fc_kW"] * DT_H
    d["kC_el"] = 0.0                                                     # tắt EL không làm tăng chi phí (bản II)
    d["kC_el_I"] = c_max * s["el_kW"] * DT_H                             # bản I dùng cận chung
    return d


def check_version_I(s, d, c_max):
    """Bản hiện tại: σ là khoảng dư khi 'cho nghỉ' (giữ nguyên trạng thái trước). Trường hợp xấu: đang chạy tải thấp
    hoặc đang bật mà buộc tắt → σ < 0. Ở đây lấy trường hợp thuận lợi nhất cho bản I (σ = δ − lão hóa nền khi giữ nguyên)
    để chứng tỏ: ngay cả khi đó, khoảng θ^H vẫn rỗng."""
    res = {}
    for x, kq in (("fc", d["m_fc_max"]), ("el", d["m_el_max"])):
        delta = d[f"delta_{x}"]
        sigma = delta - (d["fc_dD0_max"] if x == "fc" else d["el_dD0_max"])
        dDmax = (d["fc_dD0_max"] + d["fc_dDsw_max_I"]) if x == "fc" else (d["el_dD0_max"] + d["el_dDsw_max"])
        kQ = d["H_range"] * kq
        res[x] = {"sigma": sigma, "dD_max": dDmax, "kQ": kQ, "ratio_dDmax_over_sigma": dDmax / sigma if sigma > 0 else float("inf")}
    # Γ^fc ⊇ η LHV κ_Q ΔD_max /(σ P_min Δt): phần KHÔNG phụ thuộc V
    fc = AGING["fc"]
    P_min = fc["P_min_frac"] * s["fc_kW"]
    G_fc_floor = fc["eta_peak"] * LHV * res["fc"]["kQ"] * res["fc"]["dD_max"] / max(res["fc"]["sigma"], 1e-30) / (P_min * DT_H) if res["fc"]["sigma"] > 0 else float("inf")
    G_el_floor = res["el"]["kQ"] * (d["el_dD0_max"] + d["el_dDsw_max"]) / max(res["el"]["sigma"], 1e-30) / d["m_el_min"] if res["el"]["sigma"] > 0 else float("inf")
    room = d["H_range"] - d["m_el_max"] - d["m_fc_max"]
    res["Gamma_floor_sum_kg"] = G_fc_floor + G_el_floor
    res["tank_room_kg"] = room
    res["theta_H_interval_empty_for_all_V"] = res["Gamma_floor_sum_kg"] > room
    return res


def check_version_II(s, d, c_max, V, w_B, w_H, w_Z, eps=0.0):
    """Bản sửa: công thức trong đơn vị gốc, Lyapunov có trọng số."""
    r = {}
    fc, b = AGING["fc"], AGING["bat"]
    # Mệnh đề 1 (không còn phụ thuộc Z_max)
    r["V_B_max"] = w_B * d["E_slack_B"] / (b["eta_dis"] * c_max)
    if s["has_h2"]:
        r["Gamma_fc_kg"] = fc["eta_peak"] * LHV * V * c_max / w_H
        r["Gamma_el_kg"] = 0.0
        r["V_H_max"] = w_H * (d["H_range"] - d["m_el_max"] - d["m_fc_max"]) / (fc["eta_peak"] * LHV * c_max)
        for x in ("fc", "el"):
            kC = d[f"kC_{x}"]
            kQ = w_H * d["H_range"] * d[f"m_{x}_max"]
            delta = d[f"delta_{x}"]
            dDmax = (d["fc_dD0_max"] + d["fc_dDsw_max_II"]) if x == "fc" else (d["el_dD0_max"] + d["el_dDsw_max"])
            Zmax = (V * kC + kQ + eps) / (w_Z * delta) + dDmax          # σ = δ (tắt máy không lão hóa)
            r[f"Zmax_{x}"] = Zmax                                       # theo đơn vị D (1 = hết tuổi thọ)
            r[f"V_life_{x}"] = (w_Z * delta * (1 - dDmax) - kQ - eps) / kC if kC > 0 else float("inf")
            r[f"life_guarantee_{x}"] = 1 - Zmax                         # L_real ≥ L·(1 − Z_max)
            dDsw = d["fc_dDsw_max_II"] if x == "fc" else d["el_dDsw_max"]
            mu = d[f"mu_{x}"]
            r[f"beta_sw_{x}"] = (mu + w_Z * Zmax / V) * dDsw
    return r


def main():
    lines = []
    f = PROJECT_DIR / "data_clean" / "tier1_inputs.csv"
    if f.exists():
        df = pd.read_csv(f, index_col=0)
        mean_kw = {sid: float(df[f"load_{sid}"].mean()) if f"load_{sid}" in df else FALLBACK_MEAN_KW[sid] for sid in STATIONS}
        missing = [sid for sid in STATIONS if f"load_{sid}" not in df]
        if missing:
            lines.append(f"CẢNH BÁO: tier1_inputs.csv thiếu trạm {missing} – dùng phụ tải TB từ bước 1 cho các trạm này.")
        price_cols = [c for c in df.columns if c.startswith("price_")]
        c_max = float(df[price_cols].max().max())
        lines.append(f"Đọc dữ liệu: {f}")
        hp = df[price_cols].groupby(pd.to_datetime(df.index).hour).mean().round(3)
        lines.append("Giá điện (e_price) trung bình theo giờ, mỗi trạm (CNY/kWh):\n" + hp.to_string())
    else:
        mean_kw, c_max = FALLBACK_MEAN_KW, FALLBACK_PRICE_MAX
        lines.append("Không thấy tier1_inputs.csv – dùng số liệu tóm tắt từ bước 1.")
    lines.append(f"c_buy_max = {c_max:.3f} CNY/kWh\n")

    stations = [size_station(sid, mean_kw[sid]) for sid in STATIONS]
    params = {"dt_h": DT_H, "LHV_kWh_per_kg": LHV, "aging_and_devices": AGING, "stations": stations,
              "notes": "Các giá trị ghi 'giả định'/'cần xác minh' phải được kiểm tra nguồn trước khi nộp bài."}
    (OUT_PARAMS / "params_tier1.json").write_text(json.dumps(params, indent=2, ensure_ascii=False), encoding="utf-8")
    lines.append("CỠ THIẾT BỊ (quy tắc trong size_station):")
    lines.append(pd.DataFrame(stations).to_string(index=False) + "\n")

    # ---------- bản I
    lines.append("=" * 78 + "\n(I) BẢN HIỆN TẠI TRONG FILE WORD\n" + "=" * 78)
    for s in stations:
        if not s["has_h2"]:
            continue
        d = derived(s, c_max)
        r = check_version_I(s, d, c_max)
        lines.append(f"Trạm {s['station_id']}: ΔD_max/σ (FC) = {r['fc']['ratio_dDmax_over_sigma']:.0f}, (EL) = {r['el']['ratio_dDmax_over_sigma']:.1f};  "
                     f"phần Γ không phụ thuộc V = {r['Gamma_floor_sum_kg']:.3g} kg  so với chỗ trống bồn = {r['tank_room_kg']:.1f} kg  "
                     f"=> khoảng θ^H rỗng với mọi V>0: {r['theta_H_interval_empty_for_all_V']}")
    lines.append("Kết luận (I): nếu 'rỗng = True', Mệnh đề 1 bản hiện tại không áp dụng được với thiết bị thật.\n")

    # ---------- bản II: chọn trọng số
    lines.append("=" * 78 + "\n(II) BẢN SỬA: TRẢ TRƯỚC LÃO HÓA BẬT/TẮT + LYAPUNOV CÓ TRỌNG SỐ\n" + "=" * 78)
    w_B, w_H = 1.0, 1.0
    rows = []
    for w_Z in [1e6, 1e8, 1e10, 1e12]:
        for V in [0.1, 1, 10, 100, 1000]:
            agg = {"w_Z": w_Z, "V": V}
            Vb, Vh, Vl, zmax, beta, A = [], [], [], [], 0.0, 0.0
            for s in stations:
                d = derived(s, c_max)
                r = check_version_II(s, d, c_max, V, w_B, w_H, w_Z)
                Vb.append(r["V_B_max"])
                A += 0.5 * w_B * d["dE_max"] ** 2
                if s["has_h2"]:
                    Vh.append(r["V_H_max"]); Vl += [r["V_life_fc"], r["V_life_el"]]
                    zmax += [r["Zmax_fc"], r["Zmax_el"]]
                    beta += r["beta_sw_fc"] + r["beta_sw_el"]
                    A += 0.5 * w_H * d["dM_max"] ** 2
                    A += 0.5 * w_Z * ((d["fc_dD0_max"] + d["fc_dDsw_max_II"]) ** 2 + (d["el_dD0_max"] + d["el_dDsw_max"]) ** 2)
            Vmax = min(min(Vb), min(Vh), min(Vl))
            agg.update({"V_max": Vmax, "V_ok": V <= Vmax, "worst_Zmax": max(zmax), "life_guarantee_min_%": 100 * (1 - max(zmax)),
                        "gap_A_over_V_CNY_per_step": A / V, "beta_sw_CNY_per_step": beta})
            rows.append(agg)
    tab = pd.DataFrame(rows)
    pd.set_option("display.width", 200)
    lines.append(tab.to_string(index=False, float_format=lambda v: f"{v:.4g}"))
    mean_cost_step = c_max * 0.6 * sum(mean_kw.values()) * DT_H
    lines.append(f"\nĐể so sánh: chi phí mua điện mỗi bước ~ {mean_cost_step:.1f} CNY (giá TB ≈ 0,6·c_max × phụ tải TB).")
    good = tab[tab.V_ok & (tab.worst_Zmax < 0.1)]
    if len(good):
        best = good.sort_values(["gap_A_over_V_CNY_per_step"]).iloc[0]
        lines.append(f"Gợi ý: w_Z = {best.w_Z:.0e}, V = {best.V:g}  → bảo đảm tuổi thọ ≥ {best['life_guarantee_min_%']:.1f}% mục tiêu, "
                     f"cận A/V = {best.gap_A_over_V_CNY_per_step:.3g} CNY/bước, β_sw = {best.beta_sw_CNY_per_step:.3g} CNY/bước.")
    else:
        lines.append("Không có cặp (w_Z, V) nào vừa thỏa V ≤ V_max vừa Z_max < 0,1 – cần xem lại thông số.")
    lines.append("\nChú thích: Z_max tính theo đơn vị D (1 = toàn bộ tuổi thọ). 'life_guarantee_min_%' = 100·(1 − Z_max) là phần tuổi thọ"
                 " mục tiêu được bảo đảm theo Hệ quả 1. Cận A/V và β_sw là cận trên lý thuyết (bảo thủ), đo bằng CNY mỗi bước 5 phút.")
    out = OUT_RES / "step2_report.txt"
    out.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nĐã ghi: {out}\nĐã ghi: {OUT_PARAMS / 'params_tier1.json'}")


if __name__ == "__main__":
    main()
