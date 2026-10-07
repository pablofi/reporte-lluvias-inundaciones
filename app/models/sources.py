from datetime import datetime, timezone
from enum import StrEnum

from sqlalchemy import Boolean, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime, TypeDecorator

from app.db import Base


def utcnow():
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware")
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        return value.replace(tzinfo=timezone.utc) if value is not None else None


class SourceStatus(StrEnum):
    ACTUALIZADA = "ACTUALIZADA"
    VIGENTE = "VIGENTE"
    NO_DISPONIBLE_OBSOLETA = "NO_DISPONIBLE_OBSOLETA"


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    organization: Mapped[str] = mapped_column(String(80))
    source_type: Mapped[str] = mapped_column(String(40))
    url: Mapped[str] = mapped_column(Text)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class SourceSnapshot(Base):
    __tablename__ = "source_snapshots"
    __table_args__ = (UniqueConstraint("source_id", "content_hash"), Index("snapshot_source_time", "source_id", "fetched_at"))
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    fetched_at: Mapped[datetime] = mapped_column(UTCDateTime)
    detected_issue_time: Mapped[datetime | None] = mapped_column(UTCDateTime)
    validity_start: Mapped[datetime | None] = mapped_column(UTCDateTime)
    validity_end: Mapped[datetime | None] = mapped_column(UTCDateTime)
    content_hash: Mapped[str] = mapped_column(String(64))
    content_type: Mapped[str] = mapped_column(String(120))
    original_filename: Mapped[str | None] = mapped_column(String(255))
    storage_path: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class SourceCheck(Base):
    __tablename__ = "source_checks"
    __table_args__ = (Index("check_source_time", "source_id", "checked_at"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    checked_at: Mapped[datetime] = mapped_column(UTCDateTime)
    http_status: Mapped[int | None] = mapped_column(Integer)
    success: Mapped[bool] = mapped_column(Boolean)
    error_message: Mapped[str | None] = mapped_column(Text)
    etag: Mapped[str | None] = mapped_column(Text)
    last_modified: Mapped[str | None] = mapped_column(Text)
    detected_issue_time: Mapped[datetime | None] = mapped_column(UTCDateTime)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    changed: Mapped[bool] = mapped_column(Boolean, default=False)
    snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("source_snapshots.id"))
