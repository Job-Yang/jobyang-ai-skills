"""显式角色树根的真实导出颜色回归；默认深底根仍保留原文字规则。"""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import diagram_runtime as runtime
from visual_theme import contrast


def to_hex(value):
    if value.startswith('#'):
        return value
    channels = value.removeprefix('rgb(').removesuffix(')').split(',')
    return '#' + ''.join(f'{int(channel.strip()):02X}' for channel in channels)


def rendered_root(svg_path):
    svg = ET.parse(svg_path).getroot()
    root = next(el for el in svg.iter() if el.get('data-node-id') == 'root')
    face = next(el for el in root if 'tree-root' in el.get('class', '').split())
    labels = [el for el in root if el.tag.endswith('text')]
    return face, labels


class TreeRootContrastTests(unittest.TestCase):
    def test_explicit_role_root_text_is_readable_in_every_theme(self):
        source = {'version': 1, 'type': 'tree', 'meta': {'title': '角色树根'},
                  'payload': {'schema_version': 1, 'nodes': [
                      {'id': 'root', 'label': '个人总盘', 'sublabel': '安排与证据', 'role': 'frontend'},
                      {'id': 'child', 'parent': 'root', 'label': '资料', 'role': 'database'}]}}
        with tempfile.TemporaryDirectory() as temporary:
            for theme in ('light', 'dark', 'plain'):
                with self.subTest(theme=theme):
                    output = Path(temporary) / f'{theme}.html'
                    result = runtime.render(source, output, formats=['svg'], theme=theme)
                    face, labels = rendered_root(Path(result['artifacts']['svg']['path']))
                    self.assertEqual(len(labels), 2)
                    for label in labels:
                        self.assertEqual(float(label.get('opacity', '1')), 1)
                        self.assertGreaterEqual(contrast(to_hex(label.get('fill')), to_hex(face.get('fill'))), 4.5)
                    self.assertTrue(runtime.check_delivery(output.with_suffix('.receipt.json'))['ok'])

    def test_unpainted_root_keeps_original_inverse_text_style(self):
        source = {'version': 1, 'type': 'tree', 'meta': {'title': '普通树根'},
                  'payload': {'schema_version': 1, 'nodes': [
                      {'id': 'root', 'label': '总览', 'sublabel': '原样保留'},
                      {'id': 'child', 'parent': 'root', 'label': '分支'}]}}
        build_scene = runtime._native_scene

        def without_root_paint(*args):
            # 未声明角色仍会得到中性色面；这里专门验证完全没有色面覆盖的原生根。
            scene = build_scene(*args)
            next(item for item in scene['objects'] if item['id'] == 'root').pop('paint')
            return scene

        with tempfile.TemporaryDirectory() as temporary, patch.object(runtime, '_native_scene', without_root_paint):
            result = runtime.render(source, Path(temporary) / 'default.html', formats=['svg'])
            face, labels = rendered_root(Path(result['artifacts']['svg']['path']))
            self.assertEqual(to_hex(labels[0].get('fill')), '#FFFFFF')
            self.assertLessEqual(float(labels[1].get('opacity')), 0.68)
            self.assertGreaterEqual(contrast(to_hex(labels[0].get('fill')), to_hex(face.get('fill'))), 4.5)


if __name__ == '__main__':
    unittest.main()
