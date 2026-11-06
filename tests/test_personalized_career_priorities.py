"""Comprehensive automated test suite for Personalized Career Priorities System.

Tests cover:
- Test A: Different profiles, different priorities (Profile A vs Profile B with comparable jobs).
- Test B: Reordering changes job rankings.
- Test C: Persistence across reloads and restarts.
- Test D: Scheduled discovery uses latest persisted preferences.
- Test E: Mandatory eligibility checks remain independent of preference rank.
- Test F: Lower-priority roles are considered and not rejected.
- Test G: Unsupported and unselected categories behavior.
- Test H: Invalid preference data validation.
- Test I: API endpoints read/write integration.
"""
import json
import pytest
from datetime import datetime, timezone
from pathlib import Path

from careerorbit.career_priorities import (
    CareerCategory,
    SUPPORTED_CATEGORIES,
    UserCareerPreferences,
    list_supported_categories,
    get_category_by_id,
    get_category_by_legacy_code,
    classify_job_category,
    get_preference_rank,
    get_personalized_priority_order_sql,
    load_user_career_preferences,
    save_user_career_preferences,
    reset_user_career_preferences,
    validate_preference_list,
    LEGACY_DEFAULT_CATEGORY_ORDER,
)
from careerorbit.database.db import (
    init_db,
    save_job,
    list_jobs,
    get_connection,
    save_career_preferences_db,
    get_career_preferences_db,
)
from careerorbit.models.schemas import (
    Job,
    VerificationStatus,
    MatchTier,
    ScoreBreakdown,
)
from careerorbit.matcher.scorer import JobScorer
from careerorbit.web.app import app


# ----------------- In-process ASGI Helper for API Testing -----------------

async def asgi_request(app, method="GET", path="/", query="", body=b"", headers=None):
    from tests.authenticated_request import authenticated_headers
    headers = authenticated_headers(method, headers)
    """In-process ASGI helper for hermetic API testing without external dependencies."""
    req_headers = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "path": path,
        "raw_path": path.encode(),
        "query_string": query.encode(),
        "headers": req_headers,
        "server": ("127.0.0.1", 8000),
        "client": ("127.0.0.1", 54321),
    }
    messages = []
    received = False

    async def receive():
        nonlocal received
        if not received:
            received = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        messages.append(message)

    await app(scope, receive, send)

    status_code = None
    response_headers = {}
    body_parts = []
    for m in messages:
        if m["type"] == "http.response.start":
            status_code = m["status"]
            response_headers = {k.decode().lower(): v.decode() for k, v in m.get("headers", [])}
        elif m["type"] == "http.response.body":
            body_parts.append(m.get("body", b""))

    return status_code, response_headers, b"".join(body_parts)


@pytest.fixture(autouse=True)
def setup_test_db():
    init_db()


def make_test_job(uid: str, title: str, employer: str, priority_category: int, score: float = 85.0) -> Job:
    """Helper to create an eligible test job."""
    return Job(
        job_uid=uid,
        employer=employer,
        title=title,
        normalized_title=title.lower(),
        priority_category=priority_category,
        priority_label=SUPPORTED_CATEGORIES[list(SUPPORTED_CATEGORIES.keys())[priority_category - 1]].label,
        location="Bengaluru, Karnataka, India",
        work_arrangement="Hybrid",
        official_url=f"https://careers.example.com/{uid}",
        canonical_url=f"https://careers.example.com/{uid}",
        discovery_source="Test Adapter",
        verification_status=VerificationStatus.VERIFIED_OPEN,
        match_score=score,
        match_tier=MatchTier.STRONG_MATCH,
        score_breakdown=ScoreBreakdown(
            skills_and_projects=30.0,
            experience_compatibility=20.0,
            eligibility=15.0,
            freshness_and_availability=10.0,
            location_and_arrangement=10.0,
            evidence_and_realistic_fit=score - 85.0 if score > 85.0 else 0.0,
            total=score,
        ),
        required_skills=["Python", "SQL"],
        supported_skills=["Python", "SQL"],
        description=f"Opportunity for {title} working on core technology."
    )


# ===========================================================================
# Test A: Different users, different priorities
# ===========================================================================

