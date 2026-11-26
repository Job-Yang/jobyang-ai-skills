#!/usr/bin/env python3
"""独立场景规约 + 静态合约守卫（keeper 第二条静态合约测试，C1 架构对齐版）。

本文件是**冻结的自然场景规约**，不是路由器：
- SCENARIOS 是人工逐条核定的自然指令清单，每条带：预期归属、主导角色、
  以及**正文契约证据位**（哪个文件哪一节/哪句支撑这个归属）；
- 测试不根据关键词把指令路由到技能（那是宿主召回的事，本仓测不到）；
- 测试做四件事：
  ① 规约完整性：条数/分桶/归属合法/证据位非空；
  ② 旧病缺席确认：真实文件里旧措辞必须不在（OldDiseaseRegressionTest）；
  ③ 破坏反例注入：把每种旧病**内存注入**文本，同一合约检查必须报失败
     （MutationFixtureTest）——证明守卫真的会抓旧病，不是只靠 absence 碰巧通过；
  ④ 新合约措辞在位。

真实宿主召回（用户 query → 命中哪个技能 → 实际读了哪份 reference）本仓无入口、无 trace，
一律标"未验证"，本文件不模拟、不冒充。
"""
import unittest
from pathlib import Path

SKILLS_ROOT = Path(__file__).resolve().parents[2]

