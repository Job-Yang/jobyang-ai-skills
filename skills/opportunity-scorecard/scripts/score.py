#!/usr/bin/env python3
"""OPC 节点1·机会评估 —— 确定性打分与出卡。

分工（对齐 docs/scoring-rubric.md 与 docs/node-specs.md）：
  - LLM 干语义活：判地基门、逐维取证给分、写非共识申辩，填进一份 scoring JSON。
  - 本脚本干确定性活：校验契约硬要求（10 维齐全、每维必挂证据、地基门）→
    算 综合分 = Σ(维度分×权重) ÷ 11.5 → 按阈值定 verdict → 判 dark_horse →
    按 node-specs 的格式渲染 assess-<topic>.md，落 $ILOOP_DATA_ROOT/analysis/<ext-id>/。

它只做计算与格式化，不取证、不改代码、不碰 iLoop 闭环（见 EXTENDING.md 第 108 行）。
"""
import argparse
import datetime
import json
import os
import re
import sys
from pathlib import Path

# 信封 schema 版本：与冻结的 artifact_io.seal() 输出一致（opc-artifact/v1 信封格式）。
# 本字段只代表信封结构，不代表本 kit 版本；kit 版本见 CHANGELOG.md，不进信封。
OPC_VERSION = "0.2.0"

# topic slug 正则：必须与 artifact_io.py 的 SLUG 逐字一致（小写、单词间单连字符，
# 不允许前导/连续/尾部连字符）。artifact_io 已冻结，本正则是它的同步副本；
# 改前先跑 tests/ 回归里的 slug 一致性用例。
TOPIC_SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")

# 打分最小步长：证据驱动的判断只支持 0.5 一档，更小的小数是伪精确。
SCORE_STEP = 0.5

# 维度 → 权重，唯一事实源（对齐 scoring-rubric.md 的 10 维表）。
# 名称用 node-specs 机器读取表里的写法，保证下游能对上。权重和 = 11.5，即综合分除数。
DIMENSIONS = [
    ("痛点强度", 1.0),
    ("离钱近", 1.5),
    ("单位经济健康度", 1.5),
    ("一人可交付", 1.0),
    ("自然分发", 1.0),
    ("护城河", 1.5),
    ("市场趋势", 1.0),
    ("可验证性", 1.0),
    ("时机(Why now)", 1.0),
    ("AI-native契合度", 1.0),
]
WEIGHT = dict(DIMENSIONS)
DIVISOR = round(sum(WEIGHT.values()), 1)  # 11.5

# 四档：(下限, verdict, 档位文案)。桌面分天花板是"值得去验"，不是"确定做"。
TIERS = [
    (6.5, "validate", "🟢 值得去验"),
    (5.0, "refine", "🟡 有潜力·待补强"),
    (3.5, "caution", "🟠 谨慎"),
    (0.0, "reject", "🔴 暂不建议直接投入开发"),
]

# 占位/未填标记拦截词表：是 artifact_io.py 占位集合（"..." / "TODO" / "待补" / "—"）
# 的超集。artifact_io 已冻结、词表较松，score.py 在入口先拦更全的一组：
# N/A 家族（n/a、NA、N/A）、tbd、待填、xxx、无、省略号、<...>、裸横线都算没挂证据。
# 改动本表要回头对照 artifact_io.py validate_scorecard 的占位判断，保持超集关系。
_PLACEHOLDER = re.compile(r"^\s*(todo|tbd|待补|待填|xxx|n/?a|无|\.{2,}|…|—|-{1,}|<.*>)\s*$", re.I)


def _blank(v):
    return not isinstance(v, str) or not v.strip() or bool(_PLACEHOLDER.match(v.strip()))