def test_a_different_profiles_different_priorities():
    """Verify Profile A and Profile B rank the exact same jobs according to their own preferences."""
    # Profile A prioritizes: Data Analyst -> Software Engineer -> Data Engineer
    prefs_a = UserCareerPreferences(
        profile_id="profile_a",
        selected_categories=["data_analyst", "software_engineer", "data_engineer"],
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
    save_user_career_preferences(prefs_a)

    # Profile B prioritizes: Software Engineer -> Data Engineer -> Data Analyst
    prefs_b = UserCareerPreferences(
        profile_id="profile_b",
        selected_categories=["software_engineer", "data_engineer", "data_analyst"],
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
    save_user_career_preferences(prefs_b)

    # Seed 3 comparable eligible jobs with identical match scores (85.0)
    job_da = make_test_job("job_da_001", "Junior Data Analyst", "Alpha Corp", 1, score=85.0)
    job_se = make_test_job("job_se_001", "Associate Software Engineer", "Beta Corp", 3, score=85.0)
    job_de = make_test_job("job_de_001", "Junior Data Engineer", "Gamma Corp", 5, score=85.0)
    save_job(job_da)
    save_job(job_se)
    save_job(job_de)

    # Query results for Profile A
    results_a = list_jobs(profile_id="profile_a", sort_by="priority_first")
    titles_a = [j["title"] for j in results_a if j["job_uid"] in ("job_da_001", "job_se_001", "job_de_001")]
    assert titles_a == [
        "Junior Data Analyst",
        "Associate Software Engineer",
        "Junior Data Engineer",
    ], f"Profile A failed expected ranking: {titles_a}"

    # Query results for Profile B
    results_b = list_jobs(profile_id="profile_b", sort_by="priority_first")
    titles_b = [j["title"] for j in results_b if j["job_uid"] in ("job_da_001", "job_se_001", "job_de_001")]
    assert titles_b == [
        "Associate Software Engineer",
        "Junior Data Engineer",
        "Junior Data Analyst",
    ], f"Profile B failed expected ranking: {titles_b}"

    # Verify Profile A and Profile B have completely independent preference ranks
    ranks_a = {j["title"]: j["preference_rank"] for j in results_a if j["job_uid"] in ("job_da_001", "job_se_001", "job_de_001")}
    assert ranks_a["Junior Data Analyst"] == 1
    assert ranks_a["Associate Software Engineer"] == 2
    assert ranks_a["Junior Data Engineer"] == 3

    ranks_b = {j["title"]: j["preference_rank"] for j in results_b if j["job_uid"] in ("job_da_001", "job_se_001", "job_de_001")}
    assert ranks_b["Associate Software Engineer"] == 1
    assert ranks_b["Junior Data Engineer"] == 2
    assert ranks_b["Junior Data Analyst"] == 3

    # Verify changing Profile A does NOT alter Profile B
    prefs_a_updated = UserCareerPreferences(
        profile_id="profile_a",
        selected_categories=["data_engineer", "data_analyst", "software_engineer"],
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
    save_user_career_preferences(prefs_a_updated)

    loaded_b = load_user_career_preferences("profile_b")
    assert loaded_b.selected_categories == ["software_engineer", "data_engineer", "data_analyst"]
    results_b_after = list_jobs(profile_id="profile_b", sort_by="priority_first")
    titles_b_after = [j["title"] for j in results_b_after if j["job_uid"] in ("job_da_001", "job_se_001", "job_de_001")]
    assert titles_b_after == [
        "Associate Software Engineer",
        "Junior Data Engineer",
        "Junior Data Analyst",
    ]


# ===========================================================================
# Test B: Reordering works
# ===========================================================================

def test_b_reordering_works():
    """Verify changing priority order is persisted and alters job rankings."""
    profile_id = "test_reorder_user"

    # Step 1: Save Initial Order (AI Engineer -> Software Engineer -> Data Analyst)
    prefs_initial = UserCareerPreferences(
        profile_id=profile_id,
        selected_categories=["ai_engineer", "software_engineer", "data_analyst"],
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
    save_user_career_preferences(prefs_initial)

    # Seed 2 comparable eligible jobs
    job_ai = make_test_job("job_ai_reorder", "AI Engineer", "Omni AI", 4, score=80.0)
    job_se = make_test_job("job_se_reorder", "Associate Software Engineer", "Dev Labs", 3, score=80.0)
    save_job(job_ai)
    save_job(job_se)

    # Check initial order: AI Engineer (Rank 1) before Software Engineer (Rank 2)
    jobs_1 = list_jobs(profile_id=profile_id, sort_by="priority_first")
    reorder_jobs_1 = [j for j in jobs_1 if j["job_uid"] in ("job_ai_reorder", "job_se_reorder")]
    assert reorder_jobs_1[0]["title"] == "AI Engineer"
    assert reorder_jobs_1[1]["title"] == "Associate Software Engineer"
    assert reorder_jobs_1[0]["preference_rank"] == 1
    assert reorder_jobs_1[1]["preference_rank"] == 2

    # Step 2: Invert order: Software Engineer -> AI Engineer
    prefs_inverted = UserCareerPreferences(
        profile_id=profile_id,
        selected_categories=["software_engineer", "ai_engineer", "data_analyst"],
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
    save_user_career_preferences(prefs_inverted)

    # Check updated order: Software Engineer (Rank 1) now ranks before AI Engineer (Rank 2)
    jobs_2 = list_jobs(profile_id=profile_id, sort_by="priority_first")
    reorder_jobs_2 = [j for j in jobs_2 if j["job_uid"] in ("job_ai_reorder", "job_se_reorder")]
    assert reorder_jobs_2[0]["title"] == "Associate Software Engineer"
    assert reorder_jobs_2[1]["title"] == "AI Engineer"
    assert reorder_jobs_2[0]["preference_rank"] == 1
    assert reorder_jobs_2[1]["preference_rank"] == 2


# ===========================================================================
# Test C: Persistence across reloads and restarts
# ===========================================================================

def test_c_persistence_across_reloads():
    """Verify saved preferences survive reloads and restarts via database and file overrides."""
    profile_id = "default"
    custom_order = ["software_engineer", "data_engineer", "ai_engineer"]

    prefs = UserCareerPreferences(
        profile_id=profile_id,
        selected_categories=custom_order,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
    saved = save_user_career_preferences(prefs)
    assert saved.selected_categories == custom_order

    # Reload from persistence path
    reloaded = load_user_career_preferences(profile_id=profile_id)
    assert reloaded.selected_categories == custom_order
    assert reloaded.profile_id == profile_id

    # Verify database table contains the exact JSON
    db_json = get_career_preferences_db(profile_id=profile_id)
    assert db_json == custom_order


# ===========================================================================
# Test D: Scheduled discovery uses latest preferences
# ===========================================================================

def test_d_scheduled_discovery_uses_latest_preferences():
    """Verify discovery and scoring dynamically use the latest persisted preferences."""
    profile_id = "default"

    # Save a specific order
    new_order = ["ai_engineer", "data_analyst"]
    save_user_career_preferences(UserCareerPreferences(
        profile_id=profile_id,
        selected_categories=new_order,
        updated_at=datetime.now(timezone.utc).isoformat(),
    ))

    # Scorer instantiated after save should use updated preferences
    scorer = JobScorer()
    job_ai_dict = {"title": "AI Engineer", "description": "Generative AI Python"}
    res_ai = scorer.score_job(job_ai_dict)
    assert res_ai["career_category"] == "ai_engineer"
    assert res_ai["preference_rank"] == 1

    job_da_dict = {"title": "Junior Data Analyst", "description": "SQL and reporting"}
    res_da = scorer.score_job(job_da_dict)
    assert res_da["career_category"] == "data_analyst"
    assert res_da["preference_rank"] == 2


# ===========================================================================
# Test E: Eligibility independence
# ===========================================================================

def test_e_eligibility_independence():
    """Verify an ineligible job remains ineligible even if its category is user's top preference."""
    # User's top preference is Software Engineer
    save_user_career_preferences(UserCareerPreferences(
        profile_id="default",
        selected_categories=["software_engineer", "data_analyst"],
        updated_at=datetime.now(timezone.utc).isoformat(),
    ))

    scorer = JobScorer()

    # Case 1: Unpaid role in user's top preference
    job_unpaid = {
        "title": "Junior Python Developer",
        "description": "Unpaid internship stipend: none for freshers.",
        "location": "Bengaluru, India",
    }
    score_unpaid = scorer.score_job(job_unpaid)
    assert score_unpaid["is_eligible"] is False
    assert score_unpaid["match_tier"] == MatchTier.INELIGIBLE
    assert any("Unpaid position" in d for d in score_unpaid["disqualifiers"])

    # Case 2: Excessive experience (>3 years) in top preference
    job_senior = {
        "title": "Software Engineer",
        "description": "Requires minimum 6 years of experience in backend systems.",
        "location": "Bengaluru, India",
    }
    score_senior = scorer.score_job(job_senior)
    assert score_senior["is_eligible"] is False
    assert score_senior["match_tier"] == MatchTier.INELIGIBLE
    assert any("experience" in d.lower() for d in score_senior["disqualifiers"])

    # Case 3: International on-site without India authorization
    job_intl = {
        "title": "Software Developer",
        "description": "On-site role in London, UK. Must have UK work rights.",
        "location": "London, UK",
        "work_arrangement": "On-site",
    }
    score_intl = scorer.score_job(job_intl)
    assert score_intl["is_eligible"] is False
    assert score_intl["match_tier"] == MatchTier.INELIGIBLE
    assert any("not established for India-authorized" in d for d in score_intl["disqualifiers"])


# ===========================================================================
# Test F: Lower-priority roles
# ===========================================================================

def test_f_lower_priority_roles_considered():
    """Verify valid jobs in lower-ranked categories are considered and not rejected."""
    # User selects 3 categories; Data Engineer is Priority 3
    save_user_career_preferences(UserCareerPreferences(
        profile_id="default",
        selected_categories=["data_analyst", "software_engineer", "data_engineer"],
        updated_at=datetime.now(timezone.utc).isoformat(),
    ))

    scorer = JobScorer()
    job_de = {
        "title": "Junior Data Engineer",
        "description": "Build automated ETL pipelines in Python and SQL for analytics.",
        "location": "Chennai, Tamil Nadu, India",
        "work_arrangement": "Hybrid",
    }
    res = scorer.score_job(job_de)
    assert res["is_eligible"] is True
    assert res["match_tier"] in (MatchTier.STRONG_MATCH, MatchTier.REASONABLE_MATCH, MatchTier.STRETCH_OPPORTUNITY)
    assert res["preference_rank"] == 3
    assert res["career_category"] == "data_engineer"


# ===========================================================================
# Test G: Unsupported and unselected categories
# ===========================================================================

def test_g_unsupported_and_unselected_categories():
    """Verify unknown categories are rejected and unselected categories are ranked after selected."""
    # User selected only Software Engineer and AI Engineer
    prefs = UserCareerPreferences(
        profile_id="test_unselected_user",
        selected_categories=["software_engineer", "ai_engineer"],
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
    save_user_career_preferences(prefs)

    # Job in a supported category that the candidate did NOT select (e.g. Data Analyst)
    job_da = make_test_job("job_da_unselected", "Junior Data Analyst", "Data Corp", 1, score=90.0)
    # Job in a selected category (Software Engineer)
    job_se = make_test_job("job_se_selected", "Associate Software Engineer", "Code Corp", 3, score=80.0)
    save_job(job_da)
    save_job(job_se)

    # Dynamic SQL must rank selected category before unselected category
    order_sql = get_personalized_priority_order_sql(preferences=prefs)
    assert "WHEN priority_category = 3 THEN 1" in order_sql
    assert "WHEN priority_category = 4 THEN 2" in order_sql
    assert "ELSE 999" in order_sql

    jobs = list_jobs(profile_id="test_unselected_user", sort_by="priority_first")
    matching = [j for j in jobs if j["job_uid"] in ("job_da_unselected", "job_se_selected")]
    # The selected Software Engineer role must appear before the unselected Data Analyst role
    assert matching[0]["title"] == "Associate Software Engineer"
    assert matching[0]["preference_rank"] == 1
    assert matching[1]["title"] == "Junior Data Analyst"
    assert matching[1]["preference_rank"] is None  # Unselected


# ===========================================================================
# Test H: Invalid preference data validation
# ===========================================================================

def test_h_invalid_preference_data_validation():
    """Verify duplicate, unknown, and malformed category data is strictly rejected."""
    # Duplicate categories
    with pytest.raises(ValueError, match="Duplicate career category"):
        validate_preference_list(["data_analyst", "software_engineer", "data_analyst"])

    # Unknown category
    with pytest.raises(ValueError, match="Unknown career category"):
        validate_preference_list(["software_engineer", "blockchain_expert"])

    # Non-string category item
    with pytest.raises(ValueError, match="must be a string identifier"):
        validate_preference_list(["software_engineer", 123])  # type: ignore

    # Non-list input
    with pytest.raises(ValueError, match="must be a list"):
        validate_preference_list("not_a_list")  # type: ignore

    # Empty list is accepted (documented fallback: zero selected categories)
    empty_res = validate_preference_list([])
    assert empty_res == []

    # Fallback SQL for empty preferences
    empty_sql = get_personalized_priority_order_sql(preferences=[])
    assert "ELSE 999 END ASC" in empty_sql


# ===========================================================================
# Test I: API endpoints read/write integration
# ===========================================================================

@pytest.mark.anyio
async def test_i_api_endpoints_integration():
    """Verify GET and POST endpoints for career categories and preferences."""
    # 1. GET /api/career-categories
    status, headers, body = await asgi_request(app, method="GET", path="/api/career-categories")
    assert status == 200
    data = json.loads(body.decode("utf-8"))
    assert "categories" in data
    category_ids = [c["id"] for c in data["categories"]]
    assert "software_engineer" in category_ids
    assert "data_analyst" in category_ids
    assert "ai_engineer" in category_ids

    # 2. GET /api/profile/preferences (initial load)
    status, headers, body = await asgi_request(app, method="GET", path="/api/profile/preferences")
    assert status == 200
    prefs_data = json.loads(body.decode("utf-8"))
    assert "selected_categories" in prefs_data
    assert "available_categories" in prefs_data

    # 3. POST /api/profile/preferences (valid update)
    new_order = ["software_engineer", "ai_engineer", "data_engineer"]
    payload = json.dumps({"selected_categories": new_order}).encode("utf-8")
    status, headers, body = await asgi_request(
        app,
        method="POST",
        path="/api/profile/preferences",
        body=payload,
        headers={"Content-Type": "application/json"}
    )
    assert status == 200
    update_res = json.loads(body.decode("utf-8"))
    assert update_res["status"] == "success"
    assert update_res["selected_categories"] == new_order

    # 4. GET /api/profile/preferences (verify update persisted)
    status, headers, body = await asgi_request(app, method="GET", path="/api/profile/preferences")
    assert status == 200
    reloaded_prefs = json.loads(body.decode("utf-8"))
    assert reloaded_prefs["selected_categories"] == new_order

    # 5. POST /api/profile/preferences with duplicate category -> 400 Bad Request
    dup_payload = json.dumps({"selected_categories": ["software_engineer", "software_engineer"]}).encode("utf-8")
    status, headers, body = await asgi_request(
        app,
        method="POST",
        path="/api/profile/preferences",
        body=dup_payload,
        headers={"Content-Type": "application/json"}
    )
    assert status == 400
    err_data = json.loads(body.decode("utf-8"))
    assert "Duplicate" in err_data.get("detail", "")

    # 6. POST /api/profile/preferences with unknown category -> 400 Bad Request
    unknown_payload = json.dumps({"selected_categories": ["unknown_category_xyz"]}).encode("utf-8")
    status, headers, body = await asgi_request(
        app,
        method="POST",
        path="/api/profile/preferences",
        body=unknown_payload,
        headers={"Content-Type": "application/json"}
    )
    assert status == 400
    err_data = json.loads(body.decode("utf-8"))
    assert "Unknown career category" in err_data.get("detail", "")

    # 7. POST /api/profile/preferences/reset
    status, headers, body = await asgi_request(
        app,
        method="POST",
        path="/api/profile/preferences/reset",
        body=json.dumps({"profile_id": "default"}).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    assert status == 200
    reset_data = json.loads(body.decode("utf-8"))
    assert reset_data["selected_categories"] == list(LEGACY_DEFAULT_CATEGORY_ORDER)
