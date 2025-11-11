"""Database utilities and psycopg2 helpers for UNS metadata persistence."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterator, Optional, Tuple

import psycopg2
from psycopg2 import Error, OperationalError, errors, sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from psycopg2.extras import Json as _Json
from psycopg2.extras import (
    LogicalReplicationConnection as _LogicalReplicationConnection,
)
from psycopg2.extras import RealDictCursor

if TYPE_CHECKING:  # pragma: no cover - import-time helper only
    from uns_metadata_sync.config import Settings


class _CompatJson(_Json):
    """psycopg2 Json wrapper that mimics psycopg3's attribute surface."""

    def __init__(self, adapted, dumps=None):
        super().__init__(adapted, dumps=dumps)
        self.obj = adapted

    @property
    def value(self):
        return self.obj


Json = _CompatJson
Jsonb = _CompatJson


class _DictRowSentinel:
    """Sentinel representing row factory for dictionary rows."""


dict_row = _DictRowSentinel()

_USE_DEFAULT_FACTORY = object()


class _ExecuteResult:
    def __init__(self, cursor):
        self._cursor = cursor
        self._rows: Optional[list] = None
        self._index = 0
        self._load_rows()

    def fetchone(self):
        rows = self._load_rows()
        if self._index >= len(rows):
            return None
        row = rows[self._index]
        self._index += 1
        return row

    def fetchall(self):
        rows = self._load_rows()
        remaining = rows[self._index :]
        self._index = len(rows)
        return remaining

    def fetchmany(self, size: Optional[int] = None):
        rows = self._load_rows()
        if size is None:
            size = len(rows) - self._index
        start = self._index
        end = min(len(rows), start + size)
        self._index = end
        return rows[start:end]

    def __iter__(self) -> Iterator:
        rows = self._load_rows()
        start = self._index
        self._index = len(rows)
        return iter(rows[start:])

    def close(self) -> None:
        if not self._cursor.closed:
            self._cursor.close()

    def _load_rows(self) -> list:
        if self._rows is None:
            if self._cursor.description is not None:
                self._rows = list(self._cursor.fetchall())
            else:
                self._rows = []
            self._cursor.close()
        return self._rows


class _EmptyResult:
    def fetchone(self):
        return None

    def fetchall(self):
        return []

    def fetchmany(self, size: Optional[int] = None):
        return []

    def __iter__(self) -> Iterator:
        return iter(())

    def close(self) -> None:
        return None


class _Transaction:
    def __init__(self, connection: "Connection"):
        self._connection = connection

    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type is None:
            try:
                self._connection.commit()
            except psycopg2.ProgrammingError:
                pass
        else:
            try:
                self._connection.rollback()
            except psycopg2.ProgrammingError:
                pass
        return False


class Connection(psycopg2.extensions.connection):
    """psycopg2 connection subclass providing convenience helpers used by the service."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.autocommit = True
        self._row_factory = None

    def transaction(self) -> _Transaction:
        return _Transaction(self)

    def cursor(self, *args, **kwargs):
        row_factory = kwargs.pop("row_factory", _USE_DEFAULT_FACTORY)
        cursor_factory = kwargs.get("cursor_factory")
        if cursor_factory is None:
            if row_factory is dict_row:
                kwargs["cursor_factory"] = RealDictCursor
            elif row_factory is _USE_DEFAULT_FACTORY:
                if self._row_factory is dict_row:
                    kwargs["cursor_factory"] = RealDictCursor
            elif row_factory is not None:
                kwargs["cursor_factory"] = row_factory
        return super().cursor(*args, **kwargs)

    def execute(
        self, query: str, params: Optional[Tuple[Any, ...]] = None
    ) -> _ExecuteResult:
        if hasattr(query, "as_string"):
            raw_sql = query.as_string(self)
        else:
            raw_sql = str(query) if query is not None else ""
        text = raw_sql.upper()
        if text.lstrip().startswith("DROP DATABASE") or text.lstrip().startswith(
            "CREATE DATABASE"
        ):
            raw_conn = psycopg2.connect(self.dsn)
            raw_conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            try:
                with raw_conn.cursor() as cur:
                    cur.execute(query, params)
            finally:
                raw_conn.close()
            return _EmptyResult()
        if self.autocommit:
            try:
                super().commit()
            except psycopg2.ProgrammingError:
                pass
        cursor = self.cursor()
        cursor.execute(query, params)
        if self.autocommit and cursor.description is None:
            try:
                super().commit()
            except psycopg2.ProgrammingError:
                pass
        return _ExecuteResult(cursor)

    @property
    def row_factory(self):
        return self._row_factory

    @row_factory.setter
    def row_factory(self, factory) -> None:
        self._row_factory = factory


class LogicalReplicationConnection(_LogicalReplicationConnection):
    """Logical replication connection with helper constructor."""

    @classmethod
    def connect(cls, dsn: str):
        return psycopg2.connect(dsn, connection_factory=cls)


def connect(*args, **kwargs) -> Connection:
    """Create a Connection instance using psycopg2."""

    kwargs.setdefault("connection_factory", Connection)
    return psycopg2.connect(*args, **kwargs)


def connect_from_settings(settings: "Settings") -> Connection:
    """Create a psycopg2 connection using the provided service settings."""

    conn = connect(
        host=settings.db_host,
        port=settings.db_port,
        dbname=settings.db_name,
        user=settings.db_user,
        password=settings.db_password,
        options=f"-c search_path={settings.db_schema},public",
    )
    return conn


__all__ = [
    "Connection",
    "Error",
    "Json",
    "Jsonb",
    "LogicalReplicationConnection",
    "OperationalError",
    "connect",
    "connect_from_settings",
    "dict_row",
    "errors",
    "sql",
]
