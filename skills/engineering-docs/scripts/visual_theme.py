"""Shared visual tokens and legacy views (standard library only).

All base colours live in assets/visual-examples/theme.json. Entity fills,
entity borders, group borders and connectors are deliberately independent.
"""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

THEME_PATH = Path(__file__).resolve().parents[1] / "assets/visual-examples/theme.json"
_LIBRARY = json.loads(THEME_PATH.read_text(encoding="utf-8"))


def _resolve(ref):
    value = _LIBRARY
    for key in ref.split('.'):
        value = value[key]
    return deepcopy(value)


def theme_snapshot():
    """Detached compatibility view, derived from the sole resource library."""
    view = {k: deepcopy(_LIBRARY[k]) for k in ('name', 'version', 'basis', 'sequence', 'tint_amount')}
    fields = {'canvas_bg':'canvas', 'panel_bg':'panel', 'entity_fill':'entity',
              'entity_border':'entity_border', 'group_border':'group_border',
              'ink':'ink', 'muted':'muted', 'line':'line', 'edge':'edge', 'grid':'grid', 'paper':'paper'}
    view.update({key: _resolve(_LIBRARY['surface'][name]) for key, name in fields.items()})
    for group in ('roles', 'category'):
        view[group] = {name: {field: _resolve(ref) for field, ref in values.items()}
                       for name, values in _LIBRARY['mapping'][group].items()}
    for field, suffix in (('solid',''), ('fill','_fill'), ('border','_border')):
        view['semantic' + suffix] = {name: _resolve(values[field])
                                    for name, values in _LIBRARY['mapping']['semantic'].items()}
    view['colors'] = {name: [_resolve(v['solid']), _resolve(v['fill'])]
                      for name, v in _LIBRARY['mapping']['categorical'].items()}
    view['colors']['gray'] = [view['muted'], view['panel_bg']]
    view['border'] = {name: v[0] for name, v in view['colors'].items()}
    view['font'] = _LIBRARY['typography']['sans']
    view['sizes'] = {**deepcopy(_LIBRARY['typography']['sizes']), 'radius': _LIBRARY['layout']['radius']['card']}
    return view


def layout_tokens(width=960):
    """960-unit design tokens scaled before measurement, never post-layout CSS."""
    if isinstance(width, bool) or not isinstance(width, (int, float)) or not math.isfinite(width) or width <= 0:
        raise ValueError('width must be a finite positive number')
    layout, typography = _LIBRARY['layout'], _LIBRARY['typography']
    scale = width / layout['design_width']
    scaled = lambda values: {k: v * scale for k, v in values.items()}
    sizes = scaled(typography['sizes'])
    return {'width': width, 'design_width': layout['design_width'], 'document_width': layout['document_width'],
            'scale': scale, 'fonts': {k: typography[k] for k in ('sans','mono')},
            'sizes': sizes, 'line_height': deepcopy(typography['line_height']),
            'leading': {k: sizes[k] * typography['line_height'][k] for k in sizes},
            'weight': deepcopy(typography['weight']), 'measure': deepcopy(typography['measure']),
            **{k: scaled(layout[k]) for k in ('spacing','radius','line','marker')},
            'surface_outline': {key: value * scale if key.endswith('_width') else value
                                for key, value in layout.get('surface_outline', {}).items()}}


def node_surface(appearance):
    """库级双层色面：节点与外分区可区分，不依赖描边。"""
    weight = _LIBRARY['layout'].get('surface_outline', {}).get('node_weight')
    if weight is None:
        return appearance['tint']
    fill, solid = appearance['tint'], appearance['solid']
    return '#' + ''.join(f"{round(int(fill[i:i+2], 16) * (1-weight) + int(solid[i:i+2], 16) * weight):02X}" for i in (1, 3, 5))


def typed_appearance(item, kind=None):
    """Only declared type/kind contracts map semantics; ID/name/label never do."""
    appearance = dict(item)
    contextual = _LIBRARY['mapping']['typed_kind'].get(kind, {})
    defaults = contextual.get(item.get('type', item.get('kind')), contextual.get('_default', {}))
    for key, value in {**defaults, **_LIBRARY['mapping']['typed'].get(item.get('type'), {})}.items():
        if key not in appearance:
            appearance[key] = value
    return appearance


