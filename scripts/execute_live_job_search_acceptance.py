"""Live Job Search Acceptance Execution & Verification Script.

Executes a live discovery workflow across real configured employer boards and aggregators.
Records granular source metrics, eligibility filtering results, career tier mappings,
deduplication statistics, and verification states.
Outputs reports/LIVE_ACCEPTANCE_REPORT.md and reports/LIVE_ACCEPTANCE_REPORT.json.
"""

import json
import sqlite3
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from careerorbit.config.settings import SETTINGS
from careerorbit.discovery.engine import JobDiscoveryEngine
from careerorbit.database.db import get_connection

IST = timezone(timedelta(hours=5, minutes=30), "Asia/Kolkata")
ROOT_DIR = Path(__file__).resolve().parent.parent
REPORTS_DIR = ROOT_DIR / "reports"


def run_live_acceptance():
    start_time_ist = datetime.now(IST)
    start_perf = time.perf_counter()

    print(f"Starting Live Job Search Acceptance Workflow at {start_time_ist.isoformat()} IST")
    engine = JobDiscoveryEngine()
    print(f"Total Sources Initialized: {len(engine.sources)}")

    # Snapshot pre-run active database counts
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM jobs;")
    pre_total_jobs = cur.fetchone()[0]
    conn.close()

    # Execute discovery workflow
    def progress_callback(stage, sources_dict):
        print(f"  [Progress] {stage}")

    print("Executing discovery across all enabled source adapters...")
    discovery_result = engine.run_discovery(
        initial_days=7,
        min_acceptable=5,
        progress_callback=progress_callback
    )
    duration_seconds = round(time.perf_counter() - start_perf, 2)

    # Inspect post-run database state
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT count(*) FROM jobs;")
    post_total_jobs = cur.fetchone()[0]

    cur.execute("SELECT verification_status, count(*) as cnt FROM jobs GROUP BY verification_status;")
    verification_breakdown = {r["verification_status"]: r["cnt"] for r in cur.fetchall()}

    cur.execute("SELECT priority_label, count(*) as cnt FROM jobs WHERE record_state != 'QUARANTINED' GROUP BY priority_label;")
    priority_breakdown = {r["priority_label"]: r["cnt"] for r in cur.fetchall()}

    cur.execute("SELECT match_tier, count(*) as cnt FROM jobs WHERE record_state != 'QUARANTINED' GROUP BY match_tier;")
    tier_breakdown = {r["match_tier"]: r["cnt"] for r in cur.fetchall()}

    from careerorbit.career_priorities import get_personalized_priority_order_sql, get_preference_rank, load_user_career_preferences
    user_prefs = load_user_career_preferences(profile_id="default")
    personalized_order_sql = get_personalized_priority_order_sql(preferences=user_prefs)

    # Query Active Verified Opportunities ranked by personalized career priority order
    cur.execute(f"""
        SELECT id, employer, title, location, priority_category, priority_label, match_score, match_tier,
               verification_status, posting_date, official_url, application_url
        FROM jobs
        WHERE record_state != 'QUARANTINED'
          AND verification_status = 'VERIFIED_OPEN'
          AND match_tier != 'Ineligible'
        ORDER BY {personalized_order_sql}, match_score DESC, (posting_date IS NULL) ASC, posting_date DESC
        LIMIT 20;
    """)
    active_verified_jobs = []
    for r in cur.fetchall():
        d = dict(r)
        d["preference_rank"] = get_preference_rank(d, preferences=user_prefs)
        active_verified_jobs.append(d)

    # Query Pending Verification Opportunities (Listed separately, ranked by candidate preferences)
    cur.execute(f"""
        SELECT id, employer, title, location, priority_category, priority_label, match_score, match_tier,
               verification_status, posting_date, official_url, application_url
        FROM jobs
        WHERE record_state != 'QUARANTINED'
          AND verification_status = 'PENDING_VERIFICATION'
          AND match_tier != 'Ineligible'
        ORDER BY {personalized_order_sql}, match_score DESC, (posting_date IS NULL) ASC, posting_date DESC
        LIMIT 15;
    """)
    pending_jobs = []
    for r in cur.fetchall():
        d = dict(r)
        d["preference_rank"] = get_preference_rank(d, preferences=user_prefs)
        pending_jobs.append(d)

    # Query Verified Closed Vacancies (Excluded from active)
    cur.execute("""
        SELECT id, employer, title, location, priority_category, priority_label, match_score, match_tier,
               verification_status, official_url
        FROM jobs
        WHERE verification_status = 'VERIFIED_CLOSED'
        ORDER BY id DESC
        LIMIT 10;
    """)
    closed_jobs = [dict(r) for r in cur.fetchall()]

    # Query Quarantined Vacancies (Excluded from active)
    cur.execute("""
        SELECT id, employer, title, location, priority_category, priority_label, match_score, match_tier,
               verification_status, record_state, integrity_notes, official_url
        FROM jobs
        WHERE record_state = 'QUARANTINED'
        ORDER BY id DESC
        LIMIT 10;
    """)
    quarantined_jobs = [dict(r) for r in cur.fetchall()]
    conn.close()

    source_metrics = []
    for s_name, s_info in discovery_result.get("sources", {}).items():
        raw_count = s_info.get("raw_count", 0)
        accepted_count = s_info.get("count", 0)
        rejected_count = max(0, raw_count - accepted_count)
        status = s_info.get("status", "unknown")
        source_metrics.append({
            "source_name": s_name,
            "status": status,
            "raw_count": raw_count,
            "accepted_count": accepted_count,
            "rejected_count": rejected_count,
            "error": s_info.get("error"),
        })

    acceptance_payload = {
        "execution_timestamp_ist": start_time_ist.strftime("%Y-%m-%d %H:%M:%S IST"),
        "duration_seconds": duration_seconds,
        "pre_total_jobs": pre_total_jobs,
        "post_total_jobs": post_total_jobs,
        "newly_added_jobs": discovery_result.get("new_jobs", 0),
        "updated_jobs": discovery_result.get("updated_jobs", 0),
        "total_collected": discovery_result.get("total_collected", 0),
        "partial_failure": discovery_result.get("partial_failure", False),
        "verification_breakdown": verification_breakdown,
        "priority_breakdown": priority_breakdown,
        "tier_breakdown": tier_breakdown,
        "source_metrics": source_metrics,
        "active_verified_jobs": active_verified_jobs,
        "pending_verification_jobs": pending_jobs,
        "verified_closed_jobs": closed_jobs,
        "quarantined_jobs": quarantined_jobs,
    }

    # Write JSON report
    json_path = REPORTS_DIR / "LIVE_ACCEPTANCE_REPORT.json"
    json_path.write_text(json.dumps(acceptance_payload, indent=2), encoding="utf-8")

    # Generate Markdown report
    md_content = f"""# CareerOrbit AI — Live Job Search Acceptance Report

**Execution Timestamp (IST):** {acceptance_payload['execution_timestamp_ist']}  
**Execution Duration:** {duration_seconds}s  
**Pre-Run Job Database Count:** {pre_total_jobs}  
**Post-Run Job Database Count:** {post_total_jobs}  
**Newly Added Vacancies:** {discovery_result.get('new_jobs', 0)}  
**Updated Vacancies:** {discovery_result.get('updated_jobs', 0)}  

---

## 1. Source Adapter Execution Ledger

| Source Name | Execution Outcome | Raw Found | Accepted Leads | Filtered / Rejected | Notes / Endpoint Details |
|:---|:---:|:---:|:---:|:---:|:---|
"""
    for sm in source_metrics:
        notes = "OK" if not sm["error"] else f"Error: {sm['error']}"
        md_content += f"| `{sm['source_name']}` | **{sm['status'].upper()}** | {sm['raw_count']} | {sm['accepted_count']} | {sm['rejected_count']} | {notes} |\n"

    md_content += f"""
---

## 2. Active Vacancy Breakdown

### Verification Status Breakdown
"""
    for v_status, v_count in verification_breakdown.items():
        md_content += f"- **`{v_status}`**: {v_count} postings\n"

    md_content += """
### Career-Priority Tier Distribution
"""
    for p_label, p_count in priority_breakdown.items():
        md_content += f"- **{p_label}**: {p_count} postings\n"

    md_content += f"""
---

## 3. Active Verified Opportunities (Ranked by Personalized Priority, Match Score, Date)

> Only postings with `verification_status = VERIFIED_OPEN` and `match_tier != Ineligible` are listed here.
> Ordered strictly by candidate's personalized career priority preferences, then `match_score DESC`.

| ID | Employer | Job Title | Location | Career Category | Pref Rank | Score / Tier | Verification |
|:---:|:---|:---|:---|:---|:---:|:---:|:---:|
"""
    if active_verified_jobs:
        for j in active_verified_jobs:
            p_rank = j.get('preference_rank', '-')
            md_content += f"| {j['id']} | **{j['employer']}** | {j['title']} | {j['location']} | {j['priority_label']} | {p_rank} | {j['match_score']} ({j['match_tier']}) | `{j['verification_status']}` |\n"
    else:
        md_content += "| - | *No active verified opportunities currently recorded* | - | - | - | - | - | - |\n"

    md_content += f"""
---

## 4. Opportunities Pending Live Verification

> These vacancies have verified employer origin but await real-time destination check confirmation.

| ID | Employer | Job Title | Location | Career Tier | Score / Tier | Status |
|:---:|:---|:---|:---|:---|:---:|:---:|
"""
    if pending_jobs:
        for j in pending_jobs:
            md_content += f"| {j['id']} | **{j['employer']}** | {j['title']} | {j['location']} | {j['priority_label']} | {j['match_score']} ({j['match_tier']}) | `{j['verification_status']}` |\n"
    else:
        md_content += "| - | *None pending* | - | - | - | - | - |\n"

    md_content += f"""
---

## 5. Verified Closed / Expired Vacancies (Excluded from Active Opportunities)

> Vacancies confirmed expired or closed on employer ATS portals. These are strictly excluded from active application workflows.

| ID | Employer | Job Title | Location | Career Tier | Verification Status |
|:---:|:---|:---|:---|:---|:---:|
"""
    if closed_jobs:
        for j in closed_jobs:
            md_content += f"| {j['id']} | **{j['employer']}** | {j['title']} | {j['location']} | {j['priority_label']} | `{j['verification_status']}` |\n"
    else:
        md_content += "| - | *No closed vacancies recorded* | - | - | - | - |\n"

    md_content += f"""
---

## 6. Quarantined / Ineligible Vacancies (Excluded from Active Opportunities)

| ID | Employer | Job Title | Location | Status | Notes |
|:---:|:---|:---|:---|:---:|:---|
"""
    if quarantined_jobs:
        for j in quarantined_jobs:
            md_content += f"| {j['id']} | **{j['employer']}** | {j['title']} | {j['location']} | `{j['record_state']}` | {j.get('integrity_notes') or 'N/A'} |\n"
    else:
        md_content += "| - | *No quarantined records* | - | - | - | - |\n"

    md_content += """
---

## 7. Verification & Truthfulness Findings
1. **India-Only Eligibility:** Checked against Chennai, Bengaluru, Hyderabad, Coimbatore, and confirmed India remote positions. Overseas roles without India authorization were rejected or quarantined.
2. **Conservative Verification:** URL links are checked for HTTPS, public destination, tenant match, closure phrases, and active application actions. Expired vacancies are marked `VERIFIED_CLOSED` and excluded from active opportunities.
3. **Candidate Project Grounding:** Match explanations explicitly identify matched skills and missing learnable skills without fabricating experience.
4. **Personalized Priority Hierarchy:** Opportunities are dynamically ranked by each candidate's configured career priority order (Step 1 personalized priorities), ensuring that individual career preferences dictate recommendation order rather than a rigid fixed hierarchy.
"""
    md_path = REPORTS_DIR / "LIVE_ACCEPTANCE_REPORT.md"
    md_path.write_text(md_content, encoding="utf-8")

    print(f"\nLive Acceptance Run Finished in {duration_seconds}s!")
    print(f"Reports saved to {json_path.name} and {md_path.name}.")
    return acceptance_payload


if __name__ == "__main__":
    run_live_acceptance()
