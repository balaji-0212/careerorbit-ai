"""Phase 5 verification test suite for Interview Preparation Coach (Slice 2.4)."""
import json
import pytest
from careerorbit.web.app import app
from careerorbit.prep.interview_coach import InterviewCoach, DISCLAIMER_TEXT
from careerorbit.database.db import (
    init_db,
    save_job,
    get_job_by_id,
    get_interview_prep_session_by_job,
    list_interview_prep_sessions,
)


@pytest.fixture(autouse=True)
def setup_test_db():
    """Initializes the database schema for the test."""
    init_db()

from careerorbit.models.schemas import Job, VerificationStatus, MatchTier


async def asgi_request(app, method="GET", path="/", query="", body=b"", headers=None):
    from tests.authenticated_request import authenticated_headers
    headers = authenticated_headers(method, headers)
    """In-process ASGI helper supporting request bodies for FastAPI endpoints."""
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


@pytest.fixture
def mock_job_data():
    """Returns a mock job for testing."""
    return {
        "job_uid": "test-analyst-job-p5",
        "employer": "Fintech Solutions Inc",
        "title": "Senior Data Analyst",
        "normalized_title": "data analyst",
        "priority_category": 1,
        "priority_label": "Category 1",
        "location": "Bengaluru, India",
        "work_arrangement": "HYBRID",
        "employment_type": "FULL_TIME",
        "salary": "INR 12,00,000",
        "posting_date": "2026-10-24",
        "official_url": "https://example.com/careers/analyst",
        "canonical_url": "https://example.com/careers/analyst",
        "discovery_source": "Greenhouse Test Board",
        "verification_source": "Greenhouse API",
        "verification_status": VerificationStatus.VERIFIED_OPEN,
        "match_score": 88.0,
        "match_tier": MatchTier.STRONG_MATCH,
        "required_skills": ["SQL", "Power BI", "DAX", "Data Modeling"],
        "record_state": "ACTIVE",
    }


def test_briefing_generation_for_data_analyst(mock_job_data):
    """Verifies 5 role-specific questions with candidate evidence grounding for Data Analyst."""
    job_id = save_job(Job(**mock_job_data))
    coach = InterviewCoach()
    session = coach.get_or_create_briefing(job_id)

    assert session is not None
    assert session["job_id"] == job_id
    assert session["employer_name"] == "Fintech Solutions Inc"
    assert session["role_title"] == "Senior Data Analyst"

    briefing = session["briefing"]
    assert "questions" in briefing
    questions = briefing["questions"]
    assert len(questions) == 5

    # Check categories and candidate grounding
    categories = [q["category"] for q in questions]
    assert "Data Modeling & SQL Architecture" in categories
    assert "Candidate Project Evidence" in categories
    assert "STAR Behavioral & Stakeholder Defense" in categories

    # The briefing must prompt truthful examples without asserting candidate history.
    project_q = next(q for q in questions if q["category"] == "Candidate Project Evidence")
    assert "truthful real example" in project_q["candidate_example_prompt"].lower()
    serialized_questions = json.dumps(questions).lower()
    assert "previous employer" not in serialized_questions
    assert "verified improvement" not in serialized_questions
    assert "candidate_evidence_link" not in serialized_questions
    assert "rubric" in project_q["model_rubric"].lower() or len(project_q["model_rubric"]) > 20

    # Verify checklist and disclaimer
    checklist = session["checklist"]
    assert len(checklist) == 4
    assert any("Fintech Solutions Inc" in item["task"] for item in checklist)
    assert session["disclaimer"] == DISCLAIMER_TEXT


def test_briefing_generation_for_software_engineer():
    """Verifies role-specific prompts do not assert unverified candidate employment."""
    swe_job = {
        "job_uid": "test-swe-job-p5",
        "employer": "CloudScale Systems",
        "title": "Backend Python Engineer",
        "normalized_title": "backend python engineer",
        "priority_category": 3,
        "priority_label": "Category 3",
        "location": "Bengaluru, India",
        "work_arrangement": "REMOTE",
        "employment_type": "FULL_TIME",
        "salary": "INR 15,00,000",
        "posting_date": "2026-10-24",
        "official_url": "https://example.com/careers/python-eng",
        "canonical_url": "https://example.com/careers/python-eng",
        "discovery_source": "Lever Test Site",
        "verification_source": "Lever API",
        "verification_status": VerificationStatus.VERIFIED_OPEN,
        "match_score": 92.0,
        "match_tier": MatchTier.STRONG_MATCH,
        "required_skills": ["Python", "FastAPI", "PyTest", "PostgreSQL"],
        "record_state": "ACTIVE",
    }
    job_id = save_job(Job(**swe_job))
    coach = InterviewCoach()
    session = coach.get_or_create_briefing(job_id)

    briefing = session["briefing"]
    questions = briefing["questions"]
    assert len(questions) == 5

    categories = [q["category"] for q in questions]
    assert "Python Architecture & Performance" in categories
    assert "Candidate Project Evidence" in categories

    swe_evidence_q = next(q for q in questions if q["category"] == "Candidate Project Evidence")
    assert "truthful real example" in swe_evidence_q["candidate_example_prompt"].lower()
    assert "previous software team" not in json.dumps(questions).lower()


