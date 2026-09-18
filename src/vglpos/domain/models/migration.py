"""Legacy import provenance models."""

from __future__ import annotations

from sqlalchemy import Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from vglpos.domain.models.base import BIGINT, TenantEntity


class LegacyIdMap(TenantEntity):
    """Retain deterministic links from prototype identifiers to target rows."""

    __tablename__ = "legacy_id_map"
    __table_args__ = (
        Index(
            "uq_legacy_id_map_source",
            "company_id",
            "legacy_table",
            "legacy_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
        Index("idx_legacy_id_map_target", "target_table", "target_id"),
    )

    legacy_table: Mapped[str] = mapped_column(String(64), nullable=False)
    legacy_id: Mapped[str] = mapped_column(String(100), nullable=False)
    target_table: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[int] = mapped_column(BIGINT, nullable=False)
