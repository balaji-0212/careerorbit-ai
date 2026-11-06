"""Comprehensive Test Suite for India-First Geographic Priorities and Location Screening."""
import pytest
from datetime import datetime, timezone, timedelta
from careerorbit.matcher.geo import classify_geographic_priority
from careerorbit.matcher.scorer import JobScorer
from careerorbit.models.schemas import MatchTier, VerificationStatus, Job
from careerorbit.database.db import init_db, save_job, list_jobs, get_job_stats


def test_priority1_major_south_indian_tech_hubs():
    """Bengaluru, Chennai, Coimbatore, Hyderabad must classify as Priority 1 with 10.0 score."""
    primary_cities = [
        ("Bengaluru, Karnataka, India", "On-site", "Bengaluru", "Karnataka"),
        ("Bangalore", "Hybrid", "Bengaluru", "Karnataka"),
        ("Chennai, Tamil Nadu", "On-site", "Chennai", "Tamil Nadu"),
        ("Coimbatore, Tamil Nadu", "On-site", "Coimbatore", "Tamil Nadu"),
        ("Hyderabad, Telangana", "Hybrid", "Hyderabad", "Telangana"),
    ]
    for loc, arr, expected_city, expected_state in primary_cities:
        res = classify_geographic_priority(loc, arr)
        assert res["geographic_priority"] == 1, f"Failed for {loc}"
        assert res["geo_score"] == 10.0, f"Score failed for {loc}"
        assert res["city"] == expected_city
        assert res["state"] == expected_state
        assert res["location_eligibility_status"] == "VERIFIED_INDIA_ELIGIBLE"
        assert not res["is_disqualified"]


def test_priority2_home_and_south_indian_locations():
    """Cuddalore (home), Puducherry, Kochi, Mysuru must classify as Priority 2."""
    regional_cities = [
        ("Cuddalore, Tamil Nadu", "On-site", "Cuddalore", 9.0),
        ("Puducherry", "On-site", "Puducherry", 9.0),
        ("Kochi, Kerala", "Hybrid", "Kochi", 8.5),
        ("Mysuru, Karnataka", "On-site", "Mysuru", 8.5),
        ("Tiruchirappalli, Tamil Nadu", "On-site", "Tiruchirappalli", 8.5),
        ("Madurai, Tamil Nadu", "On-site", "Madurai", 8.5),
    ]
    for loc, arr, expected_city, expected_score in regional_cities:
        res = classify_geographic_priority(loc, arr)
        assert res["geographic_priority"] == 2, f"Failed for {loc}"
        assert res["geo_score"] == expected_score, f"Score failed for {loc}"
        assert res["city"] == expected_city
        assert res["location_eligibility_status"] == "VERIFIED_INDIA_ELIGIBLE"
        assert not res["is_disqualified"]


def test_priority1_confirmed_india_remote_and_worldwide():
    """Remote positions explicitly available in India or Worldwide must classify as Priority 1."""
    remote_cases = [
        ("Remote - India", "Remote", "India"),
        ("Remote (India)", "Remote", "India"),
        ("India", "Remote", "India"),
        ("Worldwide", "Remote", "India"),
        ("Anywhere in India", "Remote", "India"),
    ]
    for loc, arr, expected_country in remote_cases:
        res = classify_geographic_priority(loc, arr)
        assert res["geographic_priority"] == 1, f"Failed for {loc}"
        assert res["geo_score"] == 10.0
        assert res["location_eligibility_status"] == "VERIFIED_INDIA_ELIGIBLE"
        assert res["remote_eligibility"] == "INDIA_PERMITTED"
        assert not res["is_disqualified"]


def test_priority3_other_indian_technology_hubs():
    """Pune, Mumbai, Delhi NCR, Noida, Gurugram, Ahmedabad, Kolkata must classify as Priority 3."""
    p3_cities = [
        ("Pune, Maharashtra", "Hybrid", "Pune", "Maharashtra"),
        ("Mumbai, Maharashtra", "On-site", "Mumbai", "Maharashtra"),
        ("Noida, Uttar Pradesh", "Hybrid", "Noida", "Uttar Pradesh"),
        ("Gurugram, Haryana", "On-site", "Gurugram", "Haryana"),
        ("Delhi NCR", "Hybrid", "Delhi", "Delhi NCR"),
        ("Ahmedabad, Gujarat", "On-site", "Ahmedabad", "Gujarat"),
        ("Kolkata, West Bengal", "On-site", "Kolkata", "West Bengal"),
        ("Indore, Madhya Pradesh", "On-site", "Indore", "Madhya Pradesh"),
        ("Chandigarh", "Hybrid", "Chandigarh", "Chandigarh"),
    ]
    for loc, arr, expected_city, expected_state in p3_cities:
        res = classify_geographic_priority(loc, arr)
        assert res["geographic_priority"] == 3, f"Failed for {loc}"
        assert res["geo_score"] == 7.0, f"Score failed for {loc}"
        assert res["city"] == expected_city
        assert res["state"] == expected_state
        assert res["location_eligibility_status"] == "VERIFIED_INDIA_ELIGIBLE"
        assert not res["is_disqualified"]


