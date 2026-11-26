#!/usr/bin/env python3
"""个人技能单向同步：Git 仓是唯一权威源，推送到各运行目录与发布 zip。

路径配置来自 tools/sync.local.json（git 忽略，不同机器各自填写），模板见
tools/sync.example.json。配置字段：
  targets : [{ "dir": "<某技能宿主的技能目录>", "only": ["skill-name"], "groups": ["engineering"] }]
            only / groups 均可省略；省略表示同步全部；同时给出时取并集。
  zip_dir : "<发布 zip 目录>"

公共文件单源分发（shared/）：
  skills-manifest.json 的 shared 字段声明 shared/<path> 需要分发到哪些技能目录；
  运行 --sync-shared 从 shared/ 复制到对应技能目录；--check-shared 校验无漂移。

安全：
  - 默认 dry-run 只报差异；加 --apply 才写入。
  - 若宿主的根目录（target.dir）本身不存在，默认跳过不创建（防止误建缺失宿主目录）；
    需要显式初始化新宿主根目录时加 --create-missing-targets。
  - 正常同步前自动校验 shared/ 一致性，若发现漂移或缺失则拒绝同步。
"""
from __future__ import annotations

import argparse
import filecmp
import fnmatch
import json
import os
import re
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
REPO_PLUGINS = REPO_ROOT / "plugins"
SHARED_DIR = REPO_ROOT / "shared"
AGY_PLUGINS_CONFIG = Path("~/.gemini/config/plugins.json")

IGNORE = [".DS_Store", "__pycache__", ".pytest_cache", ".ruff_cache", "*.pyc", ".git", ".deps"]


def expand(p: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(p)))


def read_manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def build_groups_map(manifest_data: dict) -> dict[str, list[str]]:
    groups_map: dict[str, list[str]] = {}
    for g in manifest_data.get("groups", []):
        name = g.get("name")
        skills = g.get("skills", [])
        if name:
            groups_map[name] = list(skills)
    return groups_map


def expand_groups(manifest_names: list[str], groups_map: dict[str, list[str]], groups: list[str]) -> list[str]:
    if not isinstance(groups, list) or not groups or any(not isinstance(g, str) or not g for g in groups):
        sys.exit("groups 必须是非空分组名列表")
    unknown = [g for g in groups if g not in groups_map]
    if unknown:
        sys.exit(f"包含未在 manifest 定义的分组：{', '.join(unknown)}（拒绝执行）")
    selected_set = {s for g in groups for s in groups_map[g]}
    unknown_skills = [s for s in selected_set if s not in set(manifest_names)]
    if unknown_skills:
        sys.exit(f"分组包含未在 manifest 登记的技能：{', '.join(sorted(unknown_skills))}")
    return [n for n in manifest_names if n in selected_set]


def load_config() -> dict:
    cfg_path = LOCAL_CONFIG if LOCAL_CONFIG.is_file() else EXAMPLE_CONFIG
    if cfg_path == EXAMPLE_CONFIG:
        sys.exit("未找到 tools/sync.local.json：复制 tools/sync.example.json 为 sync.local.json，填入本机路径后再运行。")
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    manifest_data = read_manifest()
    manifest_names = [s["name"] for s in manifest_data["skills"]]
    groups_map = build_groups_map(manifest_data)
    targets = []
    for t in cfg.get("targets", []):
        scope = t.get("only")
        t_groups = t.get("groups")
        resolved: list[str] | None = None
        if scope is not None:
            if not isinstance(scope, list) or not scope or any(not isinstance(n, str) for n in scope):
                sys.exit("target.only 必须是非空技能名列表；省略表示同步全部")
            resolved = select_names(manifest_names, scope)
        if t_groups is not None:
            expanded = expand_groups(manifest_names, groups_map, t_groups)
            if resolved is None:
                resolved = expanded
            else:
                merged = set(resolved) | set(expanded)
                resolved = [n for n in manifest_names if n in merged]
        targets.append({"dir": expand(t["dir"]), "only": resolved})
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


def check_shared(manifest_data: dict | None = None) -> list[str]:
    """检查 manifest.shared 中声明的公共文件是否与 shared/ 权威源一致。"""
    data = manifest_data if manifest_data is not None else read_manifest()
    issues: list[str] = []
    for entry in data.get("shared", []):
        rel = entry["path"]
        src = SHARED_DIR / rel
        if not src.is_file():
            issues.append(f"MISSING_SOURCE: shared/{rel} 不存在")
            continue
        for skill in entry.get("skills", []):
            dst = REPO_SKILLS / skill / rel
            if not dst.is_file():
                issues.append(f"MISSING: skills/{skill}/{rel}")
            elif files_differ(src, dst):
                issues.append(f"DRIFT: skills/{skill}/{rel} 与 shared/{rel} 不一致")
    return issues


