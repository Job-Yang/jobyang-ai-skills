#!/usr/bin/env python3
"""分析 Git 改动范围、规模分档（Quick/Standard/Deep）与高危路径标签（纯标准库）。

用法：
  python3 diff_surface.py [--root .] [--range HEAD | main...HEAD] [--json]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

HIGH_RISK_PATTERNS = {
    "auth": re.compile(r"(?:^|/)(?:auth|oauth|jwt|session|acl|rbac|perm|permission|login|token|security)(?:[/_.-]|$)", re.I),
    "billing": re.compile(r"(?:^|/)(?:pay|payment|billing|invoice|order|wallet|ledger|refund|license|pricing)(?:[/_.-]|$)", re.I),
    "migration": re.compile(r"(?:^|/)(?:migrat(?:ion|e)s?|schema|alembic|flyway|prisma|ddl)(?:[/_.-]|$)", re.I),
    "ci": re.compile(r"(?:^\.github/workflows/|^\.gitlab-ci\.yml$|Makefile$|Dockerfile$|scripts/(?:deploy|release|build|publish))", re.I),
    "lockfile": re.compile(r"(?:package-lock\.json|pnpm-lock\.yaml|yarn\.lock|Cargo\.lock|poetry\.lock|uv\.lock|go\.sum)$"),
}


def run_git(args: list[str], cwd: Path) -> tuple[int, str, str]:
    r = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr.strip()


def analyze_surface(root: Path, rev_range: str | None = None) -> dict:
    root = root.resolve()
    rc, top, err = run_git(["rev-parse", "--show-toplevel"], root)
    if rc != 0 or not top.strip():
        raise RuntimeError(f"非 Git 仓库：{root}（{err}）")
    repo = Path(top.strip()).resolve()

    target_range = rev_range or "HEAD"
    is_working_tree = rev_range is None or rev_range == "HEAD"

    if target_range == "HEAD":
        rc_head, _, _ = run_git(["rev-parse", "--verify", "HEAD"], repo)
        if rc_head != 0:
            diff_args = ["diff", "--numstat"]
        else:
            diff_args = ["diff", "--numstat", "HEAD"]
    else:
        diff_args = ["diff", "--numstat", target_range]

    rc_d, numstat_out, err_d = run_git(diff_args, repo)
    if rc_d != 0:
        raise RuntimeError(f"git diff 失败：{err_d}")

    files: list[dict] = []
    added_total = 0
    deleted_total = 0
    for ln in numstat_out.splitlines():
        parts = ln.split("\t")
        if len(parts) < 3:
            continue
        add_s, del_s, path = parts[0], parts[1], parts[2]
        add_n = int(add_s) if add_s.isdigit() else 0
        del_n = int(del_s) if del_s.isdigit() else 0
        added_total += add_n
        deleted_total += del_n
        files.append({"path": path, "added": add_n, "deleted": del_n, "untracked": False})

    untracked_files: list[str] = []
    if is_working_tree:
        rc_u, u_out, _ = run_git(["ls-files", "--others", "--exclude-standard"], repo)
        if rc_u == 0:
            for rel in sorted(x.strip() for x in u_out.splitlines() if x.strip()):
                p = repo / rel
                line_cnt = 0
                if p.is_file():
                    try:
                        line_cnt = len(p.read_text(encoding="utf-8", errors="ignore").splitlines())
                    except OSError:
                        line_cnt = 0
                added_total += line_cnt
                untracked_files.append(rel)
                files.append({"path": rel, "added": line_cnt, "deleted": 0, "untracked": True})

    risk_hits: dict[str, list[str]] = {}
    for f in files:
        p = f["path"]
        for tag, pat in HIGH_RISK_PATTERNS.items():
            if pat.search(p):
                risk_hits.setdefault(tag, []).append(p)
        if f["deleted"] > 0 and f["added"] == 0 and (p.endswith((".py", ".ts", ".js", ".go", ".rs", ".java", ".swift"))):
            risk_hits.setdefault("delete", []).append(p)

    file_count = len(files)
    total_lines = added_total + deleted_total
    deep_risk_tags = {"auth", "billing", "migration"}
    if file_count == 0:
        depth = "Empty"
    elif total_lines > 500 or file_count > 10 or any(t in risk_hits for t in deep_risk_tags):
        depth = "Deep"
    elif total_lines >= 100 or file_count >= 6:
        depth = "Standard"
    else:
        depth = "Quick"

    human_review_tags = [t for t in ("auth", "billing", "migration", "ci", "delete") if t in risk_hits]

    return {
        "repo": str(repo),
        "range": target_range,
        "depth": depth,
        "file_count": file_count,
        "added": added_total,
        "deleted": deleted_total,
        "total_lines": total_lines,
        "untracked_count": len(untracked_files),
        "risk_tags": {k: sorted(set(v)) for k, v in sorted(risk_hits.items())},
        "human_review_needed": bool(human_review_tags),
        "human_review_tags": human_review_tags,
        "files": files,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="分析 Git diff 表面与风险分档")
    ap.add_argument("--root", default=".")
    ap.add_argument("--range", dest="rev_range", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        res = analyze_surface(Path(args.root), args.rev_range)
    except RuntimeError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print(
            f"档位: {res['depth']} | 范围: {res['range']} | "
            f"文件: {res['file_count']} (未跟踪 {res['untracked_count']}) | "
            f"+{res['added']} -{res['deleted']} (合计 {res['total_lines']} 行)"
        )
        if res["human_review_needed"]:
            print(f"高危人审触发: {', '.join(res['human_review_tags'])}")
        for f in res["files"]:
            mark = " [untracked]" if f["untracked"] else ""
            print(f"  - {f['path']} (+{f['added']} -{f['deleted']}){mark}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
