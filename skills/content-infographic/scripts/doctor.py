#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
doctor.py — 进场自检：这个平台上 content-infographic 的渲染与文生图后端能不能跑。

确定性渲染器几乎到处可跑；真正要确认的是 PNG 转换器、以及“文生图”这一下在当前
宿主怎么接。脚本可探测 Ferry＋Codex、command 与 HTTP 后端；宿主直接提供的原生图像
工具与 MCP 是否可用，仍由调用方（agent）看工具清单，报告中标为 needs_agent_check。

检查项：
  python            版本（≥3.8）
  renderer_svg      render_infographic.py 能否在本目录出 SVG（必过）
  renderer_png      rsvg-convert / Chrome headless 至少一个（缺了只影响位图导出，SVG 仍在）
  fetch_image       fetch_image.py 在位、可执行
  t2i_native        宿主原生文生图工具：脚本测不了，恒为 needs_agent_check
  t2i_mcp           文生图 MCP：同上，needs_agent_check（列出建议找的 MCP 名）
  t2i_ferry_codex   本机 Ferry＋官方 Codex 原生后端是否就绪
  t2i_http          command / HTTP 的 CI_IMAGE_* 配置；齐全则可 gen_image.py --dry-run
用法：
  python3 doctor.py             # 人类可读
  python3 doctor.py --json      # 机器可读
  python3 doctor.py --ping      # 对已就绪后端真发最小图验证端到端（耗额度）
退出码：0 核心（SVG）可用；1 核心不可用。文生图后端缺失不致命（渲染器仍可用）。
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)


