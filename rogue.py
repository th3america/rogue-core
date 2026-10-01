"""Rogue v0: five internal engines. No environment solution in this module."""
from __future__ import annotations
import ast
import copy
import hashlib
import json
from collections import deque
from pathlib import Path


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class Rule:
    """Bounded expression interpreter; a model proposes expressions, not Python code."""
    def __init__(self, expression):
        if not isinstance(expression, str) or len(expression) > 240:
            raise ValueError('Rule must be a string of at most 240 characters')
        self.expression = expression
        self.tree = ast.parse(expression, mode='eval').body
        nodes = list(ast.walk(self.tree))
        allowed = (ast.Name, ast.Load, ast.Constant, ast.BinOp, ast.UnaryOp,
                   ast.IfExp, ast.Compare, ast.BoolOp, ast.Add, ast.Sub, ast.Mult,
                   ast.Mod, ast.USub, ast.UAdd, ast.Not, ast.Eq, ast.NotEq,
                   ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.And, ast.Or)
        if len(nodes) > 80 or any(not isinstance(n, allowed) for n in nodes):
            raise ValueError('Unsupported expression syntax')
        for n in nodes:
            if isinstance(n, ast.Name) and n.id not in {'x', 'dx', 'tile', 'width'}:
                raise ValueError('Unknown expression variable')
            if isinstance(n, ast.Constant) and (type(n.value) not in (int, bool) or abs(n.value) > 100):
                raise ValueError('Only bounded integer constants are supported')

    def evaluate(self, x, dx, tile, width):
        env = dict(x=x, dx=dx, tile=tile, width=width)
        def visit(n):
            if isinstance(n, ast.Constant): return n.value
            if isinstance(n, ast.Name): return env[n.id]
            if isinstance(n, ast.IfExp): return visit(n.body if visit(n.test) else n.orelse)
            if isinstance(n, ast.UnaryOp):
                a = visit(n.operand)
                return -a if isinstance(n.op, ast.USub) else (+a if isinstance(n.op, ast.UAdd) else not a)
            if isinstance(n, ast.BoolOp):
                return all(visit(v) for v in n.values) if isinstance(n.op, ast.And) else any(visit(v) for v in n.values)
            if isinstance(n, ast.Compare):
                a = visit(n.left)
                for op, bnode in zip(n.ops, n.comparators):
                    b = visit(bnode)
                    ok = (a == b if isinstance(op, ast.Eq) else a != b if isinstance(op, ast.NotEq)
                          else a < b if isinstance(op, ast.Lt) else a <= b if isinstance(op, ast.LtE)
                          else a > b if isinstance(op, ast.Gt) else a >= b)
                    if not ok: return False
                    a = b
                return True
            a, b = visit(n.left), visit(n.right)
            value = (a + b if isinstance(n.op, ast.Add) else a - b if isinstance(n.op, ast.Sub)
                     else a * b if isinstance(n.op, ast.Mult) else a % b)
            if abs(value) > 10000: raise ValueError('Expression value exceeds bound')
            return value
        result = visit(self.tree)
        if type(result) is not int: raise ValueError('Rule must predict an integer position')
        return result


class ObservationEngine:
    @staticmethod
    def frame_read(raw):
        if (not isinstance(raw, dict) or not isinstance(raw.get('cells'), list)
                or not 2 <= len(raw['cells']) <= 64
                or any(type(v) is not int for v in raw['cells'])
                or type(raw.get('x')) is not int
                or not 0 <= raw['x'] < len(raw['cells'])):
            raise ValueError('Malformed environment observation')
        return copy.deepcopy(raw)

    @staticmethod
    def frame_diff(before, after):
        return {'x_delta': after['x'] - before['x'], 'changed_cells': [
            i for i, (a, b) in enumerate(zip(before['cells'], after['cells'])) if a != b],
            'terminal_change': before.get('terminal') != after.get('terminal')}

    @staticmethod
    def object_segment(raw):
        groups = []
        for x, value in enumerate(raw['cells']):
            if groups and groups[-1]['value'] == value: groups[-1]['positions'].append(x)
            else: groups.append({'value': value, 'positions': [x]})
        return {'grouping_rule': 'adjacent_equal_cell_values', 'candidate_regions': groups,
                'semantic_labels': 'none'}


