#!/usr/bin/env python3
"""sync_skills.py 新特性与 workspace_guard.py 的回归测试（仅依赖标准库，临时目录隔离）。"""
from __future__ import annotations

import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

TOOLS_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = TOOLS_DIR.parent
sys.path.insert(0, str(TOOLS_DIR))
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

import sync_skills as sync  # noqa: E402
import workspace_guard as wg  # noqa: E402


class SyncExtensionsTests(unittest.TestCase):
    def test_group_expansion_shared_sync_and_missing_target_skip(self):
        with tempfile.TemporaryDirectory(prefix="sync-ext-") as td:
            base = Path(td)
            shared = base / "shared"
            source = base / "skills"
            existing_target = base / "existing-host"
            missing_target = base / "missing-host"
            zips = base / "zips"
            (shared / "references").mkdir(parents=True)
            (shared / "references" / "common.md").write_text("# Common\nv1\n", encoding="utf-8")
            for sk in ("alpha", "beta", "gamma"):
                (source / sk).mkdir(parents=True)
                (source / sk / "SKILL.md").write_text(f"---\nname: {sk}\n---\n", encoding="utf-8")
            existing_target.mkdir()

            manifest = base / "manifest.json"
            manifest.write_text(json.dumps({
                "groups": [
                    {"name": "eng", "skills": ["alpha", "beta"]},
                    {"name": "misc", "skills": ["gamma"]},
                ],
                "shared": [
                    {"path": "references/common.md", "skills": ["alpha", "beta"]},
                ],
                "skills": [{"name": "alpha"}, {"name": "beta"}, {"name": "gamma"}],
            }), encoding="utf-8")

            cfg = base / "sync.local.json"
            cfg.write_text(json.dumps({
                "targets": [
                    {"dir": str(existing_target), "groups": ["eng"]},
                    {"dir": str(missing_target)},
                ],
                "zip_dir": str(zips),
            }), encoding="utf-8")

            with patch.object(sync, "MANIFEST", manifest), \
                 patch.object(sync, "LOCAL_CONFIG", cfg), \
                 patch.object(sync, "REPO_SKILLS", source), \
                 patch.object(sync, "SHARED_DIR", shared):
                # 1) 未同步 shared 前应检测到缺失
                issues = sync.check_shared()
                self.assertEqual(2, len(issues))

                # 2) 未传 --sync-shared 直接同步应拒绝
                with patch.object(sys, "argv", ["sync_skills.py", "--apply"]):
                    with self.assertRaises(SystemExit):
                        sync.main()

                # 3) --sync-shared 后检查通过
                with patch.object(sys, "argv", ["sync_skills.py", "--sync-shared"]), \
                     contextlib.redirect_stdout(io.StringIO()):
                    sync.main()
                self.assertEqual([], sync.check_shared())

                # 4) --group eng --apply 只同步 alpha/beta，且不创建 missing_target
                with patch.object(sys, "argv", ["sync_skills.py", "--group", "eng", "--apply"]), \
                     contextlib.redirect_stdout(io.StringIO()) as buf:
                    sync.main()
                self.assertIn("SKIP(宿主目录不存在)", buf.getvalue())
                self.assertFalse(missing_target.exists())
                self.assertTrue((existing_target / "alpha" / "references" / "common.md").is_file())
                self.assertTrue((existing_target / "beta" / "references" / "common.md").is_file())
                self.assertFalse((existing_target / "gamma").exists())
                self.assertTrue((zips / "alpha.zip").is_file())
                self.assertFalse((zips / "gamma.zip").exists())

                # 5) 故意篡改目标技能副本应报 DRIFT
                (source / "alpha" / "references" / "common.md").write_text("tampered\n", encoding="utf-8")
                drift = sync.check_shared()
                self.assertEqual(1, len(drift))
                self.assertIn("DRIFT", drift[0])

    def test_sync_agy_plugin_idempotent_preserves_existing_entries(self):
        with tempfile.TemporaryDirectory(prefix="sync-plugin-") as td:
            base = Path(td)
            plugins_dir = base / "plugins"
            plugins_dir.mkdir()
            cfg = base / "config" / "plugins.json"

            # 1) dry-run CREATE 不写文件
            st1, _, _ = sync.sync_agy_plugin(apply=False, config_path=cfg, plugins_dir=plugins_dir)
            self.assertEqual("CREATE", st1)
            self.assertFalse(cfg.exists())

            # 2) apply CREATE 写入配置
            st2, _, _ = sync.sync_agy_plugin(apply=True, config_path=cfg, plugins_dir=plugins_dir)
            self.assertEqual("CREATE", st2)
            self.assertTrue(cfg.is_file())

            # 3) 再次检查呈 SAME
            st3, _, _ = sync.sync_agy_plugin(apply=False, config_path=cfg, plugins_dir=plugins_dir)
            self.assertEqual("SAME", st3)

            # 4) 用户另有 inherits 与其他 entries 时，保留既有字段执行 UPDATE
            cfg.write_text(json.dumps({
                "inherits": [{"path": "/other/plugins.json"}],
                "entries": [{"path": "/other/dir", "exclude": ["x"]}],
            }), encoding="utf-8")
            st4, _, _ = sync.sync_agy_plugin(apply=True, config_path=cfg, plugins_dir=plugins_dir)
            self.assertEqual("UPDATE", st4)
            saved = json.loads(cfg.read_text(encoding="utf-8"))
            self.assertEqual([{"path": "/other/plugins.json"}], saved["inherits"])
            self.assertEqual(2, len(saved["entries"]))
            self.assertEqual(str(plugins_dir.resolve()), saved["entries"][1]["path"])


