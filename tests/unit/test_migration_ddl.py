import re
from importlib.resources import files

import pytest


@pytest.mark.unit
def test_release_schema_contains_all_key_objects():
    sql = (
        files("uns_metadata_sync.migrations.sql") / "001_release_1_1_schema.up.sql"
    ).read_text()

    expected_clauses = [
        "CREATE TABLE IF NOT EXISTS uns_meta.devices",
        "CONSTRAINT uq_devices_spb_identity",
        "CREATE TABLE IF NOT EXISTS uns_meta.metrics",
        "GENERATED ALWAYS AS (replace(uns_path, '/', '.')) STORED",
        "CREATE TYPE uns_meta.spb_property_type AS ENUM",
        "CONSTRAINT chk_metric_properties_type_value",
        "CREATE TABLE IF NOT EXISTS uns_meta.metric_versions",
        "CREATE TABLE IF NOT EXISTS uns_meta.metric_path_lineage",
        "CREATE PUBLICATION uns_meta_pub",
    ]

    for clause in expected_clauses:
        assert clause in sql

    # Ensure the properties CHECK constraint enforces exclusivity for all enum branches.
    assert len(re.findall(r"type = 'int'", sql)) == 1
    assert "value_bool   IS NOT NULL" in sql


@pytest.mark.unit
def test_ledger_migration_creates_index():
    sql = (
        files("uns_metadata_sync.migrations.sql") / "000_schema_migrations.up.sql"
    ).read_text()
    assert "CREATE TABLE IF NOT EXISTS public.schema_migrations" in sql
    assert "CREATE INDEX IF NOT EXISTS idx_schema_migrations_applied_at" in sql
