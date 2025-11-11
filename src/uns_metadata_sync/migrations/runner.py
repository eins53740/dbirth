"""Lightweight psycopg-based migration runner for UNS metadata service."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from importlib.resources import files
from typing import Dict, List, Optional, Tuple

from uns_metadata_sync.db import Connection, connect

MIGRATION_PACKAGE = "uns_metadata_sync.migrations.sql"
SCHEMA_MIGRATIONS_TABLE = "public.schema_migrations"


class MigrationError(Exception):
    """Base exception raised for migration related failures."""


class MigrationChecksumMismatch(MigrationError):
    """Raised when the on-disk migration checksum differs from the recorded one."""


class MigrationNotFound(MigrationError):
    """Raised when a down migration is missing for the requested version."""


@dataclass(frozen=True)
class Migration:
    """Value object describing a single migration pair (up/down)."""

    version: str
    name: str
    up_sql: str
    down_sql: str
    checksum: str


@dataclass(frozen=True)
class AppliedMigration:
    """Row fetched from `schema_migrations`."""

    version: str
    checksum: str


def load_migrations() -> List[Migration]:
    """Load migrations from the packaged `sql` directory sorted by version."""

    base = files(MIGRATION_PACKAGE)
    migrations: List[Migration] = []
    for entry in base.iterdir():
        name = entry.name
        if not name.endswith(".up.sql"):
            continue
        stem = name[:-7]  # strip .up.sql
        down_name = f"{stem}.down.sql"
        down_entry = base / down_name
        if not down_entry.is_file():
            raise MigrationNotFound(f"Missing down script for migration '{stem}'")

        version, _, title = stem.partition("_")
        if not version.isdigit():
            raise MigrationError(
                f"Migration '{stem}' does not start with a numeric version prefix"
            )

        up_sql = entry.read_text(encoding="utf-8")
        down_sql = down_entry.read_text(encoding="utf-8")
        checksum = hashlib.sha256(up_sql.encode("utf-8")).hexdigest()
        migrations.append(
            Migration(
                version=version,
                name=title,
                up_sql=up_sql,
                down_sql=down_sql,
                checksum=checksum,
            )
        )

    migrations.sort(key=lambda m: int(m.version))
    return migrations


def _get_connection(
    conn: Optional[Connection], conninfo: Optional[str]
) -> Tuple[Connection, bool]:
    """Return a connection, creating one if needed."""

    if conn is not None:
        return conn, False
    connection = connect(conninfo)
    connection.row_factory = None
    return connection, True


def _schema_migrations_exists(conn: Connection) -> bool:
    """Return True when the schema_migrations ledger table exists."""

    with conn.transaction():
        result = conn.execute(
            "SELECT to_regclass(%s)",
            (SCHEMA_MIGRATIONS_TABLE,),
        )
        row = result.fetchone()
    return bool(row and row[0])


def _fetch_applied(conn: Connection) -> Dict[str, AppliedMigration]:
    """Load applied migrations from the ledger, returning an empty dict if missing."""

    if not _schema_migrations_exists(conn):
        return {}
    with conn.transaction():
        result = conn.execute(
            f"SELECT version, checksum FROM {SCHEMA_MIGRATIONS_TABLE} ORDER BY version"
        )
        rows = result.fetchall()
    applied: Dict[str, AppliedMigration] = {}
    for version, checksum in rows:
        applied[version] = AppliedMigration(version=version, checksum=checksum)
    return applied


def apply_migrations(
    *,
    conn: Optional[Connection] = None,
    conninfo: Optional[str] = None,
    target_version: Optional[str] = None,
    dry_run: bool = False,
) -> List[Migration]:
    """Apply outstanding migrations up to the optional target version.

    Returns the list of migrations that were executed (or would be executed in dry-run).
    """

    migrations = load_migrations()
    connection, should_close = _get_connection(conn, conninfo)
    executed: List[Migration] = []

    try:
        applied = _fetch_applied(connection)
        for migration in migrations:
            if target_version and int(migration.version) > int(target_version):
                break

            previously = applied.get(migration.version)
            if previously:
                if previously.checksum != migration.checksum:
                    raise MigrationChecksumMismatch(
                        f"Checksum mismatch for migration {migration.version}_{migration.name}"
                    )
                continue

            executed.append(migration)
            if dry_run:
                continue

            with connection.transaction():
                connection.execute(migration.up_sql)
                connection.execute(
                    f"INSERT INTO {SCHEMA_MIGRATIONS_TABLE} (version, checksum) VALUES (%s, %s)",
                    (migration.version, migration.checksum),
                )
    finally:
        if should_close:
            connection.close()

    return executed


def rollback_last(
    *,
    conn: Optional[Connection] = None,
    conninfo: Optional[str] = None,
    dry_run: bool = False,
) -> Optional[Migration]:
    """Rollback the most recently applied migration using its down script."""

    migrations = {migration.version: migration for migration in load_migrations()}
    connection, should_close = _get_connection(conn, conninfo)

    try:
        if not _schema_migrations_exists(connection):
            return None

        result = connection.execute(
            f"SELECT version, checksum FROM {SCHEMA_MIGRATIONS_TABLE} ORDER BY (version)::int DESC LIMIT 1"
        )
        row = result.fetchone()
        if not row:
            return None

        version, checksum = row
        migration = migrations.get(version)
        if migration is None:
            raise MigrationNotFound(f"No migration files found for version {version}")
        if migration.checksum != checksum:
            raise MigrationChecksumMismatch(
                f"Checksum mismatch for migration {version}_{migration.name} during rollback"
            )

        if dry_run:
            return migration

        # Delete the ledger row first, then execute the down SQL. This keeps the
        # transaction consistent even when a down migration drops the ledger (e.g. '000').
        with connection.transaction():
            connection.execute(
                f"DELETE FROM {SCHEMA_MIGRATIONS_TABLE} WHERE version = %s",
                (version,),
            )
            connection.execute(migration.down_sql)
        return migration
    finally:
        if should_close:
            connection.close()


__all__ = [
    "Migration",
    "MigrationError",
    "MigrationChecksumMismatch",
    "MigrationNotFound",
    "apply_migrations",
    "load_migrations",
    "rollback_last",
]
