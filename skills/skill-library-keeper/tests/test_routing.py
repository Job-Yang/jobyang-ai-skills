#!/usr/bin/env python3
"""Routing-consistency guard across the technical-writing skill cluster.

These skills are siblings under the same skills root:
  feynman-explainer / talk-smith / cuihuo / engineering-docs / skill-library-keeper

The owner repeatedly hit mis-routing (a research doc that skipped feynman and was
naked-written by lark-doc; skill-library-keeper firing on external research). This
test freezes the agreed ownership so a future description edit cannot quietly
re-open the hole. It only reads SKILL.md front matter / body text; no network.

These are static contract guards, NOT a prompt router or a host recall benchmark.
Passing proves the checked wording/order remains present, not that a model loaded it.
"""
import json
import unittest
from pathlib import Path

SKILLS_ROOT = Path(__file__).resolve().parents[2]


def skill_md(name: str) -> str:
    return (SKILLS_ROOT / name / "SKILL.md").read_text(encoding="utf-8")


class TechnicalWritingRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.feynman = skill_md("feynman-explainer")
        cls.talk = skill_md("talk-smith")
        cls.cuihuo = skill_md("cuihuo")
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

    def test_talk_smith_boundary_is_audience_not_internal_external(self):
        self.assertIn("feynman-explainer", self.talk)
        self.assertIn("幽默", self.talk)
        # It must not claim to own plain internal "understand it" research.
        self.assertIn("研判", self.talk)
        # Platforms carry the finished draft; they do not drive its content.
        self.assertIn("平台只承载", self.talk)

    def test_cuihuo_is_opinion_piece_uses_feynman_and_finishes_via_haohao(self):
        self.assertIn("feynman-explainer", self.cuihuo)
        self.assertIn("观点", self.cuihuo)
        self.assertIn("haohao-shuohua", self.cuihuo)
        self.assertIn("平台", self.cuihuo)

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
        steps = [entry.index(token) for token in
                 ("1. **读方法**", "2. **取证讲透**", "3. **成稿检查**", "4. **写入发布**")]
        self.assertEqual(steps, sorted(steps))
        self.assertIn("references/style-examples.md", entry)
        self.assertIn("读取原文可在取证阶段调用平台技能", entry)
        self.assertIn("建文档骨架、复制或整理已有文件", entry)
        self.assertIn("不是宿主强制拦截", entry)
        self.assertIn("不保证自动召回", entry)

    def test_other_writers_keep_research_upstream_and_reuse_evidence(self):
        for skill in (self.talk, self.cuihuo, self.engdocs):
            with self.subTest(skill=skill.splitlines()[1]):
                self.assertIn("feynman-explainer", skill)
                self.assertIn("范例", skill)
                self.assertIn("检索与分析前" if skill != self.cuihuo else "再检索分析", skill)
                self.assertIn("复用", skill)
        self.assertNotIn("feynman 绝不反向调用本技能", self.talk)
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
            ("可被反驳的观点硬文", "cuihuo"),
            ("内部技术方案/RFC/ADR", "engineering-docs"),
            ("分享文 / talk / slides", "talk-smith"),
        )
        for token, expected in examples:
            with self.subTest(token=token):
                row = next(line for line in scope.splitlines() if token in line)
                self.assertIn(expected, row)


if __name__ == "__main__":
    unittest.main()
