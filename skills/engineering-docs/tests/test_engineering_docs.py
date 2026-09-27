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

## 建议采用托管存储

采用方案 A，并接受额外运维成本。

## 当前扩容依赖人工处理

当前链路无法满足目标。

## 改动集中在存储适配层

方案 A 在统一标准下更适合当前约束。

改造服务入口和存储适配层。

## 先压测和对账，再按租户灰度

按验证、监控、灰度和回退计划实施。
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

        self.assertIn("创建、更新和评审研发技术文档", skill_text)
        self.assertIn("协作成文", skill_text)
        self.assertIn("写技术方案、设计文档、RFC、ADR", skill_text)
        self.assertIn("纯润色", skill_text)
        self.assertIn("非技术文档不用", skill_text)

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
            self.assertEqual(len(record["gates"]), 13)
            self.assertIn("## 建议与依据", document_text)
            self.assertNotIn("非目标", document_text)

    def test_complete_record_passes_implementable_validation(self):
        record = make_complete_record()
        report = MODULE.validate_record(
            record,
            COMPLETE_DOCUMENT,
            "implementable",
        )

        self.assertTrue(report.ok, report.errors)

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
        self.assertIn("680 至 900 像素", guidance)
        self.assertIn("6 条生命线", guidance)
        self.assertIn("70% 以下", guidance)
        self.assertIn("loop + alt + par", guidance)
        self.assertIn("碎片化换行", guidance)
        self.assertIn("每张图都要有自己的图前说明和图后结论", guidance)
        self.assertIn("属于内部制图过程", guidance)
        self.assertIn("不能写成“消费者组”", guidance)
        self.assertIn("高度超过宽度两倍", guidance)
        self.assertIn("edgeLabelBackground", guidance)
        self.assertIn("返回路径也要保持同一调用边界", guidance)
        self.assertIn("不能用分组边框代替内部节点", guidance)
        self.assertIn("主要文字不得小于约 12 像素", guidance)
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


if __name__ == "__main__":
    unittest.main()
