# engine (Lane A, Python)

`grpc.aio` server on port 50051 registering `EngineService` and `InstructorAgentService` (spec §6.1).
Correctness is decided by sampling + `mpmath.quad`, never by the language model.

| File | Does |
| --- | --- |
| `parse_step.py` | Step DSL parser (§3): own tokenizer + recursive-descent parser, rules checked on the tree before any SymPy is built; DSL/LaTeX printers |
| `diagnose.py` | Equivalence test (6 seeded points, rel. tol 1e-6), the four families, the 14-entry catalog, residual labels, `diagnose` |
| `problems.py` | Problem bank: id parsing, parameter grids, the eight default problems |
| `synthetic.py` | Synthetic class generator (§8.1): one seeded RNG, valid rewrites, catalog and held-out errors, follow-through |
| `remediation.py` | Practice-problem generator (§7.3): two verification routes, never returns unverified |
| `agent.py` | Deep Agent for Analyze (§6.3): four tools, fixed system prompt, number check |
| `llm.py` | Picks the model for Analyze and the baseline: `openrouter:<id>` or `anthropic:<id>`, and the key each needs |
| `free_models.py` | Lists OpenRouter models that are free and support tool calling (`make free-models`) |
| `server.py` | gRPC server: 4-worker process pool, 5 s per-diagnosis timeout |
| `evaluate.py` | Engine-only evaluation on a synthetic class (§8.2 metrics) |

Generated stubs go in `engine/gen/` (not committed).

## Model for Analyze and the baseline (free option)

Diagnosis never calls a model. Only Analyze (the instructor brief) and `make baseline` do, and
either works with a free OpenRouter key:

```bash
export OPENROUTER_API_KEY=...        # from openrouter.ai; no credit needed for ":free" models
make free-models                     # current free models that support tool calling
export AGENT_MODEL=openrouter:<id>   # optional; blank uses llm.OPENROUTER_DEFAULT
```

With only `OPENROUTER_API_KEY` set, both default to a free model. With `ANTHROPIC_API_KEY` set,
they default to Claude. Free models are rate-limited: the baseline retries on HTTP 429 and sends
two requests at a time, and its ~200 calls can exceed a free daily allowance. Analyze keeps the
number check, so a brief with an invented count is replaced by an error rather than shown.

## Run

```bash
make gen          # from repo root: generates engine/gen/
make engine       # serves on :50051
make test         # buf lint + pytest
make eval         # engine-only evaluation, 60 students, seed 7
make acceptance   # same fixed class; fail on unmet accuracy, naming or p95 targets
```

`make acceptance` writes `engine/acceptance_out/report.json` and returns nonzero
if a target in the plan's synthetic evaluation table fails. The numerical value
cache is cleared before each diagnosis; timings still depend on the host and
other SymPy caches. This is not the gateway's 60-second class-processing gate or
a measurement of real-student accuracy. Keep generated reports local.

## Measured (this machine, seed 7, 60 students × 8 problems = 480 submissions)

| Measure | Result |
| --- | --- |
| False alarms | 0 of 167 correct (about half written as valid rewrites) |
| Flagged at the true step | 313 of 313 |
| Catalog id returned | 235 of 235, exactly one id each time |
| Held-out detected / given a catalog name | 78 of 78 / 0 |
| 32 catalog mutations on the default problems | 32 of 32 |
| Per-diagnosis latency, cold cache (96 diagnoses, 22 problems) | median 0.021 s, p95 0.339 s, max 0.758 s |

Catalog results are self-consistency, not accuracy on real students: the synthetic errors are built by the same functions that recognize them.

## Notes and deviations from the spec

- `reference/` (the starter package) was not available, so the engine was written from spec §3, §7, §8 and checked against the spec's claims by the tests in `tests/`.
- Briefs: §6.3 says "save to briefs", but §2 says only the gateway writes to the database. The engine streams `BriefEvent` with a new UUID; **the gateway must insert it into `briefs`**.
- `GenerateClass` uses `error_rate` and `heldout_share` exactly as sent; the gateway applies the defaults (0.6, 0.25) per §4.
- The parser also rejects nested powers like `(t^2)^3` (to stop huge integer powers); everything else follows the §3 rules exactly.
- Wolfram cross-check is not built (first item on the cut list).
