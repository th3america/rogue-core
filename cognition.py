"""Frozen generic cognition contract; no fixture rule or task-specific hint."""
import json
import urllib.request

SYSTEM = '''You are Rogue, a persistent solver. Your goal and observations are in CURRENT.
You own interpretation, hypothesis formation, experimental choice and stopping.
Tools perform conditional calculations; a simulated result is not environmental evidence.
Observations are immutable. Interpretations and assumptions remain revisable.
The environment is a one-dimensional row of integer cell values. You observe x and goal.
The available environment control is a signed integer dx in {-1,1}. Its actual effect must be learned.
The interface rejects out-of-range resulting positions by leaving x unchanged.
Propose a compact expression predicting next x from x, dx, tile (current cell value), width.
Allowed syntax: integer constants, those variables, + - * %, comparisons, and/or/not, Python conditional expression.
Models must be your hypotheses. Do not invent observations or assume tool predictions are true.
FOLLOW_PLAN searches and executes one shortest-route action under your current model.
TEST_ALTERNATIVE executes the control you specify; compare records predictions against the returned observation.
ROGUE_BREAK suspends the plan and registers your materially different model; it spends no environment action.
Use it to revise an existing model before acting under the replacement. Generate your own question and alternative.
The monitors expose repeated dependencies and prediction errors; you decide what they mean.
PARK_UNRESOLVED or TASK_STOP ends the run with your reason. COMPLETE requires observed terminal=true.
Choose your own route-stop condition within the outer budget. Reframing without new predictions is blocked.
Return just the schema object. Keep question, assumptions and continuation reason concise.
No outside thinker will answer your questions; investigate using these tools and observations.'''

SCHEMA = {'type': 'object', 'additionalProperties': False, 'properties': {
    'op': {'type': 'string', 'enum': ['FOLLOW_PLAN','TEST_ALTERNATIVE','ROGUE_BREAK','PARK_UNRESOLVED','TASK_STOP','COMPLETE']},
    'model': {'type': 'string'}, 'control': {'type': 'integer','enum': [-1,1]},
    'question': {'type': 'string'}, 'focus': {'type': 'string'},
    'assumptions': {'type': 'array', 'items': {'type': 'string'}, 'maxItems': 6},
    'route_stop_condition': {'type': 'string'}, 'continuation_reason': {'type': 'string'}},
    'required': ['op','model','control','question','focus','assumptions','route_stop_condition','continuation_reason']}


class LocalCognition:
    def __init__(self, port, timeout=120):
        self.url = f'http://127.0.0.1:{int(port)}/v1/chat/completions'; self.timeout = timeout

    def decide(self, current):
        request = {'messages': [{'role':'system','content':SYSTEM},
                                {'role':'user','content':'CURRENT\n'+json.dumps(current,separators=(',',':'))}],
                   'temperature': 0, 'seed': 17, 'max_tokens': 280,
                   'response_format': {'type':'json_object','schema':SCHEMA}, 'stream':False}
        req = urllib.request.Request(self.url, json.dumps(request).encode(), {'Content-Type':'application/json'})
        # No proxy, external host, API key, web access or fallback endpoint.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=self.timeout) as response: raw = json.load(response)
        text = raw['choices'][0]['message']['content']
        # Preserve raw responses before parsing in the worker, including truncated/empty replies.
        return request, raw, text
