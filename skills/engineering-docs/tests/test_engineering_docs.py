import importlib.util
import json
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "engineering_docs.py"
)
SPEC = importlib.util.spec_from_file_location("engineering_docs", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


COMPLETE_DOCUMENT = """# 示例方案

> **方案主张：** 会话服务通过适配层使用托管存储，消除人工扩容。
>
> **当前范围：** 保持客户端协议不变，只改服务端存储链路。

当前存储无法自动应对流量峰值，请技术负责人批准方案，研发和测试据此实施。

## 总体设计

会话服务先经过存储适配层，再读写托管存储。两个节点分别隔离协议变化和承担自动扩容。

| 节点 | 责任 | 下钻 |
| --- | --- | --- |
| 存储适配层 | 保持客户端协议并切换存储 | 见“存储适配层” |
| 托管存储 | 自动扩容并持久化会话 | 见“托管存储” |

## 人工扩容约束

当前链路依赖人工扩容，无法满足峰值期间的可用性目标。

## 存储适配层

适配层保持现有客户端协议，把读写切换到托管存储；超时返回可重试错误。

## 托管存储

托管存储承担自动扩容和会话持久化，代价是服务费用增加。

## 发布与回退

适配层和托管存储通过压测及双写对账后按租户灰度，异常时切回旧存储。
"""


def make_complete_record():
    template_path = (
        Path(__file__).resolve().parents[1]
        / "templates"
        / "decision-record.json"
    )
    record = json.loads(template_path.read_text(encoding="utf-8"))
    record["document"].update(
        {
            "title": "示例方案",
            "type": "technical-design",
            "status": "implementable",
            "purpose": "决定如何改造会话存储",
            "audience": ["研发", "测试"],
            "expected_action": "接受方案并据此实施",
            "scope": {
                "in": ["会话存储"],
                "out": [],
            },
            "author": "测试作者",
            "decision_owner": "技术负责人",
            "updated_at": "2026-09-22",
            "applicable_version": "main@abc123",
        }
    )
    record["problem"].update(
        {
            "current_state": "当前存储需要人工扩容",
            "evidence": [
                {
                    "id": "E1",
                    "claim": "容量峰值需要人工处理",
                    "source": "metrics://session-capacity",
                    "source_type": "runtime_metric",
                    "scope": "生产环境 2026-09",
                    "observed_at": "2026-09-20",
                    "verified_by": "值班负责人",
                    "conflicts": [],
                }
            ],
            "gap": "无法自动应对流量峰值",
            "impact": "存在容量告警和人工值守成本",
            "do_nothing": "高峰期继续依赖人工扩容",
        }
    )
    record["criteria"].update(
        {
            "goals": [
                {
                    "statement": "消除人工扩容",
                    "acceptance": "压测期间无需人工操作",
                }
            ],
            "non_goals": [],
            "constraints": ["保持现有接口兼容"],
        }
    )
    record["options"].update(
        {
            "candidates": [
                {
                    "name": "方案 A",
                    "summary": "使用托管存储",
                    "feasible": True,
                    "decisive_tradeoff": "增加成本，减少运维",
                },
                {
                    "name": "方案 B",
                    "summary": "扩容现有集群",
                    "feasible": True,
                    "decisive_tradeoff": "成本较低，继续人工运维",
                },
            ],
            "comparison_criteria": ["运维成本", "可用性"],
            "unique_path_reason": "",
        }
    )
    record["decision"].update(
        {
            "recommendation": "采用方案 A",
            "rationale": ["满足自动扩容目标"],
            "accepted_costs": ["托管服务费用增加"],
            "assumptions": [],
            "confidence": "已完成原型验证",
            "accepted_by": "技术负责人",
            "accepted_at": "2026-09-22T08:00:00+00:00",
        }
    )
    record["reading"].update(
        {
            "orientation": {
                "thesis": "会话服务通过适配层使用托管存储",
                "why_now": "当前存储无法自动应对流量峰值",
                "scope": "保持客户端协议不变，只改服务端存储链路",
                "reader_actions": ["技术负责人批准", "研发和测试实施"],
            },
            "overview": {
                "required": True,
                "exemption_reason": "",
                "heading": "总体设计",
                "summary": "会话服务经适配层读写托管存储",
                "format": "table",
                "source_ref": "",
                "nodes": [
                    {
                        "id": "adapter",
                        "name": "存储适配层",
                        "responsibility": "保持协议并切换存储",
                        "relation": "调用托管存储",
                        "chapter": "adapter",
                    },
                    {
                        "id": "managed",
                        "name": "托管存储",
                        "responsibility": "自动扩容并持久化会话",
                        "relation": "接收适配层读写",
                        "chapter": "managed",
                    },
                ],
            },
            "chapters": [
                {
                    "id": "problem",
                    "parent": "overview",
                    "heading": "人工扩容约束",
                    "summary": "现有链路无法满足峰值目标",
                    "role": "orientation",
                    "level": 2,
                    "supports": [],
                },
                {
                    "id": "adapter",
                    "parent": "overview",
                    "heading": "存储适配层",
                    "summary": "保持客户端协议并切换存储",
                    "role": "core",
                    "level": 2,
                    "supports": [],
                },
                {
                    "id": "managed",
                    "parent": "overview",
                    "heading": "托管存储",
                    "summary": "自动扩容并持久化会话",
                    "role": "core",
                    "level": 2,
                    "supports": [],
                },
                {
                    "id": "rollout",
                    "parent": "overview",
                    "heading": "发布与回退",
                    "summary": "两个节点共同通过压测、对账和灰度交付",
                    "role": "crosscutting",
                    "level": 2,
                    "supports": ["adapter", "managed"],
                },
            ],
        }
    )
    record["design"].update(
        {
            "system_boundary": ["会话服务", "托管存储"],
            "responsibilities": ["会话服务负责读写适配"],
            "main_flow": ["请求进入会话服务后读写托管存储"],
            "exceptions": ["存储超时时返回可重试错误"],
            "contracts": ["客户端协议保持不变"],
            "change_points": ["session/storage 适配层"],
        }
    )
    record["delivery"].update(
        {
            "risk_level": "standard",
            "risk_triggers": [],
            "impact_surface": ["会话读写"],
            "validation": ["压测和双写对账通过"],
            "observability": ["读写错误率和延迟"],
            "rollout": ["按租户灰度"],
            "rollback": ["切回旧存储"],
            "ownership": ["会话服务团队"],
        }
    )
    for gate_id in MODULE.GATE_IDS:
        record["gates"][gate_id] = {
            "status": "pass",
            "reason": "已完成人工检查",
            "evidence": [],
        }
    record["reader_test"].update(
        {
            "overview": {
                "answers_locked": True,
                "answers": {
                    "problem": "人工扩容无法应对峰值",
                    "top_nodes": "存储适配层和托管存储",
                    "relations": "适配层调用托管存储",
                    "expanded_nodes": "两个节点分别在正文展开",
                    "reader_action": "批准方案并实施",
                },
                "completed": True,
                "result": "pass",
                "findings": [],
            },
            "outline": {
                "answers_locked": True,
                "answers": {
                    "story": "人工扩容无法满足目标，因此改造存储适配层并通过压测、对账和灰度交付",
                    "node_mapping": "存储适配层和托管存储一一对应主章节",
                    "crosscutting": "发布与回退连接两个核心节点",
                    "detail_routes": "当前示例不需要附录",
                },
                "completed": True,
                "result": "pass",
                "findings": [],
            },
            "drilldown": {
                "answers_locked": True,
                "sample_node": "adapter",
                "answers": {
                    "responsibility": "保持协议并切换存储",
                    "boundary": "不改客户端协议",
                    "children": "当前示例不继续拆分",
                    "detail_routes": "当前示例不需要附录",
                },
                "completed": True,
                "result": "pass",
                "findings": [],
            },
            "answers_locked": True,
            "approved_by": "技术负责人",
            "answers": {
                "Q1": "当前存储依赖人工扩容",
                "Q2": "采用托管存储以消除人工扩容",
                "Q3": "不改客户端协议，接受额外费用",
                "Q4": "修改存储适配层，风险是迁移一致性",
                "Q5": "压测和对账验证，失败时切回旧存储",
            },
            "completed": True,
            "result": "pass",
            "findings": [],
        }
    )
    return record


class EngineeringDocsTests(unittest.TestCase):
    def test_trigger_description_owns_technical_documents(self):
        skill_text = (
            Path(__file__).resolve().parents[1] / "SKILL.md"
        ).read_text(encoding="utf-8")

        self.assertIn("写、改、评审研发技术文档", skill_text)
        self.assertIn("主次分明", skill_text)
        self.assertIn("技术方案、系统设计、RFC、ADR", skill_text)
        self.assertIn("平台通用", skill_text)
        self.assertIn("发布到某个平台只是可选的最后一步", skill_text)
        self.assertIn("纯润色", skill_text)
        self.assertIn("非技术文档不用", skill_text)

    def test_engineering_diagrams_are_owned_even_without_explicit_invocation(self):
        skill_text = (
            Path(__file__).resolve().parents[1] / "SKILL.md"
        ).read_text(encoding="utf-8")
        # Ownership must trigger on the task ("drawing in a doc"), not on being named.
        self.assertIn("不需要用户点名", skill_text)
        self.assertIn("更新已有文档", skill_text)
        # Engineering-relationship diagrams are diagram_kit territory ...
        self.assertIn("diagram_kit", skill_text)
        # ... and must not silently route to generic visualization, hand-written
        # mermaid, or a whiteboard DSL.
        self.assertIn("手写 mermaid", skill_text)
        self.assertIn("从零摆节点", skill_text)
        self.assertIn("通用可视化", skill_text)
        self.assertIn("发布适配器", skill_text)
        portable = (Path(__file__).resolve().parents[1] / "references"
                    / "portable-delivery.md").read_text(encoding="utf-8")
        self.assertIn("图的归属", portable)

    def test_coauthoring_is_integrated_without_mandatory_ceremony(self):
        skill_dir = Path(__file__).resolve().parents[1]
        skill_text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        workflow = (
            skill_dir / "references" / "collaboration-workflow.md"
        ).read_text(encoding="utf-8")

        self.assertIn("默认直接推进", skill_text)
        self.assertIn("collaboration-workflow.md", skill_text)
        self.assertIn("上下文已经充分时直接起草", skill_text)
        self.assertIn("一次只问会改变当前决定的最少问题", workflow)
        self.assertIn("不要默认生成 5–20 个脑暴选项", workflow)
        self.assertLessEqual(len(skill_text.splitlines()), 240)

    def test_full_lifecycle_is_owned_by_one_skill(self):
        skill_text = (
            Path(__file__).resolve().parents[1] / "SKILL.md"
        ).read_text(encoding="utf-8")

        for capability in (
            "新建或更新技术方案",
            "收集上下文",
            "建立工程判断",
            "更新已有文档",
            "设计必要的图",
            "做独立读者测试",
        ):
            self.assertIn(capability, skill_text)
        self.assertNotIn("doc-coauthoring", skill_text)

    def test_public_instructions_do_not_leak_evaluation_domain(self):
        skill_dir = Path(__file__).resolve().parents[1]
        public_files = [
            skill_dir / "SKILL.md",
            *sorted((skill_dir / "references").glob("*.md")),
        ]
        text = "\n".join(
            path.read_text(encoding="utf-8") for path in public_files
        )

        for term in ("MySQL", "Kafka", "OrderCreated", "outbox"):
            self.assertNotIn(term, text)

    def test_init_creates_a_valid_draft(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            args = Namespace(
                title="测试方案",
                author="测试作者",
                decision_owner="",
                type="technical-design",
                output=temp_dir,
                force=False,
            )
            self.assertEqual(MODULE.init_workspace(args), 0)
            record_path = Path(temp_dir) / "decision-record.json"
            document_path = Path(temp_dir) / "document.md"
            record = MODULE.load_json(record_path)
            document_text = document_path.read_text(encoding="utf-8")
            report = MODULE.validate_record(
                record,
                document_text,
            )

            self.assertTrue(report.ok, report.errors)
            self.assertEqual(record["document"]["status"], "draft")
            self.assertEqual(record["schema_version"], 3)
            self.assertEqual(len(record["gates"]), 13)
            self.assertIn("> **方案主张：**", document_text)
            self.assertIn("> **当前范围：**", document_text)
            self.assertIn("总体设计", document_text)
            self.assertNotIn("非目标", document_text)

    def test_complete_record_passes_implementable_validation(self):
        record = make_complete_record()
        report = MODULE.validate_record(
            record,
            COMPLETE_DOCUMENT,
            "implementable",
        )

        self.assertTrue(report.ok, report.errors)

    def test_orientation_is_required_for_new_formal_documents(self):
        record = make_complete_record()
        document = COMPLETE_DOCUMENT.replace(
            "> **方案主张：** 会话服务通过适配层使用托管存储，消除人工扩容。\n>\n"
            "> **当前范围：** 保持客户端协议不变，只改服务端存储链路。\n\n",
            "",
        )
        report = MODULE.validate_record(record, document, "implementable")

        self.assertFalse(report.ok)
        self.assertTrue(
            any("开场缺少" in error for error in report.errors),
            report.errors,
        )

    def test_generic_heading_is_rejected_from_new_formal_documents(self):
        record = make_complete_record()
        record["reading"]["chapters"][0]["heading"] = "背景"
        document = COMPLETE_DOCUMENT.replace(
            "## 人工扩容约束",
            "## 背景",
        )
        report = MODULE.validate_record(record, document, "implementable")

        self.assertFalse(report.ok)
        self.assertTrue(
            any("标题信息不足" in error for error in report.errors),
            report.errors,
        )

    def test_context_dependent_heading_is_rejected(self):
        record = make_complete_record()
        record["reading"]["chapters"][0]["heading"] = "三条线在版本中汇合"
        document = COMPLETE_DOCUMENT.replace(
            "## 人工扩容约束",
            "## 三条线在版本中汇合",
        )
        report = MODULE.validate_record(record, document, "implementable")

        self.assertFalse(report.ok)
        self.assertTrue(
            any("标题信息不足" in error for error in report.errors),
            report.errors,
        )

    def test_empty_group_heading_is_rejected(self):
        record = make_complete_record()
        document = COMPLETE_DOCUMENT.replace(
            "## 存储适配层\n\n适配层保持现有客户端协议，把读写切换到托管存储；超时返回可重试错误。",
            "## 存储适配层\n\n### 输入\n\n适配层接收现有协议。",
        )
        report = MODULE.validate_record(record, document, "implementable")

        self.assertFalse(report.ok)
        self.assertTrue(
            any("黑盒摘要" in error for error in report.errors),
            report.errors,
        )

    def test_overview_nodes_are_required_for_formal_documents(self):
        record = make_complete_record()
        record["reading"]["overview"]["nodes"] = []
        report = MODULE.validate_record(
            record,
            COMPLETE_DOCUMENT,
            "implementable",
        )

        self.assertFalse(report.ok)
        self.assertTrue(
            any("总体模型必须包含节点" in error for error in report.errors),
            report.errors,
        )

    def test_overview_reader_failure_blocks_implementable(self):
        record = make_complete_record()
        record["reader_test"]["overview"]["result"] = "fail"
        report = MODULE.validate_record(
            record,
            COMPLETE_DOCUMENT,
            "implementable",
        )

        self.assertFalse(report.ok)
        self.assertTrue(
            any("overview 结果必须为 pass" in error for error in report.errors),
            report.errors,
        )

    def test_overview_outline_and_drilldown_tests_block_review(self):
        record = make_complete_record()
        record["document"]["status"] = "in_review"
        record["reader_test"]["overview"]["completed"] = False
        record["reader_test"]["outline"]["result"] = "fail"
        record["reader_test"]["drilldown"]["result"] = "fail"
        report = MODULE.validate_record(
            record,
            COMPLETE_DOCUMENT,
            "in_review",
        )

        self.assertFalse(report.ok)
        self.assertTrue(
            any("overview 尚未完成" in error for error in report.errors),
            report.errors,
        )
        self.assertTrue(
            any("outline 结果必须为 pass" in error for error in report.errors),
            report.errors,
        )
        self.assertTrue(
            any("drilldown 结果必须为 pass" in error for error in report.errors),
            report.errors,
        )

    def test_readability_audit_exposes_scan_path_and_density(self):
        audit = MODULE.readability_audit(
            COMPLETE_DOCUMENT,
            make_complete_record(),
        )

        self.assertTrue(audit["orientation"]["has_thesis"])
        self.assertTrue(audit["orientation"]["has_scope"])
        self.assertEqual([], audit["generic_headings"])
        self.assertEqual([], audit["hierarchy_skips"])
        self.assertEqual(
            [
                "示例方案",
                "总体设计",
                "人工扩容约束",
                "存储适配层",
                "托管存储",
                "发布与回退",
            ],
            [item["text"] for item in audit["headings"]],
        )
        self.assertTrue(audit["overview"]["found"])
        self.assertEqual(2, audit["overview"]["nodes"])

    def test_contextual_h3_can_use_a_short_local_label(self):
        record = make_complete_record()
        record["reading"]["chapters"].append(
            {
                "id": "adapter-input",
                "parent": "adapter",
                "heading": "输入",
                "summary": "接收现有客户端协议",
                "role": "detail",
                "level": 3,
                "supports": [],
            }
        )
        document = COMPLETE_DOCUMENT.replace(
            "适配层保持现有客户端协议，把读写切换到托管存储；超时返回可重试错误。",
            "适配层保持现有客户端协议，把读写切换到托管存储；超时返回可重试错误。\n\n"
            "### 输入\n\n接收现有客户端协议。",
        )
        report = MODULE.validate_record(record, document, "implementable")

        self.assertTrue(report.ok, report.errors)

    def test_long_h2_is_rejected_instead_of_forcing_a_sentence_into_navigation(self):
        record = make_complete_record()
        long_heading = "存储适配层负责保持现有客户端协议并把全部读写安全切换到托管存储"
        record["reading"]["overview"]["nodes"][0]["name"] = long_heading
        record["reading"]["chapters"][1]["heading"] = long_heading
        document = COMPLETE_DOCUMENT.replace(
            "| 存储适配层 |",
            f"| {long_heading} |",
        ).replace(
            "## 存储适配层",
            f"## {long_heading}",
        )
        report = MODULE.validate_record(record, document, "implementable")

        self.assertFalse(report.ok)
        self.assertTrue(
            any("H1/H2 过长" in error for error in report.errors),
            report.errors,
        )

    def test_core_chapter_must_map_to_an_overview_node(self):
        record = make_complete_record()
        record["reading"]["chapters"].append(
            {
                "id": "orphan",
                "parent": "overview",
                "heading": "孤立核心章节",
                "summary": "没有出现在总体模型中",
                "role": "core",
                "level": 2,
                "supports": [],
            }
        )
        document = COMPLETE_DOCUMENT + (
            "\n## 孤立核心章节\n\n这段没有对应总体节点。\n"
        )
        report = MODULE.validate_record(record, document, "implementable")

        self.assertFalse(report.ok)
        self.assertTrue(
            any("不属于总体模型" in error for error in report.errors),
            report.errors,
        )

    def test_overview_must_show_every_node_with_same_chapter_name(self):
        record = make_complete_record()
        record["reading"]["overview"]["nodes"][0]["name"] = "协议转换层"
        report = MODULE.validate_record(
            record,
            COMPLETE_DOCUMENT,
            "implementable",
        )

        self.assertFalse(report.ok)
        self.assertTrue(
            any("名称必须与主章节标题一致" in error for error in report.errors),
            report.errors,
        )

    def test_overview_body_must_name_every_node(self):
        record = make_complete_record()
        document = COMPLETE_DOCUMENT.replace(
            "| 托管存储 | 自动扩容并持久化会话 | 见“托管存储” |\n",
            "",
        ).replace(
            "会话服务先经过存储适配层，再读写托管存储。两个节点分别隔离协议变化和承担自动扩容。",
            "会话服务先经过存储适配层，再读写第二节点。",
        )
        report = MODULE.validate_record(record, document, "implementable")

        self.assertFalse(report.ok)
        self.assertTrue(
            any("总体模型正文未展示节点" in error for error in report.errors),
            report.errors,
        )

    def test_core_chapter_order_must_follow_overview(self):
        record = make_complete_record()
        adapter = (
            "## 存储适配层\n\n"
            "适配层保持现有客户端协议，把读写切换到托管存储；超时返回可重试错误。\n\n"
        )
        managed = (
            "## 托管存储\n\n"
            "托管存储承担自动扩容和会话持久化，代价是服务费用增加。\n\n"
        )
        document = COMPLETE_DOCUMENT.replace(adapter + managed, managed + adapter)
        report = MODULE.validate_record(record, document, "implementable")

        self.assertFalse(report.ok)
        self.assertTrue(
            any("核心章节顺序" in error for error in report.errors),
            report.errors,
        )

    def test_multi_node_design_cannot_use_only_prose_as_overview(self):
        record = make_complete_record()
        record["reading"]["overview"]["format"] = "prose"
        report = MODULE.validate_record(
            record,
            COMPLETE_DOCUMENT,
            "implementable",
        )

        self.assertFalse(report.ok)
        self.assertTrue(
            any("不能只用连续文字" in error for error in report.errors),
            report.errors,
        )

    def test_overview_must_appear_before_core_chapters(self):
        record = make_complete_record()
        overview = (
            "## 总体设计\n\n"
            "会话服务先经过存储适配层，再读写托管存储。两个节点分别隔离协议变化和承担自动扩容。\n\n"
            "| 节点 | 责任 | 下钻 |\n"
            "| --- | --- | --- |\n"
            "| 存储适配层 | 保持客户端协议并切换存储 | 见“存储适配层” |\n"
            "| 托管存储 | 自动扩容并持久化会话 | 见“托管存储” |\n\n"
        )
        document = COMPLETE_DOCUMENT.replace(overview, "")
        document = document.replace(
            "## 发布与回退",
            overview + "## 发布与回退",
        )
        report = MODULE.validate_record(record, document, "implementable")

        self.assertFalse(report.ok)
        self.assertTrue(
            any("总体模型必须出现在" in error for error in report.errors),
            report.errors,
        )

    def test_crosscutting_chapter_must_name_supported_nodes(self):
        record = make_complete_record()
        record["reading"]["chapters"][-1]["supports"] = ["unknown"]
        report = MODULE.validate_record(
            record,
            COMPLETE_DOCUMENT,
            "implementable",
        )

        self.assertFalse(report.ok)
        self.assertTrue(
            any("未知节点" in error for error in report.errors),
            report.errors,
        )

    def test_simple_document_can_exempt_a_separate_overview_with_reason(self):
        record = make_complete_record()
        record["reading"]["overview"].update(
            {
                "required": False,
                "exemption_reason": "单点配置修改，两段正文即可说明",
                "heading": "",
                "summary": "只调整存储适配层超时",
                "format": "prose",
                "source_ref": "",
                "nodes": [],
            }
        )
        record["reading"]["chapters"] = [
            {
                "id": "change",
                "parent": "overview",
                "heading": "存储超时调整",
                "summary": "仅调整超时，不改变协议",
                "role": "orientation",
                "level": 2,
                "supports": [],
            }
        ]
        document = """# 存储超时调整

> **方案主张：** 延长存储超时，减少峰值误判。
>
> **当前范围：** 只改超时时间，不改协议。

## 存储超时调整

本次只调整超时参数，两段正文即可说明，不需要独立架构总览。
"""
        report = MODULE.validate_record(record, document, "implementable")

        self.assertTrue(report.ok, report.errors)

    def test_schema_v2_remains_compatible(self):
        record = make_complete_record()
        record["schema_version"] = 2
        record["reading"] = {
            "first_screen": {
                "decision": "采用托管存储",
                "why_now": "人工扩容无法满足目标",
                "boundary": "保持客户端协议不变",
                "reader_actions": ["批准并实施"],
            },
            "named_parts": [],
            "section_map": [
                {
                    "heading": item["heading"],
                    "point": item["summary"],
                    "layer": "detail" if item["role"] == "appendix" else "main",
                }
                for item in make_complete_record()["reading"]["chapters"]
            ] + [
                {
                    "heading": "总体设计",
                    "point": "适配层连接托管存储",
                    "layer": "main",
                }
            ],
        }
        record["reader_test"] = {
            "first_screen": {
                "answers_locked": True,
                "answers": {
                    "decision": "采用托管存储",
                    "why_now": "人工扩容",
                    "boundary": "协议不变",
                    "named_parts": "两个节点",
                    "reader_action": "批准",
                },
                "completed": True,
                "result": "pass",
                "findings": [],
            },
            "mainline": {
                "answers_locked": True,
                "answers": {
                    "story": "适配层连接托管存储",
                    "detail_routes": "无附录",
                },
                "completed": True,
                "result": "pass",
                "findings": [],
            },
            "answers_locked": True,
            "approved_by": "技术负责人",
            "answers": {f"Q{i}": "已回答" for i in range(1, 6)},
            "completed": True,
            "result": "pass",
            "findings": [],
        }
        document = COMPLETE_DOCUMENT.replace("方案主张", "结论").replace(
            "当前范围", "读者动作"
        )
        report = MODULE.validate_record(record, document, "implementable")

        self.assertTrue(report.ok, report.errors)

    def test_schema_v1_remains_compatible_with_warning(self):
        record = make_complete_record()
        record["schema_version"] = 1
        del record["reading"]
        del record["reader_test"]["overview"]
        del record["reader_test"]["outline"]
        del record["reader_test"]["drilldown"]

        report = MODULE.validate_record(
            record,
            COMPLETE_DOCUMENT,
            "implementable",
        )

        self.assertTrue(report.ok, report.errors)
        self.assertTrue(
            any("schema v1" in warning for warning in report.warnings),
            report.warnings,
        )

    def test_record_without_visuals_remains_compatible(self):
        record = make_complete_record()
        del record["visuals"]

        report = MODULE.validate_record(
            record,
            COMPLETE_DOCUMENT,
            "implementable",
        )

        self.assertTrue(report.ok, report.errors)

    def test_diagram_guidance_covers_core_views(self):
        guidance = (
            Path(__file__).resolve().parents[1]
            / "references"
            / "diagram-guidance.md"
        ).read_text(encoding="utf-8")

        for heading in (
            "上下文图",
            "容器图",
            "时序图",
            "流程图和泳道图",
            "状态图",
            "数据流图",
            "ER 图",
            "甘特图",
            "里程碑图",
        ):
            self.assertIn(f"### {heading}", guidance)
        self.assertIn("一图一问", guidance)
        self.assertIn("真实渲染", guidance)
        self.assertIn("800 像素文档宽度", guidance)
        self.assertNotIn("680 至 900 像素", guidance)
        self.assertIn("6 条生命线", guidance)
        self.assertIn("70% 以下", guidance)
        self.assertIn("loop + alt + par", guidance)
        self.assertIn("碎片化换行", guidance)
        self.assertIn("每张图都要有自己的图前说明和图后结论", guidance)
        self.assertIn("属于内部制图过程", guidance)
        self.assertIn("不能写成“消费者组”", guidance)
        self.assertIn("高宽比超过 1.3", guidance)
        self.assertIn("edgeLabelBackground", guidance)
        self.assertIn("返回路径也要保持同一调用边界", guidance)
        self.assertIn("不能用分组边框代替内部节点", guidance)
        self.assertIn("主要文字不小于约 12 像素", guidance)
        self.assertIn("辅助文字不小于约 9 像素", guidance)
        self.assertIn("不能从 `Inventory`、`Billing` 等名称自行推出", guidance)
        self.assertIn("中文通常不超过 8 个字", guidance)
        self.assertIn("不能出现孤立括号或尾字换行", guidance)
        self.assertIn("动作关系按执行者定方向", guidance)
        self.assertIn("编号与标签重叠就关闭自动编号", guidance)

    def test_internal_scaffolding_is_rejected_from_final_document(self):
        record = make_complete_record()
        document = COMPLETE_DOCUMENT + """

## 质量门禁

| 门禁 | 结果 |
| --- | --- |
| G1 | pass |
| G4 | pass |
| G7 | pass |
"""

        report = MODULE.validate_record(
            record,
            document,
            "implementable",
        )

        self.assertFalse(report.ok)
        self.assertTrue(
            any("泄漏" in error for error in report.errors),
            report.errors,
        )

    def test_optional_visual_with_render_evidence_passes(self):
        record = make_complete_record()
        record["visuals"] = [
            {
                "id": "V1",
                "question": "请求如何经过会话服务访问存储",
                "audience": ["研发", "测试"],
                "type": "sequence",
                "scope": "目标方案的主流程与超时分支",
                "view_state": "target",
                "source_ref": "diagrams/session-read.mmd",
                "source_format": "mermaid",
                "evidence": ["E1"],
                "placement": "改动集中在存储适配层",
                "render_evidence": "evidence/session-read.png",
                "reviewed": True,
                "last_verified_at": "2026-09-22",
            }
        ]
        document = COMPLETE_DOCUMENT + """

```mermaid
sequenceDiagram
    participant API
    participant Store
    API->>Store: 读取会话
```
"""

        report = MODULE.validate_record(
            record,
            document,
            "implementable",
        )

        self.assertTrue(report.ok, report.errors)

    def test_visual_without_render_review_blocks_implementable(self):
        record = make_complete_record()
        record["visuals"] = [
            {
                "id": "V1",
                "question": "目标系统由哪些运行单元组成",
                "audience": ["研发"],
                "type": "container",
                "scope": "目标架构",
                "view_state": "target",
                "source_ref": "diagrams/target.mmd",
                "source_format": "mermaid",
                "evidence": ["E1"],
                "placement": "改动集中在存储适配层",
                "render_evidence": "",
                "reviewed": False,
                "last_verified_at": "",
            }
        ]

        report = MODULE.validate_record(
            record,
            COMPLETE_DOCUMENT,
            "implementable",
        )

        self.assertFalse(report.ok)
        self.assertTrue(
            any("render_evidence" in error for error in report.errors),
            report.errors,
        )
        self.assertTrue(
            any("reviewed" in error for error in report.errors),
            report.errors,
        )

    def test_embedded_diagram_requires_visual_record(self):
        record = make_complete_record()
        document = COMPLETE_DOCUMENT + """

```mermaid
flowchart LR
    A --> B
```
"""

        report = MODULE.validate_record(
            record,
            document,
            "implementable",
        )

        self.assertFalse(report.ok)
        self.assertTrue(
            any("未登记 visuals" in error for error in report.errors),
            report.errors,
        )

    def test_unique_path_requires_g4_not_applicable(self):
        record = make_complete_record()
        record["options"]["candidates"] = [
            {
                "name": "唯一方案",
                "summary": "受协议约束只能沿用现有接口",
                "feasible": True,
                "decisive_tradeoff": "接受现有接口限制",
            }
        ]
        record["options"]["comparison_criteria"] = []
        record["options"]["unique_path_reason"] = "协议兼容要求排除了其他路径"
        record["gates"]["G4"] = {
            "status": "not_applicable",
            "reason": "协议兼容要求将方案空间收敛到唯一路径",
            "evidence": ["E1"],
        }

        report = MODULE.validate_record(
            record,
            COMPLETE_DOCUMENT,
            "implementable",
        )

        self.assertTrue(report.ok, report.errors)

    def test_high_risk_trigger_requires_every_control(self):
        record = make_complete_record()
        record["delivery"]["risk_level"] = "high"
        record["delivery"]["risk_triggers"] = ["data_write"]
        record["delivery"]["special_reviews"] = ["数据负责人评审通过"]
        record["delivery"]["risk_controls"]["data_write"].update(
            {
                "idempotency": "使用请求唯一键",
                "consistency": "双写对账",
                "retry_compensation": "失败任务补偿",
                "data_rollback": "",
            }
        )

        report = MODULE.validate_record(
            record,
            COMPLETE_DOCUMENT,
            "implementable",
        )

        self.assertFalse(report.ok)
        self.assertTrue(
            any("data_rollback" in error for error in report.errors),
            report.errors,
        )

    def test_open_blocker_prevents_review(self):
        record = make_complete_record()
        record["document"]["status"] = "in_review"
        record["open_items"]["blockers"] = [
            {
                "question": "权威数据源尚未确认",
                "owner": "数据负责人",
            }
        ]

        report = MODULE.validate_record(
            record,
            COMPLETE_DOCUMENT,
            "in_review",
        )

        self.assertFalse(report.ok)
        self.assertTrue(
            any("未关闭阻塞项" in error for error in report.errors),
            report.errors,
        )

    def test_unresolved_evidence_conflict_prevents_review(self):
        record = make_complete_record()
        record["document"]["status"] = "in_review"
        record["problem"]["evidence"][0]["conflicts"] = ["E2 给出相反结论"]

        report = MODULE.validate_record(
            record,
            COMPLETE_DOCUMENT,
            "in_review",
        )

        self.assertFalse(report.ok)
        self.assertTrue(
            any("未关闭的证据冲突" in error for error in report.errors),
            report.errors,
        )

    def test_transition_revalidation_can_restore_previous_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            record_path = Path(temp_dir) / "decision-record.json"
            document_path = Path(temp_dir) / "document.md"
            record = make_complete_record()
            MODULE.write_json(record_path, record)
            document_path.write_text(COMPLETE_DOCUMENT, encoding="utf-8")

            enter_args = Namespace(
                record=str(record_path),
                document=str(document_path),
                to="revalidation",
                actor="系统负责人",
                reason="发现新的容量证据",
                replacement=None,
                json=False,
            )
            self.assertEqual(MODULE.transition_command(enter_args), 0)
            revalidation = MODULE.load_json(record_path)
            self.assertEqual(
                revalidation["document"]["review_from"],
                "implementable",
            )

            restore_args = Namespace(
                record=str(record_path),
                document=str(document_path),
                to="implementable",
                actor="系统负责人",
                reason="复核后原决定仍然成立",
                replacement=None,
                json=False,
            )
            self.assertEqual(MODULE.transition_command(restore_args), 0)
            restored = MODULE.load_json(record_path)
            self.assertEqual(restored["document"]["status"], "implementable")
            self.assertIsNone(restored["document"]["review_from"])

    def test_superseded_requires_replacement(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            record_path = Path(temp_dir) / "decision-record.json"
            document_path = Path(temp_dir) / "document.md"
            record = make_complete_record()
            record["document"]["status"] = "revalidation"
            record["document"]["review_from"] = "implementable"
            record["document"]["status_reason"] = "原决定需要调整"
            MODULE.write_json(record_path, record)
            document_path.write_text(COMPLETE_DOCUMENT, encoding="utf-8")

            args = Namespace(
                record=str(record_path),
                document=str(document_path),
                to="superseded",
                actor="技术负责人",
                reason="新决定已经接受",
                replacement=None,
                json=False,
            )
            self.assertEqual(MODULE.transition_command(args), 1)
            unchanged = MODULE.load_json(record_path)
            self.assertEqual(unchanged["document"]["status"], "revalidation")

            args.replacement = "docs/new-decision.md"
            self.assertEqual(MODULE.transition_command(args), 0)
            superseded = MODULE.load_json(record_path)
            self.assertEqual(superseded["document"]["status"], "superseded")
            self.assertEqual(
                superseded["document"]["replacement_document"],
                "docs/new-decision.md",
            )

    def test_incomplete_draft_can_be_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            init_args = Namespace(
                title="撤回方案",
                author="测试作者",
                decision_owner="",
                type="technical-design",
                output=temp_dir,
                force=False,
            )
            self.assertEqual(MODULE.init_workspace(init_args), 0)
            record_path = Path(temp_dir) / "decision-record.json"
            document_path = Path(temp_dir) / "document.md"
            transition_args = Namespace(
                record=str(record_path),
                document=str(document_path),
                to="rejected",
                actor="测试作者",
                reason="需求取消",
                replacement=None,
                json=False,
            )

            self.assertEqual(MODULE.transition_command(transition_args), 0)
            rejected = MODULE.load_json(record_path)
            self.assertEqual(rejected["document"]["status"], "rejected")


class HeadingStyleTests(unittest.TestCase):
    """Titles are short topics (TOC directions), never numbered steps or sentences,
    and conversation provenance / personal data never leak into the document."""

    DOC = (
        "# 示例方案\n\n结论：现在改造，降低发布故障。\n\n"
        "## 聚合校验\n\n本章给出结论。\n\n"
        "## 发布与回退\n\n回退策略明确。\n\n"
        "## 数据采集\n\n采集口径如下。\n"
    )

    def _audit(self, document):
        return MODULE.readability_audit(document)

    def test_short_keyword_headings_pass(self):
        audit = self._audit(self.DOC)
        self.assertEqual(audit["numbered_headings"], [])
        self.assertEqual(audit["sentence_headings"], [])
        self.assertEqual(audit["conversation_leaks"], [])
        self.assertEqual(audit["personal_leaks"], [])
        for title in ("聚合校验", "tag T+1", "发布与回退", "数据采集", "背景与目标", "缓存组件明细"):
            self.assertFalse(MODULE._heading_reads_like_sentence(title), title)

    def test_sentence_headings_from_real_edits_are_rejected(self):
        for title in (
            "聚合校验是什么，为什么会被下掉",
            "tag T+1 的两条数据线怎么对照验收",
            "一条指标数据的旅程：从研发按一次构建，到看板上一个点",
            "被裁业务在手机上到底表现成什么样",
        ):
            doc = self.DOC.replace("## 聚合校验", f"## {title}")
            audit = self._audit(doc)
            self.assertIn(title, audit["sentence_headings"], title)

    def test_numbered_headings_are_rejected(self):
        for title in ("第3步 数据采集", "1. 数据采集", "一、数据采集", "(2) 发布与回退"):
            doc = self.DOC.replace("## 聚合校验", f"## {title}")
            audit = self._audit(doc)
            self.assertIn(title, audit["numbered_headings"], title)

    def test_conversation_provenance_is_rejected(self):
        for line in (
            "老板和同学问这个数据哪来的。",
            "同事说先回滚再排查。",
            "你之前让我对比两条数据线。",
        ):
            audit = self._audit(self.DOC + "\n" + line + "\n")
            self.assertTrue(audit["conversation_leaks"], line)

    def test_role_words_alone_are_not_personal_data(self):
        audit = self._audit(self.DOC + "\n请同事评审，领导同意后发布。\n")
        self.assertEqual(audit["conversation_leaks"], [])
        self.assertEqual(audit["personal_leaks"], [])

    def test_personal_info_is_rejected(self):
        # 构造隐私格式测试数据，不保存真实电话或邮箱。
        phone = "138" + "12345678"
        email = "tester" + "@" + "example.invalid"
        for line, needle in (
            (f"联系 {phone} 处理。", phone),
            (f"发 {email}。", "@"),
            ("找李明老师确认口径。", "李明老师"),
        ):
            audit = self._audit(self.DOC + "\n" + line + "\n")
            self.assertTrue(any(needle in p for p in audit["personal_leaks"]), line)

    def test_validate_record_surfaces_heading_and_leak_errors(self):
        record = make_complete_record()
        title = "聚合校验是什么，为什么会被下掉"
        record["reading"]["overview"]["nodes"][0]["name"] = "聚合校验"
        record["reading"]["chapters"][1]["heading"] = "聚合校验"
        document = COMPLETE_DOCUMENT.replace("## 存储适配层", f"## {title}")
        report = MODULE.validate_record(record, document, "implementable")
        self.assertFalse(report.ok)
        self.assertTrue(any("短关键词" in e for e in report.errors), report.errors)


if __name__ == "__main__":
    unittest.main()
