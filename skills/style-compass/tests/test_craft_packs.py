#!/usr/bin/env python3
"""4.7 多流派工艺包、自由基因引擎、动效工艺、轻量画廊与 alpha 容差检查测试。"""

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import lint_design  # noqa: E402

PACKS = (
    "obsidian-precision",
    "porcelain-craft",
    "editorial-ink",
    "executive-telemetry",
    "tactile-mobile",
    "liquid-glass",
    "nordic-frost",
    "tactile-hardware",
    "kinetic-bento",
)


class CraftPacksContractTest(unittest.TestCase):
    def test_all_nine_craft_packs_exist_with_anchors_and_clean_lint(self):
        packs_dir = ROOT / "assets" / "craft-packs"
        leak_company = "byte" + "dance"
        for name in PACKS:
            html_path = packs_dir / f"{name}.html"
            png_path = packs_dir / f"{name}.png"
            self.assertTrue(html_path.is_file(), f"缺少样板 HTML: {name}")
            self.assertTrue(png_path.is_file(), f"缺少视觉锚点 PNG: {name}")
            self.assertGreater(png_path.stat().st_size, 10_000, f"锚点图过小: {name}")
            text = html_path.read_text(encoding="utf-8")
            self.assertIn("prefers-reduced-motion", text, name)
            self.assertNotIn("/Users/", text, name)
            self.assertNotIn(leak_company, text.lower(), name)
            report = lint_design.lint_page(text, "direction", None, source=str(html_path), base_dir=packs_dir)
            self.assertEqual(report["summary"]["error"], 0, (name, report["findings"]))
            self.assertEqual(report["summary"]["warn"], 0, (name, report["findings"]))

    def test_alpha_shadows_and_derived_tints_pass_token_color(self):
        base_tokens = json.loads((ROOT / "examples" / "tokens.example.json").read_text(encoding="utf-8"))
        tokens = copy.deepcopy(base_tokens)
        tokens["color"]["accent"] = "#C85A32"
        page = """<!doctype html><html lang="zh-CN"><head><style>
          body { font-family: 'PingFang SC', sans-serif; color: #1E2228; background: #F6F7F9; }
          .card {
            background: #FFFFFF;
            border: 1px solid rgba(28, 25, 23, 0.08);
            box-shadow: 0 12px 24px rgba(15, 23, 42, 0.06);
          }
          .glow { background-color: rgba(200, 90, 50, 0.14); color: rgba(255, 255, 255, 0.92); }
          .bad-solid { color: #9333EA; }
        </style></head><body><div class="card"><p>验证半透明微高光和衍射光晕可以通过令牌校验。</p></div></body></html>"""
        report = lint_design.lint_page(page, "final", tokens)
        color_errs = [f for f in report["findings"] if f["rule"] == "TOKEN-COLOR"]
        self.assertEqual(len(color_errs), 1, color_errs)
        self.assertIn("#9333EA", color_errs[0]["message"])

    def test_build_gallery_supports_nine_variants_and_enforces_same_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            cmd = [
                sys.executable,
                str(ROOT / "scripts" / "build_gallery.py"),
                "--out",
            ]
            out_file = tmp_dir / "gallery.html"
            cmd.append(str(out_file))
            for idx, name in enumerate(PACKS):
                fname = f"v{idx}.html"
                (tmp_dir / fname).write_text(
                    f'<!doctype html><html lang="zh-CN"><body><h1>{name}</h1></body></html>',
                    encoding="utf-8",
                )
                cmd.extend(["--item", f"方案{idx + 1}|{name}|工艺亮点|{fname}"])

            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertTrue(out_file.is_file())
            gallery_html = out_file.read_text(encoding="utf-8")
            self.assertIn("ArrowRight", gallery_html)
            report = lint_design.lint_page(gallery_html, "direction", None, base_dir=tmp_dir)
            self.assertEqual(report["summary"]["error"], 0, report["findings"])
            self.assertEqual(report["summary"]["warn"], 0, report["findings"])

            bad = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "build_gallery.py"),
                    "--out",
                    str(out_file),
                    "--item",
                    "越界|X|外链|../escape.html",
                    "--item",
                    "正常|Y|可用|v0.html",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(bad.returncode, 2)

    def test_skill_and_new_references_wire_craft_engine_without_leaks(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        craft = (ROOT / "references" / "craft-packs.md").read_text(encoding="utf-8")
        genome = (ROOT / "references" / "craft-genome.md").read_text(encoding="utf-8")
        motion = (ROOT / "references" / "motion-craft.md").read_text(encoding="utf-8")
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("explore", skill)
        self.assertIn("references/craft-packs.md", skill)
        self.assertIn("references/craft-genome.md", skill)
        self.assertIn("references/motion-craft.md", skill)
        self.assertIn("scripts/capture_preview.mjs", skill)
        self.assertIn("scripts/build_gallery.py", skill)
        for name in PACKS:
            self.assertIn(name, craft)
            self.assertIn(f"assets/craft-packs/{name}.png", craft)
        for kw in ("VARIANCE", "MOTION", "DENSITY", "Remix"):
            self.assertIn(kw, genome)
        for kw in ("prefers-reduced-motion", "linear(", "Blur-Replace", "同心圆角", "频率"):
            self.assertIn(kw, motion)
        self.assertIn("## 4.7.0 — 2026-11-19", changelog)
        self.assertIn("## 4.6.0 — 2026-11-19", changelog)
        combined = "\n".join((skill, craft, genome, motion))
        self.assertNotIn("/Users/", combined)
        self.assertNotIn("byte" + "dance", combined.lower())
        self.assertTrue((ROOT / "scripts" / "capture_preview.mjs").is_file())
        self.assertTrue((ROOT / "scripts" / "build_gallery.py").is_file())


if __name__ == "__main__":
    unittest.main()
