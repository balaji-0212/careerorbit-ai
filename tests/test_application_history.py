"""Tests for application tracker stage transitions and audit history."""
import pytest
from fastapi import HTTPException

from careerorbit.database.db import (
    init_db, save_job, create_or_update_application,
    get_application_history, record_application_transition,
    update_application_stage, get_application_by_id, list_applications
)
from careerorbit.models.schemas import ApplicationStatus, Job, Application, VerificationStatus, MatchTier
from careerorbit.web.app import (
    get_application_history_endpoint,
    update_application_status_endpoint
)

@pytest.fixture(autouse=True)
def setup_db():
    init_db()
    # Seed a sample job and application for testing
    job_id = save_job(Job(
        job_uid="pytest_app_history_uid",
        employer="Test Corp",
        title="Junior Data Analyst",
        normalized_title="junior data analyst",
        official_url="https://testcorp.com/jobs/1",
        official_listing_url="https://testcorp.com/jobs/1",
        application_url="https://testcorp.com/jobs/1/apply",
        canonical_url="https://testcorp.com/jobs/1",
        discovery_source="Direct",
        verification_status=VerificationStatus.VERIFIED_OPEN,
        match_tier=MatchTier.STRONG_MATCH,
        match_score=85.0
    ))
    app_id = create_or_update_application(Application(
        job_id=job_id,
        application_status=ApplicationStatus.SAVED,
        notes="Pytest seeded application"
    ))
    record_application_transition(
        application_id=app_id,
        previous_status="CREATED",
        new_status="SAVED",
        notes="Pytest seeded application"
    )

def test_canonical_application_stages_exist():
    assert ApplicationStatus.SAVED.value == "SAVED"
    assert ApplicationStatus.READY_TO_APPLY.value == "READY_TO_APPLY"
    assert ApplicationStatus.APPLIED.value == "APPLIED"
    assert ApplicationStatus.ASSESSMENT_RECEIVED.value == "ASSESSMENT_RECEIVED"
    assert ApplicationStatus.INTERVIEW_SCHEDULED.value == "INTERVIEW_SCHEDULED"
    assert ApplicationStatus.INTERVIEW_COMPLETED.value == "INTERVIEW_COMPLETED"
    assert ApplicationStatus.OFFER_RECEIVED.value == "OFFER_RECEIVED"
    assert ApplicationStatus.REJECTED.value == "REJECTED"
    assert ApplicationStatus.WITHDRAWN.value == "WITHDRAWN"
    assert ApplicationStatus.NO_RESPONSE.value == "NO_RESPONSE"

def test_application_history_recording():
    apps = list_applications()
    assert len(apps) > 0
    app_id = apps[0]["id"]

    initial_history = get_application_history(app_id)
    assert len(initial_history) >= 1

    # Record a transition
    record_application_transition(
        application_id=app_id,
        previous_status=apps[0]["application_status"],
        new_status="INTERVIEW_SCHEDULED",
        event_source="USER_MANUAL",
        actor="CANDIDATE",
        notes="HR round scheduled for Tuesday 10am",
        evidence="Calendar invitation received"
    )

    updated_history = get_application_history(app_id)
    assert len(updated_history) == len(initial_history) + 1
    latest = updated_history[-1]
    assert latest["new_status"] == "INTERVIEW_SCHEDULED"
    assert "HR round" in latest["notes"]

def test_human_submission_barrier_on_applied():
    apps = list_applications()
    app_id = apps[0]["id"]

    # Attempting to move to APPLIED without confirmed_by_user should raise HTTPException(400)
    with pytest.raises(HTTPException) as exc_info:
        update_application_status_endpoint(app_id, {
            "status": "APPLIED",
            "confirmed_by_user": False
        })
    assert exc_info.value.status_code == 400
    assert "Explicit human confirmation is required" in exc_info.value.detail

    # Moving to APPLIED with explicit confirmation should succeed
    res_ok = update_application_status_endpoint(app_id, {
        "status": "APPLIED",
        "confirmed_by_user": True,
        "notes": "Submitted through official Greenhouse careers page"
    })
    assert res_ok["status"] == "SUCCESS"
    assert res_ok["application"]["application_status"] == "APPLIED"
    assert res_ok["application"]["submission_confirmed_by_user"] is True
