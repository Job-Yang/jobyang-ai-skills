"""Planning models and Canvas contracts. Pure tests are not visual acceptance.

Run with Python -I -B; --pure restricts execution to computation/schema tests.
No network, dependency installation, shared-file writes or business execution.
"""
from copy import deepcopy
from datetime import date, timedelta
import importlib.util
import itertools
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / 'scripts/planning_layouts.py'
loader = importlib.util.spec_from_file_location('planning_layouts', MODULE)
PL = importlib.util.module_from_spec(loader)
loader.loader.exec_module(PL)


def example(name):
    return json.loads((ROOT / 'assets/diagram-templates' / f'planning-{name}.json').read_text())


def gantt_payload():
    return example('gantt-relative')['payload']


def train_payload():
    return example('release-train')['payload']


def date_train(windows=1):
    result = {'time_mode': 'date', 'train': {'id': 'train', 'label': '合成列车'},
              'windows': [], 'branches': [{'id': 'master', 'label': 'master', 'kind': 'master',
                                          'start': '2026-01-01', 'finish': '2026-03-01'}]}
    for index in range(windows):
        start = date(2026, 1, 2) + timedelta(days=index * 7)
        finish = start + timedelta(days=5)
        result['windows'].append({'id': f'w{index}', 'label': f'合成窗口 {index+1}',
                                  'start': start.isoformat(), 'finish': finish.isoformat(),
                                  'phases': [{'id': f'p{index}', 'label': '合成集成段', 'kind': 'integration',
                                              'start': start.isoformat(), 'finish': finish.isoformat()}]})
        result['branches'].append({'id': f'release{index}', 'label': f'release/{index}', 'kind': 'release',
                                   'window': f'w{index}', 'start': start.isoformat(), 'finish': finish.isoformat()})
    return result


