#!/usr/bin/env python3
"""Routing-consistency guard across the technical-writing skill cluster.

These skills are siblings under the same skills root:
  feynman-explainer / writing-craft / engineering-docs / skill-library-keeper

The owner repeatedly hit mis-routing (a research doc that skipped feynman and was
naked-written by lark-doc; skill-library-keeper firing on external research; or
multiple expressive writing skills loading simultaneously and fighting each other).
This test freezes the consolidated C1 ownership so a future edit cannot quietly
re-open the hole. It only reads SKILL.md / references text; no network.

These are static contract guards, NOT a prompt router or a host recall benchmark.
Passing proves the checked wording/order remains present, not that a model loaded it.
"""
import json
import unittest
from pathlib import Path

SKILLS_ROOT = Path(__file__).resolve().parents[2]


def skill_md(name: str) -> str:
    return (SKILLS_ROOT / name / "SKILL.md").read_text(encoding="utf-8")


def ref_md(skill: str, rel: str) -> str:
    return (SKILLS_ROOT / skill / "references" / rel).read_text(encoding="utf-8")


class TechnicalWritingRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.feynman = skill_md("feynman-explainer")
        cls.writing = skill_md("writing-craft")
        cls.sharing_ref = ref_md("writing-craft", "sharing.md")
        cls.opinion_ref = ref_md("writing-craft", "opinion.md")
        cls.tangshan_ref = ref_md("writing-craft", "tangshan.md")
        cls.engdocs = skill_md("engineering-docs")
        cls.keeper = skill_md("skill-library-keeper")

    def test_feynman_owns_internal_and_external_research_incl_documents(self):
        # Must trigger on ANY technical research, internal or external, and be allowed
        # to deliver an internal research write-up itself.
        self.assertIn("调研", self.feynman)
        self.assertIn("内部调研报告", self.feynman)
        self.assertTrue(("对内" in self.feynman) and ("对外" in self.feynman))
        # Researching prompts/agents/a GitHub repo is research, not skill-library management.
        self.assertIn("skill-library-keeper", self.feynman)

    def test_writing_craft_unifies_three_branches_with_single_lead(self):
        for token in (
            "一稿一主帅",
            "按选定分支只读取对应的 1 份文件",
            "feynman-explainer",
            "haohao-shuohua",
            "engineering-docs",
            "平台技能",
            "references/sharing.md",
            "references/opinion.md",
            "references/tangshan.md",
        ):
            self.assertIn(token, self.writing)
        # Sharing branch must allow serious non-humor engineering stories.
        self.assertIn("不设字数配额凑梗", self.sharing_ref)
        self.assertIn("严肃事故复盘", self.sharing_ref)
        # Opinion branch covers conversational direct stances & <=120-char notes.
        self.assertIn("可被同行反驳", self.opinion_ref)
        self.assertIn("≤ 120", self.opinion_ref)
        self.assertIn("口语", self.opinion_ref)
        # Tangshan branch preserves incentive & cycle lens.
        self.assertIn("激励", self.tangshan_ref)
        self.assertIn("周期", self.tangshan_ref)

    def test_content_skills_own_content_lark_doc_only_publishes(self):
        # Feynman explicitly demotes lark-doc to a carrier for research write-ups.
        self.assertIn("lark-doc", self.feynman)
        self.assertIn("发布载体", self.feynman)
        # Engineering docs keep the platform out of content/structure, finish via
        # haohao, and lend (but do not surrender prose to) its diagram engine.
        self.assertIn("只承载成文", self.engdocs)
        self.assertIn("haohao-shuohua", self.engdocs)
        self.assertIn("只借图", self.engdocs)

    def test_keeper_does_not_fire_on_external_research_subject(self):
        # Even researching "how skills/prompts are built" externally is feynman,
        # unless the action object is the user's own installed skill set.
        self.assertIn("研究外部资料", self.keeper)
        self.assertIn("feynman-explainer", self.keeper)

    def test_short_research_request_has_frontloaded_explicit_example(self):
        # Parse this skill's quoted scalar independently of the body. A body-only
        # trigger cannot rescue metadata that does not state the research use case.
        desc = json.loads(self.feynman.splitlines()[2].split(": ", 1)[1])
        self.assertLessEqual(len(desc), 260)
        for term in ("调研", "GitHub", "源码", "论文", "先读取本技能"):
            self.assertIn(term, desc[:50])
        self.assertIn("调研一下，写个飞书文档", desc)
        self.assertIn("无需点名", desc)
        self.assertIn("讲透", desc)
        self.assertIn("haohao-shuohua", desc)
        self.assertIn("lark-doc", desc)

    def test_research_is_not_excluded_by_quick_answer_guard(self):
        self.assertNotIn("三句话以内能讲清、且用户没说", self.feynman)
        self.assertIn("只有无需调研的单点定义", self.feynman)
        self.assertIn("不要求点名", self.feynman)
        self.assertIn("单点快答不用", self.feynman)
        self.assertIn("纯创作 / 翻译 / 润色 / 文件搬运", self.feynman)

    def test_entry_orders_method_evidence_draft_and_publish(self):
        entry = self.feynman.split("## 入口", 1)[1].split("## 0.", 1)[0]
        steps = [
            entry.index(token)
            for token in ("1. **读方法**", "2. **取证讲透**", "3. **成稿检查**", "4. **写入发布**")
        ]
        self.assertEqual(steps, sorted(steps))
        self.assertIn("references/style-examples.md", entry)
        self.assertIn("读取原文可在取证阶段调用平台技能", entry)
        self.assertIn("建文档骨架、复制或整理已有文件", entry)
        self.assertIn("不是宿主强制拦截", entry)
        self.assertIn("不保证自动召回", entry)

    def test_other_writers_keep_research_upstream_and_reuse_evidence(self):
        self.assertIn("feynman-explainer", self.writing)
        self.assertIn("前置取证先拆出", self.writing)
        self.assertIn("拿到「事实与机理结论」原料", self.writing)

        self.assertIn("feynman-explainer", self.engdocs)
        self.assertIn("范例", self.engdocs)
        self.assertIn("检索与分析前", self.engdocs)
        self.assertIn("复用", self.engdocs)

        self.assertIn("避免循环调用", self.feynman)

    def test_prompt_cases_are_scope_examples_not_runtime_measurements(self):
        # Positive/negative examples specify boundaries. This test checks that the
        # prose explicitly covers them; it does not simulate tool calls or route a prompt.
        scope = self.feynman.split("## 0.", 1)[1].split("## 1.", 1)[0]
        examples = (
            ("GitHub 仓库", "本技能"),
            ("调研一下，写个飞书文档", "本技能 + 平台技能"),
            ("一句话告诉我", "直接回答"),
            ("文件搬运", "对应技能"),
            ("讲给别人听的分享文 / talk / slides", "writing-craft"),
            ("无花架子的直白口语观点硬文 / 锻造手记", "writing-craft"),
            ("内部技术方案/RFC/ADR", "engineering-docs"),
            ("汤山风味深度长评与推演", "writing-craft"),
        )
        for token, expected in examples:
            with self.subTest(token=token):
                row = next(line for line in scope.splitlines() if token in line)
                self.assertIn(expected, row)


if __name__ == "__main__":
    unittest.main()
