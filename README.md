# Conxept

An instructor tool for Linear Systems and Signals. It finds the exact step where each student's derivation first goes wrong, groups those errors into named misconceptions across the class, and generates verified practice problems for each one.

Built at HackPrinceton (Nov 14–15, 2026).

## Why not just a chat model

Conxept combines repeatable step checks, class-wide misconception counts, and checked practice problems in one instructor workflow. **Correctness is decided by the math engine, never by a language model.** Equivalence is tested by numerical sampling, not symbolic proof. A model-only comparison has not yet been run.

## Scope

Four problem families: inverse Laplace by partial fractions, causal convolution, Fourier transform (fixed convention), Laplace time shift. Each has a hand-written misconception catalog (14 entries total). No handwriting, accounts, grading, or LMS integration.

## Architecture

```
Angular (4200 dev) --Connect/HTTP--> Go gateway (8080) --gRPC/h2c--> Python engine (50051)
                                          |                               |
                                          +------- PostgreSQL 16 ---------+ (engine: read-only)
```

| Component | Stack | Port |
| --- | --- | --- |
| `web/` | Angular, TypeScript, connect-web, KaTeX | 4200 (dev) |
| `gateway/` | Go, connect-go, pgx | 8080 |
| `engine/` | Python, grpc.aio, SymPy, mpmath, Deep Agents | 50051 |
| Database | PostgreSQL 16 (Docker dev, Tiger Cloud demo) | 5432 |

Contracts live in `proto/misconception/v1/` (buf) and are the single source of truth for all three languages.

## Repository layout

```
proto/misconception/v1/   common.proto engine.proto gateway.proto
sql/                      schema.sql queries.sql
engine/                   Python engine + Deep Agent (lane A)
gateway/                  Go gateway (lane B)
web/                      Angular app (lane C)
reference/                starter package (spike code + acceptance tests)
docs/                     spec.md, plan.md
buf.yaml buf.gen.yaml docker-compose.yml Makefile
```

Generated code (`gateway/gen/`, `web/src/gen/`, `engine/gen/`) is never committed. Run `make gen`.

## Setup

Requirements: Python 3.13, Go 1.27, Node 22, and Docker or Homebrew `postgresql@16`.

```bash
cp .env.example .env
python3.13 -m venv .venv && .venv/bin/pip install -r engine/requirements.txt
npm ci && (cd web && npm ci)
go install google.golang.org/protobuf/cmd/protoc-gen-go@v1.36.12
go install connectrpc.com/connect/cmd/protoc-gen-connect-go@v1.21.1
make gen
```

## Running

Everything in containers:

```bash
docker compose up --build    # Postgres, engine, gateway; open http://localhost:8080
```

Or each piece locally:

| Command | Does |
| --- | --- |
| `make gen` | buf generate (Go, TypeScript) + Python stubs |
| `make db` | Postgres 16 (Docker, else Homebrew) + schema + read-only engine role |
| `make engine` | Python server on 50051 |
| `make web-build` | Production build of the Angular app |
| `make gateway` | Go server on 8080, serving the built app |
| `make web` | `ng serve` on 4200 with proxy to 8080 |
| `make test` | `buf lint` + engine tests |
| `make test-gateway` | Gateway end-to-end tests (needs engine and Postgres running) |
| `make eval` | Engine-only evaluation on a seeded synthetic class |
| `make demo` | Seed the default synthetic class and process it through the gateway |

## CI/CD

[.github/workflows/ci.yml](.github/workflows/ci.yml) runs on every pull request and on pushes to `main`:

| Job | Checks |
| --- | --- |
| Protos and codegen | `buf lint`; generates Go, Python and TypeScript once and shares them with the other jobs |
| Engine | 128 pytest tests; the seed-7 evaluation is posted to the run summary |
| Gateway | gofmt, `go vet`, and the end-to-end tests against Postgres 16 and a running engine |
| Web | Prettier check and the production build |
| Images | Builds both Docker images, starts the stack with `docker compose`, and runs `make demo` against it |
| Publish (`main` only) | Pushes `ghcr.io/<owner>/conxept-engine` and `conxept-gateway`, tagged with the commit SHA and `latest` |

Deployment is image-based: pull the two images and run them next to any Postgres 16 (Tiger Cloud for the demo).
The gateway needs `DATABASE_URL` and `ENGINE_ADDR`; the engine needs a read-only `DATABASE_URL` and, for
Analyze, `ANTHROPIC_API_KEY`.

## Docs

- [docs/spec.md](docs/spec.md): full build spec (source of truth)
- [docs/plan.md](docs/plan.md): build plan, lanes, gates, checklist
- [docs/devpost.md](docs/devpost.md): submission draft with measured claims and explicit limits
- [docs/submission-evidence.md](docs/submission-evidence.md): reproduction details and remaining submission gates

## Acknowledgements

[SymPy](https://www.sympy.org), [mpmath](https://mpmath.org), [Deep Agents](https://docs.langchain.com/oss/python/deepagents), [connect-go](https://connectrpc.com), [Angular](https://angular.dev), [KaTeX](https://katex.org), [buf](https://buf.build), [PostgreSQL](https://www.postgresql.org).
