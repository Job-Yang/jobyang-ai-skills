#!/usr/bin/env python3
"""通过随包 Archify 或有边界的旧模板后端生成与检查工程图。

render 默认按输入 schema 自动选择后端；不会转换 schema，也不会在执行失败后换后端。
浏览器目视验证由调用者使用独立 Playwright 执行，脚本通过不等同视觉验收。
"""
import argparse
import ast
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
BACKEND = SKILL_ROOT / "vendor/archify/bin/archify.mjs"
PIN = SKILL_ROOT / "vendor/archify-version.json"
LEGACY_RENDERER = SCRIPTS / "render_templates.py"
LEGACY_EXTRA = SCRIPTS / "structural_extra.py"
DIAGRAM_CHECK = SCRIPTS / "diagram_check.py"
TYPES = ("architecture", "workflow", "sequence", "dataflow", "lifecycle", "erd",
         "class", "tree", "timeline", "waterfall")
LEGACY_BASE_FIELDS = ("id", "name", "title", "subtitle", "note", "layout")


class BridgeError(ValueError):
    pass


def file_path(value):
    # 保留最终路径的软链接语义，由原子输出保护检查它，不提前 resolve 掩盖别名。
    return Path(value).expanduser().absolute()


def readable(path):
    if not path.is_file():
        raise BridgeError(f"输入文件不存在或不是普通文件：{path}")
    return path


def run_command(command, cwd, timeout=120):
    env = {**os.environ, "ARCHIFY_UPDATE_CHECK_DISABLED": "1"}
    try:
        result = subprocess.run(command, cwd=cwd, env=env, capture_output=True,
                                text=True, encoding="utf-8", timeout=timeout)
    except subprocess.TimeoutExpired as error:
        raise BridgeError(f"后端超时，未确认生成成功：{command[2]}") from error
    try:
        receipt = json.loads(result.stdout)
    except json.JSONDecodeError:
        receipt = None
    return {"exit_code": result.returncode, "receipt": receipt,
            "stdout": result.stdout, "stderr": result.stderr}


def output_guard(path, overwrite, suffixes=(".html",), delivery="Archify"):
    if path.suffix.lower() not in suffixes:
        allowed = "、".join(suffixes)
        raise BridgeError(f"{delivery} 输出格式仅支持 {allowed}。")
    if (path.exists() or path.is_symlink()) and not overwrite:
        raise BridgeError(f"输出已存在；先检查旧图，明确更新时传 --overwrite：{path}")
    if path.is_symlink():
        raise BridgeError("输出是软链接，拒绝覆盖；请使用独立的普通文件路径。")
    if path.exists() and not path.is_file():
        raise BridgeError(f"输出不是普通文件，拒绝覆盖：{path}")
    path.parent.mkdir(parents=True, exist_ok=True)


def reject_remote_brands(path):
    if path.suffix.lower() != ".json":
        return
    data = load_json(path)
    for collection in ("components", "nodes", "participants", "states", "entities"):
        for item in data.get(collection, []) if isinstance(data, dict) else []:
            if isinstance(item, dict) and isinstance(item.get("brand"), dict):
                raise BridgeError("默认桥接不抓取远程品牌图片；请用随包品牌名或移除 brand 对象。")