class WorldStore:
    def __init__(self, state=None):
        self.state = copy.deepcopy(state) if state is not None else {
            'self_id': 'ROGUE-V0', 'schema': 1, 'observations': [], 'models': [],
            'events': [], 'transitions': [], 'current_model': None, 'focus': '',
            'question': '', 'route_stop_condition': '', 'continuation_reason': '',
            'model_calls': 0, 'actions': 0, 'break_signatures': [], 'metacog_blocked': False,
            'status': 'active', 'last_result': {}, 'budget': {'calls': 20, 'actions': 16}}

    def event(self, kind, value, dependencies=()):
        assert kind in {'OBSERVATION', 'DERIVATION', 'INFERENCE', 'ACTION'}
        row = {'id': f'e{len(self.state["events"])}', 'class': kind,
               'value': copy.deepcopy(value), 'dependencies': list(dependencies)}
        self.state['events'].append(row)
        return row['id']

    def observe(self, raw):
        raw = ObservationEngine.frame_read(raw)
        ref = self.event('OBSERVATION', raw)
        self.state['observations'].append({'id': ref, 'raw': raw, 'sha256': digest(raw)})
        self.state['metacog_blocked'] = False
        return ref

    def hypothesis_board(self, expression, assumptions, question):
        Rule(expression)
        row = {'id': f'm{len(self.state["models"])}', 'expression': expression,
               'assumptions': copy.deepcopy(assumptions), 'question': question,
               'status': 'working_hypothesis', 'origin': 'candidate_model_output',
               'created_after_observation': self.state['observations'][-1]['id']}
        self.state['models'].append(row)
        self.event('INFERENCE', row, [row['created_after_observation']])
        return row

    def retrieve(self):
        # Every item retains its identity and scope; no summary promotes it to fact.
        return copy.deepcopy({'models': self.state['models'], 'transitions': self.state['transitions']})

    def memory_store(self, path):
        for obs in self.state['observations']:
            if digest(obs['raw']) != obs['sha256']: raise ValueError('Observation was modified')
        envelope = {'state': self.state, 'sha256': digest(self.state)}
        path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(envelope, indent=2), encoding='utf-8')
        temporary.replace(path)

    @classmethod
    def restore(cls, path):
        envelope = json.loads(Path(path).read_text(encoding='utf-8'))
        if digest(envelope['state']) != envelope['sha256']: raise ValueError('Checkpoint integrity failure')
        obj = cls(envelope['state'])
        for obs in obj.state['observations']:
            if digest(obs['raw']) != obs['sha256']: raise ValueError('Observation integrity failure')
        return obj


class TransitionEngine:
    @staticmethod
    def state_simulator(raw, model, dx):
        if type(dx) is not int or dx not in (-1, 1): raise ValueError('Illegal control')
        x = raw['x']; width = len(raw['cells'])
        pred = Rule(model['expression']).evaluate(x, dx, raw['cells'][x], width)
        # Boundary rejection is a declared interface rule, not a hidden mechanic.
        return pred if 0 <= pred < width else x

    @classmethod
    def flood(cls, raw, model):
        queue = deque([raw['x']]); paths = {raw['x']: []}
        while queue:
            x = queue.popleft()
            state = dict(raw, x=x)
            for dx in (-1, 1):
                dest = cls.state_simulator(state, model, dx)
                if dest not in paths:
                    paths[dest] = paths[x] + [dx]; queue.append(dest)
        return paths

    @classmethod
    def route_planner(cls, raw, model):
        paths = cls.flood(raw, model)
        path = paths.get(raw['goal'])
        return {'status': 'ROUTE' if path is not None else 'NO_ROUTE', 'controls': path,
                'conditional_on': {'model': model['id'], 'expression': model['expression'],
                                   'assumptions': model['assumptions'], 'goal': raw['goal']},
                'scope': 'supplied static one-dimensional model only'}


