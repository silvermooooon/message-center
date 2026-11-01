import hmac
import os
import secrets
from datetime import timedelta
from pathlib import Path

from fastapi import (
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    Request,
)
from fastapi import (
    Response as HttpResponse,
)
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from . import enrichment
from .db import SessionLocal
from .models import Delivery, Message, Source, Subscription, now
from .models import Session as LoginSession
from .schemas import (
    Login,
    MarkInput,
    MessageInput,
    MessagePatch,
    ReadInput,
    ResponseInput,
    ResultInput,
    ServiceMessage,
    SourceInput,
    SourcePatch,
    SubscriptionInput,
    SubscriptionPatch,
)
from .service import (
    PEOPLE,
    authorize,
    create_message,
    detail,
    get_or_404,
    hint,
    message_data,
    respond,
    row,
    token_hash,
    update_message,
)

app = FastAPI(title="Message Center")


def db_session():
    with SessionLocal() as db:
        yield db


def identity(request: Request, db: Session = Depends(db_session)):
    token = request.cookies.get("mc_session")
    session = db.get(LoginSession, token_hash(token)) if token else None
    if not session or session.expires_at <= now():
        raise HTTPException(401, "Login required")
    if not authorize(session.owner_id, request.method):
        raise HTTPException(403, "Forbidden")
    return session.owner_id


def service_auth(x_message_center_token: str = Header(default="")):
    token = os.getenv("MESSAGE_CENTER_SERVICE_TOKEN", "")
    if not token or not hmac.compare_digest(token, x_message_center_token):
        raise HTTPException(401, "Invalid service token")


@app.get("/health")
def health():
    return {"ok": True, "acceptance_fixture": os.getenv("MESSAGE_CENTER_TEST_FIXTURE") == "true"}


@app.post("/api/auth/login")
def login(input: Login, response: HttpResponse, db: Session = Depends(db_session)):
    owner = {"DEV-AAA": "owner-alex", "DEV-BBB": "owner-maya", "DEV-CCC": "owner-jordan"}.get(
        input.username.strip().upper()
    )
    if not owner:
        raise HTTPException(401, "Use DEV-AAA, DEV-BBB, or DEV-CCC")
    token = secrets.token_urlsafe(32)
    db.add(
        LoginSession(
            token_hash=token_hash(token), owner_id=owner, expires_at=now() + timedelta(hours=12)
        )
    )
    db.commit()
    response.set_cookie(
        "mc_session",
        token,
        httponly=True,
        samesite="lax",
        secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
        max_age=43200,
    )
    return next(person for person in PEOPLE if person["owner_id"] == owner)


@app.get("/api/auth/me")
def me(owner: str = Depends(identity)):
    return next(person for person in PEOPLE if person["owner_id"] == owner)


@app.post("/api/auth/logout")
def logout(request: Request, response: HttpResponse, db: Session = Depends(db_session)):
    token = request.cookies.get("mc_session")
    session = db.get(LoginSession, token_hash(token)) if token else None
    if session:
        db.delete(session)
        db.commit()
    response.delete_cookie("mc_session")
    return {"ok": True}


@app.get("/api/config")
def config(owner: str = Depends(identity)):
    return {
        "service_configured": bool(os.getenv("MESSAGE_CENTER_SERVICE_TOKEN")),
        "duet_configured": bool(os.getenv("DUET_BASE_URL")),
        "enrichment_enabled": enrichment.enabled(),
    }


@app.get("/api/people")
def people(owner: str = Depends(identity)):
    return PEOPLE


