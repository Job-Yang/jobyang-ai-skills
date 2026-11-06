#!/usr/bin/env python3
"""check_questions.py — 快速档题本静态校验（确定性防回归，纯标准库）。

扫描题本"快速话题地图"区块（# 快速话题地图 → # 标准档 之间）里给用户的话，排除元信息/分寸等内部行。
按话题头部标注的 T 级分区（T0/T1/T2，参考 mectx_common.DOMAIN_ASK_GATE），规则分档：
  全局（任意分区）：
    1) T2/T1 直问词：ask != T0 的域（finance/health=T2、network=T1）敏感词不得直问；
    2) 编号列表（1)2)3)、①②③、问题1/2/3）、带圈数字选项串；
    3) 报表/流水线短语（一次问三题/答完复述落盘/我们继续/接着问/下一个…包/进入…包）。
  仅非 T0 分区：
    4) 一行 ≥2 个问号（T0 允许一条自然话成组带 2–4 个轻问题，取消纯问号数量硬判）。
借壳规则保留：当下第二人称问句（你…？）即使含"以后/别客气"也不豁免；禁令动作短语白名单保留。
这是机械护栏，不做语义权威；最终分寸由写协议与用户裁决。

用法：python3 scripts/check_questions.py --questions <bootstrap.md>
exit 0 = 通过；1 = 命中违禁；2 = 参数/文件错误。
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mectx_common import DOMAIN_ASK_GATE, DEFAULT_ASK_GATE  # 单一事实源，不在此另写硬编码域清单

# 域 → 快速档不得直问的词（子串）。是否启用由 DOMAIN_ASK_GATE 决定：gate=T0 的域不拦。
DOMAIN_WORDS = {
    "finance": [
        "年薪", "月薪", "工资", "薪水", "薪资", "收入", "存款", "存钱",
        "车贷", "房贷", "负债", "借贷", "欠多少钱", "贷款", "资产",
    ],
    "health": [
        "血压", "血糖", "胆固醇", "病史", "病历", "体检报告", "体检",
        "用什么药", "长期吃药", "长期吃的药", "在吃的药", "慢性病", "手术史",
        "就诊史", "过敏",
    ],
    "network": ["结婚", "生育", "备孕", "怀孕", "孩子",
                "老婆", "老公", "丈夫", "妻子", "爱人"],
}
# 证件/密钥类（全局直问拦，不属任一 domain；onboarding 永不索要）
ID_WORDS = ["身份证", "手机号", "密码", "银行卡号", "证件号"]

# 报表式问卷模板（编号/带圈，全局拦）
BANNED_PATTERNS = [
    (re.compile(r"\d\)\s*[\u4e00-\u9fffA-Za-z]"), "编号列表 1)2)3)"),
    (re.compile(r"(?:^|[，,；;\s、])\d\s*[.、]\s*[\u4e00-\u9fffA-Za-z]"), "圆点/顿点编号 1./1、"),
    (re.compile(r"[①②③④⑤]"), "带圈编号 ①②③"),
    (re.compile(r"问题\s*[123一二三四]"), "问题1/2/3 编号"),
    (re.compile(r"模块\s*[0-9一二三四]"), "自报模块进度 模块1/模块2"),
]
# 软流水线推进语（禁令句除外，全局拦）
SOFT_PIPELINE = [
    re.compile(r"一次问三题|一次问三|逐题"), re.compile(r"我们继续"),
    re.compile(r"下一项"), re.compile(r"接着问"), re.compile(r"继续问"),
    re.compile(r"下一个"), re.compile(r"然后再问你"),
    re.compile(r"答完.{0,6}再"), re.compile(r"进入.{0,4}包"),
]
# 提示语（非直问，放行）：说明"以后/到时候才确认"；仅当本行不是当下面向用户的提问才豁免
HINT_MARKERS = ["以后", "等你", "到时候", "不用现在说", "先跟你确认", "先确认"]
# 禁令语境短语白名单（针对"提问动作"，不用单字"别"，避免"别客气/别的事"借壳）
NEGATION_PHRASES = ["别问", "不要问", "不直问", "不主动问", "禁止问", "不得问", "不问", "不打听"]

# 话题头部：允许 ##/### 等任意层级、阿拉伯/中文数字，只认 T0/T1/T2 标注；
# 标题缺 T 级时拿不准 → 保守按非 T0（收紧连问），敏感词全局仍拦。
TOPIC_HEAD = re.compile(r"^#{1,6}\s*话题.*?\b(T[012])\b")


def _is_direct_question(line):
    """当下面向用户的第二人称问句：含'你'且带问号（全/半角），或直问词紧邻问号。
    提示/禁令豁免对这种句子不生效。"""
    if "你" in line and ("？" in line or "?" in line):
        return True
    if re.search(r"[？?]\s*$", line) and any(
            w in line for ws in list(DOMAIN_WORDS.values()) + [ID_WORDS] for w in ws):
        return True
    return False


def _quick_block(text):
    m = re.search(r"#\s*快速话题地图(?P<body>.*?)(?=^#\s*标准档|\Z)", text, re.M | re.S)
    return m.group("body") if m else ""


def _exempt(line):
    """提示/禁令豁免只对'非当下提问'生效；借壳的当下问句（含你+？）不豁免。"""
    if _is_direct_question(line):
        return False
    if any(m in line for m in HINT_MARKERS):
        return True
    if any(p in line for p in NEGATION_PHRASES):
        return True
    return False


def _iter_zoned(block):
    """按话题头部 T 级分区，yield (zone, line)。
    标题缺 T 级/层级变体/中文数字导致认不出时，默认保守按非 T0（收紧连问）；
    敏感词规则是全局的，不随 zone 开关。"""
    zone = "T1"  # 拿不准默认非 T0（保守），只有标题明确标 T0 才放行成组连问
    for raw in block.splitlines():
        head = TOPIC_HEAD.search(raw.strip())
        if head:
            zone = head.group(1)
        line = raw.strip()
        if not line or line.startswith(">") or line.startswith("#"):
            continue
        if any(k in line for k in ("元信息", "分寸", "内部", "注：", "落 `profile", "落 `ME")):
            continue
        yield zone, line


def check(path):
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        print(f"[错误] 读不到题本：{e}", file=sys.stderr)
        return 2
    block = _quick_block(text)
    if not block:
        print("[错误] 未找到'快速话题地图'区块", file=sys.stderr)
        return 2

    # 由 ASK_GATE 派生启用的敏感词表（T0 域不拦）
    active = {}
    for domain, words in DOMAIN_WORDS.items():
        gate = DOMAIN_ASK_GATE.get(domain, DEFAULT_ASK_GATE)
        if gate != "T0":
            active[domain] = words

    hits = []
    warns = []
    for zone, ln in _iter_zoned(block):
        exempt = _exempt(ln)
        qmarks = ln.count("？") + ln.count("?")
        # 1) T2/T1 直问词（全局；提示/禁令豁免只对非当下提问生效，借壳问句不豁免）
        if not exempt:
            for domain, words in active.items():
                for w in words:
                    if w in ln:
                        hits.append(f"[{domain}直问:{w}] {ln}")
            for w in ID_WORDS:
                if w in ln:
                    hits.append(f"[证件直问:{w}] {ln}")
        # 2) 编号/带圈报表模板（全局）
        for pat, label in BANNED_PATTERNS:
            if pat.search(ln):
                hits.append(f"[报表模板:{label}] {ln}")
        # 3) 软流水线（全局，禁令句除外）
        if not exempt:
            for pat in SOFT_PIPELINE:
                if pat.search(ln):
                    hits.append(f"[软流水线:{pat.pattern}] {ln}")
        # 4) 一行多问号：仅非 T0 分区硬 fail（全/半角都数）
        if zone != "T0" and not exempt and qmarks >= 2:
            hits.append(f"[一次多问:{zone}一行{qmarks}个问号] {ln}")
        # 5) T0 成组软上限：一行 ≥5 问仅 WARN（不影响 rc），提示像批量盘问建议拆两三轮
        if zone == "T0" and not exempt and qmarks >= 5:
            warns.append(f"[T0成组偏多:一行{qmarks}个问号，建议拆成两三轮] {ln}")
    for w in warns:
        print(f"  ⚠ WARN {w}")
    if hits:
        print("快速档给用户的话命中违禁（T2/T1 直问 / 证件 / 报表模板 / 软流水线 / 非T0连问）：")
        for h in hits:
            print(f"  ✗ {h}")
        return 1
    print("OK：快速档无 T2/T1 直问、无证件直问、无报表模板、无软流水线")
    return 0


def main():
    ap = argparse.ArgumentParser(description="快速档题本静态校验（ASK_GATE 驱动、T 级分区）")
    ap.add_argument("--questions", required=True)
    args = ap.parse_args()
    return check(args.questions)


if __name__ == "__main__":
    sys.exit(main())