def load_json(path):
    try:
        data = json.loads(readable(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise BridgeError(f"JSON 输入无法解析：{path}") from error
    if not isinstance(data, dict):
        raise BridgeError("图源 JSON 顶层必须是对象。")
    return data


def _assignment_keys(path, name):
    """只解析字面量注册表，不执行旧模块及其可选依赖。"""
    tree = ast.parse(readable(path).read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(isinstance(target, ast.Name) and target.id == name for target in targets):
            continue
        value = node.value
        elements = value.keys if isinstance(value, ast.Dict) else value.elts if isinstance(value, (ast.Set, ast.List, ast.Tuple)) else None
        if elements is None or not all(isinstance(item, ast.Constant) and isinstance(item.value, str) for item in elements):
            raise BridgeError(f"旧注册表 {name} 不是可静态读取的字符串字面量。")
        return tuple(item.value for item in elements)
    raise BridgeError(f"旧注册表缺少 {name}：{path}")


def legacy_registry():
    structural = _assignment_keys(LEGACY_RENDERER, "STRUCTURAL")
    quantitative = _assignment_keys(LEGACY_RENDERER, "QUANTITATIVE")
    extra = _assignment_keys(LEGACY_EXTRA, "BUILDERS")
    layouts = tuple(dict.fromkeys((*structural, *quantitative, *extra)))
    return {"structural": structural, "quantitative": quantitative,
            "extra_structural": extra, "layouts": layouts}


def capabilities():
    registry = legacy_registry()
    overlap = sorted(set(TYPES) & set(registry["layouts"]))
    return {
        "ok": True,
        "native": {"types": list(TYPES), "output": ["html"], "interactive": True},
        "legacy": {
            "layouts": list(registry["layouts"]),
            "structural": list(registry["structural"]),
            "quantitative": list(registry["quantitative"]),
            "extra_structural": list(registry["extra_structural"]),
            "count": len(registry["layouts"]),
            "output": ["svg", "html"],
            "interactive": False,
        },
        "overlapping_names": overlap,
        "routing": "同名不代表 schema 等价；render 根据 diagram_type/schema_version 或 layout 选择后端，不做字段转换。",
    }


def route_render(args):
    path = readable(file_path(args.input))
    data = load_json(path)
    registry = legacy_registry()
    legacy_types = set(registry["layouts"])
    native_markers = {"diagram_type", "schema_version"} & set(data)
    has_layout = "layout" in data
    # 原生架构、树、ER等也允许layout配置对象；只有字符串才是旧模板图型标记。
    legacy_layout = isinstance(data.get("layout"), str)

    if native_markers and legacy_layout:
        raise BridgeError("输入同时包含原生 schema 标记和旧 layout 字符串，拒绝混合输入。")

    if native_markers:
        if args.backend == "legacy":
            raise BridgeError("--backend legacy 不接受 Archify schema；请提供有效旧 layout 输入。")
        if args.type not in TYPES:
            raise BridgeError(f"原生后端不支持图型：{args.type}")
        declared = data.get("diagram_type")
        if declared is not None and (not isinstance(declared, str) or declared != args.type):
            raise BridgeError(f"--type 与 diagram_type 不匹配：{args.type} != {declared!r}")
        return {"selected": "native", "reason": "native_schema",
                "requested_backend": args.backend, "requested_type": args.type,
                "fallback_reason": None, "input": path, "data": data}

    if has_layout:
        missing = [key for key in LEGACY_BASE_FIELDS
                   if not isinstance(data.get(key), str) or not data[key].strip()]
        if missing:
            raise BridgeError("旧 layout 输入缺少非空字符串字段：" + "、".join(missing))
        layout = data["layout"]
        if layout not in legacy_types:
            raise BridgeError(f"未知旧 layout：{layout}")
        if args.type != layout:
            raise BridgeError(f"--type 与 layout 不匹配：{args.type} != {layout}")
        if args.backend == "native":
            raise BridgeError("--backend native 不接受旧 layout schema；不会丢字段强行转换。")
        if args.backend == "legacy":
            reason, fallback = "explicit_legacy_backend", None
        elif layout in TYPES:
            reason, fallback = "legacy_schema_for_overlapping_name", "input_declares_legacy_layout"
        else:
            reason, fallback = "legacy_only_layout", "native_type_unavailable"
        return {"selected": "legacy", "reason": reason,
                "requested_backend": args.backend, "requested_type": args.type,
                "fallback_reason": fallback, "input": path, "data": data}

    known = sorted(set(TYPES) | legacy_types)
    if args.type not in known:
        raise BridgeError(f"未知图型：{args.type}")
    raise BridgeError("无法识别图源 schema；原生输入需有 diagram_type/schema_version，旧输入需有 layout。")


def build_command(args, node, backend):
    quality = ["--quality", args.quality]
    repo = ["--repo-root", str(file_path(args.repo_root))] if args.repo_root else []
    common = quality + repo + ["--json"]
    if args.operation in ("render", "explain"):
        inp = readable(file_path(args.input))
        reject_remote_brands(inp)
        kind = "explainer" if args.operation == "explain" else args.type
        return [node, str(backend), "deliver", kind, str(inp), str(args.output_path), *common]
    if args.operation == "compare":
        base, head = readable(file_path(args.base)), readable(file_path(args.head))
        reject_remote_brands(base)
        reject_remote_brands(head)
        return [node, str(backend), "compare", "architecture", str(base), str(head),
                str(args.output_path), *common]
    artifact = readable(file_path(args.artifact))
    replacement = readable(file_path(args.replacement))
    return [node, str(backend), "patch", "explainer", str(artifact), args.panel_id,
            str(replacement), str(args.output_path), *common]


def _native_backend_metadata():
    pin = json.loads(PIN.read_text(encoding="utf-8"))
    return {"name": pin["name"], "version": pin["version"], "commit": pin["commit"]}


def execute_native(args, decision=None):
    if not BACKEND.is_file() or not PIN.is_file():
        raise BridgeError("缺少随包 Archify 后端，请重新同步完整 engineering-docs 技能。")
    node = shutil.which("node")
    if not node:
        raise BridgeError("Archify 需要 Node.js 18+；旧后端只接受明确的旧 layout 输入，本次未自动降级。")
    version = subprocess.run([node, "--version"], capture_output=True, text=True, check=True).stdout
    match = re.match(r"v(\d+)\.", version)
    if not match or int(match.group(1)) < 18:
        raise BridgeError("Archify 需要 Node.js 18+，当前版本：" + version.strip())
    args.output_path = file_path(args.output)
    output_guard(args.output_path, args.overwrite)
    command = build_command(args, node, BACKEND)
    generated = run_command(command, args.output_path.parent)
    stages = {"generate": generated}
    route = {key: decision[key] for key in ("selected", "reason", "requested_backend", "requested_type")} if decision else {
        "selected": "native", "reason": "native_only_operation"}
    common = {"backend": _native_backend_metadata(), "route": route,
              "fallback_reason": None, "browser_verified": False}
    if generated["exit_code"] != 0 or not isinstance(generated["receipt"], dict) or generated["receipt"].get("ok") is not True:
        return {"ok": False, "stage": "generate", "stages": stages, **common}, generated["exit_code"] or 1
    if not args.output_path.is_file():
        return {"ok": False, "stage": "generate", "error": "退出码为0但输出不存在",
                "stages": stages, **common}, 1
    # compare 输出的对照页有独立 receipt，不冒用单图 delivery provenance。
    check_args = [node, str(BACKEND), "check", str(args.output_path), "--json"]
    if args.operation != "compare":
        check_args.append("--require-provenance")
    checked = run_command(check_args, args.output_path.parent)
    stages["artifact_check"] = checked
    ok = checked["exit_code"] == 0 and isinstance(checked["receipt"], dict) and checked["receipt"].get("ok") is True
    report = {"ok": ok, "stage": "checked" if ok else "artifact_check",
              "output": str(args.output_path),
              "sha256": hashlib.sha256(args.output_path.read_bytes()).hexdigest(),
              "stages": stages, **common,
              "visual_review": "待调用者用独立 Playwright 实际渲染；未自动启动浏览器。"}
    return report, 0 if ok else 1


def _legacy_backend_metadata():
    return {"name": "legacy-render_templates", "script": str(LEGACY_RENDERER),
            "registry": [str(LEGACY_RENDERER), str(LEGACY_EXTRA)]}


def _legacy_common(decision):
    route = {key: decision[key] for key in ("selected", "reason", "requested_backend", "requested_type")}
    return {"backend": _legacy_backend_metadata(), "route": route,
            "fallback_reason": decision["fallback_reason"], "browser_verified": False,
            "visual_review": "静态旧模板产物；待调用者用独立浏览器实际渲染，不能视为 Archify 交互页。"}


def _stage_error(result, fallback):
    if isinstance(result.get("receipt"), dict) and result["receipt"].get("errors"):
        return fallback + "：" + "；".join(map(str, result["receipt"]["errors"]))
    detail = (result.get("stderr") or result.get("stdout") or "").strip().splitlines()
    return fallback + ("：" + detail[-1] if detail else "")


def _decorate_svg(svg_text, source_text):
    if "<svg" not in svg_text:
        raise BridgeError("旧后端输出不是 SVG。")
    start = svg_text.index("<svg")
    end = svg_text.index(">", start)
    opening = svg_text[start:end]
    opening += ' data-backend="legacy" data-static="true"'
    metadata = '<metadata id="diagram-source" data-format="application/json">' + html.escape(source_text) + "</metadata>"
    return svg_text[:start] + opening + ">" + metadata + svg_text[end + 1:]


def _static_html(svg_text, source_text):
    safe_json = source_text.replace("<", "\\u003c")
    return ("<!doctype html>\n<html lang=\"zh-CN\" data-backend=\"legacy\" data-static=\"true\">\n"
            "<head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            "<meta name=\"archify-interactive\" content=\"false\"><title>Static legacy diagram</title>"
            "<style>html,body{margin:0;background:#fff}main{max-width:1080px;margin:0 auto;padding:24px}svg{width:100%;height:auto}</style></head>\n"
            f"<body><main>{svg_text}</main><script id=\"legacy-source-json\" type=\"application/json\">{safe_json}</script></body></html>\n")


def _commit_staged(staged, output, overwrite):
    output_guard(output, overwrite, (".svg", ".html"), "旧模板")
    if output.exists():
        staged.chmod(output.stat().st_mode & 0o777)
    os.replace(staged, output)


def execute_legacy(args, decision):
    for required in (LEGACY_RENDERER, LEGACY_EXTRA, DIAGRAM_CHECK):
        readable(required)
    args.output_path = file_path(args.output)
    output_guard(args.output_path, args.overwrite, (".svg", ".html"), "旧模板")
    source_path = decision["input"]
    if source_path.resolve() == args.output_path.resolve() or (args.output_path.exists() and os.path.samefile(source_path, args.output_path)):
        raise BridgeError("输入和输出指向同一文件，拒绝覆盖图源。")
    source_bytes = source_path.read_bytes()
    source_text = source_bytes.decode("utf-8")
    if json.loads(source_text) != decision["data"]:
        raise BridgeError("图源在路由后发生变化，请重新生成，不能混用不同版本。")
    common = _legacy_common(decision)
    stages = {}
    with tempfile.TemporaryDirectory(prefix=".archify-legacy-", dir=args.output_path.parent) as td:
        staging = Path(td)
        raw_svg = staging / "rendered.svg"
        frozen_input = staging / "source.json"
        frozen_input.write_bytes(source_bytes)
        command = [sys.executable, "-I", str(LEGACY_RENDERER), "--input", str(frozen_input), "--out", str(raw_svg)]
        generated = run_command(command, source_path.parent)
        stages["generate"] = generated
        if generated["exit_code"] != 0 or not isinstance(generated["receipt"], dict) or not raw_svg.is_file():
            return {"ok": False, "stage": "generate",
                    "error": _stage_error(generated, "旧模板生成失败"),
                    "stages": stages, **common}, generated["exit_code"] or 1

        checked_svg = staging / "checked.svg"
        checked_svg.write_text(_decorate_svg(raw_svg.read_text(encoding="utf-8"), source_text), encoding="utf-8")
        check_command = [sys.executable, "-I", str(DIAGRAM_CHECK), str(checked_svg), "--json"]
        if decision["data"]["layout"] in legacy_registry()["quantitative"]:
            check_command.append("--standard-svg")
        checked = run_command(check_command, source_path.parent)
        stages["artifact_check"] = checked
        check_ok = (checked["exit_code"] == 0 and isinstance(checked["receipt"], dict)
                    and isinstance(checked["receipt"].get("errors"), list)
                    and not checked["receipt"]["errors"]
                    and checked["receipt"].get("ok") is not False)
        if not check_ok:
            return {"ok": False, "stage": "artifact_check",
                    "error": _stage_error(checked, "旧产物检查失败"),
                    "stages": stages, **common}, checked["exit_code"] or 1

        staged_output = staging / ("delivery" + args.output_path.suffix.lower())
        if args.output_path.suffix.lower() == ".svg":
            checked_svg.replace(staged_output)
        else:
            staged_output.write_text(_static_html(checked_svg.read_text(encoding="utf-8"), source_text), encoding="utf-8")
        _commit_staged(staged_output, args.output_path, args.overwrite)

    report = {"ok": True, "stage": "checked", "output": str(args.output_path),
              "source": str(source_path),
              "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
              "sha256": hashlib.sha256(args.output_path.read_bytes()).hexdigest(),
              "stages": stages, **common}
    return report, 0


def execute(args):
    if args.operation == "capabilities":
        return capabilities(), 0
    if args.operation == "render":
        decision = route_render(args)
        if decision["selected"] == "legacy":
            return execute_legacy(args, decision)
        return execute_native(args, decision)
    return execute_native(args)


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="operation", required=True)
    sub.add_parser("capabilities")
    accepted_types = tuple(sorted(set(TYPES) | set(legacy_registry()["layouts"])))
    for op in ("render", "explain", "compare", "patch"):
        cmd = sub.add_parser(op)
        if op in ("render", "explain"):
            cmd.add_argument("--input", required=True)
        if op == "render":
            cmd.add_argument("--type", choices=accepted_types, required=True)
            cmd.add_argument("--backend", choices=("auto", "native", "legacy"), default="auto")
        if op == "compare":
            cmd.add_argument("--base", required=True)
            cmd.add_argument("--head", required=True)
        if op == "patch":
            cmd.add_argument("--artifact", required=True)
            cmd.add_argument("--panel-id", required=True)
            cmd.add_argument("--replacement", required=True)
        cmd.add_argument("--output", required=True)
        cmd.add_argument("--quality", choices=("standard", "showcase"), default="showcase")
        cmd.add_argument("--repo-root")
        cmd.add_argument("--overwrite", action="store_true")
    return p


def main():
    try:
        args = parser().parse_args()
        report, exit_code = execute(args)
    except (BridgeError, OSError, UnicodeError, subprocess.SubprocessError) as error:
        report, exit_code = {"ok": False, "error": str(error), "browser_verified": False}, 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