class TestGanttModel(unittest.TestCase):
    def test_cpm_known_answer_and_no_mutation(self):
        payload = gantt_payload()
        before = deepcopy(payload)
        model = PL.schedule_gantt(payload)
        tasks = {t['id']: t for t in model['tasks']}
        self.assertEqual(model['axis_finish'], 10)
        self.assertEqual((tasks['client']['start'], tasks['client']['finish']), (2, 6))
        self.assertEqual((tasks['client']['start_value'], tasks['client']['finish_value'], tasks['client']['slack']), (2, 6, 0))
        self.assertEqual((tasks['api']['start_value'], tasks['api']['finish_value'], tasks['api']['slack']), (2, 5, 1))
        self.assertEqual(tasks['docs']['slack'], 6)
        self.assertTrue(tasks['verify']['critical'])
        self.assertFalse(tasks['api']['critical'])
        self.assertEqual({m['id']: m['at_value'] for m in model['milestones']},
                         {'contract-ready': 2, 'integration-ready': 8, 'accept-ready': 10})
        self.assertEqual(payload, before)
        self.assertEqual(len(model['edges']), 10)

    def test_source_and_after_order_do_not_affect_results(self):
        payload = gantt_payload()
        expected = PL.schedule_gantt(payload)
        for order in (list(reversed(payload['tasks'])), sorted(payload['tasks'], key=lambda t: t['label'])):
            candidate = deepcopy(payload)
            candidate['tasks'] = deepcopy(order)
            for task in candidate['tasks']:
                task['after'] = list(reversed(task['after']))
            self.assertEqual(PL.schedule_gantt(candidate), expected)

    def test_small_dag_all_permutations(self):
        payload = {'mode': 'relative', 'unit': 'workday', 'lanes': [{'id': 'lane', 'label': '服务', 'owner': '服务组'}],
                   'tasks': [{'id': 'a', 'label': 'A', 'lane': 'lane', 'duration': 2},
                             {'id': 'b', 'label': 'B', 'lane': 'lane', 'duration': 3, 'after': ['a']},
                             {'id': 'c', 'label': 'C', 'lane': 'lane', 'duration': 1, 'after': ['a']},
                             {'id': 'd', 'label': 'D', 'lane': 'lane', 'duration': 2, 'after': ['b', 'c']}]}
        for tasks in itertools.permutations(payload['tasks']):
            with self.subTest(order=[t['id'] for t in tasks]):
                result = PL.schedule_gantt({**payload, 'tasks': list(tasks)})
                self.assertEqual(result['axis_finish'], 7)
                self.assertEqual([t['slack'] for t in result['tasks']], [0, 0, 2, 0])

    def test_cpm_against_independent_path_enumeration(self):
        import random
        randomizer = random.Random(431)
        for scenario in range(20):
            tasks = [{'id': f'n{i}', 'label': f'节点{i}', 'lane': 'lane', 'duration': randomizer.randint(1, 5),
                      'after': [f'n{j}' for j in range(i) if randomizer.random() < .3]} for i in range(7)]
            by_id = {t['id']: t for t in tasks}
            successors = {key: [t['id'] for t in tasks if key in t['after']] for key in by_id}
            paths = []
            def visit(key, path):
                extended = path + [key]
                if not successors[key]:
                    paths.append(extended)
                for child in successors[key]:
                    visit(child, extended)
            for task in tasks:
                if not task['after']:
                    visit(task['id'], [])
            lengths = [(path, sum(by_id[key]['duration'] for key in path)) for path in paths]
            expected_end = max(length for _, length in lengths)
            shuffled = deepcopy(tasks)
            randomizer.shuffle(shuffled)
            result = PL.schedule_gantt({'mode': 'relative', 'unit': 'workday',
                                       'lanes': [{'id': 'lane', 'label': '模块', 'owner': '合成组'}], 'tasks': shuffled})
            with self.subTest(scenario=scenario):
                self.assertEqual(result['axis_finish'], expected_end)
                for task in result['tasks']:
                    longest_through = max(length for path, length in lengths if task['id'] in path)
                    self.assertEqual(task['slack'], expected_end-longest_through)
                    self.assertEqual(task['critical'], longest_through == expected_end)

    def test_dates_keep_authored_intervals_without_cpm(self):
        payload = example('gantt-dates')['payload']
        model = PL.schedule_gantt(payload)
        self.assertEqual(model['unit'], 'calendar-day')
        self.assertEqual(model['axis_finish'] - model['axis_start'], 10)
        original = {t['id']: t for t in payload['tasks']}
        for task in model['tasks']:
            self.assertEqual(task['start'], original[task['id']]['start'])
            self.assertEqual(task['finish'], original[task['id']]['finish'])
            self.assertNotIn('critical', task)
            self.assertNotIn('slack', task)
            self.assertNotIn('latest_start', task)

    def test_capacity_32_tasks_8_lanes(self):
        payload = gantt_payload()
        payload['lanes'] = [{'id': f'l{i}', 'label': f'合成泳道{i}', 'owner': f'组{i}'} for i in range(8)]
        payload['tasks'] = [{'id': f't{i:02}', 'label': f'合成任务{i}', 'lane': f'l{i%8}', 'duration': 1,
                             'after': [f't{i-1:02}'] if i else []} for i in range(32)]
        payload['milestones'] = []
        result = PL.schedule_gantt(payload)
        self.assertEqual(len(result['tasks']), 32)
        self.assertEqual(result['axis_finish'], 32)
        payload['tasks'].append({'id': 'overflow', 'label': '不可接受的第33项', 'lane': 'l0', 'duration': 1})
        with self.assertRaisesRegex(PL.PlanningError, '1–32'):
            PL.schedule_gantt(payload)

    def test_reject_cycle_unknown_duplicate_and_trace_parent(self):
        changes = [
            ('cycle', lambda p: p['tasks'][3].update(after=['verify']), 'cycle'),
            ('unknown', lambda p: p['tasks'][0].update(after=['not-a-task']), 'unknown dependency'),
            ('duplicate id', lambda p: p['tasks'][0].update(id='client'), 'duplicate ID'),
            ('duplicate dependency', lambda p: p['tasks'][0].update(after=['integrate', 'integrate']), 'duplicate dependency'),
            ('trace parent', lambda p: p['tasks'][0].update(parent='trace-42'), 'unsupported'),
            ('unknown lane', lambda p: p['tasks'][0].update(lane='unknown'), 'unknown lane')]
        for label, change, error in changes:
            with self.subTest(label=label):
                payload = gantt_payload()
                change(payload)
                with self.assertRaisesRegex(PL.PlanningError, error):
                    PL.schedule_gantt(payload)

    def test_reject_unsupported_calendar_and_resource_claims(self):
        for field in ('calendar', 'holidays', 'work_week', 'working_week', 'resources', 'resource_schedule'):
            with self.subTest(field=field):
                with self.assertRaisesRegex(PL.PlanningError, 'unsupported'):
                    PL.schedule_gantt({**gantt_payload(), field: []})
        with self.assertRaisesRegex(PL.PlanningError, 'workday'):
            PL.schedule_gantt({**gantt_payload(), 'unit': 'milliseconds'})

    def test_duration_boundary_and_fractional_cpm(self):
        for duration in (0, -1, True, float('inf'), float('nan'), '2', None, 10**1000):
            with self.subTest(duration=duration):
                payload = gantt_payload()
                payload['tasks'][0]['duration'] = duration
                with self.assertRaisesRegex(PL.PlanningError, 'positive'):
                    PL.schedule_gantt(payload)
        payload = gantt_payload()
        for task in payload['tasks']:
            task['duration'] = .1
        self.assertAlmostEqual(PL.schedule_gantt(payload)['axis_finish'], .4)
        self.assertTrue(all(t['slack'] >= 0 for t in PL.schedule_gantt(payload)['tasks']))

    def test_dates_and_relative_do_not_mix(self):
        payload = gantt_payload()
        payload['tasks'][0]['start'] = '2026-11-01'
        with self.assertRaisesRegex(PL.PlanningError, 'unsupported'):
            PL.schedule_gantt(payload)
        for field in ('duration', 'critical', 'slack'):
            with self.subTest(field=field):
                payload = example('gantt-dates')['payload']
                payload['tasks'][0][field] = 1
                with self.assertRaisesRegex(PL.PlanningError, 'unsupported'):
                    PL.schedule_gantt(payload)

    def test_dates_reject_invalid_fs_and_milestone(self):
        for change, error in [
            (lambda p: p['tasks'][0].update(start='2026-11-21'), 'violate finish-to-start'),
            (lambda p: p['tasks'][1].update(finish='2026-11-16'), 'finish must follow'),
            (lambda p: p['tasks'][1].update(start='2026-02-30'), 'invalid ISO date'),
            (lambda p: p['milestones'][0].update(at='2026-11-22'), 'milestone precedes')]:
            payload = example('gantt-dates')['payload']
            change(payload)
            with self.assertRaisesRegex(PL.PlanningError, error):
                PL.schedule_gantt(payload)

    def test_milestone_needs_actual_prerequisites(self):
        payload = gantt_payload()
        payload['milestones'][0]['after'] = []
        with self.assertRaisesRegex(PL.PlanningError, 'dependency list'):
            PL.schedule_gantt(payload)


