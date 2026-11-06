#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_image.py — 跨平台文生图的「薄适配层」，零三方依赖（仅标准库 urllib）。

定位：本技能的确定性渲染器（render_infographic.py）到处都能跑；真正随平台变化的只有
"文生图"这一下。本脚本把这一下收敛成一个统一命令，换平台只改环境变量/适配器，不改技能。

优先级：
  1) 宿主原生图像工具（豆包 image_gen / Codex gpt-image / Trae 视觉模型）：有就直接用，别绕 HTTP。
  2) 已配置的文生图 MCP（Seedream MCP、OpenAI 图像 MCP 等）：用 MCP 工具。
  3) 本脚本未显式配置 HTTP 时，自动选择本机可用的 Ferry＋官方 Codex 原生后端。
  4) 显式配置 provider 或 HTTP 参数时，保留 OpenAI 兼容 HTTP / 外部命令后端。

支持的 provider：
  ferry_codex : 独立 CODEX_HOME，通过本机 Ferry 账号调用官方 Codex 原生图片工具
  openai      : POST {base}/images/generations            data[0].url|b64_json
  ark         : 火山方舟，同 OpenAI 兼容，model=doubao-seedream-*
  generic     : 自定义 base + path + 响应里图片字段的 JSON 路径
  command     : 不发 HTTP，执行一条外部命令（厂商 CLI 等），从 stdout 抓第一个 http(s) 图片 URL
配置全部走环境变量，不接受把 key 写进命令行/文件：
  CI_IMAGE_PROVIDER   ferry_codex|openai|ark|generic|command（未配置时自动探测 Ferry）
  CI_IMAGE_BASE_URL   如 https://api.openai.com/v1 、 https://ark.cn-beijing.volces.com/api/v3
  CI_IMAGE_API_KEY    Bearer 密钥
  CI_IMAGE_MODEL      如 gpt-image-1 / doubao-seedream-4-0 / doubao-seedream-5-0
  CI_IMAGE_SIZE       默认 1536x1024（约 3:2）
  CI_IMAGE_N          出几张，默认 1
  CI_IMAGE_PATH       generic 模式自定义请求路径，默认 /images/generations
  CI_IMAGE_URL_FIELD  generic 模式响应里 URL 的 JSON 路径，如 data.0.url（默认 data.0.url）
  CI_IMAGE_COMMAND     command 模式执行的命令；{prompt} 占位符会被替换并经 shell 转义

用法：
  python3 gen_image.py "一句画面提示词（图上中文用引号写全）" -o out.png
  echo "提示词" | python3 gen_image.py --stdin -o out.png
  python3 gen_image.py "..." --dry-run          # 只打印将发出的请求，不联网（自检/排错用）
