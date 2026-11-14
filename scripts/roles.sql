-- Dev roles. The engine connects as engine_ro and can only read (spec section 5).
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'engine_ro') THEN
    CREATE ROLE engine_ro LOGIN PASSWORD 'engine_ro';
  END IF;
END $$;
GRANT CONNECT ON DATABASE misconception TO engine_ro;
GRANT USAGE ON SCHEMA public TO engine_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO engine_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO engine_ro;
ALTER ROLE engine_ro SET default_transaction_read_only = on;
