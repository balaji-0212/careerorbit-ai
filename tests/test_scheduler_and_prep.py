"""Tests for timezone handling, background scheduler, interview prep coach, and daily study planner."""
from datetime import datetime, timezone, timedelta
from careerorbit.scheduler.runner import BackgroundScheduler, IST
from careerorbit.prep.study_planner import DailyStudyPlanner
from careerorbit.prep.interview_coach import InterviewCoach
from careerorbit.database.db import init_db, save_job
from careerorbit.models.schemas import Job, VerificationStatus, MatchTier

def test_ist_timezone_offset():
    """Verify Asia/Kolkata timezone offset is strictly +05:30."""
    now_ist = datetime.now(IST)
    offset = now_ist.utcoffset()
    assert offset == timedelta(hours=5, minutes=30)
    assert "Asia/Kolkata" in str(now_ist.tzinfo)

def test_scheduler_status():
    scheduler = BackgroundScheduler()
    status = scheduler.get_status()
    assert "Asia/Kolkata" in status["current_ist_time"]
    assert "08:00 AM" in status["target_discovery_time"]
    assert "08:00 PM" in status["target_study_time"]

def test_daily_study_planner_blocks():
    init_db()
    planner = DailyStudyPlanner()
    plan = planner.generate_daily_plan()

    assert plan["allocated_hours"] == 3.5
    assert len(plan["schedule_blocks"]) == 4
    assert len(plan["top_three_priorities"]) == 3
    assert "08:00 PM" in plan["target_session_time"]

    # Verify 4 blocks match structure
    block_titles = [b["stage"] for b in plan["schedule_blocks"]]
    assert any("Review" in t for t in block_titles)
    assert any("Coding" in t or "Technical" in t for t in block_titles)
    assert any("Project" in t or "Architecture" in t for t in block_titles)
    assert any("Behavioral" in t or "STAR" in t for t in block_titles)

def test_interview_coach_package(monkeypatch):
    init_db()
    monkeypatch.setattr("careerorbit.prep.interview_coach.candidate_profile_ready_for_resume", lambda: True)
    job = Job(
        job_uid="prep_coach_test_broadridge",
        employer="Broadridge",
        title="Associate Business / Data Analyst",
        normalized_title="associate business data analyst",
        priority_category=1,
        location="Hyderabad",
        official_url="https://broadridge.com/careers",
        canonical_url="https://broadridge.com/careers",
        discovery_source="Test",
        verification_status=VerificationStatus.VERIFIED_OPEN,
        match_tier=MatchTier.STRONG_MATCH,
        description="Power BI and SQL Server reporting role."
    )
    job_id = save_job(job)
    job_dict = job.model_dump()
    job_dict["id"] = job_id

    coach = InterviewCoach()
    prep = coach.generate_prep_package(job_dict)

    assert prep["company"] == "Broadridge"
    assert len(prep["technical_topics"]) >= 4
    assert len(prep["practice_exercises"]) >= 1
    assert len(prep["interview_questions"]) >= 2

    # Check for SQL window function or DAX question
    all_q_text = " ".join(q["question"] + " " + q["model_answer"] for q in prep["interview_questions"])
    assert "Loan Portfolio Risk" in all_q_text or "SQL" in all_q_text or "Power BI" in all_q_text


def test_scheduler_concurrency_lock():
    """Verify that concurrent triggers return a busy status rather than colliding."""
    scheduler = BackgroundScheduler()
    # Acquire discovery lock
    acquired = scheduler._discovery_lock.acquire(blocking=False)
    assert acquired is True
    try:
        # Triggering discovery while lock is held should return busy
        result = scheduler.trigger_discovery_now()
        assert result.get("status") == "busy"
    finally:
        scheduler._discovery_lock.release()
