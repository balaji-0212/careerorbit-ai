"""Step 4 Comprehensive Acceptance Test Suite.

End-to-End Job Discovery, Source Reliability, Database Integrity, and Report Reconciliation.
Verifies Scenarios A through L according to audit requirements:
- Scenario A: Successful live/mock discovery normalization & Fi Money slug compatibility
- Scenario B: Valid zero-results handling (recorded as 'ok', not error)
- Scenario C: Source failure handling, error categorization, and source isolation
- Scenario D: Unconfigured source handling (recorded as 'skipped')
- Scenario E: Invalid data screening and quarantine
- Scenario F: Repeated discovery deduplication & idempotency
- Scenario G: Verification status evidence preservation against transient errors
- Scenario H: Definitive vacancy closure transition
- Scenario I: Eligibility decoupling & personalized preference ranking
- Scenario J: Recommendation predicate & database reconciliation
- Scenario K: Existing database integrity & data preservation
- Scenario L: Crash recovery, transaction atomicity, and schema stability
"""

import json
from pathlib import Path
import sqlite3
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import pytest
import requests

from careerorbit.career_priorities import (
    get_personalized_priority_order_sql,
    get_preference_rank,
    load_user_career_preferences,
    save_user_career_preferences,
)
from careerorbit.database.db import (
    get_connection,
    get_job_by_uid,
    get_job_stats,
    init_db,
    save_job,
)
from careerorbit.dedup.deduplicator import Deduplicator
from careerorbit.discovery.engine import JobDiscoveryEngine
from careerorbit.discovery.sources import (
    AshbyJobBoardSource,
    BaseJobSource,
    EmployerDirectVerifiedSource,
    GreenhouseBoardSource,
    LeverSiteSource,
    RemoteOKSource,
    SmartRecruitersSource,
    UnstopSource,
    screen_job_for_candidate,
)
from careerorbit.eligibility import (
    RECOMMENDABLE_SQL_PREDICATE,
    is_recommendable,
    classify_title_to_priority,
)
from careerorbit.models.schemas import Job, VerificationStatus, MatchTier

ROOT_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def setup_db():
    init_db()


# ---------------------------------------------------------------------------
# Scenario A: Successful Discovery Normalization & Fi Money Compatibility
# ---------------------------------------------------------------------------

def test_scenario_a_successful_discovery_normalization():
    """Verifies that discovery normalizes jobs correctly and Lever handles Fi Money slug 'epifi'."""
    # Test Fi Money initialization and execution without company-slug equality ValueError
    source = LeverSiteSource(company="Fi Money", site_slug="epifi")
    assert source.configured is True

    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {
            "id": "lever-job-001",
            "text": "Software Development Engineer - Backend",
            "hostedUrl": "https://jobs.lever.co/epifi/lever-job-001",
            "applyUrl": "https://jobs.lever.co/epifi/lever-job-001/apply",
            "createdAt": now_ms,
            "categories": {
                "location": "Bengaluru, India",
                "commitment": "Full-time",
            },
            "descriptionPlain": "Building distributed fintech infrastructure in Bengaluru.",
        }
    ]

    with patch.object(source.session, "get", return_value=mock_resp):
        jobs = source.fetch_jobs(days_back=30)
        assert len(jobs) == 1
        j = jobs[0]
        assert j["employer"] == "Fi Money"
        assert j["title"] == "Software Development Engineer - Backend"
        assert "Bengaluru" in j["location"]
        assert j["priority_category"] == 3
        assert j["priority_label"] == "Software Engineer / Associate Software Engineer / Junior Developer"
        assert j["canonical_url"] == "https://jobs.lever.co/epifi/lever-job-001/apply"
        assert j["posting_date_confidence"] == "API_REPORTED"


# ---------------------------------------------------------------------------
# Scenario B: Valid Zero-Results Handling
# ---------------------------------------------------------------------------

