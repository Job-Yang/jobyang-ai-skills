#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 50 条历史材料生成三份种子数据，写进 data/：

- precedents.json：判例。每例每个工具一条，评语按「我们 / 工具1 / 工具2」原样切开，不改写、不总结。
- regression_seed.json：回归题。50 条原文，每天轮换抽几条让现用版重跑。
- clean_seed.json：干净对照。references/before-after-worktext.md 里的改稿和“可以不改”示例，再洗一遍应该基本不动。

只在更新 cases50.json、labels.json 或对照库之后重跑：python3 scripts/build_seed.py
"""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
DATA = os.path.join(SKILL, "data")
TOOLS = ["我们", "工具1", "工具2"]
ALIASES = {"我们": ["我们"], "工具1": ["工具1", "工具一"], "工具2": ["工具2", "工具二"]}


def split_comment(text):
    """评语按 <br/> 分段；段首点名哪个工具，这段就归哪个工具。没点名的段落归「总评」。"""
    segs = [s.strip() for s in re.split(r"<br\s*/?>|\n", text or "") if s.strip()]
    out = {"总评": []}
    for t in TOOLS:
        out[t] = []
    for i, s in enumerate(segs):
        if i == 0 and len(s) <= 40 and re.search(r"更好|最差|都不行|差不多|好一些|好一点|稍微好|都还行|都可以|半斤八两", s):
            out["总评"].append(s)
            continue
        owner = None
        head = s[:6]
        for t, names in ALIASES.items():
            if any(head.startswith(n) for n in names):
                owner = t
                break
        out[owner or "总评"].append(s)
    return out


def build_precedents(cases, labels):
    rows = []
    for c in cases:
        cid = str(c["id"])
        parts = split_comment(c.get("意见", ""))
        lab = labels.get(cid, {})
        for t in TOOLS:
            out = c.get(t) or ""
            if not out:
                continue
            rows.append({
                "pid": f"P-c{int(cid):02d}-{t}",
                "来源": f"cases50#{cid}",
                "文体": c.get("文体", ""),
                "原文": c.get("原始", ""),
                "改写": out,
                "工具": t,
                "保真档": lab.get(t, {}).get("f", ""),
                "通顺档": lab.get(t, {}).get("l", ""),
                "总评": "；".join(parts["总评"]),
                "评语": "；".join(parts[t]),
            })
    return rows


def build_regression(cases):
    return [{
        "id": f"reg-c{int(c['id']):02d}",
        "kind": "regression",
        "group": "regression",
        "任务": "改写",
        "文体": c.get("文体", ""),
        "力度": "标准",
        "原文": c.get("原始", ""),
        "上下文": "",
        "来源": f"cases50#{c['id']}",
    } for c in cases]


def build_clean(shuohua_dir=None):
    root = shuohua_dir or os.path.join(SKILL, "..", "haohao-shuohua")
    path = os.path.join(root, "references", "before-after-worktext.md")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        text = f.read()
    items = []
    for section in re.split(r"(?m)^##\s+", text)[1:]:
        sec, _, body = section.partition("\n")
        match = re.search(r"(?m)^\*\*✅\*\*\s*(.+)$", body)
        if not match:
            match = re.search(r"(?m)^改稿：\s*(.+)$", body)
        if not match and re.search(r"(?m)^处理：\s*保留", body):
            match = re.search(r"(?m)^原文：\s*(.+)$", body)
        if not match:
            continue
        good = match.group(1)
        n = len(items) + 1
        items.append({
            "id": f"clean-ba{n:02d}",
            "kind": "clean",
            "group": "clean",
            "任务": "改写",
            "文体": sec.split("/")[0].strip(),
            "力度": "标准",
            "原文": good.strip(),
            "上下文": "",
            "来源": "haohao-shuohua/references/before-after-worktext.md 修好稿",
        })
    return items


def main():
    cases = json.load(open(os.path.join(DATA, "cases50.json"), encoding="utf-8"))
    labels = json.load(open(os.path.join(DATA, "labels.json"), encoding="utf-8"))
    prec = build_precedents(cases, labels)
    reg = build_regression(cases)
    clean = build_clean()
    for name, obj in [("precedents.json", prec), ("regression_seed.json", reg), ("clean_seed.json", clean)]:
        with open(os.path.join(DATA, name), "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
        print(f"写出 data/{name}：{len(obj)} 条")
    empty = [p["pid"] for p in prec if not p["评语"]]
    print(f"没有单独点评的工具输出 {len(empty)} 条（只有总评）")


if __name__ == "__main__":
    main()
