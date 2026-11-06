"""Tests for duplicate detection, URL canonicalization, and official-source verification."""
import pytest
from careerorbit.dedup.deduplicator import Deduplicator
from careerorbit.verifier.checker import VerificationEngine
from careerorbit.models.schemas import VerificationStatus

def test_company_and_title_normalization():
    norm_comp = Deduplicator.normalize_company_name("Caterpillar India Pvt Ltd")
    assert norm_comp == "caterpillar"

    norm_title = Deduplicator.normalize_job_title("Junior Python Dev (m/f/d) - Remote")
    assert "junior python developer" in norm_title

def test_canonicalize_url():
    raw_url = "https://jobs.lever.co/company/abc-123?utm_source=linkedin&utm_medium=job_post&ref=partner"
    clean_url = Deduplicator.canonicalize_url(raw_url)
    assert "utm_source" not in clean_url
    assert "utm_medium" not in clean_url
    assert "jobs.lever.co/company/abc-123" in clean_url

def test_job_uid_generation():
    uid1 = Deduplicator.generate_job_uid("Bosch Global Technologies", "Power BI Developer", "REQ-101", "Coimbatore")
    uid2 = Deduplicator.generate_job_uid("Bosch Group", "Power BI Developer", "REQ-101", "Coimbatore")
    # With same REQ number, they resolve to identical UID
    assert uid1 == uid2

def test_dedup_merge_preserves_official_url():
    existing = {
        "employer": "TechCorp",
        "official_url": "https://indeed.com/viewjob?id=123",
        "verification_status": "UNVERIFIED",
        "match_score": 60.0
    }
    incoming = {
        "official_url": "https://techcorp.wd5.myworkdayjobs.com/careers/job123",
        "verification_status": "VERIFIED_OPEN",
        "verification_notes": "Official workday page open",
        "match_score": 75.0
    }
    merged, changed = Deduplicator.merge_job_records(existing, incoming)
    assert changed is True
    assert "myworkdayjobs.com" in merged["official_url"]
    assert merged["verification_status"] == "VERIFIED_OPEN"

def test_verifier_domain_detection():
    verifier = VerificationEngine()
    assert verifier.is_official_employer_url("https://company.greenhouse.io/job/123") is True
    assert verifier.is_official_employer_url("https://caterpillar.wd5.myworkdayjobs.com/careers") is True
    assert verifier.is_official_employer_url("https://www.naukri.com/job-listings") is False
    assert verifier.is_official_employer_url("https://in.indeed.com/viewjob") is False
    assert verifier.is_official_employer_url("https://notgreenhouse.io/job/123") is False

def test_verifier_rejects_non_https_and_private_targets_without_fetching():
    verifier = VerificationEngine()
    status, _ = verifier.verify_listing("http://127.0.0.1:8000/")
    assert status == VerificationStatus.STATUS_UNKNOWN

def test_verifier_does_not_treat_unknown_company_domain_as_official():
    verifier = VerificationEngine()
    assert verifier.is_official_employer_url("https://careers.example.com/jobs/123") is False

def test_recheck_active_leads():
    from unittest.mock import patch
    from careerorbit.verifier.checker import recheck_active_leads, JobVerifier
    from careerorbit.database.db import get_connection, init_db, save_job
    from careerorbit.models.schemas import Job

    init_db()
    job = Job(
        job_uid="test_recheck_uid_123",
        employer="GitHub",
        title="Data Analyst",
        normalized_title="data analyst",
        priority_category=1,
        priority_label="Data Analyst",
        location="Bengaluru, Karnataka",
        work_arrangement="Remote",
        official_url="https://jobs.lever.co/github/test-123",
        official_listing_url="https://jobs.lever.co/github/test-123",
        canonical_url="https://jobs.lever.co/github/test-123",
        discovery_source="Lever ATS",
        verification_status=VerificationStatus.UNVERIFIED,
        record_state="DISCOVERY_LEAD"
    )
    save_job(job)

    # Set last_verified_at to an older date so it is picked up for rechecking
    conn = get_connection()
    conn.cursor().execute("UPDATE jobs SET last_verified_at = '2026-01-01T00:00:00+00:00' WHERE job_uid = 'test_recheck_uid_123'")
    conn.commit()
    conn.close()

    # Mock verify_listing to return VERIFIED_OPEN
    with patch.object(JobVerifier, "verify_listing", return_value=(VerificationStatus.VERIFIED_OPEN, "Mocked 200 OK")):
        res = recheck_active_leads(max_jobs=5, days_threshold=7)
        assert res["checked"] >= 1
        assert res["verified_open"] >= 1

        # Verify DB was updated
        conn = get_connection()
        row = conn.cursor().execute(
            "SELECT verification_status, last_verified_at, verification_source FROM jobs WHERE job_uid = 'test_recheck_uid_123'"
        ).fetchone()
        conn.close()
        assert row["verification_status"] == "VERIFIED_OPEN"
        assert row["last_verified_at"] is not None
        assert row["verification_source"] == "Weekly Link Verification"


def test_recheck_active_leads_prioritizes_unverified_without_waiting_7_days():
    from unittest.mock import patch
    from datetime import datetime, timezone
    from careerorbit.verifier.checker import recheck_active_leads, JobVerifier
    from careerorbit.database.db import get_connection, init_db, save_job
    from careerorbit.models.schemas import Job

    init_db()
    now_iso = datetime.now(timezone.utc).isoformat()
    job = Job(
        job_uid="test_fresh_unverified_job_uid_999",
        employer="Test Corp",
        title="Junior Data Analyst",
        normalized_title="junior data analyst",
        priority_category=1,
        priority_label="Data Analyst",
        location="Bengaluru, Karnataka",
        work_arrangement="Remote",
        official_url="https://jobs.lever.co/testcorp/recent-job",
        official_listing_url="https://jobs.lever.co/testcorp/recent-job",
        application_url="https://jobs.lever.co/testcorp/recent-job/apply",
        canonical_url="https://jobs.lever.co/testcorp/recent-job",
        discovery_source="Telegram Export",
        verification_status=VerificationStatus.UNVERIFIED,
        record_state="DISCOVERY_LEAD"
    )
    save_job(job)

    # Set last_verified_at to today (0 days old)
    conn = get_connection()
    conn.cursor().execute(
        "UPDATE jobs SET last_verified_at = ? WHERE job_uid = 'test_fresh_unverified_job_uid_999'",
        (now_iso,)
    )
    conn.commit()
    conn.close()

    # Even though last_verified_at is fresh (< 7 days), it should be checked because status is UNVERIFIED
    with patch.object(JobVerifier, "verify_listing", return_value=(VerificationStatus.VERIFIED_CLOSED, "Application URL returned HTTP 404")):
        res = recheck_active_leads(max_jobs=10, days_threshold=7)
        assert res["checked"] >= 1
        assert res["verified_closed"] >= 1

        conn = get_connection()
        row = conn.cursor().execute(
            "SELECT verification_status, verification_notes FROM jobs WHERE job_uid = 'test_fresh_unverified_job_uid_999'"
        ).fetchone()
        conn.close()
        assert row["verification_status"] == "VERIFIED_CLOSED"
        assert "404" in row["verification_notes"]


