#!/usr/bin/env python3
"""Initialize and validate evidence-driven engineering documents."""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
import tempfile
import unicodedata
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
    "html",
    "archify-json",
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
HEADING_RE = re.compile(r"(?m)^(#{1,6})\s+(.+?)\s*$")
# Headings are a short topic / direction, like a table-of-contents entry — never a
# sentence. These patterns detect "a heading that reads like prose" so it is rejected
# and must be shortened to a keyword. All patterns operate on the heading with any
# leading numbering stripped.
SENTENCE_HEADING_RE = re.compile(
    # ends like a clause and carries a verb/relation, i.e. reads as a sentence
    r"(?:是什么|怎么样|怎么办|为什么|怎么做|如何|多少|哪些|哪里|区别|对比|对照|验收|排查|定位|处理|解决|实现|设计|选择|决定|说明|解释|理解|区分|影响|保证|确保|避免|走|到|给|对|从|把|被|让)"
)
SENTENCE_HEADING_TERMINATORS = ("是什么", "怎么样", "怎么办", "为什么", "怎么做", "如何", "多少", "哪些")
# Explicit numbering in headings is forbidden (第 N 步 / 1. / 1、 / (1) / 一、).
HEADING_NUMBER_RE = re.compile(
    r"^\s*(?:"
    r"第\s*[0-9０-９一二三四五六七八九十百]+\s*[步阶段部分章节条款]"  # 第1步 / 第三节
    r"|[0-9０-９]+[\.、\)）]"                                        # 1. / 1、 / 1)
    r"|[（(][0-9０-９]+[）)]"                                        # (1)
    r"|[一二三四五六七八九十]+[、\.]"                                # 一、
    r")\s*"
)
# Conversation / provenance must never leak into the document: the doc does not
# record who asked the question or that the author was told something.
CONVERSATION_LEAK_RE = re.compile(
    r"(?:"
    r"老板(?:[和跟与](?:同事|同学))?(?:问|说|要求|让|提|催|反馈|问的是)"
    r"|(?:同事|同学|领导|评审|对方|他们)(?:问|说|要求|让|提|催|反馈)"
    r"|你(?:问|说|要求|让|提|催|反馈|不是|可以|觉得|希望|不是让|之前|刚才)"
    r"|我跟他说|我和他说|我和你说|跟你说过|前面说过|上次说"
    r"|(?:这个|那个)(?:是)?你(?:让|要|说|提)"
    r")"
)
# Mobile / email; name+title anchored on a common surname so a preceding verb is not
# swallowed, and role words 老板/同事/同学/领导 are never treated as personal data.
_SURNAME = ("赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜戚谢邹喻柏水窦章云苏潘葛"
            "奚范彭郎鲁韦昌马苗凤花方俞任袁柳酆鲍史唐费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅皮卞齐康")
PERSONAL_INFO_RE = re.compile(
    r"(?:"
    r"1[3-9]\d{9}"                              # mobile
    rf"|[{_SURNAME}][一-龥]{{1,2}}(?:老师|先生|女士)"  # real name + title
    r"|[\w.+-]+@[\w-]+(?:\.[\w-]+)+"            # email
    r")"
)
FIRST_SCREEN_DECISION_RE = re.compile(
    r"(?m)^>\s*\*\*(?:结论|建议|决定)：\*\*\s*\S+"
)
FIRST_SCREEN_ACTION_RE = re.compile(
    r"(?m)^>\s*\*\*(?:读者动作|评审请决定|请确认)：\*\*\s*\S+"
)
ORIENTATION_THESIS_RE = re.compile(
    r"(?m)^>\s*\*\*(?:方案主张|核心主张|结论|建议|决定)：\*\*\s*\S+"
)
ORIENTATION_SCOPE_RE = re.compile(
    r"(?m)^>\s*\*\*(?:当前范围|适用范围|边界)：\*\*\s*\S+"
)
GENERIC_HEADINGS = {
    "背景",
    "现状",
    "当前情况",
    "方案",
    "方案设计",
    "技术方案",
    "实现方案",
    "详细设计",
    "详细说明",
    "流程",
    "汇合",
    "风险",
    "风险分析",
    "总结",
    "其他",
    "后续计划",
}
LOW_SCENT_HEADING_RE = re.compile(
    r"^(?:当前)?(?:事实|情况|现状)$"
    r"|^(?:上线|发布)(?:顺序|流程)$"
    r"|^验收(?:和|与)(?:回退|回滚)$"
    r"|^评审(?:需要)?拍板$"
    r"|^实施工作包$"
    r"|^关联物料$"
    r"|^[一二三四五六七八九十\d]+条线(?:.*)?$"
    r"|^.+汇合$"
)
SUPPORTED_SCHEMA_VERSIONS = {1, 2, 3}


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


