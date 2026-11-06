"""Tests for SQLite database operations, CRUD, status transitions, and approval gatekeeper."""
import pytest
from datetime import datetime, timezone
from careerorbit.database.db import (
    init_db, save_job, get_job_by_uid, get_job_by_id, list_jobs, get_job_stats,
    create_or_update_application, get_application_by_job_id, confirm_user_submission,
    export_jobs_to_csv, export_applications_to_csv
)
from careerorbit.models.schemas import (
    Job, Application, ApplicationStatus, RecruiterOutreachStatus,
    VerificationStatus, MatchTier, ScoreBreakdown
)

@pytest.fixture(autouse=True)
def setup_db():
    init_db()

def test_job_save_and_retrieve():
    test_uid = f"test_company_role_{int(datetime.now(timezone.utc).timestamp())}"
    job = Job(
        job_uid=test_uid,
        employer="TestCorp Innovations",
        title="Junior Data Analyst",
        normalized_title="junior data analyst",
        priority_category=1,
        priority_label="Data Analyst / Business Intelligence",
        location="Coimbatore, Tamil Nadu",
        work_arrangement="Hybrid",
        official_url="https://testcorp.com/careers/da",
        canonical_url="https://testcorp.com/careers/da",
        discovery_source="Test Unit",
        verification_status=VerificationStatus.UNVERIFIED,
        match_score=85.0,
        match_tier=MatchTier.STRONG_MATCH,
        score_breakdown=ScoreBreakdown(
            skills_and_projects=28.0,
            experience_compatibility=20.0,
            eligibility=15.0,
            freshness_and_availability=12.0,
            location_and_arrangement=10.0,
            evidence_and_realistic_fit=10.0,
            total=85.0
        ),
        required_skills=["Python", "SQL", "Power BI"],
        supported_skills=["Python", "SQL", "Power BI"],
        description="Test vacancy for data analyst"
    )
    job_id = save_job(job)
    assert job_id > 0

    retrieved = get_job_by_uid(test_uid)
    assert retrieved is not None
    assert retrieved["employer"] == "TestCorp Innovations"
    assert retrieved["match_score"] == 85.0
    assert retrieved["verification_status"] == "UNVERIFIED"

def test_application_approval_enforcement():
    """Security Boundary: Applications must never be submitted without explicit user confirmation."""
    test_uid = f"approval_test_{int(datetime.now(timezone.utc).timestamp())}"
    job = Job(
        job_uid=test_uid,
        employer="SecureEmployer Inc",
        title="Associate Software Engineer",
        normalized_title="associate software engineer",
        priority_category=3,
        location="Bengaluru",
        official_url="https://secure.com/apply",
        official_listing_url="https://secure.com/jobs/approval-test",
        application_url="https://secure.com/apply",
        canonical_url="https://secure.com/apply",
        discovery_source="Fixture",
        verification_status=VerificationStatus.VERIFIED_OPEN,
        match_tier=MatchTier.STRONG_MATCH
    )
    job_id = save_job(job)

    # Initial state must be AWAITING_APPROVAL with confirmation = False
    app = Application(
        job_id=job_id,
        application_status=ApplicationStatus.AWAITING_APPROVAL,
        submission_confirmed_by_user=False,
        recruiter_outreach_status=RecruiterOutreachStatus.DRAFTED
    )
    app_id = create_or_update_application(app)
    assert app_id > 0

    saved_app = get_application_by_job_id(job_id)
    assert saved_app["submission_confirmed_by_user"] is False
    assert saved_app["application_status"] == ApplicationStatus.AWAITING_APPROVAL.value

    # Explicit user confirmation call
    success = confirm_user_submission(job_id, notes="Candidate confirmed manual submission.")
    assert success is True

    updated_app = get_application_by_job_id(job_id)
    assert updated_app["submission_confirmed_by_user"] is True
    assert updated_app["application_status"] == ApplicationStatus.SUBMITTED.value
    assert updated_app["submission_date"] is not None

def test_csv_exports():
    jobs_csv = export_jobs_to_csv()
    assert jobs_csv.endswith(".csv")

    apps_csv = export_applications_to_csv()
    assert apps_csv.endswith(".csv")


def test_csv_formula_cells_are_neutralized():
    from careerorbit.database.db import _safe_csv_cell
    assert _safe_csv_cell("=HYPERLINK(\"https://bad.invalid\")") == "'=HYPERLINK(\"https://bad.invalid\")"
    assert _safe_csv_cell("  @SUM(A1:A2)") == "'  @SUM(A1:A2)"
    assert _safe_csv_cell("ordinary title") == "ordinary title"


def test_job_listing_respects_candidate_priority_order():
    for priority in (3, 1, 2):
        save_job(Job(
            job_uid=f"sort-priority-{priority}", employer="Example", title=f"Role {priority}",
            normalized_title=f"role {priority}", priority_category=priority,
            priority_label=f"Priority {priority}", location="India", work_arrangement="Hybrid",
            official_url="", canonical_url="", discovery_source="Fixture",
            verification_status=VerificationStatus.UNVERIFIED, match_score=99.0,
            match_tier=MatchTier.STRONG_MATCH,
        ))
    listed = list_jobs(limit=10)
    categories = [job["priority_category"] for job in listed]
    assert categories == sorted(categories)


