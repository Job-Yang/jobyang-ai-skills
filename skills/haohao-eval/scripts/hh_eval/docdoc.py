# -*- coding: utf-8 -*-
"""飞书召回文档：解析作者写的判断和交代、生成每天的记录。格式红线：一行没动。"""
import html
import re

from hh_eval.const import (ANSWER_RX, ANSWER_WORDS, BLANK, CODES, NOTES_TITLE, ONLY_RX, SECTION_TITLE, SLOT,
                           SLOT_RX)
from hh_eval.fs import H, load_json, log_author, read_jsonl, write_jsonl
from hh_eval.gates import add_note, answer_dispute, dispute_order, drop_note, mode_label, split_tags
from hh_eval.judge import norm
from hh_eval.rules import release_text, rules_of
from hh_eval.statedoc import bullets, clip, esc, para, rules_xml


def plain(s):
    s = re.sub(r"\\([\\`*_{}\[\]()#+\-.!|>~])", r"\1", s)
    return re.sub(r"\*\*|__|`", "", s).strip()


def doc_lines(content):
    """把飞书文档摊成 (标题级别, 文字) 一行一条，正文的级别是 0。XML 和 Markdown 都认。"""
    t = content.replace("\r\n", "\n")
    if re.search(r"<(?:p|h[1-9])[\s>]", t):
        t = re.sub(r"<h([1-9])\b[^>]*>", lambda m: "\n\x00" + m.group(1) + "\x00", t)
        t = re.sub(r"<li\b[^>]*>", "\n- ", t)
        t = re.sub(r"<br\s*/?>|</?(?:p|h[1-9]|ul|ol|li|div|callout|blockquote|pre|code|table|thead|tbody|tr|td|th"
                   r"|grid|column|title|checkbox)\b[^>]*>", "\n", t)
        t = html.unescape(re.sub(r"<[^>]+>", "", t))
    else:
        t = re.sub(r"(?m)^[ \t]*(#{1,9})[ \t]+", lambda m: "\x00" + str(len(m.group(1))) + "\x00", t)
        t = re.sub(r"<[^>]+>", "", t)
    out = []
    for raw in t.split("\n"):
        s = raw.strip()
        m = re.match(r"\x00(\d)\x00\s*(.*)$", s)
        if m:
            out.append((int(m.group(1)), plain(m.group(2))))
        elif s:
            out.append((0, plain(s)))
    return out


def recall_section(lines):
    tops = [i for i, (lv, _) in enumerate(lines) if lv == 1]
    mine = [i for i in tops if lines[i][1] == SECTION_TITLE]
    if not mine:
        return [], "missing"
    later = [i for i in tops if i > mine[-1]]
    return lines[mine[-1] + 1:later[0] if later else len(lines)], ("not_last" if later else "ok")


def section_notes(sec):
    out, inside = [], False
    for lv, s in sec:
        if lv:
            if lv <= 2:
                inside = lv == 2 and s == NOTES_TITLE
            continue
        t = re.sub(r"^(?:[-*+•·]|\d+[.、)）])\s*", "", s).strip() if inside else ""
        if not t or re.fullmatch(r"[（(].*[)）]", t):
            continue
        m = ONLY_RX.search(t)
        tags = split_tags(m.group(1)) if m else []
        text = (t[:m.start()] + t[m.end():]).strip() if m else t
        if text:
            out.append((text, tags))
    return out


def section_answers(sec, since):
    """since：题号 → 出题日期。状态丢过一天时题号会撞，写在出题日期之前那条记录下面的判断不算。"""
    found, day = {}, ""
    for n, (lv, s) in enumerate(sec):
        if lv:
            if lv <= 2:
                m = re.match(r"\d{4}-\d{2}-\d{2}", s)
                day = m.group(0) if m else ""
            continue
        m = SLOT_RX.search(s)
        if not m or m.group(1).upper() not in since or (day and day < since[m.group(1).upper()]):
            continue
        val = re.sub(r"[＿_]+", "", m.group(2)).strip()
        if re.fullmatch(r"[\s.．。…\-—]*", val):
            nxt = sec[n + 1] if n + 1 < len(sec) else (1, "")
            if nxt[0] or not ANSWER_RX.match(nxt[1]):
                continue
            val = nxt[1]
        found[m.group(1).upper()] = val
    return found


