#!/usr/bin/env python3
"""Initialize and validate evidence-driven engineering documents."""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


SKILL_DIR = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = SKILL_DIR / "templates"
GATE_IDS = tuple(f"G{index}" for index in range(13))
GATE_STATES = {"pass", "revise", "not_applicable", "blocked"}
DOCUMENT_TYPES = {
    "technical-design",
    "rfc",
    "architecture-decision",
    "refactor-migration",
}
DOCUMENT_STATUSES = {
    "draft",
    "in_review",
    "decided",
    "implementable",
    "implemented",
    "revalidation",
    "rejected",
    "superseded",
}
VISUAL_TYPES = {
    "context",
    "container",
    "component",
    "deployment",
    "sequence",
    "flowchart",
    "swimlane",
    "state",
    "dataflow",
    "erd",
    "gantt",
    "milestone",
    "other",
}
VISUAL_STATES = {"current", "target", "transition", "schedule"}
VISUAL_FORMATS = {
    "mermaid",
    "plantuml",
    "svg",
    "drawio",
    "whiteboard",
    "other",
}
STATUS_LABELS = {
    "draft": "草案",
    "in_review": "待评审",
    "decided": "已决定",
    "implementable": "可实施",
    "implemented": "已实施",
    "revalidation": "待复核",
    "rejected": "未采纳",
    "superseded": "被取代",
}
REQUIRED_GATES = {
    "draft": (),
    "in_review": GATE_IDS[:12],
    "decided": GATE_IDS[:12],
    "implementable": GATE_IDS,
    "implemented": GATE_IDS,
    "revalidation": (),
    "rejected": (),
    "superseded": (),
}
ALLOWED_TRANSITIONS = {
    "draft": {"in_review", "rejected"},
    "in_review": {"draft", "decided", "rejected"},
    "decided": {"implementable", "revalidation"},
    "implementable": {"decided", "implemented", "revalidation"},
    "implemented": {"revalidation"},
    "revalidation": {"superseded"},
    "rejected": set(),
    "superseded": set(),
}
RISK_CONTROL_FIELDS = {
    "public_interface": (
        "compatibility",
        "versioning",
        "callers",
        "migration_order",
    ),
    "data_write": (
        "idempotency",
        "consistency",
        "retry_compensation",
        "data_rollback",
    ),
    "concurrency_async": (
        "ordering",
        "duplicates",
        "loss",
        "locking",
        "capacity_degradation",
    ),
    "security_privacy": (
        "authorization",
        "audit",
        "data_exposure",
        "failure_policy",
        "special_review",
    ),
    "performance_capacity": (
        "baseline",
        "target",
        "load_test",
        "bottleneck_hypothesis",
        "metrics",
    ),
    "migration_refactor": (
        "dual_run",
        "verification",
        "cutover",
        "retirement",
        "rollback_window",
    ),
    "user_visible": (
        "error_experience",
        "supported_versions",
        "rollout_scope",
        "support_communication",
    ),
    "observability_ops": (
        "signal",
        "threshold",
        "owner",
        "response",
    ),
}
PLACEHOLDER_RE = re.compile(r"<!--")
INTERNAL_HEADING_RE = re.compile(
    r"(?m)^#{1,6}\s+"
    r"(?:文档契约|证据账本|质量门禁|标准决策对象)\s*$"
)
GATE_LABEL_RE = re.compile(r"\bG(?:[0-9]|1[0-2])\b")
EMBEDDED_DIAGRAM_RE = re.compile(
    r"```(?:mermaid|plantuml)\b|<svg\b",
    re.IGNORECASE,
)


