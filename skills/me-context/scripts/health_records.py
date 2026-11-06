"""Loss-aware health record parsing. Local data only; no diagnosis or file writes.

Canonical writes use one measurement per line. Legacy combined/prose lines are
read compatibly without fabricating numeric values or silently treating unknowns
as normal. raw_value/raw_ref/raw_line preserve the evidence being interpreted.
"""
import math
import re

NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
LABELS = {
    "systolic": "收缩压", "diastolic": "舒张压", "weight": "体重", "height": "身高",
    "bmi": "BMI", "waist": "腰围", "ua": "尿酸", "tg": "甘油三酯",
    "tc": "总胆固醇", "ldl_c": "低密度脂蛋白 LDL-C", "hdl_c": "高密度脂蛋白 HDL-C",
    "fpg": "空腹血糖", "hba1c": "糖化血红蛋白", "alt": "谷丙转氨酶 ALT",
    "ast": "谷草转氨酶 AST", "creatinine": "肌酐", "egfr": "肾小球滤过率 eGFR",
    "ck": "肌酸激酶 CK", "urine_rbc": "尿红细胞", "urine_protein": "尿蛋白",
    "urine_occult": "尿隐血", "stool_occult": "大便潜血", "tba": "总胆汁酸",
    "ggt": "谷氨酰转肽酶 GGT", "hcy": "同型半胱氨酸", "hs_crp": "超敏C反应蛋白",
}
ALIASES = {k: k for k in LABELS}
ALIASES.update({
    "尿酸": "ua", "uricacid": "ua", "甘油三酯": "tg", "triglyceride": "tg", "triglycerides": "tg",
    "总胆固醇": "tc", "cholesterol": "tc", "totalcholesterol": "tc", "ldl": "ldl_c", "ldl-c": "ldl_c",
    "hdl": "hdl_c", "hdl-c": "hdl_c", "hdl-c": "hdl_c", "hdlcholesterol": "hdl_c",
    "ldl-c": "ldl_c", "ldlcholesterol": "ldl_c",
    "低密度脂蛋白": "ldl_c", "高密度脂蛋白": "hdl_c",
    "空腹血糖": "fpg", "葡萄糖": "fpg", "糖化血红蛋白a1c": "hba1c", "糖化血红蛋白": "hba1c",
    "谷丙转氨酶": "alt", "谷草转氨酶": "ast", "肌酐": "creatinine", "肾小球滤过率": "egfr",
    "磷酸肌酸激酶": "ck", "肌酸激酶": "ck", "sbp": "systolic", "dbp": "diastolic",
    "收缩压": "systolic", "舒张压": "diastolic", "体重": "weight", "身高": "height",
    "体重指数": "bmi", "腹围": "waist", "腰围": "waist", "尿红细胞": "urine_rbc",
    "尿蛋白": "urine_protein", "尿隐血": "urine_occult", "总胆汁酸": "tba", "同型半胱氨酸": "hcy",
    "hs-crp": "hs_crp", "血压": "systolic/diastolic",
})
COMBINED = {
    "sbp/dbp": ["systolic", "diastolic"], "systolic/diastolic": ["systolic", "diastolic"],
    "weight/bmi/waist": ["weight", "bmi", "waist"], "alt/ast": ["alt", "ast"],
    "尿红细胞/尿蛋白/尿隐血": ["urine_rbc", "urine_protein", "urine_occult"],
}
ABNORMAL = {"偏高", "偏低", "阳性", "临界", "异常"}
DATE = r"\d{4}[-./]\d{1,2}[-./]\d{1,2}"


def canonical(name):
    n = re.sub(r"[（(].*?[）)]", "", str(name or "")).strip().lower().replace(" ", "")
    return ALIASES.get(n, n)  # unknown names remain visible, never discarded


def numeric(raw):
    s = str(raw or "").strip()
    # <5 is a bound, ++(80) is semiquantitative; neither is an exact number.
    m = re.fullmatch(r"(" + NUMBER + r")(?:\s*[↑↓])?", s)
    if not m:
        return None
    n = float(m.group(1))
    return n if math.isfinite(n) else None


def reference(ref):
    """Return (low, high, low_inclusive, high_inclusive) or None. No threshold invention."""
    s = re.sub(r"[（(].*?[）)]", "", str(ref or "")).strip()
    if re.search(r"[/、,，]", s):  # an unsplit combined reference is ambiguous
        return None
    s = re.sub(r"^(?:BMI|男(?:性)?(?:腹围|腰围)|女(?:性)?(?:腹围|腰围))\s*", "", s, flags=re.I)
    m = re.fullmatch(r"(" + NUMBER + r")\s*[-~～–—]\s*(" + NUMBER + r")", s)
    if m:
        lo, hi = map(float, m.groups())
        return (lo, hi, True, True) if lo <= hi else None
    m = re.fullmatch(r"(<=|>=|≤|≥|<|>)\s*(" + NUMBER + r")", s)
    if m:
        op, v = m.group(1), float(m.group(2))
        return (None, v, True, op in ("<=", "≤")) if op in ("<", "<=", "≤") else (v, None, op in (">=", "≥"), True)
    return None