class TestReleaseTrainModel(unittest.TestCase):
    def test_actual_state_explicit_edges_and_no_mutation(self):
        payload = train_payload()
        before = deepcopy(payload)
        result = PL.validate_release_train(payload)
        self.assertEqual(payload, before)
        self.assertEqual(len(result['phases']), 5)
        self.assertEqual(result['utc_offset_seconds'], 28800)
        self.assertEqual(result['axis_finish'] - result['axis_start'], 11)
        self.assertEqual(len(result['edges']), len(payload['edges']) + 4)
        self.assertEqual(result['tickets'][1]['status'], 'deferred')
        self.assertEqual(result['tickets'][1]['approvals'][0]['state'], 'pending')
        self.assertEqual(sum(e['kind'] == 'requires' for e in result['edges']), 4)

    def test_supplied_emergency_path_and_second_precision(self):
        payload = train_payload()
        payload['exceptions'][0]['kind'] = 'emergency'
        payload['exceptions'][0]['label'] = '合成紧急处理'
        payload['edges'][3]['kind'] = 'emergency'
        result = PL.validate_release_train(payload)
        self.assertEqual(result['exceptions'][0]['kind'], 'emergency')
        self.assertEqual(sum(e['kind'] == 'emergency' for e in result['edges']), 1)
        value = PL._clock('2026-11-16T09:00:01+08:00', 'datetime', 'time', set())
        self.assertEqual(PL._clock_label(result, value, True), '11-16 09:00:01')

    def test_no_unprovided_paths_are_generated(self):
        payload = date_train()
        result = PL.validate_release_train(payload)
        self.assertEqual(result['edges'], [])
        self.assertEqual(result['tickets'], [])
        self.assertEqual(result['gates'], [])
        self.assertEqual(result['exceptions'], [])
        self.assertEqual(result['deployments'], [])

    def test_multiple_window_capacity_and_order(self):
        payload = date_train(4)
        result = PL.validate_release_train(payload)
        self.assertEqual(len(result['windows']), 4)
        self.assertEqual(len(result['branches']), 5)
        payload['windows'].reverse()
        self.assertEqual(PL.validate_release_train(payload)['windows'], result['windows'])
        with self.assertRaisesRegex(PL.PlanningError, '1–4'):
            PL.validate_release_train(date_train(5))

    def test_gate_conditions_and_pending_approval_not_faked(self):
        for change, error in [
            (lambda p: p['gates'][0].update(conditions=[]), 'conditions required'),
            (lambda p: p['gates'][0].update(state='ready'), 'actual gate state'),
            (lambda p: p['tickets'][0]['approvals'][0].update(state='pending'), 'undecided approval'),
            (lambda p: p['tickets'][0]['approvals'][0].pop('approver'), 'recorded_at and approver'),
            (lambda p: p['tickets'][0]['approvals'][0].update(recorded_at='2026-11-16T13:00+08:00'), 'after ticket status'),
            (lambda p: p['gates'][0].update(state='pending'), 'passed prior approval gate'),
            (lambda p: p['gates'][1].update(state='pending'), 'passed exit gate')]:
            with self.subTest(error=error):
                payload = train_payload()
                change(payload)
                with self.assertRaisesRegex(PL.PlanningError, error):
                    PL.validate_release_train(payload)

    def test_reject_unknown_relations_and_unprovided_exceptions(self):
        for change, error in [
            (lambda p: p['edges'][0].update(to='unknown'), 'unknown edge endpoint'),
            (lambda p: p['edges'][0].update(kind='auto-approve'), 'unknown edge kind'),
            (lambda p: p['edges'][0].pop('at'), 'explicit at'),
            (lambda p: p['edges'][3].pop('condition'), 'condition'),
            (lambda p: p['edges'].pop(3), 'explicit path'),
            (lambda p: p['tickets'][0].update(branch='master'), 'release branch'),
            (lambda p: p['tickets'][0].update(approval_gate='exit-gate'), 'approval gate')]:
            with self.subTest(error=error):
                payload = train_payload()
                change(payload)
                with self.assertRaisesRegex(PL.PlanningError, error):
                    PL.validate_release_train(payload)

    def test_datetime_requires_real_timezone_and_consistent_offset(self):
        for value, error in [('09:00', 'timezone'), ('2026-11-16T09:00', 'timezone'),
                             ('2026-11-16T09:00+09:00', 'one explicit UTC offset'),
                             ('2026-02-30T09:00+08:00', 'invalid ISO datetime')]:
            payload = train_payload()
            payload['windows'][0]['start'] = value
            with self.assertRaisesRegex(PL.PlanningError, error):
                PL.validate_release_train(payload)

    def test_interval_branch_and_phase_boundaries(self):
        for change, error in [
            (lambda p: p['windows'][0]['phases'][1].update(start='2026-11-16T11:00+08:00'), 'overlapping phase'),
            (lambda p: p['windows'][0]['phases'][0].update(start='2026-11-16T08:00+08:00'), 'outside'),
            (lambda p: p['branches'][1].update(start='2026-11-16T10:00+08:00'), 'outside'),
            (lambda p: p['branches'][0].update(kind='release', window='w1'), 'one release branch'),
            (lambda p: p['gates'][0].update(phase='freeze'), 'outside'),
            (lambda p: p['deployments'][0].update(start='2026-11-16T13:59+08:00'), 'outside')]:
            with self.subTest(error=error):
                payload = train_payload()
                change(payload)
                with self.assertRaisesRegex(PL.PlanningError, error):
                    PL.validate_release_train(payload)

    def test_date_mode_and_gaps_preserve_given_data(self):
        payload = date_train()
        phase = payload['windows'][0]['phases'][0]
        phase['finish'] = '2026-01-04'
        payload['windows'][0]['phases'].append({'id': 'gap-tail', 'label': '观察', 'kind': 'observe',
                                               'start': '2026-01-05', 'finish': '2026-01-07'})
        result = PL.validate_release_train(payload)
        self.assertEqual(result['phases'][1]['start_value'] - result['phases'][0]['finish_value'], 1)
        self.assertEqual(len(result['phases']), 2)
        self.assertIsNone(result['utc_offset_seconds'])

    def test_legacy_release_is_not_a_train(self):
        with self.assertRaisesRegex(PL.PlanningError, 'unsupported'):
            PL.validate_release_train({**date_train(), 'ready': ['one'], 'deferred': []})