class WorkspaceGuardTests(unittest.TestCase):
    def _git(self, cwd: Path, *args: str) -> str:
        r = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True)
        return r.stdout.strip()

    def _init_git_repo(self, root: Path) -> None:
        self._git(root, "init")
        self._git(root, "config", "user.email", "local-test")
        self._git(root, "config", "user.name", "Test")
        (root / ".gitignore").write_text("*.log\n", encoding="utf-8")
        (root / "README.md").write_text("demo\n", encoding="utf-8")
        self._git(root, "add", ".gitignore", "README.md")
        self._git(root, "commit", "-m", "init")

    def test_non_git_ephemeral(self):
        with tempfile.TemporaryDirectory(prefix="wg-ephem-") as td:
            info = wg.detect_mode(Path(td), "auto")
            self.assertEqual("ephemeral", info["mode"])

    def test_local_mode_zero_pollution_and_hash_progress_archive(self):
        with tempfile.TemporaryDirectory(prefix="wg-local-") as td:
            root = Path(td)
            self._init_git_repo(root)

            info = wg.detect_mode(root, "auto")
            self.assertEqual("local", info["mode"])

            # init-local 初始化并写入 .git/info/exclude，不改 .gitignore
            rc = wg.main(["init-local", "--root", str(root)])
            self.assertEqual(0, rc)
            # 幂等再次执行
            rc = wg.main(["init-local", "--root", str(root)])
            self.assertEqual(0, rc)
            self.assertEqual("*.log\n", (root / ".gitignore").read_text(encoding="utf-8"))
            self.assertEqual("*\n", (root / ".agent-work" / "spec" / "archived" / ".ignore").read_text(encoding="utf-8"))
            exclude_txt = (root / ".git" / "info" / "exclude").read_text(encoding="utf-8")
            self.assertEqual(1, exclude_txt.splitlines().count(".agent-work/"))

            # 上游文件计算 hash 必须与 git hash-object 完全相等
            feat = root / ".agent-work" / "feature" / "auth.md"
            feat.write_text("# Auth\nStatus: decided\n", encoding="utf-8")
            git_hash = self._git(root, "hash-object", str(feat))
            self.assertEqual(git_hash, wg.git_blob_sha1(feat))

            # status 必须零污染
            self.assertEqual("", self._git(root, "status", "--short"))

            # 写入 spec 并验证 verify-hash 与 progress
            spec = root / ".agent-work" / "spec" / "auth.md"
            spec.write_text(
                f"# Auth Spec\n\nSource: `.agent-work/feature/auth.md` @ `{git_hash}`\n\n"
                "## Steps\n\n"
                "1. Add schema. After: none. Check: `true`\n"
                "2. Add handler. After: 1. Check: `true`\n"
                "3. Add cli. After: 1. Check: `true`\n",
                encoding="utf-8",
            )
            self.assertEqual(0, wg.main(["verify-hash", "--spec", str(spec), "--root", str(root)]))

            # 修改上游 1 字节必须拦截 exit 2
            feat.write_text("# Auth\nStatus: decided!\n", encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(2, wg.main(["verify-hash", "--spec", str(spec), "--root", str(root)]))

            # 恢复上游并测试 record-step + progress
            feat.write_text("# Auth\nStatus: decided\n", encoding="utf-8")
            wg.main(["record-step", "--slug", "auth", "--step", "1", "--sha", "abc1234", "--root", str(root), "--mode", "local"])
            with contextlib.redirect_stdout(io.StringIO()) as pbuf:
                wg.main(["progress", "--spec", str(spec), "--root", str(root)])
            prog = json.loads(pbuf.getvalue())
            self.assertEqual([1], prog["landed"])
            self.assertEqual([2, 3], prog["ready"])

            # 归档 spec
            with contextlib.redirect_stdout(io.StringIO()):
                rc = wg.main(["archive", "--spec", str(spec), "--root", str(root), "--date", "2026-11-26"])
            self.assertEqual(0, rc)
            self.assertFalse(spec.exists())
            self.assertTrue((root / ".agent-work" / "spec" / "archived" / "2026-11-26-auth.md").is_file())
            self.assertEqual("", self._git(root, "status", "--short"))

    def test_repo_mode_git_trailer_and_archive(self):
        with tempfile.TemporaryDirectory(prefix="wg-repo-") as td:
            root = Path(td)
            self._init_git_repo(root)
            (root / "docs" / "feature").mkdir(parents=True)
            (root / "docs" / "spec").mkdir(parents=True)
            info = wg.detect_mode(root, "auto")
            self.assertEqual("repo", info["mode"])

            feat = root / "docs" / "feature" / "cache.md"
            feat.write_text("# Cache\n", encoding="utf-8")
            sha = wg.git_blob_sha1(feat)
            spec = root / "docs" / "spec" / "cache.md"
            spec.write_text(
                f"# Cache Spec\n\nSource: `docs/feature/cache.md` @ `{sha}`\n\n"
                "## Steps\n\n"
                "1. Build core. After: none. Check: `true`\n"
                "2. Wire caller. After: 1. Check: `true`\n",
                encoding="utf-8",
            )
            self._git(root, "add", "docs")
            self._git(root, "commit", "-m", "Add cache docs")

            (root / "core.txt").write_text("v1\n", encoding="utf-8")
            self._git(root, "add", "core.txt")
            self._git(root, "commit", "-m", "Add cache core\n\nSpec-Step: cache#1")

            with contextlib.redirect_stdout(io.StringIO()) as pbuf:
                wg.main(["progress", "--spec", str(spec), "--root", str(root)])
            prog = json.loads(pbuf.getvalue())
            self.assertEqual([1], prog["landed"])
            self.assertEqual([2], prog["ready"])

            with contextlib.redirect_stdout(io.StringIO()):
                rc = wg.main(["archive", "--spec", str(spec), "--root", str(root), "--date", "2026-11-26"])
            self.assertEqual(0, rc)
            self.assertTrue((root / "docs" / "spec" / "archived" / "2026-11-26-cache.md").is_file())
            self.assertEqual("*\n", (root / "docs" / "spec" / "archived" / ".ignore").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
