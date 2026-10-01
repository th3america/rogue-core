# Rogue core v0

A local synthetic demonstration of dependency-carrying models, model revision, conditional planning, and governed action. This is the first executable slice, not a complete Synthient or an ARC competition result.

## Candidate boundary

The five engines and Maestro controller live in `rogue.py` in one worker process. Learned interpretation comes from an already-installed local model through a temporary loopback inference companion. The evaluator owns `fixture.py`; its rule and source are absent from the candidate prompt. The candidate has no general filesystem, network, shell, retrieval-of-builder-notes, or external-assistance operation. It sees the declared observation/action interface, its own working record, and tool results. These are interface restrictions, not a demonstrated hostile-process sandbox.

This prototype depends on Python and the existing sibling Greyspark runtime/model directory. It is locally executable but not yet a standalone portable package. The inference service and evaluator are separate supporting processes. Changing that to a literally single-process deployable entity remains packaging work.

## What is implemented

| Engine | Operations |
|---|---|
| Observation | frame-read, frame-diff, object-segment (adjacent equal-value groups, no semantic labels) |
| World/hypothesis store | hypothesis-board, memory-store/retrieve; immutable observation records with integrity hashes |
| Transition | state-simulator, flood, route-planner using candidate-authored bounded expressions |
| Experiment | probe-ranker, compare; outcome partitions rather than invented probabilities |
| History/metacognition | loop-detector, dependency-trace, Rogue-Break |

All records are typed OBSERVATION, DERIVATION, INFERENCE, or ACTION. An environment observation is preserved as supplied. Interpretation does not promote or rewrite it. Every simulated/planned result identifies its model; action outcomes return as new observations. Models remain working hypotheses even after a matching prediction.

The candidate generates the model expression, question, assumptions, focus, continuation reason and route-stop condition. Maestro admits FOLLOW_PLAN, TEST_ALTERNATIVE, ROGUE_BREAK, PARK_UNRESOLVED, TASK_STOP or COMPLETE. A route-stop condition is currently a candidate-authored statement applied through its subsequent decisions, not a separately compiled predicate. Global call/action/time ceilings are enforced mechanically.

Rogue-Break suspends commitment before registering a different model. Predicted transition tables detect equivalent expressions; `x+dx` and `dx+x` cannot count as creative progress. Further reframing is blocked until another observation after a no-delta break. Novelty is scoped to the presently representable one-dimensional state; this is not a universal semantic equivalence test. Predicted control effects, evidence, questions, model revisions, spent budgets and stopping state persist across restart.

The expression interpreter supports bounded integers, `x`, `dx`, `tile`, `width`, arithmetic, comparisons, Boolean operations and conditional expressions. It has no arbitrary code execution. This small language supports compositional conditional rules but cannot express every possible environment mechanic; representation expansion is future work.

## Demonstration and evidence

The developer-designed one-dimensional fixture initially supports a simple movement model, then produces a contradictory transition. A fixed additive-model baseline cycles. The learner receives no task-specific correction during the run. The evaluator checks for contradiction, a candidate-generated break question and revised model, an actual discriminating action, environmental success, and the candidate's completion decision. Generated claims alone do not pass the test.

`test_core.py` contains mechanical checks. Its scripted correct model tests plumbing only and is explicitly excluded from learned-cognition evidence. `evidence/trial-001/` preserves the first local learned attempt, whether it succeeds or fails. The prompt, schema, source hashes, model/runtime hashes and budgets are frozen before that attempt. Every model request/response and actual transition is saved. A new candidate process resumes the exact checkpoint after the first successful model revision when one occurs.

From this directory:

```powershell
python -m unittest -v test_core
python -X utf8 run_demo.py --out evidence/NEW-RUN-ID
```

Each run directory must be new. No download, remote model, global installation or persistent background service is performed. The runner stops its owned local inference process on completion or error. Its memory metric is inference-process peak working set; GPU allocation and total machine/candidate memory are not claimed by that metric.

## Limits of this first slice

- One development world; neither hidden benchmark generalization nor ARC performance established.
- Signed controls, positions, cells and goal are supplied by the synthetic interface. General visual parsing and unknown objective inference are not tested.
- Broad learned creativity, calibrated uncertainty, cross-world memory applicability, self-directed model training and self-modification are not established.
- Candidate failures, malformed expressions, timeouts and budget stops are results, not silently replaced by scripted successes.
- A solved fixture alone does not establish the requested model-revision sequence; the individual evidence checks remain separate.

The project implements a place to test the proposed behavior. Current measured outcomes belong in the run receipts and the linked vault report, not in architectural claims.

## First local results and subsequent repair

- Trial 001, installed Phi-3 Mini Q4: one call, zero actions, PARK_UNRESOLVED. Its explanation said it intended to test while its operation ended the run. Behavioral sequence failed.
- Trial 002, installed Granite 4.2 3B: twenty response-parse failures, zero actions, call-budget stop. The initial adapter failed to preserve raw payloads when parsing failed, so the exact cause of those empty/non-JSON replies is not established. This is an interface failure, not a fair cognitive-capacity result.
- The exact original trial sources are retained under each trial's `qa/frozen-source/` and match the pre-run hashes. Both owned inference processes stopped.
- Subsequent repair preserves the response before parsing, stops after three consecutive protocol errors, and checks model arithmetic before committing it. Sixteen mechanical tests pass. No further learned trial was started after Jason directed attention to the official ARC demo pack. A successful learned model-revision demonstration remains outstanding.
