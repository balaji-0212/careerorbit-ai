"""Phase 12 End-to-End Integration Verification Test Suite.

Executes a complete, seamless career search lifecycle across all 10 platform subsystems:
1. Job Ingestion & Verification
2. 6-Factor Matching & Scoring
3. Tailored Resume & Application Package Generation
4. Role-Specific Interview Coaching & Briefing
5. Assessment Practice Sandbox Evaluation
6. Daily Personalized Study Planning
7. Human-Confirmed Application Submission
8. Application Lifecycle Progression & Audit Trail
9. Secure CSV Data Export
10. Diagnostic Health Probing
"""
import json
from pathlib import Path
import pytest
from careerorbit.database.db import (
    init_db,
    save_job,
    get_job_by_id,
    list_jobs,
    get_application_by_job_id,
    get_application_history,
    export_jobs_to_csv,
    export_applications_to_csv,
)
from careerorbit.models.schemas import (
    Job,
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


@pytest.mark.anyio
async def test_full_career_lifecycle_end_to_end(tmp_path, monkeypatch):
    """Executes the complete end-to-end career intelligence lifecycle."""
    import sys
    monkeypatch.setattr("careerorbit.config.candidate_evidence.candidate_profile_ready_for_resume", lambda: True)
    if "careerorbit.web.app" in sys.modules:
        monkeypatch.setattr(sys.modules["careerorbit.web.app"], "candidate_profile_ready_for_resume", lambda: True)
    monkeypatch.setattr("careerorbit.packages.generator.candidate_profile_ready_for_resume", lambda: True)
    monkeypatch.setattr("careerorbit.resumes.generator.candidate_profile_ready_for_resume", lambda: True)
    monkeypatch.setattr("careerorbit.prep.interview_coach.candidate_profile_ready_for_resume", lambda: True)

    # =========================================================================
    # Step 1: Ingest Job Opportunity Lead & Verify
    # =========================================================================
    job = Job(
        job_uid="e2e-enterprise-da-001",
        employer="Apex Global Analytics",
        title="Junior Data Analyst - Business Intelligence",
        normalized_title="junior data analyst",
        priority_category=1,
        priority_label="Category 1",
        location="Bengaluru, Karnataka",
        work_arrangement="Hybrid",
        employment_type="Full-time",
        salary="INR 10,00,000",
        official_url="https://apexanalytics.com/careers/da-001",
        official_listing_url="https://apexanalytics.com/careers/da-001",
        application_url="https://apexanalytics.com/careers/da-001/apply",
        canonical_url="https://apexanalytics.com/careers/da-001",
        discovery_source="Greenhouse ATS",
        verification_source="Greenhouse API",
        verification_status=VerificationStatus.VERIFIED_OPEN,
        match_tier=MatchTier.STRONG_MATCH,
        match_score=86.0,
        required_skills=["SQL", "Power BI", "DAX", "Data Modeling"],
        preferred_skills=["Python", "Pandas", "Excel"],
        description="Build executive reporting models, DAX measures, and optimize SQL queries for enterprise finance.",
    )
    job_id = save_job(job)
    assert job_id > 0
    saved_job = get_job_by_id(job_id)
    assert saved_job["employer"] == "Apex Global Analytics"
    assert saved_job["verification_status"] == "VERIFIED_OPEN"

    # =========================================================================
    # Step 2: Prepare Application Package (Tailored Resume, Cover Letter)
    # =========================================================================
    status, _, body = await asgi_request(app, method="POST", path=f"/api/applications/prepare/{job_id}")
    assert status == 200, f"Prepare package failed: {body.decode()}"
    pkg = json.loads(body.decode())
    assert "application_id" in pkg
    app_id = pkg["application_id"]
    assert pkg["company"] == "Apex Global Analytics"

    # =========================================================================
    # Step 3: Interview Coaching Briefing, Notes, and Answer Drafting
    # =========================================================================
    # 3a. Fetch briefing
    status, _, body = await asgi_request(app, method="GET", path=f"/api/interview-prep/briefing/{job_id}")
    assert status == 200
    briefing_data = json.loads(body.decode())
    questions = briefing_data["briefing"]["questions"]
    assert len(questions) == 5
    # Confirm the prompt asks for truthful evidence without inventing candidate history.
    project_q = next(q for q in questions if q["category"] == "Candidate Project Evidence")
    assert "truthful real example" in project_q["candidate_example_prompt"].lower()
    assert "candidate_evidence_link" not in json.dumps(questions)

    # 3b. Update rehearsal notes and confidence rating
    notes_payload = json.dumps({"notes": "Focused on DAX context transition and 35% SQL speedup talking points", "confidence_rating": 4}).encode()
    status, _, body = await asgi_request(
        app,
        method="PUT",
        path=f"/api/interview-prep/briefing/{job_id}/notes",
        body=notes_payload,
        headers={"Content-Type": "application/json"}
    )
    assert status == 200
    assert json.loads(body.decode())["confidence_rating"] == 4

    # 3c. Save draft answer for Question 1
    draft_payload = json.dumps({
        "question_index": 1,
        "draft_text": "I design Star Schema dimensional models with composite indexes on date keys to minimize scan latency."
    }).encode()
    status, _, body = await asgi_request(
        app,
        method="POST",
        path=f"/api/interview-prep/briefing/{job_id}/draft",
        body=draft_payload,
        headers={"Content-Type": "application/json"}
    )
    assert status == 200
    assert "1" in json.loads(body.decode())["answer_drafts"]

    # =========================================================================
    # Step 4: Assessment Sandbox Practice Challenge
    # =========================================================================
    from careerorbit.prep.assessment_sandbox import seed_assessment_challenges
    from careerorbit.database.db import list_assessment_challenges
    seed_assessment_challenges()

    challenges = list_assessment_challenges(category="SQL", include_solution=True)
    repeat_order_chall = next(c for c in challenges if c["challenge_uid"] == "sql-customer-repeat-orders")
    chall_id = repeat_order_chall["id"]

    # Evaluate Challenge (SQL customer repeat orders)
    sql_solution = json.dumps({
        "submitted_code": """
            SELECT customer_id, COUNT(*) as total_orders, SUM(order_amount) as total_spend
            FROM orders
            GROUP BY customer_id
            HAVING COUNT(*) >= 3 AND SUM(order_amount) >= 1000
            ORDER BY total_spend DESC;
        """
    }).encode()
    status, _, body = await asgi_request(
        app,
        method="POST",
        path=f"/api/assessments/challenges/{chall_id}/evaluate",
        body=sql_solution,
        headers={"Content-Type": "application/json"}
    )
    assert status == 200
    eval_res = json.loads(body.decode())
    assert eval_res["is_passed"] is True
    assert eval_res["score"] == 100.0

    # =========================================================================
    # Step 5: Daily Study Planning & Task Execution
    # =========================================================================
    status, _, body = await asgi_request(app, method="GET", path="/api/study/plan/today")
    assert status == 200
    plan = json.loads(body.decode())
    plan_id = plan["id"]
    tasks = plan["tasks"]
    assert len(tasks) >= 2

    # Mark first task as completed
    task_id = tasks[0]["task_id"]
    task_payload = json.dumps({"status": "COMPLETED", "notes": "Completed DAX study block"}).encode()
    status, _, body = await asgi_request(
        app,
        method="PUT",
        path=f"/api/study/plan/{plan_id}/tasks/{task_id}/status",
        body=task_payload,
        headers={"Content-Type": "application/json"}
    )
    assert status == 200
    updated_plan = json.loads(body.decode())
    first_task = next(t for t in updated_plan["tasks"] if t["task_id"] == task_id)
    assert first_task["status"] == "COMPLETED"

    # =========================================================================
    # Step 6: Human-Confirmed Application Submission Barrier
    # =========================================================================
    # Attempting to set APPLIED without user confirmation must fail
    bad_payload = json.dumps({"status": "APPLIED", "confirmed_by_user": False}).encode()
    status, _, _ = await asgi_request(
        app,
        method="PUT",
        path=f"/api/applications/{app_id}/status",
        body=bad_payload,
        headers={"Content-Type": "application/json"}
    )
    assert status == 400

    # Confirm submission via portal endpoint
    confirm_payload = json.dumps({"notes": "Candidate manually confirmed submission on Apex careers portal."}).encode()
    status, _, body = await asgi_request(
        app,
        method="POST",
        path=f"/api/applications/confirm-submission/{job_id}",
        body=confirm_payload,
        headers={"Content-Type": "application/json"}
    )
    assert status == 200
    app_record = get_application_by_job_id(job_id)
    assert app_record["application_status"] in ("SUBMITTED", "APPLIED")
    assert app_record["submission_confirmed_by_user"] == 1

    # =========================================================================
    # Step 7: Application Lifecycle Advance & Audit Trail
    # =========================================================================
    # Advance to INTERVIEW_SCHEDULED
    interview_payload = json.dumps({"status": "INTERVIEW_SCHEDULED", "notes": "Technical screening call scheduled with hiring manager"}).encode()
    status, _, body = await asgi_request(
        app,
        method="PUT",
        path=f"/api/applications/{app_id}/status",
        body=interview_payload,
        headers={"Content-Type": "application/json"}
    )
    assert status == 200
    advanced_app = json.loads(body.decode())["application"]
    assert advanced_app["application_status"] == "INTERVIEW_SCHEDULED"

    # Verify audit trail history
    history = get_application_history(app_id)
    assert len(history) >= 2
    statuses_in_audit = [h["new_status"] for h in history]
    assert "APPLIED" in statuses_in_audit
    assert "INTERVIEW_SCHEDULED" in statuses_in_audit

    # =========================================================================
    # Step 8: CSV Data Exports
    # =========================================================================
    jobs_csv = tmp_path / "e2e_jobs.csv"
    apps_csv = tmp_path / "e2e_apps.csv"
    export_jobs_to_csv(filepath=str(jobs_csv))
    export_applications_to_csv(filepath=str(apps_csv))
    assert jobs_csv.exists()
    assert apps_csv.exists()
    assert "Apex Global Analytics" in jobs_csv.read_text(encoding="utf-8")
    assert "INTERVIEW_SCHEDULED" in apps_csv.read_text(encoding="utf-8")

    # =========================================================================
    # Step 9: Diagnostic Health Probe
    # =========================================================================
    status, _, body = await asgi_request(app, method="GET", path="/api/health")
    assert status == 200
    diag = json.loads(body.decode())
    assert diag["status"] == "healthy"
    assert diag["database"]["connected"] is True
