"""
Chuẩn bị dữ liệu trạm sạc từ UrbanEV cho mô phỏng (chạy trên máy của bạn).

Cách chạy đơn giản nhất:
    Đặt file này vào thư mục DATN2026 (thư mục chứa cả UrbanEV đã giải nén và weather_5min_processed.csv),
    rồi bấm Run trong VS Code, hoặc gõ:  python prepare_urbanev.py
    Script tự tìm dữ liệu bên trong thư mục đó.

Cách chạy chỉ rõ đường dẫn (khi tự tìm không được):
    python prepare_urbanev.py --raw "D:/.../20220901-20230228_station-raw" --weather "D:/.../weather_5min_processed.csv" --out data_clean

Đầu vào:
    --raw      thư mục 20220901-20230228_station-raw (có charge_5min/, station_information.csv, pile_rated_power.csv)
    --weather  file thời tiết-PV 5 phút đã chốt (có cột time và pv_kw_per_kwp)
    --out      thư mục kết quả (tự tạo)

Đầu ra trong --out:
    stations_selected.csv       danh sách trạm của từng tầng (tier1 = 7 trạm chính, tier2_20km, tier3_city)
    quality_report.csv          chất lượng dữ liệu từng trạm (thiếu, bất thường, kiểm tra nhất quán)
    summary.txt                 tóm tắt ngắn — GỬI FILE NÀY + quality_report.csv CHO CLAUDE KIỂM TRA
    stations/<id>.csv           dữ liệu sạch 5 phút từng trạm
    tier1_load_kw.csv           ma trận phụ tải 5 phút của 7 trạm chính (cột = trạm)
    tier1_price.csv             giá điện 5 phút của 7 trạm chính
    tier1_inputs.csv            gộp phụ tải + giá + PV/kWp + nhiệt độ cho tầng 1, sẵn sàng đưa vào mô phỏng
    fig_tier1_profiles.png      hình kiểm tra: phụ tải trung bình theo giờ trong ngày

Quy ước và giả định (ghi lại trong bài):
    - Δt = 5 phút. Lưới thời gian đầy đủ 2022-09-01 00:00 → 2023-02-28 23:55 (52.128 bước).
    - UrbanEV tính 'volume' (kWh) = thời gian sạc × công suất định mức trụ, nên P = volume / Δt là công suất
      khi trụ chạy ở định mức (cận trên). Hệ số DC_TAPER cho phép giảm công suất DC do sạc chậm dần khi pin gần đầy.
    - Phụ tải DC ước lượng = fast_busy × công suất DC trung bình của trạm × DC_TAPER;
      phụ tải AC ước lượng = slow_busy × công suất AC trung bình của trạm.
    - Khoảng trống ≤ 30 phút: nội suy tuyến tính. Khoảng trống dài hơn: giữ trống ở bước làm sạch,
      sau đó lấp bằng giá trị cùng giờ của tuần trước (hoặc tuần sau) và đánh dấu trong cột 'filled'.
    - Trạm bị loại nếu thiếu > 5% số bước hoặc có khoảng trống liên tục > 24 giờ.
"""
import argparse
import sys
from pathlib import Path

import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=RuntimeWarning)

# ---------------------------------------------------------------- cấu hình
TIER1 = [1061, 1087, 1093, 1214, 1229, 1242, 1589]   # 7 trạm đạt chất lượng ở lần chạy 1 (Bảo An – Quang Minh)
TIER1_SPARE = [1403]                                  # dự phòng
CENTER = (22.7165, 113.8841)                          # tâm cụm (lat, lon)
MIN_ENERGY_RATIO = 0.75   # điện năng theo volume / theo số trụ bận × định mức
MIN_CORR = 0.70           # tương quan giữa hai cách tính công suất
DT_H = 5 / 60
DC_TAPER = 1.0          # 1.0 = dùng đúng công suất định mức như UrbanEV; thử 0.7 để phân tích độ nhạy
MAX_MISSING_FRAC = 0.05
MAX_GAP_H = 24
SHORT_GAP_STEPS = 6     # 30 phút
IDX = pd.date_range("2022-09-01 00:00", "2023-02-28 23:55", freq="5min")
RAW_COLS = ["busy", "idle", "s_price", "e_price", "fast_busy", "fast_idle",
            "slow_busy", "slow_idle", "duration", "volume"]


def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * np.arcsin(np.sqrt(a))


