#!/usr/bin/env python3
"""engineering-flow 插件单元测试（纯标准库，临时目录与 session 隔离）。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PLUGIN_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = PLUGIN_DIR.parent.parent
HOOK_PATH = PLUGIN_DIR / "hooks" / "flow_hook.py"

sys.path.insert(0, str(PLUGIN_DIR / "hooks"))
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

import flow_hook  # noqa: E402
import workspace_guard as wg  # noqa: E402


class FlowHookTests(unittest.TestCase):
    def _git(self, cwd: Path, *args: str) -> str:
        r = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True)
        return r.stdout.strip()

    def _init_repo(self, root: Path) -> None:
        self._git(root, "init")
        self._git(root, "config", "user.email", "local-test")
        self._git(root, "config", "user.name", "Test")
        (root / "app.py").write_text("print('ok')\n", encoding="utf-8")
        self._git(root, "add", "app.py")
        self._git(root, "commit", "-m", "init")

    def _invoke(self, event: str, payload: dict, extra_env: dict | None = None) -> dict:
        env = {**os.environ, "ENGINEERING_FLOW_ALLOW_TMP": "1"}
        if extra_env:
            env.update(extra_env)
        proc = subprocess.run(
            [sys.executable, str(HOOK_PATH), "--event", event],
            input=json.dumps(payload, ensure_ascii=False),
            capture_output=True,
            text=True,
            env=env,
            cwd=str(PLUGIN_DIR),
        )
        self.assertEqual(0, proc.returncode, proc.stderr)
        return json.loads(proc.stdout.strip())

    def test_01_bypass_non_git_dir(self):
        with tempfile.TemporaryDirectory(prefix="ef-nongit-") as td:
            res = self._invoke("PreInvocation", {"cwd": td, "lastUserInput": "重构这个模块"})
            self.assertEqual({}, res)

    def test_02_bypass_judgment_workspace(self):
        with tempfile.TemporaryDirectory(prefix="ef-judge-") as td:
            jdir = Path(td) / "brain-workspaces" / "judgment-abc"
            jdir.mkdir(parents=True)
            with patch.dict(os.environ, {"ENGINEERING_FLOW_ALLOW_TMP": "1"}):
                out, action, _, reason = flow_hook.handle_pre_invocation({
                    "cwd": str(jdir),
                    "lastUserInput": "排查报错",
                })
            self.assertEqual({}, out)
            self.assertEqual("bypass", action)
            self.assertEqual("judgment_workspace", reason)

    def test_03_bypass_malou_connected_probe(self):
        with tempfile.TemporaryDirectory(prefix="ef-probe-") as td:
            self._init_repo(Path(td))
            with patch.dict(os.environ, {"ENGINEERING_FLOW_ALLOW_TMP": "1"}):
                out, action, _, reason = flow_hook.handle_pre_invocation({
                    "cwd": td,
                    "lastUserInput": "只回复 MALOU_CONNECTED，不执行工具。",
                })
            self.assertEqual({}, out)
            self.assertEqual("bypass", action)
            self.assertEqual("acp_brain_probe", reason)

    def test_04_bypass_jojo_ios_repo_when_no_open_spec(self):
        with tempfile.TemporaryDirectory(prefix="ef-jojo-") as td:
            repo = Path(td)
            self._init_repo(repo)
            (repo / ".jojo").mkdir()
            with patch.dict(os.environ, {"ENGINEERING_FLOW_ALLOW_TMP": "1"}):
                out, action, _, reason = flow_hook.handle_pre_invocation({
                    "cwd": td,
                    "lastUserInput": "这里报错了帮我修一下",
                })
            self.assertEqual({}, out)
            self.assertEqual("bypass", action)
            self.assertEqual("jojo_iloop_repo", reason)

    def test_05_bypass_env_disabled(self):
        with tempfile.TemporaryDirectory(prefix="ef-dis-") as td:
            self._init_repo(Path(td))
            with patch.dict(os.environ, {"ENGINEERING_FLOW_ALLOW_TMP": "1", "ENGINEERING_FLOW_DISABLED": "1"}):
                out, action, _, reason = flow_hook.handle_pre_invocation({
                    "cwd": td,
                    "lastUserInput": "这里报错了帮我查",
                })
            self.assertEqual({}, out)
            self.assertEqual("bypass", action)
            self.assertEqual("env_disabled", reason)

    def test_06_open_spec_injects_go_work_and_deduplicates(self):
        with tempfile.TemporaryDirectory(prefix="ef-spec-") as td, tempfile.TemporaryDirectory(prefix="ef-s-") as sdir:
            repo = Path(td)
            self._init_repo(repo)
            wg.main(["init-local", "--root", str(repo)])
            feat = repo / ".agent-work" / "feature" / "pay.md"
            feat.write_text("# Pay\nStatus: decided\n", encoding="utf-8")
            sha = wg.git_blob_sha1(feat)
            spec = repo / ".agent-work" / "spec" / "pay.md"
            spec.write_text(
                f"# Pay Spec\n\nSource: `.agent-work/feature/pay.md` @ `{sha}`\n\n"
                "## Steps\n\n1. Core. After: none. Check: `pytest`\n2. API. After: 1. Check: `pytest`\n",
                encoding="utf-8",
            )
            wg.main(["record-step", "--slug", "pay", "--step", "1", "--sha", "abc123", "--root", str(repo)])
            env = {"TMPDIR": sdir}
            r1 = self._invoke("PreInvocation", {"conversationId": "c-spec", "cwd": str(repo), "lastUserInput": "继续写"}, env)
            msg = r1["injectSteps"][0]["systemMessage"]["systemMessage"]
            self.assertIn("go-work/SKILL.md", msg)
            self.assertIn("ready=[2]", msg)
            r2 = self._invoke("PreInvocation", {"conversationId": "c-spec", "cwd": str(repo), "lastUserInput": "继续写"}, env)
            self.assertEqual({}, r2)

    def test_07_open_spec_hash_drift_halts_and_redirects_to_implement_spec(self):
        with tempfile.TemporaryDirectory(prefix="ef-drift-") as td, tempfile.TemporaryDirectory(prefix="ef-s-") as sdir:
            repo = Path(td)
            self._init_repo(repo)
            wg.main(["init-local", "--root", str(repo)])
            feat = repo / ".agent-work" / "feature" / "pay.md"
            feat.write_text("# Pay\nStatus: decided\n", encoding="utf-8")
            sha = wg.git_blob_sha1(feat)
            spec = repo / ".agent-work" / "spec" / "pay.md"
            spec.write_text(
                f"# Pay Spec\n\nSource: `.agent-work/feature/pay.md` @ `{sha}`\n\n"
                "## Steps\n\n1. Core. After: none. Check: `pytest`\n",
                encoding="utf-8",
            )
            feat.write_text("# Pay\nStatus: changed\n", encoding="utf-8")
            with patch.dict(os.environ, {"ENGINEERING_FLOW_ALLOW_TMP": "1", "TMPDIR": sdir}):
                out, action, stage, _ = flow_hook.handle_pre_invocation({
                    "conversationId": "c-drift",
                    "cwd": str(repo),
                    "lastUserInput": "开始按步骤写代码",
                })
            self.assertEqual("inject", action)
            self.assertEqual("implement-spec", stage)
            self.assertIn("已漂移", out["injectSteps"][0]["systemMessage"]["systemMessage"])

    def test_08_everyday_colloquial_routing_covers_all_stages(self):
        with tempfile.TemporaryDirectory(prefix="ef-route-") as td, tempfile.TemporaryDirectory(prefix="ef-s-") as sdir:
            repo = Path(td)
            self._init_repo(repo)
            cases = [
                ("登录接口报错 500 了，帮我查下原因", "code-bugfix"),
                ("提交前帮我看看刚才这些改动有没有问题", "diff-review"),
                ("功能写完了，帮我写个变更说明准备提 MR", "pr-prep"),
                ("开工前先帮我挑下这套设计方案的毛病", "spec-battle"),
                ("帮我重构一下计费模块，动工前先拆分规划", "implement-spec"),
            ]
            with patch.dict(os.environ, {"ENGINEERING_FLOW_ALLOW_TMP": "1", "TMPDIR": sdir}):
                for idx, (prompt, expected_stage) in enumerate(cases):
                    out, action, stage, _ = flow_hook.handle_pre_invocation({
                        "conversationId": f"r-{idx}",
                        "cwd": str(repo),
                        "lastUserInput": prompt,
                    })
                    self.assertEqual("inject", action, prompt)
                    self.assertEqual(expected_stage, stage, prompt)
                    self.assertIn(f"{expected_stage}/SKILL.md", out["injectSteps"][0]["systemMessage"]["systemMessage"])

    def test_09_micro_edit_and_non_dev_chat_bypass_injection(self):
        with tempfile.TemporaryDirectory(prefix="ef-micro-") as td, tempfile.TemporaryDirectory(prefix="ef-s-") as sdir:
            repo = Path(td)
            self._init_repo(repo)
            with patch.dict(os.environ, {"ENGINEERING_FLOW_ALLOW_TMP": "1", "TMPDIR": sdir}):
                out1, action1, stage1, _ = flow_hook.handle_pre_invocation({
                    "conversationId": "m1",
                    "cwd": str(repo),
                    "lastUserInput": "帮我改个文案错别字，只改一行",
                })
                out2, action2, stage2, _ = flow_hook.handle_pre_invocation({
                    "conversationId": "m2",
                    "cwd": str(repo),
                    "lastUserInput": "只回复 OK，不要改任何文件",
                })
            self.assertEqual({}, out1)
            self.assertEqual("micro", stage1)
            self.assertEqual("allow_noop", action1)
            self.assertEqual({}, out2)
            self.assertIsNone(stage2)
            self.assertEqual("allow_noop", action2)

    def test_10_pre_tool_use_git_push_ask_vs_authorized_allow(self):
        with tempfile.TemporaryDirectory(prefix="ef-push-") as td, tempfile.TemporaryDirectory(prefix="ef-s-") as sdir:
            repo = Path(td)
            self._init_repo(repo)
            with patch.dict(os.environ, {"ENGINEERING_FLOW_ALLOW_TMP": "1", "TMPDIR": sdir}):
                out_ask, act_ask, _, _ = flow_hook.handle_pre_tool_use({
                    "conversationId": "p1",
                    "cwd": str(repo),
                    "lastUserInput": "帮我运行测试检查下",
                    "toolCall": {"name": "run_command", "args": {"CommandLine": "git push origin main"}},
                })
                out_ok, act_ok, _, _ = flow_hook.handle_pre_tool_use({
                    "conversationId": "p1",
                    "cwd": str(repo),
                    "lastUserInput": "确认帮我 git push 到远端分支",
                    "toolCall": {"name": "run_command", "args": {"CommandLine": "git push origin main"}},
                })
            self.assertEqual("ask", out_ask["decision"])
            self.assertEqual("ask", act_ask)
            self.assertEqual("allow", out_ok["decision"])
            self.assertEqual("allow", act_ok)

    def test_11_pre_tool_use_write_lock_blocks_editing_open_spec(self):
        with tempfile.TemporaryDirectory(prefix="ef-lock-") as td, tempfile.TemporaryDirectory(prefix="ef-s-") as sdir:
            repo = Path(td)
            self._init_repo(repo)
            wg.main(["init-local", "--root", str(repo)])
            spec = repo / ".agent-work" / "spec" / "feat.md"
            spec.write_text("# Feat\nSource: none\n## Steps\n1. S. After: none. Check: `true`\n", encoding="utf-8")
            with patch.dict(os.environ, {"ENGINEERING_FLOW_ALLOW_TMP": "1", "TMPDIR": sdir}):
                flow_hook.handle_pre_invocation({
                    "conversationId": "wl1",
                    "cwd": str(repo),
                    "lastUserInput": "按计划写代码",
                })
                out_deny, act_deny, _, _ = flow_hook.handle_pre_tool_use({
                    "conversationId": "wl1",
                    "cwd": str(repo),
                    "lastUserInput": "按计划写代码",
                    "toolCall": {"name": "edit_file", "args": {"Path": str(spec)}},
                })
                out_code, act_code, _, _ = flow_hook.handle_pre_tool_use({
                    "conversationId": "wl1",
                    "cwd": str(repo),
                    "lastUserInput": "按计划写代码",
                    "toolCall": {"name": "edit_file", "args": {"Path": str(repo / "app.py")}},
                })
            self.assertEqual("deny", out_deny["decision"])
            self.assertEqual("deny", act_deny)
            self.assertEqual("allow", out_code["decision"])
            self.assertEqual("allow", act_code)

    def test_12_pre_tool_use_readonly_blocks_source_edit_but_allows_agent_work(self):
        with tempfile.TemporaryDirectory(prefix="ef-ro-") as td, tempfile.TemporaryDirectory(prefix="ef-s-") as sdir:
            repo = Path(td)
            self._init_repo(repo)
            with patch.dict(os.environ, {"ENGINEERING_FLOW_ALLOW_TMP": "1", "TMPDIR": sdir}):
                flow_hook.handle_pre_invocation({
                    "conversationId": "ro1",
                    "cwd": str(repo),
                    "lastUserInput": "这里报错先别改代码，只排查原因",
                })
                out_deny, _, _, _ = flow_hook.handle_pre_tool_use({
                    "conversationId": "ro1",
                    "cwd": str(repo),
                    "lastUserInput": "这里报错先别改代码，只排查原因",
                    "toolCall": {"name": "write_file", "args": {"Path": str(repo / "app.py")}},
                })
                out_notes, _, _, _ = flow_hook.handle_pre_tool_use({
                    "conversationId": "ro1",
                    "cwd": str(repo),
                    "lastUserInput": "这里报错先别改代码，只排查原因",
                    "toolCall": {"name": "write_file", "args": {"Path": str(repo / ".agent-work" / "diag.md")}},
                })
            self.assertEqual("deny", out_deny["decision"])
            self.assertEqual("allow", out_notes["decision"])

    def test_13_stop_gate_continues_once_when_unverified_and_respects_continuation_active(self):
        with tempfile.TemporaryDirectory(prefix="ef-stop1-") as td, tempfile.TemporaryDirectory(prefix="ef-s-") as sdir:
            repo = Path(td)
            self._init_repo(repo)
            with patch.dict(os.environ, {"ENGINEERING_FLOW_ALLOW_TMP": "1", "TMPDIR": sdir}):
                flow_hook.handle_pre_invocation({
                    "conversationId": "st1",
                    "cwd": str(repo),
                    "lastUserInput": "修下这个计费 bug",
                })
                flow_hook.handle_post_tool_use({
                    "conversationId": "st1",
                    "cwd": str(repo),
                    "toolCall": {"name": "edit_file", "args": {"Path": str(repo / "billing" / "charge.py")}},
                })
                out1, act1, _, _ = flow_hook.handle_stop({
                    "conversationId": "st1",
                    "cwd": str(repo),
                    "terminationReason": "NO_TOOL_CALL",
                    "fullyIdle": True,
                    "continuationActive": False,
                })
                out2, act2, _, rsn2 = flow_hook.handle_stop({
                    "conversationId": "st1",
                    "cwd": str(repo),
                    "terminationReason": "NO_TOOL_CALL",
                    "fullyIdle": True,
                    "continuationActive": True,
                })
                out3, act3, _, rsn3 = flow_hook.handle_stop({
                    "conversationId": "st1",
                    "cwd": str(repo),
                    "terminationReason": "NO_TOOL_CALL",
                    "fullyIdle": True,
                    "continuationActive": False,
                })
            self.assertEqual("continue", out1["decision"])
            self.assertIn("高危路径", out1["reason"])
            self.assertEqual("continue", act1)
            self.assertEqual({}, out2)
            self.assertEqual("skip_continuation", act2)
            self.assertEqual({}, out3)
            self.assertEqual("allow_stop", act3)
            self.assertEqual("max_nudges_reached", rsn3)

    def test_14_stop_gate_allows_after_passing_test_command_only(self):
        with tempfile.TemporaryDirectory(prefix="ef-stop2-") as td, tempfile.TemporaryDirectory(prefix="ef-s-") as sdir:
            repo = Path(td)
            self._init_repo(repo)
            with patch.dict(os.environ, {"ENGINEERING_FLOW_ALLOW_TMP": "1", "TMPDIR": sdir}):
                flow_hook.handle_post_tool_use({
                    "conversationId": "st2",
                    "cwd": str(repo),
                    "toolCall": {"name": "edit_file", "args": {"Path": str(repo / "app.py")}},
                })
                # 失败测试不得放行
                flow_hook.handle_post_tool_use({
                    "conversationId": "st2",
                    "cwd": str(repo),
                    "error": "exit status 1",
                    "toolCall": {"name": "run_command", "args": {"CommandLine": "pytest"}},
                })
                s_fail, _, _, _ = flow_hook.handle_stop({
                    "conversationId": "st2",
                    "cwd": str(repo),
                    "terminationReason": "NO_TOOL_CALL",
                    "fullyIdle": True,
                    "continuationActive": False,
                })
                # 重开新会话模拟成功测试后放行
                flow_hook.handle_post_tool_use({
                    "conversationId": "st3",
                    "cwd": str(repo),
                    "toolCall": {"name": "edit_file", "args": {"Path": str(repo / "app.py")}},
                })
                flow_hook.handle_post_tool_use({
                    "conversationId": "st3",
                    "cwd": str(repo),
                    "toolCall": {"name": "run_command", "args": {"CommandLine": "pytest tests/test_app.py"}},
                })
                s_pass, _, _, _ = flow_hook.handle_stop({
                    "conversationId": "st3",
                    "cwd": str(repo),
                    "terminationReason": "NO_TOOL_CALL",
                    "fullyIdle": True,
                    "continuationActive": False,
                })
            self.assertEqual("continue", s_fail["decision"])
            self.assertEqual({}, s_pass)

    def test_15_malformed_json_and_tmp_path_fail_open(self):
        proc = subprocess.run(
            [sys.executable, str(HOOK_PATH), "--event", "PreToolUse"],
            input="{bad json",
            capture_output=True,
            text=True,
            cwd=str(PLUGIN_DIR),
        )
        self.assertEqual(0, proc.returncode)
        self.assertEqual({"decision": "allow"}, json.loads(proc.stdout.strip()))

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ENGINEERING_FLOW_ALLOW_TMP", None)
            self.assertTrue(flow_hook.is_tmp_path(Path("/tmp/demo-repo")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
