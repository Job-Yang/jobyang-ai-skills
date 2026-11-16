"""定点修复的反例回归：不以样式改绿代替实际数据／对比门槛。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import diagram_check
from diagram_kit import Diagram
from diagram_runtime import DiagramError, supplemental_html
from visual_theme import categorical_tone, export_tokens, point_tone


class RepairContracts(unittest.TestCase):
    def test_point_scheme_is_four_distinct_slots_and_never_cycles(self):
        self.assertEqual(len({point_tone(i)[0] for i in range(4)}), 4)
        for index in (-1, 4, True, 1.5):
            with self.subTest(index=index), self.assertRaises(ValueError):
                point_tone(index)

    def test_original_eight_categorical_slots_are_unchanged(self):
        self.assertEqual([categorical_tone(i)[0] for i in range(8)],
                         ['#346CA3', '#D2915B', '#3E8250', '#B39E4C', '#944A69', '#76A15E', '#6C4D8D', '#CE7B74'])

    def test_existing_visible_border_does_not_require_another_border(self):
        diagram = Diagram(960, 500, '可辨边界')
        zone = diagram.zone('zone', 40, 120, 880, 240, '分区')
        node = diagram.card('node', 80, 190, 240, '子项')
        node.meta['body_fill'] = zone.meta['body_fill']
        self.assertFalse(any('填充' in issue for issue in diagram.check()['issues']))
        node.meta['body_border'] = node.meta['body_fill']
        self.assertTrue(any('填充' in issue for issue in diagram.check()['issues']))

    def test_static_border_contrast_accounts_for_opacity(self):
        self.assertGreaterEqual(diagram_check._outline_contrast({'stroke': '#000000', 'stroke_opacity': 1}, '#FFFFFF'), 3)
        self.assertEqual(diagram_check._outline_contrast({'stroke': '#000000', 'stroke_opacity': 0}, '#FFFFFF'), 1)
        self.assertLess(diagram_check._outline_contrast({'stroke': '#D6DCE3', 'stroke_opacity': .5}, '#FFFFFF'), 3)

    def test_supplemental_preserves_false_and_escapes_text_in_all_modes(self):
        data = {'title': '补充记录', 'sections': [{'id': 'gate', 'title': '条件', 'rows': [
            {'label': '状态', 'value': False}, {'label': '原文', 'value': '</script><img src=x> & scope < 3'}]}]}
        for mode in ('light', 'dark', 'plain'):
            with self.subTest(mode=mode):
                text = supplemental_html(data, export_tokens(), mode)
                self.assertIn('false', text)
                self.assertIn('&lt;/script&gt;&lt;img src=x&gt;', text)
                self.assertNotIn('<img src=x>', text)

    def test_duplicate_supplemental_sections_are_rejected(self):
        with self.assertRaises(DiagramError):
            supplemental_html({'sections': [{'id': 'a', 'rows': []}, {'id': 'a', 'rows': []}]}, export_tokens(), 'light')


if __name__ == '__main__':
    unittest.main()