def sh(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode == 0, (p.stdout + p.stderr).strip()


def check_python():
    ok = sys.version_info >= (3, 8)
    return {"name": "python", "status": "pass" if ok else "fail",
            "detail": f"{sys.version_info.major}.{sys.version_info.minor}."
                      f"{sys.version_info.micro}（需 ≥3.8）"}


def check_render_svg():
    spec = os.path.join(SKILL, "examples", "api-7steps.json")
    out = os.path.join(tempfile.mkdtemp(prefix="ci-doc-"), "t.svg")
    ok, msg = sh([sys.executable, os.path.join(HERE, "render_infographic.py"),
                  spec, "-o", out])
    ok = ok and os.path.exists(out) and os.path.getsize(out) > 1000
    return {"name": "renderer_svg", "status": "pass" if ok else "fail",
            "detail": "确定性渲染器可出 SVG" if ok else "渲染失败：" + msg[-200:]}


def check_render_png():
    render = os.path.join(HERE, "render_infographic.py")
    spec = os.path.join(SKILL, "examples", "api-7steps.json")
    d = tempfile.mkdtemp(prefix="ci-doc-")
    out = os.path.join(d, "t.svg")
    subprocess.run([sys.executable, render, spec, "-o", out], capture_output=True)
    backend = None
    if shutil.which("rsvg-convert"):
        backend = "rsvg-convert"
    elif os.path.exists("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"):
        backend = "chrome-headless"
    png = os.path.join(d, "t.png")
    ok, msg = sh([sys.executable, render, spec, "-o", out, "--png"])
    has_png = os.path.exists(png)
    if has_png:
        return {"name": "renderer_png", "status": "pass",
                "detail": f"PNG 导出可用（{backend}）"}
    return {"name": "renderer_png", "status": "warn",
            "detail": "没找到 rsvg-convert/Chrome，只能出 SVG（装 librsvg 或用浏览器另存 PNG）"}


def check_fetch():
    p = os.path.join(HERE, "fetch_image.py")
    ok = os.path.exists(p)
    return {"name": "fetch_image", "status": "pass" if ok else "fail",
            "detail": "签名图下载脚本在位" if ok else "缺 scripts/fetch_image.py"}


def check_native():
    # 脚本无法知道宿主有没有原生图像工具；交给 agent 自查工具清单。
    return {"name": "t2i_native", "status": "needs_agent_check",
            "detail": "宿主是否有原生文生图（豆包 image_gen / Codex gpt-image / Trae 视觉模型），"
                      "由 agent 看自身工具清单；有就优先用，无需本脚本"}


def check_mcp():
    return {"name": "t2i_mcp", "status": "needs_agent_check",
            "detail": "是否已接文生图 MCP（seedream_generate_image / OpenAI images 等），"
                      "由 agent 查 MCP 配置；接了就用 MCP 工具"}


def check_http(ping=False):
    provider = os.environ.get("CI_IMAGE_PROVIDER", "openai")
    base = os.environ.get("CI_IMAGE_BASE_URL", "")
    key = os.environ.get("CI_IMAGE_API_KEY", "")
    model = os.environ.get("CI_IMAGE_MODEL", "")
    if provider == "command":
        cmd = os.environ.get("CI_IMAGE_COMMAND", "")
        ok = bool(cmd)
        return {"name": "t2i_http", "status": "pass" if ok else "warn",
                "detail": f"provider=command，外部命令{'已配' if ok else '未配 CI_IMAGE_COMMAND'}"}
    missing = [k for k, v in (("CI_IMAGE_BASE_URL", base),
                              ("CI_IMAGE_MODEL", model)) if not v]
    if missing:
        return {"name": "t2i_http", "status": "warn",
                "detail": "未配 HTTP 文生图（缺 " + "、".join(missing) + "）；"
                          "若宿主已有原生/MCP 文生图可忽略，否则见 references/backends.md 配置"}
    # 配置齐全：dry-run 验证请求能构造；可选 --ping 真发一张
    if ping and key:
        out = os.path.join(tempfile.mkdtemp(prefix="ci-ping-"), "ping.png")
        ok, msg = sh([sys.executable, os.path.join(HERE, "gen_image.py"),
                      "一只简洁的橙色对勾图标，白底，无文字", "-o", out])
        return {"name": "t2i_http", "status": "pass" if ok and os.path.exists(out) else "fail",
                "detail": ("端到端生图成功：" + out) if ok else "端到端失败：" + msg[-300:]}
    ok, msg = sh([sys.executable, os.path.join(HERE, "gen_image.py"), "ping",
                  "--dry-run", "-o", os.path.join(tempfile.gettempdir(), "ping.png")])
    return {"name": "t2i_http",
            "status": "pass" if ok else ("warn" if not key else "fail"),
            "detail": (f"HTTP 配置齐全（{provider} / {model}），dry-run 通过；"
                       + ("未配 key，--ping 前需补 CI_IMAGE_API_KEY" if not key else "可 --ping 实测"))
                      if ok else "请求构造失败：" + msg[-200:]}


def check_ferry_codex(ping=False):
    import importlib.util
    path = os.path.join(HERE, "gen_image.py")
    spec = importlib.util.spec_from_file_location("ci_gen_image", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    backend = module.native_ferry()
    if not backend.available():
        return {"name": "t2i_ferry_codex", "status": "warn",
                "detail": "Ferry 原生 CLI 适配器未配置；见 references/ferry-codex.md"}
    try:
        backend.isolated_config()
        if ping:
            out = os.path.join(tempfile.mkdtemp(prefix="ci-native-ping-"), "ping.png")
            backend.generate("一只橙色对勾，白底，无文字；调用原生文生图工具", out)
            return {"name": "t2i_ferry_codex", "status": "pass",
                    "detail": "原生图像已生成并保存：" + out}
        return {"name": "t2i_ferry_codex", "status": "pass",
                "detail": "已验证的 Ferry＋Codex CLI 后端已就绪，不需要额外图片 API Key；视觉验收另做"}
    except Exception as exc:
        return {"name": "t2i_ferry_codex", "status": "fail", "detail": str(exc)[:300]}


def run(ping=False):
    checks = [check_python(), check_render_svg(), check_render_png(), check_fetch(),
              check_native(), check_mcp(), check_ferry_codex(ping=ping), check_http(ping=ping)]
    core_ok = all(c["status"] == "pass"
                  for c in checks if c["name"] in ("python", "renderer_svg", "fetch_image"))
    return checks, core_ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--ping", action="store_true")
    args = ap.parse_args()
    checks, core_ok = run(args.ping)
    if args.json:
        print(json.dumps({"core_ok": core_ok, "checks": checks}, ensure_ascii=False, indent=2))
    else:
        print("content-infographic · 进场自检\n")
        icon = {"pass": "✅", "fail": "❌", "warn": "⚠️ ", "needs_agent_check": "🔎"}
        for c in checks:
            print(f"{icon.get(c['status'],'·')} {c['name']:14} {c['detail']}")
        print("\n核心（确定性出 SVG）：", "可用" if core_ok else "不可用")
        print("文生图：依次看宿主原生/MCP、t2i_ferry_codex、t2i_http；任选其一，都没有就只用渲染器。")
    return 0 if core_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
