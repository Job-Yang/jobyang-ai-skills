"""Targeted regression for script embedding, explicit paint and export API fixes."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from diagram_kit import Diagram
import diagram_runtime as R

ROOT = Path(__file__).resolve().parents[1]
ATTACK = "</script><script>globalThis.__diagramKitInjected=true;document.getElementById('diagram-kit-source').textContent='{}';document.getElementById('diagram-kit-scene').textContent='{}';</script> & 中文代码 <标签>"


def safety_source():
    d = Diagram(960, 500, '数据安全回归')
    d.card('a', 50, 160, 300, '组件 A', code="中文代码 #123456", role='backend')
    d.card('b', 510, 160, 300, '组件 B', role='database')
    d.edge(d.nodes['a'], d.nodes['b'], label='真实关系')
    d.text(50, 380, '显式色 #123456', color='#123456')
    source = d.to_input()
    source['meta']['note'] = ATTACK
    source['payload']['extra_data'] = {'script': ATTACK, 'ampersand': '&', 'code': "中文代码 #123456"}
    return source


class DiagramSafetyTests(unittest.TestCase):
    def test_json_embedding_has_real_unicode_escapes(self):
        line = next(line for line in (ROOT/'scripts/diagram_adapter.mjs').read_text().splitlines() if line.startswith('const safe ='))
        for escape in ('\\\\u003c', '\\\\u0026', '\\\\u003e'):
            self.assertIn(escape, line)
        run = subprocess.run(['node', '--input-type=module', '-e', line + '\nconsole.log(safe(' + json.dumps({'text': ATTACK}, ensure_ascii=False) + '));'], capture_output=True, text=True, check=True)
        encoded = run.stdout.strip()
        self.assertNotIn('<', encoded)
        self.assertNotIn('>', encoded)
        self.assertNotIn('&', encoded)
        self.assertEqual(json.loads(encoded), {'text': ATTACK})

    def test_unknown_hex_is_not_an_undefined_token(self):
        source = safety_source()
        d = R.build_free(source)
        adapted = R._adapt_svg(d.to_scene(), d.svg())
        root = ET.fromstring(adapted)
        painted = next(e for e in root.iter() if e.get('data-explicit-fill') == '#123456')
        self.assertEqual(painted.get('fill'), '#123456')
        self.assertNotIn('var(--dk-123456)', adapted)
        self.assertIn('中文代码 #123456', adapted)
        self.assertIn('显式色 #123456', adapted)

    def test_embedded_source_scene_equal_frozen_input(self):
        source = safety_source()
        frozen = deepcopy(source)
        with tempfile.TemporaryDirectory() as td:
            result = R.render(source, Path(td)/'safe.html', formats=['svg'])
            text = Path(result['artifacts']['html']['path']).read_text()
            scene = json.loads(Path(result['artifacts']['scene']['path']).read_text())
            self.assertEqual(R.embedded_json(text, 'source'), frozen)
            self.assertEqual(R.embedded_json(text, 'scene'), scene)
            self.assertEqual(source, frozen)
            self.assertIn('\\u003c/script\\u003e', text)
            self.assertTrue(result['checks']['embedded_data']['ok'])
            self.assertTrue(R.check_delivery(Path(td)/'safe.receipt.json')['ok'])

    def test_embedding_mismatch_cannot_publish_success(self):
        with tempfile.TemporaryDirectory() as td:
            original = R._run
            def corrupt(command, cwd):
                result = original(command, cwd)
                if str(ROOT/'scripts/diagram_adapter.mjs') in command and '--preflight' not in command:
                    p = Path(cwd)/'diagram.html'
                    p.write_text(re.sub(r'(<script id="diagram-kit-source" type="application/json">)[\s\S]*?(</script>)', lambda m: m[1]+'{}'+m[2], p.read_text(), count=1))
                return result
            with patch.object(R, '_run', side_effect=corrupt), self.assertRaisesRegex(R.DiagramError, '冻结输入不一致'):
                R.render(safety_source(), Path(td)/'safe.html')
            self.assertFalse(list(Path(td).iterdir()))

    def test_malformed_embedded_json_reports_failure_not_decode_exception(self):
        with tempfile.TemporaryDirectory() as td:
            result = R.render(safety_source(), Path(td)/'safe.html')
            p = Path(result['artifacts']['html']['path'])
            p.write_text(re.sub(r'(<script id="diagram-kit-source" type="application/json">)[\s\S]*?(</script>)', lambda m: m[1]+'{invalid'+m[2], p.read_text(), count=1))
            receipt = Path(td)/'safe.receipt.json'
            data = json.loads(receipt.read_text())
            data['artifacts']['html']['sha256'] = hashlib.sha256(p.read_bytes()).hexdigest()
            receipt.write_text(R.dumps(data))
            checked = R.check_delivery(receipt)
            self.assertFalse(checked['ok'])
            self.assertTrue(any('有效JSON' in error for error in checked['errors']))


if __name__ == '__main__':
    unittest.main()