退出码：0 成功并落地图片；1 请求/下载失败；2 参数或配置错。
"""
import argparse
import importlib.util
import json
import os
import shlex
import subprocess
import sys
import urllib.error
import urllib.request
from functools import lru_cache
from pathlib import Path
from types import ModuleType

PROVIDERS = {"openai", "ark", "generic", "command", "ferry_codex"}
DEFAULT_PATH = "/images/generations"


@lru_cache(maxsize=1)
def native_ferry() -> ModuleType:
    # Works with python -I: load only this trusted sibling, never a CWD module.
    path = Path(__file__).resolve().with_name("ferry_codex.py")
    spec = importlib.util.spec_from_file_location("ci_ferry_codex", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 Ferry/Codex 后端：{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def cfg():
    provider = os.environ.get("CI_IMAGE_PROVIDER", "").strip().lower()
    if not provider:
        http_keys = ("CI_IMAGE_BASE_URL", "CI_IMAGE_MODEL", "CI_IMAGE_API_KEY")
        explicit_http = any(os.environ.get(key) for key in http_keys)
        provider = "ferry_codex" if not explicit_http and native_ferry().available() else "openai"
    return {
        "provider": provider,
        "base": os.environ.get("CI_IMAGE_BASE_URL", "").rstrip("/"),
        "key": os.environ.get("CI_IMAGE_API_KEY", ""),
        "model": os.environ.get("CI_IMAGE_MODEL", ""),
        "size": os.environ.get("CI_IMAGE_SIZE", "1536x1024"),
        "n": int(os.environ.get("CI_IMAGE_N", "1")),
        "path": os.environ.get("CI_IMAGE_PATH", DEFAULT_PATH),
        "url_field": os.environ.get("CI_IMAGE_URL_FIELD", "data.0.url"),
        "b64_field": os.environ.get("CI_IMAGE_B64_FIELD", "data.0.b64_json"),
        "command": os.environ.get("CI_IMAGE_COMMAND", ""),
    }


def build_request(c: dict, prompt: str):
    """纯函数：构造 (url, headers, body)。便于不联网单测。"""
    if c["provider"] in {"command", "ferry_codex"}:
        return None
    if not c["base"]:
        raise ValueError("缺 CI_IMAGE_BASE_URL")
    if not c["model"]:
        raise ValueError("缺 CI_IMAGE_MODEL")
    url = c["base"] + (c["path"] if c["path"].startswith("/") else "/" + c["path"])
    headers = {"Content-Type": "application/json"}
    if c["key"]:
        headers["Authorization"] = "Bearer " + c["key"]
    body = {"model": c["model"], "prompt": prompt, "size": c["size"], "n": c["n"]}
    # 各家对 size/响应格式的小差异：ark/openai 都接受 size；先求 url，落不了再退回 b64
    body["response_format"] = "url"
    return url, headers, body


def _dig(obj, dotted: str):
    cur = obj
    for part in dotted.split("."):
        if part == "":
            continue
        if isinstance(cur, list):
            cur = cur[int(part)]
        elif isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
        if cur is None:
            return None
    return cur


def parse_response(raw: str, c: dict):
    """纯函数：从响应 JSON 取 (url, b64)。"""
    d = json.loads(raw)
    url = _dig(d, c["url_field"])
    b64 = _dig(d, c["b64_field"])
    if not url and not b64:
        # 常见兼容：直接给 url 字符串 / data 是字符串
        if isinstance(d.get("data"), list) and d["data"] and isinstance(d["data"][0], str):
            url = d["data"][0]
        elif isinstance(d.get("url"), str):
            url = d["url"]
    return url, b64


def is_image(head: bytes):
    return (head.startswith(b"\x89PNG\r\n\x1a\n") or head.startswith(b"\xff\xd8\xff")
            or head[:4] == b"RIFF" and head[8:12] == b"WEBP")


def save_bytes(data: bytes, out: str):
    if not is_image(data[:16]):
        raise ValueError("返回内容不是图片（可能是错误页/鉴权失败）")
    with open(out, "wb") as f:
        f.write(data)
    return len(data)


def download(url: str, out: str, headers=None):
    # URL 路径里可能含非 ASCII（厂商域名/中文路径），按 IDNA + 百分号编码后再请求
    url = quote_url(url)
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return save_bytes(r.read(), out)


def quote_url(url: str) -> str:
    """对 URL 的 host 做 IDNA、path/query 做百分号编码，保留已编码的 %XX 与保留字符。"""
    import urllib.parse as up
    parts = up.urlsplit(url)
    host = parts.hostname.encode("idna").decode("ascii") if parts.hostname else ""
    if parts.port:
        host = f"{host}:{parts.port}"
    path = up.quote(parts.path, safe="/%")
    query = up.quote(parts.query, safe="=&%?+")
    return up.urlunsplit((parts.scheme, host, path, query, parts.fragment))


def post_json(url, headers, body, timeout=180):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:600]
        raise RuntimeError(f"HTTP {e.code}：{detail}") from None


def run_command(c: dict, prompt: str, out: str):
    import re
    if not c["command"]:
        raise ValueError("provider=command 但没配 CI_IMAGE_COMMAND")
    if "{prompt}" in c["command"]:
        cmd = c["command"].replace("{prompt}", shlex.quote(prompt))
    else:  # 没占位符就把提示词安全追加到命令末尾，由外部命令自行解析
        cmd = c["command"] + " " + shlex.quote(prompt)
    # 用 UTF-8 字节走 shell，避免 POSIX/ascii locale 下中文提示词编码报错
    proc = subprocess.run(cmd.encode("utf-8"), shell=True, capture_output=True, timeout=300)
    stdout = proc.stdout.decode("utf-8", "replace")
    stderr = proc.stderr.decode("utf-8", "replace")
    if proc.returncode != 0:
        raise RuntimeError("外部命令失败：" + stderr.strip()[:400])
    m = re.search(r"https?://[^\s\"'<>]+?\.(?:png|jpe?g|webp)[^\s\"'<>]*", stdout)
    if m:
        return download(m.group(0), out)
    if os.path.exists(out):  # 外部命令可能已直接把图写到 out
        data = open(out, "rb").read()
        if is_image(data[:16]):
            return len(data)
    raise RuntimeError("没在命令输出里找到图片 URL，也没生成 out 文件：" + stdout.strip()[:300])


def generate(prompt: str, out: str, dry_run=False, c=None):
    c = c or cfg()
    if c["provider"] not in PROVIDERS:
        raise ValueError(f"CI_IMAGE_PROVIDER 必须是 {sorted(PROVIDERS)}，得到 {c['provider']}")
    if c["provider"] == "ferry_codex":
        return native_ferry().generate(prompt, out, dry_run=dry_run)
    if c["provider"] == "command":
        if dry_run:
            print("[dry-run] 将执行外部命令（prompt 已转义传入）")
            return None
        return run_command(c, prompt, out)

    req = build_request(c, prompt)
    if req is None:
        raise ValueError("内部错误")
    url, headers, body = req
    if dry_run:
        print(json.dumps({"url": url,
                          "headers": {k: ("Bearer ***" if k.lower() == "authorization" else v)
                                      for k, v in headers.items()},
                          "body": body}, ensure_ascii=False, indent=2))
        return None
    raw = post_json(url, headers, body)
    img_url, b64 = parse_response(raw, c)
    import base64
    if img_url:
        n = download(img_url, out,
                     headers={"Authorization": "Bearer " + c["key"]} if c["key"] else None)
    elif b64:
        n = save_bytes(base64.b64decode(b64), out)
    else:
        raise RuntimeError("响应里既没有图片 URL 也没有 b64：" + raw[:400])
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("prompt", nargs="?")
    ap.add_argument("--stdin", action="store_true")
    ap.add_argument("-o", "--out")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    prompt = sys.stdin.read().strip() if args.stdin else (args.prompt or "")
    if not prompt:
        print("需要提示词（参数或 --stdin）", file=sys.stderr)
        return 2
    try:
        n = generate(prompt, args.out or "out.png", dry_run=args.dry_run)
    except ValueError as e:
        print(f"配置错：{e}", file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001
        print(f"生图失败：{e}", file=sys.stderr)
        return 1
    if not args.dry_run:
        print(f"OK: 已保存图片 -> {args.out} ({n} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
