#!/usr/bin/env python3
"""
export_spec.py — 从"拍板的最终 HTML"自动抽取结构化设计规范,供下游 coding 节点消费。

核心原则:HTML 是唯一事实源,spec 从它导出,不两头手写(否则必然漂移)。

抽取来源:
  1. HTML 里的 `:root { --xxx: yyy }` CSS 变量  → design tokens(颜色/圆角/间距/字体…)
  2. HTML 里的 <title>                          → 设计名
  3. 一个可选的同名 meta 文件 <name>.design.json → 补充语义:
       - reference   : 参考谁(信息量最高的指令,来自第2步)
       - screens     : 界面清单(来自第0步 screens.md)
       - interactions: 交互说明(来自第4步原型)
     (meta 是给"HTML 表达不了的语义"兜底;没有它也能只导出 tokens 部分)

产出:design-spec.md —— 人类可读 + coding 节点可直接照着建的结构化规范。

零第三方依赖(仅标准库)。

用法:
  python3 export_spec.py final.html [--meta final.design.json] [-o design-spec.md]
"""
import argparse
import json
import os
import re


def extract_title(html):
    m = re.search(r"<title>(.*?)</title>", html, re.I | re.S)
    return m.group(1).strip() if m else "未命名设计"


def extract_root_vars(html):
    """从 :root { ... } 抽 CSS 变量。返回 dict{var_name: value}。"""
    # 抓所有 :root 块(可能有多个,如明暗主题),合并
    blocks = re.findall(r":root\s*\{(.*?)\}", html, re.S)
    vars_ = {}
    for block in blocks:
        for name, val in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", block):
            vars_[name.strip()] = val.strip()
    return vars_


def classify_vars(vars_):
    """把 CSS 变量粗分类,方便 spec 分节呈现。"""
    buckets = {"颜色": {}, "字体": {}, "圆角": {}, "间距": {}, "动效": {}, "其他": {}}
    for k, v in vars_.items():
        key = k.lstrip("-")
        low = key.lower()
        if any(t in low for t in ("font", "mono", "sans", "serif")):
            buckets["字体"][k] = v
        elif "radius" in low:
            buckets["圆角"][k] = v
        elif any(t in low for t in ("space", "spacing", "gap", "pad")):
            buckets["间距"][k] = v
        elif any(t in low for t in ("dur", "ease", "motion", "transition")):
            buckets["动效"][k] = v
        elif any(t in low for t in ("color", "bg", "text", "accent", "border",
                                     "surface", "panel", "well", "green", "amber",
                                     "red", "hairline", "edge")):
            buckets["颜色"][k] = v
        else:
            buckets["其他"][k] = v
    return {k: v for k, v in buckets.items() if v}


def load_meta(path):
    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def md_table(d):
    lines = ["| 变量 | 值 |", "|---|---|"]
    for k, v in d.items():
        lines.append(f"| `{k}` | `{v}` |")
    return "\n".join(lines)


