#!/usr/bin/env bash
# Start a dev PostgreSQL 16 and apply sql/schema.sql plus dev roles. Idempotent.
# Uses Docker when available, otherwise a Homebrew postgresql@16 install.
set -euo pipefail
cd "$(dirname "$0")/.."

if command -v docker >/dev/null 2>&1; then
  docker compose up -d postgres
  until docker compose exec -T postgres pg_isready -U postgres >/dev/null 2>&1; do sleep 1; done
  docker compose exec -T postgres psql -U postgres -d misconception -v ON_ERROR_STOP=1 < scripts/roles.sql
  echo "postgres (docker) ready on :5432"
  exit 0
fi

# The postmaster refuses to start on macOS without a valid locale.
export LC_ALL="${LC_ALL:-en_US.UTF-8}"
PGBIN="${PGBIN:-$(brew --prefix postgresql@16 2>/dev/null)/bin}"
PGDATA="${PGDATA:-$(brew --prefix 2>/dev/null)/var/postgresql@16}"
if [ ! -x "$PGBIN/pg_ctl" ]; then
  echo "need docker or: brew install postgresql@16" >&2
  exit 1
fi
if [ ! -f "$PGDATA/PG_VERSION" ]; then
  "$PGBIN/initdb" -D "$PGDATA" --auth=trust -E UTF8 >/dev/null
fi
if ! "$PGBIN/pg_ctl" -D "$PGDATA" status >/dev/null 2>&1; then
  "$PGBIN/pg_ctl" -D "$PGDATA" -l "$PGDATA/server.log" -w start
fi

run_psql() { "$PGBIN/psql" -v ON_ERROR_STOP=1 -q "$@"; }

if ! run_psql -d postgres -Atc "SELECT 1 FROM pg_roles WHERE rolname='postgres'" | grep -q 1; then
  run_psql -d postgres -c "CREATE ROLE postgres SUPERUSER LOGIN PASSWORD 'postgres'"
fi
if ! run_psql -d postgres -Atc "SELECT 1 FROM pg_database WHERE datname='misconception'" | grep -q 1; then
  run_psql -d postgres -c "CREATE DATABASE misconception OWNER postgres"
  run_psql -U postgres -d misconception -f sql/schema.sql
fi
run_psql -U postgres -d misconception -f scripts/roles.sql
echo "postgres (local) ready on :5432"
