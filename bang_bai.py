# -*- coding: utf-8 -*-
"""
BẢNG LaTeX CHO BÀI BÁO – đọc kết quả đã khóa, không mô phỏng lại.
  Vào : results/FINAL_summary.txt, results/extra_summary.txt (cỡ H2 ×2/×3), results/drl_summary_wz1e10.txt
  Ra  : results/paper_tables/tab2_methods.tex, tab3_robustness.tex, tab4_extensions.tex  (+ bản .txt để đọc nhanh)
Chạy:   python bang_bai.py            (cần \\usepackage{booktabs} trong bài)
"""
import argparse
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
ap = argparse.ArgumentParser()
ap.add_argument("--res", default=str(HERE / "results"))
args = ap.parse_args()
RES = Path(args.res)
OUT = RES / "paper_tables"; OUT.mkdir(parents=True, exist_ok=True)
rd = lambda f: (RES / f).read_text(encoding="utf-8") if (RES / f).exists() else ""
S, X, K = rd("FINAL_summary.txt"), rd("extra_summary.txt") or "", rd("drl_summary_wz1e10.txt")
if not S:
    raise SystemExit("Thiếu results/FINAL_summary.txt – chạy reproduce_all.py trước.")
X = X or S                                       # extra_summary cũng nằm trong FINAL_summary (giai đoạn X)
K = K or S
num = lambda x: float(x.replace(",", ""))
pc = lambda a, b: 100.0 * (a / b - 1.0)
fm = lambda v, d=1: f"{v:+.{d}f}".replace("-", "$-$")
mm = lambda v, d=1: f"{v:.{d}f}".replace("-", "$-$")


def sec(text, head):
    """Lấy một khối trong FINAL_summary bắt đầu bằng dòng chứa head."""
    i = text.find(head)
    if i < 0:
        return ""
    j = text.find("\n######", i + len(head) + 200)
    return text[i: j if j > 0 else len(text)]


# ------------------------------------------------------------------ Bảng 1 trong FINAL_summary
T = {}
PAT = {"S1": "S1 – không H2", "S3": "S3 – ĐỀ XUẤT", "B0": "B0 – Lyapunov không tính lão hóa", "rule": "B2 – quy tắc",
       "mpc": r"B1 – MPC 24 h \(dự báo\)", "mpc_or": r"B1\* – MPC 24 h biết trước", "mpcL": r"B1L – MPC \+ ràng buộc tuổi thọ",
       "mpcL_or": r"B1L\* – MPC biết trước \+ tuổi thọ", "mpcV": "B1V – MPC được vay", "mpcV_or": r"B1V\* – MPC được vay, biết trước"}
for k, p in PAT.items():
    m = re.search(p + r"[^\n]*?\s([\d,]{6,})\s+[\d,]{6,}\s+[-+][\d.]+%\s+(?:[-+][\d.]+%|—)\s+([\d.]+)\s+\S+\s+([\d.]+|nan)", S)
    if m:
        T[k] = dict(cost=num(m.group(1)), ov=float(m.group(2)), life=m.group(3))
cs = re.search(r"C\* \(biết trước tương lai, LP\): ≥ ([\d,]+)", S)
CSTAR = num(cs.group(1)) if cs else None
b0eol = re.findall(r"hết tuổi thọ \(D = 1\): năm thứ ([\d.]+)", S)

# ------------------------------------------------------------------ Bảng II – so sánh phương pháp
if "S1" not in T or "S3" not in T:
    raise SystemExit("Bảng 1 trong FINAL_summary.txt thiếu S1/S3 – chạy đủ giai đoạn B của reproduce_all.py trước.")
s1, best = T["S1"], T.get("mpc_or")
ach = lambda r: 100.0 * (s1["ov"] - r["ov"]) / (s1["ov"] - best["ov"]) if best else float("nan")
fa = lambda r: f"{ach(r):.0f}" if best else "--"
ROWS = [("Battery only (no H$_2$)", "S1", "--"), (r"\textbf{Proposed}", "S3", r"\textbf{proven}"),
        ("MPC, forecasts", "mpc", "none"), (r"MPC, aging budget $\delta t$", "mpcL", "plan only"),
        (r"MPC, aging budget $\delta t+Z_{\max}$", "mpcV", "plan only"),
        ("Lyapunov without aging", "B0", f"none (EoL {min(map(float, b0eol)):.1f} yr)" if b0eol else "none"),
        ("Rule-based", "rule", "none")]
