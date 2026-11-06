#!/usr/bin/env python3
"""每日机会池采集：把可达的公开信息源拉成一张归一化的原始信号池（纯标准库）。

为什么需要它
------------
0.3.x 的雷达没有"采集"这一步：每天靠 Agent 临时跑几条通用搜索词，输入基本是
SEO 博客，原始候选只有 4 条上下。Reddit/X/即刻/小红书/Google Trends/G2 在云电脑
又大多不可达（403/429/登录墙），于是"五源"长期只读得到通用网页搜这一条路。

本脚本把**确实可达、无需登录、无需 key** 的源固化下来，每个源独立容错：
  - hunted.space   当日 Product Hunt 榜（votes/comments/topics，结构化）
  - ph_feed        Product Hunt 官方 Atom（近 50 条发布）
  - gh_trending    GitHub Trending（daily，stars today）
  - gh_new         GitHub Search：近 N 天新建且涨星快的仓（供给侧新能力）
  - hn_show        Show HN（近 N 天高赞发布）
  - hn_ask         Ask HN（近 N 天高赞提问）
  - hn_wishes      HN 评论里的许愿/愿付原话（需求侧原话）
  - hf_spaces      Hugging Face trending Spaces（新模型能力外溢）
  - devto          DEV.to 近 3 天热文（开发者痛点）
  - v2ex_create    V2EX 创造节点（中文独立开发者当日发布）
  - v2ex_hot       V2EX 热门（中文需求与发布）
  - lobsters       Lobsters hottest（技术社区发布与讨论）
  - reddit_rss     Reddit RSS（SaaS/SideProject 等，限流时只记 blocked）
  - appstore_money App Store 效率类畅销榜（钱在流向什么 app）

它只负责"取数 + 归一化 + 逐源记状态"，不判断哪个是机会——那是 Agent 的语义活。
所有源都失败也不抛异常：输出空 items + 逐源 status，由上层按"失败留痕"处理。

用法
----
  python3 collect.py --out <目录> [--since-days 3] [--only id1,id2]
产出：
  <目录>/pool.json  全量机器可读池
  <目录>/pool.md    给 Agent 读的精简清单（每源最多 12 条）

退出码：0=至少一个源取到数据；4=所有源都没取到（雷达静默失败信号，不是参数错误）；
        2=参数/输出目录错误。
"""
import argparse
import concurrent.futures as futures
import datetime as dt
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36")
TIMEOUT = 20
MAX_ITEMS_PER_SOURCE = 60
MD_PER_SOURCE = 12


def http_get(url, timeout=TIMEOUT, retries=1, ua=UA):
    """GET 文本。429 时按重试次数退避一次；其余异常原样抛出。ua 可按源覆盖。"""
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (429, 502, 503, 504) and attempt < retries:
                time.sleep(2)
                continue
            raise
        except Exception as e:  # noqa: BLE001 - 逐源容错，错误交给 status 记录
            last = e
            if attempt < retries:
                time.sleep(1)
                continue
            raise
    raise last


def clean(text, limit=None):
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", html.unescape(text))
    text = re.sub(r"\s+", " ", text).strip()
    if limit and len(text) > limit:
        text = text[:limit].rstrip() + "…"
    return text


def item(source, kind, title, url, tagline="", date=None, metric=None, topics=None):
    return {
        "source": source,
        "source_kind": kind,  # supply=新供给/发布 | demand=需求原话 | money=钱流向 | tech=技术能力
        "title": clean(title, 160),
        "tagline": clean(tagline, 240),
        "url": url or "",
        "date": date or "",
        "metric": metric or {},
        "topics": topics or [],
    }


def to_int(s):
    if s is None:
        return None
    m = re.search(r"[\d,]+", str(s))
    return int(m.group(0).replace(",", "")) if m else None


def src_hunted():
    """hunted.space 首页 __NEXT_DATA__：当日 PH 榜，含票数/评论/话题。"""
    b = http_get("https://hunted.space/")
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', b, re.S)
    if not m:
        return [], "empty: __NEXT_DATA__ not found"
    posts = json.loads(m.group(1))["props"]["pageProps"]["initialStats"]["posts"]
    out = []
    for p in posts:
        out.append(item(
            "hunted", "supply", p.get("name", ""), p.get("url", ""),
            p.get("tagline", ""), (p.get("featuredAt") or "")[:10],
            {"kind": "votes", "value": p.get("votesCount") or 0,
             "comments": p.get("commentsCount") or 0},
            [t.get("name", "") for t in p.get("topics", []) if t.get("name")]))
    return out, None


