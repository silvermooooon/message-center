import json
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .service import OWNERS


class Login(BaseModel):
    username: str


class MessageInput(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    body: str = Field(min_length=1, max_length=100000)
    kind: str = Field(default="announcement", min_length=1, max_length=80)
    source_id: str | None = Field(default=None, max_length=32)
    external_id: str | None = Field(default=None, min_length=1, max_length=200)
    client_request_key: str | None = Field(default=None, min_length=1, max_length=200)
    publisher: str | None = Field(default=None, max_length=200)
    topic: str | None = Field(default=None, max_length=200)
    channel: str | None = Field(default=None, max_length=200)
    recipients: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    expires_at: datetime | None = None

    @field_validator("metadata")
    @classmethod
    def bounded_metadata(cls, value):
        if value is not None and len(json.dumps(value, ensure_ascii=False).encode()) > 8192:
            raise ValueError("metadata exceeds 8192 bytes")
        return value

    @field_validator("recipients")
    @classmethod
    def validate_recipients(cls, value):
        if not set(value) <= OWNERS:
            raise ValueError("Unknown recipient")
        return list(dict.fromkeys(value))

    @field_validator("expires_at")
    @classmethod
    def aware_expiry(cls, value):
        if value is not None and value.utcoffset() is None:
            raise ValueError("expires_at must include a timezone")
        return value


class MessagePatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    body: str | None = Field(default=None, min_length=1, max_length=100000)
    kind: str | None = Field(default=None, min_length=1, max_length=80)
    publisher: str | None = Field(default=None, max_length=200)
    topic: str | None = Field(default=None, max_length=200)
    channel: str | None = Field(default=None, max_length=200)
    recipients: list[str] | None = None
    metadata: dict | None = None
    expires_at: datetime | None = None

    @field_validator("metadata")
    @classmethod
    def bounded_metadata(cls, value):
        if value is not None and len(json.dumps(value, ensure_ascii=False).encode()) > 8192:
            raise ValueError("metadata exceeds 8192 bytes")
        return value

    @field_validator("recipients")
    @classmethod
    def validate_recipients(cls, value):
        if value is not None and not set(value) <= OWNERS:
            raise ValueError("Unknown recipient")
        return list(dict.fromkeys(value)) if value is not None else value

    @field_validator("expires_at")
    @classmethod
    def aware_expiry(cls, value):
        if value is not None and value.utcoffset() is None:
            raise ValueError("expires_at must include a timezone")
        return value


class SourceInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    type: Literal["webhook", "poll", "manual"]
    enabled: bool = True
    url: str | None = Field(default=None, max_length=2000)
    token: str | None = Field(default=None, max_length=2000)
    poll_interval_seconds: int = Field(default=60, ge=10)


class SourcePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    type: Literal["webhook", "poll", "manual"] | None = None
    enabled: bool | None = None
    url: str | None = Field(default=None, max_length=2000)
    token: str | None = Field(default=None, max_length=2000)
    poll_interval_seconds: int | None = Field(default=None, ge=10)


class SubscriptionInput(BaseModel):
    owner_id: Literal["owner-alex", "owner-maya", "owner-jordan"]
    channel: str | None = Field(default=None, max_length=200)
    topic: str | None = Field(default=None, max_length=200)
    mode: Literal["immediate", "digest"] = "immediate"
    enabled: bool = True


class SubscriptionPatch(BaseModel):
    owner_id: Literal["owner-alex", "owner-maya", "owner-jordan"] | None = None
    channel: str | None = Field(default=None, max_length=200)
    topic: str | None = Field(default=None, max_length=200)
    mode: Literal["immediate", "digest"] | None = None
    enabled: bool | None = None


class ResponseInput(BaseModel):
    owner_id: Literal["owner-alex", "owner-maya", "owner-jordan"] | None = None
    response: Literal["acknowledge", "attending", "declined"]
    note: str | None = Field(default=None, max_length=4000)


class ServiceMessage(MessageInput):
    owner_id: Literal["owner-alex", "owner-maya", "owner-jordan"]
    client_request_key: str = Field(min_length=1, max_length=200)


class ResultInput(BaseModel):
    owner_id: Literal["owner-alex", "owner-maya", "owner-jordan"]
    status: Literal["processed", "failed"]
    notified: bool
    summary: str | None = Field(default=None, max_length=4000)


class ReadInput(BaseModel):
    owner_id: Literal["owner-alex", "owner-maya", "owner-jordan"]
    read: bool


class MarkInput(BaseModel):
    owner_id: Literal["owner-alex", "owner-maya", "owner-jordan"]
    consumed: bool