@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def is_filled(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return bool(value)
    if isinstance(value, dict):
        return bool(value)
    return value is not None


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def get_path(data: dict[str, Any], path: str, default: Any = None) -> Any:
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def require_filled(
    report: ValidationReport,
    data: dict[str, Any],
    path: str,
    label: str,
) -> None:
    if not is_filled(get_path(data, path)):
        report.error(f"{label}不能为空（{path}）")


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"找不到决策记录：{path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"决策记录不是合法 JSON：{path}:{exc.lineno}:{exc.colno} {exc.msg}"
        ) from exc
    if not isinstance(value, dict):
        raise ValueError("决策记录根节点必须是 JSON 对象")
    return value


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        delete=False,
    ) as handle:
        handle.write(content)
        temp_path = Path(handle.name)
    temp_path.replace(path)


def write_json(path: Path, data: dict[str, Any]) -> None:
    atomic_write_text(
        path,
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
    )


def replace_tokens(value: Any, replacements: dict[str, str]) -> Any:
    if isinstance(value, str):
        for token, replacement in replacements.items():
            value = value.replace(token, replacement)
        return value
    if isinstance(value, list):
        return [replace_tokens(item, replacements) for item in value]
    if isinstance(value, dict):
        return {
            key: replace_tokens(item, replacements)
            for key, item in value.items()
        }
    return value


def validate_gate_structure(
    report: ValidationReport,
    record: dict[str, Any],
    target: str,
) -> None:
    gates = as_dict(record.get("gates"))
    missing = [gate_id for gate_id in GATE_IDS if gate_id not in gates]
    unknown = sorted(set(gates) - set(GATE_IDS))
    if missing:
        report.error(f"缺少门禁记录：{', '.join(missing)}")
    if unknown:
        report.error(f"存在未知门禁：{', '.join(unknown)}")

    required = set(REQUIRED_GATES[target])
    for gate_id in GATE_IDS:
        gate = gates.get(gate_id)
        if not isinstance(gate, dict):
            continue
        status = gate.get("status")
        if status not in GATE_STATES:
            report.error(f"{gate_id} 状态非法：{status!r}")
            continue
        reason = gate.get("reason")
        evidence = gate.get("evidence")
        if not isinstance(reason, str):
            report.error(f"{gate_id}.reason 必须是字符串")
        if not isinstance(evidence, list):
            report.error(f"{gate_id}.evidence 必须是数组")
        if status == "not_applicable" and not is_filled(reason):
            report.error(f"{gate_id} 标为不适用时必须填写理由")
        if gate_id in required:
            if status not in {"pass", "not_applicable"}:
                report.error(
                    f"{STATUS_LABELS[target]}要求关闭 {gate_id}，当前为 {status}"
                )
            elif status == "pass" and not (
                is_filled(reason) or is_filled(evidence)
            ):
                report.error(f"{gate_id} 通过时必须记录理由或证据")


def validate_evidence(
    report: ValidationReport,
    evidence_items: list[Any],
) -> None:
    seen_ids: set[str] = set()
    for index, item in enumerate(evidence_items):
        prefix = f"problem.evidence[{index}]"
        if not isinstance(item, dict):
            report.error(f"{prefix} 必须是对象")
            continue
        for key in (
            "id",
            "claim",
            "source",
            "source_type",
            "scope",
            "observed_at",
            "verified_by",
        ):
            if not is_filled(item.get(key)):
                report.error(f"{prefix}.{key} 不能为空")
        evidence_id = item.get("id")
        if isinstance(evidence_id, str):
            if evidence_id in seen_ids:
                report.error(f"证据编号重复：{evidence_id}")
            seen_ids.add(evidence_id)
        conflicts = item.get("conflicts", [])
        if not isinstance(conflicts, list):
            report.error(f"{prefix}.conflicts 必须是数组")
        elif conflicts:
            report.error(f"{prefix} 仍有未关闭的证据冲突")


def validate_goals(report: ValidationReport, goals: list[Any]) -> None:
    for index, goal in enumerate(goals):
        prefix = f"criteria.goals[{index}]"
        if not isinstance(goal, dict):
            report.error(f"{prefix} 必须是对象，包含 statement 和 acceptance")
            continue
        if not is_filled(goal.get("statement")):
            report.error(f"{prefix}.statement 不能为空")
        if not is_filled(goal.get("acceptance")):
            report.error(f"{prefix}.acceptance 不能为空")


