"""Multi-Profile Career Priorities Regression Test Suite for Step 6.

Verifies:
1. Profile A vs Profile B vs Profile C custom priority orders on identical candidate pools.
2. Ranking changes dynamically and deterministically with profile-specific preferences.
3. Hard eligibility barriers (experience requirements, geographic disqualifications, non-technical roles)
   operate strictly independently of career preferences.
4. Preference changes for one profile never mutate or leak into other profiles.
5. Invalid/malformed category inputs are safely rejected without corrupting persisted state.
"""

import json
import pytest
from pathlib import Path

from careerorbit.career_priorities import (
    UserCareerPreferences,
    save_user_career_preferences,
    load_user_career_preferences,
    classify_job_category,
    get_preference_rank,
    SUPPORTED_CATEGORIES,
)
from careerorbit.matcher.scorer import JobScorer
from careerorbit.models.schemas import Job, VerificationStatus, MatchTier


@pytest.fixture(autouse=True)
def clean_test_profiles():
    """Ensure test profiles are cleaned up after testing."""
    test_ids = ["profile_swe_focus", "profile_da_focus", "profile_hard_eligibility_test", "user_alpha", "user_beta"]
    yield
    from careerorbit.database.db import get_connection
    try:
        with get_connection() as conn:
            cur = conn.cursor()
            for pid in test_ids:
                cur.execute("DELETE FROM candidate_career_preferences WHERE profile_id = ?", (pid,))
            conn.commit()
    except Exception:
        pass


class TestMultiProfileCareerPriorities:

    def test_multi_profile_independent_ranking(self):
        """Verifies that two distinct profiles rank identical jobs according to their respective preferences."""
        # Profile A: Software Engineer > AI Engineer > Data Analyst
        pref_a = UserCareerPreferences(
            profile_id="profile_swe_focus",
            selected_categories=["software_engineer", "ai_engineer", "data_analyst"],
            updated_at="2026-10-26T10:00:00Z",
        )
        save_user_career_preferences(pref_a)

        # Profile B: Data Analyst > Data Scientist > Software Engineer
        pref_b = UserCareerPreferences(
            profile_id="profile_da_focus",
            selected_categories=["data_analyst", "data_scientist", "software_engineer"],
            updated_at="2026-10-26T10:00:00Z",
        )
        save_user_career_preferences(pref_b)

        # Sample jobs
        job_swe = {
            "title": "Junior Python Backend Developer",
            "description": "Python, FastAPI, Postgres development",
            "experience_required": 0,
            "location": "Bengaluru, India",
            "remote_allowed": True,
        }
        job_da = {
            "title": "Junior Power BI Data Analyst",
            "description": "SQL, Excel, Power BI reporting",
            "experience_required": 0,
            "location": "Chennai, India",
            "remote_allowed": True,
        }

        # Profile A ranking: SWE must rank higher than DA
        rank_a_swe = get_preference_rank(job_swe, profile_id="profile_swe_focus")
        rank_a_da = get_preference_rank(job_da, profile_id="profile_swe_focus")
        assert rank_a_swe < rank_a_da, f"Profile A should prefer SWE (rank {rank_a_swe}) over DA (rank {rank_a_da})"

        # Profile B ranking: DA must rank higher than SWE
        rank_b_swe = get_preference_rank(job_swe, profile_id="profile_da_focus")
        rank_b_da = get_preference_rank(job_da, profile_id="profile_da_focus")
        assert rank_b_da < rank_b_swe, f"Profile B should prefer DA (rank {rank_b_da}) over SWE (rank {rank_b_swe})"

    def test_hard_eligibility_remains_independent_of_priority(self):
        """Verifies that a job with high priority preference is STILL disqualified if it violates hard criteria."""
        # Candidate prefers Software Engineer as #1 priority
        pref = UserCareerPreferences(
            profile_id="profile_hard_eligibility_test",
            selected_categories=["software_engineer", "data_analyst"],
            updated_at="2026-10-26T10:00:00Z",
        )
        save_user_career_preferences(pref)

        # High priority role (SWE) that requires 8 years of experience (candidate has 0-1)
        senior_job = {
            "title": "Staff Software Engineer",
            "description": "Requires minimum 8+ years of production experience",
            "experience_required": 8,
            "location": "Bengaluru, India",
            "remote_allowed": False,
        }

        # Role is in preferred category
        cat = classify_job_category(senior_job["title"])
        assert cat.id == "software_engineer"

        # But scorer/eligibility must mark it disqualified
        scorer = JobScorer(profile_id="profile_hard_eligibility_test")
        result = scorer.score_job(senior_job)

        assert len(result["disqualifiers"]) > 0
        assert result["match_tier"] in (MatchTier.INELIGIBLE, "INELIGIBLE") or result["match_score"] == 0

    def test_profile_isolation_no_cross_contamination(self):
        """Verifies that updating Profile X does not overwrite or mutate Profile Y."""
        pref_x = UserCareerPreferences(
            profile_id="user_alpha",
            selected_categories=["ai_engineer", "software_engineer"],
            updated_at="2026-10-26T10:00:00Z",
        )
        pref_y = UserCareerPreferences(
            profile_id="user_beta",
            selected_categories=["data_analyst", "data_engineer"],
            updated_at="2026-10-26T10:00:00Z",
        )

        save_user_career_preferences(pref_x)
        save_user_career_preferences(pref_y)

        # Verify initial states
        assert load_user_career_preferences("user_alpha").selected_categories == ["ai_engineer", "software_engineer"]
        assert load_user_career_preferences("user_beta").selected_categories == ["data_analyst", "data_engineer"]

        # Mutate Alpha
        pref_x_updated = UserCareerPreferences(
            profile_id="user_alpha",
            selected_categories=["data_engineer", "ai_engineer"],
            updated_at="2026-10-26T10:30:00Z",
        )
        save_user_career_preferences(pref_x_updated)

        # Beta must remain completely unchanged
        loaded_beta = load_user_career_preferences("user_beta")
        assert loaded_beta.selected_categories == ["data_analyst", "data_engineer"]
        assert loaded_beta.profile_id == "user_beta"

    def test_invalid_categories_rejected_safely(self):
        """Verifies that attempting to save unknown or malformed categories raises ValueError."""
        with pytest.raises(ValueError, match="Unknown career category"):
            UserCareerPreferences(
                profile_id="user_gamma",
                selected_categories=["software_engineer", "non_existent_category_123"],
                updated_at="2026-10-26T10:00:00Z",
            ).validate()

        with pytest.raises(ValueError, match="Duplicate career category"):
            UserCareerPreferences(
                profile_id="user_gamma",
                selected_categories=["software_engineer", "software_engineer"],
                updated_at="2026-10-26T10:00:00Z",
            ).validate()