def evaluate(data):
    """把 LLM 填好的评分 JSON 校验+算分，返回渲染所需的完整结果；不合规则抛 ValueError（一次性汇总所有问题）。"""
    errors = []

    topic = data.get("topic")
    if _blank(topic) or not TOPIC_SLUG.fullmatch(str(topic).strip()):
        errors.append("topic 必填，且为小写 slug（如 watch-sedentary；不允许连续连字符），跨节点保持一致")
    one_liner = data.get("one_liner")
    if _blank(one_liner):
        errors.append("one_liner 必填：一句话说清给谁、解决什么、怎么用")

    # 地基层硬门：命中即否（极窄，只卡逻辑不成立）。
    foundation = data.get("foundation") or {}
    found_pass = foundation.get("pass")
    if not isinstance(found_pass, bool):
        errors.append("foundation.pass 必填（true/false）：这命题本身立不立得住")
    if _blank(foundation.get("reason")):
        errors.append("foundation.reason 必填：地基门判定的理由")

    # 潜力层：10 维必须齐全、名称完全对齐、每维 0-10 且必挂证据（无证据即无分）。
    entries = data.get("dimensions") or []
    dims_in = {d.get("name"): d for d in entries if isinstance(d, dict)}
    if len(entries) != 10 or len(dims_in) != 10:
        errors.append("dimensions 必须是十个不同维度，不能重复")
    scored = []
    for name, weight in DIMENSIONS:
        d = dims_in.get(name)
        if d is None:
            errors.append(f"缺维度「{name}」：10 维必须齐全，不能增删改名")
            continue
        score = d.get("score")
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not (0 <= score <= 10):
            errors.append(f"维度「{name}」分数必须是 0-10 的数字")
            score = None
        elif abs(score * (1 / SCORE_STEP) - round(score * (1 / SCORE_STEP))) > 1e-6:
            errors.append(
                f"维度「{name}」分数 {score} 必须是 {SCORE_STEP:g} 的整数倍："
                "证据判断只支持半档，6.75 这类小数是伪精确")
            score = None
        if _blank(d.get("evidence")):
            errors.append(f"维度「{name}」没挂证据：每维必须有链接/原话/数据，无证据即不给分（回去取证）")
        if score is not None:
            scored.append((name, float(score), weight, d.get("evidence", "").strip()))

    extra = set(dims_in) - set(WEIGHT)
    if extra:
        errors.append(f"出现未定义维度 {sorted(extra)}：只认这 10 维")

    if errors:
        raise ValueError("评分 JSON 不合契约，先修下面这些再出卡：\n  - " + "\n  - ".join(errors))

    # —— 到这里数据已合规，开始确定性计算 ——
    weighted = sum(s * w for _, s, w, _ in scored)
    composite = round(weighted / DIVISOR, 2)

    # 地基门否决优先于分数：逻辑不成立=真的死，不给黑马逃生（逃生舱只救潜力层机械低分）。
    if found_pass is False:
        verdict, tier_label = "reject", "🔴 地基层否决（逻辑不成立）"
    else:
        for low, v, label in TIERS:
            if composite >= low:
                verdict, tier_label = v, label
                break

    # 非共识逃生舱：机械分没到"值得去验"线、但申辩有形状（可证伪判断 + 信息差都填了）→ 标黑马，强制人肉复看。
    rebuttal = data.get("rebuttal") or {}
    claim, blindspot = rebuttal.get("claim", ""), rebuttal.get("blindspot", "")
    rebuttal_shaped = not _blank(claim) and not _blank(blindspot)
    dark_horse = bool(found_pass is not False and composite < 6.5 and rebuttal_shaped)

    # 证据对抗自检（不阻断，只警告）：脚本无法判断证据真伪，但能抓两类结构异常——
    #   1) 同一证据被多个维度复用（偷懒打分的典型形状）；
    #   2) 无链接且含"内部消息/据传"这类不可验证措辞（伪造证据的风险形状）。
    evidence_warnings = []
    _seen = {}
    for name, score, weight, ev in scored:
        _seen.setdefault(ev.strip().lower(), []).append(name)
    for ev_key, names in _seen.items():
        if ev_key and len(names) > 1:
            evidence_warnings.append(
                f"同一证据被 {len(names)} 个维度复用（{'、'.join(names)}）：确认是不是一条料撑十维")
    _unverifiable = re.compile(r"内部消息|据传|听说|不便透露|有人说|小道", re.I)
    for name, score, weight, ev in scored:
        if _unverifiable.search(ev) and "http" not in ev:
            evidence_warnings.append(
                f"维度「{name}」证据无链接且含不可验证措辞（{ev[:20]}…）：需人复核真伪")

    # 复评驳回#3：全十维都建立在传闻/无链接证据上时，composite 仍按档位判
    # （机器 verdict 字段须与冻结 artifact_io 重算一致，不能改字符串），但产生确定性后果：
    #   evidence_lock=all_unverifiable 机器可读标志 + 卡片结论行强制带"禁止 clean 引用"警告。
    # 判据：evidence 含 http 链接 = 可验证 real；十维全部无链接 = 证据全传闻。
    real_evidence_count = sum(1 for _, _, _, ev in scored if "http" in ev.lower())
    evidence_lock = "all_unverifiable" if real_evidence_count == 0 else None
    if evidence_lock:
        evidence_warnings.append(
            "十维证据全部无可验证链接（传闻/假设占满）：本卡不得 clean validate/引用，先补一手证据")

    # 一句话诊断：LLM 给了就用；没给则从最高/最低分自动兜底。
    diagnosis = data.get("diagnosis", "").strip()
    if not diagnosis:
        top = sorted(scored, key=lambda x: -x[1])[:2]
        low = sorted(scored, key=lambda x: x[1])[:2]
        diagnosis = ("强在 " + "、".join(f"{n}({s:.0f})" for n, s, _, _ in top)
                     + "；凹陷在 " + "、".join(f"{n}({s:.0f})" for n, s, _, _ in low)
                     + "。补强方向需人审时补。")

    return {
        "topic": str(topic).strip(),
        "one_liner": one_liner.strip(),
        "upstream": data.get("upstream") or None,
        "profile": data.get("profile") or {},
        "foundation": {"pass": found_pass, "reason": foundation.get("reason", "").strip()},
        "dimensions": scored,
        "composite_score": composite,
        "verdict": verdict,
        "tier_label": tier_label,
        "evidence_lock": evidence_lock,
        "real_evidence_count": real_evidence_count,
        "dark_horse": dark_horse,
        "diagnosis": diagnosis,
        "rebuttal": {"claim": claim.strip(), "blindspot": blindspot.strip(), "shaped": rebuttal_shaped},
        "evidence_warnings": evidence_warnings,
        # 尺子置信度：先验权重/档位/地基门/dark_horse 不是统计结论，写进结果防被当成数据。
        "method_caveats": {
            "weight_source": "prior_experience",
            "statistical_significance": False,
            "note": "权重/档位/地基门/dark_horse 均为先验经验判断，无数据集校准，非统计显著；结论靠每维锚点与证据，composite 只辅助排序。",
        },
    }


