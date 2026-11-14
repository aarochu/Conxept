# Build plan

Source: [spec.md](spec.md) §10. Deadline: **Sunday Nov 15, 8:00 AM** (Devpost). Target code-complete: **Saturday 11 PM**. Last 3 hours are demo, submission and sleep only.

## Lanes

Each lane is one engineer or agent session on its own branch (`lane/engine`, `lane/gateway`, `lane/web`).

| Lane | Owns | Starts with | Done when |
| --- | --- | --- | --- |
| A: Engine (Python) | `engine/` | Port `reference/` into `engine/`; run acceptance gates | Diagnose, DiagnoseBatch, ListProblems, ListMisconceptions, GenerateClass, GenerateRemediation pass tests; §8.3 evaluation reproduces |
| B: Gateway + data (Go, SQL) | `gateway/` | Go stubs, empty handler, one Diagnose call to engine | All 12 GatewayService RPCs work against real engine + Postgres; ProcessClass streams |
| C: Web (Angular) | `web/` | TS stubs; six routes against a mock gateway | Every route works against the real gateway with the seeded class |

`proto/` and `sql/` are owned by the repo owner.

## Timeline

| Hours | Work | Gate |
| --- | --- | --- |
| H0–H1 | Scaffold, run acceptance gates, confirm Fourier convention | All gates green except Go→Python |
| H1–H4 | A: server, problem bank, catalog. B: stubs, schema, first engine call, SeedSyntheticClass. C: shell, routes, mocks | B's first Diagnose matches the Python test |
| H4–H8 | A: remediation + synthetic generators, eval reproduces. B: ProcessClass, GetHeatmap, GetClusters, GetEvaluation. C: heatmap, clusters, submission view | 60-student class seeded + processed end to end < 60 s |
| H8–H12 | A: Deep Agent + number check. B: AnalyzeClass, GenerateRemediation. C: Try, cluster practice, evaluation page | Analyze brief with real model, number check passes |
| H12–H16 | Model-alone baseline (§8.5); collect + label real classmate derivations; Devpost text from measured results only | Baseline and real-data numbers recorded |
| H16–(deadline−3) | Bug fixes only; catalog frozen; record demo once | Demo runs 3× in a row from a clean DB |
| Last 3 h | Rehearse, submit, sleep | Submitted |

## Acceptance gates

| Gate | Command | Expected |
| --- | --- | --- |
| Contracts | `npx buf lint` | no output |
| Library claims | `.venv/bin/python -m pytest engine/tests/test_diagnose.py engine/tests/test_remediation.py` | diagnosis and checked-practice tests pass (reference package unavailable) |
| Parser | `.venv/bin/python -m pytest engine/tests/test_parse.py` | valid DSL accepted; hostile DSL rejected |
| Engine eval | `make acceptance` | zero false alarms and held-out names; accuracy and p95 targets pass; JSON report saved |
| Python gRPC | `.venv/bin/python -m pytest engine/tests/test_grpc.py` | unary and streaming round trips pass |
| Agent wiring | `.venv/bin/python -m pytest engine/tests/test_agent.py` | scripted tool calls, then checked brief |
| Go→Python | first Diagnose through the gateway | same Diagnosis as Python test |

## Evaluation targets (§8.2)

| Metric | Target |
| --- | --- |
| False alarms | 0 |
| Step accuracy | ≥ 99% |
| Label accuracy | ≥ 95% |
| Held-out detection | ≥ 99% |
| Held-out given a catalog name | 0 |
| Per-diagnosis p95 | ≤ 0.5 s |
| 480-submission class run via gateway | ≤ 60 s |

## Checklist

### H0 scaffold
- [x] Repo, folders, docs, protos, SQL, Makefile, compose
- [ ] Drop starter package into `reference/`
- [x] `npx buf lint` clean
- [ ] Reference acceptance gates green (starter package missing; engine tests cover the same claims)
- [ ] Confirm course Fourier convention: X(jw) = ∫ x(t) e^(−jwt) dt

### Engine (A)
- [x] `parse_step.py`, `diagnose.py`, `problems.py` (written from spec; 32/32 mutations)
- [x] `server.py` with ProcessPoolExecutor (4 workers, 5 s timeout)
- [x] `remediation.py` (two-route verification, never return unverified)
- [x] `synthetic.py` (single seeded RNG, follow-through)
- [x] `agent.py` + number check (scripted-model test; live model not yet run)
- [ ] Optional: Wolfram probe

### Gateway (B)
- [x] Go stubs generated, empty handler compiles
- [x] First Diagnose call to engine (connect-go WithGRPC over h2c worked; no fallback)
- [x] Limits table enforced before engine calls
- [x] SeedSyntheticClass, ProcessClass, ListClasses
- [x] GetHeatmap, GetClusters, GetSubmission, GetEvaluation
- [x] TryDerivation, GenerateRemediation, AnalyzeClass (AnalyzeClass not run with a live model)
- [x] SPA file server with index.html fallback
- [x] 60-student class seeded + processed end to end: 5.4 s cold (target 60 s)

### Web (C)
- [x] Shell, routing (built against the real gateway; no mock needed)
- [x] Class list (Seed, Process + progress bar)
- [x] Dashboard heatmap + clusters + Analyze log (live model not run)
- [x] Cluster page + Generate practice
- [x] Submission view
- [x] Evaluation page
- [x] Try page

### Wrap-up
- [ ] Baseline (§8.5) run and recorded
- [ ] Real classmate derivations collected, half held aside
- [x] Devpost draft from measured numbers only (`docs/devpost.md`; not submitted)
- [x] Automated demo rehearsed 3× from clean DB (Analyze skipped; visual walkthrough and recording still pending)

## Cut list (cut in this order when behind)

1. Wolfram cross-check
2. `/try` page
3. Per-label table
4. Streaming `text_delta` from the agent
5. Tiger Cloud deployment

**Never cut:** heatmap, clusters, verified practice problems, evaluation page.

## Open items

- Course Fourier convention (§3): if different, edit only the f3 key and four f3 catalog entries.
- connect-go + h2c to Python integration gate passed; gateway integration tests and three local rehearsals reproduced the synthetic evaluation.
- Judging criteria, prize eligibility, demo slot: read the Hacker Onsite Handbook.
- Tiger Cloud Free limits: read before relying on it; Docker Postgres is the fallback.
