from datetime import timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import service, worker
from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import Delivery, now


@pytest.fixture
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app) as client:
        assert (
            client.post("/api/auth/login", json={"username": "DEV-AAA"}).json()["owner_id"]
            == "owner-alex"
        )
        yield client


def test_fanout_versions_withdraw_feedback_and_receipts(client, monkeypatch):
    for owner, mode in [
        ("owner-alex", "digest"),
        ("owner-alex", "immediate"),
        ("owner-maya", "digest"),
    ]:
        assert (
            client.post(
                "/api/subscriptions", json={"owner_id": owner, "topic": "news", "mode": mode}
            ).status_code
            == 200
        )
    msg = client.post(
        "/api/messages",
        json={"title": "News", "body": "Content", "topic": "news", "client_request_key": "one"},
    ).json()
    assert (
        client.post(
            "/api/messages", json={"title": "News", "body": "Content", "client_request_key": "one"}
        ).json()["id"]
        == msg["id"]
    )
    deliveries = client.get(f"/api/messages/{msg['id']}").json()["deliveries"]
    assert {(d["owner_id"], d["mode"]) for d in deliveries} == {
        ("owner-alex", "immediate"),
        ("owner-maya", "digest"),
    }
    sent = []

    def accept(url, **kwargs):
        sent.append(kwargs["json"])
        return httpx.Response(
            200,
            json={"request_id": "request-1", "status": "accepted"},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(worker.httpx, "post", accept)
    worker.deliver_due()
    assert len(sent) == 2 and all(x["version"] == 1 for x in sent)
    d = client.get("/api/deliveries", params={"owner_id": "owner-alex"}).json()[0]
    assert d["status"] == "accepted" and not d["notified"] and not d["human_read"]
    headers = {"X-Message-Center-Token": "test-token"}
    assert (
        client.post(
            f"/api/integrations/duet/deliveries/{d['id']}/result",
            headers=headers,
            json={"owner_id": "owner-alex", "status": "processed", "notified": False},
        ).json()["status"]
        == "processed"
    )
    assert client.post(
        f"/api/deliveries/{d['id']}/read",
        headers=headers,
        json={"owner_id": "owner-alex", "read": True},
    ).json()["human_read"]
    assert (
        client.post(
            f"/api/messages/{msg['id']}/responses", json={"response": "attending"}
        ).status_code
        == 200
    )
    assert client.get(f"/api/messages/{msg['id']}").json()["response_counts"]["attending"] == 1
    updated = client.patch(
        f"/api/messages/{msg['id']}", json={"body": "Changed", "recipients": ["owner-jordan"]}
    ).json()
    assert updated["version"] == 2
    client.post(f"/api/messages/{msg['id']}/withdraw")
    worker.deliver_due()
    assert len(sent) == 2
    assert (
        client.get(
            "/api/integrations/duet/inbox", headers=headers, params={"owner_id": "owner-jordan"}
        ).json()
        == []
    )


def test_source_toggle_retries_and_expiry(client, monkeypatch):
    source = client.post(
        "/api/sources", json={"name": "Hook", "type": "webhook", "token": "secret"}
    ).json()
    assert "token" not in source
    path = f"/api/ingress/{source['id']}"
    headers = {"X-Source-Token": "secret"}
    payload = {
        "title": "External",
        "body": "Body",
        "external_id": "event-1",
        "recipients": ["owner-alex"],
    }
    a = client.post(path, json=payload, headers=headers).json()
    assert client.post(path, json=payload, headers=headers).json()["id"] == a["id"]
    client.patch(f"/api/sources/{source['id']}", json={"enabled": False})
    assert (
        client.post(path, json={**payload, "external_id": "event-2"}, headers=headers).status_code
        == 409
    )

    def fail(url, **kwargs):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(worker.httpx, "post", fail)
    for _ in range(worker.MAX_ATTEMPTS):
        with SessionLocal.begin() as db:
            d = db.scalar(select(Delivery))
            d.next_attempt_at = now() - timedelta(seconds=1)
        worker.deliver_due()
    d = client.get("/api/deliveries").json()[0]
    assert d["status"] == "failed" and d["attempts"] == worker.MAX_ATTEMPTS
    assert client.post(f"/api/deliveries/{d['id']}/retry").json()["status"] == "pending"
    client.patch(
        f"/api/messages/{a['id']}", json={"expires_at": (now() - timedelta(seconds=1)).isoformat()}
    )
    worker.deliver_due()
    assert all(x["status"] == "cancelled" for x in client.get("/api/deliveries").json())


def test_callback_result_race_and_digest_null_request(client, monkeypatch):
    client.post("/api/subscriptions", json={"owner_id": "owner-maya", "mode": "digest"})
    client.post("/api/messages", json={"title": "Digest", "body": "Body"})

    def accept(url, **kwargs):
        payload = kwargs["json"]
        result = client.post(
            f"/api/integrations/duet/deliveries/{payload['delivery_id']}/result",
            headers={"X-Message-Center-Token": "test-token"},
            json={"owner_id": "owner-maya", "status": "processed", "notified": False},
        )
        assert result.status_code == 200
        return httpx.Response(
            200, json={"status": "accepted", "request_id": None}, request=httpx.Request("POST", url)
        )

    monkeypatch.setattr(worker.httpx, "post", accept)
    worker.deliver_due()
    assert client.get("/api/deliveries").json()[0]["status"] == "processed"


def test_poll_dedup_and_enrichment_failure_preserves_original(client, monkeypatch):
    client.post("/api/subscriptions", json={"owner_id": "owner-maya", "mode": "digest"})
    source = client.post(
        "/api/sources",
        json={
            "name": "Feed",
            "type": "poll",
            "url": "http://feed.test",
            "poll_interval_seconds": 10,
        },
    ).json()

    def fetch(url, **kwargs):
        return httpx.Response(
            200,
            json=[{"external_id": "1", "title": "Feed item", "body": "Original"}],
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(worker.httpx, "get", fetch)
    worker.poll_sources()
    with SessionLocal.begin() as db:
        from app.models import Source

        db.get(Source, source["id"]).next_poll_at = now() - timedelta(seconds=1)
    worker.poll_sources()
    messages = client.get("/api/messages").json()
    assert len(messages) == 1
    deliveries = client.get(f"/api/messages/{messages[0]['id']}").json()["deliveries"]
    assert [(item["owner_id"], item["mode"]) for item in deliveries] == [("owner-maya", "digest")]
    monkeypatch.setattr("app.enrichment.enabled", lambda: True)

    async def failed(*args):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr("app.enrichment.enrich", failed)
    assert client.post(f"/api/messages/{messages[0]['id']}/enrich").status_code == 502
    assert client.get(f"/api/messages/{messages[0]['id']}").json()["body"] == "Original"


def test_service_auth_and_subscriptions(client):
    path = "/api/integrations/duet/subscriptions"
    assert client.get(path, params={"owner_id": "owner-alex"}).status_code == 401
    headers = {"X-Message-Center-Token": "test-token"}
    sub = client.post(path, headers=headers, json={"owner_id": "owner-alex", "topic": "ops"}).json()
    assert (
        client.get(path, headers=headers, params={"owner_id": "owner-alex"}).json()[0]["id"]
        == sub["id"]
    )
    assert (
        client.patch(
            f"{path}/{sub['id']}",
            headers=headers,
            params={"owner_id": "owner-maya"},
            json={"mode": "digest"},
        ).status_code
        == 409
    )


def test_service_invitation_targets_only_explicit_recipients(client, monkeypatch):
    headers = {"X-Message-Center-Token": "test-token"}
    for owner in ("owner-alex", "owner-maya", "owner-jordan"):
        client.post("/api/subscriptions", json={"owner_id": owner, "mode": "digest"})
    payload = {
        "owner_id": "owner-jordan",
        "client_request_key": "invitation-1",
        "title": "Team lunch",
        "body": "Lunch on Friday",
        "kind": "invitation",
        "recipients": ["owner-alex", "owner-maya", "owner-alex"],
        "metadata": {"activity": "lunch"},
    }
    path = "/api/integrations/duet/messages"
    message = client.post(path, headers=headers, json=payload).json()
    assert client.post(path, headers=headers, json=payload).json()["id"] == message["id"]
    deliveries = client.get(f"/api/messages/{message['id']}").json()["deliveries"]
    assert {(d["owner_id"], d["mode"]) for d in deliveries} == {
        ("owner-alex", "immediate"),
        ("owner-maya", "immediate"),
    }

    sent = []

    def accept(url, **kwargs):
        sent.append(kwargs["json"])
        return httpx.Response(
            200,
            json={"request_id": "request-1", "status": "accepted"},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(worker.httpx, "post", accept)
    worker.deliver_due()
    assert {item["owner_id"] for item in sent} == {"owner-alex", "owner-maya"}
    assert len(sent) == 2
    assert all(item["message"]["kind"] == "invitation" for item in sent)
    assert all(item["message"]["metadata"] == {"activity": "lunch"} for item in sent)
    response = client.post(
        f"{path}/{message['id']}/responses",
        headers=headers,
        json={"owner_id": "owner-maya", "response": "attending"},
    )
    assert response.status_code == 200
    assert client.get(f"/api/messages/{message['id']}").json()["response_counts"]["attending"] == 1


def test_registered_owner_uses_all_delivery_contracts_and_unknown_owner_is_rejected(client):
    person = {"owner_id": "owner-dev-four", "name": "Developer Four"}
    service.PEOPLE.append(person)
    headers = {"X-Message-Center-Token": "test-token"}
    base = "/api/integrations/duet"
    try:
        subscription = client.post(
            f"{base}/subscriptions",
            headers=headers,
            json={"owner_id": person["owner_id"], "topic": "stories"},
        )
        assert subscription.status_code == 200
        subscription_id = subscription.json()["id"]
        assert (
            client.patch(
                f"{base}/subscriptions/{subscription_id}",
                headers=headers,
                params={"owner_id": person["owner_id"]},
                json={"owner_id": person["owner_id"], "mode": "digest"},
            ).status_code
            == 200
        )
        payload = {
            "owner_id": person["owner_id"],
            "client_request_key": "fourth-owner",
            "title": "Story assignment",
            "body": "Please review",
            "recipients": [person["owner_id"], person["owner_id"]],
        }
        published = client.post(f"{base}/messages", headers=headers, json=payload)
        assert published.status_code == 200
        message = published.json()
        assert message["publisher"] == person["owner_id"] and message["recipients"] == [
            person["owner_id"]
        ]
        delivery = client.get(f"/api/messages/{message['id']}").json()["deliveries"][0]
        delivery_path = f"{base}/deliveries/{delivery['id']}"
        assert (
            client.post(
                delivery_path + "/result",
                headers=headers,
                json={"owner_id": person["owner_id"], "status": "processed", "notified": False},
            ).status_code
            == 200
        )
        assert (
            client.post(
                delivery_path + "/mark",
                headers=headers,
                json={"owner_id": person["owner_id"], "consumed": True},
            ).status_code
            == 200
        )
        assert (
            client.post(
                f"/api/deliveries/{delivery['id']}/read",
                json={"owner_id": person["owner_id"], "read": True},
            ).status_code
            == 200
        )
        assert (
            client.post(
                f"{base}/messages/{message['id']}/responses",
                headers=headers,
                json={"owner_id": person["owner_id"], "response": "acknowledge"},
            ).status_code
            == 200
        )
        assert (
            client.patch(
                f"/api/messages/{message['id']}", json={"recipients": [person["owner_id"]]}
            ).status_code
            == 200
        )

        unknown = "owner-not-registered"
        assert (
            client.post(
                f"{base}/messages", headers=headers, json={**payload, "owner_id": unknown}
            ).status_code
            == 422
        )
        assert (
            client.post(
                f"{base}/messages", headers=headers, json={**payload, "recipients": [unknown]}
            ).status_code
            == 422
        )
        assert (
            client.patch(
                f"/api/messages/{message['id']}", json={"recipients": [unknown]}
            ).status_code
            == 422
        )
        assert (
            client.post(
                f"{base}/subscriptions", headers=headers, json={"owner_id": unknown}
            ).status_code
            == 422
        )
        assert (
            client.patch(
                f"{base}/subscriptions/{subscription_id}",
                headers=headers,
                params={"owner_id": person["owner_id"]},
                json={"owner_id": unknown},
            ).status_code
            == 422
        )
        assert (
            client.post(
                delivery_path + "/result",
                headers=headers,
                json={"owner_id": unknown, "status": "processed", "notified": False},
            ).status_code
            == 422
        )
        assert (
            client.post(
                delivery_path + "/mark",
                headers=headers,
                json={"owner_id": unknown, "consumed": True},
            ).status_code
            == 422
        )
        assert (
            client.post(
                f"/api/deliveries/{delivery['id']}/read", json={"owner_id": unknown, "read": True}
            ).status_code
            == 422
        )
        assert (
            client.post(
                f"{base}/messages/{message['id']}/responses",
                headers=headers,
                json={"owner_id": unknown, "response": "acknowledge"},
            ).status_code
            == 422
        )
    finally:
        service.PEOPLE.remove(person)


def test_metadata_pagination_expiry_and_subscription_replay(client):
    headers = {"X-Message-Center-Token": "test-token"}
    path = "/api/integrations/duet/subscriptions"
    sub = {"owner_id": "owner-alex", "topic": "ops", "mode": "digest", "enabled": False}
    first = client.post(path, headers=headers, json=sub).json()
    second = client.post(path, headers=headers, json={**sub, "enabled": True}).json()
    assert first["id"] == second["id"] and second["enabled"]
    msg = client.post(
        "/api/messages",
        json={"title": "Ops", "body": "Original", "topic": "ops", "metadata": {"ticket": "T-1"}},
    ).json()
    assert msg["metadata"] == {"ticket": "T-1"}
    assert len(client.get("/api/messages", params={"limit": 1, "offset": 1}).json()) == 0
    assert (
        client.get(
            "/api/integrations/duet/messages",
            headers=headers,
            params={"owner_id": "owner-alex", "q": "Ops"},
        ).json()[0]["id"]
        == msg["id"]
    )
    assert (
        client.patch(f"/api/messages/{msg['id']}", json={"metadata": {"ticket": "T-2"}}).json()[
            "version"
        ]
        == 2
    )
    detail = client.get(f"/api/messages/{msg['id']}").json()
    assert detail["revisions"][0]["content"]["metadata"]["ticket"] == "T-1"
    client.patch(
        f"/api/messages/{msg['id']}",
        json={"expires_at": (now() - timedelta(seconds=1)).isoformat()},
    )
    assert (
        client.post(
            f"/api/messages/{msg['id']}/responses", json={"response": "attending"}
        ).status_code
        == 409
    )
    worker.expire_messages()
    assert client.get(f"/api/messages/{msg['id']}").json()["status"] == "expired"
    assert all(
        item["status"] == "cancelled"
        for item in client.get(f"/api/messages/{msg['id']}").json()["deliveries"]
    )


def test_service_search_summary_is_bounded(client):
    client.post("/api/messages", json={"title": "Long", "body": "x" * 600})
    headers = {"X-Message-Center-Token": "test-token"}
    path = "/api/integrations/duet/messages"
    summary = client.get(
        path, headers=headers, params={"owner_id": "owner-alex", "summary": True}
    ).json()[0]
    assert len(summary["body_excerpt"]) == 500 and "body" not in summary
    assert (
        client.get(
            path, headers=headers, params={"owner_id": "owner-alex", "limit": 101}
        ).status_code
        == 422
    )