CLV = [(r"MPC$^\star$", "mpc_or", "none"), (r"MPC$^\star$, aging budget $\delta t$", "mpcL_or", "plan only"),
       (r"MPC$^\star$, aging budget $\delta t+Z_{\max}$", "mpcV_or", "plan only")]
L = [r"% Bảng II – sinh tự động bởi bang_bai.py từ results/FINAL_summary.txt",
     r"\begin{table*}[t]\centering",
     r"\caption{Methods compared on the seven stations, 30 days (Nov.~2022). Cost includes stack aging at the stack price.}\label{tab:methods}",
     r"\setlength{\tabcolsep}{3.2pt}\footnotesize",
     r"\begin{tabular}{lrrrrc}\toprule",
     r"Method & Cost & $\Delta$cost & Above limit & Achieved & Lifetime \\",
     r" & (k CNY) & (\%) & (MWh) & (\%)$^\dagger$ & guarantee \\ \midrule"]
for lab, k, gu in ROWS:
    r = T.get(k)
    if not r:
        continue
    dc = "--" if k == "S1" else fm(pc(r["cost"], s1["cost"]))
    a = "--" if k == "S1" else fa(r)
    c = f"{r['cost'] / 1e3:,.1f}"
    if k == "S3":
        c, dc, a = rf"\textbf{{{c}}}", rf"\textbf{{{dc}}}", rf"\textbf{{{a}}}"
    L.append(f"{lab} & {c} & {dc} & {r['ov']:.1f} & {a} & {gu} \\\\")
L.append(r"\midrule \multicolumn{6}{l}{\emph{Clairvoyant (knows the next 24 h exactly; not implementable):}} \\")
for lab, k, gu in CLV:
    r = T.get(k)
    if r:
        L.append(f"{lab} & {r['cost'] / 1e3:,.1f} & {fm(pc(r['cost'], s1['cost']))} & {r['ov']:.1f} & {ach(r):.0f} & {gu} \\\\")
if CSTAR:
    L.append(rf"$C^\star$ (LP lower bound, 30 days) & {CSTAR / 1e3:,.1f} & {fm(pc(CSTAR, s1['cost']))} & -- & -- & -- \\")
# khối dự báo tốt dần cho MPC-V (cùng ngân sách tuổi thọ)
FB = re.findall(r"α = (0\.25|0\.5|0\.75)\s+nMAE phụ tải\s+([\d.]+)%\s+chi phí\s+([\d,]+)\s+so S1\s+([-+]?[\d.]+)%\s+so ĐỀ XUẤT\s+[-+]?[\d.]+%\s+vượt MBA\s+([\d.]+) MWh", X)
if FB:
    L.append(r"\midrule \multicolumn{6}{l}{\emph{MPC, aging budget $\delta t+Z_{\max}$, with better forecasts (hourly load nMAE):}} \\")
    for al, e, c, dc, ov in FB:
        r_ = dict(cost=num(c), ov=float(ov))
        L.append(rf"nMAE {float(e):.0f}\% & {num(c) / 1e3:,.1f} & {fm(float(dc))} & {float(ov):.1f} & {ach(r_):.0f} & plan only \\")
# khối không chia sẻ giữa trạm: PPO và PPO + khiên
s1b = re.search(r"S1b không H2, k\. chia sẻ\s+([\d,]+)", K); s3b = re.search(r"S3b không chia sẻ\s+([\d,]+)\s+[\d.]+%\s+([\d.]+)", K)
ppo = re.search(r"PPO trung bình\s+([\d,]+)\s+[\d.]+%\s+([\d.]+).*?độ lệch chuẩn chi phí ([\d,]+)", K)
if s1b and s3b and ppo:
    b_ = num(s1b.group(1))
    L.append(r"\midrule \multicolumn{6}{l}{\emph{Without inter-station sharing (as for PPO):}} \\")
    L.append(f"Proposed & {num(s3b.group(1)) / 1e3:,.1f} & {fm(pc(num(s3b.group(1)), b_))} & {float(s3b.group(2)):.1f} & -- & proven \\\\")
    L.append(rf"PPO, 3 seeds & {num(ppo.group(1)) / 1e3:,.1f}$\pm${num(ppo.group(3)) / 1e3:.1f} & {fm(pc(num(ppo.group(1)), b_))} & "
             rf"{float(ppo.group(2)):.1f} & -- & none \\")
