#!/usr/bin/env python3
"""Bootstrap optional Python dependencies for engineering-docs, invisibly.

The core tools (diagram_kit.py, diagram_check.py, doc_check.py) only use the
standard library. Quantitative chart examples (render_templates.py,
assets/visual-examples/render_charts.py) additionally need matplotlib and numpy.

This module tries, in order:
  1. import the package from the current interpreter;
  2. reuse a previously bootstrapped copy under .deps/ next to this script;
  3. `python3 -m pip install --target <skill>/.deps <packages>` (user site is
     never touched; no sudo; uses the configured package index when provided);
  4. give the exact manual command to run, once, clearly.

Usage:
    from bootstrap import require
    plt, np = require("matplotlib.pyplot", "numpy")

Exit codes on failure are 0 only when the packages are importable afterwards.
"""
import importlib
import os
import subprocess
import sys
from pathlib import Path

DEPS_DIR = Path(
    os.environ.get(
        "ENGINEERING_DOCS_DEPS_DIR",
        str(Path(__file__).resolve().parent.parent / ".deps" / f"py{sys.version_info.major}{sys.version_info.minor}"),
    )
)
_DEFAULT_PACKAGES = ("matplotlib", "numpy")
_BOOTSTRAPPED = False


def _deps_on_path():
    if DEPS_DIR.is_dir() and str(DEPS_DIR) not in sys.path:
        sys.path.insert(0, str(DEPS_DIR))


def _pip_install(packages):
    env = dict(os.environ)
    env.setdefault("PIP_DISABLE_PIP_VERSION_CHECK", "1")
    # Respect a user-configured mirror; otherwise use pip's normal index.
    index = env.get("PIP_INDEX_URL")
    cmd = [sys.executable, "-m", "pip", "install", "--target", str(DEPS_DIR), *packages]
    if index:
        cmd += ["-i", index]
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=600)
    return proc.returncode == 0, (proc.stdout or "")[-400:] + (proc.stderr or "")[-800:]


def require(*module_names, packages=None):
    """Import modules by name, bootstrapping their pip packages once if missing.

    module_names: importable module names, e.g. "matplotlib.pyplot", "numpy".
    packages: pip distribution names, inferred from the module names when omitted.
    Raises SystemExit with a copy-pasteable fix only after install also fails.
    """
    global _BOOTSTRAPPED
    _deps_on_path()
    try:
        return tuple(importlib.import_module(m) for m in module_names)
    except ImportError:
        pass

    if not _BOOTSTRAPPED:
        wanted = list(packages) if packages else sorted({m.split(".")[0] for m in module_names})
        manual = " ".join(wanted)
        if os.environ.get("ENGINEERING_DOCS_ALLOW_PIP") != "1":
            raise SystemExit(
                "缺少可选依赖：" + manual + "\n"
                "核心结构图、高密度布局与文档检查不依赖它们；仅定量数据图表示例需要。\n"
                "未默认自动联网安装；获准后可设置 ENGINEERING_DOCS_ALLOW_PIP=1 重试，或手动隔离安装：\n"
                f"  {sys.executable} -m pip install --target {DEPS_DIR} {manual}"
            )
        DEPS_DIR.mkdir(parents=True, exist_ok=True)
        ok, log = _pip_install(wanted)
        if not ok:
            raise SystemExit(
                "缺少可选依赖：" + manual + "\n"
                "核心结构图、文档检查不依赖它们；只有数据图表示例需要。\n"
                "正在自动安装失败，请手动执行一次后重试：\n"
                f"  {sys.executable} -m pip install {manual}\n"
                "若在内网且 PyPI 不可达，加公司镜像源参数，或让管理员预装。\n"
                "安装日志：\n" + log
            )
        _deps_on_path()
        for root_name in sorted({m.split(".")[0] for m in module_names}):
            for mod_key in [k for k in list(sys.modules) if k == root_name or k.startswith(root_name + ".")]:
                sys.modules.pop(mod_key, None)
        importlib.invalidate_caches()
        _BOOTSTRAPPED = True

    try:
        return tuple(importlib.import_module(m) for m in module_names)
    except ImportError as exc:
        missing = exc.name or ", ".join(module_names)
        pyver = f"{sys.version_info.major}.{sys.version_info.minor}"
        raise SystemExit(
            f"依赖已安装但仍无法导入 {missing}（当前 Python {pyver}：{exc}）：请检查 Python 版本与平台 wheel 是否匹配。"
        )


if __name__ == "__main__":
    mods = sys.argv[1:] or ["matplotlib", "numpy"]
    loaded = require(*mods)
    for m in loaded:
        print(f"{m.__name__} {getattr(m, '__version__', 'ok')}")