class TestAxisAndRouting(unittest.TestCase):
    def test_measured_axis_retains_endpoints(self):
        for extent in ((0, 10), (0, .4), (0, 3660), (739930, 739931), (12.5, 28.25)):
            with self.subTest(extent=extent):
                ticks = PL.axis_ticks(*extent, 560, 100)
                self.assertEqual((ticks[0], ticks[-1]), extent)
                self.assertEqual(ticks, sorted(set(ticks)))
                self.assertLessEqual(len(ticks), 8)
        self.assertEqual(PL.axis_ticks(0, 1, 560, 100, True), [0, 1])
        with self.assertRaisesRegex(PL.PlanningError, 'invalid axis'):
            PL.axis_ticks(0, 0, 560, 100)

    def test_route_avoids_intervening_bar_in_both_directions(self):
        a, b, obstacle = (300, 100, 100, 24), (500, 300, 120, 24), (350, 190, 180, 24)
        for source, target in ((a, b), (b, a)):
            with self.subTest(direction=target[1]-source[1]):
                points = PL.route_dependency(source, target, [a, b, obstacle], 280, 650, 6)
                vertical = [(p, q) for p, q in zip(points, points[1:]) if p[0] == q[0] and p[1] != q[1]]
                for p, q in vertical:
                    if min(p[1], q[1]) < obstacle[1]+obstacle[3] and max(p[1], q[1]) > obstacle[1]:
                        self.assertFalse(obstacle[0] < p[0] < obstacle[0]+obstacle[2])
                self.assertTrue(all(280 <= p[0] <= 650 for p in points))

    def test_clear_route_does_not_detour_needlessly(self):
        a, b, other = (300, 100, 100, 24), (500, 300, 120, 24), (450, 190, 100, 24)
        points = PL.route_dependency(a, b, [a, b, other], 280, 650, 6)
        self.assertEqual(points[2][0], 400)


