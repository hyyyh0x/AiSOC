"""Read/write access to the canonical ``connectors`` table.

The schema for that table lives in ``services/api/app/models/connector.py``;
the API service owns the migrations. We deliberately do **not** import that
ORM model here — it would drag the API's full app.* package into our import
graph. Instead we pin the column shape via SQLAlchemy Core ``Table``/
``MetaData`` against the same ``connectors`` table and limit ourselves to the
columns the scheduler needs.

If the API service ever changes the column shape in a backwards-incompatible
way, the scheduler will fail loudly at first poll (column not found), which is
what we want — silent drift between two services that share a table is the
worst possible failure mode.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

metadata = MetaData()

# Mirror of services/api/app/models/connector.py:Connector. Only includes the
# columns the scheduler reads or writes; we don't claim ownership of the full
# table shape.
connectors_table = Table(
    "connectors",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column("name", String(255), nullable=False),
    Column("connector_type", String(100), nullable=False),
    Column("category", String(50), nullable=False),
    Column("is_enabled", Boolean, nullable=False),
    Column("auth_config", JSONB, nullable=False),
    Column("connector_config", JSONB, nullable=False),
    Column("health_status", String(20), nullable=False),
    Column("last_health_check", DateTime(timezone=True)),
    Column("last_sync", DateTime(timezone=True)),
    Column("events_ingested", Integer, nullable=False),
    Column("events_dropped", Integer, nullable=False),
    Column("error_count", Integer, nullable=False),
    # Schema-drift sentinel columns (migration 026). Nullable: a brand-new
    # connector hasn't established a fingerprint baseline yet.
    Column("schema_fingerprint", Text),
    Column("last_schema_drift_at", DateTime(timezone=True)),
    Column("last_drift_details", JSONB),
    Column("tags", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)


@dataclass
class ConnectorInstance:
    """Light dataclass over a row in ``connectors``.

    We use a plain dataclass instead of an ORM mapping so the scheduler stays
    decoupled from the API service's ``Base`` declarative class and avoids
    lazy-loading attributes from a closed session by mistake.
    """

    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    connector_type: str
    is_enabled: bool
    auth_config: dict[str, Any]
    connector_config: dict[str, Any]
    health_status: str
    last_sync: datetime | None
    events_ingested: int
    events_dropped: int
    error_count: int
    # Drift-sentinel state. ``schema_fingerprint`` is the SHA-256 of the
    # sorted, deduped top-level field names from the previous successful
    # poll. NULL on first poll.
    schema_fingerprint: str | None
    last_schema_drift_at: datetime | None
    last_drift_details: dict[str, Any] | None


async def fetch_enabled_connectors(connection: Any) -> list[ConnectorInstance]:
    """Return every connector instance with ``is_enabled = True``.

    ``connection`` must be a SQLAlchemy ``AsyncConnection``. We accept ``Any``
    in the type hint to avoid forcing every caller to import the async
    connection type.
    """
    stmt = select(
        connectors_table.c.id,
        connectors_table.c.tenant_id,
        connectors_table.c.name,
        connectors_table.c.connector_type,
        connectors_table.c.is_enabled,
        connectors_table.c.auth_config,
        connectors_table.c.connector_config,
        connectors_table.c.health_status,
        connectors_table.c.last_sync,
        connectors_table.c.events_ingested,
        connectors_table.c.events_dropped,
        connectors_table.c.error_count,
        connectors_table.c.schema_fingerprint,
        connectors_table.c.last_schema_drift_at,
        connectors_table.c.last_drift_details,
    ).where(connectors_table.c.is_enabled.is_(True))

    result = await connection.execute(stmt)
    rows = result.fetchall()
    return [
        ConnectorInstance(
            id=row.id,
            tenant_id=row.tenant_id,
            name=row.name,
            connector_type=row.connector_type,
            is_enabled=row.is_enabled,
            auth_config=row.auth_config or {},
            connector_config=row.connector_config or {},
            health_status=row.health_status,
            last_sync=row.last_sync,
            events_ingested=row.events_ingested,
            events_dropped=row.events_dropped,
            error_count=row.error_count,
            schema_fingerprint=row.schema_fingerprint,
            last_schema_drift_at=row.last_schema_drift_at,
            last_drift_details=row.last_drift_details,
        )
        for row in rows
    ]


async def record_poll_success(
    connection: Any,
    connector_id: uuid.UUID,
    *,
    events_added: int,
    events_dropped: int = 0,
    schema_fingerprint: str | None = None,
) -> None:
    """Update last_sync, increment counters, mark healthy.

    If ``schema_fingerprint`` is provided it is written to the row; the
    drift bookkeeping (``last_schema_drift_at`` / ``last_drift_details``)
    is updated by ``record_schema_drift`` so the two callers don't race
    on the same UPDATE.
    """
    now = datetime.now(UTC)
    values: dict[str, Any] = {
        "last_sync": now,
        "last_health_check": now,
        "health_status": "healthy",
        "events_ingested": connectors_table.c.events_ingested + events_added,
        "events_dropped": connectors_table.c.events_dropped + events_dropped,
        "updated_at": now,
    }
    if schema_fingerprint is not None:
        values["schema_fingerprint"] = schema_fingerprint
    stmt = (
        update(connectors_table)
        .where(connectors_table.c.id == connector_id)
        .values(**values)
    )
    await connection.execute(stmt)


async def record_poll_failure(
    connection: Any,
    connector_id: uuid.UUID,
) -> None:
    """Mark a poll attempt as failed without touching last_sync."""
    now = datetime.now(UTC)
    stmt = (
        update(connectors_table)
        .where(connectors_table.c.id == connector_id)
        .values(
            last_health_check=now,
            health_status="unhealthy",
            error_count=connectors_table.c.error_count + 1,
            updated_at=now,
        )
    )
    await connection.execute(stmt)


async def record_schema_drift(
    connection: Any,
    connector_id: uuid.UUID,
    *,
    fingerprint: str,
    details: dict[str, Any],
) -> None:
    """Record a confirmed schema drift event.

    Called by the scheduler when the new poll's fingerprint differs from
    the stored baseline. Writes the new fingerprint, drift timestamp and
    details so the dashboard can surface "what changed" to operators.
    """
    now = datetime.now(UTC)
    stmt = (
        update(connectors_table)
        .where(connectors_table.c.id == connector_id)
        .values(
            schema_fingerprint=fingerprint,
            last_schema_drift_at=now,
            last_drift_details=details,
            updated_at=now,
        )
    )
    await connection.execute(stmt)


__all__ = [
    "ConnectorInstance",
    "connectors_table",
    "fetch_enabled_connectors",
    "metadata",
    "record_poll_failure",
    "record_poll_success",
    "record_schema_drift",
]