def station_table(raw: Path) -> pd.DataFrame:
    s = pd.read_csv(raw / "station_information.csv")
    p = pd.read_csv(raw / "pile_rated_power.csv")
    p["station_id"] = p["station_id"].astype(int)
    dc = p[p.pileType == "DC"].groupby("station_id").power.agg(dc_n="size", dc_kw="sum")
    ac = p[p.pileType == "AC"].groupby("station_id").power.agg(ac_n="size", ac_kw="sum")
    s = s.merge(dc, left_on="station_id", right_index=True, how="left")
    s = s.merge(ac, left_on="station_id", right_index=True, how="left").fillna({"dc_n": 0, "dc_kw": 0, "ac_n": 0, "ac_kw": 0})
    s["dc_avg_kw"] = np.where(s.dc_n > 0, s.dc_kw / s.dc_n.clip(lower=1), 0.0)
    s["ac_avg_kw"] = np.where(s.ac_n > 0, s.ac_kw / s.ac_n.clip(lower=1), 0.0)
    s["dist_km"] = haversine_km(CENTER[0], CENTER[1], s.latitude, s.longitude)
    s["pile_info_ok"] = s.fast_count == s.dc_n
    return s


def select_tiers(s: pd.DataFrame) -> pd.DataFrame:
    medium_dc = (s.dc_n >= 2) & s.pile_info_ok & (s.dc_kw <= 3000)
    rows = [(sid, "tier1") for sid in TIER1] + [(sid, "tier1_spare") for sid in TIER1_SPARE]
    rows += [(sid, "tier2_20km") for sid in s.loc[medium_dc & (s.dist_km <= 20), "station_id"]]
    rows += [(sid, "tier3_city") for sid in s.loc[medium_dc, "station_id"]]
    t = pd.DataFrame(rows, columns=["station_id", "tier"])
    return t.merge(s, on="station_id", how="left")


def longest_gap_steps(mask: np.ndarray) -> int:
    best = cur = 0
    for m in mask:
        cur = cur + 1 if m else 0
        best = max(best, cur)
    return best