# 每条结构：(指令, 归属, 主导, 备注, 正文契约证据位)
# 归属取值：feynman / writing-craft:sharing / writing-craft:opinion / writing-craft:tangshan
#         / engdocs / haohao / light（直接轻答）
#         / feynman+writing-craft:sharing / sansi+haohao / sansi+writing-craft:sharing
# 主导取值：成稿/清洗文体主导者；light 为无（直接答）。
SCENARIOS = [
    # —— feynman：复杂技术调研/机制理解；对外发布的研究报告仍归 feynman ——
    ("调研一下这个 repo 怎么做缓存", "feynman", "feynman", "内部技术调研",
     "feynman SKILL.md §0 表「解读源码/黑盒机制/硬核技术→本技能」"),
    ("讲讲 Mamba 的原理", "feynman", "feynman", "机制讲透",
     "feynman SKILL.md §0 表「讲透/讲明白/帮我搞懂→本技能」"),
    ("把这篇论文总结一下，我自己看", "feynman", "feynman", "输入型理解",
     "feynman SKILL.md §0 表「总结一下这篇复杂文档/论文/方案→本技能」"),
    ("这个 API 超时一直有，帮我查查可能原因", "feynman", "feynman", "机制排查",
     "feynman SKILL.md §0「费曼是调研与讲透的事实源——任何技术调研（对内、对外）都先过费曼」"),
    ("Codex 的上下文压缩到底是怎么工作的", "feynman", "feynman", "黑盒机制",
     "feynman SKILL.md §0 表「解读源码/黑盒机制→本技能」"),
    ("对外发布这个 GitHub 项目的调研报告", "feynman", "feynman", "强制负例：公开研究≠sharing",
     "feynman SKILL.md §0「费曼可以自己交付研究报告、机制解读、选型研判…哪怕对外发布、面向读者」"),
    ("我自己搞懂一下这个调度器的队列模型，不用写东西", "feynman", "feynman", "无成稿理解也归 feynman",
     "feynman SKILL.md §0 表「讲透/讲明白/帮我搞懂 XX→本技能」"),

    # —— writing-craft:sharing：讲给别人听的技术分享/经验叙事；严肃无幽默可；短句输出意图不排 ——
    ("把我做的这个重试机制写成一篇技术博客", "writing-craft:sharing", "writing-craft:sharing", "技术博客成稿",
     "writing-craft SKILL.md description「写给人看的中文文章、技术分享、项目复盘」"),
    ("下周组内分享讲讲我们怎么把 CI 时间砍半的", "writing-craft:sharing", "writing-craft:sharing", "组内分享",
     "writing-craft SKILL.md §1 表「实战复盘、经验分享、动手实录、工具安利、方法论传播、talk / slides → sharing」"),
    ("做一份复盘 slides，讲这次配置发布事故我们学到什么", "writing-craft:sharing", "writing-craft:sharing", "复盘 slides",
     "writing-craft SKILL.md §1 表「实战复盘…talk / slides（按需读 references/sharing-formats.md）→ sharing」"),
    ("把我这两年做客户端架构的经验整理成一篇分享", "writing-craft:sharing", "writing-craft:sharing", "个人工程实践/经验传播",
     "writing-craft references/sharing.md「写给人看的经验分享、项目复盘、动手实录」"),
    ("严肃地、不带段子地写一篇关于可观测性建设的技术分享", "writing-craft:sharing", "writing-craft:sharing", "强制负例：无幽默照样启用",
     "writing-craft references/sharing.md §1.4「不设字数配额凑梗；严肃事故复盘与官方发布场合保持平直克制，不做俏皮」"),
    ("就按这个提纲，写一篇我们团队数据看板建设的分享稿", "writing-craft:sharing", "writing-craft:sharing", "提纲输入=明确输出意图不排",
     "writing-craft SKILL.md §1 表「经验分享、方法论传播→sharing」，不被简短指令排除"),
    ("研究后讲讲我们怎么做、怎么踩坑的技术分享", "feynman+writing-craft:sharing", "writing-craft:sharing", "强制组合例：调研上游+分享成稿",
     "feynman SKILL.md §0 表「讲给别人听的分享文→writing-craft（sharing 分支）成稿」"),
    ("给新同事讲讲我们的发布流程，做成一个 talk", "writing-craft:sharing", "writing-craft:sharing", "经验/流程讲述",
     "writing-craft SKILL.md §1 表「talk / slides → sharing」"),
    ("把咱们团队这个季度的技术成果总结成一篇对内汇报分享", "writing-craft:sharing", "writing-craft:sharing", "团队分享复盘",
     "writing-craft SKILL.md §1 表「实战复盘、经验分享→sharing」"),

    # —— writing-craft:opinion：直白口语观点硬文 & 锻造手记 ——
    ("就“验收权必须独立于实现权”这个观点，给我写篇硬文", "writing-craft:opinion", "writing-craft:opinion", "观点硬文",
     "writing-craft references/opinion.md §1.1「围绕一个可被同行反驳的核心判断直球推演」"),
    ("把“AI 写得越快，代码越没人看”这个想法记一笔", "writing-craft:opinion", "writing-craft:opinion", "锻造手记",
     "writing-craft SKILL.md §1 表「≤ 120 字锻造手记 → opinion」"),
    ("我认为测试不该由写代码的人自己写，展开成一篇观点文", "writing-craft:opinion", "writing-craft:opinion", "观点展开",
     "writing-craft SKILL.md §1 表「无花架子、偏自然口语化的同行直白观点硬文 → opinion」"),

    # —— engineering-docs：内部评审方案 ——
    ("写个配置中心灰度发布的技术方案，要评审", "engdocs", "engdocs", "评审方案",
     "feynman SKILL.md §0 表「需要评审拍板的内部技术方案/RFC/ADR→engineering-docs」"),
    ("把这张架构图按我们现在的实际结构重画一遍", "engdocs", "engdocs", "架构图",
     "engineering-docs SKILL.md「写、改、评审研发技术文档…并用 diagram_kit 统一画工程图」"),
    ("评审一下这份 ADR，看落地方案有没有坑", "engdocs", "engdocs", "ADR 评审",
     "feynman SKILL.md §0 表「需要评审拍板的内部技术方案/RFC/ADR→engineering-docs」"),

    # —— writing-craft:tangshan：专栏长评、激励博弈与历史周期推演；不限题材 ——
    ("用汤山体推演五年后程序员这个职业会变成什么样", "writing-craft:tangshan", "writing-craft:tangshan", "专栏长评推演",
     "writing-craft SKILL.md §1 表「带公众号专栏风味，从激励博弈、制度结构与历史周期深剖的长评与推演 → tangshan」"),
    ("从激励机制和周期视角把 Token 经济写成一篇汤山专栏长评", "writing-craft:tangshan", "writing-craft:tangshan", "激励与周期分析",
     "writing-craft references/tangshan.md「从激励博弈、制度结构与历史周期切入」"),
    ("从博弈与组织结构分析未来十年远程协作会变成什么样", "writing-craft:tangshan", "writing-craft:tangshan", "非技术题材长评同样认领",
     "writing-craft references/tangshan.md「把行业、组织、社会或技术现象写成冷峻通透的深度长评与推演」"),

    # —— 负例：轻答 / 通用清洗 / 不被误吞 ——
    ("一句话解释什么是幂等", "light", "无", "单点定义轻答",
     "feynman SKILL.md §0 表「一句话告诉我 XX 是啥→直接回答」"),
    ("三句话告诉我什么是 Raft", "light", "无", "只要简短定义轻答",
     "feynman SKILL.md §0 表「简单说就行，别展开→直接回答」"),
    ("帮我改一下这段周报，它太像 AI 写的", "haohao", "haohao", "行政短文通用清洗",
     "haohao SKILL.md §使用面「周报、通知、邮件等无专门文体承接的短文，由本技能直接起草」"),
    ("这段怎么润色得像人话一点", "haohao", "haohao", "去 AI 味收尾",
     "haohao SKILL.md description「去 AI 味、去翻译腔」"),
    ("我们周报就写三行", "haohao", "haohao", "行政短文通用起草，不走全技能",
     "haohao SKILL.md §使用面「免走成稿五段全套」"),
    ("把这篇硬文按评审意见合并重复小节、精简结构", "sansi+haohao", "haohao", "强制负例：结构精简走 sansi 前置+haohao 清洗",
     "writing-craft SKILL.md §0「改已有中大型文档骨架前先走 sansi-erhouxing」"),
    ("把硬文里这一段删两句啰嗦词就行", "haohao", "haohao", "轻路径：不改结构的局部润色直走 haohao",
     "sansi-erhouxing SKILL.md §零「≤ 3 句措辞修订、不增删章节的局部润色或去 AI 味——直接交 haohao-shuohua」"),

    # —— 组合归属 / 多轮 ——
    ("先调研下某开源项目的限流实现，然后写成一篇对内分享", "feynman+writing-craft:sharing", "writing-craft:sharing", "调研上游+分享成稿",
     "writing-craft SKILL.md §2.1「前置取证先拆出…先调 feynman-explainer 取证…调研完回到本技能选定唯一主帅再起稿」"),
    ("我先给你一段笔记，你用汤山体写成深度专栏长评", "writing-craft:tangshan", "writing-craft:tangshan", "已有材料成专栏长评",
     "writing-craft SKILL.md §1 表「专栏长评 → tangshan」"),
    ("这个观点我扎好了，你帮我过一遍去 AI 味", "haohao", "haohao", "观点成稿后清洗",
     "haohao SKILL.md §使用面「被上层调用：其他专门文体技能收尾去 AI 味时单向调用本技能」"),
    ("改一下这篇分享稿的第三节，注意别伤了叙事弧", "sansi+writing-craft:sharing", "writing-craft:sharing", "实质修改：sansi 前置、sharing 主导，非仅润色",
     "sansi-erhouxing SKILL.md「严格不吞文体：改动仍由原文体…主导」"),
    ("把这份内部调研报告写成飞书文档发出来", "feynman", "feynman", "平台只是承载，成稿仍 feynman",
     "feynman SKILL.md §5 表「平台负责写入/独立成稿与平台写入分离」"),
]

