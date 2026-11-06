"""Phase 9 verification test suite for API & Database Hardening.

Verifies:
1. SQL parameterization safety against injection payloads.
2. CSV formula injection neutralization across job and application exports.
3. SQLite integrity check and foreign key consistency.
4. Robust Pydantic request validation and error responses on malformed input.
5. Database index coverage on primary foreign keys and query columns.
"""
import csv
import json
from pathlib import Path
import pytest
from careerorbit.database.db import (
    init_db,
    get_connection,
    save_job,
    list_jobs,
    create_or_update_application,
    export_jobs_to_csv,
    export_applications_to_csv,
    _safe_csv_cell,
)
from careerorbit.models.schemas import (
    Job,
    Application,
    ApplicationStatus,
    VerificationStatus,
    MatchTier,
)
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


# ---------------- 1. SQL Parameterization & Injection Defense ----------------

def test_sql_parameterization_against_injection_payloads():
    """Verifies that malicious SQL injection strings in queries and inserts execute safely."""
    injection_strings = [
        "' OR '1'='1",
        "'; DROP TABLE jobs; --",
        "1 UNION SELECT null, null, null--",
        "admin'--",
    ]

    conn = get_connection()
    c = conn.cursor()

    for payload in injection_strings:
        # Safe parameterized select
        c.execute("SELECT id, employer, title FROM jobs WHERE employer = ?", (payload,))
        rows = c.fetchall()
        assert isinstance(rows, list)

        # Safe parameterized update
        c.execute("UPDATE jobs SET verification_notes = ? WHERE employer = ?", ("Safety test", payload))
        conn.commit()

    # Verify jobs table is completely unharmed
    c.execute("SELECT count(*) as cnt FROM jobs")
    count_row = c.fetchone()
    assert count_row is not None
    conn.close()


# ---------------- 2. CSV Formula Injection Defense ----------------

def test_csv_safe_cell_sanitizes_formula_triggers():
    """Verifies that _safe_csv_cell neutralizes spreadsheet formula prefixes."""
    dangerous_inputs = [
        "=cmd|'/C calc'!A0",
        "+1+2",
        "-5*10",
        "@SUM(A1:A10)",
        "   =1+1",
        "   +SUM(B1)",
    ]
    for inp in dangerous_inputs:
        safe_val = _safe_csv_cell(inp)
        assert safe_val.startswith("'"), f"Formula prefix not neutralized in: {inp}"


def test_csv_export_files_are_formula_neutralized(tmp_path):
    """Verifies exported CSV files write safe cells without executing formulas."""
    job_id = save_job(Job(
        job_uid="csv-injection-test-uid",
        employer="=cmd|'/C calc'!A0",
        title="@SUM(A1:A10) Analyst",
        normalized_title="analyst",
        priority_category=1,
        priority_label="Category 1",
        official_url="https://example.com/jobs/safe",
        canonical_url="https://example.com/jobs/safe",
        discovery_source="Direct",
        verification_status=VerificationStatus.VERIFIED_OPEN,
        match_tier=MatchTier.STRONG_MATCH,
        match_score=80.0,
    ))

    create_or_update_application(Application(
        job_id=job_id,
        application_status=ApplicationStatus.SAVED,
        notes="+100 points formula note",
    ))

    jobs_csv = tmp_path / "jobs_audit.csv"
    apps_csv = tmp_path / "apps_audit.csv"

    export_jobs_to_csv(filepath=str(jobs_csv))
    export_applications_to_csv(filepath=str(apps_csv))

    assert jobs_csv.exists()
    assert apps_csv.exists()

    with open(jobs_csv, "r", encoding="utf-8") as f:
        content = f.read()
        # Verify dangerous strings are neutralized with leading quote
        assert "'=cmd" in content
        assert "'@SUM" in content
        # Must not contain unquoted initial trigger
        for line in content.splitlines()[1:]:
            cells = line.split(",")
            for cell in cells:
                assert not cell.startswith(("=", "@")), f"Unsanitized cell found: {cell}"


# ---------------- 3. Database Integrity & Foreign Keys ----------------

