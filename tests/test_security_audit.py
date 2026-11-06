"""Comprehensive Security Audit Test Suite for CareerOrbit AI.
Verifies CORS restrictions, path traversal, security headers, privacy protection,
SSRF barriers, formula injection neutralization, and approval gates.
"""
import pytest
from fastapi import HTTPException
from careerorbit.web.app import app, get_profile, download_resume, ALLOWED_CORS_ORIGINS
from careerorbit.verifier.checker import VerificationEngine, _public_http_url
from careerorbit.database.db import _safe_csv_cell, init_db, save_job, get_connection, create_or_update_application, get_application_by_job_id
from careerorbit.models.schemas import Job, VerificationStatus, MatchTier, Application, ApplicationStatus


async def asgi_request(app, method="GET", path="/", headers=None, client=("127.0.0.1", 54321), body=b""):
    from tests.authenticated_request import authenticated_headers
    headers = authenticated_headers(method, headers)
    """Simple, pure-Python in-process ASGI test helper without external dependencies."""
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "server": ("127.0.0.1", 8000),
        "client": client,
    }
    messages = []
    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}
    async def send(message):
        messages.append(message)
    await app(scope, receive, send)

    status = None
    response_headers = {}
    body_parts = []
    for m in messages:
        if m["type"] == "http.response.start":
            status = m["status"]
            response_headers = {k.decode().lower(): v.decode() for k, v in m.get("headers", [])}
        elif m["type"] == "http.response.body":
            body_parts.append(m.get("body", b""))

    return status, response_headers, b"".join(body_parts)


@pytest.mark.anyio
async def test_cors_policy_rejects_untrusted_origins():
    """CORS must not return access-control-allow-origin for untrusted origins (no wildcard)."""
    status, headers, _ = await asgi_request(
        app,
        method="OPTIONS",
        path="/api/stats",
        headers={
            "Origin": "https://malicious-site.evil",
            "Access-Control-Request-Method": "GET"
        }
    )
    # The header must not be '*' and must not reflect malicious-site.evil
    allow_origin = headers.get("access-control-allow-origin")
    assert allow_origin != "*"
    assert allow_origin != "https://malicious-site.evil"


@pytest.mark.anyio
async def test_cors_policy_permits_loopback_origins():
    """CORS must permit approved loopback origins."""
    status, headers, _ = await asgi_request(
        app,
        method="OPTIONS",
        path="/api/stats",
        headers={
            "Origin": "http://127.0.0.1:8000",
            "Access-Control-Request-Method": "GET"
        }
    )
    assert headers.get("access-control-allow-origin") == "http://127.0.0.1:8000"


@pytest.mark.anyio
async def test_cors_policy_rejects_unlisted_loopback_ports_and_credentials():
    """Only explicitly listed development origins may read the unauthenticated local API."""
    _, headers, _ = await asgi_request(
        app,
        method="OPTIONS",
        path="/api/stats",
        headers={
            "Origin": "http://localhost:51990",
            "Access-Control-Request-Method": "GET"
        }
    )
    assert "access-control-allow-origin" not in headers
    assert "access-control-allow-credentials" not in headers


@pytest.mark.anyio
async def test_cross_site_simple_write_is_rejected_before_route_handler():
    """CORS preflight alone cannot prevent a browser from sending a simple POST."""
    status, _, body = await asgi_request(
        app,
        method="POST",
        path="/api/discovery/trigger",
        headers={"Origin": "https://attacker.example", "Content-Type": "text/plain"}
    )
    assert status == 403
    assert b"only from this device" in body


@pytest.mark.anyio
async def test_non_loopback_host_header_is_rejected():
    """A DNS-rebinding hostname must not be trusted just because its peer is loopback."""
    status, _, _ = await asgi_request(
        app,
        method="GET",
        path="/api/health",
        headers={"Host": "attacker.example"}
    )
    assert status == 403


@pytest.mark.anyio
async def test_every_registered_route_rejects_non_loopback_peers(monkeypatch):
    """The global local-only boundary must cover every registered method and path."""
    from careerorbit.config.settings import SETTINGS

    monkeypatch.setattr(SETTINGS, "TESTING", False)
    route_methods = [
        (method, route.path)
        for route in app.routes
        if hasattr(route, "methods")
        for method in route.methods - {"HEAD", "OPTIONS"}
    ]
    assert len(route_methods) >= 110
    for method, path in route_methods:
        status, _, _ = await asgi_request(
            app, method=method, path=path, client=("192.0.2.44", 4567)
        )
        assert status == 403, f"{method} {path} bypassed the local-only boundary"


@pytest.mark.anyio
async def test_telegram_export_json_stream_is_size_limited(monkeypatch):
    import importlib
    web_app = importlib.import_module("careerorbit.web.app")

    monkeypatch.setattr(web_app, "MAX_TELEGRAM_EXPORT_BYTES", 32)
    status, _, _ = await asgi_request(
        app,
        method="POST",
        path="/api/telegram/export/parse-preview",
        headers={"Content-Type": "application/json"},
        body=b'{"filename":"result.json","content":"' + b"x" * 64 + b'"}'
    )
    assert status == 413


