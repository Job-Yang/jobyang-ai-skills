#!/usr/bin/env python3
"""Portable X/Twitter data provider — stdlib only, no company dependency.

This is the "refined" X intelligence layer. It does NOT know any fixed
endpoint or hold any key. Every backend is described by a provider profile
in config, so the same code works against:

  - any JSON-over-HTTP X API / proxy you are entitled to use (RapidAPI-style,
    Twitter API v2-style, an internal gateway, a self-hosted collector);
  - the shell: the host agent reads public profile pages and passes JSON in
    via --stdin (default zero-dependency mode).

Three semantic actions, regardless of backend shape:
  search_posts   -- keyword/time search
  user_posts     -- a handle's recent posts
  post_detail    -- one or more post ids/urls

Every backend is normalized to ONE output schema so the briefing pipeline
never depends on a specific vendor's field names.

Credentials come ONLY from environment variables referenced in the profile
(e.g. {"x-rapidapi-key": "$X_API_KEY"}). Never put a key on the command line,
in config that is committed, or in the skill files.

Usage:
  python3 x_provider.py search_posts --profile p.json --query "agent" --count 10
  python3 x_provider.py user_posts   --profile p.json --handle sama --count 10
  python3 x_provider.py post_detail  --profile p.json --post 123,456
  python3 x_provider.py search_posts --stdin < host_fetched.json

With --stdin it expects an array (or {"items":[...]}) already shaped like the
normalized schema; useful when the host agent itself reads x.com profiles.
"""
import argparse
import gzip
import io
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def fail(msg, code=2):
    sys.stderr.write(json.dumps({"error": msg}, ensure_ascii=False) + "\n")
    sys.exit(code)


def _get_path(obj, path):
    """Read a dotted path out of nested dicts/lists. 'a.b.0.c'."""
    cur = obj
    for part in (path or "").split("."):
        if part == "":
            continue
        if isinstance(cur, dict):
            if part not in cur:
                return None
            cur = cur[part]
        elif isinstance(cur, list) and part.isdigit():
            i = int(part)
            cur = cur[i] if i < len(cur) else None
        else:
            return None
    return cur


def _first(item, paths, default=None):
    for p in paths:
        v = _get_path(item, p)
        if v not in (None, ""):
            return v
    return default


