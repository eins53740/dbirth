import json
import re
from importlib.resources import files
from pathlib import Path

import pytest

CONTRACT_PATH = Path("docs/contracts/postgres_schema.json")


@pytest.mark.contract
def test_schema_contract_matches_migration_sql():
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    ledger_sql = (
        files("uns_metadata_sync.migrations.sql") / "000_schema_migrations.up.sql"
    ).read_text()
    schema_sql = (
        files("uns_metadata_sync.migrations.sql") / "001_release_1_1_schema.up.sql"
    ).read_text()
    combined_sql = "\n".join([ledger_sql, schema_sql])

    def extract(pattern):
        return sorted(set(re.findall(pattern, combined_sql)))

    tables = sorted(
        {
            *extract(r"CREATE TABLE IF NOT EXISTS ([\w\.]+)"),
        }
    )
    indexes = extract(r"CREATE INDEX IF NOT EXISTS (\w+)")
    triggers = extract(r"CREATE TRIGGER (\w+)")
    types = extract(r"CREATE TYPE ([\w\.]+) AS ENUM")
    publications = extract(r"CREATE PUBLICATION (\w+)")

    expected = {
        "tables": tables,
        "indexes": indexes,
        "triggers": triggers,
        "types": types,
        "publications": publications,
    }

    for key, parsed in expected.items():
        assert contract[key] == parsed, f"Schema contract mismatch for {key}: {parsed}"