L += [r"\bottomrule\end{tabular}",
      r"\\[2pt]\parbox{0.8\textwidth}{\scriptsize $\Delta$cost relative to battery only (in the sharing-free block: to battery only without sharing; costs there are before the end-of-period storage correction, which changes them by $<$0.4\%). "
      r"$^\dagger$Share of the overload reduction of MPC$^\star$ that the method achieves. "
      r"``Plan only'': the aging budget constrains each 24-h plan; no pathwise proof.}",
      r"\end{table*}"]
(OUT / "tab2_methods.tex").write_text("\n".join(L), encoding="utf-8")

# ------------------------------------------------------------------ Bảng III – độ vững
J, G = sec(S, "VIỆC 4.4 – ĐỘ NHẠY"), sec(S, "VIỆC 4.2 – SAI LỆCH MÔ HÌNH")
REN = {"điện máy nén kWh/kg": ("Compressor", " kWh/kg"), "giá stack FC": ("FC stack cost", ""), "giá stack EL": ("EL stack cost", ""),
       "giới hạn chia sẻ kW": ("Sharing limit", " kW"), "hao mòn pin CNY/kWh": ("Battery wear", " CNY/kWh"),
       "MBA (× đỉnh tải)": ("Connection limit", r"$\times$peak"), "quy mô PV": ("PV size", "")}
L = [r"% Bảng III – sinh tự động bởi bang_bai.py",
     r"\begin{table}[t]\centering",
     r"\caption{Robustness of the proposed controller (30 days). All theoretical checks pass in every case.}\label{tab:robust}",
     r"\setlength{\tabcolsep}{3.5pt}\footnotesize",
     r"\begin{tabular}{lrr}\toprule",
     r"Case & Cost red.\ (\%) & Overload red.\ (\%) \\ \midrule",
     r"\multicolumn{3}{l}{\emph{Sensitivity (relative to battery only)}} \\"]
for m in re.finditer(r"\n(điện máy nén kWh/kg|giá stack FC|giá stack EL|giới hạn chia sẻ kW|hao mòn pin CNY/kWh|MBA \(× đỉnh tải\)|quy mô PV)\s+"
                     r"(× ?[\d,]+|[\d,]+)\s+[\d,]+\s+[-+]?[\d.]+%\s+([-+]?[\d.]+)%\s+([-+]?[\d.]+)%", J):
    L.append(f"{REN[m.group(1)][0]} {m.group(2).replace(',', '.').replace('× ', r'$\times$')}{REN[m.group(1)][1]} & "
             f"{mm(-float(m.group(3)))} & {mm(-float(m.group(4)))} \\\\")
for m in re.finditer(r"c_ov =\s*(\d+) CNY/kWh\s+S1\s+[\d,]+\s+S3\s+[\d,]+\s+chi phí\s+([-+]?[\d.]+)%\s+vượt MBA\s+[\d.]+ →\s+[\d.]+ MWh \(\s*([-+]?[\d.]+)%\)", X):
    if m.group(1) != "5":                          # 5 CNY/kWh là cấu hình chính
        L.append(f"Overload penalty {m.group(1)} CNY/kWh & {mm(-float(m.group(2)))} & {mm(-float(m.group(3)))} \\\\")
for m in re.finditer(r"chia\s+(\d+) bước\s+[\d,]+\s+chi phí\s+([-+]?[\d.]+)%\s+vượt MBA\s+[\d.]+ MWh \(\s*([-+]?[\d.]+)%\)", X):
    L.append(f"Start-up price spread $N_s={m.group(1)}$ & {mm(-float(m.group(2)))} & {mm(-float(m.group(3)))} \\\\")
L += [r"\midrule", r"Case & $\Delta$cost (\%) & Min.\ tank margin (kg) \\ \midrule",
      r"\multicolumn{3}{l}{\emph{Model mismatch (relative to exact model)}} \\"]
MM = {"M1": "smooth true curves", "M2": "2-segment model", "M3": "1-segment model", "M4": "aged stack, no update",
      "M5": "aged stack, daily update", "M6": r"efficiency bias $+10\%$", "M7": r"efficiency bias $-10\%$"}