class ExperimentEngine:
    @staticmethod
    def probe_ranker(raw, models):
        rows = []
        for dx in (-1, 1):
            groups = {}
            for model in models:
                dest = TransitionEngine.state_simulator(raw, model, dx)
                groups.setdefault(str(dest), []).append(model['id'])
            rows.append({'dx': dx, 'predicted_outcome_groups': groups,
                         'distinct_outcomes': len(groups), 'environment_action_cost': 1})
        return sorted(rows, key=lambda r: -r['distinct_outcomes'])

    @staticmethod
    def compare(before, dx, after, models):
        return [{'model': m['id'], 'predicted_x': TransitionEngine.state_simulator(before, m, dx),
                 'observed_x': after['x'], 'match': TransitionEngine.state_simulator(before, m, dx) == after['x']}
                for m in models]


class HistoryEngine:
    @staticmethod
    def loop_detector(state):
        counts = {}; mismatches = {}
        for t in state['transitions']:
            key = (t['before_x'], t['dx'], t['after_x'], t['selected_model'])
            counts[key] = counts.get(key, 0) + 1
            for c in t['comparisons']:
                if not c['match']: mismatches[c['model']] = mismatches.get(c['model'], 0) + 1
        return {'repeated_transitions': [dict(before_x=k[0], dx=k[1], after_x=k[2], model=k[3], count=v)
                                        for k, v in counts.items() if v > 1],
                'prediction_mismatches_by_model': mismatches,
                'interpretation': 'signals only; repeated action is not automatically waste'}

    @staticmethod
    def dependency_trace(state, model_id):
        model = next(m for m in state['models'] if m['id'] == model_id)
        return {'model': copy.deepcopy(model), 'dependent_event_ids': [
            e['id'] for e in state['events'] if model_id in e['dependencies']]}

    @staticmethod
    def fingerprint(raw, model):
        # Material difference is predicted behavior, not expression spelling.
        return digest([TransitionEngine.state_simulator(dict(raw, x=x), model, dx)
                       for x in range(len(raw['cells'])) for dx in (-1, 1)])


