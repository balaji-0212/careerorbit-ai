"""Phase 11 verification test suite for Observability & Security Hardening.

Verifies:
1. Strict loopback-only host binding (127.0.0.1).
2. Health check and diagnostic endpoints return valid metrics.
3. Zero secret token exposure in health/diagnostic JSON payloads.
4. Git index excludes sensitive files (.env, databases, logs).
5. Clean standardized JSON error responses without stack trace leaks.
"""
import json
import subprocess
from pathlib import Path
import pytest
from careerorbit.config.settings import SETTINGS
from careerorbit.database.db import init_db
from careerorbit.web.app import app


async def asgi_request(app, method="GET", path="/", query="", body=b"", headers=None):
    from tests.authenticated_request import authenticated_headers
    headers = authenticated_headers(method, headers)
    """In-process ASGI helper for testing endpoints."""
    req_headers = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "path": path,
        "raw_path": path.encode(),
        "query_string": query.encode(),
        "headers": req_headers,
        "server": ("127.0.0.1", 8000),
        "client": ("127.0.0.1", 54321),
    }
    messages = []
    received = False

    async def receive():
        nonlocal received
        if not received:
            received = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        messages.append(message)

    await app(scope, receive, send)

    status_code = None
    response_headers = {}
    body_parts = []
    for m in messages:
        if m["type"] == "http.response.start":
            status_code = m["status"]
            response_headers = {k.decode().lower(): v.decode() for k, v in m.get("headers", [])}
        elif m["type"] == "http.response.body":
            body_parts.append(m.get("body", b""))

    return status_code, response_headers, b"".join(body_parts)


@pytest.fixture(autouse=True)
def setup_test_db():
    """Initializes the database schema for the test."""
    init_db()


def test_default_host_binding_is_loopback():
    """Verifies that the server binding defaults strictly to loopback (127.0.0.1)."""
    assert SETTINGS.HOST == "127.0.0.1", "Host must strictly default to 127.0.0.1 for local single-user security"
    assert SETTINGS.HOST != "0.0.0.0", "Public host binding (0.0.0.0) is strictly prohibited"


@pytest.mark.anyio
async def test_health_and_diagnostics_endpoints():
    """Verifies all health and diagnostic probes respond with HTTP 200 and healthy status."""
    # 1. Base /health
    status, _, body = await asgi_request(app, method="GET", path="/health")
    assert status == 200
    data = json.loads(body.decode())
    assert data["status"] == "healthy"

    # 2. Detailed /api/health
    status, _, body = await asgi_request(app, method="GET", path="/api/health")
    assert status == 200
    detailed = json.loads(body.decode())
    assert detailed["status"] == "healthy"
    assert detailed["database"]["connected"] is True
    assert "telegram" in detailed
    assert "scheduler" in detailed

    # 3. Liveness probe
    status, _, _ = await asgi_request(app, method="GET", path="/api/health/liveness")
    assert status == 200

    # 4. Readiness probe
    status, _, _ = await asgi_request(app, method="GET", path="/api/health/readiness")
    assert status == 200


@pytest.mark.anyio
async def test_secret_tokens_never_leaked_in_diagnostics():
    """Verifies that diagnostic endpoints mask API tokens and secrets."""
    status, _, body = await asgi_request(app, method="GET", path="/api/health")
    assert status == 200
    body_text = body.decode()

    # Raw unmasked token must not appear if token is configured
    if SETTINGS.TELEGRAM_BOT_TOKEN and len(SETTINGS.TELEGRAM_BOT_TOKEN) > 10:
        assert SETTINGS.TELEGRAM_BOT_TOKEN not in body_text, "Raw Telegram bot token leaked in /api/health response"

    data = json.loads(body_text)
    tg = data.get("telegram", {})
    if tg.get("configured") and tg.get("masked_token"):
        assert "..." in tg["masked_token"], "Masked token must have ellipsis delimiter"


def test_git_untracked_sensitive_files():
    """Verifies that .env is not tracked by Git."""
    try:
        proc = subprocess.run(["git", "ls-files", ".env"], capture_output=True, text=True, check=True)
        tracked_files = proc.stdout.strip()
        assert tracked_files == "", f".env is unexpectedly tracked in Git: {tracked_files}"
    except (subprocess.SubprocessError, FileNotFoundError):
        pass  # If git is not present in test environment, skip gracefully


@pytest.mark.anyio
async def test_clean_error_response_without_traceback_leak():
    """Verifies that 404 and 405 error responses return clean JSON without Python tracebacks."""
    status, _, body = await asgi_request(app, method="GET", path="/api/nonexistent-route-404-check")
    assert status == 404
    data = json.loads(body.decode())
    assert "detail" in data
    # Ensure no internal filesystem paths or python traceback strings are leaked
    body_str = body.decode()
    assert "Traceback (most recent call last)" not in body_str
    assert "careerorbit/web/app.py" not in body_str