for m in re.finditer(r"\n(M[1-7])\s+[\d,]+\s+([-+]?[\d.]+)%\s+[\d.]+%\s+[\d.]+%\s+([\d.]+)", G):
    L.append(f"{m.group(1)} {MM[m.group(1)]} & {fm(float(m.group(2)), 2)} & {float(m.group(3)):.1f} \\\\")
L += [r"\bottomrule\end{tabular}", r"\end{table}"]
(OUT / "tab3_robustness.tex").write_text("\n".join(L), encoding="utf-8")

# ------------------------------------------------------------------ Bảng IV – mở rộng
I_, H_, D_, E_ = sec(S, "VIỆC 4.3 – MỞ RỘNG MẠNG"), sec(S, "VIỆC 3.1–3.2 – ADMM"), sec(S, "VIỆC 2.6 – H2 SO VỚI PIN LỚN HƠN"), sec(S, "######## grid33_6thang_vv")
L = [r"% Bảng IV – sinh tự động bởi bang_bai.py",
     r"\begin{table*}[t]\centering",
     r"\caption{Extensions: scale, distributed solution, hardware size, grid impact.}\label{tab:ext}",
     r"\setlength{\tabcolsep}{3.5pt}\footnotesize",
     r"\begin{tabular}{lll}\toprule",
     r"Case & Result & Remark \\ \midrule"]
for m in re.finditer(r"\n\s+(20|35|50)\s+([\d.]+)\s+([\d.]+)\s+[\d,]+\s+([-+][\d.]+)%\s+[\d.]+\s+([-+][\d.]+)%", I_):
    L.append(rf"$N={m.group(1)}$ charging nodes & cost {fm(float(m.group(4)))}\%, overload {fm(float(m.group(5)))}\% & "
             rf"solve {1e3 * float(m.group(2)):.0f} ms/step (max {1e3 * float(m.group(3)):.0f}) \\")
best = min(((float(m.group(2)), m.group(1)) for m in re.finditer(r"\n(k=\d+, ρ=[\de.-]+)\s+[\d,]+\s+([\d.]+)%", H_)), default=None)
worst = max(((float(m.group(2)), m.group(1)) for m in re.finditer(r"\n(k=\d+, ρ=[\de.-]+)\s+[\d,]+\s+([\d.]+)%", H_)), default=None)
if best:
    L.append(rf"ADMM, 7 stations & {best[0]:.2f}--{worst[0]:.2f}\% above centralized & guarantees kept (early stopping) \\")
for k in ("2", "3"):
    m = re.search(rf"H2 × {k}\s+([\d,]+)\s+([-+][\d.]+)%\s+([\d.]+) MWh\s+([-+][\d.]+)%", X)
    if m:
        L.append(rf"H$_2$ chain $\times{k}$ & cost {fm(float(m.group(2)))}\%, overload {fm(float(m.group(4)))}\% & {"overload cut grows, still saves" if float(m.group(2)) < 0 else "overload cut grows, cost exceeds battery only"} \\")
m = re.search(r"PIN HÒA VỐN: cần thêm ≈ ([\d,]+) kWh pin", D_)
if m:
    L.append(rf"Larger battery instead of H$_2$ & {num(m.group(1)) / 1e3:.1f} MWh gives the same overload cut & battery is cheaper \\")
gv = re.search(r"Đề xuất, có tính lưới\s+giờ thiếu áp giảm\s+([-\d.]+)%", E_); vv = re.search(r"Đề xuất, lưới \+ volt–var\s+giờ thiếu áp giảm\s+([-\d.]+)%", E_)
if gv and vv:
    L.append(rf"IEEE 33-bus, 6 months & under-voltage hours {fm(-float(gv.group(1)))}\% (grid-aware), {fm(-float(vv.group(1)))}\% (+volt--var) & AC power flow \\")
L += [r"\bottomrule\end{tabular}", r"\end{table*}"]
(OUT / "tab4_extensions.tex").write_text("\n".join(L), encoding="utf-8")

for f in sorted(OUT.glob("*.tex")):
    n = f.read_text(encoding="utf-8").count("\\\\")
    print(f"  ✓ {f.name}: {n} dòng")
print(f"XONG → {OUT}")
