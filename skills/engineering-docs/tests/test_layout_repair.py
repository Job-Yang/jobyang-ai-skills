"""Bounded layout contracts; same-input PNG review is separate evidence."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import render_templates as R
import structural_extra as S

EXAMPLES = R._load_examples()
BASE = {'title': '布局回归', 'subtitle': '', 'note': ''}


def example(layout):
    return copy.deepcopy(next(s for s in EXAMPLES if s['layout'] == layout))


class LayoutRepairTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'diagram.svg'

    def draw(self, builder, spec):
        original = copy.deepcopy(spec)
        canvas = builder(spec)
        result = canvas.save(self.path)
        self.assertEqual(spec, original)
        self.svg = ET.parse(self.path).getroot()
        self.text = ''.join(e.text or '' for e in self.svg.findall('.//{*}text'))
        return canvas, result

    def test_workflow_short_nodes_use_measured_caps_and_keep_and_edges(self):
        spec = example('workflow')
        spec['orientation'] = 'vertical'
        spec['lanes'] = ['研发', '协调', '验证']
        spec['nodes'] = [{'id': k, 'label': label, 'lane': lane, 'step': step}
                         for k, label, lane, step in [('req','确认',0,0), ('fork','并行（AND）',1,1), ('code','实现',0,2), ('cases','用例',2,2), ('join','全部（AND）',1,3), ('test','回归',2,4)]]
        spec['edges'] = [{'from': a, 'to': b} for a,b in [('req','fork'),('fork','code'),('fork','cases'),('code','join'),('cases','join'),('join','test')]]
        c, result = self.draw(R.workflow, spec)
        for node in spec['nodes']:
            _,_,w,h = c.boxes[node['id']]
            self.assertAlmostEqual(h, c.measure_block(node['label'], '', w)['height'])
            self.assertLess(h, 73)
        self.assertEqual([(e['from'],e['to']) for e in result['scene_graph']['edges']], [(e['from'],e['to']) for e in spec['edges']])
        self.assertIn('全部（AND）', self.text)
        self.assertTrue(all(l['size'] >= 16 for l in c.labels if l['text'] in spec['lanes']))
        spec['nodes'][2]['label'] = '完整的长活动名称与执行条件' * 16
        self.draw(R.workflow, spec)
        self.assertIn(spec['nodes'][2]['label'], self.text)

    def test_matrix_shared_columns_and_rows_have_content_budget(self):
        spec = {**BASE, 'rows':['评审','交付'], 'columns':['功能','运行','恢复'], 'values':[['验收口径']*3,['验收记录']*3]}
        c, result = self.draw(R.matrix, spec)
        cells = [o for o in result['scene_graph']['objects'] if o['kind']=='cell']
        self.assertEqual(len(cells), 6)
        self.assertTrue(all(l['size'] >= 15 for l in c.labels if l['text'] in spec['columns']+spec['rows']))
        self.assertTrue(all(l['size'] >= 14 for l in c.labels if l['text']=='验收口径'))
        self.assertLess(max(o['geometry'][3] for o in cells), 76)
        for row in ('评审','交付'):
            group = [o for o in cells if o['content']['row']==row]
            self.assertEqual(len({o['geometry'][1] for o in group}),1)
            self.assertEqual(len({o['geometry'][3] for o in group}),1)
        widths = {o['geometry'][2] for o in cells}
        self.assertEqual(len(widths),1)
        spec['rows'][0] = '已有较长的阶段名称' * 5
        spec['columns'][1] = '较长证据类型' * 8
        spec['values'][1][2] = '保留每一个条件和边界。' * 35
        self.draw(R.matrix,spec)
        self.assertIn(spec['values'][1][2],self.text)
        with self.assertRaises(ValueError): R.matrix({**spec,'values':[['缺列']]})

    def test_business_keeps_nine_zone_topology_but_hugs_text(self):
        spec = example('business')
        c, result = self.draw(R.business, spec)
        b = c.boxes
        self.assertEqual(len(b),9)
        self.assertLess(b['cell0'][3],350)
        self.assertAlmostEqual(b['cell0'][1],b['cell1'][1])
        self.assertAlmostEqual(b['cell0'][1]+b['cell0'][3],b['cell2'][1]+b['cell2'][3])
        self.assertEqual(b['cell3'][1:4:2],b['cell0'][1:4:2])
        self.assertAlmostEqual(b['cell7'][1],b['cell8'][1])
        for cell in spec['cells']:
            for item in cell['items']: self.assertIn(item,self.text)
        for index in (0,2,3,7):
            changed = copy.deepcopy(spec)
            changed['cells'][index]['items'] = ['所有原始事实与业务边界均须保留。' * 22]
            self.draw(R.business,changed)
            self.assertIn(changed['cells'][index]['items'][0],self.text)
        with self.assertRaises(ValueError): R.business({**spec,'cells':spec['cells'][:8]})

    def mixed_layers(self):
        return {**BASE, 'canvas_width':960, 'groups':[{'id':'business','label':'业务能力','items':[
            {'id':'content','label':'内容管理','detail':'已有职责说明保持完整','children':[{'id':'version','label':'版本管理','detail':'记录更新历史'},{'id':'review','label':'内容审核'}]},
            {'id':'search','label':'检索与问答','detail':'基于权限范围提供结果'},
            {'id':'auth','label':'权限校验','children':[{'id':'role','label':'用户角色'},{'id':'scope','label':'资源范围'}]}]}]}

    def test_layers_mixed_responsibilities_pack_children_without_empty_short_column(self):
        spec = self.mixed_layers()
        c, result = self.draw(R.layers,spec)
        objects = {o['id']:o for o in result['scene_graph']['objects']}
        self.assertEqual(objects['business']['membership']['members'],['content','search','auth'])
        self.assertEqual(objects['content']['membership']['members'],['version','review'])
        content = objects['content']['geometry']
        search = objects['search']['geometry']
        self.assertLessEqual(search[1]+search[3],content[1])
        self.assertAlmostEqual(objects['version']['geometry'][1],objects['review']['geometry'][1])
        self.assertIn('已有职责说明保持完整',self.text)
        label = next(l for l in c.labels if l['text']=='业务能力')
        self.assertEqual(label['anchor'],'middle')
        nested = spec['groups'][0]['items'][0]['children'][0]
        nested['children'] = [{'id':'deep','label':'二层成员','detail':'完整已有长说明' * 20}]
        _,result = self.draw(R.layers,spec)
        objects = {o['id']:o for o in result['scene_graph']['objects']}
        self.assertEqual(objects['version']['membership']['members'],['deep'])
        for parent in ('business','content','version','auth'):
            x,y,w,h = objects[parent]['geometry']
            for child in objects[parent]['membership']['members']:
                a,b,c,d = objects[child]['geometry']
                self.assertTrue(x <= a and y <= b and a+c <= x+w+.01 and b+d <= y+h+.01)
        self.assertIn(nested['children'][0]['detail'],self.text)
        self.assertEqual(result['scene_graph']['edges'],[])

    def test_state_main_path_bounded_by_actual_node_widths_and_keeps_symbols(self):
        spec = example('state_machine')
        c,result = self.draw(S.state_machine,spec)
        edges = result['scene_graph']['edges']
        self.assertEqual({(e['from'],e['to'],e['label']) for e in edges},{(e['from'],e['to'],e['label']) for e in spec['transitions']})
        work = c.boxes['sm-work']; done = c.boxes['sm-done']
        self.assertLessEqual(done[0]-(work[0]+work[2]), work[2]+c.gap*8)
        self.assertEqual(len(self.svg.findall(".//{*}g[@data-node-id='done']/{*}rect")),2)
        self.assertIsNotNone(self.svg.find(".//{*}g[@data-node-id='idle']/{*}circle"))
        for s in spec['states'][1:]: s['label'] = s['label']+'已有长状态名称'*5
        self.draw(S.state_machine,spec)
        for s in spec['states'][1:]: self.assertIn(s['label'],self.text)

    def test_state_multiple_branches_keep_each_transition(self):
        spec = {**BASE,'start':'start','states':[{'id':'start','label':'起点'},{'id':'work','label':'处理'},{'id':'done','label':'完成','kind':'end'},{'id':'failed','label':'失败','kind':'end'},{'id':'cancel','label':'取消','kind':'end'}],
                'transitions':[{'from':a,'to':b,'label':l} for a,b,l in [('start','work','开始'),('work','done','成功'),('work','failed','异常'),('work','cancel','取消'),('failed','start','重试')]]}
        _,result = self.draw(S.state_machine,spec)
        self.assertEqual(len(result['scene_graph']['edges']),len(spec['transitions']))
        spec['states'][3]['label']='保留失败状态的长名称与处理边界'
        c,result = self.draw(S.state_machine,spec)
        parent, branch = c.boxes['sm-work'], c.boxes['sm-failed']
        self.assertAlmostEqual(parent[0]+parent[2]/2,branch[0]+branch[2]/2)
        self.assertEqual(len(result['scene_graph']['edges']),len(spec['transitions']))
        with self.assertRaises(ValueError): S.state_machine({**spec,'transitions':spec['transitions']+[spec['transitions'][0]]})

    def test_state_bounded_columns_and_unrouted_transitions_are_not_silently_lost(self):
        for count in (3,5,8):
            spec = {**BASE, 'start':'s0', 'states':[{'id':f's{i}','label':f'状态{i}','kind':'end' if i==count-1 else 'normal'} for i in range(count)],
                    'transitions':[{'from':f's{i}','to':f's{i+1}','label':'继续'} for i in range(count-1)]}
            _, result = self.draw(S.state_machine,spec)
            self.assertEqual(len(result['scene_graph']['edges']),count-1)
            self.assertEqual(len(result['scene_graph']['objects']),count)
        spec['transitions'].append({'from':'s1','to':'s1','label':'真实自循环'})
        with self.assertRaisesRegex(ValueError,'未路由'):
            S.state_machine(spec)

    def test_pyramid_equal_tiers_collinear_outline_complete_notes_and_ordinals(self):
        spec = example('pyramid')
        spec['groups'][2]['items'] = ['完整的长说明，目标设计实现验证边界不删除。' * 15]
        c,result = self.draw(R.pyramid,spec)
        levels = [o for o in result['scene_graph']['objects'] if o['kind']=='level']
        self.assertEqual(len({round(o['geometry'][3],5) for o in levels}),1)
        polys = self.svg.findall('.//{*}polygon')
        slopes=[]
        for polygon in polys:
            points = [tuple(map(float,p.split(','))) for p in polygon.get('points').split()]
            slopes.append((points[2][0]-points[1][0])/(points[2][1]-points[1][1]))
            self.assertAlmostEqual(points[0][1],points[1][1])
            self.assertAlmostEqual(points[2][1],points[3][1])
        self.assertLess(max(slopes)-min(slopes),1e-6)
        for i,g in enumerate(spec['groups']):
            self.assertIn(str(i+1),self.text)
            self.assertIn(g['label'],self.text)
            for detail in g['items']: self.assertIn(detail,self.text)
        spec['groups'][0]['label']='已有的较长层级标题'*7
        self.draw(R.pyramid,spec)
        self.assertIn(spec['groups'][0]['label'],self.text)

    def test_house_centers_only_short_pillar_descriptions(self):
        spec = example('house')
        c,_ = self.draw(R.house,spec)
        for pillar in spec['pillars']:
            for item in pillar['items']:
                rows = [l for l in c.labels if l['text']==item]
                self.assertTrue(rows)
                self.assertTrue(all(l['anchor']=='middle' for l in rows))
        spec['pillars'][0]['items'] = ['保持长说明的逐行可读性与完整内容。' * 12]
        c,_ = self.draw(R.house,spec)
        self.assertIn(spec['pillars'][0]['items'][0],self.text)
        rows = [l for l in c.labels if l['text'].startswith('保持长')]
        self.assertTrue(rows)
        self.assertTrue(all(l['anchor']=='start' for l in rows))

    def test_cycle_is_single_filled_clockwise_arrow_body_and_keeps_real_links(self):
        for count in (3,4):
            spec=example('cycle'); spec['groups']=spec['groups'][:count]
            spec['links']=[{'from':'cycle0','to':'cycle1','label':'真实反馈','assumption':False}, {'from':'cycle1','to':'cycle2','label':'待验反馈','assumption':True}]
            c,result=self.draw(R.cycle,spec)
            paths=self.svg.findall('.//{*}path[@data-edge-key]')
            self.assertEqual(len(paths),count)
            self.assertEqual(len([p for p in self.svg.findall('.//{*}path') if ' A' in p.get('d','')]),count)
            for p in paths:
                self.assertNotEqual(p.get('fill'),'none')
                self.assertEqual(p.get('stroke'),'none')
                self.assertTrue(p.get('d').endswith('Z'))
                self.assertIsNone(p.get('marker-end'))
                self.assertEqual(p.get('data-edge-directed'),'true')
            self.assertEqual(result['scene_graph']['edges'][0]['assumption'],False)
            self.assertEqual(result['scene_graph']['edges'][1]['assumption'],True)
            self.assertIn('假设：待验反馈',self.text)
            self.assertNotIn('假设：真实反馈',self.text)
        with self.assertRaises(ValueError): R.cycle({**spec,'groups':spec['groups']*2})

    def test_canvas_supplemental_is_copied_without_changing_existing_scene(self):
        c=R.Canvas(BASE)
        c.supplemental={'title':'完整详情','sections':[{'id':'audit','title':'审批','rows':[{'label':'记录','value':'全部原文'}]}]}
        _,result=self.draw(lambda _:c.finish(c.content_top),BASE)
        self.assertIn('supplemental',result)
        self.assertEqual(result['supplemental'],c.supplemental)
        result['supplemental']['sections'][0]['rows'][0]['value']='变化'
        self.assertEqual(c.supplemental['sections'][0]['rows'][0]['value'],'全部原文')
        plain=R.Canvas(BASE).finish(100).save(self.path)
        self.assertNotIn('supplemental',plain)


if __name__ == '__main__': unittest.main()