def strip_nonprose(text: str) -> str:
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)


def first_screen_text(document_text: str) -> str:
    prose = strip_nonprose(document_text)
    match = re.search(r"(?m)^##\s+", prose)
    return prose[: match.start()] if match else prose


def text_units(text: str) -> float:
    return sum(
        1 if unicodedata.east_asian_width(char) in "WF" else 0.55
        for char in text
    )


def _heading_reads_like_sentence(text: str) -> bool:
    """A heading should be a short topic word, not a clause. Heuristics for prose:

    - ends with a question-word clause (是什么 / 为什么 / 如何 / 怎么办 …)
    - contains a relation that turns the phrase into a statement
      (从…到… / A 和 B 的 … / …怎么对照验收)
    - is long enough to be a clause (>= 12 CJK units) AND contains a verb
    Short keyword headings like 「聚合校验」「发布与回退」「数据采集」pass.
    """
    t = text.strip(" ：:、. ")
    if not t:
        return False
    units = text_units(t)
    if any(t.endswith(term) for term in SENTENCE_HEADING_TERMINATORS):
        return True
    # "A 到 B" journey / "A 和 B 的 C" / "怎么 X" reads as a sentence
    if re.search(r"从[^，。]{1,12}到", t) and units >= 8:
        return True
    if re.search(r"(?:怎么|怎样|如何|为什么)", t):
        return True
    if re.search(r"的[^，。]{1,10}(?:对照|对比|验收|链路|旅程|关系|区别)", t):
        return True
    # long heading carrying a verb is a clause; keywords stay short
    if units >= 12 and SENTENCE_HEADING_RE.search(t):
        return True
    return False


def readability_audit(
    document_text: str,
    record: dict[str, Any] | None = None,
) -> dict[str, Any]:
    prose = strip_nonprose(document_text)
    headings = [
        {"level": len(marker), "text": title.strip()}
        for marker, title in HEADING_RE.findall(prose)
    ]
    generic = [
        item["text"]
        for item in headings
        if item["level"] <= 2
        and (
            item["text"].strip(" ：:") in GENERIC_HEADINGS
            or LOW_SCENT_HEADING_RE.fullmatch(item["text"].strip(" ：:"))
        )
    ]
    long_headings = [
        item["text"]
        for item in headings
        if item["level"] <= 2 and text_units(item["text"]) > 30
    ]
    # Headings are a short topic word (a TOC direction), not a sentence and not a
    # numbered step. Detect across H1..H3; numbering and prose phrasing are flagged.
    numbered_headings, sentence_headings = [], []
    for item in headings:
        if item["level"] > 3:
            continue
        raw = item["text"].strip()
        if HEADING_NUMBER_RE.match(raw):
            numbered_headings.append(raw)
        bare = HEADING_NUMBER_RE.sub("", raw).strip(" ：:、.")
        if _heading_reads_like_sentence(bare):
            sentence_headings.append(raw)
    # Conversation provenance and personal data must not be written into the doc.
    conversation_leaks = sorted({m.group(0) for m in CONVERSATION_LEAK_RE.finditer(prose)})
    personal_leaks = sorted({m.group(0) for m in PERSONAL_INFO_RE.finditer(prose)})
    hierarchy_skips = []
    for previous, current in zip(headings, headings[1:]):
        if current["level"] > previous["level"] + 1:
            hierarchy_skips.append(
                f"{previous['text']} → {current['text']}"
            )

    paragraphs = [
        re.sub(r"\s+", "", paragraph)
        for paragraph in re.split(r"\n\s*\n", prose)
        if len(re.sub(r"\s+", "", paragraph)) >= 24
        and not paragraph.lstrip().startswith(("#", "|", "-", ">"))
    ]
    duplicates = sorted(
        {paragraph for paragraph in paragraphs if paragraphs.count(paragraph) > 1}
    )

    sections = []
    empty_headings = []
    matches = list(HEADING_RE.finditer(prose))
    for index, match in enumerate(matches):
        if len(match.group(1)) != 2:
            continue
        end = matches[index + 1].start() if index + 1 < len(matches) else len(prose)
        section_text = re.sub(r"\s+", "", prose[match.end():end])
        if not section_text:
            empty_headings.append(match.group(2).strip())
        sections.append(
            {"heading": match.group(2).strip(), "characters": len(section_text)}
        )

    first = first_screen_text(document_text)
    appendix = re.search(r"(?m)^##\s+附录(?:：|:)", prose)
    main_end = appendix.start() if appendix else len(prose)
    result = {
        "first_screen": {
            "characters": len(re.sub(r"\s+", "", first)),
            "has_decision": bool(FIRST_SCREEN_DECISION_RE.search(first)),
            "has_reader_action": bool(FIRST_SCREEN_ACTION_RE.search(first)),
        },
        "orientation": {
            "characters": len(re.sub(r"\s+", "", first)),
            "has_thesis": bool(ORIENTATION_THESIS_RE.search(first)),
            "has_scope": bool(ORIENTATION_SCOPE_RE.search(first)),
            "has_reader_action": bool(FIRST_SCREEN_ACTION_RE.search(first)),
        },
        "headings": headings,
        "generic_headings": generic,
        "long_headings": long_headings,
        "numbered_headings": numbered_headings,
        "sentence_headings": sentence_headings,
        "conversation_leaks": conversation_leaks,
        "personal_leaks": personal_leaks,
        "hierarchy_skips": hierarchy_skips,
        "empty_headings": empty_headings,
        "duplicate_paragraphs": duplicates,
        "main_characters": len(re.sub(r"\s+", "", prose[:main_end])),
        "detail_characters": len(re.sub(r"\s+", "", prose[main_end:])),
        "sections": sections,
    }
    if record and record.get("schema_version") == 3:
        overview = as_dict(as_dict(record.get("reading")).get("overview"))
        heading = overview.get("heading")
        heading_positions = {
            item["text"]: index for index, item in enumerate(headings)
        }
        result["overview"] = {
            "required": overview.get("required"),
            "heading": heading,
            "found": bool(heading and heading in heading_positions),
            "heading_index": heading_positions.get(heading),
            "nodes": len(as_list(overview.get("nodes"))),
        }
    return result


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