def test_synthetic_test_source_is_not_returned_as_a_job_lead():
    save_job(Job(
        job_uid="test-source-hidden", employer="Test Employer", title="Junior Data Analyst",
        normalized_title="junior data analyst", priority_category=1, priority_label="Data Analyst",
        location="India", work_arrangement="Hybrid", official_url="", canonical_url="",
        discovery_source="Test", verification_status=VerificationStatus.UNVERIFIED,
        match_tier=MatchTier.STRONG_MATCH,
    ))
    assert all(job["job_uid"] != "test-source-hidden" for job in list_jobs(limit=100))


def test_dashboard_api_withholds_contacts_and_quarantined_records():
    from fastapi import HTTPException
    from careerorbit.config.profile import CANDIDATE_PROFILE
    from careerorbit.web.app import get_profile, get_jobs, get_single_job, _present_candidate_fit, app

    save_job(Job(
        job_uid="api-test-fixture", employer="Fixture Employer", title="Junior Data Analyst",
        normalized_title="junior data analyst", priority_category=1, priority_label="Data Analyst",
        location="India", work_arrangement="Hybrid", official_url="https://fixture.invalid/apply",
        canonical_url="https://fixture.invalid/job", discovery_source="Test",
        verification_status=VerificationStatus.UNVERIFIED, match_score=99.0,
        match_tier=MatchTier.STRONG_MATCH,
    ))
    profile = get_profile()
    serialized = str(profile)
    assert CANDIDATE_PROFILE["personal"]["email"] not in serialized
    assert CANDIDATE_PROFILE["personal"]["phone"] not in serialized
    claims = {row["field"]: row for row in profile["candidate_claims"]}
    assert claims["personal.email"]["legacy_value"] == "[withheld]"
    fit = {"match_score": 99, "match_tier": "Strong match", "disqualifiers": ["degree required"],
           "verification_status": "UNVERIFIED", "discovery_source": "Jobicy Public API"}
    _present_candidate_fit(fit, ready=False)
    assert fit["candidate_fit_score"] is None
    assert fit["mandatory_eligibility_result"] == "NEEDS_CANDIDATE_REVIEW"
    reviewed_fit = {"match_score": 99, "match_tier": "Strong match", "disqualifiers": ["degree required"],
                    "verification_status": "UNVERIFIED", "discovery_source": "Jobicy Public API"}
    _present_candidate_fit(reviewed_fit, ready=True)
    assert reviewed_fit["candidate_fit_score"] == 99
    assert reviewed_fit["mandatory_eligibility_result"] == "INELIGIBLE"
    assert reviewed_fit["source_evidence_quality"] == "THIRD_PARTY_DISCOVERY"
    jobs = get_jobs(priority=None, match_tier=None, verification_status=None, location=None,
                    search=None, min_score=None, work_arrangement=None, saved_only=False,
                    sort_by="priority_first", limit=100, offset=0)["jobs"]
    assert all(row["discovery_source"] != "Test" for row in jobs)
    assert all(row["match_score"] is None for row in jobs)
    quarantined_id = save_job(Job(
        job_uid="api-test-quarantined", employer="Fixture Employer", title="Junior Data Analyst",
        normalized_title="junior data analyst", priority_category=1, priority_label="Data Analyst",
        location="India", work_arrangement="Hybrid", official_url="https://fixture.invalid/apply",
        canonical_url="https://fixture.invalid/job", discovery_source="Test",
        verification_status=VerificationStatus.UNVERIFIED, match_tier=MatchTier.STRONG_MATCH,
    ))
    with pytest.raises(HTTPException) as err:
        get_single_job(quarantined_id)
    assert err.value.status_code == 404
    assert not any(route.path == "/api/profile/confirm-all" for route in app.routes)


def test_job_bookmarking_toggle():
    from careerorbit.database.db import toggle_save_job, is_job_saved
    job_uid = f"bookmark_test_{int(datetime.now(timezone.utc).timestamp())}"
    job_id = save_job(Job(
        job_uid=job_uid, employer="Acme Corp", title="Data Analyst",
        normalized_title="data analyst", priority_category=1, priority_label="Data Analyst",
        location="Bengaluru", work_arrangement="Remote", official_url="https://acme.com",
        canonical_url="https://acme.com", discovery_source="Unit Test",
        verification_status=VerificationStatus.UNVERIFIED, match_tier=MatchTier.STRONG_MATCH
    ))
    assert is_job_saved(job_id) is False
    saved = toggle_save_job(job_id)
    assert saved is True
    assert is_job_saved(job_id) is True
    unsaved = toggle_save_job(job_id)
    assert unsaved is False
    assert is_job_saved(job_id) is False


def test_candidate_evidence_snapshot_and_confirmation():
    from careerorbit.config.candidate_evidence import (
        export_profile_snapshot, set_candidate_field_evidence, candidate_evidence_summary
    )
    import hashlib
    import json

    # A one-field confirmation cannot bulk-confirm unrelated candidate claims.
    set_candidate_field_evidence("personal.full_name", "CONFIRMED_BY_CANDIDATE", "unit-test-only explicit confirmation")
    summary = candidate_evidence_summary()
    assert summary["ready_for_resume"] is False
    assert summary["requires_confirmation"] > 0
    assert summary["confirmed_by_candidate"] > 0

    # Export snapshot and verify SHA-256 hash
    snapshot = export_profile_snapshot()
    assert "integrity_sha256" in snapshot
    recorded_hash = snapshot.pop("integrity_sha256")
    canonical_bytes = json.dumps(snapshot, sort_keys=True).encode("utf-8")
    expected_hash = hashlib.sha256(canonical_bytes).hexdigest()
    assert recorded_hash == expected_hash
