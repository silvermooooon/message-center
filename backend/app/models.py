from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def now():
    return datetime.now(UTC)


def uid():
    return uuid4().hex


class Session(Base):
    __tablename__ = "mc_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(100))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Source(Base):
    __tablename__ = "mc_sources"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(200))
    type: Mapped[str] = mapped_column(String(20))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    url: Mapped[str | None] = mapped_column(Text)
    token: Mapped[str | None] = mapped_column(Text)
    poll_interval_seconds: Mapped[int] = mapped_column(Integer, default=60)
    next_poll_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    last_error: Mapped[str | None] = mapped_column(Text)


class Message(Base):
    __tablename__ = "mc_messages"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id"),
        UniqueConstraint("client_request_key"),
        Index("mc_message_expiry", "status", "expires_at"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    source_id: Mapped[str | None] = mapped_column(ForeignKey("mc_sources.id"))
    external_id: Mapped[str | None] = mapped_column(String(200))
    client_request_key: Mapped[str | None] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(80), default="announcement")
    publisher: Mapped[str | None] = mapped_column(String(200))
    topic: Mapped[str | None] = mapped_column(String(200))
    channel: Mapped[str | None] = mapped_column(String(200))
    recipients: Mapped[list] = mapped_column(JSONB, default=list)
    meta: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    enrichment: Mapped[dict | None] = mapped_column(JSONB)


class Revision(Base):
    __tablename__ = "mc_revisions"
    __table_args__ = (UniqueConstraint("message_id", "version"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    message_id: Mapped[str] = mapped_column(ForeignKey("mc_messages.id"))
    version: Mapped[int] = mapped_column(Integer)
    content: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Subscription(Base):
    __tablename__ = "mc_subscriptions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(String(100), index=True)
    channel: Mapped[str | None] = mapped_column(String(200))
    topic: Mapped[str | None] = mapped_column(String(200))
    mode: Mapped[str] = mapped_column(String(20), default="immediate")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Delivery(Base):
    __tablename__ = "mc_deliveries"
    __table_args__ = (
        UniqueConstraint("message_id", "version", "owner_id"),
        Index("mc_delivery_due", "status", "next_attempt_at"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    message_id: Mapped[str] = mapped_column(ForeignKey("mc_messages.id"))
    version: Mapped[int] = mapped_column(Integer)
    owner_id: Mapped[str] = mapped_column(String(100))
    mode: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    notified: Mapped[bool] = mapped_column(Boolean, default=False)
    human_read: Mapped[bool] = mapped_column(Boolean, default=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    request_id: Mapped[str | None] = mapped_column(String(200))
    last_error: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Response(Base):
    __tablename__ = "mc_responses"
    __table_args__ = (UniqueConstraint("message_id", "owner_id"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    message_id: Mapped[str] = mapped_column(ForeignKey("mc_messages.id"))
    owner_id: Mapped[str] = mapped_column(String(100))
    response: Mapped[str] = mapped_column(String(30))
    note: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
