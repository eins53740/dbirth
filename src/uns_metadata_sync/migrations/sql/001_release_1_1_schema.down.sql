-- Release 1.1 schema definition for UNS metadata service
-- Migration: 001_release_1_1_schema (down)

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM pg_publication p
    WHERE p.pubname = 'uns_meta_pub'
  ) THEN
    DROP PUBLICATION uns_meta_pub;
  END IF;
END$$;

DROP TABLE IF EXISTS uns_meta.metric_path_lineage;
DROP TABLE IF EXISTS uns_meta.metric_versions;
DROP TABLE IF EXISTS uns_meta.metric_properties;
DROP TABLE IF EXISTS uns_meta.metrics;
DROP TABLE IF EXISTS uns_meta.devices;

DROP TYPE IF EXISTS uns_meta.spb_property_type;
DROP FUNCTION IF EXISTS uns_meta.set_updated_at();
DROP SCHEMA IF EXISTS uns_meta CASCADE;
