#!/usr/bin/env python3
"""token_utils.py：tokens.json 的读取、校验、字体栈拼装和颜色计算。

export_tokens.py、lint_design.py、design_memory.py 共用。只用标准库。
"""

from __future__ import annotations

import json
import math
import re
from typing import Dict, Iterator, List, Optional, Tuple

RGBA = Tuple[float, float, float, float]

REQUIRED_COLORS = ("bg", "surface", "text", "text_muted", "accent", "border")

# 简体/繁体中文字体。日文、韩文字体的汉字字形不同，不算中文回退。
CJK_FAMILIES = {
    "pingfang sc", "pingfang tc", "pingfang hk", "hiragino sans gb",
    "microsoft yahei", "microsoft yahei ui", "微软雅黑", "microsoft jhenghei",
    "noto sans sc", "noto sans tc", "noto sans hk", "noto sans cjk sc", "noto sans cjk tc",
    "noto serif sc", "noto serif tc", "noto serif cjk sc",
    "source han sans sc", "source han sans cn", "source han sans tc", "source han sans", "思源黑体",
    "source han serif sc", "source han serif cn", "source han serif tc", "source han serif", "思源宋体",
    "songti sc", "stsong", "simsun", "宋体", "nsimsun", "heiti sc", "stheiti", "黑体", "simhei",
    "kaiti sc", "stkaiti", "kaiti", "楷体", "fangsong", "stfangsong", "仿宋",
    "harmonyos sans sc", "harmonyos sans", "misans", "misans vf",
    "alibaba puhuiti", "alibaba puhuiti 2.0", "alibaba puhuiti 3.0", "阿里巴巴普惠体",
    "oppo sans", "oppo sans 4.0", "vivo sans", "honor sans",
    "lxgw wenkai", "lxgw wenkai screen", "霞鹜文楷", "smiley sans", "得意黑",
    "wenquanyi micro hei", "文泉驿微米黑", "wenquanyi zen hei", "文泉驿正黑",
}
GENERIC_FAMILIES = {
    "serif", "sans-serif", "monospace", "cursive", "fantasy", "system-ui", "ui-sans-serif",
    "ui-serif", "ui-monospace", "ui-rounded", "emoji", "math", "-apple-system", "blinkmacsystemfont",
}
# Anthropic frontend-design 点名的"用滥了的字体"。
OVERUSED_FONTS = {"inter", "roboto", "arial", "open sans", "helvetica", "helvetica neue"}
# impeccable 列出的训练数据高频字体：不是禁用，是"选它要有别的字体给不了的理由"。
TRAINING_DEFAULT_FONTS = {
    "fraunces", "playfair display", "cormorant", "cormorant garamond", "lora", "crimson pro",
    "crimson text", "newsreader", "syne", "space grotesk", "space mono", "ibm plex sans",
    "ibm plex serif", "ibm plex mono", "dm sans", "dm serif display", "dm serif text", "outfit",
    "plus jakarta sans", "instrument sans", "instrument serif",
}

NAMED_COLORS = {
    "white": (255, 255, 255), "black": (0, 0, 0), "red": (255, 0, 0), "green": (0, 128, 0),
    "blue": (0, 0, 255), "yellow": (255, 255, 0), "orange": (255, 165, 0),
    "purple": (128, 0, 128), "violet": (238, 130, 238), "indigo": (75, 0, 130),
    "pink": (255, 192, 203), "gray": (128, 128, 128), "grey": (128, 128, 128),
    "silver": (192, 192, 192), "navy": (0, 0, 128), "teal": (0, 128, 128),
    "magenta": (255, 0, 255), "fuchsia": (255, 0, 255), "cyan": (0, 255, 255),
    "aqua": (0, 255, 255), "lime": (0, 255, 0), "maroon": (128, 0, 0), "olive": (128, 128, 0),
    "brown": (165, 42, 42), "gold": (255, 215, 0), "coral": (255, 127, 80),
    "tomato": (255, 99, 71), "crimson": (220, 20, 60), "royalblue": (65, 105, 225),
    "slateblue": (106, 90, 205), "mediumpurple": (147, 112, 219), "blueviolet": (138, 43, 226),
    "rebeccapurple": (102, 51, 153), "whitesmoke": (245, 245, 245), "gainsboro": (220, 220, 220),
    "lightgray": (211, 211, 211), "lightgrey": (211, 211, 211), "darkgray": (169, 169, 169),
    "darkgrey": (169, 169, 169), "dimgray": (105, 105, 105), "dimgrey": (105, 105, 105),
}
IGNORED_COLOR_WORDS = {"transparent", "currentcolor", "inherit", "initial", "unset", "revert", "none"}

