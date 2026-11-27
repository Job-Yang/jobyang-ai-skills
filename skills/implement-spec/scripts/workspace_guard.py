#!/usr/bin/env python3
"""工程工作区与 Spec 状态机守卫（纯 Python 3.9+ 标准库，零外部依赖）。

支持个人仓（docs/ + Git trailer）与多人公司大仓（.agent-work/ + .git/info/exclude 零污染）
以及非 Git 仓降级（ephemeral）。

子命令：
  detect       自动识别工作区模式（repo / local / ephemeral）并输出路径映射 JSON
  init-local   初始化 .agent-work/ 并幂等写入本机私有 .git/info/exclude
  hash         计算文件 Git blob SHA-1（与 git hash-object 完全一致）
  verify-hash  校验 Spec 头部的 Source/Feature 摘要是否与当前上游文件一致
  progress     汇总 Spec 步骤的 Git Spec-Step trailer 与 state JSON，计算 ready 步骤
  record-step  在 .agent-work/state/<slug>.json 记录已完成步骤与提交 SHA
  archive      归档已完成 Spec 至 archived/<YYYY-MM-DD>-<slug>.md 并确保 .ignore
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
try:
    import fcntl
except ImportError:
    fcntl = None
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SOURCE_RE = re.compile(r"^(?:Source|Feature):\s*(?:`([^`\n]+)`|([^\n]+?))\s*@\s*`?([0-9a-fA-F]{7,40})`?\s*$")
SOURCE_NONE_RE = re.compile(r"^(?:Source|Feature):\s*`?none\b`?", re.I)
STEP_RE = re.compile(r"^(\d+)\.\s+(.*)$")
AFTER_RE = re.compile(r"\bAfter:\s*([^\n.;。；]+)", re.I)
SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate_slug(slug: str) -> str:
    s = (slug or "").strip()
    if not s or ".." in s or "/" in s or "\\" in s or not SLUG_RE.match(s):
        raise ValueError(f"非法 slug：{slug!r}（仅允许 [A-Za-z0-9._-]+ 且不含路径片段）")
    return s


def validate_date(date_str: str) -> str:
    d = (date_str or "").strip()
    if not DATE_RE.match(d):
        raise ValueError(f"非法日期格式：{date_str!r}（需要 YYYY-MM-DD）")
    dt.date.fromisoformat(d)
    return d


def run_git(args: list[str], cwd: Path) -> tuple[int, str, str]:
    r = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def git_root(start: Path) -> Path | None:
    rc, out, _ = run_git(["rev-parse", "--show-toplevel"], start)
    return Path(out).resolve() if rc == 0 and out else None


def resolve_repo_root(root_arg: str | None, spec_path: Path | None = None) -> Path | None:
    """解析目标仓库根目录：未显式指定 --root 时优先跟随 Spec 所在仓库，避免跨仓误判。"""
    explicit_root = Path(root_arg).resolve() if root_arg else None
    spec_root = git_root(spec_path.parent) if spec_path is not None else None
    if root_arg and root_arg != ".":
        return (git_root(explicit_root) if explicit_root is not None else None) or spec_root
    if spec_root is not None:
        return spec_root
    if explicit_root is None:
        return None
    er = git_root(explicit_root)
    if er is not None and spec_path is not None:
        try:
            spec_path.resolve().relative_to(er)
        except ValueError:
            return None
    return er


def git_blob_sha1(path: Path) -> str:
    data = path.read_bytes()
    header = f"blob {len(data)}\0".encode("utf-8")
    return hashlib.sha1(header + data).hexdigest()


def detect_mode(start: Path, force_mode: str = "auto") -> dict:
    start = start.resolve()
    root = git_root(start)
    if force_mode == "ephemeral" or (force_mode == "auto" and root is None):
        return {
            "mode": "ephemeral",
            "root": str(start),
            "work_dir": None,
            "feature_dir": None,
            "spec_dir": None,
            "archived_dir": None,
            "state_dir": None,
            "glossary": None,
        }
    if root is None:
        sys.exit(f"错误：目录 {start} 不在 Git 仓库内，无法使用 {force_mode} 模式")

    if force_mode == "auto":
        if (root / "docs" / "spec").is_dir() or (root / "docs" / "feature").is_dir():
            mode = "repo"
        else:
            mode = "local"
    else:
        mode = force_mode

    if mode == "repo":
        work_dir = root / "docs"
        return {
            "mode": "repo",
            "root": str(root),
            "work_dir": str(work_dir),
            "feature_dir": str(work_dir / "feature"),
            "spec_dir": str(work_dir / "spec"),
            "archived_dir": str(work_dir / "spec" / "archived"),
            "state_dir": str(work_dir / "spec" / ".state"),
            "glossary": str(work_dir / "GLOSSARY.md"),
        }

    work_dir = root / ".agent-work"
    return {
        "mode": "local",
        "root": str(root),
        "work_dir": str(work_dir),
        "feature_dir": str(work_dir / "feature"),
        "spec_dir": str(work_dir / "spec"),
        "archived_dir": str(work_dir / "spec" / "archived"),
        "state_dir": str(work_dir / "state"),
        "glossary": str(work_dir / "GLOSSARY.md"),
    }


def ensure_ignore_file(archived_dir: Path) -> Path:
    archived_dir.mkdir(parents=True, exist_ok=True)
    ignore_path = archived_dir / ".ignore"
    existing = ignore_path.read_text(encoding="utf-8") if ignore_path.is_file() else ""
    lines = [ln.strip() for ln in existing.splitlines() if ln.strip()]
    if "*" not in lines:
        new_content = (existing.rstrip("\n") + "\n*\n").lstrip("\n") if existing else "*\n"
        ignore_path.write_text(new_content, encoding="utf-8")
    return ignore_path


def cmd_detect(args: argparse.Namespace) -> int:
    info = detect_mode(Path(args.root), args.mode)
    print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0


def cmd_init_local(args: argparse.Namespace) -> int:
    root = git_root(Path(args.root).resolve())
    if root is None:
        print("错误：当前目录不是 Git 仓库，跳过 .agent-work 初始化（请改用 ephemeral 模式）", file=sys.stderr)
        return 1
    work = root / ".agent-work"
    for sub in ("feature", "spec", "state"):
        (work / sub).mkdir(parents=True, exist_ok=True)
    ignore_file = ensure_ignore_file(work / "spec" / "archived")

    rc, exclude_rel, err = run_git(["rev-parse", "--git-path", "info/exclude"], root)
    if rc != 0 or not exclude_rel:
        print(f"错误：无法定位 git info/exclude：{err}", file=sys.stderr)
        return 1
    exclude_path = Path(exclude_rel) if os.path.isabs(exclude_rel) else (root / exclude_rel)
    exclude_path.parent.mkdir(parents=True, exist_ok=True)
    current = exclude_path.read_text(encoding="utf-8") if exclude_path.is_file() else ""
    entries = {ln.strip() for ln in current.splitlines() if ln.strip() and not ln.strip().startswith("#")}
    added_exclude = False
    if ".agent-work/" not in entries and ".agent-work" not in entries:
        prefix = "" if (not current or current.endswith("\n")) else "\n"
        exclude_path.write_text(current + prefix + ".agent-work/\n", encoding="utf-8")
        added_exclude = True

    print(json.dumps({
        "root": str(root),
        "work_dir": str(work),
        "archived_ignore": str(ignore_file),
        "exclude_file": str(exclude_path),
        "exclude_updated": added_exclude,
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_hash(args: argparse.Namespace) -> int:
    p = Path(args.file)
    if not p.is_file():
        print(f"错误：文件不存在：{p}", file=sys.stderr)
        return 1
    print(git_blob_sha1(p))
    return 0


def resolve_source_ref(spec_path: Path, root: Path | None) -> tuple[str | None, str | None]:
    lines = spec_path.read_text(encoding="utf-8", errors="replace").splitlines()[:25]
    saw_none = False
    for ln in lines:
        s = ln.strip()
        m = SOURCE_RE.match(s)
        if m:
            path_part = (m.group(1) or m.group(2) or "").strip()
            return path_part, m.group(3).lower()
        if SOURCE_NONE_RE.match(s):
            saw_none = True
    if saw_none:
        return None, None
    return "", None


def cmd_verify_hash(args: argparse.Namespace) -> int:
    spec_path = Path(args.spec).resolve()
    if not spec_path.is_file():
        print(f"错误：Spec 不存在：{spec_path}", file=sys.stderr)
        return 1
    root = resolve_repo_root(args.root, spec_path) or Path(args.root).resolve()
    rel_src, want_sha = resolve_source_ref(spec_path, root)
    if rel_src is None and want_sha is None:
        print(json.dumps({"status": "skipped", "reason": "Source: none"}, ensure_ascii=False))
        return 0
    if rel_src == "" or want_sha is None:
        print(json.dumps({"status": "missing_anchor", "spec": str(spec_path)}, ensure_ascii=False), file=sys.stderr)
        return 1

    src_path = Path(rel_src)
    if not src_path.is_absolute():
        candidate_root = (root / rel_src).resolve()
        candidate_spec = (spec_path.parent / rel_src).resolve()
        src_path = candidate_root if candidate_root.is_file() else candidate_spec
    else:
        src_path = src_path.resolve()
    try:
        src_path.relative_to(root.resolve())
    except ValueError:
        print(json.dumps({"status": "source_outside_repo", "source": rel_src}, ensure_ascii=False), file=sys.stderr)
        return 2
    if not src_path.is_file():
        print(json.dumps({"status": "source_missing", "source": rel_src}, ensure_ascii=False), file=sys.stderr)
        return 2

    got_sha = git_blob_sha1(src_path)
    matched = got_sha.startswith(want_sha) or want_sha.startswith(got_sha)
    out = {
        "status": "ok" if matched else "drifted",
        "source": rel_src,
        "expected": want_sha,
        "actual": got_sha,
    }
    print(json.dumps(out, ensure_ascii=False))
    return 0 if matched else 2


def parse_steps(spec_path: Path) -> list[dict]:
    lines = spec_path.read_text(encoding="utf-8", errors="replace").splitlines()
    in_steps = False
    in_fence = False
    fence_delim = ""
    steps: dict[int, dict] = {}
    cur_step: int | None = None
    for ln in lines:
        stripped = ln.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            delim = "```" if stripped.startswith("```") else "~~~"
            if not in_fence:
                in_fence = True
                fence_delim = delim
                continue
            if stripped.startswith(fence_delim):
                in_fence = False
                fence_delim = ""
                continue
        if in_fence:
            continue
        if re.match(r"^##\s+Steps\b", stripped, re.I):
            in_steps = True
            cur_step = None
            continue
        if in_steps and re.match(r"^##\s+", stripped):
            break
        if not in_steps:
            continue
        m = STEP_RE.match(ln) if not ln[:1].isspace() else None
        if m:
            num = int(m.group(1))
            cur_step = num
            steps[num] = {"step": num, "title": m.group(2).strip(), "after": []}
            am = AFTER_RE.search(stripped)
            if am:
                steps[num]["after"] = parse_after_nums(am.group(1))
        elif cur_step is not None and not steps[cur_step]["after"]:
            am = AFTER_RE.search(stripped)
            if am:
                steps[cur_step]["after"] = parse_after_nums(am.group(1))
    return [steps[k] for k in sorted(steps)]


def parse_after_nums(raw: str) -> list[int]:
    if re.search(r"\bnone\b|无", raw, re.I):
        return []
    return sorted({int(x) for x in re.findall(r"\d+", raw)})


def infer_slug(spec_path: Path, explicit_slug: str | None) -> str:
    if explicit_slug:
        return explicit_slug
    stem = spec_path.stem
    return re.sub(r"^\d{4}-\d{2}-\d{2}-", "", stem)


def state_file_for(root: Path, spec_path: Path, slug: str) -> Path:
    info = detect_mode(root, "repo" if (root / "docs" / "spec") in spec_path.parents else "auto")
    if ".agent-work" in spec_path.parts:
        return root / ".agent-work" / "state" / f"{slug}.json"
    state_dir = Path(info["state_dir"]) if info["state_dir"] else (root / ".agent-work" / "state")
    return state_dir / f"{slug}.json"


def read_state_steps(state_path: Path) -> dict[int, str]:
    if not state_path.is_file():
        return {}
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        raw_landed = data.get("landed") if isinstance(data, dict) else None
        if not isinstance(raw_landed, dict):
            return {}
        out = {}
        for k, v in raw_landed.items():
            out[int(k)] = str(v)
        return out
    except (OSError, ValueError):
        return {}


def read_git_trailer_steps(root: Path, spec_path: Path, slug: str) -> set[int]:
    try:
        rel_spec_path = spec_path.resolve().relative_to(root.resolve())
    except ValueError:
        return set()
    if ".agent-work" in rel_spec_path.parts:
        return set()
    rc_h, _, _ = run_git(["rev-parse", "--verify", "HEAD"], root)
    if rc_h != 0:
        return set()

    rel_spec = str(rel_spec_path)
    cutoffs: list[str] = []
    rc_a, last_arch, _ = run_git(
        ["log", "-1", "--format=%H", "--", f":(glob)docs/spec/archived/*-{slug}.md"], root
    )
    if rc_a == 0 and last_arch:
        cutoffs.append(last_arch)
    rc_d, last_del, _ = run_git(
        ["log", "-1", "--diff-filter=D", "--format=%H", "--", rel_spec], root
    )
    if rc_d == 0 and last_del and last_del not in cutoffs:
        cutoffs.append(last_del)

    rev_args = ["HEAD", *(f"^{c}" for c in cutoffs)]
    rc, out, _ = run_git(["log", "--format=%(trailers:key=Spec-Step,valueonly)", *rev_args], root)
    if rc != 0 or not out:
        return set()
    landed = set()
    prefix = f"{slug}#"
    for ln in out.splitlines():
        s = ln.strip()
        if s.startswith(prefix):
            tail = s[len(prefix):]
            if tail.isdigit():
                landed.add(int(tail))
    return landed


def cmd_progress(args: argparse.Namespace) -> int:
    spec_path = Path(args.spec).resolve()
    if not spec_path.is_file():
        print(f"错误：Spec 不存在：{spec_path}", file=sys.stderr)
        return 1
    root = resolve_repo_root(args.root, spec_path)
    try:
        slug = validate_slug(infer_slug(spec_path, args.slug))
    except ValueError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 1
    steps = parse_steps(spec_path)

    landed_map: dict[int, str] = {}
    if root is not None:
        for num in read_git_trailer_steps(root, spec_path, slug):
            landed_map[num] = "git-trailer"
        for num, sha in read_state_steps(state_file_for(root, spec_path, slug)).items():
            landed_map.setdefault(num, sha)

    landed = sorted(landed_map)
    landed_set = set(landed)
    ready, blocked = [], []
    for st in steps:
        n = st["step"]
        if n in landed_set:
            continue
        missing_deps = [d for d in st["after"] if d not in landed_set]
        if missing_deps:
            blocked.append({"step": n, "waiting_for": missing_deps})
        else:
            ready.append(n)

    print(json.dumps({
        "slug": slug,
        "total": len(steps),
        "landed": landed,
        "ready": ready,
        "blocked_by_deps": blocked,
    }, ensure_ascii=False, indent=2))
    return 0


def _atomic_write_json(target: Path, data: dict) -> None:
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.stem}-", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        os.replace(tmp_name, target)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise


def cmd_record_step(args: argparse.Namespace) -> int:
    try:
        slug = validate_slug(args.slug)
    except ValueError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 1
    spec_arg = getattr(args, "spec", None)
    spec_path = Path(spec_arg).resolve() if spec_arg else None
    root = resolve_repo_root(args.root, spec_path) or Path(args.root).resolve()
    if spec_path is not None and args.mode == "auto":
        sf = state_file_for(root, spec_path, slug)
        state_dir = sf.parent
    else:
        info = detect_mode(root, args.mode)
        state_dir = Path(info["state_dir"]) if info["state_dir"] else (root / ".agent-work" / "state")
        sf = state_dir / f"{slug}.json"
    state_dir.mkdir(parents=True, exist_ok=True)
    try:
        sf.resolve().relative_to(state_dir.resolve())
    except ValueError:
        print(f"错误：状态文件路径越界：{sf}", file=sys.stderr)
        return 1

    lock_path = state_dir / f".{slug}.lock"
    with lock_path.open("a+", encoding="utf-8") as lfh:
        if fcntl is not None:
            fcntl.flock(lfh.fileno(), fcntl.LOCK_EX)
        try:
            data = {"slug": slug, "landed": {}}
            if sf.is_file():
                try:
                    loaded = json.loads(sf.read_text(encoding="utf-8"))
                    if isinstance(loaded, dict):
                        data = loaded
                except ValueError:
                    pass
            landed = data.get("landed")
            if not isinstance(landed, dict):
                landed = {}
                data["landed"] = landed
            landed[str(args.step)] = args.sha
            _atomic_write_json(sf, data)
        finally:
            if fcntl is not None:
                fcntl.flock(lfh.fileno(), fcntl.LOCK_UN)
    print(json.dumps({"state_file": str(sf), "slug": slug, "landed": landed}, ensure_ascii=False))
    return 0


def cmd_archive(args: argparse.Namespace) -> int:
    spec_path = Path(args.spec).resolve()
    if not spec_path.is_file():
        print(f"错误：Spec 不存在：{spec_path}", file=sys.stderr)
        return 1
    root = resolve_repo_root(args.root, spec_path) or spec_path.parent
    mode = args.mode
    if mode == "auto":
        mode = "local" if ".agent-work" in spec_path.parts else detect_mode(root, "auto")["mode"]
    if mode == "ephemeral":
        print("错误：ephemeral（非 Git 目录）模式不支持持久化 archive 归档", file=sys.stderr)
        return 1
    try:
        slug = validate_slug(infer_slug(spec_path, args.slug))
        date_str = validate_date(args.date or dt.date.today().isoformat())
    except ValueError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 1
    archived_dir = (root / ".agent-work" / "spec" / "archived") if mode == "local" else (root / "docs" / "spec" / "archived")
    ignore_file = ensure_ignore_file(archived_dir)
    dest = archived_dir / f"{date_str}-{slug}.md"
    suffix = 2
    while dest.exists():
        dest = archived_dir / f"{date_str}-{slug}-{suffix}.md"
        suffix += 1
    try:
        dest.resolve().relative_to(archived_dir.resolve())
    except ValueError:
        print(f"错误：归档路径越界：{dest}", file=sys.stderr)
        return 1

    used_git_mv = False
    if mode == "repo":
        try:
            rel_src = str(spec_path.relative_to(root.resolve()))
            rel_dst = str(dest.relative_to(root.resolve()))
            rc_ls, _, _ = run_git(["ls-files", "--error-unmatch", rel_src], root)
            if rc_ls == 0:
                rc_mv, _, err = run_git(["mv", rel_src, rel_dst], root)
                if rc_mv != 0:
                    print(f"错误：git mv 失败：{err}", file=sys.stderr)
                    return 1
                used_git_mv = True
                run_git(["add", str(ignore_file.relative_to(root.resolve()))], root)
        except ValueError:
            pass

    if not used_git_mv:
        shutil.move(str(spec_path), str(dest))

    print(json.dumps({
        "mode": mode,
        "archived_to": str(dest),
        "archived_ignore": str(ignore_file),
        "git_mv": used_git_mv,
    }, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="工程工作区与 Spec 状态机守卫")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_det = sub.add_parser("detect")
    p_det.add_argument("--root", default=".")
    p_det.add_argument("--mode", choices=["auto", "repo", "local", "ephemeral"], default="auto")
    p_det.set_defaults(func=cmd_detect)

    p_init = sub.add_parser("init-local")
    p_init.add_argument("--root", default=".")
    p_init.set_defaults(func=cmd_init_local)

    p_hash = sub.add_parser("hash")
    p_hash.add_argument("file")
    p_hash.set_defaults(func=cmd_hash)

    p_vh = sub.add_parser("verify-hash")
    p_vh.add_argument("--spec", required=True)
    p_vh.add_argument("--root", default=".")
    p_vh.set_defaults(func=cmd_verify_hash)

    p_prog = sub.add_parser("progress")
    p_prog.add_argument("--spec", required=True)
    p_prog.add_argument("--root", default=".")
    p_prog.add_argument("--slug", default=None)
    p_prog.set_defaults(func=cmd_progress)

    p_rec = sub.add_parser("record-step")
    p_rec.add_argument("--slug", required=True)
    p_rec.add_argument("--step", type=int, required=True)
    p_rec.add_argument("--sha", required=True)
    p_rec.add_argument("--root", default=".")
    p_rec.add_argument("--mode", choices=["auto", "repo", "local"], default="auto")
    p_rec.add_argument("--spec", default=None)
    p_rec.set_defaults(func=cmd_record_step)

    p_arc = sub.add_parser("archive")
    p_arc.add_argument("--spec", required=True)
    p_arc.add_argument("--mode", choices=["auto", "repo", "local"], default="auto")
    p_arc.add_argument("--root", default=".")
    p_arc.add_argument("--slug", default=None)
    p_arc.add_argument("--date", default=None)
    p_arc.set_defaults(func=cmd_archive)

    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
