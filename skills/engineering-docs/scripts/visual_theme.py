"""Shared visual tokens and legacy views (standard library only).

All base colours live in assets/visual-examples/theme.json. Entity fills,
entity borders, group borders and connectors are deliberately independent.
"""
import json
from pathlib import Path

THEME_PATH = Path(__file__).resolve().parents[1] / "assets/visual-examples/theme.json"
THEME = json.loads(THEME_PATH.read_text(encoding="utf-8"))
DEFAULT_THEME = THEME["name"]
THEME_ALIASES = dict.fromkeys(("default", "warm-cream", "warm", "cream-blue", "cream",
                             "doubao", "vivid", "document-pastel", "v1-review",
                             "v2-magazine", "v3-outline", "v4-dashboard"), DEFAULT_THEME)


def mix_white(color, amount):
    """Mix amount of a colour into paper white, in sRGB channel space."""
    rgb = [int(color[i:i + 2], 16) for i in (1, 3, 5)]
    white = [int(THEME["paper"][i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(w + (c - w) * amount):02X}" for c, w in zip(rgb, white))


def grayscale(color):
    color = color.strip()
    if len(color) == 4:
        color = "#" + "".join(c * 2 for c in color[1:])
    rgb = [int(color[i:i + 2], 16) for i in (1, 3, 5)]
    value = round(sum(c * w for c, w in zip(rgb, (.2126, .7152, .0722))))
    return "#" + f"{value:02X}" * 3


def contrast(a, b):
    def luminance(color):
        rgb = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in rgb]
        return sum(c * w for c, w in zip(linear, (.2126, .7152, .0722)))
    lo, hi = sorted((luminance(a), luminance(b)))
    return (hi + .05) / (lo + .05)


TONE_ALIASES = {
    "blue": "sky", "purple": "lavender", "pink": "rose", "green": "sage",
    "teal": "sage", "orange": "sand", "amber": "sand", "gray": "neutral",
    "strong": "success", "passed": "success", "mid": "warning",
    "red": "error", "weak": "error", "blocked": "error",
}


def _tone(solid, tint, entity_border, plain):
    if plain:
        solid, tint, entity_border = map(grayscale, (solid, tint, entity_border))
    text = solid if contrast(solid, tint) >= 4.5 else grayscale(THEME["ink"]) if plain else THEME["ink"]
    return {"solid": solid, "text": text, "tint": tint,
            "border": solid, "entity_border": entity_border}


def tones(plain=False):
    result = {
        "neutral": _tone(THEME["muted"], THEME["entity_fill"], THEME["entity_border"], plain)
    }
    for name, solid in THEME["semantic"].items():
        result[name] = _tone(solid, THEME["semantic_fill"][name],
                             THEME["semantic_border"][name], plain)
    for name, values in THEME["category"].items():
        result[name] = _tone(values["solid"], values["fill"], values["border"], plain)
    for alias, name in TONE_ALIASES.items():
        result[alias] = dict(result[name])
    return result


def semantic_tone(item=None):
    """Resolve explicit tone/status/emphasis; unknown values stay neutral."""
    item = item if isinstance(item, dict) else {}
    name = item.get("tone") or item.get("status")
    if not name:
        emphasis = item.get("emphasis")
        name = emphasis if isinstance(emphasis, str) else "accent" if emphasis else "neutral"
    available = tones()
    return available.get(name, available["neutral"])


def structural_tone(item=None):
    t = semantic_tone(item)
    if t == tones()["neutral"]:
        return THEME["line"], THEME["panel_bg"]
    return t["border"], t["tint"]


def categorical_tone(index):
    return tuple(THEME["colors"][THEME["sequence"][index % len(THEME["sequence"])]])


def palette(plain=False):
    return {"canvas": THEME["canvas_bg"], **{
        name: {"solid": t["solid"], "ink": t["text"],
               "soft": t["entity_border"], "tint": t["tint"]}
        for name, t in tones(plain).items()}}


def lines(plain=False):
    edge = grayscale(THEME["edge"]) if plain else THEME["edge"]
    accent = tones(plain)["accent"]["solid"]
    warning = tones(plain)["warning"]["solid"]
    return {
        "main": (edge, 1.6, None),
        "normal": (edge, 1.25, None),
        "accent": (accent, 1.6, None),
        "dash": (edge, 1.25, "6 4"),
        "planned": (accent, 1.6, "6 4"),
        "alert": (warning, 1.5, "6 4"),
    }


def legacy_components(plain=False):
    ts = tones(plain)
    ink = grayscale(THEME["ink"]) if plain else THEME["ink"]
    neutral, accent = ts["neutral"], ts["accent"]
    categories = {name: {"fill": t["tint"], "border": t["entity_border"], "title": ink}
                  for name, t in ts.items()}
    pills = {name: {"fill": t["tint"], "text": t["text"]} for name, t in ts.items()}
    return {
        "canvas": THEME["canvas_bg"], "ink": ink, "body": ink,
        "muted": neutral["text"], "action": accent["text"],
        "row_border": neutral["entity_border"], "cell_border": neutral["entity_border"],
        "row_header_bg": neutral["tint"], "verdict_bg": accent["tint"],
        "verdict_text": ink, "matrix_head_bg": neutral["tint"], "matrix_head_text": ink,
        "categories": categories, "pills": pills,
        "prio_bar": {"p0": ts["error"]["solid"], "p1": ts["warning"]["solid"],
                     "p2": accent["solid"], "none": neutral["solid"]},
    }


def variant():
    return {"claim": "浅分类面、轻实体边界、中性分组", "radius": 10.0, "card_border_w": 1.1,
            "neutral_border": THEME["entity_border"], "card_fill": THEME["entity_fill"],
            "focal": "category-trio", "zone_fill": THEME["panel_bg"],
            "zone_border": THEME["group_border"], "heavy": "none"}
