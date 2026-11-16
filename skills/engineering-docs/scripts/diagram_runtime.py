"""Unified author input, capability registry, typed scenes and transactional delivery.

Components are implementation details. Schema adaptation occurs before rendering;
failures never select another renderer. Python sources are never imported/executed.
"""
import argparse
from copy import deepcopy
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

from archify_bridge import (TYPES, legacy_registry, load_json, file_path, readable,
                            output_guard, run_command, BACKEND, PIN, SKILL_ROOT, BridgeError)
from visual_theme import export_tokens, semantic_tone, typed_appearance, tones, roles, THEME, grayscale, node_surface
from diagram_scene import validate, check_svg

SCRIPTS = SKILL_ROOT / "scripts"
NATIVE_COLLECTIONS = dict(zip(TYPES, ("components", "nodes", "participants", "nodes", "states", "entities", "types", "nodes", "events", "spans")))
RELATIONS = {"architecture": "connections", "workflow": "edges", "sequence": "messages", "dataflow": "flows",
             "lifecycle": "transitions", "erd": "relationships", "class": "relationships"}
VARIANTS = {"workflow": "workflow-steps", "tree": "tree-hierarchy", "timeline": "timeline-stages", "sequence": "sequence-steps"}


class DiagramError(BridgeError):
    pass


def dumps(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"


def digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else dumps(value).encode()).hexdigest()


def registry():
    layouts = legacy_registry()
    result = [{"id": kind, "type": kind, "schema": f"typed/{kind}", "component": "typed", "formats": ["html", "svg", "png"],
               "features": ["typed-payload", "search", "focus", "theme"], "dependencies": ["node>=18", "playwright+chromium"]} for kind in TYPES]
    for kind in layouts["layouts"]:
        result.append({"id": VARIANTS.get(kind, kind), "type": kind, "schema": f"layout/{kind}", "component": "layout", "layout": kind,
                       "formats": ["html", "svg", "png"], "features": ["bounded-layout", "search", "focus", "theme"],
                       "dependencies": ["node>=18", "playwright+chromium"] + (["matplotlib", "numpy"] if kind in layouts["quantitative"] else [])})
    result.append({"id": "free", "type": "free", "schema": "objects/free", "component": "objects", "formats": ["html", "svg", "png", "drawio"],
                   "features": ["arbitrary-zones", "zone-endpoints", "explicit-members", "frozen-geometry", "search", "focus", "explicit-paths", "theme"],
                   "dependencies": ["node>=18", "playwright+chromium"]})
    return result


def capabilities():
    items = [{k: v for k, v in r.items() if k not in {"component", "layout"}} for r in registry()]
    return {"ok": True, "input_version": 1, "count": len(items), "items": items,
            "delivery": ["source.json", "scene.json", "html", "receipt.json"],
            "schema_compatibility": VARIANTS, "limitations": ["draw.io 目前仅支持自由对象图；拒绝其他图型，不嵌入SVG冒称可编辑。",
                "自动布局受各图型Schema约束；检查或生成失败不换图。", "SVG/PNG是固定主题静态图；交互仅在HTML。", "仅声明而未实现的配方不注册。"]}


def normalize(data, requested=None):
    """Preserve every authored field; compatibility schema is explicit, not lossy."""
    data = deepcopy(data)
    if "schema_version" in data and "diagram_type" not in data and requested in TYPES and not isinstance(data.get("layout"), str):
        data["diagram_type"] = requested
    if "payload" in data or "version" in data:
        if data.get("version") != 1 or not isinstance(data.get("payload"), dict):
            raise DiagramError("统一输入需要 version=1、meta 和对象 payload")
        if set(data) - {"version", "type", "meta", "payload"}:
            raise DiagramError("统一输入不能混入顶层layout/diagram_type等其他Schema字段")
        kind, payload, meta = data.get("type"), data["payload"], data.get("meta")
        if not isinstance(meta, dict) or not isinstance(meta.get("title"), str) or not meta["title"].strip():
            raise DiagramError("meta.title 必须是非空字符串")
        if requested and requested != kind:
            raise DiagramError("--type 与统一输入type不一致")
        if any(k in payload for k in ("meta", "version", "diagram_type")):
            raise DiagramError("payload不能包含另一套meta或顶层图型标记")
        candidates = [r for r in registry() if r["id"] == kind]
        if not candidates:
            raise DiagramError(f"未知图型：{kind}")
        selected = candidates[0]
    elif isinstance(data.get("layout"), str):
        if "diagram_type" in data or "schema_version" in data:
            raise DiagramError("混合Schema：layout字符串与typed标记不能共存")
        kind = data["layout"]
        candidates = [r for r in registry() if r.get("layout") == kind]
        if not candidates or requested not in (None, kind, candidates[0]["id"]):
            raise DiagramError(f"未知或不匹配layout：{kind}")
        selected = candidates[0]
        meta = {k: data[k] for k in ("title", "subtitle", "note", "id", "name") if k in data}
        payload = {k: v for k, v in data.items() if k not in meta and k != "layout"}
        data = {"version": 1, "type": selected["id"], "meta": meta, "payload": payload}
    elif data.get("diagram_type") in TYPES:
        kind = data["diagram_type"]
        if requested not in (None, kind):
            raise DiagramError("--type与diagram_type不一致")
        selected = next(r for r in registry() if r["id"] == kind)
        meta = data.get("meta", {})
        payload = {k: v for k, v in data.items() if k not in {"meta", "diagram_type"}}
        data = {"version": 1, "type": kind, "meta": meta, "payload": payload}
    else:
        raise DiagramError("无法识别输入；使用version=1、type、meta＋payload，或有效兼容JSON")
    if not isinstance(meta.get("title"), str) or not meta["title"].strip():
        raise DiagramError("缺少标题")
    for key in ("subtitle", "note", "locale"):
        if key in meta and not isinstance(meta[key], str):
            raise DiagramError(f"meta.{key}必须为字符串，缺省可省略")
    if selected["component"] == "typed" and isinstance(payload.get("layout"), str):
        raise DiagramError(f"{kind}的payload采用typed Schema；步骤布局请明确使用{VARIANTS.get(kind, kind)}")
    return data, selected


