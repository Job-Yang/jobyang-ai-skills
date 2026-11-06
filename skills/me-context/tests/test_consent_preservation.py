"""Regression: health permissions must not erase unrelated person records.

All fixtures are fictional and local. No production profile is read or modified.
"""
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import mectx_common as C


def header(entity="friend", domain="network", layer="L2"):
    return ("---\nschema: personal-context/v1\n"
            f"entity: {entity}\ntype: person\nlayer: {layer}\ndomain: {domain}\n"
            "circle: close\nconfidence: high\nsource: declared\nupdated: 2026-10-27\n---\n")


class ConsentPreservation(unittest.TestCase):
    def filtered(self, text, scope):
        return C.consent_filtered_body("entities/friend.md", text,
                                      {"allowed": scope != "off", "scope": scope})[0]

    def test_unrelated_sections_and_prelude_survive_all_scopes(self):
        text = header() + "# 林予安\n- 称呼：小林\n\n## 工作\n- 职业：设计师\n\n## 喜好\n- 爱好：摄影\n"
        for scope in ("off", "index_only", "facts_only", "full"):
            with self.subTest(scope=scope):
                clean = self.filtered(text, scope)
                for fact in ("小林", "设计师", "摄影"):
                    self.assertIn(fact, clean)
                self.assertEqual(C.parse_frontmatter(clean)[0]["entity"], "friend")

    def test_flat_records_survive_but_health_lines_are_filtered(self):
        text = header() + "# 林予安\n- 职业：设计师\n- 爱好：摄影\n- 青霉素过敏，备孕中\n"
        for scope in ("off", "index_only", "facts_only"):
            with self.subTest(scope=scope):
                clean = self.filtered(text, scope)
                self.assertIn("设计师", clean)
                self.assertIn("摄影", clean)
                self.assertNotIn("备孕", clean)
                self.assertEqual("青霉素" in clean, scope == "facts_only")

    def test_health_section_never_treats_ordinary_line_as_safe_fact(self):
        text = header() + "## 健康\n- 青霉素过敏，备孕中\n- 检验结果 456\n- 已到医院复查\n## 工作\n- 职业：设计师\n"
        clean = self.filtered(text, "facts_only")
        self.assertIn("青霉素", clean)
        self.assertIn("设计师", clean)
        for forbidden in ("备孕", "456", "医院复查"):
            self.assertNotIn(forbidden, clean)
        for scope in ("off", "index_only"):
            self.assertNotIn("青霉素", self.filtered(text, scope))

    def test_mixed_sentence_keeps_only_whitelisted_clause(self):
        text = header() + "## 简介\n- 职业：设计师\n- 长期用药降压药，焦虑病史，坐骨神经疼痛\n"
        clean = self.filtered(text, "facts_only")
        self.assertIn("设计师", clean)
        self.assertIn("降压药", clean)
        for forbidden in ("焦虑", "坐骨神经", "疼痛"):
            self.assertNotIn(forbidden, clean)

    def test_full_does_not_rewrite_any_content(self):
        text = header() + "# 简介\n\n## 工作\n- 职业：设计师\n## 健康\n- 备孕中\n"
        self.assertEqual(self.filtered(text, "full"), text)

    def test_nonhealth_profile_not_erased(self):
        text = header("me", "work", "L1") + "## 职业方向\n- 计划转型设计\n"
        clean, _ = C.consent_filtered_body("profile/work.md", text,
                                         {"allowed": True, "scope": "facts_only"})
        self.assertIn("计划转型设计", clean)

    def test_real_cli_gate_export_zip_viz_share_preservation(self):
        with tempfile.TemporaryDirectory(prefix="mectx-consent-test-") as td:
            root = Path(td)
            (root / "entities").mkdir()
            (root / "ME.md").write_text(header("me", "identity", "L0") + "# 虚构本人\n- 称呼：小周\n", encoding="utf-8")
            (root / "network.md").write_text(header("me") + "## 朋友\n- friend：林予安\n", encoding="utf-8")
            (root / "entities/friend.md").write_text(header(layer="L3") + "# 林予安\n- 称呼：小林\n## 工作\n- 工作：设计师\n## 喜好\n- 爱好：摄影\n## 健康\n- 青霉素过敏，备孕中\n", encoding="utf-8")
            (root / "relations.md").write_text(header("me", "relations") + "# 关系\n", encoding="utf-8")
            (root / "exports").mkdir()
            for scope in ("off", "index_only", "facts_only", "full"):
                with self.subTest(scope=scope):
                    (root / "CONSENT-health.md").write_text(f"---\nscope: {scope}\ngranted: true\n---\n", encoding="utf-8")
                    def run(script, *args, rc=0):
                        result = subprocess.run([sys.executable, str(SCRIPTS / script), "--data", td, *args], text=True, capture_output=True)
                        self.assertEqual(result.returncode, rc, result.stderr)
                        return result.stdout
                    gate = run("gate.py", "--domain", "network", "--entity", "friend", "--audience", "local", "--emit")
                    md, zp, page = root / "exports/out.md", root / "exports/out.zip", root / "exports/out.html"
                    run("export.py", "--all-layers", "--out", str(md))
                    run("export.py", "--format", "zip", "--out", str(zp))
                    with zipfile.ZipFile(zp) as z:
                        zipped = z.read("entities/friend.md").decode("utf-8")
                    run("viz.py", "--out", str(page))
                    match = re.search(r'<script type="application/json" id="mc-data">(.*?)</script>', page.read_text(encoding="utf-8"), re.S)
                    person = next(p for p in json.loads(match.group(1))["people"] if p["id"] == "friend")
                    self.assertTrue(person["zones"])
                    self.assertIn("设计师", person["summary"])
                    payload = json.dumps(person, ensure_ascii=False)
                    for clean in (gate, md.read_text(encoding="utf-8"), zipped, payload):
                        self.assertIn("设计师", clean)
                        self.assertIn("摄影", clean)
                        self.assertEqual("备孕中" in clean, scope == "full")
                        self.assertEqual("青霉素" in clean, scope in ("facts_only", "full"))
                    cloud = run("gate.py", "--domain", "network", "--entity", "friend", "--audience", "cloud", "--emit", rc=2)
                    self.assertNotIn("青霉素", cloud)
                    self.assertNotIn("备孕中", cloud)
                    run("viz.py", "--audience", "cloud", "--out", str(page))
                    match = re.search(r'<script type="application/json" id="mc-data">(.*?)</script>', page.read_text(encoding="utf-8"), re.S)
                    cloud_person = next(p for p in json.loads(match.group(1))["people"] if p["id"] == "friend")
                    cloud_payload = json.dumps(cloud_person, ensure_ascii=False)
                    self.assertIn("设计师", cloud_payload)
                    self.assertNotIn("青霉素", cloud_payload)
                    self.assertNotIn("备孕中", cloud_payload)


if __name__ == "__main__":
    unittest.main()
