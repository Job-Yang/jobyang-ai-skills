#!/usr/bin/env python3
"""候选超量分页/分包（纯 stdlib）。

背景：radar 候选可能几十上百条，冻结版 artifact_io 的信封是"一个文件一份 radar"，
没有规定超量怎么办。本脚本规定分页 schema 并提供 split/merge：

  一个目录 = 一个分页包：
    manifest.json                        # 分包索引（schema=opc-radar-pages/v1）
    radar-<date>-page001.md             # 每页 ≤ page_size（默认 20）条候选
    radar-<date>-page002.md
    ...

  每页自身就是一份合法 radar 信封（opc_node: radar / topic: null / 每条候选带
  evidence: real|assumption），split 后立即用冻结版 artifact_io.validate_envelope
  逐页校验——分页不破坏信封契约。

用法：
  python3 paginate.py split --input radar-2026-10-16.md --out-dir pages/ [--page-size 20]
  python3 paginate.py merge --manifest pages/manifest.json --out radar-merged.md

退出码：0=成功；2=参数/IO 错误；3=任一分页未过冻结版信封校验（不该发生，发生即拒）。
"""
import argparse
import json
import re
import sys
from pathlib import Path

# 复用冻结版信封校验器（只读调用，不改它）：分页产物必须与单文件同构。
sys.path.insert(0, str(Path(__file__).resolve().parent))
from artifact_io import validate_envelope  # noqa: E402

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 50
_CAND_SPLIT = re.compile(r"(?m)^(##\s+候选[：:].*?)(?=^##\s+候选[：:]|\Z)", re.S)


def split_candidates(body: str) -> list:
    """把 radar 正文切成 [前言, 候选块1, 候选块2, ...]。"""
    blocks = _CAND_SPLIT.findall(body)
    preface = body[:body.find("## 候选")] if "## 候选" in body else body
    return preface, [b.strip() for b in blocks]


def build_page(preface: str, chunk: list, created: str, page_no: int, page_count: int,
               produced_by: str) -> str:
    fm = [
        "---",
        "schema: opc-artifact/v1",
        "opc_node: radar",
        "artifact_kind: radar",
        "opc_version: 0.2.0",
        "topic: null",
        f"created: {created}",
        "upstream: null",
        f"produced_by: {produced_by}",
        "human_review: pending",
        f"part: \"page{page_no:03d}/{page_count:03d}\"",
        "---",
        "",
    ]
    # 分页包的前言只保留一次摘要行，避免每页都重复整段 preface。
    summary = [l for l in preface.splitlines() if l.strip()][:3]
    return "\n".join(fm + summary + [""] + [b + "\n" for b in chunk])


def split_radar(input_path: Path, out_dir: Path, page_size: int) -> int:
    text = input_path.read_text(encoding="utf-8")
    m = re.match(r"\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)(.*)\Z", text, re.S)
    if not m:
        print(json.dumps({"status": "rejected", "error": "输入不是合法 radar 信封：缺 front-matter"},
                         ensure_ascii=False), file=sys.stderr)
        return 2
    fm_text, body = m.group(1), m.group(2)
    created = re.search(r"created:\s*(\S+)", fm_text)
    produced_by = re.search(r"produced_by:\s*(\S+)", fm_text)
    date = (created.group(1)[:10] if created else "unknown-date")
    producer = produced_by.group(1) if produced_by else "standalone"

    preface, blocks = split_candidates(body)
    if not blocks:
        print(json.dumps({"status": "rejected", "error": "正文没有 ## 候选： 条目，无可分页"},
                         ensure_ascii=False), file=sys.stderr)
        return 2
    out_dir.mkdir(parents=True, exist_ok=True)
    chunks = [blocks[i:i + page_size] for i in range(0, len(blocks), page_size)]
    manifest = {"schema": "opc-radar-pages/v1", "date": date,
                "page_size": page_size, "page_count": len(chunks),
                "candidate_count": len(blocks), "pages": []}
    bad = 0
    for idx, chunk in enumerate(chunks, 1):
        md = build_page(preface, chunk, created.group(1) if created else date,
                        idx, len(chunks), producer)
        # 分页不破坏冻结信封契约：逐页过冻结版 validate_envelope。
        _, errors = validate_envelope(md)
        if errors:
            bad += 1
            print(json.dumps({"page": idx, "errors": errors}, ensure_ascii=False))
        name = f"radar-{date}-page{idx:03d}.md"
        (out_dir / name).write_text(md, encoding="utf-8")
        manifest["pages"].append(name)
    if bad:
        print(json.dumps({"status": "rejected", "error": f"{bad} 页未过冻结信封校验"},
                         ensure_ascii=False), file=sys.stderr)
        return 3
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "split", "out_dir": str(out_dir), **manifest},
                     ensure_ascii=False))
    return 0


def merge_pages(manifest_path: Path, out: Path) -> int:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "opc-radar-pages/v1":
        print(json.dumps({"status": "rejected", "error": "manifest schema 不是 opc-radar-pages/v1"},
                         ensure_ascii=False), file=sys.stderr)
        return 2
    pages_text = [(manifest_path.parent / name).read_text(encoding="utf-8")
                  for name in manifest["pages"]]
    # 合并：以第一页信封为准（去掉 part 行），正文 = 各页候选块依次拼接。
    m = re.match(r"\A(---[ \t]*\n)(.*?)(\n---[ \t]*\n?)(.*)\Z", pages_text[0], re.S)
    if not m:
        print(json.dumps({"status": "rejected", "error": "首页不是合法信封"},
                         ensure_ascii=False), file=sys.stderr)
        return 2
    fm_lines = [ln for ln in m.group(2).splitlines() if not ln.strip().startswith("part:")]
    bodies = []
    for p in pages_text:
        mm = re.match(r"\A---[ \t]*\n.*?\n---[ \t]*(?:\n|\Z)(.*)\Z", p, re.S)
        bodies.append(mm.group(1).strip())
    merged = m.group(1) + "\n".join(fm_lines) + m.group(3) + "\n\n" + "\n\n".join(bodies) + "\n"
    _, errors = validate_envelope(merged)
    if errors:
        print(json.dumps({"status": "rejected", "error": ["合并后未过冻结信封校验"] + errors},
                         ensure_ascii=False), file=sys.stderr)
        return 3
    out.write_text(merged, encoding="utf-8")
    print(json.dumps({"status": "merged", "output": str(out),
                      "candidate_count": manifest["candidate_count"]}, ensure_ascii=False))
    return 0


def main(argv) -> int:
    ap = argparse.ArgumentParser(description="radar 候选超量分页/分包")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("split")
    sp.add_argument("--input", required=True)
    sp.add_argument("--out-dir", required=True)
    sp.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE)
    mp = sub.add_parser("merge")
    mp.add_argument("--manifest", required=True)
    mp.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    if args.cmd == "split":
        ps = min(args.page_size, MAX_PAGE_SIZE)
        return split_radar(Path(args.input), Path(args.out_dir), ps)
    return merge_pages(Path(args.manifest), Path(args.out))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
