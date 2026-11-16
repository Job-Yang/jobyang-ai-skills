"""Bounded planning layouts. No demo business rules, calendars or schedulers.

Public builders: BUILDERS['gantt'|'release-train'] -> the shared Canvas.
Pure models: schedule_gantt(payload), validate_release_train(payload).

Gantt v1
========
lanes: 1..8 {id,label,owner}; tasks: 1..32 {id,label,lane,owner?}.
An omitted task owner inherits its explicitly referenced lane owner.
mode='relative', unit='workday': tasks have positive duration and after=[task IDs].
This is an abstract workday FS DAG with unlimited resources, no lag or calendar.
mode='dates': tasks have ISO start/finish dates, half-open [start,finish), optional
FS after references; provided intervals are checked, never rescheduled. No CPM.
Optional milestones (<=16) have {id,label,after} in relative mode, or {id,label,at,
after?} in dates mode. References point to tasks, not traces or visual parents.
All IDs are globally unique. Unknown dependencies/cycles/mixed modes are errors.

Release-train v1
================
One train {id,label}, time_mode='date' or 'datetime' (timezone required; one
explicit UTC offset throughout), 1..4 disjoint windows {id,label,start,finish,
phases:[{id,label,kind,start,finish,detail?}]}. Phase segments are bounded,
nonoverlapping; gaps remain gaps. kind is integration/freeze/deploy/canary/
observe/close/custom. One master branch and exactly one release branch per window:
branches=[{id,label,kind,window?,start,finish}]. Branches must cover their windows.
Tickets (<=24): {id,label,window,branch,at,status,approval_gate,
approvals:[{label,state,recorded_at?,approver?,conditions?}],detail?}.
Ticket status: pending/approved/rejected/boarded/deferred. Approval records are
actual supplied state (pending/approved/rejected), not layout decoration.
Gates (<=16): {id,label,window,phase,at,kind,state,conditions:[nonempty strings]}.
kind=ticket-approval|exit; state=pending|passed|blocked; no state is inferred.
Deployments (<=16): {id,label,window,phase,branch,start,finish,gate,state,scope,
detail?}; state=planned|running|complete|blocked. Scope is supplied text, not an
invented traffic percentage. An executing deployment requires a passed gate.
Optional exceptions (<=8): {id,label,kind,window,branch,at,condition,detail?},
kind=rollback|emergency. They require an explicitly supplied corresponding edge.
Optional edges (<=96): {id,from,to,kind,label,at?,condition?}; kind=branch/merge/
board/progression/rollback/emergency. Only supplied edges are control paths.
Explicit gate references create requires edges; no geometric path inference.

Examples are synthetic and say so. Formats are source/scene/HTML/SVG/PNG via the
existing runtime; no draw.io support is claimed by these layouts.
"""
from copy import deepcopy
from datetime import date, datetime
import heapq
import math
import re


class PlanningError(ValueError):
    """An authored planning contract is invalid or unsupported."""


def _check(ok, message):
    if not ok:
        raise PlanningError(message)


def _text(value, where):
    _check(isinstance(value, str) and bool(value.strip()), f'{where}: nonempty string required')
    return value


def _number(value, where, positive=False):
    numeric = isinstance(value, (int, float)) and not isinstance(value, bool)
    try:
        finite = numeric and math.isfinite(value)
    except OverflowError:
        finite = False
    _check(finite and (value > 0 if positive else value >= 0),
           f'{where}: finite {"positive" if positive else "nonnegative"} number required')
    return value


def _records(value, where, minimum, maximum):
    _check(isinstance(value, list) and minimum <= len(value) <= maximum,
           f'{where}: supports {minimum}–{maximum} records')
    _check(all(isinstance(item, dict) for item in value), f'{where}: objects required')
    return value


def _index(items, where, used=None):
    used = set() if used is None else used
    result = {}
    for item in items:
        key = _text(item.get('id'), f'{where}.id')
        _check(re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]*', key), f'{where}.id: use stable identifier')
        _check(key not in used, f'duplicate ID: {key}')
        used.add(key)
        _text(item.get('label'), f'{where}[{key}].label')
        if 'detail' in item:
            _check(isinstance(item['detail'], str), f'{key}.detail: string required')
        result[key] = item
    return result


def _refs(value, lookup, where, required=False):
    _check(isinstance(value, list) and (not required or value), f'{where}: dependency list required')
    _check(all(isinstance(ref, str) for ref in value), f'{where}: string IDs required')
    _check(len(set(value)) == len(value), f'{where}: duplicate dependency')
    _check(all(ref in lookup for ref in value), f'{where}: unknown dependency')
    return sorted(value)


def _topological(lookup):
    successors = {key: [] for key in lookup}
    indegree = {}
    for key, item in lookup.items():
        indegree[key] = len(item['after'])
        for dep in item['after']:
            successors[dep].append(key)
    ready = [key for key, count in indegree.items() if count == 0]
    heapq.heapify(ready)
    order = []
    while ready:
        key = heapq.heappop(ready)
        order.append(key)
        for child in sorted(successors[key]):
            indegree[child] -= 1
            if indegree[child] == 0:
                heapq.heappush(ready, child)
    _check(len(order) == len(lookup), 'cycle in finish-to-start dependencies')
    return order, successors