def test_briefing_generation_for_data_scientist():
    """Verifies questions and candidate evidence grounding for Data Scientist role."""
    ds_job = {
        "job_uid": "test-ds-job-p5",
        "employer": "NeuralInsights Labs",
        "title": "Computer Vision AI Engineer",
        "normalized_title": "computer vision ai engineer",
        "priority_category": 2,
        "priority_label": "Category 2",
        "location": "Hyderabad, India",
        "work_arrangement": "HYBRID",
        "employment_type": "FULL_TIME",
        "salary": "INR 18,00,000",
        "posting_date": "2026-10-24",
        "official_url": "https://example.com/careers/cv-eng",
        "canonical_url": "https://example.com/careers/cv-eng",
        "discovery_source": "Greenhouse Test Board",
        "verification_source": "Greenhouse API",
        "verification_status": VerificationStatus.VERIFIED_OPEN,
        "match_score": 90.0,
        "match_tier": MatchTier.STRONG_MATCH,
        "required_skills": ["PyTorch", "CNN", "OpenCV", "Flask"],
        "record_state": "ACTIVE",
    }
    job_id = save_job(Job(**ds_job))
    coach = InterviewCoach()
    session = coach.get_or_create_briefing(job_id)

    briefing = session["briefing"]
    questions = briefing["questions"]
    assert len(questions) == 5

    ds_evidence_q = next(q for q in questions if q["category"] == "Candidate Project Evidence")
    assert "truthful real example" in ds_evidence_q["candidate_example_prompt"].lower()
    assert "facial emotions" not in json.dumps(briefing).lower()


def test_briefing_caching_and_idempotency(mock_job_data):
    """Verifies that calling get_or_create_briefing multiple times returns the cached session."""
    job_id = save_job(Job(**mock_job_data))
    coach = InterviewCoach()

    first_call = coach.get_or_create_briefing(job_id)
    second_call = coach.get_or_create_briefing(job_id)

    assert first_call["id"] == second_call["id"]
    assert first_call["created_at"] == second_call["created_at"]


def test_notes_and_confidence_rating_update(mock_job_data):
    """Verifies updating candidate notes and 1-5 confidence rating persists."""
    job_id = save_job(Job(**mock_job_data))
    coach = InterviewCoach()

    coach.get_or_create_briefing(job_id)
    updated = coach.update_notes(job_id, notes="Focus on DAX context transition examples", confidence_rating=4)

    assert updated["candidate_notes"] == "Focus on DAX context transition examples"
    assert updated["confidence_rating"] == 4

    reloaded = get_interview_prep_session_by_job(job_id)
    assert reloaded["candidate_notes"] == "Focus on DAX context transition examples"
    assert reloaded["confidence_rating"] == 4


def test_checklist_item_completion(mock_job_data):
    """Verifies updating readiness checklist checkboxes persists."""
    job_id = save_job(Job(**mock_job_data))
    coach = InterviewCoach()

    session = coach.get_or_create_briefing(job_id)
    checklist = session["checklist"]
    checklist[0]["completed"] = True
    checklist[2]["completed"] = True

    coach.update_checklist(job_id, checklist)

    reloaded = get_interview_prep_session_by_job(job_id)
    assert reloaded["checklist"][0]["completed"] is True
    assert reloaded["checklist"][1]["completed"] is False
    assert reloaded["checklist"][2]["completed"] is True


def test_answer_draft_persistence(mock_job_data):
    """Verifies saving question rehearsal answer drafts persists."""
    job_id = save_job(Job(**mock_job_data))
    coach = InterviewCoach()

    coach.get_or_create_briefing(job_id)
    draft_answer_1 = "I use Star Schema with integer surrogate keys and composite indexes for fast filtering."
    coach.save_answer_draft(job_id, 1, draft_answer_1)

    reloaded = get_interview_prep_session_by_job(job_id)
    assert "1" in reloaded["answer_drafts"]
    assert reloaded["answer_drafts"]["1"] == draft_answer_1