def test_scenario_b_zero_results_recorded_as_ok():
    """Verifies that a valid HTTP 200 response with zero postings is recorded as 'ok', not failed."""
    source = LeverSiteSource(company="Fi Money", site_slug="epifi")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = []

    with patch.object(source.session, "get", return_value=mock_resp):
        jobs = source.fetch_jobs(days_back=7)
        assert jobs == []

    # Run discovery engine with mock empty source
    engine = JobDiscoveryEngine()
    engine.sources = [source]

    with patch.object(source.session, "get", return_value=mock_resp):
        results = engine.run_discovery(initial_days=7, min_acceptable=1)
        src_status = results["sources"].get(source.name, {})
        assert src_status.get("status") == "ok"
        assert src_status.get("count") == 0
        assert src_status.get("error") is None


# ---------------------------------------------------------------------------
# Scenario C: Source Failure Handling, Error Categorization, and Isolation
# ---------------------------------------------------------------------------

def test_scenario_c_source_failure_handling_and_isolation():
    """Verifies that failing sources raise exceptions, are categorized as 'failed', and do not crash the run."""
    failing_source = AshbyJobBoardSource(company="FailingCorp", board_token="broken-board")
    mock_err_resp = MagicMock()
    mock_err_resp.status_code = 503
    mock_err = requests.HTTPError(response=mock_err_resp)

    # In isolation, fetch_jobs now propagates the HTTP error rather than swallowing it
    with patch.object(failing_source.session, "get", side_effect=mock_err):
        with pytest.raises(requests.HTTPError):
            failing_source.fetch_jobs(days_back=7)

    # In engine, the failing source is captured as failed and does not abort healthy sources
    healthy_source = LeverSiteSource(company="HealthyCorp", site_slug="healthycorp")
    mock_ok_resp = MagicMock()
    mock_ok_resp.status_code = 200
    mock_ok_resp.json.return_value = []

    engine = JobDiscoveryEngine()
    engine.sources = [failing_source, healthy_source]

    def mock_get(url, *args, **kwargs):
        if "ashby" in url:
            raise mock_err
        return mock_ok_resp

    with patch.object(requests.Session, "get", side_effect=mock_get):
        results = engine.run_discovery(initial_days=7, min_acceptable=1)
        sources_summary = results["sources"]
        assert sources_summary[failing_source.name]["status"] == "failed"
        assert sources_summary[failing_source.name]["error"] == "HTTPError"
        assert sources_summary[healthy_source.name]["status"] == "ok"


# ---------------------------------------------------------------------------
# Scenario D: Unconfigured Source Handling
# ---------------------------------------------------------------------------

def test_scenario_d_unconfigured_source_handling():
    """Verifies that unconfigured sources report 'skipped' with appropriate reason."""
    unconfigured = EmployerDirectVerifiedSource()
    assert unconfigured.configured is False

    engine = JobDiscoveryEngine()
    engine.sources = [unconfigured]

    results = engine.run_discovery(initial_days=7, min_acceptable=1)
    status_entry = results["sources"][unconfigured.name]
    assert status_entry["status"] == "skipped"
    assert status_entry["count"] == 0
    assert "not configured" in status_entry.get("reason", "").lower() or "configured" in status_entry.get("reason", "").lower()


# ---------------------------------------------------------------------------
# Scenario E: Invalid Data Screening and Quarantine
# ---------------------------------------------------------------------------

def test_scenario_e_invalid_data_screening():
    """Verifies that non-technical, overseas, or over-seniority postings are screened out."""
    non_tech = {
        "title": "Creative Content Writer & Graphic Designer",
        "employer": "MediaCorp",
        "location": "Bengaluru, India",
        "description": "Create marketing collaterals and social media copy.",
    }
    assert screen_job_for_candidate(non_tech) == "title_not_in_career_priorities"

    over_senior = {
        "title": "Senior Software Development Engineer",
        "employer": "TechGiant",
        "location": "Bengaluru, India",
        "description": "Minimum 8+ years of experience leading software architecture.",
    }
    assert screen_job_for_candidate(over_senior) in ("seniority_out_of_scope", "experience_requirement_over_3_years")

    overseas = {
        "title": "Junior Python Developer",
        "employer": "EuroCorp",
        "location": "Berlin, Germany",
        "description": "On-site role in Berlin office only. No remote or India authorization.",
        "work_arrangement": "On-site",
    }
    assert screen_job_for_candidate(overseas) == "location_restricted_outside_india"