def validate_reading_contract(
    report: ValidationReport,
    record: dict[str, Any],
    document_text: str,
    target: str,
) -> None:
    schema_version = record.get("schema_version")
    if schema_version == 1:
        report.warn("schema v1 未启用第一屏、阅读地图和分层读者测试")
        return
    if schema_version == 3:
        validate_reading_tree(report, record, document_text, target)
        return
    if schema_version != 2:
        return

    reading = as_dict(record.get("reading"))
    first_screen = as_dict(reading.get("first_screen"))
    if target not in {"draft", "revalidation", "rejected", "superseded"}:
        for field_name, label in (
            ("decision", "第一屏一句话决定"),
            ("why_now", "为什么现在做"),
            ("boundary", "当前版本边界"),
            ("reader_actions", "读者动作"),
        ):
            if not is_filled(first_screen.get(field_name)):
                report.error(f"{label}不能为空（reading.first_screen.{field_name}）")

        section_map = as_list(reading.get("section_map"))
        if not section_map:
            report.error("新版正式文档必须提供 section_map")
        document_headings = {
            item["text"] for item in readability_audit(document_text)["headings"]
        }
        for index, section in enumerate(section_map):
            prefix = f"reading.section_map[{index}]"
            if not isinstance(section, dict):
                report.error(f"{prefix} 必须是对象")
                continue
            for key in ("heading", "point", "layer"):
                if not is_filled(section.get(key)):
                    report.error(f"{prefix}.{key} 不能为空")
            if section.get("layer") not in {"main", "detail"}:
                report.error(f"{prefix}.layer 必须是 main 或 detail")
            heading = section.get("heading")
            if is_filled(heading) and heading not in document_headings:
                report.error(f"{prefix}.heading 未出现在 Markdown 标题中：{heading}")

        for index, part in enumerate(as_list(reading.get("named_parts"))):
            prefix = f"reading.named_parts[{index}]"
            if not isinstance(part, dict):
                report.error(f"{prefix} 必须是对象")
                continue
            if not is_filled(part.get("name")):
                report.error(f"{prefix}.name 不能为空")
            if not is_filled(part.get("responsibility")):
                report.error(f"{prefix}.responsibility 不能为空")

        audit = readability_audit(document_text)
        if not audit["first_screen"]["has_decision"]:
            report.error("第一屏缺少“结论／建议／决定”高亮")
        if not audit["first_screen"]["has_reader_action"]:
            report.error("第一屏缺少“读者动作／评审请决定／请确认”高亮")
        if audit["generic_headings"]:
            report.error(
                "标题信息不足："
                + "、".join(audit["generic_headings"])
            )
        if audit["hierarchy_skips"]:
            report.error(
                "标题层级跳跃："
                + "、".join(audit["hierarchy_skips"])
            )
        if audit["empty_headings"]:
            report.error(
                "标题后缺少承上启下的首段："
                + "、".join(audit["empty_headings"])
            )
        if audit["duplicate_paragraphs"]:
            report.warn(
                f"正文存在 {len(audit['duplicate_paragraphs'])} 段完全重复内容"
            )


