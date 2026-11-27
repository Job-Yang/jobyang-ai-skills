#!/usr/bin/env python3
"""pr-prep 离线 HTML 视觉导览与防仓内污染回归测试（零外部依赖）。"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT / "scripts"))
import pr_visual_report as pvr  # noqa: E402

ISOLATED_GIT_ENV = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


class PrVisualReportTests(unittest.TestCase):
    def setUp(self):
        env_patch = patch.dict(os.environ, ISOLATED_GIT_ENV)
        env_patch.start()
        self.addCleanup(env_patch.stop)

    def _git(self, cwd: Path, *args: str) -> str:
        r = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True)
        return r.stdout.strip()

    def test_contract_and_visual_report_generation(self):
        skill_md = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        for rel in (
            "references/engineering-workspace.md",
            "references/big-repo-safety.md",
            "references/pr-checklist.md",
            "scripts/pr_visual_report.py",
        ):
            self.assertIn(rel, skill_md)
            self.assertTrue((SKILL_ROOT / rel).is_file(), rel)

        with tempfile.TemporaryDirectory(prefix="pr-repo-") as td, \
             tempfile.TemporaryDirectory(prefix="pr-out-") as out_td:
            root = Path(td)
            self._git(root, "init")
            self._git(root, "config", "user.email", "local-test")
            self._git(root, "config", "user.name", "T")
            (root / "README.md").write_text("base\n", encoding="utf-8")
            self._git(root, "add", "README.md")
            self._git(root, "commit", "-m", "init")
            base_branch = self._git(root, "rev-parse", "--abbrev-ref", "HEAD")

            self._git(root, "checkout", "-b", "feat/payment-v2")
            (root / "migrations").mkdir()
            (root / "migrations" / "001_init.sql").write_text("CREATE TABLE t(id INT);\n", encoding="utf-8")
            (root / "billing").mkdir()
            (root / "billing" / "charge.py").write_text(
                "def charge():\n    return '<script>alert(1)</script>'\n", encoding="utf-8"
            )
            self._git(root, "add", "migrations", "billing")
            self._git(root, "commit", "-m", "Add billing & migration <test>")

            data = pvr.collect_pr_data(root, base_branch)
            self.assertIn("migration", data["risk_tags"])
            self.assertIn("billing", data["risk_tags"])

            html_path, md_path = pvr.write_reports(data, Path(out_td))
            self.assertTrue(html_path.is_file())
            self.assertTrue(md_path.is_file())

            html_txt = html_path.read_text(encoding="utf-8")
            self.assertNotIn("<script src=", html_txt)
            self.assertNotIn("https://", html_txt)
            self.assertIn("&lt;test&gt;", html_txt)
            self.assertIn("PR 视觉导览", html_txt)

            # 禁止写入业务仓内部
            with self.assertRaises(RuntimeError):
                pvr.write_reports(data, root / "reports")

            # 代码仓工作树保持零污染
            self.assertEqual("", self._git(root, "status", "--short"))

    def test_secret_before_debug_redaction_rename_and_local_main_fallback(self):
        with tempfile.TemporaryDirectory(prefix="pr-sec-") as td, \
             tempfile.TemporaryDirectory(prefix="pr-sec-out-") as out_td:
            root = Path(td)
            self._git(root, "init", "-b", "main")
            self._git(root, "config", "user.email", "local-test")
            self._git(root, "config", "user.name", "T")
            (root / "src").mkdir()
            (root / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
            self._git(root, "add", "src/a.py")
            self._git(root, "commit", "-m", "init main")

            secret_val = "sk_live_TESTONLY9876543210"
            jwt_val = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3OCJ9.abcDEF123456_7890"
            (root / "src" / "leak.js").write_text(
                f"console.log(\"api_key='{secret_val}'\");\n"
                f"const tok = '{jwt_val}';\n"
                "console.log('my_debug_value_12345');\n",
                encoding="utf-8",
            )
            (root / "auth").mkdir()
            self._git(root, "mv", "src/a.py", "auth/a.py")
            self._git(root, "add", "src/leak.js", "auth/a.py")
            self._git(root, "commit", "-m", "add commit on local main")

            # 无 origin/main 时，在 main 分支回退至 HEAD~1 而不输出 0 diff
            data = pvr.collect_pr_data(root)
            self.assertEqual("HEAD~1", data["base"])
            self.assertIn("auth", data["risk_tags"])

            html_path, md_path = pvr.write_reports(data, Path(out_td))
            md_txt = md_path.read_text(encoding="utf-8")
            html_txt = html_path.read_text(encoding="utf-8")
            self.assertIn("<已脱敏>", md_txt)
            self.assertIn("&lt;已脱敏&gt;", html_txt)
            for text in (md_txt, html_txt):
                self.assertIn("已脱敏", text)
                self.assertNotIn(secret_val, text)
                self.assertNotIn(jwt_val, text)
                self.assertNotIn("my_debug_value_12345", text)

            # 拒绝非法 --base 选项注入
            victim = root / "evil.txt"
            with self.assertRaises(RuntimeError):
                pvr.collect_pr_data(root, f"--output={victim}")
            self.assertFalse(victim.exists())

    def test_backtick_url_mixed_quote_redaction_cjk_quotepath_and_risk_total(self):
        with tempfile.TemporaryDirectory(prefix="pr-adv-") as td, \
             tempfile.TemporaryDirectory(prefix="pr-adv-out-") as out_td:
            root = Path(td)
            self._git(root, "init", "-b", "main")
            self._git(root, "config", "user.email", "local-test")
            self._git(root, "config", "user.name", "T")
            self._git(root, "config", "core.quotePath", "true")
            (root / "中文删库").mkdir()
            del_py = root / "中文删库" / "旧脚本.py"
            del_py.write_text("def old():\n    return 1\n", encoding="utf-8")
            self._git(root, "add", "中文删库/旧脚本.py")
            self._git(root, "commit", "-m", "init cn")

            self._git(root, "checkout", "-b", "feat/adv-security")
            self._git(root, "rm", "中文删库/旧脚本.py")

            bt_secret = "demoBt" + "Key1234567890"
            url_pass = "demoUrl" + "Pass9876"
            mixed_dbg = "mixedInner" + "DebugVal"
            bt_dbg = "tplSecret" + "DebugVal"
            raw_tok = "rawTok" + "Unquoted99"

            (root / "billing").mkdir()
            cn_billing = root / "billing" / "退款回调.py"
            cn_billing.write_text(
                f"k1 = `api_key={bt_secret}`\n"
                f'u = "https://dev:{url_pass}@staging.example.invalid/api"\n'
                f'console.log("it\'s {mixed_dbg}");\n'
                f"console.log(`tpl={bt_dbg}`);\n"
                f"console.log(token={raw_tok});\n",
                encoding="utf-8",
            )
            (root / "auth").mkdir()
            for idx in range(8):
                (root / "auth" / f"guard_{idx}.py").write_text(f"v = {idx}\n", encoding="utf-8")

            self._git(root, "add", "billing", "auth")
            self._git(root, "commit", "-m", "adv redaction and cn paths")

            data = pvr.collect_pr_data(root, "main")
            self.assertIn("billing", data["risk_tags"])
            self.assertIn("billing/退款回调.py", data["risk_tags"]["billing"])
            self.assertIn("delete", data["risk_tags"])
            self.assertIn("中文删库/旧脚本.py", data["risk_tags"]["delete"])
            self.assertEqual(8, len(data["risk_tags"]["auth"]))

            html_path, md_path = pvr.write_reports(data, Path(out_td))
            md_txt = md_path.read_text(encoding="utf-8")
            html_txt = html_path.read_text(encoding="utf-8")

            self.assertIn("等共 8 个文件", md_txt)
            self.assertIn("等共 8 个文件", html_txt)
            self.assertIn("billing/退款回调.py", md_txt)
            for text in (md_txt, html_txt):
                for leaked in (bt_secret, url_pass, mixed_dbg, bt_dbg, raw_tok):
                    self.assertNotIn(leaked, text)
                self.assertIn("已脱敏", text)
                self.assertIn("REDACTED", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
