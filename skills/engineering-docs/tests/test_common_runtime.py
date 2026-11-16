"""SVG primitive paint, style and HTML namespace compatibility."""
from copy import deepcopy
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT = Path(os.environ.get('COMMON_TEST_ROOT', Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(ROOT / 'scripts'))
import diagram_runtime as R
import visual_theme as VT

NS = '{http://www.w3.org/2000/svg}'


class TestRuntime(unittest.TestCase):
    def scene(self, kind='architecture'):
        return {'type':kind, 'objects':[{'id':'a','kind':'card','content':{'label':'入口'},'paint':VT.roles()['frontend']}], 'edges':[]}

    def test_inline_style_and_attributes_have_identical_library_bindings(self):
        ink = VT.THEME['ink']
        svg = f'<svg xmlns="http://www.w3.org/2000/svg"><g data-node-id="a"><text fill="{ink}" style="fill: {ink}; stroke: {ink}; font-family: old">正文</text></g></svg>'
        scene = self.scene()
        root = ET.fromstring(R._adapt_svg(scene, svg))
        text = next(root.iter(NS+'text'))
        token = 'var(--dk-' + ink[1:].lower() + ')'
        self.assertEqual(text.get('fill'), token)
        self.assertIn('fill: ' + token, text.get('style'))
        self.assertIn('stroke: ' + token, text.get('style'))
        self.assertIn('sans-serif', text.get('font-family'))
        self.assertEqual(scene['visual_provenance']['before']['paint'][ink], 3)
        self.assertIn('font-family:old', scene['visual_provenance']['before']['fonts'])

    def test_body_header_badge_and_terminal_ring_are_separate(self):
        svg = '<svg xmlns="http://www.w3.org/2000/svg"><g data-node-id="a"><rect class="c-mask"/><rect class="c-frontend"/><rect class="c-frontend" style="fill: none"/><path class="cl-header"/><rect class="cl-badge-chip"/></g></svg>'
        root = ET.fromstring(R._adapt_svg(self.scene(), svg))
        mask, body, ring, header, badge = list(next(root.iter(NS+'g')))
        self.assertEqual([e.get('data-dk-paint') for e in (mask,body,ring,header,badge)], ['mask','body','body','header','badge'])
        self.assertEqual(body.get('data-dk-fill'), VT.node_surface(VT.roles()['frontend']))
        self.assertIsNone(mask.get('data-dk-fill'))
        self.assertIn('fill: none', ring.get('style'))
        self.assertEqual(header.get('data-dk-stroke'), 'none')
        self.assertIsNone(badge.get('data-dk-fill'))

    def test_user_custom_and_brand_paints_are_not_registered_as_library(self):
        scene = self.scene()
        scene['objects'][0]['content']['colour'] = '#123ABC'
        svg = '<svg xmlns="http://www.w3.org/2000/svg"><g data-node-id="a"><rect class="c-frontend"/><g data-brand-mark="example" data-brand-source="local-author"><path fill="#123ABC"/></g></g></svg>'
        root = ET.fromstring(R._adapt_svg(scene, svg))
        body = next(root.iter(NS+'rect'))
        self.assertEqual(body.get('fill'), '#123ABC')
        self.assertEqual(next(root.iter(NS+'path')).get('fill'), '#123ABC')
        self.assertNotIn('--dk-123abc', VT.export_tokens()['modes']['light'])
        self.assertTrue(scene['visual_provenance']['overrides'])
        self.assertTrue(all(not r['library_member'] for r in scene['visual_provenance']['overrides']))

    def test_free_custom_annotation_colour_has_author_origin_not_fake_library_membership(self):
        scene = {'type':'free','objects':[],'edges':[],
                 'annotations':[{'kind':'text','value':'自定义标注','color':'#123ABC'}]}
        svg = '<svg xmlns="http://www.w3.org/2000/svg"><text fill="#123ABC">自定义标注</text></svg>'
        root = ET.fromstring(R._adapt_svg(scene,svg))
        self.assertEqual(next(root.iter(NS+'text')).get('fill'),'#123ABC')
        self.assertEqual(scene['visual_provenance']['overrides'][0]['source'],'author-annotation')
        self.assertEqual(scene['visual_provenance']['unmapped'],[])
        self.assertNotIn('--dk-123abc',VT.export_tokens()['modes']['light'])

    def test_statistical_text_keeps_its_actually_measured_library_face(self):
        scene = self.scene('bubble')
        scene['typography_budget'] = {'font':'Arial Unicode MS'}
        svg = '<svg xmlns="http://www.w3.org/2000/svg"><text font-size="10">中文数据</text></svg>'
        text = next(ET.fromstring(R._adapt_svg(scene,svg)).iter(NS+'text'))
        self.assertTrue(text.get('font-family').startswith('"Arial Unicode MS"'))
        self.assertIn('font-family: "Arial Unicode MS"',text.get('style'))
        self.assertEqual(text.get('font-size'),'10')
        scene['typography_budget']['font'] = 'not-in-library'
        with self.assertRaises(R.DiagramError): R._adapt_svg(scene,svg)

    def test_er_field_display_names_are_sans_only_declared_code_is_mono(self):
        svg = '<svg xmlns="http://www.w3.org/2000/svg"><g data-node-id="a"><text class="t-primary">客户名称</text><text class="er-type">string</text><text class="cl-member">pay(): void</text></g></svg>'
        root = ET.fromstring(R._adapt_svg(self.scene('erd'), svg))
        texts = list(root.iter(NS+'text'))
        self.assertEqual([t.get('data-dk-font') for t in texts], ['sans','mono','mono'])
        self.assertIsNone(texts[0].get('data-code'))
        self.assertEqual(texts[1].get('data-code'), 'true')

    def test_layout_first_serialize_keeps_svg2_and_xlink_references_and_width(self):
        svg = '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"><defs><path id="p" d="M0 0L4 0L4 4Z"/></defs><use xlink:href="#p"/><use href="#p"/></svg>'
        source = {'type':'bubble','meta':{'title':'数值'},'payload':{}}
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)/'out.svg'
            def render(spec, output):
                output.write_text(svg)
                return {'width':912,'height':456}
            with patch('render_templates.render', side_effect=render):
                scene, first, compiled = R._layout_scene(source, {'title':'数值','layout':'bubble'}, out)
        self.assertEqual(scene['canvas'], [912,456])
        self.assertIn('xlink:href="#p"', first)
        final = R._adapt_svg(scene, first)
        self.assertIn('xlink:href="#p"', final)
        self.assertIn('href="#p"', final)
        self.assertNotIn('ns1:href', final)

    def test_layout_canvas_without_builder_dimensions_uses_svg_viewbox_not_680(self):
        source={'type':'bubble','meta':{'title':'数值'},'payload':{}}
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'out.svg'
            def render(spec,output):
                output.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 489.6 424.8"/>')
                return {'statistics':{}}
            with patch('render_templates.render',side_effect=render):
                scene,svg,_=R._layout_scene(source,{'title':'数值','layout':'bubble'},out)
        self.assertEqual(scene['canvas'],[489.6,424.8])

    def test_planning_builder_bytes_participate_in_component_fingerprint(self):
        before=R.component_fingerprint()
        original=Path.read_bytes
        def bytes_for(path):
            value=original(path)
            return value+b'\n# candidate fingerprint probe\n' if path==R.SCRIPTS/'planning_layouts.py' else value
        with patch.object(Path,'read_bytes',bytes_for):
            after=R.component_fingerprint()
        self.assertNotEqual(before['sha256'],after['sha256'])
        self.assertNotEqual(before['adapter_files']['scripts/planning_layouts.py'],after['adapter_files']['scripts/planning_layouts.py'])
        self.assertEqual(before['upstream_files_sha256'],after['upstream_files_sha256'])

    def test_declared_type_and_colour_semantics_never_all_fall_to_neutral(self):
        for values, expected in [({'type':'backend'}, VT.roles()['backend']), ({'type':'frontend'},VT.roles()['frontend']), ({'type':'failure'}, VT.tones()['error']), ({'type':'backend','tone':'warning'},VT.tones()['warning']), ({'type':'backend','colour':'rose'},VT.tones()['rose'])]:
            with self.subTest(values=values):
                source = {'type':'architecture','meta':{'title':'业务'},'payload':{'components':[{'id':'a',**values}]}}
                result = R._native_scene(source,'architecture','<svg xmlns="http://www.w3.org/2000/svg"/>')
                self.assertEqual(result['objects'][0]['paint'], expected)


if __name__ == '__main__':
    unittest.main()