def validate_options(
    report: ValidationReport,
    record: dict[str, Any],
    target: str,
) -> None:
    options = as_dict(record.get("options"))
    candidates = as_list(options.get("candidates"))
    comparison = as_list(options.get("comparison_criteria"))
    unique_reason = options.get("unique_path_reason")
    gate_g4 = as_dict(as_dict(record.get("gates")).get("G4"))
    gate_status = gate_g4.get("status")

    if is_filled(unique_reason):
        if len(candidates) > 1:
            report.error("已声明方案唯一，不能同时提供多个候选方案")
        if target in REQUIRED_GATES and "G4" in REQUIRED_GATES[target]:
            if gate_status != "not_applicable":
                report.error("方案唯一时 G4 必须标为 not_applicable")
        return

    if target != "draft":
        if len(candidates) < 2:
            report.error("存在方案取舍时至少需要两个真实候选；否则填写 unique_path_reason")
        if not comparison:
            report.error("存在方案取舍时 comparison_criteria 不能为空")

    for index, candidate in enumerate(candidates):
        prefix = f"options.candidates[{index}]"
        if not isinstance(candidate, dict):
            report.error(f"{prefix} 必须是对象")
            continue
        for key in ("name", "summary", "decisive_tradeoff"):
            if not is_filled(candidate.get(key)):
                report.error(f"{prefix}.{key} 不能为空")
        if not isinstance(candidate.get("feasible"), bool):
            report.error(f"{prefix}.feasible 必须是布尔值")


def validate_risk_controls(
    report: ValidationReport,
    record: dict[str, Any],
    target: str,
) -> None:
    delivery = as_dict(record.get("delivery"))
    risk_level = delivery.get("risk_level")
    if risk_level not in {"low", "standard", "high"}:
        report.error(f"delivery.risk_level 非法：{risk_level!r}")

    triggers = as_list(delivery.get("risk_triggers"))
    if len(triggers) != len(set(triggers)):
        report.error("delivery.risk_triggers 存在重复项")
    unknown = sorted(set(triggers) - set(RISK_CONTROL_FIELDS))
    if unknown:
        report.error(f"未知风险触发项：{', '.join(unknown)}")

    if risk_level == "high" and not triggers:
        report.error("高风险文档至少需要一个 risk_trigger")

    if target not in {"implementable", "implemented"}:
        return

    controls = as_dict(delivery.get("risk_controls"))
    for trigger in triggers:
        trigger_controls = as_dict(controls.get(trigger))
        for field_name in RISK_CONTROL_FIELDS[trigger]:
            if not is_filled(trigger_controls.get(field_name)):
                report.error(
                    f"风险触发项 {trigger} 缺少控制字段：{field_name}"
                )

    if risk_level == "high":
        for path, label in (
            ("delivery.observability", "高风险方案的感知办法"),
            ("delivery.rollout", "高风险方案的灰度或迁移办法"),
            ("delivery.rollback", "高风险方案的止损或回退办法"),
            ("delivery.special_reviews", "高风险方案的专项评审记录"),
        ):
            require_filled(report, record, path, label)


