#!/usr/bin/env python3
"""个人技能单向同步：Git 仓是唯一权威源，推送到各运行目录与发布 zip。

路径配置来自 tools/sync.local.json（git 忽略，不同机器各自填写），模板见
tools/sync.example.json。配置字段：
  targets : [{ "dir": "<某技能宿主的技能目录>", "only": ["skill-name"] }]
            only 可省略；设置后该目标只接收列出的技能。
  zip_dir : "<发布 zip 目录>"

为什么以 Git 仓为唯一权威源：
  - 方向单向，杜绝旧副本反向覆盖新版本；
  - .deps/.git/__pycache__ 等运行时产物不入库，同步时也永远不会被推出去；
  - 目标目录采用"删除后按源重建"，残留的运行时目录会被一并清掉。

版本找回：
  - 不在目标/发布目录留任何同步备份；旧版本一律通过 Git 历史找回（git log / git checkout）。
  - 发布 zip 目录只保留"当前最新"一版，方便直接打包上传，不做归档。

安全：
  - 默认 dry-run 只报差异；加 --apply 才写入。
  - 只处理 manifest 白名单；目标目录里的其他技能/公司内部技能一律不碰。
  - 若某目标存在"源里没有、且不属于忽略项"的文件（可能在该目标直接改过没回灌），
    标 ALERT 并在 dry-run/apply 输出里列出这些将被清除的源外文件；apply 不做文件备份，
    需要保留请先把它回灌 Git 并 commit——Git 是唯一备份。
"""
from __future__ import annotations

import argparse
import filecmp
import fnmatch
import json
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_DIR.parent
MANIFEST = TOOLS_DIR / "skills-manifest.json"
LOCAL_CONFIG = TOOLS_DIR / "sync.local.json"
EXAMPLE_CONFIG = TOOLS_DIR / "sync.example.json"

REPO_SKILLS = REPO_ROOT / "skills"

IGNORE = [".DS_Store", "__pycache__", ".pytest_cache", ".ruff_cache", "*.pyc", ".git", ".deps"]


def expand(p: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(p)))


def load_config() -> dict:
    cfg_path = LOCAL_CONFIG if LOCAL_CONFIG.is_file() else EXAMPLE_CONFIG
    if cfg_path == EXAMPLE_CONFIG:
        sys.exit("未找到 tools/sync.local.json：复制 tools/sync.example.json 为 sync.local.json，填入本机路径后再运行。")
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    manifest_names = [s["name"] for s in json.loads(MANIFEST.read_text(encoding="utf-8"))["skills"]]
    targets = []
    for t in cfg.get("targets", []):
        scope = t.get("only")
        if scope is not None and (not isinstance(scope, list) or not scope or any(not isinstance(n, str) for n in scope)):
            sys.exit("target.only 必须是非空技能名列表；省略表示同步全部")
        targets.append({"dir": expand(t["dir"]), "only": select_names(manifest_names, scope) if scope is not None else None})
    if not targets:
        sys.exit("sync.local.json 里 targets 为空，至少配置一个技能运行目录。")
    zip_dir = expand(cfg["zip_dir"])
    return {"targets": targets, "zip_dir": zip_dir}


def skip_name(name: str) -> bool:
    return any(fnmatch.fnmatch(name, pat) for pat in IGNORE)


def ignored_rel(rel: "os.PathLike[str] | str") -> bool:
    return any(skip_name(part) for part in Path(rel).parts)


def ignore_func(_dir: str, names: list[str]) -> set[str]:
    out = set()
    for n in names:
        if skip_name(n):
            out.add(n)
            continue
        p = Path(_dir) / n
        if p.is_symlink() and not p.exists():
            out.add(n)
    return out


def list_files(root: Path) -> set[str]:
    if not root.exists():
        return set()
    out = set()
    for p in root.rglob("*"):
        rel = str(p.relative_to(root))
        if ignored_rel(rel):
            continue
        if p.is_file() and not p.is_symlink():
            out.add(rel)
    return out


def files_differ(a: Path, b: Path) -> bool:
    try:
        return not filecmp.cmp(a, b, shallow=False)
    except OSError:
        return True


def tree_diff(src: Path, dst: Path) -> tuple[set[str], set[str]]:
    sf, df = list_files(src), list_files(dst)
    src_side = {rel for rel in sf if rel not in df or files_differ(src / rel, dst / rel)}
    dst_only = set(df - sf)
    return src_side, dst_only


def sync_dir(src: Path, dst: Path, apply: bool) -> tuple[str, set[str]]:
    """返回 (状态, 目标独有的源外文件)。apply 时统一"删除后按源重建"，不留备份。"""
    if not dst.exists():
        if apply:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(src, dst, ignore=ignore_func)
        return "CREATE", set()
    src_side, dst_only = tree_diff(src, dst)
    has_residual_deps = (dst / ".deps").exists()
    if not src_side and not dst_only and not has_residual_deps:
        return "SAME", set()
    flags = []
    if dst_only:
        flags.append(f"ALERT(源外独有 {len(dst_only)})")
    if has_residual_deps:
        flags.append("清理.deps")
    if apply:
        shutil.rmtree(dst)
        shutil.copytree(src, dst, ignore=ignore_func)
    return "UPDATE " + ("+".join(flags) if flags else ""), dst_only


