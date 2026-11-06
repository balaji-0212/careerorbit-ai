"""Phase 3 — Personalized Learning Planner & Skill Gap Engine Tests.

Tests candidate skill categorization, dynamic gap extraction, bounded scheduling,
task status tracking, study analytics, edge case handling, and API integration.
"""

from __future__ import annotations

import json
import pytest
from datetime import datetime, timezone

from careerorbit.database.db import (
    init_db,
    save_job,
    save_daily_study_plan,
    get_daily_study_plan,
    get_daily_study_plan_by_date,
    list_daily_study_plans,
    update_study_task_status,
    get_study_analytics
)
from careerorbit.models.schemas import Job, VerificationStatus, MatchTier
from careerorbit.prep.study_planner import DailyStudyPlanner
from careerorbit.web.app import app


async def asgi_request(app, method="GET", path="/", query="", body=b"", headers=None):
    from tests.authenticated_request import authenticated_headers
    headers = authenticated_headers(method, headers)
    """Simple in-process ASGI test helper."""
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "path": path,
        "raw_path": path.encode(),
        "query_string": query.encode(),
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
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


def test_candidate_skills_provenance_distinction():
    """Verify candidate skills are cleanly categorized into verified, declared, and learning targets."""
    planner = DailyStudyPlanner()
    skills = planner.get_candidate_skills()

    assert "evidence_supported" in skills
    assert "user_declared" in skills
    assert "learning_targets" in skills

    # Python and SQL should be evidence-supported from candidate experience
    assert "Python" in skills["evidence_supported"]
    assert "SQL" in skills["evidence_supported"]

    # Cloud technologies are explicitly learning targets, not verified skills
    assert any("PySpark" in t or "Azure" in t or "Databricks" in t for t in skills["learning_targets"])
    assert "PySpark" not in skills["evidence_supported"]


def test_dynamic_gap_extraction_with_real_jobs():
    """Verify skill gaps are extracted and ranked from active job records."""
    init_db()

    # Seed two sample jobs with explicit missing skills
    save_job(Job(
        job_uid="gap_test_job_1",
        employer="Test Corp A",
        title="Junior Data Analyst",
        normalized_title="junior data analyst",
        priority_category=1,
        location="Bengaluru",
        official_url="https://test.com/1",
        canonical_url="https://test.com/1",
        discovery_source="Greenhouse Test Corp",
        verification_status=VerificationStatus.VERIFIED_OPEN,
        match_tier=MatchTier.STRONG_MATCH,
        missing_skills=["Window Functions", "DAX / CALCULATE"],
        learnable_skills=["Power BI Service"]
    ))

    save_job(Job(
        job_uid="gap_test_job_2",
        employer="Test Corp B",
        title="BI Analyst",
        normalized_title="bi analyst",
        priority_category=1,
        location="Chennai",
        official_url="https://test.com/2",
        canonical_url="https://test.com/2",
        discovery_source="Lever Test Corp",
        verification_status=VerificationStatus.VERIFIED_OPEN,
        match_tier=MatchTier.STRONG_MATCH,
        missing_skills=["Window Functions", "PostgreSQL"],
        learnable_skills=["DAX / CALCULATE"]
    ))

    planner = DailyStudyPlanner()
    gaps_info = planner.extract_skill_gaps(target_priority=1)

    assert gaps_info["target_priority"] == 1
    top_gaps = gaps_info["top_gaps"]
    assert len(top_gaps) >= 2

    # Window Functions appeared in both jobs, should have highest frequency
    gap_skills = [g["skill"] for g in top_gaps]
    assert "Window Functions" in gap_skills
    wf_gap = next(g for g in top_gaps if g["skill"] == "Window Functions")
    assert wf_gap["frequency"] == 2


def test_daily_plan_bounded_schedule_generation():
    """Verify daily plan respects time budget bounds and divides time across 4 stages."""
    init_db()
    planner = DailyStudyPlanner()

    # Test with custom 120-minute budget
    plan = planner.generate_daily_plan(daily_budget_minutes=120, save_to_db=True)

    assert plan["daily_budget_minutes"] == 120
    assert plan["allocated_hours"] == 2.0
    assert len(plan["schedule_blocks"]) == 4
    assert len(plan["tasks"]) == 4

    # Verify task stages
    task_stages = [t["stage"] for t in plan["tasks"]]
    assert "CONCEPT_MASTERY" in task_stages
    assert "HANDS_ON_CODING" in task_stages
    assert "PROJECT_ARCHITECTURE" in task_stages
    assert "BEHAVIORAL_DEFENSE" in task_stages

    # Verify each task has a transparent explanation
    for task in plan["tasks"]:
        assert len(task["explanation"]) > 10
        assert task["status"] == "NOT_STARTED"
        assert task["completed_at"] is None


def test_task_status_lifecycle_and_persistence():
    """Verify updating task status updates DB record, timestamps, and overall completion."""
    init_db()
    planner = DailyStudyPlanner()
    plan = planner.generate_daily_plan(daily_budget_minutes=90, save_to_db=True)
    plan_id = plan["id"]

    # Initially not completed
    assert plan["is_completed"] is False

    # Mark first task IN_PROGRESS
    updated_1 = update_study_task_status(plan_id, "task_1", "IN_PROGRESS")
    assert updated_1 is not None
    t1 = next(t for t in updated_1["tasks"] if t["task_id"] == "task_1")
    assert t1["status"] == "IN_PROGRESS"
    assert t1["completed_at"] is None
    assert updated_1["is_completed"] is False

    # Mark first task COMPLETED
    updated_2 = update_study_task_status(plan_id, "task_1", "COMPLETED")
    assert updated_2 is not None
    t1_done = next(t for t in updated_2["tasks"] if t["task_id"] == "task_1")
    assert t1_done["status"] == "COMPLETED"
    assert t1_done["completed_at"] is not None
    assert updated_2["is_completed"] is False  # remaining tasks not done

    # Complete all remaining tasks
    for tid in ["task_2", "task_3", "task_4"]:
        update_study_task_status(plan_id, tid, "COMPLETED")

    # Reload from DB and verify plan is now marked completed
    final_plan = get_daily_study_plan(plan_id)
    assert final_plan is not None
    assert final_plan["is_completed"] is True
    assert all(t["status"] == "COMPLETED" for t in final_plan["tasks"])


