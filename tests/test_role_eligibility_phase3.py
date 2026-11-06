"""Tests for Phase 3: Job Role Eligibility and Target Career Track Enforcement.

Verifies:
1. Negative eligibility rules explicitly reject non-technical roles (Creative, HR, Marketing, Sales, Admin, Operations, Finance/clerical, Customer Care).
2. 'intern', 'fresher', 'trainee' alone NEVER qualifies a non-technical role.
3. Positive classification into Priorities 1 to 6.
4. Priority 6 is reserved strictly for early-career technical roles with positive technical keywords.
5. Scorer mandatory disqualifiers: match_score == 0.0, match_tier == INELIGIBLE, is_eligible == False.
"""

import pytest
from careerorbit.eligibility import (
    classify_title_to_priority,
    is_unrelated_nontechnical_role,
    screen_job_for_candidate,
    PRIORITY_LABELS,
)
from careerorbit.matcher.scorer import JobScorer
from careerorbit.models.schemas import MatchTier, VerificationStatus


@pytest.fixture
def scorer():
    return JobScorer()


# ---------------- Negative Eligibility Tests ----------------

@pytest.mark.parametrize("title", [
    "Intern - Creative & Communications, People Team",
    "Creative Communications Intern",
    "Social Media & Content Writer Trainee",
    "Graphic Designer Intern",
    "UI/UX Design Intern",
    "HR Intern",
    "Human Resources Trainee",
    "Talent Acquisition Associate",
    "Recruitment Coordinator Intern",
    "Marketing Intern",
    "Digital Marketing Trainee",
    "SEO & Content Marketing Intern",
    "Sales Trainee",
    "Sales Associate",
    "Business Development Intern (BDE)",
    "Telecalling Executive",
    "Administrative Assistant",
    "Front Desk Receptionist",
    "Data Entry Clerk",
    "Accounting Trainee",
    "Payroll & Billing Assistant",
    "Customer Support Representative",
    "Customer Care Executive",
    "Call Center Agent",
    "Operations Intern",
    "Warehouse Operations Associate",
])
def test_unrelated_nontechnical_roles_are_flagged_and_rejected(title):
    """Verifies that non-technical roles are flagged as unrelated and given priority 0."""
    assert is_unrelated_nontechnical_role(title) is True, f"Failed to flag non-technical role: {title}"
    priority = classify_title_to_priority(title)
    assert priority == 0, f"Expected priority 0 for '{title}', got {priority}"
    screen_result = screen_job_for_candidate({"title": title, "location": "Bengaluru", "work_arrangement": "On-site"})
    assert screen_result == "title_not_in_career_priorities", f"Expected screen rejection for '{title}', got {screen_result}"


def test_intern_or_fresher_alone_never_qualifies_nontechnical_role():
    """Verifies that 'intern', 'trainee', or 'fresher' does not permit non-technical roles."""
    non_tech_titles = [
        "HR Intern",
        "Marketing Trainee",
        "Creative Fresher",
        "Sales Intern",
        "Operations Trainee",
    ]
    for title in non_tech_titles:
        assert is_unrelated_nontechnical_role(title) is True
        assert classify_title_to_priority(title) == 0
        assert screen_job_for_candidate({"title": title}) == "title_not_in_career_priorities"


# ---------------- Positive Technical Track Tests ----------------

def test_priority_1_data_analyst_tracks():
    """Priority 1: Data Analyst / BI / Power BI / Reporting."""
    p1_titles = [
        "Junior Data Analyst",
        "Power BI Developer",
        "Business Intelligence Analyst",
        "Reporting Analyst",
        "SQL Data Analyst",
        "Data Analytics Associate",
    ]
    for title in p1_titles:
        assert is_unrelated_nontechnical_role(title) is False
        assert classify_title_to_priority(title) == 1, f"Failed P1 classification for {title}"


def test_priority_2_data_scientist_tracks():
    """Priority 2: Data Scientist / Junior Data Scientist."""
    p2_titles = [
        "Junior Data Scientist",
        "Graduate Data Scientist",
        "Applied Data Scientist",
        "Machine Learning Scientist",
    ]
    for title in p2_titles:
        assert is_unrelated_nontechnical_role(title) is False
        assert classify_title_to_priority(title) == 2, f"Failed P2 classification for {title}"


