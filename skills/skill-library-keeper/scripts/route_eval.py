#!/usr/bin/env python3
"""技能库中立路由活卷盲测与真实翻车回归工具（纯标准库、零环境依赖）。

核心原则：只存考纲（blueprint）与真实翻车池，不固化 AI 凑数的静态考卷；
每次改后须用新随机序 + 全新活卷复验，防止优化演变成刷分背题。

用法：
    python3 route_eval.py blueprint [技能库目录] [--shuffle] [--seed N] [--out-catalog FILE] [--out-blueprint FILE]
    python3 route_eval.py audit <cases.jsonl> [技能库目录] [--strict] [--allow-partial] [--export-blind FILE]
    python3 route_eval.py score <cases.jsonl> <pred1.jsonl> [pred2.jsonl ...] [--root DIR] [--json]
    python3 route_eval.py run <catalog.json> <blind_cases.jsonl> --out <pred.jsonl>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import sys
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import library_doctor as doctor  # noqa: E402

VALID_CATEGORIES = ("positive", "boundary", "negative", "handoff", "real-badcase")
NO_SKILL = "NONE"
NONE_ALIASES = {"", "none", "null", "nil", "n/a", "na", "无", "不适用", "无需技能", "直接回答", "不需要"}

NEGATIVE_ARCHETYPE_POOL = [
    "日常寒暄、致谢或纯闲聊",
    "单句或短段直接中英互译（非长篇精读/去AI味）",
    "一句话可答的通用基础概念/名词解释",
    "仅修改一两处错别字或单句文案的局部微调",
    "简单算术、单位换算或日期查询",
    "明显超出当前技能库任何领域范围的普通请求",
]

ANTI_LEAK_RULES = [
    "严禁在 query 中出现任何英文技能名（slug）或 SKILL.md 等内部文件名",
    "严禁原样照抄目标技能 description 里引号包裹的触发样例短语",
    "严禁在 query 中暴露技能方法论黑话或脚本名，须用真实用户日常口语",
    "boundary 与 negative 类用例严禁填写 acceptable；boundary 须在 forbidden 写明相邻易抢技能",
    "至少一半活题须为 ≤35 字的日常简短口语，避免把技能功能清单逐条复述进题干导致区分度失真",
    "本活卷考完即弃（仅报告诊断），改完技能后必须重新出新卷并换随机序复验",
]


def load_neutral_catalog(root: Path, exclude: set[str] | None = None) -> list[dict]:
    """仅读取技能 frontmatter 的 name 与 description，彻底剥离正文。"""
    excluded = exclude or set()
    skill_mds = sorted(root.glob("*/SKILL.md"))
    if not skill_mds and (root / "SKILL.md").exists():
        skill_mds = [root / "SKILL.md"]

    catalog: list[dict] = []
    for sk_md in skill_mds:
        fm, _body, _err = doctor.parse_frontmatter(doctor.read_text(sk_md))
        name = str(fm.get("name") or sk_md.parent.name).strip()
        if not name or name in excluded:
            continue
        desc = str(fm.get("description") or "").strip()
        catalog.append({"name": name, "description": desc})
    catalog.sort(key=lambda item: item["name"])
    return catalog


def catalog_fingerprint(catalog: list[dict]) -> str:
    """按规范化名称顺序计算中立目录的 12 位 SHA-256 指纹。"""
    canonical = sorted((item["name"], item["description"]) for item in catalog)
    payload = json.dumps(canonical, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def extract_quoted_samples(desc: str) -> list[str]:
    """从 description 中提取引号包裹的触发短语样例。"""
    seen: set[str] = set()
    samples: list[str] = []
    for raw in doctor.SAMPLE_PAT.findall(desc):
        cleaned = raw[1:-1].strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            samples.append(cleaned)
    return samples


def _char_ngrams(text: str, n: int = 2) -> set[str]:
    compact = re.sub(r"[\s，。、：；！？「」『』“”\"'（）()\[\]`.,:/\\-]+", "", text.lower())
    if len(compact) < n:
        return {compact} if compact else set()
    return {compact[i : i + n] for i in range(len(compact) - n + 1)}


def _read_optional_manifest_groups(root: Path) -> list[list[str]]:
    """可选读取仓库 tools/skills-manifest.json 的分组信息；不存在或非法时静默返回空。"""
    manifest_path = root.parent / "tools" / "skills-manifest.json"
    if not manifest_path.is_file():
        return []
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(data, dict) or not isinstance(data.get("groups"), list):
        return []
    groups: list[list[str]] = []
    for g in data["groups"]:
        if isinstance(g, dict) and isinstance(g.get("skills"), list):
            members = [str(s).strip() for s in g["skills"] if isinstance(s, str) and s.strip()]
            if len(members) >= 2:
                groups.append(members)
    return groups


def infer_neighbor_pairs(root: Path, catalog: list[dict], max_pairs: int = 15) -> list[dict]:
    """从 description 互相点名、可选分组配置及文本重合度推断易混淆边界技能对。"""
    if len(catalog) < 2:
        return []
    names = [c["name"] for c in catalog]
    name_set = set(names)
    desc_map = {c["name"]: c["description"] for c in catalog}

    pair_reasons: dict[tuple[str, str], str] = {}

    def register(a: str, b: str, reason: str) -> None:
        if a == b or a not in name_set or b not in name_set:
            return
        key = (a, b) if a < b else (b, a)
        pair_reasons.setdefault(key, reason)

    # 1. 最高优先级：description 中显式点名了另一个技能（边界对比/分流）
    for src in names:
        src_desc = desc_map[src]
        for tgt in names:
            if tgt != src and re.search(rf"(?<![a-z0-9-]){re.escape(tgt)}(?![a-z0-9-])", src_desc):
                register(src, tgt, "description-contrast")

    # 2. 次高优先级：可选 manifest 同组，按 2-gram 重合度排序
    grams = {n: _char_ngrams(desc_map[n]) for n in names}

    def jaccard(a: str, b: str) -> float:
        ga, gb = grams[a], grams[b]
        if not ga or not gb:
            return 0.0
        return len(ga & gb) / len(ga | gb)

    group_candidates: list[tuple[float, str, str]] = []
    for members in _read_optional_manifest_groups(root):
        in_cat = [m for m in members if m in name_set]
        for i, a in enumerate(in_cat):
            for b in in_cat[i + 1 :]:
                group_candidates.append((jaccard(a, b), a, b))
    for _score, a, b in sorted(group_candidates, key=lambda x: (-x[0], x[1], x[2])):
        register(a, b, "same-group")

    # 3. 兜底：全库 description 2-gram 重合度最高者
    overlap_candidates: list[tuple[float, str, str]] = []
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            overlap_candidates.append((jaccard(a, b), a, b))
    for sim, a, b in sorted(overlap_candidates, key=lambda x: (-x[0], x[1], x[2])):
        if len(pair_reasons) >= max_pairs:
            break
        if sim > 0:
            register(a, b, "desc-overlap")

    priority_rank = {"description-contrast": 0, "same-group": 1, "desc-overlap": 2}
    ordered = sorted(
        pair_reasons.items(),
        key=lambda kv: (priority_rank[kv[1]], -jaccard(kv[0][0], kv[0][1]), kv[0][0], kv[0][1]),
    )
    return [{"pair": [a, b], "reason": reason} for (a, b), reason in ordered[:max_pairs]]


def normalize_selection(value: object) -> str:
    """将模型输出的选择归一化为技能名或 NONE。"""
    if value is None:
        return NO_SKILL
    if isinstance(value, list):
        if not value:
            return NO_SKILL
        value = value[0]
    text = str(value).strip().strip("`\"'")
    if text.lower() in NONE_ALIASES:
        return NO_SKILL
    return text


def parse_router_reply(raw_text: str) -> dict:
    """容错解析路由模型返回文本（支持纯 JSON、代码围栏与前后缀混杂文本）。"""
    text = (raw_text or "").strip()
    candidates: list[str] = []

    fence_matches = re.findall(r"```(?:json)?\s*(.*?)```", text, flags=re.S | re.I)
    candidates.extend(fence_matches)
    candidates.append(text)

    for cand in candidates:
        cand = cand.strip()
        if not cand:
            continue
        try:
            obj = json.loads(cand)
            if isinstance(obj, dict) and "selected" in obj:
                return {
                    "selected": normalize_selection(obj.get("selected")),
                    "reason": str(obj.get("reason") or "").strip(),
                    "parse_ok": True,
                }
        except ValueError:
            pass

        decoder = json.JSONDecoder()
        for idx, ch in enumerate(cand):
            if ch != "{":
                continue
            try:
                obj, _end = decoder.raw_decode(cand[idx:])
                if isinstance(obj, dict) and "selected" in obj:
                    return {
                        "selected": normalize_selection(obj.get("selected")),
                        "reason": str(obj.get("reason") or "").strip(),
                        "parse_ok": True,
                    }
            except ValueError:
                continue

    return {"selected": NO_SKILL, "reason": text[:160], "parse_ok": False}


def _resolve_root_or_exit(raw_root: str) -> Path:
    root = doctor.find_library(Path(raw_root))
    if root is None:
        print(
            f"找不到技能库：{Path(raw_root).resolve()} 及其上级均无多个 <name>/SKILL.md",
            file=sys.stderr,
        )
        sys.exit(2)
    return root


def _parse_csv_set(raw: str) -> set[str]:
    return {item.strip() for item in raw.split(",") if item.strip()}


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(row, ensure_ascii=False) for row in rows]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


# ---------------------------------------------------------------- blueprint


def build_blueprint_payload(
    root: Path,
    catalog: list[dict],
    fp: str,
    shuffle: bool,
    seed: int | None,
    max_pairs: int,
    neg_count: int,
    paraphrase_count: int,
    focus: set[str],
) -> tuple[dict, dict]:
    """构建中立目录导出件与抽考蓝图。"""
    cat_names = {c["name"] for c in catalog}
    unknown_focus = sorted(focus - cat_names)
    if unknown_focus:
        print(f"--focus 包含库中不存在的技能：{', '.join(unknown_focus)}", file=sys.stderr)
        sys.exit(2)

    shuffle_seed: int | None = None
    out_skills = list(catalog)
    if shuffle:
        shuffle_seed = seed if seed is not None else random.SystemRandom().randint(1000, 9999999)
        random.Random(shuffle_seed).shuffle(out_skills)

    all_pairs = infer_neighbor_pairs(root, catalog, max_pairs=max(max_pairs * 2, 30))
    if focus:
        filtered_pairs = [p for p in all_pairs if p["pair"][0] in focus or p["pair"][1] in focus][:max_pairs]
        targets = set(focus)
        for p in filtered_pairs:
            targets.update(p["pair"])
        target_skills = sorted(targets)
        neighbor_pairs = filtered_pairs
    else:
        target_skills = [c["name"] for c in catalog]
        neighbor_pairs = all_pairs[:max_pairs]

    rng = random.Random(shuffle_seed if shuffle_seed is not None else (seed if seed is not None else 42))
    para_pool = list(target_skills)
    rng.shuffle(para_pool)
    paraphrase_targets = sorted(para_pool[: min(max(paraphrase_count, 0), len(para_pool))])

    neg_items = [
        NEGATIVE_ARCHETYPE_POOL[i % len(NEGATIVE_ARCHETYPE_POOL)] for i in range(max(neg_count, 0))
    ]

    catalog_payload = {
        "catalog_fingerprint": fp,
        "shuffle_seed": shuffle_seed,
        "skill_count": len(out_skills),
        "skills": out_skills,
    }
    blueprint_payload = {
        "catalog_fingerprint": fp,
        "shuffle_seed": shuffle_seed,
        "skill_count": len(out_skills),
        "target_skills": target_skills,
        "neighbor_pairs": neighbor_pairs,
        "negative_count": len(neg_items),
        "negative_archetypes": neg_items,
        "paraphrase_targets": paraphrase_targets,
        "anti_leak_rules": ANTI_LEAK_RULES,
    }
    return catalog_payload, blueprint_payload


def cmd_blueprint(args: argparse.Namespace) -> int:
    root = _resolve_root_or_exit(args.root)
    exclude = _parse_csv_set(args.exclude)
    focus = _parse_csv_set(args.focus)
    catalog = load_neutral_catalog(root, exclude=exclude)
    if not catalog:
        print(f"技能库为空：{root}", file=sys.stderr)
        return 2
    fp = catalog_fingerprint(catalog)
    catalog_payload, blueprint_payload = build_blueprint_payload(
        root=root,
        catalog=catalog,
        fp=fp,
        shuffle=args.shuffle,
        seed=args.seed,
        max_pairs=args.max_pairs,
        neg_count=args.neg_count,
        paraphrase_count=args.paraphrase_count,
        focus=focus,
    )

    if args.out_catalog:
        _write_json(Path(args.out_catalog), catalog_payload)
    if args.out_blueprint:
        _write_json(Path(args.out_blueprint), blueprint_payload)

    if args.json:
        print(json.dumps({"catalog": catalog_payload, "blueprint": blueprint_payload}, ensure_ascii=False, indent=2))
    else:
        print(f"技能库: {root}（{len(catalog)} 个技能，指纹 {fp}）")
        print(f"乱序种子: {catalog_payload['shuffle_seed'] or '未打乱（字典序）'}")
        print(f"待测技能: {len(blueprint_payload['target_skills'])} 个 | 邻居边界对: {len(blueprint_payload['neighbor_pairs'])} 对")
        print(f"轻任务负例配额: {blueprint_payload['negative_count']} 条 | 同义改写抽样: {', '.join(blueprint_payload['paraphrase_targets']) or '无'}")
        if args.out_catalog:
            print(f"已导出中立目录: {args.out_catalog}")
        if args.out_blueprint:
            print(f"已导出抽考蓝图: {args.out_blueprint}")
    return 0


# ---------------------------------------------------------------- audit


def _validate_str_list(obj: dict, key: str, line_no: int, findings: list[dict], case_id: str) -> list[str]:
    val = obj.get(key)
    if val is None:
        return []
    if not isinstance(val, list) or any(not isinstance(x, str) or not x.strip() for x in val):
        findings.append({
            "sev": "high", "rule": "A001", "case_id": case_id,
            "evidence": f"第 {line_no} 行字段 `{key}` 必须是非空字符串数组",
        })
        return []
    return [x.strip() for x in val]


def audit_cases(cases_path: Path, root: Path, allow_partial: bool = False) -> tuple[list[dict], list[dict]]:
    """校验活卷/翻车病例 JSONL，返回 (parsed_cases, findings)。"""
    findings: list[dict] = []
    catalog = load_neutral_catalog(root)
    known_skills = {c["name"] for c in catalog}
    samples_by_skill = {c["name"]: extract_quoted_samples(c["description"]) for c in catalog}

    parsed_cases: list[dict] = []
    seen_ids: set[str] = set()
    covered_skills: set[str] = set()
    has_negative = False

    lines = cases_path.read_text(encoding="utf-8").splitlines()
    for line_no, raw_ln in enumerate(lines, start=1):
        if not raw_ln.strip():
            continue
        try:
            obj = json.loads(raw_ln)
        except ValueError as exc:
            findings.append({
                "sev": "high", "rule": "A001", "case_id": f"line:{line_no}",
                "evidence": f"第 {line_no} 行 JSON 解析失败：{exc}",
            })
            continue
        if not isinstance(obj, dict):
            findings.append({
                "sev": "high", "rule": "A001", "case_id": f"line:{line_no}",
                "evidence": f"第 {line_no} 行顶层必须是 JSON 对象",
            })
            continue

        missing = [
            k for k in ("id", "category", "query", "expected")
            if not isinstance(obj.get(k), str) or not obj[k].strip()
        ]
        case_id = str(obj.get("id") or f"line:{line_no}").strip()
        if missing:
            findings.append({
                "sev": "high", "rule": "A001", "case_id": case_id,
                "evidence": f"第 {line_no} 行缺少非空必填字段：{', '.join(missing)}",
            })
            continue

        if case_id in seen_ids:
            findings.append({
                "sev": "high", "rule": "A001", "case_id": case_id,
                "evidence": f"第 {line_no} 行存在重复 case id：`{case_id}`",
            })
            continue
        seen_ids.add(case_id)

        category = obj["category"].strip()
        query = obj["query"].strip()
        expected = obj["expected"].strip()

        if category not in VALID_CATEGORIES:
            findings.append({
                "sev": "high", "rule": "A001", "case_id": case_id,
                "evidence": f"非法 category `{category}`（允许：{', '.join(VALID_CATEGORIES)}）",
            })

        forbidden = _validate_str_list(obj, "forbidden", line_no, findings, case_id)
        acceptable = _validate_str_list(obj, "acceptable", line_no, findings, case_id)

        allow_literal = obj.get("allow_literal_slug", False)
        if not isinstance(allow_literal, bool):
            findings.append({
                "sev": "high", "rule": "A001", "case_id": case_id,
                "evidence": "字段 `allow_literal_slug` 必须是布尔值",
            })
            allow_literal = False

        # A002: 库内存在性检查
        if expected != NO_SKILL and expected not in known_skills:
            findings.append({
                "sev": "high", "rule": "A002", "case_id": case_id,
                "evidence": f"expected 指向不存在的技能 `{expected}`",
            })
        for field_name, items in (("forbidden", forbidden), ("acceptable", acceptable)):
            bad = [s for s in items if s != NO_SKILL and s not in known_skills]
            if bad:
                findings.append({
                    "sev": "high", "rule": "A002", "case_id": case_id,
                    "evidence": f"{field_name} 包含不存在的技能：{', '.join(bad)}",
                })

        # A003: 标签自洽性
        if category == "negative" and expected != NO_SKILL:
            findings.append({
                "sev": "high", "rule": "A003", "case_id": case_id,
                "evidence": f"negative 用例的 expected 必须为 `{NO_SKILL}`，实际 `{expected}`",
            })
        if category in ("boundary", "negative") and acceptable:
            findings.append({
                "sev": "high", "rule": "A003", "case_id": case_id,
                "evidence": f"{category} 用例严禁设置 acceptable（防边界和稀泥）",
            })
        if expected in forbidden:
            findings.append({
                "sev": "high", "rule": "A003", "case_id": case_id,
                "evidence": f"expected `{expected}` 同时出现在 forbidden 中",
            })

        # A004: 英文 slug 与内部文件名泄题检查
        if re.search(r"SKILL\.md", query, re.I):
            findings.append({
                "sev": "high", "rule": "A004", "case_id": case_id,
                "evidence": "query 出现 `SKILL.md` 内部术语泄题",
            })
        if expected != NO_SKILL and not (category == "real-badcase" and allow_literal):
            if re.search(rf"(?<![a-z0-9-]){re.escape(expected)}(?![a-z0-9-])", query, re.I):
                findings.append({
                    "sev": "high", "rule": "A004", "case_id": case_id,
                    "evidence": f"query 直接包含目标英文技能名 `{expected}`（测成关键词匹配）",
                })

        # A005: 照抄 description 引号触发样例检查
        if category != "real-badcase" and expected in samples_by_skill:
            q_lower = query.lower()
            copied = [
                smp for smp in samples_by_skill[expected]
                if len(smp.strip()) >= 4 and smp.strip().lower() in q_lower
            ]
            if copied:
                findings.append({
                    "sev": "mid", "rule": "A005", "case_id": case_id,
                    "evidence": f"query 原样照抄 `{expected}` 描述中的触发样例：「{copied[0]}」",
                })

        if expected != NO_SKILL:
            covered_skills.add(expected)
        if category == "negative" and expected == NO_SKILL:
            has_negative = True

        parsed_cases.append({
            "id": case_id,
            "category": category,
            "query": query,
            "expected": expected,
            "forbidden": forbidden,
            "acceptable": [] if category in ("boundary", "negative") else acceptable,
            "paraphrase_group": str(obj.get("paraphrase_group") or "").strip(),
            "source": str(obj.get("source") or "").strip(),
            "note": str(obj.get("note") or "").strip(),
        })

    if not parsed_cases and not findings:
        findings.append({
            "sev": "high", "rule": "A001", "case_id": "file",
            "evidence": "用例文件为空，没有有效用例",
        })

    if not allow_partial:
        uncovered = sorted(known_skills - covered_skills)
        if uncovered:
            findings.append({
                "sev": "mid", "rule": "A006", "case_id": "coverage",
                "evidence": f"库中 {len(uncovered)} 个技能无任何用例覆盖：{', '.join(uncovered)}",
            })
        if not has_negative:
            findings.append({
                "sev": "mid", "rule": "A007", "case_id": "coverage",
                "evidence": "缺少 `negative` 轻任务负例（expected=NONE）",
            })
        probe_lens = sorted(len(c["query"]) for c in parsed_cases if c["category"] != "real-badcase")
        if probe_lens and probe_lens[len(probe_lens) // 2] > 55:
            findings.append({
                "sev": "low", "rule": "A008", "case_id": "query-length",
                "evidence": f"活卷非真翻车题干中位数 {probe_lens[len(probe_lens) // 2]} 字符 > 55，建议掺入 ≤35 字日常短口语避免区分度失真",
            })

    return parsed_cases, findings


def cmd_audit(args: argparse.Namespace) -> int:
    cases_path = Path(args.cases)
    if not cases_path.is_file():
        print(f"用例文件不存在：{cases_path}", file=sys.stderr)
        return 2
    root = _resolve_root_or_exit(args.root)

    parsed_cases, findings = audit_cases(cases_path, root, allow_partial=args.allow_partial)
    fail_sevs = {"high", "mid"} if args.strict else {"high"}
    has_high = any(f["sev"] == "high" for f in findings)

    exported_blind = False
    if args.export_blind:
        if has_high:
            print("存在 high 级阻断错误，跳过导出盲测题单。", file=sys.stderr)
        else:
            blind_rows = [{"id": c["id"], "query": c["query"]} for c in parsed_cases]
            _write_jsonl(Path(args.export_blind), blind_rows)
            exported_blind = True

    if args.json:
        print(json.dumps({
            "cases_file": str(cases_path),
            "root": str(root),
            "case_count": len(parsed_cases),
            "exported_blind": args.export_blind if exported_blind else None,
            "findings": findings,
        }, ensure_ascii=False, indent=2))
    else:
        print(f"审计用例: {cases_path}（{len(parsed_cases)} 条）| 技能库: {root}")
        for f in findings:
            print(f"[{f['sev'].upper():4} {f['rule']}] {f['case_id']} | {f['evidence']}")
        if not findings:
            print("活卷审计通过 ✅（零泄题、标签自洽、覆盖完整）。")
        if exported_blind:
            print(f"已导出严格去标签盲测题单: {args.export_blind}（{len(parsed_cases)} 条）")

    return 1 if any(f["sev"] in fail_sevs for f in findings) else 0


# ---------------------------------------------------------------- score


def _load_cases_for_score(cases_path: Path) -> list[dict]:
    cases: list[dict] = []
    seen: set[str] = set()
    for line_no, raw_ln in enumerate(cases_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw_ln.strip():
            continue
        obj = json.loads(raw_ln)
        if not isinstance(obj, dict):
            raise ValueError(f"第 {line_no} 行不是 JSON 对象")
        cid = str(obj["id"]).strip()
        if cid in seen:
            raise ValueError(f"重复 case id: {cid}")
        seen.add(cid)
        cat = str(obj["category"]).strip()
        acceptable = [] if cat in ("boundary", "negative") else list(obj.get("acceptable") or [])
        cases.append({
            "id": cid,
            "category": cat,
            "query": str(obj["query"]).strip(),
            "expected": str(obj["expected"]).strip(),
            "forbidden": [str(x).strip() for x in (obj.get("forbidden") or [])],
            "acceptable": [str(x).strip() for x in acceptable],
            "paraphrase_group": str(obj.get("paraphrase_group") or "").strip(),
            "note": str(obj.get("note") or "").strip(),
        })
    if not cases:
        raise ValueError("用例文件为空")
    return cases


def _load_predictions(pred_path: Path) -> tuple[dict[str, dict], list[dict]]:
    preds: dict[str, dict] = {}
    malformed: list[dict] = []
    for line_no, raw_ln in enumerate(pred_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw_ln.strip():
            continue
        try:
            obj = json.loads(raw_ln)
        except ValueError as exc:
            malformed.append({"file": str(pred_path), "line": line_no, "error": str(exc)})
            continue
        if not isinstance(obj, dict) or not isinstance(obj.get("id"), str) or not obj["id"].strip():
            malformed.append({"file": str(pred_path), "line": line_no, "error": "缺少有效 id 字段"})
            continue
        cid = obj["id"].strip()
        if "selected" in obj:
            parsed = {
                "selected": normalize_selection(obj.get("selected")),
                "reason": str(obj.get("reason") or "").strip(),
                "parse_ok": True,
            }
        elif isinstance(obj.get("raw"), str):
            parsed = parse_router_reply(obj["raw"])
        else:
            parsed = {"selected": NO_SKILL, "reason": "", "parse_ok": False}
        preds[cid] = parsed
    return preds, malformed


def evaluate_runs(
    cases: list[dict],
    pred_files: list[Path],
    known_skills: set[str] | None = None,
) -> dict:
    """聚合单轮或多轮路由预测，生成无总分体检雷达报告。"""
    k = len(pred_files)
    runs_data: list[dict[str, dict]] = []
    malformed_lines: list[dict] = []
    missing_predictions: list[dict] = []
    hallucinated_skills: list[dict] = []

    case_ids = {c["id"] for c in cases}
    extra_prediction_ids: list[dict] = []

    for pf in pred_files:
        preds, bad = _load_predictions(pf)
        runs_data.append(preds)
        malformed_lines.extend(bad)
        for cid in sorted(set(preds.keys()) - case_ids):
            extra_prediction_ids.append({"file": str(pf), "case_id": cid})

    by_category: dict[str, dict] = {
        cat: {"case_count": 0, "slots": 0, "hits": 0, "misses": 0, "pass_at_k": 0, "pass_pow_k": 0}
        for cat in VALID_CATEGORIES
    }
    misses: list[dict] = []
    confusion_counter: Counter[str] = Counter()
    forbidden_hits: list[dict] = []
    neg_fp_sources: Counter[str] = Counter()
    neg_fp_cases: list[dict] = []
    jitter_cases: list[dict] = []
    real_badcase_results: list[dict] = []

    total_hits = 0
    total_slots = len(cases) * k
    pass_at_k_count = 0
    pass_pow_k_count = 0

    for c in cases:
        cid = c["id"]
        cat = c["category"]
        expected = c["expected"]
        forbidden_set = set(c["forbidden"])
        acceptable_set = set(c["acceptable"])

        cat_bucket = by_category.setdefault(
            cat, {"case_count": 0, "slots": 0, "hits": 0, "misses": 0, "pass_at_k": 0, "pass_pow_k": 0}
        )
        cat_bucket["case_count"] += 1
        cat_bucket["slots"] += k

        run_selections: list[str] = []
        run_reasons: list[str] = []
        hit_count = 0

        for pf, run_preds in zip(pred_files, runs_data):
            if cid not in run_preds:
                missing_predictions.append({"file": str(pf), "case_id": cid})
                sel = "<MISSING>"
                reason = "missing prediction"
                is_hit = False
            else:
                sel = run_preds[cid]["selected"]
                reason = run_preds[cid]["reason"]
                is_hit = sel == expected or (sel in acceptable_set and sel not in forbidden_set)

            run_selections.append(sel)
            run_reasons.append(reason)

            if known_skills is not None and sel not in (NO_SKILL, "<MISSING>") and sel not in known_skills:
                hallucinated_skills.append({"file": str(pf), "case_id": cid, "selected": sel})

            if is_hit:
                hit_count += 1
                total_hits += 1
                cat_bucket["hits"] += 1
            else:
                cat_bucket["misses"] += 1
                confusion_counter[f"{expected} -> {sel}"] += 1
                if sel in forbidden_set:
                    forbidden_hits.append({
                        "case_id": cid, "category": cat, "expected": expected,
                        "actual": sel, "file": str(pf), "query": c["query"],
                    })
                if cat == "negative" and sel not in (NO_SKILL, "<MISSING>"):
                    neg_fp_sources[sel] += 1
                    neg_fp_cases.append({
                        "case_id": cid, "actual": sel, "file": str(pf), "query": c["query"],
                    })

        if hit_count >= 1:
            pass_at_k_count += 1
            cat_bucket["pass_at_k"] += 1
        if hit_count == k:
            pass_pow_k_count += 1
            cat_bucket["pass_pow_k"] += 1
        if 0 < hit_count < k:
            jitter_cases.append({
                "case_id": cid, "category": cat, "expected": expected,
                "hits": hit_count, "runs": k, "selections": run_selections, "query": c["query"],
            })
        if hit_count < k:
            misses.append({
                "case_id": cid, "category": cat, "expected": expected,
                "acceptable": c["acceptable"], "forbidden": c["forbidden"],
                "hits": hit_count, "runs": k, "selections": run_selections,
                "reasons": run_reasons, "query": c["query"], "note": c["note"],
            })
        if cat == "real-badcase":
            real_badcase_results.append({
                "case_id": cid,
                "status": "PASS" if hit_count == k else "REGRESSED",
                "expected": expected,
                "hits": hit_count,
                "runs": k,
                "selections": run_selections,
                "query": c["query"],
            })

    # 同义改写一致性检查（检查同 paraphrase_group 内不同成员在各轮的选择是否一致）
    para_groups: dict[str, list[tuple[dict, list[str]]]] = defaultdict(list)
    sel_by_id = {
        c["id"]: [run_preds[c["id"]]["selected"] if c["id"] in run_preds else "<MISSING>" for run_preds in runs_data]
        for c in cases
    }
    for c in cases:
        grp = c["paraphrase_group"]
        if grp:
            para_groups[grp].append((c, sel_by_id[c["id"]]))

    paraphrase_inconsistencies: list[dict] = []
    for grp, items in sorted(para_groups.items()):
        if len(items) < 2:
            continue
        all_sels = {sel for _c, sels in items for sel in sels}
        if len(all_sels) > 1:
            paraphrase_inconsistencies.append({
                "group": grp,
                "expected": sorted({c["expected"] for c, _ in items}),
                "members": [
                    {"case_id": c["id"], "selections": sels, "query": c["query"]}
                    for c, sels in items
                ],
            })

    active_categories = {k_cat: v for k_cat, v in by_category.items() if v["case_count"] > 0}
    return {
        "runs": k,
        "pred_files": [str(p) for p in pred_files],
        "total_cases": len(cases),
        "total_slots": total_slots,
        "hit_slots": total_hits,
        "miss_slots": total_slots - total_hits,
        "pass_at_k": {"count": pass_at_k_count, "total": len(cases)} if k >= 2 else None,
        "pass_pow_k": {"count": pass_pow_k_count, "total": len(cases)} if k >= 2 else None,
        "by_category": active_categories,
        "alerts": {
            "misses": misses,
            "confusion_matrix": dict(confusion_counter.most_common()),
            "forbidden_hits": forbidden_hits,
            "negative_false_positives": {
                "by_skill": dict(neg_fp_sources.most_common()),
                "cases": neg_fp_cases,
            },
            "jitter_cases": jitter_cases,
            "paraphrase_inconsistencies": paraphrase_inconsistencies,
            "real_badcases": real_badcase_results,
        },
        "anomalies": {
            "missing_predictions": missing_predictions,
            "hallucinated_skills": hallucinated_skills,
            "extra_prediction_ids": extra_prediction_ids,
            "malformed_lines": malformed_lines,
        },
    }


def _print_score_report(report: dict, model_label: str) -> None:
    label = f" [{model_label}]" if model_label else ""
    print(f"=== 路由盲测体检雷达{label} ===")
    print(f"题数: {report['total_cases']} | 轮次: {report['runs']} | 槽位命中: {report['hit_slots']}/{report['total_slots']}（未命中 {report['miss_slots']}）")
    if report["runs"] >= 2:
        p_at = report["pass_at_k"]
        p_pow = report["pass_pow_k"]
        k = report["runs"]
        print(f"多轮稳定性: pass@{k} = {p_at['count']}/{p_at['total']} | pass^{k} = {p_pow['count']}/{p_pow['total']}")

    print("\n[分类明细]")
    for cat, st in report["by_category"].items():
        extra = f" | pass^{report['runs']}={st['pass_pow_k']}/{st['case_count']}" if report["runs"] >= 2 else ""
        print(f"  - {cat:<13} 题数 {st['case_count']:<3} 命中 {st['hits']}/{st['slots']}{extra}")

    alerts = report["alerts"]
    print("\n[警报 1 · 漏触/错配清单]")
    if not alerts["misses"]:
        print("  无")
    else:
        for m in alerts["misses"]:
            print(f"  - {m['case_id']} ({m['category']}) 命中 {m['hits']}/{m['runs']} | 期望 `{m['expected']}` → 实选 {m['selections']} | {m['query'][:60]}")

    print("\n[警报 2 · 边界互抢与混淆矩阵]")
    if alerts["forbidden_hits"]:
        for fh in alerts["forbidden_hits"]:
            print(f"  - [严重误抢] {fh['case_id']}: 期望 `{fh['expected']}` 却误触发 forbidden `{fh['actual']}`")
    if alerts["confusion_matrix"]:
        for pair, cnt in alerts["confusion_matrix"].items():
            print(f"  - {pair} × {cnt}")
    elif not alerts["forbidden_hits"]:
        print("  无")

    print("\n[警报 3 · 轻任务误触源 (expected=NONE)]")
    neg_by_skill = alerts["negative_false_positives"]["by_skill"]
    if not neg_by_skill:
        print("  无")
    else:
        for sk, cnt in neg_by_skill.items():
            print(f"  - `{sk}` 误触发 {cnt} 次")

    print("\n[警报 4 · 顺序抖动与同义改写不一致]")
    if not alerts["jitter_cases"] and not alerts["paraphrase_inconsistencies"]:
        print("  无")
    else:
        for j in alerts["jitter_cases"]:
            print(f"  - [抖动] {j['case_id']}: 期望 `{j['expected']}`，各轮 {j['selections']}")
        for p in alerts["paraphrase_inconsistencies"]:
            detail = " / ".join(f"{m['case_id']}={m['selections']}" for m in p["members"])
            print(f"  - [同义不一致] 组 `{p['group']}`（期望 {p['expected']}）：{detail}")

    print("\n[警报 5 · 真实翻车回归]")
    if not alerts["real_badcases"]:
        print("  无")
    else:
        for rb in alerts["real_badcases"]:
            print(f"  - [{rb['status']}] {rb['case_id']}: 期望 `{rb['expected']}`，命中 {rb['hits']}/{rb['runs']}，实选 {rb['selections']}")

    anom = report["anomalies"]
    if any(anom.values()):
        print("\n[数据异常告警]")
        for kind, items in anom.items():
            if items:
                print(f"  - {kind}: {len(items)} 条（示例: {items[0]}）")


def cmd_score(args: argparse.Namespace) -> int:
    cases_path = Path(args.cases)
    if not cases_path.is_file():
        print(f"用例文件不存在：{cases_path}", file=sys.stderr)
        return 2
    pred_paths = [Path(p) for p in args.preds]
    missing_files = [str(p) for p in pred_paths if not p.is_file()]
    if missing_files:
        print(f"预测文件不存在：{', '.join(missing_files)}", file=sys.stderr)
        return 2

    known_skills: set[str] | None = None
    if args.root:
        root = _resolve_root_or_exit(args.root)
        known_skills = {c["name"] for c in load_neutral_catalog(root)}

    try:
        cases = _load_cases_for_score(cases_path)
    except (ValueError, KeyError) as exc:
        print(f"读取用例失败：{exc}", file=sys.stderr)
        return 2

    report = evaluate_runs(cases, pred_paths, known_skills=known_skills)
    if args.model_label:
        report["model_label"] = args.model_label

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_score_report(report, args.model_label)

    alerts = report["alerts"]
    failed = False
    if args.fail_on_forbidden and alerts["forbidden_hits"]:
        failed = True
    if args.fail_on_neg_fp and alerts["negative_false_positives"]["cases"]:
        failed = True
    if args.fail_on_real_badcase and any(r["status"] == "REGRESSED" for r in alerts["real_badcases"]):
        failed = True
    if args.max_miss_rate is not None and report["total_slots"] > 0:
        if (report["miss_slots"] / report["total_slots"]) > args.max_miss_rate:
            failed = True
    return 1 if failed else 0


# ---------------------------------------------------------------- run


def _load_catalog_list(catalog_path: Path) -> list[dict]:
    data = json.loads(catalog_path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("skills"), list):
        return data["skills"]
    if isinstance(data, list):
        return data
    raise ValueError("catalog.json 格式必须为技能数组或含 skills 字段的对象")


def _build_router_prompt(skills: list[dict], query: str) -> list[dict]:
    lines = [f"- `{s['name']}`: {s.get('description', '')}" for s in skills]
    sys_msg = (
        "你是技能路由器。只能依据下列技能名称与 description 判断用户请求应触发哪一个技能；"
        "如果不需要任何专业技能或只是一般轻任务，返回 \"NONE\"。"
        "只输出一个 JSON 对象：{\"selected\": \"<skill-name-or-NONE>\", \"reason\": \"简短理由\"}。"
    )
    user_msg = "可用技能清单：\n" + "\n".join(lines) + f"\n\n用户请求：\n{query}"
    return [{"role": "system", "content": sys_msg}, {"role": "user", "content": user_msg}]


def cmd_run(args: argparse.Namespace) -> int:
    base_url = (args.base_url or os.environ.get("ROUTE_EVAL_BASE_URL") or "").strip()
    env_val = (os.environ.get(args.api_key_env) or "").strip()
    model = (args.model or os.environ.get("ROUTE_EVAL_MODEL") or "").strip()

    missing = []
    if not base_url:
        missing.append("ROUTE_EVAL_BASE_URL / --base-url")
    if not env_val:
        missing.append(f"环境变量 {args.api_key_env}")
    if not model:
        missing.append("ROUTE_EVAL_MODEL / --model")
    if missing:
        print(
            f"缺少可选 HTTP Runner 配置：{', '.join(missing)}。\n"
            "提示：本工具默认推荐直接在宿主内用干净上下文子代理执行盲选（零 API Key 配置），"
            "无需强依赖 HTTP Runner。",
            file=sys.stderr,
        )
        return 2

    catalog_path = Path(args.catalog)
    blind_path = Path(args.blind_cases)
    if not catalog_path.is_file() or not blind_path.is_file():
        print("catalog 或 blind_cases 文件不存在。", file=sys.stderr)
        return 2

    skills = _load_catalog_list(catalog_path)
    blind_cases = [json.loads(ln) for ln in blind_path.read_text(encoding="utf-8").splitlines() if ln.strip()]

    endpoint = base_url.rstrip("/") + "/chat/completions"
    results: list[dict] = []
    for item in blind_cases:
        payload = json.dumps({
            "model": model,
            "temperature": args.temperature,
            "messages": _build_router_prompt(skills, item["query"]),
        }).encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {env_val}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=args.timeout) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
            content = resp_data["choices"][0]["message"]["content"]
            parsed = parse_router_reply(content)
        except (urllib.error.URLError, KeyError, IndexError, ValueError) as exc:
            parsed = {"selected": NO_SKILL, "reason": f"runner error: {type(exc).__name__}", "parse_ok": False}

        results.append({
            "id": item["id"],
            "selected": parsed["selected"],
            "reason": parsed["reason"],
            "parse_ok": parsed["parse_ok"],
        })

    _write_jsonl(Path(args.out), results)
    print(f"已完成 {len(results)} 条推理，结果写入：{args.out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="技能库中立路由活卷盲测与真实翻车回归工具")
    sub = ap.add_subparsers(dest="command", required=True)

    bp = sub.add_parser("blueprint", help="导出纯中立目录（可选乱序）与本次抽考蓝图")
    bp.add_argument("root", nargs="?", default=".", help="技能库目录（默认自动发现）")
    bp.add_argument("--shuffle", action="store_true", help="打乱技能列表顺序消除位置偏置")
    bp.add_argument("--seed", type=int, default=None, help="随机种子")
    bp.add_argument("--max-pairs", type=int, default=15, help="最多抽取多少对邻居边界")
    bp.add_argument("--neg-count", type=int, default=8, help="建议轻任务负例条数")
    bp.add_argument("--paraphrase-count", type=int, default=4, help="同义改写配对抽样技能数")
    bp.add_argument("--focus", default="", help="逗号分隔的重点关注技能（局部增量体检）")
    bp.add_argument("--exclude", default="", help="逗号分隔的排除技能")
    bp.add_argument("--out-catalog", default="", help="导出纯中立目录 JSON 路径")
    bp.add_argument("--out-blueprint", default="", help="导出抽考蓝图 JSON 路径")
    bp.add_argument("--json", action="store_true")

    au = sub.add_parser("audit", help="审计活卷/病例质量（泄题、照抄、标签自洽与覆盖）")
    au.add_argument("cases", help="待审计的 JSONL 用例文件")
    au.add_argument("root", nargs="?", default=".", help="技能库目录（默认自动发现）")
    au.add_argument("--strict", action="store_true", help="将 mid 严重度告警也视为失败（exit 1）")
    au.add_argument("--allow-partial", action="store_true", help="跳过全库覆盖与负例检查（适用于真翻车回归集）")
    au.add_argument("--export-blind", default="", help="导出严格去标签的盲测题单 JSONL")
    au.add_argument("--json", action="store_true")

    sc = sub.add_parser("score", help="聚合单轮/多轮预测并输出无总分体检雷达")
    sc.add_argument("cases", help="完整标注的 JSONL 用例文件")
    sc.add_argument("preds", nargs="+", help="1 份或多份预测结果 JSONL")
    sc.add_argument("--root", default="", help="可选技能库目录，用于检出幻觉技能名")
    sc.add_argument("--model-label", default="", help="报告标题标注的模型/组别名称")
    sc.add_argument("--fail-on-forbidden", action="store_true")
    sc.add_argument("--fail-on-neg-fp", action="store_true")
    sc.add_argument("--fail-on-real-badcase", action="store_true")
    sc.add_argument("--max-miss-rate", type=float, default=None)
    sc.add_argument("--json", action="store_true")

    rn = sub.add_parser("run", help="可选 OpenAI 兼容 HTTP Runner（无配置时推荐走宿主子代理）")
    rn.add_argument("catalog", help="blueprint 导出的 catalog.json")
    rn.add_argument("blind_cases", help="audit 导出的去标签 blind_cases.jsonl")
    rn.add_argument("--out", required=True, help="预测结果 JSONL 输出路径")
    rn.add_argument("--base-url", default="")
    rn.add_argument("--api-key-env", default="ROUTE_EVAL_API_KEY")
    rn.add_argument("--model", default="")
    rn.add_argument("--temperature", type=float, default=0.0)
    rn.add_argument("--timeout", type=int, default=30)

    return ap


def main() -> int:
    ap = build_parser()
    args = ap.parse_args()
    handlers = {
        "blueprint": cmd_blueprint,
        "audit": cmd_audit,
        "score": cmd_score,
        "run": cmd_run,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