OWNERS = {
    "feynman",
    "writing-craft:sharing",
    "writing-craft:opinion",
    "writing-craft:tangshan",
    "engdocs",
    "haohao",
    "light",
    "feynman+writing-craft:sharing",
    "sansi+haohao",
    "sansi+writing-craft:sharing",
}


def _read(rel):
    return (SKILLS_ROOT / rel).read_text(encoding="utf-8")


class ScenarioSpecIntegrityTest(unittest.TestCase):
    """规约自身完整性：条数、合法归属、分桶覆盖、证据位绑定。"""

    def test_spec_has_at_least_30_scenarios(self):
        self.assertGreaterEqual(len(SCENARIOS), 30, "自然指令规约不足 30 条")

    def test_all_entries_well_formed(self):
        bad = [e for e in SCENARIOS if len(e) != 5]
        self.assertEqual(bad, [], "每条规约必须是 (指令, 归属, 主导, 备注, 证据位) 五元组")

    def test_all_expected_owners_known(self):
        bad = [(i, o) for i, o, _, _, _ in SCENARIOS if o not in OWNERS]
        self.assertEqual(bad, [], f"归属取值不在白名单：{bad}")

    def test_evidence_binds_to_contract(self):
        bad = [(i, ev) for i, _, _, _, ev in SCENARIOS if "SKILL.md" not in ev and "references/" not in ev and "§" not in ev]
        self.assertEqual(bad, [], f"每条规约必须绑定正文契约位置（文件+章节/原句）：{bad}")

    def test_bucket_coverage(self):
        owners = [o for _, o, _, _, _ in SCENARIOS]
        for g in (
            "feynman",
            "writing-craft:sharing",
            "writing-craft:opinion",
            "engdocs",
            "writing-craft:tangshan",
            "haohao",
            "light",
        ):
            self.assertIn(g, owners, f"文体桶缺失：{g}")
        self.assertGreaterEqual(owners.count("light"), 2, "轻答负例不足")
        self.assertGreaterEqual(sum(1 for o in owners if "+" in o), 3, "组合归属例不足")

    def test_mandatory_counterexamples_frozen(self):
        instructions = [i for i, _, _, _, _ in SCENARIOS]
        self.assertIn("对外发布这个 GitHub 项目的调研报告", instructions,
                      "强制负例缺失：公开研究必须仍归 feynman")
        self.assertIn("研究后讲讲我们怎么做、怎么踩坑的技术分享", instructions,
                      "强制组合例缺失：调研上游+分享成稿")


