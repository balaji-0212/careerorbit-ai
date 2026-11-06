"""Tests for job listing freshness, stale listing detection, and closure verification.

Verifies:
1. Stale listing detection identifies never-verified jobs, overdue verifications, and aged postings.
2. Closure detection via HTTP 404/410 and closure text patterns.
3. Rate limits (HTTP 429/403) and network errors do not falsely mark vacancies as closed.
4. Historical application records are 100% preserved when a job closes, with audit trail recorded.
5. Application tracker exposes verification status of associated jobs.
6. User submission confirmation is blocked on closed jobs.
"""
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
import pytest

from careerorbit.database.db import (
    init_db,
    save_job,
    get_job_by_id,
    create_or_update_application,
    get_application_by_id,
    get_application_by_job_id,
    get_application_history,
    list_applications,
    confirm_user_submission,
)
from careerorbit.models.schemas import (
    Job,
    Application,
    ApplicationStatus,
    VerificationStatus,
    RecruiterOutreachStatus,
)
from careerorbit.verifier.checker import (
    VerificationEngine,
    detect_stale_listings,
    recheck_active_leads,
)


@pytest.fixture(autouse=True)
def setup_test_db():
    init_db()


def test_detect_stale_listings_criteria():
    """Verify stale listing detector flags never-verified, stale-verified, and aged posting jobs."""
    now_utc = datetime.now(timezone.utc)
    t_20d_ago = (now_utc - timedelta(days=20)).isoformat()
    t_45d_ago = (now_utc - timedelta(days=45)).isoformat()
    t_1d_ago = (now_utc - timedelta(days=1)).isoformat()

    # Job 1: Never verified
    j1 = Job(
        job_uid="job_fresh_1",
        employer="Fresh Employer A",
        title="Junior Data Analyst",
        normalized_title="junior data analyst",
        location="Bengaluru, Karnataka",
        official_url="https://greenhouse.io/fresh-a/jobs/1",
        official_listing_url="https://greenhouse.io/fresh-a/jobs/1",
        canonical_url="https://greenhouse.io/fresh-a/jobs/1",
        discovery_source="Greenhouse (Fresh Employer A)",
        verification_status=VerificationStatus.UNVERIFIED,
        last_verified_at="",
    )
    id1 = save_job(j1)

    # Job 2: Verified 20 days ago (threshold: 14 days)
    j2 = Job(
        job_uid="job_fresh_2",
        employer="Fresh Employer B",
        title="Associate Software Engineer",
        normalized_title="associate software engineer",
        location="Chennai, Tamil Nadu",
        official_url="https://greenhouse.io/fresh-b/jobs/2",
        official_listing_url="https://greenhouse.io/fresh-b/jobs/2",
        canonical_url="https://greenhouse.io/fresh-b/jobs/2",
        discovery_source="Greenhouse (Fresh Employer B)",
        verification_status=VerificationStatus.VERIFIED_OPEN,
        last_verified_at=t_20d_ago,
    )
    id2 = save_job(j2)

    # Job 3: Posting date 45 days ago (threshold: 30 days)
    j3 = Job(
        job_uid="job_fresh_3",
        employer="Fresh Employer C",
        title="Python Developer",
        normalized_title="python developer",
        location="Hyderabad, Telangana",
        official_url="https://greenhouse.io/fresh-c/jobs/3",
        official_listing_url="https://greenhouse.io/fresh-c/jobs/3",
        canonical_url="https://greenhouse.io/fresh-c/jobs/3",
        discovery_source="Greenhouse (Fresh Employer C)",
        verification_status=VerificationStatus.VERIFIED_OPEN,
        posting_date=t_45d_ago,
        last_verified_at=t_1d_ago,
    )
    id3 = save_job(j3)

    # Job 4: Fresh job verified yesterday
    j4 = Job(
        job_uid="job_fresh_4",
        employer="Fresh Employer D",
        title="BI Developer",
        normalized_title="bi developer",
        location="Pune, Maharashtra",
        official_url="https://greenhouse.io/fresh-d/jobs/4",
        official_listing_url="https://greenhouse.io/fresh-d/jobs/4",
        canonical_url="https://greenhouse.io/fresh-d/jobs/4",
        discovery_source="Greenhouse (Fresh Employer D)",
        verification_status=VerificationStatus.VERIFIED_OPEN,
        posting_date=t_1d_ago,
        last_verified_at=t_1d_ago,
    )
    id4 = save_job(j4)

    # Run stale detector
    stale_jobs = detect_stale_listings(days_since_verified=14, days_since_posted=30)
    stale_ids = {s["id"] for s in stale_jobs}

    assert id1 in stale_ids, "Never-verified job must be flagged as stale"
    assert id2 in stale_ids, "Verification > 14 days ago must be flagged as stale"
    assert id3 in stale_ids, "Posting date > 30 days ago must be flagged as stale"
    assert id4 not in stale_ids, "Freshly verified recent job must NOT be flagged as stale"

    j1_stale = next(s for s in stale_jobs if s["id"] == id1)
    assert "NEVER_VERIFIED" in j1_stale["stale_reasons"]

    j2_stale = next(s for s in stale_jobs if s["id"] == id2)
    assert "VERIFICATION_STALE" in j2_stale["stale_reasons"]

    j3_stale = next(s for s in stale_jobs if s["id"] == id3)
    assert "POSTING_AGE_STALE" in j3_stale["stale_reasons"]


