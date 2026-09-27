#!/usr/bin/env python3
"""校验设计阶段契约与 HTML 中的真实语义覆盖。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set


SCHEMA = "design-stage-contract/v1"
BOUNDARY_FIELDS = ("confirmed", "flexible", "deferred", "evidence")
BOUNDARY_ORDER = (
    "requirements",
    "structure",
    "interaction",
    "visualDirection",
    "visualFinal",
    "delivery",
)
COLLECTION_PREFIXES = {
    "requirements": "R",
    "pages": "P",
    "journeys": "J",
    "actions": "A",
    "states": "S",
}
SEMANTIC_ATTRIBUTES = {
    "pages": "data-design-page",
    "journeys": "data-design-journey",
    "actions": "data-design-action",
    "states": "data-design-state",
}
VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


def semantic_tokens(value: Optional[str]) -> Set[str]:
    return set((value or "").split())


class ContractHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.current_variant: Optional[str] = None
        self.current_stage: Optional[str] = None
        self.variant_stack: List[Optional[str]] = []
        self.stage_stack: List[Optional[str]] = []
        self.coverage: Dict[str, Dict[str, Set[str]]] = {}
        self.interactive_actions: Dict[str, Set[str]] = {}
        self.action_results: Dict[str, Dict[str, Set[str]]] = {}
        self.stage_coverage: Dict[str, Dict[str, Set[str]]] = {}
        self.stage_interactive_actions: Dict[str, Set[str]] = {}
        self.stage_action_results: Dict[str, Dict[str, Set[str]]] = {}

    @staticmethod
    def _coverage_for(
        collection: Dict[str, Dict[str, Set[str]]],
        item_id: str,
    ) -> Dict[str, Set[str]]:
        return collection.setdefault(
            item_id,
            {name: set() for name in SEMANTIC_ATTRIBUTES},
        )

    def _collect(
        self,
        item_id: str,
        coverage_collection: Dict[str, Dict[str, Set[str]]],
        interactive_collection: Dict[str, Set[str]],
        result_collection: Dict[str, Dict[str, Set[str]]],
        values: dict,
    ) -> None:
        coverage = self._coverage_for(coverage_collection, item_id)
        for name, attribute in SEMANTIC_ATTRIBUTES.items():
            coverage[name].update(semantic_tokens(values.get(attribute)))

        action_ids = semantic_tokens(values.get("data-design-action"))
        if action_ids and values.get("data-prototype-action"):
            interactive_collection.setdefault(item_id, set()).update(action_ids)
            result_ids = semantic_tokens(values.get("data-design-result"))
            coverage["states"].update(result_ids)
            results = result_collection.setdefault(item_id, {})
            for action_id in action_ids:
                results.setdefault(action_id, set()).update(result_ids)

    def handle_starttag(self, tag: str, attrs) -> None:
        values = dict(attrs)
        if tag not in VOID_TAGS:
            self.variant_stack.append(self.current_variant)
            self.stage_stack.append(self.current_stage)
        if values.get("data-review-artboard") and values.get("data-review-variant"):
            self.current_variant = values["data-review-variant"]
            self._coverage_for(self.coverage, self.current_variant)
            self.interactive_actions.setdefault(self.current_variant, set())
            self.action_results.setdefault(self.current_variant, {})
        if values.get("data-review-artboard") and values.get("data-review-stage"):
            self.current_stage = values["data-review-stage"]
            self._coverage_for(self.stage_coverage, self.current_stage)
            self.stage_interactive_actions.setdefault(self.current_stage, set())
            self.stage_action_results.setdefault(self.current_stage, {})

        if self.current_variant:
            self._collect(
                self.current_variant,
                self.coverage,
                self.interactive_actions,
                self.action_results,
                values,
            )
        if self.current_stage:
            self._collect(
                self.current_stage,
                self.stage_coverage,
                self.stage_interactive_actions,
                self.stage_action_results,
                values,
            )

    def handle_startendtag(self, tag: str, attrs) -> None:
        values = dict(attrs)
        variant_id = values.get("data-review-variant") or self.current_variant
        stage_id = values.get("data-review-stage") or self.current_stage
        if variant_id:
            self._collect(
                variant_id,
                self.coverage,
                self.interactive_actions,
                self.action_results,
                values,
            )
        if stage_id:
            self._collect(
                stage_id,
                self.stage_coverage,
                self.stage_interactive_actions,
                self.stage_action_results,
                values,
            )

    def handle_endtag(self, tag: str) -> None:
        if self.variant_stack:
            self.current_variant = self.variant_stack.pop()
        if self.stage_stack:
            self.current_stage = self.stage_stack.pop()


def load_object(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(f"文件不存在：{path}") from None
    except json.JSONDecodeError as error:
        raise ValueError(f"JSON 无法解析：{path}：{error}") from None
    if not isinstance(value, dict):
        raise ValueError(f"契约必须是 JSON 对象：{path}")
    return value


def index_collection(
    contract: dict,
    name: str,
    errors: List[str],
) -> Dict[str, dict]:
    values = contract.get(name)
    if not isinstance(values, list) or not values:
        errors.append(f"`{name}` 必须是非空数组")
        return {}

    expected_prefix = COLLECTION_PREFIXES[name]
    indexed: Dict[str, dict] = {}
    for position, item in enumerate(values, 1):
        if not isinstance(item, dict):
            errors.append(f"`{name}[{position}]` 必须是对象")
            continue
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id:
            errors.append(f"`{name}[{position}]` 缺少 id")
            continue
        if not re.fullmatch(rf"{expected_prefix}\d{{2,}}", item_id):
            errors.append(f"`{item_id}` 必须使用 {expected_prefix} 加至少两位数字")
        if item_id in indexed:
            errors.append(f"`{name}` 出现重复 id：{item_id}")
        indexed[item_id] = item
    return indexed


def require_references(
    source: dict,
    field: str,
    valid_ids: Set[str],
    label: str,
    errors: List[str],
    allow_empty: bool = False,
) -> Set[str]:
    raw = source.get(field)
    if not isinstance(raw, list) or (not raw and not allow_empty):
        errors.append(f"{label} 的 `{field}` 必须是{'可为空的' if allow_empty else '非空'}数组")
        return set()
    values = {value for value in raw if isinstance(value, str)}
    if len(values) != len(raw):
        errors.append(f"{label} 的 `{field}` 只能包含字符串")
    unknown = values - valid_ids
    if unknown:
        errors.append(f"{label} 的 `{field}` 引用了未知编号：{', '.join(sorted(unknown))}")
    return values


def required_ids(items: Dict[str, dict], phase: str) -> Set[str]:
    flag = "directionRequired" if phase == "direction" else "finalRequired"
    return {
        item_id
        for item_id, item in items.items()
        if item.get(flag, phase == "final")
    }


def coverage_percent(actual: Set[str], required: Set[str]) -> int:
    if not required:
        return 100
    return round(len(actual & required) * 100 / len(required))


def validate(contract: dict, html: str, phase: str) -> dict:
    errors: List[str] = []
    if contract.get("schema") != SCHEMA:
        errors.append(f"`schema` 必须是 `{SCHEMA}`")
    if contract.get("phase") not in ("direction", "final"):
        errors.append("`phase` 必须是 `direction` 或 `final`")

    boundaries = contract.get("stageBoundaries")
    if not isinstance(boundaries, dict):
        errors.append("`stageBoundaries` 必须是对象")
        boundaries = {}
    for boundary_name in BOUNDARY_ORDER:
        boundary = boundaries.get(boundary_name)
        if not isinstance(boundary, dict):
            errors.append(f"缺少阶段边界：{boundary_name}")
            continue
        for field in BOUNDARY_FIELDS:
            if not isinstance(boundary.get(field), list):
                errors.append(f"`stageBoundaries.{boundary_name}.{field}` 必须是数组")

    evidence_boundaries = (
        ("requirements", "structure", "interaction")
        if phase == "direction"
        else ("requirements", "structure", "interaction", "visualDirection")
    )
    for boundary_name in evidence_boundaries:
        evidence = boundaries.get(boundary_name, {}).get("evidence", [])
        if not evidence:
            errors.append(f"`stageBoundaries.{boundary_name}.evidence` 不能为空")

    indexed = {
        name: index_collection(contract, name, errors)
        for name in COLLECTION_PREFIXES
    }

    requirement_ids = set(indexed["requirements"])
    page_ids = set(indexed["pages"])
    journey_ids = set(indexed["journeys"])
    action_ids = set(indexed["actions"])
    state_ids = set(indexed["states"])

    covered_requirements: Set[str] = set()
    for page_id, page in indexed["pages"].items():
        covered_requirements.update(
            require_references(
                page,
                "requirementIds",
                requirement_ids,
                f"页面 {page_id}",
                errors,
            )
        )
    missing_requirements = requirement_ids - covered_requirements
    if missing_requirements:
        errors.append(f"以下需求没有页面承载：{', '.join(sorted(missing_requirements))}")

    for journey_id, journey in indexed["journeys"].items():
        require_references(
            journey,
            "actionIds",
            action_ids,
            f"旅程 {journey_id}",
            errors,
        )

    for action_id, action in indexed["actions"].items():
        for field in ("fromState", "toState"):
            state_id = action.get(field)
            if not isinstance(state_id, str) or state_id not in state_ids:
                errors.append(f"动作 {action_id} 的 `{field}` 必须引用有效状态")

    variants = contract.get("variants")
    if not isinstance(variants, list) or not variants:
        errors.append("`variants` 必须是非空数组")
        variants = []

    variant_index: Dict[str, dict] = {}
    for position, variant in enumerate(variants, 1):
        if not isinstance(variant, dict):
            errors.append(f"`variants[{position}]` 必须是对象")
            continue
        variant_id = variant.get("id")
        if not isinstance(variant_id, str) or not variant_id:
            errors.append(f"`variants[{position}]` 缺少 id")
            continue
        if variant_id in variant_index:
            errors.append(f"`variants` 出现重复 id：{variant_id}")
        variant_index[variant_id] = variant
        require_references(variant, "pageIds", page_ids, f"方案 {variant_id}", errors)
        require_references(variant, "journeyIds", journey_ids, f"方案 {variant_id}", errors)
        require_references(variant, "actionIds", action_ids, f"方案 {variant_id}", errors)
        require_references(variant, "stateIds", state_ids, f"方案 {variant_id}", errors)

    target_variants = {
        variant_id: variant
        for variant_id, variant in variant_index.items()
        if variant.get("phase") == phase
    }
    if phase == "final":
        selected_variant_id = contract.get("selectedVariantId")
        if not isinstance(selected_variant_id, str) or not selected_variant_id:
            errors.append("最终阶段必须设置 `selectedVariantId`")
        elif selected_variant_id not in target_variants:
            errors.append("`selectedVariantId` 必须引用一个 `phase=final` 的方案")
        else:
            target_variants = {selected_variant_id: target_variants[selected_variant_id]}
    elif not target_variants:
        errors.append("方向阶段至少需要一个 `phase=direction` 的方案")

    parser = ContractHTMLParser()
    parser.feed(html)

    interaction_required = {
        "pages": page_ids,
        "journeys": journey_ids,
        "actions": action_ids,
        "states": state_ids,
    }
    interaction_dom = parser.stage_coverage.get(
        "interaction",
        {name: set() for name in SEMANTIC_ATTRIBUTES},
    )
    interaction_report = {"coverage": {}}
    for name in SEMANTIC_ATTRIBUTES:
        missing = interaction_required[name] - interaction_dom[name]
        if missing:
            errors.append(
                f"交互基线未覆盖{name}：{', '.join(sorted(missing))}"
            )
        interaction_report["coverage"][name] = coverage_percent(
            interaction_dom[name],
            interaction_required[name],
        )

    missing_interaction_actions = (
        interaction_required["actions"]
        - parser.stage_interactive_actions.get("interaction", set())
    )
    if missing_interaction_actions:
        errors.append(
            "交互基线动作没有真实 `data-prototype-action`："
            + ", ".join(sorted(missing_interaction_actions))
        )
    for action_id in interaction_required["actions"] - missing_interaction_actions:
        expected_state = indexed["actions"][action_id].get("toState")
        actual_states = parser.stage_action_results.get("interaction", {}).get(
            action_id,
            set(),
        )
        if expected_state not in actual_states:
            errors.append(
                f"交互基线动作 {action_id} 未声明结果状态 {expected_state}"
            )
    interaction_report["interactiveActionCoverage"] = coverage_percent(
        parser.stage_interactive_actions.get("interaction", set()),
        interaction_required["actions"],
    )

    required = {
        "pages": page_ids if phase == "final" else set(),
        "journeys": required_ids(indexed["journeys"], phase),
        "actions": required_ids(indexed["actions"], phase),
        "states": required_ids(indexed["states"], phase),
    }
    variant_reports = []
    for variant_id, variant in target_variants.items():
        dom = parser.coverage.get(
            variant_id,
            {name: set() for name in SEMANTIC_ATTRIBUTES},
        )
        report = {"id": variant_id, "coverage": {}}
        declared = {
            "pages": set(variant.get("pageIds", [])),
            "journeys": set(variant.get("journeyIds", [])),
            "actions": set(variant.get("actionIds", [])),
            "states": set(variant.get("stateIds", [])),
        }
        for name in SEMANTIC_ATTRIBUTES:
            missing_declared = required[name] - declared[name]
            missing_dom = required[name] - dom[name]
            unrendered_declared = declared[name] - dom[name]
            if missing_declared:
                errors.append(
                    f"方案 {variant_id} 未声明必需{name}：{', '.join(sorted(missing_declared))}"
                )
            if missing_dom:
                errors.append(
                    f"方案 {variant_id} 的 HTML 未承载必需{name}：{', '.join(sorted(missing_dom))}"
                )
            if unrendered_declared:
                errors.append(
                    f"方案 {variant_id} 声明但未渲染{name}：{', '.join(sorted(unrendered_declared))}"
                )
            report["coverage"][name] = coverage_percent(dom[name], required[name])

        missing_interactive = required["actions"] - parser.interactive_actions.get(variant_id, set())
        if missing_interactive:
            errors.append(
                f"方案 {variant_id} 的动作没有真实 `data-prototype-action`："
                + ", ".join(sorted(missing_interactive))
            )
        for action_id in required["actions"] - missing_interactive:
            expected_state = indexed["actions"][action_id].get("toState")
            actual_states = parser.action_results.get(variant_id, {}).get(action_id, set())
            if expected_state not in actual_states:
                errors.append(
                    f"方案 {variant_id} 的动作 {action_id} 未声明结果状态 {expected_state}"
                )
        report["interactiveActionCoverage"] = coverage_percent(
            parser.interactive_actions.get(variant_id, set()),
            required["actions"],
        )
        variant_reports.append(report)

    return {
        "schema": SCHEMA,
        "phase": phase,
        "passed": not errors,
        "required": {name: sorted(values) for name, values in required.items()},
        "interactionBaseline": interaction_report,
        "variants": variant_reports,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", required=True, help="index.design.json 路径")
    parser.add_argument("--html", required=True, help="评审工作台 index.html 路径")
    parser.add_argument("--phase", choices=("direction", "final"), required=True)
    parser.add_argument("--json", action="store_true", help="输出完整 JSON 报告")
    parser.add_argument("--report", help="把完整 JSON 报告写入指定路径")
    args = parser.parse_args()

    try:
        contract = load_object(Path(args.contract).expanduser().resolve())
        html = Path(args.html).expanduser().resolve().read_text(encoding="utf-8")
    except (OSError, ValueError) as error:
        print(f"[stage-contract] ERROR {error}", file=sys.stderr)
        return 2

    report = validate(contract, html, args.phase)
    if args.report:
        report_path = Path(args.report).expanduser().resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif report["passed"]:
        print(
            f"[stage-contract] PASS phase={args.phase} "
            f"variants={len(report['variants'])}"
        )
        for variant in report["variants"]:
            coverage = variant["coverage"]
            print(
                f"[stage-contract] {variant['id']} "
                f"journeys={coverage['journeys']}% "
                f"actions={coverage['actions']}% "
                f"states={coverage['states']}% "
                f"interactive={variant['interactiveActionCoverage']}%"
            )
    else:
        print(f"[stage-contract] FAIL phase={args.phase}", file=sys.stderr)
        for error in report["errors"]:
            print(f"- {error}", file=sys.stderr)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
