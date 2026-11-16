"""Fixed-contract regression: complete scene, compatibility and fail-closed delivery."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from diagram_kit import Diagram
import diagram_runtime as R
from diagram_scene import validate, check_svg
from visual_theme import export_tokens


class UnifiedInputTests(unittest.TestCase):
    def test_registry_has_all_implemented_modes(self):
        r=R.registry()
        self.assertEqual(len(r),40)
        self.assertEqual(len({x['id'] for x in r}),40)
        self.assertTrue({'gantt','release-train'} <= {x['id'] for x in r})
        self.assertEqual({x['type'] for x in r if x['component']=='typed'},set(R.TYPES))
        self.assertEqual({x['layout'] for x in r if x['component']=='layout'},set(R.legacy_registry()['layouts']))
        self.assertFalse({'native','legacy'} & set(R.capabilities()))
        import diagram_kit as kit
        self.assertEqual(kit.capabilities(), R.capabilities())
        self.assertTrue(callable(kit.render))
        self.assertTrue(callable(kit.check_delivery))

    def test_optional_meta_is_not_invented(self):
        source={'version':1,'type':'matrix','meta':{'title':'比较'},'payload':{'rows':['A'],'columns':['X','Y'],'values':[['1','2']]}}
        normalized,_=R.normalize(source)
        self.assertEqual(normalized,source)
        self.assertNotIn('subtitle',normalized['meta'])
        self.assertNotIn('note',normalized['meta'])

    def test_compatibility_preserves_schema_fields(self):
        for layout in ('workflow','sequence','timeline','tree'):
            with self.subTest(layout=layout):
                data={'id':'example','name':'示例','title':'测试','layout':layout,'custom':{'condition':'不能丢'}}
                source,entry=R.normalize(data)
                self.assertEqual(source['type'],R.VARIANTS[layout])
                self.assertEqual(source['payload']['custom'],data['custom'])
                self.assertEqual(entry['schema'],'layout/'+layout)

    def test_typed_input_preserves_every_payload_field(self):
        original={'schema_version':3,'diagram_type':'lifecycle','meta':{'title':'事件'},'states':[{'id':'x','tag':'保留'}],'transitions':[],'mainPath':['x']}
        source,_=R.normalize(original)
        self.assertEqual(source['payload'],{k:v for k,v in original.items() if k not in {'diagram_type','meta'}})

    def test_mixed_schema_is_rejected(self):
        cases=[{'version':1,'type':'workflow','meta':{'title':'T'},'payload':{},'layout':'workflow'},
               {'title':'T','layout':'workflow','diagram_type':'workflow'},
               {'version':1,'type':'workflow','meta':{'title':'T'},'payload':{'layout':'workflow'}}]
        for data in cases:
            with self.subTest(data=data),self.assertRaises(R.DiagramError):R.normalize(data)

    def test_format_is_rejected_before_renderer(self):
        data={'version':1,'type':'matrix','meta':{'title':'T'},'payload':{}}
        with tempfile.TemporaryDirectory() as td,patch.object(R,'_run') as run:
            with self.assertRaisesRegex(R.DiagramError,'未实现格式'):R.render(data,Path(td)/'x.drawio')
            run.assert_not_called()
            self.assertFalse(list(Path(td).iterdir()))

    def test_missing_browser_is_rejected_before_renderer(self):
        d=SceneTests().sample()
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ,{'PLAYWRIGHT_MODULE':'/missing/playwright-module'}), patch.object(R,'build_free') as build:
            with self.assertRaises(R.DiagramError):R.render(d.to_input(),Path(td)/'x.html')
            build.assert_not_called()
            self.assertFalse(list(Path(td).iterdir()))

    def test_unknown_python_is_never_executed(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);source=root/'input.py';marker=root/'EXECUTED'
            source.write_text(f'from pathlib import Path\nPath({str(marker)!r}).write_text("bad")')
            with self.assertRaisesRegex(R.DiagramError,'绝不执行'):R.render(source,root/'x.html')
            self.assertFalse(marker.exists())

    def test_unknown_type_has_no_output(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(R.DiagramError):R.render({'version':1,'type':'unknown','meta':{'title':'T'},'payload':{}},Path(td)/'x.html')
            self.assertFalse(list(Path(td).iterdir()))


class SceneTests(unittest.TestCase):
    def sample(self):
        d=Diagram(960,650,'完整场景')
        a=d.card('a',50,170,300,'节点A',desc='长说明',code='POST /api',chips=[('标签','filled','accent')],rows=[('字段','只读','outline','sky')],badge='1',role='backend',status='')
        b=d.card('b',510,170,300,'节点B',role='database')
        z=d.zone_around('z',[a,b],'显式区域')
        d.edge(a,b,label='真实条件',style='dash')
        d.text(50,450,'自由说明')
        return d

    def test_scene_is_lossless_including_row_styles_and_badge(self):
        d=self.sample();before=d.to_scene();after=R.build_free(d.to_input()).to_scene()
        self.assertEqual(before,after)
        a=before['objects'][0]
        self.assertEqual(a['content']['row_specs'][0],['字段','只读','outline','sky'])
        self.assertEqual(a['content']['badge'],'1')
        self.assertEqual(a['content']['role'],'backend')
        self.assertEqual(before['annotations'][0]['value'],'自由说明')
        self.assertEqual(before['annotations'][0]['id'],'annotation-0')
        self.assertEqual(len(before['annotations'][0]['geometry']),4)
        self.assertIn('自由说明',d.svg())

    def test_unknown_membership_is_not_inferred(self):
        d=Diagram(960,500,'分区')
        d.zone('z',20,100,900,350,'区域')
        d.card('a',80,180,260,'A')
        scene=d.to_scene()
        self.assertEqual(scene['objects'][0]['membership'],{'state':'unknown','members':None})
        self.assertEqual(scene['edges'],[])

    def test_zone_endpoint_is_a_real_node(self):
        d=self.sample();d.edge(d.nodes['z'],(930,480),a_side='right',b_side='top',port='fixed')
        scene=d.to_scene()
        self.assertEqual(scene['edges'][-1]['from'],'z')
        self.assertTrue(validate(scene)['ok'])
        svg=R._adapt_svg(scene,d.svg())
        self.assertTrue(check_svg(scene,svg)['ok'])

    def test_explicit_members_fail_on_unknown_ids(self):
        d=self.sample()
        with self.assertRaises(ValueError):d.set_members('z',['missing'])
        d.nodes['z'].meta['members']=['missing']
        self.assertFalse(validate(d.to_scene())['ok'])

    def test_group_containment_is_not_card_overlap(self):
        self.assertTrue(validate(self.sample().to_scene())['ok'])

    def test_viewer_semantic_kind_keeps_typed_role(self):
        source={'version':1,'type':'workflow','meta':{'title':'T'},'payload':{'nodes':[{'id':'a','type':'backend','label':'A'}]}}
        raw='<svg xmlns="http://www.w3.org/2000/svg"><g data-node-id="a"><rect width="10" height="10"/></g></svg>'
        scene=R._native_scene(source,'workflow',raw)
        adapted=ET.fromstring(R._adapt_svg(scene,raw))
        self.assertEqual(adapted.find('.//*[@data-node-id]').get('data-node-kind'),'backend')
        span_source={'version':1,'type':'waterfall','meta':{'title':'T'},'payload':{'spans':[{'id':'request','name':'POST /checkout'}]}}
        span_svg='<svg xmlns="http://www.w3.org/2000/svg"><g data-node-id="request"><rect width="10" height="10"/></g></svg>'
        span_scene=R._native_scene(span_source,'waterfall',span_svg)
        span_adapted=ET.fromstring(R._adapt_svg(span_scene,span_svg))
        self.assertEqual(span_adapted.find('.//*[@data-node-id]').get('data-node-label'),'POST /checkout')

    def test_wrong_svg_edge_is_not_unrecognized_success(self):
        d=self.sample();scene=d.to_scene();svg=R._adapt_svg(scene,d.svg())
        svg=svg.replace('data-edge-to="b"','data-edge-to="a"')
        self.assertFalse(check_svg(scene,svg)['ok'])

    def test_non_directed_relation_is_not_skipped_by_checker(self):
        d=self.sample();d._edge_specs[0]['arrow']=False;d._finalized=False
        scene=d.to_scene();svg=R._adapt_svg(scene,d.svg())
        self.assertIn('data-edge-directed="false"',svg)
        self.assertTrue(check_svg(scene,svg)['ok'])
        self.assertFalse(check_svg(scene,svg.replace('data-edge-to="b"','data-edge-to="a"'))['ok'])

    def test_dangling_edge_fails(self):
        scene=self.sample().to_scene();scene['edges'][0]['to']='missing'
        self.assertFalse(validate(scene)['ok'])

    def test_members_are_not_fake_call_edges(self):
        scene=self.sample().to_scene()
        self.assertEqual(len(scene['edges']),1)
        self.assertEqual(scene['objects'][-1]['membership']['members'],['a','b'])

    def test_drawio_ids_and_real_bindings(self):
        root=ET.fromstring(self.sample().drawio());cells=root.findall('.//mxCell')
        self.assertEqual(len({c.get('id') for c in cells}),len(cells))
        edge=next(c for c in cells if c.get('edge')=='1')
        self.assertEqual((edge.get('source'),edge.get('target')),('a','b'))
        self.assertNotIn('<svg',self.sample().drawio())

    def test_shared_theme_has_all_modes_without_modifying_v4(self):
        t=export_tokens();self.assertEqual(set(t['modes']),{'light','dark','plain'})
        from visual_theme import roles
        self.assertEqual(t['modes']['light']['--frontend-fill'], roles()['frontend']['tint'])
        self.assertEqual(t['modes']['light']['--security-fill'], roles()['security']['tint'])
        self.assertNotEqual(t['modes']['light']['--bg'],t['modes']['dark']['--bg'])
        for v in t['modes']['plain'].values():
            if v.startswith('#'):self.assertEqual(v[1:3],v[3:5]);self.assertEqual(v[3:5],v[5:7])


class DeliveryTests(unittest.TestCase):
    def test_source_and_artifacts_must_match_final_receipt(self):
        d=SceneTests().sample()
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'diagram.html';report=R.render(d.to_input(),p,formats=['svg','drawio'])
            receipt=Path(td)/'diagram.receipt.json'
            self.assertTrue(R.check_delivery(receipt)['ok'])
            self.assertFalse(report['browser_verified'])
            scene=Path(report['artifacts']['scene']['path']);scene.write_text(scene.read_text()+' ')
            self.assertFalse(R.check_delivery(receipt)['ok'])

    def test_final_check_failure_has_no_success_residue(self):
        d=SceneTests().sample()
        with tempfile.TemporaryDirectory() as td,patch.object(R,'validate',return_value={'ok':False,'errors':['probe-failure']}):
            with self.assertRaisesRegex(R.DiagramError,'probe-failure'):R.render(d.to_input(),Path(td)/'diagram.html')
            self.assertFalse(list(Path(td).iterdir()))

    def test_source_mutation_during_generation_rejects_delivery(self):
        d=SceneTests().sample()
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/'input.json';source.write_text(R.dumps(d.to_input()))
            original=R._run
            def mutate(command,cwd):
                result=original(command,cwd);source.write_text(source.read_text()+' ');return result
            with patch.object(R,'_run',side_effect=mutate),self.assertRaisesRegex(R.DiagramError,'发生变化'):
                R.render(source,Path(td)/'out.html')
            self.assertEqual(sorted(p.name for p in Path(td).iterdir()),['input.json'])

    def test_existing_files_are_not_residual_success(self):
        d=SceneTests().sample()
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'x.html';p.write_text('old file')
            with self.assertRaises(R.BridgeError):R.render(d.to_input(),p)
            self.assertEqual(p.read_text(),'old file')

    def test_typed_appearance_is_preserved_outside_compiler_schema(self):
        root=Path(__file__).resolve().parents[1]
        original=json.loads((root/'vendor/archify/examples/agent-run.lifecycle.json').read_text())
        source=R.normalize(original)[0]
        source['meta']['note']='共同说明 $&'
        source['payload']['states'][0].update({'role':'security','tone':'','status':'warning','emphasis':False})
        frozen=deepcopy(source)
        with tempfile.TemporaryDirectory() as td:
            result=R.render(source,Path(td)/'x.html')
            self.assertEqual(source,frozen)
            self.assertEqual(json.loads(Path(result['artifacts']['source']['path']).read_text()),frozen)
            scene=json.loads(Path(result['artifacts']['scene']['path']).read_text())
            self.assertEqual(scene['objects'][0]['content'],frozen['payload']['states'][0])
            self.assertIn('共同说明 $&amp;',Path(result['artifacts']['html']['path']).read_text())

    def test_minimal_metadata_cross_components(self):
        root=Path(__file__).resolve().parents[1]
        sources=[{'version':1,'type':'matrix','meta':{'title':'仅有标题'},'payload':{'rows':['A'],'columns':['X','Y'],'values':[['1','2']]}}]
        native=json.loads((root/'vendor/archify/examples/orders.erd.json').read_text());native['meta']={'title':'仅有标题'}
        sources.append(R.normalize(native)[0])
        for source in sources:
            with self.subTest(type=source['type']),tempfile.TemporaryDirectory() as td:
                result=R.render(source,Path(td)/'x.html')
                saved=json.loads(Path(result['artifacts']['source']['path']).read_text())
                self.assertEqual(saved['meta'],{'title':'仅有标题'})
                scene=json.loads(Path(result['artifacts']['scene']['path']).read_text())
                self.assertEqual(scene['meta'],saved['meta'])


if __name__=='__main__':unittest.main()
