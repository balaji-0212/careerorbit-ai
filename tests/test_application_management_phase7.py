"""Phase 7 verification test suite for Resume & Application Management.

Verifies:
1. Full 10 canonical application lifecycle stages.
2. Complete audit trail recording in application_history.
3. Strict enforcement of the human submission barrier.
4. Resume tailoring truthfulness and zero fabrication of candidate metrics.
5. Application package generation and audit metadata tracking.
"""
from datetime import datetime, timezone
import pytest
from fastapi import HTTPException
from careerorbit.database.db import (
    init_db,
    save_job,
    create_or_update_application,
    get_application_by_id,
    get_application_history,
    record_application_transition,
    list_applications,
)
from careerorbit.models.schemas import (
    ApplicationStatus,
    Job,
    Application,
    VerificationStatus,
    MatchTier,
)
from careerorbit.resumes.tailor import ResumeTailor
from careerorbit.web.app import update_application_status_endpoint, get_application_history_endpoint


@pytest.fixture(autouse=True)
def setup_test_db():
    """Initializes the database schema for the test."""
    init_db()


@pytest.fixture
def sample_job_id():
    """Creates a sample verified job and returns its ID."""
    return save_job(Job(
        job_uid="phase7-test-job-uid",
        employer="Target Financial Tech",
        title="Junior Data Analyst",
        normalized_title="junior data analyst",
        priority_category=1,
        priority_label="Category 1",
        official_url="https://targetfintech.com/jobs/101",
        official_listing_url="https://targetfintech.com/jobs/101",
        application_url="https://targetfintech.com/jobs/101/apply",
        canonical_url="https://targetfintech.com/jobs/101",
        discovery_source="Greenhouse ATS",
        verification_status=VerificationStatus.VERIFIED_OPEN,
        match_tier=MatchTier.STRONG_MATCH,
        match_score=88.0,
        required_skills=["SQL", "Power BI", "DAX"],
    ))


def test_ten_canonical_stages_enumeration():
    """Verifies all 10 canonical lifecycle stages exist in ApplicationStatus."""
    expected_stages = [
        "SAVED",
        "READY_TO_APPLY",
        "APPLIED",
        "ASSESSMENT_RECEIVED",
        "INTERVIEW_SCHEDULED",
        "INTERVIEW_COMPLETED",
        "OFFER_RECEIVED",
        "REJECTED",
        "WITHDRAWN",
        "NO_RESPONSE",
    ]
    for stage in expected_stages:
        assert hasattr(ApplicationStatus, stage), f"Missing canonical stage: {stage}"
        assert getattr(ApplicationStatus, stage).value == stage


def test_sequential_lifecycle_stage_transitions(sample_job_id):
    """Verifies an application can transition through successive lifecycle stages."""
    app_id = create_or_update_application(Application(
        job_id=sample_job_id,
        application_status=ApplicationStatus.SAVED,
        notes="Saved for review",
    ))
    assert app_id is not None

    # Transition 1: SAVED -> READY_TO_APPLY
    res1 = update_application_status_endpoint(app_id, {
        "status": "READY_TO_APPLY",
        "notes": "Application package generated and reviewed",
    })
    assert res1["status"] == "SUCCESS"
    assert res1["application"]["application_status"] == "READY_TO_APPLY"

    # Transition 2: READY_TO_APPLY -> APPLIED (with human confirmation)
    res2 = update_application_status_endpoint(app_id, {
        "status": "APPLIED",
        "confirmed_by_user": True,
        "notes": "Candidate manually confirmed portal submission",
    })
    assert res2["status"] == "SUCCESS"
    assert res2["application"]["application_status"] == "APPLIED"

    # Transition 3: APPLIED -> ASSESSMENT_RECEIVED
    res3 = update_application_status_endpoint(app_id, {
        "status": "ASSESSMENT_RECEIVED",
        "notes": "HackerRank SQL assessment link received",
    })
    assert res3["status"] == "SUCCESS"
    assert res3["application"]["application_status"] == "ASSESSMENT_RECEIVED"

    # Transition 4: ASSESSMENT_RECEIVED -> INTERVIEW_SCHEDULED
    res4 = update_application_status_endpoint(app_id, {
        "status": "INTERVIEW_SCHEDULED",
        "notes": "Technical screening round scheduled for Friday 2 PM",
    })
    assert res4["status"] == "SUCCESS"
    assert res4["application"]["application_status"] == "INTERVIEW_SCHEDULED"

    # Transition 5: INTERVIEW_SCHEDULED -> INTERVIEW_COMPLETED
    res5 = update_application_status_endpoint(app_id, {
        "status": "INTERVIEW_COMPLETED",
        "notes": "Technical round completed; discussed Sample Analytics Project project",
    })
    assert res5["status"] == "SUCCESS"
    assert res5["application"]["application_status"] == "INTERVIEW_COMPLETED"

    # Transition 6: INTERVIEW_COMPLETED -> OFFER_RECEIVED
    res6 = update_application_status_endpoint(app_id, {
        "status": "OFFER_RECEIVED",
        "notes": "Formal offer letter received",
    })
    assert res6["status"] == "SUCCESS"
    assert res6["application"]["application_status"] == "OFFER_RECEIVED"


