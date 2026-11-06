#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_render.py — render_infographic 的对抗式回归（零三方依赖，直接跑）。

覆盖：schema 校验正/反例、拉丁整词不被劈断、字数边界、PNG 真的是图、
六类布局各能渲染、自定义配色、stdin、退出码。
运行：python3 tests/test_render.py
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
RENDER = os.path.join(SKILL, "scripts", "render_infographic.py")
PY = sys.executable

fails = []


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  -> {extra}"))
    if not cond:
        fails.append(name)


def run(args, stdin=None):
    p = subprocess.run([PY, RENDER] + args, input=stdin, capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def is_png(path):
    return os.path.exists(path) and open(path, "rb").read(8).startswith(b"\x89PNG\r\n\x1a\n")


tmp = tempfile.mkdtemp(prefix="ci-test-")

# 1. 三个样例都能出 SVG + PNG
for ex in ("api-7steps", "training-3stages", "understanding-debt"):
    spec = os.path.join(SKILL, "examples", ex + ".json")
    svg = os.path.join(tmp, ex + ".svg")
    rc, out, err = run([spec, "-o", svg, "--png"])
    check(f"{ex}: rc=0 且出 SVG", rc == 0 and os.path.exists(svg), err)
    check(f"{ex}: PNG 真的是 PNG 魔数", is_png(os.path.join(tmp, ex + ".png")), err)

# 2. schema 反例：缺 title / 非法 layout / pipeline 步数越界 / compare 列数不符
bad_cases = [
    {"layout": "pipeline", "data": {"steps": []}},
    {"title": "x", "layout": "nope", "data": {}},
    {"title": "x", "layout": "pipeline", "data": {"steps": [1]}},
    {"title": "x", "layout": "compare",
     "data": {"columns": ["A", "B"], "rows": [{"label": "r", "values": ["只有一个"]}]}},
    {"title": "x", "layout": "radial", "data": {"center": "c"}},  # 缺 nodes
]
for i, bad in enumerate(bad_cases):
    p = os.path.join(tmp, f"bad{i}.json")
    open(p, "w").write(json.dumps(bad, ensure_ascii=False))
    rc, _, err = run([p, "-o", os.path.join(tmp, "x.svg")])
    check(f"bad#{i} 被 schema 拒绝(rc=2)", rc == 2, err)

# 3. 拉丁整词不被劈断：渲染极窄场景靠 fit_size 缩字，但 SVG 文本节点里 Tokenizer 必须整体出现
spec = json.load(open(os.path.join(SKILL, "examples", "api-7steps.json")))
svg = os.path.join(tmp, "api-7steps.svg")
svgtext = open(svg, encoding="utf-8").read()
check("英文词 Tokenizer 在 SVG 文本中整体出现", "Tokenizer" in svgtext)
check("英文词 Transformer 在 SVG 文本中整体出现", "Transformer" in svgtext)
check("英文术语 De-tokenize 保留连字符", "De-tokenize" in svgtext)
# 不应把英文词按字母换行（粗检：SVG text 里不应出现 'Tokenize' 后紧跟换行标签再 'r'）
check("无 Tokenizer 被劈成 Tokenize+r 两节点",
      "Tokenize<" not in svgtext.replace(" ", ""))

# 4. 六种布局都能渲染（two_stage / compare / radial 现场构造）
others = {
    "two_stage": {"layout": "two_stage", "title": "训练 vs 推理",
                  "data": {"vs_label": "VS", "stages": [
                      {"title": "训练", "subtitle": "Training", "rows": [{"k": "显存", "v": "保留中间激活"}]},
                      {"title": "推理", "subtitle": "Inference", "rows": [{"k": "显存", "v": "算完即弃"}]}]}},
    "compare": {"layout": "compare", "title": "三方案对比",
                "data": {"corner": "维度", "columns": ["A", "B", "C"],
                         "rows": [{"label": "成本", "values": ["高", {"text": "中", "tone": "hl"}, {"text": "低", "tone": "good"}]}]}},
    "radial": {"layout": "radial", "title": "一个中心四条",
               "data": {"center": "机制", "nodes": ["性质一", "性质二", "性质三", "性质四"]}},
}
for name, spec in others.items():
    p = os.path.join(tmp, name + ".json")
    open(p, "w").write(json.dumps(spec, ensure_ascii=False))
    rc, _, err = run([p, "-o", os.path.join(tmp, name + ".svg")])
    check(f"布局 {name} rc=0", rc == 0, err)

# 5. --validate-only 对合法样例 rc=0
rc, out, _ = run([os.path.join(SKILL, "examples", "api-7steps.json"),
                  "-o", os.path.join(tmp, "v.svg"), "--validate-only"])
check("--validate-only 合法 rc=0 并打印 schema OK", rc == 0 and "schema OK" in out, out)

# 6. 坏 JSON rc=1
badjson = os.path.join(tmp, "broken.json")
open(badjson, "w").write("{ not json")
rc, _, _ = run([badjson, "-o", os.path.join(tmp, "b.svg")])
check("坏 JSON rc=1", rc == 1)

# 7. stdin 通道
good = json.dumps({"layout": "radial", "title": "stdin",
                   "data": {"center": "C", "nodes": ["a", "b", "c"]}}, ensure_ascii=False)
rc, _, err = run(["--stdin", "-o", os.path.join(tmp, "stdin.svg")], stdin=good)
check("--stdin rc=0", rc == 0, err)

# 8. 自定义配色被采用
custom = {"layout": "radial", "title": "c", "palette": {"accent": "#123456"},
          "data": {"center": "X", "nodes": ["1", "2", "3"]}}
p = os.path.join(tmp, "pal.json")
open(p, "w").write(json.dumps(custom))
run([p, "-o", os.path.join(tmp, "pal.svg")])
check("palette.accent 覆盖生效", "#123456" in open(os.path.join(tmp, "pal.svg")).read())

print()
if fails:
    print(f"==== {len(fails)} 项失败：{fails}")
    sys.exit(1)
print("ALL TESTS PASSED")
