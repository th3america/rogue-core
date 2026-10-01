"""Launch owned, temporary loopback inference; preserve every result, including failures."""
import argparse
import ctypes
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from cognition import SYSTEM, SCHEMA
from fixture import TinyWorld
from rogue import TransitionEngine, WorldStore, digest

ROOT=Path(__file__).resolve().parent
DEFAULT_RUNTIME=ROOT.parent/'greyspark-tool-use-ai-design/local-runtime'

def resolve_runtime(args):
    runtime=Path(args.runtime_dir or os.environ.get('ROGUE_RUNTIME_DIR') or DEFAULT_RUNTIME).expanduser().resolve()
    model_value=args.model_path or os.environ.get('ROGUE_MODEL_PATH')
    server_value=args.server or os.environ.get('ROGUE_SERVER_PATH')
    model=Path(model_value).expanduser().resolve() if model_value else (runtime/'models'/args.model).resolve()
    server=Path(server_value).expanduser().resolve() if server_value else (runtime/'llama-b10930-cuda12.4/llama-server.exe').resolve()
    return runtime,model,server

def file_hash(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(8*1024*1024),b''): h.update(chunk)
    return h.hexdigest()

def memory(process):
    if os.name != 'nt': return None
    class Counters(ctypes.Structure):
        _fields_=[('cb',ctypes.c_ulong),('PageFaultCount',ctypes.c_ulong)]+[
            (name,ctypes.c_size_t) for name in ['PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage',
            'QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage']]
    c=Counters(); c.cb=ctypes.sizeof(c)
    fn=ctypes.WinDLL('psapi').GetProcessMemoryInfo
    fn.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_ulong]
    return int(c.PeakWorkingSetSize) if fn(int(process._handle),ctypes.byref(c),c.cb) else None

def baseline():
    world=TinyWorld(); rows=[]
    model={'id':'fixed-human-baseline','expression':'x+dx','assumptions':['unconditional additive control']}
    for _ in range(16):
        raw=world.observe()
        if raw['terminal']: break
        plan=TransitionEngine.route_planner(raw,model)
        if not plan['controls']: break
        dx=plan['controls'][0]; after=world.act(dx)
        rows.append({'before':raw['x'],'dx':dx,'after':after['x']})
    return {'label':'scripted fixed-model baseline, not learned cognition','solved':world.observe()['terminal'],
            'actions':len(rows),'transitions':rows}

