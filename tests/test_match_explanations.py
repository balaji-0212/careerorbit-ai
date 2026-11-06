"""Tests for explainable matching engine in Phase 1."""
import pytest
from careerorbit.matcher.scorer import JobScorer
from careerorbit.models.schemas import MatchTier

def test_scorer_returns_explainable_match_fields():
    scorer = JobScorer()
    job_data = {
        "title": "Junior Data Analyst",
        "description": "Looking for Python, SQL, and Power BI skills. Experience with dashboards and ETL.",
        "location": "Bengaluru, India",
        "work_arrangement": "Hybrid",
        "posting_date_confidence": "SOURCE_REPORTED",
        "posting_date": "2026-10-23T00:00:00+00:00"
    }
    result = scorer.score_job(job_data)
    assert result["match_score"] > 60.0
    assert result["match_tier"] in (MatchTier.STRONG_MATCH, MatchTier.REASONABLE_MATCH)

    # Check explainable fields
    assert "matched_requirements" in result
    assert len(result["matched_requirements"]) >= 3
    assert any("Python" in r for r in result["matched_requirements"])

    assert "missing_requirements" in result
    assert "potential_blockers" in result
    assert "uncertain_information" in result
    assert any("Compensation" in u or "Salary" in u for u in result["uncertain_information"])

    assert "recommendations" in result
    assert len(result["recommendations"]) >= 1

    assert "disclaimer" in result
    assert "not a prediction or guarantee" in result["disclaimer"].lower()

    assert "match_explanation" in result
    explanation = result["match_explanation"]
    assert explanation["overall_score"] == result["match_score"]
    assert explanation["geographic_priority"] == 1

def test_scorer_ineligible_role():
    scorer = JobScorer()
    job_data = {
        "title": "Senior Principal Cloud Architect",
        "description": "Requires 10+ years experience in distributed cloud systems.",
        "location": "Bengaluru, India"
    }
    result = scorer.score_job(job_data)
    assert result["match_tier"] == MatchTier.INELIGIBLE
    assert len(result["potential_blockers"]) >= 1
