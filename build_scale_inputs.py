"""
VIỆC 4.3 – DỮ LIỆU CHO MẠNG LỚN (20–50 điểm sạc).
Dữ liệu trạm 5 phút chỉ có 13 trạm đạt chất lượng (quality_report.csv), không đủ 20–50. Vì vậy dùng bộ dữ liệu ĐÃ LÀM SẠCH của chính
UrbanEV ở mức VÙNG GIAO THÔNG (TAZ): volume.csv (kWh mỗi giờ của mọi trụ trong vùng) và e_price.csv (giá điện mỗi giờ), 275 vùng,
6 tháng, không có lỗ hổng. Mỗi vùng được coi là MỘT điểm sạc tập trung. Chọn N vùng gần cụm 7 trạm nhất, có phụ tải TB 20–1.000 kW
và ít giờ bằng 0. Dữ liệu giờ được giữ nguyên trong 12 bước 5 phút (nói rõ trong bài: phụ tải mượt hơn dữ liệu trạm 5 phút).
PV và nhiệt độ lấy từ data_clean/tier1_inputs.csv (cùng thành phố). Cỡ thiết bị theo ĐÚNG quy tắc của 7 trạm (step2_check_theory.py):
PV = phụ tải TB, pin = 2 giờ phụ tải TB (0,5C); 30% điểm lớn nhất có H2: FC = 0,5 × phụ tải TB, EL = 0,5 × PV, bồn đủ 8 giờ FC.
Chạy:   python build_scale_inputs.py                       (tự tìm thư mục UrbanEV có volume.csv)
        python build_scale_inputs.py --urbanev "D:/.../UrbanEV/data"
Ghi:    data_clean/scale{N}_inputs.csv, params/params_scale{N}.json với N = 20, 35, 50
"""
import argparse
import json
import math
import sys
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
CENTER = (22.7165, 113.8841)
H2_FRAC = 0.3


def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * np.arcsin(np.sqrt(a))


def find_file(name, prefer=("charge_5min", "charge_1hour", "UrbanEV_data", "data")):
    """Tìm file trong DATN2026; ưu tiên bản 5 phút của bộ Dryad (zone-cleaned-aggregated/charge_5min)."""
    found = list(PROJECT_DIR.rglob(name))
    for key in prefer:
        for f in found:
            if f.parent.name == key:
                return f
    return found[0] if found else None


