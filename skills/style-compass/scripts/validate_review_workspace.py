#!/usr/bin/env python3
"""校验设计罗盘工作台外壳，防止项目改写公共交互。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, List, Set, Tuple


WORKSPACE_LAYOUT = "spatial-studio/v1"
REQUIRED_STAGES = ("structure", "interaction", "visual-final", "delivery")
REQUIRED_LEFT_RESOURCES = ("pages", "states", "assets", "outputs")
REQUIRED_REVIEW_MODES = ("experience", "explain", "comment", "compare")
REQUIRED_ROLES = {
    "stage-list",
    "page-list",
    "context-strip",
    "bottom-dock",
    "comment-list",
    "compare-list",
}
REQUIRED_SIDE_PANELS = {"left", "right"}
REQUIRED_COMMANDS = {
    "left-panel-toggle",
    "right-panel-toggle",
    "stage-confirm",
}


class WorkspaceHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.roles: Set[str] = set()
        self.side_panels: Set[str] = set()
        self.commands: Set[str] = set()
        self.modes: Set[str] = set()
        self.resource_tabs: Set[str] = set()
        self.artboards: Set[str] = set()

    def handle_starttag(self, tag: str, attrs) -> None:
        values = dict(attrs)
        for attribute, target in (
            ("data-role", self.roles),
            ("data-side-panel", self.side_panels),
            ("data-command", self.commands),
            ("data-mode", self.modes),
            ("data-resource-tab", self.resource_tabs),
            ("data-review-artboard", self.artboards),
        ):
            value = values.get(attribute)
            if value:
                target.add(value)


def load_manifest(html: str) -> Dict:
    match = re.search(
        r'<script id="review-manifest" type="application/json">\s*(.*?)\s*</script>',
        html,
        re.S,
    )
    if not match:
        raise ValueError("缺少 review-manifest")
    manifest = json.loads(match.group(1))
    if not isinstance(manifest, dict):
        raise ValueError("review-manifest 必须是 JSON 对象")
    return manifest


def inspect_workspace(path: Path) -> Tuple[Dict, List[str]]:
    html = path.read_text(encoding="utf-8")
    manifest = load_manifest(html)
    parser = WorkspaceHTMLParser()
    parser.feed(html)
    errors: List[str] = []

    workspace = manifest.get("workspace")
    if not isinstance(workspace, dict):
        errors.append("review-manifest 缺少 workspace")
        workspace = {}

    if workspace.get("layout") != WORKSPACE_LAYOUT:
        errors.append(
            f"workspace.layout 必须是 {WORKSPACE_LAYOUT}，实际为 {workspace.get('layout')!r}"
        )
    if tuple(workspace.get("leftResources", [])) != REQUIRED_LEFT_RESOURCES:
        errors.append("workspace.leftResources 必须包含 pages/states/assets/outputs")
    if tuple(workspace.get("reviewModes", [])) != REQUIRED_REVIEW_MODES:
        errors.append("workspace.reviewModes 必须包含 experience/explain/comment/compare")
    if workspace.get("narrowPanelPolicy") != "exclusive":
        errors.append("workspace.narrowPanelPolicy 必须是 exclusive")
    if workspace.get("contextDock") is not True:
        errors.append("workspace.contextDock 必须为 true")

    stage_ids = tuple(
        item.get("id")
        for item in manifest.get("stages", [])
        if isinstance(item, dict)
    )
    if stage_ids != REQUIRED_STAGES:
        errors.append(
            "stages 必须依次为 structure/interaction/visual-final/delivery"
        )

    for label, required, actual in (
        ("data-role", REQUIRED_ROLES, parser.roles),
        ("data-side-panel", REQUIRED_SIDE_PANELS, parser.side_panels),
        ("data-command", REQUIRED_COMMANDS, parser.commands),
        ("data-mode", set(REQUIRED_REVIEW_MODES), parser.modes),
        ("data-resource-tab", set(REQUIRED_LEFT_RESOURCES), parser.resource_tabs),
    ):
        missing = required - actual
        if missing:
            errors.append(f"缺少 {label}：{', '.join(sorted(missing))}")

    declared_artboards = {
        item.get("id")
        for item in manifest.get("artboards", [])
        if isinstance(item, dict) and item.get("id")
    }
    if not declared_artboards:
        errors.append("review-manifest 至少要声明一张 artboard")
    if declared_artboards != parser.artboards:
        missing_dom = declared_artboards - parser.artboards
        missing_manifest = parser.artboards - declared_artboards
        if missing_dom:
            errors.append(
                "设计清单已声明但 HTML 未渲染 artboard："
                + ", ".join(sorted(missing_dom))
            )
        if missing_manifest:
            errors.append(
                "HTML 已渲染但设计清单未声明 artboard："
                + ", ".join(sorted(missing_manifest))
            )

    report = {
        "schema": "design-review-workspace-report/v1",
        "passed": not errors,
        "layout": workspace.get("layout"),
        "stages": list(stage_ids),
        "artboards": len(declared_artboards),
        "errors": errors,
    }
    return report, errors


def validate_workspace(path: Path) -> Dict:
    report, errors = inspect_workspace(path)
    if errors:
        raise ValueError("; ".join(errors))
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("html", help="评审工作台 index.html 路径")
    parser.add_argument("--json", action="store_true", help="输出完整 JSON 报告")
    args = parser.parse_args()

    path = Path(args.html).expanduser().resolve()
    try:
        report, errors = inspect_workspace(path)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"[review-workspace] ERROR {error}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif errors:
        print("[review-workspace] FAIL", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
    else:
        print(
            f"[review-workspace] PASS layout={report['layout']} "
            f"stages={len(report['stages'])} artboards={report['artboards']}"
        )
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
