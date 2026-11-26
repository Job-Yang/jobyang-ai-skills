#!/usr/bin/env python3
"""Antigravity 原生插件生命周期钩子（纯 Python 3.9+ 标准库，异常一律 fail-open 放行）。

事件覆盖：
- PreInvocation: 毫秒级识别仓库上下文与当前开放 Spec，自动注入对应阶段与必读技能，避免断链或漏触发；
- PreToolUse:    拦截三条红线（未授权 git push、执行/盲审期直接改写开放 Spec、只读模式改仓库源码）；
- PostToolUse:   记录本轮改过的仓库代码文件与是否通过验证命令（测试/静态检查）；
- Stop:          改过业务代码却未跑通任何验证时有界拉回一次，防无证宣称完成。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = PLUGIN_ROOT.parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
SHARED_SCRIPTS_DIR = REPO_ROOT / "shared" / "scripts"

if str(SHARED_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_SCRIPTS_DIR))

try:
    import workspace_guard as wg  # type: ignore
except Exception:  # pragma: no cover - 独立复制到外部环境时的兜底
    wg = None  # type: ignore

SOURCE_RE = re.compile(r"^(?:Source|Feature):\s*`?([^`\s@]+)`?\s*@\s*`?([0-9a-fA-F]{7,40})`?")
SOURCE_NONE_RE = re.compile(r"^(?:Source|Feature):\s*none\b", re.I)

EDIT_TOOLS = {
    "edit_file",
    "write_file",
    "replace_file_content",
    "multi_replace_file_content",
    "write_to_file",
}
SHELL_TOOLS = {
    "run_command",
    "run_shell_command",
    "bash",
    "execute_command",
}

VERIFY_CMD_RE = re.compile(
    r"(?:^|[;&|\s/(])(?:python[0-9.]*\s+-m\s+)?(?:pytest|unittest|npm\s+test|pnpm\s+test|"
    r"yarn\s+test|cargo\s+test|go\s+test|run_all_tests(?:\.py)?|xcodebuild|swift\s+test|"
    r"eslint|tsc\b|ruff\b|mypy\b|flake8|library_doctor(?:\.py)?|workspace_guard(?:\.py)?)",
    re.I,
)
GIT_PUSH_RE = re.compile(r"(?:^|[;&|\s])git\s+push\b", re.I)
PUSH_AUTH_RE = re.compile(r"\bgit\s+push\b|\bpush\b|推送|推上去", re.I)
HIGH_RISK_PATH_RE = re.compile(
    r"(?:^|/)(?:auth|billing|payment|payments|migration|migrations)(?:/|$)|\.github/workflows/",
    re.I,
)

# 意图识别正则（全大白话覆盖）
MICRO_EDIT_RE = re.compile(
    r"微改|改个文案|改错字|修个错别字|只改一行|改一下注释|\btypo\b|改个配色|调个文案",
    re.I,
)
HEAVY_DEV_RE = re.compile(
    r"新功能|开发一个|新增.*功能|重构|跨文件|拆.*步骤|定接口|架构改造|实现.*功能|做个.*功能|写个.*模块",
    re.I,
)
READONLY_DIAG_RE = re.compile(
    r"先别改代码|不要改代码|先不改代码|别动代码|只排查|只看原因|只定位",
    re.I,
)
BUGFIX_RE = re.compile(
    r"报错|修下?.*bug|\bbug\b|崩溃|异常|回归|跑不通|挂了|丢单|超时|排查.*原因|定位.*问题|traceback|exception|panic",
    re.I,
)
DIFF_REVIEW_RE = re.compile(
    r"code\s*review|\bcr\b|看.*diff|审.*mr|审.*pr|看看.*改动|改动.*有没有问题|提交前自查|审查.*代码|帮我审",
    re.I,
)
PR_PREP_RE = re.compile(
    r"准备[提发]\s*pr|准备[提发]\s*mr|[提发]\s*pr|[写做]个?\s*pr|[写做]个?\s*mr|pr\s*说明|mr\s*说明|合入前.*检查|pr\s*导览|拆分\s*pr",
    re.I,
)
BATTLE_RE = re.compile(
    r"\bbattle\b|盲审|挑.*毛病|挑刺|隐藏坑|开工前.*把关|把把关",
    re.I,
)
NON_DEV_RE = re.compile(
    r"^[\s，。！？]*(?:你好|hi|hello|谢谢|只回复\s*ok|帮我翻译|写一?篇.*文章|润色一下|列出.*技能)",
    re.I,
)


def session_dir() -> Path:
    base = os.environ.get("ENGINEERING_FLOW_STATE_DIR") or os.environ.get("TMPDIR") or tempfile.gettempdir()
    return Path(base) / "engineering-flow-sessions"


def safe_conv_id(raw: str | None) -> str:
    val = (raw or "default").strip()
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", val)[:80]
    return cleaned or "default"


def session_path(conv_id: str | None) -> Path:
    return session_dir() / f"{safe_conv_id(conv_id)}.json"


def load_session(conv_id: str | None) -> dict:
    p = session_path(conv_id)
    if p.is_file():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (OSError, ValueError):
            pass
    return {
        "last_input_hash": "",
        "stage": None,
        "read_only_mode": None,
        "injected_keys": [],
        "edited_code_files": [],
        "ran_verify_ok": False,
        "touched_high_risk": False,
        "stop_nudges": 0,
    }


def save_session(conv_id: str | None, state: dict) -> None:
    try:
        p = session_path(conv_id)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass


def emit_trace(event: str, payload: dict, action: str, stage: str | None = None, detail: str = "") -> None:
    trace_file = os.environ.get("ENGINEERING_FLOW_TRACE_FILE", "").strip()
    if not trace_file:
        return
    try:
        tool_call = payload.get("toolCall") if isinstance(payload.get("toolCall"), dict) else {}
        entry = {
            "event": event,
            "hookEventName": payload.get("hookEventName"),
            "conversationId": payload.get("conversationId"),
            "cwd": payload.get("cwd"),
            "toolName": tool_call.get("name"),
            "action": action,
            "stage": stage,
            "detail": detail[:200],
        }
        tf = Path(trace_file)
        tf.parent.mkdir(parents=True, exist_ok=True)
        with tf.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def extract_cwd(payload: dict) -> Path | None:
    raw_cwd = payload.get("cwd")
    if isinstance(raw_cwd, str) and raw_cwd.strip():
        return Path(raw_cwd.strip())
    ws = payload.get("workspacePaths")
    if isinstance(ws, list) and ws and isinstance(ws[0], str) and ws[0].strip():
        return Path(ws[0].strip())
    return None


def is_tmp_path(p: Path) -> bool:
    if os.environ.get("ENGINEERING_FLOW_ALLOW_TMP") == "1":
        return False
    raw = str(p)
    try:
        res = str(p.resolve())
    except OSError:
        res = raw
    for s in (raw, res):
        if s in {"/tmp", "/private/tmp"} or s.startswith(("/tmp/", "/private/tmp/")):
            return True
    return False


def resolve_git_root(cwd: Path) -> Path | None:
    try:
        r = subprocess.run(
            ["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if r.returncode == 0 and r.stdout.strip():
            return Path(r.stdout.strip()).resolve()
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def find_open_specs(git_root: Path) -> list[Path]:
    specs: list[Path] = []
    for base in (git_root / "docs" / "spec", git_root / ".agent-work" / "spec"):
        if base.is_dir():
            for p in sorted(base.glob("*.md")):
                if p.is_file() and p.name.lower() != "readme.md":
                    specs.append(p)
    return specs


def should_bypass(payload: dict) -> tuple[bool, str, Path | None]:
    if os.environ.get("ENGINEERING_FLOW_DISABLED") == "1":
        return True, "env_disabled", None
    user_input = str(payload.get("lastUserInput") or "")
    if any(tok in user_input for tok in ("MALOU_CONNECTED", "ACP主脑", "connection_check")):
        return True, "acp_brain_probe", None

    cwd = extract_cwd(payload)
    if cwd is None or not cwd.exists():
        return True, "missing_cwd", None

    norm_cwd = str(cwd)
    norm_art = str(payload.get("artifactDirectoryPath") or "")
    if "brain-workspaces/judgment" in norm_cwd or "brain-workspaces/judgment" in norm_art:
        return True, "judgment_workspace", None
    if is_tmp_path(cwd):
        return True, "tmp_workspace", None

    git_root = resolve_git_root(cwd)
    if git_root is None:
        return True, "non_git", None
    if (git_root / ".agent-work" / "flow-disabled").exists():
        return True, "repo_flow_disabled", git_root

    open_specs = find_open_specs(git_root)
    if (git_root / ".jojo").is_dir() and not open_specs and not (git_root / ".agent-work" / "flow-state.json").is_file():
        return True, "jojo_iloop_repo", git_root

    return False, "", git_root


def check_spec_hash_and_progress(git_root: Path, spec_path: Path) -> tuple[str, list[int], list[int]]:
    if wg is not None:
        try:
            rel_src, want_sha = wg.resolve_source_ref(spec_path, git_root)
            if rel_src is None and want_sha is None:
                hash_status = "ok"
            elif not rel_src or not want_sha:
                hash_status = "missing_anchor"
            else:
                src_path = Path(rel_src)
                if not src_path.is_absolute():
                    cand_root = (git_root / rel_src).resolve()
                    cand_spec = (spec_path.parent / rel_src).resolve()
                    src_path = cand_root if cand_root.is_file() else cand_spec
                if not src_path.is_file():
                    hash_status = "drifted"
                else:
                    got_sha = wg.git_blob_sha1(src_path)
                    hash_status = "ok" if (got_sha.startswith(want_sha) or want_sha.startswith(got_sha)) else "drifted"

            slug = wg.infer_slug(spec_path, None)
            steps = wg.parse_steps(spec_path)
            landed_set = set(wg.read_git_trailer_steps(git_root, spec_path, slug))
            landed_set.update(wg.read_state_steps(wg.state_file_for(git_root, spec_path, slug)).keys())
            landed = sorted(landed_set)
            ready = [
                st["step"]
                for st in steps
                if st["step"] not in landed_set and all(d in landed_set for d in st["after"])
            ]
            return hash_status, landed, ready
        except Exception:
            pass

    lines = spec_path.read_text(encoding="utf-8", errors="ignore").splitlines()[:25]
    for ln in lines:
        s = ln.strip()
        if SOURCE_NONE_RE.match(s):
            return "ok", [], []
        m = SOURCE_RE.match(s)
        if m:
            src_cand = (git_root / m.group(1)).resolve()
            if not src_cand.is_file():
                return "drifted", [], []
            data = src_cand.read_bytes()
            sha = hashlib.sha1(f"blob {len(data)}\0".encode("utf-8") + data).hexdigest()
            return ("ok" if sha.startswith(m.group(2).lower()) else "drifted"), [], []
    return "ok", [], []


def skill_path(name: str) -> str:
    return str(SKILLS_DIR / name / "SKILL.md")


def detect_intent(user_input: str) -> tuple[str | None, str | None]:
    """无开放 Spec 时从大白话识别工程节点与只读护栏模式。"""
    text = user_input.strip()
    if not text or NON_DEV_RE.match(text):
        return None, None
    if MICRO_EDIT_RE.search(text) and not HEAVY_DEV_RE.search(text):
        return "micro", None

    if BUGFIX_RE.search(text):
        ro = "bugfix-diagnose" if READONLY_DIAG_RE.search(text) else None
        return "code-bugfix", ro
    if DIFF_REVIEW_RE.search(text):
        return "diff-review", "diff-review"
    if PR_PREP_RE.search(text):
        return "pr-prep", None
    if BATTLE_RE.search(text):
        return "spec-battle", None
    if HEAVY_DEV_RE.search(text):
        return "implement-spec", None
    return None, None


def handle_pre_invocation(payload: dict) -> tuple[dict, str, str | None, str]:
    bypass, reason, git_root = should_bypass(payload)
    if bypass or git_root is None:
        return {}, "bypass", None, reason

    conv_id = payload.get("conversationId")
    state = load_session(conv_id)
    user_input = str(payload.get("lastUserInput") or "")
    input_hash = hashlib.sha1(user_input.encode("utf-8")).hexdigest()[:12]

    if state.get("last_input_hash") != input_hash:
        state["last_input_hash"] = input_hash
        state["edited_code_files"] = []
        state["ran_verify_ok"] = False
        state["touched_high_risk"] = False
        state["stop_nudges"] = 0

    open_specs = find_open_specs(git_root)
    msg = ""
    stage: str | None = None
    read_only_mode: str | None = None
    spec_status = "none"

    if open_specs:
        spec = open_specs[0]
        rel_spec = str(spec.relative_to(git_root)) if git_root in spec.parents else str(spec)
        hash_status, landed, ready = check_spec_hash_and_progress(git_root, spec)
        spec_status = f"{rel_spec}:{hash_status}:{landed}:{ready}"
        if hash_status == "drifted":
            stage = "implement-spec"
            msg = (
                f"[engineering-flow] 检测到开放 Spec（{rel_spec}）的上游 Source 摘要已漂移，"
                f"禁止直接按过期步骤开工；请先阅读并执行 {skill_path('implement-spec')} 重算并同步 Spec。"
            )
        elif BUGFIX_RE.search(user_input):
            stage = "code-bugfix"
            read_only_mode = "bugfix-diagnose" if READONLY_DIAG_RE.search(user_input) else None
            msg = (
                f"[engineering-flow] 本轮为故障排查/修复任务，优先按红灯根因工作流执行；"
                f"请先阅读 {skill_path('code-bugfix')}（未过第 4 步证伪探针不改业务代码，密钥一律脱敏为 <REDACTED>）。"
            )
        elif DIFF_REVIEW_RE.search(user_input):
            stage = "diff-review"
            read_only_mode = "diff-review"
            msg = (
                f"[engineering-flow] 本轮为只读代码审查任务，严禁修改仓库代码；"
                f"请先阅读 {skill_path('diff-review')} 执行分级 CR 与 Skeptic 去误报。"
            )
        elif PR_PREP_RE.search(user_input):
            stage = "pr-prep"
            msg = (
                f"[engineering-flow] 本轮为 PR/MR 合入备料任务，禁止擅自 git push；"
                f"请先阅读 {skill_path('pr-prep')} 完成卫生检查、说明生成与临时目录视觉导览。"
            )
        elif BATTLE_RE.search(user_input):
            stage = "spec-battle"
            msg = (
                f"[engineering-flow] 检测到开放 Spec（{rel_spec}）进入盲审挑刺阶段，"
                f"已锁定 `landed={landed}`、`ready={ready}`；请先阅读 {skill_path('spec-battle')} 严格写死隔离（不直接改开放 Spec 正文）。"
            )
        else:
            stage = "go-work"
            msg = (
                f"[engineering-flow] 仓库存在开放 Spec（{rel_spec}），进度 `landed={landed}`、`ready={ready}`；"
                f"请先阅读 {skill_path('go-work')} 按步骤落地，严格守住只读 Spec 铁律（禁止直接修改开放 Spec）。"
            )
    else:
        stage, read_only_mode = detect_intent(user_input)
        spec_status = "no_open_spec"
        skill_hints = {
            "code-bugfix": f"[engineering-flow] 识别为报错排查/修 Bug 任务，请先阅读并遵循 {skill_path('code-bugfix')}。",
            "diff-review": f"[engineering-flow] 识别为只读代码审查任务，请先阅读并遵循 {skill_path('diff-review')}（只读不改源码）。",
            "pr-prep": f"[engineering-flow] 识别为发 PR/MR 备料任务，请先阅读并遵循 {skill_path('pr-prep')}（绝不擅自 git push）。",
            "spec-battle": f"[engineering-flow] 识别为动工前方案挑刺任务，请先阅读并遵循 {skill_path('spec-battle')}。",
            "implement-spec": f"[engineering-flow] 识别为新功能/跨文件改造/重构规划任务，动工前请先阅读并遵循 {skill_path('implement-spec')} 拆定接口与步骤。",
        }
        msg = skill_hints.get(stage or "", "")

    state["stage"] = stage
    state["read_only_mode"] = read_only_mode

    if not msg:
        save_session(conv_id, state)
        return {}, "allow_noop", stage, "no_msg"

    dedup_key = hashlib.sha1(f"{input_hash}|{stage}|{read_only_mode}|{spec_status}".encode("utf-8")).hexdigest()[:16]
    injected = list(state.get("injected_keys") or [])
    if dedup_key in injected:
        save_session(conv_id, state)
        return {}, "dedup_skip", stage, dedup_key

    injected.append(dedup_key)
    state["injected_keys"] = injected[-20:]
    save_session(conv_id, state)
    out = {
        "injectSteps": [
            {
                "systemMessage": {
                    "systemMessage": msg,
                }
            }
        ],
        "terminationBehavior": "",
    }
    return out, "inject", stage, dedup_key


def extract_tool_command(tool_call: dict) -> str:
    args = tool_call.get("args")
    if not isinstance(args, dict):
        return ""
    for k in ("CommandLine", "commandLine", "command", "cmd"):
        v = args.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def extract_tool_path(tool_call: dict, cwd: Path | None) -> Path | None:
    args = tool_call.get("args")
    if not isinstance(args, dict):
        return None
    for k in ("Path", "path", "TargetFile", "targetFile", "target_file", "file_path", "FilePath"):
        v = args.get(k)
        if isinstance(v, str) and v.strip():
            p = Path(v.strip())
            if not p.is_absolute() and cwd is not None:
                p = cwd / p
            try:
                return p.resolve()
            except OSError:
                return p
    return None


def is_open_spec_path(target: Path, git_root: Path) -> bool:
    try:
        rel = target.relative_to(git_root.resolve())
    except ValueError:
        return False
    parts = rel.parts
    if len(parts) >= 3 and parts[:2] == ("docs", "spec") and "archived" not in parts and rel.suffix.lower() == ".md":
        return True
    if len(parts) >= 3 and parts[:2] == (".agent-work", "spec") and "archived" not in parts and rel.suffix.lower() == ".md":
        return True
    return False


def is_repo_code_or_doc_mutable(target: Path, git_root: Path) -> bool:
    try:
        rel = target.relative_to(git_root.resolve())
    except ValueError:
        return False
    if rel.parts and rel.parts[0] in {".agent-work", ".git"}:
        return False
    return True


def handle_pre_tool_use(payload: dict) -> tuple[dict, str, str | None, str]:
    bypass, reason, git_root = should_bypass(payload)
    if bypass or git_root is None:
        return {"decision": "allow"}, "bypass", None, reason

    tool_call = payload.get("toolCall") if isinstance(payload.get("toolCall"), dict) else {}
    tool_name = str(tool_call.get("name") or "").strip().lower()
    conv_id = payload.get("conversationId")
    state = load_session(conv_id)
    stage = state.get("stage")
    ro_mode = state.get("read_only_mode")
    user_input = str(payload.get("lastUserInput") or "")

    # 兜底：若用户首句触发直接调工具而未经过 PreInvocation 状态同步
    if not ro_mode and user_input:
        _, detected_ro = detect_intent(user_input)
        ro_mode = detected_ro

    # 红线 1：未明确授权禁止直接 git push
    if tool_name in SHELL_TOOLS:
        cmd = extract_tool_command(tool_call)
        if cmd and GIT_PUSH_RE.search(cmd) and "--dry-run" not in cmd and not PUSH_AUTH_RE.search(user_input):
            return (
                {
                    "decision": "ask",
                    "reason": "engineering-flow 红线：本轮未见显式 push 授权，执行 git push 前需人工确认。",
                },
                "ask",
                stage,
                "git_push_guard",
            )

    # 红线 2 与红线 3：写操作隔离检查
    if tool_name in EDIT_TOOLS:
        target = extract_tool_path(tool_call, extract_cwd(payload))
        if target is not None:
            if stage in {"go-work", "spec-battle"} and is_open_spec_path(target, git_root):
                return (
                    {
                        "decision": "deny",
                        "reason": (
                            f"engineering-flow 写死隔离红线：当前处于 `{stage}` 阶段，禁止直接改写开放 Spec 正文；"
                            "请停下汇报阻塞或输出 Hand-off 清单交回 `implement-spec`。"
                        ),
                    },
                    "deny",
                    stage,
                    "open_spec_write_lock",
                )
            if ro_mode in {"diff-review", "bugfix-diagnose"} and is_repo_code_or_doc_mutable(target, git_root):
                return (
                    {
                        "decision": "deny",
                        "reason": (
                            f"engineering-flow 只读红线：当前处于 `{ro_mode}` 只读审查/诊断模式，"
                            "禁止修改业务源码或仓内文件。"
                        ),
                    },
                    "deny",
                    stage,
                    f"readonly_{ro_mode}",
                )

    return {"decision": "allow"}, "allow", stage, tool_name or "unknown"


def handle_post_tool_use(payload: dict) -> tuple[dict, str, str | None, str]:
    bypass, reason, git_root = should_bypass(payload)
    if bypass or git_root is None:
        return {}, "bypass", None, reason

    if payload.get("error"):
        return {}, "tool_failed", None, str(payload.get("error"))[:80]

    tool_call = payload.get("toolCall") if isinstance(payload.get("toolCall"), dict) else {}
    tool_name = str(tool_call.get("name") or "").strip().lower()
    conv_id = payload.get("conversationId")
    state = load_session(conv_id)
    stage = state.get("stage")
    changed = False

    if tool_name in EDIT_TOOLS:
        target = extract_tool_path(tool_call, extract_cwd(payload))
        if target is not None and is_repo_code_or_doc_mutable(target, git_root):
            try:
                rel = str(target.relative_to(git_root.resolve()))
            except ValueError:
                rel = str(target)
            if not rel.endswith(".md"):
                files = list(state.get("edited_code_files") or [])
                if rel not in files:
                    files.append(rel)
                    state["edited_code_files"] = files
                    changed = True
                if HIGH_RISK_PATH_RE.search(rel):
                    state["touched_high_risk"] = True
                    changed = True

    elif tool_name in SHELL_TOOLS:
        cmd = extract_tool_command(tool_call)
        if cmd and VERIFY_CMD_RE.search(cmd):
            state["ran_verify_ok"] = True
            changed = True

    if changed:
        save_session(conv_id, state)
    return {}, "recorded" if changed else "noop", stage, tool_name or "unknown"


def handle_stop(payload: dict) -> tuple[dict, str, str | None, str]:
    bypass, reason, git_root = should_bypass(payload)
    if bypass or git_root is None:
        return {}, "bypass", None, reason

    if payload.get("terminationReason") != "NO_TOOL_CALL":
        return {}, "skip_reason", None, str(payload.get("terminationReason"))
    if not payload.get("fullyIdle", True):
        return {}, "skip_not_idle", None, "bg_active"
    if payload.get("continuationActive", False):
        return {}, "skip_continuation", None, "already_continued"

    conv_id = payload.get("conversationId")
    state = load_session(conv_id)
    stage = state.get("stage")
    edited = list(state.get("edited_code_files") or [])
    if not edited or state.get("ran_verify_ok", False):
        return {}, "allow_stop", stage, "verified_or_clean"
    if int(state.get("stop_nudges", 0)) >= 1:
        return {}, "allow_stop", stage, "max_nudges_reached"

    state["stop_nudges"] = 1
    save_session(conv_id, state)
    files_preview = "、".join(edited[:3]) + (" 等" if len(edited) > 3 else "")
    risk_note = "（含高危路径，建议同步自查并标注需人工必审）" if state.get("touched_high_risk") else ""
    return (
        {
            "decision": "continue",
            "reason": (
                f"[engineering-flow 收口门禁] 本轮已修改代码文件（{files_preview}）"
                f"但尚未运行测试或静态验证命令{risk_note}；请先补跑最小验证命令并汇报真实结果后再结束。"
            ),
        },
        "continue",
        stage,
        "missing_verify",
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="engineering-flow Antigravity hook")
    ap.add_argument("--event", required=True, choices=["PreInvocation", "PreToolUse", "PostToolUse", "Stop", "SessionStart"])
    args = ap.parse_args(argv)

    fallback = {"decision": "allow"} if args.event == "PreToolUse" else {}
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        print(json.dumps(fallback, ensure_ascii=False))
        return 0

    event = args.event
    try:
        if event == "PreInvocation":
            out, action, stage, detail = handle_pre_invocation(payload)
        elif event == "PreToolUse":
            out, action, stage, detail = handle_pre_tool_use(payload)
        elif event == "PostToolUse":
            out, action, stage, detail = handle_post_tool_use(payload)
        elif event == "Stop":
            out, action, stage, detail = handle_stop(payload)
        else:
            out, action, stage, detail = {}, "noop", None, "session_start"
    except Exception as exc:
        emit_trace(event, payload, "fail_open_error", detail=str(exc))
        print(json.dumps(fallback, ensure_ascii=False))
        return 0

    emit_trace(event, payload, action, stage=stage, detail=detail)
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
