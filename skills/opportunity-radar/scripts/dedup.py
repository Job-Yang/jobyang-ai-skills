#!/usr/bin/env python3
"""与历史追踪台去重（纯 stdlib，每日雷达幂等的核心脚本）。

背景：雷达每天扫一轮。没有脚本前，"和历史重复"靠 Agent 读追踪台文档自觉判断——
自觉就意味着今天可能把昨天已经 triage 过的信号再开一条新条目。本脚本把这件事
变成确定性判断：给定追踪台历史 markdown 与今日候选 JSON，逐条判定
NEW / DUP / RELATED，并给出命中的历史条目，让"今天没有新东西"可复现、可被 cron 读取。

输入：
  --history <path>    追踪台 markdown 文件或目录（可重复给多个）。
                      抽取形如 `## 2026-10-12 · 标题` 的条目及其下正文（到下一个标题为止）。
  --candidates <json> 今日候选数组，每条：
                      {"title": str, "direction": str?, "evidence_url": str?, ...}

输出（stdout，JSON）：
  {"all_dup": bool, "summary": {...}, "results": [
     {"title", "verdict": "NEW|DUP|RELATED", "score": 0.00,
      "matched": {"date", "title"} | null, "reason": "..."}]}

判定规则（确定性，无随机性）：
  - 文本归一化：小写；英文词 token（[a-z0-9][a-z0-9.+-]*，去停用词）；中文剔除
    跨主题通用停用词后按相邻字两两成 bigram。
  - df 折扣：某个词出现在 ≥40% 历史条目（且至少 3 条）时，视为本批通用词，
    不计入交集（0.4.0：解决"付费/机会/agent"等通用词把所有候选判成近亲的问题）。
  - 历史条目 token = 标题 + 正文；今日候选 token = 标题 + 方向。
  - 主指标 = 覆盖率 coverage = |候选∩历史| / |候选有效词|（候选的词有多少落在历史条目里）。
    不用 Jaccard：历史条目正文长，会把重合度稀释到看不见；覆盖率对长短历史都稳。
    另设"交集 token 数"门槛，防止只有两三个词的短候选被覆盖率误判。
  - DUP    = coverage ≥ 0.45 且交集 ≥ 8（同一件事换皮；含"昨日运行记录已 triage 过的信号再冒头"）。
  - RELATED = coverage ≥ 0.30 且交集 ≥ 6（近亲方向，不深挖，条目里注明近亲是谁）。
  - NEW    = 其余（历史上没出现过的方向，可以立条）。
  - 证据 URL 归一化后与历史条目里任一链接完全相同 → 直接按 DUP 处理。

退出码：
  0 = 至少一条 NEW（今天有可立的新方向）
  4 = 无 NEW（全 DUP/RELATED——"安静日"信号，不是错误；cron 据此走"无强机会留痕"分支）
  2 = 参数 / 文件 / JSON 错误
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

# 判定阈值（用 tests/fixtures 里三条历史 + 今日候选校准过，改阈值先跑回归）。
# 主指标 = 覆盖率 coverage = |候选∩历史| / |候选|（候选的词有多少落在历史条目里）。
# 不用 Jaccard：历史条目正文长，会把重合度稀释到看不见；覆盖率对长短历史都稳。
# 另设"交集 token 数"门槛，防止只有两三个词的短候选被覆盖率误判。
DUP_COV_MIN = 0.45        # 候选近半的词都在某条历史条目里 = 同一件事换皮（含"昨天运行记录已 triage 过的信号再冒头"）
DUP_INTER_MIN = 8
DUP_TITLE_MIN = 0.50      # 复评驳回#2：标题短语覆盖率≥0.50 = 同主体换皮（词换了主体没变）
RELATED_COV_MIN = 0.25    # 0.4.0：原 0.18 被跨条目通用词打穿；配合停用词+df 折扣后收紧到 0.25
RELATED_INTER_MIN = 8     # 0.4.0：至少 8 个有效交集词（原为 4，4 个碎片 bigram 就误判近亲）
DUP_DOMAIN_COV_MIN = 0.40  # 0.4.0：同域名不同文章必须有 40% 文本重合才按 DUP，原 0.18 误杀同源新文章
# 注意：以上阈值均由小样本 fixture（3 条历史 + 今日候选）校准，非统计显著；
# 真实连续运行积累后由数据说话调整，不靠拍脑袋。
# 0.4.0 召回复盘（2026-10-20）：阈值和停用词改动后同步更新了 test_dedup 断言。

_EN_WORD = re.compile(r"[a-z0-9][a-z0-9.+\-]*")
_CJK = re.compile(r"[一-鿿]")
_DATE = re.compile(r"(20\d{2})-(\d{2})-(\d{2})")
_HEADING = re.compile(r"^#{1,6}\s+")

# 英文停用词：不携带方向信息的小词，避免 "the/a/of" 把不相关条目误判成相似。
_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with",
    "is", "are", "was", "be", "it", "its", "this", "that", "there", "what",
    "how", "why", "now", "at", "by", "as", "from", "up", "de", "la",
}

# 中文停用词：0.4.0 新增。只收跨主题通用、不携带方向的过程词/元词。
# 判据：在追踪台多条历史里出现、换任何主题都成立。「付费/钱在/流动/差评」
# 这类蓝海判据词不收——它们有筛选语义，残余的跨条目通用问题由 df 折扣兜底。
_CN_STOP = {
    "机会", "没有", "够强", "综合分", "打分", "深挖", "今天", "当天", "一个",
    "这个", "那个", "自己", "已经", "还是", "就是", "可以", "不是", "但是",
    "方向", "信号", "供给", "用户", "产品", "建议", "记录", "结论", "评分",
    "候选", "直接", "自动", "备注",
}

# 一个词出现在 ≥40% 历史条目里（且至少 3 条），就视为本批通用词，
# 不计入某条历史与候选的交集（df 折扣，跨语言通用）。
DF_RATIO_MIN = 0.4
DF_MIN_ENTRIES = 3


def _strip_cn_stop(text: str) -> str:
    for w in _CN_STOP:
        text = text.replace(w, "")
    return text


def tokenize(text: str) -> set:
    """英文词 + 中文 bigram，统一小写。无第三方依赖。"""
    if not text:
        return set()
    text = text.lower()
    tokens = set()
    for w in _EN_WORD.findall(text):
        w = w.strip(".-")
        if len(w) >= 2 and w not in _STOP:
            tokens.add(w)
    cjk_run = _strip_cn_stop("".join(_CJK.findall(text)))
    for i in range(len(cjk_run) - 1):
        tokens.add(cjk_run[i:i + 2])
    return tokens


def df_generic_tokens(history: list) -> set:
    """跨条目文档频率过高的词：本批通用词，比较交集时整体剔除。

    只有历史条目达到 DF_MIN_ENTRIES 才启用；条目少时任何词都保留。
    """
    n = len(history)
    if n < DF_MIN_ENTRIES:
        return set()
    df = Counter()
    for e in history:
        for t in e["tokens"]:
            df[t] += 1
    return {t for t, c in df.items() if c / n >= DF_RATIO_MIN and c >= DF_MIN_ENTRIES}


def normalize_url(url: str) -> str:
    if not url:
        return ""
    u = url.strip().lower()
    u = re.sub(r"^https?://", "", u)
    u = u.split("?", 1)[0].split("#", 1)[0]
    u = u.rstrip("/")
    return u


def parse_history(path: Path):
    """从追踪台 markdown 抽条目：## <date> · <title> 起，到下一个同级/更短标题为止。"""
    entries = []
    lines = path.read_text(encoding="utf-8").splitlines()
    cur = None
    for line in lines:
        h = _HEADING.match(line)
        if h:
            head = _HEADING.sub("", line).strip()
            m = _DATE.search(head)
            if m:
                # 标题形如 "2026-10-12 · 浏览器 Agent 结果确认层" 或 "2026-10-12 浏览器..."
                title = _DATE.sub("", head).strip(" ·:-—　 ")
                cur = {"date": m.group(0), "title": title, "body_lines": [],
                       "source": path.name}
                entries.append(cur)
                continue
        if cur is not None:
            cur["body_lines"].append(line)
    out = []
    for e in entries:
        body = "\n".join(e.pop("body_lines"))
        e["tokens"] = tokenize(e["title"] + "\n" + body)
        e["urls"] = re.findall(r"https?://\S+", body)
        out.append(e)
    return out


