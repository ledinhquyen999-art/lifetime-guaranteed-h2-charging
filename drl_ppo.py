"""
VIỆC 4.1 – SO VỚI HỌC TĂNG CƯỜNG SÂU (DRL, PPO).
Môi trường dùng ĐÚNG thông số, mô hình H2 (đường tuyến tính từng đoạn), lão hóa và cách tính chi phí K2 của step3_simulate.py,
cùng khóa an toàn bồn (S2, S3) và giới hạn pin. Khác biệt duy nhất: chính sách là mạng nơ-ron học từ dữ liệu, KHÔNG có hàng đợi
sức khỏe → không có bảo đảm tuổi thọ. Không có chia sẻ giữa các trạm → so công bằng với S3b (step3 --no_share), và báo thêm S3.
  Huấn luyện: 2022-09-01 → 2022-10-31 (dữ liệu "quá khứ"), mỗi tập 7 ngày, điểm bắt đầu ngẫu nhiên.
  Đánh giá:   2022-11-01 → 2022-11-30 (chưa từng thấy), chính sách tất định, bắt đầu từ cùng mức θ như S3.
Cài (một lần):  python -m pip install stable-baselines3 gymnasium
Chạy:           python drl_ppo.py --seed 0            (một hạt giống, ~20–40 phút)
                (run_drl.py chạy 3 hạt giống + S3b và gom kết quả)
"""
import argparse
import json
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
sys.path.insert(0, str(HERE))
import step3_simulate as S  # noqa: E402

PROJECT_DIR = S.PROJECT_DIR
DT = S.DT


def load_setup(eval_start="2022-11-01", eval_days=30, train_start="2022-09-01", train_end="2022-10-31", w_Z=1e10):
    params = json.loads((PROJECT_DIR / "params" / "params_tier1.json").read_text(encoding="utf-8"))
    S.apply_fc_calibration(params, Namespace(no_fc_calib=False, no_el_calib=False))
    allin = pd.read_csv(PROJECT_DIR / "data_clean" / "tier1_inputs.csv", index_col=0, parse_dates=True)
    t0 = pd.Timestamp(eval_start)
    ev = allin.loc[t0: t0 + pd.Timedelta(days=eval_days) - pd.Timedelta(minutes=5)]
    tr = allin.loc[pd.Timestamp(train_start): pd.Timestamp(train_end) + pd.Timedelta(hours=23, minutes=55)]
    # thông số thiết bị lấy y như step3 cho kỳ đánh giá (MBA = 0,6 × đỉnh của kỳ đó), PV × 1, không bán lên lưới
    # (w_Z chỉ dùng để tính Z_max cho KHIÊN – cùng mức bảo đảm với đề xuất; DRL không có hàng đợi trong hàm mục tiêu)
    st, c_max = S.prepare(params, ev, 1.0, w_Z, pv_scale=1.0, export_frac=0.0, V_REF=1.0, tr_frac=0.6, no_h2=False)
    return st, tr, ev


def seg_mass(segs, P):
    """Khối lượng H2 theo đường tuyến tính từng đoạn của step3 (cùng mô hình bộ điều khiển dùng)."""
    if P <= 1e-9:
        return 0.0
    for lo, hi, sl, ic in segs:
        if P <= hi + 1e-9:
            return sl * max(P, lo) + ic
    lo, hi, sl, ic = segs[-1]
    return sl * hi + ic


