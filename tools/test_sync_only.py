#!/usr/bin/env python3
"""select_names 过滤逻辑的最小单测：只验 --only 过滤与未知名拒绝，不触任何真实目录/配置。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sync_skills import select_names  # noqa: E402

MANIFEST = ["engineering-docs", "content-infographic", "haohao-eval", "cuihuo"]


def expect_eq(actual, want, label):
    assert actual == want, f"{label}: got {actual!r}, want {want!r}"


def test_default_is_all():
    expect_eq(select_names(MANIFEST, None), MANIFEST, "不传 --only 应返回全部")
    expect_eq(select_names(MANIFEST, []), MANIFEST, "空 --only 应返回全部")


def test_filter_valid():
    expect_eq(select_names(MANIFEST, ["engineering-docs"]), ["engineering-docs"], "单技能过滤")
    expect_eq(select_names(MANIFEST, ["content-infographic", "engineering-docs"]),
              ["content-infographic", "engineering-docs"], "多技能过滤保序")


def test_dedupe():
    expect_eq(select_names(MANIFEST, ["engineering-docs", "engineering-docs"]),
              ["engineering-docs"], "重复名去重")


def test_reject_unknown():
    for bad in ["nope", "engineering-docs ", "../evil", ""]:
        try:
            select_names(MANIFEST, ["engineering-docs", bad])
        except SystemExit:
            continue
        raise AssertionError(f"未知名 {bad!r} 应触发 SystemExit")


def test_target_scope():
    import contextlib
    import io
    import json
    import tempfile
    from unittest.mock import patch
    import sync_skills as sync

    with tempfile.TemporaryDirectory(prefix="skill-sync-scope-") as td:
        base = Path(td)
        source, target = base / "source", base / "target"
        for name in ("allowed", "unrelated"):
            (source / name).mkdir(parents=True)
            (source / name / "SKILL.md").write_text(name)
        (target / "unrelated").mkdir(parents=True)
        sentinel = target / "unrelated" / "SKILL.md"
        sentinel.write_text("user-owned")
        manifest, config = base / "manifest.json", base / "config.json"
        manifest.write_text(json.dumps({"skills": [{"name": "allowed"}, {"name": "unrelated"}]}))
        cfg = {"targets": [{"dir": str(target), "only": ["allowed"]}], "zip_dir": str(base / "zips")}
        config.write_text(json.dumps(cfg))
        with patch.object(sync, "MANIFEST", manifest), patch.object(sync, "LOCAL_CONFIG", config), patch.object(sync, "REPO_SKILLS", source):
            with patch.object(sys, "argv", ["sync_skills.py", "--apply"]), contextlib.redirect_stdout(io.StringIO()):
                sync.main()
            expect_eq((target / "allowed" / "SKILL.md").read_text(), "allowed", "范围内技能应更新")
            expect_eq(sentinel.read_text(), "user-owned", "范围外技能不许覆盖")
            expect_eq(sync.tree_diff(source / "allowed", target / "allowed"), (set(), set()), "二次同步应无差异")
            for invalid in ([], "allowed", ["nope"], [1]):
                cfg["targets"][0]["only"] = invalid
                config.write_text(json.dumps(cfg))
                try:
                    sync.load_config()
                except SystemExit:
                    continue
                raise AssertionError(f"非法目标范围 {invalid!r} 必须拒绝")
            cfg["targets"][0].pop("only")
            config.write_text(json.dumps(cfg))
            expect_eq(sync.load_config()["targets"][0]["only"], None, "旧配置应保持全量行为")


if __name__ == "__main__":
    test_default_is_all()
    test_filter_valid()
    test_dedupe()
    test_reject_unknown()
    test_target_scope()
    print("PASS: command filtering and scoped synchronization (5 cases, no real dirs touched)")