def validate_reading_tree(
    report: ValidationReport,
    record: dict[str, Any],
    document_text: str,
    target: str,
) -> None:
    if target in {"draft", "revalidation", "rejected", "superseded"}:
        return
    reading = as_dict(record.get("reading"))
    orientation = as_dict(reading.get("orientation"))
    overview = as_dict(reading.get("overview"))
    chapters = as_list(reading.get("chapters"))
    audit = readability_audit(document_text, record)

    for field_name, label in (
        ("thesis", "顶层主张"),
        ("why_now", "为什么现在做"),
        ("scope", "当前范围"),
        ("reader_actions", "读者动作"),
    ):
        if not is_filled(orientation.get(field_name)):
            report.error(f"{label}不能为空（reading.orientation.{field_name}）")

    if not audit["orientation"]["has_thesis"]:
        report.error("开场缺少“方案主张／核心主张／结论”高亮")
    if not audit["orientation"]["has_scope"]:
        report.error("开场缺少“当前范围／适用范围／边界”高亮")

    required = overview.get("required")
    if not isinstance(required, bool):
        report.error("reading.overview.required 必须是布尔值")
        required = False
    for field_name, label in (
        ("summary", "总体模型摘要"),
        ("format", "总体模型格式"),
    ):
        if not is_filled(overview.get(field_name)):
            report.error(f"{label}不能为空（reading.overview.{field_name}）")
    if overview.get("format") not in {"diagram", "table", "list", "prose"}:
        report.error("reading.overview.format 必须是 diagram、table、list 或 prose")

    if required:
        if not is_filled(overview.get("heading")):
            report.error("正式方案必须指定总体模型章节")
        nodes = as_list(overview.get("nodes"))
        if not nodes:
            report.error("正式方案的总体模型必须包含节点")
        if overview.get("format") == "diagram" and not is_filled(
            overview.get("source_ref")
        ):
            report.error("图示总览必须提供可编辑 source_ref")
        if (
            get_path(record, "document.type") == "technical-design"
            and len(nodes) > 1
            and overview.get("format") == "prose"
        ):
            report.error("多节点技术设计不能只用连续文字作为总体模型")
    else:
        nodes = as_list(overview.get("nodes"))
        if not is_filled(overview.get("exemption_reason")):
            report.error("省略独立总体模型时必须填写 exemption_reason")

    node_ids: set[str] = set()
    node_ids_ordered: list[str] = []
    node_chapters: list[str] = []
    for index, node in enumerate(nodes):
        prefix = f"reading.overview.nodes[{index}]"
        if not isinstance(node, dict):
            report.error(f"{prefix} 必须是对象")
            continue
        for key in ("id", "name", "responsibility", "relation", "chapter"):
            if not is_filled(node.get(key)):
                report.error(f"{prefix}.{key} 不能为空")
        node_id = node.get("id")
        if is_filled(node_id):
            if node_id in node_ids:
                report.error(f"总体模型节点 id 重复：{node_id}")
            node_ids.add(node_id)
            node_ids_ordered.append(node_id)
        if is_filled(node.get("chapter")):
            node_chapters.append(node["chapter"])

    chapter_ids: set[str] = set()
    chapter_by_id: dict[str, dict[str, Any]] = {}
    valid_roles = {"orientation", "core", "crosscutting", "detail", "appendix"}
    for index, chapter in enumerate(chapters):
        prefix = f"reading.chapters[{index}]"
        if not isinstance(chapter, dict):
            report.error(f"{prefix} 必须是对象")
            continue
        for key in ("id", "parent", "heading", "summary", "role", "level"):
            if not is_filled(chapter.get(key)):
                report.error(f"{prefix}.{key} 不能为空")
        chapter_id = chapter.get("id")
        if is_filled(chapter_id):
            if chapter_id in chapter_ids:
                report.error(f"章节 id 重复：{chapter_id}")
            chapter_ids.add(chapter_id)
            chapter_by_id[chapter_id] = chapter
        if chapter.get("role") not in valid_roles:
            report.error(f"{prefix}.role 非法：{chapter.get('role')!r}")
        if chapter.get("level") not in {2, 3}:
            report.error(f"{prefix}.level 必须是 2 或 3")
    for chapter_id, chapter in chapter_by_id.items():
        parent = chapter.get("parent")
        if parent != "overview" and parent not in chapter_ids:
            report.error(f"章节 {chapter_id} 的 parent 不存在：{parent}")
        if chapter.get("role") == "crosscutting":
            supports = as_list(chapter.get("supports"))
            if not supports:
                report.error(f"横切章节 {chapter_id} 必须声明 supports")
            unknown = sorted(set(supports) - node_ids)
            if unknown:
                report.error(
                    f"横切章节 {chapter_id} 引用了未知节点：{'、'.join(unknown)}"
                )
        if parent in chapter_by_id:
            parent_level = chapter_by_id[parent].get("level")
            if isinstance(parent_level, int) and chapter.get("level") != parent_level + 1:
                report.error(
                    f"章节 {chapter_id} 的 level 与 parent 不一致"
                )
        seen = {chapter_id}
        cursor = parent
        while cursor in chapter_by_id:
            if cursor in seen:
                report.error(f"章节树存在环：{chapter_id}")
                break
            seen.add(cursor)
            cursor = chapter_by_id[cursor].get("parent")

    if required:
        for node_id in node_ids_ordered:
            chapter = chapter_by_id.get(node_id)
            if not chapter or chapter.get("role") != "core":
                report.error(f"总体节点 {node_id} 必须映射同 id 的 core 章节")
            node = next(
                (
                    item for item in nodes
                    if isinstance(item, dict) and item.get("id") == node_id
                ),
                {},
            )
            if node.get("chapter") != node_id:
                report.error(f"总体节点 {node_id} 的 chapter 必须引用同 id 章节")
            if chapter and node.get("name") != chapter.get("heading"):
                report.error(f"总体节点 {node_id} 的名称必须与主章节标题一致")
        orphan_core = sorted(
            chapter_id
            for chapter_id, chapter in chapter_by_id.items()
            if chapter.get("role") == "core" and chapter_id not in node_ids
        )
        if orphan_core:
            report.error("存在不属于总体模型的核心章节：" + "、".join(orphan_core))
        if len(node_chapters) != len(set(node_chapters)):
            report.error("多个总体节点不能映射到同一个主章节")

    heading_levels = {
        item["text"]: item["level"] for item in audit["headings"]
    }
    overview_heading = overview.get("heading")
    expected_h2 = {
        chapter["heading"]
        for chapter in chapters
        if isinstance(chapter, dict) and chapter.get("level") == 2
    }
    if required and is_filled(overview_heading):
        expected_h2.add(overview_heading)
    actual_h2 = {
        item["text"] for item in audit["headings"] if item["level"] == 2
    }
    missing = sorted(expected_h2 - actual_h2)
    extra = sorted(actual_h2 - expected_h2)
    if missing:
        report.error("结构树章节未出现在 Markdown：" + "、".join(missing))
    if extra:
        report.error("Markdown 存在未登记的主章节：" + "、".join(extra))
    for chapter in chapters:
        if not isinstance(chapter, dict) or not is_filled(chapter.get("heading")):
            continue
        level = heading_levels.get(chapter["heading"])
        if level and level != chapter.get("level"):
            report.error(
                f"章节层级不一致：{chapter['heading']} 应为 H{chapter.get('level')}"
            )

    if required and overview_heading in heading_levels:
        overview_index = next(
            index for index, item in enumerate(audit["headings"])
            if item["text"] == overview_heading
        )
        core_indices = [
            next(
                index for index, item in enumerate(audit["headings"])
                if item["text"] == chapter["heading"]
            )
            for chapter in chapters
            if isinstance(chapter, dict)
            and chapter.get("role") == "core"
            and chapter.get("heading") in heading_levels
        ]
        if any(index < overview_index for index in core_indices):
            report.error("总体模型必须出现在任何核心节点细节之前")
        node_order = [
            next(
                index for index, item in enumerate(audit["headings"])
                if item["text"] == chapter_by_id[node_id]["heading"]
            )
            for node_id in node_ids_ordered
            if node_id in chapter_by_id
            and chapter_by_id[node_id].get("heading") in heading_levels
        ]
        if node_order != sorted(node_order):
            report.error("核心章节顺序必须与总体模型节点顺序一致")
        prose = strip_nonprose(document_text)
        overview_match = re.search(
            rf"(?m)^##\s+{re.escape(overview_heading)}\s*$",
            prose,
        )
        if overview_match:
            next_h2 = re.search(r"(?m)^##\s+", prose[overview_match.end():])
            overview_end = (
                overview_match.end() + next_h2.start()
                if next_h2
                else len(prose)
            )
            overview_body = prose[overview_match.end():overview_end]
            missing_names = [
                node.get("name")
                for node in nodes
                if isinstance(node, dict)
                and is_filled(node.get("name"))
                and node["name"] not in overview_body
            ]
            if missing_names:
                report.error(
                    "总体模型正文未展示节点："
                    + "、".join(missing_names)
                )

    if audit["generic_headings"]:
        report.error("H1/H2 标题信息不足：" + "、".join(audit["generic_headings"]))
    if audit["hierarchy_skips"]:
        report.error("标题层级跳跃：" + "、".join(audit["hierarchy_skips"]))
    if audit["empty_headings"]:
        report.error(
            "H2 后缺少概括下层的黑盒摘要："
            + "、".join(audit["empty_headings"])
        )
    if audit["long_headings"]:
        report.error(
            "H1/H2 过长，请把完整结论移到章首摘要："
            + "、".join(audit["long_headings"])
        )
    if audit.get("numbered_headings"):
        report.error(
            "标题不要编号（不写“第 N 步/1./一、”），标题是短关键词、由目录顺序表达先后："
            + "、".join(audit["numbered_headings"])
        )
    if audit.get("sentence_headings"):
        report.error(
            "标题要写成短关键词/方向，不要写成一句话或把作用域、结论塞进标题（结论放正文）："
            + "、".join(audit["sentence_headings"])
        )
    if audit.get("conversation_leaks"):
        report.error(
            "技术文档不要写入对话来源或提问者（如“老板/同事问”“你让我”），直接陈述事实与结论："
            + "、".join(audit["conversation_leaks"][:6])
        )
    if audit.get("personal_leaks"):
        report.error(
            "技术文档出现手机号/邮箱/姓名称谓等个人信息，须删除或脱敏："
            + "、".join(audit["personal_leaks"][:6])
        )
    if audit["duplicate_paragraphs"]:
        report.warn(f"正文存在 {len(audit['duplicate_paragraphs'])} 段完全重复内容")


