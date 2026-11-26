#!/usr/bin/env python3
"""Antigravity 原生插件生命周期钩子（纯 Python 3.9+ 标准库，异常一律 fail-open 放行）。

事件覆盖：
- PreInvocation: 毫秒级识别仓库上下文与当前开放 Spec，自动注入对应阶段与必读技能，避免断链或漏触发；
- PreToolUse:    拦截三条红线（未授权 git push、执行/盲审期修改开放 Spec、只读模式改仓库源码）；
- PostToolUse:   记录本轮改过的仓库代码文件（改动代码即清零验证态），并仅在真实验证命令通过后置绿；
- Stop:          改过业务代码却未在最近改动后跑通任何验证时有界拉回一次，防无证宣称完成。
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import re
import shlex
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

SOURCE_RE = re.compile(r"^(?:Source|Feature):\s*`?([^`\n@]+?)`?\s*@\s*`?([0-9a-fA-F]{7,40})`?\s*$")
SOURCE_NONE_RE = re.compile(r"^(?:Source|Feature):\s*none\b", re.I)

EDIT_TOOLS = {
    "edit_file",
    "write_file",
    "replace_file_content",
    "multi_replace_file_content",
    "write_to_file",
    "delete_file",
    "edit_notebook",
    "notebook_edit",
    "update_file",
    "apply_patch",
    "code_action",
    "file_change",
    "move",
    "delete_directory",
    "create_file",
    "str_replace_editor",
}
SHELL_TOOLS = {
    "run_command",
    "run_shell_command",
    "bash",
    "execute_command",
    "shell_exec",
}

VERIFY_CMD_START_RE = re.compile(
    r"^(?:(?:env|time|nice|nohup)\s+|[A-Za-z_][A-Za-z0-9_]*=\S+\s+)*"
    r"(?:(?:python[0-9.]*\s+-m\s+)?(?:pytest|unittest)\b|"
    r"python[0-9.]*\s+(?:\S+/)?test_[^\s/]+\.py\b|"
    r"node\s+(?:--test\b|\S+\.test\.(?:mjs|cjs|js|ts)\b)|"
    r"(?:npx\s+)?(?:vitest|jest|eslint|tsc)\b|"
    r"(?:npm|pnpm|yarn|bun)\s+(?:run\s+)?(?:test|build|lint|typecheck|check)\b|bun\s+test\b|"
    r"cargo\s+(?:test|check|build|clippy)\b|go\s+(?:test|build|vet)\b|swift\s+(?:test|build)\b|xcodebuild\b|"
    r"(?:\./)?gradlew\s+(?:test|check|build)\b|gradle\s+(?:test|check|build)\b|"
    r"(?:\./)?mvnw\s+(?:test|verify|package)\b|mvn\s+(?:test|verify)\b|"
    r"make\s+(?:test|check|lint)\b|cmake\s+--build\b|ctest\b|bazel\s+(?:test|build)\b|"
    r"buck2?\s+(?:test|build)\b|jojo\s+(?:build|test)\b|dotnet\s+test\b|"
    r"ruff\b|mypy\b|flake8\b|(?:python[0-9.]*\s+)?(?:\S+/)?(?:library_doctor|run_all_tests)(?:\.py)?\b)",
    re.I,
)
DISALLOWED_VERIFY_TAIL_RE = re.compile(r"\|\|\s*(?:true|:)\s*(?:$|[;&|\n])")
DISALLOWED_NON_VERIFY_HEAD_RE = re.compile(
    r"^(?:echo|printf|cat|head|tail|less|more|rg|grep|ag|find|ls|git\s+(?:commit|add|tag|log|status))\b",
    re.I,
)

# git top-level options (0-arg vs 1-arg before subcommand)
GIT_ZERO_ARG_FLAGS = {
    "--no-pager", "--paginate", "-p", "-P", "--bare", "--literal-pathspecs",
    "--glob-pathspecs", "--noglob-pathspecs", "--icase-pathspecs",
    "--no-replace-objects", "--no-lazy-fetch", "--no-optional-locks",
}
GIT_ONE_ARG_FLAGS = {"-c", "-C", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--super-prefix", "--config-env"}

SPEC_REVISE_RE = re.compile(
    r"(?:修改|调整|更新|重拆|回流|重写|修订).{0,24}(?:spec|方案|步骤|计划|第\s*\d+\s*步)|"
    r"第\s*\d+\s*步.{0,24}(?:改|调整|拆|补|删)|按.*hand-?off.*(?:改|修|更新)|回流\s*implement-spec",
    re.I,
)
NEG_SPEC_REVISE_RE = re.compile(
    r"(?:不要|别|勿|禁止|不能|不可|切勿)\s*(?:修改|改|动|编辑)\s*(?:spec|开放\s*spec)",
    re.I,
)
CONCEPT_QA_RE = re.compile(
    r"^(?:请?\s*(?:解释|说明|介绍|讲讲|聊聊|对比|调研)|什么是)|"
    r"(?:原理是什么|有什么区别|是什么意思|设计成这样)[？?\s]*$",
    re.I,
)
WHY_QUESTION_RE = re.compile(r"为什么.*(?:报错|异常|超时|失败)|怎么回事", re.I)
BUGFIX_ACTION_RE = re.compile(
    r"帮我查|帮我修|修一下|排查|定位|跑不通|跑不过|挂了|丢单|失败了|接口报错|线上.*(?:异常|超时|报错)",
    re.I,
)
FIX_VERB_RE = re.compile(r"(?:修|改|解决|修复|(?<![A-Za-z0-9_])fix(?![A-Za-z0-9_])|(?<![A-Za-z0-9_])patch(?![A-Za-z0-9_]))", re.I)
DIAG_VERB_RE = re.compile(r"排查|查下|查一下|查查|定位|为什么|看看.*原因|只看", re.I)

NEG_PUSH_RE = re.compile(
    r"(?:不要|别|勿|禁|不可|不能|切勿|无需|不用)\s*(?:.{0,6})?(?:git\s*push|(?<![A-Za-z0-9_])push(?![A-Za-z0-9_])|推送|推上去)",
    re.I,
)
POS_PUSH_RE = re.compile(
    r"\bgit\s+push\b|帮我\s*(?:push|推送)|确认.*(?:push|推送)|"
    r"把.{0,6}(?:代码|改动|提交|分支).{0,6}推(?:送|上去)|(?<![A-Za-z0-9_])push\s+(?:to|origin|main|master|HEAD)\b",
    re.I,
)
HIGH_RISK_PATH_RE = re.compile(
    r"(?:^|/)(?:auth|billing|payment|payments|migration|migrations)(?:/|$)|\.github/workflows/",
    re.I,
)

# 意图识别正则（使用 ASCII 非字母数字边界以兼容中文无空格连写）
MICRO_EDIT_RE = re.compile(
    r"微改|改个文案|改错字|修个错别字|只改一行|改一下注释|(?<![A-Za-z0-9_])typo(?![A-Za-z0-9_])|改个配色|调个文案",
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
    r"报错|修下?.*bug|(?<![A-Za-z0-9_])bug(?![A-Za-z0-9_])|崩溃|异常|回归|跑不通|跑不过|失败了|挂了|丢单|超时|排查|定位|traceback|exception|panic",
    re.I,
)
DIFF_REVIEW_RE = re.compile(
    r"(?<![A-Za-z0-9_])review(?![A-Za-z0-9_])|(?<![A-Za-z0-9_])cr(?![A-Za-z0-9_])|"
    r"看[下看]?.*diff|审[下查]?.*(?:mr|pr|代码|改动)|看看.*改动|改动.*有没有问题|提交前自查|帮我审",
    re.I,
)
EXPLICIT_READONLY_RE = re.compile(
    r"只读|先别改|不要改|先不改|别动代码|不改代码|只审不改|只看不改",
    re.I,
)
MUTATION_INTENT_RE = re.compile(
    r"(?:修掉|修复|修一下|修下|把.{0,12}(?:问题|bug|缺陷|毛病)修|修改代码|改代码|改写|改掉|改完|直接改|开始改|继续改|继续修|"
    r"落地实现|写代码|编写|重构|新增.{0,8}功能|(?<![A-Za-z0-9_])(?:fix|patch|implement|refactor)(?![A-Za-z0-9_]))",
    re.I,
)
SELF_REVIEW_ONLY_RE = re.compile(r"(?:自己|互相|相互|自我)\s*review(?![A-Za-z0-9_])", re.I)
CONCRETE_REVIEW_TARGET_RE = re.compile(
    r"code\s+review|(?<![A-Za-z0-9_])cr(?![A-Za-z0-9_])|看[下看]?.*diff|"
    r"审[下查]?.*(?:mr|pr|代码|改动)|看看.*改动|改动.*有没有问题|提交前自查|帮我审|"
    r"帮我\s*review|review\s*(?:下|一下|这个|这段|代码|改动|pr|mr|diff|commit|分支)",
    re.I,
)
PR_PREP_RE = re.compile(
    r"准备[提发]个?\s*(?:pr|mr)|[提发][一个]?\s*(?:pr|mr)|[写做]个?\s*(?:pr|mr)|(?:pr|mr)\s*说明|合入前.*检查|(?:pr|mr)\s*导览|拆分\s*pr",
    re.I,
)
BATTLE_RE = re.compile(
    r"(?<![A-Za-z0-9_])battle(?![A-Za-z0-9_])|盲审|挑.*毛病|挑刺|隐藏坑|开工前.*把关|把把关",
    re.I,
)
VDD_RE = re.compile(
    r"代码终审|验一下完成度|确认有没有过度修改|实证终审|跑[个下]?.{0,4}(?<![A-Za-z0-9_])vdd(?![A-Za-z0-9_])",
    re.I,
)
NON_DEV_RE = re.compile(
    r"^[\s，。！？]*(?:你好|hi|hello|谢谢|只回复\s*ok|帮我翻译|写一?篇.*文章|润色一下|列出.*技能)[！!。.\s]*$",
    re.I,
)

DESTRUCTIVE_GIT_SUBCMDS = {"checkout", "switch", "reset", "clean", "stash", "restore", "apply", "am", "rebase", "cherry-pick"}


def _is_darwin() -> bool:
    return sys.platform == "darwin"


def _norm_case(s: str) -> str:
    return s.lower() if _is_darwin() else s


def session_dir() -> Path:
    base = os.environ.get("ENGINEERING_FLOW_STATE_DIR") or os.environ.get("TMPDIR") or tempfile.gettempdir()
    return Path(base) / "engineering-flow-sessions"


def safe_conv_id(raw: str | None) -> str:
    val = (raw or "default").strip()
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", val)[:80]
    return cleaned or "default"


def session_path(conv_id: str | None) -> Path:
    return session_dir() / f"{safe_conv_id(conv_id)}.json"


def _default_state() -> dict:
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


@contextlib.contextmanager
def _session_lock(conv_id: str | None):
    sdir = session_dir()
    sdir.mkdir(parents=True, exist_ok=True)
    lock_p = sdir / f"{safe_conv_id(conv_id)}.lock"
    fh = lock_p.open("a+", encoding="utf-8")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        finally:
            fh.close()


def _load_session_unlocked(conv_id: str | None) -> dict:
    p = session_path(conv_id)
    if p.is_file():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (OSError, ValueError):
            pass
    return _default_state()


def load_session(conv_id: str | None) -> dict:
    try:
        with _session_lock(conv_id):
            return _load_session_unlocked(conv_id)
    except OSError:
        return _load_session_unlocked(conv_id)


def _save_session_unlocked(conv_id: str | None, state: dict) -> None:
    p = session_path(conv_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{p.stem}-", suffix=".tmp", dir=str(p.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tfh:
            tfh.write(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
        os.replace(tmp_name, p)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise


def save_session(conv_id: str | None, state: dict) -> None:
    try:
        with _session_lock(conv_id):
            _save_session_unlocked(conv_id, state)
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
    target = cwd if cwd.is_dir() else cwd.parent
    if not target.exists():
        return None
    try:
        r = subprocess.run(
            ["git", "-C", str(target), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if r.returncode == 0 and r.stdout.strip():
            return Path(r.stdout.strip()).resolve()
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def has_jojo_context(git_root: Path, cwd: Path) -> bool:
    if (git_root / ".jojo").is_dir() or (git_root / "jojo_ai_guide.md").is_file():
        return True
    try:
        cur = cwd.resolve()
        root_res = git_root.resolve()
        for candidate in (cur, *cur.parents):
            if (candidate / ".jojo").is_dir():
                return True
            if candidate == root_res:
                break
    except OSError:
        pass
    return False


def find_open_specs(git_root: Path) -> list[Path]:
    specs: list[Path] = []
    for base in (git_root / "docs" / "spec", git_root / ".agent-work" / "spec"):
        if base.is_dir():
            for p in sorted(base.glob("*.md")):
                if p.is_file() and p.name.lower() != "readme.md":
                    specs.append(p)
    return specs


def pick_active_spec(open_specs: list[Path], user_input: str) -> Path:
    low_input = user_input.lower()
    for p in open_specs:
        slug = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", p.stem).lower()
        if slug and slug in low_input:
            return p
    return max(open_specs, key=lambda p: p.stat().st_mtime)


def should_bypass(payload: dict) -> tuple[bool, str, Path | None]:
    if os.environ.get("ENGINEERING_FLOW_DISABLED") == "1":
        return True, "env_disabled", None
    user_input = str(payload.get("lastUserInput") or "")
    if any(tok in user_input for tok in ("只回复 MALOU_CONNECTED", "MALOU_CONNECTED", "ACP主脑")):
        return True, "acp_brain_probe", None

    cwd = extract_cwd(payload)
    if cwd is None or not cwd.exists():
        return True, "missing_cwd", None

    norm_cwd = _norm_case(str(cwd))
    norm_art = _norm_case(str(payload.get("artifactDirectoryPath") or ""))
    if "brain-workspaces/judgment" in norm_cwd or "brain-workspaces/judgment" in norm_art:
        return True, "judgment_workspace", None
    if ".ai-butler/workspaces/" in norm_cwd or "/.ai-butler/workspaces" in norm_cwd:
        return True, "butler_workspace", None
    if is_tmp_path(cwd):
        return True, "tmp_workspace", None

    git_root = resolve_git_root(cwd)
    if git_root is None:
        return True, "non_git", None
    if (git_root / ".agent-work" / "flow-disabled").exists():
        return True, "repo_flow_disabled", git_root

    open_specs = find_open_specs(git_root)
    if has_jojo_context(git_root, cwd) and not open_specs:
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
                try:
                    src_path.resolve().relative_to(git_root.resolve())
                except ValueError:
                    hash_status = "drifted"
                    src_path = Path("__outside__")
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
            try:
                src_cand.relative_to(git_root.resolve())
            except ValueError:
                return "drifted", [], []
            if not src_cand.is_file():
                return "drifted", [], []
            data = src_cand.read_bytes()
            sha = hashlib.sha1(f"blob {len(data)}\0".encode("utf-8") + data).hexdigest()
            return ("ok" if sha.startswith(m.group(2).lower()) else "drifted"), [], []
    return "missing_anchor", [], []


def split_shell_segments(cmd: str) -> list[str]:
    segments = [s.strip() for s in re.split(r"(?:\s*(?:&&|\|\||;|\n|\|)\s*)", cmd) if s.strip()]
    out = list(segments)
    for seg in segments:
        try:
            toks = shlex.split(seg)
        except ValueError:
            toks = seg.split()
        # 剥离 sh -c / bash -c / zsh -c 内联命令
        for idx, tok in enumerate(toks[:-1]):
            if Path(tok).name in {"sh", "bash", "zsh"} and toks[idx + 1] in {"-c", "-lc"} and idx + 2 < len(toks):
                out.extend(split_shell_segments(toks[idx + 2]))
        # 剥离简单 $(...) 嵌套
        for m in re.finditer(r"\$\(([^()]+)\)", seg):
            out.extend(split_shell_segments(m.group(1)))
    return out


def parse_git_subcommand(seg: str) -> tuple[str | None, list[str]]:
    try:
        toks = shlex.split(seg)
    except ValueError:
        toks = seg.split()
    if not toks:
        return None, []
    i = 0
    while i < len(toks):
        base = Path(toks[i]).name
        if toks[i] in {"env", "sudo", "command", "nohup", "time"} or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=.*$", toks[i]):
            i += 1
            continue
        if base == "git":
            i += 1
            while i < len(toks):
                t = toks[i]
                if t in GIT_ZERO_ARG_FLAGS:
                    i += 1
                    continue
                if t in GIT_ONE_ARG_FLAGS:
                    i += 2
                    continue
                if any(t.startswith(f + "=") for f in GIT_ONE_ARG_FLAGS) or re.match(r"^-[Cc]\S+", t):
                    i += 1
                    continue
                if t.startswith("-"):
                    i += 1
                    continue
                return t.lower(), toks[i + 1 :]
        break
    return None, []


def has_unauthorized_git_push(cmd: str, user_input: str) -> bool:
    for seg in split_shell_segments(cmd):
        subcmd, rest = parse_git_subcommand(seg)
        if subcmd == "push":
            if "--dry-run" in rest or "-n" in rest:
                continue
            if NEG_PUSH_RE.search(user_input) or not POS_PUSH_RE.search(user_input):
                return True
    return False


def matches_verify_cmd(cmd: str, git_root: Path) -> bool:
    if DISALLOWED_VERIFY_TAIL_RE.search(cmd):
        return False
    custom_patterns: list[str] = []
    custom_file = git_root / ".agent-work" / "verify-patterns.txt"
    if custom_file.is_file():
        try:
            custom_patterns = [
                ln.strip() for ln in custom_file.read_text(encoding="utf-8", errors="ignore").splitlines()
                if ln.strip() and not ln.strip().startswith("#")
            ]
        except OSError:
            custom_patterns = []

    for seg in split_shell_segments(cmd):
        if DISALLOWED_NON_VERIFY_HEAD_RE.match(seg):
            continue
        if VERIFY_CMD_START_RE.match(seg):
            return True
        low_seg = seg.lower()
        for pat in custom_patterns:
            if pat.lower() in low_seg:
                return True
            try:
                if re.search(pat, seg, re.I):
                    return True
            except re.error:
                continue
    return False


def skill_path(name: str) -> str:
    candidate = SKILLS_DIR / name / "SKILL.md"
    if candidate.is_file():
        return str(candidate)
    # 独立迁移部署兜底常见全局技能目录
    for base in (
        Path.home() / ".claude" / "skills",
        Path.home() / ".agents" / "skills",
        Path.home() / ".codex" / "skills",
        Path.home() / ".trae" / "skills",
    ):
        alt = base / name / "SKILL.md"
        if alt.is_file():
            return str(alt)
    return str(candidate)


def is_pure_concept_qa(text: str) -> bool:
    if BUGFIX_ACTION_RE.search(text):
        return False
    if CONCEPT_QA_RE.search(text):
        return True
    if WHY_QUESTION_RE.search(text) and re.search(r"概念|原理|机制|设计|一般|通常会", text):
        return True
    return False


def infer_bugfix_ro(text: str) -> str | None:
    if READONLY_DIAG_RE.search(text):
        return "bugfix-diagnose"
    if DIAG_VERB_RE.search(text) and not FIX_VERB_RE.search(text):
        return "bugfix-diagnose"
    return None


def is_diff_review_intent(text: str) -> bool:
    if not DIFF_REVIEW_RE.search(text):
        return False
    if EXPLICIT_READONLY_RE.search(text):
        return True
    if MUTATION_INTENT_RE.search(text):
        return False
    if SELF_REVIEW_ONLY_RE.search(text) and not CONCRETE_REVIEW_TARGET_RE.search(text):
        return False
    return True


def detect_intent(user_input: str) -> tuple[str | None, str | None]:
    """无开放 Spec 时从大白话识别工程节点与只读护栏模式。"""
    text = user_input.strip()
    if not text or NON_DEV_RE.match(text):
        return None, None
    if MICRO_EDIT_RE.search(text) and not HEAVY_DEV_RE.search(text):
        return "micro", None
    if is_pure_concept_qa(text):
        return None, None

    if VDD_RE.search(text):
        return "vdd", None
    if BUGFIX_RE.search(text):
        return "code-bugfix", infer_bugfix_ro(text)
    if is_diff_review_intent(text):
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
        spec = pick_active_spec(open_specs, user_input)
        rel_spec = str(spec.relative_to(git_root)) if git_root in spec.parents else str(spec)
        hash_status, landed, ready = check_spec_hash_and_progress(git_root, spec)
        spec_status = f"{rel_spec}:{hash_status}:{landed}:{ready}"
        multi_note = (
            f"（另检测到 {len(open_specs) - 1} 份开放 Spec；如有歧义请先向用户确认）"
            if len(open_specs) > 1 else ""
        )

        if hash_status in {"drifted", "missing_anchor"}:
            stage = "implement-spec"
            why_txt = "上游 Source 摘要已漂移" if hash_status == "drifted" else "缺少有效 Source 锚点"
            msg = (
                f"[engineering-flow] 检测到开放 Spec（{rel_spec}）{why_txt}，"
                f"禁止直接按过期步骤开工；请先阅读并执行 {skill_path('implement-spec')} 重算并同步 Spec。"
            )
        elif NON_DEV_RE.match(user_input) or is_pure_concept_qa(user_input) or (
            MICRO_EDIT_RE.search(user_input) and not HEAVY_DEV_RE.search(user_input)
        ):
            stage = "micro" if MICRO_EDIT_RE.search(user_input) else None
        elif VDD_RE.search(user_input):
            stage = "vdd"
            msg = f"[engineering-flow] 本轮为完成终审与防漂移验收，请先阅读 {skill_path('vdd')}。"
        elif BUGFIX_RE.search(user_input):
            stage = "code-bugfix"
            read_only_mode = infer_bugfix_ro(user_input)
            msg = (
                f"[engineering-flow] 本轮为故障排查/修复任务，优先按红灯根因工作流执行；"
                f"请先阅读 {skill_path('code-bugfix')}（未过第 4 步证伪探针不改业务代码，密钥一律脱敏为 <REDACTED>）。"
            )
        elif is_diff_review_intent(user_input):
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
        elif SPEC_REVISE_RE.search(user_input) and not NEG_SPEC_REVISE_RE.search(user_input):
            stage = "implement-spec"
            msg = (
                f"[engineering-flow] 本轮为修订开放 Spec（{rel_spec}），已切换回 `implement-spec` 解锁 Spec 写入；"
                f"请先阅读 {skill_path('implement-spec')} 按深模块与兼容性重算步骤（已落地 `landed={landed}` 保持不回改）。"
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
                f"[engineering-flow] 仓库存在开放 Spec（{rel_spec}），进度 `landed={landed}`、`ready={ready}`{multi_note}；"
                f"请先阅读 {skill_path('go-work')} 按步骤落地，严格守住只读 Spec 铁律（禁止直接修改开放 Spec）。"
            )
    else:
        stage, read_only_mode = detect_intent(user_input)
        spec_status = "no_open_spec"
        skill_hints = {
            "vdd": f"[engineering-flow] 识别为完成终审与防漂移验收，请先阅读并遵循 {skill_path('vdd')}。",
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
    for k in ("CommandLine", "commandLine", "command_line", "command", "cmd", "Cmd"):
        v = args.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _resolve_maybe(raw: str, cwd: Path | None) -> Path:
    p = Path(raw.strip())
    if not p.is_absolute() and cwd is not None:
        p = cwd / p
    try:
        return p.resolve()
    except OSError:
        return p


def extract_tool_paths(tool_call: dict, cwd: Path | None) -> list[Path]:
    args = tool_call.get("args")
    if not isinstance(args, dict):
        return []
    out: list[Path] = []
    for k in (
        "Path", "path", "TargetFile", "targetFile", "target_file",
        "file_path", "FilePath", "NotebookPath", "notebook_path",
        "SourcePath", "DestinationPath", "old_path", "new_path",
    ):
        v = args.get(k)
        if isinstance(v, str) and v.strip():
            p = _resolve_maybe(v, cwd)
            if p not in out:
                out.append(p)
    for k in ("patch", "Patch", "input", "diff"):
        v = args.get(k)
        if isinstance(v, str) and "*** " in v:
            for m in re.finditer(r"^\*\*\*\s+(?:Update|Add|Delete)\s+File:\s*(.+)$|^\*\*\*\s+Move to:\s*(.+)$", v, re.M):
                hit = (m.group(1) or m.group(2) or "").strip()
                if hit:
                    p = _resolve_maybe(hit, cwd)
                    if p not in out:
                        out.append(p)
    return out


def is_open_spec_path(target: Path, git_root: Path) -> bool:
    try:
        rel = target.relative_to(git_root.resolve())
    except ValueError:
        if _is_darwin():
            try:
                rel = Path(_norm_case(str(target))).relative_to(_norm_case(str(git_root.resolve())))
            except ValueError:
                return False
        else:
            return False
    parts = tuple(_norm_case(pt) for pt in rel.parts)
    if len(parts) >= 3 and parts[:2] in {("docs", "spec"), (".agent-work", "spec")} and "archived" not in parts and rel.suffix.lower() == ".md":
        return True
    return False


def is_repo_code_or_doc_mutable(target: Path, git_root: Path) -> bool:
    try:
        rel = target.relative_to(git_root.resolve())
    except ValueError:
        if _is_darwin():
            try:
                rel = Path(_norm_case(str(target))).relative_to(_norm_case(str(git_root.resolve())))
            except ValueError:
                return False
        else:
            return False
    if rel.parts and _norm_case(rel.parts[0]) == ".agent-work":
        return False
    return True


def _shell_targets_open_spec(seg: str) -> bool:
    low = _norm_case(seg)
    if not ("docs/spec/" in low or ".agent-work/spec/" in low):
        return False
    if "archived/" in low:
        return False
    return bool(re.search(
        r"(?:>>?|\btee\b|\bsed\s+-i|\brm\s+|\bmv\s+|\bcp\s+|open\(|write_text|write_bytes|unlink)",
        low,
    ))


def _shell_violates_readonly(seg: str) -> bool:
    subcmd, _ = parse_git_subcommand(seg)
    if subcmd in DESTRUCTIVE_GIT_SUBCMDS:
        return True
    low = _norm_case(seg)
    if re.search(r"\b(?:sed\s+-i|tee\b|rm\s+|mv\s+|truncate\b)", low):
        if "/dev/null" in low and ">" in low and not re.search(r"\b(?:sed\s+-i|rm\s+|mv\s+)\b", low):
            return False
        if any(safe in low for safe in (".agent-work/", "/tmp/", "/private/tmp/")):
            return False
        return True
    for m in re.finditer(r">{1,2}\s*([^\s;&|]+)", low):
        tgt = m.group(1)
        if tgt == "/dev/null" or tgt.startswith(("&", "/tmp/", "/private/tmp/", ".agent-work/")):
            continue
        return True
    return False


def handle_pre_tool_use(payload: dict) -> tuple[dict, str, str | None, str]:
    user_input = str(payload.get("lastUserInput") or "")
    tool_call = payload.get("toolCall") if isinstance(payload.get("toolCall"), dict) else {}
    tool_name = str(tool_call.get("name") or "").strip().lower()

    # 白名单仅做环境短路，但即便在 non_git 下也检查显式 git push（防 ~ 目录跨仓 push）
    bypass, reason, git_root = should_bypass(payload)
    if bypass and reason in {"env_disabled", "acp_brain_probe", "judgment_workspace", "butler_workspace", "jojo_iloop_repo"}:
        return {"decision": "allow"}, "bypass", None, reason

    if tool_name in SHELL_TOOLS:
        cmd = extract_tool_command(tool_call)
        if cmd and has_unauthorized_git_push(cmd, user_input):
            return (
                {
                    "decision": "force_ask",
                    "reason": "engineering-flow 红线：本轮未见显式 push 授权，执行 git push 前需人工强制确认。",
                },
                "force_ask",
                None,
                "git_push_guard",
            )

    targets = extract_tool_paths(tool_call, extract_cwd(payload)) if tool_name in EDIT_TOOLS else []
    if (bypass or git_root is None) and targets:
        # 跨仓操作兜底：从目标文件反推其所在的真实 Git 仓库
        for tgt in targets:
            if not is_tmp_path(tgt):
                cand = resolve_git_root(tgt)
                if cand is not None and not (cand / ".agent-work" / "flow-disabled").exists():
                    git_root = cand
                    bypass = False
                    break

    if bypass or git_root is None:
        return {"decision": "allow"}, "bypass", None, reason

    conv_id = payload.get("conversationId")
    state = load_session(conv_id)
    stage = state.get("stage")
    ro_mode = state.get("read_only_mode")

    # 兜底：若子代理/首轮未经过 PreInvocation 恢复阶段状态，按开放 Spec 与意图恢复
    if not ro_mode and user_input:
        _, detected_ro = detect_intent(user_input)
        ro_mode = detected_ro
    if stage is None:
        open_specs = find_open_specs(git_root)
        if open_specs and not (SPEC_REVISE_RE.search(user_input) and not NEG_SPEC_REVISE_RE.search(user_input)):
            stage = "spec-battle" if BATTLE_RE.search(user_input) else "go-work"

    if tool_name in SHELL_TOOLS:
        cmd = extract_tool_command(tool_call)
        if cmd:
            for seg in split_shell_segments(cmd):
                if stage in {"go-work", "spec-battle"} and _shell_targets_open_spec(seg):
                    return (
                        {
                            "decision": "deny",
                            "reason": f"engineering-flow 写死隔离红线：当前处于 `{stage}` 阶段，禁止通过 Shell 修改开放 Spec。",
                        },
                        "deny",
                        stage,
                        "open_spec_shell_lock",
                    )
                if ro_mode in {"diff-review", "bugfix-diagnose"} and _shell_violates_readonly(seg):
                    return (
                        {
                            "decision": "deny",
                            "reason": f"engineering-flow 只读红线：当前处于 `{ro_mode}` 只读模式，禁止破坏工作树或改写仓内文件。",
                        },
                        "deny",
                        stage,
                        f"readonly_shell_{ro_mode}",
                    )

    if tool_name in EDIT_TOOLS and targets:
        for target in targets:
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
                            "禁止修改业务源码、`.git/` 或仓内文件。"
                        ),
                    },
                    "deny",
                    stage,
                    f"readonly_{ro_mode}",
                )

    return {"decision": "allow"}, "allow", stage, tool_name or "unknown"


def handle_post_tool_use(payload: dict) -> tuple[dict, str, str | None, str]:
    bypass, reason, git_root = should_bypass(payload)
    tool_call = payload.get("toolCall") if isinstance(payload.get("toolCall"), dict) else {}
    tool_name = str(tool_call.get("name") or "").strip().lower()
    targets = extract_tool_paths(tool_call, extract_cwd(payload)) if tool_name in EDIT_TOOLS else []
    if (bypass or git_root is None) and targets and reason in {"non_git", "tmp_workspace", "missing_cwd"}:
        for tgt in targets:
            if not is_tmp_path(tgt):
                cand = resolve_git_root(tgt)
                if cand is not None:
                    git_root = cand
                    bypass = False
                    break

    if bypass or git_root is None:
        return {}, "bypass", None, reason
    if payload.get("error"):
        return {}, "tool_failed", None, str(payload.get("error"))[:80]

    conv_id = payload.get("conversationId")
    try:
        with _session_lock(conv_id):
            state = _load_session_unlocked(conv_id)
            stage = state.get("stage")
            changed = False

            if tool_name in EDIT_TOOLS and targets:
                for target in targets:
                    if is_repo_code_or_doc_mutable(target, git_root):
                        try:
                            rel = str(target.relative_to(git_root.resolve()))
                        except ValueError:
                            rel = str(target)
                        if not rel.lower().endswith(".md"):
                            files = list(state.get("edited_code_files") or [])
                            if rel not in files:
                                files.append(rel)
                                state["edited_code_files"] = files
                            # 只要发生新代码改动，此前通过的验证一律失效
                            if state.get("ran_verify_ok", False):
                                state["ran_verify_ok"] = False
                            changed = True
                            if HIGH_RISK_PATH_RE.search(rel):
                                state["touched_high_risk"] = True

            elif tool_name in SHELL_TOOLS:
                cmd = extract_tool_command(tool_call)
                if cmd and matches_verify_cmd(cmd, git_root):
                    state["ran_verify_ok"] = True
                    changed = True

            if changed:
                _save_session_unlocked(conv_id, state)
    except OSError:
        stage = None
        changed = False
    return {}, "recorded" if changed else "noop", stage, tool_name or "unknown"


def handle_stop(payload: dict) -> tuple[dict, str, str | None, str]:
    bypass, reason, git_root = should_bypass(payload)
    if bypass and reason in {"env_disabled", "acp_brain_probe", "judgment_workspace", "butler_workspace", "jojo_iloop_repo"}:
        return {}, "bypass", None, reason

    conv_id = payload.get("conversationId")
    state = load_session(conv_id)
    edited = list(state.get("edited_code_files") or [])
    if (bypass or git_root is None) and not edited:
        return {}, "bypass", None, reason

    if payload.get("terminationReason") != "NO_TOOL_CALL":
        return {}, "skip_reason", None, str(payload.get("terminationReason"))
    if not payload.get("fullyIdle", True):
        return {}, "skip_not_idle", None, "bg_active"
    if payload.get("continuationActive", False):
        return {}, "skip_continuation", None, "already_continued"

    stage = state.get("stage")
    if not edited or state.get("ran_verify_ok", False):
        out_reason = "verified_or_clean"
        state["edited_code_files"] = []
        state["ran_verify_ok"] = False
        state["touched_high_risk"] = False
        state["stop_nudges"] = 0
        save_session(conv_id, state)
        return {}, "allow_stop", stage, out_reason
    if int(state.get("stop_nudges", 0)) >= 1:
        state["edited_code_files"] = []
        state["ran_verify_ok"] = False
        state["touched_high_risk"] = False
        state["stop_nudges"] = 0
        save_session(conv_id, state)
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
                f"但在最新修改后尚未通过测试或静态验证命令{risk_note}；请先补跑最小验证命令并汇报真实结果后再结束。"
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