def validate_visuals(
    report: ValidationReport,
    record: dict[str, Any],
    document_text: str,
    target: str,
) -> None:
    visuals = record.get("visuals", [])
    if not isinstance(visuals, list):
        report.error("visuals 必须是数组")
        return

    seen_ids: set[str] = set()
    for index, visual in enumerate(visuals):
        prefix = f"visuals[{index}]"
        if not isinstance(visual, dict):
            report.error(f"{prefix} 必须是对象")
            continue

        for key in (
            "id",
            "question",
            "audience",
            "type",
            "scope",
            "view_state",
            "source_ref",
            "source_format",
            "evidence",
            "placement",
        ):
            if not is_filled(visual.get(key)):
                report.error(f"{prefix}.{key} 不能为空")

        visual_id = visual.get("id")
        if isinstance(visual_id, str):
            if visual_id in seen_ids:
                report.error(f"图示编号重复：{visual_id}")
            seen_ids.add(visual_id)

        if visual.get("type") not in VISUAL_TYPES:
            report.error(f"{prefix}.type 非法：{visual.get('type')!r}")
        if visual.get("view_state") not in VISUAL_STATES:
            report.error(
                f"{prefix}.view_state 非法：{visual.get('view_state')!r}"
            )
        if visual.get("source_format") not in VISUAL_FORMATS:
            report.error(
                f"{prefix}.source_format 非法："
                f"{visual.get('source_format')!r}"
            )
        if not isinstance(visual.get("audience"), list):
            report.error(f"{prefix}.audience 必须是数组")
        if not isinstance(visual.get("evidence"), list):
            report.error(f"{prefix}.evidence 必须是数组")

        if target in {"implementable", "implemented"}:
            if not is_filled(visual.get("render_evidence")):
                report.error(f"{prefix}.render_evidence 不能为空")
            if visual.get("reviewed") is not True:
                report.error(f"{prefix}.reviewed 必须为 true")
            if not is_filled(visual.get("last_verified_at")):
                report.error(f"{prefix}.last_verified_at 不能为空")

    if EMBEDDED_DIAGRAM_RE.search(document_text) and not visuals:
        report.error("正文包含图示源码，但 decision-record.json 未登记 visuals")


def validate_reader_test(
    report: ValidationReport,
    record: dict[str, Any],
    target: str,
) -> None:
    if target not in {"implementable", "implemented"}:
        return
    reader_test = as_dict(record.get("reader_test"))
    if reader_test.get("answers_locked") is not True:
        report.error("进入可实施状态前必须锁定独立读者测试答案")
    if not is_filled(reader_test.get("approved_by")):
        report.error("独立读者测试答案必须由决定责任人确认")
    answers = as_dict(reader_test.get("answers"))
    for index in range(1, 6):
        if not is_filled(answers.get(f"Q{index}")):
            report.error(f"reader_test.answers.Q{index} 不能为空")
    if reader_test.get("completed") is not True:
        report.error("进入可实施状态前必须完成独立读者测试")
    if reader_test.get("result") != "pass":
        report.error("独立读者测试结果必须为 pass")


def validate_status_fields(
    report: ValidationReport,
    record: dict[str, Any],
    target: str,
) -> None:
    document = as_dict(record.get("document"))
    review_from = document.get("review_from")
    if target == "revalidation":
        if review_from not in {"decided", "implementable", "implemented"}:
            report.error("待复核状态必须记录合法的 review_from")
        if not is_filled(document.get("status_reason")):
            report.error("待复核状态必须记录复核原因")
    elif is_filled(review_from):
        report.error("只有待复核状态可以保留 review_from")

    if target == "rejected" and not is_filled(document.get("status_reason")):
        report.error("未采纳状态必须记录否决或撤回理由")
    if target == "superseded":
        if not is_filled(document.get("replacement_document")):
            report.error("被取代状态必须指向替代文档")
        if not is_filled(document.get("status_reason")):
            report.error("被取代状态必须记录原因")

    if target in {"decided", "implementable", "implemented"}:
        require_filled(
            report,
            record,
            "decision.accepted_by",
            "决定责任人",
        )
        require_filled(
            report,
            record,
            "decision.accepted_at",
            "决定接受时间",
        )

    if target == "implemented":
        require_filled(
            report,
            record,
            "delivery.implementation_evidence",
            "实现与验证证据",
        )