def build_free(source):
    from diagram_kit import Diagram
    p, meta = source["payload"], source["meta"]
    d = Diagram(*p["canvas"], meta["title"], meta.get("subtitle", ""), meta.get("note", ""), font=p.get("font", THEME["font"]))
    objects = p.get("objects", [])
    ids = [o["id"] for o in objects]
    if len(set(ids)) != len(ids) or set(ids) & {"0", "1", "title"}:
        raise DiagramError("自由图存在重复或draw.io保留ID")
    for o in objects:
        m, (x, y, w, h), nid = o.get("content", {}), o["geometry"], o["id"]
        kind = m.get("kind_tag", o["kind"])
        common = {k: m[k] for k in ("tone", "dashed") if k in m}
        if kind in ("group", "zone"):
            d.zone(nid, x, y, w, h, m["label"], **common, fill=m.get("fill", m.get("body_fill") is not None),
                   label_side=m.get("label_side", "top"), members=m.get("members"))
        elif kind == "bar":
            d.bar(nid, x, y, w, m.get("label", m["title"]), m.get("items", []), m.get("tone", "neutral"), h)
        elif kind == "banner":
            d.phase_banner(nid, x, y, w, m["index"], m["heading"], m.get("desc"), m.get("tone", "neutral"), h)
        elif kind == "note":
            d.note(nid, x, y, w, m["title"], m["text"], m.get("tone", "neutral"), h)
        elif kind == "verdict":
            d.verdict_bar(nid, x, y, w, m["title"], h)
        elif kind == "category":
            d.category_card(nid, x, y, w, m["title"], m["body"], m.get("cat", "neutral"), h, m.get("left_bar", False))
        elif kind == "row":
            d.evidence_action_row(nid, x, y, w, m["title"], m["evidence"], m["action"], m.get("prio", "none"), h)
        elif kind == "matrix":
            d.matrix_table(nid, x, y, w, m["headers"], m["rows"], m.get("row_header_w"), m.get("cell_h"))
        elif kind == "card":
            d.card(nid, x, y, w, m["title"], h=h, rows=m.get("row_specs", m.get("rows", [])),
                   **{k: m[k] for k in ("desc", "code", "chips", "badge", "tone", "emphasis", "dashed", "shadow", "role", "status") if k in m})
        else:
            raise DiagramError(f"未实现自由对象：{kind}")
    for e in p.get("edge_requests", []):
        def endpoint(value):
            if isinstance(value, str):
                if value not in d.nodes: raise DiagramError(f"悬空端点：{value}")
                return d.nodes[value]
            if not isinstance(value, list) or len(value) != 2: raise DiagramError("无效坐标端点")
            return value
        # Requests already contain resolved/distributed ports, retain them exactly.
        spec = deepcopy(e)
        spec["a"], spec["b"] = endpoint(e["a"]), endpoint(e["b"])
        d._edge_specs.append(spec)
    for annotation in p.get("annotations", []):
        args = {k: v for k, v in annotation.items() if k not in {'kind','id','geometry','geometry_source'}}
        if annotation["kind"] not in {"text", "chip", "status_pill"}:
            raise DiagramError("未知自由注释")
        getattr(d, annotation["kind"])(**args)
        if 'id' in annotation: d.annotations[-1]['id'] = annotation['id']
    if p.get("legend"):
        d.legend(**p["legend"])
    d._finalized = False
    return d


def _svg_from_html(text):
    match = re.search(r"<svg\b[\s\S]*?</svg>", text)
    if not match: raise DiagramError("编译结果没有SVG")
    return match.group()


