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
TEST_PATH_RE = re.compile(
    r"(?:^|/)(?:tests?|__tests__|spec|specs|fixtures?)(?:/|$)|(?:^|/)test_[^/]+$|(?:_test|\.test|\.spec)\.[^/]+$",
    re.I,
)
CODE_SUFFIXES = (
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".go", ".rs", ".java", ".kt", ".swift", ".m", ".mm",
    ".c", ".cc", ".cpp", ".h", ".hpp", ".cs", ".rb", ".php",
    ".sql", ".sh", ".bash", ".zsh",
)
RENAME_BRACE_RE = re.compile(r"^(.*)\{([^{}]*)\s+=>\s+([^{}]*)\}(.*)$")


def _clean_rel_path(p: str) -> str:
    return re.sub(r"/+", "/", p.strip()).strip("/")


def expand_numstat_path(raw_path: str) -> tuple[str, list[str]]:
    """展开 git diff --numstat 中的重命名语法 `{old => new}` / `old => new`。"""
    m = RENAME_BRACE_RE.match(raw_path)
    if m:
        prefix, old_seg, new_seg, suffix = m.groups()
        old_p = _clean_rel_path(prefix + old_seg + suffix)
        new_p = _clean_rel_path(prefix + new_seg + suffix)
        paths = [p for p in dict.fromkeys((old_p, new_p)) if p]
        return new_p or old_p, paths
    if " => " in raw_path:
        old_seg, new_seg = raw_path.split(" => ", 1)
        old_p = _clean_rel_path(old_seg)
        new_p = _clean_rel_path(new_seg)
        paths = [p for p in dict.fromkeys((old_p, new_p)) if p]
        return new_p or old_p, paths
    p = _clean_rel_path(raw_path)
    return p, [p] if p else []


def run_git(args: list[str], cwd: Path) -> tuple[int, str, str]:
    r = subprocess.run(
        ["git", "-c", "core.quotePath=false", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    return r.returncode, r.stdout, r.stderr.strip()


def validate_rev_range(target_range: str, repo: Path) -> None:
    if not target_range or target_range.startswith("-"):
        raise RuntimeError(f"非法的 diff 范围参数：{target_range!r}（拒绝以 `-` 开头的选项注入）")
    sep = "..." if "..." in target_range else (".." if ".." in target_range else None)
    if sep:
        left, right = target_range.split(sep, 1)
        sides = [s for s in (left, right) if s]
        if not sides:
            raise RuntimeError(f"非法的 diff 范围：{target_range!r}")
        for side in sides:
            if side.startswith("-"):
                raise RuntimeError(f"非法的 diff 引用：{side!r}")
            rc, _, err = run_git(["rev-parse", "--verify", side], repo)
            if rc != 0:
                raise RuntimeError(f"无效的 git 引用 {side!r}：{err}")
    elif target_range != "HEAD":
        rc, _, err = run_git(["rev-parse", "--verify", target_range], repo)
        if rc != 0:
            raise RuntimeError(f"无效的 git 引用 {target_range!r}：{err}")


def analyze_surface(root: Path, rev_range: str | None = None) -> dict:
    root = root.resolve()
    rc, top, err = run_git(["rev-parse", "--show-toplevel"], root)
    if rc != 0 or not top.strip():
        raise RuntimeError(f"非 Git 仓库：{root}（{err}）")
    repo = Path(top.strip()).resolve()

    target_range = rev_range or "HEAD"
    validate_rev_range(target_range, repo)
    is_working_tree = rev_range is None or ".." not in target_range

    if target_range == "HEAD":
        rc_head, _, _ = run_git(["rev-parse", "--verify", "HEAD"], repo)
        if rc_head != 0:
            diff_args = ["diff", "--no-ext-diff", "--numstat", "--"]
        else:
            diff_args = ["diff", "--no-ext-diff", "--numstat", "HEAD", "--"]
    else:
        diff_args = ["diff", "--no-ext-diff", "--numstat", target_range, "--"]

    rc_d, numstat_out, err_d = run_git(diff_args, repo)
    if rc_d != 0:
        raise RuntimeError(f"git diff 失败：{err_d}")

    files: list[dict] = []
    check_paths_by_idx: list[list[str]] = []
    added_total = 0
    deleted_total = 0
    for ln in numstat_out.splitlines():
        parts = ln.split("\t")
        if len(parts) < 3:
            continue
        add_s, del_s, raw_path = parts[0], parts[1], parts[2]
        display_path, all_paths = expand_numstat_path(raw_path)
        add_n = int(add_s) if add_s.isdigit() else 0
        del_n = int(del_s) if del_s.isdigit() else 0
        added_total += add_n
        deleted_total += del_n
        files.append({"path": display_path, "added": add_n, "deleted": del_n, "untracked": False})
        check_paths_by_idx.append(all_paths)

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
                check_paths_by_idx.append([rel])

    risk_hits: dict[str, list[str]] = {}
    for f, cand_paths in zip(files, check_paths_by_idx):
        display_p = f["path"]
        prod_paths = [cp for cp in cand_paths if not TEST_PATH_RE.search(cp)]
        for cp in prod_paths:
            for tag, pat in HIGH_RISK_PATTERNS.items():
                if pat.search(cp):
                    risk_hits.setdefault(tag, []).append(display_p)
        if f["deleted"] > 0 and f["added"] == 0 and any(cp.lower().endswith(CODE_SUFFIXES) for cp in prod_paths):
            risk_hits.setdefault("delete", []).append(display_p)

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
