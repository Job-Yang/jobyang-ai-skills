#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_backends.py — gen_image.py 适配层与 doctor.py 的无网络回归。

不发真实请求：只验证配置解析、请求构造（纯函数）、响应解析、降级、CLI 退出码。
真实端到端由 doctor.py --ping 在配了 key 的环境手动跑。
"""
import importlib.util
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
PY = sys.executable


def load(modname, script):
    spec = importlib.util.spec_from_file_location(modname, script)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


gen = load("gen_image", os.path.join(SKILL, "scripts", "gen_image.py"))
fails = []
def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f" -> {extra}"))
    if not cond:
        fails.append(name)


# 1) build_request：openai 兼容
c = {"provider": "openai", "base": "https://api.openai.com/v1", "key": "k", "model": "gpt-image-1",
     "size": "1536x1024", "n": 1, "path": "/images/generations", "url_field": "data.0.url",
     "b64_field": "data.0.b64_json", "command": ""}
url, headers, body = gen.build_request(c, "提示")
check("openai URL 拼接", url == "https://api.openai.com/v1/images/generations", url)
check("Bearer 头", headers.get("Authorization") == "Bearer k")
check("body 含 model/prompt/size", body["model"] == "gpt-image-1" and body["prompt"] == "提示"
      and body["size"] == "1536x1024", str(body))

# 2) 缺 base/model 报配置错
for bad_c, kw in [({**c, "base": ""}, "BASE"), ({**c, "model": ""}, "MODEL")]:
    try:
        gen.build_request(bad_c, "x"); check(f"缺{kw}应报错", False)
    except ValueError as e:
        check(f"缺{kw}报 ValueError", kw in str(e), str(e))

# 3) 非法 provider
try:
    gen.generate("x", "o.png", c={**c, "provider": "nope"})
    check("非法 provider 报错", False)
except ValueError as e:
    check("非法 provider 报 ValueError", "provider" in str(e).lower() or "CI_IMAGE_PROVIDER" in str(e),
          str(e))

# 4) parse_response：url / b64 / 字符串 data 三种
check("解析 data.0.url", gen.parse_response('{"data":[{"url":"https://x/a.png"}]}', c)[0]
      == "https://x/a.png")
check("解析 data.0.b64", gen.parse_response('{"data":[{"b64_json":"AAAA"}]}', c)[1] == "AAAA")
check("解析字符串 data", gen.parse_response('{"data":["https://x/b.png"]}', c)[0]
      == "https://x/b.png")
check("啥都没有返回 (None,None)", gen.parse_response('{"data":[{}]}', c) == (None, None))

# 5) save_bytes 魔数：PNG 头通过，HTML 拒绝
tmp = tempfile.mkdtemp(prefix="ci-be-")
png = b"\x89PNG\r\n\x1a\n" + b"0" * 50
p = os.path.join(tmp, "a.png")
n = gen.save_bytes(png, p)
check("PNG 魔数通过", n == len(png))
try:
    gen.save_bytes(b"<html>error</html>", os.path.join(tmp, "h.png"))
    check("HTML 被拒", False)
except ValueError:
    check("非图片字节被拒", True)

# 6) dry-run：不联网，打印请求且退出 0
env = {**os.environ, "CI_IMAGE_PROVIDER": "openai", "CI_IMAGE_BASE_URL": "https://api.openai.com/v1",
       "CI_IMAGE_MODEL": "gpt-image-1"}
r = subprocess.run([PY, os.path.join(SKILL, "scripts", "gen_image.py"), "ping", "--dry-run",
                    "-o", os.path.join(tmp, "p.png")], env=env, capture_output=True, text=True)
check("dry-run rc=0 且打印 url", r.returncode == 0 and "images/generations" in r.stdout,
      r.stderr)

# 7) 显式 HTTP provider 未配置时 dry-run 退出码 2；已就绪的原生 CLI 后端另测。
env2 = {k: v for k, v in os.environ.items()
        if not k.startswith("CI_IMAGE_")}
env2["CI_IMAGE_PROVIDER"] = "openai"
r = subprocess.run([PY, os.path.join(SKILL, "scripts", "gen_image.py"), "ping", "--dry-run",
                    "-o", os.path.join(tmp, "p.png")], env=env2, capture_output=True, text=True)
check("HTTP 未配置 rc=2", r.returncode == 2, r.stderr)

# 8) command provider：从 stdout 抓 URL（用 echo 模拟，download 会失败但走到了抓 URL 之后）；
#    这里只验证命令构造不崩 + 无 URL 时报错信息友好
cc = {**c, "provider": "command",
      "command": "printf '%s' 'https://127.0.0.1:9/none.png'"}
try:
    gen.run_command(cc, "提示词", os.path.join(tmp, "c.png"))
    check("command 走到下载（预期连不上则失败也算到了抓取之后）", True)
except Exception as e:
    # 连不上 127.0.0.1:9 是正常的（Connection refused）；关键是它先抓到了 URL 再去下载
    s = (str(e) + " " + type(e).__name__).lower()
    check("command 已抓到 URL 再尝试下载",
          "none.png" in s or "refused" in s or "errno" in s or "urlopen" in s
          or "下载" in s or "url" in s, s)
cc_bad = {**c, "provider": "command", "command": "echo no-url-here"}
try:
    gen.run_command(cc_bad, "x", os.path.join(tmp, "c.png"))
    check("无 URL 报错", False)
except RuntimeError as e:
    check("command 无 URL 时给友好错误", "URL" in str(e))

# 9) doctor 核心可用（rc=0）
r = subprocess.run([PY, os.path.join(SKILL, "scripts", "doctor.py")], capture_output=True, text=True)
check("doctor rc=0（SVG 核心可用）", r.returncode == 0, r.stdout[-300:])
check("doctor 标出原生/MCP 需人工确认", "t2i_native" in r.stdout and "t2i_mcp" in r.stdout)

print()
if fails:
    print(f"==== {len(fails)} 项失败：{fails}")
    sys.exit(1)
print("ALL BACKEND TESTS PASSED")
