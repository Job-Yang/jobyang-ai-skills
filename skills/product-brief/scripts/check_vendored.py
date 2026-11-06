#!/usr/bin/env python3
"""opc-envelope vendored 公共文件一致性自检。

两种用法：
  1) 在技能根（或 scripts 的上一级）运行：
       python3 scripts/check_vendored.py
     读取 <skill_root>/scripts/vendor-manifest.json，校验 manifest 中声明的
     vendored 文件 sha256 与期望一致；缺失或不符 -> exit 1。

  2) 跨包漂移检查（开发者机器，多技能并排时）：
       python3 scripts/check_vendored.py --drift /path/to/skillA /path/to/skillB ...
     对每个给定技能根，收集其 manifest 声明的相对路径 -> sha256，
     同一路径在不同包之间哈希不一致即报漂移 -> exit 1。

仅依赖标准库。manifest 结构：
{
  "kit": "opc-envelope",
  "version": "0.2.0",
  "vendored": [
    {"path": "scripts/artifact_io.py", "sha256": "..."},
    {"path": "scripts/scoring-rules.json", "sha256": "..."}
  ]
}
某个包不再携带某文件时，从该包 manifest 的 vendored 列表移除即可。
"""
import hashlib
import json
import sys
from pathlib import Path


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def skill_root_for_manifest() -> Path:
    here = Path(__file__).resolve().parent          # <root>/scripts
    return here.parent


def load_manifest(root: Path):
    mf = root / "scripts" / "vendor-manifest.json"
    if not mf.exists():
        return None
    return json.loads(mf.read_text(encoding="utf-8"))


def check_one(root: Path) -> int:
    root = root.resolve()
    manifest = load_manifest(root)
    if manifest is None:
        print(f"[vendor] SKIP 无 scripts/vendor-manifest.json: {root}")
        return 0
    bad = 0
    print(f"[vendor] {manifest.get('kit','?')} {manifest.get('version','?')} @ {root.name}")
    for item in manifest.get("vendored", []):
        rel, want = item["path"], item["sha256"]
        p = root / rel
        if not p.exists():
            print(f"  MISSING {rel}")
            bad += 1
            continue
        got = sha256_file(p)
        if got != want:
            print(f"  HASH-MISMATCH {rel}\n    want {want}\n    got  {got}")
            bad += 1
        else:
            print(f"  OK {rel}")
    return 1 if bad else 0


def check_drift(roots) -> int:
    # rel path -> {skill_name: sha}
    seen = {}
    skipped = []
    for r in roots:
        root = Path(r).resolve()
        manifest = load_manifest(root)
        if manifest is None:
            skipped.append(root.name)
            continue
        for item in manifest.get("vendored", []):
            seen.setdefault(item["path"], {})[root.name] = item["sha256"]
    drift = 0
    for rel, by_pkg in sorted(seen.items()):
        hashes = set(by_pkg.values())
        if len(hashes) > 1:
            drift += 1
            print(f"[drift] {rel} 在包间不一致:")
            for pkg, h in sorted(by_pkg.items()):
                print(f"    {pkg:28s} {h}")
        else:
            print(f"[drift] OK {rel}（{len(by_pkg)} 个包一致）")
    for s in skipped:
        print(f"[drift] SKIP {s}（无 vendor-manifest.json）")
    if drift:
        print(f"[drift] 发现 {drift} 处漂移")
        return 1
    print("[drift] 无漂移")
    return 0


def main(argv) -> int:
    if len(argv) >= 2 and argv[0] == "--drift":
        if len(argv) < 2:
            print("用法: check_vendored.py --drift <skill_root> [<skill_root> ...]")
            return 2
        return check_drift(argv[1:])
    return check_one(skill_root_for_manifest())


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