class TestPlanningCanvas(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory(prefix='planning-canvas-')
        self.addCleanup(self.workspace.cleanup)
        scripts = str(ROOT / 'scripts')
        sys.path.insert(0, scripts)
        self.addCleanup(lambda: sys.path.remove(scripts))

    def draw(self, name):
        source = example(name)
        spec = {**source['payload'], **source['meta'], 'layout': source['type'], 'id': source['meta']['id']}
        canvas = PL.BUILDERS[source['type']](spec)
        target = Path(self.workspace.name) / (name + '.svg')
        compiled = canvas.save(target)
        return canvas, compiled, ET.fromstring(target.read_text())

    def test_capacity_canvas_date_ticks_and_complete_rows(self):
        for name in ('gantt-capacity', 'release-capacity'):
            with self.subTest(name=name):
                canvas, compiled, svg = self.draw(name)
                model = canvas.planning_model
                self.assertEqual(compiled['width'], canvas.width)
                self.assertEqual(len(compiled['scene_graph']['edges']), len(model['edges']))
                labels = [item for item in compiled['labels'] if item['text'].startswith('2026-')]
                for a, b in itertools.combinations(labels, 2):
                    if a['y'] != b['y']:
                        continue
                    ax = a['x'] - (a['width']/2 if a['anchor'] == 'middle' else a['width'] if a['anchor'] == 'end' else 0)
                    bx = b['x'] - (b['width']/2 if b['anchor'] == 'middle' else b['width'] if b['anchor'] == 'end' else 0)
                    self.assertTrue(ax+a['width'] <= bx or bx+b['width'] <= ax)
                if name == 'gantt-capacity':
                    self.assertEqual(len(model['tasks']), 24)
                else:
                    self.assertEqual(len(model['windows']), 2)
                    self.assertEqual(len(model['tickets']), 4)

    def test_gantt_actual_canvas_and_explicit_scene(self):
        for name in ('gantt-relative', 'gantt-dates'):
            with self.subTest(name=name):
                canvas, compiled, svg = self.draw(name)
                model = canvas.planning_model
                objects = {o['id']: o for o in compiled['scene_graph']['objects']}
                self.assertEqual(compiled['width'], canvas.width)
                self.assertEqual(len(objects), len(model['lanes'])+len(model['tasks'])+len(model['milestones']))
                self.assertEqual(len(compiled['scene_graph']['edges']), len(model['edges']))
                for lane in model['lanes']:
                    self.assertEqual(objects[lane['id']]['membership']['members'],
                                     [t['id'] for t in model['tasks'] if t['lane'] == lane['id']])
                self.assertEqual({e['kind'] for e in compiled['scene_graph']['edges']},
                                 {'finish-to-start', 'completion-prerequisite'})
                text = ''.join(el.text or '' for el in svg.iter() if el.tag.endswith('text'))
                self.assertIn('里程碑', text)
                if name == 'gantt-relative':
                    self.assertIn('不做资源调度', text)
                else:
                    self.assertIn('不推算关键路径、余量或资源', text)
                if name == 'gantt-dates':
                    self.assertTrue(all('critical' not in objects[t['id']]['content'] for t in model['tasks']))

    def test_release_actual_canvas_complete_objects_edges_and_conditions(self):
        canvas, compiled, svg = self.draw('release-train')
        model = canvas.planning_model
        objects = {o['id']: o for o in compiled['scene_graph']['objects']}
        kinds = {o['kind'] for o in objects.values()}
        self.assertTrue({'train', 'window', 'phase', 'branch', 'ticket', 'gate', 'deployment', 'exception'} <= kinds)
        self.assertEqual(len(compiled['scene_graph']['edges']), len(model['edges']))
        self.assertEqual(objects['ticket-cache']['content']['status'], 'deferred')
        self.assertEqual(objects['ticket-cache']['content']['approvals'][0]['state'], 'pending')
        text = ''.join(el.text or '' for el in svg.iter() if el.tag.endswith('text'))
        self.assertIn('候选 SHA', text)
        self.assertIn('未声明已发生回退', text)
        self.assertEqual(objects['exit-gate']['content']['conditions'], train_payload()['gates'][1]['conditions'])


class TestReleaseSupplemental(unittest.TestCase):
    """Reader-visible conditions are separate from complete explanatory records."""
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory(prefix='release-supplemental-')
        self.addCleanup(self.workspace.cleanup)
        scripts = str(ROOT / 'scripts')
        sys.path.insert(0, scripts)
        self.addCleanup(lambda: sys.path.remove(scripts))

    def draw_source(self, source):
        before = deepcopy(source)
        canvas = PL.release_train({**source['payload'], **source['meta']})
        target = Path(self.workspace.name) / 'release.svg'
        compiled = canvas.save(target)
        self.assertEqual(source, before)
        text = ''.join(el.text or '' for el in ET.fromstring(target.read_text()).iter()
                       if el.tag.endswith('text'))
        return canvas, compiled, text

    def test_complete_records_conditions_and_control_model(self):
        source = example('release-train')
        canvas, compiled, text = self.draw_source(source)
        supplemental = canvas.supplemental
        self.assertEqual(set(supplemental), {'title', 'sections'})
        sections = {s['id']: s for s in supplemental['sections']}
        self.assertEqual(len(sections), len(supplemental['sections']))
        for kind, items in (('ticket', source['payload']['tickets']),
                            ('gate', source['payload']['gates']),
                            ('deployment', source['payload']['deployments']),
                            ('exception', source['payload']['exceptions'])):
            for item in items:
                section = sections[kind + ':' + item['id']]
                self.assertEqual(section['title'], item['label'])
                values = [row['value'] for row in section['rows']]
                for key in ('detail', 'scope', 'condition'):
                    if key in item:
                        self.assertIn(item[key], values)
                for condition in item.get('conditions', []):
                    self.assertIn(condition, values)
                    self.assertIn(condition, text)
                for approval in item.get('approvals', []):
                    for key in ('label', 'state', 'approver', 'recorded_at'):
                        if key in approval:
                            self.assertIn(approval[key], values)
                    for condition in approval.get('conditions', []):
                        self.assertIn(condition, values)
                        self.assertIn(condition, text)
                if 'condition' in item:
                    self.assertIn(item['condition'], text)
        self.assertEqual(canvas.planning_model, PL.validate_release_train(source['payload']))
        expected = [(e['id'], e['from'], e['to'], e['kind'], e['label'])
                    for e in canvas.planning_model['edges']]
        self.assertEqual(expected, [(e['id'], e['from'], e['to'], e['kind'], e['label'])
                                    for e in compiled['scene_graph']['edges']])
        for edge in canvas.planning_model['edges']:
            values = [row['value'] for row in sections['edge:' + edge['id']]['rows']]
            self.assertIn(edge['label'], values)
            if edge.get('condition'):
                self.assertIn(edge['condition'], values)
                self.assertIn(edge['condition'], text)
        self.assertIn('冻结后不再新增普通车票', text)
        self.assertIn('不会自动上车', text)
        self.assertIn('未声明已发生回退', text)
        self.assertNotIn('合成 API reviewer', text)
        self.assertNotIn('审批记录与条件', text)

    def test_long_platform_records_do_not_expand_main_graph(self):
        source = example('release-train')
        before, _, before_text = self.draw_source(source)
        long = deepcopy(source)
        narrative = '平台流水记录已归档，候选编号与记录附件逐项核对。' * 45
        for ticket in long['payload']['tickets']:
            ticket['detail'] = ticket.get('detail', '') + '\n' + narrative
            for approval in ticket['approvals']:
                if 'approver' in approval:
                    approval['approver'] += '\n' + narrative
        for phase in long['payload']['windows'][0]['phases']:
            phase['detail'] = phase.get('detail', '') + '\n' + narrative
        for item in long['payload']['gates'] + long['payload']['deployments'] + long['payload']['exceptions']:
            item['detail'] = item.get('detail', '') + '\n' + narrative
        after, _, after_text = self.draw_source(long)
        self.assertEqual(after.height, before.height)
        self.assertEqual(after_text, before_text)
        values = [r['value'] for s in after.supplemental['sections'] for r in s['rows']]
        self.assertTrue(any(narrative in v for v in values))
        for phase in long['payload']['windows'][0]['phases']:
            section = next(s for s in after.supplemental['sections'] if s['id'] == 'phase:' + phase['id'])
            self.assertIn(phase['detail'], [r['value'] for r in section['rows']])

    def test_late_business_constraints_and_long_conditions_are_not_truncated(self):
        source = example('release-train')
        restriction = '仅当兼容审查全部通过且候选 SHA 与验收包一致时才允许上车；否则拒绝。'
        source['payload']['windows'][0]['phases'][1]['detail'] = (
            '平台流水记录已归档。' * 30 + restriction)
        source['payload']['gates'][1]['conditions'].append(restriction)
        source['payload']['tickets'][1]['approvals'][0]['conditions'].append(restriction)
        canvas, _, text = self.draw_source(source)
        self.assertIn(restriction, text)
        self.assertIn('否则拒绝', text)
        values = [r['value'] for s in canvas.supplemental['sections'] for r in s['rows']]
        self.assertGreaterEqual(values.count(restriction), 2)

    def test_two_windows_four_tickets_keep_all_entities_and_supplemental_ids(self):
        source = example('release-capacity')
        canvas, compiled, text = self.draw_source(source)
        model = canvas.planning_model
        self.assertEqual(len(model['windows']), 2)
        self.assertEqual(len(model['tickets']), 4)
        objects = {o['id']: o for o in compiled['scene_graph']['objects']}
        for kind in ('windows', 'phases', 'branches', 'tickets', 'gates', 'deployments'):
            for item in model[kind]:
                self.assertIn(item['id'], objects)
                self.assertEqual(objects[item['id']]['content']['label'], item['label'])
        ids = [s['id'] for s in canvas.supplemental['sections']]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(canvas.planning_model, PL.validate_release_train(source['payload']))
        self.assertEqual(len(compiled['scene_graph']['edges']), len(model['edges']))

    def test_canvas_save_preserves_supplemental(self):
        canvas, compiled, _ = self.draw_source(example('release-train'))
        self.assertIn('supplemental', compiled,
                      'Shared Canvas.save must preserve the planning supplemental contract')
        self.assertEqual(compiled['supplemental'], canvas.supplemental)

    def test_source_note_and_sample_remain_visible(self):
        source = example('release-train')
        source['meta']['note'] = '只展示给定发布计划，不代表真实执行结果。'
        source['payload']['sample'] = True
        _, _, text = self.draw_source(source)
        self.assertIn(source['meta']['note'], text)
        self.assertIn('合成示例', text)


if __name__ == '__main__':
    pure = '--pure' in sys.argv
    if pure:
        sys.argv.remove('--pure')
        suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(cls)
                                   for cls in (TestGanttModel, TestReleaseTrainModel, TestAxisAndRouting))
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        raise SystemExit(not result.wasSuccessful())
    unittest.main(verbosity=2)