def validate_record(
    record: dict[str, Any],
    document_text: str,
    target: str | None = None,
) -> ValidationReport:
    report = ValidationReport()
    if record.get("schema_version") != 1:
        report.error("schema_version 必须为 1")

    for key in (
        "document",
        "problem",
        "criteria",
        "options",
        "decision",
        "design",
        "delivery",
        "open_items",
        "gates",
        "reader_test",
        "history",
    ):
        if key not in record:
            report.error(f"缺少顶层字段：{key}")

    document = as_dict(record.get("document"))
    current_status = document.get("status")
    effective_target = target or current_status
    if effective_target not in DOCUMENT_STATUSES:
        report.error(f"目标状态非法：{effective_target!r}")
        return report
    if current_status not in DOCUMENT_STATUSES:
        report.error(f"当前状态非法：{current_status!r}")
    if target and current_status != target:
        report.warn(
            f"当前记录状态为 {current_status}，本次按目标状态 {target} 预检"
        )

    require_filled(report, record, "document.title", "文档标题")
    require_filled(report, record, "document.type", "文档类型")
    require_filled(report, record, "document.author", "作者")
    if document.get("type") not in DOCUMENT_TYPES:
        report.error(f"document.type 非法：{document.get('type')!r}")
    if document.get("template_mode") not in {"default", "team"}:
        report.error("document.template_mode 必须是 default 或 team")
    if not isinstance(record.get("history"), list):
        report.error("history 必须是数组")

    validate_gate_structure(report, record, effective_target)
    validate_status_fields(report, record, effective_target)
    validate_visuals(report, record, document_text, effective_target)

    if effective_target not in {
        "draft",
        "revalidation",
        "rejected",
        "superseded",
    }:
        for path, label in (
            ("document.purpose", "文档目的"),
            ("document.audience", "目标读者"),
            ("document.expected_action", "读者期望动作"),
            ("document.scope.in", "范围内事项"),
            ("document.decision_owner", "决定责任人"),
            ("document.updated_at", "更新时间"),
            ("document.applicable_version", "适用版本"),
            ("problem.current_state", "当前状态"),
            ("problem.evidence", "现状证据"),
            ("problem.gap", "问题差距"),
            ("problem.impact", "问题影响"),
            ("problem.do_nothing", "保持现状的结果"),
            ("criteria.goals", "目标"),
            ("criteria.constraints", "约束"),
            ("decision.recommendation", "推荐决定"),
            ("decision.rationale", "决定依据"),
            ("decision.accepted_costs", "接受的代价"),
            ("design.system_boundary", "系统边界"),
            ("design.responsibilities", "职责划分"),
            ("design.main_flow", "主流程"),
            ("design.exceptions", "异常与边界"),
            ("design.contracts", "关键契约"),
            ("design.change_points", "改造落点"),
            ("delivery.impact_surface", "影响面"),
            ("delivery.validation", "验证办法"),
            ("delivery.ownership", "交付负责人"),
        ):
            require_filled(report, record, path, label)

        evidence_items = as_list(get_path(record, "problem.evidence", []))
        validate_evidence(report, evidence_items)
        validate_goals(
            report,
            as_list(get_path(record, "criteria.goals", [])),
        )
        validate_options(report, record, effective_target)

        blockers = as_list(get_path(record, "open_items.blockers", []))
        if blockers:
            report.error("存在未关闭阻塞项，不能进入当前目标状态")

    validate_risk_controls(report, record, effective_target)
    validate_reader_test(report, record, effective_target)

    if not document_text.strip():
        report.error("Markdown 正文为空")
    elif effective_target not in {
        "draft",
        "revalidation",
        "rejected",
        "superseded",
    }:
        placeholder_count = len(PLACEHOLDER_RE.findall(document_text))
        if placeholder_count:
            report.error(f"Markdown 正文仍有 {placeholder_count} 处填写提示")
        leaked_headings = INTERNAL_HEADING_RE.findall(document_text)
        if leaked_headings:
            report.error(
                "默认正文泄漏内部过程章节："
                + "、".join(sorted(set(leaked_headings)))
            )
        gate_labels = GATE_LABEL_RE.findall(document_text)
        if len(gate_labels) >= 3:
            report.error("默认正文泄漏 G0-G12 门禁检查结果")

    return report