def load_history(paths):
    entries = []
    for p in paths:
        p = Path(p)
        if p.is_dir():
            for md in sorted(p.glob("*.md")):
                entries.extend(parse_history(md))
        else:
            entries.extend(parse_history(p))
    return entries


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _host(url_norm: str) -> str:
    """归一化后的 URL 取域名（去掉 scheme 与路径）。"""
    if not url_norm:
        return ""
    return url_norm.split("/", 1)[0]


def judge(cand: dict, history: list, generic: set | None = None) -> dict:
    generic = generic or set()
    c_all = tokenize(cand.get("title", "") + "\n" + cand.get("direction", ""))
    c_tokens = c_all - generic
    c_title = tokenize(cand.get("title", "")) - generic
    c_url = normalize_url(cand.get("evidence_url", ""))
    c_host = _host(c_url)
    best = None
    best_cov = -1.0
    best_inter = 0
    best_title_cov = 0.0
    best_same_domain = False
    for e in history:
        e_tokens = e["tokens"] - generic
        inter = len(c_tokens & e_tokens)
        cov = inter / len(c_tokens) if c_tokens else 0.0
        # 复评驳回#2：标题短语覆盖率（title-only）。标题是浓缩主体，
        # 标题重合高 = 同主体换皮，比全句 coverage 更早抓到改写。
        title_cov = (len(c_title & e_tokens) / len(c_title)) if c_title else 0.0
        # 同一证据链接：强重复。
        same_url = bool(c_url) and any(
            c_url == normalize_url(u) for u in e.get("urls", []))
        if same_url:
            cov = max(cov, 0.9)
        # 同一证据域名（不必同链接）+ 同问题域：同一来源反复报同一件事。
        same_domain = bool(c_host) and any(
            c_host == _host(normalize_url(u)) for u in e.get("urls", []))
        if cov > best_cov:
            best_cov, best_inter, best = cov, inter, e
            best_title_cov, best_same_domain = title_cov, same_domain
    if best is None:
        return {"title": cand.get("title", ""), "verdict": "NEW", "score": 0.0,
                "matched": None, "reason": "历史为空，首跑全部 NEW"}
    # DUP 三条触发线（任一命中即同一件事换皮）：
    #   1) 全句覆盖率达标（原规则）；
    #   2) 标题短语覆盖率 ≥ 0.50（同主体改写，词换了但主体没变）；
    #   3) 同一证据域名 + 高文本重合（0.4.0 起要求 cov≥0.40，同源不同文章不再误判 DUP）。
    # 阈值仍由小样本 fixture 校准，真实数据积累后再调（见文件头注释）。
    dup_by_cov = best_cov >= DUP_COV_MIN and best_inter >= DUP_INTER_MIN
    dup_by_title = best_title_cov >= DUP_TITLE_MIN
    dup_by_domain = (best_same_domain
                     and best_cov >= DUP_DOMAIN_COV_MIN
                     and best_inter >= RELATED_INTER_MIN)
    if dup_by_cov or dup_by_title or dup_by_domain:
        verdict = "DUP"
        why = "标题短语高度重合" if dup_by_title else (
            "同一证据域名且高文本重合" if dup_by_domain else "方向覆盖率达标")
        reason = (f"{why}：候选与 {best['date']}「{best['title']}」是同一件事换皮"
                  f"（coverage {best_cov:.2f}，title_cov {best_title_cov:.2f}），不重复立条")
    elif best_cov >= RELATED_COV_MIN and best_inter >= RELATED_INTER_MIN:
        verdict = "RELATED"
        reason = (f"候选 {best_inter} 个有效词落在 {best['date']}「{best['title']}」里"
                  f"（覆盖率 {best_cov:.2f}，已剔除跨条目通用词），属近亲方向，不深挖，条目里注明近亲即可")
    else:
        verdict = "NEW"
        reason = (f"与最接近历史条目覆盖率 {best_cov:.2f}"
                  f"（{best_inter} 个有效词，title_cov {best_title_cov:.2f}，已剔除通用词），历史未覆盖，可立条")
    return {"title": cand.get("title", ""), "verdict": verdict,
            "score": round(best_cov, 3), "intersection": best_inter,
            "matched": {"date": best["date"], "title": best["title"]} if verdict != "NEW" else None,
            "reason": reason}


def main(argv) -> int:
    ap = argparse.ArgumentParser(description="与历史追踪台去重（每日雷达幂等）")
    ap.add_argument("--history", nargs="+", required=True,
                    help="追踪台 markdown 文件或目录（可多个）")
    ap.add_argument("--candidates", required=True, help="今日候选 JSON 路径")
    args = ap.parse_args(argv)

    try:
        history = load_history(args.history)
        candidates = json.loads(Path(args.candidates).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        # 错误信封与 score.py / artifact_io 同形同路（stderr），便于 Agent 机器解析。
        print(json.dumps({"status": "rejected", "error": str(e)}, ensure_ascii=False),
              file=sys.stderr)
        return 2

    generic = df_generic_tokens(history)
    results = [judge(c, history, generic) for c in candidates]
    summary = {"NEW": 0, "DUP": 0, "RELATED": 0, "candidates": len(results)}
    for r in results:
        summary[r["verdict"]] += 1
    payload = {"all_dup": summary["NEW"] == 0, "history_entries": len(history),
               "df_generic_dropped": sorted(generic),
               "summary": summary, "results": results}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if summary["NEW"] > 0 else 4


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
