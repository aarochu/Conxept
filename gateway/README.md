# gateway (Lane B, Go)

connect-go `GatewayService` on port 8080 (spec §6.2). Serves the built Angular app, owns every database
write (pgx), and calls the Python engine with a connect-go client using `connect.WithGRPC()` over
cleartext HTTP/2 (h2c). Module name: `misconception`.

| File | Does |
| --- | --- |
| `main.go` | Config from env, pgx pool, mux (`/misconception.v1.GatewayService/` + SPA with `index.html` fallback), h2c server |
| `engine.go` | h2c gRPC clients for `EngineService` and `InstructorAgentService` |
| `service.go` | The 12 RPCs, the §4 limits and defaults (checked before any engine call), error codes |
| `db.go` | All SQL: seeding in one transaction, diagnoses, the four queries from `sql/queries.sql`, briefs |
| `cmd/demo` | `make demo`: seed the default class and process it through the gateway |
| `queries.sql` | Copied from `sql/queries.sql` by `make gen` and embedded; not committed |

Generated code in `gateway/gen/go/` (not committed). Run `make gen` from the repo root first.

## Run

```bash
make db             # Postgres 16 (Docker, else Homebrew postgresql@16) + schema + engine_ro role
make engine         # :50051
make gateway        # :8080 (WEB_DIR defaults to ./web)
make demo           # seed + process 60 students, print the evaluation
make test-gateway   # Go tests against the running engine and Postgres
```

## Measured (this machine)

| Check | Result |
| --- | --- |
| First integration gate: connect-go `WithGRPC()` over h2c to the Python engine | Passed; no grpc-go fallback needed |
| Seed + process 60 students × 8 problems through the gateway (target ≤ 60 s) | 5.4 s with a freshly started engine, 4.8 s warm |
| Evaluation through SQL (`GetEvaluation`) | Same as the engine's own evaluation: 0 false alarms of 167, 313/313 step, 235/235 label, 78/78 held-out |

## Behaviour notes

- **Error codes** (§4): bad input → `INVALID_ARGUMENT`; unknown or malformed class, submission, problem, or misconception id → `NOT_FOUND`; engine unreachable → `UNAVAILABLE`; the engine's `FAILED_PRECONDITION` (agent without an API key) passes through.
- **Defaults**: proto3 cannot tell an unset number from zero, so `0` means "use the default" for `num_students` (60), `seed` (7), `error_rate` (0.6), `heldout_share` (0.25) and `count` (3).
- **Submission ids**: the engine's synthetic ids are derived from the seed, so the gateway gives every stored submission a fresh UUID and remaps ground truth. Seeding the same seed twice therefore works.
- **ProcessClass** clears the class's diagnoses, streams the engine's `DiagnoseBatch`, inserts each result as it arrives, and sets `processed_at` only when every submission is done.
- **Briefs**: `AnalyzeClass` stores each `BriefEvent` in `briefs` (the engine never writes to the database).