def find_urbanev(arg):
    if arg:
        d = Path(arg)
        return d / "volume.csv", d / "e_price.csv", (d / "inf.csv") if (d / "inf.csv").exists() else find_file("inf.csv")
    vol, pri, inf = find_file("volume.csv"), find_file("e_price.csv"), find_file("inf.csv")
    if vol is None or pri is None or inf is None:
        sys.exit("Không tìm thấy volume.csv / e_price.csv / inf.csv của UrbanEV trong DATN2026. Chạy với --urbanev \"thư_mục\".")
    if (vol.parent / "e_price.csv").exists():
        pri = vol.parent / "e_price.csv"
    return vol, pri, inf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--urbanev", default=None)
    ap.add_argument("--sizes", default="20,35,50")
    args = ap.parse_args()
    fv, fp, fi = find_urbanev(args.urbanev)
    print(f"[*] phụ tải: {fv}\n[*] giá:     {fp}\n[*] vị trí:  {fi}")
    vol = pd.read_csv(fv, index_col=0, parse_dates=True)
    pri = pd.read_csv(fp, index_col=0, parse_dates=True)
    inf = pd.read_csv(fi)
    vol.columns = [str(c).split(".")[0] for c in vol.columns]; pri.columns = [str(c).split(".")[0] for c in pri.columns]
    step_h = (vol.index[1] - vol.index[0]).total_seconds() / 3600.0
    if step_h < 0.99:      # dữ liệu 5 phút: volume là kWh MỖI BƯỚC → kW = volume / bước (kiểm tra với bản 1 giờ nếu có)
        h1 = fv.parent.parent / "charge_1hour" / "volume.csv"
        if h1.exists():
            v1 = pd.read_csv(h1, index_col=0, parse_dates=True)
            r = float(vol.mean().mean() / step_h / max(v1.mean().mean(), 1e-9))
            print(f"[*] kiểm tra đơn vị: TB(volume 5 phút)/bước ÷ TB(volume 1 giờ) = {r:.3f} (≈ 1 nghĩa là volume 5 phút tính bằng kWh mỗi bước)")
            if abs(r - 1) > 0.15 and abs(r * step_h - 1) < 0.15:
                print("[*] volume 5 phút đã là kW (không chia bước)"); step_h = 1.0
        vol = vol / step_h
        print(f"[*] dữ liệu {step_h * 60:.0f} phút → đổi sang kW")
    else:
        print("[*] dữ liệu theo giờ: giữ nguyên trong 12 bước 5 phút")
    base = pd.read_csv(PROJECT_DIR / "data_clean" / "tier1_inputs.csv", index_col=0, parse_dates=True)
    params = json.loads((PROJECT_DIR / "params" / "params_tier1.json").read_text(encoding="utf-8"))
    LHV, eta_pk = params["LHV_kWh_per_kg"], params["aging_and_devices"]["fc"].get("eta_peak", 0.5)

    cen = inf.groupby("TAZID")[["latitude", "longitude"]].mean()
    vh = vol.resample("1h").mean()                     # tiêu chí chọn vùng tính theo giờ (như bản 1 giờ)
    z = pd.DataFrame({"mean_kw": vh.mean(), "zero_frac": (vh <= 0).mean()})
    z.index = z.index.astype(int)
    z = z.join(cen, how="inner")
    z["dist_km"] = haversine_km(CENTER[0], CENTER[1], z.latitude, z.longitude)
    ok = z[(z.mean_kw >= 20) & (z.mean_kw <= 1000) & (z.zero_frac <= 0.10)].sort_values("dist_km")
    print(f"[*] {len(z)} vùng, {len(ok)} vùng đạt (phụ tải TB 20–1.000 kW, ≤ 10% số giờ bằng 0)")
    r50 = lambda x: max(50.0, 50.0 * round(x / 50.0))
    r10 = lambda x: max(10.0, 10.0 * round(x / 10.0))
    for N in [int(x) for x in args.sizes.split(",")]:
        sel = ok.head(N)
        if len(sel) < N:
            print(f"  chỉ có {len(sel)} vùng đạt, bỏ N = {N}"); continue
        ids = list(sel.index)
        load = vol[[str(i) for i in ids]].reindex(base.index, method="ffill").fillna(0.0)
        price = pri[[str(i) for i in ids]].reindex(base.index, method="ffill").bfill()
        inp = pd.concat([load.set_axis([f"load_{i}" for i in ids], axis=1), price.set_axis([f"price_{i}" for i in ids], axis=1),
                         base[["pv_kw_per_kwp", "t_air"]]], axis=1)
        inp.index.name = "time"
        inp.round(4).to_csv(PROJECT_DIR / "data_clean" / f"scale{N}_inputs.csv")
        n_h2 = max(1, round(H2_FRAC * N))
        h2 = set(sel.sort_values("mean_kw", ascending=False).index[:n_h2])
        st = []
        for i in ids:
            m = float(sel.loc[i, "mean_kw"]); pv = r10(m); e = r10(2 * m)
            s = {"station_id": int(i), "pv_kWp": pv, "bat_kWh": e, "bat_kW": e / 2, "has_h2": i in h2,
                 "lat": float(sel.loc[i, "latitude"]), "lon": float(sel.loc[i, "longitude"])}
            if s["has_h2"]:
                s["fc_kW"] = r50(0.5 * m); s["el_kW"] = r50(0.5 * pv)
                s["tank_kg"] = float(10 * math.ceil(s["fc_kW"] * 8 / (eta_pk * LHV) / 0.85 / 10))
            st.append(s)
        p = dict(params); p["stations"] = st
        p["notes"] = (f"Mạng {N} điểm sạc = {N} vùng TAZ của UrbanEV gần cụm 7 trạm nhất (bán kính {sel.dist_km.max():.1f} km); "
                      f"{n_h2} điểm lớn nhất có H2. Cỡ thiết bị theo quy tắc của 7 trạm. " + params.get("notes", ""))
        (PROJECT_DIR / "params" / f"params_scale{N}.json").write_text(json.dumps(p, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  N = {N}: bán kính {sel.dist_km.max():.1f} km, phụ tải tổng TB {sel.mean_kw.sum():,.0f} kW, {n_h2} điểm có H2 "
              f"(FC tổng {sum(s.get('fc_kW', 0) for s in st):,.0f} kW) → data_clean/scale{N}_inputs.csv, params/params_scale{N}.json")


if __name__ == "__main__":
    main()
