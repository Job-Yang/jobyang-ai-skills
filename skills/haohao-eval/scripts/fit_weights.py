#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用 50 条人工评语拟合评分权重(不再拍)。

模型(与 scorer_v3 同构):
    统一分 = 保真系数 × (w_flu × 通顺分 + w_res × 残留分),  w_flu = 1 - w_res
    保真系数: 绿=1.0(锚) / 黄 / 橙 / 红          —— 3 个待拟合
    通顺分:   顺=100(锚) / 硬 / 不通顺           —— 2 个待拟合
    w_res                                        —— 1 个待拟合
    残留分: scorer_v3 正则算,是输入特征,不拟合

Ground truth = 人工评语拆成的偏好约束:
    winner=单方  → 赢家分 ≥ 各输方 + MARGIN
    winner=平    → 三者两两分差 ≤ TIE
    winner=A|B   → A、B 都 ≥ 第三方 + MARGIN,且 |A-B| ≤ TIE

损失 = Σ 违反量的平方(hinge) ,带单调约束 + 边界,多起点全局搜。
初值 = 当前拍的值 (w_res=.35, 黄.85 橙.60 红.30, 硬75 不通顺50)。
"""
import json, os, numpy as np
from scipy.optimize import minimize
import sys

# 路径全部相对本脚本解析,技能整体可移植
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR  = os.path.dirname(SCRIPT_DIR)
DATA_DIR   = os.path.join(SKILL_DIR, "data")
sys.path.insert(0, SCRIPT_DIR)
from scorer import score_residual   # scorer.py = 最新 v3 评测尺

CASES  = json.load(open(os.path.join(DATA_DIR, "cases50.json"), encoding="utf-8"))
LABELS = json.load(open(os.path.join(DATA_DIR, "labels.json"), encoding="utf-8"))
TOOLS  = ["我们", "工具1", "工具2"]

# 预算 50×3 残留分(只算一次,是特征)
RES = {}
for it in CASES:
    cid = str(it["id"])
    RES[cid] = {t: score_residual(it.get(t, "") or "")[0] for t in TOOLS}

# 档位索引:fid ∈ {绿0,黄1,橙2,红3}  flu ∈ {顺0,硬1,不通顺2}
FID_IDX = {"绿": 0, "黄": 1, "橙": 2, "红": 3}
FLU_IDX = {"顺": 0, "硬": 1, "不通顺": 2}

def unpack(p):
    w_res = p[0]
    fid = np.array([1.0, p[1], p[2], p[3]])   # 绿锚1.0
    flu = np.array([100.0, p[4], p[5]])       # 顺锚100
    return w_res, fid, flu

def score_of(cid, tool, p):
    w_res, fid, flu = unpack(p)
    lab = LABELS[cid][tool]
    f = fid[FID_IDX[lab["f"]]]
    l = flu[FLU_IDX[lab["l"]]]
    r = RES[cid][tool]
    return f * ((1 - w_res) * l + w_res * r)

MARGIN = 8.0   # 赢家至少高出的分
TIE    = 12.0  # 齐平/并列容差

def constraints_report(p):
    """返回 (满足数, 总数, 违反明细)。"""
    ok = tot = 0
    viol = []
    for it in CASES:
        cid = str(it["id"])
        w = LABELS[cid]["winner"]
        s = {t: score_of(cid, t, p) for t in TOOLS}
        if w in ("平", "都差不多", "都不行"):
            tot += 1
            spread = max(s.values()) - min(s.values())
            if spread <= TIE: ok += 1
            else: viol.append((cid, f"平但分差{spread:.0f}>{TIE:.0f}"))
        elif "|" in w:
            co = w.split("|"); others = [t for t in TOOLS if t not in co]
            tot += 1
            good = all(min(s[c] for c in co) >= s[o] + MARGIN for o in others) if others else True
            close = abs(s[co[0]] - s[co[1]]) <= TIE
            if good and close: ok += 1
            else: viol.append((cid, f"并列 {w}: {[round(s[t]) for t in TOOLS]}"))
        else:
            others = [t for t in TOOLS if t != w]
            tot += 1
            if all(s[w] >= s[o] + MARGIN for o in others): ok += 1
            else: viol.append((cid, f"{w}应最高: {[(t,round(s[t])) for t in TOOLS]}"))
    return ok, tot, viol

def loss(p):
    L = 0.0
    for it in CASES:
        cid = str(it["id"])
        w = LABELS[cid]["winner"]
        s = {t: score_of(cid, t, p) for t in TOOLS}
        if w in ("平", "都差不多", "都不行"):
            spread = max(s.values()) - min(s.values())
            L += max(0, spread - TIE) ** 2
        elif "|" in w:
            co = w.split("|"); others = [t for t in TOOLS if t not in co]
            for o in others:
                for c in co:
                    L += max(0, (s[o] + MARGIN) - s[c]) ** 2
            L += max(0, abs(s[co[0]] - s[co[1]]) - TIE) ** 2
        else:
            for o in [t for t in TOOLS if t != w]:
                L += max(0, (s[o] + MARGIN) - s[w]) ** 2
    return L

# 约束:单调 绿1.0 ≥ 黄 ≥ 橙 ≥ 红 ≥ 0.05;  顺100 ≥ 硬 ≥ 不通顺 ≥ 10
cons = [
    {"type": "ineq", "fun": lambda p: 1.0 - p[1]},      # 黄 ≤ 1
    {"type": "ineq", "fun": lambda p: p[1] - p[2]},     # 黄 ≥ 橙
    {"type": "ineq", "fun": lambda p: p[2] - p[3]},     # 橙 ≥ 红
    {"type": "ineq", "fun": lambda p: p[3] - 0.05},     # 红 ≥ .05
    {"type": "ineq", "fun": lambda p: 100.0 - p[4]},    # 硬 ≤ 100
    {"type": "ineq", "fun": lambda p: p[4] - p[5]},     # 硬 ≥ 不通顺
    {"type": "ineq", "fun": lambda p: p[5] - 10.0},     # 不通顺 ≥ 10
]
bounds = [(0.05, 0.95), (0.05, 1.0), (0.05, 1.0), (0.05, 1.0), (10, 100), (10, 100)]

x0 = np.array([0.35, 0.85, 0.60, 0.30, 75.0, 50.0])  # 拍的初值

print("=== 拟合前(拍的初值) ===")
ok0, tot0, _ = constraints_report(x0)
print(f"初值参数: w_res={x0[0]}, 黄={x0[1]} 橙={x0[2]} 红={x0[3]}, 硬={x0[4]} 不通顺={x0[5]}")
print(f"偏好对满足: {ok0}/{tot0} ({ok0/tot0*100:.1f}%)  loss={loss(x0):.0f}")

# 多起点全局搜
best = None
rng = np.random.default_rng(42)
starts = [x0] + [np.array([
    rng.uniform(0.15, 0.55), rng.uniform(0.6, 0.95),
    rng.uniform(0.35, 0.75), rng.uniform(0.1, 0.5),
    rng.uniform(60, 90), rng.uniform(30, 65)]) for _ in range(60)]
for s0 in starts:
    r = minimize(loss, s0, method="SLSQP", bounds=bounds,
                 constraints=cons, options={"maxiter": 500, "ftol": 1e-6})
    if best is None or r.fun < best.fun:
        best = r

p = best.x
print("\n=== 拟合后 ===")
print(f"新参数: w_res={p[0]:.4f} (w_flu={1-p[0]:.4f}), "
      f"黄={p[1]:.4f} 橙={p[2]:.4f} 红={p[3]:.4f}, 硬={p[4]:.2f} 不通顺={p[5]:.2f}")
ok1, tot1, viol = constraints_report(p)
print(f"偏好对满足: {ok1}/{tot1} ({ok1/tot1*100:.1f}%)  loss={best.fun:.1f}")
print("违反明细:")
for cid, msg in viol:
    print(f"  #{cid}: {msg}")

# 导出新分数表
out = []
for it in CASES:
    cid = str(it["id"])
    row = {"id": cid, "文体": it["文体"]}
    for t in TOOLS:
        row[t] = round(score_of(cid, t, p), 1)
    row["winner"] = LABELS[cid]["winner"]
    out.append(row)
json.dump({"weights": {"w_res": round(p[0],4), "w_flu": round(1-p[0],4),
                       "fid": {"绿":1.0,"黄":round(p[1],4),"橙":round(p[2],4),"红":round(p[3],4)},
                       "flu": {"顺":100,"硬":round(p[4],2),"不通顺":round(p[5],2)}},
           "satisfy": f"{ok1}/{tot1}", "scores": out},
          open(os.path.join(os.getcwd(), "fitted_weights.json"),"w",encoding="utf-8"),
          ensure_ascii=False, indent=2)
print(f"\n写出 {os.path.join(os.getcwd(), 'fitted_weights.json')}")
