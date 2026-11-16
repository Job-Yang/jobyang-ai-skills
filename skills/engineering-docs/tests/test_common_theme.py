"""Single source, detached compatibility and categorical capacity contract."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import visual_theme as VT


class TestTheme(unittest.TestCase):
    def test_only_resource_sections_store_hex_and_snapshot_is_detached(self):
        raw = json.loads(VT.THEME_PATH.read_text())
        self.assertNotIn('colors', raw)
        self.assertNotIn('border', raw)
        self.assertNotIn('category', raw)
        refs = json.dumps({k:v for k,v in raw.items() if k not in ('foundation','ramp')})
        self.assertNotIn('#', refs)
        snapshot = VT.theme_snapshot()
        snapshot['roles']['frontend']['solid'] = 'changed'
        self.assertEqual(VT.theme_snapshot()['roles']['frontend'], VT.THEME['roles']['frontend'])
        self.assertEqual(VT.export_tokens()['fonts'], VT.layout_tokens()['fonts'])

    def test_layout_scaled_before_measurement_has_shared_roles_and_leading(self):
        full, small = VT.layout_tokens(), VT.layout_tokens(680)
        self.assertEqual(full['design_width'],960)
        self.assertEqual(full['document_width'],800)
        for role in ('title','heading','node','body','caption','code'):
            self.assertAlmostEqual(small['sizes'][role],full['sizes'][role]*680/960)
            self.assertAlmostEqual(small['leading'][role],small['sizes'][role]*small['line_height'][role])
        for invalid in (0,-1,True,float('nan'),float('inf'),None,'680'):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError): VT.layout_tokens(invalid)

    def test_categorical_capacity_and_stable_explicit_order(self):
        palette = [VT.categorical_tone(i)[0] for i in range(8)]
        self.assertEqual(len(set(palette)),8)
        for invalid in (-1,8,100,True,1.5):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError): VT.categorical_tone(invalid)
        initial = ['b','a','c']
        whole = VT.categorical_assignment(initial,initial)
        filtered = VT.categorical_assignment(['c','b'],initial)
        self.assertEqual(filtered, {k:whole[k] for k in ('c','b')})
        with self.assertRaises(ValueError): VT.categorical_assignment(['d'],initial)
        with self.assertRaises(ValueError): VT.categorical_assignment(['a'],['a','a'])

    def test_structural_schemes_are_finite_duties_with_explicit_appearance_first(self):
        house = VT.colour_scheme('house')
        self.assertEqual(house['roof'], VT.tones()['sky'])
        self.assertEqual(house['foundation'], VT.tones()['sage'])
        self.assertEqual(len(house['pillar']), 6)
        self.assertEqual(VT.scheme_tone('house','pillar',0), house['pillar'][0])
        for fields, expected in [({'tone':'warning','role':'frontend'},VT.tones()['warning']),
                                 ({'status':'error'},VT.tones()['error']),
                                 ({'role':''},VT.tones()['neutral']),
                                 ({'tone':'','status':'','emphasis':''},house['roof'])]:
            with self.subTest(fields=fields):
                self.assertEqual(VT.scheme_tone('house','roof',item=fields), expected)
        with self.assertRaises(ValueError): VT.scheme_tone('house','pillar',6)
        with self.assertRaises(ValueError): VT.scheme_tone('house','pillar',True)
        with self.assertRaises(ValueError): VT.colour_scheme('unknown')
        self.assertEqual(VT.semantic_tone({'role':'HousePillar'}),VT.tones()['neutral'])
        for value in VT.colour_scheme('pyramid',plain=True)['layer']:
            for color in value.values(): self.assertEqual(color[1:3],color[3:5])
        house['roof']['solid']='changed'
        self.assertEqual(VT.colour_scheme('house')['roof'],VT.tones()['sky'])

    def test_dark_series_use_declared_steps_and_keep_light_identity(self):
        raw=json.loads(VT.THEME_PATH.read_text())
        tokens=VT.export_tokens()
        for index,name in enumerate(VT.THEME['sequence']):
            light=VT.categorical_tone(index)[0]
            dark=raw['ramp']['cvd_'+name]['dark_mark']
            key='--dk-'+light[1:].lower()
            self.assertEqual(tokens['modes']['light'][key],light)
            self.assertEqual(tokens['modes']['dark'][key],dark)
            self.assertEqual(tokens['categorical_modes'][name],{'light':light,'dark':dark})

    def test_dark_primary_ink_is_explicit_library_surface_mapping(self):
        tokens=VT.export_tokens()
        self.assertEqual(tokens['modes']['dark']['--text'],VT.THEME['paper'])
        self.assertEqual(tokens['modes']['dark']['--dk-'+VT.THEME['ink'][1:].lower()],VT.THEME['paper'])
        self.assertGreaterEqual(VT.contrast(tokens['modes']['dark']['--text'],tokens['modes']['dark']['--bg']),4.5)
        self.assertEqual(tokens['modes']['light']['--text'],VT.THEME['ink'])

    def test_empty_override_priority_contract_is_preserved(self):
        for fields, expected in [({'tone':'','status':'success'},VT.tones()['success']),({'status':'','emphasis':'warning'},VT.tones()['warning']),({'tone':'','status':'','emphasis':'','role':'backend'},VT.roles()['backend']),({'tone':'warning','status':'error','emphasis':'success','role':'frontend'},VT.tones()['warning']),({'role':'unknown','emphasis':True},VT.tones()['neutral'])]:
            with self.subTest(fields=fields): self.assertEqual(VT.semantic_tone(fields),expected)


if __name__ == '__main__':
    unittest.main()