def src_ph_feed():
    """Product Hunt 官方 Atom：近期发布，无票数，补 hunted 之外的长尾。"""
    b = http_get("https://www.producthunt.com/feed")
    out, seen = [], set()
    for e in re.findall(r"<entry>(.*?)</entry>", b, re.S):
        t = re.search(r"<title[^>]*>(.*?)</title>", e, re.S)
        l = re.search(r'<link[^>]*href="([^"]+)"', e)
        d = re.search(r"<published>(.*?)</published>", e, re.S)
        c = re.search(r"<content[^>]*>(.*?)</content>", e, re.S)
        url = l.group(1) if l else ""
        if url in seen:
            continue
        seen.add(url)
        out.append(item("ph_feed", "supply", t.group(1) if t else "", url,
                        c.group(1) if c else "", (d.group(1)[:10] if d else "")))
    return out, None


def src_gh_trending():
    """GitHub Trending daily 页（HTML 正则，只取公开字段）。"""
    b = http_get("https://github.com/trending?since=daily")
    out = []
    for art in re.findall(r'<article class="Box-row">(.*?)</article>', b, re.S):
        m = re.search(r'<h2[^>]*>\s*<a[^>]*href="/([^"]+)"', art, re.S)
        if not m:
            continue
        repo = re.sub(r"\s+", "", m.group(1))
        desc = re.search(r'<p class="col-9[^"]*">(.*?)</p>', art, re.S)
        today = re.search(r"([\d,]+)\s*stars today", art)
        total = re.search(r'aria-label="[\d,]+ stars"[^>]*>\s*([\d,]+)', art)
        lang = re.search(r'itemprop="programmingLanguage">([^<]+)<', art)
        out.append(item(
            "github_trending", "tech", repo, f"https://github.com/{repo}",
            desc.group(1) if desc else "", "",
            {"kind": "stars_today", "value": to_int(today.group(1)) if today else None,
             "stars_total": to_int(total.group(1)) if total else None},
            [lang.group(1).strip()] if lang else []))
    return out, None


def src_gh_new(since_days):
    """GitHub Search API：近 N 天新建、star 已过百的仓（能力爆发的早期信号）。

    无 token 限流 10 次/分钟，这里只用两个查询：泛 AI 关键词 + 不限关键词，
    避免把非 AI 新高星也漏掉。
    """
    cutoff = (dt.date.today() - dt.timedelta(days=since_days)).isoformat()
    queries = [
        f"created:>{cutoff} stars:>100",
    ]
    out, seen = [], set()
    for q in queries:
        u = ("https://api.github.com/search/repositories?q="
             + urllib.parse.quote(q) + "&sort=stars&order=desc&per_page=30")
        b = http_get(u)
        for it in json.loads(b).get("items", []):
            full = it["full_name"]
            if full in seen:
                continue
            seen.add(full)
            out.append(item(
                "github_new", "tech", full, it["html_url"], it.get("description") or "",
                (it.get("created_at") or "")[:10],
                {"kind": "stars", "value": it.get("stargazers_count")},
                [it.get("language") or ""]))
    return out, None


def _hn(tags, since_days, min_points, kind, url_field=None, limit=40):
    cutoff = int(time.time()) - since_days * 86400
    nf = f"created_at_i>{cutoff},points>{min_points}"
    u = ("https://hn.algolia.com/api/v1/search_by_date?tags="
         + urllib.parse.quote(tags) + "&numericFilters="
         + urllib.parse.quote(nf) + f"&hitsPerPage={limit}")
    b = http_get(u)
    out = []
    for h in json.loads(b).get("hits", []):
        title = h.get("title") or h.get("story_title") or ""
        url = url_field and h.get(url_field) or h.get("url") or \
            f"https://news.ycombinator.com/item?id={h.get('objectID')}"
        if not h.get("url") and "news.ycombinator.com" not in url:
            url = f"https://news.ycombinator.com/item?id={h.get('objectID')}"
        date = (h.get("created_at") or "")[:10]
        out.append(item("hackernews", kind, title, url,
                        h.get("story_text") or "", date,
                        {"kind": "points", "value": h.get("points") or 0,
                         "comments": h.get("num_comments") or 0}))
    return out


def src_hn_show(since_days):
    return _hn("show_hn", max(since_days, 3), 15, "supply"), None