def render(r, producer=None):
    """按 node-specs.md 节点1 的输出格式渲染 assess-<topic>.md 全文。"""
    created = datetime.datetime.now().astimezone().replace(microsecond=0).isoformat()
    p = r["profile"]
    comps = p.get("competitors") or []
    # produced_by：谁产的（跨平台留痕）。优先显式 OPC_PRODUCED_BY；否则 iLoop 托管=iloop，独立跑=standalone。
    produced_by = producer or os.environ.get("OPC_PRODUCED_BY") or ("iloop" if os.environ.get("ILOOP_DATA_ROOT") else "standalone")
    fm = [
        "---",
        "schema: opc-artifact/v1",
        "opc_node: assess",
        "artifact_kind: assess",
        f"opc_version: {OPC_VERSION}",
        f"topic: {r['topic']}",
        f"created: {created}",
        f"upstream: {json.dumps(r['upstream'] or 'null', ensure_ascii=False)}",
        f"produced_by: {json.dumps(produced_by, ensure_ascii=False)}",
        "human_review: pending",
        f"composite_score: {r['composite_score']:.2f}",
        f"verdict: {r['verdict']}",
        f"dark_horse: {'true' if r['dark_horse'] else 'false'}",
    ]
    # 复评驳回#3：证据全传闻时，front-matter 加机器可读 evidence_lock（extra 标量键，
    # 冻结 validate_envelope 允许；机器 verdict 档位不变以保持与重算一致）。
    if r.get("evidence_lock"):
        fm.append(f"evidence_lock: {r['evidence_lock']}")
    fm.append("---")
    lines = fm + [
        "",
        f"## 机会：{r['one_liner']}",
        "",
        "### 形态画像",
        (f"- 形态：{p.get('form','—')} | 端：{p.get('endpoint','—')} | "
         f"市场：{p.get('market','—')} | 变现：{p.get('monetization','—')}"),
        "- 竞品：" + ("；".join(comps) if comps else "—"),
        "",
        "### 地基层（硬门）",
        f"- 逻辑成立性：{'pass' if r['foundation']['pass'] else 'FAIL'} — {r['foundation']['reason']}",
        "",
        "### 潜力层（10 维，每维 0-10 + 证据）",
        "| 维度 | 分 | 权重 | 证据 |",
        "|------|----|----|------|",
    ]
    for name, score, weight, evidence in r["dimensions"]:
        evidence = evidence.replace("|", "&#124;").replace("\n", "<br>")
        lines.append(f"| {name} | {score:g} | {weight:.1f} | {evidence} |")
    # 复评驳回#3：证据全传闻时，结论行强制带"禁止 clean 引用"后果（正文 tier 文案，
    # 冻结校验只看机器 verdict/composite/dark_horse，不看正文文案）。
    conclusion_label = r["tier_label"]
    if r.get("evidence_lock"):
        conclusion_label += "　⚠ 证据全传闻·不可 clean 引用（先补一手证据）"
    lines += [
        "",
        "### 综合分与结论",
        f"- composite_score：{r['composite_score']:.2f} → {conclusion_label}",
        f"- 一句话诊断：{r['diagnosis']}",
        "",
        "### 非共识逃生舱",
    ]
    if r["rebuttal"]["shaped"]:
        lines.append(f"- 申辩：{r['rebuttal']['claim']}")
        lines.append(f"- 别人没看到的点：{r['rebuttal']['blindspot']}")
        if r["dark_horse"]:
            lines.append("- ⚑ dark_horse=true：机械分未到线但申辩有形状，**强制人肉复看**，不让尺子一票否掉。")
    else:
        lines.append("- 申辩：无")
    lines += [
        "",
        "### 尺子置信度声明",
        "- 权重/档位/地基门/dark_horse 均为先验经验判断，无数据集校准，**非统计显著**；结论靠每维锚点与证据，composite 只辅助排序。",
        "- composite_score 两位小数仅为与交接复算对齐，人读按 0.5 一档理解。",
    ]
    if r.get("evidence_warnings"):
        lines.append("- 证据警告（不阻断，需人看）：")
        for w in r["evidence_warnings"]:
            lines.append(f"  - {w}")
    lines.append("")
    lines.append("> 本卡是桌面评估。下一步由用户或当前编排决定；导入不代表人审放行。")
    lines.append("")
    return "\n".join(lines)


