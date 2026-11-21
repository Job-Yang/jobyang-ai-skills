#!/usr/bin/env python3
"""library_doctor.py 的有效性自测（零第三方依赖，临时夹具，自动清理）。

证明两件事：
1. 一个完全合规的技能必须零误报（否则规则不可信，会冤枉好技能）；
2. 每个被埋的坏样例必须被对应规则 ID 命中（否则规则形同虚设）。

运行：python3 test_doctor.py
退出码：0 全过；1 有断言失败。
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import library_doctor as doctor  # noqa: E402

GOOD_DESC = (
    "把混乱的会议纪要整理成结构化结论与待办。适用于会后整理、长录音转写、多人讨论归纳；"
    "用户说「帮我整理这份纪要」「把这段讨论理一下」「会议要点是什么」时触发。"
    "不适用：实时翻译、纯事实摘要（一句话能说清的直接答）。"
)

GOOD_BODY = """# 好技能（合规夹具）

## 定位
把纪要整理成结论与待办。

## 触发与边界
本技能适用于会后整理。**不适用**于实时翻译和一句话能说清的纯摘要。

## 流程
1. 读全文，按人/主题归并。
2. 输出结论与待办。
完整字段见 [整理手册](references/good-guide.md)；句尾裸路径测试见 references/good-guide.md.；链接语法用 `[标题](url)`；超长会议见 [长手册](references/long-guide.md)。
执行脚本见 [整理脚本](scripts/do_thing.py)。

## 收口自检
- [ ] 待办都有责任人和可验证完成条件。
"""

GOOD_GUIDE = """# 整理手册

- 结论与待办分开。
- 保留争议，不强行合并。
"""

LONG_GUIDE = """# 长手册