def print_report(
    report: ValidationReport,
    target: str,
    as_json: bool = False,
) -> None:
    if as_json:
        print(
            json.dumps(
                {
                    "ok": report.ok,
                    "target": target,
                    "errors": report.errors,
                    "warnings": report.warnings,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    for message in report.errors:
        print(f"[失败] {message}")
    for message in report.warnings:
        print(f"[提醒] {message}")
    if report.ok:
        print(f"[通过] 文档满足“{STATUS_LABELS[target]}”的机器校验")
    else:
        print(
            f"[未通过] “{STATUS_LABELS[target]}”机器校验发现 "
            f"{len(report.errors)} 个问题"
        )


def init_workspace(args: argparse.Namespace) -> int:
    output = Path(args.output).expanduser().resolve()
    document_path = output / "document.md"
    record_path = output / "decision-record.json"
    existing = [path for path in (document_path, record_path) if path.exists()]
    if existing and not args.force:
        paths = "、".join(str(path) for path in existing)
        print(f"[失败] 目标文件已存在：{paths}", file=sys.stderr)
        print("[提示] 确认要覆盖时使用 --force", file=sys.stderr)
        return 1

    replacements = {
        "__TITLE__": args.title,
        "__TYPE__": args.type,
        "__AUTHOR__": args.author,
        "__DATE__": date.today().isoformat(),
    }
    markdown = (TEMPLATE_DIR / "engineering-doc.md").read_text(
        encoding="utf-8"
    )
    for token, replacement in replacements.items():
        markdown = markdown.replace(token, replacement)

    record_template = json.loads(
        (TEMPLATE_DIR / "decision-record.json").read_text(encoding="utf-8")
    )
    record = replace_tokens(record_template, replacements)
    record["document"]["decision_owner"] = args.decision_owner or ""
    record["history"].append(
        {
            "from": None,
            "to": "draft",
            "actor": args.author,
            "at": utc_now(),
            "reason": "初始化研发文档工作区",
        }
    )

    output.mkdir(parents=True, exist_ok=True)
    atomic_write_text(document_path, markdown)
    write_json(record_path, record)
    print(f"[完成] 正文：{document_path}")
    print(f"[完成] 决策记录：{record_path}")
    return 0


def resolve_document_path(
    record_path: Path,
    document_arg: str | None,
) -> Path:
    if document_arg:
        return Path(document_arg).expanduser().resolve()
    return record_path.parent / "document.md"


def validate_command(args: argparse.Namespace) -> int:
    record_path = Path(args.record).expanduser().resolve()
    document_path = resolve_document_path(record_path, args.document)
    try:
        record = load_json(record_path)
        document_text = document_path.read_text(encoding="utf-8")
    except (ValueError, FileNotFoundError) as exc:
        print(f"[失败] {exc}", file=sys.stderr)
        return 1

    target = args.target or get_path(record, "document.status")
    report = validate_record(record, document_text, target)
    print_report(report, target, args.json)
    return 0 if report.ok else 1


def allowed_transition(record: dict[str, Any], target: str) -> bool:
    current = get_path(record, "document.status")
    if current == "revalidation":
        review_from = get_path(record, "document.review_from")
        return target in {"superseded", review_from}
    return target in ALLOWED_TRANSITIONS.get(current, set())


def transition_command(args: argparse.Namespace) -> int:
    record_path = Path(args.record).expanduser().resolve()
    document_path = resolve_document_path(record_path, args.document)
    try:
        original = load_json(record_path)
        document_text = document_path.read_text(encoding="utf-8")
    except (ValueError, FileNotFoundError) as exc:
        print(f"[失败] {exc}", file=sys.stderr)
        return 1

    current = get_path(original, "document.status")
    target = args.to
    if target not in DOCUMENT_STATUSES:
        print(f"[失败] 目标状态非法：{target}", file=sys.stderr)
        return 1
    if not allowed_transition(original, target):
        print(
            f"[失败] 不允许从 {current} 流转到 {target}",
            file=sys.stderr,
        )
        return 1
    if not args.reason.strip():
        print("[失败] 状态流转必须填写原因", file=sys.stderr)
        return 1

    candidate = copy.deepcopy(original)
    document = candidate["document"]
    if target == "revalidation":
        document["review_from"] = current
    elif current == "revalidation" and target == document.get("review_from"):
        document["review_from"] = None
    elif target != "revalidation":
        document["review_from"] = None

    document["status"] = target
    document["status_reason"] = args.reason
    document["updated_at"] = date.today().isoformat()

    if target == "decided":
        if not args.actor.strip():
            print("[失败] 进入已决定状态必须指定 --actor", file=sys.stderr)
            return 1
        candidate["decision"]["accepted_by"] = args.actor
        candidate["decision"]["accepted_at"] = utc_now()
    if target == "superseded":
        if not args.replacement:
            print(
                "[失败] 进入被取代状态必须指定 --replacement",
                file=sys.stderr,
            )
            return 1
        document["replacement_document"] = args.replacement

    candidate["history"].append(
        {
            "from": current,
            "to": target,
            "actor": args.actor,
            "at": utc_now(),
            "reason": args.reason,
        }
    )

    report = validate_record(candidate, document_text, target)
    if not report.ok:
        print_report(report, target, args.json)
        print("[未写回] 目标状态校验失败，决策记录保持不变")
        return 1

    write_json(record_path, candidate)
    print(f"[完成] {current} → {target}")
    print(f"[写回] {record_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="研发文档初始化、门禁校验和状态流转工具"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser(
        "init",
        help="创建 Markdown 正文和结构化决策记录",
    )
    init_parser.add_argument("--title", required=True, help="文档标题")
    init_parser.add_argument("--author", required=True, help="作者")
    init_parser.add_argument(
        "--decision-owner",
        default="",
        help="决定责任人",
    )
    init_parser.add_argument(
        "--type",
        choices=sorted(DOCUMENT_TYPES),
        default="technical-design",
        help="文档类型",
    )
    init_parser.add_argument("--output", required=True, help="输出目录")
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="覆盖已有 document.md 和 decision-record.json",
    )
    init_parser.set_defaults(handler=init_workspace)

    validate_parser = subparsers.add_parser(
        "validate",
        help="检查结构化记录、Markdown 和质量门禁",
    )
    validate_parser.add_argument("--record", required=True, help="决策记录路径")
    validate_parser.add_argument(
        "--document",
        help="Markdown 路径；默认读取决策记录同目录的 document.md",
    )
    validate_parser.add_argument(
        "--target",
        choices=sorted(DOCUMENT_STATUSES),
        help="按目标状态预检；默认使用记录中的当前状态",
    )
    validate_parser.add_argument(
        "--json",
        action="store_true",
        help="输出 JSON 报告",
    )
    validate_parser.set_defaults(handler=validate_command)

    transition_parser = subparsers.add_parser(
        "transition",
        help="校验并流转文档状态",
    )
    transition_parser.add_argument("--record", required=True, help="决策记录路径")
    transition_parser.add_argument(
        "--document",
        help="Markdown 路径；默认读取决策记录同目录的 document.md",
    )
    transition_parser.add_argument(
        "--to",
        required=True,
        choices=sorted(DOCUMENT_STATUSES),
        help="目标状态",
    )
    transition_parser.add_argument(
        "--actor",
        required=True,
        help="执行本次流转的人",
    )
    transition_parser.add_argument(
        "--reason",
        required=True,
        help="状态变化原因",
    )
    transition_parser.add_argument(
        "--replacement",
        help="进入 superseded 时的新文档路径或链接",
    )
    transition_parser.add_argument(
        "--json",
        action="store_true",
        help="校验失败时输出 JSON 报告",
    )
    transition_parser.set_defaults(handler=transition_command)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