class StationsEnv:
    """Môi trường nhiều trạm, bước 5 phút. Hành động ∈ [-1, 1]^(N + 4·NH):
       pin trạm i: a > 0 xả a·P_bat, a < 0 sạc |a|·P_bat;
       FC/EL trạm H2: (lệnh bật/tắt, mức công suất). Bật/tắt có TRỄ: > +0,3 thì bật, < −0,3 thì tắt, ở giữa thì giữ trạng thái cũ
       (tránh bật/tắt liên tục khi khám phá – thông lệ cho DRL có biến bật/tắt); mức công suất ∈ [−1, 1] → [P_min, P_max]."""

    def __init__(self, st, data, ep_steps=2016, seed=0, randomize=True, shield=False):
        import gymnasium as gym
        self.shield = shield
        self.st, self.I = st, sorted(st)
        self.H = [i for i in self.I if st[i]["h2"]]
        self.N, self.NH = len(self.I), len(self.H)
        self.load = data[[f"load_{i}" for i in self.I]].to_numpy(float)
        self.price = data[[f"price_{i}" for i in self.I]].to_numpy(float)
        self.pv = data["pv_kw_per_kwp"].to_numpy(float)
        self.hour = (data.index.hour + data.index.minute / 60.0).to_numpy(); self.dow = data.index.dayofweek.to_numpy()
        self.T = len(data); self.ep_steps = min(ep_steps, self.T); self.randomize = randomize
        self.rng = np.random.default_rng(seed)
        self.peak = np.array([max(1.0, st[i]["P_tr"] / 0.6) for i in self.I])
        self.pmax = max(1.0, float(self.price.max()))
        nobs = 4 + 5 * self.N + self.NH * 5
        self.observation_space = gym.spaces.Box(-5, 5, shape=(nobs,), dtype=np.float32)
        self.action_space = gym.spaces.Box(-1, 1, shape=(self.N + 4 * self.NH,), dtype=np.float32)

    # ---- trạng thái
    def reset(self, seed=None, options=None, start=None):
        if seed is not None:
            self.rng = np.random.default_rng(seed)
        if start is not None:
            self.t0 = start
        elif self.randomize:
            self.t0 = int(self.rng.integers(0, self.T - self.ep_steps + 1))
        else:
            self.t0 = 0
        self.t = self.t0
        st = self.st
        self.E = {i: st[i]["theta_B"] for i in self.I}
        self.M = {i: st[i]["theta_H"] for i in self.H}
        self.ufp = {i: 0 for i in self.H}; self.uep = {i: 0 for i in self.H}; self.Pfp = {i: 0.0 for i in self.H}
        self.D = {i: [0.0, 0.0] for i in self.H}
        self.Z = {i: [0.0, 0.0] for i in self.H}; self.Zpk = {i: [0.0, 0.0] for i in self.H}; self.nblock = 0
        return self._obs(), {}

    def _obs(self):
        t = min(self.t, self.T - 1); st = self.st; h = self.hour[t]
        dw = self.dow[t]
        o = [np.sin(2 * np.pi * h / 24), np.cos(2 * np.pi * h / 24), self.pv[t], 1.0 if dw >= 5 else 0.0]     # giờ, PV, cuối tuần
        o += list(self.load[t] / self.peak) + list(self.price[t] / self.pmax)
        o += [(st[i]["P_tr"] - self.load[t, k] + self.pv[t] * st[i]["pv_kWp"]) / self.peak[k] for k, i in enumerate(self.I)]   # còn dư bao nhiêu trước khi quá tải MBA
        o += list(self.price[min(t + 12, self.T - 1)] / self.pmax)                                                         # giá 1 giờ tới (biểu giá giờ đã biết trước)
        o += [(self.E[i] - st[i]["E_min"]) / max(1e-9, st[i]["E_max"] - st[i]["E_min"]) for i in self.I]
        for i in self.H:
            o += [(self.M[i] - st[i]["M_min"]) / (st[i]["M_max"] - st[i]["M_min"]), self.ufp[i], self.uep[i],
                  self.Pfp[i] / st[i]["P_fc"], 100.0 * self.D[i][0]]
        return np.asarray(o, np.float32)

    # ---- một bước
    def step(self, a):
        a = np.clip(np.asarray(a, float), -1, 1)
        st, t = self.st, self.t
        cost = 0.0; info = {"ov": 0.0, "buy": 0.0, "row": {}}
        aH = {i: tuple(a[self.N + 4 * k: self.N + 4 * k + 4]) for k, i in enumerate(self.H)}
        for k, i in enumerate(self.I):
            d = st[i]; load = self.load[t, k]; pv_av = self.pv[t] * d["pv_kWp"]
            # pin (giữ trong giới hạn – giống ràng buộc S1)
            pb = a[k] * d["P_bat"]
            dis = min(max(pb, 0.0), (self.E[i] - d["E_min"]) * d["eta_dis"] / DT)
            ch = min(max(-pb, 0.0), (d["E_max"] - self.E[i]) / (d["eta_ch"] * DT))
            Pf = Pe = 0.0; uf = ue = 0
            if i in self.H:
                sf, lf_, se, le = aH[i]
                Pmin_f, Pmin_e = d["fc_seg"][0][0], d["el_seg"][0][0]
                want_f = 1 if sf > 0.3 else (0 if sf < -0.3 else self.ufp[i])
                want_e = 1 if se > 0.3 else (0 if se < -0.3 else self.uep[i])
                if self.shield:      # KHIÊN hàng đợi sức khỏe: Z ≥ Z_max − ΔD_max thì buộc tắt (tắt không làm già → Z ≤ Z_max mọi lúc)
                    if self.Z[i][0] >= d["Zmax_fc"] - d["dD_fc_max"]:
                        self.nblock += want_f; want_f = 0
                    if self.Z[i][1] >= d["Zmax_el"] - d["dD_el_max"]:
                        self.nblock += want_e; want_e = 0
                if want_f and self.M[i] >= d["M_min"] + d["m_fc_max"]:                   # khóa (S2)
                    uf = 1; Pf = Pmin_f + 0.5 * (lf_ + 1) * (d["P_fc"] - Pmin_f)
                if want_e and self.M[i] <= d["M_max"] - d["m_el_max"]:                   # khóa (S3)
                    ue = 1; Pe = Pmin_e + 0.5 * (le + 1) * (d["P_el"] - Pmin_e)
            me = seg_mass(d["el_seg"], Pe) if ue else 0.0
            Pcp = S.E_CP * me / DT
            # cân bằng: thiếu thì mua lưới; thừa thì cắt PV, rồi bớt xả, rồi bớt/tắt FC (không bán lên lưới – giống S3)
            net = load + ch + Pe + Pcp - pv_av - dis - Pf
            pv = pv_av
            if net < 0:
                cut = min(-net, pv_av); pv -= cut; net += cut
            if net < 0:
                r = min(-net, dis); dis -= r; net += r
            if net < 0 and uf:
                if Pf + net >= d["fc_seg"][0][0]:
                    Pf += net; net = 0.0
                else:
                    net += Pf; Pf = 0.0; uf = 0
            if net < 0:          # vẫn thừa (hiếm): coi như cắt tải phụ, không tính tiền
                net = 0.0
            buy = net; ov = max(0.0, buy - d["P_tr"])
            mf = seg_mass(d["fc_seg"], Pf) if uf else 0.0
            c = (self.price[t, k] * buy + S.C_OV * ov + S.C_BAT * (ch + dis)) * DT
            self.E[i] += (d["eta_ch"] * ch - dis / d["eta_dis"]) * DT
            if i in self.H:
                dP = abs(Pf - self.Pfp[i]) if (uf and self.ufp[i]) else 0.0
                hp = max(0.0, (Pf - d["P_hi"]) / (d["P_fc"] - d["P_hi"])) if uf else 0.0
                dDf = d["fc_k_start"] * uf * (1 - self.ufp[i]) + d["fc_k_lc"] * dP + d["fc_k_lo"] * (1 if (uf and Pf < d["P_lo"]) else 0) + d["fc_k_hp"] * hp + d["fc_k_run"] * uf
                dDe = d["el_k_start"] * ue * (1 - self.uep[i]) + d["el_k_a0"] * ue
                c += d["mu_fc"] * dDf + d["mu_el"] * dDe
                self.M[i] += me - mf
                self.D[i][0] += dDf; self.D[i][1] += dDe
                self.Z[i][0] = max(self.Z[i][0] + dDf - d["delta_fc"], 0.0); self.Z[i][1] = max(self.Z[i][1] + dDe - d["delta_el"], 0.0)
                self.Zpk[i] = [max(self.Zpk[i][0], self.Z[i][0]), max(self.Zpk[i][1], self.Z[i][1])]
                self.ufp[i], self.uep[i], self.Pfp[i] = uf, ue, Pf
                info["row"].update({f"ufc_{i}": uf, f"uel_{i}": ue, f"Pfc_{i}": Pf, f"Pel_{i}": Pe, f"M_{i}": self.M[i]})
            info["row"].update({f"buy_{i}": buy, f"ov_{i}": ov, f"E_{i}": self.E[i], f"load_{i}": load})
            cost += c; info["ov"] += ov; info["buy"] += buy
        info["cost"] = cost
        self.t += 1
        done = (self.t - self.t0) >= self.ep_steps or self.t >= self.T
        return self._obs(), -cost / 100.0, bool(done), False, info


