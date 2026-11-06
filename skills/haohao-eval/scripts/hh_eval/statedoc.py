# -*- coding: utf-8 -*-
"""飞书状态文档：生成、解析、恢复。格式红线：一行没动（sha256 头、pre/code 块、分段）。"""
import datetime as dt
import hashlib
import html
import json
import os
import re
import unicodedata

from hh_eval.const import (NOTES_TITLE, SECTION_TITLE, STATE_BLOCK_MAX, STATE_DOC_TITLE, STATE_LINE_MAX,
                           STATE_TAG, VERSION, Stop)
from hh_eval.fs import (H, eval_home, load_json, published_path, read_json, read_jsonl, read_text,
                        save_json, write_jsonl, write_text)
from hh_eval.gates import cluster_tag, mode_label
from hh_eval.rules import rules_of
from hh_eval.seed import active_notes, eligible_clusters


def state_files():
    """跨天要带走的文件：数据目录里除了运行目录、导出、锁和临时文件以外的全部。"""
    home, out = eval_home(), []
    for root, dirs, names in os.walk(home):
        rel = os.path.relpath(root, home)
        parts = [] if rel == "." else rel.split(os.sep)
        if not parts:
            dirs[:] = [d for d in dirs if d not in ("runs", "exports")]
        dirs.sort()
        for nm in sorted(names):
            if nm != "loop.lock" and not nm.endswith(".tmp"):
                out.append("/".join(parts + [nm]))
    return out


def doc_safe(obj):
    """一行 JSON，只留飞书文档不会动的字符：尖括号、& 和各种不可见字符都写成 \\u 转义。"""
    out = []
    for ch in json.dumps(obj, ensure_ascii=False, separators=(",", ":")):
        o = ord(ch)
        if o > 0xFFFF:
            o -= 0x10000
            out.append("\\u%04x\\u%04x" % (0xD800 + (o >> 10), 0xDC00 + (o & 0x3FF)))
        elif ch in "<>&" or (o >= 0x7F and unicodedata.category(ch)[0] in "CZ"):
            out.append("\\u%04x" % o)
        else:
            out.append(ch)
    return "".join(out)


def flatten(rel, path, v, out):
    """大的 JSON 拆成「路径 + 值」一行一条，每行都不长，文档里分段存也不会从中间截断。"""
    line = doc_safe(["v", rel, path, v])
    if len(line) <= STATE_LINE_MAX or not isinstance(v, (dict, list, str)):
        out.append(line)
    elif isinstance(v, str):
        step = STATE_LINE_MAX // 3
        for i in range(0, len(v), step):
            out.append(doc_safe(["s", rel, path, v[i:i + step]]))
    else:
        out.append(doc_safe(["v", rel, path, {} if isinstance(v, dict) else []]))
        for k, x in (v.items() if isinstance(v, dict) else enumerate(v)):
            flatten(rel, path + [k], x, out)


def state_body():
    body = []
    for rel in state_files():
        path = os.path.join(eval_home(), *rel.split("/"))
        kind = "jsonl" if rel.endswith(".jsonl") else "json" if rel.endswith(".json") else "text"
        body.append(doc_safe(["f", rel, kind]))
        flatten(rel, [], read_jsonl(path) if kind == "jsonl" else load_json(path) if kind == "json" else read_text(path), body)
    if os.path.exists(published_path()):
        body.append(doc_safe(["f", "@published", "text"]))
        flatten("@published", [], read_text(published_path()), body)
    return body


def get_at(root, path):
    cur = root
    for k in path:
        if isinstance(cur, list) and isinstance(k, int) and k < len(cur):
            cur = cur[k]
        elif isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            return None
    return cur


def put_at(root, path, v):
    if not path:
        return v
    parent, k = get_at(root, path[:-1]), path[-1]
    if isinstance(parent, list) and isinstance(k, int) and k <= len(parent):
        parent[k:k + 1] = [v]
    elif isinstance(parent, dict) and isinstance(k, str):
        parent[k] = v
    else:
        raise Stop("状态里的路径对不上：" + json.dumps(path, ensure_ascii=False))
    return root