# ---------------------------------------------------------------------------
# Scenario F: Repeated Discovery Deduplication & Idempotency
# ---------------------------------------------------------------------------

def test_scenario_f_repeated_discovery_idempotency():
    """Verifies that running discovery multiple times with identical jobs does not create duplicates."""
    source = LeverSiteSource(company="Hevo Data", site_slug="hevodata")
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {
            "id": "hevo-sde-idemp",
            "text": "Associate Software Engineer",
            "hostedUrl": "https://jobs.lever.co/hevodata/hevo-sde-idemp",
            "applyUrl": "https://jobs.lever.co/hevodata/hevo-sde-idemp/apply",
            "createdAt": now_ms,
            "categories": {"location": "Bengaluru, India", "commitment": "Full-time"},
            "descriptionPlain": "Python software engineering.",
        }
    ]

    engine = JobDiscoveryEngine()
    engine.sources = [source]

    # Mock verifier to avoid live HTTP calls
    engine.verifier.verify_listing = MagicMock(return_value=(VerificationStatus.VERIFIED_OPEN, "Official Lever posting confirmed"))

    with patch.object(source.session, "get", return_value=mock_resp):
        res1 = engine.run_discovery(initial_days=7, min_acceptable=1)
        res2 = engine.run_discovery(initial_days=7, min_acceptable=1)

    assert res1["new_jobs_added"] >= 1 or res1["jobs_updated"] >= 1
    # Second run should identify the job as existing and update rather than duplicate
    assert res2["new_jobs_added"] == 0


# ---------------------------------------------------------------------------
# Scenario G: Verification Status Evidence Preservation
# ---------------------------------------------------------------------------

def test_scenario_g_verification_evidence_preservation():
    """Verifies that a VERIFIED_OPEN job is never downgraded by transient error or unverified leads."""
    existing_job = {
        "employer": "Atlan",
        "title": "Data Engineer",
        "official_url": "https://jobs.ashbyhq.com/atlan/de-01",
        "verification_status": "VERIFIED_OPEN",
        "verification_notes": "Confirmed on Ashby portal",
        "last_observed_status": "VERIFIED_OPEN",
        "last_observed_status_at": "2026-10-25T10:00:00+00:00",
    }

    # Transient check 1: Network Timeout / Rate limit (VERIFICATION_ERROR)
    transient_incoming = {
        "official_url": "https://jobs.ashbyhq.com/atlan/de-01",
        "verification_status": "VERIFICATION_ERROR",
        "verification_notes": "HTTP 429 Rate limited; automated check inconclusive",
        "last_observed_status": "VERIFICATION_ERROR",
        "last_observed_status_at": "2026-10-26T08:00:00+00:00",
    }
    merged, changed = Deduplicator.merge_job_records(existing_job, transient_incoming)

    # Verification status remains VERIFIED_OPEN
    assert merged["verification_status"] == "VERIFIED_OPEN"
    # Latest transient check is noted in last_observed_status
    assert merged["last_observed_status"] == "VERIFICATION_ERROR"
    assert merged["last_observed_status_at"] == "2026-10-26T08:00:00+00:00"

    # Transient check 2: New unverified aggregator lead (PENDING_VERIFICATION)
    unverified_lead = {
        "official_url": "https://jobs.ashbyhq.com/atlan/de-01",
        "verification_status": "PENDING_VERIFICATION",
        "verification_notes": "Awaiting verification",
        "last_observed_status": "PENDING_VERIFICATION",
        "last_observed_status_at": "2026-10-26T08:30:00+00:00",
    }
    merged2, changed2 = Deduplicator.merge_job_records(existing_job, unverified_lead)
    assert merged2["verification_status"] == "VERIFIED_OPEN"

    # Database defense-in-depth: test save_job UPSERT protection
    test_uid = "preservation_test_uid_001"
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM jobs WHERE job_uid = ?", (test_uid,))
    conn.commit()

    j_open = Job(
        job_uid=test_uid,
        employer="Test Corp",
        title="Software Engineer",
        normalized_title="software engineer",
        priority_category=3,
        location="Bengaluru, India",
        official_url="https://testcorp.com/careers/swe",
        canonical_url="https://testcorp.com/careers/swe",
        discovery_source="Test",
        verification_status=VerificationStatus.VERIFIED_OPEN,
        verification_notes="Initial verified open",
    )
    save_job(j_open)

    # Attempt to overwrite with VERIFICATION_ERROR via save_job directly
    j_error = Job(
        job_uid=test_uid,
        employer="Test Corp",
        title="Software Engineer",
        normalized_title="software engineer",
        priority_category=3,
        location="Bengaluru, India",
        official_url="https://testcorp.com/careers/swe",
        canonical_url="https://testcorp.com/careers/swe",
        discovery_source="Test",
        verification_status=VerificationStatus.VERIFICATION_ERROR,
        verification_notes="Attempted downgrade",
    )
    save_job(j_error)

    persisted = get_job_by_uid(test_uid)
    assert persisted is not None
    assert persisted["verification_status"] == "VERIFIED_OPEN"