def src_hn_ask(since_days):
    return _hn("ask_hn", max(since_days, 7), 10, "demand"), None


def src_hn_wishes(since_days):
    """HN 评论里的许愿/愿付原话。同一帖只保留一条，tagline 是评论原话。

    Algolia 对 query 不支持 OR 布尔，每个许愿短语分开发请求。
    """
    phrases = ['"wish there was"', '"would pay for"']
    cutoff = int(time.time()) - max(since_days, 14) * 86400
    best = {}
    for phrase in phrases:
        u = ("https://hn.algolia.com/api/v1/search?tags=comment&query="
             + urllib.parse.quote(phrase)
             + f"&numericFilters=created_at_i%3E{cutoff}&hitsPerPage=50")
        for h in json.loads(http_get(u)).get("hits", []):
            sid = h.get("story_id")
            text = clean(h.get("comment_text"), 200)
            if not text:
                continue
            cur = best.get(sid)
            if cur is None or (h.get("points") or 0) > cur[0]:
                story_title = h.get("story_title") or "HN 讨论"
                date = (h.get("created_at") or "")[:10]
                url = f"https://news.ycombinator.com/item?id={h.get('objectID')}"
                best[sid] = (h.get("points") or 0,
                             item("hackernews_comments", "demand",
                                  f"HN 许愿：{story_title}", url, text, date,
                                  {"kind": "points", "value": h.get("points") or 0}))
    return [v[1] for v in best.values()], None


def src_hn_front(since_days):
    """Hacker News 首页：当天业界最热的事，包括讨论里的机会线索。"""
    u = "https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=30"
    out = []
    for h in json.loads(http_get(u)).get("hits", []):
        out.append(item(
            "hn_front", "demand", h.get("title", ""),
            h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}",
            "", (h.get("created_at") or "")[:10],
            {"kind": "points", "value": h.get("points") or 0,
             "comments": h.get("num_comments") or 0}))
    return out, None


def src_hf_spaces(since_days):
    b = http_get("https://huggingface.co/api/spaces?sort=trendingScore&limit=40")
    out = []
    for s in json.loads(b):
        card = s.get("cardData") or {}
        desc = card.get("short_description", "") if isinstance(card, dict) else ""
        out.append(item(
            "huggingface", "tech", s.get("id", ""),
            f"https://huggingface.co/spaces/{s.get('id','')}", desc,
            (s.get("lastModified") or "")[:10],
            {"kind": "likes", "value": s.get("likes") or 0,
             "trending": s.get("trendingScore")}))
    return out, None


def src_hf_models(since_days):
    """Hugging Face trending models：最新模型能力发布，产品机会跟着新能力走。"""
    b = http_get("https://huggingface.co/api/models?sort=trendingScore&limit=40")
    out = []
    for m in json.loads(b):
        out.append(item(
            "hf_models", "tech", m.get("id", ""),
            f"https://huggingface.co/{m.get('id','')}",
            (m.get("pipeline_tag") or ""), (m.get("lastModified") or "")[:10],
            {"kind": "likes", "value": m.get("likes") or 0,
             "downloads": m.get("downloads") or 0},
            [m.get("pipeline_tag") or ""]))
    return out, None


def src_devto(since_days):
    # 最新 40 条 + 近一周热门 40 条合并：只看 top 会漏掉当天新文。
    urls = ["https://dev.to/api/articles?per_page=40",
            "https://dev.to/api/articles?top=7&per_page=40"]
    out, seen = [], set()
    for u in urls:
        for a in json.loads(http_get(u)):
            if a.get("url") in seen:
                continue
            seen.add(a.get("url"))
            out.append(item(
                "devto", "demand", a.get("title", ""), a.get("url", ""),
                a.get("description", ""), (a.get("published_at") or "")[:10],
                {"kind": "reactions", "value": a.get("public_reactions_count") or 0,
                 "comments": a.get("comments_count") or 0},
                [str(t) for t in (a.get("tag_list") or [])[:4]]))
    return out, None


V2EX_UA = "radar-personal-research/0.4 (opportunity-radar; contact=local)"


def _v2ex_node(node, source, kind):
    b = http_get(f"https://www.v2ex.com/api/topics/show.json?node_name={node}", ua=V2EX_UA)
    out = []
    for t in json.loads(b):
        date = dt.datetime.fromtimestamp(t["created"]).date().isoformat()
        out.append(item(source, kind, t.get("title", ""), t.get("url", ""),
                        t.get("content_rendered", ""), date,
                        {"kind": "replies", "value": t.get("replies", 0)},
                        [node]))
    return out


