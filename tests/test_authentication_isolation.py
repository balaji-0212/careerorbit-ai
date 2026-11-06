"""Regression coverage for authentication, CSRF, logout, and tenant storage."""
import json
from pathlib import Path

import pytest

from careerorbit.auth.store import account_data_dir, get_user, register_user
from careerorbit.config.settings import account_storage_context
from careerorbit.config.profile import candidate_profile_context
from careerorbit.database.db import (
    get_connection, create_interview_prep_workspace, get_interview_prep_workspace, list_jobs,
    save_job, create_or_update_application, save_resume_metadata, save_inbox_message,
)
from careerorbit.models.schemas import Application, Job, ResumeMetadata
from careerorbit.web.app import app, get_telegram_status, trigger_telegram_poll
from careerorbit.database.db import init_db


@pytest.fixture(autouse=True)
def initialize_application_database():
    init_db()


async def request(method: str, path: str, *, headers: dict | None = None, body: bytes = b""):
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": method, "scheme": "http", "path": path, "raw_path": path.encode(),
        "query_string": b"", "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "server": ("127.0.0.1", 8000), "client": ("127.0.0.1", 43210),
    }
    messages = []
    request_sent = False
    async def receive():
        nonlocal request_sent
        if not request_sent:
            request_sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}
    async def send(message):
        messages.append(message)
    await app(scope, receive, send)
    start = next(message for message in messages if message["type"] == "http.response.start")
    chunks = [message.get("body", b"") for message in messages if message["type"] == "http.response.body"]
    response_headers = {}
    for key, value in start["headers"]:
        name = key.decode().lower()
        decoded = value.decode()
        if name == "set-cookie":
            response_headers.setdefault(name, []).append(decoded)
        else:
            response_headers[name] = decoded
    return start["status"], response_headers, b"".join(chunks)


@pytest.mark.anyio
async def test_private_api_rejects_anonymous_requests():
    for path in ("/api/jobs", "/api/health"):
        status, _, body = await request("GET", path)
        assert status == 401
        assert json.loads(body)["detail"] == "Authentication required."


@pytest.mark.anyio
async def test_rejected_candidate_field_edit_does_not_mutate_account_profile():
    """The authenticated API must not persist a field when evidence validation rejects the edit."""
    from careerorbit.config.profile import CANDIDATE_PROFILE
    from careerorbit.config.settings import current_data_dir

    original = CANDIDATE_PROFILE["personal"]["notice_period_status"]
    headers = {
        "cookie": "careerorbit_session=test-session-token; careerorbit_csrf=test-csrf-token",
        "x-csrf-token": "test-csrf-token",
        "content-type": "application/json",
    }
    status, _, body = await request(
        "POST", "/api/profile/field", headers=headers,
        body=json.dumps({
            "field": "personal.notice_period_status",
            "value": "must not persist",
            "state": "NOT_PROVIDED",
        }).encode(),
    )

    assert status == 400
    assert "cannot be marked not provided" in json.loads(body)["detail"]
    assert CANDIDATE_PROFILE["personal"]["notice_period_status"] == original
    assert not (current_data_dir() / "candidate_profile_overrides.json").exists()


@pytest.mark.anyio
async def test_expired_session_is_rejected():
    import sqlite3
    from careerorbit.config.settings import SETTINGS
    with sqlite3.connect(SETTINGS.DATA_DIR / "auth.db") as conn:
        conn.execute(
            "UPDATE sessions SET expires_at='2000-01-01T00:00:00+00:00' WHERE user_id='test-user'"
        )
    status, _, _ = await request(
        "GET", "/api/jobs",
        headers={"cookie": "careerorbit_session=test-session-token; careerorbit_csrf=test-csrf-token"},
    )
    assert status == 401


def test_role_workspace_migration_is_idempotent():
    init_db()
    init_db()
    with get_connection() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version='2026-10-26-role-interview-workspaces-v1'"
        ).fetchone()[0]
        table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='interview_prep_workspaces'"
        ).fetchone()
    assert count == 1
    assert table is not None