_HEX_RE = re.compile(r"#([0-9a-fA-F]{3,8})(?![0-9a-zA-Z_-])")
_FUNC_RE = re.compile(r"\b(rgba?|hsla?|oklch|oklab)\(\s*([^()]*)\)", re.I)
_WORD_RE = re.compile(r"(?<![\w#-])([a-zA-Z]+)(?![\w-])")


class TokenError(Exception):
    """tokens.json 无法读取或结构不对。"""


# ---------- 颜色 ----------

def parse_hex(text: str) -> Optional[RGBA]:
    m = re.fullmatch(r"#?([0-9a-fA-F]{3,8})", (text or "").strip())
    if not m:
        return None
    h = m.group(1)
    if len(h) in (3, 4):
        h = "".join(c * 2 for c in h)
    if len(h) not in (6, 8):
        return None
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    a = int(h[6:8], 16) / 255 if len(h) == 8 else 1.0
    return (float(r), float(g), float(b), a)


def _num(token: str, scale: float = 1.0, percent_of: float = 100.0) -> float:
    token = token.strip()
    if token.endswith("%"):
        return float(token[:-1]) / 100 * percent_of
    if token.endswith("deg"):
        return float(token[:-3])
    return float(token) * scale


def _split_args(body: str) -> Tuple[List[str], Optional[str]]:
    body = body.replace(",", " ")
    alpha = None
    if "/" in body:
        body, alpha = body.split("/", 1)
    return body.split(), (alpha.strip() if alpha else None)


def _hsl_to_rgb(h: float, s: float, l: float) -> Tuple[float, float, float]:
    h = (h % 360) / 360
    if s == 0:
        v = l * 255
        return v, v, v

    def hue(p, q, t):
        t %= 1
        if t < 1 / 6:
            return p + (q - p) * 6 * t
        if t < 1 / 2:
            return q
        if t < 2 / 3:
            return p + (q - p) * (2 / 3 - t) * 6
        return p

    q = l * (1 + s) if l < 0.5 else l + s - l * s
    p = 2 * l - q
    return hue(p, q, h + 1 / 3) * 255, hue(p, q, h) * 255, hue(p, q, h - 1 / 3) * 255


def parse_func_color(name: str, body: str) -> Optional[RGBA]:
    name = name.lower()
    args, alpha_token = _split_args(body)
    try:
        if name in ("rgb", "rgba"):
            if len(args) == 4 and alpha_token is None:
                args, alpha_token = args[:3], args[3]
            if len(args) != 3:
                return None
            r, g, b = (_num(a, percent_of=255) for a in args)
            rgb = (r, g, b)
        elif name in ("hsl", "hsla"):
            if len(args) == 4 and alpha_token is None:
                args, alpha_token = args[:3], args[3]
            if len(args) != 3:
                return None
            h = _num(args[0])
            s = _num(args[1], percent_of=1)
            l = _num(args[2], percent_of=1)
            s = s / 100 if not args[1].endswith("%") and s > 1 else s
            l = l / 100 if not args[2].endswith("%") and l > 1 else l
            rgb = _hsl_to_rgb(h, s, l)
        elif name == "oklch":
            if len(args) != 3:
                return None
            L = _num(args[0], percent_of=1)
            C = _num(args[1], percent_of=0.4)
            H = math.radians(_num(args[2]))
            rgb = oklab_to_rgb(L, C * math.cos(H), C * math.sin(H))
        else:  # oklab
            if len(args) != 3:
                return None
            L = _num(args[0], percent_of=1)
            rgb = oklab_to_rgb(L, _num(args[1], percent_of=0.4), _num(args[2], percent_of=0.4))
        alpha = 1.0 if alpha_token is None else _num(alpha_token, percent_of=1)
    except ValueError:
        return None
    r, g, b = (min(255.0, max(0.0, v)) for v in rgb)
    return (r, g, b, min(1.0, max(0.0, alpha)))


