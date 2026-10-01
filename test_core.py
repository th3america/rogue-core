import copy
import json
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path
from cognition import SYSTEM
from fixture import TinyWorld
from rogue import (Rule, Rogue, WorldStore, ObservationEngine, TransitionEngine,
                   ExperimentEngine, HistoryEngine, digest)
from worker import execute_turn
from run_demo import resolve_runtime


def decision(op='FOLLOW_PLAN',model='x+dx',control=1):
    return dict(op=op,model=model,control=control,question='fixture plumbing question',focus='fixture',
                assumptions=['test-only scripted hypothesis'],route_stop_condition='stop on contradiction',
                continuation_reason='plumbing test only')


class CoreTests(unittest.TestCase):
    def test_runtime_paths_are_explicitly_replaceable(self):
        args=SimpleNamespace(runtime_dir='runtime-root',model_path='chosen/model.gguf',server='chosen/server',model='ignored.gguf')
        with patch.dict('os.environ',{},clear=True):
            runtime,model,server=resolve_runtime(args)
        self.assertEqual(runtime.name,'runtime-root')
        self.assertEqual(model.name,'model.gguf')
        self.assertEqual(server.name,'server')

    def test_expression_rejects_code_and_unbounded_values(self):
        for expr in ["__import__('os')",'x.__class__','[x for x in range(2)]','2**999','100000','hidden_rule']:
            with self.subTest(expr=expr), self.assertRaises((ValueError,SyntaxError)): Rule(expr)

    def test_expression_conditional_composition(self):
        rule=Rule('x-dx if tile == 7 else x+dx')
        self.assertEqual(rule.evaluate(3,1,7,7),2)
        self.assertEqual(rule.evaluate(2,1,0,7),3)

    def test_no_route_is_conditional(self):
        model=dict(id='m0',expression='x',assumptions=['nothing moves'])
        result=TransitionEngine.route_planner(TinyWorld().observe(),model)
        self.assertEqual(result['status'],'NO_ROUTE')
        self.assertEqual(result['conditional_on']['model'],'m0')

    def test_segmentation_has_no_wall_labels(self):
        result=ObservationEngine.object_segment(TinyWorld().observe())
        self.assertEqual(result['semantic_labels'],'none')

    def test_derivations_do_not_create_observations(self):
        world=TinyWorld(); agent=Rogue(world.observe())
        agent.step(decision('ROGUE_BREAK'),world)
        self.assertEqual(len(agent.state['observations']),1)
        self.assertEqual(agent.state['actions'],0)
        self.assertEqual(agent.state['models'][0]['status'],'working_hypothesis')

    def test_exact_contradiction_and_dependencies(self):
        world=TinyWorld(); agent=Rogue(world.observe())
        for _ in range(4): agent.step(decision(),world)
        last=agent.state['transitions'][-1]
        self.assertEqual((last['before_x'],last['after_x']),(3,2))
        self.assertFalse(last['comparisons'][0]['match'])
        trace=HistoryEngine.dependency_trace(agent.state,'m0')
        self.assertGreater(len(trace['dependent_event_ids']),0)

    def test_equivalent_reframes_are_blocked(self):
        world=TinyWorld(); agent=Rogue(world.observe())
        agent.step(decision(),world)
        agent.step(decision('ROGUE_BREAK','dx+x'),world)
        self.assertTrue(agent.state['metacog_blocked'])
        self.assertEqual(len(agent.state['models']),1)
        with self.assertRaisesRegex(ValueError,'METACOG_LOOP'):
            agent.step(decision('ROGUE_BREAK','x-dx'),world)

    def test_probe_groups_are_not_probabilities(self):
        raw=TinyWorld().observe(); raw['x']=3
        models=[dict(id='a',expression='x+dx'),dict(id='b',expression='x-dx')]
        ranked=ExperimentEngine.probe_ranker(raw,models)
        self.assertEqual(ranked[0]['distinct_outcomes'],2)
        self.assertNotIn('confidence',ranked[0])

    def test_observation_copy_and_tamper_detection(self):
        store=WorldStore(); raw=TinyWorld().observe(); store.observe(raw); raw['x']=2
        self.assertEqual(store.state['observations'][0]['raw']['x'],0)
        store.state['observations'][0]['raw']['x']=2
        with tempfile.TemporaryDirectory() as folder, self.assertRaisesRegex(ValueError,'modified'):
            store.memory_store(Path(folder)/'state.json')

    def test_checkpoint_new_process_preserves_question_and_budget(self):
        world=TinyWorld(); agent=Rogue(world.observe()); agent.step(decision(),world)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'state.json'; agent.store.memory_store(path)
            script='from rogue import WorldStore,digest; import sys; print(digest(WorldStore.restore(sys.argv[1]).state))'
            restored=subprocess.check_output([sys.executable,'-c',script,str(path)],cwd=Path(__file__).parent,text=True).strip()
            self.assertEqual(restored,digest(agent.state))

    def test_stale_rule_cannot_change_without_break(self):
        world=TinyWorld(); agent=Rogue(world.observe()); agent.step(decision(),world)
        with self.assertRaisesRegex(ValueError,'ROGUE_BREAK'):
            agent.step(decision(model='x-dx'),world)
        self.assertEqual(agent.state['actions'],1)

    def test_scripted_fixture_solution_is_labeled_plumbing_only(self):
        # This tests the simulator/controller. It is NOT evidence of learned cognition.
        world=TinyWorld(); agent=Rogue(world.observe())
        for _ in range(4): agent.step(decision(),world)
        revised='x-dx if tile == 7 else x+dx'
        agent.step(decision('ROGUE_BREAK',revised),world)
        for _ in range(5):
            if agent.raw['terminal']: break
            agent.step(decision(model=revised),world)
        self.assertTrue(agent.raw['terminal'])

    def test_completion_requires_environment(self):
        world=TinyWorld(); agent=Rogue(world.observe())
        with self.assertRaisesRegex(ValueError,'evidence'): agent.step(decision('COMPLETE'),world)

    def test_prompt_does_not_contain_fixture_solution(self):
        for text in ['local-reversal','tile == 7','x-dx if','special=3']:
            self.assertNotIn(text,SYSTEM)

    def test_invalid_arithmetic_does_not_poison_committed_model(self):
        world=TinyWorld(); agent=Rogue(world.observe())
        with self.assertRaises(ZeroDivisionError): agent.step(decision(model='x % 0'),world)
        self.assertIsNone(agent.current())
        self.assertEqual(agent.working_record()['observation']['x'],0)

    def test_rejected_raw_reply_is_preserved_and_retries_are_bounded(self):
        class InvalidReply:
            def decide(self,current): return {'messages':[]},{'choices':[{'message':{'content':''}}]},''
        world=TinyWorld(); agent=Rogue(world.observe())
        for _ in range(3): record=execute_turn(agent,InvalidReply(),world)
        self.assertIn('response',record)
        self.assertEqual(agent.state['status'],'PROTOCOL_ERROR_STOP')
        self.assertEqual(agent.state['actions'],0)


if __name__=='__main__': unittest.main()
