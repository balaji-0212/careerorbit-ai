"""Test suite verifying full Application Tracker CRUD operations and human approval barriers."""
import json
import pytest
from careerorbit.database.db import (
    init_db,
    save_job,
    get_application_by_id,
    list_applications,
)
from careerorbit.models.schemas import (
    Job,
    ApplicationStatus,
    VerificationStatus,
    MatchTier,
)
from careerorbit.web.app import (
    add_application_endpoint,
    get_single_application_endpoint,
    edit_application_endpoint,
    delete_application_endpoint,
    export_single_application_history_endpoint,
    export_all_applications_history_endpoint,
)
from fastapi import HTTPException


@pytest.fixture(autouse=True)
def setup_db():
    init_db()


@pytest.fixture
def sample_job():
    return save_job(Job(
        job_uid="app-crud-test-job-uid",
        employer="Orbit Analytics Inc",
        title="Senior BI Analyst",
        normalized_title="senior bi analyst",
        priority_category=1,
        priority_label="Category 1",
        location="Bengaluru, Karnataka, India",
        work_arrangement="Hybrid",
        official_url="https://orbitanalytics.com/jobs/42",
        official_listing_url="https://orbitanalytics.com/jobs/42",
        application_url="https://orbitanalytics.com/jobs/42/apply",
        canonical_url="https://orbitanalytics.com/jobs/42",
        discovery_source="Direct Test",
        verification_status=VerificationStatus.VERIFIED_OPEN,
        match_tier=MatchTier.STRONG_MATCH,
        match_score=92.0,
        required_skills=["Power BI", "SQL", "DAX"],
    ))


def test_add_application_from_existing_job(sample_job):
    payload = {
        "job_id": sample_job,
        "application_status": "SAVED",
        "recruiter_name": "Priya Sharma",
        "recruiter_email": "priya@orbitanalytics.com",
        "interview_stage": "Screening",
        "interview_date": "2026-11-12",
        "follow_up_date": "2026-11-15",
        "deadline": "2026-11-20",
        "notes": "Connected via LinkedIn recruiter message.",
    }
    res = add_application_endpoint(payload)
    assert res["status"] == "SUCCESS"
    app_id = res["application_id"]
    assert app_id > 0

    # Verify retrieval
    app_item = get_single_application_endpoint(app_id)
    assert app_item["id"] == app_id
    assert app_item["employer"] == "Orbit Analytics Inc"
    assert app_item["recruiter_name"] == "Priya Sharma"
    assert app_item["recruiter_email"] == "priya@orbitanalytics.com"
    assert app_item["interview_date"] == "2026-11-12"
    assert len(app_item["history"]) >= 1


def test_add_manual_application_creates_job_and_app():
    payload = {
        "employer": "Fintech Solutions India",
        "title": "Data Analyst Trainee",
        "location": "Chennai, Tamil Nadu, India",
        "official_url": "https://fintechsolutions.in/careers/data-analyst",
        "application_status": "TO_APPLY",
        "recruiter_name": "Ramesh Kumar",
        "recruiter_email": "ramesh@fintechsolutions.in",
        "notes": "Direct portal application draft.",
    }
    res = add_application_endpoint(payload)
    assert res["status"] == "SUCCESS"
    app_id = res["application_id"]

    app_item = get_single_application_endpoint(app_id)
    assert app_item["employer"] == "Fintech Solutions India"
    assert app_item["title"] == "Data Analyst Trainee"
    assert app_item["recruiter_name"] == "Ramesh Kumar"


def test_edit_application_metadata(sample_job):
    res = add_application_endpoint({
        "job_id": sample_job,
        "notes": "Initial draft",
    })
    app_id = res["application_id"]

    edit_res = edit_application_endpoint(app_id, {
        "notes": "Updated notes after recruiter phone screening.",
        "recruiter_name": "Anita Roy",
        "recruiter_email": "anita@orbitanalytics.com",
        "interview_date": "2026-11-18",
        "deadline": "2026-11-25",
    })
    assert edit_res["status"] == "SUCCESS"
    updated = edit_res["application"]
    assert updated["recruiter_name"] == "Anita Roy"
    assert updated["interview_date"] == "2026-11-18"
    assert "Updated notes" in updated["notes"]


def test_submission_barrier_on_edit_endpoint(sample_job):
    res = add_application_endpoint({
        "job_id": sample_job,
        "application_status": "SAVED",
    })
    app_id = res["application_id"]

    # Attempting to move to APPLIED without candidate confirmation must fail
    with pytest.raises(HTTPException) as exc_info:
        edit_application_endpoint(app_id, {
            "status": "APPLIED",
            "confirmed_by_user": False,
        })
    assert exc_info.value.status_code == 400
    assert "Explicit human confirmation is required" in exc_info.value.detail

    # Moving to APPLIED with explicit candidate confirmation succeeds
    res_confirmed = edit_application_endpoint(app_id, {
        "status": "APPLIED",
        "confirmed_by_user": True,
        "notes": "Candidate manually confirmed portal submission.",
    })
    assert res_confirmed["status"] == "SUCCESS"
    assert res_confirmed["application"]["application_status"] == "APPLIED"


def test_delete_application_safety_barrier(sample_job):
    res = add_application_endpoint({"job_id": sample_job})
    app_id = res["application_id"]

    # Deletion without confirm=True raises 400
    with pytest.raises(HTTPException) as exc_info:
        delete_application_endpoint(app_id, confirm=False)
    assert exc_info.value.status_code == 400

    # Deletion with confirm=True succeeds
    del_res = delete_application_endpoint(app_id, confirm=True)
    assert del_res["status"] == "SUCCESS"

    # Subsequent fetch returns 404
    with pytest.raises(HTTPException) as exc_info_404:
        get_single_application_endpoint(app_id)
    assert exc_info_404.value.status_code == 404


def test_export_application_history(sample_job):
    res = add_application_endpoint({"job_id": sample_job, "notes": "Initial"})
    app_id = res["application_id"]
    edit_application_endpoint(app_id, {"status": "READY_TO_APPLY", "notes": "Ready"})

    # Single app export
    single_res = export_single_application_history_endpoint(app_id)
    assert single_res.status_code == 200
    assert "text/csv" in single_res.media_type

    # All apps export
    all_res = export_all_applications_history_endpoint()
    assert all_res.status_code == 200
    assert "text/csv" in all_res.media_type
