import logging
import os
import time
from datetime import timedelta

import httpx
import redis
from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError
from sqlalchemy import func, select, update

from .db import SessionLocal
from .models import Delivery, Message, Source, now
from .schemas import MessageInput
from .service import create_message, message_data

log = logging.getLogger("message_center.worker")
MAX_ATTEMPTS = 5


def poll_sources():
    with SessionLocal() as db:
        sources = list(
            db.scalars(
                select(Source)
                .where(
                    Source.type == "poll", Source.enabled.is_(True), Source.next_poll_at <= now()
                )
                .order_by(Source.next_poll_at)
                .limit(20)
            )
        )
        for source in sources:
            source.next_poll_at = now() + timedelta(seconds=source.poll_interval_seconds)
            db.commit()
            try:
                headers = {"Authorization": f"Bearer {source.token}"} if source.token else {}
                response = httpx.get(
                    source.url, headers=headers, timeout=10, follow_redirects=False
                )
                response.raise_for_status()
                records = response.json()
                records = records if isinstance(records, list) else [records]
                for record in records:
                    values = MessageInput.model_validate(record).model_dump()
                    if not values["external_id"]:
                        raise ValueError("external_id required")
                    values["source_id"] = source.id
                    create_message(db, values)
                source.last_error = None
            except (httpx.HTTPError, ValidationError, ValueError, TypeError):
                db.rollback()
                source = db.get(Source, source.id)
                source.last_error = "Poll failed; check the endpoint and ingress schema"
            db.commit()


def deliver_due():
    with SessionLocal() as db:
        ids = list(
            db.scalars(
                select(Delivery.id)
                .where(Delivery.status == "pending", Delivery.next_attempt_at <= now())
                .order_by(Delivery.next_attempt_at)
                .limit(50)
            )
        )
    for delivery_id in ids:
        with SessionLocal() as db:
            delivery = db.get(Delivery, delivery_id)
            message = db.get(Message, delivery.message_id)
            if (
                message.status != "active"
                or message.version != delivery.version
                or (message.expires_at and message.expires_at <= now())
            ):
                delivery.status, delivery.updated_at = "cancelled", now()
                db.commit()
                continue
            payload = {
                "delivery_id": delivery.id,
                "message_id": message.id,
                "version": delivery.version,
                "owner_id": delivery.owner_id,
                "mode": delivery.mode,
                "message": message_data(db, message),
            }
            db.commit()
        error = None
        request_id = None
        try:
            base = os.getenv("DUET_BASE_URL", "").rstrip("/")
            token = os.getenv("MESSAGE_CENTER_SERVICE_TOKEN", "")
            if not base or not token:
                raise ValueError("Duet transport is not configured")
            response = httpx.post(
                f"{base}/api/message-center/deliveries",
                headers={"X-Message-Center-Token": token},
                json=jsonable_encoder(payload),
                timeout=10,
            )
            response.raise_for_status()
            result = response.json()
            if (
                not isinstance(result, dict)
                or result.get("status") != "accepted"
                or (payload["mode"] == "immediate" and not result.get("request_id"))
            ):
                raise ValueError("Duet did not accept delivery")
            request_id = str(result["request_id"]) if result.get("request_id") else None
        except (httpx.HTTPError, ValueError, TypeError):
            error = "Duet delivery failed; check transport and Duet availability"
        with SessionLocal() as db:
            delivery = db.get(Delivery, delivery_id)
            message = db.get(Message, delivery.message_id)
            if (
                message.status != "active"
                or message.version != delivery.version
                or (message.expires_at and message.expires_at <= now())
            ):
                values = {"status": "cancelled"}
            elif not error:
                values = {"status": "accepted", "request_id": request_id, "last_error": None}
            else:
                attempts = delivery.attempts + 1
                values = {
                    "attempts": attempts,
                    "last_error": error,
                    "status": "failed" if attempts >= MAX_ATTEMPTS else "pending",
                    "next_attempt_at": now() + timedelta(seconds=min(300, 2**attempts * 5)),
                }
            db.execute(
                update(Delivery)
                .where(Delivery.id == delivery_id, Delivery.status == "pending")
                .values(**values, updated_at=now())
            )
            db.commit()


def expire_messages():
    with SessionLocal.begin() as db:
        messages = list(
            db.scalars(
                select(Message)
                .where(Message.status == "active", Message.expires_at <= now())
                .order_by(Message.expires_at)
                .limit(50)
            )
        )
        for message in messages:
            message.status, message.updated_at = "expired", now()
            db.execute(
                update(Delivery)
                .where(
                    Delivery.message_id == message.id,
                    Delivery.status.in_(["pending", "accepted", "failed"]),
                )
                .values(status="cancelled", updated_at=now())
            )


def next_wait():
    interval = max(30, min(60, int(os.getenv("MESSAGE_CENTER_RECONCILE_SECONDS", "45"))))
    with SessionLocal() as db:
        deadlines = [
            db.scalar(
                select(func.min(Delivery.next_attempt_at)).where(Delivery.status == "pending")
            ),
            db.scalar(
                select(func.min(Source.next_poll_at)).where(
                    Source.enabled.is_(True), Source.type == "poll"
                )
            ),
            db.scalar(
                select(func.min(Message.expires_at)).where(
                    Message.status == "active", Message.expires_at.is_not(None)
                )
            ),
        ]
    return max(
        0,
        min(
            [interval] + [(deadline - now()).total_seconds() for deadline in deadlines if deadline]
        ),
    )


def run():
    logging.basicConfig(level=logging.INFO)
    pubsub = None
    if os.getenv("REDIS_URL"):
        try:
            pubsub = redis.Redis.from_url(
                os.environ["REDIS_URL"], socket_connect_timeout=1, socket_timeout=65
            ).pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe("message-center:delivery")
        except (redis.RedisError, ValueError):
            log.warning("Redis unavailable; using database reconciliation")
            pubsub = None
    while True:
        try:
            expire_messages()
            poll_sources()
            deliver_due()
        except Exception:
            log.exception("Worker cycle failed")
        try:
            delay = next_wait()
        except Exception:
            log.exception("Unable to calculate next deadline")
            delay = 45
        if pubsub:
            try:
                pubsub.get_message(timeout=delay)
                continue
            except redis.RedisError:
                log.warning("Redis unavailable; using database reconciliation")
                pubsub = None
        time.sleep(delay)


if __name__ == "__main__":
    run()