def _native_scene(source, kind, raw_svg):
    p = source["payload"]
    objects = []
    # Authored semantics are copied from source, never inferred from SVG text.
    for item in p.get(NATIVE_COLLECTIONS[kind], []):
        if not isinstance(item, dict): raise DiagramError("无效typed对象")
        appearance = typed_appearance(item, kind)
        if 'role' not in appearance and item.get('type') in THEME['roles']:
            appearance['role'] = item['type']
        # Compatibility colour is an explicit library name, not an ordinal hue.
        colour = item.get('colour')
        if isinstance(colour, str) and not any(item.get(k) for k in ('tone','status','emphasis','role')):
            if colour in roles(): appearance['role'] = colour
            elif colour in tones(): appearance['tone'] = colour
        t = semantic_tone(appearance)
        objects.append({"id": item["id"], "kind": {"sequence": "participant", "timeline": "event", "waterfall": "span"}.get(kind, "card"),
                        "content": deepcopy(item), "geometry": None, "paint": t,
                        "membership": {"state": "unknown", "members": None}})
    for collection in ("groups", "lanes", "phases", "notes", "fragments", "frames"):
        for i, item in enumerate(p.get(collection, [])):
            members = item.get("members")
            if collection == "lanes":
                members = [n["id"] for n in p.get("nodes", []) if n.get("lane") == item["id"]]
            objects.append({"id": "group:" + collection + ":" + str(item.get("id", i)), "kind": "group" if collection not in {"notes"} else "annotation",
                            "content": deepcopy(item), "geometry": None, "interactive": False,
                            "membership": {"state": "explicit" if members is not None else "unknown", "members": members}})
    roots = ET.fromstring(raw_svg)
    compiled_edges = {}
    for el in roots.iter():
        if el.get("data-edge-from"):
            compiled_edges.setdefault((el.get("data-edge-from"), el.get("data-edge-to")), []).append(el.attrib)
    edges = []
    relationship_input = p.get(RELATIONS.get(kind, ""), [])
    if kind in {'tree', 'waterfall'}:
        collection = p.get(NATIVE_COLLECTIONS[kind], [])
        relationship_input = [{'from': item['parent'], 'to': item['id'], 'kind': 'hierarchy' if kind=='tree' else 'temporal-nesting'}
                              for item in collection if item.get('parent') is not None]
        for obj in objects:
            children = [item['id'] for item in collection if item.get('parent') == obj['id']]
            if children: obj['membership'] = {'state':'explicit','members':children}
    for i, item in enumerate(relationship_input):
        a, b = item.get("from", item.get("source")), item.get("to", item.get("target"))
        # Native ER/class endpoints can be structured field references.
        if isinstance(a, dict): a = a.get("entity", a.get("type"))
        if isinstance(b, dict): b = b.get("entity", b.get("type"))
        available = compiled_edges.get((a, b), [])
        keys = list(dict.fromkeys(el.get("data-edge-key") for el in available))
        key = item.get("id") if item.get("id") in keys else (keys[0] if keys else None)
        fragments = [el for el in available if el.get("data-edge-key") == key]
        compiled_edges[(a, b)] = [el for el in available if el.get("data-edge-key") != key]
        label = fragments[0].get("data-edge-label", "") if fragments else item.get("label", "")
        directed = kind not in {"erd", "class", "tree", "waterfall"}
        edges.append({"id": key or item.get("id") or f"relation-{i}", "from": a, "to": b,
                      "label": label, "directed": directed, "content": deepcopy(item), "compiled": fragments})
    marks = [{"id": f"compiled-mark-{i}", "tag": el.tag.split('}')[-1], "attributes": dict(el.attrib), "text": el.text}
             for i, el in enumerate(roots.iter())]
    for mark in marks:
        attrs = mark['attributes']
        frame = attrs.get('data-composition-frame-id', '')
        if not frame or not all(k in attrs for k in ('x', 'y', 'width', 'height')): continue
        match = re.match(r'(group|lane|phase)-(\d+)', frame)
        if match:
            collection = {'group':'groups', 'lane':'lanes', 'phase':'phases'}[match.group(1)]
            index = int(match.group(2))
            if index < len(p.get(collection, [])):
                item = p[collection][index]
                key = 'group:' + collection + ':' + str(item.get('id', index))
                for obj in objects:
                    if obj['id'] == key and obj['geometry'] is None:
                        obj['geometry'] = [float(attrs[k]) for k in ('x','y','width','height')]
    return {"scene_version": 1, "type": source["type"], "meta": source["meta"], "objects": objects, "edges": edges,
            "annotations": deepcopy(p.get("notes", [])), "payload": deepcopy(p), "compiled_marks": marks,
            "geometry_source": "renderer primitives + browser getBBox"}


def _serialize_svg(root):
    # Register before the FIRST serialization too; HTML does not recover nsN:href.
    ET.register_namespace('', 'http://www.w3.org/2000/svg')
    ET.register_namespace('xlink', 'http://www.w3.org/1999/xlink')
    return ET.tostring(root, encoding='unicode')


def _style_items(value):
    return [(key.strip(), val.strip()) for part in value.split(';') if ':' in part
            for key, val in [part.split(':', 1)]]


def _hex(value):
    value = value.strip()
    if re.fullmatch(r'#[0-9a-fA-F]{3}', value):
        value = '#' + ''.join(c * 2 for c in value[1:])
    return value.upper() if re.fullmatch(r'#[0-9a-fA-F]{6}', value) else None


def _visual_inventory(root):
    """Independent raw paint/font counts; never inferred from author data."""
    paint, fonts = {}, {}
    for el in root.iter():
        entries = list(el.attrib.items()) + _style_items(el.get('style', ''))
        for key, value in entries:
            if key in ('fill','stroke','color'):
                paint[value] = paint.get(value, 0) + 1
            if key in ('font-family','font','font-size'):
                item = key + ':' + value
                fonts[item] = fonts.get(item, 0) + 1
    return {'paint': paint, 'fonts': fonts,
            'text_elements': sum(el.tag.split('}')[-1] == 'text' for el in root.iter()),
            'use_elements': sum(el.tag.split('}')[-1] == 'use' for el in root.iter())}


def _paint_role(el):
    """Exact compiler classes identify responsibilities, not all sibling shapes."""
    classes = set(el.get('class', '').split())
    if 'c-mask' in classes: return 'mask'
    if classes & {'er-table-header','cl-header'}: return 'header'
    if classes & {'er-table-cap','cl-cap','tree-accent'}: return 'accent'
    if classes & {'er-key-badge','cl-badge-chip','cl-vis-chip'}: return 'badge'
    if classes & {'er-zebra','cl-zebra'}: return 'row'
    if el.get('data-graph-role') == 'structural-frame': return 'group'
    if (classes & {'er-table','cl-type','tree-root','tree-branch','tree-leaf','tl-card','wf-bar'} or
            (el.tag.split('}')[-1] in {'rect','polygon','ellipse','circle'} and
             any(c.startswith('c-') and c not in {'c-grid','c-lane','c-region','c-security-group'} for c in classes))):
        return 'body'
    return None


