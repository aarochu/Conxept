# Conxept

An instructor tool for Linear Systems and Signals. It finds the exact step where each student's derivation first goes wrong, groups those errors into named misconceptions across the class, and generates verified practice problems for each one.

Built at HackPrinceton (Nov 14–15, 2026).

## Why not just a chat model

A chat model can mark one derivation. It can't deterministically prove which step broke, aggregate hundreds of submissions into a class heatmap, or guarantee a generated answer key is correct. Those three things are the product. **Correctness is decided by SymPy, never by a language model.**

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

Requirements: Python 3.13, Go 1.24+, Node 22, Docker.

```bash
cp .env.example .env
pip install sympy mpmath grpcio grpcio-tools protobuf deepagents "psycopg[binary]"
npm i -D @bufbuild/buf @bufbuild/protoc-gen-es @bufbuild/protobuf
npm i @connectrpc/connect @connectrpc/connect-web
go install google.golang.org/protobuf/cmd/protoc-gen-go@latest
go install connectrpc.com/connect/cmd/protoc-gen-connect-go@latest
make gen
```

## Running

| Command | Does |
| --- | --- |
| `make gen` | buf generate + Python stubs |
| `make db` | start postgres:16 and apply schema |
| `make engine` | Python server on 50051 |
| `make gateway` | Go server on 8080 |
| `make web` | `ng serve` with proxy to 8080 |
| `make test` | engine tests + `buf lint` |
| `make demo` | seed the default synthetic class and process it |

## Docs

- [docs/spec.md](docs/spec.md): full build spec (source of truth)
- [docs/plan.md](docs/plan.md): build plan, lanes, gates, checklist

## Acknowledgements

[SymPy](https://www.sympy.org), [mpmath](https://mpmath.org), [Deep Agents](https://docs.langchain.com/oss/python/deepagents), [connect-go](https://connectrpc.com), [Angular](https://angular.dev), [KaTeX](https://katex.org), [buf](https://buf.build), [PostgreSQL](https://www.postgresql.org).
