"""Tests for functionality repairs: stage transitions, resume upload/delete, and telegram scoping."""
import io
import pytest
from careerorbit.web.app import app
from careerorbit.database.db import (
    init_db, save_job, get_application_by_id, list_resumes, get_resume_by_id
)
from careerorbit.models.schemas import Job, ApplicationStatus, canonicalize_application_stage
from careerorbit.config.settings import SETTINGS, current_resumes_dir


def test_canonicalize_application_stage_mappings():
    assert canonicalize_application_stage("INTERVIEW") == "INTERVIEW_SCHEDULED"
    assert canonicalize_application_stage("interview_scheduled") == "INTERVIEW_SCHEDULED"
    assert canonicalize_application_stage("OFFER") == "OFFER_RECEIVED"
    assert canonicalize_application_stage("SUBMITTED") == "APPLIED"
    assert canonicalize_application_stage("TO_APPLY") == "READY_TO_APPLY"
    assert canonicalize_application_stage("SAVED") == "SAVED"
    assert canonicalize_application_stage("REJECTED") == "REJECTED"


def test_update_application_status_with_interview(monkeypatch):
    init_db()
    job_id = save_job(Job(
        job_uid="repair-test-job-uid-1",
        employer="Orbit Analytics",
        title="BI Lead",
        normalized_title="bi lead",
        official_url="https://orbitanalytics.com/jobs/1",
        official_listing_url="https://orbitanalytics.com/jobs/1",
        application_url="https://orbitanalytics.com/jobs/1/apply",
        canonical_url="https://orbitanalytics.com/jobs/1",
        discovery_source="Direct",
        verification_status="VERIFIED_OPEN",
    ))
    from careerorbit.database.db import create_manual_application
    app_id = create_manual_application(job_data={"job_id": job_id}, app_data={"job_id": job_id, "application_status": "SAVED"})

    # Update with status='INTERVIEW' should canonicalize to INTERVIEW_SCHEDULED and succeed
    from careerorbit.web.app import update_application_status_endpoint
    res = update_application_status_endpoint(
        app_id=app_id,
        payload={"status": "INTERVIEW", "notes": "Technical screening scheduled."}
    )
    assert res["status"] == "SUCCESS"
    updated = get_application_by_id(app_id)
    assert updated["application_status"] == "INTERVIEW_SCHEDULED"


def test_resume_upload_and_delete_endpoints():
    import asyncio

    async def _run():
        init_db()
        fake_content = b"%PDF-1.4 test resume document content"
        fake_file = io.BytesIO(fake_content)

        from careerorbit.web.app import upload_resume_endpoint, delete_resume_endpoint
        from fastapi import UploadFile

        uf = UploadFile(filename="candidate_master_cv.pdf", file=fake_file)
        upload_res = await upload_resume_endpoint(
            file=uf,
            job_id=None,
            company_name="Acme Corp",
            role_title="Senior Data Engineer"
        )
        assert upload_res["status"] == "SUCCESS"
        resume_id = upload_res["resume_id"]
        filename = upload_res["filename"]
        assert resume_id > 0
        assert (current_resumes_dir() / filename).exists()

        # Verify resume appears in list_resumes
        res_list = list_resumes()
        matching = [r for r in res_list if r["id"] == resume_id]
        assert len(matching) == 1
        assert matching[0]["source_resume_type"] == "Candidate Upload"

        # Delete resume
        del_res = delete_resume_endpoint(resume_id)
        assert del_res["status"] == "SUCCESS"
        assert get_resume_by_id(resume_id) is None
        assert not (current_resumes_dir() / filename).exists()

    asyncio.run(_run())