def _adapt_svg(scene, text):
    root = ET.fromstring(text)
    root.set("data-diagram-kit", "1")
    root.set("data-node-ui", "")
    by_id = {o["id"]: o for o in scene["objects"]}
    kinds = {o["id"]: o["kind"] for o in scene["objects"]}
    edge_index = 0
    tokens = export_tokens()
    known_tokens = tokens['modes']['light']
    provenance = {'library_sha256': tokens['library_sha256'], 'before': _visual_inventory(root),
                  'bindings': [], 'overrides': [], 'unmapped': []}
    parent = {child: el for el in root.iter() for child in el}
    viewbox = root.get('viewBox', '').split()
    outline_scale = float(viewbox[2]) / tokens['layout']['document_width'] if len(viewbox) == 4 else 1
    boundary_rects = [el for el in root.iter() if el.tag.split('}')[-1] == 'rect' and 'c-security-group' in el.get('class', '').split()]
    outer_boundaries = set()
    for outer in boundary_rects:
        x, y, w, h = (float(outer.get(k, '0')) for k in ('x', 'y', 'width', 'height'))
        for inner in boundary_rects:
            if inner is outer:
                continue
            ix, iy, iw, ih = (float(inner.get(k, '0')) for k in ('x', 'y', 'width', 'height'))
            if iw * ih < w * h and x - 2 <= ix and y - 2 <= iy and ix + iw <= x + w + 2 and iy + ih <= y + h + 2:
                outer_boundaries.add(outer)
    # Bind individual primitives. Python layouts already own their measured paint;
    # only pinned typed classes need role-based body/header/badge adapters.
    typed = scene['type'] in TYPES
    for el in root.iter():
        nid = el.get("data-node-id") or (el.get("data-id") if el.get("data-id") in by_id else None)
        if nid:
            o = by_id[nid]
            if o.get("interactive", True):
                el.set("data-node-id", nid)
                el.set("data-node-label", str(o['content'].get('title', o['content'].get('label', o['content'].get('name', el.get('data-node-label') or nid)))))
                semantic_kind = o['content'].get('role') or o['content'].get('type') or o['content'].get('kind') or el.get('data-node-kind') or kinds[nid]
                el.set("data-node-kind", semantic_kind if isinstance(semantic_kind, str) else kinds[nid])
                el.set("tabindex", "0")
                el.set("role", "button")
                el.set("aria-label", el.get("data-node-label"))
        if scene["type"] == "free" and el.get("data-kind") == "edge":
            edge = scene["edges"][edge_index]; edge_index += 1
            if edge.get("from") and edge.get("to"):
                for k, v in {"from": edge["from"], "to": edge["to"], "key": edge["id"], "label": edge.get("label") or ""}.items():
                    el.set("data-edge-" + k, str(v))
        # Retain every real relation for inspection/checking. Directionality is
        # separate: containment/ER/association must not become control paths.
        if el.get('data-edge-key'):
            edge = next((e for e in scene['edges'] if e['id'] == el.get('data-edge-key')), None)
            if edge is not None:
                el.set('data-edge-directed', 'true' if edge.get('directed', edge.get('arrow', True)) else 'false')
        styles = dict(_style_items(el.get('style', '')))
        ancestor, brand = el, None
        while ancestor is not None:
            if ancestor.get('data-brand-mark'):
                brand = ancestor
                break
            ancestor = parent.get(ancestor)
        if brand is el:
            provenance['overrides'].append({'brand': brand.get('data-brand-mark'),
                                            'source': brand.get('data-brand-source') or 'author-requested built-in brand',
                                            'sha256': brand.get('data-brand-sha256'), 'library_member': False})
        owner = parent.get(el)
        obj = by_id.get(owner.get('data-node-id')) if owner is not None else None
        duty = _paint_role(el) if typed else None
        if duty:
            el.set('data-dk-paint', duty)
        if obj and duty and obj.get('paint'):
            p = obj['paint']
            paints = {'body': {'fill': node_surface(p), 'stroke': p['entity_border']},
                      'header': {'fill': p['tint'], 'stroke': 'none'},
                      'accent': {'stroke': p['solid']}, 'row': {'fill': p['tint'], 'stroke': 'none'}}.get(duty, {})
            # Preserve terminal inner rings, not another coloured filled body.
            if styles.get('fill') == 'none': paints.pop('fill', None)
            custom = obj['content'].get('colour')
            if duty == 'body' and isinstance(custom, str) and _hex(custom):
                paints['fill'] = custom
                provenance['overrides'].append({'object': obj['id'], 'field': 'colour', 'value': custom,
                                                'source': 'author-payload', 'library_member': False})
            for attr, value in paints.items():
                styles.pop(attr, None)
                el.set(attr, value)
                el.set('data-dk-' + attr, value)
            provenance['bindings'].append({'object': obj['id'], 'duty': duty, 'paint': paints})
        if el.tag.split('}')[-1] == 'rect' and brand is None:
            classes = set(el.get('class', '').split())
            dash = styles.get('stroke-dasharray', el.get('stroke-dasharray', '')).strip()
            declared = obj.get('content', {}) if obj else {}
            outlined = (bool(dash and dash != 'none') or bool(classes & {'c-security-group', 'planned'})
                        or declared.get('status') in {'planned', 'future'} or declared.get('planned') is True)
            fill = styles.get('fill', el.get('fill', '')).strip()
            transparent = fill in {'none', 'transparent', 'rgba(0, 0, 0, 0)'}
            surface = bool(fill and not transparent) or (typed and duty in {'body', 'header', 'group', 'mask', 'row', 'badge'} and not transparent)
            policy = tokens['layout'].get('surface_outline', {})
            if el in outer_boundaries:
                # 仅调整已声明边界的绘制层级，不推断或改写成员关系。
                fill = roles()['security']['tint']
                el.set('fill', fill)
                el.set('data-dk-fill', fill)
                el.set('stroke', roles()['security']['entity_border'])
                el.set('data-dk-stroke', roles()['security']['entity_border'])
                el.set('stroke-dasharray', 'none')
                el.set('data-boundary-treatment', 'filled-outer')
                styles.pop('fill', None)
                styles.pop('stroke-dasharray', None)
                outlined, transparent, surface = False, False, True
            if scene['type'] == 'free' and obj and obj.get('kind') == 'card' and declared.get('role') in roles():
                geometry = obj.get('geometry') or []
                rect = [float(el.get(key, '0')) for key in ('x', 'y', 'width', 'height')]
                if len(geometry) == 4 and all(abs(a-b) < .5 for a, b in zip(rect, geometry)):
                    el.set('fill', node_surface(semantic_tone(declared)))
                    styles.pop('fill', None)
            if policy and surface and not outlined:
                stroke = styles.get('stroke', el.get('data-dk-stroke', el.get('stroke', THEME['group_border'])))
                styles.pop('stroke', None)
                styles.pop('stroke-width', None)
                if policy['filled'] == 'none' or stroke == 'none':
                    el.set('stroke', 'none')
                    el.set('data-dk-stroke', 'none')
                    el.set('data-surface-outline', 'none')
                else:
                    width = policy['filled_width'] * outline_scale
                    el.set('stroke', stroke)
                    el.set('data-dk-stroke', stroke)
                    el.set('stroke-width', str(width))
                    el.set('stroke-opacity', str(policy['filled_opacity']))
                    el.set('data-surface-outline', 'thin')
                    el.set('data-surface-outline-width', str(width))
            elif policy and (outlined or transparent):
                width = policy['semantic_width'] * outline_scale
                el.set('data-surface-outline', 'semantic')
                el.set('data-surface-outline-width', str(width))
                el.set('stroke-width', str(width))
                styles.pop('stroke-width', None)
        # Both presentation attributes AND inline style consume the same library.
        # Unknown compiler literals remain explicitly unmapped, not auto-enrolled.
        for attr in ('fill','stroke','color'):
            for container in (el.attrib, styles):
                value = container.get(attr, '')
                color = _hex(value)
                if not color or brand is not None: continue
                token = '--dk-' + color[1:].lower()
                annotation = next((a for a in scene.get('annotations', [])
                                   if a.get('kind') == 'text' and a.get('value') == el.text
                                   and isinstance(a.get('color'), str) and _hex(a['color']) == color), None)
                authored = (obj and obj['content'].get('colour') == value) or annotation is not None
                if annotation is not None and token not in known_tokens:
                    record = {'field': 'annotation.color', 'value': value, 'source': 'author-annotation',
                              'annotation': deepcopy(annotation), 'library_member': False}
                    if record not in provenance['overrides']: provenance['overrides'].append(record)
                if token in known_tokens and not authored:
                    container[attr] = 'var(' + token + ')'
                elif color in {THEME['paper'], _hex('#000')} and not authored:
                    replacement = THEME['ink'] if color == _hex('#000') else THEME['paper']
                    container[attr] = 'var(--dk-' + replacement[1:].lower() + ')'
                else:
                    el.set('data-explicit-' + attr, value)
                    if not authored:
                        provenance['unmapped'].append({'tag': el.tag.split('}')[-1], 'property': attr, 'value': value,
                                                      'source': 'compiler-literal', 'library_member': False})
        if el.tag.split('}')[-1] == 'text':
            classes = set(el.get('class', '').split())
            # Class signatures and declared ER datatype are code; field display
            # names and ordinary Chinese prose remain sans, never all ER rows mono.
            code = el.get('data-code') == 'true' or bool(classes & {'cl-member','er-type'})
            if not typed and 'Menlo' in el.get('font-family', ''): code = True
            family = tokens['fonts']['mono' if code else 'sans']
            measured_font = scene.get('typography_budget', {}).get('font')
            if not code and measured_font:
                candidates = [name.strip().strip('\"\'') for name in tokens['fonts']['sans'].split(',')]
                if measured_font not in candidates:
                    raise DiagramError('builder measured font is not a library sans candidate')
                family = '\"' + measured_font + '\", ' + family
                # Preserve the backend's actually measured library face; do not
                # let later family-only CSS invalidate the statistical geometry.
                styles['font-family'] = family
                el.set('data-dk-measured-font', measured_font)
            el.set('font-family', family)
            if code: el.set('data-code', 'true')
            el.set('data-dk-font', 'mono' if code else 'sans')
            if 'font-family' in styles: styles['font-family'] = family
            # Matplotlib font shorthand retains its measured size/weight.
            if 'font' in styles:
                match = re.search(r'((?:[0-9.]+)(?:px|pt)(?:/[0-9.]+)?)', styles['font'])
                if match: styles['font'] = styles['font'][:match.end()] + ' ' + family
        if styles: el.set('style', '; '.join(k + ': ' + v for k, v in styles.items()))
    provenance['after'] = _visual_inventory(root)
    provenance['font_budget'] = {'typed_geometry_and_sizes_unchanged': typed,
                                  'typed_measurement': 'pinned textUnits CJK/ASCII conservative budget; no font-size CSS override',
                                  'professional_size_unification': False if typed else 'layout-owned premeasurement'}
    scene['visual_provenance'] = provenance
    return _serialize_svg(root)