# ---------------------------------------------------------------------------
# Scenario H: Definitive Vacancy Closure Transition
# ---------------------------------------------------------------------------

def test_scenario_h_definitive_closure_transition():
    """Verifies that a VERIFIED_OPEN job transitions to VERIFIED_CLOSED upon definitive closure."""
    existing_job = {
        "employer": "Stripe",
        "title": "Backend Engineer",
        "official_url": "https://stripe.com/jobs/123",
        "verification_status": "VERIFIED_OPEN",
        "verification_notes": "Open",
    }

    # Definitive closure (HTTP 404 or explicit closure text)
    closed_incoming = {
        "official_url": "https://stripe.com/jobs/123",
        "verification_status": "VERIFIED_CLOSED",
        "verification_notes": "HTTP 404 Not Found; vacancy is closed or removed",
        "last_observed_status": "VERIFIED_CLOSED",
        "last_observed_status_at": "2026-10-26T09:00:00+00:00",
    }

    merged, changed = Deduplicator.merge_job_records(existing_job, closed_incoming)
    assert changed is True
    assert merged["verification_status"] == "VERIFIED_CLOSED"
    assert "closed" in merged["verification_notes"].lower()


# ---------------------------------------------------------------------------
# Scenario I: Eligibility Decoupling & Personalized Ranking
# ---------------------------------------------------------------------------

def test_scenario_i_eligibility_decoupling_and_personalized_ranking():
    """Verifies that mandatory eligibility rules screen jobs regardless of user preference,
    and eligible recommendable jobs are ranked according to candidate preferences."""
    # Preference Profile A: Prioritize Data Analyst over Software Engineer
    prefs_a = ["data-analyst", "software-engineer"]
    # Preference Profile B: Prioritize Software Engineer over Data Analyst
    prefs_b = ["software-engineer", "data-analyst"]

    job_da = {
        "id": 1,
        "title": "Junior Data Analyst",
        "career_category": "data-analyst",
        "priority_category": 1,
        "priority_label": "Data Analyst / BI / Power BI / Reporting",
        "match_score": 75.0,
        "match_tier": "Strong match",
        "verification_status": "VERIFIED_OPEN",
        "record_state": "DISCOVERY_LEAD",
    }
    job_swe = {
        "id": 2,
        "title": "Software Engineer",
        "career_category": "software-engineer",
        "priority_category": 3,
        "priority_label": "Software Engineer / Associate Software Engineer / Junior Developer",
        "match_score": 85.0,
        "match_tier": "Strong match",
        "verification_status": "VERIFIED_OPEN",
        "record_state": "DISCOVERY_LEAD",
    }

    # Under Profile A, Data Analyst has rank 1, SWE has rank 2
    rank_da_a = get_preference_rank(job_da, preferences=prefs_a)
    rank_swe_a = get_preference_rank(job_swe, preferences=prefs_a)
    assert rank_da_a < rank_swe_a

    # Under Profile B, SWE has rank 1, Data Analyst has rank 2
    rank_da_b = get_preference_rank(job_da, preferences=prefs_b)
    rank_swe_b = get_preference_rank(job_swe, preferences=prefs_b)
    assert rank_swe_b < rank_da_b

    # Mandatory rule: An ineligible role is never recommended regardless of rank
    job_ineligible = {
        "id": 3,
        "title": "HR Specialist",
        "match_tier": "Ineligible",
        "verification_status": "VERIFIED_OPEN",
        "record_state": "DISCOVERY_LEAD",
    }
    assert is_recommendable(job_ineligible) is False


