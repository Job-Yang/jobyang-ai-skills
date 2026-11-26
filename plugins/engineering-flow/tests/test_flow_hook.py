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
            self.assertEqual("force_ask", out_ask["decision"])
            self.assertEqual("force_ask", act_ask)
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

    def test_16_open_spec_revise_unlocks_implement_spec_and_allows_spec_edit(self):
        with tempfile.TemporaryDirectory(prefix="ef-rev-") as td, tempfile.TemporaryDirectory(prefix="ef-s-") as sdir:
            repo = Path(td)
            self._init_repo(repo)
            wg.main(["init-local", "--root", str(repo)])
            spec = repo / ".agent-work" / "spec" / "checkout.md"
            spec.write_text("# Checkout\nSource: none\n## Steps\n1. S. After: none. Check: `true`\n", encoding="utf-8")
            with patch.dict(os.environ, {"ENGINEERING_FLOW_ALLOW_TMP": "1", "TMPDIR": sdir}):
                out, action, stage, _ = flow_hook.handle_pre_invocation({
                    "conversationId": "rev-1",
                    "cwd": str(repo),
                    "lastUserInput": "按刚才 Hand-off 清单调整一下 spec 的第 1 步，回流 implement-spec",
                })
                pre_tool, _, _, _ = flow_hook.handle_pre_tool_use({
                    "conversationId": "rev-1",
                    "cwd": str(repo),
                    "lastUserInput": "按刚才 Hand-off 清单调整一下 spec 的第 1 步，回流 implement-spec",
                    "toolCall": {"name": "edit_file", "args": {"Path": str(spec)}},
                })
            self.assertEqual("inject", action)
            self.assertEqual("implement-spec", stage)
            self.assertIn("implement-spec/SKILL.md", out["injectSteps"][0]["systemMessage"]["systemMessage"])
            self.assertEqual("allow", pre_tool["decision"])

    def test_17_multi_open_spec_picks_mentioned_slug_or_latest(self):
        with tempfile.TemporaryDirectory(prefix="ef-multi-") as td, tempfile.TemporaryDirectory(prefix="ef-s-") as sdir:
            repo = Path(td)
            self._init_repo(repo)
            wg.main(["init-local", "--root", str(repo)])
            s_alpha = repo / ".agent-work" / "spec" / "alpha-auth.md"
            s_zebra = repo / ".agent-work" / "spec" / "zeta-cache.md"
            s_alpha.write_text("# A\nSource: none\n## Steps\n1. A1. After: none. Check: `true`\n", encoding="utf-8")
            s_zebra.write_text("# Z\nSource: none\n## Steps\n1. Z1. After: none. Check: `true`\n", encoding="utf-8")
            # 确保 zeta-cache 更新时间严格晚于 alpha-auth
            os.utime(s_alpha, (1000.0, 1000.0))
            os.utime(s_zebra, (2000.0, 2000.0))
            with patch.dict(os.environ, {"ENGINEERING_FLOW_ALLOW_TMP": "1", "TMPDIR": sdir}):
                # 未指名 slug 时优先最新修改的 zeta-cache
                out_latest, _, _, _ = flow_hook.handle_pre_invocation({
                    "conversationId": "m-latest",
                    "cwd": str(repo),
                    "lastUserInput": "继续往下写",
                })
                # 明确指名 alpha-auth 时切中 alpha-auth
                out_named, _, _, _ = flow_hook.handle_pre_invocation({
                    "conversationId": "m-named",
                    "cwd": str(repo),
                    "lastUserInput": "开始实现 alpha-auth",
                })
            self.assertIn("zeta-cache.md", out_latest["injectSteps"][0]["systemMessage"]["systemMessage"])
            self.assertIn("alpha-auth.md", out_named["injectSteps"][0]["systemMessage"]["systemMessage"])

    def test_18_verify_cmd_covers_node_cargo_go_build_and_custom_patterns(self):
        with tempfile.TemporaryDirectory(prefix="ef-vcmd-") as td:
            repo = Path(td)
            self._init_repo(repo)
            for cmd in (
                "node --test tests/*.test.mjs",
                "npm run build",
                "cargo check --workspace",
                "go test ./...",
                "bazel test //pkg:all",
            ):
                self.assertTrue(flow_hook.matches_verify_cmd(cmd, repo), cmd)

            (repo / ".agent-work").mkdir(parents=True)
            (repo / ".agent-work" / "verify-patterns.txt").write_text("# comment\njust verify\n", encoding="utf-8")
            self.assertTrue(flow_hook.matches_verify_cmd("just verify --all", repo))
            self.assertFalse(flow_hook.matches_verify_cmd("echo hello", repo))

    def test_19_concept_qa_does_not_misroute_to_bugfix(self):
        with tempfile.TemporaryDirectory(prefix="ef-qa-") as td, tempfile.TemporaryDirectory(prefix="ef-s-") as sdir:
            repo = Path(td)
            self._init_repo(repo)
            with patch.dict(os.environ, {"ENGINEERING_FLOW_ALLOW_TMP": "1", "TMPDIR": sdir}):
                out1, act1, st1, _ = flow_hook.handle_pre_invocation({
                    "conversationId": "qa-1",
                    "cwd": str(repo),
                    "lastUserInput": "解释一下 TimeoutError 超时异常重试的原理是什么？",
                })
                out2, act2, st2, _ = flow_hook.handle_pre_invocation({
                    "conversationId": "qa-2",
                    "cwd": str(repo),
                    "lastUserInput": "接口报 TimeoutError 超时了，帮我查一下原因",
                })
            self.assertEqual({}, out1)
            self.assertEqual("allow_noop", act1)
            self.assertIsNone(st1)
            self.assertEqual("inject", act2)
            self.assertEqual("code-bugfix", st2)

    def test_20_stop_gate_excludes_workspace_guard_and_resets_verify_on_edit(self):
        with tempfile.TemporaryDirectory(prefix="ef-stop-reset-") as td, tempfile.TemporaryDirectory(prefix="ef-s-") as sdir:
            repo = Path(td)
            self._init_repo(repo)
            with patch.dict(os.environ, {"ENGINEERING_FLOW_ALLOW_TMP": "1", "TMPDIR": sdir}):
                # 1) workspace_guard / echo / || true / commit message 不算通过代码验证
                for non_verify in (
                    "python3 shared/scripts/workspace_guard.py verify-hash --spec s.md",
                    "pytest || true",
                    'git commit -m "fix ruff and pytest"',
                    "echo pytest",
                ):
                    self.assertFalse(flow_hook.matches_verify_cmd(non_verify, repo), non_verify)
                self.assertTrue(flow_hook.matches_verify_cmd("python3 tests/test_flow_hook.py", repo))

                # 2) 先改 a -> 跑 pytest 置绿 -> 再改 b 后必须重置 ran_verify_ok 并触发 Stop 拉回
                flow_hook.handle_post_tool_use({
                    "conversationId": "rst1",
                    "cwd": str(repo),
                    "toolCall": {"name": "edit_file", "args": {"Path": str(repo / "app.py")}},
                })
                flow_hook.handle_post_tool_use({
                    "conversationId": "rst1",
                    "cwd": str(repo),
                    "toolCall": {"name": "run_command", "args": {"CommandLine": "pytest"}},
                })
                flow_hook.handle_post_tool_use({
                    "conversationId": "rst1",
                    "cwd": str(repo),
                    "toolCall": {"name": "edit_file", "args": {"Path": str(repo / "other.py")}},
                })
                s_blocked, act_b, _, _ = flow_hook.handle_stop({
                    "conversationId": "rst1",
                    "cwd": str(repo),
                    "terminationReason": "NO_TOOL_CALL",
                    "fullyIdle": True,
                    "continuationActive": False,
                })
            self.assertEqual("continue", act_b)
            self.assertEqual("continue", s_blocked["decision"])

    def test_21_git_push_variants_cmd_key_dry_run_negation_and_cross_repo(self):
        with tempfile.TemporaryDirectory(prefix="ef-push2-") as td, \
             tempfile.TemporaryDirectory(prefix="ef-ng-") as non_git, \
             tempfile.TemporaryDirectory(prefix="ef-s-") as sdir:
            repo = Path(td)
            self._init_repo(repo)
            with patch.dict(os.environ, {"ENGINEERING_FLOW_ALLOW_TMP": "1", "TMPDIR": sdir}):
                bypass_cmds = [
                    "git -C repo push origin main",
                    "git --no-pager push",
                    "/usr/bin/git push origin main",
                    'bash -c "git push origin main"',
                    'echo "--dry-run" && git push origin main',
                    "git push --dry-run && git push origin main",
                ]
                for idx, cmd in enumerate(bypass_cmds):
                    out, act, _, _ = flow_hook.handle_pre_tool_use({
                        "conversationId": f"pv-{idx}",
                        "cwd": str(repo),
                        "lastUserInput": "帮我运行检查",
                        "toolCall": {"name": "run_command", "args": {"CommandLine": cmd}},
                    })
                    self.assertEqual("force_ask", out["decision"], cmd)
                    self.assertEqual("force_ask", act, cmd)

                # "Cmd" 字段与非授权语境/否定语境
                out_cmd_key, _, _, _ = flow_hook.handle_pre_tool_use({
                    "conversationId": "pv-cmd",
                    "cwd": str(repo),
                    "lastUserInput": "跑一下检查",
                    "toolCall": {"name": "shell_exec", "args": {"Cmd": "git push origin main"}},
                })
                out_neg, _, _, _ = flow_hook.handle_pre_tool_use({
                    "conversationId": "pv-neg",
                    "cwd": str(repo),
                    "lastUserInput": "不要 git push，我先自己看",
                    "toolCall": {"name": "run_command", "args": {"CommandLine": "git push origin main"}},
                })
                out_noun, _, _, _ = flow_hook.handle_pre_tool_use({
                    "conversationId": "pv-noun",
                    "cwd": str(repo),
                    "lastUserInput": "加一个 push 通知功能",
                    "toolCall": {"name": "run_command", "args": {"CommandLine": "git push origin main"}},
                })
                out_cross, _, _, _ = flow_hook.handle_pre_tool_use({
                    "conversationId": "pv-cross",
                    "cwd": non_git,
                    "lastUserInput": "看看状态",
                    "toolCall": {"name": "run_command", "args": {"CommandLine": f"git -C {repo} push origin main"}},
                })
                out_dry, _, _, _ = flow_hook.handle_pre_tool_use({
                    "conversationId": "pv-dry",
                    "cwd": str(repo),
                    "lastUserInput": "跑一下检查",
                    "toolCall": {"name": "run_command", "args": {"CommandLine": "git push --dry-run origin main"}},
                })
            self.assertEqual("force_ask", out_cmd_key["decision"])
            self.assertEqual("force_ask", out_neg["decision"])
            self.assertEqual("force_ask", out_noun["decision"])
            self.assertEqual("force_ask", out_cross["decision"])
            self.assertEqual("allow", out_dry["decision"])

    def test_22_extended_edit_tools_shell_write_locks_case_and_git_dir(self):
        with tempfile.TemporaryDirectory(prefix="ef-locks2-") as td, tempfile.TemporaryDirectory(prefix="ef-s-") as sdir:
            repo = Path(td)
            self._init_repo(repo)
            wg.main(["init-local", "--root", str(repo)])
            spec = repo / ".agent-work" / "spec" / "feat.md"
            spec.write_text("# Feat\nSource: none\n## Steps\n1. S. After: none.\n", encoding="utf-8")

            with patch.dict(os.environ, {"ENGINEERING_FLOW_ALLOW_TMP": "1", "TMPDIR": sdir}):
                flow_hook.handle_pre_invocation({
                    "conversationId": "lk-gw",
                    "cwd": str(repo),
                    "lastUserInput": "按计划写代码",
                })
                for name, args in (
                    ("delete_file", {"Path": str(spec)}),
                    ("edit_notebook", {"NotebookPath": str(spec)}),
                    ("apply_patch", {"patch": f"*** Begin Patch\n*** Update File: {spec}\n*** End Patch"}),
                    ("run_command", {"CommandLine": "sed -i '' 's/a/b/' .agent-work/spec/feat.md"}),
                ):
                    out, _, _, _ = flow_hook.handle_pre_tool_use({
                        "conversationId": "lk-gw",
                        "cwd": str(repo),
                        "lastUserInput": "按计划写代码",
                        "toolCall": {"name": name, "args": args},
                    })
                    self.assertEqual("deny", out["decision"], name)

                if sys.platform == "darwin":
                    out_case, _, _, _ = flow_hook.handle_pre_tool_use({
                        "conversationId": "lk-gw",
                        "cwd": str(repo),
                        "lastUserInput": "按计划写代码",
                        "toolCall": {"name": "edit_file", "args": {"Path": str(repo / ".Agent-Work" / "Spec" / "Feat.md")}},
                    })
                    self.assertEqual("deny", out_case["decision"])

                # 只读模式下禁止改 .git/、破坏性 git 和仓内重定向，允许 pytest / git diff / .agent-work
                flow_hook.handle_pre_invocation({
                    "conversationId": "lk-ro",
                    "cwd": str(repo),
                    "lastUserInput": "先别改代码，帮我 CR 一下",
                })
                for name, args in (
                    ("write_file", {"Path": str(repo / ".git" / "hooks" / "pre-commit")}),
                    ("run_command", {"CommandLine": "git reset --hard"}),
                    ("run_command", {"CommandLine": "echo x > app.py"}),
                ):
                    out_d, _, _, _ = flow_hook.handle_pre_tool_use({
                        "conversationId": "lk-ro",
                        "cwd": str(repo),
                        "lastUserInput": "先别改代码，帮我 CR 一下",
                        "toolCall": {"name": name, "args": args},
                    })
                    self.assertEqual("deny", out_d["decision"], f"{name}:{args}")
                for name, args in (
                    ("run_command", {"CommandLine": "pytest"}),
                    ("run_command", {"CommandLine": "git diff HEAD"}),
                    ("write_file", {"Path": str(repo / ".agent-work" / "notes.md")}),
                ):
                    out_a, _, _, _ = flow_hook.handle_pre_tool_use({
                        "conversationId": "lk-ro",
                        "cwd": str(repo),
                        "lastUserInput": "先别改代码，帮我 CR 一下",
                        "toolCall": {"name": name, "args": args},
                    })
                    self.assertEqual("allow", out_a["decision"], f"{name}:{args}")

    def test_23_cjk_word_boundaries_bugfix_ro_and_review_false_positive(self):
        with tempfile.TemporaryDirectory(prefix="ef-nlu2-") as td, tempfile.TemporaryDirectory(prefix="ef-s-") as sdir:
            repo = Path(td)
            self._init_repo(repo)
            with patch.dict(os.environ, {"ENGINEERING_FLOW_ALLOW_TMP": "1", "TMPDIR": sdir}):
                for text, exp_stage in (
                    ("帮我cr一下", "diff-review"),
                    ("有个bug跑不过", "code-bugfix"),
                    ("提个pr", "pr-prep"),
                    ("代码终审", "vdd"),
                ):
                    _, act, st, _ = flow_hook.handle_pre_invocation({
                        "conversationId": f"nlu-{exp_stage}",
                        "cwd": str(repo),
                        "lastUserInput": text,
                    })
                    self.assertEqual("inject", act, text)
                    self.assertEqual(exp_stage, st, text)

                # "查下原因" 无修复动词 -> bugfix-diagnose 只读锁生效
                flow_hook.handle_pre_invocation({
                    "conversationId": "diag-ro",
                    "cwd": str(repo),
                    "lastUserInput": "接口报错 500 了，帮我查下原因",
                })
                out_diag, _, _, _ = flow_hook.handle_pre_tool_use({
                    "conversationId": "diag-ro",
                    "cwd": str(repo),
                    "lastUserInput": "接口报错 500 了，帮我查下原因",
                    "toolCall": {"name": "edit_file", "args": {"Path": str(repo / "app.py")}},
                })
                self.assertEqual("deny", out_diag["decision"])

                # 现场踩坑回归：明确要求修问题但带 "自己review" 时，绝不误进只读 diff-review
                fp_prompt = "可以把明确的P0P1问题修掉，再起几个Agent让它们自己review"
                _, _, st_fp, _ = flow_hook.handle_pre_invocation({
                    "conversationId": "fp-rev",
                    "cwd": str(repo),
                    "lastUserInput": fp_prompt,
                })
                out_fp, _, _, _ = flow_hook.handle_pre_tool_use({
                    "conversationId": "fp-rev",
                    "cwd": str(repo),
                    "lastUserInput": fp_prompt,
                    "toolCall": {"name": "edit_file", "args": {"Path": str(repo / "app.py")}},
                })
                self.assertNotEqual("diff-review", st_fp)
                self.assertEqual("allow", out_fp["decision"])

                # 明确只读 + review 仍进 diff-review 只读锁
                flow_hook.handle_pre_invocation({
                    "conversationId": "true-rev",
                    "cwd": str(repo),
                    "lastUserInput": "先别改代码，把改动 review 一下",
                })
                out_tr, _, _, _ = flow_hook.handle_pre_tool_use({
                    "conversationId": "true-rev",
                    "cwd": str(repo),
                    "lastUserInput": "先别改代码，把改动 review 一下",
                    "toolCall": {"name": "edit_file", "args": {"Path": str(repo / "app.py")}},
                })
                self.assertEqual("deny", out_tr["decision"])

    def test_24_open_spec_missing_anchor_exemptions_and_fallback_stage(self):
        with tempfile.TemporaryDirectory(prefix="ef-spec2-") as td, tempfile.TemporaryDirectory(prefix="ef-s-") as sdir:
            repo = Path(td)
            self._init_repo(repo)
            wg.main(["init-local", "--root", str(repo)])
            spec = repo / ".agent-work" / "spec" / "work.md"

            with patch.dict(os.environ, {"ENGINEERING_FLOW_ALLOW_TMP": "1", "TMPDIR": sdir}):
                # 1) 缺 Source 锚点拦进 implement-spec
                spec.write_text("# No Anchor\n## Steps\n1. S. After: none.\n", encoding="utf-8")
                out_na, _, st_na, _ = flow_hook.handle_pre_invocation({
                    "conversationId": "sp-na",
                    "cwd": str(repo),
                    "lastUserInput": "开始实现",
                })
                self.assertEqual("implement-spec", st_na)
                self.assertIn("缺少有效 Source 锚点", out_na["injectSteps"][0]["systemMessage"]["systemMessage"])

                # 2) 合法开放 Spec 下，微改/vdd/概念问答 不落入 go-work
                spec.write_text("# Work\nSource: none\n## Steps\n1. S. After: none.\n", encoding="utf-8")
                _, _, st_micro, _ = flow_hook.handle_pre_invocation({
                    "conversationId": "sp-m",
                    "cwd": str(repo),
                    "lastUserInput": "改个typo",
                })
                _, _, st_vdd, _ = flow_hook.handle_pre_invocation({
                    "conversationId": "sp-v",
                    "cwd": str(repo),
                    "lastUserInput": "代码终审",
                })
                _, act_qa, st_qa, _ = flow_hook.handle_pre_invocation({
                    "conversationId": "sp-qa",
                    "cwd": str(repo),
                    "lastUserInput": "解释一下原理是什么",
                })
                self.assertEqual("micro", st_micro)
                self.assertEqual("vdd", st_vdd)
                self.assertEqual("allow_noop", act_qa)
                self.assertIsNone(st_qa)

                # 3) "不要修改 spec" 保持写死，"把第 2 步拆一下" 解锁，"未经 PreInvocation 直调 PreToolUse" 同样拦住
                flow_hook.handle_pre_invocation({
                    "conversationId": "sp-neg",
                    "cwd": str(repo),
                    "lastUserInput": "不要修改 spec，按计划实现",
                })
                out_neg, _, _, _ = flow_hook.handle_pre_tool_use({
                    "conversationId": "sp-neg",
                    "cwd": str(repo),
                    "lastUserInput": "不要修改 spec，按计划实现",
                    "toolCall": {"name": "edit_file", "args": {"Path": str(spec)}},
                })
                _, _, st_rev, _ = flow_hook.handle_pre_invocation({
                    "conversationId": "sp-rev2",
                    "cwd": str(repo),
                    "lastUserInput": "把第 2 步拆一下",
                })
                out_rev, _, _, _ = flow_hook.handle_pre_tool_use({
                    "conversationId": "sp-rev2",
                    "cwd": str(repo),
                    "lastUserInput": "把第 2 步拆一下",
                    "toolCall": {"name": "edit_file", "args": {"Path": str(spec)}},
                })
                out_direct, _, _, _ = flow_hook.handle_pre_tool_use({
                    "conversationId": "sp-direct-no-pre",
                    "cwd": str(repo),
                    "lastUserInput": "继续开发",
                    "toolCall": {"name": "edit_file", "args": {"Path": str(spec)}},
                })
                self.assertEqual("deny", out_neg["decision"])
                self.assertEqual("implement-spec", st_rev)
                self.assertEqual("allow", out_rev["decision"])
                self.assertEqual("deny", out_direct["decision"])

    def test_25_monorepo_jojo_butler_connection_check_and_repeat_prompt_stop(self):
        with tempfile.TemporaryDirectory(prefix="ef-misc-") as td, tempfile.TemporaryDirectory(prefix="ef-s-") as sdir:
            base = Path(td)
            # 1) 多 App JoJo monorepo（根仅 jojo_ai_guide.md + 子目录 .jojo）
            m1 = base / "mono1"
            m1.mkdir()
            self._init_repo(m1)
            (m1 / "jojo_ai_guide.md").write_text("# guide\n", encoding="utf-8")

            m2 = base / "mono2"
            sub_app = m2 / "apps" / "AppA"
            sub_app.mkdir(parents=True)
            self._init_repo(m2)
            (sub_app / ".jojo").mkdir()

            butler_ws = base / ".ai-butler" / "workspaces" / "goal1" / "task1"
            butler_ws.mkdir(parents=True)
            self._init_repo(butler_ws)

            normal_repo = base / "normal"
            normal_repo.mkdir()
            self._init_repo(normal_repo)

            with patch.dict(os.environ, {"ENGINEERING_FLOW_ALLOW_TMP": "1", "TMPDIR": sdir}):
                _, act_j1, _, rsn_j1 = flow_hook.handle_pre_invocation({
                    "conversationId": "j1",
                    "cwd": str(m1),
                    "lastUserInput": "修一个 bug",
                })
                _, act_j2, _, rsn_j2 = flow_hook.handle_pre_invocation({
                    "conversationId": "j2",
                    "cwd": str(sub_app),
                    "lastUserInput": "修一个 bug",
                })
                _, act_bw, _, rsn_bw = flow_hook.handle_pre_invocation({
                    "conversationId": "bw1",
                    "cwd": str(butler_ws),
                    "lastUserInput": "把代码 review 一下",
                })
                _, act_cc, st_cc, _ = flow_hook.handle_pre_invocation({
                    "conversationId": "cc1",
                    "cwd": str(normal_repo),
                    "lastUserInput": "帮我重构 connection_check 模块",
                })
                self.assertEqual(("bypass", "jojo_iloop_repo"), (act_j1, rsn_j1))
                self.assertEqual(("bypass", "jojo_iloop_repo"), (act_j2, rsn_j2))
                self.assertEqual(("bypass", "butler_workspace"), (act_bw, rsn_bw))
                self.assertEqual("inject", act_cc)
                self.assertEqual("implement-spec", st_cc)

                # 2) 两轮重复 "继续" 在允许 Stop 后应清空 stop_nudges，第二轮改代码仍触发 Stop
                for rnd in (1, 2):
                    flow_hook.handle_pre_invocation({
                        "conversationId": "rep-1",
                        "cwd": str(normal_repo),
                        "lastUserInput": "继续",
                    })
                    flow_hook.handle_post_tool_use({
                        "conversationId": "rep-1",
                        "cwd": str(normal_repo),
                        "toolCall": {"name": "edit_file", "args": {"Path": str(normal_repo / "app.py")}},
                    })
                    s1, _, _, _ = flow_hook.handle_stop({
                        "conversationId": "rep-1",
                        "cwd": str(normal_repo),
                        "terminationReason": "NO_TOOL_CALL",
                        "fullyIdle": True,
                        "continuationActive": False,
                    })
                    self.assertEqual("continue", s1["decision"], f"round {rnd}")
                    s2, act_s2, _, _ = flow_hook.handle_stop({
                        "conversationId": "rep-1",
                        "cwd": str(normal_repo),
                        "terminationReason": "NO_TOOL_CALL",
                        "fullyIdle": True,
                        "continuationActive": False,
                    })
                    self.assertEqual({}, s2, f"round {rnd}")
                    self.assertEqual("allow_stop", act_s2, f"round {rnd}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