def test_application_history_audit_trail_completeness(sample_job_id):
    """Verifies that every status transition appends a complete event record to application_history."""
    app_id = create_or_update_application(Application(
        job_id=sample_job_id,
        application_status=ApplicationStatus.SAVED,
        notes="Initial save",
    ))
    record_application_transition(
        application_id=app_id,
        previous_status="CREATED",
        new_status="SAVED",
        actor="CANDIDATE",
        notes="Saved to tracker",
    )

    # Perform updates
    update_application_status_endpoint(app_id, {
        "status": "READY_TO_APPLY",
        "notes": "Package prepared",
    })
    update_application_status_endpoint(app_id, {
        "status": "APPLIED",
        "confirmed_by_user": True,
        "notes": "Manually submitted",
    })

    # Fetch audit history via endpoint
    res = get_application_history_endpoint(app_id)
    history = res["history"]
    assert len(history) >= 3

    statuses = [h.get("new_status") for h in history]
    assert "SAVED" in statuses
    assert "READY_TO_APPLY" in statuses
    assert "APPLIED" in statuses

    # Verify audit metadata fields
    for event in history:
        assert "actor" in event
        assert "timestamp" in event or "created_at" in event
        assert "notes" in event


def test_human_submission_barrier_enforcement(sample_job_id):
    """Verifies that moving to APPLIED without explicit user confirmation is rejected."""
    app_id = create_or_update_application(Application(
        job_id=sample_job_id,
        application_status=ApplicationStatus.READY_TO_APPLY,
        notes="Ready",
    ))

    # Rejection on unconfirmed status update
    with pytest.raises(HTTPException) as exc_info:
        update_application_status_endpoint(app_id, {
            "status": "APPLIED",
            "confirmed_by_user": False,
        })
    assert exc_info.value.status_code == 400
    assert "Explicit human confirmation is required" in exc_info.value.detail

    # Rejection when confirmed_by_user flag is omitted entirely
    with pytest.raises(HTTPException) as exc_info:
        update_application_status_endpoint(app_id, {
            "status": "APPLIED",
        })
    assert exc_info.value.status_code == 400

    # Success when confirmed_by_user is True
    res = update_application_status_endpoint(app_id, {
        "status": "APPLIED",
        "confirmed_by_user": True,
        "notes": "Verified manual application via official portal",
    })
    assert res["status"] == "SUCCESS"
    assert res["application"]["submission_confirmed_by_user"] is True


def test_resume_tailoring_truthfulness_and_project_metrics():
    """Verifies that resume tailoring truthfully presents verified project metrics without fabrication."""
    tailor = ResumeTailor()

    # 1. Data Analyst tailoring
    da_analysis = tailor.analyze_tailoring(
        job_title="Business Intelligence Analyst",
        job_description="Seeking a Power BI and SQL developer to optimize queries and build executive KPI dashboards.",
        priority_category=1,
    )
    assert da_analysis["source_type"] == "data_analyst"
    summary = da_analysis["professional_summary"]
    # Candidate-specific metrics are excluded unless tied to reviewed profile facts.
    assert "35%" not in summary
    assert "40%" not in summary
    assert "Power BI" in da_analysis["supported_keywords"]
    assert "SQL" in da_analysis["supported_keywords"]

    # 2. Software Engineer tailoring
    swe_analysis = tailor.analyze_tailoring(
        job_title="Associate Python Engineer",
        job_description="Build backend microservices with Python, FastAPI, and PostgreSQL with automated testing.",
        priority_category=3,
    )
    assert swe_analysis["source_type"] == "software_engineer"
    swe_summary = swe_analysis["professional_summary"]
    assert "Computer Engineering" in swe_summary
    assert "Python" in swe_analysis["supported_keywords"]
    assert "FastAPI" in swe_analysis["supported_keywords"]

    # 3. AI Engineer tailoring
    ai_analysis = tailor.analyze_tailoring(
        job_title="Computer Vision Engineer",
        job_description="Deploy CNN models using TensorFlow and OpenCV with Flask model serving.",
        priority_category=4,
    )
    assert ai_analysis["source_type"] in ("ai_engineer", "data_scientist")
    ai_summary = ai_analysis["professional_summary"]
    assert "87%" not in ai_summary
    assert "20%" not in ai_summary

    # 4. Learning targets must never be claimed as existing production skills
    de_analysis = tailor.analyze_tailoring(
        job_title="Data Engineer",
        job_description="Build ETL pipelines using PySpark, Azure Databricks, and SQL Server.",
        priority_category=5,
    )
    # Check that PySpark / Azure Databricks are categorized under missing requirements or learning targets
    assert any("PySpark" in req or "Databricks" in req for req in de_analysis["missing_requirements"])
