#!/usr/bin/env python3
"""Portable OPC artifact IO. Python 3.9+, stdlib only; never executes attachments."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import zipfile

SCHEMA = "opc-artifact/v1"
MAX_BYTES = 32 * 1024 * 1024
MAX_FILES = 1000
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
TYPES = {
    "radar": ("radar", ["候选", "证据", "信号强度"]),
    "assess": ("assess", ["机会", "地基层", "潜力层", "综合分", "非共识"]),
    "prd": ("prd", ["问题", "目标人群", "用户旅程", "功能范围", "验收", "平台", "未决"]),
    "plan": ("plan", ["里程碑", "依赖", "验收", "估算"]),
    "design": ("design-spec", ["页面清单", "组件", "Token", "状态", "交互", "prototype"]),
    "technical": ("technical-spec", ["方案", "取舍", "风险", "验证", "回退"]),
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_path(value):
    if not isinstance(value, str) or not value or "\\" in value or "\0" in value:
        raise ValueError("非法相对路径")
    p = PurePosixPath(value)
    if p.is_absolute() or any(x in ("", ".", "..") for x in value.split("/")) or ":" in value:
        raise ValueError("路径必须是包内相对路径：" + value)
    if any(x.startswith(".") for x in p.parts):
        raise ValueError("不接受隐藏文件：" + value)
    return p


def split_document(text):
    text = text.removeprefix("\ufeff").replace("\r\n", "\n")
    # A text-only host may return exactly one fenced artifact, not prose plus blocks.
    fence = re.fullmatch(r"```(?:markdown|md)?\s*\n(.*?)\n```\s*", text, re.S)
    if fence:
        text = fence.group(1) + "\n"
    m = re.match(r"\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)(.*)\Z", text, re.S)
    if not m:
        raise ValueError("缺 front-matter：输出完整 Markdown，顶部必须有 --- 信封")
    fm = {}
    for line in m.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        hit = re.fullmatch(r"([a-z][a-z0-9_]*):[ \t]*(.*)", line)
        if not hit:
            raise ValueError("信封只接受单层标量字段；数组请使用 JSON 单行：" + line)
        key, raw = hit.groups()
        if key in fm:
            raise ValueError("重复信封字段：" + key)
        if raw.startswith('"'):
            decoder = json.JSONDecoder()
            value, end = decoder.raw_decode(raw)
            if raw[end:].strip() and not raw[end:].lstrip().startswith("#"):
                raise ValueError("字段引号后有多余内容：" + key)
        elif raw.startswith("'"):
            match = re.fullmatch(r"'((?:[^']|'')*)'\s*(?:#.*)?", raw)
            if not match:
                raise ValueError("非法引号：" + key)
            value = match.group(1).replace("''", "'")
        else:
            value = re.split(r"\s+#", raw, maxsplit=1)[0].strip()
        fm[key] = str(value)
    return fm, m.group(2), text


def parse_front_matter(text):
    try:
        return split_document(text)[0]
    except ValueError:
        return {}


def kind_of(fm):
    return fm.get("artifact_kind") or fm.get("opc_node")


def validate_envelope(text):
    try:
        fm, body, _ = split_document(text)
    except (ValueError, json.JSONDecodeError) as e:
        return {}, [str(e)]
    errors = []
    for key in ("schema", "opc_node", "opc_version", "topic", "created", "upstream",
                "produced_by", "human_review"):
        if key not in fm or not fm[key]:
            errors.append("缺字段：" + key)
    if fm.get("schema") != SCHEMA:
        errors.append("schema 不支持；本工具只接受 opc-artifact/v1")
    kind = kind_of(fm)
    if kind not in TYPES:
        errors.append("未注册产物类型：" + str(kind))
    if not re.fullmatch(r"[a-z][a-z0-9_-]*", fm.get("opc_node", "")):
        errors.append("opc_node 必须为语义标识")
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][\w.-]+)?", fm.get("opc_version", "")):
        errors.append("opc_version 必须是内容规格版本")
    try:
        when = dt.datetime.fromisoformat(fm.get("created", "").replace("Z", "+00:00"))
        if when.tzinfo is None:
            errors.append("created 必须带时区")
    except ValueError:
        errors.append("created 必须是有效 ISO8601 时间")
    topic = fm.get("topic", "")
    if (topic == "null" and kind != "radar") or (
            topic != "null" and not SLUG.fullmatch(topic)):
        errors.append("topic 必须是小写 slug；仅 radar 允许 null")
    if fm.get("human_review") not in {"pending", "approved", "rejected"}:
        errors.append("human_review 必须是 pending/approved/rejected")
    if fm.get("upstream") not in (None, "null"):
        try:
            safe_path(fm["upstream"])
        except ValueError as e:
            errors.append("upstream：" + str(e))
    if "inputs" in fm:
        try:
            refs = json.loads(fm["inputs"])
            if not isinstance(refs, list) or not all(isinstance(r, str) for r in refs):
                raise ValueError("inputs 必须是路径数组的 JSON 字符串")
            for ref in refs:
                safe_path(ref)
        except (ValueError, TypeError) as e:
            errors.append(str(e))
    if not body.strip():
        errors.append("正文不能为空")
    elif kind in TYPES:
        for section in TYPES[kind][1]:
            if section.lower() not in body.lower():
                errors.append("正文缺少内容：" + section)
    if kind == "radar" and body.strip():
        candidates = re.split(r"(?m)^##\s+候选[：:]", body)[1:]
        if not candidates:
            errors.append("至少需要一个 ## 候选： 条目")
        for candidate in candidates:
            if not re.search(r"evidence:\s*(real|assumption)\b", candidate):
                errors.append("候选需声明 evidence: real|assumption")
            if re.search(r"evidence:\s*real\b", candidate) and not re.search(r"https?://\S+", candidate):
                errors.append("真实候选缺少来源 URL")
    if kind == "assess":
        errors.extend(validate_scorecard(fm, body))
    return fm, errors


def validate_scorecard(fm, body):
    errors, rows = [], []
    for line in body.splitlines():
        if not line.startswith("|"):
            continue
        cols = [c.strip() for c in line.strip("|").split("|")]
        if len(cols) >= 4:
            try:
                score, weight = float(cols[1]), float(cols[2])
            except ValueError:
                continue
            rows.append((cols[0], score, weight, "|".join(cols[3:])))
    try:
        # This registry is generated from the scorer's DIMENSIONS, never maintained twice.
        rules = json.loads(Path(__file__).with_name("scoring-rules.json").read_text())
        expected = dict(rules["dimensions"])
        if len(rows) != len(expected) or {r[0] for r in rows} != set(expected):
            errors.append("评分表必须包含且仅包含十个不同维度")
        for name, score, weight, evidence in rows:
            if not math.isfinite(score) or not 0 <= score <= 10 or weight != expected.get(name):
                errors.append("分数或权重非法：" + name)
            if not evidence or evidence in {"...", "TODO", "待补", "—"}:
                errors.append("维度证据为空或占位：" + name)
        composite = float(fm.get("composite_score", "nan"))
        actual = round(sum(r[1] * r[2] for r in rows) / rules["divisor"], 2)
        if not math.isfinite(composite) or abs(actual - composite) > 0.001:
            errors.append("composite_score 与逐维数据不一致")
        failed = bool(re.search(r"逻辑成立性[：:]\s*(?:FAIL|fail)", body))
        verdict = "reject" if failed else next(v for low, v in rules["tiers"] if composite >= low)
        if fm.get("verdict") != verdict:
            errors.append("verdict 与地基或分数不一致")
        shaped = bool(re.search(r"(?m)^- 申辩[：:]\s*(?!无\s*$)\S+", body)) and "别人没看到的点" in body
        horse = not failed and composite < 6.5 and shaped
        if fm.get("dark_horse") != str(horse).lower():
            errors.append("dark_horse 与分数或申辩不一致")
    except (OSError, ValueError, StopIteration, KeyError) as e:
        errors.append("评分卡缺少可复算字段或包内评分规则：" + str(e))
    return errors


def canonical_name(fm):
    kind, topic = kind_of(fm), fm.get("topic")
    if kind not in TYPES:
        raise ValueError("未知产物类型")
    if kind == "radar" and topic == "null":
        topic = fm["created"][:10]
    if not topic or not SLUG.fullmatch(topic):
        raise ValueError("非法 topic")
    return TYPES[kind][0] + "-" + topic + ".md"


def normalize(text, pending=False):
    fm, body, _ = split_document(text)
    if pending:
        fm["human_review"] = "pending"
    return "---\n" + "\n".join(k + ": " + json.dumps(v, ensure_ascii=False) for k, v in fm.items()) + "\n---\n" + body


def seal(body, node, topic, upstream="null", producer="standalone", kind=None):
    if body.lstrip().startswith("---"):
        raise ValueError("seal 输入应为正文，不能重复封装信封")
    fm = {
        "schema": SCHEMA, "opc_node": node, "artifact_kind": kind or node,
        "opc_version": "0.2.0", "topic": topic,
        "created": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "upstream": upstream, "produced_by": producer, "human_review": "pending",
    }
    return "---\n" + "\n".join(k + ": " + json.dumps(v, ensure_ascii=False) for k, v in fm.items()) + "\n---\n" + body


def checked(text):
    fm, errors = validate_envelope(text)
    if errors:
        raise ValueError("\n".join(errors))
    return fm


def references(fm):
    refs = json.loads(fm.get("inputs", "[]"))
    if fm.get("upstream") not in (None, "", "null"):
        refs.append(fm["upstream"])
    return list(dict.fromkeys(refs))


def package(paths, attachment_dirs=(), scoring_paths=()):
    files, topics = {}, set()
    for path in paths:
        raw = Path(path).read_bytes()
        text = raw.decode("utf-8")
        fm = checked(text)
        if fm["topic"] != "null":
            topics.add(fm["topic"])
        name = canonical_name(fm)
        if name in files:
            raise ValueError("包内存在相同产物；请拆成不同包或 topic")
        files[name] = raw
    if len(topics) > 1:
        raise ValueError("一次交接包只承载一个 topic")
    topic = next(iter(topics), None)
    for path in scoring_paths:
        data = json.loads(Path(path).read_text())
        if data.get("topic") != topic:
            raise ValueError("评分 JSON 的 topic 与包不一致")
        files["_scoring-" + topic + ".json"] = Path(path).read_bytes()
    for directory in attachment_dirs:
        if not topic:
            raise ValueError("附带原型需要 topic")
        directory = Path(directory)
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError("附件必须是普通目录")
        # Explicit --attach is always the prototype root, irrespective of remote dirname.
        for path in sorted(directory.rglob("*")):
            if path.is_symlink():
                raise ValueError("不接受符号链接附件")
            if path.is_file():
                rel = str(path.relative_to(directory)).replace(os.sep, "/")
                safe_path(rel)
                files[topic + "/prototype/" + rel] = path.read_bytes()
    check_files(files)
    return files


def check_files(files):
    if not files or len(files) > MAX_FILES or sum(map(len, files.values())) > MAX_BYTES:
        raise ValueError("交接包为空或超过限制")
    canonical = set()
    topics = set()
    for name, data in files.items():
        path = safe_path(name)
        if any(str(parent) in files for parent in path.parents if str(parent) != "."):
            raise ValueError("文件与目录前缀冲突：" + name)
        if "/" not in name and name.endswith(".md"):
            fm = checked(data.decode("utf-8"))
            if canonical_name(fm) != name:
                raise ValueError("清单文件名与信封不一致")
            canonical.add(name)
            if fm["topic"] != "null":
                topics.add(fm["topic"])
    if not canonical or len(topics) > 1:
        raise ValueError("交接包缺根产物或混入多个 topic")
    for name in files:
        if name in canonical:
            continue
        if name.startswith("_scoring-") and name.endswith(".json") and "/" not in name:
            obj = json.loads(files[name])
            if obj.get("topic") not in topics or name != "_scoring-" + obj["topic"] + ".json":
                raise ValueError("评分 JSON 归属不一致")
            check_scoring_input(obj, files.get("assess-" + obj["topic"] + ".md"))
        elif not any(name.startswith(t + "/prototype/") for t in topics):
            raise ValueError("未声明的附件位置：" + name)


def check_scoring_input(obj, card_data):
    """Independently cross-check the source data against the rendered card."""
    if not card_data:
        raise ValueError("评分 JSON 必须与同 topic 评分卡一起交接")
    fm, body, _ = split_document(card_data.decode())
    rules = json.loads(Path(__file__).with_name("scoring-rules.json").read_text())
    weights = dict(rules["dimensions"])
    dims = obj.get("dimensions")
    if not isinstance(dims, list) or len(dims) != len(weights):
        raise ValueError("评分 JSON 缺少十维数据")
    by_name = {d.get("name"): d for d in dims if isinstance(d, dict)}
    if set(by_name) != set(weights):
        raise ValueError("评分 JSON 维度不完整或重复")
    total = 0
    for name, weight in weights.items():
        row = by_name[name]
        value, evidence = row.get("score"), row.get("evidence")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 10:
            raise ValueError("评分 JSON 分数非法")
        if not isinstance(evidence, str) or not evidence.strip():
            raise ValueError("评分 JSON 证据为空")
        escaped = evidence.strip().replace("|", "&#124;").replace("\n", "<br>")
        # Numeric spelling may vary; compare each parsed row's values and evidence.
        matches = [line.strip().strip("|").split("|") for line in body.splitlines()
                   if line.startswith("|") and line.strip("|").split("|")[0].strip() == name]
        if len(matches) != 1 or float(matches[0][1]) != value or matches[0][3].strip() != escaped:
            raise ValueError("评分 JSON 与卡片逐维内容不一致：" + name)
        total += value * weight
    foundation = obj.get("foundation") or {}
    passed = foundation.get("pass")
    if not isinstance(passed, bool):
        raise ValueError("评分 JSON 地基判定必须是布尔值")
    composite = round(total / rules["divisor"], 2)
    verdict = "reject" if not passed else next(v for low, v in rules["tiers"] if composite >= low)
    rebuttal = obj.get("rebuttal") or {}
    horse = passed and composite < 6.5 and all(
        isinstance(rebuttal.get(k), str) and rebuttal[k].strip() for k in ("claim", "blindspot"))
    if float(fm["composite_score"]) != composite or fm["verdict"] != verdict or fm["dark_horse"] != str(bool(horse)).lower():
        raise ValueError("评分 JSON 与卡片结论不一致")


def zip_bytes(files):
    check_files(files)
    manifest = {
        "schema": "opc-bundle/v1",
        "files": [{"path": name, "sha256": digest(data)} for name, data in sorted(files.items())],
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


def read_bundle(path):
    with zipfile.ZipFile(path) as z:
        infos = z.infolist()
        names = [i.filename for i in infos]
        if len(names) != len(set(names)) or len(names) > MAX_FILES + 1:
            raise ValueError("ZIP 重复条目或文件过多")
        if sum(i.file_size for i in infos) > MAX_BYTES:
            raise ValueError("ZIP 解压体积超过限制")
        for info in infos:
            safe_path(info.filename)
            if stat.S_ISLNK(info.external_attr >> 16) or info.is_dir():
                raise ValueError("只接受普通文件 ZIP")
        manifest = json.loads(z.read("manifest.json"))
        if manifest.get("schema") != "opc-bundle/v1":
            raise ValueError("未知 bundle schema")
        rows = manifest["files"]
        listed = [r["path"] for r in rows]
        if len(listed) != len(set(listed)) or set(listed) != set(names) - {"manifest.json"}:
            raise ValueError("清单与 ZIP 文件不一致")
        files = {}
        for row in rows:
            data = z.read(row["path"])
            if digest(data) != row["sha256"]:
                raise ValueError("摘要不符：" + row["path"])
            files[row["path"]] = data
    check_files(files)
    return files


def destination(root, relative):
    safe_path(relative)
    root = root.resolve()
    target = root / relative
    if root not in target.resolve().parents:
        raise ValueError("目标路径逃逸")
    if any(p.is_symlink() for p in [target, *target.parents] if p != root and root in p.parents):
        raise ValueError("导入目标包含符号链接")
    if any(p.exists() and not p.is_dir() for p in target.parents if p == root or root in p.parents):
        raise ValueError("目标的父路径不是目录")
    if target.exists() and not target.is_file():
        raise ValueError("目标不是普通文件")
    return target


def ingest(files, root, dry_run=False):
    """Save immutable incoming evidence first; all conflicts checked before promotion.

    Incoming approvals are source claims only. New local docs are pending.
    Existing identical source inputs are idempotent, preserving later local review.
    """
    check_files(files)
    root = Path(root).expanduser()
    raw_bundle = zip_bytes(files)
    bundle_id = digest(json.dumps({n: digest(b) for n, b in sorted(files.items())}).encode())
    receipt_dir = root / "_handoffs" / bundle_id
    archive = destination(root, "_handoffs/" + bundle_id + "/source.zip")
    receipt_file = destination(root, "_handoffs/" + bundle_id + "/receipt.json")
    planned, missing = {}, []
    for name, data in files.items():
        local = data
        if "/" not in name and name.endswith(".md"):
            fm = checked(data.decode())
            missing += [ref for ref in references(fm)
                        if ref not in files and not destination(root, ref).exists()]
            local = normalize(data.decode(), pending=True).encode()
        target = destination(root, name)
        if target.exists():
            old = target.read_bytes()
            # Local human_review is allowed to differ; everything else must match.
            same = old == local
            if name.endswith(".md") and "/" not in name:
                try:
                    same = normalize(old.decode(), pending=True).encode() == local
                except ValueError:
                    pass
            if not same:
                raise ValueError("同名内容冲突，未覆盖任何文件：" + name)
        else:
            planned[name] = local
    receipt = {"bundle_id": bundle_id, "status": "pending_review",
               "files": list(files), "missing_inputs": sorted(set(missing)),
               "written": list(planned), "approval": "incoming claims do not authorize local work"}
    if dry_run:
        return {**receipt, "dry_run": True}
    receipt_dir.mkdir(parents=True, exist_ok=True)
    if not archive.exists():
        with archive.open("xb") as f:
            f.write(raw_bundle)
    created = []
    try:
        for name, data in planned.items():
            target = destination(root, name)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as f:
                created.append(target)
                f.write(data)
        # Recheck before writing; evidence leaves cannot redirect the output.
        destination(root, "_handoffs/" + bundle_id + "/receipt.json")
        receipt_file.write_text(json.dumps(receipt, ensure_ascii=False, indent=2))
    except (OSError, ValueError):
        # Only files created by this invocation are removed. Existing user files
        # are never overwritten; the incoming archive remains for recovery.
        for target in reversed(created):
            if not target.is_symlink() and target.is_file():
                target.unlink()
        raise
    return receipt


def main():
    parser = argparse.ArgumentParser(description="Portable OPC handoff; Python 3.9+")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for cmd in ("validate", "ingest"):
        p = sub.add_parser(cmd)
        group = p.add_mutually_exclusive_group(required=True)
        group.add_argument("--input")
        group.add_argument("--stdin", action="store_true")
        if cmd == "ingest":
            p.add_argument("--output-root", help="explicit artifact directory; no iLoop needed")
            p.add_argument("--dry-run", action="store_true")
    p = sub.add_parser("pack")
    p.add_argument("--input", nargs="+", required=True)
    p.add_argument("--attach", action="append", default=[])
    p.add_argument("--scoring", action="append", default=[])
    p.add_argument("--out", required=True)
    p = sub.add_parser("seal")
    p.add_argument("--input", required=True)
    p.add_argument("--node", required=True)
    p.add_argument("--kind")
    p.add_argument("--topic", required=True)
    p.add_argument("--upstream", default="null")
    p.add_argument("--producer", default="standalone")
    p.add_argument("--out", required=True)
    args = parser.parse_args()
    try:
        if args.cmd == "seal":
            text = seal(Path(args.input).read_text(), args.node, args.topic, args.upstream,
                        args.producer, args.kind)
            checked(text)
            Path(args.out).write_text(text, encoding="utf-8")
            print(json.dumps({"output": args.out}))
            return 0
        if args.cmd == "pack":
            files = package(args.input, args.attach, args.scoring)
            Path(args.out).write_bytes(zip_bytes(files))
            print(json.dumps({"output": args.out, "files": list(files)}, ensure_ascii=False))
            return 0
        if args.input and zipfile.is_zipfile(args.input):
            files = read_bundle(args.input)
        else:
            text = sys.stdin.read() if args.stdin else Path(args.input).read_bytes().decode("utf-8")
            fm = checked(text)
            files = {canonical_name(fm): text.encode("utf-8")}
        if args.cmd == "validate":
            print(json.dumps({"status": "valid", "files": list(files),
                              "scope": "structure_and_calculation_only; not approval or evidence truth"}))
            return 0
        root = args.output_root
        if not root:
            data = os.environ.get("ILOOP_DATA_ROOT")
            if not data:
                raise ValueError("需要 --output-root 或 ILOOP_DATA_ROOT")
            root = Path(data) / "analysis" / "opc.product-pipeline"
        print(json.dumps(ingest(files, root, args.dry_run), ensure_ascii=False))
        return 0
    except (ValueError, OSError, KeyError, TypeError, zipfile.BadZipFile) as e:
        print(json.dumps({"status": "rejected", "error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