def test_study_analytics_metrics():
    """Verify study analytics aggregates streaks, completed tasks, and studied minutes."""
    init_db()
    planner = DailyStudyPlanner()
    plan = planner.generate_daily_plan(daily_budget_minutes=120, save_to_db=True)
    plan_id = plan["id"]

    # Mark 2 tasks completed (e.g. 15 mins + 40 mins)
    update_study_task_status(plan_id, "task_1", "COMPLETED")
    update_study_task_status(plan_id, "task_2", "COMPLETED")

    analytics = get_study_analytics()
    assert analytics["total_plans"] >= 1
    assert analytics["total_tasks_completed"] >= 2
    assert analytics["total_minutes_studied"] > 0
    assert analytics["current_streak_days"] >= 1
    assert isinstance(analytics["mastered_skills"], list)


def test_edge_cases_empty_catalog_and_invalid_inputs(monkeypatch):
    """Verify planner handles empty catalog, invalid goals, and extreme budgets without crashing."""
    init_db()
    planner = DailyStudyPlanner()

    # 1. Invalid / negative time budget defaults safely
    plan_neg = planner.generate_daily_plan(daily_budget_minutes=-50, save_to_db=False)
    assert plan_neg["daily_budget_minutes"] == 210
    assert plan_neg["allocated_hours"] == 3.5

    # 2. Extreme upper bound capped realistically (360 mins)
    plan_huge = planner.generate_daily_plan(daily_budget_minutes=1000, save_to_db=False)
    assert plan_huge["daily_budget_minutes"] == 360

    # 3. Missing profile handled gracefully
    monkeypatch.setattr("careerorbit.prep.study_planner.CANDIDATE_PROFILE", {})
    skills_fallback = planner.get_candidate_skills()
    assert len(skills_fallback["evidence_supported"]) >= 1

    # 4. Unknown priority defaults gracefully
    gaps_unknown = planner.extract_skill_gaps(target_priority=99)
    assert len(gaps_unknown["top_gaps"]) >= 1


@pytest.mark.anyio
async def test_api_study_plan_endpoints():
    """Verify all /api/study/ REST endpoints function with validated request/response models."""
    init_db()

    # 1. GET /api/study/plan/today
    st, _, body = await asgi_request(app, method="GET", path="/api/study/plan/today")
    assert st == 200
    plan = json.loads(body.decode())
    assert "id" in plan
    assert "tasks" in plan
    plan_id = plan["id"]

    # 2. POST /api/study/plan/generate with custom budget
    payload = json.dumps({
        "target_role": "Junior Data Analyst",
        "daily_budget_minutes": 100,
        "target_priority": 1,
        "notes": "Testing generation"
    }).encode()
    st2, _, body2 = await asgi_request(
        app, method="POST", path="/api/study/plan/generate",
        body=payload, headers={"content-type": "application/json"}
    )
    assert st2 == 200
    gen_plan = json.loads(body2.decode())
    assert gen_plan["daily_budget_minutes"] == 100
    assert gen_plan["notes"] == "Testing generation"

    # 3. PUT /api/study/plan/{id}/tasks/{task_id}/status
    task_payload = json.dumps({"status": "COMPLETED", "notes": "Done"}).encode()
    st3, _, body3 = await asgi_request(
        app, method="PUT", path=f"/api/study/plan/{plan_id}/tasks/task_1/status",
        body=task_payload, headers={"content-type": "application/json"}
    )
    assert st3 == 200
    updated_plan = json.loads(body3.decode())
    t1 = next(t for t in updated_plan["tasks"] if t["task_id"] == "task_1")
    assert t1["status"] == "COMPLETED"

    # 4. Invalid status returns 400
    bad_payload = json.dumps({"status": "INVALID_STATE"}).encode()
    st_bad, _, _ = await asgi_request(
        app, method="PUT", path=f"/api/study/plan/{plan_id}/tasks/task_1/status",
        body=bad_payload, headers={"content-type": "application/json"}
    )
    assert st_bad == 400

    # 5. GET /api/study/skill-gaps
    st_gaps, _, body_gaps = await asgi_request(app, method="GET", path="/api/study/skill-gaps")
    assert st_gaps == 200
    gaps_data = json.loads(body_gaps.decode())
    assert "top_gaps" in gaps_data

    # 6. GET /api/study/analytics/progress
    st_ana, _, body_ana = await asgi_request(app, method="GET", path="/api/study/analytics/progress")
    assert st_ana == 200
    ana_data = json.loads(body_ana.decode())
    assert "total_tasks_completed" in ana_data
    assert "total_minutes_studied" in ana_data

    # 7. Backward compatibility: GET /api/prep/daily-plan
    st_leg, _, body_leg = await asgi_request(app, method="GET", path="/api/prep/daily-plan")
    assert st_leg == 200
    leg_data = json.loads(body_leg.decode())
    assert "schedule_blocks" in leg_data
    assert "top_three_priorities" in leg_data