def validate_reader_test(
    report: ValidationReport,
    record: dict[str, Any],
    target: str,
) -> None:
    review_targets = {"in_review", "decided", "implementable", "implemented"}
    if target not in review_targets:
        return
    reader_test = as_dict(record.get("reader_test"))
    if record.get("schema_version") == 2:
        for layer, fields in (
            (
                "first_screen",
                ("decision", "why_now", "boundary", "named_parts", "reader_action"),
            ),
            ("mainline", ("story", "detail_routes")),
        ):
            layer_test = as_dict(reader_test.get(layer))
            if layer_test.get("answers_locked") is not True:
                report.error(f"reader_test.{layer} 必须先锁定标准答案")
            answers = as_dict(layer_test.get("answers"))
            for field_name in fields:
                if not is_filled(answers.get(field_name)):
                    report.error(
                        f"reader_test.{layer}.answers.{field_name} 不能为空"
                    )
            if layer_test.get("completed") is not True:
                report.error(f"reader_test.{layer} 尚未完成")
            if layer_test.get("result") != "pass":
                report.error(f"reader_test.{layer} 结果必须为 pass")
    if record.get("schema_version") == 3:
        for layer, fields in (
            (
                "overview",
                ("problem", "top_nodes", "relations", "expanded_nodes", "reader_action"),
            ),
            (
                "outline",
                ("story", "node_mapping", "crosscutting", "detail_routes"),
            ),
            (
                "drilldown",
                ("responsibility", "boundary", "children", "detail_routes"),
            ),
        ):
            layer_test = as_dict(reader_test.get(layer))
            if layer_test.get("answers_locked") is not True:
                report.error(f"reader_test.{layer} 必须先锁定标准答案")
            if layer == "drilldown" and not is_filled(layer_test.get("sample_node")):
                report.error("reader_test.drilldown.sample_node 不能为空")
            answers = as_dict(layer_test.get("answers"))
            for field_name in fields:
                if not is_filled(answers.get(field_name)):
                    report.error(
                        f"reader_test.{layer}.answers.{field_name} 不能为空"
                    )
            if layer_test.get("completed") is not True:
                report.error(f"reader_test.{layer} 尚未完成")
            if layer_test.get("result") != "pass":
                report.error(f"reader_test.{layer} 结果必须为 pass")
    if target not in {"implementable", "implemented"}:
        return
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
    if record.get("schema_version") not in SUPPORTED_SCHEMA_VERSIONS:
        report.error("schema_version 必须为 1、2 或 3")

    required_keys = [
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
    ]
    if record.get("schema_version") in {2, 3}:
        required_keys.append("reading")
    for key in required_keys:
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
    validate_reading_contract(
        report,
        record,
        document_text,
        effective_target,
    )

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