class OldDiseaseRegressionTest(unittest.TestCase):
    """破坏反例确认：真实文件里旧病措辞必须不在（缺席确认）。"""

    def test_retired_directories_absent(self):
        for retired in ("talk-smith", "cuihuo", "tangshan-style"):
            self.assertFalse((SKILLS_ROOT / retired).exists(), f"已退场目录仍存在：{retired}")

    def test_writing_craft_no_humor_or_old_template_gate(self):
        wc = _read("writing-craft/SKILL.md")
        sh = _read("writing-craft/references/sharing.md")
        self.assertNotIn("带个人幽默感和口语风格", wc)
        self.assertNotIn("面向听众读者、要有叙事和人味", wc)
        self.assertNotIn("（输入型，不发布）", wc)
        self.assertNotIn("小标题写成论点句", sh)
        self.assertNotIn("小标题是**一句论点**", sh)
        self.assertNotIn("三句话能讲清 | —— | 不启用，直接答", wc)

    def test_feynman_no_humor_axis(self):
        f = _read("feynman-explainer/SKILL.md")
        self.assertNotIn("要不要人味地传播", f)
        self.assertNotIn("带个人幽默感、口语化的分享文", f)

    def test_opinion_not_fluff_cutting_or_tech_gate(self):
        wc = _read("writing-craft/SKILL.md")
        op = _read("writing-craft/references/opinion.md")
        self.assertNotIn("删车轱辘话", wc.split("---")[1])
        self.assertNotIn("把一个技术观点写成", op)
        self.assertNotIn("技术想法硬文", wc)

    def test_haohao_not_overreaching(self):
        self.assertIn("不越位", _read("haohao-shuohua/SKILL.md"))

    def test_engdocs_example_fixed(self):
        w = _read("engineering-docs/references/writing-contract.md")
        self.assertNotIn("## 灰度发布：先内部再全量", w)

    def test_sansi_not_swallowing_genres(self):
        self.assertIn("不吞文体", _read("sansi-erhouxing/SKILL.md"))