@pytest.mark.anyio
async def test_registration_login_csrf_and_logout_lifecycle():
    payload = json.dumps({
        "email": "new.account@example.test",
        "password": "long-enough-test-password",
        "display_name": "New Account",
    }).encode()
    status, headers, body = await request(
        "POST", "/api/auth/register", headers={"content-type": "application/json"}, body=payload
    )
    assert status == 200, body.decode()
    assert json.loads(body)["user"]["email"] == "new.account@example.test"
    cookie_headers = headers["set-cookie"]
    session_cookie = next(value.split(";", 1)[0] for value in cookie_headers if value.startswith("careerorbit_session="))
    csrf_cookie = next(value.split(";", 1)[0] for value in cookie_headers if value.startswith("careerorbit_csrf="))
    session_token = session_cookie.split("=", 1)[1]
    csrf_token = csrf_cookie.split("=", 1)[1]
    cookies = f"{session_cookie}; {csrf_cookie}"

    status, _, body = await request("GET", "/api/auth/me", headers={"cookie": cookies})
    assert status == 200
    assert json.loads(body)["user"]["email"] == "new.account@example.test"

    status, _, _ = await request("POST", "/api/auth/logout", headers={"cookie": cookies})
    assert status == 403
    status, _, _ = await request(
        "POST", "/api/auth/logout", headers={"cookie": cookies, "x-csrf-token": csrf_token}
    )
    assert status == 200
    status, _, _ = await request("GET", "/api/auth/me", headers={"cookie": f"careerorbit_session={session_token}"})
    assert status == 401

    status, headers, _ = await request(
        "POST", "/api/auth/login", headers={"content-type": "application/json"}, body=payload
    )
    assert status == 200
    assert any(value.startswith("careerorbit_session=") for value in headers["set-cookie"])


@pytest.mark.anyio
async def test_role_only_interview_prep_persists_without_candidate_review():
    payload = json.dumps({"role_title": "Data Analyst"}).encode()
    headers = {
        "content-type": "application/json",
        "cookie": "careerorbit_session=test-session-token; careerorbit_csrf=test-csrf-token",
        "x-csrf-token": "test-csrf-token",
    }
    status, _, body = await request("POST", "/api/interview-prep/role-workspaces", headers=headers, body=payload)
    assert status == 200, body.decode()
    workspace = json.loads(body)
    assert workspace["role_title"] == "Data Analyst"
    assert workspace["source_type"] == "ROLE"
    assert len(workspace["briefing"]["questions"]) == 5
    assert "No resume" in workspace["briefing"]["summary"]
    assert "SQL" in workspace["briefing"]["questions"][1]["question"]
    assert workspace["briefing"]["questions"][1]["difficulty"] == "Intermediate"

    update = json.dumps({
        "candidate_notes": "Practice the SQL question.",
        "confidence_rating": 3,
        "answer_drafts": {"1": "I would first clarify the metric definition."},
    }).encode()
    status, _, body = await request(
        "PUT", f"/api/interview-prep/role-workspaces/{workspace['workspace_id']}",
        headers=headers, body=update,
    )
    assert status == 200, body.decode()
    saved = json.loads(body)
    assert saved["candidate_notes"] == "Practice the SQL question."
    assert saved["confidence_rating"] == 3
    assert saved["answer_drafts"]["1"].startswith("I would first")


@pytest.mark.anyio
async def test_application_tracker_starts_role_practice_from_saved_application():
    job_id = save_job(Job(
        job_uid="synthetic-application-interview",
        employer="Synthetic Analytics",
        title="Junior Data Analyst",
        normalized_title="junior data analyst",
        priority_category=1,
        priority_label="Data Analyst",
        location="Chennai",
        work_arrangement="Hybrid",
        official_url="https://example.test/careers/analyst",
        official_listing_url="https://example.test/careers/analyst",
        application_url="https://example.test/careers/analyst/apply",
        canonical_url="https://example.test/careers/analyst",
        discovery_source="Synthetic test fixture",
        match_tier="Ineligible",
        description="Use SQL, Excel, and Power BI to build accurate dashboards.",
    ))
    application_id = create_or_update_application(Application(job_id=job_id))
    headers = {
        "cookie": "careerorbit_session=test-session-token; careerorbit_csrf=test-csrf-token",
        "x-csrf-token": "test-csrf-token",
    }
    status, _, body = await request(
        "POST", f"/api/interview-prep/from-application/{application_id}", headers=headers,
    )
    assert status == 200, body.decode()
    workspace = json.loads(body)
    assert workspace["role_title"] == "Junior Data Analyst"
    assert "SQL, Excel, and Power BI" in workspace["job_description"]
    assert workspace["briefing"]["application_context"]["application_id"] == application_id
    assert workspace["briefing"]["application_context"]["employer"] == "Synthetic Analytics"
    assert len(workspace["briefing"]["questions"]) == 5
    technical_question = workspace["briefing"]["questions"][1]
    assert any(
        "job-description context" in area and "Power" in area and "SQL" in area
        for area in technical_question["focus_areas"]
    )
    assert get_interview_prep_workspace(workspace["workspace_id"])["role_title"] == "Junior Data Analyst"