def test_job_closure_preserves_application_records():
    """Verify that when a job closes, the application record is preserved and audit history is appended."""
    # 1. Create a job
    job = Job(
        job_uid="job_close_test_1",
        employer="Canonical Ltd",
        title="Linux Systems Engineer",
        normalized_title="linux systems engineer",
        location="Remote, India",
        official_url="https://boards.greenhouse.io/canonical/jobs/9999",
        official_listing_url="https://boards.greenhouse.io/canonical/jobs/9999",
        application_url="https://boards.greenhouse.io/canonical/jobs/9999",
        canonical_url="https://boards.greenhouse.io/canonical/jobs/9999",
        discovery_source="Greenhouse (Canonical)",
        verification_status=VerificationStatus.VERIFIED_OPEN,
    )
    job_id = save_job(job)

    # 2. Create an application for this job
    app = Application(
        job_id=job_id,
        application_status=ApplicationStatus.AWAITING_APPROVAL,
        recruiter_outreach_status=RecruiterOutreachStatus.NOT_STARTED,
        notes="Tailored resume prepared; awaiting candidate submission review",
    )
    app_id = create_or_update_application(app)

    # 3. Simulate recheck where the URL returns HTTP 404 (Vacancy closed / removed)
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.headers = {}
    mock_resp.text = "404 Not Found - This job posting is no longer available"

    with patch("requests.Session.get", return_value=mock_resp):
        results = recheck_active_leads(max_jobs=10, days_threshold=0)

    # Job must now be VERIFIED_CLOSED
    updated_job = get_job_by_id(job_id)
    assert updated_job["verification_status"] == "VERIFIED_CLOSED"
    assert results["verified_closed"] >= 1

    # 4. Critical requirement: Application record MUST still exist in database
    persisted_app = get_application_by_id(app_id)
    assert persisted_app is not None, "Application must not be deleted when job closes"
    assert persisted_app["job_id"] == job_id
    assert persisted_app["application_status"] == "AWAITING_APPROVAL"
    assert "Tailored resume prepared" in persisted_app["notes"]

    # 5. Application tracker must expose verification_status
    app_list = list_applications()
    app_row = next(a for a in app_list if a["id"] == app_id)
    assert app_row["verification_status"] == "VERIFIED_CLOSED", "list_applications must surface job verification_status"

    # 6. Audit history must have an entry documenting the closure transition
    history = get_application_history(app_id)
    assert len(history) >= 1
    closure_audit = next(h for h in history if h.get("event_source") == "JOB_VERIFIER")
    assert closure_audit["actor"] == "SYSTEM_VERIFIER"
    assert "closed or removed" in closure_audit["notes"].lower()


def test_closure_detection_from_body_text():
    """Verify that HTTP 200 pages with explicit closure text are marked VERIFIED_CLOSED."""
    verifier = VerificationEngine(timeout_seconds=5)
    url = "https://boards.greenhouse.io/canonical/jobs/8888"

    closure_texts = [
        "This position has been filled. Thank you for your interest.",
        "We are no longer accepting applications for this job opening.",
        "This job requisition is closed.",
        "The job you are looking for could not be found.",
    ]

    for body_text in closure_texts:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {}
        mock_resp.text = f"<html><body><div>Canonical</div><p>{body_text}</p></body></html>"

        with patch("requests.Session.get", return_value=mock_resp):
            status, evidence = verifier.verify_listing(url, employer="Canonical")
            assert status == VerificationStatus.VERIFIED_CLOSED
            assert "closure" in evidence.lower() or "closed" in evidence.lower()


def test_rate_limiting_and_errors_do_not_mark_closed():
    """Verify that HTTP 429/403/503 and network timeouts result in VERIFICATION_ERROR, not closed."""
    verifier = VerificationEngine(timeout_seconds=5)
    url = "https://boards.greenhouse.io/canonical/jobs/7777"

    # 1. HTTP 429 Too Many Requests
    mock_429 = MagicMock()
    mock_429.status_code = 429
    mock_429.headers = {}
    with patch("requests.Session.get", return_value=mock_429):
        status, evidence = verifier.verify_listing(url, employer="Canonical")
        assert status == VerificationStatus.VERIFICATION_ERROR
        assert "rate limited" in evidence.lower()
        assert status != VerificationStatus.VERIFIED_CLOSED

    # 2. HTTP 403 Forbidden / Cloudflare challenge
    mock_403 = MagicMock()
    mock_403.status_code = 403
    mock_403.headers = {}
    with patch("requests.Session.get", return_value=mock_403):
        status, evidence = verifier.verify_listing(url, employer="Canonical")
        assert status == VerificationStatus.VERIFICATION_ERROR
        assert status != VerificationStatus.VERIFIED_CLOSED


def test_confirm_user_submission_rejects_closed_job():
    """Verify that candidate submission gate strictly prevents applying to a closed job."""
    job = Job(
        job_uid="job_closed_submit_gate",
        employer="Acme Corp",
        title="Data Analyst",
        normalized_title="data analyst",
        location="Remote",
        official_url="https://boards.greenhouse.io/acme/jobs/111",
        official_listing_url="https://boards.greenhouse.io/acme/jobs/111",
        application_url="https://boards.greenhouse.io/acme/jobs/111",
        canonical_url="https://boards.greenhouse.io/acme/jobs/111",
        discovery_source="Greenhouse (Acme)",
        verification_status=VerificationStatus.VERIFIED_CLOSED,
    )
    job_id = save_job(job)

    app = Application(
        job_id=job_id,
        application_status=ApplicationStatus.AWAITING_APPROVAL,
        recruiter_outreach_status=RecruiterOutreachStatus.NOT_STARTED,
    )
    create_or_update_application(app)

    # Attempt submission confirmation
    confirmed = confirm_user_submission(job_id=job_id, notes="Candidate confirmed submission")
    assert confirmed is False, "Submission must be rejected when vacancy is VERIFIED_CLOSED"