def status(row):
    raw = str(row.get("raw_value", row.get("qualitative", row.get("value", "")))).strip()
    value = row.get("value")
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        rr = reference(row.get("ref", ""))
        if rr:
            lo, hi, li, ui = rr
            if lo is not None and (value < lo or (value == lo and not li)):
                return "偏低"
            if hi is not None and (value > hi or (value == hi and not ui)):
                return "偏高"
            return "正常"
    # Source flag is useful even if the printed range is unavailable.
    flag = str(row.get("flag", ""))
    if "↑" in raw or flag in ("H", "high", "偏高", "↑"):
        return "偏高"
    if "↓" in raw or flag in ("L", "low", "偏低", "↓"):
        return "偏低"
    core = re.sub(r"[（(].*?[）)]", "", raw).strip()
    if "±" in core or core in ("+-", "+-.", "弱阳性", "可疑阳性"):
        return "临界"
    if re.fullmatch(r"[+＋]+\.?", core) or core == "阳性":
        return "阳性"
    if core in ("阴性", "未查见", "未检出", "-", "(-)", "（-）"):
        return "正常"
    if any(x in str(row.get("ref", "")) for x in ("报告未标异常", "随目标跟踪")):
        return "参考"
    if not reference(row.get("ref", "")):
        if "↑" in str(row.get("ref", "")):
            return "偏高"
        if "↓" in str(row.get("ref", "")):
            return "偏低"
    return "待核对"


def _split_values(s, count):
    values = re.split(r"\s*/\s*|、", s)
    return values if len(values) == count else [s] + [""] * (count - 1)


def _units(s, count):
    if "、" in s:
        parts = s.split("、")
    else:
        # Do not split the slash in mmol/L, U/L, /μl or Ery/μl.
        parts = re.split(r"\s+/\s+", s)
    if len(parts) == count:
        return [p.strip() for p in parts]
    if len(parts) == 1:
        return [s.strip()] * count
    return [""] * count


def _refs(s, names):
    parts = re.split(r"、|，|\s+/\s+", s)
    if names == ["weight", "bmi", "waist"]:
        out = ["", "", ""]
        for part in parts:
            if "bmi" in part.lower():
                out[1] = part.strip()
            elif "围" in part:
                out[2] = part.strip()
            elif "体重" in part:
                out[0] = part.strip()
        return out
    if len(parts) == len(names):
        return [p.strip() for p in parts]
    if len(parts) == 1:
        return [s.strip()] * len(names)
    return [""] * len(names)


def make_row(name, raw, unit="", ref="", meta=None, raw_line=""):
    meta = dict(meta or {})
    n = numeric(raw)
    d = re.search(DATE, str(meta.get("date", "")))
    return dict(meta, name=canonical(name), value=n, raw_value=str(raw).strip(), unit=unit.strip(),
                ref=ref.strip(), raw_ref=ref, raw_line=raw_line,
                date=d.group().replace("/", "-").replace(".", "-") if d else "",
                qualitative=str(raw).strip() if n is None else "")


def metric_rows(section_text, defaults=None):
    rows = []
    for line in section_text.splitlines():
        m = re.match(r"\s*-\s*(?:指标|analyte)\s+(.+)", line)
        if not m:
            continue
        cells = [s.strip() for s in m.group(1).split("|")]
        name = cells[0]
        kv = {}
        for cell in cells[1:]:
            pair = cell.split(None, 1)
            if len(pair) == 2:
                kv[pair[0]] = pair[1]
        raw = kv.get("数值", kv.get("value", ""))
        if not raw or raw.startswith("<例") or raw == "<v>":
            continue
        meta = dict(defaults or {})
        for source, dest in (("日期", "date"), ("机构", "lab"), ("方法", "method"),
                             ("采血条件", "preconditions"), ("provenance", "provenance"),
                             ("confidence", "confidence"), ("标记", "flag"), ("标本", "specimen")):
            if kv.get(source):
                meta[dest] = kv[source]
        key = re.sub(r"\s+", "", name.lower())
        names = COMBINED.get(key, [canonical(name)])
        values = _split_values(raw, len(names)) if len(names) > 1 else [raw]
        units = _units(kv.get("单位", ""), len(names))
        refs = _refs(kv.get("参考", ""), names)
        for n, v, u, ref in zip(names, values, units, refs):
            if v.strip():
                rows.append(make_row(n, v, u, ref, meta, line))
    return rows


