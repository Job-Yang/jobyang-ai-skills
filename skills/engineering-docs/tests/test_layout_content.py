"""Content/layout contracts, not an aesthetic acceptance claim."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import render_templates as R
from visual_theme import layout_tokens

EX = {s['id']: s for s in R._load_examples()}


class LayoutContentTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'diagram.svg'

    def render(self, key, **updates):
        spec = copy.deepcopy(EX[key]); spec.update(updates)
        result = R.render(spec, self.path)
        self.svg = ET.parse(self.path).getroot()
        return result

    def texts(self):
        return ''.join(e.text or '' for e in self.svg.findall('.//{*}text'))

    def test_canvas_uses_actual_shared_budget_and_width(self):
        for width in (680, 960):
            c = R.Canvas(EX['hierarchy'], width=width)
            self.assertEqual(c.size('body'), layout_tokens(width)['sizes']['body'])
            budget = c.measure_block('标题', '已有说明保持完整。' * 12, width*.4)
            h = c.box('measured', c.margin, c.content_top, width*.4, None, '标题', '已有说明保持完整。' * 12)
            self.assertAlmostEqual(h, budget['height'])
            result = c.finish(c.content_top+h).save(self.path)
            self.assertEqual(result['width'], width)
            self.assertEqual(float(ET.parse(self.path).getroot().get('width')), width)
            self.assertGreater(h, c.measure_block('标题', '', width*.4)['height'])
            with self.assertRaisesRegex(ValueError, 'Text exceeds'):
                c.box('too-small', c.margin, c.content_top, width*.4, 10, '标题')

    def test_internal_name_footer_removed_but_source_nature_kept(self):
        self.render('system-architecture', name='internal-registry-name', sample=True)
        self.assertNotIn('internal-registry-name', self.texts())
        self.assertNotIn('document-roles', self.texts())
        self.assertIn('合成示例', self.texts())
        self.assertIn(EX['system-architecture']['note'], self.texts())

    def test_nested_members_explicit_and_bounding_boxes_contain_children(self):
        result = self.render('system-architecture', groups=[{'label':'服务', 'items':[{'id':'parent','label':'内容','detail':'已有说明','children':[{'id':'a','label':'子模块甲'},{'id':'b','label':'子模块乙','detail':'保持细节'}]}]}])
        objects = {o['id']: o for o in result['scene_graph']['objects']}
        self.assertEqual(objects['parent']['membership']['members'], ['a','b'])
        self.assertEqual(result['scene_graph']['edges'], [])
        x,y,w,h = objects['parent']['geometry']
        for key in ('a','b'):
            a,b,c,d = objects[key]['geometry']
            self.assertTrue(a>x and b>y and a+c<x+w and b+d<y+h)
        self.assertIn('已有说明', self.texts())
        with self.assertRaises(ValueError):
            self.render('system-architecture', groups=[{'label':'服务','items':[{'id':'x','label':'甲'},{'id':'x','label':'乙'}]}])

    def test_grid_groups_hug_independent_content_and_declare_members(self):
        result = self.render('capability-grid', columns=2, groups=[{'label':'甲','items':['一个成员']},{'label':'乙','items':['一个成员','另一个成员','第三个成员']}])
        groups = [o for o in result['scene_graph']['objects'] if o['kind']=='group']
        self.assertLess(groups[0]['geometry'][3], groups[1]['geometry'][3])
        self.assertEqual([len(o['membership']['members']) for o in groups], [1,3])

    def test_tree_optional_detail_and_leaf_subtree_span(self):
        nodes = copy.deepcopy(EX['hierarchy']['nodes']); nodes[1]['detail']='真实职责说明'
        result = self.render('hierarchy', nodes=nodes)
        self.assertIn('真实职责说明', self.texts())
        self.assertEqual(len(result['scene_graph']['edges']), len(nodes)-1)
        self.assertTrue(all(e['directed'] is False for e in result['scene_graph']['edges']))
        self.assertLess(result['boxes']['space'][3], 83)
        self.assertGreater(result['boxes']['product'][3], result['boxes']['tech'][3])

    def test_mindmap_title_only_hugs_and_classification_is_undirected(self):
        result = self.render('mind-map', groups=[{'label':'甲','items':[]},{'label':'乙','items':[]}])
        self.assertLess(result['boxes']['root'][3], 82)
        self.assertLess(result['boxes']['branch0'][3], 110)
        self.assertTrue(all(not e['directed'] for e in result['scene_graph']['edges']))
        self.assertIn('不表示执行顺序', self.texts())

    def test_numeric_timeline_spacing_unit_and_no_iso_coercion(self):
        events = [{'at':v,'label':str(v),'detail':'实际事件'} for v in (0,2,8,10)]
        self.render('horizontal-timeline', events=events, unit='分钟')
        xs = [float(e.get('cx')) for e in self.svg.findall('.//{*}circle')]
        self.assertAlmostEqual((xs[2]-xs[1])/(xs[1]-xs[0]), 3)
        self.assertIn('8 分钟', self.texts())
        with self.assertRaises(ValueError):
            self.render('horizontal-timeline', events=[{'at':'2026-01-01','label':'甲'},{'at':'2026-01-02','label':'乙'}])

    def test_pyramid_keeps_every_layer_name_detail_and_ordinal(self):
        self.render('pyramid')
        for g in EX['pyramid']['groups']:
            self.assertIn(g['label'], self.texts())
            for t in g['items']: self.assertIn(t, self.texts())
        for value in range(1,5): self.assertIn(str(value), self.texts())

    def test_cycle_edges_keep_supplied_meaning_and_assumption(self):
        links = [{'from':'cycle0','to':'cycle1','label':'实际反馈','assumption':True}]
        result = self.render('growth-flywheel', links=links)
        self.assertIn('假设：实际反馈', self.texts())
        self.assertEqual(result['scene_graph']['edges'][0]['label'], '实际反馈')
        self.assertTrue(result['scene_graph']['edges'][0]['assumption'])

    def test_radar_multiseries_has_same_data_markers_legend_and_table(self):
        series=[{'id':'a','label':'甲系列','values':[1,2,3,4,5]},{'id':'b','label':'乙系列','values':[5,4,3,2,1]}]
        result=self.render('radar', series=series, unit='分', series_order=['a','b'])
        self.assertEqual(result['statistics']['series'], series)
        self.assertIn('数据查看（分）', self.texts())
        self.assertIn('甲系列', self.texts()); self.assertIn('乙系列', self.texts())
        hit_targets=[e for e in self.svg.findall('.//{*}circle') if e.get('tabindex')=='0']
        self.assertEqual(len(hit_targets),10)
        self.assertTrue(all(e.find('{*}title') is not None for e in hit_targets))
        first = {g.get('data-node-id'):g.find('{*}path').get('stroke') for g in self.svg.findall('.//{*}g') if g.get('data-node-id') in ('a','b')}
        self.render('radar',series=list(reversed(series)),series_order=['a','b'])
        reordered={g.get('data-node-id'):g.find('{*}path').get('stroke') for g in self.svg.findall('.//{*}g') if g.get('data-node-id') in ('a','b')}
        self.assertEqual(first,reordered)
        four = series + [{'id':'c','label':'丙系列','values':[1,2,3,4,5]}, {'id':'d','label':'丁系列','values':[5,4,3,2,1]}]
        with self.assertRaisesRegex(ValueError, '1–3 series'): self.render('radar',series=four)
        with self.assertRaises(ValueError): self.render('radar',series=series,series_order=['a','b','c','d'])
        with self.assertRaises(ValueError): self.render('radar',series=[{**series[0],'unit':'秒'}],unit='分')
        with self.assertRaises(ValueError): self.render('radar',series=[{**series[0],'labels':list(reversed(EX['radar']['labels']))}])

    def test_default_schemes_are_library_bound_and_explicit_style_wins(self):
        self.render('system-architecture')
        first = self.svg.find(".//{*}g[@data-node-id='layer0']/{*}rect")
        self.assertEqual(first.get('fill'), R.scheme_tone('layers','layer',0)['tint'])
        member = self.svg.find(".//{*}g[@data-node-id='g0-0']/{*}rect")
        self.assertEqual(member.get('fill'), R.node_surface(R.scheme_tone('layers','layer',0)))
        groups = copy.deepcopy(EX['system-architecture']['groups']); groups[0]['tone']='warning'
        self.render('system-architecture', groups=groups)
        first = self.svg.find(".//{*}g[@data-node-id='layer0']/{*}rect")
        self.assertEqual(first.get('fill'), R.semantic_tone({'tone':'warning'})['tint'])
        self.render('brand-house')
        roof = self.svg.find(".//{*}g[@data-node-id='house-roof']/{*}polygon")
        self.assertEqual(roof.get('fill'), R.scheme_tone('house','roof')['tint'])

    def test_old_maximum_layer_members_remains_legal(self):
        groups = [{'label':f'层{i}','items':[f'成员{j}' for j in range(9)]} for i in range(6)]
        result = self.render('system-architecture', groups=groups)
        self.assertEqual(len(result['boxes']),54)

    def test_statistics_share_font_budget_and_svg_dimensions(self):
        result = self.render('pie')
        self.assertIn(result['font'], R.layout_tokens(680)['fonts']['sans'])
        self.assertEqual(result['text_budget']['point_per_pixel'], .72)
        self.assertEqual(result['text_budget']['tokens']['sizes']['body'], R.layout_tokens(680)['sizes']['body'])
        view = list(map(float, self.svg.get('viewBox').split()))
        self.assertEqual([result['width'],result['height']], view[2:])

    def test_planning_uses_existing_dispatch(self):
        self.assertIn('gantt', R._extra_structural())
        self.assertIn('release-train', R._extra_structural())


if __name__ == '__main__': unittest.main()
