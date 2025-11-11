-- Schema migrations ledger
-- Migration: 000_schema_migrations (up)

CREATE TABLE IF NOT EXISTS public.schema_migrations (
  version    TEXT PRIMARY KEY,
  checksum   TEXT NOT NULL,
  applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_schema_migrations_applied_at
  ON public.schema_migrations (applied_at DESC);
