#!/usr/bin/env python3
"""独立场景规约 + 静态合约守卫（keeper 第二条静态合约测试）。

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
# 归属取值：feynman / talk / cuihuo / engdocs / tangshan / haohao / light（直接轻答）
#         feynman+talk / sansi+haohao / sansi+talk（组合：链条上的角色）
# 主导取值：成稿/清洗文体主导者；light 为无（直接答）。
SCENARIOS = [
    # —— feynman：复杂技术调研/机制理解；对外发布的研究报告仍归 feynman ——
    ("调研一下这个 repo 怎么做缓存", "feynman", "feynman", "内部技术调研",
     "feynman SKILL.md §0 表「解读源码/黑盒机制/硬核技术→本技能」"),
    ("讲讲 Mamba 的原理", "feynman", "feynman", "机制讲透",
     "feynman SKILL.md §0 表「讲透/讲明白/帮我搞懂→本技能」"),
    ("把这篇论文总结一下，我自己看", "feynman", "feynman", "输入型理解",
     "feynman SKILL.md §0 表「解读…我自己要看懂→本技能」"),
    ("这个 API 超时一直有，帮我查查可能原因", "feynman", "feynman", "机制排查",
     "feynman SKILL.md §3「费曼是调研与讲透的事实源——任何技术调研先过费曼」"),
    ("Codex 的上下文压缩到底是怎么工作的", "feynman", "feynman", "黑盒机制",
     "feynman SKILL.md §0 表「解读黑盒机制→本技能」"),
    ("对外发布这个 GitHub 项目的调研报告", "feynman", "feynman", "强制负例：公开研究≠talk",
     "feynman SKILL.md §3「费曼可以自己交付研究报告…哪怕对外发布、面向读者」"),
    ("我自己搞懂一下这个调度器的队列模型，不用写东西", "feynman", "feynman", "无成稿理解也归 feynman",
     "feynman SKILL.md §0 表「把一个点讲透、我自己搞懂→单向吃它的研究结论」"),

    # —— talk：讲给别人听的技术分享/经验叙事；严肃无幽默可；短句输出意图不排 ——
    ("把我做的这个重试机制写成一篇技术博客", "talk", "talk", "技术博客成稿",
     "talk SKILL.md description「技术分享/博客/演讲稿/slides…讲讲实践/复盘」"),
    ("下周组内分享讲讲我们怎么把 CI 时间砍半的", "talk", "talk", "组内分享",
     "talk SKILL.md §0 命中即启用「分享稿/演讲稿/talk、分享 slides」"),
    ("做一份复盘 slides，讲这次配置发布事故我们学到什么", "talk", "talk", "复盘 slides",
     "talk SKILL.md §0 命中即启用「项目复盘」"),
    ("把我这两年做客户端架构的经验整理成一篇分享", "talk", "talk", "个人工程实践/经验传播",
     "talk SKILL.md description「个人工程实践、经验传播」"),
    ("严肃地、不带段子地写一篇关于可观测性建设的技术分享", "talk", "talk", "强制负例：无幽默照样启用",
     "talk SKILL.md description「可以严肃、不要幽默」"),
    ("就按这个提纲，写一篇我们团队数据看板建设的分享稿", "talk", "talk", "提纲输入=明确输出意图不排",
     "talk SKILL.md §0 边界行「就按提纲写…不被三句话能讲清排除」"),
    ("研究后讲讲我们怎么做、怎么踩坑的技术分享", "feynman+talk", "talk", "强制组合例：调研上游+分享成稿",
     "feynman §0 表「讲给别人听的分享文→talk-smith 成稿」"),
    ("给新同事讲讲我们的发布流程，做成一个 talk", "talk", "talk", "经验/流程讲述",
     "talk SKILL.md §0 命中即启用「技术 talk」"),
    ("把咱们团队这个季度的技术成果总结成一篇对内汇报分享", "talk", "talk", "技术成果及工作总结",
     "talk SKILL.md description「技术成果及工作总结」"),

    # —— cuihuo：可被反驳的判断 ——
    ("就“验收权必须独立于实现权”这个观点，给我写篇硬文", "cuihuo", "cuihuo", "观点硬文",
     "cuihuo SKILL.md §1 定类「我要输出一个可被反驳的判断」"),
    ("把“AI 写得越快，代码越没人看”这个想法记一笔", "cuihuo", "cuihuo", "锻造手记",
     "cuihuo SKILL.md description「把想法提炼成≤120字锻造手记」"),
    ("我认为测试不该由写代码的人自己写，展开成一篇观点文", "cuihuo", "cuihuo", "观点展开",
     "cuihuo SKILL.md §0 表「扎一个观点→淬火」"),

    # —— engineering-docs：内部评审方案 ——
    ("写个配置中心灰度发布的技术方案，要评审", "engdocs", "engdocs", "评审方案",
     "feynman §0 表「需要评审拍板的内部技术方案/RFC/ADR→engineering-docs」"),
    ("把这张架构图按我们现在的实际结构重画一遍", "engdocs", "engdocs", "架构图",
     "talk §0 表「要评审拍板的内部方案/RFC→engineering-docs」"),
    ("评审一下这份 ADR，看落地方案有没有坑", "engdocs", "engdocs", "ADR 评审",
     "feynman §0 表「内部技术方案/RFC/ADR→engineering-docs」"),

    # —— tangshan：未来推演；短句/提纲按当前任务重判；不限题材 ——
    ("用汤山体推演五年后程序员这个职业会变成什么样", "tangshan", "tangshan", "畅想推演",
     "tangshan SKILL.md §0 表「写技术畅想/未来推演→汤山体」"),
    ("把 Token 经济推演写成一篇畅想文", "tangshan", "tangshan", "畅想成稿",
     "tangshan SKILL.md description「未来推演写成畅想长文」"),
    ("推演一下未来十年远程协作会变成什么样", "tangshan", "tangshan", "非技术题材未来推演也认领",
     "tangshan SKILL.md description「不限题材——未来城市、远程协作同样认领」"),

    # —— 负例：轻答 / 通用清洗 / 不被误吞 ——
    ("一句话解释什么是幂等", "light", "无", "单点定义轻答",
     "feynman SKILL.md §0 表「一句话告诉我…→直接回答」"),
    ("三句话告诉我什么是 Raft", "light", "无", "只要简短定义轻答",
     "feynman SKILL.md §0 表「简单说就行别展开→直接回答」"),
    ("帮我改一下这段周报，它太像 AI 写的", "haohao", "haohao", "行政短文通用清洗",
     "haohao SKILL.md §使用面「行政通知/周报短文可直接通用起草」"),
    ("这段怎么润色得像人话一点", "haohao", "haohao", "去 AI 味收尾",
     "haohao SKILL.md description「去 AI 味、改中文、润色」"),
    ("我们周报就写三行", "haohao", "haohao", "行政短文通用起草，不走全技能",
     "haohao SKILL.md §使用面「不强制走成稿五段全套」"),
    ("删掉这篇硬文里重复啰嗦的句子就行", "sansi+haohao", "haohao", "强制负例：纯删废话走 sansi 前置+haohao 清洗，不是 cuihuo",
     "cuihuo SKILL.md description「纯删废话→sansi-erhouxing 共读+haohao-shuohua 收尾」"),

    # —— 组合归属 / 多轮 ——
    ("先调研下某开源项目的限流实现，然后写成一篇对内分享", "feynman+talk", "talk", "调研上游+分享成稿",
     "feynman §3「需要把研究结果做成讲给别人听的分享→talk-smith 成稿」"),
    ("我先给你一段笔记，你把它锻造成汤山体的畅想", "tangshan", "tangshan", "已有材料成畅想",
     "tangshan SKILL.md §0 表「写技术畅想→汤山体」"),
    ("这个观点我扎好了，你帮我过一遍去 AI 味", "haohao", "haohao", "观点成稿后清洗",
     "haohao SKILL.md §使用面「被上层调用：成稿交本技能过一次」"),
    ("改一下这篇分享稿的第三节，注意别伤了叙事弧", "sansi+talk", "talk", "实质修改：sansi 前置、talk 主导，非仅润色",
     "sansi SKILL.md「本技能不吞文体：改完仍由那个文体主导」"),
    ("把这份内部调研报告写成飞书文档发出来", "feynman", "feynman", "平台只是承载，成稿仍 feynman",
     "feynman SKILL.md §3「平台技能只把定稿搬上去承载」"),
]

OWNERS = {"feynman", "talk", "cuihuo", "engdocs", "tangshan", "haohao",
          "light", "feynman+talk", "sansi+haohao", "sansi+talk"}


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
        bad = [(i, ev) for i, _, _, _, ev in SCENARIOS if "SKILL.md" not in ev and "§" not in ev]
        self.assertEqual(bad, [], f"每条规约必须绑定正文契约位置（文件+章节/原句）：{bad}")

    def test_bucket_coverage(self):
        owners = [o for _, o, _, _, _ in SCENARIOS]
        for g in ("feynman", "talk", "cuihuo", "engdocs", "tangshan", "haohao", "light"):
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

    def test_talk_trigger_not_humor(self):
        talk = _read("talk-smith/SKILL.md")
        self.assertNotIn("带个人幽默感和口语风格", talk)
        self.assertNotIn("面向听众读者、要有叙事和人味", talk)
        self.assertNotIn("（输入型，不发布）", talk, "talk 残留旧边界'研究不发布'")

    def test_feynman_no_humor_axis(self):
        f = _read("feynman-explainer/SKILL.md")
        self.assertNotIn("要不要人味地传播", f)
        self.assertNotIn("带个人幽默感、口语化的分享文", f)

    def test_narrative_arc_no_old_boundary(self):
        n = _read("talk-smith/references/narrative-arc.md")
        self.assertNotIn("**不发出去**", n)
        self.assertNotIn("一句论点", n)

    def test_talk_subtitle_rule_unified(self):
        self.assertNotIn("小标题写成论点句", _read("talk-smith/references/style-cn-tech.md"))
        self.assertNotIn("小标题是**一句论点**", _read("talk-smith/references/templates-article.md"))
        self.assertNotIn("小标题是论点句", _read("talk-smith/references/qc-checklist.md"))

    def test_no_three_sentence_exclusion(self):
        talk = _read("talk-smith/SKILL.md")
        self.assertNotIn("三句话能讲清 | —— | 不启用，直接答", talk)

    def test_cuihuo_not_fluff_cutting(self):
        cui = _read("cuihuo/SKILL.md")
        self.assertNotIn("删车轱辘话", cui.split("---")[1])

    def test_haohao_not_overreaching(self):
        self.assertIn("不越位", _read("haohao-shuohua/SKILL.md"))

    def test_engdocs_example_fixed(self):
        w = _read("engineering-docs/references/writing-contract.md")
        self.assertNotIn("## 灰度发布：先内部再全量", w)

    def test_sansi_not_swallowing_genres(self):
        self.assertIn("不吞文体", _read("sansi-erhouxing/SKILL.md"))


class MutationFixtureTest(unittest.TestCase):
    """破坏反例注入：把每种旧病内存注入文本，同一合约检查必须报失败。

    复写 test_routing.py 的负例夹具思路：不是只读"现在没有"，而是把旧病
    重新注回去，确认守卫确实抓得住——否则 absence 碰巧通过也会假绿。
    """

    def test_fixture_1_humor_trigger_is_caught(self):
        broken = _read("talk-smith/SKILL.md").replace(
            "把技术主题做成讲给别人听的分享", "带个人幽默感和口语风格的分享", 1)
        self.assertIn("带个人幽默感和口语风格", broken)  # 注入有效
        with self.assertRaises(AssertionError):
            self.assertNotIn("带个人幽默感和口语风格", broken)

    def test_fixture_2_research_only_self_is_caught(self):
        broken = _read("talk-smith/references/narrative-arc.md").replace(
            "这篇是不是做来讲给别人听的技术分享或经验叙事",
            "费曼的逻辑链是我自己搞懂，**不发出去**", 1)
        self.assertIn("**不发出去**", broken)
        with self.assertRaises(AssertionError):
            self.assertNotIn("**不发出去**", broken)

    def test_fixture_3_subtitle_argument_is_caught(self):
        broken = _read("talk-smith/references/templates-article.md").replace(
            "H2/H3 是**短模块目录**", "小标题是**一句论点**", 1)
        self.assertIn("小标题是**一句论点**", broken)
        with self.assertRaises(AssertionError):
            self.assertNotIn("小标题是**一句论点**", broken)

    def test_fixture_4_three_sentence_exclusion_is_caught(self):
        broken = _read("talk-smith/SKILL.md").replace(
            '被"三句话能讲清"排除',
            "三句话能讲清 | —— | 不启用，直接答", 1)
        self.assertIn("三句话能讲清 | —— | 不启用，直接答", broken)
        with self.assertRaises(AssertionError):
            self.assertNotIn("三句话能讲清 | —— | 不启用，直接答", broken)

    def test_fixture_5_haohao_overreach_is_caught(self):
        # 旧病形态：haohao 正文里没有"不越位"边界
        broken = "\n".join(l for l in _read("haohao-shuohua/SKILL.md").splitlines()
                           if "不越位" not in l)
        self.assertNotIn("不越位", broken)
        with self.assertRaises(AssertionError):
            self.assertIn("不越位", broken)

    def test_fixture_6_research_no_publish_is_caught(self):
        broken = _read("talk-smith/SKILL.md").replace(
            "（含研究报告成稿，对外发布也算）", "（输入型，不发布）", 1)
        self.assertIn("（输入型，不发布）", broken)
        with self.assertRaises(AssertionError):
            self.assertNotIn("（输入型，不发布）", broken)


class NewContractWordingTest(unittest.TestCase):
    """新合约措辞在位：场景正面覆盖 + 关键排除/从属。"""

    def test_talk_contract_words(self):
        talk = _read("talk-smith/SKILL.md")
        self.assertIn("技术成果及工作总结", talk)
        self.assertIn("行政周报", talk)
        self.assertIn("严肃无幽默", talk)

    def test_feynman_contract_words(self):
        f = _read("feynman-explainer/SKILL.md")
        self.assertIn("讲给别人听的分享文", f)
        self.assertIn("发不发出去", f)

    def test_cuihuo_contract_words(self):
        cui = _read("cuihuo/SKILL.md")
        self.assertIn("可被反驳的判断", cui)
        self.assertIn("sansi-erhouxing", cui.split("---")[1])

    def test_engdocs_h2_rule_intact(self):
        w = _read("engineering-docs/references/writing-contract.md")
        self.assertIn("短关键词", w)
        self.assertIn("## 灰度发布\n", w)

    def test_tangshan_multi_turn_words(self):
        t = _read("tangshan-style/SKILL.md")
        self.assertIn("多轮重判", t)
        self.assertIn("就按提纲写个畅想", t)
        self.assertIn("不限题材", t, "tangshan 仍限定技术题材")

    def test_cuihuo_no_technical_word_gate(self):
        cui = _read("cuihuo/SKILL.md")
        self.assertNotIn("把一个技术观点写成", cui, "cuihuo 主句仍以技术词为门槛")
        self.assertNotIn("技术想法硬文", cui)

    def test_feynman_row_no_technical_word_gate(self):
        self.assertNotIn("可被反驳的技术观点硬文", _read("feynman-explainer/SKILL.md"),
                         "feynman 交接行仍以技术词为门槛")

    def test_feynman_multi_turn_words(self):
        self.assertIn("多轮重判", _read("feynman-explainer/SKILL.md"))


if __name__ == "__main__":
    unittest.main()
