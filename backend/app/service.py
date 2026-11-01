import hashlib
import os

import redis
from fastapi import HTTPException
from sqlalchemy import inspect, or_, select

from .models import Delivery, Message, Response, Revision, Source, Subscription, now

PEOPLE = [
    {"owner_id": "owner-alex", "name": "Alex"},
    {"owner_id": "owner-maya", "name": "Maya"},
    {"owner_id": "owner-jordan", "name": "Jordan"},
]
OWNERS = {p["owner_id"] for p in PEOPLE}


def row(obj, exclude=()):
    return {
        prop.columns[0].name: getattr(obj, prop.key)
        for prop in inspect(type(obj)).column_attrs
        if prop.columns[0].name not in exclude
    }


def authorize(owner_id, action):
    return True


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def get_or_404(db, cls, item_id):
    obj = db.get(cls, item_id)
    if obj is None:
        raise HTTPException(404, "Not found")
    return obj


def message_data(db, message):
    data = row(message)
    source = db.get(Source, message.source_id) if message.source_id else None
    data["source"] = source.name if source else None
    return data


def detail(db, message):
    data = message_data(db, message)
    data["revisions"] = [
        row(x)
        for x in db.scalars(
            select(Revision).where(Revision.message_id == message.id).order_by(Revision.version)
        )
    ]
    data["deliveries"] = [
        row(x)
        for x in db.scalars(
            select(Delivery).where(Delivery.message_id == message.id).order_by(Delivery.created_at)
        )
    ]
    data["responses"] = [
        row(x) for x in db.scalars(select(Response).where(Response.message_id == message.id))
    ]
    data["response_counts"] = {
        key: sum(r["response"] == key for r in data["responses"])
        for key in ("acknowledge", "attending", "declined")
    }
    return data


def fanout(db, message):
    recipients = {owner: "immediate" for owner in message.recipients}
    if not recipients:
        subscriptions = db.scalars(
            select(Subscription).where(
                Subscription.enabled.is_(True),
                or_(Subscription.channel.is_(None), Subscription.channel == message.channel),
                or_(Subscription.topic.is_(None), Subscription.topic == message.topic),
            )
        )
        for sub in subscriptions:
            if sub.owner_id not in recipients or sub.mode == "immediate":
                recipients[sub.owner_id] = sub.mode
    for owner, mode in recipients.items():
        db.add(Delivery(message_id=message.id, version=message.version, owner_id=owner, mode=mode))


def save_revision(db, message):
    content = {
        key: getattr(message, key)
        for key in ("title", "body", "kind", "publisher", "topic", "channel", "recipients", "meta")
    }
    content["metadata"] = content.pop("meta")
    content["expires_at"] = message.expires_at.isoformat() if message.expires_at else None
    db.add(Revision(message_id=message.id, version=message.version, content=content))


def create_message(db, values):
    if values.get("source_id"):
        source = get_or_404(db, Source, values["source_id"])
        if not source.enabled:
            raise HTTPException(409, "Source is disabled")
    if values.get("client_request_key"):
        existing = db.scalar(
            select(Message).where(Message.client_request_key == values["client_request_key"])
        )
        if existing:
            return existing
    if values.get("source_id") and values.get("external_id"):
        existing = db.scalar(
            select(Message).where(
                Message.source_id == values["source_id"],
                Message.external_id == values["external_id"],
            )
        )
        if existing:
            return existing
    values = dict(values)
    values["meta"] = values.pop("metadata", {})
    message = Message(**values)
    db.add(message)
    db.flush()
    save_revision(db, message)
    fanout(db, message)
    db.commit()
    hint()
    return message


def update_message(db, message, values):
    values = dict(values)
    if "metadata" in values:
        values["meta"] = values.pop("metadata")
    if message.status != "active":
        raise HTTPException(409, "Message is withdrawn")
    changed = any(getattr(message, k) != v for k, v in values.items())
    if not changed:
        return message
    for key, value in values.items():
        setattr(message, key, value)
    for delivery in db.scalars(
        select(Delivery).where(
            Delivery.message_id == message.id,
            Delivery.status.in_(["pending", "accepted", "failed"]),
        )
    ):
        delivery.status = "cancelled"
        delivery.updated_at = now()
    message.enrichment = None
    message.version += 1
    message.updated_at = now()
    save_revision(db, message)
    fanout(db, message)
    db.commit()
    hint()
    return message


def respond(db, message, owner, response, note):
    if message.status != "active" or (message.expires_at and message.expires_at <= now()):
        raise HTTPException(409, "Message is no longer actionable")
    item = db.scalar(
        select(Response).where(Response.message_id == message.id, Response.owner_id == owner)
    )
    if not item:
        item = Response(message_id=message.id, owner_id=owner, response=response)
        db.add(item)
    item.response, item.note, item.updated_at = response, note, now()
    db.commit()
    return item


def hint():
    url = os.getenv("REDIS_URL")
    if url:
        try:
            redis.Redis.from_url(url, socket_connect_timeout=0.2, socket_timeout=0.2).publish(
                "message-center:delivery", "wake"
            )
        except (redis.RedisError, ValueError):
            pass
