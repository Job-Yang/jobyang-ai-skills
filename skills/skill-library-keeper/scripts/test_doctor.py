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
完整字段见 [整理手册](references/good-guide.md)；超长会议见 [长手册](references/long-guide.md)。
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
            "no-desc": "F008",
            "claude-thing": "F003",
            "broken-ref": "R001",
            "hard-bind": "P001",
            "too-long": "S001",
            "open-fence": "R002",
            "orphan-file": "S004",
            "leaked-secret": "S006",
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