def _layout_scene(source, spec, output):
    import render_templates as rt
    compiled = rt.render(spec, output)
    raw = output.read_text()
    root = ET.fromstring(raw)
    viewbox = [float(n) for n in root.get('viewBox', '').replace(',', ' ').split()]
    canvas = [compiled.get('width'), compiled.get('height')]
    if any(value is None for value in canvas):
        if len(viewbox) != 4:
            raise DiagramError('builder must return width/height or a complete SVG viewBox')
        canvas = [canvas[i] if canvas[i] is not None else viewbox[i + 2] for i in range(2)]
    scene = {"scene_version": 1, "type": source["type"], "meta": source["meta"], "payload": deepcopy(source["payload"]),
             "objects": [], "edges": [], "annotations": compiled.get("labels", []), "canvas": canvas,
             "geometry_source": "layout Canvas / statistical SVG marks",
             'typography_budget': {'font': compiled.get('font'), 'source': 'builder measurement before SVG'}}
    if compiled.get('supplemental') is not None:
        scene['supplemental'] = deepcopy(compiled['supplemental'])
    # Layout Canvas knows true boxes. Every other visual mark is retained below;
    # no edges are guessed from line segments or visual containment.
    for key, geometry in compiled.get("boxes", {}).items():
        content = compiled.get("scene_objects", {}).get(str(key), {"title": str(key)})
        scene["objects"].append({"id": str(key), "kind": "card", "geometry": list(geometry), "content": deepcopy(content),
                                 "membership": {"state": "unknown", "members": None}})
    if compiled.get("scene_graph", {}).get("objects"):
        scene["objects"] = deepcopy(compiled["scene_graph"]["objects"])
        scene["edges"] = deepcopy(compiled["scene_graph"]["edges"])
    # All renderer marks and labels are losslessly indexed, including chart
    # glyphs and circle annotations. They are not fabricated graph nodes.
    scene["marks"] = [{"id": f"mark-{i}", "tag": el.tag.split("}")[-1], "attributes": dict(el.attrib), "text": el.text}
                      for i, el in enumerate(root.iter())]
    # Wrap exact renderer ranges for card hit targets where the Canvas exposes
    # them. Existing Canvas semantic groups are preferred over geometric matching.
    recognized = {el.get("data-node-id") for el in root.iter() if el.get("data-node-id")}
    for obj in scene["objects"]:
        if obj["id"] not in recognized: obj["interactive"] = False
    if not recognized:
        # Non-card layouts get a genuine whole-figure focus target, no fake paths.
        scene["objects"] = [{"id": "figure", "kind": "figure", "geometry": None,
                             "content": {"title": spec["title"], "layout": spec["layout"], "data": deepcopy(source["payload"])},
                             "membership": {"state": "unknown", "members": None}}]
        group = ET.Element("{http://www.w3.org/2000/svg}g", {"data-node-id": "figure"})
        for child in list(root):
            if child.tag.split("}")[-1] not in {"defs", "title", "desc", "metadata"}:
                root.remove(child); group.append(child)
        root.append(group)
    return scene, _serialize_svg(root), compiled