def parse_answer(val):
    m = ANSWER_RX.match(val.strip())
    if not m:
        return None, ""
    return ANSWER_WORDS[m.group(1)], clip(re.sub(r"^[的啊呀吧呢\s,，。.;；:：、!！]+", "", m.group(2)), 300)


def sync_doc_notes(st, doc_notes, today, apply):
    """「你的交代」里的每一行对应一条作者说明：新写的记下，删掉的作废。对话里说的那些不受影响。"""
    rows = read_jsonl(H("notes.jsonl"))
    key = lambda text, tags: norm(text) + "|" + "、".join(sorted(tags))
    active = {key(n["text"], n.get("文体") or []): n for n in rows if n.get("status") == "active"}
    want = {key(t, g): (t, g) for t, g in doc_notes}
    held = {key(n["text"], n.get("文体") or []): n for n in rows if n.get("doc_hold")}
    added = [want[k] for k in want if k not in active and k not in held]
    gone = [n for k, n in active.items() if n.get("来源") == "文档" and k not in want]
    released = [n for k, n in held.items() if k not in want]
    if gone and not want and len(gone) >= 2:
        return [f"「{NOTES_TITLE}」一条都没读到，原来从文档记下的有 {len(gone)} 条，先没动。"
                "要是作者真删了，在对话里确认以后用 note drop 逐条作废。"]
    if not apply:
        return [f"（只看不改）会新记 {len(added)} 条交代、作废 {len(gone)} 条。"] if added or gone else []
    msgs = []
    for t, g in added:
        msgs.append(add_note(st, rows, t, g, today, "文档")[1])
    for n in gone:
        msgs.append(drop_note(n, today))
    for n in released:
        n.pop("doc_hold")
    if msgs or released:
        write_jsonl(H("notes.jsonl"), rows)
        for msg in msgs:
            log_author(today, msg)
    return msgs


def apply_doc_answers(cfg, st, sec, today, apply):
    ds = read_jsonl(H("disputes.jsonl"))
    known = {d["id"].upper(): d for d in ds}
    msgs = []
    for did, val in section_answers(sec, {k: d.get("created", "") for k, d in known.items()}).items():
        d = known[did]
        if d.get("doc_answer") == val:
            continue
        ans, note = parse_answer(val)
        if not ans:
            msgs.append(f"看不懂 {d['id']} 的回答「{clip(val, 60)}」：按回话表理解后用 disputes answer 记下，或者在对话里问作者。")
            continue
        if not apply:
            msgs.append(f"（只看不改）{d['id']} 会记成 {ans}" + (f"（{note}）" if note else ""))
            continue
        d["doc_answer"] = val
        if d["status"] == "answered" and d["answer"] == ans and (d.get("note") or "") == note:
            write_jsonl(H("disputes.jsonl"), ds)
            continue
        extra = answer_dispute(cfg, st, ds, d, ans, note, today)
        msgs.append(f"{d['id']} 记下了：{ans}" + (f"（{note}）" if note else "") + "（写在召回文档里的）")
        if extra:
            msgs.append(extra)
    return msgs


def section_head(cfg):
    days = cfg["disputes"]["default_after_days"]
    return [f"<h1>{SECTION_TITLE}</h1>",
            para("这一节由 Mira 的每日召回任务自动追加，每天一条，最新的在最下面。它只往这一节末尾加内容，文档前面的部分只读不改。"),
            para("你要做的只有两件事，都可以不做："),
            bullets([f"记录里有「待你判断」时，把「Dxx 你的判断：{BLANK}」的横线换成 有 / 没有 / 跳过，后面可以跟一句为什么。"
                     f"不填也行，{days} 天后按默认处理。",
                     f"有长期要它记住的判断标准，写在下面「{NOTES_TITLE}」里，一行一条；只对某些文体生效，就在那一行里写"
                     "（只用于：感谢信、寄语）。删掉一行就是作废那一条。"]),
            para("也可以直接在任务对话里说，效果一样。"),
            f"<h2>{NOTES_TITLE}</h2>",
            bullets(["（一行一条写在这里，这一行不用删）"])]


def rule_changes(release_id, ids):
    rules = {re.match(r"## 细则 (L\d{3})", r).group(1): r for r in rules_of(release_text(release_id))[0]
             if re.match(r"## 细则 (L\d{3})", r)}
    return [rules.get(i) or f"## 细则 {i} · （这一条删掉了）" for i in sorted(ids)]