def test_priority_3_software_engineer_tracks():
    """Priority 3: Software Engineer / Associate Software Engineer / Junior Developer."""
    p3_titles = [
        "Associate Software Engineer",
        "Junior Python Developer",
        "Graduate Software Engineer Trainee",
        "Backend Developer",
        "Full Stack Developer",
        "SDE Intern",
    ]
    for title in p3_titles:
        assert is_unrelated_nontechnical_role(title) is False
        assert classify_title_to_priority(title) == 3, f"Failed P3 classification for {title}"


def test_priority_4_ai_engineer_tracks():
    """Priority 4: AI / ML / Computer Vision / AI Application Engineer."""
    p4_titles = [
        "AI Engineer",
        "Machine Learning Engineer",
        "Computer Vision Engineer",
        "Junior ML Engineer",
        "AI Application Developer",
    ]
    for title in p4_titles:
        assert is_unrelated_nontechnical_role(title) is False
        assert classify_title_to_priority(title) == 4, f"Failed P4 classification for {title}"


def test_priority_5_data_engineer_tracks():
    """Priority 5: Data Engineer / Analytics Engineer / ETL Developer."""
    p5_titles = [
        "Junior Data Engineer",
        "ETL Developer",
        "Analytics Engineer",
        "Cloud Data Engineer",
    ]
    for title in p5_titles:
        assert is_unrelated_nontechnical_role(title) is False
        assert classify_title_to_priority(title) == 5, f"Failed P5 classification for {title}"


def test_priority_6_other_technical_early_career_tracks():
    """Priority 6: Reserved strictly for early-career technical roles with positive technical keywords."""
    p6_titles = [
        "QA Automation Engineer",
        "Junior SDET",
        "Automation Test Engineer",
        "Technical Support Engineer",
        "Application Support Engineer",
        "Cloud Support Associate",
        "Junior DevOps Engineer",
        "Python Automation Developer",
    ]
    for title in p6_titles:
        assert is_unrelated_nontechnical_role(title) is False
        assert classify_title_to_priority(title) == 6, f"Failed P6 classification for {title}"


# ---------------- Scorer Mandatory Disqualification Tests ----------------

def test_scorer_disqualifies_nontechnical_role_with_zero_score(scorer):
    """The reported bug: 'Intern - Creative & Communications, People Team' scored 86.0.
    Must now be strictly disqualified with match_score == 0.0 and is_eligible == False."""
    job_input = {
        "title": "Intern - Creative & Communications, People Team",
        "description": "Join our People team as a creative communications intern in Bengaluru. Help design newsletters and employee engagement campaigns.",
        "location": "Bengaluru, Karnataka",
        "work_arrangement": "Hybrid",
        "posting_date": "2026-03-01T10:00:00Z",
        "verification_status": VerificationStatus.VERIFIED_OPEN.value,
    }
    result = scorer.score_job(job_input)
    assert result["match_tier"] == MatchTier.INELIGIBLE
    assert result["match_score"] == 0.0
    assert result["is_eligible"] is False
    assert any("career priorities" in d.lower() or "non-technical" in d.lower() for d in result["disqualifiers"])


def test_scorer_disqualifies_hr_and_marketing_roles(scorer):
    """Verifies HR and Marketing roles are disqualified by JobScorer."""
    for title in ["HR Intern", "Digital Marketing Trainee", "Sales Development Representative"]:
        job = {
            "title": title,
            "description": "Entry level position in Bangalore.",
            "location": "Bengaluru",
            "work_arrangement": "Hybrid",
            "verification_status": VerificationStatus.VERIFIED_OPEN.value,
        }
        res = scorer.score_job(job)
        assert res["match_tier"] == MatchTier.INELIGIBLE
        assert res["match_score"] == 0.0
        assert res["is_eligible"] is False


def test_priority_labels_mapping():
    """Verifies PRIORITY_LABELS preserves exact priority naming and hierarchy."""
    assert PRIORITY_LABELS[1] == "Data Analyst / BI / Power BI / Reporting"
    assert PRIORITY_LABELS[2] == "Data Scientist / Junior Data Scientist"
    assert PRIORITY_LABELS[3] == "Software Engineer / Associate Software Engineer / Junior Developer"
    assert PRIORITY_LABELS[4] == "AI / ML / Computer Vision / AI Application Engineer"
    assert PRIORITY_LABELS[5] == "Data Engineer / Analytics Engineer / ETL Developer"
    assert PRIORITY_LABELS[6] == "Other relevant early-career technical roles"
    assert 0 in PRIORITY_LABELS