def sync_shared(manifest_data: dict | None = None) -> tuple[int, int, list[str]]:
    """将 shared/ 权威源单向复制到 manifest.shared 声明的各技能目录。"""
    data = manifest_data if manifest_data is not None else read_manifest()
    copied = 0
    unchanged = 0
    errors: list[str] = []
    for entry in data.get("shared", []):
        rel = entry["path"]
        src = SHARED_DIR / rel
        if not src.is_file():
            errors.append(f"缺少公共源文件：shared/{rel}")
            continue
        for skill in entry.get("skills", []):
            skill_dir = REPO_SKILLS / skill
            if not skill_dir.is_dir():
                errors.append(f"目标技能目录不存在：skills/{skill}")
                continue
            dst = skill_dir / rel
            if dst.is_file() and not files_differ(src, dst):
                unchanged += 1
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied += 1
    return copied, unchanged, errors


def tree_diff(src: Path, dst: Path) -> tuple[set[str], set[str]]:
    sf, df = list_files(src), list_files(dst)
    src_side = {rel for rel in sf if rel not in df or files_differ(src / rel, dst / rel)}
    dst_only = set(df - sf)
    return src_side, dst_only


def sync_dir(src: Path, dst: Path, apply: bool, managed_peers: set[Path] | None = None) -> tuple[str, set[str]]:
    """返回 (状态, 目标独有的源外文件)。apply 时统一"删除后按源重建"，不留备份；遇到符号链接若指向受管同源目标则保留软链，否则仅 unlink 后重建。"""
    if dst.is_symlink():
        link_target = Path(os.path.abspath(os.path.join(str(dst.parent), os.readlink(dst))))
        if managed_peers and link_target in managed_peers:
            if dst.exists() and dst.is_dir():
                src_side, dst_only = tree_diff(src, dst)
                if not src_side and not dst_only and not (dst / ".deps").exists():
                    return "SAME(软链)", set()
            return "LINK(随源更新)", set()
        if dst.exists() and dst.is_dir():
            src_side, dst_only = tree_diff(src, dst)
            has_residual_deps = (dst / ".deps").exists()
            if not src_side and not dst_only and not has_residual_deps:
                return "SAME(软链)", set()
            flags = ["替换软链"]
            if dst_only:
                flags.append(f"ALERT(源外独有 {len(dst_only)})")
            if has_residual_deps:
                flags.append("清理.deps")
            if apply:
                dst.unlink()
                shutil.copytree(src, dst, ignore=ignore_func)
            return "UPDATE " + "+".join(flags), dst_only
        if apply:
            dst.unlink()
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(src, dst, ignore=ignore_func)
        return "UPDATE 清理坏软链", set()
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


def read_frontmatter_name(sk_md: Path) -> str | None:
    if not sk_md.is_file():
        return None
    try:
        text = sk_md.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    m = re.search(r"(?m)^name:\s*(.+)$", parts[1])
    return m.group(1).strip().strip("\"'") if m else None


def scan_target_shadows(targets: list[dict], manifest_names: set[str]) -> list[str]:
    """检查配置了 only 的目标目录中是否存在未纳管的同源旧副本或重名目录。"""
    managed_skill_dirs: set[tuple[Path, str]] = set()
    for t in targets:
        for sname in manifest_names:
            if t["only"] is None or sname in t["only"]:
                managed_skill_dirs.add(((t["dir"] / sname).resolve(), sname))

    extra_alerts: list[str] = []
    for i, t in enumerate(targets):
        tdir = t["dir"]
        if not tdir.exists():
            continue
        for child in sorted(tdir.iterdir()):
            if child.name.startswith(".") or not (child.is_dir() or child.is_symlink()):
                continue
            fm_name = read_frontmatter_name(child / "SKILL.md")
            matched_name = fm_name if fm_name in manifest_names else (child.name if child.name in manifest_names else None)
            if matched_name is None:
                continue
            if fm_name in manifest_names and child.name != fm_name:
                extra_alerts.append(
                    f"ALIAS_ALERT: 目标{i+1}({tdir}) 存在同源重名目录 `{child.name}`（其 name 为 `{fm_name}`）；请删除重复目录并统一用 `{fm_name}` 纳管"
                )
            if t["only"] is not None and child.name not in t["only"]:
                is_managed_link = (
                    child.is_symlink()
                    and child.exists()
                    and (
                        child.resolve() == (REPO_SKILLS / matched_name).resolve()
                        or (child.resolve(), matched_name) in managed_skill_dirs
                    )
                )
                if not is_managed_link:
                    extra_alerts.append(
                        f"SHADOW_ALERT: 目标{i+1}({tdir}) 存在未纳入 only 的同源技能 `{child.name}`（可能以旧版遮蔽新版）；请纳入 only 或移除"
                    )
    return extra_alerts


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


