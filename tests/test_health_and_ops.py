"""Automated tests for CareerOrbit AI operational health and diagnostics endpoints."""
import json
import pytest
from run import is_loopback_host
from careerorbit.web.app import app
from careerorbit.database.db import init_db
from careerorbit.config.settings import SETTINGS


def test_launcher_accepts_only_loopback_bind_hosts():
    assert is_loopback_host("localhost")
    assert is_loopback_host("127.0.0.1")
    assert is_loopback_host("::1")
    assert not is_loopback_host("0.0.0.0")
    assert not is_loopback_host("192.168.1.10")
    assert not is_loopback_host("careerorbit.example.com")


@pytest.mark.anyio
async def test_non_loopback_peer_is_rejected_outside_testing(monkeypatch):
    monkeypatch.setattr(SETTINGS, "TESTING", False)
    status, _, body = await asgi_request(
        app, method="GET", path="/api/health/liveness", client=("192.168.1.25", 4567)
    )
    assert status == 403
    assert b"only from this device" in body


async def asgi_request(app, method="GET", path="/", query="", headers=None, client=("127.0.0.1", 12345)):
    from tests.authenticated_request import authenticated_headers
    headers = authenticated_headers(method, headers)
    scope = {
        "type": "http",
        "scheme": "http",
        "method": method,
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": query.encode("utf-8"),
        "headers": [(k.lower().encode("utf-8"), v.encode("utf-8")) for k, v in (headers or {}).items()],
        "server": ("127.0.0.1", 8000),
        "client": client,
    }
    response_body = []
    response_headers = {}
    response_status = 200

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        nonlocal response_status, response_headers, response_body
        if message["type"] == "http.response.start":
            response_status = message["status"]
            response_headers = {k.decode("utf-8"): v.decode("utf-8") for k, v in message.get("headers", [])}
        elif message["type"] == "http.response.body":
            response_body.append(message.get("body", b""))

    await app(scope, receive, send)
    return response_status, response_headers, b"".join(response_body)


@pytest.mark.anyio
async def test_health_aggregate_endpoint():
    init_db()
    status, _, body = await asgi_request(app, method="GET", path="/api/health")
    assert status == 200
    data = json.loads(body.decode("utf-8"))
    assert data["status"] in ("healthy", "degraded")
    assert data["liveness"] == "alive"
    assert data["readiness"] in ("ready", "unready")
    assert "database" in data
    assert "discovery" in data
    assert "telegram" in data
    assert "whatsapp" in data
    assert "scheduler" in data
    assert data["whatsapp"]["import_capability"] == "ready"


@pytest.mark.anyio
async def test_liveness_endpoint():
    status, _, body = await asgi_request(app, method="GET", path="/api/health/liveness")
    assert status == 200
    data = json.loads(body.decode("utf-8"))
    assert data["status"] == "alive"
    assert data["app"] == "CareerOrbit AI"


@pytest.mark.anyio
async def test_readiness_endpoint():
    init_db()
    status, _, body = await asgi_request(app, method="GET", path="/api/health/readiness")
    assert status == 200
    data = json.loads(body.decode("utf-8"))
    assert data["status"] == "ready"
    assert data["database"] == "connected"


@pytest.mark.anyio
async def test_db_health_endpoint():
    init_db()
    status, _, body = await asgi_request(app, method="GET", path="/api/health/db")
    assert status == 200
    data = json.loads(body.decode("utf-8"))
    assert data["status"] == "healthy"
    assert data["integrity"] == "ok"
    assert "tables" in data
    assert "jobs" in data["tables"]
    assert "applications" in data["tables"]
    assert "inbox_messages" in data["tables"]
    assert "learning_resources" in data["tables"]


@pytest.mark.anyio
async def test_sources_health_endpoint():
    status, _, body = await asgi_request(app, method="GET", path="/api/health/sources")
    assert status == 200
    data = json.loads(body.decode("utf-8"))
    assert data["count"] >= 6
    assert "sources" in data
    source_names = [s["name"] for s in data["sources"]]
    assert any("Jobicy" in name for name in source_names)
    assert any("Remotive" in name for name in source_names)
    assert any("Arbeitnow" in name for name in source_names)


@pytest.mark.anyio
async def test_telegram_health_endpoint():
    status, _, body = await asgi_request(app, method="GET", path="/api/health/telegram")
    assert status == 200
    data = json.loads(body.decode("utf-8"))
    assert "configured" in data
    assert "running" in data
    assert "bot_username" in data


@pytest.mark.anyio
async def test_scheduler_health_endpoint():
    status, _, body = await asgi_request(app, method="GET", path="/api/health/scheduler")
    assert status == 200
    data = json.loads(body.decode("utf-8"))
    assert "scheduler_running" in data
    assert "target_discovery_time" in data
    assert "08:00 AM" in data["target_discovery_time"]
    assert "Disabled" in data.get("target_study_time", "") or "On-Demand" in data.get("target_study_time", "")


@pytest.mark.anyio
async def test_secret_redaction_across_health_endpoints(monkeypatch):
    test_secret = "1234567890:AAHSecretTokenValueTest123456"
    monkeypatch.setattr(SETTINGS, "TELEGRAM_BOT_TOKEN", test_secret)

    endpoints = [
        "/api/health",
        "/api/health/liveness",
        "/api/health/readiness",
        "/api/health/db",
        "/api/health/sources",
        "/api/health/telegram",
        "/api/health/scheduler",
    ]
    for ep in endpoints:
        status, _, body = await asgi_request(app, method="GET", path=ep)
        body_text = body.decode("utf-8")
        assert test_secret not in body_text, f"Secret token exposed in {ep}!"
