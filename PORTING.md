# Porting Rogue Core

Rogue Core has two portability layers: a standard-library mechanical core and a
model-backed demonstration runner. Verify them separately. Mechanical tests do
not establish learned cognition, and swapping a model runtime does not establish
equivalent model behavior.

## Preserve these invariants

- OBSERVATION, DERIVATION, INFERENCE, and ACTION remain distinct record types.
- Interpretations never rewrite supplied environmental observations.
- Plans and simulations identify the hypothesis on which they depend.
- Contradiction, Rogue-Break, model revision, discriminating action, environment
  result, and completion remain separately testable events.
- Completion requires environmental evidence; malformed model output and budget
  stops remain failures/results rather than scripted success.
- The candidate receives only the declared prompt, schema, working record, and
  tool results. Evaluator rules remain outside its prompt.
- Every model request/response and runtime/source identity needed for the trial
  receipt remains captured.

## Replaceable adapters

| Adapter | Current implementation | Target contract |
|---|---|---|
| Cognition endpoint | loopback OpenAI-style chat-completions HTTP | Return schema-conforming decisions; preserve raw response before parsing and timeout behavior |
| Inference process | llama.cpp executable | Owned temporary process, loopback-only, readiness check, bounded resources, stopped on success/error |
| Model artifact | local GGUF | Explicit path, immutable identity/hash in the frozen contract |
| Environment | `TinyWorld` evaluator fixture | Supply observations/actions without leaking hidden rule into candidate prompt |
| Persistence | JSON state and JSONL calls | Preserve hashes, restart point, raw payloads, and immutable run-directory convention |

## Runtime configuration

The runner accepts target paths instead of requiring the original sibling
directory:

```text
python run_demo.py --out evidence/NEW-RUN \
  --server /path/to/inference-server \
  --model-path /path/to/model.gguf
```

Alternatives are `--runtime-dir`, `ROGUE_RUNTIME_DIR`,
`ROGUE_SERVER_PATH`, and `ROGUE_MODEL_PATH`. The original sibling layout remains
a compatibility fallback, not a portability requirement.

If the target server uses a different API, implement a narrow cognition adapter
that preserves request/response capture, schema enforcement, timeouts, and error
classification. Do not bury prompt changes inside the transport adapter.

## Target conversion

1. Record OS, architecture, Python version, inference server/version/hash,
   model/hash, accelerator, resource ceilings, and endpoint schema.
2. Run mechanical tests without a model.
3. Independently test server lifecycle and a schema-conforming response.
4. Freeze prompt, schema, fixture, source hashes, model, runtime, seed, and
   budgets before a learned trial.
5. Use a new output directory. Preserve failures and raw responses.
6. Verify restart, cleanup, and the six behavioral checks independently.
7. Label the result for that exact model/runtime/fixture. Do not generalize it to
   ARC performance, consciousness, or broad creativity.
8. Write a `PortableScaffoldConversion/1` receipt plus the existing run receipt.

## Verification matrix

```text
python -m unittest -v test_core
python run_demo.py --help
```

The model-backed command is target-specific and must be executed separately with
explicit server/model paths. Cross-platform CI covers only the mechanical core.

## AI handoff

A converting AI must list the model/runtime/API differences before editing. It
must not replace failed model decisions with scripted ones, leak the evaluator
rule, or describe mechanical tests as learned-recursion evidence.