def parse_color(text: str) -> Optional[RGBA]:
    text = (text or "").strip()
    if text.startswith("#"):
        return parse_hex(text)
    m = _FUNC_RE.fullmatch(text)
    if m:
        return parse_func_color(m.group(1), m.group(2))
    named = NAMED_COLORS.get(text.lower())
    if named:
        return (float(named[0]), float(named[1]), float(named[2]), 1.0)
    return None


def iter_colors(value: str, include_named: bool = True) -> Iterator[Tuple[str, RGBA, int]]:
    """逐个找出 CSS 值里的颜色字面量，返回 (原文, rgba, 偏移)。var() 不算字面量。"""
    stripped = re.sub(r"var\([^()]*\)", lambda m: " " * len(m.group(0)), value)
    stripped = re.sub(r"url\([^()]*\)", lambda m: " " * len(m.group(0)), stripped)
    for m in _HEX_RE.finditer(stripped):
        rgba = parse_hex(m.group(0))
        if rgba:
            yield m.group(0), rgba, m.start()
    for m in _FUNC_RE.finditer(stripped):
        rgba = parse_func_color(m.group(1), m.group(2))
        if rgba:
            yield m.group(0), rgba, m.start()
    if include_named:
        blanked = _FUNC_RE.sub(lambda m: " " * len(m.group(0)), stripped)
        for m in _WORD_RE.finditer(blanked):
            word = m.group(1).lower()
            if word in NAMED_COLORS:
                r, g, b = NAMED_COLORS[word]
                yield m.group(1), (float(r), float(g), float(b), 1.0), m.start()


def to_hex(rgba: RGBA) -> str:
    return "#{:02X}{:02X}{:02X}".format(*(int(round(v)) for v in rgba[:3]))