def safe_rel(rel):
    return rel == "@published" or (isinstance(rel, str) and bool(re.fullmatch(r"[A-Za-z0-9._/\-]+", rel))
                                   and not rel.startswith("/") and ".." not in rel.split("/"))


def unflatten(lines):
    files = {}
    for n, ln in enumerate(lines, 1):
        try:
            rec = json.loads(ln)
            kind, rel = rec[0], rec[1]
            if kind == "f":
                if not safe_rel(rel) or rec[2] not in ("json", "jsonl", "text"):
                    raise Stop(f"状态里有不该有的文件：{rel}")
                files[rel] = [rec[2], None]
            elif rel in files and kind in ("v", "s"):
                f = files[rel]
                f[1] = put_at(f[1], rec[2], rec[3] if kind == "v" else (get_at(f[1], rec[2]) or "") + rec[3])
            else:
                raise Stop(f"状态第 {n} 行读不懂，不恢复。")
        except (json.JSONDecodeError, IndexError, TypeError, KeyError):
            raise Stop(f"状态第 {n} 行读不懂，不恢复。")
    return files


def free_path(base):
    path, n = base, 1
    while os.path.exists(path):
        path, n = f"{base}-{n}", n + 1
    return path


def install_state(files):
    """先写到旁边的临时目录，写完整了再换上；原来的数据目录和细则挪到 .bak 备份。"""
    home = eval_home().rstrip(os.sep)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    tmp = free_path(f"{home}.load-{stamp}")
    pub = None
    for rel, (kind, value) in files.items():
        if rel == "@published":
            pub = value or ""
            continue
        dst = os.path.join(tmp, *rel.split("/"))
        if kind == "jsonl":
            write_jsonl(dst, value or [])
        elif kind == "json":
            save_json(dst, value)
        else:
            write_text(dst, value or "")
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
        write_text(pp, pub)
    return moved


def esc(s):
    return html.escape(str(s), quote=False)


def para(s):
    return f"<p>{esc(s)}</p>"


def bullets(items):
    return "<ul>" + "".join(f"<li>{esc(s)}</li>" for s in items) + "</ul>"


def clip(s, n):
    s = (s or "").strip()
    return s if len(s) <= n else s[:n] + "……"


def rules_xml(rules, title):
    """细则是 Markdown：「## 细则」那行用 title 包成小标题，连着的「- 」行并成一个列表，别的行照段落。"""
    x, items = [], []
    for ln in "\n".join(rules).splitlines() + [""]:
        s = ln.strip()
        if s.startswith("- "):
            items.append(s[2:].strip())
            continue
        if items:
            x.append(bullets(items))
            items = []
        m = re.match(r"#+\s+(.*)$", s)
        if m:
            x.append(title(esc(m.group(1))))
        elif s:
            x.append(para(s))
    return x


def state_header(body, seq, today, empty=False):
    h = {STATE_TAG: 1, "version": VERSION, "seq": seq, "date": today, "lines": len(body),
         "sha256": hashlib.sha256("\n".join(body).encode("utf-8")).hexdigest()}
    if empty:
        h["empty"] = True
    return h


def state_doc_xml(header, body, summary, rules):
    blocks, cur, size = [], [], 0
    for ln in [doc_safe(header)] + body:
        if cur and size + len(ln) + 1 > STATE_BLOCK_MAX:
            blocks.append(cur)
            cur, size = [], 0
        cur.append(ln)
        size += len(ln) + 1
    blocks.append(cur)
    x = [f"<title>{STATE_DOC_TITLE}</title>",
         "<callout><p>这份文档是每日召回跨天的记忆，Mira 每天收尾时整篇重写。「现在的情况」和「现用细则」可以随时看；"
         "下面的机器状态别手改，改过就对不上，第二天会停下来等你处理。"
         f"要交代什么，写在召回文档「{SECTION_TITLE}」里的「{NOTES_TITLE}」，或者直接在任务对话里说。</p></callout>",
         "<h2>现在的情况</h2>", bullets(summary)]
    if rules is not None:
        x.append("<h2>现用细则</h2>")
        x += rules_xml(rules_of(rules)[0], lambda t: f"<h3>{t}</h3>") or [para("（还没有细则）")]
    x.append("<h2>机器状态</h2>")
    x.append(para(f"第 {header['seq']} 份 · {header['date']} · {len(blocks)} 段 · 校验 {header['sha256'][:12]}"))
    for i, b in enumerate(blocks, 1):
        x.append(f'<pre lang="json" caption="状态 {i}/{len(blocks)}"><code>' + "\n".join(b) + "</code></pre>")
    return "\n".join(x) + "\n"


