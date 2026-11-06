"""Production UI and Route Acceptance Test Suite.

Verifies:
1. Application startup and routing contracts.
2. Unauthenticated root serves login page with security headers.
3. Protected assets (e.g. index.html) are hidden (404) from unauthenticated visitors.
4. Public static assets (CSS, favicon) are served cleanly.
5. Loopback host boundary enforcement (non-loopback access returns 403).
6. Protected API endpoints reject unauthenticated access with 401.
7. Public health and auth status endpoints respond with 200.
8. Authenticated root serves full SPA dashboard (index.html).
9. Authenticated UI data contracts for profile, jobs, applications, inbox, resumes, and interview preparation.
"""
import asyncio
import json
import pytest

from careerorbit.database.db import init_db
from careerorbit.web.app import app
from tests.authenticated_request import authenticated_headers


@pytest.fixture(autouse=True)
def setup_test_db():
    init_db()


async def _asgi_call(method: str, path: str, headers: dict = None, body: bytes = b"", host_header: str = "127.0.0.1:8000"):
    req_headers = [
        (b"host", host_header.encode()),
    ]
    for k, v in (headers or {}).items():
        req_headers.append((k.lower().encode(), v.encode()))

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": req_headers,
        "server": ("127.0.0.1", 8000),
        "client": ("127.0.0.1", 54321),
    }
    sent_response = {}
    response_body = []
    body_sent = False
    disconn = asyncio.Event()

    async def receive():
        nonlocal body_sent
        if not body_sent:
            body_sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        await disconn.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.start":
            sent_response["status"] = message["status"]
            sent_response["headers"] = dict(message.get("headers", []))
        elif message["type"] == "http.response.body":
            response_body.append(message.get("body", b""))
            if not message.get("more_body", False):
                disconn.set()

    await app(scope, receive, send)
    resp_headers = {k.decode().lower(): v.decode() for k, v in sent_response.get("headers", {}).items()}
    return sent_response.get("status", 500), resp_headers, b"".join(response_body).decode("utf-8", errors="replace")


def test_ui_unauthenticated_login_serving():
    """Verify that visiting root unauthenticated delivers the login page with security headers."""
    headers = authenticated_headers("GET", {"X-Test-Unauthenticated": "true"})
    st, hdrs, body = asyncio.run(_asgi_call("GET", "/", headers=headers))
    assert st == 200
    assert "CareerOrbit" in body
    assert "password" in body
    assert hdrs.get("x-content-type-options") == "nosniff"
    assert hdrs.get("x-frame-options") == "DENY"
    assert hdrs.get("cache-control") == "no-store"


def test_ui_protected_static_index_hidden_from_anonymous_visitors():
    """Verify that unauthenticated direct GET /static/index.html is hidden (404)."""
    headers = authenticated_headers("GET", {"X-Test-Unauthenticated": "true"})
    st, hdrs, body = asyncio.run(_asgi_call("GET", "/static/index.html", headers=headers))
    assert st == 404


def test_ui_public_static_assets():
    """Verify that design-system CSS and favicon are served with 200."""
    headers = authenticated_headers("GET", {"X-Test-Unauthenticated": "true"})
    st_css, hdrs_css, body_css = asyncio.run(_asgi_call("GET", "/static/design-system.css", headers=headers))
    assert st_css == 200
    assert len(body_css) > 1000
    assert "CareerOrbit AI" in body_css or "body" in body_css

    st_fav, hdrs_fav, body_fav = asyncio.run(_asgi_call("GET", "/static/favicon.svg", headers=headers))
    assert st_fav == 200
    assert "<svg" in body_fav


def test_ui_loopback_boundary_enforcement():
    """Verify that requests targeting non-loopback hostnames are rejected with 403."""
    headers = authenticated_headers("GET", {"X-Test-Unauthenticated": "true"})
    st, hdrs, body = asyncio.run(_asgi_call("GET", "/", headers=headers, host_header="remote-host.com:8000"))
    assert st == 403
    assert "available only from this device" in body


def test_ui_unauthenticated_api_rejection():
    """Verify that protected API endpoints return 401 when accessed without authentication."""
    headers = authenticated_headers("GET", {"X-Test-Unauthenticated": "true"})
    for endpoint in ["/api/jobs", "/api/applications", "/api/profile", "/api/inbox", "/api/resumes"]:
        st, hdrs, body = asyncio.run(_asgi_call("GET", endpoint, headers=headers))
        assert st == 401, f"{endpoint} allowed unauthenticated access with status {st}"


def test_ui_public_health_and_auth_status_routes():
    """Verify health and auth status endpoints return 200 for public readiness checks."""
    headers = authenticated_headers("GET", {"X-Test-Unauthenticated": "true"})
    st_health, _, body_health = asyncio.run(_asgi_call("GET", "/health", headers=headers))
    assert st_health == 200
    assert json.loads(body_health).get("status") == "healthy"

    st_live, _, body_live = asyncio.run(_asgi_call("GET", "/api/health/liveness", headers=headers))
    assert st_live == 200

    st_ready, _, body_ready = asyncio.run(_asgi_call("GET", "/api/health/readiness", headers=headers))
    assert st_ready == 200

    st_auth, _, body_auth = asyncio.run(_asgi_call("GET", "/api/auth/status", headers=headers))
    assert st_auth == 200
    assert "registration_enabled" in json.loads(body_auth)


def test_ui_authenticated_dashboard_serving():
    """Verify that authenticated visitors to root receive the full SPA dashboard index.html."""
    headers = authenticated_headers("GET")
    st, hdrs, body = asyncio.run(_asgi_call("GET", "/", headers=headers))
    assert st == 200
    assert "CareerOrbit AI" in body
    assert "tab-btn" in body or "Dashboard" in body or "nav" in body.lower()
    assert hdrs.get("cache-control") == "no-store"


def test_ui_authenticated_core_data_contracts():
    """Verify that all core UI sections have functioning data contracts."""
    sections = [
        ("GET", "/api/profile", "Profile"),
        ("GET", "/api/profile/full", "Full Profile with Evidence"),
        ("GET", "/api/profile/history", "Profile Change History"),
        ("GET", "/api/profile/evidence/documents", "Evidence Documents"),
        ("GET", "/api/jobs", "Jobs"),
        ("GET", "/api/dashboard", "Dashboard Stats"),
        ("GET", "/api/applications", "Applications"),
        ("GET", "/api/inbox", "Inbox"),
        ("GET", "/api/inbox/stats", "Inbox Stats"),
        ("GET", "/api/resumes", "Resumes"),
        ("GET", "/api/interview-prep/role-workspaces", "Prep Workspaces"),
        ("GET", "/api/resources/pathways", "Learning Pathways"),
        ("GET", "/api/resources", "Curated Resources"),
    ]
    for method, endpoint, label in sections:
        headers = authenticated_headers(method)
        st, hdrs, body = asyncio.run(_asgi_call(method, endpoint, headers=headers))
        assert st == 200, f"{label} ({endpoint}) failed with status {st}: {body[:200]}"
        # Ensure valid JSON response
        data = json.loads(body)
        assert data is not None, f"{label} returned empty or null data"