def test_role_question_bank_uses_role_family_without_candidate_facts():
    from careerorbit.prep.interview_coach import InterviewCoach
    analyst = InterviewCoach.create_role_workspace("Junior Data Analyst")
    developer = InterviewCoach.create_role_workspace("Python Developer")
    scientist = InterviewCoach.create_role_workspace("Data Scientist")
    assert "SQL" in analyst["briefing"]["questions"][1]["question"]
    assert "API" in developer["briefing"]["questions"][1]["question"]
    assert "model" in scientist["briefing"]["questions"][1]["question"].lower()
    assert "Candidate examples must be supplied and verified by you" in analyst["disclaimer"]


@pytest.mark.anyio
async def test_custom_career_role_preferences_persist_and_affect_discovery_rank():
    from careerorbit.career_priorities import get_preference_rank
    headers = {
        "cookie": "careerorbit_session=test-session-token; careerorbit_csrf=test-csrf-token",
        "x-csrf-token": "test-csrf-token",
        "content-type": "application/json",
    }
    role_id = "custom:Junior%20Data%20Analyst"
    status, _, body = await request(
        "POST", "/api/profile/preferences", headers=headers,
        body=json.dumps({"profile_id": "default", "selected_categories": [role_id]}).encode(),
    )
    assert status == 200, body.decode()
    status, _, body = await request("GET", "/api/profile/preferences", headers={
        "cookie": "careerorbit_session=test-session-token; careerorbit_csrf=test-csrf-token",
    })
    assert status == 200
    preferences = json.loads(body)
    assert preferences["selected_categories"] == [role_id]
    role = next(item for item in preferences["available_categories"] if item["id"] == role_id)
    assert role["label"] == "Junior Data Analyst"
    assert get_preference_rank(
        {"title": "Junior Data Analyst", "priority_category": 1},
        preferences=preferences["selected_categories"],
    ) == 1
    save_job(Job(
        job_uid="custom-role-rank-analyst", employer="Synthetic A", title="Junior Data Analyst",
        normalized_title="junior data analyst", priority_category=1, priority_label="Data Analyst",
        location="Chennai", work_arrangement="Hybrid", official_url="https://a.example.test/job",
        canonical_url="https://a.example.test/job", discovery_source="Synthetic ranking test",
        match_score=80, match_tier="Ineligible",
    ))
    save_job(Job(
        job_uid="custom-role-rank-engineer", employer="Synthetic B", title="Associate Software Engineer",
        normalized_title="associate software engineer", priority_category=3, priority_label="Software Engineer",
        location="Chennai", work_arrangement="Hybrid", official_url="https://b.example.test/job",
        canonical_url="https://b.example.test/job", discovery_source="Synthetic ranking test",
        match_score=80, match_tier="Ineligible",
    ))
    ordered_jobs = list_jobs(profile_id="default", sort_by="priority_first")
    ranked = [job for job in ordered_jobs if job["job_uid"].startswith("custom-role-rank-")]
    assert [job["title"] for job in ranked] == ["Junior Data Analyst", "Associate Software Engineer"]
    assert ranked[0]["preference_rank"] == 1


def test_account_storage_roots_and_database_contents_are_isolated():
    first, _, _ = register_user("isolation.one@example.test", "first-test-password-long", "First")
    second, _, _ = register_user("isolation.two@example.test", "second-test-password-long", "Second")
    first_root = account_data_dir(first)
    second_root = account_data_dir(second)
    assert first_root != second_root
    assert first_root != Path(second_root)

    with account_storage_context(first_root):
        workspace = create_interview_prep_workspace({
            "source_type": "ROLE", "role_title": "Test Engineer",
            "briefing": {"summary": "Synthetic role practice."}, "checklist": [],
            "disclaimer": "Test only.",
        })
        with get_connection() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS isolation_marker(value TEXT NOT NULL)")
            conn.execute("INSERT INTO isolation_marker(value) VALUES('first-only')")
    with account_storage_context(second_root):
        assert get_interview_prep_workspace(workspace["workspace_id"]) is None
        telegram = get_telegram_status()
        assert telegram["status"] == "ACCOUNT_SCOPED_UNAVAILABLE"
        assert telegram["configured"] is False
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as telegram_error:
            trigger_telegram_poll()
        assert telegram_error.value.status_code == 403
        with get_connection() as conn:
            found = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='isolation_marker'"
            ).fetchone()
            assert found is None


