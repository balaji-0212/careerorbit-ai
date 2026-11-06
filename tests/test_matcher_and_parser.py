"""Tests for 100-point job scoring, experience filtering, priority tiers, and mandatory disqualifiers."""
import pytest
from datetime import datetime, timedelta, timezone
from careerorbit.matcher.scorer import JobScorer
from careerorbit.models.schemas import MatchTier, VerificationStatus

@pytest.fixture
def scorer():
    return JobScorer()

def test_strong_match_data_analyst(scorer):
    """Tier 1: Test a prime Data Analyst vacancy matching the candidate profile."""
    job_input = {
        "title": "Junior Power BI & Data Analyst",
        "description": (
            "We are seeking an entry-level / junior Data Analyst to build Power BI dashboards, "
            "model metrics using DAX, and write optimized SQL queries. Experience with Python, Pandas, "
            "and ETL pipelines is a plus. B.E. graduates welcome."
        ),
        "location": "Coimbatore, Tamil Nadu",
        "work_arrangement": "Hybrid",
        "posting_date": (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat(),
        "verification_status": VerificationStatus.VERIFIED_OPEN.value
    }

    result = scorer.score_job(job_input)
    assert result["match_score"] >= 75.0
    assert result["match_tier"] == MatchTier.STRONG_MATCH
    assert len(result["disqualifiers"]) == 0
    assert "Power Bi" in result["supported_skills"]
    assert "Sql" in result["supported_skills"]
    assert result["score_breakdown"].skills_and_projects >= 24.0
    assert result["score_breakdown"].experience_compatibility == 20.0
    assert result["score_breakdown"].eligibility == 15.0

def test_tier2_data_scientist_match(scorer):
    """Tier 2: Data Scientist / Applied Data Science vacancy."""
    job_input = {
        "title": "Junior Data Scientist",
        "description": (
            "Exciting role for an early-career or junior data scientist. Responsibilities include "
            "exploratory data analysis with Python, NumPy, Pandas, SQL data extraction, and machine learning "
            "model prototyping. 0-2 years experience required."
        ),
        "location": "Bengaluru",
        "work_arrangement": "Hybrid",
        "posting_date": datetime.now(timezone.utc).isoformat(),
        "verification_status": VerificationStatus.VERIFIED_OPEN.value
    }
    result = scorer.score_job(job_input)
    assert result["match_score"] >= 70.0
    assert result["match_tier"] in (MatchTier.STRONG_MATCH, MatchTier.REASONABLE_MATCH)
    assert "Python" in result["supported_skills"]
    assert "Sql" in result["supported_skills"]

def test_tier3_software_engineer_match(scorer):
    """Tier 3: Software Engineer / Associate Software Engineer matching current Example Systems experience."""
    job_input = {
        "title": "Associate Software Engineer - Python",
        "description": (
            "Example Systems or enterprise software development. Build backend REST APIs using FastAPI/Flask, "
            "work with MySQL/PostgreSQL databases, participate in Git workflows, code reviews, and CI/CD pipelines. "
            "Entry-level or 0-1 year experience."
        ),
        "location": "Chennai",
        "work_arrangement": "On-site",
        "posting_date": datetime.now(timezone.utc).isoformat(),
        "verification_status": VerificationStatus.VERIFIED_OPEN.value
    }
    result = scorer.score_job(job_input)
    assert result["match_score"] >= 75.0
    assert result["match_tier"] == MatchTier.STRONG_MATCH
    assert "Fastapi" in result["supported_skills"]
    assert "Git" in result["supported_skills"]

def test_tier4_ai_engineer_match(scorer):
    """Tier 4: AI Engineer / Junior ML / Computer Vision matching Example Vision Project project."""
    job_input = {
        "title": "Junior AI Engineer - Computer Vision",
        "description": (
            "Build computer vision models using TensorFlow, Keras, and OpenCV. "
            "Deploy inference services via Flask/FastAPI REST APIs. Freshers or graduate engineers welcome."
        ),
        "location": "Bengaluru",
        "work_arrangement": "Hybrid",
        "posting_date": datetime.now(timezone.utc).isoformat(),
        "verification_status": VerificationStatus.VERIFIED_OPEN.value
    }
    result = scorer.score_job(job_input)
    assert result["match_score"] >= 75.0
    assert result["match_tier"] == MatchTier.STRONG_MATCH
    assert "Tensorflow" in result["supported_skills"]
    assert "Keras" in result["supported_skills"]
    assert "Opencv" in result["supported_skills"]
    assert "documented project evidence pending review" in result["evidence_notes"]

def test_tier5_data_engineer_with_learnable_skills(scorer):
    """Tier 5: Data Engineer role where Azure cloud technologies are recognized as learnable targets."""
    job_input = {
        "title": "Associate Data Engineer",
        "description": (
            "Build data pipelines with Python and SQL. Familiarity with Azure Data Factory, "
            "PySpark, and Azure Databricks is preferred or can be learned on the job. 0-2 years experience."
        ),
        "location": "Hyderabad",
        "work_arrangement": "Hybrid",
        "posting_date": datetime.now(timezone.utc).isoformat(),
        "verification_status": VerificationStatus.VERIFIED_OPEN.value
    }
    result = scorer.score_job(job_input)
    assert result["match_score"] >= 65.0
    assert "Python" in result["supported_skills"]
    assert "Sql" in result["supported_skills"]
    # Verify that Azure/Databricks/PySpark are flagged as learnable, NOT fabricated as hands-on skills
    assert any("Azure Data Factory" in l for l in result["learnable_skills"])
    assert any("Pyspark" in l for l in result["learnable_skills"])
    assert "Azure Data Factory" not in result["supported_skills"]

def test_tier6_other_early_career_role(scorer):
    """Tier 6: Other early career technical roles."""
    job_input = {
        "title": "Graduate Technical Support Engineer",
        "description": "Troubleshoot SQL queries, inspect REST APIs, write Python scripts. Entry-level.",
        "location": "Chennai",
        "work_arrangement": "On-site",
        "posting_date": datetime.now(timezone.utc).isoformat(),
        "verification_status": VerificationStatus.VERIFIED_OPEN.value
    }
    result = scorer.score_job(job_input)
    assert result["match_score"] >= 55.0
    assert len(result["disqualifiers"]) == 0

def test_disqualify_senior_role(scorer):
    """Senior roles (>3 yrs experience) must be disqualified to protect candidate time."""
    job_input = {
        "title": "Lead Software Architect",
        "description": "Looking for 8+ years of experience leading distributed cloud backend systems.",
        "location": "Bengaluru",
        "work_arrangement": "Hybrid",
        "posting_date": datetime.now(timezone.utc).isoformat(),
        "verification_status": VerificationStatus.VERIFIED_OPEN.value
    }

    result = scorer.score_job(job_input)
    assert result["match_tier"] == MatchTier.INELIGIBLE
    assert any("Senior role requirement" in d or "exceeds" in d for d in result["disqualifiers"])


def test_manager_role_is_ineligible_even_when_keyword_overlap_is_high(scorer):
    result = scorer.score_job({
        "title": "Manager, Machine Learning Engineering",
        "description": "Lead Python, SQL, TensorFlow, Keras, computer vision and API engineering teams.",
        "location": "USA", "work_arrangement": "Remote",
        "posting_date": datetime.now(timezone.utc).isoformat(),
        "verification_status": VerificationStatus.UNVERIFIED.value,
    })
    assert result["match_tier"] == MatchTier.INELIGIBLE
    assert any("Senior role requirement" in note for note in result["disqualifiers"])
    assert any("Remote eligibility" in note for note in result["disqualifiers"])

def test_disqualify_unpaid_role(scorer):
    """Platform policy strictly prohibits unpaid positions."""
    job_input = {
        "title": "Data Analyst Trainee",
        "description": "3-month unpaid internship for freshers.",
        "location": "Remote",
        "work_arrangement": "Remote",
        "posting_date": datetime.now(timezone.utc).isoformat(),
        "verification_status": VerificationStatus.VERIFIED_OPEN.value
    }

    result = scorer.score_job(job_input)
    assert result["match_tier"] == MatchTier.INELIGIBLE
    assert any("Unpaid position" in d for d in result["disqualifiers"])

def test_disqualify_strict_phd_requirement(scorer):
    """Strict PhD requirement must disqualify or mark as ineligible."""
    job_input = {
        "title": "Research Scientist",
        "description": "Doctorate required. PhD strictly required in Computer Science.",
        "location": "Bengaluru",
        "work_arrangement": "On-site",
        "posting_date": datetime.now(timezone.utc).isoformat(),
        "verification_status": VerificationStatus.VERIFIED_OPEN.value
    }
    result = scorer.score_job(job_input)
    assert any("PhD/Master's" in d for d in result["disqualifiers"])
    assert result["match_tier"] == MatchTier.INELIGIBLE

def test_freshness_decay(scorer):
    """Old postings receive lower freshness scores."""
    old_date = (datetime.now(timezone.utc) - timedelta(days=20)).isoformat()
    job_input = {
        "title": "Junior Python Developer",
        "description": "Python, SQL, REST APIs.",
        "location": "Chennai",
        "work_arrangement": "Hybrid",
        "posting_date": old_date,
        "verification_status": VerificationStatus.VERIFIED_OPEN.value
    }
    result = scorer.score_job(job_input)
    assert result["score_breakdown"].freshness_and_availability < 10.0


def test_unknown_publication_date_does_not_receive_freshness_credit(scorer):
    recent = datetime.now(timezone.utc).isoformat()
    result = scorer.score_job({
        "title": "Junior Data Analyst", "description": "SQL and Power BI dashboards.",
        "location": "Chennai, India", "work_arrangement": "Hybrid",
        "posting_date": recent, "posting_date_confidence": "UNKNOWN",
        "verification_status": VerificationStatus.UNVERIFIED.value,
    })
    assert result["score_breakdown"].freshness_and_availability == 8.0


def test_two_year_minimum_is_not_scored_as_fully_compatible(scorer):
    result = scorer.score_job({
        "title": "Software Engineer, AI Coding Tasks",
        "description": "Requires 2+ years of professional software engineering and Python.",
        "location": "Worldwide", "work_arrangement": "Remote",
        "posting_date": datetime.now(timezone.utc).isoformat(),
        "posting_date_confidence": "SOURCE_REPORTED",
        "verification_status": VerificationStatus.UNVERIFIED.value,
    })
    assert result["score_breakdown"].experience_compatibility == 10.0