def _lin(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _gamma(c: float) -> float:
    c = min(1.0, max(0.0, c))
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def rgb_to_oklab(rgba: RGBA) -> Tuple[float, float, float]:
    r, g, b = (_lin(v / 255) for v in rgba[:3])
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l_, m_, s_ = (math.copysign(abs(x) ** (1 / 3), x) for x in (l, m, s))
    return (
        0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
        1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
        0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_,
    )


def oklab_to_rgb(L: float, a: float, b: float) -> Tuple[float, float, float]:
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_ ** 3, m_ ** 3, s_ ** 3
    r = 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
    g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
    bb = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s
    return _gamma(r) * 255, _gamma(g) * 255, _gamma(bb) * 255


def oklch(rgba: RGBA) -> Tuple[float, float, float]:
    """返回 (明度 0..1, 彩度, 色相角)。"""
    L, a, b = rgb_to_oklab(rgba)
    return L, math.hypot(a, b), math.degrees(math.atan2(b, a)) % 360


def delta_e(c1: RGBA, c2: RGBA) -> float:
    """OKLab 距离乘 100。约 2 以下肉眼难分。"""
    a, b = rgb_to_oklab(c1), rgb_to_oklab(c2)
    return math.dist(a, b) * 100


def hue_distance(h1: float, h2: float) -> float:
    d = abs(h1 - h2) % 360
    return min(d, 360 - d)


def composite(fg: RGBA, bg: RGBA) -> RGBA:
    a = fg[3]
    return (
        fg[0] * a + bg[0] * (1 - a),
        fg[1] * a + bg[1] * (1 - a),
        fg[2] * a + bg[2] * (1 - a),
        1.0,
    )


def relative_luminance(rgba: RGBA) -> float:
    r, g, b = (_lin(v / 255) for v in rgba[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg: RGBA, bg: RGBA) -> float:
    if fg[3] < 1:
        fg = composite(fg, bg)
    l1, l2 = relative_luminance(fg), relative_luminance(bg)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def is_grayish(rgba: RGBA, max_chroma: float = 0.025) -> bool:
    return oklch(rgba)[1] <= max_chroma


# ---------- 字体 ----------

def split_families(stack: str) -> List[str]:
    families = []
    for part in re.split(r",(?=(?:[^'\"]*['\"][^'\"]*['\"])*[^'\"]*$)", stack or ""):
        name = part.strip().strip("'\"").strip()
        if name:
            families.append(name)
    return families


def has_cjk_family(families: List[str]) -> bool:
    return any(f.lower() in CJK_FAMILIES for f in families)


def first_named_family(families: List[str]) -> Optional[str]:
    for f in families:
        if f.lower() not in GENERIC_FAMILIES:
            return f
    return None


def font_stack(tokens: dict, role: str) -> str:
    """拼出某个角色的完整字体栈。显式 *_font 优先；否则拉丁字体在前、中文字体在后。"""
    typ = tokens.get("typography", {}) or {}
    explicit = typ.get(f"{role}_font")
    if explicit:
        return str(explicit)
    latin = str(typ.get(f"latin_{role}") or "").strip().rstrip(",")
    if role == "mono":
        stack = latin or "ui-monospace, 'SF Mono', Menlo, Consolas"
        cjk = str(typ.get("cjk_sans") or "").strip().rstrip(",")
        if cjk and not has_cjk_family(split_families(stack)):
            stack = f"{stack}, {cjk}"
        if "monospace" not in [f.lower() for f in split_families(stack)]:
            stack = f"{stack}, monospace"
        return stack
    serif = typ.get(f"{role}_cjk") == "serif"
    cjk = str(typ.get("cjk_serif" if serif else "cjk_sans") or "").strip().rstrip(",")
    generic = "serif" if serif else "sans-serif"
    parts = [p for p in (latin, cjk) if p]
    stack = ", ".join(parts)
    families = [f.lower() for f in split_families(stack)]
    if generic not in families:
        stack = f"{stack}, {generic}" if stack else generic
    return stack


def line_heights(tokens: dict) -> Dict[str, float]:
    lh = (tokens.get("typography", {}) or {}).get("line_height")
    if isinstance(lh, (int, float)):
        return {"base": float(lh)}
    if isinstance(lh, dict):
        return {k: float(v) for k, v in lh.items() if isinstance(v, (int, float))}
    return {}


def is_cjk(tokens: dict) -> bool:
    locale = tokens.get("locale", {}) or {}
    if locale.get("cjk") is True:
        return True
    lang = str(locale.get("lang", "")).lower()
    return lang.startswith(("zh", "ja", "ko"))


# ---------- 读取与校验 ----------

def load_tokens(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        raise TokenError(f"找不到 tokens 文件：{path}") from None
    except json.JSONDecodeError as e:
        raise TokenError(f"{path} 不是合法 JSON：第 {e.lineno} 行第 {e.colno} 列，{e.msg}") from None
    if not isinstance(data, dict):
        raise TokenError(f"{path} 顶层必须是对象")
    return data


def token_colors(tokens: dict) -> Dict[str, RGBA]:
    result = {}
    for key, value in (tokens.get("color", {}) or {}).items():
        rgba = parse_hex(value) if isinstance(value, str) else None
        if rgba:
            result[key] = rgba
    return result


def _finding(severity: str, rule: str, message: str, where: str = "tokens") -> dict:
    return {"severity": severity, "rule": rule, "message": message, "where": where}


def _check_numbers(group: dict, label: str, findings: List[dict], minimum: float = 0) -> None:
    for key, value in group.items():
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value < minimum:
            findings.append(_finding("error", "TOKENS-NUMBER", f"{label}.{key} 必须是不小于 {minimum} 的数字：{value!r}"))


def validate_tokens(tokens: dict) -> List[dict]:
    """检查 tokens 结构、对比度和中文字体。error 会让导出失败，warn 和 info 只提示。"""
    findings: List[dict] = []
    color = tokens.get("color")
    if not isinstance(color, dict) or not color:
        findings.append(_finding("error", "TOKENS-COLOR", "缺少 color 对象"))
        color = {}
    for key, value in color.items():
        if not isinstance(value, str) or parse_hex(value) is None or parse_hex(value)[3] < 1:
            findings.append(_finding("error", "TOKENS-COLOR", f"color.{key} 必须是不透明的 #RRGGBB：{value!r}"))
    missing = [role for role in REQUIRED_COLORS if role not in color]
    if color and missing:
        findings.append(_finding("warn", "TOKENS-ROLES", "color 缺少常用角色：" + ", ".join(missing)))

    typ = tokens.get("typography", {})
    if not isinstance(typ, dict):
        findings.append(_finding("error", "TOKENS-TYPE", "typography 必须是对象"))
        typ = {}
    scale = typ.get("scale", {})
    if isinstance(scale, dict):
        _check_numbers(scale, "typography.scale", findings, minimum=1)
    else:
        findings.append(_finding("error", "TOKENS-TYPE", "typography.scale 必须是对象"))
    for role, value in line_heights(tokens).items():
        if not 0.8 <= value <= 3:
            findings.append(_finding("error", "TOKENS-LEADING", f"typography.line_height.{role} 应在 0.8 到 3 之间：{value}"))
    for group in ("radius", "spacing"):
        value = tokens.get(group, {})
        if isinstance(value, dict):
            _check_numbers(value, group, findings)
        else:
            findings.append(_finding("error", "TOKENS-NUMBER", f"{group} 必须是对象"))
    motion = tokens.get("motion", {}) or {}
    _check_numbers({k: v for k, v in motion.items() if k.startswith("duration")}, "motion", findings)

    colors = token_colors(tokens)
    pairs = [("text", "bg", 4.5), ("text", "surface", 4.5), ("text_muted", "bg", 4.5),
             ("text_muted", "surface", 4.5), ("on_accent", "accent", 4.5)]
    for fg, bg, need in pairs:
        if fg in colors and bg in colors:
            ratio = contrast_ratio(colors[fg], colors[bg])
            if ratio < need:
                findings.append(_finding("warn", "TOKENS-CONTRAST",
                                         f"{fg} 在 {bg} 上对比度 {ratio:.2f}:1，正文需要至少 {need}:1（WCAG 1.4.3）"))
    if "accent" in colors and "bg" in colors:
        ratio = contrast_ratio(colors["accent"], colors["bg"])
        if ratio < 3:
            findings.append(_finding("info", "TOKENS-CONTRAST",
                                     f"accent 在 bg 上只有 {ratio:.2f}:1；用作文字或图标时达不到 3:1（WCAG 1.4.11）"))
    if "on_accent" not in colors and "accent" in colors:
        best = max((255, 255, 255, 1.0), (0, 0, 0, 1.0), key=lambda c: contrast_ratio(c, colors["accent"]))
        ratio = contrast_ratio(best, colors["accent"])
        if ratio < 4.5:
            findings.append(_finding("warn", "TOKENS-CONTRAST",
                                     f"accent 上放白字或黑字最多 {ratio:.2f}:1；主按钮文字会看不清，补 on_accent 或调整 accent"))

    if is_cjk(tokens):
        for role in ("heading", "body"):
            families = split_families(font_stack(tokens, role))
            if not has_cjk_family(families):
                findings.append(_finding("warn", "TOKENS-CJK-FONT",
                                         f"{role} 字体栈里没有中文字体，中文会落到浏览器默认字体：{font_stack(tokens, role)}"))
        body_lh = line_heights(tokens).get("body", line_heights(tokens).get("base"))
        if body_lh is not None and body_lh < 1.5:
            findings.append(_finding("warn", "TOKENS-CJK-LEADING",
                                     f"中文正文行高 {body_lh} 偏紧；clreq 建议 1.5 到 2.0"))
        spacing = typ.get("letter_spacing", {}) or {}
        cjk_tracking = spacing.get("cjk") if isinstance(spacing, dict) else None
        if isinstance(cjk_tracking, str) and cjk_tracking.strip().startswith("-"):
            findings.append(_finding("warn", "TOKENS-CJK-TRACKING", f"汉字不要用负字距：letter_spacing.cjk={cjk_tracking}"))
    elif not tokens.get("locale"):
        findings.append(_finding("info", "TOKENS-LOCALE", "没写 locale；中文产品请写 \"locale\": {\"lang\": \"zh-CN\"}"))
    return findings


def accepted_defaults(tokens: Optional[dict]) -> Dict[str, str]:
    """方向明确接受的默认长相：{规则 ID: 理由}。支持字符串 "ID: 理由" 或 {"id", "reason"}。"""
    result: Dict[str, str] = {}
    if not tokens:
        return result
    for item in (tokens.get("guardrails", {}) or {}).get("accepted_defaults", []) or []:
        if isinstance(item, dict) and item.get("id"):
            result[str(item["id"]).strip()] = str(item.get("reason", "")).strip()
        elif isinstance(item, str) and item.strip():
            rule, _, reason = item.partition(":")
            result[rule.strip()] = reason.strip()
    return result
