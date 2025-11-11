"""Repository helpers for metadata persistence upserts."""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Sequence

from psycopg2 import Error

from . import Connection, dict_row


class RepositoryError(Exception):
    """Raised when repository operations fail."""


@dataclass(frozen=True)
class DevicePayload:
    group_id: str
    country: str
    business_unit: str
    plant: str
    edge: str
    device: str
    uns_path: str


@dataclass(frozen=True)
class MetricPayload:
    device_id: int
    name: str
    uns_path: str
    datatype: str


@dataclass(frozen=True)
class MetricPropertyPayload:
    metric_id: int
    key: str
    type: str
    value: Any


@dataclass(frozen=True)
class UpsertResult:
    status: str  # inserted | updated | noop
    record: Dict[str, Any]


class MetadataRepository:
    """Convenience wrapper around psycopg connection for metadata upserts."""

    def __init__(self, conn: Connection):
        self.conn = conn
        self.conn.row_factory = dict_row

    # ------------------------------------------------------------------
    def upsert_device(self, payload: DevicePayload) -> UpsertResult:
        try:
            with self.conn.transaction():
                existing = self.conn.execute(
                    """
                    SELECT device_id,
                           group_id,
                           country,
                           business_unit,
                           plant,
                           edge,
                           device,
                           uns_path,
                           created_at,
                           updated_at
                      FROM uns_meta.devices
                     WHERE uns_path = %s
                    """,
                    (payload.uns_path,),
                ).fetchone()

                if existing:
                    if self._device_rows_equal(existing, payload):
                        return UpsertResult("noop", existing)

                    updated = self.conn.execute(
                        """
                        UPDATE uns_meta.devices
                           SET group_id = %s,
                               country = %s,
                               business_unit = %s,
                               plant = %s,
                               edge = %s,
                               device = %s
                         WHERE device_id = %s
                     RETURNING device_id,
                               group_id,
                               country,
                               business_unit,
                               plant,
                               edge,
                               device,
                               uns_path,
                               created_at,
                               updated_at
                        """,
                        (
                            payload.group_id,
                            payload.country,
                            payload.business_unit,
                            payload.plant,
                            payload.edge,
                            payload.device,
                            existing["device_id"],
                        ),
                    ).fetchone()
                    return UpsertResult("updated", updated)

                identity = self.conn.execute(
                    """
                    SELECT device_id,
                           uns_path
                      FROM uns_meta.devices
                     WHERE group_id = %s
                       AND edge = %s
                       AND device = %s
                    """,
                    (payload.group_id, payload.edge, payload.device),
                ).fetchone()

                if identity:
                    updated = self.conn.execute(
                        """
                        UPDATE uns_meta.devices
                           SET country = %s,
                               business_unit = %s,
                               plant = %s,
                               uns_path = %s
                         WHERE device_id = %s
                     RETURNING device_id,
                               group_id,
                               country,
                               business_unit,
                               plant,
                               edge,
                               device,
                               uns_path,
                               created_at,
                               updated_at
                        """,
                        (
                            payload.country,
                            payload.business_unit,
                            payload.plant,
                            payload.uns_path,
                            identity["device_id"],
                        ),
                    ).fetchone()
                    return UpsertResult("updated", updated)

                inserted = self.conn.execute(
                    """
                    INSERT INTO uns_meta.devices (
                        group_id,
                        country,
                        business_unit,
                        plant,
                        edge,
                        device,
                        uns_path
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING device_id,
                              group_id,
                              country,
                              business_unit,
                              plant,
                              edge,
                              device,
                              uns_path,
                              created_at,
                              updated_at
                    """,
                    (
                        payload.group_id,
                        payload.country,
                        payload.business_unit,
                        payload.plant,
                        payload.edge,
                        payload.device,
                        payload.uns_path,
                    ),
                ).fetchone()
                return UpsertResult("inserted", inserted)

        except Error as exc:  # noqa: BLE001 - wrap driver errors
            raise RepositoryError(f"device upsert failed: {exc}") from exc

    # ------------------------------------------------------------------
    def upsert_metric(self, payload: MetricPayload) -> UpsertResult:
        try:
            with self.conn.transaction():
                existing = self.conn.execute(
                    """
                    SELECT metric_id,
                           device_id,
                           name,
                           uns_path,
                           datatype,
                           canary_id,
                           created_at,
                           updated_at
                      FROM uns_meta.metrics
                     WHERE uns_path = %s
                    """,
                    (payload.uns_path,),
                ).fetchone()

                if existing:
                    if self._metric_rows_equal(existing, payload):
                        return UpsertResult("noop", existing)

                    updated = self.conn.execute(
                        """
                        UPDATE uns_meta.metrics
                           SET device_id = %s,
                               name = %s,
                               datatype = %s
                         WHERE metric_id = %s
                     RETURNING metric_id,
                               device_id,
                               name,
                               uns_path,
                               datatype,
                               canary_id,
                               created_at,
                               updated_at
                        """,
                        (
                            payload.device_id,
                            payload.name,
                            payload.datatype,
                            existing["metric_id"],
                        ),
                    ).fetchone()
                    return UpsertResult("updated", updated)

                identity = self.conn.execute(
                    """
                    SELECT metric_id,
                           uns_path
                      FROM uns_meta.metrics
                     WHERE device_id = %s
                       AND name = %s
                    """,
                    (payload.device_id, payload.name),
                ).fetchone()

                if identity:
                    updated = self.conn.execute(
                        """
                        UPDATE uns_meta.metrics
                           SET uns_path = %s,
                               datatype = %s
                         WHERE metric_id = %s
                     RETURNING metric_id,
                               device_id,
                               name,
                               uns_path,
                               datatype,
                               canary_id,
                               created_at,
                               updated_at
                        """,
                        (
                            payload.uns_path,
                            payload.datatype,
                            identity["metric_id"],
                        ),
                    ).fetchone()
                    return UpsertResult("updated", updated)

                inserted = self.conn.execute(
                    """
                    INSERT INTO uns_meta.metrics (
                        device_id,
                        name,
                        uns_path,
                        datatype
                    ) VALUES (%s, %s, %s, %s)
                    RETURNING metric_id,
                              device_id,
                              name,
                              uns_path,
                              datatype,
                              canary_id,
                              created_at,
                              updated_at
                    """,
                    (
                        payload.device_id,
                        payload.name,
                        payload.uns_path,
                        payload.datatype,
                    ),
                ).fetchone()
                return UpsertResult("inserted", inserted)

        except Error as exc:  # noqa: BLE001
            raise RepositoryError(f"metric upsert failed: {exc}") from exc

    # ------------------------------------------------------------------
    def upsert_metrics_bulk(
        self,
        payloads: Sequence[MetricPayload],
        *,
        batch_size: int = 1000,
    ) -> Dict[str, int]:
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        items = list(payloads)
        if not items:
            return {}

        try:
            id_map: Dict[str, int] = {}
            for i in range(0, len(items), batch_size):
                batch_items = items[i : i + batch_size]
                rows = [
                    (p.device_id, p.name, p.uns_path, p.datatype) for p in batch_items
                ]
                if not rows:
                    continue

                values_clause = ", ".join(["(%s, %s, %s, %s)"] * len(rows))
                params: List[Any] = [value for row in rows for value in row]
                statement = (
                    "INSERT INTO uns_meta.metrics (device_id, name, uns_path, datatype) "
                    f"VALUES {values_clause} "
                    "ON CONFLICT (device_id, name) DO UPDATE SET "
                    "uns_path = EXCLUDED.uns_path, "
                    "datatype = EXCLUDED.datatype"
                )

                with self.conn.cursor() as cur:
                    cur.execute(statement, params)

                    placeholder = ", ".join(["%s"] * len(batch_items))
                    names = [p.name for p in batch_items]
                    device_id = batch_items[0].device_id
                    cur.execute(
                        "SELECT name, metric_id FROM uns_meta.metrics "
                        f"WHERE device_id = %s AND name IN ({placeholder})",
                        [device_id] + names,
                    )
                    for row in cur.fetchall():
                        id_map[row["name"]] = row["metric_id"]

            return id_map

        except Error as exc:  # noqa: BLE001
            raise RepositoryError(f"metric bulk upsert failed: {exc}") from exc

    def upsert_metric_property(self, payload: MetricPropertyPayload) -> UpsertResult:
        columns = self._property_column_values(payload)

        try:
            with self.conn.transaction():
                existing = self.conn.execute(
                    """
                    SELECT metric_id,
                           key,
                           type,
                           value_int,
                           value_long,
                           value_float,
                           value_double,
                           value_string,
                           value_bool,
                           updated_at
                      FROM uns_meta.metric_properties
                     WHERE metric_id = %s
                       AND key = %s
                    """,
                    (payload.metric_id, payload.key),
                ).fetchone()

                if existing:
                    if self._property_rows_equal(existing, payload, columns):
                        return UpsertResult("noop", existing)

                    updated = self.conn.execute(
                        """
                        UPDATE uns_meta.metric_properties
                           SET type = %s,
                               value_int = %s,
                               value_long = %s,
                               value_float = %s,
                               value_double = %s,
                               value_string = %s,
                               value_bool = %s
                         WHERE metric_id = %s
                           AND key = %s
                     RETURNING metric_id,
                               key,
                               type,
                               value_int,
                               value_long,
                               value_float,
                               value_double,
                               value_string,
                               value_bool,
                               updated_at
                        """,
                        (
                            payload.type,
                            columns["value_int"],
                            columns["value_long"],
                            columns["value_float"],
                            columns["value_double"],
                            columns["value_string"],
                            columns["value_bool"],
                            payload.metric_id,
                            payload.key,
                        ),
                    ).fetchone()
                    return UpsertResult("updated", updated)

                inserted = self.conn.execute(
                    """
                    INSERT INTO uns_meta.metric_properties (
                        metric_id,
                        key,
                        type,
                        value_int,
                        value_long,
                        value_float,
                        value_double,
                        value_string,
                        value_bool
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING metric_id,
                              key,
                              type,
                              value_int,
                              value_long,
                              value_float,
                              value_double,
                              value_string,
                              value_bool,
                              updated_at
                    """,
                    (
                        payload.metric_id,
                        payload.key,
                        payload.type,
                        columns["value_int"],
                        columns["value_long"],
                        columns["value_float"],
                        columns["value_double"],
                        columns["value_string"],
                        columns["value_bool"],
                    ),
                ).fetchone()
                return UpsertResult("inserted", inserted)

        except Error as exc:  # noqa: BLE001
            raise RepositoryError(f"metric property upsert failed: {exc}") from exc

    def upsert_metric_properties_bulk(
        self,
        payloads: Sequence[MetricPropertyPayload],
        *,
        batch_size: int = 10000,
        manage_transaction: bool = True,
    ) -> int:
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        items = list(payloads)
        if not items:
            return 0

        grouped: Dict[int, Dict[str, MetricPropertyPayload]] = {}
        for payload in items:
            grouped.setdefault(payload.metric_id, {})[payload.key] = payload

        context = self.conn.transaction if manage_transaction else nullcontext

        try:
            with context():
                rows: List[tuple[Any, ...]] = []
                for metric_payloads in grouped.values():
                    for payload in metric_payloads.values():
                        columns = self._property_column_values(payload)
                        rows.append(
                            (
                                payload.metric_id,
                                payload.key,
                                payload.type,
                                columns["value_int"],
                                columns["value_long"],
                                columns["value_float"],
                                columns["value_double"],
                                columns["value_string"],
                                columns["value_bool"],
                            )
                        )

                if not rows:
                    return 0

                total = 0
                for start in range(0, len(rows), batch_size):
                    batch = rows[start : start + batch_size]
                    values_clause = ", ".join(
                        ["(%s, %s, %s, %s, %s, %s, %s, %s, %s)"] * len(batch)
                    )
                    params: List[Any] = [value for row in batch for value in row]
                    statement = (
                        "INSERT INTO uns_meta.metric_properties AS mp ("
                        "metric_id, key, type, value_int, value_long, value_float, "
                        "value_double, value_string, value_bool"
                        ") VALUES "
                        f"{values_clause} "
                        "ON CONFLICT (metric_id, key) DO UPDATE SET "
                        "type = EXCLUDED.type, "
                        "value_int = EXCLUDED.value_int, "
                        "value_long = EXCLUDED.value_long, "
                        "value_float = EXCLUDED.value_float, "
                        "value_double = EXCLUDED.value_double, "
                        "value_string = EXCLUDED.value_string, "
                        "value_bool = EXCLUDED.value_bool "
                        "WHERE mp.type IS DISTINCT FROM EXCLUDED.type "
                        "OR mp.value_int IS DISTINCT FROM EXCLUDED.value_int "
                        "OR mp.value_long IS DISTINCT FROM EXCLUDED.value_long "
                        "OR mp.value_float IS DISTINCT FROM EXCLUDED.value_float "
                        "OR mp.value_double IS DISTINCT FROM EXCLUDED.value_double "
                        "OR mp.value_string IS DISTINCT FROM EXCLUDED.value_string "
                        "OR mp.value_bool IS DISTINCT FROM EXCLUDED.value_bool"
                    )
                    with self.conn.cursor(row_factory=None) as cur:
                        cur.execute(statement, params)
                        total += cur.rowcount
            return total
        except Error as exc:  # noqa: BLE001
            raise RepositoryError(f"metric property bulk upsert failed: {exc}") from exc

    # ------------------------------------------------------------------
    @staticmethod
    def _device_rows_equal(existing: Dict[str, Any], payload: DevicePayload) -> bool:
        return (
            existing["group_id"] == payload.group_id
            and existing["country"] == payload.country
            and existing["business_unit"] == payload.business_unit
            and existing["plant"] == payload.plant
            and existing["edge"] == payload.edge
            and existing["device"] == payload.device
            and existing["uns_path"] == payload.uns_path
        )

    @staticmethod
    def _metric_rows_equal(existing: Dict[str, Any], payload: MetricPayload) -> bool:
        return (
            existing["device_id"] == payload.device_id
            and existing["name"] == payload.name
            and existing["uns_path"] == payload.uns_path
            and existing["datatype"] == payload.datatype
        )

    @staticmethod
    def _property_rows_equal(
        existing: Dict[str, Any],
        payload: MetricPropertyPayload,
        columns: Dict[str, Any],
    ) -> bool:
        return (
            existing["type"] == payload.type
            and existing["value_int"] == columns["value_int"]
            and existing["value_long"] == columns["value_long"]
            and existing["value_float"] == columns["value_float"]
            and existing["value_double"] == columns["value_double"]
            and existing["value_string"] == columns["value_string"]
            and existing["value_bool"] == columns["value_bool"]
        )

    @staticmethod
    def _property_column_values(payload: MetricPropertyPayload) -> Dict[str, Any]:
        allowed = {"int", "long", "float", "double", "string", "boolean"}
        if payload.type not in allowed:
            raise RepositoryError(f"invalid property type: {payload.type}")

        columns: Dict[str, Any] = {
            "value_int": None,
            "value_long": None,
            "value_float": None,
            "value_double": None,
            "value_string": None,
            "value_bool": None,
        }

        value = payload.value
        if payload.type == "int":
            columns["value_int"] = int(value) if value is not None else None
        elif payload.type == "long":
            columns["value_long"] = int(value) if value is not None else None
        elif payload.type == "float":
            columns["value_float"] = float(value) if value is not None else None
        elif payload.type == "double":
            columns["value_double"] = float(value) if value is not None else None
        elif payload.type == "string":
            columns["value_string"] = None if value is None else str(value)
        elif payload.type == "boolean":
            columns["value_bool"] = bool(value) if value is not None else None
        return columns

    @staticmethod
    def _batched(
        items: Sequence[MetricPropertyPayload], size: int
    ) -> Iterable[Sequence[MetricPropertyPayload]]:
        for start in range(0, len(items), size):
            yield items[start : start + size]


__all__ = [
    "DevicePayload",
    "MetadataRepository",
    "MetricPayload",
    "MetricPropertyPayload",
    "RepositoryError",
    "UpsertResult",
]