def make_gym(st, data, seed, shield=False):
    import gymnasium as gym

    class G(gym.Env):
        def __init__(self):
            super().__init__()
            self.e = StationsEnv(st, data, seed=seed, shield=shield)
            self.observation_space, self.action_space = self.e.observation_space, self.e.action_space

        def reset(self, seed=None, options=None):
            super().reset(seed=seed)
            return self.e.reset(seed=seed)

        def step(self, a):
            return self.e.step(a)
    return G()


def evaluate(policy, st, ev, vecnorm=None, shield=False):
    env = StationsEnv(st, ev, ep_steps=len(ev), randomize=False, shield=shield)
    obs, _ = env.reset(start=0)
    rows, cost, ov = [], 0.0, 0.0
    for t in range(len(ev)):
        o = obs if vecnorm is None else vecnorm.normalize_obs(obs[None])[0]
        act = policy(o)
        obs, r, done, _, info = env.step(act)
        cost += info["cost"]; ov += info["ov"]
        info["row"]["time"] = ev.index[t]; info["row"]["cost"] = info["cost"]; rows.append(info["row"])
    df = pd.DataFrame(rows).set_index("time")
    yrs = len(ev) * DT / 8760.0
    life = {i: (yrs / env.D[i][0] if env.D[i][0] > 0 else float("inf")) for i in env.H}
    life_el = {i: (yrs / env.D[i][1] if env.D[i][1] > 0 else float("inf")) for i in env.H}
    starts = {i: int(((df[f"ufc_{i}"].diff() == 1).sum())) for i in env.H}
    tank = {i: (float(df[f"M_{i}"].min()) - st[i]["M_min"]) for i in env.H}
    pb = float(env.price.mean())               # hiệu chỉnh cuối kỳ giống step3: năng lượng còn trong pin, bồn so với đầu kỳ
    vE = sum((env.E[i] - st[i]["theta_B"]) * st[i]["eta_dis"] for i in env.I)
    vM = sum((env.M[i] - st[i]["theta_H"]) * st[i]["eta_peak"] * S.LHV for i in env.H)
    return dict(cost=cost, cost_corr=cost - pb * (vE + vM), ov_MWh=ov * DT / 1000.0, life_fc=life, life_el=life_el, starts=starts, tank_gap=tank, df=df,
                fc_run=sum(df[f"ufc_{i}"].mean() for i in env.H) / len(env.H),
                D={i: list(env.D[i]) for i in env.H}, Zpk={i: list(env.Zpk[i]) for i in env.H}, nblock=env.nblock,
                Zmax={i: (st[i]["Zmax_fc"], st[i]["Zmax_el"]) for i in env.H}, plan=len(ev) * DT / 8760.0 / 5.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--algo", choices=["ppo", "sac"], default="ppo")
    ap.add_argument("--steps", type=float, default=3e6, help="số bước huấn luyện")
    ap.add_argument("--n_envs", type=int, default=4, help="số môi trường song song (PPO)")
    ap.add_argument("--eval_every", type=float, default=250_000)
    ap.add_argument("--ent", type=float, default=0.0, help="hệ số entropy (khuyến khích khám phá)")
    ap.add_argument("--gamma", type=float, default=0.995)
    ap.add_argument("--tag", default=None)
    ap.add_argument("--threads", type=int, default=1)
    ap.add_argument("--shield", action="store_true", help="bọc KHIÊN hàng đợi sức khỏe (Z ≥ Z_max − ΔD_max thì buộc tắt FC/EL) – khi học và khi thử")
    ap.add_argument("--eval_days", type=int, default=30, help="số ngày thử từ 2022-11-01 (tối đa 120 = hết 2/2023)")
    ap.add_argument("--wz", type=float, default=1e10, help="w_Z để tính Z_max của khiên (cùng mức bảo đảm với đề xuất)")
    args = ap.parse_args()
    import copy
    import torch
    torch.set_num_threads(args.threads)
    from stable_baselines3 import PPO, SAC
    from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize
    st, tr_all, ev = load_setup(eval_days=args.eval_days, w_Z=args.wz)
    SH = args.shield
    # tách 7 ngày cuối của dữ liệu huấn luyện làm TẬP KIỂM ĐỊNH để chọn mô hình (không nhìn tập thử tháng 11)
    va = tr_all.loc["2022-10-25":]
    tr = tr_all.loc[:"2022-10-24 23:55"]
    tag = args.tag or f"drl_{args.algo}_s{args.seed}"
    out = PROJECT_DIR / "results" / tag; out.mkdir(parents=True, exist_ok=True)
    n_envs = args.n_envs if args.algo == "ppo" else 1
    venv = VecNormalize(DummyVecEnv([(lambda k=k: make_gym(st, tr, args.seed * 100 + k, SH)) for k in range(n_envs)]),
                        norm_obs=True, norm_reward=True, gamma=args.gamma)
    if args.algo == "ppo":
        model = PPO("MlpPolicy", venv, learning_rate=3e-4, n_steps=2048, batch_size=512, n_epochs=10, gamma=args.gamma, gae_lambda=0.95,
                    clip_range=0.2, ent_coef=args.ent, max_grad_norm=0.5, policy_kwargs=dict(net_arch=[256, 256], log_std_init=-1.0),
                    seed=args.seed, verbose=0, device="cpu")
    else:
        model = SAC("MlpPolicy", venv, learning_rate=3e-4, buffer_size=300_000, batch_size=256, gamma=args.gamma, tau=0.005,
                    learning_starts=10_000, train_freq=1, gradient_steps=1, policy_kwargs=dict(net_arch=[256, 256]),
                    seed=args.seed, verbose=0, device="cpu")
    t0 = time.time(); done = 0; curve = []; best = (float("inf"), None, None)
    print(f"[*] {args.algo.upper()} hạt giống {args.seed}: huấn luyện {int(args.steps):,} bước trên {tr.index[0].date()}→{tr.index[-1].date()} "
          f"({n_envs} môi trường), chọn mô hình theo tập kiểm định {va.index[0].date()}→{va.index[-1].date()}, "
          f"thử trên {ev.index[0].date()}→{ev.index[-1].date()}", flush=True)
    pol = lambda o: model.predict(o, deterministic=True)[0]
    while done < args.steps:
        n = int(min(args.eval_every, args.steps - done))
        model.learn(total_timesteps=n, reset_num_timesteps=False)
        done += n
        venv.training = False
        rv = evaluate(pol, st, va, venv, SH)
        rt = evaluate(pol, st, ev, venv, SH)
        venv.training = True
        curve.append((done, rv["cost"], rt["cost"], 100 * rt["fc_run"], min(rt["life_fc"].values())))
        if rv["cost"] < best[0]:
            best = (rv["cost"], done, copy.deepcopy(rt))
            model.save(out / "model_best.zip"); venv.save(str(out / "vecnorm_best.pkl"))
        print(f"  {done:>9,} bước | {(time.time() - t0) / 60:5.1f} phút | kiểm định 7 ngày {rv['cost']:,.0f} | thử {args.eval_days} ngày {rt['cost']:,.0f} CNY | "
              f"vượt MBA {rt['ov_MWh']:.1f} MWh | FC chạy {100 * rt['fc_run']:.0f}% | FC sống ≥ {min(rt['life_fc'].values()):.1f} năm", flush=True)
    r = best[2]
    r["df"].round(5).to_csv(out / "timeseries.csv")
    rs = None
    if not SH:   # BỌC KHIÊN KHI TRIỂN KHAI: cùng mô hình tốt nhất, KHÔNG học lại, chỉ thêm khiên hàng đợi sức khỏe
        mb = (PPO if args.algo == "ppo" else SAC).load(str(out / "model_best.zip"), device="cpu")
        vn = VecNormalize.load(str(out / "vecnorm_best.pkl"), venv); vn.training = False
        rs = evaluate(lambda o: mb.predict(o, deterministic=True)[0], st, ev, vn, True)
        rs["df"].round(5).to_csv(out / "timeseries_shield.csv")
    L = [f"DRL ({args.algo.upper()}{' + KHIÊN hàng đợi sức khỏe' if SH else ''}) – hạt giống {args.seed} – {int(args.steps):,} bước huấn luyện ({(time.time() - t0) / 60:.0f} phút) – "
         f"mô hình chọn theo tập kiểm định (tốt nhất ở {best[1]:,} bước) – thử {args.eval_days} ngày từ 2022-11-01 | k_run = {S.AGE.get('k_run', 0):.4g} µV/h",
         f"  K2 – chi phí (gồm giá lão hóa): {r['cost']:,.0f} CNY",
         f"  K2 hiệu chỉnh cuối kỳ: {r['cost_corr']:,.0f} CNY",
         f"  K6 – vượt giới hạn MBA: {r['ov_MWh']:.2f} MWh",
         "  K7 – tuổi thọ dự kiến FC: " + ", ".join(f"{i}: {v:.1f} năm" for i, v in r["life_fc"].items())
         + " | EL: " + ", ".join(f"{i}: {v:.1f} năm" for i, v in r["life_el"].items()),
         "  số lần bật FC: " + ", ".join(f"{i}: {v}" for i, v in r["starts"].items()) + f" | FC chạy {100 * r['fc_run']:.1f}% thời gian",
         "  bồn cách đáy nhỏ nhất: " + ", ".join(f"{i}: {v:.1f} kg" for i, v in r["tank_gap"].items()),
         "  lão hóa FC cuối kỳ D (kế hoạch {:.4f}): ".format(r["plan"]) + ", ".join(f"{i}: {v[0]:.4f}" for i, v in r["D"].items()),
         "  Z FC lớn nhất / Z_max: " + ", ".join(f"{i}: {r['Zpk'][i][0]:.4f}/{r['Zmax'][i][0]:.4f}" for i in r["D"])
         + " | EL: " + ", ".join(f"{i}: {r['Zpk'][i][1]:.4f}/{r['Zmax'][i][1]:.4f}" for i in r["D"])
         + f" | khiên chặn {r['nblock']} lệnh bật/chạy",
         "  BẢO ĐẢM tuổi thọ FC (khiên): ≥ " + ", ".join(f"{i}: {5 * (1 - r['Zmax'][i][0]):.2f} năm" for i in r["D"]) if SH else "  KHÔNG có bảo đảm tuổi thọ (không khiên)",
         "  đường học (bước: kiểm định / thử CNY, FC chạy %, FC sống ≥ năm):",
         *[f"      {a:>9,}: {b:>9,.0f} / {c:>9,.0f} | {f:4.1f}% | {l:6.1f}" for a, b, c, f, l in curve],
         "  Lưu ý: " + ("khiên chỉ buộc TẮT khi Z ≥ Z_max − ΔD_max; tắt không làm già → Z ≤ Z_max với mọi chính sách" if SH else "DRL không có hàng đợi sức khỏe → không có bảo đảm tuổi thọ")
         + "; không chia sẻ giữa trạm → so với S3b (--no_share)."]
    if rs is not None:
        L += [f"KHIÊN KHI TRIỂN KHAI – cùng mô hình trên, không học lại, bọc khiên hàng đợi sức khỏe (Z ≥ Z_max − ΔD_max thì buộc tắt FC/EL):",
              f"  K2 (khiên) – chi phí (gồm giá lão hóa): {rs['cost']:,.0f} CNY",
              f"  K2 (khiên) hiệu chỉnh cuối kỳ: {rs['cost_corr']:,.0f} CNY",
              f"  K6 (khiên) – vượt giới hạn MBA: {rs['ov_MWh']:.2f} MWh",
              "  lão hóa FC cuối kỳ D (khiên) (kế hoạch {:.4f}): ".format(rs["plan"]) + ", ".join(f"{i}: {v[0]:.4f}" for i, v in rs["D"].items()),
              "  Z FC lớn nhất / Z_max (khiên): " + ", ".join(f"{i}: {rs['Zpk'][i][0]:.4f}/{rs['Zmax'][i][0]:.4f}" for i in rs["D"])
              + f" | khiên chặn {rs['nblock']} lệnh bật/chạy",
              "  BẢO ĐẢM tuổi thọ FC (khiên): ≥ " + ", ".join(f"{i}: {5 * (1 - rs['Zmax'][i][0]):.2f} năm" for i in rs["D"])]
    (out / "summary.txt").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