def clean_station(path: Path, info: pd.Series):
    df = pd.read_csv(path)
    df.columns = [c.strip() for c in df.columns]
    missing_cols = [c for c in ["time"] + RAW_COLS if c not in df.columns]
    if missing_cols:
        return None, {"station_id": info.station_id, "status": "LOAI: thiếu cột " + ",".join(missing_cols)}
    df["time"] = pd.to_datetime(df["time"], errors="coerce")
    n_bad_time = int(df["time"].isna().sum())
    df = df.dropna(subset=["time"])
    n_dup = int(df["time"].duplicated().sum())
    df = df.drop_duplicates("time", keep="first").set_index("time").sort_index()
    off_grid = int((~df.index.isin(IDX)).sum())
    df = df.reindex(IDX)

    rep = {"station_id": int(info.station_id), "rows_in_file": int(len(df.dropna(how="all"))),
           "bad_time": n_bad_time, "duplicates": n_dup, "off_grid_times": off_grid}

    # volume tích lũy hay theo từng bước?
    v = df["volume"]
    vv = v.dropna()
    rep["volume_looks_cumulative"] = bool(len(vv) > 10 and vv.is_monotonic_increasing and vv.iloc[-1] > 50 * max(vv.median(), 1e-9))
    if rep["volume_looks_cumulative"]:
        df["volume"] = v.diff().clip(lower=0)

    # giá trị bất thường
    neg = {c: int((df[c] < 0).sum()) for c in ["busy", "fast_busy", "slow_busy", "volume", "duration"]}
    rep["negative_values"] = sum(neg.values())
    for c in neg:
        df.loc[df[c] < 0, c] = np.nan
    over_dc = int((df["fast_busy"] > info.dc_n).sum()) if info.dc_n > 0 else 0
    rep["fast_busy_gt_dc_piles"] = over_dc
    if info.dc_n > 0:
        df.loc[df["fast_busy"] > info.dc_n, "fast_busy"] = np.nan
    rep["price_out_of_range"] = int(((df["e_price"] < 0.1) | (df["e_price"] > 3)).sum())
    df.loc[(df["e_price"] < 0.1) | (df["e_price"] > 3), "e_price"] = np.nan

    # thiếu dữ liệu
    miss = df[["fast_busy", "slow_busy", "volume", "e_price"]].isna().any(axis=1).to_numpy()
    rep["missing_steps"] = int(miss.sum())
    rep["missing_frac"] = round(miss.mean(), 4)
    rep["longest_gap_h"] = round(longest_gap_steps(miss) * DT_H, 2)

    # lấp trống: ngắn -> nội suy; dài -> cùng giờ tuần trước/tuần sau
    filled = np.zeros(len(df), dtype=bool)
    for c in ["busy", "idle", "fast_busy", "fast_idle", "slow_busy", "slow_idle", "duration", "volume", "e_price", "s_price"]:
        before = df[c].isna().to_numpy()
        df[c] = df[c].interpolate(limit=SHORT_GAP_STEPS, limit_area="inside")
        for lag in (2016, -2016, 4032, -4032):   # 1 tuần = 2016 bước
            df[c] = df[c].fillna(df[c].shift(lag))
        df[c] = df[c].ffill().bfill()
        filled |= before & df[c].notna().to_numpy()
    df["filled"] = filled.astype(int)

    # công suất
    df["p_vol_kw"] = df["volume"] / DT_H
    df["p_dc_kw"] = df["fast_busy"] * info.dc_avg_kw * DC_TAPER
    df["p_ac_kw"] = df["slow_busy"] * info.ac_avg_kw
    df["p_load_kw"] = df["p_dc_kw"] + df["p_ac_kw"]

    # kiểm tra nhất quán: công suất từ volume so với từ số trụ bận × định mức
    a, b = df["p_vol_kw"].to_numpy(), (df["fast_busy"] * info.dc_avg_kw + df["slow_busy"] * info.ac_avg_kw).to_numpy()
    rep["energy_ratio_volume_vs_busy"] = round(np.nansum(a) / max(np.nansum(b), 1e-9), 3)
    rep["corr_volume_vs_busy"] = round(float(pd.Series(a).corr(pd.Series(b))), 3)
    rep["mean_p_load_kw"] = round(df["p_load_kw"].mean(), 1)
    rep["peak_p_load_kw"] = round(df["p_load_kw"].max(), 1)
    rep["mean_p_dc_kw"] = round(df["p_dc_kw"].mean(), 1)
    rep["dc_capacity_kw"] = float(info.dc_kw)
    rep["dc_utilisation"] = round(df["p_dc_kw"].mean() / info.dc_kw, 3) if info.dc_kw > 0 else np.nan
    rep["mean_e_price"] = round(df["e_price"].mean(), 3)

    reasons = []
    if rep["missing_frac"] > MAX_MISSING_FRAC:
        reasons.append("thiếu nhiều")
    if rep["longest_gap_h"] > MAX_GAP_H:
        reasons.append("khoảng trống dài")
    if not (rep["energy_ratio_volume_vs_busy"] >= MIN_ENERGY_RATIO and rep["corr_volume_vs_busy"] >= MIN_CORR):
        reasons.append("hai cách tính phụ tải không khớp")
    rep["status"] = "OK" if not reasons else "LOAI: " + ", ".join(reasons)
    out = df[["p_load_kw", "p_dc_kw", "p_ac_kw", "p_vol_kw", "fast_busy", "slow_busy", "e_price", "s_price", "filled"]]
    out.index.name = "time"
    return out, rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=None, help="bỏ trống: tự tìm thư mục 20220901-20230228_station-raw")
    ap.add_argument("--weather", default=None, help="bỏ trống: tự tìm file weather_5min_processed.csv")
    ap.add_argument("--out", default=None, help="bỏ trống: tạo data_clean cạnh file script")
    ap.add_argument("--search", default=None, help="thư mục gốc để tự tìm dữ liệu (mặc định: thư mục chứa script)")
    ap.add_argument("--tiers", default="tier1,tier1_spare,tier3_city", help="các tầng cần xử lý, cách nhau dấu phẩy (thêm tier3_city nếu muốn cả thành phố)")
    args = ap.parse_args()

    here = Path(__file__).resolve().parent
    project = Path(__file__).resolve().parent
    if not project.exists():
        project = here
    base = Path(args.search) if args.search else project
    if args.raw is None:
        found = [p for p in base.rglob("20220901-20230228_station-raw") if (p / "charge_5min").is_dir()]
        if not found:
            sys.exit(f"Không tìm thấy thư mục 20220901-20230228_station-raw (có charge_5min) bên trong {base}.\n"
                     f"Hãy đặt file script này vào thư mục cha của dữ liệu UrbanEV đã GIẢI NÉN, hoặc chạy với --raw \"đường_dẫn\".")
        args.raw = str(found[0])
    if args.weather is None:
        found = sorted(base.rglob("weather_5min_processed.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not found:
            sys.exit(f"Không tìm thấy weather_5min_processed.csv bên trong {base}. Chạy với --weather \"đường_dẫn\".")
        args.weather = str(found[0])
    if args.out is None:
        args.out = str(project / "data_clean")
    print(f"[*] Dữ liệu trạm : {args.raw}\n[*] Thời tiết    : {args.weather}\n[*] Kết quả lưu ở: {args.out}")

    raw, out = Path(args.raw), Path(args.out)
    (out / "stations").mkdir(parents=True, exist_ok=True)
    charge_dir = raw / "charge_5min"
    if not charge_dir.exists():
        sys.exit(f"Không thấy thư mục {charge_dir}. Kiểm tra lại --raw.")

    s = station_table(raw)
    tiers = select_tiers(s)
    tiers.to_csv(out / "stations_selected.csv", index=False)
    want = set(args.tiers.split(","))
    todo = tiers[tiers.tier.isin(want)].drop_duplicates("station_id")
    print(f"Sẽ xử lý {len(todo)} trạm thuộc {sorted(want)}")

    reports = []
    for _, info in todo.iterrows():
        f = charge_dir / f"{int(info.station_id)}.csv"
        if not f.exists():
            reports.append({"station_id": int(info.station_id), "status": "LOAI: không có file"})
            continue
        data, rep = clean_station(f, info)
        rep["tier"] = info.tier
        reports.append(rep)
        if data is not None:
            data.round(4).to_csv(out / "stations" / f"{int(info.station_id)}.csv")
        print(f"  {int(info.station_id)}: {rep['status']}  thiếu {rep.get('missing_frac', '?')}  khoảng trống dài nhất {rep.get('longest_gap_h', '?')} h")

    rep = pd.DataFrame(reports)
    rep.to_csv(out / "quality_report.csv", index=False)

    # tầng 1: dùng 7 trạm chính; trạm nào bị loại thì thay bằng trạm dự phòng
    ok = set(rep.loc[rep.status.astype(str) == "OK", "station_id"].astype(int))
    tier1 = [x for x in TIER1 if x in ok]
    for spare in TIER1_SPARE:
        if len(tier1) < len(TIER1) and spare in ok:
            tier1.append(spare)

    w = pd.read_csv(args.weather)
    tcol = w.columns[0]
    w[tcol] = pd.to_datetime(w[tcol].astype(str).str.replace(r"\+\d\d:\d\d$", "", regex=True))
    w = w.set_index(tcol).reindex(IDX)
    pv_col = next((c for c in w.columns if "kwp" in c.lower()), None)
    t_col = next((c for c in w.columns if c.lower().startswith("temperature")), None)

    lines = [f"Số trạm xử lý: {len(rep)} | OK: {len(ok)} | bị loại: {len(rep) - len(ok)}",
             f"Tầng 1 dùng: {tier1}",
             f"Thời tiết: {len(w)} bước, thiếu PV {int(w[pv_col].isna().sum()) if pv_col else 'KHÔNG CÓ CỘT PV'}"]
    if tier1:
        load = pd.concat({sid: pd.read_csv(out / "stations" / f"{sid}.csv", index_col=0, parse_dates=True)["p_load_kw"] for sid in tier1}, axis=1)
        price = pd.concat({sid: pd.read_csv(out / "stations" / f"{sid}.csv", index_col=0, parse_dates=True)["e_price"] for sid in tier1}, axis=1)
        load.index.name = price.index.name = "time"
        load.round(3).to_csv(out / "tier1_load_kw.csv")
        price.round(4).to_csv(out / "tier1_price.csv")
        inp = load.add_prefix("load_")
        inp = inp.join(price.add_prefix("price_"))
        if pv_col:
            inp["pv_kw_per_kwp"] = w[pv_col].to_numpy()
        if t_col:
            inp["t_air"] = w[t_col].to_numpy()
        inp.round(4).to_csv(out / "tier1_inputs.csv")
        lines += [f"Tầng 1 – phụ tải trung bình toàn cụm: {load.sum(axis=1).mean():.0f} kW, đỉnh: {load.sum(axis=1).max():.0f} kW",
                  f"Tầng 1 – năng lượng sạc 6 tháng: {load.sum(axis=1).sum() * DT_H / 1000:.0f} MWh",
                  f"Giá điện: {price.stack().min():.3f}–{price.stack().max():.3f} CNY/kWh, các mức khác nhau: {np.unique(price.stack().round(3)).size}"]
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            prof = load.groupby(load.index.hour).mean()
            ax = prof.plot(figsize=(9, 4), title="Phụ tải trung bình theo giờ – tầng 1 (kW)")
            ax.set_xlabel("Giờ trong ngày")
            plt.tight_layout()
            plt.savefig(out / "fig_tier1_profiles.png", dpi=110)
        except Exception as e:  # không có matplotlib vẫn chạy được
            lines.append(f"(Không vẽ được hình: {e})")
    (out / "summary.txt").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nXong. Gửi cho Claude: {out / 'summary.txt'}, {out / 'quality_report.csv'}, {out / 'fig_tier1_profiles.png'}")


if __name__ == "__main__":
    main()
