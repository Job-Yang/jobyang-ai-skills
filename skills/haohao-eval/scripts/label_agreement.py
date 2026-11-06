#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""多人标注一致性工具：解决「50 条单人标签是循环自证地基」的扩样第一步。

背景（诚实声明）：
现在 data/labels.json 的 50 条标签只有作者一个人标，没有第二个人复核。单人标注 +
作者自己就是被评测对象（写规则的人也是裁判的判例来源），天然循环自证：
用这批标签拟合出来的东西一定会跟作者自洽。所以这批标签现在只够做启发式冒烟
（裁判体检抽 9 条看手感），**不足以支撑任何显著性结论**。

这个工具干什么：
等你（或另一个标注者）把同样的题目标第二遍，用它算两个人判得一不一致：
- pairwise：每一对标注者，在共同标的题上的原始一致率（f 保真档、l 通顺档）+ Cohen's kappa
- matrix：标注者两两一致率表
- disagreements：导出两人 f 档不一致的题，带 case_id 和两档分歧，空一列给你写「以谁为准」

数据格式：CSV 长表，每行一条标注，表头固定：
    case_id,annotator,f,l[,note]
    1,甲,绿,顺,
    1,乙,绿,顺,
    2,甲,红,顺,
    2,乙,橙,顺,
f ∈ {红,橙,黄,绿}（保真档，有序）；l ∈ {顺,硬,不通顺}（通顺档）。

kappa 解读（写在打印里）：<0.2 极差，0.2–0.4 一般，0.4–0.6 中等，0.6–0.8 高度，>0.8 几乎完美。
kappa 低不是谁错，是判据没对齐——先对着 disagreements 导出表把判据谈拢，再扩样。

纯标准库，不进每日召回流程（loop.py 从不调用它）。
"""
import argparse
import csv
import os
import sys

ORDER = {"红": 0, "橙": 1, "黄": 2, "绿": 3}


def load(path):
    rows = []
    with open(path, encoding="utf-8-sig") as f:
        for n, r in enumerate(csv.DictReader(f), 2):
            cid = (r.get("case_id") or "").strip()
            ann = (r.get("annotator") or "").strip()
            f_ = (r.get("f") or "").strip()
            l_ = (r.get("l") or "").strip()
            if not cid or not ann:
                raise SystemExit(f"{path} 第 {n} 行缺 case_id 或 annotator")
            if f_ not in ORDER:
                raise SystemExit(f"{path} 第 {n} 行 f 档是「{f_}」，只认 {'/'.join(ORDER)}")
            rows.append({"case_id": cid, "annotator": ann, "f": f_, "l": l_})
    if not rows:
        raise SystemExit(f"{path} 里一行标注都没有")
    return rows


def by_case(rows):
    cases = {}
    for r in rows:
        cases.setdefault(r["case_id"], {}).setdefault(r["annotator"], r)
    return cases


def kappa(labels):
    """labels: list of (a, b) pairs over the same items. 返回 (raw, kappa)。"""
    n = len(labels)
    if n == 0:
        return None, None
    cats = sorted({x for pair in labels for x in pair})
    same = sum(1 for a, b in labels if a == b)
    po = same / n
    from_a = {c: sum(1 for a, _ in labels if a == c) / n for c in cats}
    from_b = {c: sum(1 for _, b in labels if b == c) / n for c in cats}
    pe = sum(from_a[c] * from_b[c] for c in cats)
    k = (po - pe) / (1 - pe) if pe < 1 else 1.0
    return po, k


def pairs(rows):
    cases = by_case(rows)
    anns = sorted({r["annotator"] for r in rows})
    out = []
    for i in range(len(anns)):
        for j in range(i + 1, len(anns)):
            a, b = anns[i], anns[j]
            both = [c for c, d in cases.items() if a in d and b in d]
            fl, ll = [], []
            for c in both:
                fl.append((cases[c][a]["f"], cases[c][b]["f"]))
                ll.append((cases[c][a]["l"], cases[c][b]["l"]))
            po_f, k_f = kappa(fl)
            po_l, _ = kappa(ll)
            out.append({"a": a, "b": b, "n": len(both), "raw_f": po_f, "kappa_f": k_f, "raw_l": po_l})
    return out, cases, anns


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", help="标注长表 CSV（case_id,annotator,f,l[,note]）")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--pairwise", action="store_true", help="每对标注者：共同题数、原始一致率、kappa")
    g.add_argument("--matrix", action="store_true", help="标注者两两一致率表")
    g.add_argument("--disagreements", metavar="OUT_CSV", help="导出 f 档不一致的题，留出「以谁为准」空列")
    args = ap.parse_args(argv)

    rows = load(args.csv)
    pairs_, cases, anns = pairs(rows)

    if args.disagreements:
        a, b = anns[0], anns[1] if len(anns) >= 2 else (None, None)
        if len(anns) < 2:
            raise SystemExit("只有一个标注者，没有分歧可导出——先标第二遍")
        with open(args.disagreements, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["case_id", f"{a}_f", f"{b}_f", "差几档", "以谁为准", "备注"])
            n = 0
            for c in sorted(cases, key=lambda x: (len(x), x)):
                if a in cases[c] and b in cases[c]:
                    fa, fb = cases[c][a]["f"], cases[c][b]["f"]
                    if fa != fb:
                        w.writerow([c, fa, fb, abs(ORDER[fa] - ORDER[fb]), "", ""])
                        n += 1
        print(f"导出 {n} 条 f 档分歧 → {args.disagreements}")
        return 0

    header = f"{'标注者对':<16}{'共同题':>5}{'f一致率':>9}{'f kappa':>9}{'l一致率':>9}"
    print(header)
    print("-" * len(header))
    for p in pairs_:
        tag = f"{p['a']}×{p['b']}"
        print(f"{tag:<16}{p['n']:>5}{p['raw_f']:>9.2f}{p['kappa_f']:>9.2f}{(p['raw_l'] or 0):>9.2f}")
    print()
    print("kappa 解读：<0.2 极差，0.2–0.4 一般，0.4–0.6 中等，0.6–0.8 高度，>0.8 几乎完美。")
    print("样本量提醒：共同题 n<20 时 kappa 抖动很大，先当粗看，别当结论。")
    if len(anns) < 2:
        print("（现在只有一个标注者，算不出一致性——这正是 50 条单人标签的局限）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