def summarize(out):
    state=WorldStore.restore(out/'candidate.json').state
    calls=[json.loads(line) for line in (out/'calls.jsonl').read_text().splitlines()]
    transitions=state['transitions']; models=state['models']
    mismatch=any(any(not c['match'] and c['model']==t['selected_model'] for c in t['comparisons']) for t in transitions)
    breaks=[r for r in calls if r.get('decision',{}).get('op')=='ROGUE_BREAK' and not r.get('error')]
    discriminators=[t for t in transitions if len({c['predicted_x'] for c in t['comparisons']})>1
                    and any(c['model']==t['selected_model'] and c['match'] for c in t['comparisons'])]
    solved=state['observations'][-1]['raw']['terminal']
    checks={'observed_prediction_contradiction':mismatch,
            'candidate_generated_nonempty_break_question':any(r['decision']['question'].strip() for r in breaks),
            'candidate_generated_different_transition_model':len(models)>1,
            'performed_discriminating_action_with_matching_selected_model':bool(discriminators),
            'environment_goal_reached':solved,'candidate_declared_completion':state['status']=='COMPLETE'}
    result={'checks':checks,'behavioral_sequence_pass':all(checks.values()),'status':state['status'],
            'model_calls':state['model_calls'],'environment_actions':state['actions'],'models':models,
            'discriminating_transitions':discriminators,'restart_performed':(out/'restart.json').exists(),
            'generation_tokens':sum(r.get('response',{}).get('usage',{}).get('completion_tokens',0) for r in calls),
            'prompt_tokens':sum(r.get('response',{}).get('usage',{}).get('prompt_tokens',0) for r in calls),
            'call_seconds':sum(r['elapsed_seconds'] for r in calls),
            'limits':['One developer-designed synthetic fixture, not an ARC result or broad generalization test.',
                      'A schema and general rule-expression grammar are provided; rule content and decisions come from the candidate.',
                      'This receipt checks observable decisions and transitions, not private reasoning or consciousness.',
                      'No OS/network sandbox proof: exposed candidate operations have no network or filesystem access.',
                      'The local inference companion and evaluator are separate processes; five candidate engines share one worker.']}
    (out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result

def run(args):
    out=Path(args.out).resolve()
    if out.exists(): raise ValueError('Use a new run directory; prior outcomes are immutable')
    out.mkdir(parents=True)
    runtime,model,server=resolve_runtime(args)
    if not model.is_file() or not server.is_file():
        raise FileNotFoundError(f'Configured local runtime/model missing: server={server}; model={model}')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
    contract={'prompt':SYSTEM,'schema':SCHEMA,'temperature':0,'seed':17,'output_tokens':280,
              'model':str(model),'model_bytes':model.stat().st_size,'model_sha256':file_hash(model),
              'runtime':str(server),'runtime_root':str(runtime),'runtime_sha256':file_hash(server),
              'source_hashes':{p.name:file_hash(p) for p in ROOT.glob('*.py')},
              'candidate_prompt_fixture_rule_included':False,'outside_cognitive_assistance_during_run':False,
              'limits':{'model_calls':20,'actions':16,'worker_seconds':600,'global_seconds':1100,
                        'model_peak_working_set_ceiling_bytes':12*1024**3},
              'fixture_role':'development fixture; known to the builder, hidden from candidate prompt'}
    (out/'frozen-contract.json').write_text(json.dumps(contract,indent=2))
    (out/'baseline.json').write_text(json.dumps(baseline(),indent=2))
    command=[str(server),'-m',str(model),'--host','127.0.0.1','--port',str(port),'-c','4096',
             '-t','6','-np','1','-ngl',str(args.gpu_layers)]
    flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
    started=time.monotonic(); peak=0; worker=None; result=None
    with (out/'server.log').open('w',encoding='utf-8') as logfile:
        process=subprocess.Popen(command,stdout=logfile,stderr=subprocess.STDOUT,creationflags=flags)
        try:
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            while True:
                if process.poll() is not None: raise RuntimeError('Local inference exited; inspect server.log')
                if time.monotonic()-started>150: raise TimeoutError('Local inference startup timeout')
                try:
                    with opener.open(f'http://127.0.0.1:{port}/health',timeout=1) as r:
                        if r.status==200: break
                except Exception: time.sleep(.25)
            print('Local model ready; frozen trial begins.',flush=True)
            for phase in ('initial','resume'):
                cmd=[sys.executable,'-X','utf8',str(ROOT/'worker.py'),'--port',str(port),'--out',str(out)]
                cmd += ['--pause-on-break'] if phase=='initial' else ['--resume']
                worker=subprocess.Popen(cmd,creationflags=flags)
                while worker.poll() is None:
                    peak=max(peak,memory(process) or 0)
                    if peak>12*1024**3 or time.monotonic()-started>1100:
                        worker.terminate(); worker.wait(timeout=10); raise TimeoutError('Run resource ceiling')
                    time.sleep(.25)
                if worker.returncode: raise RuntimeError('Candidate worker failed')
                state=WorldStore.restore(out/'candidate.json').state
                if phase=='initial' and state['status']=='active':
                    (out/'before-restart.json').write_text(json.dumps({'sha256':digest(state),'model_calls':state['model_calls'],'actions':state['actions']}))
                    print('Restarting candidate process from its exact saved state.',flush=True)
                else: break
            result=summarize(out)
        except Exception as error:
            (out/'run-error.json').write_text(json.dumps({'error':str(error)})); raise
        finally:
            if worker is not None and worker.poll() is None:
                worker.terminate(); worker.wait(timeout=10)
            peak=max(peak,memory(process) or 0)
            process.terminate()
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=10)
            (out/'runtime-receipt.json').write_text(json.dumps({'elapsed_seconds':time.monotonic()-started,
                'inference_peak_working_set_bytes':peak,'gpu_memory_measured':False,
                'owned_inference_process_stopped':process.poll() is not None,'server_pid':process.pid,
                'candidate_engine_processes_simultaneous':1,'command':command},indent=2))
    print(json.dumps({k:result[k] for k in ['checks','behavioral_sequence_pass','status','model_calls','environment_actions','restart_performed']},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--out',required=True)
    p.add_argument('--model',default='Phi-3-mini-4k-instruct-q4.gguf'); p.add_argument('--gpu-layers',type=int,default=99)
    p.add_argument('--runtime-dir',help='Runtime root; defaults to ROGUE_RUNTIME_DIR or the legacy sibling layout')
    p.add_argument('--server',help='Inference server executable; defaults to ROGUE_SERVER_PATH or runtime layout')
    p.add_argument('--model-path',help='Model file; defaults to ROGUE_MODEL_PATH or runtime/models/--model')
    run(p.parse_args())

