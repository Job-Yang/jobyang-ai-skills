"""Label coordinates must remain author-owned; exercises the public SVG API."""
import os
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(os.environ.get('COMMON_TEST_ROOT', Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(ROOT / 'scripts'))
import diagram_kit as DK


class TestLabels(unittest.TestCase):
    def test_explicit_coordinates_and_offsets_survive_finalize(self):
        for previous_auto in (False, True):
            with self.subTest(previous_auto=previous_auto):
                d = DK.Diagram(960, 400, '标签坐标')
                a = d.card('a', 40, 120, 180, '甲')
                b = d.card('b', 400, 120, 180, '乙')
                if previous_auto:
                    d.edge(a, b, label='自动')
                d.edge(a, b, label='显式', label_at=(300, 270), label_dx=7, label_dy=-9)
                root = ET.fromstring(d.svg())
                label = next(e for e in root.iter() if e.tag.endswith('text') and e.text == '显式')
                # label_at is the label centre; SVG text baseline is centre + 0.36em.
                self.assertEqual((float(label.get('x')), float(label.get('y'))), (307, 265.5))
                _, left, top, right, bottom = d.label_boxes[-1]
                self.assertEqual(((left + right) / 2, (top + bottom) / 2), (307, 261))
                self.assertEqual(d.svg(), d.svg())

    def test_auto_coordinates_work_for_node_and_point_endpoints(self):
        for points in (False, True):
            with self.subTest(points=points):
                d = DK.Diagram(960, 400, '自动标签')
                if points:
                    a, b = (40, 120), (400, 120)
                else:
                    a = d.card('a', 40, 120, 180, '甲')
                    b = d.card('b', 400, 120, 180, '乙')
                d.edge(a, b, label='自动')
                root = ET.fromstring(d.svg())
                self.assertEqual(sum(e.text == '自动' for e in root.iter() if e.tag.endswith('text')), 1)


if __name__ == '__main__':
    unittest.main()