## 目录
- [分段](#分段)
- [去重](#去重)
- [核验](#核验)

""" + "\n".join(f"## 小节{i}\n内容行 {i}。" for i in range(60))

DO_THING = "#!/usr/bin/env python3\nprint('ok')\n"


def w(root, skill, fname, content):
    d = Path(root) / skill
    d.mkdir(parents=True, exist_ok=True)
    p = d / fname
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def skill_md(name, desc, body, extra_fm=""):
    desc_line = "" if desc is None else f'description: "{desc}"\n'
    return f"---\nname: {name}\n{desc_line}{extra_fm}---\n{body}"


def build_good(root):
    w(root, "good-skill", "SKILL.md", skill_md("good-skill", GOOD_DESC, GOOD_BODY))
    w(root, "good-skill", "references/good-guide.md", GOOD_GUIDE)
    w(root, "good-skill", "references/long-guide.md", LONG_GUIDE)
    w(root, "good-skill", "scripts/do_thing.py", DO_THING)


def build_bad(root):
    w(root, "bad-name", "SKILL.md",
      skill_md("Bad_Name", GOOD_DESC, "边界：不适用时不触发。\n"))
    w(root, "no-desc", "SKILL.md",
      "---\nname: no-desc\n---\n正文写明了不适用边界。\n")
    w(root, "claude-thing", "SKILL.md",
      skill_md("claude-thing", GOOD_DESC, "边界：不适用时不触发。\n"))
    w(root, "broken-ref", "SKILL.md",
      skill_md("broken-ref", GOOD_DESC,
               "不适用：无。见 [丢失文件](references/missing.md)。\n"))
    w(root, "hard-bind", "SKILL.md",
      skill_md("hard-bind", GOOD_DESC,
               "不适用：无。数据在 " + "/Users/" + "fixture-user/secret/x.json。\n"))
    w(root, "too-long", "SKILL.md",
      skill_md("too-long", GOOD_DESC,
               "不适用：无。\n" + "\n".join(f"第 {i} 行内容" for i in range(520))))
    w(root, "open-fence", "SKILL.md",
      skill_md("open-fence", GOOD_DESC,
               "不适用：无。\n```python\nprint('未闭合')\n"))
    w(root, "orphan-file", "SKILL.md",
      skill_md("orphan-file", GOOD_DESC, "不适用：无。正文没引用任何资源。\n"))
    w(root, "orphan-file", "references/lonely.md", "我没被 SKILL.md 引用。\n")
    w(root, "double--dash", "SKILL.md",
      skill_md("double--dash", GOOD_DESC, "边界：不适用时不触发。\n"))
    w(root, "claude-bind", "SKILL.md",
      skill_md("claude-bind", GOOD_DESC, "不适用：无。安装到 ~/.claude/skills 目录。\n"))
    w(root, "self-orphan", "SKILL.md",
      skill_md("self-orphan", GOOD_DESC, "不适用：无。正文没提任何引用。\n"))
    w(root, "self-orphan", "references/lone.md", "我只在自己 lone.md 里写了文件名。\n")
    w(root, "ref-broken", "SKILL.md",
      skill_md("ref-broken", GOOD_DESC, "不适用：无。见 [手册](references/guide.md)。\n"))
    w(root, "ref-broken", "references/guide.md", "下一步见 [缺失参考](references/missing.md)。\n")
    w(root, "leaked-secret", "SKILL.md",
      skill_md("leaked-secret", GOOD_DESC,
               '不适用：无。\napi_key="AKIA1234567890ABCDEF" 见脚本。\n'))

    # C003 覆盖真空夹具：三个技能都碰到「源码调研×要成稿」，却都把它推走、无人认领。
    w(root, "vac-a", "SKILL.md", skill_md(
        "vac-a", "调研开源仓库源码搞懂机制；要写成给读者看的成稿走 vac-share。", "不适用其它。"))
    w(root, "vac-b", "SKILL.md", skill_md(
        "vac-b", "只接对外技术分享/博客/slides；对内调研开源仓库源码不适用。", "不适用其它。"))
    w(root, "vac-c", "SKILL.md", skill_md(
        "vac-c", "技术方案 RFC 评审；调研开源仓库源码写成报告这类不适用。", "不适用其它。"))
    # C001 悬空交接夹具：明确把任务指给一个库里不存在的技能。
    w(root, "dangling", "SKILL.md", skill_md(
        "dangling", GOOD_DESC, "需要时走 no-such-skill 技能承接。\n不适用其它。"))

    # B001/B003/B004/B005/X001-X004 夹具
    w(root, "bloated-desc", "SKILL.md", skill_md(
        "bloated-desc", GOOD_DESC + "补充说明与适用辨析。".replace("。", "：") + ("示例对比、" * 45),
        "不适用：无。\n"))
    w(root, "heavy-startup", "SKILL.md", skill_md(
        "heavy-startup", GOOD_DESC,
        "不适用：无。\n动手前先读 references/heavy.md。\n"))
    w(root, "heavy-startup", "references/heavy.md",
      "## 目录\n- [一](#一)\n- [二](#二)\n- [三](#三)\n" + "\n".join(f"内容行 {i}。" for i in range(265)))
    w(root, "crutch-skill", "SKILL.md", skill_md(
        "crutch-skill", GOOD_DESC,
        "不适用：无。\n读完仍不知道下一步该干嘛，视为本次失败，重做。\n"))
    w(root, "costume-skill", "SKILL.md", skill_md(
        "costume-skill", GOOD_DESC,
        "不适用：无。\n## 五段流水线（不是可选项）\n任何一篇的骨架都是固定五段。\n"))
    w(root, "maint-leak", "SKILL.md", skill_md(
        "maint-leak", GOOD_DESC,
        "不适用：无。\n## 维护说明\n发布前运行 check_vendored.py 检查漂移。\n"))

    w(root, "chain-a", "SKILL.md", skill_md(
        "chain-a", GOOD_DESC,
        "不适用：无。\nH2 是短关键词。\n定稿调用 chain-b 标准档清洗（冲突豁免本技能短标题）。\n"))
    w(root, "chain-b", "SKILL.md", skill_md(
        "chain-b", GOOD_DESC,
        "不适用：无。\n章节小标题直接写本节要点。\n完成后调用 chain-c 归档。\n"))
    w(root, "chain-c", "SKILL.md", skill_md(
        "chain-c", GOOD_DESC,
        "不适用：无。\n归档保存结果。\n"))
    w(root, "self-clash", "SKILL.md", skill_md(
        "self-clash", GOOD_DESC,
        "不适用：无。\n本技能不设全局禁令，详见 [细则](references/rules.md)。\n"))
    w(root, "self-clash", "references/rules.md",
      "默认要求：严禁使用紫色渐变背景。\n")
    w(root, "omni-skill", "SKILL.md", skill_md(
        "omni-skill",
        "任何一次改代码或写总结都要使用本技能校验。适用于所有任务，当给出「帮我检查一下」时触发。",
        "只有完全不涉及文本时跳过。\n"))
    w(root, "meta-close-skill", "SKILL.md", skill_md(
        "meta-close-skill", GOOD_DESC,
        "不适用：无。\n- **收口自检多答一句**：在结论后加一段过程反思。\n"))
    w(root, "short-coercive-skill", "SKILL.md", skill_md(
        "short-coercive-skill", GOOD_DESC,
        "不适用：无。\n" + "\n".join(f"{i}. 必须禁止不得强迫执行第 {i} 条。" for i in range(1, 35)) + "\n" + "\n".join(f"说明行 {j}。" for j in range(36))))


def verify_b002_and_metrics(failures: list[str]) -> None:
    tmp = Path(tempfile.mkdtemp(prefix="doctor-b002-"))
    try:
        root = tmp / "skills"
        root.mkdir()
        for i in range(6):
            desc = GOOD_DESC + f" 补充场景编号{i}。"
            w(root, f"s-{i}", "SKILL.md", skill_md(f"s-{i}", desc, "不适用：无。\n"))
        _, findings, metrics = doctor.check_library_with_metrics(root, max_desc_total=300)
        if not any(f["rule"] == "B002" for f in findings):
            failures.append("[漏报] 全库 description 超出 max_desc_total=300 时未报 B002")
        if metrics.get("desc_total_chars", 0) <= 300:
            failures.append(f"[metrics 错误] desc_total_chars 异常：{metrics}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def verify_x_positive_exemptions(failures: list[str]) -> None:
    tmp = Path(tempfile.mkdtemp(prefix="doctor-x-pos-"))
    try:
        root = tmp / "skills"
        root.mkdir()
        w(root, "yield-a", "SKILL.md", skill_md(
            "yield-a", GOOD_DESC,
            "不适用：无。\nH2 是短关键词。\n定稿调用 yield-b 标准档清洗（遵守上游小标题体例）。\n"))
        w(root, "yield-b", "SKILL.md", skill_md(
            "yield-b", GOOD_DESC,
            "不适用：无。\n无上游专门文体的独立成稿时，章节小标题直接写本节要点。\n"
            "由 yield-a 等上游文体技能调用时，遵守上游小标题体例，不改成论点句。\n"
            "背景详见 passive-ref/references/notes.md。\n"))
        w(root, "passive-ref", "SKILL.md", skill_md(
            "passive-ref", GOOD_DESC, "不适用：无。\n静态参考集。\n"))
        w(root, "up-src", "SKILL.md", skill_md(
            "up-src", GOOD_DESC, "不适用：无。\n需要调研时先读取 mid-guarded，再回本技能成稿。\n"))
        w(root, "mid-guarded", "SKILL.md", skill_md(
            "mid-guarded", GOOD_DESC,
            "不适用：无。\n仅独立成稿时调用 tail-end；被 up-src 作为前置调研调用时不在此环节调用 tail-end，由最终成稿技能统一收尾。\n"
            "需要借图时可选借用 up-src 的 diagram_kit render（只借图不走文档流程）。\n"))
        w(root, "tail-end", "SKILL.md", skill_md(
            "tail-end", GOOD_DESC, "不适用：无。\n最终收尾。\n"))
        _, findings = doctor.check_library(root)
        bad_x = [f for f in findings if f["rule"] in ("X001", "X002")]
        if bad_x:
            failures.append(f"[误报] X001/X002 正面豁免夹具误报：{bad_x}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    tmp = Path(tempfile.mkdtemp(prefix="doctor-fixture-"))
    try:
        root = tmp / "skills"
        root.mkdir()
        build_good(root)
        build_bad(root)

        _, findings = doctor.check_library(root)
        by = {}
        for f in findings:
            by.setdefault(f["skill"], set()).add(f["rule"])

        failures = []

        good_hits = by.get("good-skill", set())
        if good_hits:
            failures.append(f"[误报] 合规技能 good-skill 命中：{sorted(good_hits)}")

        expect = {
            "bad-name": "F002",
            "double--dash": "F002",
            "no-desc": "F008",
            "claude-thing": "F003",
            "broken-ref": "R001",
            "ref-broken": "R001",
            "hard-bind": "P001",
            "claude-bind": "P001",
            "too-long": "S001",
            "open-fence": "R002",
            "orphan-file": "S004",
            "self-orphan": "S004",
            "leaked-secret": "S006",
            "bloated-desc": "B001",
            "heavy-startup": "B003",
            "crutch-skill": "B004",
            "costume-skill": "B004",
            "maint-leak": "B005",
            "self-clash": "X003",
            "omni-skill": "X004",
            "meta-close-skill": "B004",
            "short-coercive-skill": "B004",
        }
        for skill, need in expect.items():
            got = by.get(skill, set())
            if need not in got:
                failures.append(f"[漏报] {skill} 应命中 {need}，实际 {sorted(got)}")

        # C003 覆盖真空：vac-a/b/c 围出的洞必须被库级扫到
        c003 = [f for f in findings if f["rule"] == "C003"]
        if not c003:
            failures.append("[漏报] vac-a/b/c 的覆盖真空未报 C003")
        # C001 悬空交接：dangling 指向不存在的 no-such-skill 必须被报
        c001 = [f for f in findings if f["rule"] == "C001" and "no-such-skill" in f["evidence"]]
        if not c001:
            failures.append("[漏报] dangling 的悬空技能交接未报 C001")
        # X001 串联/单向豁免 & X002 极性冲突
        if not any(f["rule"] == "X001" and "chain-a → chain-b" in f["skill"] for f in findings):
            failures.append("[漏报] chain-a → chain-b 单向豁免未报 X001")
        if not any(f["rule"] == "X001" and "depth ≥ 3" in f["skill"] for f in findings):
            failures.append("[漏报] 3 跳串联链未报 X001")
        if not any(f["rule"] == "X002" and "chain-a ↔ chain-b" in f["skill"] for f in findings):
            failures.append("[漏报] chain-a ↔ chain-b 小标题极性冲突未报 X002")

        verify_b002_and_metrics(failures)
        verify_x_positive_exemptions(failures)

        if failures:
            print("自测失败：")
            for x in failures:
                print("  -", x)
            print(f"\n夹具规则分布：{sorted({f['rule'] for f in findings})}")
            return 1

        print(f"自测通过 ✅  合规技能零误报；{len(expect)} 类坏样例全部命中预期规则。")
        print(f"夹具共 {len(findings)} 条 finding（坏样例同时触发附带规则属正常）。")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