class MutationFixtureTest(unittest.TestCase):
    """破坏反例注入：把每种旧病内存注入文本，同一合约检查必须报失败。"""

    def test_fixture_1_humor_trigger_is_caught(self):
        broken = _read("writing-craft/SKILL.md").replace(
            "写给人看的中文文章、技术分享、项目复盘、口语化直白观点硬文、锻造手记、汤山专栏长评与演讲稿/slides",
            "带个人幽默感和口语风格的分享",
            1,
        )
        self.assertIn("带个人幽默感和口语风格", broken)
        with self.assertRaises(AssertionError):
            self.assertNotIn("带个人幽默感和口语风格", broken)

    def test_fixture_2_research_only_self_is_caught(self):
        broken = _read("writing-craft/SKILL.md").replace(
            "先立**唯一主帅**，再动笔写。",
            "费曼的逻辑链是我自己搞懂，**不发出去**",
            1,
        )
        self.assertIn("**不发出去**", broken)
        with self.assertRaises(AssertionError):
            self.assertNotIn("**不发出去**", broken)

    def test_fixture_3_subtitle_argument_is_caught(self):
        broken = _read("writing-craft/references/sharing.md").replace(
            "直白发问",
            "小标题是**一句论点**",
            1,
        )
        self.assertIn("小标题是**一句论点**", broken)
        with self.assertRaises(AssertionError):
            self.assertNotIn("小标题是**一句论点**", broken)

    def test_fixture_4_three_sentence_exclusion_is_caught(self):
        broken = _read("writing-craft/SKILL.md").replace(
            "行政周报、通知、邮件等无专门文体短文本也交",
            "三句话能讲清 | —— | 不启用，直接答",
            1,
        )
        self.assertIn("三句话能讲清 | —— | 不启用，直接答", broken)
        with self.assertRaises(AssertionError):
            self.assertNotIn("三句话能讲清 | —— | 不启用，直接答", broken)

    def test_fixture_5_haohao_overreach_is_caught(self):
        broken = "\n".join(
            l for l in _read("haohao-shuohua/SKILL.md").splitlines() if "不越位" not in l
        )
        self.assertNotIn("不越位", broken)
        with self.assertRaises(AssertionError):
            self.assertIn("不越位", broken)

    def test_fixture_6_research_no_publish_is_caught(self):
        broken = _read("feynman-explainer/SKILL.md").replace(
            "（对内对外都接，哪怕对外发布、面向读者）",
            "（输入型，不发布）",
            1,
        )
        self.assertIn("（输入型，不发布）", broken)
        with self.assertRaises(AssertionError):
            self.assertNotIn("（输入型，不发布）", broken)


class NewContractWordingTest(unittest.TestCase):
    """新合约措辞在位：C1 分支收口 + 正面覆盖 + 关键排除/从属。"""

    def test_writing_craft_contract_words(self):
        wc = _read("writing-craft/SKILL.md")
        for token in (
            "一稿一主帅",
            "按选定分支只读取对应的 1 份文件",
            "行政周报",
            "feynman-explainer",
            "haohao-shuohua",
            "sansi-erhouxing",
        ):
            self.assertIn(token, wc)

    def test_sharing_branch_contract_words(self):
        sh = _read("writing-craft/references/sharing.md")
        self.assertIn("不设字数配额凑梗", sh)
        self.assertIn("严肃事故复盘", sh)
        self.assertIn("不是套固定模板填表", sh)

    def test_opinion_branch_contract_words(self):
        op = _read("writing-craft/references/opinion.md")
        self.assertIn("可被同行反驳", op)
        self.assertIn("自然、直白、稍微口语化", op)
        self.assertIn("≤ 120", op)

    def test_tangshan_branch_contract_words(self):
        ts = _read("writing-craft/references/tangshan.md")
        self.assertIn("先认账再翻前提", ts)
        self.assertIn("激励博弈", ts)
        self.assertIn("历史周期", ts)

    def test_feynman_contract_words(self):
        f = _read("feynman-explainer/SKILL.md")
        self.assertIn("讲给别人听的分享文", f)
        self.assertIn("writing-craft", f)
        self.assertIn("发不发出去", f)
        self.assertIn("多轮重判", f)
        self.assertNotIn("可被反驳的技术观点硬文", f)


if __name__ == "__main__":
    unittest.main()
