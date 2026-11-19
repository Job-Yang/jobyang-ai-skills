#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_linkage.py — check_linkage.py 判别力回归（零三方依赖）。

核心：好图（图上每个词都在锚定正文、有过渡句）必须放行；坏图（另起比喻/自造术语、
裸放图、空过渡）必须拦下。用真实文章《写给 RD 的 AI 底层原理》的段落做素材。
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
CL_PATH = os.path.join(SKILL, "scripts", "check_linkage.py")

spec = importlib.util.spec_from_file_location("check_linkage", CL_PATH)
cl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cl)

fails = []
def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f" -> {extra}"))
    if not cond:
        fails.append(name)


def codes(E, c):
    return {e["code"] for e in E if e["code"] == c}


# 一段含"训练数据里有新闻…论文"和三阶段的真实正文（节选，逐字来自原文）
SRC = (
    "想象你教一个新员工校对文章……因为训练数据里有新闻、有教材、有代码、有对话、有论文，"
    "「下一个 token 最可能是什么」这个问题，要答得准，模型必须理解世界是什么样的。\n"
    "预训练做的是上面说的那件事：给模型喂海量文本，让它学会「预测下一个 token」。"
    "这阶段结束后，模型学会了大量世界知识，但它不知道怎么「听话」。\n"
    "Instruction Tuning（指令微调）：用「问题-回答」格式的数据继续训练，数据量少得多"
    "（几万到几百万条），模型学会了「当输入是问题时，输出应该是回答」。\n"
    "RLHF（人类反馈强化学习）：让人类标注员对模型的多个输出排序，训练一个「打分模型」，"
    "再用强化学习让语言模型的输出尽量获得高分。\n"
    "这三步可以类比客户端开发：预训练是把整个 SDK 编译好；Instruction Tuning 是在 SDK 基础上"
    "开发应用层逻辑；RLHF 是做用户测试然后迭代产品。"
)

GOOD = {
    "mode": "supplement", "source_text": SRC,
    "bridge": "先学知识、再学听话、最后学得让人满意，这三步对应的训练如下图。",
    "caption": "预训练 vs 微调 vs RLHF · 编译 SDK → 应用层 → 用户测试",
    "figure": {"kind": "renderer", "spec": {"layout": "columns", "title": "预训练、微调、RLHF",
        "data": {"columns": [
            {"title": "预训练", "subtitle": "喂海量文本", "scene": "新闻、教材、代码、对话、论文",
             "bullets": ["学会了大量世界知识", "学到的是文本续写，不是指令执行"]},
            {"title": "指令微调", "subtitle": "问题-回答格式的数据", "scene": "几万到几百万条",
             "bullets": ["当输入是问题时，输出应该是回答"]},
            {"title": "RLHF", "subtitle": "人类对多个输出排序",
             "bullets": ["训练一个打分模型", "回答得让人满意"]}],
        "chain": ["把整个 SDK 编译好", "在 SDK 基础上开发应用层逻辑", "做用户测试然后迭代产品"]}}}
}

# 1) 好图：无 ERROR
E, W, _ = cl.evaluate(GOOD)
check("好图无必改", not E, str([(e["code"], e["text"]) for e in E]))

# 2) 坏图 A：图里另起正文没有的比喻（读书学生/傅马同学）+ 自造英文阶段名
bad = {**GOOD, "figure": {"kind": "renderer", "spec": {"layout": "columns",
    "title": "模型是怎么学会的——三阶段流水线",
    "data": {"columns": [
        {"title": "Pretraining\n预训练", "bullets": ["背下整个互联网"]},
        {"title": "Instruction Tuning\n指令微调", "bullets": ["看高质量问答对"]},
        {"title": "RLHF\n人类反馈强化学习", "bullets": ["人类排序好坏"]}],
        "chain": ["傅马同学：什么都在学", "实习生：跟着范例学习", "职场人：让人满意"]}}}}
E, W, _ = cl.evaluate(bad)
etexts = " ".join(e["text"] for e in E)
check("坏图抓到另起比喻「傅马同学」", any("傅马" in e["text"] for e in E), etexts)
check("坏图抓到自造术语 Pretraining", any(e["code"] == "E2" for e in E), str(codes(E, "E2")))
check("坏图抓到「背下整个互联网」脱锚", any("背下整个互联网" in e["text"] for e in E), etexts)