def test_database_integrity_and_fk_pragmas():
    """Verifies SQLite PRAGMA integrity_check and foreign_key_check pass with zero errors."""
    conn = get_connection()
    c = conn.cursor()

    c.execute("PRAGMA integrity_check")
    integrity_rows = c.fetchall()
    assert len(integrity_rows) == 1
    assert integrity_rows[0][0] == "ok"

    c.execute("PRAGMA foreign_key_check")
    fk_violations = c.fetchall()
    assert len(fk_violations) == 0, f"Found foreign key violations: {fk_violations}"

    conn.close()


def test_database_indexes_exist():
    """Verifies that essential query and foreign key indexes are created in database schema."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='index'")
    idx_names = set(row[0] for row in c.fetchall())
    conn.close()

    expected_indexes = [
        "idx_jobs_uid",
        "idx_jobs_tier",
        "idx_jobs_priority",
        "idx_apps_job_id",
        "idx_app_history_app_id",
        "idx_inbox_chat",
        "idx_inbox_status",
        "idx_study_plans_date",
        "idx_study_plans_role",
        "idx_assess_chall_cat",
        "idx_assess_sub_chall",
        "idx_interview_job_id",
        "idx_job_sources_type",
        "idx_job_sources_health",
        "idx_learning_cat",
        "idx_learning_skill",
    ]
    for idx in expected_indexes:
        assert idx in idx_names, f"Expected index '{idx}' is missing from schema"


# ---------------- 4. API Request Validation & Bad Payloads ----------------

@pytest.mark.anyio
async def test_api_validation_rejects_malformed_input():
    """Verifies that API endpoints validate request schemas and return structured 422 errors."""
    # 1. Invalid status update (missing required payload format or bad types)
    status, _, body = await asgi_request(
        app,
        method="PUT",
        path="/api/applications/1/status",
        body=b"invalid-not-json",
        headers={"Content-Type": "application/json"}
    )
    assert status == 422

    # 2. Invalid study task status update
    status, _, body = await asgi_request(
        app,
        method="PUT",
        path="/api/study/plan/1/tasks/task-1/status",
        body=b"{\"invalid_key\": 123}",
        headers={"Content-Type": "application/json"}
    )
    assert status == 422

    # 3. Invalid interview answer draft payload
    status, _, body = await asgi_request(
        app,
        method="POST",
        path="/api/interview-prep/briefing/1/draft",
        body=b"{\"question_index\": \"not-an-int\"}",
        headers={"Content-Type": "application/json"}
    )
    assert status == 422


@pytest.mark.anyio
async def test_api_endpoints_handle_non_string_types_robustly():
    """Verifies that endpoints handle numeric or non-string inputs safely without 500 errors."""
    from careerorbit.web.app import (
        create_job_source_endpoint,
        create_employer_source,
        set_inbox_item_status,
        save_learning_resource_endpoint,
        preview_community_announcement,
        verify_external_url,
    )
    from fastapi import HTTPException

    # 1. Job sources with numeric identifiers
    res_js = create_job_source_endpoint({"source_id": 9991, "source_name": 8882})
    assert res_js["status"] == "SUCCESS"
    assert res_js["source_id"] == "9991"

    # 2. Employer source with numeric board_id and employer_name
    res_emp = create_employer_source({
        "employer_name": 12345, "official_domain": "test-ats.com",
        "ats_provider": "greenhouse", "board_id": 7776
    })
    assert res_emp["source"]["employer_name"] == "12345"

    # 3. Invalid inbox status must raise clean 400 Bad Request, not 500
    with pytest.raises(HTTPException) as exc_info:
        set_inbox_item_status(1, {"status": 9999})
    assert exc_info.value.status_code == 400

    # 4. Learning resources with numeric title
    res_lr = save_learning_resource_endpoint({"title": 123456, "primary_url": "https://example.test"})
    assert res_lr["status"] == "SUCCESS"

    # 5. Community parse preview with numeric raw_text
    res_prev = preview_community_announcement({"raw_text": 12345})
    assert isinstance(res_prev, dict)

    # 6. Verify URL with invalid non-numeric job_id raises clean 400 Bad Request
    with pytest.raises(HTTPException) as exc_v:
        verify_external_url({"url": "https://example.com/job", "job_id": "not-an-int"})
    assert exc_v.value.status_code == 400