@pytest.mark.anyio
async def test_private_records_are_isolated_between_authenticated_accounts():
    """Exercise tenant isolation through real API middleware and record IDs."""
    first = get_user("test-user")
    assert first is not None
    second, second_session, second_csrf = register_user(
        "api.isolation.two@example.test", "second-account-password-long", "Second account"
    )
    first_headers = {
        "cookie": "careerorbit_session=test-session-token; careerorbit_csrf=test-csrf-token",
        "x-csrf-token": "test-csrf-token",
        "content-type": "application/json",
    }
    second_headers = {
        "cookie": f"careerorbit_session={second_session}; careerorbit_csrf={second_csrf}",
        "x-csrf-token": second_csrf,
        "content-type": "application/json",
    }

    # Create a private role-practice record through account one's API session.
    status, _, body = await request(
        "POST", "/api/interview-prep/role-workspaces", headers=first_headers,
        body=json.dumps({"role_title": "Synthetic Tenant Analyst"}).encode(),
    )
    assert status == 200, body.decode()
    workspace_id = json.loads(body)["workspace_id"]

    # Seed job and application data only in account one's isolated store.
    with account_storage_context(account_data_dir(first)), candidate_profile_context(account_data_dir(first)):
        job_id = save_job(Job(
            job_uid="cross-account-private-job", employer="Synthetic Tenant Corp",
            title="Synthetic Tenant Analyst", normalized_title="synthetic tenant analyst",
            priority_category=1, priority_label="Analyst", location="Remote",
            work_arrangement="Remote", official_url="https://example.test/private-job",
            canonical_url="https://example.test/private-job", discovery_source="Synthetic isolation test",
        ))
        application_id = create_or_update_application(Application(job_id=job_id))
        resume_id = save_resume_metadata(ResumeMetadata(
            job_id=job_id, company_name="Synthetic Tenant Corp", role_title="Synthetic Tenant Analyst",
            source_resume_type="synthetic-test", pdf_filename="tenant-private.pdf",
            pdf_path="tenant-private.pdf", docx_filename="tenant-private.docx",
            docx_path="tenant-private.docx", tailoring_summary="Synthetic tenant isolation fixture.",
        ))
        (account_data_dir(first) / "resumes" / "tenant-private.pdf").write_bytes(b"synthetic test document")
        inbox_id = save_inbox_message({
            "message_uid": "cross-account-private-inbox", "channel": "synthetic-test",
            "chat_id": "test", "message_id": 991, "raw_text": "Private synthetic account message",
            "classification": "Other Career Resources", "category_group": "other",
        })

    # Profile and preferences also use account-specific persistence roots.
    status, _, body = await request(
        "POST", "/api/profile/field", headers=first_headers,
        body=json.dumps({
            "field": "personal.location", "value": "Synthetic Tenant One",
            "state": "CONFIRMED", "note": "Synthetic isolation fixture",
        }).encode(),
    )
    assert status == 200, body.decode()
    private_preference = "custom:Tenant%20One%20Analyst"
    status, _, body = await request(
        "POST", "/api/profile/preferences", headers=first_headers,
        body=json.dumps({"profile_id": "default", "selected_categories": [private_preference]}).encode(),
    )
    assert status == 200, body.decode()

    # Account one sees its own records; account two cannot list or fetch them by ID.
    status, _, body = await request("GET", "/api/jobs", headers=first_headers)
    assert status == 200
    assert any(row["id"] == job_id for row in json.loads(body)["jobs"])
    status, _, body = await request("GET", "/api/applications", headers=first_headers)
    assert status == 200
    assert any(row["id"] == application_id for row in json.loads(body)["applications"])
    status, _, body = await request("GET", f"/api/interview-prep/role-workspaces/{workspace_id}", headers=first_headers)
    assert status == 200, body.decode()
    status, _, body = await request("GET", "/api/resumes", headers=first_headers)
    assert status == 200
    assert any(row["id"] == resume_id for row in json.loads(body)["resumes"])
    status, _, body = await request("GET", f"/api/resumes/download/tenant-private.pdf", headers=first_headers)
    assert status == 200
    status, _, body = await request("GET", f"/api/inbox/{inbox_id}", headers=first_headers)
    assert status == 200
    assert json.loads(body)["raw_text"] == "Private synthetic account message"
    status, _, body = await request("GET", "/api/profile", headers=first_headers)
    assert status == 200
    first_claims = {row["field"]: row["legacy_value"] for row in json.loads(body)["candidate_claims"]}
    assert first_claims["personal.location"] == "Synthetic Tenant One"

    status, _, body = await request("GET", "/api/jobs", headers=second_headers)
    assert status == 200
    assert all(row["id"] != job_id for row in json.loads(body)["jobs"])
    status, _, body = await request("GET", "/api/jobs/" + str(job_id), headers=second_headers)
    assert status == 404
    status, _, body = await request("GET", "/api/applications", headers=second_headers)
    assert status == 200
    assert all(row["id"] != application_id for row in json.loads(body)["applications"])
    status, _, body = await request("GET", "/api/resumes", headers=second_headers)
    assert status == 200
    assert all(row["id"] != resume_id for row in json.loads(body)["resumes"])
    status, _, body = await request("GET", "/api/resumes/download/tenant-private.pdf", headers=second_headers)
    assert status == 404
    status, _, body = await request("GET", "/api/inbox", headers=second_headers)
    assert status == 200
    assert all(row["id"] != inbox_id for row in json.loads(body)["items"])
    status, _, body = await request("GET", f"/api/inbox/{inbox_id}", headers=second_headers)
    assert status == 404
    status, _, body = await request(
        "PUT", f"/api/inbox/{inbox_id}/status", headers=second_headers,
        body=json.dumps({"status": "ARCHIVED"}).encode(),
    )
    assert status == 404
    status, _, body = await request("GET", f"/api/inbox/{inbox_id}", headers=first_headers)
    assert status == 200
    assert json.loads(body)["status"] == "NEW"
    status, _, body = await request("GET", "/api/profile", headers=second_headers)
    assert status == 200
    second_claims = {row["field"]: row["legacy_value"] for row in json.loads(body)["candidate_claims"]}
    assert second_claims["personal.location"] != "Synthetic Tenant One"
    status, _, body = await request("GET", "/api/profile/preferences", headers=second_headers)
    assert status == 200
    assert private_preference not in json.loads(body)["selected_categories"]

    # Exercise cross-account writes and deletions by guessing account one's record IDs.
    status, _, _ = await request("POST", f"/api/jobs/{job_id}/save", headers=second_headers)
    assert status == 404
    status, _, _ = await request(
        "PUT", f"/api/applications/{application_id}/status", headers=second_headers,
        body=json.dumps({"status": "INTERVIEW_SCHEDULED", "notes": "cross-account attempt"}).encode(),
    )
    assert status == 404
    status, _, _ = await request("DELETE", f"/api/inbox/{inbox_id}", headers=second_headers)
    assert status == 404
    status, _, _ = await request("GET", f"/api/applications/{application_id}/history", headers=second_headers)
    assert status == 404
    status, _, _ = await request("POST", f"/api/interview-prep/from-application/{application_id}", headers=second_headers)
    assert status == 404
    status, _, _ = await request(
        "PUT", f"/api/interview-prep/role-workspaces/{workspace_id}", headers=second_headers,
        body=json.dumps({"candidate_notes": "cross-account attempt"}).encode(),
    )
    assert status == 404
    status, _, _ = await request(
        "POST", "/api/profile/field", headers=second_headers,
        body=json.dumps({
            "field": "personal.location", "value": "Synthetic Tenant Two",
            "state": "CONFIRMED", "note": "Synthetic isolation fixture",
        }).encode(),
    )
    assert status == 200
    second_preference = "custom:Tenant%20Two%20Analyst"
    status, _, body = await request(
        "POST", "/api/profile/preferences", headers=second_headers,
        body=json.dumps({"profile_id": "default", "selected_categories": [second_preference]}).encode(),
    )
    assert status == 200, body.decode()

    status, _, body = await request("GET", "/api/profile", headers=first_headers)
    assert status == 200
    first_after = {row["field"]: row["legacy_value"] for row in json.loads(body)["candidate_claims"]}
    assert first_after["personal.location"] == "Synthetic Tenant One"
    status, _, body = await request("GET", "/api/profile/preferences", headers=first_headers)
    assert status == 200
    assert json.loads(body)["selected_categories"] == [private_preference]

    status, _, body = await request("GET", "/api/applications", headers=first_headers)
    first_application = next(row for row in json.loads(body)["applications"] if row["id"] == application_id)
    assert first_application["application_status"] == "SAVED"
    status, _, body = await request("GET", f"/api/interview-prep/role-workspaces/{workspace_id}", headers=first_headers)
    assert status == 200
    assert json.loads(body)["candidate_notes"] != "cross-account attempt"
    status, _, body = await request("GET", f"/api/interview-prep/role-workspaces/{workspace_id}", headers=second_headers)
    assert status == 404
    status, _, body = await request("GET", "/api/interview-prep/role-workspaces", headers=second_headers)
    assert status == 200
    assert json.loads(body)["workspaces"] == []