def build_spec(html_path, meta, topic=None, upstream=None, opc=False, producer="standalone"):
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()
    title = extract_title(html)
    vars_ = extract_root_vars(html)
    meta_tokens = meta.get("tokens", {})
    if isinstance(meta_tokens, dict):
        vars_.update({
            key: str(value)
            for key, value in meta_tokens.items()
            if isinstance(key, str) and key.startswith("--")
        })
    buckets = classify_vars(vars_)
    html_name = os.path.basename(html_path)

    reference = meta.get("reference", "")
    screens = meta.get("screens") or meta.get("pages", [])
    interactions = meta.get("interactions") or meta.get("actions", [])
    components = meta.get("components", [])
    states = meta.get("states", [])
    requirements = meta.get("requirements", [])
    journeys = meta.get("journeys", [])
    boundaries = meta.get("stageBoundaries", {})
    variants = meta.get("variants", [])
    prototype_index = meta.get("prototype_index", [])
    human_review = meta.get("humanReview", {})

    out = []
    # —— OPC front-matter(标准道必带;供下游机器读取 + 人审留痕)——
    if opc or topic:
        import datetime
        if not topic or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", topic):
            raise ValueError("交接需要合法 --topic；不能用占位符")
        out.append("---")
        out.append("schema: opc-artifact/v1")
        out.append("opc_node: design")
        out.append("artifact_kind: design")
        out.append("opc_version: 0.2.0")
        out.append(f"topic: {topic or '<topic>'}")
        out.append(f"created: {datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')}")
        out.append(f"upstream: {json.dumps(upstream or 'null', ensure_ascii=False)}")
        out.append(f"produced_by: {json.dumps(producer, ensure_ascii=False)}")
        out.append("human_review: pending")
        out.append("---")
        out.append("")

    out.append(f"# 设计规范 · {title}")
    out.append("")
    out.append("> 由 style-compass 从最终 HTML **自动导出**。HTML 是唯一事实源,改 HTML 后重新导出本文件。")
    out.append(f"> 视觉事实源:`{html_name}`(可运行,coding 时对照它)。")
    if human_review:
        out.append(
            f"> 人审状态：`{human_review.get('status', 'pending')}`"
            f" · {human_review.get('approvedAt', '')}"
            f" · {human_review.get('note', '')}"
        )
    out.append("")

    # 首要指令
    out.append("## 首要指令(给 coding 节点,信息量最高)")
    if reference:
        out.append(f"**参考 {reference} 那种美学**——实现时调动对该产品的理解,而不是机械套色值。")
    else:
        out.append("(未提供 reference;请对照最终 HTML 的实际观感实现)")
    out.append(f"\n最忠实的参考是可运行的 `{html_name}` 本身。下面的 tokens/结构/交互是它的结构化转写,供还原。")
    out.append("")

    out.append("## 阶段边界与追溯关系")
    if boundaries:
        labels = {
            "requirements": "需求",
            "structure": "结构",
            "interaction": "交互",
            "visualDirection": "高保真方向",
            "visualFinal": "视觉定稿",
            "delivery": "设计交付",
        }
        for key, label in labels.items():
            boundary = boundaries.get(key)
            if not isinstance(boundary, dict):
                continue
            out.append(f"### {label}")
            for field, title_ in (
                ("confirmed", "已确认"),
                ("flexible", "可发挥"),
                ("deferred", "待确定"),
                ("evidence", "验证证据"),
            ):
                values = boundary.get(field, [])
                if values:
                    out.append(f"- {title_}：" + "；".join(str(value) for value in values))
        out.append("")

    if requirements:
        out.append("### 需求")
        for item in requirements:
            out.append(
                f"- `{item.get('id', '')}` **{item.get('title', '')}**："
                f"{item.get('acceptance', '')}"
            )
        out.append("")

    if journeys:
        out.append("### 用户旅程")
        for item in journeys:
            action_ids = " → ".join(item.get("actionIds", []))
            out.append(
                f"- `{item.get('id', '')}` **{item.get('title', '')}**：{action_ids}"
            )
        out.append("")

    # 信息架构 / 页面清单(每页对应 PRD 哪个 in-scope 功能)——契约字段
    out.append("## 信息架构 / 页面清单")
    if screens:
        for i, s in enumerate(screens, 1):
            screen_id = s.get("id", "")
            screen_name = s.get("name") or s.get("title") or "(未命名)"
            out.append(f"### {i}. {screen_name}")
            if screen_id:
                out.append(f"- 页面编号：`{screen_id}`")
            if s.get("requirementIds"):
                out.append(f"- 对应需求：{', '.join(s['requirementIds'])}")
            if s.get("prd_feature"):
                out.append(f"- 对应 PRD 功能:{s['prd_feature']}")
            if s.get("contains"):
                out.append(f"- 包含:{s['contains']}")
            if s.get("actions"):
                out.append(f"- 主要动作:{s['actions']}")
        if meta.get("flow"):
            out.append(f"\n**跳转/信息架构**:{meta['flow']}")
    else:
        out.append("(meta 未提供页面清单;见 screens.md,或对照 HTML 结构)")
    out.append("")

    # 组件清单 —— 契约字段
    out.append("## 组件清单")
    if components:
        for c in components:
            out.append(f"- **{c.get('name','')}**:{c.get('note','')}")
    else:
        out.append("(meta 未提供组件清单;可对照 HTML 里复用的结构块列出)")
    out.append("")

    # Design tokens(从 HTML 自动抽)
    out.append("## 设计 Token（从 HTML 与阶段契约自动抽取）")
    if buckets:
        for cat, d in buckets.items():
            out.append(f"\n### {cat}")
            out.append(md_table(d))
    else:
        out.append("(未在 HTML 中找到 :root CSS 变量;建议渲染时把 tokens 写进 :root 以便导出)")
    out.append("")

    # 各状态(空/加载/错误)—— 契约字段
    out.append("## 各状态(空 / 加载 / 错误)")
    if states:
        for st in states:
            state_id = st.get("id", "")
            state_name = st.get("state") or st.get("title") or ""
            state_desc = st.get("desc") or st.get("description") or ""
            prefix = f"`{state_id}` " if state_id else ""
            out.append(f"- {prefix}**{state_name}**:{state_desc}")
    else:
        out.append("(meta 未提供状态说明;至少覆盖 空态/加载态/错误态,别让下游猜)")
    out.append("")

    # 关键交互说明(来自 meta.interactions)
    out.append("## 关键交互说明")
    if interactions:
        for it in interactions:
            action_id = it.get("id", "")
            action_name = it.get("on") or it.get("title") or ""
            behavior = it.get("behavior") or (
                f"{it.get('fromState', '')} → {it.get('toState', '')}"
            )
            prefix = f"`{action_id}` " if action_id else ""
            out.append(f"- {prefix}**{action_name}**:{behavior}")
    else:
        out.append("(meta 未提供交互说明;对照可点原型或 HTML 的 :hover/:active 与 JS)")
    out.append("")

    out.append("## 方案覆盖")
    if variants:
        for variant in variants:
            out.append(
                f"- **{variant.get('id', '')}**（{variant.get('phase', '')}）："
                f"页面 {', '.join(variant.get('pageIds', [])) or '无'}；"
                f"旅程 {', '.join(variant.get('journeyIds', [])) or '无'}；"
                f"动作 {', '.join(variant.get('actionIds', [])) or '无'}；"
                f"状态 {', '.join(variant.get('stateIds', [])) or '无'}"
            )
    else:
        out.append("(meta 未提供方案覆盖声明)")
    out.append("")

    # prototype 索引 —— 契约字段
    out.append("## prototype 索引")
    if prototype_index:
        for p in prototype_index:
            out.append(f"- `{p.get('file','')}` → {p.get('page','')}")
    else:
        out.append("(meta 未提供;列出 prototype/ 下每个 html 对应哪个页面,入口为 index.html)")
    out.append("")

    # 给 coding 的落地提示
    out.append("## 给 coding 节点的落地提示")
    out.append("- 优先对照可运行 HTML 还原视觉,tokens 表用于抽成常量(勿写死 hex)。")
    out.append("- 字体:若目标环境无对应字体会静默回退,需打包字体或选可加载 webfont;别只信字体名。")
    out.append("- 交互手感以可点原型为准,过渡时长/缓动照抓。")
    out.append("")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("html", help="拍板的最终 HTML 路径(通常是 prototype/index.html 或代表页)")
    ap.add_argument("--meta", default=None, help="可选的 <name>.design.json,补充页面/参考/组件/状态/交互/prototype索引")
    ap.add_argument("--topic", default=None, help="OPC topic slug(标准道必填,用于文件名和 front-matter)")
    ap.add_argument("--upstream", default=None, help="上游产物文件名,如 prd-<topic>.md")
    ap.add_argument("--opc", action="store_true", help="OPC 标准道:输出带 front-matter、文件名 design-spec-<topic>.md")
    ap.add_argument("--producer", default="standalone", help="生成宿主标识，如 mira；不自动猜测 iLoop")
    ap.add_argument("-o", "--out", default=None, help="显式输出路径(覆盖默认命名)")
    args = ap.parse_args()

    # meta 默认找同名 .design.json
    meta_path = args.meta
    if meta_path is None:
        guess = os.path.splitext(args.html)[0] + ".design.json"
        meta_path = guess if os.path.exists(guess) else None
    meta = load_meta(meta_path)
    # topic 兜底:meta 里有就用
    topic = args.topic or meta.get("topic")

    if args.opc and not topic:
        ap.error("--opc 需要 --topic 或 meta.topic")
    spec = build_spec(args.html, meta, topic=topic, upstream=args.upstream, opc=args.opc,
                      producer=args.producer)

    # 默认输出名:OPC 标准道用 design-spec-<topic>.md,否则 design-spec.md
    if args.out:
        out = args.out
    else:
        base = f"design-spec-{topic}.md" if topic else "design-spec.md"
        out = os.path.join(os.path.dirname(os.path.abspath(args.html)), base)
    with open(out, "w", encoding="utf-8") as f:
        f.write(spec)
    print(f"已导出设计规范: {out}")
    if args.opc:
        print(f"  (OPC 标准道:带 front-matter,topic={topic}, upstream={args.upstream or 'null'})")
    if meta_path:
        print(f"  (含 meta: {meta_path})")
    else:
        print("  (未找到 meta;仅导出 tokens+骨架。补 <name>.design.json 可加页面/组件/状态/交互/prototype索引)")


if __name__ == "__main__":
    main()
