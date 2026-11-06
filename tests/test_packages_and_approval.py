"""Tests for application package generation, outreach drafts, and approval gatekeeper."""
import pytest
from datetime import datetime, timezone
from careerorbit.packages.generator import ApplicationPackageGenerator
from careerorbit.database.db import init_db, save_job, get_application_by_job_id, confirm_user_submission
from careerorbit.models.schemas import Job, VerificationStatus, MatchTier, ApplicationStatus

@pytest.fixture(autouse=True)
def setup_db():
    init_db()

def test_package_generator_workflow(monkeypatch):
    monkeypatch.setattr("careerorbit.packages.generator.candidate_profile_ready_for_resume", lambda: True)
    monkeypatch.setattr("careerorbit.resumes.generator.candidate_profile_ready_for_resume", lambda: True)
    unique_uid = f"pkg_test_caterpillar_da_{int(datetime.now(timezone.utc).timestamp() * 1000)}"
    job = Job(
        job_uid=unique_uid,
        employer="Caterpillar",
        title="Junior Data Analyst",
        normalized_title="junior data analyst",
        priority_category=1,
        location="Bengaluru",
        official_url="https://caterpillar.wd5.myworkdayjobs.com/careers/da",
            official_listing_url="https://caterpillar.wd5.myworkdayjobs.com/careers/da",
            application_url="https://caterpillar.wd5.myworkdayjobs.com/careers/da/apply",
        canonical_url="https://caterpillar.wd5.myworkdayjobs.com/careers/da",
        discovery_source="Fixture",
        verification_status=VerificationStatus.VERIFIED_OPEN,
        match_tier=MatchTier.STRONG_MATCH,
        supported_skills=["Power BI", "SQL", "DAX", "Python"],
        description="Power BI, DAX, and SQL reporting role."
    )
    job_id = save_job(job)
    job_dict = job.model_dump()
    job_dict["id"] = job_id

    pkg_gen = ApplicationPackageGenerator()
    pkg = pkg_gen.prepare_package_for_job(job_dict)

    assert pkg["company"] == "Caterpillar"
    assert pkg["submission_status"] == "AWAITING_APPROVAL"
    assert pkg["submission_confirmed_by_user"] is False

    # Check Cover Letter
    cl = pkg["cover_letter"]
    assert "Caterpillar" in cl
    assert "Candidate" in cl
    assert "Loan Portfolio Risk" not in cl

    # Check Questionnaire Answers
    answers = pkg["application_answers"]
    assert answers["work_authorization"]["verified"] is False
    assert answers["work_authorization"]["answer"] == ""
    assert answers["notice_period"]["answer"] == ""
    assert answers["notice_period"]["verified"] is False
    assert answers["salary_expectations"]["verified"] is False
    assert answers["relocation"]["verified"] is False

    # Check Outreach Drafts
    outreach = pkg["outreach_messages"]
    assert "referral_request" in outreach
    assert "recruiter_outreach" in outreach
    assert outreach["referral_request"]["approval_status"] == "DRAFTED_AWAITING_USER_APPROVAL"

    # Verify DB state is locked to AWAITING_APPROVAL
    app_db = get_application_by_job_id(job_id)
    assert app_db["application_status"] == ApplicationStatus.AWAITING_APPROVAL.value
    assert app_db["submission_confirmed_by_user"] is False

    # Perform user approval
    confirmed = confirm_user_submission(job_id, "Candidate confirmed submission on Workday.")
    assert confirmed is True

    app_db_after = get_application_by_job_id(job_id)
    assert app_db_after["application_status"] == ApplicationStatus.SUBMITTED.value
    assert app_db_after["submission_confirmed_by_user"] is True