# 3) 坏图 B：裸放（无过渡句）
b2 = {**GOOD, "bridge": ""}
E, _, _ = cl.evaluate(b2)
check("无过渡句报 E1", any(e["code"] == "E1" for E2 in [E] for e in E2))

# 4) 坏图 C：空指图（只有"如下图所示"，没点图里东西）
b3 = {**GOOD, "bridge": "如下图所示。"}
E, _, _ = cl.evaluate(b3)
check("空指图报 E1/E5", any(e["code"] in ("E1", "E5") for e in E))

# 5) 坏图 D：图自造数字（正文没有 90%）
b4 = {**GOOD, "figure": {"kind": "renderer", "spec": {"layout": "columns",
    "title": "预训练、微调、RLHF",
    "data": {"columns": [
        {"title": "预训练", "bullets": ["学会 90% 的世界知识"]},
        {"title": "指令微调", "bullets": ["当输入是问题时，输出应该是回答"]},
        {"title": "RLHF", "bullets": ["回答得让人满意"]}]}}}}
E, _, _ = cl.evaluate(b4)
check("图自造数字 90% 报 E3", any(e["code"] == "E3" for e in E))

# 6) 缺锚定正文
b5 = {"mode": "supplement", "source_text": "", "bridge": "x 如下图",
      "figure": {"kind": "renderer", "spec": {"layout": "pipeline",
      "title": "t", "data": {"steps": [{"title": "a"}, {"title": "b"}]}}}}
E, _, _ = cl.evaluate(b5)
check("缺锚定正文报 E0", any(e["code"] == "E0" for e in E))

# 7) 封面：无过渡句也放行（但术语仍对账）
cov = {"cover": True, "mode": "supplement", "source_text": SRC,
       "figure": {"kind": "cover", "prompt": "画面只有引号标题「预训练、微调、RLHF」"}}
E, _, _ = cl.evaluate(cov)
check("封面免过渡句且无必改", not E, str(E))

# 8) t2i：提示词里引号的内容文字要对账；指图词「如下图」是指令不是图上字，故不放进引号
t2i = {**GOOD, "figure": {"kind": "t2i",
       "prompt": "扁平信息图，画面只有三张卡片，引号文字分别是「预训练」「指令微调」「RLHF」，除此不出现其它文字"}}
E, _, _ = cl.evaluate(t2i)
check("t2i 引号文字对账通过", not E, str(E))

# 9) replace 模式：图里保留 source 术语通过，kept+图都丢术语时 W5 告警
rep_ok = {
    **GOOD,
    "mode": "replace",
    "kept_text": "先看三阶段训练流程。",
}
E, W, _ = cl.evaluate(rep_ok)
check("replace 模式保留图术语无必改", not E, str(E))
rep_miss = {
    **rep_ok,
    "figure": {"kind": "renderer", "spec": {"layout": "columns", "title": "三阶段",
        "data": {"columns": [
            {"title": "预训练", "bullets": ["学会了大量世界知识"]},
            {"title": "指令微调", "bullets": ["当输入是问题时"]},
            {"title": "RLHF", "bullets": ["回答得让人满意"]}]}}},
}
_, W_miss, _ = cl.evaluate(rep_miss)
check("replace 模式漏 Tokenizer/Instruction 术语触发 W5",
      any(w["code"] == "W5" and "instruction" in w["text"].lower() for w in W_miss), str(W_miss))

# 10) allow_new 对中文新比喻与数字同样生效
an = {
    "mode": "supplement",
    "source_text": "缓存把热数据留在内存，请求不用每次回源查库。",
    "allow_new": ["图书馆书车", "24小时"],
    "bridge": "把缓存想成图书馆书车，流程如下图。",
    "caption": "图书馆书车比喻",
    "figure": {"kind": "renderer", "spec": {"layout": "columns", "title": "图书馆书车",
        "data": {"columns": [
            {"title": "图书馆书车", "bullets": ["缓存留在内存 24 小时"]},
            {"title": "回源查库", "bullets": ["书车里没有再查库"]}]}}},
}
E_an, _, _ = cl.evaluate(an)
check("allow_new 对中文与数字生效", not E_an, str(E_an))

print()
if fails:
    print(f"==== {len(fails)} 项失败：{fails}")
    sys.exit(1)
print("ALL LINKAGE TESTS PASSED")