def src_v2ex_create(since_days):
    return _v2ex_node("create", "v2ex", "supply"), None


def src_v2ex_hot(since_days):
    out, seen = [], set()
    for endpoint in ("hot", "latest"):
        b = http_get(f"https://www.v2ex.com/api/topics/{endpoint}.json", ua=V2EX_UA)
        for t in json.loads(b):
            if t.get("url") in seen:
                continue
            seen.add(t.get("url"))
            date = dt.datetime.fromtimestamp(t["created"]).date().isoformat()
            out.append(item("v2ex_hot", "demand", t.get("title", ""), t.get("url", ""),
                            t.get("content_rendered", ""), date,
                            {"kind": "replies", "value": t.get("replies", 0)},
                            [t.get("node", {}).get("title", "")]))
    return out, None



def src_lobsters(since_days):
    out, seen = [], set()
    for endpoint in ("hottest", "newest"):
        b = http_get(f"https://lobste.rs/{endpoint}.json")
        for t in json.loads(b):
            if t.get("short_id") in seen:
                continue
            seen.add(t.get("short_id"))
            out.append(item("lobsters", "supply", t.get("title", ""),
                            t.get("url") or f"https://lobste.rs/s/{t.get('short_id')}",
                            t.get("description", ""), (t.get("created_at") or "")[:10],
                            {"kind": "points", "value": t.get("score") or 0,
                             "comments": t.get("comment_count") or 0},
                            t.get("tags", [])))
    return out, None


def src_reddit(since_days):
    """Reddit 公开 RSS（云电脑 JSON API 被 403，RSS 偶发 429）。

    每个 sub 独立容错；全挂时 status=blocked，不算整池失败。
    """
    subs = ["SaaS", "SideProject", "indie", "Entrepreneur", "smallbusiness"]
    out, seen, errors = [], set(), []
    for i, sub in enumerate(subs):
        if i:
            time.sleep(1.0)
        try:
            b = http_get(f"https://www.reddit.com/r/{sub}/top/.rss?t=week&limit=15",
                         retries=1)
            for e in re.findall(r"<entry>(.*?)</entry>", b, re.S):
                t = re.search(r"<title>(.*?)</title>", e, re.S)
                l = re.search(r'<link href="([^"]+)"', e)
                d = re.search(r"<updated>(.*?)</updated>", e, re.S)
                c = re.search(r"<content[^>]*>(.*?)</content>", e, re.S)
                url = l.group(1) if l else ""
                if url in seen:
                    continue
                seen.add(url)
                out.append(item(f"reddit_{sub.lower()}", "demand",
                                t.group(1) if t else "", url,
                                c.group(1) if c else "",
                                (d.group(1)[:10] if d else "")))
        except Exception as e:  # noqa: BLE001
            errors.append(f"{sub}:{type(e).__name__}")
    err = "blocked: " + ",".join(errors) if errors and not out else None
    if errors and out:
        err = "partial: " + ",".join(errors)
    return out, err


def src_appstore_money(since_days):
    """美区效率类畅销榜：钱正在流向哪些 app（付费流向观察，非机会本身）。"""
    u = ("https://itunes.apple.com/us/rss/topgrossingapplications"
         "/genre=6007/limit=25/json")
    b = http_get(u)
    entries = json.loads(b)["feed"].get("entry", [])
    if isinstance(entries, dict):
        entries = [entries]
    out = []
    for i, a in enumerate(entries):
        name = a.get("im:name", {}).get("label", "")
        out.append(item("appstore_money", "money", name,
                        a.get("id", {}).get("label", ""),
                        f"美区效率类畅销榜第 {i + 1} 名", "",
                        {"kind": "rank", "value": i + 1}))
    return out, None


# 第三项 = 是否吃 --since-days 时间窗参数
# 0.4.1：ph_feed、hunted 是榜单快照不吃窗口；其余文本源窗口 5 天。
SOURCES = [
    ("hunted", src_hunted, False),
    ("ph_feed", src_ph_feed, False),
    ("gh_trending", src_gh_trending, False),
    ("gh_new", src_gh_new, True),
    ("hn_show", src_hn_show, True),
    ("hn_ask", src_hn_ask, True),
    ("hn_wishes", src_hn_wishes, True),
    ("hf_spaces", src_hf_spaces, True),
    ("hf_models", src_hf_models, True),
    ("hn_front", src_hn_front, True),
    ("devto", src_devto, True),
    ("v2ex_create", src_v2ex_create, True),
    ("v2ex_hot", src_v2ex_hot, True),
    ("lobsters", src_lobsters, True),
    ("reddit_rss", src_reddit, True),
    ("appstore_money", src_appstore_money, True),
]