# ---------------------------------------------------------------------------
# Scenario J: Recommendation Predicate & Database Reconciliation
# ---------------------------------------------------------------------------

def test_scenario_j_recommendation_predicate_matches_db():
    """Verifies that is_recommendable() in Python matches RECOMMENDABLE_SQL_PREDICATE in SQLite."""
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # Query via SQL predicate
    c.execute(f"SELECT * FROM jobs WHERE {RECOMMENDABLE_SQL_PREDICATE}")
    sql_recommendable = [dict(r) for r in c.fetchall()]

    # Query all active jobs and filter via Python predicate
    c.execute("SELECT * FROM jobs")
    all_jobs = [dict(r) for r in c.fetchall()]
    py_recommendable = [j for j in all_jobs if is_recommendable(j)]

    assert len(sql_recommendable) == len(py_recommendable)
    sql_ids = {j["id"] for j in sql_recommendable}
    py_ids = {j["id"] for j in py_recommendable}
    assert sql_ids == py_ids


# ---------------------------------------------------------------------------
# Scenario K: Existing Data Preservation
# ---------------------------------------------------------------------------

def test_scenario_k_existing_data_preservation():
    """Verifies that baseline database records and relationships are undamaged."""
    # Verify the workspace production-like database directly on disk when present
    ws_db = ROOT_DIR / "data" / "careerorbit.db"
    if ws_db.is_file():
        conn = sqlite3.connect(ws_db)
        c = conn.cursor()

        # Schema integrity check
        c.execute("PRAGMA integrity_check")
        assert c.fetchone()[0] == "ok"

        # Foreign key check
        c.execute("PRAGMA foreign_key_check")
        assert c.fetchall() == []

        # Total jobs preserved
        c.execute("SELECT count(*) FROM jobs")
        total_jobs = c.fetchone()[0]
        assert total_jobs >= 100, f"Expected at least 100 jobs, found {total_jobs}"
        conn.close()

    # Always verify the runtime environment database schema and integrity
    test_conn = get_connection()
    tc = test_conn.cursor()
    tc.execute("PRAGMA integrity_check")
    assert tc.fetchone()[0] == "ok"
    tc.execute("PRAGMA foreign_key_check")
    assert tc.fetchall() == []


# ---------------------------------------------------------------------------
# Scenario L: Crash Recovery & Transaction Safety
# ---------------------------------------------------------------------------

def test_scenario_l_crash_recovery_transaction_safety():
    """Verifies that unhandled errors roll back cleanly without leaving corrupted state."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT count(*) FROM jobs")
    before_count = c.fetchone()[0]

    test_uid = "trans_safety_job_uid_999"
    try:
        with conn:
            c.execute(
                """INSERT INTO jobs (
                    job_uid, employer, title, normalized_title, priority_category, priority_label,
                    location, work_arrangement, official_url, canonical_url, discovery_source,
                    verification_status, match_tier, first_discovered_at, last_verified_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    test_uid, "Temp Corp", "Temp Title", "temp title", 3, "Software Engineer",
                    "Bengaluru, India", "Hybrid", "https://tempcorp.com/swe", "https://tempcorp.com/swe", "Test",
                    "VERIFIED_OPEN", "Strong match", "2026-10-26T00:00:00", "2026-10-26T00:00:00"
                )
            )
            # Deliberate failure within transaction
            raise RuntimeError("Simulated mid-pipeline crash")
    except RuntimeError:
        pass

    # Record should have been rolled back
    c.execute("SELECT * FROM jobs WHERE job_uid = ?", (test_uid,))
    assert c.fetchone() is None

    c.execute("SELECT count(*) FROM jobs")
    after_count = c.fetchone()[0]
    assert before_count == after_count

    c.execute("PRAGMA integrity_check")
    assert c.fetchone()[0] == "ok"
