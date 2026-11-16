"""Typed scene integrity. Containment is not a relationship; geometry is transport."""
import math
import xml.etree.ElementTree as ET


def validate(scene):
    errors = []
    objects = scene.get("objects", [])
    ids = [o.get("id") for o in objects]
    if any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
        errors.append("missing or duplicate object IDs")
    known = set(ids)
    groups = {}
    for obj in objects:
        geometry = obj.get("geometry")
        if geometry is not None and (len(geometry) != 4 or any(not isinstance(n, (int, float)) or not math.isfinite(n) for n in geometry) or min(geometry[2:]) < 0):
            errors.append(f"invalid geometry: {obj['id']}")
        membership = obj.get("membership", {"state": "unknown", "members": None})
        if membership.get("state") == "explicit":
            members = membership.get("members")
            if not isinstance(members, list) or len(set(members)) != len(members) or any(i not in known or i == obj["id"] for i in members):
                errors.append(f"invalid members: {obj['id']}")
            else:
                groups[obj["id"]] = members
        elif membership != {"state": "unknown", "members": None}:
            errors.append(f"invalid unknown membership: {obj['id']}")
    def visit(key, ancestors):
        if key in ancestors:
            errors.append(f"containment cycle: {key}")
            return
        for child in groups.get(key, []):
            visit(child, ancestors | {key})
    for key in groups:
        visit(key, set())
    edge_ids = []
    for edge in scene.get("edges", []):
        edge_ids.append(edge.get("id"))
        for end in ("from", "to"):
            if edge.get(end) and edge[end] not in known:
                errors.append(f"dangling {end}: {edge.get('id')}")
        if edge.get("directed", edge.get("arrow", True)) and (not edge.get("from") or not edge.get("to")):
            # Free coordinate connectors have geometry, but no invented path semantics.
            if not edge.get("points"):
                errors.append(f"unbound relationship: {edge.get('id')}")
    if len(set(edge_ids)) != len(edge_ids) or any(not i for i in edge_ids):
        errors.append("missing or duplicate relationship IDs")
    # Ordinary cards may not intersect. Containers/frames and timed marks are
    # deliberately excluded: their members are not ordinary overlapping cards.
    cards = [o for o in objects if o.get("kind") in {"card", "note"} and o.get("geometry")]
    for i, a in enumerate(cards):
        ax, ay, aw, ah = a["geometry"]
        for b in cards[i + 1:]:
            bx, by, bw, bh = b["geometry"]
            if min(ax + aw, bx + bw) > max(ax, bx) + .5 and min(ay + ah, by + bh) > max(ay, by) + .5:
                errors.append(f"overlapping cards: {a['id']} / {b['id']}")
    return {"ok": not errors, "errors": errors, "objects": len(objects), "edges": len(edge_ids),
            "explicit_groups": len(groups), "unknown_groups": sum(o.get("kind") == "group" and o.get("membership", {}).get("state") == "unknown" for o in objects)}


def check_svg(scene, svg):
    root = ET.fromstring(svg)
    nodes = [el for el in root.iter() if el.get("data-node-id")]
    ids = [el.get("data-node-id") for el in nodes]
    expected = [o["id"] for o in scene["objects"] if o.get("interactive", True)]
    errors = []
    if len(set(ids)) != len(ids) or set(ids) != set(expected):
        errors.append("SVG semantic objects do not match typed scene")
    relations = {}
    for el in root.iter():
        if el.get("data-edge-key"):
            value = (el.get("data-edge-from"), el.get("data-edge-to"), el.get("data-edge-label", ""))
            if el.get("data-edge-key") in relations and relations[el.get("data-edge-key")] != value:
                errors.append("inconsistent relationship fragments")
            relations[el.get("data-edge-key")] = value
    for edge in scene.get("edges", []):
        if not edge.get("from") or not edge.get("to"):
            continue
        if relations.get(edge["id"]) != (edge["from"], edge["to"], edge.get("label") or ""):
            errors.append(f"SVG relationship missing or mismatched: {edge['id']}")
    if set(relations) - {e["id"] for e in scene.get("edges", [])}:
        errors.append("SVG contains unauthored relationships")
    return {"ok": not errors, "errors": errors, "recognized_objects": len(ids), "recognized_edges": len(relations)}