def test_bare_remote_without_india_confirmation_is_marked_unconfirmed():
    """A position that simply says 'Remote' without India authorization must be tagged UNCONFIRMED."""
    res = classify_geographic_priority("Remote", "Remote")
    assert res["geographic_priority"] == 4
    assert res["location_eligibility_status"] == "LOCATION_ELIGIBILITY_UNCONFIRMED"
    assert res["remote_eligibility"] == "LOCATION_ELIGIBILITY_UNCONFIRMED"
    assert res["geo_score"] == 0.0
    assert not res["is_disqualified"]


def test_overseas_restricted_locations_are_disqualified():
    """Positions restricted to US only, Europe only, etc. must be marked restricted and disqualified."""
    restricted = [
        ("United States only", "Remote"),
        ("USA only", "Remote"),
        ("Canada only", "Remote"),
        ("UK only", "Remote"),
        ("Europe only", "Remote"),
        ("San Francisco, CA", "On-site"),
        ("New York, NY", "On-site"),
    ]
    for loc, arr in restricted:
        res = classify_geographic_priority(loc, arr)
        assert res["geographic_priority"] == 4
        assert res["is_disqualified"] is True
        assert res["geo_score"] == 0.0


def test_international_with_visa_sponsorship_is_priority4_eligible():
    """International opportunity with explicit visa sponsorship must be Priority 4 with 4.0 points."""
    res = classify_geographic_priority(
        "London, UK", "On-site",
        description="Full visa sponsorship and relocation package provided for international candidates."
    )
    assert res["geographic_priority"] == 4
    assert res["location_eligibility_status"] == "VERIFIED_INTERNATIONAL_ELIGIBLE"
    assert res["geo_score"] == 4.0
    assert res["is_disqualified"] is False


def test_career_priority_sorting_with_geographic_subranking():
    """Within the same role tier, Priority 1 geographic locations rank above Priority 2 and 3."""
    init_db()
    now_iso = datetime.now(timezone.utc).isoformat()
    # Save 3 Data Analyst jobs with different geographic priorities
    p1_job = Job(
        job_uid=f"geo-p1-test-{int(datetime.now(timezone.utc).timestamp())}",
        employer="P1 Tech",
        title="Junior Data Analyst",
        normalized_title="junior data analyst",
        priority_category=1,
        priority_label="Data Analyst",
        location="Bengaluru, Karnataka",
        work_arrangement="Hybrid",
        official_url="https://example.com/p1",
        canonical_url="https://example.com/p1",
        discovery_source="Jobicy Public API",
        verification_status=VerificationStatus.UNVERIFIED,
        match_score=85.0,
        match_tier=MatchTier.STRONG_MATCH,
        posting_date=now_iso,
        geographic_priority=1,
        city="Bengaluru"
    )
    p2_job = Job(
        job_uid=f"geo-p2-test-{int(datetime.now(timezone.utc).timestamp())}",
        employer="P2 Tech",
        title="Junior Data Analyst",
        normalized_title="junior data analyst",
        priority_category=1,
        priority_label="Data Analyst",
        location="Pune, Maharashtra",
        work_arrangement="Hybrid",
        official_url="https://example.com/p2",
        canonical_url="https://example.com/p2",
        discovery_source="Jobicy Public API",
        verification_status=VerificationStatus.UNVERIFIED,
        match_score=88.0,  # Higher raw score, but P2 geo
        match_tier=MatchTier.STRONG_MATCH,
        posting_date=now_iso,
        geographic_priority=2,
        city="Pune"
    )
    save_job(p1_job)
    save_job(p2_job)

    # list_jobs with default priority_first
    results = list_jobs(priority=1, limit=20)
    uids = [j["job_uid"] for j in results]
    assert p1_job.job_uid in uids
    assert p2_job.job_uid in uids

    p1_idx = uids.index(p1_job.job_uid)
    p2_idx = uids.index(p2_job.job_uid)
    assert p1_idx < p2_idx, "Priority 1 geographic job must rank ahead of Priority 2 within same career tier!"


def test_geographic_and_recency_filters():
    """list_jobs must filter correctly by geographic_priority, city, and recency_days."""
    init_db()
    now_iso = datetime.now(timezone.utc).isoformat()
    save_job(Job(
        job_uid="filter-test-p1", employer="F1", title="Data Analyst", normalized_title="data analyst",
        priority_category=1, location="Bengaluru", work_arrangement="On-site", official_url="http://x",
        canonical_url="http://x", discovery_source="Jobicy Public API", geographic_priority=1, city="Bengaluru",
        posting_date=now_iso
    ))
    save_job(Job(
        job_uid="filter-test-p2", employer="F2", title="Data Analyst", normalized_title="data analyst",
        priority_category=1, location="Pune", work_arrangement="Hybrid", official_url="http://y",
        canonical_url="http://y", discovery_source="Jobicy Public API", geographic_priority=2, city="Pune",
        posting_date=(datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    ))
    p1_jobs = list_jobs(geographic_priority=1, limit=50)
    for j in p1_jobs:
        assert j["geographic_priority"] == 1

    p2_jobs = list_jobs(geographic_priority=2, limit=50)
    for j in p2_jobs:
        assert j["geographic_priority"] == 2

    recent_jobs = list_jobs(recency_days=7, limit=50)
    now = datetime.now(timezone.utc)
    for j in recent_jobs:
        if j.get("posting_date"):
            dt = datetime.fromisoformat(j["posting_date"].replace("Z", "+00:00"))
            assert dt >= now - timedelta(days=7, hours=1)