def collect(since_days, only):
    wanted = {s for s in only.split(",") if s} if only else None
    jobs = {}
    with futures.ThreadPoolExecutor(max_workers=7) as ex:
        for sid, fn, uses_window in SOURCES:
            if wanted and sid not in wanted:
                continue
            jobs[ex.submit(fn, since_days) if uses_window else ex.submit(fn)] = sid
        results = {}
        for fut in futures.as_completed(jobs):
            results[jobs[fut]] = fut
    sources, items = [], []
    for sid, fn, _ in SOURCES:
        if wanted and sid not in wanted:
            continue
        fut = results.get(sid)
        if fut is None:
            continue
        try:
            src_items, err = fut.result()
            src_items = src_items[:MAX_ITEMS_PER_SOURCE]
            for x in src_items:
                x["source"] = sid
            status = "ok" if src_items else ("empty" if not err else "blocked")
            sources.append({"id": sid, "status": status, "count": len(src_items),
                            "error": err})
            items.extend(src_items)
        except Exception as e:  # noqa: BLE001
            sources.append({"id": sid, "status": "blocked", "count": 0,
                            "error": f"{type(e).__name__}: {str(e)[:120]}"})
    # 全池按 URL 去重（保留先出现的，通常是票数更高的源）。
    # 注意：HN 评论链接是 item?id=<id> 形式，id 在 query 里，不能先砍 query，
    # 否则所有 HN 评论会被并成一条（0.4.0 实测踩过）。
    def _dedup_key(url):
        if "news.ycombinator.com/item" in url:
            return url.split("#", 1)[0]
        return url.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    dedup, seen = [], set()
    for it in items:
        key = _dedup_key(it["url"])
        if key and key not in seen:
            seen.add(key)
            dedup.append(it)
    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(),
        "since_days": since_days,
        "sources": sources,
        "total_items": len(dedup),
        "items": dedup,
    }


def render_md(pool):
    lines = [f"# 每日机会池 {pool['generated_at'][:10]}（窗口 {pool['since_days']} 天）",
             f"共 {pool['total_items']} 条，逐源状态："
             + "，".join(f"{s['id']} {s['status']}({s['count']})"
                        for s in pool["sources"]),
             ""]
    by = {}
    for it in pool["items"]:
        by.setdefault(it["source"], []).append(it)
    for s in pool["sources"]:
        group = by.get(s["id"], [])[:MD_PER_SOURCE]
        lines.append(f"## {s['id']} · {s['status']} · {s['count']} 条")
        if s["error"]:
            lines.append(f"> 取数备注：{s['error']}")
        for it in group:
            mv = it["metric"].get("value")
            metric = f"（{it['metric'].get('kind')} {mv}）" if mv is not None else ""
            tag = f" — {it['tagline']}" if it["tagline"] else ""
            lines.append(f"- **{it['title']}**{metric}{tag} {it['url']}")
        if not group:
            lines.append("- （本源今日无数据）")
        lines.append("")
    return "\n".join(lines)


def main(argv) -> int:
    ap = argparse.ArgumentParser(description="每日机会池多源采集（纯标准库）")
    ap.add_argument("--out", required=True, help="输出目录")
    ap.add_argument("--since-days", type=int, default=5)
    ap.add_argument("--only", help="只跑指定源（逗号分隔），调试用")
    args = ap.parse_args(argv)
    out_dir = Path(args.out)
    if not out_dir.is_dir():
        print(json.dumps({"status": "rejected",
                          "error": f"输出目录不存在: {out_dir}"}, ensure_ascii=False),
              file=sys.stderr)
        return 2
    pool = collect(args.since_days, args.only)
    (out_dir / "pool.json").write_text(
        json.dumps(pool, ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / "pool.md").write_text(render_md(pool), encoding="utf-8")
    ok = sum(1 for s in pool["sources"] if s["status"] == "ok")
    print(json.dumps({"status": "collected", "total_items": pool["total_items"],
                      "sources_ok": ok, "sources": pool["sources"]},
                     ensure_ascii=False, indent=1))
    return 0 if pool["total_items"] > 0 else 4


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