def component_fingerprint():
    pin = json.loads(PIN.read_text())
    vendor = SKILL_ROOT / 'vendor/archify'
    altered = [name for name, expected in pin['files'].items()
               if not (vendor/name).is_file() or hashlib.sha256((vendor/name).read_bytes()).hexdigest() != expected]
    if altered:
        raise DiagramError('固定上游组件被修改且未登记patch：' + ', '.join(altered))
    files = {str(p.relative_to(SKILL_ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(SCRIPTS.glob("diagram_*.py"))}
    for p in (SCRIPTS/"diagram_adapter.mjs", SCRIPTS/"visual_theme.py", SCRIPTS/"render_templates.py", SCRIPTS/"structural_extra.py", SCRIPTS/"planning_layouts.py", SCRIPTS/"archify_bridge.py", PIN):
        files[str(p.relative_to(SKILL_ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return {"archify_version": pin["version"], "archify_commit": pin["commit"], "adapter_files": files,
            "sha256": digest({'adapters': files, 'vendor': pin['files']}), "upstream_files_sha256": digest(pin['files']), "upstream_modified": pin["upstream_modified"], "local_adaptation": "diagram_adapter.mjs: template assembly, theme tokens, typed semantics, export API"}


def _run(command, cwd):
    result = run_command(command, cwd, timeout=180)
    if result["exit_code"]:
        raise DiagramError((result["stderr"] or result["stdout"])[-5000:])
    return result


def supplemental_html(data, tokens, theme):
    """补充记录独立交付，完整保留值；不把解释清单撑进主图。"""
    if not isinstance(data, dict) or not isinstance(data.get('sections'), list):
        raise DiagramError('supplemental must contain a sections array')
    title = data.get('title', '补充记录与说明')
    sections, seen = [], set()
    for section in data['sections']:
        if not isinstance(section, dict) or not isinstance(section.get('rows'), list):
            raise DiagramError('supplemental sections require rows')
        sid = section.get('id')
        if not isinstance(sid, str) or sid in seen:
            raise DiagramError('supplemental section IDs must be unique strings')
        seen.add(sid)
        cells = []
        for row in section['rows']:
            if not isinstance(row, dict) or 'label' not in row or 'value' not in row:
                raise DiagramError('supplemental row requires label and value')
            value = row['value'] if isinstance(row['value'], str) else dumps(row['value'])
            cells.append('<tr><th>' + html.escape(str(row['label'])) + '</th><td>' + html.escape(value) + '</td></tr>')
        sections.append('<section id="' + html.escape(sid, quote=True) + '"><h2>' + html.escape(str(section.get('title', sid))) + '</h2><table>' + ''.join(cells) + '</table></section>')
    variables = ';'.join(key + ':' + value for key, value in tokens['modes'][theme].items())
    css = ':root{' + variables + '}body{margin:0;font:16px/1.6 ' + tokens['fonts']['sans'] + ';background:var(--bg);color:var(--text)}main{max-width:960px;margin:auto;padding:24px}table{width:100%;border-collapse:collapse}th,td{padding:10px;text-align:left;vertical-align:top;border-bottom:1px solid var(--panel-border);white-space:pre-wrap;overflow-wrap:anywhere}th{width:28%;font-weight:600}'
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>' + html.escape(str(title)) + '</title><style>' + css + '</style><main><h1>' + html.escape(str(title)) + '</h1>' + ''.join(sections) + '</main></html>'


def render(input_value, output, *, formats=None, theme="light", overwrite=False, requested=None, quality=None, repo_root=None):
    output = file_path(output)
    if output.suffix.lower() not in {".html", ".svg", ".png", ".drawio"}:
        raise DiagramError("输出必须为.html/.svg/.png/.drawio")
    source_path = None
    if isinstance(input_value, (str, Path)):
        source_path = readable(file_path(input_value))
        if source_path.suffix.lower() != ".json":
            raise DiagramError("只自动读取JSON；未知Python文件绝不执行。已审阅程序可用Diagram.deliver/to_input。")
        source_bytes = source_path.read_bytes()
        data = load_json(source_path)
    else:
        data = deepcopy(input_value); source_bytes = dumps(data).encode()
    source, entry = normalize(data, requested)
    if theme not in {"light", "dark", "plain"}: raise DiagramError("未知主题")
    formats = list(dict.fromkeys(["html", output.suffix[1:].lower(), *(formats or [])]))
    unsupported = set(formats) - set(entry["formats"])
    if unsupported: raise DiagramError(f"{source['type']}未实现格式：{', '.join(sorted(unsupported))}；渲染前拒绝")
    node = shutil.which("node")
    if not node: raise DiagramError("需要Node.js 18+，不自动安装或换组件")
    version = subprocess.run([node, "--version"], capture_output=True, text=True, check=True).stdout
    if int(version.strip().lstrip("v").split(".")[0]) < 18: raise DiagramError("需要Node.js 18+")
    stem = output.with_suffix("")
    destinations = {f: Path(str(stem) + "." + f) for f in formats}
    destinations.update({"source": Path(str(stem)+".source.json"), "scene": Path(str(stem)+".scene.json"), "receipt": Path(str(stem)+".receipt.json")})
    for path in destinations.values():
        if source_path and (path.resolve() == source_path.resolve() or (path.exists() and os.path.samefile(path, source_path))):
            raise DiagramError("交付路径不能覆盖作者源或其别名")
        output_guard(path, overwrite, (path.suffix,), "统一绘图")
    tokens = export_tokens()
    dependency_check = _run([node, str(SCRIPTS/'diagram_adapter.mjs'), '--preflight'], output.parent)
    if dependency_check.get('receipt', {}).get('ok') is not True:
        raise DiagramError('浏览器依赖预检没有给出成功凭证')
    stages = {'dependencies': dependency_check}
    with tempfile.TemporaryDirectory(prefix=".diagram-kit-", dir=output.parent) as temp:
        stage = Path(temp)
        source_evidence = None
        if entry["component"] == "objects":
            d = build_free(source)
            original_check = d.check()
            # Contrast proximity with a visible outline is advisory, not a
            # geometry error. Keep the accepted security role fill unchanged.
            hard = [e for e in original_check["issues"] if "底色几乎相同" not in e]
            if hard: raise DiagramError("自由图检查失败：" + "; ".join(hard))
            stages["component_check"] = original_check
            scene, raw_svg = d.to_scene(), d.svg()
            for o in scene["objects"]:
                if o["kind"] == "zone": o["kind"] = "group"
            if "drawio" in formats: (stage/"diagram.drawio").write_text(d.drawio())
        elif entry["component"] == "typed":
            native = {"diagram_type": entry["type"], "schema_version": 2 if entry["type"] == "workflow" else 1,
                      **deepcopy(source["payload"]), "meta": {**source["meta"], "output": source["meta"].get("output", "component.html"), "locale": source["meta"].get("locale", "zh-CN")}}
            # Shared display-only metadata/appearance lives in the unified
            # source/scene, not in the pinned compiler's strict graph Schema.
            for key in ("note", "id", "name"):
                native["meta"].pop(key, None)
            for item in native.get(NATIVE_COLLECTIONS[entry["type"]], []):
                for key in ("role", "status", "tone", "emphasis", "colour"):
                    item.pop(key, None)
            (stage/"component.json").write_text(dumps(native))
            # Reject remote brand requests before the renderer can fetch them.
            from archify_bridge import reject_remote_brands
            reject_remote_brands(stage/"component.json")
            options = (["--quality", quality] if quality else []) + (["--repo-root", str(file_path(repo_root))] if repo_root else [])
            generated = _run([node, str(BACKEND), "deliver", entry["type"], str(stage/"component.json"), str(stage/"component.html"), "--json", *options], stage)
            if not generated.get("receipt", {}).get("ok"): raise DiagramError("typed组件未给出成功回执")
            stages["component_check"] = generated
            component_html = (stage/"component.html").read_text()
            evidence_match = re.search(r'<script id="archify-source-evidence-data" type="application/json">([\s\S]*?)</script>', component_html)
            if evidence_match: source_evidence = json.loads(evidence_match.group(1))
            raw_svg = _svg_from_html(component_html)
            scene = _native_scene(source, entry["type"], raw_svg)
        else:
            if source_path and source["payload"].get("image_path"):
                image = Path(source["payload"]["image_path"])
                if not image.is_absolute() and (source_path.parent / image).is_file():
                    # Freeze the image bytes into component input; normalized
                    # author source stays unchanged, including the relative path.
                    import base64
                    component_payload = deepcopy(source["payload"])
                    component_payload["image_b64"] = base64.b64encode((source_path.parent / image).read_bytes()).decode()
                else: component_payload = source["payload"]
            else: component_payload = source["payload"]
            spec = {"id": source["meta"].get("id", "diagram"), "name": source["meta"].get("name", entry["id"]),
                    **source["meta"], **component_payload, "layout": entry["layout"]}
            scene, raw_svg, stages["component_check"] = _layout_scene(source, spec, stage/"component.svg")
        scene["meta"] = deepcopy(source["meta"])
        scene["source_sha256"] = digest(source)
        adapted = _adapt_svg(scene, raw_svg)
        explicit_colors = {el.get('data-explicit-' + attr): grayscale(el.get('data-explicit-' + attr))
                           for el in ET.fromstring(adapted).iter() for attr in ('fill','stroke')
                           if el.get('data-explicit-' + attr)}
        supplemental_href = None
        if 'supplemental' in scene:
            from urllib.parse import quote
            for suffix in ('details.html', 'details.json'):
                path = Path(str(stem) + '.' + suffix)
                if source_path and (path.resolve() == source_path.resolve() or (path.exists() and os.path.samefile(path, source_path))):
                    raise DiagramError('补充交付不能覆盖作者源或其别名')
                output_guard(path, overwrite, (path.suffix,), '补充记录')
                destinations[suffix] = path
            (stage/'diagram.details.json').write_text(dumps(scene['supplemental']))
            (stage/'diagram.details.html').write_text(supplemental_html(scene['supplemental'], tokens, theme))
            supplemental_href = quote(destinations['details.html'].name, safe='')
        (stage/"input.json").write_text(dumps({"source": source, "scene": scene, "svg": adapted, "tokens": tokens, "theme": theme,
                                               "formats": formats, "components": component_fingerprint(), "sourceEvidence": source_evidence, "explicitColors": explicit_colors,
                                               'supplementalHref': supplemental_href}))
        stages["assembly"] = _run([node, str(SCRIPTS/"diagram_adapter.mjs"), str(stage/"input.json"), str(stage)], stage)
        scene = json.loads((stage/"diagram.scene.json").read_text())
        final_html = (stage/'diagram.html').read_text()
        for name, expected in (('source', source), ('scene', scene)):
            if embedded_json(final_html, name) != expected:
                raise DiagramError('内嵌' + name + '与冻结输入不一致')
        checks = {"scene": validate(scene), "semantic_svg": check_svg(scene, _svg_from_html(final_html)),
                  "embedded_data": {"ok": True, "errors": []}}
        if entry["component"] == "typed":
            # Original checker is run against the final assembled HTML, without
            # claiming that the component's earlier provenance proves this file.
            checks["typed_output"] = _run([node, str(SKILL_ROOT/"vendor/archify/scripts/check-render-output.mjs"), str(stage/"diagram.html")], stage)
        if any(not r["ok"] for k, r in checks.items() if k != "typed_output"):
            raise DiagramError("统一终稿检查失败：" + dumps(checks))
        if source_path and source_path.read_bytes() != source_bytes:
            raise DiagramError("作者源在生成期间发生变化，拒绝发布残留成功")
        (stage/"diagram.source.json").write_text(dumps(source))
        artifacts = {key: {"path": str(path), "sha256": hashlib.sha256((stage/("diagram." + (key+".json" if key in {"scene", "source"} else key))).read_bytes()).hexdigest()} for key, path in destinations.items() if key != "receipt"}
        report = {"ok": True, "input_version": 1, "type": entry["id"], "schema": entry["schema"], "output": str(output),
                  "source_origin": str(source_path) if source_path else "Diagram/in-memory", "source_origin_sha256": digest(source_bytes),
                  "source_sha256": digest(source), "scene_sha256": digest(scene), "theme_sha256": digest(tokens), "theme": theme,
                  "components": component_fingerprint(), "artifacts": artifacts, "checks": checks, "stages": stages,
                  "browser_verified": False, "browser_evidence": stages["assembly"].get("receipt"),
                  "visual_review": "浏览器DOM/导出观测已记录；尚未独立视觉验收。", "fallback": None}
        (stage/"diagram.receipt.json").write_text(dumps(report))
        # Recheck ALL paths before touching any destination. Receipt is committed
        # last and hashes the bundle; partial I/O failures cannot validate success.
        for key, path in destinations.items(): output_guard(path, overwrite, (path.suffix,), "统一绘图")
        commit_order = [key for key in destinations if key != 'receipt'] + ['receipt']
        for key in commit_order:
            path = destinations[key]
            candidate = stage/("diagram." + (key+".json" if key in {"scene", "source", "receipt"} else key))
            if path.exists(): candidate.chmod(path.stat().st_mode & 0o777)
            os.replace(candidate, path)
    return report


def embedded_json(text, name):
    matches = re.findall(rf'<script id="diagram-kit-{name}" type="application/json">([\s\S]*?)</script>', text)
    if len(matches) != 1:
        raise DiagramError(f'内嵌{name}缺失或重复')
    try:
        return json.loads(matches[0])
    except json.JSONDecodeError as error:
        raise DiagramError(f'内嵌{name}不是有效JSON') from error


def check_delivery(receipt_path):
    report = load_json(readable(file_path(receipt_path)))
    errors = []
    if report.get("ok") is not True: errors.append("receipt is not successful")
    for name, artifact in report.get("artifacts", {}).items():
        p = Path(artifact["path"])
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != artifact["sha256"]:
            errors.append(f"changed or missing artifact: {name}")
    if report.get("components", {}).get("sha256") != component_fingerprint()["sha256"]: errors.append("component fingerprint changed")
    if report.get("theme_sha256") != digest(export_tokens()): errors.append("theme fingerprint changed")
    if not errors:
        source = load_json(Path(report["artifacts"]["source"]["path"]))
        scene = load_json(Path(report["artifacts"]["scene"]["path"]))
        text = Path(report["artifacts"]["html"]["path"]).read_text()
        for name, value in (("source", source), ("scene", scene)):
            try:
                if embedded_json(text, name) != value: errors.append(f'embedded {name} differs')
            except DiagramError as error:
                errors.append(str(error))
        if digest(source) != report.get("source_sha256") or digest(scene) != report.get("scene_sha256"): errors.append("source/scene fingerprint differs")
        errors.extend(validate(scene)["errors"])
        errors.extend(check_svg(scene, _svg_from_html(text))["errors"])
    return {"ok": not errors, "errors": errors, "browser_verified": bool(report.get("browser_verified")) and not errors}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="operation", required=True)
    sub.add_parser("capabilities")
    r = sub.add_parser("render")
    r.add_argument("--input", required=True); r.add_argument("--output", required=True)
    r.add_argument("--type"); r.add_argument("--formats", default="")
    r.add_argument("--theme", choices=("light", "dark", "plain"), default="light")
    r.add_argument("--overwrite", action="store_true")
    c = sub.add_parser("check"); c.add_argument("receipt")
    # Writing/explainer methodology remains the existing implementation.
    for op in ("explain", "compare", "patch"):
        sub.add_parser(op, add_help=False)
    try:
        args, rest = p.parse_known_args(argv)
        if args.operation in {"explain", "compare", "patch"}:
            from archify_bridge import parser, execute
            result, code = execute(parser().parse_args([args.operation, *rest]))
        elif rest: raise DiagramError("未知参数：" + " ".join(rest))
        elif args.operation == "capabilities": result, code = capabilities(), 0
        elif args.operation == "check":
            result = check_delivery(args.receipt); code = 0 if result["ok"] else 1
        else:
            result = render(args.input, args.output, formats=[f for f in args.formats.split(",") if f], theme=args.theme, overwrite=args.overwrite, requested=args.type); code = 0
    except (ValueError, OSError, UnicodeError, subprocess.SubprocessError, KeyError, TypeError) as error:
        result, code = {"ok": False, "error": str(error), "browser_verified": False, "fallback": None}, 2
    print(dumps(result), end="")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