def zip_files(zip_path: Path, name: str) -> set[str]:
    if not zip_path.exists():
        return set()
    prefix = name + "/"
    out = set()
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if info.is_dir() or not info.filename.startswith(prefix):
                continue
            rel = info.filename[len(prefix):]
            if not ignored_rel(rel):
                out.add(rel)
    return out


def zip_differs(src: Path, zip_path: Path, name: str) -> bool:
    zfiles, sfiles = zip_files(zip_path, name), list_files(src)
    if zfiles != sfiles:
        return True
    with zipfile.ZipFile(zip_path) as zf:
        for rel in sfiles:
            crc = zipfile.crc32((src / rel).read_bytes()) & 0xFFFFFFFF
            if zf.getinfo(name + "/" + rel).CRC != crc:
                return True
    return False


def build_zip(src: Path, name: str, zip_dir: Path) -> None:
    zip_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        stage = Path(td) / name
        shutil.copytree(src, stage, ignore=ignore_func)
        with zipfile.ZipFile(zip_dir / f"{name}.zip", "w", zipfile.ZIP_DEFLATED) as zf:
            for p in sorted(stage.rglob("*")):
                if p.is_file():
                    zf.write(p, p.relative_to(Path(td)))


def sync_zip(src: Path, name: str, zip_dir: Path, apply: bool) -> str:
    zip_path = zip_dir / f"{name}.zip"
    if not zip_path.exists():
        if apply:
            build_zip(src, name, zip_dir)
        return "CREATE"
    if zip_differs(src, zip_path, name):
        if apply:
            build_zip(src, name, zip_dir)
        return "UPDATE"
    return "SAME"


def select_names(manifest_names: list[str], only: list[str] | None) -> list[str]:
    """按 --only 白名单过滤；未知名直接拒绝。不传则保持全量既有行为。"""
    if not only:
        return list(manifest_names)
    only = list(dict.fromkeys(only))
    unknown = [n for n in only if n not in set(manifest_names)]
    if unknown:
        sys.exit(f"--only 含未在 manifest 白名单的技能：{', '.join(unknown)}（拒绝执行）")
    return only


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--only", nargs="+", default=None, metavar="SKILL",
                    help="只处理白名单内指定技能；拒绝未知名。不传=全部（既有行为）")
    args = ap.parse_args()
    cfg = load_config()
    all_names = [s["name"] for s in json.loads(MANIFEST.read_text(encoding="utf-8"))["skills"]]
    names = select_names(all_names, args.only)
    n = len(cfg["targets"])
    scope = "全部" if not args.only else f"仅 {' '.join(names)}"
    print(f"模式: {'APPLY' if args.apply else 'DRY-RUN'} | 权威源=git仓 skills/ | 白名单 {len(all_names)} 个 | 本轮 {scope} | 目标 {n} 个运行目录 + zip\n")
    col = 24
    print(f"{'技能':<22}" + "".join(f"{f'目标{i+1}':<{col}}" for i in range(n)) + "zip")
    print("-" * (22 + col * n + 8))
    alerts: list[str] = []
    for name in names:
        src = REPO_SKILLS / name
        if not (src / "SKILL.md").is_file():
            print(f"{name:<22}权威源缺 SKILL.md，跳过（先在 git 仓补全）")
            alerts.append(f"{name}: git 权威源缺 SKILL.md")
            continue
        dir_results = []
        for i, t in enumerate(cfg["targets"]):
            if t["only"] is not None and name not in t["only"]:
                dir_results.append("SKIP(目标范围外)")
                continue
            status, dst_only = sync_dir(src, t["dir"] / name, args.apply)
            dir_results.append(status)
            if dst_only:
                alerts.append(f"{name} → 目标{i+1} 有 {len(dst_only)} 个源外文件"
                              f"{'，apply 已按权威源清除' if args.apply else '，apply 时将被清除'}："
                              + "、".join(sorted(dst_only)[:5])
                              + (" …" if len(dst_only) > 5 else ""))
        r_zip = sync_zip(src, name, cfg["zip_dir"], args.apply)
        print(f"{name:<22}" + "".join(f"{r:<{col}}" for r in dir_results) + r_zip)
    print()
    if alerts:
        print("⚠️ ALERT（目标里有 git 源没有的内容；同步不留文件备份，需要保留请先回灌 Git 并 commit）：")
        for a in alerts:
            print("  -", a)
    else:
        print("所有目标与 git 权威源一致，无 ALERT。")
    if not args.apply:
        print("（dry-run；确认后加 --apply。同步只从 git 仓往外推，不会用旧副本覆盖 git；旧版本从 Git 历史找回）")


if __name__ == "__main__":
    raise SystemExit(main())