THEME = theme_snapshot()
DEFAULT_THEME = THEME["name"]
THEME_ALIASES = dict.fromkeys(("default", "document-neutral", "warm-cream", "warm", "cream-blue", "cream",
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


def roles(plain=False):
    """Explicit engineering categories, separate from tone/status aliases.

    Solid is deeper for white-letter badges; entity_border is the ordinary
    role outline. No runtime dependency on the reference vendor.
    """
    return {name: _tone(v["solid"], v["fill"], v["border"], plain)
            for name, v in THEME["roles"].items()}


def semantic_tone(item=None, plain=False, *, tone_map=None, role_map=None):
    """颜色优先级：tone > status > 字符串 emphasis > role > 布尔 emphasis。

    tone/status/字符串 emphasis 的空字符串沿用旧接口，视为未指定。
    非空未知颜色或未知角色回中性；不根据标签和 ID 猜颜色。
    布尔 emphasis 只加强角色轮廓；可选映射保持各 Diagram 实例隔离。
    """
    item = item if isinstance(item, dict) else {}
    available = tones(plain) if tone_map is None else tone_map
    neutral = available["neutral"]
    name = item.get("tone") or item.get("status")
    emphasis = item.get("emphasis")
    if not name and isinstance(emphasis, str):
        name = emphasis
    if name:
        return available.get(name, neutral) if isinstance(name, str) else neutral
    role = item.get("role")
    if role is not None:
        role_available = roles(plain) if role_map is None else role_map
        return role_available.get(role, neutral) if isinstance(role, str) else neutral
    return available["accent"] if emphasis else neutral


def colour_scheme(name, plain=False):
    """Finite builder-owned visual duties, not inferred business roles or series."""
    if name not in _LIBRARY['scheme']:
        raise ValueError('unknown structural colour scheme: ' + str(name))
    available, role_available = tones(plain), roles(plain)
    def lookup(ref):
        return deepcopy(role_available[ref.split('.', 1)[1]] if ref.startswith('roles.') else available[ref])
    return {slot: [lookup(ref) for ref in refs] if isinstance(refs, list) else lookup(refs)
            for slot, refs in _LIBRARY['scheme'][name].items()}


def scheme_tone(name, slot, index=None, item=None, plain=False):
    """Explicit appearance wins; finite default duties never cycle past capacity."""
    item = item if isinstance(item, dict) else {}
    if (item.get('tone') or item.get('status') or item.get('emphasis') or
            ('role' in item and item['role'] is not None)):
        return deepcopy(semantic_tone(item, plain))
    scheme = colour_scheme(name, plain)
    if slot not in scheme:
        raise ValueError('unknown structural duty: ' + str(slot))
    value = scheme[slot]
    if isinstance(value, list):
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(value):
            raise ValueError('structural duty capacity exceeded; choose an explicit scheme, never cycle colours')
        return value[index]
    return value


def structural_tone(item=None, plain=False):
    t = semantic_tone(item, plain)
    if t == tones(plain)["neutral"]:
        pair = THEME["line"], THEME["panel_bg"]
        return tuple(map(grayscale, pair)) if plain else pair
    item = item if isinstance(item, dict) else {}
    ordinary_role = (item.get("role") and not item.get("tone")
                     and not item.get("status") and not item.get("emphasis"))
    return t["entity_border"] if ordinary_role else t["border"], t["tint"]


def categorical_tone(index):
    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(THEME['sequence']):
        raise ValueError('categorical capacity is 8; facet or declare secondary encoding, never cycle colours')
    return tuple(THEME['colors'][THEME['sequence'][index]])


def point_tone(index):
    """独立点的任意色对安全方案；单面最多四种，超过时分面而非循环。"""
    slots = _LIBRARY['mapping']['independent_points']
    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(slots):
        raise ValueError('independent point panel capacity is 4; facet without deleting data')
    return _resolve(slots[index]['mark']), _resolve(slots[index]['fill'])


def categorical_assignment(ids, initial_order):
    """Filtering/reordering preserves entity colour; order is explicit and frozen."""
    order = list(initial_order)
    if len(order) != len(set(order)) or len(order) > len(THEME['sequence']):
        raise ValueError('initial_order must be unique and within categorical capacity 8')
    if not set(ids) <= set(order):
        raise ValueError('all series IDs must exist in initial_order')
    return {key: categorical_tone(order.index(key)) for key in ids}


def diagram_metrics():
    """Legacy Diagram geometry budget now owned by the shared library."""
    return deepcopy(_LIBRARY['layout']['diagram_metrics'])


def palette(plain=False):
    return {"canvas": THEME["canvas_bg"], **{
        name: {"solid": t["solid"], "ink": t["text"],
               "soft": t["entity_border"], "tint": t["tint"]}
        for name, t in tones(plain).items()}}


def lines(plain=False):
    edge = grayscale(THEME["edge"]) if plain else THEME["edge"]
    accent = tones(plain)["accent"]["solid"]
    warning = tones(plain)["warning"]["solid"]
    widths = layout_tokens()['line']
    return {
        'main': (edge, widths['main'], None),
        'normal': (edge, widths['normal'], None),
        'accent': (accent, widths['accent'], None),
        'dash': (edge, widths['normal'], '6 4'),
        'planned': (accent, widths['accent'], '6 4'),
        'alert': (warning, widths['alert'], '6 4'),
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


def export_tokens():
    """One light/dark/plain token bundle for Python and JS; v4 light is unchanged."""
    def blend(a, b, amount):
        return "#" + "".join(f"{round(int(a[i:i+2], 16)*(1-amount)+int(b[i:i+2], 16)*amount):02X}" for i in (1, 3, 5))
    colors = set()
    def collect(v):
        if isinstance(v, str) and len(v) == 7 and v.startswith("#"):
            colors.add(v.upper())
        elif isinstance(v, dict):
            for item in v.values(): collect(item)
        elif isinstance(v, list):
            for item in v: collect(item)
    collect(THEME)
    collect([node_surface(tone) for tone in {**tones(), **roles()}.values()])
    point_slots = _LIBRARY['mapping']['independent_points']
    collect([_resolve(slot[key]) for slot in point_slots for key in ('mark', 'fill', 'dark_mark')])
    dark_marks = {_resolve(_LIBRARY['mapping']['categorical'][name]['solid']).upper(): _resolve(values['solid'])
                  for name, values in _LIBRARY['mapping']['categorical_modes']['dark'].items()}
    dark_marks.update({_resolve(slot['mark']).upper(): _resolve(slot['dark_mark']) for slot in point_slots})
    modes = {}
    for mode in ("light", "dark", "plain"):
        def color(value):
            if mode == "plain": return grayscale(value)
            if mode == "light": return value
            if value.upper() == THEME['ink'].upper():
                return _resolve(_LIBRARY['surface_modes']['dark']['ink'])
            if value.upper() in dark_marks: return dark_marks[value.upper()]
            rgb = [int(value[i:i+2], 16) for i in (1, 3, 5)]
            return blend(THEME["ink"], value, .08) if min(rgb) > 200 else blend(value, THEME["paper"], .50)
        ts, rs = tones(mode == "plain"), roles(mode == "plain")
        vars = {"--dk-" + c[1:].lower(): color(c) for c in colors}
        for key, field in {"bg": "canvas_bg", "grid": "grid", "text": "ink", "text-muted": "muted",
                           "text-dim": "muted", "text-faint": "muted", "panel": "paper", "panel-border": "group_border",
                           "lane-fill": "panel_bg", "lane-stroke": "group_border", "arrow": "edge", "mask": "paper",
                           "toolbar-bg": "paper", "toolbar-border": "group_border", "toolbar-text": "muted",
                           "toolbar-hover": "panel_bg", "toolbar-menu-bg": "paper"}.items():
            vars["--" + key] = color(THEME[field])
        vars["--arrow-emphasis"] = color(THEME["semantic"]["accent"])
        vars["--dk-paper"] = THEME["paper"]
        for name, t in {**ts, **rs}.items():
            vars["--" + name + "-fill"] = color(t["tint"])
            vars["--" + name + "-stroke"] = color(t["entity_border"])
            vars["--" + name + "-solid"] = color(t["solid"])
        modes[mode] = vars
    library_sha = hashlib.sha256(json.dumps(_LIBRARY, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return {'name': DEFAULT_THEME, 'version': THEME['version'], 'modes': modes,
            'fonts': layout_tokens()['fonts'], 'sizes': deepcopy(THEME['sizes']),
            'layout': layout_tokens(), 'library_sha256': library_sha,
            'mapping': deepcopy(_LIBRARY['mapping']),
            'schemes': {name: colour_scheme(name) for name in _LIBRARY['scheme']},
            'categorical_modes': {name: {'light': categorical_tone(i)[0], 'dark': dark_marks[categorical_tone(i)[0].upper()]}
                                  for i, name in enumerate(THEME['sequence'])},
            'overrides': deepcopy(_LIBRARY['overrides'])}


def variant():
    return {"claim": "显式角色浅色面、清晰实体轮廓、中性分组", "radius": 10.0, "card_border_w": 1.1,
            "neutral_border": THEME["entity_border"], "card_fill": THEME["entity_fill"],
            "focal": "category-trio", "zone_fill": THEME["panel_bg"],
            "zone_border": THEME["group_border"], "heavy": "none"}