@app.get("/api/messages")
def messages(
    q: str | None = None,
    channel: str | None = None,
    topic: str | None = None,
    status: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    owner: str = Depends(identity),
    db: Session = Depends(db_session),
):
    query = (
        select(Message, Source.name)
        .outerjoin(Source, Message.source_id == Source.id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(limit)
        .offset(offset)
    )
    if q:
        query = query.where(or_(Message.title.ilike(f"%{q}%"), Message.body.ilike(f"%{q}%")))
    for field, value in (
        (Message.channel, channel),
        (Message.topic, topic),
        (Message.status, status),
    ):
        if value is not None:
            query = query.where(field == value)
    return [{**row(item), "source": source} for item, source in db.execute(query)]


@app.post("/api/messages")
def publish(input: MessageInput, owner: str = Depends(identity), db: Session = Depends(db_session)):
    values = input.model_dump()
    values["publisher"] = values["publisher"] or owner
    return message_data(db, create_message(db, values))


@app.get("/api/messages/{message_id}")
def get_message(message_id: str, owner: str = Depends(identity), db: Session = Depends(db_session)):
    return detail(db, get_or_404(db, Message, message_id))


@app.patch("/api/messages/{message_id}")
def patch_message(
    message_id: str,
    input: MessagePatch,
    owner: str = Depends(identity),
    db: Session = Depends(db_session),
):
    values = input.model_dump(exclude_unset=True)
    if any(
        values.get(k, "valid") is None for k in ("title", "body", "kind", "recipients", "metadata")
    ):
        raise HTTPException(422, "title, body, kind and recipients cannot be null")
    return message_data(db, update_message(db, get_or_404(db, Message, message_id), values))


@app.post("/api/messages/{message_id}/withdraw")
def withdraw(message_id: str, owner: str = Depends(identity), db: Session = Depends(db_session)):
    message = get_or_404(db, Message, message_id)
    message.status = "withdrawn"
    message.updated_at = now()
    for delivery in db.scalars(
        select(Delivery).where(
            Delivery.message_id == message_id,
            Delivery.status.in_(["pending", "accepted", "failed"]),
        )
    ):
        delivery.status, delivery.updated_at = "cancelled", now()
    db.commit()
    return message_data(db, message)


@app.post("/api/messages/{message_id}/responses")
def response(
    message_id: str,
    input: ResponseInput,
    owner: str = Depends(identity),
    db: Session = Depends(db_session),
):
    return row(
        respond(
            db,
            get_or_404(db, Message, message_id),
            input.owner_id or owner,
            input.response,
            input.note,
        )
    )


@app.post("/api/messages/{message_id}/enrich")
async def enrich(
    message_id: str, owner: str = Depends(identity), db: Session = Depends(db_session)
):
    message = get_or_404(db, Message, message_id)
    if not enrichment.enabled():
        raise HTTPException(503, "Enrichment is not configured")
    version = message.version
    try:
        result = await enrichment.enrich(message.title, message.body)
    except Exception:  # noqa: BLE001
        raise HTTPException(502, "Enrichment failed; the original message is unchanged") from None
    db.refresh(message)
    if message.version != version or message.status != "active":
        raise HTTPException(409, "Message changed during enrichment")
    message.enrichment = result
    db.commit()
    return message_data(db, message)


@app.get("/api/sources")
def sources(owner: str = Depends(identity), db: Session = Depends(db_session)):
    return [row(item, ("token",)) for item in db.scalars(select(Source).order_by(Source.name))]


@app.post("/api/sources")
def add_source(
    input: SourceInput, owner: str = Depends(identity), db: Session = Depends(db_session)
):
    item = Source(**input.model_dump())
    db.add(item)
    db.commit()
    return row(item, ("token",))


@app.patch("/api/sources/{source_id}")
def patch_source(
    source_id: str,
    input: SourcePatch,
    owner: str = Depends(identity),
    db: Session = Depends(db_session),
):
    item = get_or_404(db, Source, source_id)
    for key, value in input.model_dump(exclude_unset=True).items():
        if value is None and key in ("name", "type", "enabled", "poll_interval_seconds"):
            raise HTTPException(422, f"{key} cannot be null")
        setattr(item, key, value)
    db.commit()
    return row(item, ("token",))


@app.delete("/api/sources/{source_id}")
def delete_source(
    source_id: str, owner: str = Depends(identity), db: Session = Depends(db_session)
):
    item = get_or_404(db, Source, source_id)
    if db.scalar(select(Message.id).where(Message.source_id == source_id).limit(1)):
        raise HTTPException(409, "Source has messages; disable it instead")
    db.delete(item)
    db.commit()
    return {"ok": True}


@app.post("/api/ingress/{source_id}")
def ingress(
    source_id: str,
    input: MessageInput,
    x_source_token: str = Header(default=""),
    db: Session = Depends(db_session),
):
    source = get_or_404(db, Source, source_id)
    if (
        source.type != "webhook"
        or not source.token
        or not hmac.compare_digest(source.token, x_source_token)
    ):
        raise HTTPException(401, "Invalid source credential")
    if not input.external_id:
        raise HTTPException(422, "external_id is required")
    values = input.model_dump()
    values["source_id"] = source_id
    return message_data(db, create_message(db, values))


@app.get("/api/subscriptions")
def subscriptions(owner: str = Depends(identity), db: Session = Depends(db_session)):
    return [row(item) for item in db.scalars(select(Subscription).order_by(Subscription.owner_id))]


@app.post("/api/subscriptions")
def add_subscription(
    input: SubscriptionInput, owner: str = Depends(identity), db: Session = Depends(db_session)
):
    item = Subscription(**input.model_dump())
    db.add(item)
    db.commit()
    return row(item)


@app.patch("/api/subscriptions/{subscription_id}")
def patch_subscription(
    subscription_id: str,
    input: SubscriptionPatch,
    owner: str = Depends(identity),
    db: Session = Depends(db_session),
):
    item = get_or_404(db, Subscription, subscription_id)
    for key, value in input.model_dump(exclude_unset=True).items():
        if value is None and key in ("owner_id", "mode", "enabled"):
            raise HTTPException(422, f"{key} cannot be null")
        setattr(item, key, value)
    db.commit()
    return row(item)


@app.delete("/api/subscriptions/{subscription_id}")
def delete_subscription(
    subscription_id: str, owner: str = Depends(identity), db: Session = Depends(db_session)
):
    db.delete(get_or_404(db, Subscription, subscription_id))
    db.commit()
    return {"ok": True}


@app.get("/api/deliveries")
def deliveries(
    owner_id: str | None = None,
    status: str | None = None,
    message_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    owner: str = Depends(identity),
    db: Session = Depends(db_session),
):
    query = (
        select(Delivery)
        .order_by(Delivery.created_at.desc(), Delivery.id.desc())
        .limit(limit)
        .offset(offset)
    )
    for field, value in (
        (Delivery.owner_id, owner_id),
        (Delivery.status, status),
        (Delivery.message_id, message_id),
    ):
        if value is not None:
            query = query.where(field == value)
    return [row(item) for item in db.scalars(query)]


@app.post("/api/deliveries/{delivery_id}/retry")
def retry(delivery_id: str, owner: str = Depends(identity), db: Session = Depends(db_session)):
    item = get_or_404(db, Delivery, delivery_id)
    message = get_or_404(db, Message, item.message_id)
    if (
        item.status != "failed"
        or message.status != "active"
        or item.version != message.version
        or (message.expires_at and message.expires_at <= now())
    ):
        raise HTTPException(409, "Delivery cannot be retried")
    item.status, item.attempts, item.next_attempt_at, item.last_error = "pending", 0, now(), None
    db.commit()
    hint()
    return row(item)


@app.get("/api/dashboard")
def dashboard(owner: str = Depends(identity), db: Session = Depends(db_session)):
    counts = {
        name: db.scalar(select(func.count()).select_from(model))
        for name, model in (
            ("messages", Message),
            ("sources", Source),
            ("subscriptions", Subscription),
            ("deliveries", Delivery),
        )
    }
    counts["active_messages"] = db.scalar(
        select(func.count())
        .select_from(Message)
        .where(
            Message.status == "active",
            or_(Message.expires_at.is_(None), Message.expires_at > now()),
        )
    )
    for status in ("pending", "accepted", "processed", "failed", "cancelled"):
        counts[status] = db.scalar(
            select(func.count()).select_from(Delivery).where(Delivery.status == status)
        )
    return counts


@app.get("/api/integrations/duet/inbox", dependencies=[Depends(service_auth)])
def inbox(
    owner_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(db_session),
):
    query = (
        select(Delivery, Message, Source.name)
        .join(Message, Delivery.message_id == Message.id)
        .outerjoin(Source, Message.source_id == Source.id)
        .where(
            Delivery.owner_id == owner_id,
            Message.status == "active",
            Delivery.version == Message.version,
            Delivery.status != "cancelled",
            or_(Message.expires_at.is_(None), Message.expires_at > now()),
        )
        .order_by(Delivery.created_at.desc(), Delivery.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return [
        {**row(delivery), "message": {**row(message), "source": source}}
        for delivery, message, source in db.execute(query)
    ]


@app.get("/api/integrations/duet/messages/{message_id}", dependencies=[Depends(service_auth)])
def service_message(message_id: str, owner_id: str, db: Session = Depends(db_session)):
    return detail(db, get_or_404(db, Message, message_id))


@app.post("/api/integrations/duet/messages", dependencies=[Depends(service_auth)])
def service_publish(input: ServiceMessage, db: Session = Depends(db_session)):
    values = input.model_dump(exclude={"owner_id"})
    values["publisher"] = input.owner_id
    return message_data(db, create_message(db, values))


@app.post(
    "/api/integrations/duet/messages/{message_id}/responses", dependencies=[Depends(service_auth)]
)
def service_response(message_id: str, input: ResponseInput, db: Session = Depends(db_session)):
    if not input.owner_id:
        raise HTTPException(422, "owner_id is required")
    return row(
        respond(db, get_or_404(db, Message, message_id), input.owner_id, input.response, input.note)
    )


@app.post(
    "/api/integrations/duet/deliveries/{delivery_id}/result", dependencies=[Depends(service_auth)]
)
def delivery_result(delivery_id: str, input: ResultInput, db: Session = Depends(db_session)):
    item = get_or_404(db, Delivery, delivery_id)
    if item.owner_id != input.owner_id:
        raise HTTPException(409, "Delivery owner does not match")
    message = get_or_404(db, Message, item.message_id)
    if (
        message.status != "active"
        or message.version != item.version
        or (message.expires_at and message.expires_at <= now())
    ):
        raise HTTPException(409, "Delivery is no longer current")
    item.status, item.notified, item.summary, item.updated_at = (
        input.status,
        input.notified,
        input.summary,
        now(),
    )
    db.commit()
    return row(item)


@app.get("/api/integrations/duet/messages", dependencies=[Depends(service_auth)])
def service_search(
    owner_id: str,
    q: str | None = None,
    channel: str | None = None,
    topic: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    summary: bool = False,
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(db_session),
):
    query = (
        select(Message, Source.name)
        .outerjoin(Source, Message.source_id == Source.id)
        .where(
            Message.status == "active",
            or_(Message.expires_at.is_(None), Message.expires_at > now()),
        )
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(limit)
        .offset(offset)
    )
    if q:
        query = query.where(or_(Message.title.ilike(f"%{q}%"), Message.body.ilike(f"%{q}%")))
    if channel is not None:
        query = query.where(Message.channel == channel)
    if topic is not None:
        query = query.where(Message.topic == topic)
    results = [{**row(item), "source": source} for item, source in db.execute(query)]
    if summary:
        for result in results:
            result["body_excerpt"] = result.pop("body")[:500]
    return results


@app.get("/api/integrations/duet/subscriptions", dependencies=[Depends(service_auth)])
def service_subscriptions(owner_id: str, db: Session = Depends(db_session)):
    return [
        row(item)
        for item in db.scalars(select(Subscription).where(Subscription.owner_id == owner_id))
    ]


@app.post("/api/integrations/duet/subscriptions", dependencies=[Depends(service_auth)])
def service_subscribe(input: SubscriptionInput, db: Session = Depends(db_session)):
    item = db.scalar(
        select(Subscription).where(
            Subscription.owner_id == input.owner_id,
            Subscription.channel == input.channel,
            Subscription.topic == input.topic,
            Subscription.mode == input.mode,
        )
    )
    if item is None:
        item = Subscription(**input.model_dump())
        db.add(item)
    else:
        item.enabled = input.enabled
    db.commit()
    return row(item)


@app.patch(
    "/api/integrations/duet/subscriptions/{subscription_id}", dependencies=[Depends(service_auth)]
)
def service_patch_subscription(
    subscription_id: str, owner_id: str, input: SubscriptionPatch, db: Session = Depends(db_session)
):
    item = get_or_404(db, Subscription, subscription_id)
    if item.owner_id != owner_id or (input.owner_id is not None and input.owner_id != owner_id):
        raise HTTPException(409, "Subscription owner does not match")
    for key, value in input.model_dump(exclude_unset=True).items():
        if value is None and key in ("owner_id", "mode", "enabled"):
            raise HTTPException(422, f"{key} cannot be null")
        setattr(item, key, value)
    db.commit()
    return row(item)


@app.delete(
    "/api/integrations/duet/subscriptions/{subscription_id}", dependencies=[Depends(service_auth)]
)
def service_delete_subscription(
    subscription_id: str, owner_id: str, db: Session = Depends(db_session)
):
    item = get_or_404(db, Subscription, subscription_id)
    if item.owner_id != owner_id:
        raise HTTPException(409, "Subscription owner does not match")
    db.delete(item)
    db.commit()
    return {"ok": True}


@app.post(
    "/api/integrations/duet/deliveries/{delivery_id}/mark", dependencies=[Depends(service_auth)]
)
def mark_consumed(delivery_id: str, input: MarkInput, db: Session = Depends(db_session)):
    item = get_or_404(db, Delivery, delivery_id)
    if item.owner_id != input.owner_id:
        raise HTTPException(409, "Delivery owner does not match")
    message = get_or_404(db, Message, item.message_id)
    if (
        message.status != "active"
        or message.version != item.version
        or (message.expires_at and message.expires_at <= now())
    ):
        raise HTTPException(409, "Delivery is no longer current")
    item.status, item.updated_at = ("processed" if input.consumed else "accepted"), now()
    db.commit()
    return row(item)


@app.post("/api/deliveries/{delivery_id}/read")
def mark_read(
    delivery_id: str,
    input: ReadInput,
    owner: str = Depends(identity),
    db: Session = Depends(db_session),
):
    item = get_or_404(db, Delivery, delivery_id)
    if item.owner_id != input.owner_id:
        raise HTTPException(409, "Delivery owner does not match")
    item.human_read, item.updated_at = input.read, now()
    db.commit()
    return row(item)


frontend = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if frontend.is_dir():
    app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
