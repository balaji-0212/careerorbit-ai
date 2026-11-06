"""Remediate and synchronize all database job records with updated JobScorer and eligibility rules.

Updates:
- priority_category & priority_label
- match_score & match_tier
- score_breakdown
- disqualifiers
- supported_skills, missing_skills, learnable_skills
- evidence_notes & recommended_action
"""

import json
import sqlite3
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from careerorbit.database.db import get_connection
from careerorbit.matcher.scorer import JobScorer
from careerorbit.eligibility import classify_title_to_priority, PRIORITY_LABELS


def remediate_database():
    scorer = JobScorer()
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT id, employer, title, description, location, work_arrangement, salary,
               shift, posting_date, posting_date_confidence, verification_status
        FROM jobs;
    """)
    rows = cur.fetchall()
    print(f"Loaded {len(rows)} job records from database for remediation.")

    updated_count = 0
    ineligible_count = 0

    for r in rows:
        job_id = r["id"]
        title = r["title"] or ""
        desc = r["description"] or ""

        p_category = classify_title_to_priority(title, desc)
        p_label = PRIORITY_LABELS.get(p_category, "Other relevant early-career technical roles")

        score_res = scorer.score_job({
            "title": title,
            "description": desc,
            "location": r["location"],
            "work_arrangement": r["work_arrangement"],
            "salary": r["salary"],
            "shift": r["shift"],
            "posting_date": r["posting_date"],
            "posting_date_confidence": r["posting_date_confidence"],
            "verification_status": r["verification_status"],
        })

        match_score = score_res["match_score"]
        match_tier = score_res["match_tier"].value
        score_bd_json = score_res["score_breakdown"].model_dump_json()
        disqualifiers_json = json.dumps(score_res["disqualifiers"])
        supported_skills_json = json.dumps(score_res["supported_skills"])
        missing_skills_json = json.dumps(score_res["missing_skills"])
        learnable_skills_json = json.dumps(score_res["learnable_skills"])
        evidence_notes = score_res["evidence_notes"]
        recommended_action = score_res["recommended_action"]

        if match_tier == "Ineligible":
            ineligible_count += 1

        cur.execute("""
            UPDATE jobs
            SET priority_category = ?,
                priority_label = ?,
                match_score = ?,
                match_tier = ?,
                score_breakdown = ?,
                disqualifiers = ?,
                supported_skills = ?,
                missing_skills = ?,
                learnable_skills = ?,
                evidence_notes = ?,
                recommended_action = ?
            WHERE id = ?;
        """, (
            p_category,
            p_label,
            match_score,
            match_tier,
            score_bd_json,
            disqualifiers_json,
            supported_skills_json,
            missing_skills_json,
            learnable_skills_json,
            evidence_notes,
            recommended_action,
            job_id,
        ))
        updated_count += 1

    conn.commit()
    conn.close()
    print(f"Successfully remediated {updated_count} records ({ineligible_count} categorized as Ineligible).")


if __name__ == "__main__":
    remediate_database()
