import pytest

from uns_metadata_sync.migrations.runner import (
    SCHEMA_MIGRATIONS_TABLE,
    apply_migrations,
    load_migrations,
    rollback_last,
)


class FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class FakeTransaction:
    def __init__(self, connection, **kwargs):
        self._connection = connection
        self.kwargs = kwargs

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeConnection:
    def __init__(self):
        self.has_ledger = False
        self.executed_sql = []
        self.applied = []  # list of (version, checksum)

    def execute(self, sql, params=None):
        self.executed_sql.append((sql, params))
        normalized = " ".join(sql.split())
        if normalized.startswith("SELECT to_regclass"):
            value = SCHEMA_MIGRATIONS_TABLE if self.has_ledger else None
            return FakeCursor([(value,)])
        if normalized.startswith(
            f"SELECT version, checksum FROM {SCHEMA_MIGRATIONS_TABLE} ORDER BY (version)::int DESC"
        ):
            if not self.applied:
                return FakeCursor([])
            version, checksum = self.applied[-1]
            return FakeCursor([(version, checksum)])
        if normalized.startswith(
            f"SELECT version, checksum FROM {SCHEMA_MIGRATIONS_TABLE} ORDER BY applied_at DESC"
        ):
            if not self.applied:
                return FakeCursor([])
            version, checksum = self.applied[-1]
            return FakeCursor([(version, checksum)])
        if normalized.startswith(
            f"SELECT version, checksum FROM {SCHEMA_MIGRATIONS_TABLE} ORDER BY version"
        ):
            return FakeCursor(list(self.applied))
        if normalized.startswith(f"INSERT INTO {SCHEMA_MIGRATIONS_TABLE}"):
            version, checksum = params
            self.applied.append((version, checksum))
            self.has_ledger = True
            return FakeCursor([])
        if normalized.startswith(f"DELETE FROM {SCHEMA_MIGRATIONS_TABLE}"):
            version = params[0]
            self.applied = [row for row in self.applied if row[0] != version]
            if not self.applied:
                self.has_ledger = False
            return FakeCursor([])
        if "CREATE TABLE IF NOT EXISTS public.schema_migrations" in normalized:
            self.has_ledger = True
        if "DROP TABLE IF EXISTS public.schema_migrations" in normalized:
            self.has_ledger = False
        return FakeCursor([])

    def transaction(self, *args, **kwargs):
        return FakeTransaction(self, **kwargs)

    def close(self):
        pass


@pytest.mark.unit
def test_load_migrations_orders_versions():
    migrations = load_migrations()
    versions = [migration.version for migration in migrations]
    assert versions == sorted(versions)
    assert any(migration.name.startswith("release_1_1") for migration in migrations)


@pytest.mark.unit
def test_apply_migrations_creates_records_in_order():
    connection = FakeConnection()

    executed = apply_migrations(conn=connection)

    assert [migration.version for migration in executed] == ["000", "001"]
    assert connection.applied == [
        (migration.version, migration.checksum) for migration in executed
    ]

    # Running again should be a no-op.
    executed_again = apply_migrations(conn=connection)
    assert executed_again == []


@pytest.mark.unit
def test_rollback_last_removes_latest_entry():
    connection = FakeConnection()
    apply_migrations(conn=connection)

    rolled_back = rollback_last(conn=connection)

    assert rolled_back is not None
    assert rolled_back.version == "001"
    assert [row[0] for row in connection.applied] == ["000"]


@pytest.mark.unit
def test_apply_migrations_dry_run_only_reports():
    connection = FakeConnection()

    executed = apply_migrations(conn=connection, dry_run=True)
    assert [migration.version for migration in executed] == ["000", "001"]
    assert connection.applied == []