def doc_content(path):
    """docs +fetch 的输出（JSON）和文档正文本身（XML / Markdown）都认。"""
    raw = read_text(path)
    if not raw.strip():
        raise Stop(f"{path} 是空的：文档没读下来。")
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    if isinstance(obj, dict):
        if obj.get("ok") is False:
            raise Stop("读文档失败：" + json.dumps(obj.get("error") or obj, ensure_ascii=False)[:300])
        doc = (obj.get("data") or {}).get("document") or obj.get("document") or obj
        if isinstance(doc, dict) and isinstance(doc.get("content"), str):
            return doc["content"]
    raise Stop(f"{path} 读不懂：既不是 docs +fetch 的输出，也不是文档正文。")


def state_from_doc(content):
    blocks = re.findall(r"<pre\b[^>]*>\s*<code\b[^>]*>(.*?)</code>\s*</pre>", content, re.S)
    if blocks:
        blocks = [html.unescape(re.sub(r"<[^>]+>", "", re.sub(r"<br\s*/?>", "\n", b))) for b in blocks]
    else:
        blocks = re.findall(r"(?m)^```[^\n]*\n(.*?)\n```", content, re.S)
    lines = [ln.strip() for b in blocks for ln in b.split("\n") if ln.strip()]
    start = next((i for i, ln in enumerate(lines) if ln.startswith('{"' + STATE_TAG + '"')), None)
    if start is None:
        raise Stop("这份文档里找不到机器状态：不是状态文档，或者被改过。")
    try:
        header = json.loads(lines[start])
        want = int(header["lines"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        raise Stop("状态文档的开头一行读不懂，不用它。")
    body = lines[start + 1:start + 1 + want]
    digest = hashlib.sha256("\n".join(body).encode("utf-8")).hexdigest()
    if len(body) != want or digest != header.get("sha256"):
        raise Stop(f"状态文档读回来对不上（第 {header.get('seq')} 份应有 {want} 行，读到 {len(body)} 行，"
                   f"校验{'一致' if digest == header.get('sha256') else '不一致'}）：被手改过或者没写全，不用它。")
    return header, body


def state_summary(cfg, st, today):
    rows, _ = eligible_clusters(cfg, st, today)
    open_d = [d for d in read_jsonl(H("disputes.jsonl")) if d["status"] == "open"]
    s = [f"第 {st['state_seq']} 份，{today} 存的。{mode_label(cfg, st, today)}。",
         f"现用细则 {st['published']['release']}（{st['published']['date']}），锚点 {st['anchor']}"
         + (f"，预发布 {st['rc']['id']}（{st['rc']['cluster']}）等复测" if st.get("rc") else "") + "。",
         f"待你判断 {len(open_d)} 条，作者交代 {len(active_notes())} 条。"]
    if rows:
        s.append("问题池：" + "，".join(f"{r['cluster']} {r['count']} 条（{cluster_tag(r, today)}）" for r in rows[:6]) + "。")
    if st.get("last"):
        s.append(f"最近一次：{st['last']['date']} · {st['last']['headline']}")
    return s


__all__ = [
    "state_files", "doc_safe", "flatten", "state_body", "get_at", "put_at", "safe_rel", "unflatten",
    "free_path", "install_state", "esc", "para", "bullets", "clip", "rules_xml", "state_header",
    "state_doc_xml", "doc_content", "state_from_doc", "state_summary",
]
