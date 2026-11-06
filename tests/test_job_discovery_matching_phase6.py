"""Phase 6 verification test suite for Job Discovery & Matching Audit.

Verifies:
1. Source registry health monitoring & all 32 sources.
2. Canonical URL normalization and deduplication merge rules.
3. Strict adherence to the 6-factor matching rubric (30/20/15/15/10/10).
4. Mandatory disqualifiers (unpaid, over-seniority, international without India auth, closed vacancy).
5. India-first geographic tiering and priority sorting.
"""
from datetime import datetime, timedelta, timezone
import pytest
from careerorbit.database.db import (
    init_db,
    list_job_sources,
    get_job_source,
    save_job_source,
    update_job_source_health,
    toggle_job_source_enabled,
)
from careerorbit.dedup.deduplicator import Deduplicator
from careerorbit.matcher.scorer import JobScorer
from careerorbit.matcher.geo import classify_geographic_priority
from careerorbit.models.schemas import MatchTier, VerificationStatus, ScoreBreakdown


@pytest.fixture(autouse=True)
def setup_test_db():
    """Initializes the database schema for the test."""
    init_db()


@pytest.fixture
def scorer():
    return JobScorer()


# ---------------- 1. Source Registry & Health Monitoring ----------------

def test_source_registry_complete_32_sources():
    """Verifies that all 32 configured job discovery sources are registered."""
    sources = list_job_sources()
    assert len(sources) >= 32, f"Expected at least 32 job sources, got {len(sources)}"
    categories = set(s["category"] for s in sources)
    assert "EMPLOYER_ATS" in categories
    assert "PUBLIC_AGGREGATOR" in categories


def test_source_health_transition_and_recovery():
    """Verifies that source health transitions on errors and recovers on success."""
    test_src_id = "test-phase6-source"
    save_job_source({
        "source_id": test_src_id,
        "source_name": "Phase 6 Test Source",
        "category": "EMPLOYER_ATS",
        "source_type": "GREENHOUSE",
        "endpoint_or_board_id": "test_board",
        "is_configured": True,
        "is_enabled": True,
        "health_status": "UNKNOWN",
    })

    # 1. Record error
    update_job_source_health(
        source_id=test_src_id,
        health_status="FAILING",
        error_category="HTTP_TIMEOUT",
        error_message="Gateway timeout connecting to ATS",
        success=False,
    )
    src = get_job_source(test_src_id)
    assert src["health_status"] == "FAILING"
    assert src["retry_count"] >= 1
    assert src["last_error_category"] == "HTTP_TIMEOUT"

    # 2. Record success / recovery
    update_job_source_health(
        source_id=test_src_id,
        health_status="HEALTHY",
        discovered_count=15,
        updated_count=4,
        rejected_count=1,
        deduped_count=2,
        success=True,
    )
    recovered = get_job_source(test_src_id)
    assert recovered["health_status"] == "HEALTHY"
    assert recovered["retry_count"] == 0
    assert recovered["last_error_category"] is None
    assert recovered["last_discovered_count"] == 15
    assert recovered["last_deduped_count"] == 2


def test_source_toggle_enabled():
    """Verifies enabling and disabling a job source persists."""
    src = list_job_sources()[0]
    sid = src["source_id"]
    initial_enabled = bool(src["is_enabled"])

    toggle_job_source_enabled(sid, not initial_enabled)
    updated = get_job_source(sid)
    assert bool(updated["is_enabled"]) == (not initial_enabled)

    # Restore
    toggle_job_source_enabled(sid, initial_enabled)


# ---------------- 2. Deduplication & Canonical URLs ----------------

def test_canonical_url_strips_tracking_params():
    """Verifies canonical URL normalization removes UTM tags, refId, and trailing slashes."""
    dirty_url = "https://boards.greenhouse.io/corp/jobs/12345/?utm_source=linkedin&utm_medium=job_post&ref=referral&refId=abc789"
    clean_url = Deduplicator.canonicalize_url(dirty_url)
    assert clean_url == "https://boards.greenhouse.io/corp/jobs/12345"
    assert "utm_source" not in clean_url
    assert "refId" not in clean_url


def test_company_normalization_removes_corporate_suffixes():
    """Verifies company normalization equates variations of corporate names."""
    c1 = Deduplicator.normalize_company_name("Acme Technologies India Pvt Ltd")
    c2 = Deduplicator.normalize_company_name("Acme Corp.")
    c3 = Deduplicator.normalize_company_name("Acme Solutions Inc")
    assert c1 == "acme"
    assert c2 == "acme"
    assert c3 == "acme"


def test_title_normalization_synonyms():
    """Verifies job title normalization unifies common abbreviations."""
    t1 = Deduplicator.normalize_job_title("Jr. SWE - Python (Remote)")
    t2 = Deduplicator.normalize_job_title("Junior Software Engineer - Python [Immediate]")
    assert t1 == "junior software engineer python"
    assert t2 == "junior software engineer python"


def test_dedup_merges_and_promotes_official_url():
    """Verifies that merging records promotes official ATS URLs over aggregator URLs."""
    existing_record = {
        "job_uid": "test_job_1",
        "employer": "TechCorp",
        "title": "Data Analyst",
        "official_url": "https://aggregator.example.com/job/123",
        "discovery_source": "Aggregator Feed",
        "match_score": 70.0,
    }
    incoming_record = {
        "job_uid": "test_job_1",
        "employer": "TechCorp",
        "title": "Data Analyst",
        "official_url": "https://boards.greenhouse.io/techcorp/jobs/999",
        "official_listing_url": "https://boards.greenhouse.io/techcorp/jobs/999",
        "discovery_source": "Greenhouse ATS",
        "match_score": 85.0,
    }
    merged, changed = Deduplicator.merge_job_records(existing_record, incoming_record)
    assert changed is True
    assert merged["official_url"] == "https://boards.greenhouse.io/techcorp/jobs/999"
    assert merged["match_score"] == 85.0
    assert "Aggregator Feed" in merged["discovery_source"]
    assert "Greenhouse ATS" in merged["discovery_source"]