@pytest.mark.anyio
async def test_api_endpoints_integration(mock_job_data):
    """Exercises all Interview Prep REST API routes via in-process ASGI calls."""
    job_id = save_job(Job(**mock_job_data))

    # 1. GET briefing
    status, _, body = await asgi_request(app, method="GET", path=f"/api/interview-prep/briefing/{job_id}")
    assert status == 200
    data = json.loads(body.decode())
    assert data["job_id"] == job_id
    assert len(data["briefing"]["questions"]) == 5

    # 2. PUT notes and confidence
    notes_payload = json.dumps({"notes": "API test notes", "confidence_rating": 5}).encode()
    status, _, body = await asgi_request(
        app,
        method="PUT",
        path=f"/api/interview-prep/briefing/{job_id}/notes",
        body=notes_payload,
        headers={"Content-Type": "application/json"}
    )
    assert status == 200
    res_data = json.loads(body.decode())
    assert res_data["confidence_rating"] == 5

    # 3. PUT checklist
    updated_checklist = data["checklist"]
    updated_checklist[0]["completed"] = True
    checklist_payload = json.dumps({"checklist": updated_checklist}).encode()
    status, _, body = await asgi_request(
        app,
        method="PUT",
        path=f"/api/interview-prep/briefing/{job_id}/checklist",
        body=checklist_payload,
        headers={"Content-Type": "application/json"}
    )
    assert status == 200
    res_data = json.loads(body.decode())
    assert res_data["checklist"][0]["completed"] is True

    # 4. POST answer draft
    draft_payload = json.dumps({
        "question_index": 2,
        "draft_text": "In my Sample Analytics Project project, I optimized execution plans..."
    }).encode()
    status, _, body = await asgi_request(
        app,
        method="POST",
        path=f"/api/interview-prep/briefing/{job_id}/draft",
        body=draft_payload,
        headers={"Content-Type": "application/json"}
    )
    assert status == 200
    res_data = json.loads(body.decode())
    assert res_data["answer_drafts"]["2"] == "In my Sample Analytics Project project, I optimized execution plans..."

    # 5. GET sessions list
    status, _, body = await asgi_request(app, method="GET", path="/api/interview-prep/sessions")
    assert status == 200
    sessions_data = json.loads(body.decode())
    assert sessions_data["count"] >= 1
    assert any(s["job_id"] == job_id for s in sessions_data["sessions"])

    # 6. 404 on nonexistent job
    status, _, _ = await asgi_request(app, method="GET", path="/api/interview-prep/briefing/99999999")
    assert status == 404


@pytest.mark.anyio
async def test_discovery_job_can_start_interview_practice_without_fit_or_open_verification(
    mock_job_data, monkeypatch
):
    """Role practice is independent from vacancy verification and candidate-fit readiness."""
    job_data = dict(mock_job_data)
    job_data.update({
        "job_uid": "pending-role-practice-test",
        "verification_status": VerificationStatus.PENDING_VERIFICATION,
        "match_score": 0.0,
        "match_tier": MatchTier.INELIGIBLE,
        "official_url": "",
        "canonical_url": "https://example.test/pending-role-practice",
        "description": "Use SQL, Power BI, KPI validation, and stakeholder reporting.",
    })
    job_id = save_job(Job(**job_data))
    import importlib
    web_app_module = importlib.import_module("careerorbit.web.app")
    monkeypatch.setattr(web_app_module, "candidate_profile_ready_for_resume", lambda: False)

    response_status, _, body = await asgi_request(
        app, method="POST", path=f"/api/prep/interview/{job_id}"
    )

    assert response_status == 200, body.decode()
    workspace = json.loads(body.decode())
    assert workspace["role_title"] == job_data["title"]
    assert workspace["job_description"] == job_data["description"]
    assert len(workspace["briefing"]["questions"]) >= 5
    assert "match score" in workspace["briefing"]["summary"].lower()
    assert "candidate_evidence_link" not in json.dumps(workspace)


def test_application_package_interview_examples_do_not_claim_candidate_history(monkeypatch, mock_job_data):
    """Archived package prompts describe answer structure, never invented first-person achievements."""
    monkeypatch.setattr("careerorbit.prep.interview_coach.candidate_profile_ready_for_resume", lambda: True)
    job_id = save_job(Job(**mock_job_data))
    job = get_job_by_id(job_id)
    package = InterviewCoach().generate_prep_package(job)
    answers = " ".join(item["model_answer"] for item in package["interview_questions"]).lower()
    for fabricated_claim in (
        "in my previous roles",
        "at a previous employer",
        "at a previous software team",
        "in the reviewed analytics project",
        "i automated the data ingestion",
    ):
        assert fabricated_claim not in answers
    assert "hypothetical" in answers