def record_rules(st, today):
    """今天出的预发布、今天正式发布的细则，只列改动的那几条。"""
    out = []
    rc = st.get("rc")
    if rc and rc["date"] == today:
        meta = load_json(H("releases", rc["id"], "meta.json"), {}) or {}
        out.append((f"候选细则 {rc['id']}（{rc['cluster']}）" + ("，影子期只记录，不会真发布" if rc.get("shadow") else "，明天复测通过就发布")
                    + "，改动的部分：", rule_changes(rc["id"], meta.get("changed") or [])))
    for r in st.get("releases", []):
        if r["date"] == today and r["type"] == "发布":
            meta = load_json(H("releases", r["id"], "meta.json"), {}) or {}
            rcm = load_json(H("releases", meta.get("from_rc") or "", "meta.json"), {}) or {}
            out.append((f"正式发布 {r['id']}（{r['cluster']}），改动的部分：", rule_changes(r["id"], rcm.get("changed") or [])))
    x = []
    for title, rules in out:
        x.append(para(title))
        x.append("<blockquote>" + "".join(rules_xml(rules, lambda t: f"<p><b>{t}</b></p>")) + "</blockquote>")
    return x


def table(headers, rows):
    """飞书表格：表头一行、数据若干行。每个单元格都是转义后的 <p>；
    槽位行（「D12 你的判断：＿＿」）必须独占一个 td 的 <p>，doc read 靠它解析。"""
    x = ["<table><thead><tr>"]
    for h in headers:
        x.append(f"<th><p>{esc(h)}</p></th>")
    x.append("</tr></thead><tbody>")
    for row in rows:
        x.append("<tr>")
        for c in row:
            x.append(f"<td><p>{esc(c) if c is not None else ''}</p></td>")
        x.append("</tr>")
    x.append("</tbody></table>")
    return "".join(x)


def heard_rows(today):
    """今天记下的作者回话拆成 编号 / 内容 两列；编号取开头到第一个空格。"""
    rows = []
    for t in (r["text"] for r in read_jsonl(H("inbox.jsonl")) if r.get("date") == today):
        nid, _, rest = t.partition(" ")
        rows.append((nid, rest.strip("：: ") if rest else t))
    return rows