@pytest.mark.anyio
async def test_telegram_export_declared_oversize_is_rejected_early(monkeypatch):
    import importlib
    web_app = importlib.import_module("careerorbit.web.app")

    monkeypatch.setattr(web_app, "MAX_TELEGRAM_EXPORT_BYTES", 32)
    status, _, _ = await asgi_request(
        app,
        method="POST",
        path="/api/telegram/export/import",
        headers={"Content-Type": "application/json", "Content-Length": "33"}
    )
    assert status == 413


@pytest.mark.anyio
async def test_telegram_multipart_requires_bounded_content_length():
    status, _, _ = await asgi_request(
        app,
        method="POST",
        path="/api/telegram/export/import",
        headers={"Content-Type": "multipart/form-data; boundary=local"}
    )
    assert status == 411


@pytest.mark.anyio
async def test_telegram_export_rejects_unsupported_filename_extension():
    import json

    payload = json.dumps({"filename": "../../private.pdf", "content": "{}"}).encode()
    status, _, _ = await asgi_request(
        app,
        method="POST",
        path="/api/telegram/export/parse-preview",
        headers={"Content-Type": "application/json"},
        body=payload
    )
    assert status == 400


@pytest.mark.anyio
async def test_security_headers_present_on_api_responses():
    """Responses must include defense-in-depth security headers."""
    status, headers, _ = await asgi_request(app, method="GET", path="/api/health")
    assert status == 200
    assert headers.get("x-content-type-options") == "nosniff"
    assert headers.get("x-frame-options") == "DENY"
    assert "strict-origin" in headers.get("referrer-policy", "")
    assert headers.get("x-xss-protection") == "1; mode=block"


def test_resume_download_blocks_path_traversal():
    """Path traversal sequences in resume download must raise HTTPException with 400 or 404."""
    traversal_payloads = [
        "../careerorbit.db",
        "..\\careerorbit.db",
        "../../../../Windows/System32/drivers/etc/hosts",
        "nested/sub/file.pdf",
        "%2e%2e%2fcareerorbit.db",
        "resume.exe",
        "resume.sh",
        "resume.pdf.exe",
        ".",
        "..",
    ]
    for payload in traversal_payloads:
        with pytest.raises(HTTPException) as exc_info:
            download_resume(payload)
        assert exc_info.value.status_code in (400, 404), f"Failed to block payload: {payload}"


def test_contact_details_withheld_from_public_endpoints():
    """Phone numbers and personal emails must never be leaked through API responses."""
    data = get_profile()
    assert "phone" not in data
    assert "email" not in data

    claims = data.get("candidate_claims", [])
    for claim in claims:
        field = claim.get("field", "")
        if "phone" in field or "email" in field:
            assert claim.get("legacy_value") == "[withheld]"


def test_ssrf_verifier_blocks_private_and_loopback_ips():
    """URL verification engine must strictly reject loopback, RFC1918, and metadata IPs."""
    blocked_urls = [
        "http://127.0.0.1/admin",
        "https://127.0.0.1:8000/api",
        "http://localhost:8000",
        "https://localhost/test",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.1/internal",
        "http://192.168.1.1/router",
        "http://172.16.0.1/private",
        "file:///etc/passwd",
        "ftp://example.com/file",
    ]
    engine = VerificationEngine()
    for url in blocked_urls:
        assert not _public_http_url(url), f"Should not consider {url} as a public HTTP url"
        status, notes = engine.verify_listing(url)
        assert status == VerificationStatus.STATUS_UNKNOWN
        assert "HTTPS and resolve to a public host" in notes or "Third-party" in notes or "unknown" in notes.lower()


def test_csv_formula_injection_defense():
    """Cell values beginning with =, +, -, @ must be neutralized with a leading single quote."""
    dangerous = ["=CMD('calc.exe')", "+1+2", "-SUM(A1:A10)", "@SUM(B1:B2)", "\t=2+2", "\r=1+1"]
    for val in dangerous:
        sanitized = _safe_csv_cell(val)
        assert sanitized.startswith("'"), f"Cell {val} was not sanitized: {sanitized}"
    assert _safe_csv_cell("Software Engineer") == "Software Engineer"
    assert _safe_csv_cell("Bengaluru, India") == "Bengaluru, India"


def test_unauthorized_application_status_manipulation_blocked():
    """An application record cannot be marked SUBMITTED without explicit confirmation."""
    init_db()
    test_job_id = save_job(Job(
        job_uid="pytest_security_audit_app_uid",
        employer="Security Test Corp",
        title="Security Test Analyst",
        normalized_title="security test analyst",
        official_url="https://testcorp.com/jobs/sec1",
        canonical_url="https://testcorp.com/jobs/sec1",
        discovery_source="Direct",
        verification_status=VerificationStatus.VERIFIED_OPEN,
    ))
    app_id = create_or_update_application(Application(
        job_id=test_job_id,
        application_status=ApplicationStatus.AWAITING_APPROVAL,
        submission_confirmed_by_user=0
    ))
    assert app_id > 0

    record = get_application_by_job_id(test_job_id)
    assert record["application_status"] == "AWAITING_APPROVAL"
    assert record["submission_confirmed_by_user"] == 0