def readability_command(args: argparse.Namespace) -> int:
    document_path = Path(args.document).expanduser().resolve()
    try:
        document_text = document_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"[失败] 找不到 Markdown：{document_path}", file=sys.stderr)
        return 1

    record = None
    if args.record:
        try:
            record = load_json(Path(args.record).expanduser().resolve())
        except (ValueError, FileNotFoundError) as exc:
            print(f"[失败] {exc}", file=sys.stderr)
            return 1
    audit = readability_audit(document_text, record)
    schema_version = record.get("schema_version") if record else None
    if schema_version == 3:
        structure_report = ValidationReport()
        validate_reading_tree(
            structure_report,
            record,
            document_text,
            "in_review",
        )
        audit["structure_errors"] = structure_report.errors
        audit["structure_warnings"] = structure_report.warnings
        audit["ok"] = not structure_report.errors
    else:
        audit["ok"] = (
            (
                audit["first_screen"]["has_decision"]
                and audit["first_screen"]["has_reader_action"]
            )
            or (
                audit["orientation"]["has_thesis"]
                and audit["orientation"]["has_scope"]
            )
        ) and not audit["generic_headings"] \
            and not audit["hierarchy_skips"] \
            and not audit["empty_headings"]
    if args.json:
        print(json.dumps(audit, ensure_ascii=False, indent=2))
    else:
        first = audit["orientation"]
        print(
            "[开场] "
            f"主张={'有' if first['has_thesis'] else '缺'} · "
            f"范围={'有' if first['has_scope'] else '缺'} · "
            f"非空字符={first['characters']}"
        )
        if "overview" in audit:
            overview = audit["overview"]
            print(
                "[总览] "
                f"章节={'找到' if overview['found'] else '缺失'} · "
                f"节点={overview['nodes']}"
            )
        if audit["generic_headings"]:
            print("[H1/H2] 信息不足：" + "、".join(audit["generic_headings"]))
        if audit["long_headings"]:
            print("[H1/H2] 可能过长：" + "、".join(audit["long_headings"]))
        if audit["hierarchy_skips"]:
            print("[标题] 层级跳跃：" + "、".join(audit["hierarchy_skips"]))
        if audit["empty_headings"]:
            print("[段首] H2 后没有黑盒摘要：" + "、".join(audit["empty_headings"]))
        if audit["duplicate_paragraphs"]:
            print(
                f"[重复] 发现 {len(audit['duplicate_paragraphs'])} 段完全重复内容"
            )
        for error in audit.get("structure_errors", []):
            print("[结构] " + error)
        print("[标题扫描] " + " → ".join(
            item["text"] for item in audit["headings"]
        ))
    return 0 if audit["ok"] else 1


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

    readability_parser = subparsers.add_parser(
        "readability",
        help="检查第一屏、标题层级、重复段落和章节密度",
    )
    readability_parser.add_argument("--document", required=True, help="Markdown 路径")
    readability_parser.add_argument(
        "--record",
        help="可选决策记录；schema v3 时校验总体模型与章节树",
    )
    readability_parser.add_argument(
        "--json",
        action="store_true",
        help="输出 JSON 报告",
    )
    readability_parser.set_defaults(handler=readability_command)

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
