"""显式覆盖语义和测量几何的回归测试，不是审美评分。"""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import diagram_runtime as runtime
import structural_extra as extra
from diagram_scene import validate, check_svg

BASE = {'id': 'coverage', 'name': '覆盖图', 'title': '按阶段查找能力',
        'stages': [{'id': 'a', 'label': '准备'}, {'id': 'b', 'label': '运行'}],
        'categories': [{'id': 'rules', 'label': '规则'}, {'id': 'empty', 'label': '扩展'}],
        'capabilities': [{'id': 'x', 'stage': 'a', 'category': 'rules', 'label': '校验', 'detail': '字段完整性'}],
        'shared': [{'id': 'audit', 'label': '审计', 'stages': ['a', 'b']}]}


class CoverageTests(unittest.TestCase):
    def scene(self, updates=None):
        spec = deepcopy(BASE)
        spec.update(updates or {})
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / 'result.svg'
            source = {'version': 1, 'type': 'capability_map', 'meta': {'title': spec['title']},
                      'payload': {k: v for k, v in spec.items() if k not in ('id', 'name', 'title')}}
            scene, svg, compiled = runtime._layout_scene(source, {**spec, 'layout': 'capability_map'}, out)
        self.assertTrue(validate(scene)['ok'])
        self.assertTrue(check_svg(scene, svg)['ok'])
        return scene, svg, compiled

    def test_registers_through_unique_entry(self):
        entry = next(e for e in runtime.registry() if e['id'] == 'capability_map')
        self.assertEqual(entry['component'], 'layout')
        self.assertEqual(entry['formats'], ['html', 'svg', 'png'])

    def test_empty_category_and_shared_scope_have_no_fake_edges(self):
        scene, svg, _ = self.scene()
        self.assertEqual(scene['edges'], [])
        objects = {o['id']: o for o in scene['objects']}
        self.assertEqual(objects['empty']['membership']['members'], [])
        self.assertEqual(objects['a']['membership']['members'], ['x'])
        self.assertEqual(objects['audit']['content']['stages'], ['a', 'b'])
        self.assertEqual(objects['audit']['kind'], 'coverage')
        self.assertIn('—', svg)
        self.assertNotIn('marker-end=', svg)

    def test_category_color_inherits_without_focus_or_source_mutation(self):
        categories = [{'id': 'rules', 'label': '规则', 'tone': 'sky', 'emphasis': True},
                      {'id': 'empty', 'label': '扩展', 'tone': 'sage'}]
        base, _, _ = self.scene()
        colored, svg, _ = self.scene({'categories': categories})
        node = next(o for o in colored['objects'] if o['id'] == 'x')
        self.assertEqual(node['presentation']['effective']['tone'], 'sky')
        self.assertEqual(node['presentation']['inherited_from'], 'rules')
        self.assertFalse(node['presentation']['focus'])
        self.assertEqual(node['content'], BASE['capabilities'][0])
        self.assertEqual(colored['payload']['capabilities'], BASE['capabilities'])
        self.assertEqual(base['canvas'], colored['canvas'])
        self.assertEqual({o['id']: o['geometry'] for o in base['objects']},
                         {o['id']: o['geometry'] for o in colored['objects']})
        self.assertIn('fill-opacity="0.24"', svg)

    def test_explicit_item_color_and_focus_override_category(self):
        categories = [{'id': 'rules', 'label': '规则', 'tone': 'sky'}, BASE['categories'][1]]
        for own in ({'role': 'security'}, {'tone': 'neutral'}, {'status': 'warning'}):
            item = {**BASE['capabilities'][0], **own}
            scene, _, _ = self.scene({'categories': categories, 'capabilities': [item]})
            node = next(o for o in scene['objects'] if o['id'] == 'x')
            self.assertIsNone(node['presentation']['inherited_from'])
            self.assertEqual(node['content'], item)
        item = {**BASE['capabilities'][0], 'emphasis': True}
        scene, svg, _ = self.scene({'categories': categories, 'capabilities': [item]})
        node = next(o for o in scene['objects'] if o['id'] == 'x')
        self.assertTrue(node['presentation']['focus'])
        self.assertEqual(node['presentation']['effective']['tone'], 'sky')
        group = next(e for e in ET.fromstring(svg).iter() if e.get('data-node-id') == 'x')
        self.assertEqual(group.find('{*}text').get('font-weight'), '700')
        self.assertEqual(group.find('{*}rect').get('stroke-width'), '1.6')

    def test_shared_coverage_keeps_role_without_default_focus(self):
        shared = [{**BASE['shared'][0], 'role': 'security'}]
        scene, svg, _ = self.scene({'shared': shared})
        node = next(o for o in scene['objects'] if o['id'] == 'audit')
        self.assertEqual(node['content']['role'], 'security')
        self.assertFalse(node['presentation']['focus'])
        group = next(e for e in ET.fromstring(svg).iter() if e.get('data-node-id') == 'audit')
        self.assertEqual(group.find('{*}rect').get('fill'), extra.THEME['panel_bg'])
        self.assertEqual(group.find('{*}text').get('font-weight'), '500')
        self.assertEqual(group.find('{*}text').get('font-size'), '15')

    def test_long_text_grows_without_shrinking(self):
        short, _, _ = self.scene()
        item = deepcopy(BASE['capabilities'][0])
        item['label'] = '字段约束与默认值共同校验'
        item['detail'] = '同时核对可选字段、版本兼容和失败返回条件，保留所有约束；' * 3
        long, svg, _ = self.scene({'capabilities': [item]})
        def height(s):
            return next(o['geometry'][3] for o in s['objects'] if o['id'] == 'x')
        self.assertGreater(height(long), height(short))
        self.assertIn('font-size="15"', svg)
        self.assertIn('font-size="13"', svg)
        self.assertEqual(long['payload']['capabilities'][0], item)

    def test_disjoint_shared_spans_share_row_but_overlap_does_not(self):
        stages = BASE['stages'] + [{'id': 'c', 'label': '复盘'}]
        bands = [{'id': 'left', 'label': '审批', 'stages': ['a', 'b']},
                 {'id': 'right', 'label': '复盘记录', 'stages': ['c']},
                 {'id': 'overlap', 'label': '全程审计', 'stages': ['a', 'b', 'c']}]
        scene, _, _ = self.scene({'stages': stages, 'shared': bands})
        objects = {o['id']: o for o in scene['objects']}
        self.assertEqual(objects['left']['geometry'][1], objects['right']['geometry'][1])
        self.assertGreater(objects['overlap']['geometry'][1], objects['left']['geometry'][1])

    def test_long_stage_titles_and_unbalanced_empty_columns(self):
        stages = [{'id': 'a', 'label': '准备阶段需要核对来源版本和责任边界'},
                  {'id': 'b', 'label': '运行阶段观察实时反馈'},
                  {'id': 'c', 'label': '复盘阶段'}]
        items = [{**BASE['capabilities'][0], 'id': f'x-{i}', 'label': f'约束项{i}'} for i in range(9)]
        scene, svg, _ = self.scene({'stages': stages, 'capabilities': items})
        objects = {o['id']: o for o in scene['objects']}
        self.assertEqual(objects['b']['membership']['members'], [])
        self.assertEqual(objects['c']['membership']['members'], [])
        self.assertEqual(len(objects['rules']['membership']['members']), 9)
        self.assertEqual(scene['payload']['stages'], stages)
        self.assertGreater(objects['a']['geometry'][3], 37)

    def test_explicit_document_width_keeps_native_fonts_and_real_scene_width(self):
        default, _, _ = self.scene()
        wide, svg, compiled = self.scene({'layout': {'width': 960}})
        self.assertEqual(default['canvas'][0], 680)
        self.assertEqual(wide['canvas'][0], 960)
        self.assertEqual(float(ET.fromstring(svg).get('width')), 960)
        self.assertEqual(compiled['width'], 960)
        root = ET.fromstring(svg)
        background = next(el for el in root.iter() if el.tag.endswith('rect') and el.get('height') == '100%')
        self.assertEqual(float(background.get('width')), 960)
        _, noted_svg, noted = self.scene({'layout': {'width': 960}, 'note': '保留明确的原始说明'})
        self.assertIn(f'M32 {noted["height"]-69} H928', noted_svg)
        self.assertIn('保留明确的原始说明', noted_svg)
        self.assertEqual(wide['payload']['layout'], {'width': 960})
        old = next(o['geometry'] for o in default['objects'] if o['id'] == 'x')
        new = next(o['geometry'] for o in wide['objects'] if o['id'] == 'x')
        self.assertGreater(new[2], old[2])
        sizes = {float(el.get('font-size')) for el in ET.fromstring(svg).iter() if el.get('font-size')}
        self.assertTrue({15, 13}.issubset(sizes))
        for width in (679, 0, -1, True, '960', float('nan')):
            with self.subTest(width=width), self.assertRaises(ValueError):
                self.scene({'layout': {'width': width}})

    def wrapping_cases(self):
        stages = [{'id': f's{i}', 'label': f'阶段{i+1}'} for i in range(5)]
        for label, detail in [('initial_limit', ''), ('校验', 'minimum initial limit\n下一条约束')]:
            for layout in ({}, {'layout': {'width': 960}}):
                for emphasis in (False, True):
                    yield {'stages': stages, 'shared': [], 'capabilities': [
                        {'id': 'target', 'stage': 's0', 'category': 'rules', 'label': label,
                         'detail': detail, 'emphasis': emphasis}], **layout}

    def test_prebroken_words_are_emitted_once_and_fit_measured_height(self):
        for case in self.wrapping_cases():
            scene, svg, compiled = self.scene(case)
            node = next(el for el in ET.fromstring(svg).iter() if el.get('data-node-id') == 'target')
            lines = [el.text for el in node.findall('{*}text')]
            if case['capabilities'][0]['label'] == 'initial_limit':
                self.assertEqual(lines, ['initial_limit'])
            else:
                self.assertIn('下一条约束', lines)
                self.assertNotIn('it', lines)
            x, y, width, height = compiled['boxes']['target']
            labels = [item for item in compiled['labels'] if item['text'] in lines]
            for item in labels:
                self.assertLessEqual(item['y'] + 2, y + height)
                self.assertLessEqual(item['x'] + item['width'], x + width)
            self.assertEqual(len({item['y'] for item in labels}), len(labels))

    @unittest.skipUnless(os.environ.get('PLAYWRIGHT_MODULE'), 'Actual glyph check requires the existing Playwright module.')
    def test_browser_glyph_bounds_do_not_overflow_or_overlap(self):
        # getBBox 观察真实字形，不依赖场景校验的结论。
        script = r'''
const fs=require('fs'), {chromium}=require(process.env.PLAYWRIGHT_MODULE);
(async()=>{
 const browser=await chromium.launch({headless:true}); const page=await browser.newPage();
 await page.setContent(fs.readFileSync(process.argv[1],'utf8')); await page.evaluate(()=>document.fonts.ready);
 const result=await page.evaluate(()=>{
  const group=document.querySelector('g[data-node-id="target"]'), rect=group.querySelector(':scope > rect');
  const r={x:+rect.getAttribute('x'),y:+rect.getAttribute('y'),w:+rect.getAttribute('width'),h:+rect.getAttribute('height')};
  const boxes=[...group.querySelectorAll('text')].map(t=>{const b=t.getBBox();return {text:t.textContent,x:b.x,y:b.y,w:b.width,h:b.height}});
  const overflow=boxes.filter(b=>b.x<r.x-.5||b.y<r.y-.5||b.x+b.w>r.x+r.w+.5||b.y+b.h>r.y+r.h+.5);
  const overlaps=[];for(let i=0;i<boxes.length;i++)for(let j=i+1;j<boxes.length;j++){
   const a=boxes[i],b=boxes[j];if(Math.min(a.x+a.w,b.x+b.w)>Math.max(a.x,b.x)+.5&&Math.min(a.y+a.h,b.y+b.h)>Math.max(a.y,b.y)+.5)overlaps.push([a,b]);
  }return {r,boxes,overflow,overlaps};
 }); console.log(JSON.stringify(result)); await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
'''
        for case in self.wrapping_cases():
            _, svg, _ = self.scene(case)
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / 'glyphs.svg'
                # 观察渲染器真实 SVG，不使用 ET 添加 ns0 前缀后的传输文本。
                extra.capability_map({**deepcopy(BASE), **case}).save(path)
                result = subprocess.run(['node', '-e', script, str(path)], capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            observed = json.loads(result.stdout)
            self.assertEqual(observed['overflow'], [], observed)
            self.assertEqual(observed['overlaps'], [], observed)
            self.assertTrue(any(b['text'] == case['capabilities'][0]['label'] for b in observed['boxes']))

    def test_bad_scope_ids_and_real_edges_are_rejected(self):
        invalid = [ {'capabilities': [{**BASE['capabilities'][0], 'stage': 'unknown'}]},
                    {'shared': [{'id': 'x', 'label': '重复', 'stages': ['a', 'b']}]},
                    {'shared': [{'id': 'audit', 'label': '审计', 'stages': ['unknown']}]},
                    {'edges': [{'from': 'x', 'to': 'audit'}]},
                    {'stages': BASE['stages'] + [{'id': 'c', 'label': '复盘'}],
                     'shared': [{'id': 'audit', 'label': '审计', 'stages': ['a', 'c']}]},
                    {'capabilities': [{**BASE['capabilities'][0], 'label': 'UNBREAKABLE_IDENTIFIER_' * 20}]} ]
        invalid.extend({key: [{'from': 'x', 'to': 'audit', 'label': '显式关系'}]}
                       for key in ('connections', 'flows', 'messages', 'relations'))
        for updates in invalid:
            with self.subTest(updates=updates), self.assertRaises(ValueError):
                self.scene(updates)

if __name__ == '__main__':
    unittest.main()