def record_body(cfg, st, today, dec, stopped):
    if stopped:
        return [f"<h2>{esc(today)} · 今天停下了</h2>", para("原因：" + stopped),
                para("召回的数据没动，明天照常开跑。需要你做什么的话，会在任务对话里单独说。")]
    m, c = dec["metrics"], dec.get("calib") or {}
    x = [f"<h2>{esc(today)} · {esc(clip(dec['headline'], 48))}</h2>"]
    if len(dec["headline"]) > 48:
        x.append(para("结论：" + dec["headline"]))

    # 今天的数据：一张表（不含干净稿份数，干净稿只看误改率）
    if c.get("bad_n") is None:
        calib_txt = "没跑"
    else:
        calib_txt = (("通过" if c.get("pass") else "没过")
                     + f"（已知改坏抓到 {c.get('caught')}/{c.get('bad_n')}，"
                       f"没改坏误报 {c.get('fa')}/{c.get('good_n')}）")
    x.append(para("今天的数据："))
    x.append(table(["实际改写份数", "纳入主指标份数", "改坏", "其中编造", "AI 味残留", "干净稿误改", "裁判体检"],
                  [[m.get("output_n", "历史未统计"), m["n"], m["harm"], m["fab"], m["residue"],
                    f"{m['over_edit']}/{m['clean_n']}", calib_txt]]))

    # 手改稿对照：作者亲手改过的种子，我们当天改写跟上多少（观察项，不进门禁）
    sd = m.get("seed_diff")
    if sd:
        def _cell(k):
            r = sd[k]
            return f"{r['hit']}/{r['n']}" if r["n"] else "无对照句"

        def _rate(k):
            r = sd[k]
            return f"{r['rate']:.0%}" if r["rate"] is not None else "—"
        x.append(para(f"手改稿对照（作者亲手改过的 {sd['n']} 条种子；只做字面核对，不代表学会，不进门禁）："))
        x.append(table(["作者删的·我们也删", "作者原样留的·我们越动", "作者替换的新片段·字面命中"],
                      [[f"{_cell('delete')}（{_rate('delete')}）",
                        f"{_cell('keep')}，越动率 {_rate('keep')}",
                        f"{_cell('edit')}（{_rate('edit')}）" if sd["edit"]["n"] else "无"]]))
        detail = [d for d in (dec.get("seed_diffs") or []) if d.get("跟删") is not None or d.get("越动") is not None]
        if detail:
            rows = []
            for d in detail:
                def _pct(v):
                    return "—" if v is None else f"{v:.0%}"
                rows.append([d["seed"], _pct(d["跟删"]), _pct(d["越动"]),
                             _pct(d["跟改"]) if d.get("跟改") is not None else "—"])
            x.append(table(["种子", "跟删率", "越动率", "跟改率"], rows))

    # 新召回：一张表，最多 6 类，每类一个例子
    rec = sorted((dec.get("recalled") or {}).items(), key=lambda kv: -kv[1])
    x.append(para("新召回（今天发现的问题；同一类攒够数、过了门禁才会改规则）："))
    if rec:
        todays = [e for e in read_jsonl(H("pool.jsonl")) if e.get("run") == today and e.get("kind") != "dispute"]
        rows = []
        for k, n in rec[:6]:
            e = next((e for e in todays if e["cluster"] == k and (e.get("quote_src") or e.get("quote_out"))), None)
            rows.append([
                f"{k}（{CODES.get(k.split('·')[0], k)}）×{n}",
                (e.get("文体") or "—") if e else "—",
                clip(e.get("quote_src"), 120) if e and e.get("quote_src") else "（原句没留住）",
                clip(e.get("quote_out"), 120) if e and e.get("quote_out") else "（改写里没有对应的话）",
                clip(e.get("note"), 160) if e else "—",
            ])
        x.append(table(["类型 × 数量", "文体", "原文", "改成", "裁判为什么算问题"], rows))
    else:
        x.append(para("今天没有召回新问题。"))

    x += [para("动作：" + a) for a in dec.get("actions", [])]
    x += record_rules(st, today)

    # 今天记下的回话：一张表
    heard = heard_rows(today)
    if heard:
        x.append(para("今天记下你的回话："))
        x.append(table(["编号", "内容（原话）"], heard))

    # 待你判断：一张表列全部 open 的；「先看」跟日报口径一致——按争议优先级取前 N 条，
    # 不是只挑今天新问的（今天新出的同类题也可能排在老题后面，标「排队」）
    shown = st.setdefault("doc_shown", {})
    ds_all = sorted([d for d in read_jsonl(H("disputes.jsonl")) if d["status"] == "open"], key=dispute_order)
    first_ids = {d["id"] for d in ds_all if shown.get(d["id"]) is None}
    for d in ds_all:
        if d["id"] in first_ids:
            shown[d["id"]] = today
    top_ids = {d["id"] for d in ds_all[:cfg["disputes"]["max_per_day"]]}
    if ds_all:
        x.append(para(f"待你判断（共 {len(ds_all)} 条。最右一列填 有 / 没有 / 跳过，"
                      f"或者直接在任务对话里说「Dxx 有」也行；不填也可以，出题 {cfg['disputes']['default_after_days']} "
                      "天后按括号里的默认处理；排队的提前判也可以）："))
        rows = []
        for d in ds_all:
            rows.append([
                "先看" if d["id"] in top_ids else "排队",
                d["id"],
                f"{d['kind']} · {d.get('文体') or '—'}",
                clip(d["原文片段"], 120),
                clip(d["改写片段"], 120) or "（改写里没有对应的话）",
                clip(d.get("原因"), 160),
                f"{d['question']}（默认：{d['default']}）",
                f"{d['id']} {SLOT}：{BLANK}",
            ])
        x.append(table(["次序", "题号", "类型 · 文体", "原文", "改写", "拿不准的点",
                       "问你的是非题", "你的判断（有 / 没有 / 跳过）"], rows))
    else:
        x.append(para("今天没有要你判断的。"))

    x += [para("注意：" + n) for n in dec.get("notes", [])]
    return x


__all__ = [
    "plain", "doc_lines", "recall_section", "section_notes", "section_answers", "parse_answer",
    "sync_doc_notes", "apply_doc_answers", "section_head", "rule_changes", "record_rules", "record_body",
    "table", "heard_rows",
]