def heading_meta(heading):
    meta = {"date": "", "lab": "", "method": "", "preconditions": "", "provenance": "", "confidence": ""}
    d = re.search(DATE, heading)
    if d:
        meta["date"] = d.group().replace("/", "-").replace(".", "-")
        suffix = heading[d.end():].lstrip(" ，,(（")
        lab = re.split(r"[，,（(]", suffix, maxsplit=1)[0].strip()
        if lab and not any(x in lab for x in ("空腹", "方法", "provenance")):
            meta["lab"] = lab
    if "imported_report" in heading:
        meta["provenance"] = "imported_report"
    if "confirmed" in heading:
        meta["confidence"] = "confirmed"
    if "空腹" in heading:
        meta["preconditions"] = "空腹（章节说明）"
    return meta


def _legacy_rows(text, meta, unit_index):
    """Read a narrow legacy prose grammar; only the value immediately after an explicit analyte.
    Missing units may use an explicit unit from the same analyte's latest row, marked
    as inherited, and therefore never obtain high comparison confidence.
    """
    rows = []
    alias_pattern = "|".join(re.escape(a) for a in sorted(ALIASES, key=len, reverse=True))
    prefix = re.compile(r"^\s*(" + alias_pattern + r")\s*[:：]?\s*(.*)$", re.I)
    for line in text.splitlines():
        if not line.lstrip().startswith("-") or re.match(r"\s*-\s*指标\s", line):
            continue
        content = line.lstrip("- ")
        # Legacy prose may introduce a urine group after other analytes on the same line.
        content = re.sub(r"([；;])\s*尿[：:]\s*(?:潜血|隐血)?\s*", r"\1尿隐血 ", content)
        for piece in re.split(r"[；;、]|\s+/\s+", content):
            piece = piece.strip()
            piece = re.sub(r"^(?:潜血|隐血)\s*", "尿隐血 ", piece)
            piece = re.sub(r"^(?:镜检红细胞|红细胞)\s*", "尿红细胞 ", piece)
            piece = re.sub(r"^蛋白", "尿蛋白 ", piece)
            hit = prefix.match(piece)
            if not hit:
                continue
            name, tail = canonical(hit.group(1)), hit.group(2)
            if name == "systolic/diastolic":
                bp = re.match(r"(\d+)\s*/\s*(\d+)", tail)
                if bp:
                    for n, v in zip(("systolic", "diastolic"), bp.groups()):
                        r = make_row(n, v, unit_index.get(n, ""), "", meta, line)
                        r["unit_inferred"] = True
                        rows.append(r)
                continue
            value_match = re.match(r"(±(?:[（(][^）)]*[）)])?|[+＋]+(?:[（(][^）)]*[）)])?|阴性|(" + NUMBER + r")[↑↓]?)", tail)
            if not value_match:
                continue
            raw = value_match.group(1)
            suffix = tail[value_match.end():]
            unit_match = re.match(r"\s*(kg|cm|mmHg|mmol/L|[μµu]mol/L|mg/dL|U/L|ml/min|%|g/L|/μl|/HP)", suffix, re.I)
            unit = unit_match.group().strip() if unit_match else unit_index.get(name, "")
            ref_match = re.search(r"[（(]([^）)]+)[）)]", suffix)
            ref = ref_match.group(1) if ref_match and reference(ref_match.group(1)) is not None else ""
            if name == "urine_rbc" and "/HP" in piece:
                unit = "/HP"
            r = make_row(name, raw, unit, ref, meta, line)
            if "↑" in raw:
                r["flag"] = "↑"
            elif "↓" in raw:
                r["flag"] = "↓"
            r["legacy"] = True
            r["unit_inferred"] = not bool(unit_match)
            rows.append(r)
    return rows


def sections(body):
    latest, hist = [], []
    blocks = list(re.finditer(r"^##\s+([^\n]+)\n(.*?)(?=^##\s|\Z)", body, re.M | re.S))
    for b in blocks:
        if b.group(1).startswith("最新关键指标"):
            latest.extend(metric_rows(b.group(2), heading_meta(b.group(1))))
    unit_index = {r["name"]: r["unit"] for r in latest if r["unit"]}
    for b in blocks:
        if not b.group(1).startswith("历史快照"):
            continue
        text = b.group(2)
        snapshots = list(re.finditer(r"^###\s+([^\n]+)\n(.*?)(?=^###\s|\Z)", text, re.M | re.S))
        parts = [(s.group(2), heading_meta(s.group(1))) for s in snapshots] or [(text, {})]
        for txt, meta in parts:
            hist.extend(metric_rows(txt, meta))
            hist.extend(_legacy_rows(txt, meta, unit_index))
    return latest, hist