def _env(value):
    """Replace '$VAR' / '${VAR}' markers with environment variables."""
    if isinstance(value, str):
        m = re.fullmatch(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?", value.strip())
        if m:
            return os.environ.get(m.group(1), "")
    if isinstance(value, dict):
        return {k: _env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_env(v) for v in value]
    return value


def load_profile(path):
    if not path:
        return None
    try:
        with io.open(path, "r", encoding="utf-8") as f:
            prof = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        fail("读取 X provider profile 失败: %s" % e)
    prof = _env(prof)
    return prof


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def http_json(method, url, headers=None, payload=None, timeout=30, retries=2):
    headers = dict(headers or {})
    headers.setdefault("User-Agent", UA)
    headers.setdefault("Accept-Encoding", "gzip")
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers.setdefault("Content-Type", "application/json")
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return json.loads(raw.decode("utf-8", errors="ignore"))
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", "replace")[:300]
            except Exception:
                pass
            last = "HTTP %s %s" % (e.code, body)
            if e.code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(1.5 * (attempt + 1))
                continue
            fail("X provider 请求失败: %s" % last)
        except Exception as e:  # network/DNS/TLS/TLS
            last = str(e)
            if attempt < retries:
                time.sleep(1.0 * (attempt + 1))
                continue
            fail("X provider 网络失败（请检查公网/代理/凭证）: %s" % last)


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

POST_URL_RE = re.compile(r"(?:x|twitter)\.com/[^/]+/status/(\d+)")


def _candidates(spec):
    """A field spec may be a single dotted path or 'a|b' alternatives."""
    if not spec:
        return []
    if isinstance(spec, (list, tuple)):
        out = []
        for x in spec:
            out.extend(_candidates(x))
        return out
    return [p for p in str(spec).split("|") if p]


def normalize_post(item, maps):
    item = item if isinstance(item, dict) else {}
    author = _get_path(item, maps.get("author_path", "")) if maps.get("author_path") else item
    if not isinstance(author, dict):
        author = item

    text = _first(item, _candidates(maps.get("text")) or
                  ["text", "content", "full_text", "title", "description"], "")
    post_id = _first(item, _candidates(maps.get("id")), "")
    url = _first(item, _candidates(maps.get("url")), "")
    created = _first(item, _candidates(maps.get("created_at")) or
                     ["created_at", "publish_time", "published_at"], "")
    handle = _first(author, _candidates(maps.get("author_handle_path")) or
                    ["screen_name", "username"], "")
    name = _first(author, _candidates(maps.get("author_name_path")) or
                  ["name", "nickname"], "")
    if not url and post_id:
        url = "https://x.com/%s/status/%s" % (handle or "i", post_id)

    stats_spec = maps.get("stats")
    st = _first(item, _candidates(stats_spec), {}) if stats_spec else {}
    if not isinstance(st, dict):
        st = {}
    # stdin / no-map mode: accept the common metric containers from several
    # vendors so host-read data normalizes without a profile.
    for cand in ("statistics", "public_metrics", "metrics", "stats"):
        v = _get_path(item, cand)
        if isinstance(v, dict) and v:
            st = v
            break

    return {
        "id": str(post_id or ""),
        "url": url or "",
        "text": text,
        "created_at": created,
        "author": {"handle": handle, "name": name},
        "metrics": {
            "likes": _first(st, ["like_count", "likes", "favorite_count", "heart_count"], None),
            "reposts": _first(st, ["repost_count", "retweet_count", "shares", "share_count"], None),
            "replies": _first(st, ["reply_count", "comment_count", "replies", "comments"], None),
            "views": _first(st, ["view_count", "views", "impression_count"], None),
        },
    }


def extract_items(resp, action, maps):
    # 1) explicit items path
    items_path = maps.get("items_path")
    if items_path:
        items = _get_path(resp, items_path)
        if isinstance(items, list):
            return items
    # 2) common fallbacks
    for p in ("data.items", "data.tweets", "data", "items", "tweets", "results"):
        v = _get_path(resp, p)
        if isinstance(v, list):
            return v
    # 3) single post detail may be a dict
    if action == "post_detail" and isinstance(resp, dict):
        for p in ("data", "data.tweet", "tweet"):
            v = _get_path(resp, p)
            if isinstance(v, dict):
                return [v]
    return []


def call_action(profile, action, query=None, handle=None, posts=None, count=20,
                after=None, before=None, search_type="Top"):
    if not profile:
        fail("没有配置 X provider profile；零依赖模式请用 --stdin 传入宿主读到的帖子")
    mode = profile.get("mode", "http")
    maps = profile.get("maps", {})
    if mode == "stdin":
        raw = json.loads(sys.stdin.read() or "{}")
        items = raw.get("items", raw if isinstance(raw, list) else [])
        return [normalize_post(it, maps) for it in items]

    action_cfg = (profile.get("actions") or {}).get(action)
    if not action_cfg:
        fail("profile 缺少 action 配置: %s" % action)
    url = action_cfg["url"]
    method = (action_cfg.get("method") or "POST").upper()
    # build body/query from the profile's parameter template
    params = dict(action_cfg.get("params", {}))
    for k, v in (
        ("query", query), ("q", query), ("keyword", query),
        ("handle", handle), ("screen_name", handle), ("id", handle), ("username", handle),
        ("posts", posts), ("tweet_ids", posts), ("ids", posts),
        ("count", count), ("limit", count),
        ("after", after), ("published_after", after), ("since", after),
        ("before", before), ("published_before", before), ("until", before),
        ("search_type", search_type),
    ):
        if v is None or v == "":
            continue
        if k in params and "{value}" in str(params[k]):
            params[k] = str(params[k]).replace("{value}", str(v))
        elif k not in params:
            params[k] = v
    headers = _env(profile.get("headers", {}))
    if method == "GET":
        from urllib.parse import urlencode
        url = url + ("&" if "?" in url else "?") + urlencode({k: v for k, v in params.items() if v is not None})
        resp = http_json(method, url, headers, None, profile.get("timeout", 30))
    else:
        body_tpl = action_cfg.get("body")
        if body_tpl:
            body = json.loads(json.dumps(body_tpl))
            for k, v in params.items():
                if v is not None:
                    body[k] = v
        else:
            body = params
        resp = http_json(method, url, headers, body, profile.get("timeout", 30))
    items = extract_items(resp, action, maps)
    out = [normalize_post(it, maps) for it in items]
    return out[:count] if count else out


def split_posts(raw):
    if not raw:
        return None
    ids = []
    for part in re.split(r"[,\s]+", raw.strip()):
        m = POST_URL_RE.search(part)
        ids.append(m.group(1) if m else part)
    return ",".join([i for i in ids if i])


def main():
    ap = argparse.ArgumentParser(description="Portable X data provider (stdlib only).")
    ap.add_argument("action", choices=["search_posts", "user_posts", "post_detail"])
    ap.add_argument("--profile", default="", help="JSON file describing the backend (endpoint + field maps).")
    ap.add_argument("--stdin", action="store_true", help="Read host-fetched posts JSON from stdin.")
    ap.add_argument("--query"), ap.add_argument("--handle"), ap.add_argument("--post")
    ap.add_argument("--count", type=int, default=20)
    ap.add_argument("--after"), ap.add_argument("--before"), ap.add_argument("--search-type", default="Top")
    args = ap.parse_args()

    profile = load_profile(args.profile) if not args.stdin else {"mode": "stdin"}
    posts = split_posts(args.post) if args.post else None
    items = call_action(
        profile, args.action,
        query=args.query, handle=args.handle, posts=posts,
        count=args.count, after=args.after, before=args.before,
        search_type=args.search_type,
    )
    json.dump({"provider": (profile or {}).get("name", "stdin"),
               "action": args.action, "count": len(items), "items": items},
              sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