# ---------------- 3. 6-Factor Matching Rubric Verification ----------------

def test_six_factor_rubric_weights_sum_to_100(scorer):
    """Verifies the exact 6-factor rubric: 30/20/15/15/10/10 summing to 100."""
    ideal_job = {
        "title": "Junior Data Analyst & Power BI Developer",
        "description": (
            "Entry level 0-1 year position for fresh graduates. Build Power BI dashboards, "
            "write optimized SQL queries, DAX measures, and Python pandas scripts. "
            "Experience with financial reporting, loan data, or sales dashboards is highly desirable. "
            "B.E. degree in Engineering required."
        ),
        "location": "Bengaluru, Karnataka",
        "work_arrangement": "Hybrid",
        "posting_date": datetime.now(timezone.utc).isoformat(),
        "posting_date_confidence": "SOURCE_REPORTED",
        "verification_status": VerificationStatus.VERIFIED_OPEN.value,
    }

    result = scorer.score_job(ideal_job)
    breakdown = result["score_breakdown"]

    # Maximum factor allocations
    assert breakdown.skills_and_projects <= 30.0, "Skills and projects factor exceeded max 30"
    assert breakdown.experience_compatibility <= 20.0, "Experience compatibility factor exceeded max 20"
    assert breakdown.eligibility <= 15.0, "Eligibility factor exceeded max 15"
    assert breakdown.freshness_and_availability <= 15.0, "Freshness factor exceeded max 15"
    assert breakdown.location_and_arrangement <= 10.0, "Location factor exceeded max 10"
    assert breakdown.evidence_and_realistic_fit <= 10.0, "Evidence factor exceeded max 10"

    # Perfect scenario should reach maximum in each component
    assert breakdown.skills_and_projects == 30.0
    assert breakdown.experience_compatibility == 20.0
    assert breakdown.eligibility == 15.0
    assert breakdown.freshness_and_availability == 15.0
    assert breakdown.location_and_arrangement == 10.0
    assert breakdown.evidence_and_realistic_fit == 10.0
    assert breakdown.total == 100.0


def test_mandatory_disqualifier_unpaid_position(scorer):
    """Verifies that unpaid or zero-stipend positions are strictly disqualified."""
    job = {
        "title": "Data Analyst Intern (Unpaid)",
        "description": "Gain experience working with our data team. Stipend: None. Unpaid volunteer role.",
        "location": "Bengaluru",
        "work_arrangement": "Remote",
    }
    result = scorer.score_job(job)
    assert result["match_tier"] == MatchTier.INELIGIBLE
    assert any("Unpaid position" in d for d in result["disqualifiers"])


def test_mandatory_disqualifier_over_seniority(scorer):
    """Verifies that roles requiring >3 years experience or senior/lead titles are disqualified."""
    job1 = {
        "title": "Senior Data Architect",
        "description": "Requires 5+ years of production cloud data engineering experience.",
        "location": "Bengaluru",
    }
    result1 = scorer.score_job(job1)
    assert result1["match_tier"] == MatchTier.INELIGIBLE
    assert any("Senior role" in d or "Experience requirement" in d for d in result1["disqualifiers"])

    job2 = {
        "title": "Data Analyst",
        "description": "Minimum 4-6 years of experience in enterprise data warehousing.",
        "location": "Bengaluru",
    }
    result2 = scorer.score_job(job2)
    assert result2["match_tier"] == MatchTier.INELIGIBLE
    assert any("4+ years" in d or "exceeds early-career" in d for d in result2["disqualifiers"])


def test_mandatory_disqualifier_closed_vacancy(scorer):
    """Verifies that vacancies verified closed are disqualified with 0 freshness score."""
    job = {
        "title": "Junior Data Analyst",
        "description": "SQL and Python reporting role for freshers.",
        "location": "Bengaluru",
        "verification_status": VerificationStatus.VERIFIED_CLOSED.value,
    }
    result = scorer.score_job(job)
    assert result["match_tier"] == MatchTier.INELIGIBLE
    assert result["score_breakdown"].freshness_and_availability == 0.0
    assert any("closed" in d.lower() for d in result["disqualifiers"])


# ---------------- 4. India-First Geographic Prioritization ----------------

def test_india_first_geographic_priority_hierarchy():
    """Verifies South India metros and confirmed India-remote are Priority 1."""
    # Bengaluru (P1)
    geo_blr = classify_geographic_priority("Bengaluru, Karnataka", "Hybrid", "")
    assert geo_blr["geographic_priority"] == 1
    assert geo_blr["geo_score"] == 10.0

    # Chennai (P1)
    geo_che = classify_geographic_priority("Chennai, Tamil Nadu", "Onsite", "")
    assert geo_che["geographic_priority"] == 1
    assert geo_che["geo_score"] == 10.0

    # Coimbatore (P1)
    geo_cbe = classify_geographic_priority("Coimbatore", "Onsite", "")
    assert geo_cbe["geographic_priority"] == 1
    assert geo_cbe["geo_score"] == 10.0

    # Pune / Mumbai / Delhi NCR (P3)
    geo_pune = classify_geographic_priority("Pune, Maharashtra", "Onsite", "")
    assert geo_pune["geographic_priority"] == 3
    assert geo_pune["geo_score"] == 7.0

    # International on-site without India work auth (Disqualified)
    geo_us = classify_geographic_priority("New York, NY, USA", "Onsite", "")
    assert geo_us["is_disqualified"] is True
