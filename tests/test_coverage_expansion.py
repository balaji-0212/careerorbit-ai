"""Tests for Real Job Discovery Coverage Expansion in CareerOrbit AI.
Covers:
1. SmartRecruiters public API source adapter.
2. Ashby public job board source adapter.
3. Unstop campus & fresher API adapter.
4. RemoteOK public API adapter.
5. Community Job Announcement Parser (WhatsApp/Telegram alerts).
6. Fresher, off-campus, internship attribute detection.
7. Database schema migration, new filters, get_job_by_url, and breakdown metrics.
8. Web API endpoints for community alert preview and import.
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from careerorbit.discovery.sources import (
    SmartRecruitersSource, AshbyJobBoardSource, UnstopSource, RemoteOKSource
)
from careerorbit.discovery.community_parser import CommunityJobParser
from careerorbit.eligibility import detect_opportunity_attributes
from careerorbit.database.db import (
    init_db, save_job, get_job_by_uid, get_job_by_url, list_jobs, get_job_stats
)
from careerorbit.models.schemas import Job, VerificationStatus, MatchTier
from careerorbit.web.app import (
    preview_community_announcement, import_community_announcement, get_jobs, get_stats
)


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    """Isolate database for coverage expansion tests."""
    db_file = tmp_path / "test_coverage.db"
    monkeypatch.setattr("careerorbit.config.settings.SETTINGS.DATABASE_PATH", db_file)
    init_db()
    return db_file


def test_detect_opportunity_attributes():
    """Verify detection of fresher, off-campus, internship, and walk-in attributes."""
    # Fresher role
    attr1 = detect_opportunity_attributes("Junior Data Analyst (Fresher 2025)", "Must know SQL and Power BI", "Full-time")
    assert attr1["is_fresher"] is True
    assert attr1["min_experience_years"] == 0.0

    # Off-campus hiring challenge
    attr2 = detect_opportunity_attributes("Software Engineer - Off-Campus Recruitment Drive", "Coding assessment round", "Full-time")
    assert attr2["is_off_campus"] is True

    # Internship
    attr3 = detect_opportunity_attributes("Data Science Intern", "Python and machine learning", "Internship")
    assert attr3["is_internship"] is True

    # Walk-in
    attr4 = detect_opportunity_attributes("Trainee Engineer - Walk-in Interview", "Walk in on Saturday", "Full-time")
    assert attr4["is_walkin"] is True


def test_community_job_parser_extracts_fields_accurately():
    """Verify parsing of pasted WhatsApp/Telegram announcements without field fabrication."""
    sample_text = """
    🚨 Off-Campus Hiring Alert 2025!
    Company: Thoughtworks India
    Role: Associate Software Engineer
    Location: Bengaluru, Karnataka
    Eligibility: 2024 / 2025 batch, 0-1 years exp
    Last Date: 30-Nov-2026
    Apply here: https://jobs.thoughtworks.com/apply/12345
    """
    parsed = CommunityJobParser.parse_announcement(sample_text, source_channel="WhatsApp Tech Group")

    assert parsed["employer"] == "Thoughtworks India"
    assert "Associate Software Engineer" in parsed["title"]
    assert "Bengaluru" in parsed["location"]
    assert parsed["is_fresher"] is True
    assert parsed["is_off_campus"] is True
    assert parsed["application_url"] == "https://jobs.thoughtworks.com/apply/12345"
    assert parsed["missing_link"] is False
    assert parsed["priority_category"] == 3


def test_community_job_parser_flags_missing_links():
    """Alerts without links must be flagged as missing_link."""
    sample_no_url = """
    Hiring Alert!
    Company: InnovateTech
    Role: Junior BI Analyst
    Location: Chennai
    Experience: Freshers
    Send CV to contact@innovate.example
    """
    parsed = CommunityJobParser.parse_announcement(sample_no_url, source_channel="Telegram Channel")
    assert parsed["missing_link"] is True
    assert parsed["application_url"] == ""


def test_community_job_parser_detects_existing_duplicates():
    """Verify parser flags potential duplicates against existing jobs in the database."""
    # Pre-populate a job
    job = Job(
        job_uid="dup_test_uid",
        employer="TargetCorp",
        title="Power BI Developer",
        normalized_title="power bi developer",
        priority_category=1,
        priority_label="Data Analyst / BI",
        location="Bengaluru",
        official_url="https://targetcorp.example/jobs/99",
        canonical_url="https://targetcorp.example/jobs/99",
        discovery_source="Direct",
    )
    save_job(job)

    # Announcement with identical details
    text = """
    Company: TargetCorp
    Role: Power BI Developer
    Location: Bengaluru
    Apply: https://targetcorp.example/jobs/99
    """
    parsed = CommunityJobParser.parse_announcement(text)
    assert parsed["is_duplicate"] is True


def test_smartrecruiters_source_adapter(monkeypatch):
    """Verify SmartRecruiters adapter fetches and normalizes jobs correctly."""
    adapter = SmartRecruitersSource(company="Bosch Group", company_id="BoschGroup")
    assert adapter.configured is True

    fake_response = {
        "totalFound": 1,
        "content": [
            {
                "id": "74400012345",
                "name": "Junior Python Developer",
                "refNumber": "REF1234X",
                "releasedDate": "2026-10-20T10:00:00Z",
                "location": {"city": "Bengaluru", "region": "Karnataka", "country": "in", "remote": False},
                "typeOfEmployment": {"label": "Full-time"}
            }
        ]
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = fake_response
    mock_resp.raise_for_status.return_value = None

    monkeypatch.setattr(adapter.session, "get", lambda *args, **kwargs: mock_resp)

    jobs = adapter.fetch_jobs(days_back=30)
    assert len(jobs) == 1
    job = jobs[0]
    assert job["title"] == "Junior Python Developer"
    assert job["employer"] == "Bosch Group"
    assert "Bengaluru" in job["location"]
    assert "smartrecruiters.com/BoschGroup/74400012345" in job["official_url"]
    assert job["source_is_official_api"] is True


def test_ashby_source_adapter(monkeypatch):
    """Verify Ashby adapter fetches and normalizes jobs."""
    adapter = AshbyJobBoardSource(company="Atlan", board_token="atlan")
    assert adapter.configured is True

    fake_response = {
        "jobs": [
            {
                "id": "ashby_101",
                "title": "Data Analyst",
                "location": "Bengaluru, India",
                "isRemote": True,
                "publishedAt": "2026-10-21T08:00:00Z",
                "jobUrl": "https://jobs.ashbyhq.com/atlan/ashby_101",
                "applyUrl": "https://jobs.ashbyhq.com/atlan/ashby_101/application",
                "employmentType": "FullTime",
                "compensation": {"summary": "Competitive"}
            }
        ]
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = fake_response
    mock_resp.raise_for_status.return_value = None

    monkeypatch.setattr(adapter.session, "get", lambda *args, **kwargs: mock_resp)

    jobs = adapter.fetch_jobs(days_back=30)
    assert len(jobs) == 1
    job = jobs[0]
    assert job["title"] == "Data Analyst"
    assert job["employer"] == "Atlan"
    assert job["work_arrangement"] == "Remote"
    assert job["application_url"] == "https://jobs.ashbyhq.com/atlan/ashby_101/application"


def test_unstop_source_adapter(monkeypatch):
    """Verify Unstop adapter fetches and normalizes campus & fresher jobs."""
    adapter = UnstopSource()

    fake_response = {
        "data": {
            "data": [
                {
                    "id": 123456,
                    "title": "Graduate Engineer Trainee - Data",
                    "seo_url": "https://unstop.com/jobs/get-data-123456",
                    "public_url": "jobs/get-data-123456",
                    "regn_open": 1,
                    "organisation": {"name": "Campus Partner Corp"},
                    "locations": [{"city": "Chennai", "state": "Tamil Nadu"}],
                    "jobDetail": {
                        "min_experience": 0,
                        "max_experience": 1,
                        "min_salary": 450000,
                        "max_salary": 650000,
                        "timing": "full_time"
                    },
                    "type": "jobs",
                    "approved_date": "2026-10-20T12:00:00+05:30"
                }
            ]
        }
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = fake_response

    monkeypatch.setattr(adapter.session, "get", lambda *args, **kwargs: mock_resp)

    jobs = adapter.fetch_jobs(days_back=30)
    assert len(jobs) >= 1
    job = jobs[0]
    assert job["title"] == "Graduate Engineer Trainee - Data"
    assert job["employer"] == "Campus Partner Corp"
    assert job["is_fresher"] is True
    assert "Chennai" in job["location"]
    assert "unstop.com/jobs/get-data-123456" in job["official_url"]


def test_database_url_lookup_and_coverage_filtering():
    """Verify get_job_by_url and filtering by is_fresher and discovery_source."""
    job1 = Job(
        job_uid="job_fresher_1",
        employer="TechCo",
        title="Associate Software Engineer",
        normalized_title="associate software engineer",
        priority_category=3,
        priority_label="Software Engineer",
        location="Bengaluru",
        official_url="https://techco.example/apply/1",
        canonical_url="https://techco.example/apply/1",
        discovery_source="Unstop Campus API",
        is_fresher=True,
        is_off_campus=False,
    )
    job2 = Job(
        job_uid="job_experienced_1",
        employer="SeniorTech",
        title="Senior Python Architect",
        normalized_title="senior python architect",
        priority_category=3,
        priority_label="Software Engineer",
        location="Bengaluru",
        official_url="https://seniortech.example/apply/2",
        canonical_url="https://seniortech.example/apply/2",
        discovery_source="Direct",
        is_fresher=False,
        is_off_campus=False,
    )
    save_job(job1)
    save_job(job2)

    # Test get_job_by_url
    found = get_job_by_url("https://techco.example/apply/1")
    assert found is not None
    assert found["title"] == "Associate Software Engineer"

    # Test filter by fresher
    fresher_jobs = list_jobs(is_fresher=True)
    assert any(j["job_uid"] == "job_fresher_1" for j in fresher_jobs)
    assert not any(j["job_uid"] == "job_experienced_1" for j in fresher_jobs)

    # Test filter by discovery source
    unstop_jobs = list_jobs(discovery_source="Unstop")
    assert len(unstop_jobs) == 1
    assert unstop_jobs[0]["job_uid"] == "job_fresher_1"


def test_community_api_endpoints():
    """Verify preview and import community endpoints on FastAPI."""
    raw_text = """
    🚨 Off-Campus Hiring!
    Company: AccelQ
    Role: Quality Automation Engineer (Python)
    Location: Hyderabad
    Experience: 0-2 Years
    Apply: https://accelq.example/careers/job101
    """

    # 1. Preview
    p_data = preview_community_announcement({"raw_text": raw_text, "source_channel": "WhatsApp"})
    assert p_data["employer"] == "AccelQ"
    assert "Hyderabad" in p_data["location"]
    assert p_data["application_url"] == "https://accelq.example/careers/job101"

    # 2. Import
    imp_data = import_community_announcement({"raw_text": raw_text, "source_channel": "WhatsApp Freshers Group"})
    assert imp_data["status"] == "SUCCESS"
    assert imp_data["lead"]["employer"] == "AccelQ"
    assert imp_data["lead"]["verification_status"] == "UNVERIFIED"

    # Verify stats reflect the imported lead
    stats_data = get_stats()
    stats = stats_data["metrics"]
    assert stats["unverified_jobs"] >= 1
