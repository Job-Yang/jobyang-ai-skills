#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""haohao-eval 每日召回的确定性部分。

模型负责出题、改写、裁判、写候选细则；落盘、机械检查、盲评打乱、引用核对、门禁、发布、回滚、
争议队列和日报都由这个脚本算。模型不许凭记忆汇总结果，也不许绕过这里的判定。

只用 Python 标准库。数据目录：$HAOHAO_EVAL_HOME，或 $XDG_DATA_HOME/haohao-eval，
或 ~/.local/share/haohao-eval。发布位置：$XDG_DATA_HOME/haohao-shuohua/daily-learning.md，
或 ~/.local/share/haohao-shuohua/daily-learning.md（和 haohao-shuohua 读的是同一份）。

数据目录能不能跨天留住取决于运行环境；留不住时用 pack / unpack 把整份数据打成一个包，存到别处再取回。

用法见 references/daily-loop.md，或 python3 loop.py -h。
"""
import argparse
import datetime as dt
import difflib
import glob
import hashlib
import io
import json
import math
import os
import random
import re
import shutil
import sys
import tarfile
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
PKG_DATA = os.path.join(SKILL_DIR, "data")
sys.path.insert(0, HERE)
import scorer  # noqa: E402  残留扫描和新数字预筛，只当提示用

# ---------------------------------------------------------------- 常量

CODES = {
    "A1": "编数字", "A2": "编承诺", "A3": "编因果场景", "A4": "编身份经历",
    "B": "丢信息", "G": "删了功能件",
    "C1": "程度范围模态漂移", "C2": "术语通俗化", "C3": "主被动调换", "C4": "抬头语气降格",
    "D": "场合错配",
    "E1": "破折号硬接", "E2": "自造黑话", "E3": "绕口不通",
    "F": "冗余没删", "H": "无必要改动", "U": "原句不清没提醒", "R": "AI味残留",
    "P": "作者判定有问题",
}
FAB = {"A1", "A2", "A3", "A4"}
HARM = FAB | {"B", "G", "C1", "C2", "C3", "C4", "D", "P"}
MINOR = {"E1", "E2", "E3", "H"}
RESIDUE = {"R", "F"}
R_LABELS = ["翻案体", "三连排比", "量词标题", "名词化", "万能动词", "元话语", "段末拔高", "翻译腔句式",
            "空心比喻", "车轱辘", "半角标点", "套话", "被字句", "造词", "词不配位", "姿态", "标题"]
SEVERITY = ["A1", "A2", "A3", "A4", "C2", "B", "G", "C1", "C3", "C4", "D", "E1", "E2", "E3", "H", "U", "F", "R"]
REGISTERS = ["官方对外", "敬语", "要气势", "私人软场合", "技术议论"]
VERDICTS = ["改坏了", "没改好", "合格", "不确定"]
VERSIONS = ["current", "cand", "rc", "anchor"]
FLAG_NEED = {  # 需要裁判逐条回应的机器旗标，以及「确认」时必须有的问题编码
    "新数字": FAB | {"C1"}, "新英文词": FAB | {"C2", "D"}, "承诺时间词新增": FAB | {"C1"},
    "确定性加强": {"C1"} | FAB, "模态变化": {"C1"}, "术语丢失": {"C2", "B"}, "术语替换": {"C2"},
    "事实关键词缺失": {"B", "G", "C1", "C2", "C3", "C4"}, "长度异常": set(),
}
MODAL = ["可能", "也许", "或许", "大概", "大约", "估计", "预计", "初步", "疑似", "似乎", "应该", "倾向",
         "计划", "打算", "有望", "争取", "暂定", "原则上", "考虑", "尝试"]
CERTAIN = ["一定", "肯定", "必然", "确定是", "确保", "保证", "大概率", "绝对", "必定", "务必", "彻底"]
PROMISE = ["第一时间", "马上", "立刻", "尽快", "随时", "保证", "一定会", "下周", "明天", "今天", "今晚",
           "下午", "上午", "稍后", "回头", "改天", "请客", "时间点", "工作日", "小时内", "当天"]
SAME_TIME = [("今日", "今天"), ("明日", "明天"), ("即刻", "立刻"), ("立即", "立刻"), ("午后", "下午")]
TECH_TERMS = ["重构", "解耦", "横向扩展", "纵向扩展", "幂等", "回滚", "灰度", "降级", "熔断", "限流",
              "缓存", "分布式", "连接池", "消息队列", "可扩展", "高可用", "可观测", "容灾", "鉴权", "索引",
              "分库分表", "异步", "并发", "线程", "进程", "协程", "死锁", "事务", "一致性", "吞吐",
              "召回", "准确率", "埋点", "告警", "链路", "微服务", "容器", "脏读", "慢查询", "压测"]
TERM_SWAPS = {"重构": ["重写"], "解耦": ["拆开", "分开"], "横向扩展": ["加机器"], "幂等": ["重复"],
              "回滚": ["退回", "撤回"], "灰度": ["小范围"], "降级": ["关掉"], "熔断": ["断开"]}
FORBIDDEN_RULE = re.compile(
    r"忽略|无视|不必遵守|可以不管|优先于底线|覆盖底线|放宽保真|不用管保真|"
    r"允许.{0,6}(补|编|加|添)|可以.{0,4}(补充|补上|加上|编|添上)|适当(补充|增加|添加|加入)|"
    r"合理(推测|想象|补充|发挥)|自行(补充|发挥)|更像人|人味|加点(细节|场景|口吻)|一律口语|全部口语")
HEADER_RX = re.compile(r"^\s*(<!--.*?-->\s*)+", re.S)
MARK_START, MARK_END = "<!-- 底线条款:开始", "<!-- 底线条款:结束"

DEFAULTS = {
    "shuohua_skill_dir": "",
    "model_name": "",
    "shadow_days": 14,
    "auto_switch": True,
    "daily": {"synthetic": 8, "drafting": 2, "real_max": 3, "regression": 5, "clean": 3, "probes": 6,
              "calib_red": 3, "calib_orange": 2, "calib_green": 4},
    "cluster": {"min_findings": 6, "min_spread": 2, "cooldown_days": 7, "stuck_after": 3, "stuck_window_days": 14},
    "gates": {"calib_min_catch": 0.8, "calib_max_false_alarm": 0.25, "max_uncertain": 0.2,
              "target_min_discordant": 5, "target_alpha": 0.05, "clean_edit_slack": 0.05,
              "clean_edit_alarm": 0.3, "overlay_max_chars": 6000, "overlay_max_rules": 30,
              "rule_max_chars": 400, "max_rules_changed": 2},
    "monitor": {"window_days": 7, "harm_rate_margin": 0.10, "min_days_after_release": 2, "min_harm_items": 3},
    "disputes": {"max_per_day": 3, "default_after_days": 3, "audit_weekday": 1, "audit_count": 3,
                 "auto_match_similarity": 0.75, "audit_miss_pause": 0.1, "audit_min_answered": 5},
    "sources": {"badcase_base": "", "badcase_table": "", "read_new_badcases": False},
    "pack": {"keep_runs_days": 14},
}


class Stop(Exception):
    """流程必须停下来的情况：给出中文原因，退出码 2。"""


# ---------------------------------------------------------------- 路径与读写

def xdg_data():
    return os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")


def eval_home():
    return os.environ.get("HAOHAO_EVAL_HOME") or os.path.join(xdg_data(), "haohao-eval")


def shuohua_home():
    return os.path.join(xdg_data(), "haohao-shuohua")


def published_path():
    return os.path.join(shuohua_home(), "daily-learning.md")


def H(*parts):
    return os.path.join(eval_home(), *parts)


def run_dir(date):
    return H("runs", date)


def today_str(args=None):
    if args is not None and getattr(args, "date", None):
        return args.date
    return dt.date.today().isoformat()


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def read_jsonl(path):
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise Stop(f"{path} 第 {n} 行不是合法 JSON：{e}")
    return rows


def write_jsonl(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def append_jsonl(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def read_text(path, default=""):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return f.read()


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def sha(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


def file_sha(path):
    return sha(read_text(path)) if os.path.exists(path) else "absent"


def deep_merge(base, over):
    out = json.loads(json.dumps(base))
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config():
    return deep_merge(DEFAULTS, load_json(H("config.json"), {}))


def load_state():
    st = load_json(H("state.json"))
    if st is None:
        raise Stop("还没初始化。先跑：python3 scripts/loop.py init")
    return st


def save_state(st):
    save_json(H("state.json"), st)


class Lock:
    def __init__(self):
        self.path = H("loop.lock")

    def __enter__(self):
        os.makedirs(eval_home(), exist_ok=True)
        if os.path.exists(self.path):
            age = dt.datetime.now().timestamp() - os.path.getmtime(self.path)
            if age < 6 * 3600:
                raise Stop(f"另一个流程正在跑（{self.path}）。确认没有别的会话在跑，再删掉这个文件重试。")
            os.remove(self.path)
        with open(self.path, "w") as f:
            f.write(str(os.getpid()))
        return self

    def __exit__(self, *exc):
        if os.path.exists(self.path):
            os.remove(self.path)


def days_between(a, b):
    return (dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days


def log_author(today, text):
    """作者的回话执行过什么，日报里列出来，作者据此知道回话有没有被读到。"""
    append_jsonl(H("inbox.jsonl"), [{"date": today, "text": text}])


def file_digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------- 文本工具

_TRANS = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'", "「": '"', "」": '"', "『": '"', "』": '"',
                        "，": ",", "。": ".", "：": ":", "；": ";", "！": "!", "？": "?", "（": "(", "）": ")",
                        "\u3000": " "})


def norm(s):
    return re.sub(r"\s+", "", (s or "").translate(_TRANS))


def quote_in(quote, text):
    """引用必须是原样连续片段；允许用「……」省略中间，省略两侧各段都要按顺序找得到。"""
    q = (quote or "").strip()
    if not q:
        return False
    parts = [norm(p) for p in re.split(r"……|\.\.\.|…", q)]
    parts = [p for p in parts if p]
    if not parts or sum(len(p) for p in parts) < 2:
        return False
    t = norm(text)
    pos = 0
    for p in parts:
        i = t.find(p, pos)
        if i < 0:
            return False
        pos = i + len(p)
    return True


def bigrams(s):
    s = norm(s)
    return {s[i:i + 2] for i in range(len(s) - 1)}


def jaccard(a, b):
    A, B = bigrams(a), bigrams(b)
    return len(A & B) / len(A | B) if A and B else 0.0


def shingles(s, k=5):
    s = norm(s)
    return {s[i:i + k] for i in range(max(1, len(s) - k + 1))}


def split_output(text):
    """输出正文和「给作者」提醒分开：机械检查只查正文，提醒里的问题不算新加的信息。"""
    m = re.search(r"(^|\n)\s*(【给作者】|[「\[]?给作者[」\]]?\s*[：:])", text or "")
    if m:
        return text[:m.start()].strip(), text[m.end():].strip()
    return (text or "").strip(), ""


def cjk_len(s):
    return len(re.sub(r"\s+", "", s or ""))


def edit_ratio(a, b):
    return round(1 - difflib.SequenceMatcher(None, norm(a), norm(b), autojunk=False).ratio(), 3)


def latin_tokens(t):
    return {w.lower() for w in re.findall(r"[A-Za-z][A-Za-z0-9_+#.\-]*[A-Za-z0-9+#]|[A-Za-z]{2,}", t or "")}


# ---------------------------------------------------------------- 机械检查

def mechanical_check(item, output_text):
    body, notes = split_output(output_text)
    src = item.get("原文", "")
    ctx = item.get("上下文", "") or ""
    basis = src + "\n" + ctx
    task = item.get("任务", "改写")
    flags, hints = [], []

    def flag(kind, content, why):
        flags.append({"kid": f"K{len(flags) + 1}", "类型": kind, "内容": content, "说明": why})

    oq, rq = scorer._normalize_quant(basis), scorer._normalize_quant(body)
    for v in sorted(rq - oq):
        flag("新数字", v, "改写里有、原文和上下文里没有的量化说法（已按中文数字、百分比、一半归一化）")
    for w in sorted(latin_tokens(body) - latin_tokens(basis)):
        flag("新英文词", w, "改写里新出现的英文词或缩写")
    basis_t = basis
    for a_, b_ in SAME_TIME:
        basis_t = basis_t.replace(a_, b_)
    for w in PROMISE:
        if w in body and w not in basis_t:
            flag("承诺时间词新增", w, "改写里新出现的承诺或时间说法")
    for w in CERTAIN:
        if w in body and w not in basis:
            flag("确定性加强", w, "改写里新出现的确定语气")
    src_modal = [w for w in MODAL if w in basis]
    out_modal = [w for w in MODAL if w in body]
    if src_modal and len(out_modal) < len(src_modal):
        lost = [w for w in src_modal if w not in body]
        if lost:
            flag("模态变化", "、".join(lost), "原文的不确定语气在改写里少了")
    if task == "改写":
        for w in sorted(latin_tokens(src) - latin_tokens(body)):
            flag("术语丢失", w, "原文的英文术语在改写里没有了")
        for term in TECH_TERMS:
            if term in src and term not in body:
                swapped = [s for s in TERM_SWAPS.get(term, []) if s in body and s not in src]
                if swapped:
                    flag("术语替换", f"{term}→{swapped[0]}", "专业术语可能被换成了通俗说法")
                else:
                    flag("术语丢失", term, "原文的专业术语在改写里没有了")
    for fact in item.get("事实", []) or []:
        kws = fact.get("关键词") or []
        if kws and not any(k in body for k in kws):
            flag("事实关键词缺失", fact.get("id", ""), f"这条事实的关键词（{'、'.join(kws)}）在改写里都找不到，可能丢了或改了")
    ratio = round(cjk_len(body) / max(1, cjk_len(src)), 2)
    if task == "改写" and (ratio < 0.5 or ratio > 1.6):
        flag("长度异常", str(ratio), "改写长度是原文的 %.2f 倍" % ratio)
    dash_new = body.count("——") - src.count("——")
    if dash_new > 0:
        hints.append(f"破折号比原文多 {dash_new} 个")
    half = re.findall(r"[\u4e00-\u9fff][,;:](?=[\u4e00-\u9fff])", body)
    if half:
        hints.append(f"中文里夹了半角标点 {len(half)} 处")
    res, detail = scorer.score_residual(body)
    for d in detail:
        if d["小计"] > 0 and "密度" not in d["类别"]:
            hints.append(f"正则提示·{d['类别']}：{' / '.join(d['样本'][:2])}")
    stats = {"原文字数": cjk_len(src), "改写字数": cjk_len(body), "长度比": ratio,
             "改动比例": edit_ratio(src, body), "一字未改": norm(src) == norm(body),
             "残留分": res, "有给作者提醒": bool(notes)}
    return {"flags": flags, "hints": hints, "stats": stats, "body": body, "notes": notes}


# ---------------------------------------------------------------- 裁判答案核对

def check_finding(code, src_q, out_q, basis, body):
    """按编码核对引用。返回 (是否有效, 原因)。"""
    need_src = code in {"B", "G", "C1", "C2", "C3", "C4", "H", "U"}
    need_out = code in FAB | {"C1", "C2", "C3", "C4", "D", "E1", "E2", "E3", "F", "R", "H"}
    if need_src and not quote_in(src_q, basis):
        return False, "原文引用在原文里找不到" if src_q else "缺原文引用"
    if need_out and not quote_in(out_q, body):
        return False, "改写引用在改写里找不到" if out_q else "缺改写引用"
    if code in FAB and quote_in(out_q, basis):
        return False, "这段在原文里就有，不算新加的"
    if src_q and not need_src and not quote_in(src_q, basis):
        return False, "原文引用在原文里找不到"
    if out_q and not need_out and not quote_in(out_q, body):
        return False, "改写引用在改写里找不到"
    return True, ""


def cluster_of(code, label):
    if code == "R":
        return "R·" + (label if label in R_LABELS else "新")
    return code


def verify_answer(ans, q):
    errs, findings, dropped = [], [], []
    basis = (q.get("原文", "") or "") + "\n" + (q.get("上下文", "") or "")
    body = q.get("改写", "") or ""
    claim = ans.get("结论")
    if claim not in VERDICTS:
        errs.append("结论必须是：改坏了 / 没改好 / 合格 / 不确定")
    if ans.get("场合") not in REGISTERS:
        errs.append("场合必须是五类之一：" + " / ".join(REGISTERS))
    facts = {f.get("id"): f for f in (q.get("事实") or [])}
    seen = set()
    for e in ans.get("对账") or []:
        fid, res = e.get("事实"), e.get("结果")
        if facts and fid not in facts:
            errs.append(f"对账里的 {fid} 不在事实清单里")
            continue
        seen.add(fid)
        if res not in ("保留", "丢了", "变了"):
            errs.append(f"对账 {fid} 的结果必须是：保留 / 丢了 / 变了")
            continue
        if res == "保留":
            continue
        code = e.get("编码") or ("B" if res == "丢了" else "C1")
        if code not in CODES or code == "P":
            errs.append(f"对账 {fid} 的编码 {code} 不认识")
            continue
        f = {"code": code, "label": e.get("病灶", ""), "src": e.get("原文引用", ""), "out": e.get("改写引用", ""),
             "note": e.get("说明", ""), "fact": fid}
        ok, why = check_finding(code, f["src"], f["out"], basis, body)
        (findings if ok else dropped).append(f if ok else dict(f, 作废原因=why))
    if facts:
        missing = [fid for fid in facts if fid not in seen]
        if missing:
            errs.append("事实清单没对完：" + "、".join(missing))
    for p in ans.get("问题") or []:
        code = p.get("编码")
        if code not in CODES or code == "P":
            errs.append(f"问题编码 {code} 不认识")
            continue
        f = {"code": code, "label": p.get("病灶", ""), "src": p.get("原文引用", ""), "out": p.get("改写引用", ""),
             "note": p.get("说明", "")}
        ok, why = check_finding(code, f["src"], f["out"], basis, body)
        (findings if ok else dropped).append(f if ok else dict(f, 作废原因=why))
    need = {k["kid"]: k for k in (q.get("旗标") or [])}
    answered = {}
    for r in ans.get("旗标") or []:
        kid, con = r.get("旗标"), r.get("结论")
        if kid in need and con in ("确认", "排除") and (r.get("理由") or "").strip():
            answered[kid] = con
    miss = [k for k in need if k not in answered]
    if miss:
        errs.append("机器旗标没回应（每条要写 确认/排除 和理由）：" + "、".join(miss))
    codes = {f["code"] for f in findings}
    for kid, con in answered.items():
        want = FLAG_NEED.get(need[kid]["类型"], set())
        if con == "确认" and want and not (codes & want):
            errs.append(f"旗标 {kid}（{need[kid]['类型']}）确认了，问题清单里却没有对应的条目")
    dispute = None
    if claim == "不确定":
        if not (ans.get("不确定原因") or "").strip():
            errs.append("结论是不确定时，要写不确定原因")
        d = ans.get("争议片段") or {}
        if d.get("问题类型") not in ("保真", "场合"):
            errs.append("结论是不确定时，要给争议片段：问题类型（保真/场合）、原文引用、改写引用")
        elif not quote_in(d.get("原文引用", ""), basis) or not quote_in(d.get("改写引用", ""), body):
            errs.append("争议片段的引用对不上原文或改写")
        else:
            dispute = {"类型": d["问题类型"], "原文片段": d["原文引用"], "改写片段": d["改写引用"],
                       "疑似编码": d.get("疑似编码", ""), "原因": ans.get("不确定原因", "")}
    uniq = {}
    for f in findings:
        k = (f["code"], norm(f.get("src", "")), norm(f.get("out", "")))
        if k in uniq:
            if not uniq[k].get("note") and f.get("note"):
                uniq[k]["note"] = f["note"]
            if not uniq[k].get("label") and f.get("label"):
                uniq[k]["label"] = f["label"]
        else:
            uniq[k] = dict(f)
    findings = list(uniq.values())
    verdict = derive_verdict(findings, claim)
    return {"errors": errs, "findings": findings, "dropped": dropped, "verdict": verdict, "claim": claim,
            "register": ans.get("场合"), "dispute": dispute,
            "claim_mismatch": claim in VERDICTS and claim != "不确定" and claim != verdict}


def derive_verdict(findings, claim):
    if claim == "不确定":
        return "不确定"
    codes = {f["code"] for f in findings}
    if codes & HARM:
        return "改坏了"
    if codes & (MINOR | RESIDUE | {"U"}):
        return "没改好"
    return "合格"


# ---------------------------------------------------------------- 种子数据与抽样

def pkg(name, default=None):
    return load_json(os.path.join(PKG_DATA, name), default if default is not None else [])


def regression_pool():
    return pkg("regression_seed.json") + load_json(H("regression_extra.json"), [])


def clean_pool():
    return pkg("clean_seed.json") + load_json(H("clean.json"), [])


def precedent_library():
    seeds = pkg("precedents.json")
    answered = [p for p in read_jsonl(H("precedents.jsonl"))]
    return seeds, answered


def rotate(pool, k, date, salt):
    if not pool or k <= 0:
        return []
    pool = sorted(pool, key=lambda x: x["id"])
    day = dt.date.fromisoformat(date).toordinal()
    rng = random.Random(f"{salt}-{day // max(1, len(pool) // max(1, k))}")
    order = pool[:]
    rng.shuffle(order)
    start = (day * k) % len(order)
    return [order[(start + i) % len(order)] for i in range(min(k, len(order)))]


def pick_calibration(cfg, st, date):
    cases = {str(c["id"]): c for c in pkg("cases50.json")}
    labels = pkg("labels.json", {})
    recent = {tuple(x[1]) for x in st.get("calib_recent", []) if days_between(x[0], date) < 14}
    buckets = {"红": [], "橙": [], "绿": []}
    for cid, lab in labels.items():
        for tool in ("我们", "工具1", "工具2"):
            f = lab.get(tool, {}).get("f")
            if f in buckets and cases.get(cid, {}).get(tool):
                buckets[f].append((cid, tool))
    rng = random.Random("calib-" + date)
    picks = []
    for f, n in (("红", cfg["daily"]["calib_red"]), ("橙", cfg["daily"]["calib_orange"]), ("绿", cfg["daily"]["calib_green"])):
        pool = [x for x in buckets[f] if x not in recent] or buckets[f]
        rng.shuffle(pool)
        picks += [(x, f) for x in pool[:n]]
    rng.shuffle(picks)
    queue, key = [], {}
    for i, ((cid, tool), f) in enumerate(picks, 1):
        c = cases[cid]
        item = {"原文": c["原始"], "上下文": "", "任务": "改写"}
        chk = mechanical_check(item, c[tool])
        kid = f"K{i:02d}"
        queue.append({"jid": kid, "任务": "改写", "文体": c.get("文体", ""), "力度": "标准", "原文": c["原始"],
                      "上下文": "", "事实": [], "改写": chk["body"], "给作者": chk["notes"],
                      "旗标": chk["flags"], "提示": chk["hints"], "判例": [],
                      "作者说明": notes_for(c.get("文体", ""))})
        key[kid] = {"case": cid, "tool": tool, "f": f}
    return queue, key


def active_notes():
    return [n for n in read_jsonl(H("notes.jsonl")) if n.get("status") == "active"]


def notes_for(genre, k=5):
    """作者说过的原话里适用于这个文体的（没限定文体的都适用），取最近 k 条。"""
    out = [{"id": n["id"], "原话": n["text"]} for n in active_notes()
           if not n.get("文体") or any(t in (genre or "") for t in n["文体"])]
    return out[-k:]


def nearest_precedents(text, k=2, exclude_source=None):
    seeds, answered = precedent_library()
    scored = []
    for p in answered:
        s = jaccard(text, (p.get("原文片段", "") or "") + (p.get("改写片段", "") or ""))
        scored.append((s, {"来源": "作者回答 " + p.get("id", ""), "原文片段": p.get("原文片段", ""),
                           "改写片段": p.get("改写片段", ""), "作者判断": p.get("answer", ""), "备注": p.get("note", "")}))
    for p in seeds:
        if exclude_source and p.get("来源") == exclude_source:
            continue
        if not p.get("评语"):
            continue
        s = jaccard(text, p.get("原文", ""))
        scored.append((s, {"来源": p["来源"] + "·" + p["工具"], "文体": p.get("文体", ""),
                           "保真档": p.get("保真档", ""), "作者原话": (p.get("总评", "") + "；" + p["评语"]).strip("；")}))
    scored.sort(key=lambda x: -x[0])
    return [dict(v, 相似度=round(s, 2)) for s, v in scored[:k] if s >= 0.12]


def item_precedents(it):
    """真实材料带着作者对这段旧改写的评价时，它就是这道题最贴身的判例，排第一。"""
    ev = it.get("作者评价") or {}
    if not ev.get("评价"):
        return nearest_precedents(it["原文"], 2)
    own = {"来源": "作者对这段原文旧改写的评价（" + it.get("来源", "") + "）",
           "改写片段": ev.get("旧改写", "")[:400], "作者原话": ev["评价"][:800]}
    return [own] + nearest_precedents(it["原文"], 1)


# ---------------------------------------------------------------- 问题池与病灶

def pool_entries():
    return read_jsonl(H("pool.jsonl"))


def eligible_clusters(cfg, st, date):
    fixed_at = st.get("cluster_fixed_at", {})
    groups = {}
    for e in pool_entries():
        c = e["cluster"]
        if c == "P" or e.get("release", "v0000") < fixed_at.get(c, "v0000"):
            continue
        groups.setdefault(c, []).append(e)
    out = []
    for c, es in groups.items():
        cd = st.get("cooldown", {}).get(c, {})
        spread = max(len({e["date"] for e in es}), len({e["kind"] for e in es}))
        row = {"cluster": c, "count": len(es), "days": len({e["date"] for e in es}),
               "kinds": sorted({e["kind"] for e in es}), "cooldown_until": cd.get("until"),
               "status": cd.get("status", "")}
        row["eligible"] = (len(es) >= cfg["cluster"]["min_findings"] and spread >= cfg["cluster"]["min_spread"]
                           and not (cd.get("until") and cd["until"] > date) and cd.get("status") != "stuck")
        out.append(row)
    sev = {c: i for i, c in enumerate(SEVERITY)}
    out.sort(key=lambda r: (not r["eligible"], sev.get(r["cluster"].split("·")[0], 99), -r["count"]))
    return out, groups


def split_dev_holdout(entries):
    by_item = {}
    for e in entries:
        if (e.get("item") or {}).get("原文"):
            by_item.setdefault(e["item_id"], []).append(e)
    ids = sorted(by_item, key=lambda i: hashlib.md5(i.encode()).hexdigest())
    dev_ids, hold_ids = ids[0::2], ids[1::2]
    return [e for i in dev_ids for e in by_item[i]], [by_item[i][0] for i in hold_ids]


# ---------------------------------------------------------------- 指纹

def constitution_text(skill_md):
    text = read_text(skill_md)
    parts, pos = [], 0
    while True:
        s = text.find(MARK_START, pos)
        if s < 0:
            break
        e = text.find(MARK_END, s)
        if e < 0:
            break
        parts.append(text[s:e])
        pos = e + len(MARK_END)
    return "\n".join(parts)


def find_shuohua_dir(cfg):
    cands = [cfg.get("shuohua_skill_dir") or "", os.path.join(os.path.dirname(SKILL_DIR), "haohao-shuohua")]
    home = os.path.expanduser("~")
    for root in (".agents/skills", ".claude/skills", ".cursor/skills", ".trae/skills", ".trae-cn/skills",
                 ".codex/skills", "skills", ".mira/skills"):
        cands.append(os.path.join(home, root, "haohao-shuohua"))
    for c in cands:
        if c and os.path.exists(os.path.join(c, "SKILL.md")):
            return os.path.abspath(c)
    return ""


def fingerprints(cfg):
    fp = {}
    sd = find_shuohua_dir(cfg)
    fp["shuohua_dir"] = sd
    if sd:
        fp["shuohua_skill"] = sha(read_text(os.path.join(sd, "SKILL.md")))
        refs = sorted(glob.glob(os.path.join(sd, "references", "*.md")))
        fp["shuohua_refs"] = sha("".join(read_text(p) for p in refs))
        fp["constitution"] = sha(constitution_text(os.path.join(sd, "SKILL.md")))
    files = [os.path.join(SKILL_DIR, "SKILL.md")] + sorted(glob.glob(os.path.join(SKILL_DIR, "references", "*.md"))) \
        + sorted(glob.glob(os.path.join(SKILL_DIR, "scripts", "*.py")))
    fp["eval_skill"] = sha("".join(read_text(p) for p in files))
    fp["config"] = sha(json.dumps(cfg, ensure_ascii=False, sort_keys=True))
    fp["published"] = file_sha(published_path())
    return fp


# ---------------------------------------------------------------- 细则文件

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


NEGATION = re.compile(r"不|别|勿|禁止|严禁|避免|防止|没有")


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


# ---------------------------------------------------------------- init / status

def cmd_init(args):
    os.makedirs(eval_home(), exist_ok=True)
    if os.path.exists(H("state.json")):
        if not args.force:
            print(f"已经初始化过：{eval_home()}。只想刷新配置（技能目录、模型名）就加 --force，数据和发布记录都不动。")
            return 0
        with Lock():
            cfg = load_config()
            if args.shuohua_dir:
                cfg["shuohua_skill_dir"] = os.path.abspath(args.shuohua_dir)
            cfg["shuohua_skill_dir"] = find_shuohua_dir(cfg)
            if args.model:
                cfg["model_name"] = args.model
            save_json(H("config.json"), cfg)
            st = load_state()
            st["constitution"] = fingerprints(cfg).get("constitution", "")
            save_state(st)
        print(f"配置已刷新：好好说话技能目录 {cfg['shuohua_skill_dir'] or '没找到'}。数据和发布记录没动。")
        return 0
    with Lock():
        cfg = load_config()
        if args.shuohua_dir:
            cfg["shuohua_skill_dir"] = os.path.abspath(args.shuohua_dir)
        found = find_shuohua_dir(cfg)
        cfg["shuohua_skill_dir"] = found
        if args.model:
            cfg["model_name"] = args.model
        save_json(H("config.json"), cfg)
        today = today_str(args)
        old = {}
        pub = published_path()
        existing = read_text(pub) if os.path.exists(pub) else ""
        existing = re.sub(r"^# 好好说话 · 每日细则\s*", "", rules_of(existing)[1]).strip()
        existing = "" if existing == "（还没有细则）" else existing
        write_text(H("releases", "v0000", "daily-learning.md"), existing)
        save_json(H("releases", "v0000", "meta.json"), {"id": "v0000", "date": today,
                                                        "source": "初始化时已有的文件" if existing else "空"})
        st = {"schema": 1, "created": old.get("created", today), "mode": "shadow", "shadow_start": today,
              "published": {"release": "v0000", "sha": file_sha(pub), "date": today},
              "rc": None, "anchor": "v0000", "releases": old.get("releases", []),
              "cluster_fixed_at": old.get("cluster_fixed_at", {}), "cooldown": old.get("cooldown", {}),
              "calib_recent": [], "calib_history": old.get("calib_history", []), "audits": old.get("audits", []),
              "next_dispute": old.get("next_dispute", 1), "next_rc": old.get("next_rc", 1),
              "next_release": old.get("next_release", 1), "paused_reason": None,
              "constitution": fingerprints(cfg).get("constitution", "")}
        save_state(st)
        for d in ("runs", "releases", "exports"):
            os.makedirs(H(d), exist_ok=True)
    print(f"初始化完成：{eval_home()}")
    print(f"好好说话技能目录：{found or '没找到，底线哈希和技能指纹先跳过；在 config.json 里填 shuohua_skill_dir'}")
    print(f"细则发布位置：{pub}（{'已有文件，记为 v0000' if existing else '还没有，记为空的 v0000'}）")
    print(f"模式：影子运行 {cfg['shadow_days']} 天，只记录不发布。")
    print("可选：把人写的干净文本导进来做误改对照：python3 scripts/loop.py import-clean 文件.json")
    return 0


def cmd_status(args):
    cfg, st = load_config(), load_state()
    today = today_str(args)
    rows, _ = eligible_clusters(cfg, st, today)
    open_d = [d for d in read_jsonl(H("disputes.jsonl")) if d["status"] == "open"]
    print(f"数据目录：{eval_home()}")
    print(f"模式：{mode_label(cfg, st, today)}")
    print(f"现用细则：{st['published']['release']}（{st['published']['date']}）· 锚点：{st['anchor']}"
          + (f" · 预发布：{st['rc']['id']}（{st['rc']['cluster']}）" if st.get("rc") else ""))
    print(f"待你判断：{len(open_d)} 条 · 作者说明：{len(active_notes())} 条")
    if st.get("pack_seq"):
        print(f"数据包：最近打的是第 {st['pack_seq']} 份（{st.get('packed', '')}）")
    print("问题池（前 8 类）：")
    for r in rows[:8]:
        tag = "够数" if r["eligible"] else ("冷却到 " + r["cooldown_until"] if r["cooldown_until"] and r["cooldown_until"] > today else ("招不回" if r["status"] == "stuck" else "未够数"))
        print(f"  {r['cluster']:<10} {r['count']:>3} 条 · {r['days']} 天 · {'/'.join(r['kinds'])} · {tag}")
    runs = sorted(glob.glob(H("runs", "*", "decision.json")))
    if runs:
        d = load_json(runs[-1])
        print(f"最近一次：{d.get('date')} · {d.get('headline')}")
    return 0


def mode_label(cfg, st, date):
    if st["mode"] == "shadow":
        n = days_between(st["shadow_start"], date) + 1
        return f"影子运行第 {n}/{cfg['shadow_days']} 天（只记录不发布）"
    if st["mode"] == "paused":
        return "自动发布已暂停：" + (st.get("paused_reason") or "")
    return "自动发布"


# ---------------------------------------------------------------- start

def maybe_auto_switch(cfg, st, date, notes):
    if st["mode"] != "shadow" or not cfg.get("auto_switch"):
        return
    if days_between(st["shadow_start"], date) < cfg["shadow_days"]:
        return
    hist = [h for h in st.get("calib_history", []) if h["date"] >= st["shadow_start"]]
    ok_days = sum(1 for h in hist if h["pass"])
    audits = [a for a in st.get("audits", []) if a.get("answer") in ("有", "没有")]
    miss = sum(1 for a in audits if a["answer"] == "有")
    miss_rate = miss / len(audits) if audits else 0.0
    if hist and ok_days / len(hist) >= 0.7 and miss_rate <= cfg["disputes"]["audit_miss_pause"]:
        st["mode"] = "auto"
        st["anchor"] = st["published"]["release"]
        thin = "（抽查答得少，漏判率只能参考）" if len(audits) < cfg["disputes"]["audit_min_answered"] else ""
        notes.append(f"影子期结束：裁判体检 {ok_days}/{len(hist)} 天通过，抽查漏判 {miss}/{len(audits)}{thin}，已切到自动发布。"
                     "想继续只记录不发布，回复「保持影子」。")
    else:
        st["shadow_start"] = (dt.date.fromisoformat(date) - dt.timedelta(days=cfg["shadow_days"] - 7)).isoformat()
        notes.append(f"影子期到期但条件不够（体检通过 {ok_days}/{len(hist)} 天，抽查漏判 {miss}/{len(audits)}），再影子运行 7 天。")


def cmd_start(args):
    cfg, st = load_config(), load_state()
    today = today_str(args)
    rd = run_dir(today)
    if os.path.exists(os.path.join(rd, "manifest.json")) and not args.force:
        print(f"今天这一轮已经开过：{rd}。接着往下跑就行；要整轮重开加 --force。")
        print_plan(load_json(os.path.join(rd, "plan.json")), rd)
        return 0
    with Lock():
        if args.force and os.path.exists(rd):
            os.replace(rd, rd + ".bak-" + dt.datetime.now().strftime("%H%M%S"))
        notes = []
        maybe_auto_switch(cfg, st, today, notes)
        notes += expire_disputes(cfg, st, today)
        fp = fingerprints(cfg)
        if fp.get("constitution") and st.get("constitution") and fp["constitution"] != st["constitution"]:
            notes.append("好好说话的底线条款跟上次不一样了（作者手工改过），已记下新版本。")
            st["constitution"] = fp["constitution"]
        manual = fp["published"] != st["published"]["sha"]
        if manual:
            notes.append("daily-learning.md 被手工改过：今天不出候选、不发布。回复「接受手工修改」后恢复。")
        confirm = bool(st.get("rc")) and st["rc"]["date"] < today and not manual
        calib_q, calib_key = pick_calibration(cfg, st, today)
        calib_cases = {f"cases50#{v['case']}" for v in calib_key.values()}
        items = []
        reg_pool = [r for r in regression_pool() if r.get("来源") not in calib_cases]
        for it in rotate(reg_pool, cfg["daily"]["regression"], today, "reg"):
            items.append(dict(it, id=f"{today}-{it['id']}", kind="regression", group="regression", origin=it["id"]))
        items += pick_clean(cfg, today)
        target = None
        if not confirm and not manual:
            rows, groups = eligible_clusters(cfg, st, today)
            elig = [r for r in rows if r["eligible"]]
            if elig:
                c = elig[0]["cluster"]
                dev, hold = split_dev_holdout(groups[c])
                target = {"cluster": c, "name": CODES.get(c.split("·")[0], c), "count": elig[0]["count"],
                          "dev": dev, "holdout": [h["item_id"] for h in hold]}
                for n, h in enumerate(hold, 1):
                    snap = h.get("item", {})
                    items.append({"id": f"{today}-h{n:02d}", "kind": "holdout", "group": "target", "cluster": c,
                                  "origin": h["item_id"], "任务": snap.get("任务", "改写"), "文体": snap.get("文体", ""),
                                  "力度": snap.get("力度", "标准"), "原文": snap.get("原文", ""),
                                  "上下文": snap.get("上下文", ""), "事实": snap.get("事实", [])})
        write_jsonl(os.path.join(rd, "calib", "queue.jsonl"), calib_q)
        save_json(os.path.join(rd, "private", "calib_key.json"), calib_key)
        st["calib_recent"] = [x for x in st.get("calib_recent", []) if days_between(x[0], today) < 14] + \
            [[today, [v["case"], v["tool"]]] for v in calib_key.values()]
        save_json(os.path.join(rd, "items.json"), items)
        write_text(os.path.join(rd, "overlays", "current.md"), read_text(published_path()) or with_header("", st["published"]["release"], today))
        versions = ["current"]
        if confirm:
            write_text(os.path.join(rd, "overlays", "rc.md"), with_header(release_text(st["rc"]["id"]), st["rc"]["id"], today))
            versions.append("rc")
            if st["anchor"] != st["published"]["release"]:
                write_text(os.path.join(rd, "overlays", "anchor.md"), with_header(release_text(st["anchor"]), st["anchor"], today))
                versions.append("anchor")
        if target:
            save_json(os.path.join(rd, "target.json"), target)
        d = cfg["daily"]
        plan = {"date": today, "mode": st["mode"], "confirm_rc": confirm, "versions": versions,
                "target": {k: target[k] for k in ("cluster", "name", "count", "holdout")} if target else None,
                "quota": {"synthetic": d["synthetic"], "drafting": d["drafting"], "real_max": d["real_max"],
                          "probes": d["probes"] if target else 0},
                "calib_n": len(calib_q), "notes": notes, "manual_edit": manual}
        save_json(os.path.join(rd, "plan.json"), plan)
        save_json(os.path.join(rd, "manifest.json"), {"date": today, "fingerprints": fp, "mode": st["mode"],
                                                      "published": st["published"], "rc": st.get("rc"),
                                                      "anchor": st["anchor"], "model": args.model or cfg.get("model_name", "")})
        st["last_run"] = today
        save_state(st)
    print_plan(plan, rd)
    return 0


def pick_clean(cfg, today):
    out = []
    k = cfg["daily"]["clean"]
    prev = sorted(d for d in glob.glob(H("runs", "*")) if os.path.basename(d) < today)
    if prev and k > 0:
        last = prev[-1]
        items = {i["id"]: i for i in load_json(os.path.join(last, "items.json"), [])}
        for path in sorted(glob.glob(os.path.join(last, "judgments", "current", "*.json"))):
            j = load_json(path)
            it = items.get(j["item_id"])
            if not it or j["verdict"] != "合格" or it.get("任务") != "改写" or it.get("group") not in ("fresh", "regression"):
                continue
            body = split_output(read_text(os.path.join(last, "outputs", "current", j["item_id"] + ".txt")))[0]
            if body and not cjk_len(body) > 400:
                out.append({"id": f"{today}-idem01", "kind": "clean-idem", "group": "clean", "任务": "改写",
                            "文体": it.get("文体", ""), "力度": "标准", "原文": body, "上下文": it.get("上下文", ""),
                            "origin": j["item_id"], "来源": "昨天判为合格的改写，再洗一遍"})
                break
    for n, it in enumerate(rotate(clean_pool(), k - len(out), today, "clean"), 1):
        out.append(dict(it, id=f"{today}-{it['id']}", kind="clean", group="clean", origin=it["id"]))
    return out


def print_plan(plan, rd):
    print(f"今天的运行目录：{rd}")
    for n in plan.get("notes", []):
        print("注意：" + n)
    print(f"模式：{plan['mode']} · 要改写的版本：{'、'.join(plan['versions'])}"
          + (" · 今天复测预发布，不出新候选" if plan["confirm_rc"] else ""))
    t = plan.get("target")
    if t:
        print(f"今天的目标病灶：{t['cluster']}（{t['name']}，池里 {t['count']} 条）。开发组证据在 target.json，"
              f"留作验证的 {len(t['holdout'])} 条已放进题目，写候选时不许看它们。")
    else:
        print("今天没有够数的病灶，只召回，不出候选。")
    q = plan["quota"]
    print(f"要出的新题：合成改写 {q['synthetic']} 条、起草 {q['drafting']} 条"
          + (f"、针对目标病灶的探针 {q['probes']} 条" if q["probes"] else "")
          + f"；真实材料最多 {q['real_max']} 条（没有就不加）。")
    print(f"裁判体检：{plan['calib_n']} 条，在 calib/queue.jsonl，答案写到 calib/answers.jsonl。")
    print("下一步：体检 → python3 scripts/loop.py calib-score；出题 → add-items；改写 → writer-view。")


# ---------------------------------------------------------------- 题目

REQUIRED_FACT_KINDS = {"synthetic", "probe", "drafting"}


def all_past_items(before):
    out = []
    for d in sorted(glob.glob(H("runs", "*"))):
        if os.path.basename(d) >= before:
            continue
        out += load_json(os.path.join(d, "items.json"), [])
    return out


def cmd_add_items(args):
    today = today_str(args)
    rd = run_dir(today)
    plan = load_json(os.path.join(rd, "plan.json"))
    if not plan:
        raise Stop("今天还没 start。")
    new = load_json(args.file)
    if isinstance(new, dict):
        new = new.get("items", [])
    items = load_json(os.path.join(rd, "items.json"), [])
    past = all_past_items(today)[-2000:] + items + regression_pool() + clean_pool()
    past_sh = [(p.get("id"), shingles(p.get("原文", ""))) for p in past]
    prefix = {"synthetic": "s", "probe": "p", "drafting": "d", "real": "r"}
    errs, added = [], []
    counts = {k: sum(1 for i in items if i.get("kind") == k) for k in prefix}
    q_all = plan["quota"]
    for n, it in enumerate(new, 1):
        kind = it.get("kind")
        tag = f"第 {n} 条"
        if kind not in prefix:
            errs.append(f"{tag}：kind 必须是 synthetic / probe / drafting / real")
            continue
        task = "起草" if kind == "drafting" else it.get("任务", "改写")
        src = (it.get("原文") or "").strip()
        if cjk_len(src) < 20:
            errs.append(f"{tag}：原文（起草题是材料）太短")
            continue
        if not it.get("文体"):
            errs.append(f"{tag}：缺文体")
            continue
        if kind == "drafting" and not it.get("要求"):
            errs.append(f"{tag}：起草题要写「要求」")
            continue
        facts = it.get("事实") or []
        if kind in REQUIRED_FACT_KINDS:
            if len(facts) < 3:
                errs.append(f"{tag}：{kind} 题至少要 3 条事实")
                continue
            bad = [f.get("id") for f in facts if not f.get("id") or not f.get("关键词")
                   or not all(quote_in(k, src) for k in f["关键词"])]
            if bad:
                errs.append(f"{tag}：这些事实缺 id/关键词，或关键词不在原文里：{bad}")
                continue
        if kind == "probe" and (it.get("cluster") != (plan.get("target") or {}).get("cluster") or not it.get("陷阱")):
            errs.append(f"{tag}：探针要写 cluster（等于今天的目标病灶）和 陷阱")
            continue
        if kind == "real" and not it.get("来源"):
            errs.append(f"{tag}：真实材料要写来源")
            continue
        ev = it.get("作者评价")
        if ev is not None and (kind != "real" or not isinstance(ev, dict) or not (ev.get("评价") or "").strip()):
            errs.append(f"{tag}：作者评价只给真实材料，写成 {{\"旧改写\": \"...\", \"评价\": \"作者原话\"}}")
            continue
        cap = {"synthetic": q_all["synthetic"], "drafting": q_all["drafting"], "probe": q_all["probes"],
               "real": q_all["real_max"]}[kind]
        if counts[kind] >= cap:
            errs.append(f"{tag}：今天的 {kind} 题已经够 {cap} 条了")
            continue
        sh = shingles(src)
        dup = next((pid for pid, psh in past_sh if psh and len(sh & psh) / max(1, len(sh | psh)) >= 0.8), None)
        if dup:
            errs.append(f"{tag}：跟 {dup} 几乎一样，换一条")
            continue
        counts[kind] += 1
        iid = f"{today}-{prefix[kind]}{counts[kind]:02d}"
        rec = {"id": iid, "kind": kind, "group": "target" if kind == "probe" else "fresh", "任务": task,
               "文体": it["文体"], "读者": it.get("读者", ""), "场合": it.get("场合", ""),
               "力度": it.get("力度", "标准"), "原文": src, "上下文": it.get("上下文", ""),
               "要求": it.get("要求", ""), "事实": facts, "陷阱": it.get("陷阱", ""),
               "cluster": it.get("cluster", ""), "来源": it.get("来源", "synthetic:" + today)}
        if ev:
            rec["作者评价"] = {"旧改写": (ev.get("旧改写") or "").strip(), "评价": ev["评价"].strip()}
        items.append(rec)
        past_sh.append((iid, sh))
        added.append(iid)
    save_json(os.path.join(rd, "items.json"), items)
    print(f"收下 {len(added)} 条：{'、'.join(added) if added else '无'}")
    for e in errs:
        print("退回：" + e)
    q = plan["quota"]
    have = {k: sum(1 for i in items if i.get("kind") == k) for k in prefix}
    print(f"今天已有：合成 {have['synthetic']}/{q['synthetic']}，起草 {have['drafting']}/{q['drafting']}，"
          f"探针 {have['probe']}/{q['probes']}，真实 {have['real']}/{q['real_max']}")
    return 1 if errs else 0


def needed(version, items, plan):
    groups = {"current": {"fresh", "target", "regression", "clean"}, "cand": {"target", "regression", "clean"},
              "rc": {"fresh", "regression", "clean"}, "anchor": {"regression"}}[version]
    return [i for i in items if i.get("group") in groups]


def cmd_writer_view(args):
    today = today_str(args)
    rd = run_dir(today)
    plan = load_json(os.path.join(rd, "plan.json"))
    items = load_json(os.path.join(rd, "items.json"), [])
    v = args.version
    if v == "cand" and not os.path.exists(os.path.join(rd, "overlays", "cand.md")):
        raise Stop("候选还没 stage，不能改写 cand。")
    if v not in plan["versions"] and v != "cand":
        raise Stop(f"今天不需要改写 {v} 版。")
    todo = [i for i in needed(v, items, plan) if not os.path.exists(os.path.join(rd, "outputs", v, i["id"] + ".txt"))]
    print(f"版本 {v}：还有 {len(todo)} 条要写。改写时把 {os.path.join(rd, 'overlays', v + '.md')} 当作 daily-learning.md 读，"
          f"不读已发布那份。每条只看下面给的内容，写到指定文件；原文缺的具体写在正文后面的「【给作者】」一段里。")
    for i in todo:
        print("\n" + "=" * 60)
        print(f"题 {i['id']} → 写到 {os.path.join(rd, 'outputs', v, i['id'] + '.txt')}")
        print(f"任务：{i.get('任务', '改写')} · 文体：{i.get('文体', '')}" + (f" · 读者：{i['读者']}" if i.get("读者") else "")
              + f" · 力度：{i.get('力度', '标准')}")
        if i.get("任务") == "起草":
            print("【材料】\n" + i["原文"])
            print("【要求】\n" + i.get("要求", ""))
        else:
            print("【原文】\n" + i["原文"])
        if i.get("上下文"):
            print("【上下文】\n" + i["上下文"])
    return 0


# ---------------------------------------------------------------- 候选

def cmd_target(args):
    rd = run_dir(today_str(args))
    t = load_json(os.path.join(rd, "target.json"))
    if not t:
        print("今天没有目标病灶。")
        return 0
    print(f"目标病灶：{t['cluster']}（{t['name']}），开发组证据 {len(t['dev'])} 条：")
    for e in t["dev"]:
        print(f"- [{e['date']} {e['文体']}] 原文：{e.get('quote_src') or '（无）'} ｜ 改写：{e.get('quote_out') or '（无）'} ｜ 裁判：{e.get('note', '')}")
    notes = active_notes()
    if notes:
        print("\n作者说过的话（候选细则不许跟这些冲突）：")
        for n in notes:
            print(f"- {n['id']}（{'、'.join(n['文体']) if n.get('文体') else '所有文体'}）：{n['text']}")
    print(f"\n现用细则：{os.path.join(rd, 'overlays', 'current.md')}")
    print("写候选前读 references/fix-proposal.md。写好后：python3 scripts/loop.py stage 候选文件.md")
    return 0


def cmd_stage(args):
    cfg, st = load_config(), load_state()
    today = today_str(args)
    rd = run_dir(today)
    plan = load_json(os.path.join(rd, "plan.json"))
    items = load_json(os.path.join(rd, "items.json"), [])
    if plan.get("confirm_rc"):
        raise Stop("今天是复测日，不出新候选。")
    if args.aa:
        if st["mode"] != "shadow":
            raise Stop("A/A 自测只在影子期做。")
    elif not plan.get("target"):
        raise Stop("今天没有目标病灶，不出候选。")
    calib = load_json(os.path.join(rd, "calib", "result.json"))
    if not calib or not calib.get("pass"):
        raise Stop("裁判体检没过（或还没跑 calib-score），今天不出候选。")
    gate_items = needed("cand", items, plan)
    if not args.aa and not any(i["kind"] == "probe" for i in gate_items):
        raise Stop("还没加针对目标病灶的探针题（add-items，kind=probe）。")
    missing = [i["id"] for i in gate_items if not os.path.exists(os.path.join(rd, "outputs", "current", i["id"] + ".txt"))]
    if missing:
        raise Stop("这些题的现用版改写还没写，先写完再 stage（防止候选影响现用版）：" + "、".join(missing))
    text = read_text(args.file)
    current = read_text(os.path.join(rd, "overlays", "current.md"))
    if args.aa:
        text = current
    hold = [i["原文"] for i in items if i.get("group") == "target"]
    errs, changed = validate_candidate(text, cfg, current, hold, aa=args.aa)
    if errs:
        print("候选没通过格式检查：")
        for e in errs:
            print("- " + e)
        return 1
    _, body = rules_of(text)
    body = re.sub(r"^# 好好说话 · 每日细则\s*", "", body).strip()
    write_text(os.path.join(rd, "overlays", "cand.md"), with_header(body, "候选", today))
    save_json(os.path.join(rd, "candidate.json"), {"sha": sha(body), "changed": sorted(changed), "aa": bool(args.aa),
                                                   "cluster": (plan.get("target") or {}).get("cluster", "A/A"),
                                                   "note": read_text(args.note) if args.note else ""})
    print(f"候选已冻结：overlays/cand.md（改动细则：{'、'.join(sorted(changed)) or 'A/A 自测，无改动'}）。")
    print("下一步：python3 scripts/loop.py writer-view cand，逐条写 cand 版改写。")
    return 0


# ---------------------------------------------------------------- 检查、盲评、核对

def versions_present(rd):
    return [v for v in VERSIONS if os.path.isdir(os.path.join(rd, "outputs", v))]


def cmd_check(args):
    rd = run_dir(today_str(args))
    plan = load_json(os.path.join(rd, "plan.json"))
    items = load_json(os.path.join(rd, "items.json"), [])
    missing, total = [], 0
    vs = [v for v in VERSIONS if v in plan["versions"] or (v == "cand" and os.path.exists(os.path.join(rd, "overlays", "cand.md")))]
    for v in vs:
        for it in needed(v, items, plan):
            p = os.path.join(rd, "outputs", v, it["id"] + ".txt")
            if not os.path.exists(p):
                missing.append(f"{v}/{it['id']}")
                continue
            out = read_text(p)
            if not split_output(out)[0]:
                missing.append(f"{v}/{it['id']}（文件是空的）")
                continue
            save_json(os.path.join(rd, "checks", v, it["id"] + ".json"), mechanical_check(it, out))
            total += 1
    print(f"机械检查完成 {total} 份。")
    if missing:
        print("还缺这些改写：" + "、".join(missing))
        return 1
    return 0


def cmd_blind(args):
    rd = run_dir(today_str(args))
    if cmd_check(args) != 0:
        raise Stop("还有改写没写完，写完再生成盲评队列。")
    items = {i["id"]: i for i in load_json(os.path.join(rd, "items.json"), [])}
    keyp = os.path.join(rd, "private", "judge_key.json")
    key = load_json(keyp, {})
    queue = read_jsonl(os.path.join(rd, "judge", "queue.jsonl"))
    have = {(m[0], m[1]) for ms in key.values() for m in ms}
    by_body = {}
    for jid, ms in key.items():
        for iid, v, bsha in ms:
            by_body[(iid, bsha)] = jid
    fresh = []
    for v in versions_present(rd):
        for path in sorted(glob.glob(os.path.join(rd, "checks", v, "*.json"))):
            iid = os.path.basename(path)[:-5]
            if (iid, v) in have or iid not in items:
                continue
            chk = load_json(path)
            fresh.append((iid, v, chk))
    rng = random.Random(os.urandom(8))
    rng.shuffle(fresh)
    n = len(key)
    for iid, v, chk in fresh:
        bsha = sha(norm(chk["body"]) + "|" + norm(chk["notes"]))
        if (iid, bsha) in by_body:
            key[by_body[(iid, bsha)]].append([iid, v, bsha])
            continue
        n += 1
        jid = f"J{n:03d}"
        it = items[iid]
        key[jid] = [[iid, v, bsha]]
        by_body[(iid, bsha)] = jid
        queue.append({"jid": jid, "任务": it.get("任务", "改写"), "文体": it.get("文体", ""), "读者": it.get("读者", ""),
                      "力度": it.get("力度", "标准"), "原文": it["原文"], "上下文": it.get("上下文", ""),
                      "要求": it.get("要求", ""),
                      "事实": [{"id": f["id"], "内容": f.get("内容", "")} for f in it.get("事实", []) or []],
                      "改写": chk["body"], "给作者": chk["notes"], "旗标": chk["flags"], "提示": chk["hints"],
                      "判例": item_precedents(it), "作者说明": notes_for(it.get("文体", ""))})
    write_jsonl(os.path.join(rd, "judge", "queue.jsonl"), queue)
    save_json(keyp, key)
    print(f"盲评队列 {len(queue)} 份（新加 {len(fresh)} 份；同一题两个版本一字不差的只判一次）。")
    print(f"队列：{os.path.join(rd, 'judge', 'queue.jsonl')}；答案一行一个 JSON，写到 judge/answers.jsonl。")
    print("判之前不要打开 private/ 目录。判法见 references/judge-protocol.md。")
    return 0


def read_answers(d):
    rows = []
    p = os.path.join(d, "answers.jsonl")
    if os.path.exists(p):
        rows = read_jsonl(p)
    pj = os.path.join(d, "answers.json")
    if os.path.exists(pj):
        obj = load_json(pj)
        rows += obj if isinstance(obj, list) else []
    last = {}
    for r in rows:
        if isinstance(r, dict) and r.get("jid"):
            last[r["jid"]] = r
    return list(last.values())


def cmd_verify(args):
    rd = run_dir(today_str(args))
    queue = {q["jid"]: q for q in read_jsonl(os.path.join(rd, "judge", "queue.jsonl"))}
    key = load_json(os.path.join(rd, "private", "judge_key.json"), {})
    answers = {a["jid"]: a for a in read_answers(os.path.join(rd, "judge"))}
    bad, missing, mism, dropped_n = [], [], 0, 0
    results = {}
    for jid, q in queue.items():
        a = answers.get(jid)
        if not a:
            if args.partial:
                results[jid] = {"errors": [], "findings": [], "dropped": [], "verdict": "不确定", "claim": "没判",
                                "register": None, "dispute": None, "claim_mismatch": False, "unjudged": True}
            else:
                missing.append(jid)
            continue
        r = verify_answer(a, q)
        if r["errors"]:
            bad.append((jid, r["errors"]))
            continue
        mism += r["claim_mismatch"]
        dropped_n += len(r["dropped"])
        results[jid] = r
    if bad or missing:
        for jid, es in bad:
            print(f"{jid} 要重判：" + "；".join(es))
        if missing:
            print("还没判：" + "、".join(missing))
        print("改好 judge/answers.jsonl 里对应的行（同一个 jid 以最后一行为准），再跑一次 verify。")
        return 1
    for jid, r in results.items():
        for iid, v, _ in key.get(jid, []):
            findings = [dict(f, cluster=cluster_of(f["code"], f.get("label", ""))) for f in r["findings"]]
            save_json(os.path.join(rd, "judgments", v, iid + ".json"),
                      {"item_id": iid, "version": v, "jid": jid, "verdict": r["verdict"], "claim": r["claim"],
                       "register": r["register"], "findings": findings, "dropped": r["dropped"],
                       "dispute": r["dispute"], "unjudged": r.get("unjudged", False)})
    save_json(os.path.join(rd, "judge", "verify.json"), {"n": len(results), "dropped_findings": dropped_n,
                                                         "claim_mismatch": mism, "partial": bool(args.partial)})
    print(f"核对完成：{len(results)} 份有效；引用对不上被作废的问题 {dropped_n} 条；结论和问题清单对不上 {mism} 份（按问题清单算）。")
    return 0


def cmd_calib_score(args):
    cfg, st = load_config(), load_state()
    today = today_str(args)
    rd = run_dir(today)
    queue = {q["jid"]: q for q in read_jsonl(os.path.join(rd, "calib", "queue.jsonl"))}
    key = load_json(os.path.join(rd, "private", "calib_key.json"), {})
    answers = {a["jid"]: a for a in read_answers(os.path.join(rd, "calib"))}
    overrides = load_json(H("calib_overrides.json"), {})
    bad = []
    caught = bad_n = fa = good_n = unsure = soft_fa = 0
    detail, conflicts = [], []
    for jid, q in queue.items():
        a = answers.get(jid)
        if not a:
            bad.append((jid, ["还没判"]))
            continue
        r = verify_answer(a, q)
        if r["errors"]:
            bad.append((jid, r["errors"]))
            continue
        k = key[jid]
        cid = f"{k['case']}|{k['tool']}"
        f = overrides.get(cid, {}).get("f") or k["f"]
        is_bad = f in ("红", "橙")
        hit = r["verdict"] == "改坏了"
        unsure += r["verdict"] == "不确定"
        soft = False
        if is_bad:
            bad_n += 1
            caught += hit
        else:
            good_n += 1
            hard = hit and (f == "绿确认" or any(x["code"] in FAB for x in r["findings"]))
            soft = hit and not hard
            fa += hard
            soft_fa += soft
            if soft:
                harm = next(x for x in r["findings"] if x["code"] in HARM)
                conflicts.append({"calib_id": cid, "case": k["case"], "tool": k["tool"], "文体": q.get("文体", ""),
                                  "code": harm["code"], "src": harm.get("src", ""), "out": harm.get("out", ""),
                                  "note": harm.get("note", "")})
        detail.append({"jid": jid, "case": k["case"], "tool": k["tool"], "人工档": f, "裁判": r["verdict"],
                       "对上": hit == is_bad, "分歧": soft})
    if bad:
        for jid, es in bad:
            print(f"{jid}：" + "；".join(es))
        print("体检答案要全部判完且格式合格，改好 calib/answers.jsonl 再跑。")
        return 1
    catch = caught / bad_n if bad_n else 1.0
    far = fa / good_n if good_n else 0.0
    g = cfg["gates"]
    ok = catch >= g["calib_min_catch"] and far <= g["calib_max_false_alarm"]
    res = {"date": today, "catch": round(catch, 2), "false_alarm": round(far, 2), "caught": caught, "bad_n": bad_n,
           "fa": fa, "good_n": good_n, "soft_fa": soft_fa, "unsure": unsure, "pass": ok, "detail": detail,
           "conflicts": conflicts}
    save_json(os.path.join(rd, "calib", "result.json"), res)
    with Lock():
        st = load_state()
        st["calib_history"] = [h for h in st.get("calib_history", []) if h["date"] != today] + \
            [{"date": today, "catch": res["catch"], "false_alarm": res["false_alarm"], "pass": ok}]
        save_state(st)
    extra = f"（另有 {soft_fa} 条跟你当时的判断不一样，会问你一次）" if soft_fa else ""
    print(f"裁判体检：已知改坏的抓到 {caught}/{bad_n}，已知没改坏的误报 {fa}/{good_n}{extra}，拿不准 {unsure} 条 → "
          f"{'通过' if ok else '没过，今天只召回，不出候选、不发布'}")
    return 0


# ---------------------------------------------------------------- 决策

def load_judgments(rd):
    J = {}
    for v in VERSIONS:
        for p in glob.glob(os.path.join(rd, "judgments", v, "*.json")):
            j = load_json(p)
            J.setdefault(v, {})[j["item_id"]] = j
    return J


def codes_of(j):
    return [f["code"] for f in j.get("findings", [])]


def count_in(j, s):
    return sum(1 for c in codes_of(j) if c in s)


def gate_compare(base, cand, items, JB, JC, cfg, target=None, checks=None):
    reasons, stats = [], {}
    ids = [i["id"] for i in items if i["id"] in JB and i["id"] in JC]
    if not ids:
        return {"pass": False, "reasons": ["没有两个版本都判过的题"], "stats": {}}
    unc = sum(1 for i in ids if JB[i]["verdict"] == "不确定" or JC[i]["verdict"] == "不确定")
    stats["题数"] = len(ids)
    stats["不确定"] = unc
    if unc / len(ids) > cfg["gates"]["max_uncertain"]:
        reasons.append(f"拿不准的题占 {unc}/{len(ids)}，超过 {int(cfg['gates']['max_uncertain'] * 100)}%，今天不下结论")
    newfab = [i for i in ids if count_in(JC[i], FAB) and not count_in(JB[i], FAB)]
    stats["新增编造"] = newfab
    if newfab:
        reasons.append("候选新编了原文没有的信息：" + "、".join(newfab))
    cand_unsure = sum(1 for i in ids if JC[i]["verdict"] == "不确定")
    hb = sum(count_in(JB[i], HARM) for i in ids)
    hc = sum(count_in(JC[i], HARM) for i in ids) + cand_unsure
    stats["改坏问题"] = [hb, hc]
    if hc > hb:
        reasons.append(f"改坏类问题变多：{hb} → {hc}（候选拿不准的按改坏算）")
    mb = sum(count_in(JB[i], MINOR) for i in ids)
    mc = sum(count_in(JC[i], MINOR) for i in ids)
    stats["新毛病"] = [mb, mc]
    if mc > mb:
        reasons.append(f"破折号、绕口、手痒这类新毛病变多：{mb} → {mc}")
    reg = [i["id"] for i in items if i.get("group") == "regression" and i["id"] in ids]
    broke = [i for i in reg if JC[i]["verdict"] in ("改坏了", "不确定") and JB[i]["verdict"] not in ("改坏了", "不确定")]
    stats["回归变坏"] = broke
    if broke:
        reasons.append("回归题有原来没坏、现在改坏的：" + "、".join(broke))
    clean = [i["id"] for i in items if i.get("group") == "clean" and i["id"] in ids]
    if clean and checks:
        eb = sum(checks["base"].get(i, {}).get("stats", {}).get("改动比例", 0) for i in clean) / len(clean)
        ec = sum(checks["cand"].get(i, {}).get("stats", {}).get("改动比例", 0) for i in clean) / len(clean)
        stats["干净稿改动比例"] = [round(eb, 3), round(ec, 3)]
        if ec > eb + cfg["gates"]["clean_edit_slack"]:
            reasons.append(f"干净稿被改得更多：改动比例 {eb:.2f} → {ec:.2f}")
    if target:
        tids = [i["id"] for i in items if i.get("group") == "target" and i["id"] in ids]
        has = lambda j: any(f.get("cluster") == target for f in j.get("findings", []))  # noqa: E731
        fixed = sum(1 for i in tids if has(JB[i]) and not has(JC[i]))
        broken = sum(1 for i in tids if has(JC[i]) and not has(JB[i]))
        p = sign_p(fixed, broken)
        stats["目标病灶"] = {"题数": len(tids), "修好": fixed, "新犯": broken, "p": round(p, 3)}
        if fixed + broken < cfg["gates"]["target_min_discordant"] or p >= cfg["gates"]["target_alpha"]:
            reasons.append(f"目标病灶 {target} 修好 {fixed}、新犯 {broken}（p={p:.2f}），不够显著")
    return {"pass": not reasons, "reasons": reasons, "stats": stats}


def sign_p(fixed, broken):
    n = fixed + broken
    if n == 0:
        return 1.0
    return sum(math.comb(n, k) for k in range(fixed, n + 1)) / 2 ** n


def item_metrics(items, JV, checks_v, alarm=0.3):
    body = [i for i in items if i.get("group") in ("fresh", "regression") and i["id"] in JV]
    clean = [i for i in items if i.get("group") == "clean" and i["id"] in JV]
    n = len(body)
    harm = sum(1 for i in body if JV[i["id"]]["verdict"] == "改坏了")
    fab = sum(1 for i in body if count_in(JV[i["id"]], FAB))
    resi = sum(1 for i in body if count_in(JV[i["id"]], RESIDUE))
    unsure = sum(1 for i in body if JV[i["id"]]["verdict"] == "不确定")
    over = 0
    for i in clean:
        er = checks_v.get(i["id"], {}).get("stats", {}).get("改动比例", 0)
        if count_in(JV[i["id"]], {"H"}) or er >= alarm:
            over += 1
    return {"n": n, "harm": harm, "fab": fab, "residue": resi, "unsure": unsure, "clean_n": len(clean), "over_edit": over}


def load_checks(rd, v):
    return {os.path.basename(p)[:-5]: load_json(p) for p in glob.glob(os.path.join(rd, "checks", v, "*.json"))}


def next_dispute_id(existing):
    nums = [int(d["id"][1:]) for d in existing if re.match(r"D\d+$", d.get("id", ""))]
    return max(nums, default=0) + 1


def new_dispute(st, kind, item, version, src, out, reason, suspect, date, affects):
    did = f"D{st['_next_d']}"
    st["_next_d"] += 1
    q = {"保真": "这处改写有没有改掉原文的意思？", "场合": f"放在「{item.get('文体', '')}」里，这个说法有没有不合适？",
         "新问题": "改写这句读着还有 AI 味吗？", "抽查": "整段看，这版改写有没有改坏或者没改好？",
         "体检": "这处算不算改坏了？"}[kind]
    default = {"保真": "有", "场合": "有", "新问题": "没有", "抽查": "跳过", "体检": "跳过"}[kind]
    return {"id": did, "created": date, "kind": kind, "item_id": item["id"], "version": version, "文体": item.get("文体", ""),
            "原文片段": src, "改写片段": out, "原因": reason, "疑似编码": suspect, "question": q, "default": default,
            "affects": affects, "status": "open", "answer": None, "answered": None, "note": ""}


def auto_match(d, cfg):
    if d["kind"] in ("抽查", "体检"):
        return d
    best, bs = None, 0.0
    for p in read_jsonl(H("precedents.jsonl")):
        if p.get("kind") != d["kind"]:
            continue
        s = jaccard(d["原文片段"] + d["改写片段"], p.get("原文片段", "") + p.get("改写片段", ""))
        if s > bs:
            best, bs = p, s
    if best and bs >= cfg["disputes"]["auto_match_similarity"]:
        d.update(status="auto", answer=best["answer"], answered=d["created"], note=f"跟 {best['id']} 几乎一样，照你当时的判断处理")
    return d


def cmd_decide(args):
    cfg = load_config()
    today = today_str(args)
    rd = run_dir(today)
    if os.path.exists(os.path.join(rd, "decision.json")) and not args.force:
        print(f"今天已经决策过：{load_json(os.path.join(rd, 'decision.json'))['headline']}")
        return 0
    with Lock():
        st = load_state()
        plan = load_json(os.path.join(rd, "plan.json"))
        items = load_json(os.path.join(rd, "items.json"), [])
        byid = {i["id"]: i for i in items}
        if not os.path.exists(os.path.join(rd, "judge", "verify.json")):
            raise Stop("还没 verify，不能决策。")
        man = load_json(os.path.join(rd, "manifest.json"))
        fp_now = fingerprints(cfg)
        drift = [k for k in ("shuohua_skill", "shuohua_refs", "eval_skill", "config") if man["fingerprints"].get(k) != fp_now.get(k)]
        J = load_judgments(rd)
        JCUR = J.get("current", {})
        calib = load_json(os.path.join(rd, "calib", "result.json")) or {"pass": False}
        dec = {"date": today, "mode": st["mode"], "actions": [], "notes": list(plan.get("notes", [])), "gates": {}}
        if drift:
            dec["notes"].append("跑到一半，这些东西变了：" + "、".join(drift) + "。今天只记录，不发布。")
        # 1 召回入池
        pool_old = {(e["run"], e["item_id"], e["code"], e.get("quote_out", "")) for e in pool_entries()}
        new_pool = []
        for iid, j in JCUR.items():
            it = byid.get(iid)
            if not it or it.get("group") not in ("fresh", "regression", "clean"):
                continue
            for f in j.get("findings", []):
                k = (today, iid, f["code"], f.get("out", ""))
                if k in pool_old:
                    continue
                pool_old.add(k)
                new_pool.append({"date": today, "run": today, "item_id": iid, "kind": it.get("kind"),
                                 "文体": it.get("文体", ""), "release": st["published"]["release"], "code": f["code"],
                                 "cluster": f["cluster"], "quote_src": f.get("src", ""), "quote_out": f.get("out", ""),
                                 "note": f.get("note", ""),
                                 "item": {k2: it.get(k2) for k2 in ("任务", "文体", "力度", "原文", "上下文", "事实", "要求")}})
        append_jsonl(H("pool.jsonl"), new_pool)
        dec["recalled"] = {}
        for e in new_pool:
            dec["recalled"][e["cluster"]] = dec["recalled"].get(e["cluster"], 0) + 1
        # 2 指标
        m = item_metrics(items, JCUR, load_checks(rd, "current"), cfg["gates"]["clean_edit_alarm"])
        m["calib"] = [calib.get("caught", 0), calib.get("bad_n", 0), calib.get("fa", 0), calib.get("good_n", 0)]
        m.update(date=today, release=st["published"]["release"], calib_pass=bool(calib.get("pass")))
        rows = [r for r in read_jsonl(H("metrics.jsonl")) if r["date"] != today] + [m]
        write_jsonl(H("metrics.jsonl"), rows)
        dec["metrics"] = m
        # 3 争议
        disputes = read_jsonl(H("disputes.jsonl"))
        st["_next_d"] = next_dispute_id(disputes)
        created = []
        for v, JV in J.items():
            for iid, j in JV.items():
                it = byid.get(iid)
                if not it:
                    continue
                if j.get("dispute") and (v == "current" or it.get("group") in ("target", "regression", "clean", "fresh")):
                    d = j["dispute"]
                    created.append(new_dispute(st, d["类型"], it, v, d["原文片段"], d["改写片段"], d["原因"],
                                               d.get("疑似编码", ""), today, "发布判断" if v != "current" else "召回"))
                if v == "current":
                    for f in j.get("findings", []):
                        if f["code"] == "R" and f.get("cluster") == "R·新":
                            created.append(new_dispute(st, "新问题", it, v, f.get("src", ""), f.get("out", ""),
                                                       f.get("note", ""), "R", today, "召回"))
        if dt.date.fromisoformat(today).isoweekday() == cfg["disputes"]["audit_weekday"] and \
                not any(d["kind"] == "抽查" and days_between(d["created"], today) < 6 for d in disputes):
            ok_items = [iid for iid, j in JCUR.items() if j["verdict"] == "合格" and byid.get(iid, {}).get("group") == "fresh"
                        and cjk_len(byid[iid]["原文"]) <= 260]
            random.Random("audit" + today).shuffle(ok_items)
            for iid in ok_items[:cfg["disputes"]["audit_count"]]:
                body = split_output(read_text(os.path.join(rd, "outputs", "current", iid + ".txt")))[0]
                created.append(new_dispute(st, "抽查", byid[iid], "current", byid[iid]["原文"], body, "每周随机抽查", "", today, "抽查"))
        asked = {d.get("calib_id") for d in disputes if d["kind"] == "体检"}
        comments = {(p["来源"], p["工具"]): (p.get("评语") or p.get("总评") or "") for p in pkg("precedents.json", [])}
        overall = {str(c["id"]): re.split(r"<br/>|\n", c.get("意见", ""))[0].strip() for c in pkg("cases50.json", [])}
        for c in calib.get("conflicts", []):
            if c["calib_id"] in asked:
                continue
            asked.add(c["calib_id"])
            said = comments.get((f"cases50#{c['case']}", c["tool"]), "") or overall.get(str(c["case"]), "")
            said = said if len(said) <= 60 else said[:60] + "……"
            reason = (f"你当时对这版的评语：「{said}」" if said else "你当时没挑这版的毛病") + \
                f"；裁判认为{CODES.get(c['code'], c['code'])}：{c.get('note', '')}"
            d = new_dispute(st, "体检", {"id": f"cases50#{c['case']}·{c['tool']}", "文体": c["文体"]}, "calib",
                            c["src"], c["out"], reason, c["code"], today, "体检")
            d["calib_id"] = c["calib_id"]
            created.append(d)
        seen_d = {(d["created"], d["item_id"], d["version"], d["kind"], d["原文片段"]) for d in disputes}
        uniq = []
        for d in created:
            k = (d["created"], d["item_id"], d["version"], d["kind"], d["原文片段"])
            if k not in seen_d:
                seen_d.add(k)
                uniq.append(auto_match(d, cfg))
        created = uniq
        disputes += created
        write_jsonl(H("disputes.jsonl"), disputes)
        for d in created:
            if d["status"] == "auto":
                apply_answer(d, st, today, to_precedent=False)
        # 4 门禁
        blocked = drift or not calib.get("pass")
        headline = None
        chk_cur = load_checks(rd, "current")
        cand_meta = load_json(os.path.join(rd, "candidate.json"))
        if plan.get("confirm_rc") and st.get("rc"):
            rc = st["rc"]
            if blocked:
                rc["retries"] = rc.get("retries", 0) + 1
                if rc["retries"] >= 2:
                    dec["actions"].append(f"预发布 {rc['id']} 连续两天没法复测，撤回")
                    set_cooldown(st, rc["cluster"], today, cfg)
                    st["rc"] = None
                    headline = "预发布撤回（连续两天没法复测）"
                else:
                    headline = "裁判体检没过，预发布顺延一天复测" if not calib.get("pass") else "运行中途有文件变化，预发布顺延"
            else:
                grp = [i for i in items if i.get("group") in ("fresh", "regression", "clean")]
                g1 = gate_compare("current", "rc", grp, JCUR, J.get("rc", {}), cfg,
                                  checks={"base": chk_cur, "cand": load_checks(rd, "rc")})
                tgt = rc["cluster"]
                fb = sum(1 for i in grp if any(f.get("cluster") == tgt for f in JCUR.get(i["id"], {}).get("findings", [])))
                fc = sum(1 for i in grp if any(f.get("cluster") == tgt for f in J.get("rc", {}).get(i["id"], {}).get("findings", [])))
                g1["stats"]["目标病灶在新题上"] = [fb, fc]
                if fc > fb:
                    g1["pass"] = False
                    g1["reasons"].append(f"目标病灶在新题上反而变多：{fb} → {fc}")
                dec["gates"]["复测"] = g1
                if "anchor" in plan["versions"]:
                    reg = [i for i in items if i.get("group") == "regression"]
                    g2 = gate_compare("anchor", "rc", reg, J.get("anchor", {}), J.get("rc", {}), cfg)
                    dec["gates"]["对锚点"] = g2
                    if not g2["pass"]:
                        g1["pass"] = False
                        g1["reasons"] += ["对锚点：" + r for r in g2["reasons"]]
                if g1["pass"]:
                    if rc.get("shadow") or st["mode"] != "auto":
                        headline = f"影子：复测通过，本来会发布（{tgt}）"
                        st["rc"] = None
                    else:
                        rid = promote(st, rc, today, cfg, items, J)
                        headline = f"已发布 {rid}（{tgt}）"
                        dec["actions"].append(headline)
                else:
                    headline = "复测没过，预发布撤回：" + "；".join(g1["reasons"][:2])
                    set_cooldown(st, tgt, today, cfg)
                    st["rc"] = None
        elif cand_meta:
            grp = needed("cand", items, plan)
            tgt = None if cand_meta.get("aa") else cand_meta["cluster"]
            g = gate_compare("current", "cand", grp, JCUR, J.get("cand", {}), cfg, target=tgt,
                             checks={"base": chk_cur, "cand": load_checks(rd, "cand")})
            dec["gates"]["候选"] = g
            if cand_meta.get("aa"):
                headline = "A/A 自测：" + ("两份一样的细则没被判出差别" if not [r for r in g["reasons"] if not r.startswith("目标")] else "同一份细则跑两遍被判出差别：" + "；".join(g["reasons"][:2]))
                dec["aa"] = g["stats"]
            elif blocked:
                headline = "候选作废（运行中途有文件变化）"
            elif g["pass"]:
                rcid = f"rc{st['next_rc']:04d}"
                st["next_rc"] += 1
                body = rules_of(read_text(os.path.join(rd, "overlays", "cand.md")))[1]
                body = re.sub(r"^# 好好说话 · 每日细则\s*", "", body).strip()
                write_text(H("releases", rcid, "daily-learning.md"), body)
                save_json(H("releases", rcid, "meta.json"), {"id": rcid, "date": today, "cluster": tgt, "gate": g,
                                                             "changed": cand_meta.get("changed", []), "note": cand_meta.get("note", "")})
                st["rc"] = {"id": rcid, "date": today, "cluster": tgt, "shadow": st["mode"] != "auto",
                            "holdout": [i["id"] for i in items if i.get("group") == "target"], "run": today}
                headline = ("影子：" if st["mode"] != "auto" else "") + f"预发布 {rcid}（{tgt}），明天用新题复测"
                dec["actions"].append(headline)
            else:
                headline = f"候选被拒（{tgt}）：" + "；".join(g["reasons"][:2])
                set_cooldown(st, tgt, today, cfg)
        if headline is None:
            if not calib.get("pass"):
                headline = "裁判体检没过：今天只召回，不出候选"
            elif plan.get("manual_edit"):
                headline = "细则被手工改过：今天只召回，等你确认"
            elif plan.get("target"):
                headline = f"有够数的病灶（{plan['target']['cluster']}），但今天没出候选"
            else:
                headline = "没有够数的病灶：今天只召回"
        # 5 监控回滚
        rb = monitor(st, cfg, today)
        if rb:
            dec["actions"].append(rb)
            headline = rb + "；" + headline
        dec["headline"] = headline
        dec["calib"] = {k: calib.get(k) for k in ("caught", "bad_n", "fa", "good_n", "pass")}
        st.pop("_next_d", None)
        save_json(os.path.join(rd, "decision.json"), dec)
        save_state(st)
    print(headline)
    for a in dec["actions"]:
        print("动作：" + a)
    return 0


def set_cooldown(st, cluster, today, cfg, days=None):
    cd = st.setdefault("cooldown", {}).setdefault(cluster, {"attempts": []})
    cd["attempts"] = [d for d in cd.get("attempts", []) if days_between(d, today) < cfg["cluster"]["stuck_window_days"]] + [today]
    cd["until"] = (dt.date.fromisoformat(today) + dt.timedelta(days=days or cfg["cluster"]["cooldown_days"])).isoformat()
    if len(cd["attempts"]) >= cfg["cluster"]["stuck_after"]:
        cd["status"] = "stuck"


def publish_text(st, body, release_id, today):
    path = published_path()
    cur = file_sha(path)
    if cur != st["published"]["sha"]:
        raise Stop("daily-learning.md 被手工改过，拒绝覆盖。回复「接受手工修改」把它记成新版本，或者先恢复原样。")
    content = with_header(body, release_id, today)
    write_text(path, content)
    back = file_sha(path)
    if back != sha(content):
        raise Stop("发布后回读对不上，停下检查磁盘。")
    st["published"] = {"release": release_id, "sha": back, "date": today}


def promote(st, rc, today, cfg, items, J):
    rid = f"v{st['next_release']:04d}"
    st["next_release"] += 1
    body = release_text(rc["id"])
    write_text(H("releases", rid, "daily-learning.md"), body)
    prev = st["published"]["release"]
    save_json(H("releases", rid, "meta.json"), {"id": rid, "date": today, "from_rc": rc["id"], "cluster": rc["cluster"], "prev": prev})
    publish_text(st, body, rid, today)
    st.setdefault("releases", []).append({"id": rid, "date": today, "cluster": rc["cluster"], "prev": prev, "type": "发布"})
    st.setdefault("cluster_fixed_at", {})[rc["cluster"]] = rid
    st.get("cooldown", {}).pop(rc["cluster"], None)
    st["rc"] = None
    extra = load_json(H("regression_extra.json"), [])
    rc_run = load_json(os.path.join(run_dir(rc["run"]), "items.json"), [])
    for it in [i for i in rc_run if i.get("id") in rc.get("holdout", [])][:3]:
        extra.append({"id": f"reg-{it['id']}", "kind": "regression", "group": "regression", "任务": it.get("任务", "改写"),
                      "文体": it.get("文体", ""), "力度": it.get("力度", "标准"), "原文": it["原文"],
                      "上下文": it.get("上下文", ""), "事实": it.get("事实", []), "来源": f"{rid} 修好的 {rc['cluster']}"})
    save_json(H("regression_extra.json"), extra)
    return rid


def unfix(st, to_release):
    fixed = st.setdefault("cluster_fixed_at", {})
    for c in [c for c, r in fixed.items() if r > to_release]:
        fixed.pop(c)


def monitor(st, cfg, today):
    if st["mode"] != "auto" or file_sha(published_path()) != st["published"]["sha"]:
        return None
    rels = [r for r in st.get("releases", []) if r["type"] == "发布"]
    if not rels:
        return None
    last = rels[-1]
    if st["published"]["release"] != last["id"] or days_between(last["date"], today) > cfg["monitor"]["window_days"]:
        return None
    rows = read_jsonl(H("metrics.jsonl"))
    after = [r for r in rows if r["date"] > last["date"] and r["release"] == last["id"]]
    before = [r for r in rows if 0 <= days_between(r["date"], last["date"]) <= cfg["monitor"]["window_days"] and r["release"] != last["id"]]
    if len(after) < cfg["monitor"]["min_days_after_release"] or not before:
        return None
    ra = sum(r["harm"] for r in after) / max(1, sum(r["n"] for r in after))
    rb = sum(r["harm"] for r in before) / max(1, sum(r["n"] for r in before))
    if ra - rb > cfg["monitor"]["harm_rate_margin"] and sum(r["harm"] for r in after) >= cfg["monitor"]["min_harm_items"]:
        body = release_text(last["prev"])
        publish_text(st, body, last["prev"], today)
        st["releases"].append({"id": last["prev"], "date": today, "cluster": last["cluster"], "prev": last["id"], "type": "回滚"})
        unfix(st, last["prev"])
        set_cooldown(st, last["cluster"], today, cfg, days=14)
        return f"已自动回滚到 {last['prev']}：发布 {last['id']} 后改坏率 {ra:.0%}，发布前 {rb:.0%}"
    return None


# ---------------------------------------------------------------- 争议

def expire_disputes(cfg, st, today):
    ds = read_jsonl(H("disputes.jsonl"))
    notes, changed = [], False
    for d in ds:
        if d["status"] == "open" and days_between(d["created"], today) >= cfg["disputes"]["default_after_days"]:
            d.update(status="defaulted", answer=d["default"], answered=today, note="超时，按保守默认处理")
            changed = True
            apply_answer(d, st, today, defaulted=True)
    if changed:
        write_jsonl(H("disputes.jsonl"), ds)
        n = sum(1 for d in ds if d["answered"] == today and d["status"] == "defaulted")
        notes.append(f"{n} 条待判断的题超过 {cfg['disputes']['default_after_days']} 天没回，已按保守默认处理。")
    return notes


def apply_answer(d, st, today, defaulted=False, to_precedent=True):
    """超时默认只影响当时的发布判断，不进问题池、不进判例；作者亲自回答的才进。"""
    if defaulted:
        return
    if d["kind"] == "体检":
        ov = load_json(H("calib_overrides.json"), {})
        if d["answer"] == "有":
            ov[d["calib_id"]] = {"f": "橙", "dispute": d["id"], "date": today}
        elif d["answer"] == "没有":
            ov[d["calib_id"]] = {"f": "绿确认", "dispute": d["id"], "date": today}
        else:
            ov.pop(d["calib_id"], None)
        save_json(H("calib_overrides.json"), ov)
    if d["kind"] == "抽查":
        st["audits"] = [a for a in st.get("audits", []) if a["id"] != d["id"]]
        if d["answer"] in ("有", "没有"):
            st["audits"].append({"id": d["id"], "date": today, "answer": d["answer"]})
        return
    pool = read_jsonl(H("pool.jsonl"))
    had = [e for e in pool if e.get("kind") == "dispute" and e.get("dispute_id") == d["id"]]
    if had:
        write_jsonl(H("pool.jsonl"), [e for e in pool if not (e.get("kind") == "dispute" and e.get("dispute_id") == d["id"])])
    if d["answer"] == "有" and d["version"] == "current":
        code = d.get("疑似编码") or ("D" if d["kind"] == "场合" else ("R" if d["kind"] == "新问题" else "P"))
        if code not in CODES:
            code = "P"
        its = {i["id"]: i for i in load_json(os.path.join(run_dir(d["created"]), "items.json"), [])}
        it = its.get(d["item_id"], {})
        append_jsonl(H("pool.jsonl"), [{"date": today, "run": d["created"], "item_id": d["item_id"], "kind": "dispute",
                                        "dispute_id": d["id"], "文体": d.get("文体", ""),
                                        "release": st["published"]["release"], "code": code,
                                        "cluster": cluster_of(code, "新") if code == "R" else code,
                                        "quote_src": d["原文片段"], "quote_out": d["改写片段"],
                                        "note": "作者判定：" + d.get("原因", ""),
                                        "item": {k: it.get(k) for k in ("任务", "文体", "力度", "原文", "上下文", "事实", "要求")}}])
    if not to_precedent:
        return
    prec = [p for p in read_jsonl(H("precedents.jsonl")) if p.get("id") != d["id"]]
    if d["answer"] in ("有", "没有"):
        prec.append({"id": d["id"], "date": today, "kind": d["kind"], "文体": d.get("文体", ""),
                     "原文片段": d["原文片段"], "改写片段": d["改写片段"], "answer": d["answer"], "note": d.get("note", "")})
    write_jsonl(H("precedents.jsonl"), prec)


def cmd_disputes(args):
    cfg = load_config()
    today = today_str(args)
    if args.action == "list":
        ds = read_jsonl(H("disputes.jsonl"))
        show = [d for d in ds if d["status"] == "open"] if not args.all else ds
        for d in show:
            print(render_dispute(d) + (f"\n  状态：{d['status']} {d.get('answer') or ''} {d.get('note') or ''}" if args.all else ""))
        if not show:
            print("没有待判断的题。")
        return 0
    if args.action == "answer":
        ans = {"是": "有", "有": "有", "有问题": "有", "否": "没有", "没有": "没有", "没问题": "没有", "跳过": "跳过"}.get(args.answer)
        if not ans:
            raise Stop("回答只认：有 / 没有 / 跳过（也认 是 / 否）")
        with Lock():
            st = load_state()
            ds = read_jsonl(H("disputes.jsonl"))
            d = next((x for x in ds if x["id"].upper() == args.id.upper()), None)
            if not d:
                raise Stop(f"找不到 {args.id}")
            if d["status"] not in ("open", "defaulted", "auto"):
                print(f"{d['id']} 已经回答过（{d['answer']}），这次覆盖。")
            d.update(status="answered", answer=ans, answered=today, note=args.note or "")
            apply_answer(d, st, today)
            write_jsonl(H("disputes.jsonl"), ds)
            msg = check_audit_pause(st, cfg)
            save_state(st)
            log_author(today, f"{d['id']} {ans}" + (f"（{args.note}）" if args.note else ""))
        print(f"{d['id']} 记下了：{ans}" + (f"（{args.note}）" if args.note else ""))
        if msg:
            print(msg)
        return 0
    return 0


def check_audit_pause(st, cfg):
    audits = [a for a in st.get("audits", []) if a["answer"] in ("有", "没有")][-20:]
    if len(audits) < cfg["disputes"]["audit_min_answered"]:
        return None
    miss = sum(1 for a in audits if a["answer"] == "有") / len(audits)
    if miss > cfg["disputes"]["audit_miss_pause"] and st["mode"] == "auto":
        st["mode"] = "paused"
        st["paused_reason"] = f"抽查里裁判漏判 {miss:.0%}，超过 {cfg['disputes']['audit_miss_pause']:.0%}"
        return "抽查漏判率超标，自动发布已暂停，召回照常跑。"
    return None


def render_dispute(d):
    return (f"{d['id']} · {d['kind']} · {d.get('文体', '')}\n  原文：{d['原文片段']}\n"
            f"  改写：{d['改写片段'] or '（改写里没有对应的话）'}\n"
            + (f"  拿不准的地方：{d['原因']}\n" if d.get("原因") else "")
            + f"  {d['question']} 回复「{d['id']} 有」或「{d['id']} 没有」")


# ---------------------------------------------------------------- 报告

def cmd_report(args):
    cfg, st = load_config(), load_state()
    today = today_str(args)
    rd = run_dir(today)
    dec = load_json(os.path.join(rd, "decision.json"))
    if not dec:
        raise Stop("今天还没 decide。")
    rows = read_jsonl(H("metrics.jsonl"))
    past = [r for r in rows if 0 < days_between(r["date"], today) <= 7]

    def rate(k, rs, base="n"):
        n = sum(r[base] for r in rs)
        return (sum(r[k] for r in rs), n)
    m = dec["metrics"]

    def fmt(k, base="n"):
        a, n = m[k], m[base]
        pa, pn = rate(k, past, base)
        avg = f"7 天 {pa}/{pn}" if pn else "7 天无数据"
        return f"{a}/{n}（{avg}）"
    lines = [f"好好说话 · 每日召回 {today} · {mode_label(cfg, st, today)}",
             f"结论：{dec['headline']}",
             f"改坏 {fmt('harm')}，其中编造 {m['fab']} · 残留 {fmt('residue')} · 干净稿误改 {fmt('over_edit', 'clean_n')}"]
    c = dec.get("calib") or {}
    if c.get("bad_n") is not None:
        lines.append(f"裁判体检：已知改坏的抓到 {c.get('caught')}/{c.get('bad_n')}，已知没改坏的误报 {c.get('fa')}/{c.get('good_n')}"
                     + ("" if c.get("pass") else "，没过"))
    rec = dec.get("recalled") or {}
    if rec:
        top = sorted(rec.items(), key=lambda x: -x[1])[:4]
        lines.append("今天新召回：" + "，".join(f"{k}（{CODES.get(k.split('·')[0], k)}）×{n}" for k, n in top))
    if dt.date.fromisoformat(today).isoweekday() == cfg["disputes"]["audit_weekday"]:
        wk = [r for r in st.get("releases", []) if 0 <= days_between(r["date"], today) < 7]
        stuck = [k for k, v in st.get("cooldown", {}).items() if v.get("status") == "stuck"]
        lines.append(f"本周：发布 {sum(1 for r in wk if r['type'] == '发布')} 次，回滚 {sum(1 for r in wk if r['type'] == '回滚')} 次"
                     + (f"；招不回、待研究：{'、'.join(stuck)}" if stuck else ""))
    heard = [r["text"] for r in read_jsonl(H("inbox.jsonl")) if r.get("date") == today]
    if heard:
        lines.append("今天记下你的回话：" + "；".join(t if len(t) <= 60 else t[:60] + "……" for t in heard))
    ds = [d for d in read_jsonl(H("disputes.jsonl")) if d["status"] == "open"]
    kind_pri = {"保真": 0, "场合": 1, "体检": 2, "新问题": 3, "抽查": 4}
    ds.sort(key=lambda d: (kind_pri[d["kind"]], d["affects"] == "发布判断", d["created"]))
    show = ds[:cfg["disputes"]["max_per_day"]]
    if show:
        lines.append(f"待你判断 {len(ds)} 条（先看这 {len(show)} 条，不回也行，{cfg['disputes']['default_after_days']} 天后按保守默认处理）：")
        lines += [render_dispute(d) for d in show]
    else:
        lines.append("今天没有要你判断的。")
    for n in dec.get("notes", []):
        lines.append("注意：" + n)
    lines.append(f"运行目录：{rd}")
    text = "\n".join(lines)
    write_text(os.path.join(rd, "report.md"), text + "\n")
    print(text)
    return 0


# ---------------------------------------------------------------- 作者指令

def cmd_mode(args):
    with Lock():
        st = load_state()
        if args.mode == "auto":
            st["mode"], st["paused_reason"] = "auto", None
            if st.get("rc"):
                st["rc"]["shadow"] = False
        elif args.mode == "shadow":
            st["mode"] = "shadow"
            st["shadow_start"] = today_str(args)
        else:
            st["mode"], st["paused_reason"] = "paused", args.reason or "作者手动暂停"
        save_state(st)
        log_author(today_str(args), f"模式切到 {st['mode']}")
    print(f"模式已切到：{st['mode']}")
    return 0


def cmd_anchor(args):
    with Lock():
        st = load_state()
        st["anchor"] = st["published"]["release"]
        save_state(st)
        log_author(today_str(args), f"锚点设为 {st['anchor']}")
    print(f"锚点设为 {st['anchor']}：以后每次发布都要在回归题上不比它差。")
    return 0


def cmd_rollback(args):
    cfg = load_config()
    today = today_str(args)
    with Lock():
        st = load_state()
        cur = st["published"]["release"]
        to = args.to
        if not to:
            rels = [r for r in st.get("releases", []) if r["id"] == cur and r["type"] == "发布"]
            to = rels[-1]["prev"] if rels else None
        if not to or not os.path.exists(H("releases", to, "daily-learning.md")):
            raise Stop("没有可以回滚到的版本。")
        if args.force:
            st["published"]["sha"] = file_sha(published_path())
        publish_text(st, release_text(to), to, today)
        cl = next((r["cluster"] for r in reversed(st.get("releases", [])) if r["id"] == cur), "")
        st.setdefault("releases", []).append({"id": to, "date": today, "cluster": cl, "prev": cur, "type": "回滚"})
        unfix(st, to)
        if cl and cl != "手工":
            set_cooldown(st, cl, today, cfg, days=14)
        save_state(st)
        log_author(today, f"回滚 {cur} → {to}")
    print(f"已回滚：{cur} → {to}")
    return 0


def cmd_accept_manual(args):
    today = today_str(args)
    with Lock():
        st = load_state()
        path = published_path()
        text = read_text(path)
        rid = f"v{st['next_release']:04d}"
        st["next_release"] += 1
        body = re.sub(r"^# 好好说话 · 每日细则\s*", "", rules_of(text)[1]).strip()
        write_text(H("releases", rid, "daily-learning.md"), body)
        save_json(H("releases", rid, "meta.json"), {"id": rid, "date": today, "source": "作者手工修改"})
        prev = st["published"]["release"]
        st["published"] = {"release": rid, "sha": file_sha(path), "date": today}
        st.setdefault("releases", []).append({"id": rid, "date": today, "cluster": "手工", "prev": prev, "type": "手工"})
        st["anchor"] = rid
        save_state(st)
        log_author(today, f"手工修改记成 {rid}")
    print(f"手工修改已记成 {rid}，并设为锚点。明天起恢复正常。")
    return 0


def cmd_import_clean(args):
    rows = load_json(args.file)
    have = load_json(H("clean.json"), [])
    seen = {norm(x["原文"]) for x in have}
    n0 = len(have)
    for r in rows:
        t = (r.get("原文") or r.get("text") or "").strip()
        if cjk_len(t) < 20 or norm(t) in seen:
            continue
        seen.add(norm(t))
        have.append({"id": f"clean-u{len(have) + 1:03d}", "kind": "clean", "group": "clean", "任务": "改写",
                     "文体": r.get("文体", "随笔"), "力度": "标准", "原文": t, "上下文": "", "来源": r.get("来源", "作者导入")})
    save_json(H("clean.json"), have)
    print(f"干净对照新增 {len(have) - n0} 条，共 {len(have)} 条（另有技能自带 {len(pkg('clean_seed.json'))} 条）。")
    return 0


def cmd_export(args):
    st = load_state()
    today = today_str(args)
    text = release_text(st["published"]["release"])
    rels = [r for r in st.get("releases", []) if r["type"] == "发布"]
    lines = [f"# 每日细则合并提案 {today}", "",
             f"现用版本 {st['published']['release']}，累计发布 {len(rels)} 次。下面这些细则已经过门禁，"
             "稳定了可以并进 haohao-shuohua 的 references（不要动底线条款），并进之后把 daily-learning.md 清空并记成新锚点。", "",
             "## 现用细则", "", text or "（没有）", "", "## 发布记录", ""]
    for r in st.get("releases", []):
        lines.append(f"- {r['date']} {r['type']} {r['id']}（{r['cluster']}，上一版 {r['prev']}）")
    out = H("exports", f"{today}-merge.md")
    write_text(out, "\n".join(lines) + "\n")
    print(f"写出 {out}")
    return 0


def cmd_note(args):
    today = today_str(args)
    if args.action == "list":
        rows = active_notes()
        for n in rows:
            print(f"{n['id']}（{n['date']}，{'、'.join(n['文体']) if n.get('文体') else '所有文体'}）：{n['text']}")
        if not rows:
            print("还没有记下的作者说明。")
        return 0
    if not (args.text or "").strip():
        raise Stop("add 后面跟作者原话，drop 后面跟编号（比如 N003）。")
    load_state()
    with Lock():
        rows = read_jsonl(H("notes.jsonl"))
        if args.action == "add":
            text = args.text.strip()
            tags = [t.strip() for t in re.split(r"[,，、/]", args.genre or "") if t.strip()]
            n = {"id": f"N{len(rows) + 1:03d}", "date": today, "text": text, "文体": tags, "status": "active"}
            rows.append(n)
            msg = f"{n['id']} 记下了（{'只用于' + '、'.join(tags) if tags else '所有文体都适用'}）：{text}"
        else:
            n = next((x for x in rows if x["id"].upper() == args.text.strip().upper()), None)
            if not n:
                raise Stop(f"找不到 {args.text}")
            n.update(status="dropped", dropped=today)
            msg = f"{n['id']} 作废了：{n['text']}"
        write_jsonl(H("notes.jsonl"), rows)
        log_author(today, msg)
    print(msg)
    return 0


# ---------------------------------------------------------------- 数据包

def pack_members(today, keep_days):
    home = eval_home()
    out = []
    for root, dirs, names in os.walk(home):
        rel = os.path.relpath(root, home)
        parts = [] if rel == "." else rel.split(os.sep)
        if parts == ["runs"]:
            dirs[:] = [d for d in dirs
                       if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) or days_between(d, today) <= keep_days]
        dirs.sort()
        for nm in sorted(names):
            if nm == "loop.lock" or nm.endswith(".tmp"):
                continue
            out.append("/".join(parts + [nm]))
    return out


PACK_NAME = "haohao-eval-data.tgz"


def free_path(base):
    path, n = base, 1
    while os.path.exists(path):
        path, n = f"{base}-{n}", n + 1
    return path


def write_manifest(tf, man):
    data = json.dumps(man, ensure_ascii=False, indent=1).encode("utf-8")
    info = tarfile.TarInfo("manifest.json")
    info.size, info.mtime = len(data), int(dt.datetime.now().timestamp())
    tf.addfile(info, io.BytesIO(data))


def cmd_pack(args):
    today = today_str(args)
    out_dir = os.path.abspath(args.out or tempfile.gettempdir())
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, PACK_NAME)
    if args.empty:
        with tarfile.open(path, "w:gz") as tf:
            write_manifest(tf, {"format": 1, "seq": 0, "date": today, "files": {}, "published": None, "empty": True})
        print(f"空数据包：{path}")
        print("给还没存过数据的云空间文件占位，第一次运行 unpack 会提示先 init。")
        return 0
    cfg = load_config()
    with Lock():
        st = load_state()
        st["pack_seq"] = st.get("pack_seq", 0) + 1
        st["packed"] = today
        save_state(st)
        seq = st["pack_seq"]
        rels = pack_members(today, cfg["pack"]["keep_runs_days"])
        man = {"format": 1, "seq": seq, "date": today, "files": {}, "published": None}
        with tarfile.open(path, "w:gz") as tf:
            for rel in rels:
                src = os.path.join(eval_home(), *rel.split("/"))
                man["files"]["eval/" + rel] = file_digest(src)
                tf.add(src, arcname="eval/" + rel, recursive=False)
            if os.path.exists(published_path()):
                man["published"] = file_digest(published_path())
                tf.add(published_path(), arcname="shuohua/daily-learning.md", recursive=False)
            write_manifest(tf, man)
    print(f"数据包：{path}")
    print(f"第 {seq} 份 · {len(rels)} 个文件 · {os.path.getsize(path)} 字节 · sha256 {file_digest(path)}")
    return 0


def cmd_unpack(args):
    home = eval_home().rstrip(os.sep)
    lock = H("loop.lock")
    if os.path.exists(lock) and dt.datetime.now().timestamp() - os.path.getmtime(lock) < 6 * 3600:
        raise Stop(f"另一个流程正在跑（{lock}），先别恢复。")
    try:
        tf = tarfile.open(os.path.abspath(args.file), "r:gz")
    except (OSError, tarfile.TarError) as e:
        raise Stop(f"数据包打不开：{e}")
    with tf:
        members = tf.getmembers()
        for m in members:
            known = m.name in ("manifest.json", "shuohua/daily-learning.md") or m.name.startswith("eval/")
            if not known or not m.isfile() or m.name.startswith("/") or "\\" in m.name or ".." in m.name.split("/"):
                raise Stop(f"数据包里有不该有的东西：{m.name}")
        names = {m.name for m in members}
        if "manifest.json" not in names:
            raise Stop("数据包里没有 manifest.json，不是 loop.py pack 打的包。")
        man = json.loads(tf.extractfile("manifest.json").read().decode("utf-8"))
        local = load_json(H("state.json"))
        if man.get("empty"):
            if names != {"manifest.json"}:
                raise Stop("标着空包的数据包里有文件，不恢复。")
            if local is not None:
                print("数据包是空的（还没存过数据），本地已有数据，以本地为准。")
            else:
                print("数据包是空的（还没存过数据）：这是第一次运行，接着跑 loop.py init。")
            return 0
        files = man.get("files", {})
        if "eval/state.json" not in files or set(files) != {n for n in names if n.startswith("eval/")}:
            raise Stop("数据包的清单跟里面的文件对不上，不恢复。")
        if local is not None and not args.force:
            ls = local.get("pack_seq", 0)
            if ls > man["seq"]:
                raise Stop(f"本地数据比数据包新（本地第 {ls} 份，包里第 {man['seq']} 份），不恢复。"
                           "确认要用旧包盖掉本地，加 --force。")
            if ls == man["seq"]:
                print(f"本地数据就是第 {ls} 份，跟数据包一样，不用恢复。")
                return 0
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        tmp = free_path(f"{home}.unpack-{stamp}")
        pub = None
        try:
            for m in members:
                if m.name == "manifest.json":
                    continue
                data = tf.extractfile(m).read()
                want = man.get("published") if m.name == "shuohua/daily-learning.md" else files.get(m.name)
                if hashlib.sha256(data).hexdigest() != want:
                    raise Stop(f"数据包校验不过：{m.name}")
                if m.name == "shuohua/daily-learning.md":
                    pub = data
                    continue
                dst = os.path.join(tmp, *m.name[len("eval/"):].split("/"))
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with open(dst, "wb") as f:
                    f.write(data)
            if man.get("published") and pub is None:
                raise Stop("数据包清单里有 daily-learning.md，包里却没有。")
        except Stop:
            shutil.rmtree(tmp, ignore_errors=True)
            raise
    moved = []
    if os.path.exists(home):
        moved.append(free_path(f"{home}.bak-{stamp}"))
        os.replace(home, moved[-1])
    os.replace(tmp, home)
    pp = published_path()
    if os.path.exists(pp):
        moved.append(free_path(f"{pp}.bak-{stamp}"))
        os.replace(pp, moved[-1])
    if pub is not None:
        os.makedirs(os.path.dirname(pp), exist_ok=True)
        with open(pp, "wb") as f:
            f.write(pub)
    print(f"已恢复第 {man['seq']} 份数据（{man['date']} 打的包），{len(files)} 个文件，校验通过。")
    for p in moved:
        print(f"原来的挪到了 {p}")
    return 0


# ---------------------------------------------------------------- 入口

def main(argv=None):
    ap = argparse.ArgumentParser(description="haohao-eval 每日召回（详见 references/daily-loop.md）")
    ap.add_argument("--date", help="指定日期 YYYY-MM-DD（默认今天，测试用）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init", help="第一次运行：建数据目录、配置和状态")
    p.add_argument("--shuohua-dir")
    p.add_argument("--model")
    p.add_argument("--force", action="store_true")
    sub.add_parser("status", help="看当前模式、版本、问题池和待判断的题")
    p = sub.add_parser("start", help="开今天这一轮：抽体检题、回归题、干净对照，定目标病灶")
    p.add_argument("--model")
    p.add_argument("--force", action="store_true")
    sub.add_parser("calib-score", help="给裁判体检算分")
    p = sub.add_parser("add-items", help="收下今天新出的题（JSON 数组）")
    p.add_argument("file")
    p = sub.add_parser("writer-view", help="列出某个版本还要改写的题")
    p.add_argument("version", choices=VERSIONS)
    sub.add_parser("target", help="看目标病灶的开发组证据")
    p = sub.add_parser("stage", help="冻结候选细则")
    p.add_argument("file", nargs="?", default="")
    p.add_argument("--note")
    p.add_argument("--aa", action="store_true", help="影子期 A/A 自测：候选就是现用版")
    sub.add_parser("check", help="机械检查所有改写")
    sub.add_parser("blind", help="打乱、匿名，生成盲评队列")
    p = sub.add_parser("verify", help="核对裁判答案（格式、引用、旗标）")
    p.add_argument("--partial", action="store_true", help="没判完的按拿不准算（时间不够时用）")
    p = sub.add_parser("decide", help="入池、算指标、建争议、过门禁、发布或回滚")
    p.add_argument("--force", action="store_true")
    sub.add_parser("report", help="生成今天的日报")
    p = sub.add_parser("disputes", help="待判断的题：list / answer")
    p.add_argument("action", choices=["list", "answer"])
    p.add_argument("id", nargs="?")
    p.add_argument("answer", nargs="?")
    p.add_argument("--note")
    p.add_argument("--all", action="store_true")
    p = sub.add_parser("mode", help="切模式：auto / shadow / paused")
    p.add_argument("mode", choices=["auto", "shadow", "paused"])
    p.add_argument("--reason")
    sub.add_parser("anchor", help="把现用版设为锚点")
    p = sub.add_parser("rollback", help="回滚细则")
    p.add_argument("--to")
    p.add_argument("--force", action="store_true", help="文件被手工改过也回滚（手工改动会被覆盖）")
    sub.add_parser("accept-manual", help="把手工改过的 daily-learning.md 记成新版本")
    p = sub.add_parser("import-clean", help="导入人写的干净文本做误改对照")
    p.add_argument("file")
    sub.add_parser("export", help="生成细则合并提案")
    p = sub.add_parser("note", help="记下作者的原话（判断标准、偏好），裁判和写候选时都会看到")
    p.add_argument("action", choices=["add", "list", "drop"])
    p.add_argument("text", nargs="?", help="add 跟作者原话，drop 跟编号")
    p.add_argument("--文体", "--genre", dest="genre", help="只用于哪些文体，逗号隔开；不写就是所有文体")
    p = sub.add_parser("pack", help="把数据目录打成一个包，跨天留不住数据时存到别处")
    p.add_argument("--out", help="包放在哪个目录（默认系统临时目录）")
    p.add_argument("--empty", action="store_true", help="打一个空包，给还没存过数据的云空间文件占位")
    p = sub.add_parser("unpack", help="从数据包恢复数据目录（本地比包新时不覆盖）")
    p.add_argument("file")
    p.add_argument("--force", action="store_true", help="本地比包新也用包覆盖（原来的挪走备份）")
    args = ap.parse_args(argv)
    fn = {"init": cmd_init, "status": cmd_status, "start": cmd_start, "calib-score": cmd_calib_score,
          "add-items": cmd_add_items, "writer-view": cmd_writer_view, "target": cmd_target, "stage": cmd_stage,
          "check": cmd_check, "blind": cmd_blind, "verify": cmd_verify, "decide": cmd_decide, "report": cmd_report,
          "disputes": cmd_disputes, "mode": cmd_mode, "anchor": cmd_anchor, "rollback": cmd_rollback,
          "accept-manual": cmd_accept_manual, "import-clean": cmd_import_clean, "export": cmd_export,
          "note": cmd_note, "pack": cmd_pack, "unpack": cmd_unpack}[args.cmd]
    try:
        return fn(args) or 0
    except Stop as e:
        print("停下：" + str(e), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
