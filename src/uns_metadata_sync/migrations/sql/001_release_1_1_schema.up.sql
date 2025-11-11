-- Release 1.1 schema definition for UNS metadata service
-- Migration: 001_release_1_1_schema (up)

CREATE SCHEMA IF NOT EXISTS uns_meta;

CREATE OR REPLACE FUNCTION uns_meta.set_updated_at() RETURNS trigger AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;$$ LANGUAGE plpgsql;

CREATE TABLE IF NOT EXISTS uns_meta.devices (
  device_id     BIGSERIAL PRIMARY KEY,
  group_id      TEXT        NOT NULL,
  country       TEXT        NOT NULL,
  business_unit TEXT        NOT NULL,
  plant         TEXT        NOT NULL,
  edge          TEXT        NOT NULL,
  device        TEXT        NOT NULL,
  uns_path      TEXT        NOT NULL UNIQUE,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_devices_spb_identity UNIQUE (group_id, edge, device)
);

CREATE INDEX IF NOT EXISTS idx_devices_plant    ON uns_meta.devices (plant);
CREATE INDEX IF NOT EXISTS idx_devices_uns_path ON uns_meta.devices (uns_path);

CREATE TRIGGER trg_devices_updated_at
BEFORE UPDATE ON uns_meta.devices
FOR EACH ROW EXECUTE FUNCTION uns_meta.set_updated_at();

CREATE TABLE IF NOT EXISTS uns_meta.metrics (
  metric_id   BIGSERIAL PRIMARY KEY,
  device_id   BIGINT      NOT NULL REFERENCES uns_meta.devices(device_id) ON DELETE CASCADE,
  name        TEXT        NOT NULL,
  uns_path    TEXT        NOT NULL UNIQUE,
  canary_id   TEXT        GENERATED ALWAYS AS (replace(uns_path, '/', '.')) STORED,
  datatype    TEXT        NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_metric_spb_identity UNIQUE (device_id, name)
);

CREATE INDEX IF NOT EXISTS idx_metrics_device_id ON uns_meta.metrics (device_id);
CREATE INDEX IF NOT EXISTS idx_metrics_canary_id ON uns_meta.metrics (canary_id);
CREATE INDEX IF NOT EXISTS idx_metrics_uns_path  ON uns_meta.metrics (uns_path);

CREATE TRIGGER trg_metrics_updated_at
BEFORE UPDATE ON uns_meta.metrics
FOR EACH ROW EXECUTE FUNCTION uns_meta.set_updated_at();

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_type t
    WHERE t.typname = 'spb_property_type'
      AND t.typnamespace = 'uns_meta'::regnamespace
  ) THEN
    CREATE TYPE uns_meta.spb_property_type AS ENUM ('int','long','float','double','string','boolean');
  END IF;
END$$;

CREATE TABLE IF NOT EXISTS uns_meta.metric_properties (
  metric_id     BIGINT      NOT NULL REFERENCES uns_meta.metrics(metric_id) ON DELETE CASCADE,
  key           TEXT        NOT NULL,
  type          uns_meta.spb_property_type NOT NULL,
  value_int     INTEGER,
  value_long    BIGINT,
  value_float   REAL,
  value_double  DOUBLE PRECISION,
  value_string  TEXT,
  value_bool    BOOLEAN,
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (metric_id, key),
  CONSTRAINT chk_metric_properties_type_value CHECK (
    (type = 'int'     AND value_int    IS NOT NULL AND value_long IS NULL AND value_float IS NULL AND value_double IS NULL AND value_string IS NULL AND value_bool IS NULL) OR
    (type = 'long'    AND value_long   IS NOT NULL AND value_int  IS NULL AND value_float IS NULL AND value_double IS NULL AND value_string IS NULL AND value_bool IS NULL) OR
    (type = 'float'   AND value_float  IS NOT NULL AND value_int  IS NULL AND value_long  IS NULL AND value_double IS NULL AND value_string IS NULL AND value_bool IS NULL) OR
    (type = 'double'  AND value_double IS NOT NULL AND value_int  IS NULL AND value_long  IS NULL AND value_float  IS NULL AND value_string IS NULL AND value_bool IS NULL) OR
    (type = 'string'  AND value_string IS NOT NULL AND value_int  IS NULL AND value_long  IS NULL AND value_float  IS NULL AND value_double IS NULL AND value_bool IS NULL) OR
    (type = 'boolean' AND value_bool   IS NOT NULL AND value_int  IS NULL AND value_long  IS NULL AND value_float  IS NULL AND value_double IS NULL AND value_string IS NULL)
  )
);

CREATE INDEX IF NOT EXISTS idx_prop_metric_updated ON uns_meta.metric_properties (metric_id, updated_at DESC);

CREATE TRIGGER trg_metric_properties_updated_at
BEFORE UPDATE ON uns_meta.metric_properties
FOR EACH ROW EXECUTE FUNCTION uns_meta.set_updated_at();

CREATE TABLE IF NOT EXISTS uns_meta.metric_versions (
  version_id BIGSERIAL   PRIMARY KEY,
  metric_id  BIGINT      NOT NULL REFERENCES uns_meta.metrics(metric_id) ON DELETE CASCADE,
  changed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  changed_by TEXT        NOT NULL DEFAULT 'system',
  diff       JSONB       NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_versions_metric_changed ON uns_meta.metric_versions (metric_id, changed_at DESC);

CREATE TABLE IF NOT EXISTS uns_meta.metric_path_lineage (
  lineage_id   BIGSERIAL   PRIMARY KEY,
  metric_id    BIGINT      NOT NULL REFERENCES uns_meta.metrics(metric_id) ON DELETE CASCADE,
  old_uns_path TEXT        NOT NULL,
  new_uns_path TEXT        NOT NULL,
  changed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_lineage UNIQUE (metric_id, old_uns_path, new_uns_path)
);

CREATE INDEX IF NOT EXISTS idx_lineage_old ON uns_meta.metric_path_lineage (old_uns_path);
CREATE INDEX IF NOT EXISTS idx_lineage_new ON uns_meta.metric_path_lineage (new_uns_path);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_publication p
    WHERE p.pubname = 'uns_meta_pub'
  ) THEN
    CREATE PUBLICATION uns_meta_pub FOR TABLE
      uns_meta.metrics,
      uns_meta.metric_properties;
  END IF;
END$$;