def _rejected(msg):
    """与 artifact_io.py 一致的错误信封：JSON 打到 stderr，exit 1。"""
    print(json.dumps({"status": "rejected", "error": msg}, ensure_ascii=False), file=sys.stderr)
    return 1


def main():
    parser = argparse.ArgumentParser(description="OPC assess 打分与出卡（纯内核，双模式）")
    parser.add_argument("--input", required=True, help="LLM 填好的评分 JSON 路径")
    parser.add_argument("--stdout", action="store_true",
                        help="不落盘，把渲染好的 assess markdown 打到标准输出（独立/离线运行用）")
    parser.add_argument("--out", help="显式评分卡输出路径")
    parser.add_argument("--producer", help="宿主或调用方标识")
    args = parser.parse_args()

    # 契约统一：输入缺维度/非法/JSON 坏掉时，不抛裸 traceback，
    # 输出与 artifact_io.py 相同形状的 JSON 错误信封到 stderr 并 exit 1。
    try:
        raw = Path(args.input).read_text(encoding="utf-8")
        result = evaluate(json.loads(raw))
    except OSError as e:
        return _rejected(f"读取输入失败：{args.input}: {e.strerror or e}")
    except json.JSONDecodeError as e:
        return _rejected(f"评分 JSON 不是合法 JSON：{e}")
    except ValueError as e:
        return _rejected(str(e))

    md = render(result, args.producer)
    if args.out:
        dest = Path(args.out).expanduser()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(md, encoding="utf-8")
        print(json.dumps({"status": "scored", "output": str(dest),
                          "composite_score": result["composite_score"]}, ensure_ascii=False))
        return

    # 双模式：
    #   ① iLoop 托管（注入 ILOOP_DATA_ROOT）→ 落盘 assess-<topic>.md，打 JSON 状态。
    #   ② 独立/离线（无 ILOOP_DATA_ROOT，或显式 --stdout）→ 直接把 markdown 打到 stdout，
    #      让 Mira 等别的 harness 自己接手保存。计算内核完全一致，只是落点不同。
    data_root = os.environ.get("ILOOP_DATA_ROOT")
    if args.stdout or not data_root:
        print(md)
        return

    ext_id = os.environ.get("ILOOP_EXTENSION_ID", "opc.product-pipeline")
    out_dir = Path(data_root).resolve() / "analysis" / ext_id
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"assess-{result['topic']}.md"
    dest.write_text(md, encoding="utf-8")

    print(json.dumps({
        "status": "scored",
        "output": str(dest),
        "composite_score": result["composite_score"],
        "verdict": result["verdict"],
        "dark_horse": result["dark_horse"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
