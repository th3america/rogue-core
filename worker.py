"""Candidate worker with explicit checkpoint/resume; inference remains local."""
import argparse
import json
import time
from pathlib import Path
from cognition import LocalCognition
from fixture import TinyWorld
from rogue import Rogue, WorldStore, digest


def execute_turn(candidate, cognition, world):
    current=candidate.working_record(); before_calls=candidate.state['model_calls']
    record={'call':before_calls+1,'input_state_sha256':digest(candidate.state),'current':current}
    tick=time.monotonic()
    try:
        request,response,text=cognition.decide(current)
        record.update(request=request,response=response)
        decision=json.loads(text)
        record['decision']=decision
        candidate.step(decision,world)
        candidate.state['consecutive_protocol_errors']=0
    except Exception as error:
        record['error']=str(error)
        if candidate.state['model_calls']==before_calls: candidate.state['model_calls']+=1
        candidate.state['last_result']={'tool_error':str(error)[:350]}
        count=candidate.state.get('consecutive_protocol_errors',0)+1
        candidate.state['consecutive_protocol_errors']=count
        if count>=3: candidate.state['status']='PROTOCOL_ERROR_STOP'
    record.update(elapsed_seconds=round(time.monotonic()-tick,3),
                  status=candidate.state['status'],state_sha256=digest(candidate.state))
    return record


def run(args):
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    checkpoint = out/'candidate.json'; world_file = out/'environment.json'
    if args.resume:
        candidate = Rogue(store=WorldStore.restore(checkpoint))
        world = TinyWorld.restore(json.loads(world_file.read_text()))
        assert world.observe() == candidate.raw, 'Environment/SELF checkpoint mismatch'
        (out/'restart.json').write_text(json.dumps({'status':'restored','self_id':candidate.state['self_id'],
            'state_sha256':digest(candidate.state), 'actions':candidate.state['actions'],
            'calls':candidate.state['model_calls'], 'question':candidate.state['question'],
            'models':candidate.state['models'], 'observations':len(candidate.state['observations'])},indent=2))
    else:
        world = TinyWorld(special=args.special, variant=args.variant)
        candidate = Rogue(world.observe())
    cognition = LocalCognition(args.port, timeout=90)
    start = time.monotonic()
    with (out/'calls.jsonl').open('a',encoding='utf-8') as log:
        while candidate.state['status'] == 'active':
            if candidate.state['model_calls'] >= candidate.state['budget']['calls']:
                candidate.state['status']='CALL_BUDGET_STOP'; break
            if time.monotonic()-start > args.seconds:
                candidate.state['status']='WALL_TIME_STOP'; break
            record=execute_turn(candidate,cognition,world)
            log.write(json.dumps(record,separators=(',',':'))+'\n'); log.flush()
            candidate.store.memory_store(checkpoint)
            world_file.write_text(json.dumps(world.checkpoint()))
            print(json.dumps({'call':candidate.state['model_calls'],'actions':candidate.state['actions'],
                'x':candidate.raw['x'],'op':record.get('decision',{}).get('op'),
                'model':candidate.current()['expression'] if candidate.current() else None,
                'status':candidate.state['status'],'error':record.get('error'),
                'seconds':record['elapsed_seconds']}),flush=True)
            if args.pause_on_break and record.get('decision',{}).get('op') == 'ROGUE_BREAK' and len(candidate.state['models']) > 1:
                return 0
    candidate.store.memory_store(checkpoint)
    world_file.write_text(json.dumps(world.checkpoint()))
    return 0


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',required=True); parser.add_argument('--port',type=int,required=True)
    parser.add_argument('--special',type=int,default=3)
    parser.add_argument('--variant',choices=['local-reversal','ordinary'],default='local-reversal')
    parser.add_argument('--resume',action='store_true'); parser.add_argument('--pause-on-break',action='store_true')
    parser.add_argument('--seconds',type=int,default=600)
    raise SystemExit(run(parser.parse_args()))