class Rogue:
    """One candidate controller; cognition is injected via decisions from a local model."""
    def __init__(self, raw=None, store=None):
        self.store = store or WorldStore()
        if raw is not None: self.store.observe(raw)

    @property
    def state(self): return self.store.state

    @property
    def raw(self): return copy.deepcopy(self.state['observations'][-1]['raw'])

    def current(self):
        return next((m for m in self.state['models'] if m['id'] == self.state['current_model']), None)

    def working_record(self):
        raw = self.raw; model = self.current()
        result = {'self_id': self.state['self_id'], 'objective': 'reach observed goal position',
                  'observation': raw, 'focus': self.state['focus'], 'question': self.state['question'],
                  'current_model': model, 'hypotheses': self.state['models'],
                  'recent_transitions': self.state['transitions'][-7:],
                  'monitor': HistoryEngine.loop_detector(self.state),
                  'last_result': self.state['last_result'],
                  'budget_remaining': {k: v-self.state['model_calls' if k == 'calls' else 'actions']
                                       for k, v in self.state['budget'].items()},
                  'route_stop_condition': self.state['route_stop_condition'],
                  'continuation_reason': self.state['continuation_reason'],
                  'metacog_blocked_until_observation': self.state['metacog_blocked']}
        if model:
            result['plan'] = TransitionEngine.route_planner(raw, model)
            result['probe_comparison'] = ExperimentEngine.probe_ranker(raw, self.state['models'])
        return result

    def step(self, decision, environment):
        """Host supplies no cognitive reply. Tool errors are returned verbatim as data."""
        if self.state['status'] != 'active': raise ValueError('Candidate already stopped')
        self.state['model_calls'] += 1
        if self.state['model_calls'] > self.state['budget']['calls']:
            self.state['status'] = 'CALL_BUDGET_STOP'; return
        op = decision.get('op')
        if op not in {'FOLLOW_PLAN', 'TEST_ALTERNATIVE', 'ROGUE_BREAK', 'PARK_UNRESOLVED', 'TASK_STOP', 'COMPLETE'}:
            raise ValueError('Invalid operation')
        for key in ('question', 'focus', 'route_stop_condition', 'continuation_reason'):
            value = decision.get(key)
            if not isinstance(value, str) or len(value) > 400: raise ValueError('Invalid working record field')
            self.state[key] = value
        self.store.event('INFERENCE', {'decision': decision, 'origin': 'local_model'})
        if op in {'TASK_STOP', 'PARK_UNRESOLVED', 'COMPLETE'}:
            if op == 'COMPLETE' and not self.raw.get('terminal'): raise ValueError('Completion lacks environment evidence')
            self.state['status'] = op; return
        expression = decision.get('model')
        if not isinstance(expression, str): raise ValueError('Supply a predictive expression')
        assumptions = decision.get('assumptions')
        if not isinstance(assumptions, list) or len(assumptions) > 6 or any(not isinstance(a, str) or len(a)>200 for a in assumptions):
            raise ValueError('Malformed assumptions')
        # Validate total behavior in the present domain before committing a model.
        # A malformed hypothesis must not poison the next working-record construction.
        HistoryEngine.fingerprint(self.raw, {'expression': expression})
        model = self.current()
        if op == 'ROGUE_BREAK':
            if self.state['metacog_blocked']: raise ValueError('METACOG_LOOP: no further reframe until observation; act or stop')
            proposed = {'expression': expression}
            signature = [self.state['observations'][-1]['id'], HistoryEngine.fingerprint(self.raw, proposed)]
            same = model and HistoryEngine.fingerprint(self.raw, model) == signature[1]
            if same or signature in self.state['break_signatures']:
                self.state['metacog_blocked'] = True
                self.state['last_result'] = {'signal': 'METACOG_LOOP', 'reason': 'No new predicted transition in current domain'}
                self.store.event('DERIVATION', self.state['last_result'], [model['id']] if model else [])
                return
            self.state['break_signatures'].append(signature)
            if model: self.store.event('DERIVATION', HistoryEngine.dependency_trace(self.state, model['id']), [model['id']])
        elif model and model['expression'] != expression:
            raise ValueError('Suspend and revise a model with ROGUE_BREAK before acting under it')
        if model is None or model['expression'] != expression:
            model = self.store.hypothesis_board(expression, assumptions, decision['question'])
            self.state['current_model'] = model['id']
        if op == 'ROGUE_BREAK':
            self.state['last_result'] = {'status': 'PLAN_SUSPENDED_MODEL_REVISED',
                                        'new_model': model['id'], 'new_predictions': ExperimentEngine.probe_ranker(self.raw, self.state['models'])}
            return
        if self.state['actions'] >= self.state['budget']['actions']:
            self.state['status'] = 'ACTION_BUDGET_STOP'; return
        raw = self.raw; observation_id = self.state['observations'][-1]['id']
        plan = TransitionEngine.route_planner(raw, model)
        self.store.event('DERIVATION', {'tool': 'route-planner', 'result': plan}, [observation_id, model['id']])
        if op == 'FOLLOW_PLAN':
            if not plan['controls']:
                self.state['last_result'] = plan; return
            dx = plan['controls'][0]
        else:
            dx = decision.get('control')
        if type(dx) is not int or dx not in (-1, 1): raise ValueError('Control must be -1 or 1')
        self.store.event('DERIVATION', {'tool': 'probe-ranker', 'result': ExperimentEngine.probe_ranker(raw, self.state['models'])},
                         [observation_id] + [m['id'] for m in self.state['models']])
        action_id = self.store.event('ACTION', {'dx': dx, 'status': 'submitted'}, [observation_id, model['id']])
        after = environment.act(dx)
        self.state['actions'] += 1
        after_id = self.store.observe(after)
        comparison = ExperimentEngine.compare(raw, dx, after, self.state['models'])
        transition = {'before_observation': observation_id, 'action': action_id, 'after_observation': after_id,
                      'before_x': raw['x'], 'before_tile': raw['cells'][raw['x']], 'dx': dx, 'after_x': after['x'],
                      'selected_model': model['id'], 'comparisons': comparison}
        self.state['transitions'].append(transition)
        self.store.event('DERIVATION', {'tool': 'compare', 'result': comparison,
                                      'frame_diff': ObservationEngine.frame_diff(raw, after)},
                         [observation_id, action_id, after_id] + [m['id'] for m in self.state['models']])
        self.state['last_result'] = transition
