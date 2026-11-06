# -*- coding: utf-8 -*-
"""细则（每日细则 markdown）解析与候选校验。从 loop.py 原样搬来。"""
import re

from hh_eval.const import FORBIDDEN_RULE, HEADER_RX
from hh_eval.fs import H, read_text
from hh_eval.judge import norm

NEGATION = re.compile(r"不|别|勿|禁止|严禁|避免|防止|没有")


def rules_of(text):
    body = HEADER_RX.sub("", text or "").strip()
    rules = re.split(r"(?m)^(?=## 细则 )", body)
    return [r.strip() for r in rules if r.strip().startswith("## 细则 ")], body


def release_text(release_id):
    return read_text(H("releases", release_id, "daily-learning.md"))


def with_header(body, release_id, date):
    head = (f"<!-- haohao-eval 自动维护 · 版本 {release_id} · {date} · 排在 SKILL.md 底线和四条原则之下，"
            f"冲突时以底线为准 · 手工改过的话，自动发布会暂停，等作者确认 -->\n")
    return head + "# 好好说话 · 每日细则\n\n" + (body.strip() + "\n" if body.strip() else "（还没有细则）\n")


def forbidden_hit(rule):
    for m in FORBIDDEN_RULE.finditer(rule):
        if not NEGATION.search(rule[max(0, m.start() - 6):m.start()]):
            return m.group(0)
    return ""


def validate_candidate(text, cfg, current_text, holdout_texts, aa=False):
    errs = []
    rules, body = rules_of(text)
    body = re.sub(r"^# 好好说话 · 每日细则\s*", "", body).strip()
    g = cfg["gates"]
    if len(body) > g["overlay_max_chars"]:
        errs.append(f"细则总长 {len(body)} 字，超过上限 {g['overlay_max_chars']}")
    if len(rules) > g["overlay_max_rules"]:
        errs.append(f"细则 {len(rules)} 条，超过上限 {g['overlay_max_rules']}")
    left = re.sub(r"(?m)^## 细则 .*?(?=^## 细则 |\Z)", "", body, flags=re.S).strip()
    left = re.sub(r"（还没有细则）", "", left).strip()
    if left:
        errs.append("细则之外不许有别的内容（每条以「## 细则 Lnnn · 标题」开头）")
    ids = []
    for r in rules:
        head = r.splitlines()[0]
        m = re.match(r"## 细则 (L\d{3}) · (.+)", head)
        if not m:
            errs.append(f"标题格式不对：{head}（要写成「## 细则 L001 · 标题」）")
            continue
        ids.append(m.group(1))
        if len(r) > g["rule_max_chars"]:
            errs.append(f"{m.group(1)} 有 {len(r)} 字，超过单条上限 {g['rule_max_chars']}")
        if "- 适用：" not in r or "- 做法：" not in r:
            errs.append(f"{m.group(1)} 缺「- 适用：」或「- 做法：」")
        hit = forbidden_hit(r)
        if hit:
            errs.append(f"{m.group(1)} 含禁用说法「{hit}」：细则不许放宽保真，不许让模型补信息")
    if len(set(ids)) != len(ids):
        errs.append("细则编号有重复")
    cur_rules, _ = rules_of(current_text)
    cur_map = {re.match(r"## 细则 (L\d{3})", r).group(1): r for r in cur_rules if re.match(r"## 细则 (L\d{3})", r)}
    new_map = {re.match(r"## 细则 (L\d{3})", r).group(1): r for r in rules if re.match(r"## 细则 (L\d{3})", r)}
    changed = [i for i in set(cur_map) | set(new_map) if norm(cur_map.get(i, "")) != norm(new_map.get(i, ""))]
    if not changed and not aa:
        errs.append("候选跟现用版一样，没有改动")
    if len(changed) > g["max_rules_changed"]:
        errs.append(f"一次改了 {len(changed)} 条细则，上限 {g['max_rules_changed']} 条（一次只修一类问题）")
    for t in holdout_texts:
        for i in range(0, max(0, len(norm(t)) - 11)):
            piece = norm(t)[i:i + 12]
            if len(piece) == 12 and piece in norm(body):
                errs.append("候选里引用了留作验证的题目原文，验证就不准了。例子只能取自开发组的召回。")
                return errs, changed
    return errs, changed


__all__ = ["rules_of", "release_text", "with_header", "forbidden_hit", "validate_candidate"]
