"""Render the v2.3 extra structural gold standards (examples_extra.json) to
SVG + PNG previews under assets/diagram-templates/gallery/.

    python3 scripts/render_extra_examples.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import render_templates  # noqa: E402
import structural_extra  # noqa: E402
import diagram_check  # noqa: E402

GALLERY = ROOT / "assets/diagram-templates/gallery"
EXAMPLES = json.loads((ROOT / "assets/diagram-templates/examples_extra.json").read_text())


def build(spec):
    layout = spec["layout"]
    if layout in structural_extra.BUILDERS:
        return structural_extra.BUILDERS[layout](spec)
    if layout == "workflow":
        return render_templates.STRUCTURAL["workflow"](spec)
    raise ValueError(f"Unknown layout: {layout}")


def main():
    GALLERY.mkdir(parents=True, exist_ok=True)
    for spec in EXAMPLES:
        item = {**spec, "sample": True}
        svg = GALLERY / f"{spec['id']}.svg"
        png = GALLERY / f"{spec['id']}.png"
        build(item).save(svg)
        msg = diagram_check.render_png(svg, png, width=1360)
        print(f"{spec['id']}: svg={svg.name} png={'ok' if png.exists() else msg}")


if __name__ == "__main__":
    main()
