"""Daily career study planner targeting evening preparation with structured, gap-connected learning."""
from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

from careerorbit.config.settings import SETTINGS
from careerorbit.config.profile import CANDIDATE_PROFILE
from careerorbit.config.candidate_evidence import get_candidate_evidence
from careerorbit.database.db import (
    get_connection,
    save_daily_study_plan,
    get_daily_study_plan_by_date,
    list_learning_resources
)

# Asia/Kolkata is fixed UTC+05:30 with zero DST variation
IST_TIMEZONE = timezone(timedelta(hours=5, minutes=30), "Asia/Kolkata")


class DailyStudyPlanner:
    """Orchestrates daily personalized study schedules connected directly to job skill gaps."""

    def __init__(self, tz=IST_TIMEZONE):
        self.tz = tz

    def get_current_local_time(self) -> datetime:
        return datetime.now(self.tz)

    def get_candidate_skills(self) -> Dict[str, Any]:
        """Categorize candidate skills into verified, declared, learning targets, and unknown."""
        evidence_supported: List[str] = []
        user_declared: List[str] = []
        learning_targets: List[str] = []
        unknown_proficiency: List[str] = []

        try:
            # Check employment experience for verified professional skills
            employment = CANDIDATE_PROFILE.get("employment", []) if isinstance(CANDIDATE_PROFILE, Mapping) else []
            for job in employment:
                for skill in job.get("skills_used", []):
                    if skill not in evidence_supported:
                        evidence_supported.append(skill)

            # Check projects for project-verified skills
            projects = CANDIDATE_PROFILE.get("projects", []) if isinstance(CANDIDATE_PROFILE, Mapping) else []
            for proj in projects:
                for tech in proj.get("technologies", []):
                    if tech not in evidence_supported:
                        evidence_supported.append(tech)

            # Check documented skills / learning targets
            doc_skills = CANDIDATE_PROFILE.get("documented_skills", {}) if isinstance(CANDIDATE_PROFILE, Mapping) else {}
            for target in doc_skills.get("learning_targets_cloud_data", []):
                if target not in learning_targets and target not in evidence_supported:
                    learning_targets.append(target)

            for pref in doc_skills.get("programming_languages", []):
                if pref not in evidence_supported and pref not in user_declared:
                    user_declared.append(pref)

            for db_skill in doc_skills.get("databases_and_analytics", []):
                if db_skill not in evidence_supported and db_skill not in user_declared:
                    user_declared.append(db_skill)
        except Exception:
            pass

        # Fallback defaults if candidate profile is empty
        if not evidence_supported and not user_declared:
            evidence_supported = ["Python", "SQL"]

        return {
            "evidence_supported": sorted(evidence_supported),
            "user_declared": sorted(user_declared),
            "learning_targets": sorted(learning_targets),
            "unknown_proficiency": unknown_proficiency
        }

    def extract_skill_gaps(self, target_priority: int = 1, target_role: Optional[str] = None) -> Dict[str, Any]:
        """Aggregate missing and learnable skills from active and saved job listings."""
        candidate_skills = self.get_candidate_skills()
        verified_set = {s.lower() for s in candidate_skills["evidence_supported"]}

        missing_counter = Counter()
        learnable_counter = Counter()
        analyzed_jobs = 0

        try:
            conn = get_connection()
            cursor = conn.cursor()

            query = """
                SELECT missing_skills, learnable_skills, required_skills
                FROM jobs
                WHERE COALESCE(record_state, 'DISCOVERY_LEAD') != 'QUARANTINED'
                  AND discovery_source NOT IN ('Test', 'Test Unit')
            """
            params: List[Any] = []

            if target_priority is not None and target_priority > 0:
                query += " AND priority_category = ?"
                params.append(target_priority)

            cursor.execute(query, params)
            rows = cursor.fetchall()
            analyzed_jobs = len(rows)

            for row in rows:
                # Missing skills
                raw_missing = row["missing_skills"]
                if raw_missing:
                    try:
                        parsed = json.loads(raw_missing) if isinstance(raw_missing, str) and raw_missing.startswith("[") else [s.strip() for s in raw_missing.split(",") if s.strip()]
                        for item in parsed:
                            clean = item.strip()
                            if clean and clean.lower() not in verified_set:
                                missing_counter[clean] += 1
                    except Exception:
                        pass

                # Learnable skills
                raw_learnable = row["learnable_skills"]
                if raw_learnable:
                    try:
                        parsed = json.loads(raw_learnable) if isinstance(raw_learnable, str) and raw_learnable.startswith("[") else [s.strip() for s in raw_learnable.split(",") if s.strip()]
                        for item in parsed:
                            clean = item.strip()
                            if clean and clean.lower() not in verified_set:
                                learnable_counter[clean] += 1
                    except Exception:
                        pass

            conn.close()
        except Exception:
            pass

        # If database query produced no gaps (e.g. fresh db or no jobs), provide standard curriculum gaps
        if not missing_counter and not learnable_counter:
            missing_counter = Counter({
                "Window Functions": 5,
                "DAX / CALCULATE": 4,
                "PySpark": 3,
                "Azure Data Factory": 3,
                "Pandas Data Wrangling": 2
            })

        # Rank gaps
        ranked_gaps = []
        for skill, count in missing_counter.most_common(10):
            ranked_gaps.append({
                "skill": skill,
                "frequency": count,
                "type": "MISSING_SKILL",
                "in_candidate_learning_targets": any(skill.lower() in t.lower() for t in candidate_skills["learning_targets"])
            })

        for skill, count in learnable_counter.most_common(5):
            if not any(g["skill"].lower() == skill.lower() for g in ranked_gaps):
                ranked_gaps.append({
                    "skill": skill,
                    "frequency": count,
                    "type": "LEARNABLE_SKILL",
                    "in_candidate_learning_targets": any(skill.lower() in t.lower() for t in candidate_skills["learning_targets"])
                })

        return {
            "target_priority": target_priority,
            "target_role": target_role or "Data Analyst / BI / Power BI",
            "analyzed_jobs_count": analyzed_jobs,
            "top_gaps": ranked_gaps,
            "candidate_skills": candidate_skills
        }

    def generate_daily_plan(
        self,
        target_role: Optional[str] = None,
        daily_budget_minutes: int = 210,
        target_priority: int = 1,
        save_to_db: bool = True
    ) -> Dict[str, Any]:
        """Build an evidence-grounded daily study plan bounded by available time budget."""
        local_now = self.get_current_local_time()

        # Enforce realistic duration bounds (30 mins to 360 mins)
        if not isinstance(daily_budget_minutes, (int, float)) or daily_budget_minutes <= 0:
            daily_budget_minutes = 210
        daily_budget_minutes = max(30, min(360, int(daily_budget_minutes)))

        target_role_clean = (target_role or "Data Analyst / BI / Power BI / Reporting Analyst").strip()

        # Extract real skill gaps from active job vacancies
        gaps_info = self.extract_skill_gaps(target_priority=target_priority, target_role=target_role_clean)
        top_gaps = gaps_info.get("top_gaps", [])
        gap_names = [g["skill"] for g in top_gaps]

        # Fetch relevant curated resources from library
        primary_gap = gap_names[0] if gap_names else "SQL Window Functions"
        secondary_gap = gap_names[1] if len(gap_names) > 1 else "DAX Measures"
        cloud_gap = gap_names[2] if len(gap_names) > 2 else "PySpark"

        matched_resources = []
        try:
            # Query library for relevant resources
            all_resources = list_learning_resources(limit=50)
            for res in all_resources:
                tag = str(res.get("skill_tag") or "").lower()
                cat = str(res.get("category") or "").lower()
                title = str(res.get("title") or "").lower()
                if any(g.lower() in tag or g.lower() in cat or g.lower() in title for g in [primary_gap, secondary_gap, cloud_gap]):
                    matched_resources.append(res)
        except Exception:
            matched_resources = []

        # Time allocation (percentage distribution across 4 stages)
        review_mins = max(15, int(daily_budget_minutes * 0.15))
        coding_mins = max(25, int(daily_budget_minutes * 0.35))
        arch_mins = max(20, int(daily_budget_minutes * 0.35))
        behavioral_mins = max(15, daily_budget_minutes - (review_mins + coding_mins + arch_mins))

        allocated_hours = round(daily_budget_minutes / 60.0, 1)

        # Matched resource pointers
        res_review = matched_resources[0] if len(matched_resources) > 0 else None
        res_coding = matched_resources[1] if len(matched_resources) > 1 else (matched_resources[0] if matched_resources else None)
        res_arch = matched_resources[2] if len(matched_resources) > 2 else None

        # Build 4 structured schedule blocks (satisfies backward compatibility requirements)
        schedule_blocks = [
            {
                "time_slot": f"08:00 PM – {self._add_minutes_to_time_str('08:00 PM', review_mins)} IST ({review_mins} mins)",
                "stage": "Study Setup and Review",
                "goal": f"Choose one learning objective ({primary_gap}) and review notes from previous session.",
                "duration_minutes": review_mins,
                "action_items": [
                    f"Write one specific learning objective targeting {primary_gap}",
                    "Review previous session notes and identify unresolved questions",
                    "Choose a small practice dataset or coding playground"
                ]
            },
            {
                "time_slot": f"{self._add_minutes_to_time_str('08:00 PM', review_mins)} – {self._add_minutes_to_time_str('08:00 PM', review_mins + coding_mins)} IST ({coding_mins} mins)",
                "stage": "Hands-On Technical Coding & SQL",
                "goal": f"Practice {primary_gap} and analytical data wrangling with verified sample data.",
                "duration_minutes": coding_mins,
                "action_items": [
                    f"Practice {primary_gap} filtering, joins, grouping and window functions",
                    "Verify query execution plan and check outputs against expected figures",
                    "Record unfamiliar syntax and runtime warnings for subsequent review"
                ]
            },
            {
                "time_slot": f"{self._add_minutes_to_time_str('08:00 PM', review_mins + coding_mins)} – {self._add_minutes_to_time_str('08:00 PM', review_mins + coding_mins + arch_mins)} IST ({arch_mins} mins)",
                "stage": "Project Architecture & Technical Defense",
                "goal": f"Study {secondary_gap} reporting architecture and {cloud_gap} cloud learning target.",
                "duration_minutes": arch_mins,
                "action_items": [
                    f"Study {secondary_gap} metric definitions and data storytelling using public datasets",
                    "Practice explaining one chart and its technical trade-offs in plain language",
                    f"Advance cloud-data target: {cloud_gap} (maintain honest non-hands-on status)"
                ]
            },
            {
                "time_slot": f"{self._add_minutes_to_time_str('08:00 PM', review_mins + coding_mins + arch_mins)} – {self._add_minutes_to_time_str('08:00 PM', daily_budget_minutes)} IST ({behavioral_mins} mins)",
                "stage": "Behavioral STAR & Tomorrow's Action Plan",
                "goal": "Review what was learned and prepare a manageable next study step.",
                "duration_minutes": behavioral_mins,
                "action_items": [
                    "Summarize one concept learned and one open technical question",
                    "Save a short practice exercise for the next session",
                    "Plan tomorrow's study topic independently of daily job-search results"
                ]
            }
        ]

        # Build granular interactive tasks
        tasks = [
            {
                "task_id": "task_1",
                "stage": "CONCEPT_MASTERY",
                "title": f"Review & Concept Setup: {primary_gap}",
                "duration_minutes": review_mins,
                "skill_tag": primary_gap,
                "status": "NOT_STARTED",
                "completed_at": None,
                "explanation": f"High-frequency vacancy requirement identified across active {target_role_clean} listings.",
                "resource_id": res_review.get("id") if res_review else None,
                "resource_title": res_review.get("title") if res_review else f"{primary_gap} Documentation",
                "resource_url": res_review.get("canonical_url") if res_review else "https://mode.com/sql-tutorial/"
            },
            {
                "task_id": "task_2",
                "stage": "HANDS_ON_CODING",
                "title": f"Hands-On Query & Coding Practice: {primary_gap}",
                "duration_minutes": coding_mins,
                "skill_tag": primary_gap,
                "status": "NOT_STARTED",
                "completed_at": None,
                "explanation": f"Directly addresses primary technical evaluation criteria in target role interviews.",
                "resource_id": res_coding.get("id") if res_coding else None,
                "resource_title": res_coding.get("title") if res_coding else f"Interactive {primary_gap} Playground",
                "resource_url": res_coding.get("canonical_url") if res_coding else "https://sqlzoo.net/"
            },
            {
                "task_id": "task_3",
                "stage": "PROJECT_ARCHITECTURE",
                "title": f"Architecture & Defense: {secondary_gap} & {cloud_gap}",
                "duration_minutes": arch_mins,
                "skill_tag": secondary_gap,
                "status": "NOT_STARTED",
                "completed_at": None,
                "explanation": f"Connects {secondary_gap} to candidate portfolio projects (e.g. Loan Risk Dashboard).",
                "resource_id": res_arch.get("id") if res_arch else None,
                "resource_title": res_arch.get("title") if res_arch else f"{secondary_gap} Best Practices",
                "resource_url": res_arch.get("canonical_url") if res_arch else "https://learn.microsoft.com/en-us/training/powerplatform/"
            },
            {
                "task_id": "task_4",
                "stage": "BEHAVIORAL_DEFENSE",
                "title": "STAR Behavioral Formulation & Reflection",
                "duration_minutes": behavioral_mins,
                "skill_tag": "Interview Readiness",
                "status": "NOT_STARTED",
                "completed_at": None,
                "explanation": "Grounds interview responses in confirmed candidate evidence and projects.",
                "resource_id": None,
                "resource_title": "STAR Method Behavioral Guide",
                "resource_url": "https://www.themuse.com/advice/star-interview-method"
            }
        ]

        top_three_priorities = [
            f"1. Practice {primary_gap} using realistic sample tables and verifiable assertions.",
            f"2. Study {secondary_gap} report modeling, metric definitions, and data storytelling.",
            f"3. Advance {cloud_gap} as a learning target; maintain transparent candidate evidence boundaries."
        ]

        plan_date = local_now.strftime("%Y-%m-%d")

        plan_dict = {
            "date": local_now.strftime("%A, %B %d, %Y"),
            "plan_date": plan_date,
            "target_session_time": f"08:00 PM {SETTINGS.TIMEZONE}",
            "allocated_hours": allocated_hours,
            "daily_budget_minutes": daily_budget_minutes,
            "target_priority": target_priority,
            "focus_role": target_role_clean,
            "target_role": target_role_clean,
            "top_three_priorities": top_three_priorities,
            "schedule_blocks": schedule_blocks,
            "tasks": tasks,
            "skill_gaps": top_gaps,
            "user_skills": gaps_info.get("candidate_skills", {}),
            "notes": "",
            "is_completed": False,
            "is_evening_session_ready": True
        }

        # Persist to daily_study_plans table
        if save_to_db:
            try:
                plan_id = save_daily_study_plan(plan_dict)
                plan_dict["id"] = plan_id
            except Exception:
                plan_dict["id"] = 1

        return plan_dict

    def _add_minutes_to_time_str(self, time_str: str, minutes_to_add: int) -> str:
        """Helper to format incremental time strings like '08:45 PM'."""
        try:
            base = datetime.strptime(time_str.replace(" IST", "").strip(), "%I:%M %p")
            new_time = base + timedelta(minutes=minutes_to_add)
            return new_time.strftime("%I:%M %p")
        except Exception:
            return time_str