def _date(value, where):
    _check(isinstance(value, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', value),
           f'{where}: ISO date YYYY-MM-DD required')
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise PlanningError(f'{where}: invalid ISO date') from exc


def _unsupported(p, fields):
    found = sorted(set(p) & set(fields))
    _check(not found, 'unsupported planning fields: ' + ', '.join(found))


def schedule_gantt(payload):
    """Validate and compute a deterministic FS DAG, or validate supplied dates.

    Returns JSON-safe data. start_value/finish_value are axis coordinates;
    authored start/finish in dates mode remain intact. Does not mutate input.
    """
    _check(isinstance(payload, dict), 'gantt payload: object required')
    p = deepcopy(payload)
    _unsupported(p, ('calendar', 'holidays', 'work_week', 'working_week', 'resources',
                     'resource_schedule', 'timezone', 'lag'))
    mode = p.get('mode')
    _check(mode in ('relative', 'dates'), 'gantt mode must be relative or dates')
    _check(p.get('unit') == 'workday' if mode == 'relative' else p.get('unit') in (None, 'calendar-day'),
           'relative uses unit=workday; dates use calendar-day intervals')
    used = set()
    lanes = _records(p.get('lanes'), 'lanes', 1, 8)
    lane_map = _index(lanes, 'lanes', used)
    for lane in lanes:
        _text(lane.get('owner'), f'{lane["id"]}.owner')
    tasks = _records(p.get('tasks'), 'tasks', 1, 32)
    lookup = _index(tasks, 'tasks', used)
    for task in tasks:
        key = task['id']
        _check(isinstance(task.get('lane'), str) and task['lane'] in lane_map, f'{key}: unknown lane')
        task['owner'] = _text(task.get('owner', lane_map[task['lane']]['owner']), f'{key}.owner')
        task['after'] = _refs(task.get('after', []), lookup, f'{key}.after')
        _unsupported(task, ('parent', 'lag', 'resources', 'critical', 'slack', 'latest_start', 'latest_finish'))
        if mode == 'relative':
            _unsupported(task, ('start', 'finish', 'date', 'at'))
            _number(task.get('duration'), f'{key}.duration', True)
        else:
            _unsupported(task, ('duration',))
            start, finish = _date(task.get('start'), f'{key}.start'), _date(task.get('finish'), f'{key}.finish')
            _check(start < finish, f'{key}: finish must follow start in [start,finish)')
            task['start_value'], task['finish_value'] = start.toordinal(), finish.toordinal()
            task['duration_value'] = (finish - start).days
    _check(sum(len(t['after']) for t in tasks) <= 96, 'gantt supports at most 96 FS dependencies')
    order, successors = _topological(lookup)
    if mode == 'relative':
        for key in order:
            task = lookup[key]
            task['start_value'] = max((lookup[d]['finish_value'] for d in task['after']), default=0)
            task['finish_value'] = task['start_value'] + task['duration']
            task['start'], task['finish'] = task['start_value'], task['finish_value']
            task['duration_value'] = task['duration']
        end = max(t['finish_value'] for t in tasks)
        _check(end <= 3660, 'relative span exceeds 3660 abstract workdays; use focused plans')
        for key in reversed(order):
            task = lookup[key]
            task['latest_finish'] = min((lookup[s]['latest_start'] for s in successors[key]), default=end)
            task['latest_start'] = task['latest_finish'] - task['duration']
            slack = task['latest_start'] - task['start_value']
            task['slack'] = 0 if abs(slack) <= 1e-9 else slack
            task['critical'] = abs(slack) <= 1e-9
        axis_start = 0
    else:
        for key in order:
            task = lookup[key]
            _check(all(lookup[d]['finish_value'] <= task['start_value'] for d in task['after']),
                   f'{key}: provided dates violate finish-to-start dependency')
        axis_start = min(t['start_value'] for t in tasks)
        end = max(t['finish_value'] for t in tasks)
    milestones = _records(p.get('milestones', []), 'milestones', 0, 16)
    _index(milestones, 'milestones', used)
    for item in milestones:
        _unsupported(item, ('critical', 'slack', 'duration', 'start', 'finish', 'parent'))
        item['after'] = _refs(item.get('after', []), lookup, f'{item["id"]}.after', mode == 'relative')
        if mode == 'relative':
            _unsupported(item, ('at', 'date'))
            item['at_value'] = max(lookup[d]['finish_value'] for d in item['after'])
        else:
            item['at_value'] = _date(item.get('at'), f'{item["id"]}.at').toordinal()
            _check(all(lookup[d]['finish_value'] <= item['at_value'] for d in item['after']),
                   f'{item["id"]}: milestone precedes a prerequisite finish')
        axis_start, end = min(axis_start, item['at_value']), max(end, item['at_value'])
    if mode == 'dates':
        _check(end - axis_start <= 3660, 'date span exceeds 3660 calendar days; use focused plans')
    edges = [{'id': f'fs-{dep}-{key}', 'from': dep, 'to': key,
              'kind': 'finish-to-start', 'label': 'FS', 'directed': True}
             for key in order for dep in lookup[key]['after']]
    edges += [{'id': f'completion-{dep}-{m["id"]}', 'from': dep, 'to': m['id'],
               'kind': 'completion-prerequisite', 'label': '完成前置', 'directed': True}
              for m in milestones for dep in m['after']]
    limitations = (['FS DAG；无限资源；不做资源调度', '抽象工作日估算；未计工作周、节假日、等待与不确定性']
                   if mode == 'relative' else ['日期区间 [开始,结束)；按日历日定位，不改给定排期',
                                               '不计算关键路径或余量；未计工作周、节假日，不做资源调度'])
    return {'mode': mode, 'unit': 'workday' if mode == 'relative' else 'calendar-day',
            'lanes': lanes, 'tasks': [lookup[key] for key in order], 'milestones': milestones,
            'axis_start': axis_start, 'axis_finish': end, 'edges': edges, 'limitations': limitations}


def _clock(value, mode, where, offsets):
    if mode == 'date':
        return _date(value, where).toordinal()
    _check(isinstance(value, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:\d{2})', value),
           f'{where}: ISO datetime with timezone required')
    try:
        instant = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise PlanningError(f'{where}: invalid ISO datetime') from exc
    offsets.add(instant.utcoffset().total_seconds())
    _check(len(offsets) == 1, 'datetime inputs must use one explicit UTC offset')
    return instant.timestamp() / 3600


def validate_release_train(payload):
    """Validate one train and explicit operational state; never simulate approval."""
    _check(isinstance(payload, dict), 'release-train payload: object required')
    p = deepcopy(payload)
    _unsupported(p, ('calendar', 'holidays', 'work_week', 'working_week', 'ready', 'deferred', 'fixed_phases'))
    mode = p.get('time_mode')
    _check(mode in ('date', 'datetime'), 'release-train time_mode must be date or datetime')
    used, offsets = set(), set()
    train = p.get('train')
    _check(isinstance(train, dict), 'train: object required')
    _index([train], 'train', used)
    windows = _records(p.get('windows'), 'windows', 1, 4)
    wm = _index(windows, 'windows', used)

    def at(item, key):
        item[key + '_value'] = _clock(item.get(key), mode, f'{item["id"]}.{key}', offsets)
        return item[key + '_value']

    def interval(item):
        _check(at(item, 'start') < at(item, 'finish'), f'{item["id"]}: finish must follow start')

    def within(item, container, point=False):
        a, b = (item['at_value'], item['at_value']) if point else (item['start_value'], item['finish_value'])
        _check(container['start_value'] <= a <= b <= container['finish_value'],
               f'{item["id"]}: time outside {container["id"]}')

    phases, pm = [], {}
    for window in windows:
        interval(window)
        parts = _records(window.get('phases'), f'{window["id"]}.phases', 1, 8)
        pm.update(_index(parts, 'phases', used))
        for phase in parts:
            _check(phase.get('kind') in ('integration', 'freeze', 'deploy', 'canary', 'observe', 'close', 'custom'),
                   f'{phase["id"]}: unknown phase kind')
            phase['window'] = window['id']
            interval(phase)
            within(phase, window)
        parts.sort(key=lambda s: (s['start_value'], s['id']))
        _check(all(a['finish_value'] <= b['start_value'] for a, b in zip(parts, parts[1:])),
               f'{window["id"]}: overlapping phase segments are unsupported')
        phases.extend(parts)
    windows.sort(key=lambda s: (s['start_value'], s['id']))
    _check(all(a['finish_value'] <= b['start_value'] for a, b in zip(windows, windows[1:])),
           'single train windows must be disjoint')
    branches = _records(p.get('branches'), 'branches', 2, 5)
    bm = _index(branches, 'branches', used)
    masters = []
    release_for = {}
    for branch in branches:
        _check(branch.get('kind') in ('master', 'release'), f'{branch["id"]}: unknown branch kind')
        interval(branch)
        if branch['kind'] == 'master':
            _check('window' not in branch, 'master is train-wide; do not assign a window')
            masters.append(branch)
        else:
            _check(branch.get('window') in wm, f'{branch["id"]}: unknown window')
            _check(branch['window'] not in release_for, 'exactly one release branch per window')
            release_for[branch['window']] = branch
            within(wm[branch['window']], branch)
    _check(len(masters) == 1 and set(release_for) == set(wm),
           'requires one master and one release branch for each window')
    for window in windows:
        within(window, masters[0])
    gates = _records(p.get('gates', []), 'gates', 0, 16)
    gm = _index(gates, 'gates', used)
    for gate in gates:
        _check(gate.get('window') in wm and gate.get('phase') in pm, f'{gate["id"]}: unknown window or phase')
        _check(pm[gate['phase']]['window'] == gate['window'], f'{gate["id"]}: phase belongs to another window')
        _check(gate.get('kind') in ('ticket-approval', 'exit'), f'{gate["id"]}: invalid gate kind')
        _check(gate.get('state') in ('pending', 'passed', 'blocked'), f'{gate["id"]}: actual gate state required')
        conditions = gate.get('conditions')
        _check(isinstance(conditions, list) and 1 <= len(conditions) <= 8, f'{gate["id"]}: 1–8 gate conditions required')
        for condition in conditions:
            _text(condition, f'{gate["id"]}.conditions')
        at(gate, 'at')
        within(gate, pm[gate['phase']], True)
    tickets = _records(p.get('tickets', []), 'tickets', 0, 24)
    tm = _index(tickets, 'tickets', used)

    def assignment(item):
        _check(item.get('window') in wm and item.get('branch') in bm, f'{item["id"]}: unknown window or branch')
        _check(bm[item['branch']]['kind'] == 'release' and bm[item['branch']].get('window') == item['window'],
               f'{item["id"]}: must reference its window release branch')

    for ticket in tickets:
        assignment(ticket)
        at(ticket, 'at')
        within(ticket, wm[ticket['window']], True)
        gate = gm.get(ticket.get('approval_gate'))
        _check(gate and gate['kind'] == 'ticket-approval' and gate['window'] == ticket['window'],
               f'{ticket["id"]}: actual ticket approval gate required')
        _check(ticket.get('status') in ('pending', 'approved', 'rejected', 'boarded', 'deferred'),
               f'{ticket["id"]}: invalid ticket status')
        approvals = _records(ticket.get('approvals'), f'{ticket["id"]}.approvals', 1, 8)
        for approval in approvals:
            _text(approval.get('label'), 'approval.label')
            _check(approval.get('state') in ('pending', 'approved', 'rejected'), 'approval: actual state required')
            if 'approver' in approval:
                _text(approval['approver'], 'approval.approver')
            if 'recorded_at' in approval:
                clock = _clock(approval['recorded_at'], mode, 'approval.recorded_at', offsets)
                _check(clock <= ticket['at_value'], 'approval record occurs after ticket status timestamp')
            if approval['state'] in ('approved', 'rejected'):
                _check('recorded_at' in approval and 'approver' in approval,
                       'decided approval requires recorded_at and approver')
            if 'conditions' in approval:
                _check(isinstance(approval['conditions'], list), 'approval.conditions: list required')
                for condition in approval['conditions']:
                    _text(condition, 'approval.conditions')
        if ticket['status'] in ('approved', 'boarded'):
            _check(all(a['state'] == 'approved' for a in approvals), 'approved/boarded ticket has undecided approval')
        if ticket['status'] == 'boarded':
            _check(gate['state'] == 'passed' and gate['at_value'] <= ticket['at_value'],
                   'boarded ticket requires a passed prior approval gate')
    deployments = _records(p.get('deployments', []), 'deployments', 0, 16)
    dm = _index(deployments, 'deployments', used)
    for item in deployments:
        assignment(item)
        _check(item.get('phase') in pm and pm[item['phase']]['window'] == item['window'],
               f'{item["id"]}: unknown or mismatched deployment phase')
        _check(pm[item['phase']]['kind'] in ('deploy', 'canary', 'observe', 'custom'),
               f'{item["id"]}: deployment requires a deployment/observation phase')
        interval(item)
        within(item, pm[item['phase']])
        _text(item.get('scope'), f'{item["id"]}.scope')
        _check(item.get('state') in ('planned', 'running', 'complete', 'blocked'), f'{item["id"]}: invalid deployment state')
        gate = gm.get(item.get('gate'))
        _check(gate and gate['kind'] == 'exit' and gate['window'] == item['window'],
               f'{item["id"]}: actual exit gate required')
        _check(gate['at_value'] <= item['start_value'], f'{item["id"]}: gate must precede deployment')
        if item['state'] in ('running', 'complete'):
            _check(gate['state'] == 'passed', 'executing deployment requires a passed exit gate')
    exceptions = _records(p.get('exceptions', []), 'exceptions', 0, 8)
    em = _index(exceptions, 'exceptions', used)
    for item in exceptions:
        assignment(item)
        _check(item.get('kind') in ('rollback', 'emergency'), f'{item["id"]}: invalid exception kind')
        _text(item.get('condition'), f'{item["id"]}.condition')
        at(item, 'at')
        within(item, wm[item['window']], True)
    all_nodes = {**bm, **pm, **gm, **tm, **dm, **em}
    edges = _records(p.get('edges', []), 'edges', 0, 96)
    edge_ids = set(used)
    for edge in edges:
        key = _text(edge.get('id'), 'edge.id')
        _check(key not in edge_ids, f'duplicate ID: {key}')
        edge_ids.add(key)
        _check(isinstance(edge.get('from'), str) and edge['from'] in all_nodes
               and isinstance(edge.get('to'), str) and edge['to'] in all_nodes, f'{key}: unknown edge endpoint')
        _check(edge['from'] != edge['to'], f'{key}: self edge unsupported')
        _check(edge.get('kind') in ('branch', 'merge', 'board', 'progression', 'rollback', 'emergency'), f'{key}: unknown edge kind')
        _text(edge.get('label'), f'{key}.label')
        if 'condition' in edge:
            _text(edge['condition'], f'{key}.condition')
        if 'at' in edge:
            at(edge, 'at')
        a, b = all_nodes[edge['from']], all_nodes[edge['to']]
        if edge['kind'] in ('branch', 'merge'):
            _check(edge['from'] in bm and edge['to'] in bm and 'at' in edge,
                   f'{key}: branch/merge needs two branches and explicit at')
            _check((a['kind'], b['kind']) == (('master', 'release') if edge['kind'] == 'branch' else ('release', 'master')),
                   f'{key}: invalid branch/merge direction')
            within(edge, a, True)
            within(edge, b, True)
        if edge['kind'] == 'board':
            _check(edge['from'] in tm and edge['to'] in bm and a['status'] == 'boarded' and a['branch'] == b['id'],
                   f'{key}: board edge requires an actually boarded ticket and its branch')
        if edge['kind'] in ('rollback', 'emergency'):
            _check(edge.get('condition') and (a.get('kind') == edge['kind'] or b.get('kind') == edge['kind']),
                   f'{key}: exception path requires its supplied exception and condition')
        edge['directed'] = True
    for item in exceptions:
        _check(any(e['kind'] == item['kind'] and item['id'] in (e['from'], e['to']) for e in edges),
               f'{item["id"]}: exception requires an explicit path')
    for item in tickets + deployments:
        gate_id = item['approval_gate'] if item['id'] in tm else item['gate']
        key = f'requires-{gate_id}-{item["id"]}'
        _check(key not in edge_ids, f'duplicate generated relation ID: {key}')
        edge_ids.add(key)
        edges.append({'id': key, 'from': gate_id, 'to': item['id'], 'kind': 'requires',
                      'label': '审批前置' if item['id'] in tm else '准出前置', 'directed': True})
    axis_start = min(b['start_value'] for b in branches)
    axis_finish = max(b['finish_value'] for b in branches)
    _check(axis_finish - axis_start <= (366 * 24 if mode == 'datetime' else 366),
           'release train span exceeds 366 days; use focused trains')
    return {'train': train, 'time_mode': mode, 'windows': windows, 'phases': phases,
            'branches': branches, 'tickets': tickets, 'gates': gates, 'deployments': deployments,
            'exceptions': exceptions, 'edges': edges, 'axis_start': axis_start,
            'axis_finish': axis_finish, 'utc_offset_seconds': next(iter(offsets)) if offsets else None,
            'limitations': ['单列车；窗口和阶段使用给定时间；不模拟审批或实际发布',
                            '仅显示给定分支关系、准出条件和异常路径；不补团队规则']}


def axis_ticks(start, finish, pixels, label_pixels, integral=False):
    """Measured tick budget on a single linear axis; retain both true endpoints."""
    _check(finish > start and pixels > 0 and label_pixels > 0, 'invalid axis extent or label budget')
    count = max(1, int(pixels // label_pixels))
    step0 = (finish - start) / count
    exponent = 10 ** math.floor(math.log10(step0))
    step = next(m * exponent for m in (1, 2, 2.5, 5, 10) if m * exponent >= step0)
    if integral:
        step = max(1, math.ceil(step))
    first = math.ceil(start / step) * step
    ticks = [start] + [first + i * step for i in range(count + 2) if start < first + i * step < finish] + [finish]
    # Near-end interior ticks are omitted; endpoint labels are never squeezed.
    if len(ticks) > 2 and ticks[1] - start < step * .7:
        ticks.pop(1)
    if len(ticks) > 2 and finish - ticks[-2] < step * .7:
        ticks.pop(-2)
    return ticks


def route_dependency(source, target, obstacles, left, right, clearance):
    """Orthogonal bar connector; bypass intervening bars, in either row direction.

    Bar geometry=(x,y,w,h). Horizontal legs run in reserved row gutters; a
    vertical leg uses a safe common outside channel when bars obstruct it.
    Returns explicit points, not semantic membership inferred from geometry.
    """
    sx, sy, sw, sh = source
    tx, ty, tw, th = target
    down = ty >= sy
    start = (sx + sw, sy + sh if down else sy)
    finish = (tx, ty if down else ty + th)
    y1 = start[1] + clearance if down else start[1] - clearance
    y2 = finish[1] - clearance if down else finish[1] + clearance
    low, high = sorted((y1, y2))
    between = [r for r in obstacles if r is not source and r is not target
               and min(r[1] + r[3], high) > max(r[1], low)]
    blocked = any(r[0] - clearance <= start[0] <= r[0] + r[2] + clearance for r in between)
    channel = min((left, right), key=lambda x: abs(x - start[0]) + abs(x - finish[0])) if blocked else start[0]
    return [start, (start[0], y1), (channel, y1), (channel, y2), (finish[0], y2), finish]


def _path(points):
    return 'M' + ' L'.join(f'{x:g} {y:g}' for x, y in points)


# Canvas is intentionally imported only inside builders. Pure validation remains
# usable while the shared Canvas API is being implemented by its owning worker.
def gantt(spec):
    return _draw_gantt(spec, schedule_gantt(spec))


def release_train(spec):
    return _draw_release_train(spec, validate_release_train(spec))


def _canvas(spec):
    from render_templates import Canvas
    from visual_theme import layout_tokens, theme_snapshot
    # The design width is a library value, not this module's canvas constant.
    width = spec.get('canvas_width', layout_tokens()['design_width'])
    return Canvas(spec, width=width), theme_snapshot()


def _block(c, x, y, width, title, detail, theme):
    """Use Canvas' exact text budget without turning every row into a card."""
    budget = c.measure_block(title, detail, width)
    tx = x + budget['pad']
    c.text(tx, y + budget['pad'] + budget['title_size'], title,
           budget['title_size'], theme['ink'], c.tokens['weight']['node'], width - 2 * budget['pad'])
    if detail:
        yy = y + budget['pad'] + len(budget['title_rows']) * c.line_height(budget['title_size']) + budget['gap']
        c.text(tx, yy + budget['detail_size'], detail, budget['detail_size'],
               theme['muted'], c.tokens['weight']['body'], width - 2 * budget['pad'])
    return budget['height']


def _gantt_time(model, value):
    return f'D{value:g}' if model['mode'] == 'relative' else date.fromordinal(int(value)).isoformat()


def _clock_label(model, value, full=False):
    if model['time_mode'] == 'date':
        return date.fromordinal(int(value)).isoformat()
    from datetime import timezone, timedelta
    zone = timezone(timedelta(seconds=model['utc_offset_seconds']))
    instant = datetime.fromtimestamp(round(value * 3600), zone)
    clock = '%H:%M:%S' if instant.second else '%H:%M'
    return instant.strftime(('%m-%d ' if full else '') + clock)


def _axis(c, theme, x0, x1, y, start, finish, formatter, date_axis=False):
    from render_templates import units
    size = c.size('caption')
    labels = [formatter(start), formatter(finish), formatter((start + finish) / 2)]
    budget = max(units(s) * size for s in labels) + 2 * c.pad
    candidates = axis_ticks(start, finish, x1 - x0, budget, date_axis)
    # Endpoint labels use start/end anchors, not the half-width of a middle
    # anchor. Filter only optional interior ticks against actual text spans.
    ticks = [start]
    previous_right = x0 + units(formatter(start)) * size
    finish_left = x1 - units(formatter(finish)) * size
    for value in candidates[1:-1]:
        x = x0 + (value - start) / (finish - start) * (x1 - x0)
        half = units(formatter(value)) * size / 2
        if x - half >= previous_right + c.gap and x + half <= finish_left - c.gap:
            ticks.append(value)
            previous_right = x + half
    ticks.append(finish)
    c.path(f'M{x0:g} {y:g} H{x1:g}', theme['line'], c.tokens['line']['normal'])
    for value in ticks:
        x = x0 + (value - start) / (finish - start) * (x1 - x0)
        c.path(f'M{x:g} {y:g} v{c.gap:g}', theme['line'], c.tokens['line']['normal'])
        anchor = 'start' if value == start else 'end' if value == finish else 'middle'
        c.text(x, y + c.gap + size, formatter(value), size, theme['muted'],
               c.tokens['weight']['caption'], budget, anchor)
    return y + c.gap + c.line_height(size) + c.section


def _diamond(c, theme, x, y, appearance):
    half = c.tokens['marker']['size']
    c.path(f'M{x:g} {y-half:g} L{x+half:g} {y:g} L{x:g} {y+half:g} L{x-half:g} {y:g} Z',
           appearance['border'], c.tokens['line']['normal'], fill=appearance['tint'])


def _gantt_dependency_points(source, target, obstacles, clearance, milestone=False):
    """Gantt-only side ports and shortest clear local orthogonal corridor.

    Obstacles are actual bars/markers/text, never lane backgrounds or groups.
    The release-train router is intentionally unchanged.
    """
    sx, sy, sw, sh = source
    tx, ty, tw, th = target
    start = (sx+sw, sy+sh/2)
    finish = (tx-th/2 if milestone else tx, ty+th/2)
    direction = 1 if finish[1] >= start[1] else -1
    exit_y = start[1]+direction*(sh/2+clearance)
    entry_y = finish[1]-direction*(th/2+clearance)
    out_x, in_x = start[0]+clearance, finish[0]-clearance
    padding = clearance/2

    def clear(points):
        for a, b in zip(points, points[1:]):
            if a == b:
                continue
            for x, y, width, height in obstacles:
                left, right, top, bottom = x-padding, x+width+padding, y-padding, y+height+padding
                if a[0] == b[0]:
                    hit = left < a[0] < right and min(a[1],b[1]) < bottom and max(a[1],b[1]) > top
                else:
                    hit = top < a[1] < bottom and min(a[0],b[0]) < right and max(a[0],b[0]) > left
                if hit:
                    return False
        return True

    if start[1] == finish[1] and finish[0] >= start[0] and clear([start,finish]):
        return [start,finish]
    low, high = sorted((exit_y,entry_y))
    channels = {out_x,in_x,(out_x+in_x)/2}
    for x, y, width, height in obstacles:
        if y < high+clearance and y+height > low-clearance:
            channels.update((x-clearance,x+width+clearance))
    candidates = []
    for channel in sorted(channels):
        points = [start,(out_x,start[1]),(out_x,exit_y),(channel,exit_y),
                  (channel,entry_y),(in_x,entry_y),(in_x,finish[1]),finish]
        if clear(points):
            candidates.append(points)
    _check(candidates, 'No clear Gantt dependency corridor; inspect actual text/bar geometry.')
    points = min(candidates,key=lambda ps: sum(abs(a[0]-b[0])+abs(a[1]-b[1]) for a,b in zip(ps,ps[1:])))
    compact = []
    for point in points:
        if compact and point == compact[-1]:
            continue
        while len(compact) >= 2 and ((compact[-2][0] == compact[-1][0] == point[0])
                                     or (compact[-2][1] == compact[-1][1] == point[1])):
            compact.pop()
        compact.append(point)
    return compact


def _draw_gantt(spec, model):
    from visual_theme import semantic_tone
    c, theme = _canvas(spec)
    label_width = c.content_width * .36
    x0 = c.margin + label_width + 2 * c.pad
    x1 = c.width - c.margin - 2 * c.pad
    y = c.content_top
    title = '相对工作日 · 区间 [开始,结束)' if model['mode'] == 'relative' else '给定日期 · 区间 [开始,结束)'
    y += c.text(c.margin, y + c.size('body'), title, c.size('body'), theme['muted'],
                c.tokens['weight']['body'], c.content_width) + c.gap
    y = _axis(c, theme, x0, x1, y, model['axis_start'], model['axis_finish'],
              lambda v: _gantt_time(model, v), model['mode'] == 'dates')
    scale = (x1 - x0) / (model['axis_finish'] - model['axis_start'])
    bars, rows = {}, {}
    for lane in model['lanes']:
        children = [task for task in model['tasks'] if task['lane'] == lane['id']]
        lane_heading = f'{lane["label"]} · {lane["owner"]}'
        heading_budget = c.measure_block(lane_heading, '', c.content_width)
        heights = []
        details = []
        for task in children:
            interval = f'{_gantt_time(model, task["start_value"])} → {_gantt_time(model, task["finish_value"])}'
            interval += f' · {task["duration_value"]:g}{" 工作日" if model["mode"] == "relative" else " 日历日"}'
            if model['mode'] == 'relative':
                interval += ' · 关键' if task['critical'] else f' · 余量 {task["slack"]:g}'
            if task['owner'] != lane['owner']:
                interval += f'\n负责人：{task["owner"]}'
            if task.get('detail'):
                interval += '\n' + task['detail']
            details.append(interval)
            heights.append(c.measure_block(task['label'], interval, label_width)['height'])
        lane_height = heading_budget['height'] + sum(heights) + c.gap
        end_lane = c.group(lane['id'], {**lane, 'title': lane_heading},
                           (c.margin, y, c.content_width, lane_height), 'lane', [t['id'] for t in children])
        c.rect(c.margin, y, c.content_width, heading_budget['height'], theme['panel_bg'], theme['group_border'],
               c.tokens['radius']['corner'])
        _block(c, c.margin, y, c.content_width, lane_heading, '', theme)
        y += heading_budget['height']
        for task, height, detail in zip(children, heights, details):
            content = {**task, 'title': task['label'], 'mode': model['mode'], 'unit': model['unit']}
            close = c.group(task['id'], content, (c.margin, y, c.content_width, height), 'task', [])
            _block(c, c.margin, y, label_width, task['label'], detail, theme)
            bh = c.line_height(c.size('body'))
            bx = x0 + (task['start_value'] - model['axis_start']) * scale
            by = y + (height - bh) / 2
            bw = task['duration_value'] * scale
            appearance_item = dict(task)
            appearance_item.setdefault('emphasis', bool(task.get('critical')))
            appearance = semantic_tone(appearance_item)
            c.rect(bx, by, bw, bh, appearance['tint'], appearance['border'], c.tokens['radius']['corner'])
            bars[task['id']] = (bx, by, bw, bh)
            rows[task['id']] = (y, height)
            c.path(f'M{c.margin:g} {y+height:g} H{c.width-c.margin:g}', theme['grid'], c.tokens['line']['group'])
            close()
            y += height
        end_lane()
        y += c.gap
    if model['milestones']:
        y += c.text(c.margin + c.pad, y + c.size('heading'), '里程碑', c.size('heading'), theme['ink'],
                    c.tokens['weight']['heading'], c.content_width - 2 * c.pad) + c.gap
    from render_templates import units, wrap
    packed, row_ends, row_heights = [], [], []
    for milestone in sorted(model['milestones'], key=lambda m: (m['at_value'], m['id'])):
        detail = _gantt_time(model, milestone['at_value'])
        if milestone.get('detail'):
            detail += '\n'+milestone['detail']
        width = min(max(units(milestone['label'])*c.size('node'),
                        max(units(line)*c.size('body') for line in detail.split('\n'))), c.content_width/2)
        height = (2*c.tokens['marker']['size']+c.gap+len(wrap(milestone['label'],width,c.size('node')))*c.line_height(c.size('node'))
                  +len(wrap(detail,width,c.size('body')))*c.line_height(c.size('body'))+c.gap)
        x = x0+(milestone['at_value']-model['axis_start'])*scale
        desired = min(max(c.margin,x-width/2),c.width-c.margin-width)
        for row, end_x in enumerate(row_ends):
            left = max(desired,end_x+c.gap)
            if left+width <= c.width-c.margin:
                break
        else:
            row, left = len(row_ends),desired
            row_ends.append(c.margin)
            row_heights.append(0)
        row_ends[row] = left+width
        row_heights[row] = max(row_heights[row],height)
        packed.append((milestone,detail,width,height,x,row,left))
    offsets, bottom = [], y
    for height in row_heights:
        offsets.append(bottom)
        c.path(f'M{x0:g} {bottom+c.tokens["marker"]["size"]:g} H{x1:g}',theme['grid'],c.tokens['line']['normal'])
        bottom += height+c.gap
    for milestone,detail,width,height,x,row,left in packed:
        top = offsets[row]
        cy = top+c.tokens['marker']['size']
        close = c.group(milestone['id'],{**milestone,'title':milestone['label'],'time_anchor':[x,cy],'unit':model['unit']},
                        (left,top,width,height),'milestone',[])
        _diamond(c,theme,x,cy,semantic_tone(milestone))
        ty = cy+c.tokens['marker']['size']+c.gap+c.size('node')
        c.text(left,ty,milestone['label'],c.size('node'),theme['ink'],c.tokens['weight']['node'],width)
        ty += len(wrap(milestone['label'],width,c.size('node')))*c.line_height(c.size('node'))-c.size('node')+c.size('body')
        c.text(left,ty,detail,c.size('body'),theme['muted'],c.tokens['weight']['body'],width)
        bars[milestone['id']] = (x,cy-c.tokens['marker']['size'],0,2*c.tokens['marker']['size'])
        close()
    y = bottom
    from render_templates import _label_left
    milestone_ids = {m['id'] for m in model['milestones']}
    for edge in model['edges']:
        source, target = bars[edge['from']], bars[edge['to']]
        obstacles = []
        for key, rect in bars.items():
            if key in (edge['from'],edge['to']):
                continue
            if key in milestone_ids:
                bx, by, _, bh = rect
                rect = (bx-bh/2,by,bh,bh)
            obstacles.append(rect)
        obstacles.extend((_label_left(t),t['y']-t['size'],t['width'],t['size']+c.gap/2) for t in c.labels if t['width'] > 0)
        milestone = edge['to'] in milestone_ids
        points = _gantt_dependency_points(source,target,obstacles,c.gap,milestone)
        relation = {**edge, 'from_port':'finish-right', 'to_port':'milestone-left' if milestone else 'start-left',
                    'source_anchor':list(points[0]),'target_anchor':list(points[-1])}
        if milestone:
            relation['milestone_time_anchor'] = [target[0],target[1]+target[3]/2]
        c.path(_path(points),theme['edge'],c.tokens['line']['normal'],True,relation=relation)
    y += c.section
    legend = '条＝任务持续时间；箭头＝FS 完成前置；菱形＝里程碑'
    if model['mode'] == 'relative':
        legend += '\n“关键”／“余量”：零滞后 FS DAG、无限资源模型'
    y += c.text(c.margin, y+c.size('body'),legend,c.size('body'),theme['ink'],
                c.tokens['weight']['body'],c.content_width)+c.gap
    note = spec.get('note','')
    missing = []
    if '资源' not in note:
        missing.append('不做资源调度')
    if '工作周' not in note or '节假日' not in note:
        missing.append('未计工作周和节假日')
    if model['mode'] == 'relative' and ('等待' not in note or '不确定性' not in note):
        missing.append('未计额外等待与估算不确定性')
    if model['mode'] == 'dates' and ('关键' not in note or '余量' not in note):
        missing.append('日期模式不计算关键路径或余量')
    if missing:
        y += c.text(c.margin,y+c.size('body'),'；'.join(missing),c.size('body'),theme['muted'],
                    c.tokens['weight']['body'],c.content_width)+c.gap
    c.planning_model = model
    return c.finish(y)


def _release_detail(item, kind, model):
    time = (_clock_label(model, item['at_value'], True) if 'at_value' in item else
            f'{_clock_label(model, item["start_value"], True)} → {_clock_label(model, item["finish_value"], True)}')
    detail = time
    if kind == 'gate':
        state = {'passed': '已通过', 'pending': '待决', 'blocked': '阻断'}[item['state']]
        detail += f' · {state}\n前置：' + '；'.join(item['conditions'])
    elif kind == 'ticket':
        state = {'boarded': '已上车', 'approved': '已批准', 'pending': '待审批',
                 'rejected': '已拒绝', 'deferred': '已延期'}[item['status']]
        gate = next(g for g in model['gates'] if g['id'] == item['approval_gate'])
        detail += f' · {state}\n审批前置：{gate["label"]}'
        names = {'pending': '待决', 'approved': '已批准', 'rejected': '已拒绝'}
        for approval in item['approvals']:
            detail += '\n' + approval['label'] + '：' + names[approval['state']]
            if approval.get('approver'):
                detail += ' · ' + approval['approver']
            if approval.get('recorded_at'):
                value = _clock(approval['recorded_at'], model['time_mode'], 'approval.recorded_at', set())
                detail += '\n记录：' + _clock_label(model, value, True)
            if approval.get('conditions'):
                detail += '\n条件：' + '；'.join(approval['conditions'])
    elif kind == 'deployment':
        state = {'planned': '计划', 'running': '执行中', 'complete': '已完成', 'blocked': '阻断'}[item['state']]
        gate = next(g for g in model['gates'] if g['id'] == item['gate'])
        detail += f' · {state}\n范围：{item["scope"]}\n准出前置：{gate["label"]}'
    elif kind == 'exception':
        detail += '\n仅当：' + item['condition']
    if item.get('detail'):
        detail += '\n' + item['detail']
    return detail


def _draw_release_train(spec, model):
    from render_templates import units, wrap, _label_left
    from visual_theme import semantic_tone
    c, theme = _canvas(spec)
    x0, x1 = c.margin, c.width - c.margin
    scale = c.content_width / (model['axis_finish'] - model['axis_start'])
    position = lambda value: x0 + (value - model['axis_start']) * scale
    y = c.content_top
    context = model['train']['label']+' · '+model['windows'][0]['start']+' → '+model['windows'][-1]['finish']
    y += c.text(x0, y + c.size('body'), context, c.size('body'), theme['muted'],
                c.tokens['weight']['body'], c.content_width) + c.gap
    y = _axis(c, theme, x0, x1, y, model['axis_start'], model['axis_finish'],
              lambda v: _clock_label(model, v), model['time_mode'] == 'date')
    graph_top = y
    rects, pins, rails = {}, {}, {}
    edge_notes, phase_notes = [], []

    def constraints(detail):
        # Project whole restrictive clauses from free-form notes, not prefixes.
        # Explicit conditions below are never filtered or truncated. All original
        # prose, including these clauses, is also retained in supplemental rows.
        clauses = re.split(r'(?<=[。！？；;\n])', detail)
        return '\n'.join(clause.strip() for clause in clauses if re.search(
            r'仅|只能|只要|条件|前置|必须|需|禁止|不得|不再|不会|不能|未声明|'
            r'允许|拒绝|触发|否则|限制|至少|至多|\b(?:if|only|unless|must)\b',
            clause, re.IGNORECASE))

    # Structured, lossless records for the shared runtime's details delivery.
    # Keep IDs and raw timestamp/state values; do not infer an approval decision.
    fields = {'id':'实体 ID', 'label':'名称', 'kind':'类型', 'window':'窗口',
              'phase':'阶段', 'branch':'分支', 'start':'开始', 'finish':'结束',
              'at':'时间', 'status':'票据状态', 'state':'状态', 'approval_gate':'审批前置',
              'gate':'准出前置', 'scope':'范围', 'from':'来源', 'to':'去向',
              'condition':'触发条件', 'detail':'完整说明'}
    sections = []
    for kind, items in (('train',[model['train']]), ('window',model['windows']),
                        ('phase',model['phases']), ('branch',model['branches']),
                        ('ticket',model['tickets']), ('gate',model['gates']),
                        ('deployment',model['deployments']), ('exception',model['exceptions']),
                        ('edge',model['edges'])):
        for item in items:
            rows = [{'label':label, 'value':item[key]} for key,label in fields.items() if key in item]
            rows.extend({'label':f'条件 {i}', 'value':value}
                        for i,value in enumerate(item.get('conditions',[]),1))
            for i,approval in enumerate(item.get('approvals',[]),1):
                for key,label in (('label','名称'),('state','状态'),('approver','审批人'),('recorded_at','记录时间')):
                    if key in approval:
                        rows.append({'label':f'审批 {i} · {label}', 'value':approval[key]})
                rows.extend({'label':f'审批 {i} · 条件 {j}', 'value':value}
                            for j,value in enumerate(approval.get('conditions',[]),1))
            sections.append({'id':kind+':'+item['id'], 'title':item['label'], 'rows':rows})
    c.supplemental = {'title':spec['title']+' · 审批记录与解释明细', 'sections':sections}

    # One continuous, genuinely timed phase band per window. Gaps stay gaps;
    # the tallest measured phase label sets band height, not a fixed giant row.
    band_h = max(len(wrap(p['label'], max(c.pad, (p['finish_value']-p['start_value'])*scale-2*c.gap),
                         c.size('node'))) * c.line_height(c.size('node')) + 2*c.pad for p in model['phases'])
    window_heading = c.line_height(c.size('body'))+c.gap
    for window in model['windows']:
        wx, ww = position(window['start_value']), (window['finish_value']-window['start_value'])*scale
        members = [p['id'] for p in window['phases']]
        members += [r['id'] for r in model['branches']+model['gates']+model['tickets']+model['deployments']+model['exceptions']
                    if r.get('window') == window['id']]
        close = c.group(window['id'], window, (wx,y,ww,band_h+window_heading), 'window', members)
        c.text(wx+c.gap,y+c.size('body'),window['label'],c.size('body'),theme['ink'],c.tokens['weight']['body'],max(c.pad,ww-2*c.gap))
        phase_y = y+window_heading
        for phase in window['phases']:
            px, pw = position(phase['start_value']), (phase['finish_value']-phase['start_value'])*scale
            end = c.group(phase['id'],phase,(px,phase_y,pw,band_h),'phase',
                          [r['id'] for r in model['gates']+model['deployments'] if r['phase'] == phase['id']])
            appearance = semantic_tone(phase)
            c.rect(px,phase_y,pw,band_h,appearance['tint'],appearance['entity_border'],c.tokens['radius']['corner'])
            c.text(px+c.gap,phase_y+c.pad+c.size('node'),phase['label'],c.size('node'),theme['ink'],
                   c.tokens['weight']['node'],max(c.pad,pw-2*c.gap))
            rects[phase['id']] = (px,phase_y,pw,band_h)
            end()
            note = constraints(phase.get('detail',''))
            if note:
                phase_notes.append(phase['label']+'：'+note)
        close()
    y += band_h+window_heading+c.section
    for note in phase_notes:
        y += c.text(x0,y+c.size('body'),note,c.size('body'),theme['muted'],
                    c.tokens['weight']['body'],c.content_width)+c.gap
    if phase_notes:
        y += c.section

    # Master and the release segments are adjacent tracks, not object-list rows.
    master = next(b for b in model['branches'] if b['kind'] == 'master')
    release_branches = [b for b in model['branches'] if b['kind'] == 'release']
    track_gap = c.line_height(c.size('node')) + 2*c.section
    master_y, release_y = y+c.line_height(c.size('node')), y+c.line_height(c.size('node'))+track_gap
    for branch in model['branches']:
        by = master_y if branch['kind'] == 'master' else release_y
        bx, bw = position(branch['start_value']), (branch['finish_value']-branch['start_value'])*scale
        budget = c.measure_block(branch['label'], '', max(bw, 2*c.pad+c.size('node')))
        end = c.group(branch['id'], branch, (bx, by-budget['height'], bw, budget['height']+c.gap), 'branch',
                      [r['id'] for r in model['tickets']+model['deployments']+model['exceptions'] if r['branch'] == branch['id']])
        c.text(bx+c.gap, by-c.gap-c.size('node'), branch['label'], c.size('node'), theme['ink'],
               c.tokens['weight']['node'], max(c.pad, bw-2*c.gap))
        c.path(f'M{bx:g} {by:g} H{bx+bw:g}', theme['edge'], c.tokens['line']['main'])
        rails[branch['id']] = by
        rects[branch['id']] = (bx, by, bw, 0)
        end()
    y = release_y + 2*c.section

    def event_row(items, kind, top):
        if not items:
            return top
        packed, row_ends, row_heights = [], [], []
        for item in sorted(items, key=lambda r: (r.get('at_value', r.get('start_value')), r['id'])):
            if kind == 'gate':
                state = {'passed':'已通过', 'pending':'待决', 'blocked':'阻断'}[item['state']]
                status = {'passed':'success', 'pending':'warning', 'blocked':'error'}[item['state']]
            elif kind == 'ticket':
                state = {'boarded':'已上车','approved':'已批准','pending':'待审批','rejected':'已拒绝','deferred':'已延期'}[item['status']]
                status = {'boarded':'success','approved':'success','pending':'warning','rejected':'error','deferred':'neutral'}[item['status']]
            elif kind == 'deployment':
                state = {'planned':'计划','running':'执行中','complete':'已完成','blocked':'阻断'}[item['state']]
                status = {'planned':'neutral','running':'accent','complete':'success','blocked':'error'}[item['state']]
            else:
                state, status = '条件路径', 'neutral'
            stamp = (_clock_label(model, item['at_value']) if 'at_value' in item else
                     _clock_label(model, item['start_value'])+' → '+_clock_label(model, item['finish_value']))
            short = stamp+' · '+state
            if kind == 'gate':
                short += '\n前置：'+'；'.join(item['conditions'])
            elif kind == 'ticket':
                for approval in item['approvals']:
                    if approval.get('conditions'):
                        short += '\n'+approval['label']+'：'+'；'.join(approval['conditions'])
            elif kind == 'deployment':
                short = stamp+'\n'+state+'\n'+item['scope']
            else:
                short += '\n仅当：'+item['condition']
            note = constraints(item.get('detail',''))
            if note:
                short += '\n'+note
            text_w = max(units(item['label'])*c.size('node'), max(units(s)*c.size('body') for s in short.split('\n')))+2*c.pad
            width = min(text_w, c.content_width*.42)
            height = c.measure_block(item['label'], short, width)['height']
            when = item.get('at_value', (item.get('start_value', 0)+item.get('finish_value', 0))/2)
            px = position(when)
            desired = min(max(x0, px-width/2), x1-width)
            for row, end_x in enumerate(row_ends):
                left = max(desired, end_x+c.gap)
                if left+width <= x1:
                    break
            else:
                row, left = len(row_ends), desired
                row_ends.append(x0)
                row_heights.append(0)
            row_ends[row] = left+width
            row_heights[row] = max(row_heights[row], height)
            packed.append((item, short, status, row, left, width, height, px))
        offsets, cursor = [], top
        for height in row_heights:
            offsets.append(cursor+c.section)
            cursor += height+2*c.section
        for item, short, status, row, left, width, height, px in packed:
            by = offsets[row]
            pin_y = by-2*c.gap
            content = {**item, 'time_anchor':[px,pin_y], 'title':item['label']}
            end = c.group(item['id'], content, (left,by,width,height), kind, [])
            appearance = semantic_tone({**item, 'status':status})
            if 'start_value' in item:
                bx, bw = position(item['start_value']), (item['finish_value']-item['start_value'])*scale
                c.rect(bx, pin_y-c.tokens['marker']['size']/2, bw, c.tokens['marker']['size'],
                       appearance['tint'], appearance['border'], c.tokens['radius']['corner'])
            else:
                _diamond(c, theme, px, pin_y, appearance)
            cx = left+width/2
            c.path(_path([(px,pin_y),(px,by-c.gap),(cx,by-c.gap),(cx,by)]), theme['line'], c.tokens['line']['normal'])
            c.rect(left,by,width,height,appearance['tint'],appearance['entity_border'],c.tokens['radius']['card'])
            _block(c,left,by,width,item['label'],short,theme)
            rects[item['id']], pins[item['id']] = (left,by,width,height), (px,pin_y)
            end()
        return cursor

    y = event_row(model['gates'], 'gate', y)
    y = event_row(model['tickets'], 'ticket', y)
    y = event_row(model['deployments'], 'deployment', y)
    y = event_row(model['exceptions'], 'exception', y)

    # Edges come from the validated model. Their control ports use the newly
    # drawn shapes; time markers remain fixed to actual input instants.
    shown = set()
    for edge in model['edges']:
        a, b = rects[edge['from']], rects[edge['to']]
        if edge['kind'] in ('branch','merge'):
            px = position(edge['at_value'])
            points = [(px,rails[edge['from']]),(px,rails[edge['to']])]
            lx = px+c.pad if edge['kind'] == 'branch' else px-c.pad
            ly = master_y+c.section
            anchor = 'start' if edge['kind'] == 'branch' else 'end'
        elif edge['kind'] == 'board':
            px, py = pins[edge['from']]
            points = route_dependency((px,py,0,0),(px,rails[edge['to']],0,0),list(rects.values()),
                                      x0-c.gap,x1+c.gap,c.gap)
            lx, ly, anchor = px+c.pad, release_y+c.section, 'start'
        else:
            points = route_dependency(a,b,list(rects.values()),x0-c.gap,x1+c.gap,c.gap)
            lx = (a[0]+a[2]/2+b[0]+b[2]/2)/2
            ly = (max(a[1]+a[3],b[1]+b[3])+c.size('caption')+c.gap if abs(a[1]-b[1])<c.gap
                  else min(a[1]+a[3],b[1]+b[3])+c.size('caption')+c.gap)
            anchor = 'middle'
        c.path(_path(points),theme['edge'],c.tokens['line']['normal'],True,
               dash=edge['kind'] in ('rollback','emergency'),relation=edge)
        signature = (edge['from'],edge['label'])
        if signature not in shown:
            width = units(edge['label'])*c.size('caption')+2*c.gap
            left = lx-(width/2 if anchor == 'middle' else width if anchor == 'end' else 0)
            left = min(max(x0,left),x1-width)
            collision = any(min(left+width,_label_left(t)+t['width'])>max(left,_label_left(t))
                            and min(ly+2,t['y']+2)>max(ly-c.size('caption'),t['y']-t['size']) for t in c.labels)
            if collision:
                edge_notes.append(edge['label'])
            else:
                c.rect(left,ly-c.size('caption'),width,c.line_height(c.size('caption')),theme['paper'],'none',c.tokens['radius']['corner'])
                c.text(left+c.gap,ly,edge['label'],c.size('caption'),theme['ink'],c.tokens['weight']['caption'],width-2*c.gap)
            shown.add(signature)
        if edge.get('condition'):
            edge_notes.append(edge['label']+'：'+edge['condition'])

    # Keep collision-displaced edge labels and every explicit edge condition
    # readable in the main SVG; the full records live in supplemental, not here.
    for note in dict.fromkeys(edge_notes):
        y += c.text(x0,y+c.size('body'),note,c.size('body'),theme['ink'],
                    c.tokens['weight']['body'],c.content_width)+c.gap
    for limit in model['limitations']:
        if limit not in spec.get('note',''):
            y += c.text(x0,y+c.size('body'),limit,c.size('body'),theme['muted'],
                        c.tokens['weight']['body'],c.content_width)+c.gap
    close = c.group(model['train']['id'],model['train'],(x0,graph_top,c.content_width,y-graph_top), 'train',
                    [master['id']]+[w['id'] for w in model['windows']])
    close()
    c.planning_model = model
    return c.finish(y)


BUILDERS = {'gantt': gantt, 'release-train': release_train}
