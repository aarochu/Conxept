# Tiger Cloud demo deployment

Status: deployment configuration is prepared; no hosted database or deployment host has been provisioned or tested. Local Docker Postgres remains the demo fallback.

## Database

Create a service using the [Tiger Cloud quickstart](https://www.tigerdata.com/docs/get-started/quickstart/create-service). Select the free Shared option if available and review its current limits in the console. Save the connection settings privately; retain the service URL's TLS settings. Conxept uses ordinary PostgreSQL tables and does not require TimescaleDB extensions.

Connect with `psql` using the service administrator connection and apply `sql/schema.sql` to a new, dedicated demo database. Do not apply `scripts/roles.sql` in the cloud: it contains local development credentials and a hard-coded database name.

Connected as the schema owner, create a dedicated read-only engine role; the engine must never own the schema. The [Tiger Cloud role guide](https://www.tigerdata.com/docs/deploy/tiger-cloud/tiger-cloud-aws/security/read-only-role) documents the underlying grants:

```sql
CREATE ROLE engine_ro LOGIN;
GRANT USAGE ON SCHEMA public TO engine_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO engine_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO engine_ro;
ALTER ROLE engine_ro SET default_transaction_read_only = on;
```

In `psql`, use `\password engine_ro` to set a unique password without putting it in command history. Grant CONNECT on the actual database if its public CONNECT privilege has been revoked. Use the schema-owner connection for the gateway and the new role for the engine. URL-encode credentials when constructing connection URLs.

Verify the engine connection before starting the app:

```sql
SELECT current_user, current_database();
SHOW transaction_read_only;
SELECT count(*) FROM classes;
SELECT has_table_privilege(current_user, 'classes', 'INSERT');
```

Expected: `engine_ro`, the intended database, `on`, a successful count, and `false`. The default-privilege grant applies to future tables created by the role executing it; run it as the schema owner.

## Application host

Use a Docker host that can reach the database. Copy `deploy/.env.example` to `deploy/.env`, restrict its permissions to the host owner, and fill in the two connection URLs. Set `IMAGE_TAG` to the full SHA of a `main` commit whose Publish images jobs succeeded; both services use that same tag. Authenticate Docker to GHCR if the packages are private.

```bash
chmod 600 deploy/.env
docker compose --env-file deploy/.env -f deploy/compose.yml config --quiet
docker compose --env-file deploy/.env -f deploy/compose.yml pull
docker compose --env-file deploy/.env -f deploy/compose.yml up -d --wait
```

Only the gateway binds a host port, on loopback. For the demo, forward it over SSH (`ssh -L 8080:127.0.0.1:8080 your-host`) and open `http://localhost:8080`. A public deployment needs HTTPS and access control in front of the gateway: the app intentionally has no accounts and exposes data-changing demo actions. The engine must remain internal.

Open the class list, seed a synthetic class, Process, then verify the heatmap, clusters, one submission, practice problems, and evaluation. Analyze requires a valid model key; record it as skipped if unavailable. `make demo` is an alternative smoke check through the forwarded port; it inserts another synthetic class. Never use `make rehearse` against this database: its reset deletes all project data.

## Rollback and fallback

Keep the previous image SHA. To roll back application code, set `IMAGE_TAG` to that SHA and repeat pull/up. This does not undo database writes or schema changes. This deployment adds no schema migration.

If hosting is unavailable, use the repository's original `docker compose up --build` and demonstrate locally. Do not claim a Tiger Cloud deployment until the hosted smoke check passes. Record the image SHA, date, evaluation counts, and whether Analyze ran in the submission evidence.