def sync_agy_plugin(
    apply: bool,
    config_path: Path | None = None,
    plugins_dir: Path | None = None,
) -> tuple[str, Path, Path]:
    """幂等注册本仓 plugins/ 目录到 Antigravity 的 plugins.json，保留用户既有配置。"""
    cfg_path = config_path if config_path is not None else expand(str(AGY_PLUGINS_CONFIG))
    p_dir = (plugins_dir if plugins_dir is not None else REPO_PLUGINS).resolve()

    existed = cfg_path.is_file()
    if existed:
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
        except ValueError as exc:
            sys.exit(f"解析 {cfg_path} 失败：{exc}")
        if not isinstance(data, dict):
            sys.exit(f"格式错误：{cfg_path} 顶层必须是 JSON 对象")
    else:
        data = {}

    entries = data.get("entries")
    if entries is None:
        entries = []
    if not isinstance(entries, list):
        sys.exit(f"格式错误：{cfg_path} 中 entries 必须是数组")

    already = False
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            continue
        try:
            if expand(entry["path"]).resolve() == p_dir:
                already = True
                break
        except OSError:
            continue

    if already:
        return "SAME", cfg_path, p_dir

    entries.append({"path": str(p_dir)})
    data["entries"] = entries
    status = "UPDATE" if existed else "CREATE"
    if apply:
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        cfg_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return status, cfg_path, p_dir


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
    ap.add_argument("--group", nargs="+", default=None, metavar="GROUP",
                    help="按逻辑分组过滤白名单技能（不可与 --only 同时使用）")
    ap.add_argument("--sync-shared", action="store_true",
                    help="将 shared/ 公共文件单向同步到各目标技能目录")
    ap.add_argument("--check-shared", action="store_true",
                    help="只读校验 shared/ 公共文件与各技能副本无漂移")
    ap.add_argument("--create-missing-targets", action="store_true",
                    help="允许创建本地尚不存在的宿主根目录（默认跳过不建）")
    ap.add_argument("--sync-agy-plugin", action="store_true",
                    help="将本仓 plugins/ 注册到 ~/.gemini/config/plugins.json（保留既有配置，不改 hooks.json）")
    args = ap.parse_args()

    if args.only and args.group:
        sys.exit("--only 与 --group 不能同时指定，请二选一。")

    manifest_data = read_manifest()

    if args.check_shared:
        issues = check_shared(manifest_data)
        if issues:
            for item in issues:
                print(item)
            sys.exit(1)
        print("shared/ 公共文件一致性检查通过。")
        return

    if args.sync_shared:
        copied, unchanged, errors = sync_shared(manifest_data)
        print(f"shared/ 同步完成：更新 {copied} 份，已一致 {unchanged} 份。")
        if errors:
            for e in errors:
                print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)
        if not args.apply and not args.only and not args.group:
            return

    shared_issues = check_shared(manifest_data)
    if shared_issues:
        for item in shared_issues:
            print(item, file=sys.stderr)
        sys.exit("检测到 shared/ 副本缺失或漂移，请先运行 `python3 tools/sync_skills.py --sync-shared`。")

    cfg = load_config()
    all_names = [s["name"] for s in manifest_data["skills"]]
    groups_map = build_groups_map(manifest_data)
    if args.group:
        names = expand_groups(all_names, groups_map, args.group)
    else:
        names = select_names(all_names, args.only)

    n = len(cfg["targets"])
    if args.group:
        scope = f"分组 {' '.join(args.group)}（{len(names)} 个）"
    elif args.only:
        scope = f"仅 {' '.join(names)}"
    else:
        scope = "全部"
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
        managed_peers = {
            Path(os.path.abspath(ot["dir"] / name))
            for ot in cfg["targets"]
            if (ot["only"] is None or name in ot["only"]) and ot["dir"].exists() and not (ot["dir"] / name).is_symlink()
        } | {src.resolve()}
        dir_results = []
        for i, t in enumerate(cfg["targets"]):
            if not t["dir"].exists() and not args.create_missing_targets:
                dir_results.append("SKIP(宿主目录不存在)")
                continue
            if t["only"] is not None and name not in t["only"]:
                dir_results.append("SKIP(目标范围外)")
                continue
            status, dst_only = sync_dir(src, t["dir"] / name, args.apply, managed_peers)
            dir_results.append(status)
            if dst_only:
                alerts.append(f"{name} → 目标{i+1} 有 {len(dst_only)} 个源外文件"
                              f"{'，apply 已按权威源清除' if args.apply else '，apply 时将被清除'}："
                              + "、".join(sorted(dst_only)[:5])
                              + (" …" if len(dst_only) > 5 else ""))
        r_zip = sync_zip(src, name, cfg["zip_dir"], args.apply)
        print(f"{name:<22}" + "".join(f"{r:<{col}}" for r in dir_results) + r_zip)
    alerts.extend(scan_target_shadows(cfg["targets"], set(all_names)))
    print()
    if args.sync_agy_plugin:
        p_status, p_cfg, p_dir = sync_agy_plugin(args.apply)
        print(f"[AGY-PLUGIN] status={p_status} | config={p_cfg} | entry={p_dir}\n")
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
