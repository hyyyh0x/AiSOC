"""Connector ORM model."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class Connector(Base):
    __tablename__ = "connectors"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    connector_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    auth_config: Mapped[dict] = mapped_column(JSONB, default=dict)  # Encrypted at application layer
    connector_config: Mapped[dict] = mapped_column(JSONB, default=dict)
    health_status: Mapped[str] = mapped_column(String(20), default="unknown")
    last_health_check: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    events_ingested: Mapped[int] = mapped_column(default=0)
    events_dropped: Mapped[int] = mapped_column(default=0)
    error_count: Mapped[int] = mapped_column(default=0)
    # Schema-drift sentinel state (migration 026). NULL until the first
    # non-empty poll has populated a fingerprint baseline.
    schema_fingerprint: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_schema_drift_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_drift_details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    tags: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="connectors")
