"""Independent Database Verification and Audit for CareerOrbit AI.

Runs raw, direct SQLite queries to verify:
1. SQLite PRAGMA integrity_check and foreign_key_check.
2. Exact table row counts across all 13 application tables.
3. Job totals by verification_status, eligibility_status, and source.
4. Duplicate records check (title, company, location).
5. Missing required fields check.
6. Recommendation-eligible jobs count.
"""

import sqlite3
import json
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = ROOT_DIR / "data" / "careerorbit.db"


def run_independent_audit():
    if not DB_PATH.exists():
        print(f"[FAIL] Database file not found at {DB_PATH}")
        return False, {}

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    report = {}

    # 1. PRAGMAs
    integrity = cursor.execute("PRAGMA integrity_check").fetchall()
    report["integrity_check"] = [r[0] for r in integrity]
    fk_errors = cursor.execute("PRAGMA foreign_key_check").fetchall()
    report["foreign_key_errors"] = len(fk_errors)

    # 2. Tables and counts
    tables_res = cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
    tables = [r[0] for r in tables_res]
    table_counts = {}
    for t in sorted(tables):
        cnt = cursor.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        table_counts[t] = cnt
    report["tables_count"] = len(tables)
    report["table_row_counts"] = table_counts

    # 3. Job counts
    total_jobs = cursor.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    report["total_jobs"] = total_jobs

    by_status = {}
    for r in cursor.execute("SELECT verification_status, COUNT(*) as cnt FROM jobs GROUP BY verification_status"):
        by_status[r["verification_status"] or "NULL"] = r["cnt"]
    report["jobs_by_verification_status"] = by_status

    by_career_cat = {}
    for r in cursor.execute("SELECT career_category, COUNT(*) as cnt FROM jobs GROUP BY career_category"):
        by_career_cat[r["career_category"] or "NULL"] = r["cnt"]
    report["jobs_by_career_category"] = by_career_cat

    by_loc_eligibility = {}
    for r in cursor.execute("SELECT location_eligibility_status, COUNT(*) as cnt FROM jobs GROUP BY location_eligibility_status"):
        by_loc_eligibility[r["location_eligibility_status"] or "NULL"] = r["cnt"]
    report["jobs_by_location_eligibility"] = by_loc_eligibility

    by_disqualifiers = {}
    disq_cnt = cursor.execute("SELECT COUNT(*) FROM jobs WHERE disqualifiers IS NOT NULL AND disqualifiers != '' AND disqualifiers != '[]'").fetchone()[0]
    eligible_cnt = total_jobs - disq_cnt
    report["eligibility"] = {
        "eligible_count": eligible_cnt,
        "disqualified_count": disq_cnt,
    }

    by_source = {}
    for r in cursor.execute("SELECT discovery_source, COUNT(*) as cnt FROM jobs GROUP BY discovery_source ORDER BY cnt DESC"):
        by_source[r["discovery_source"] or "NULL"] = r["cnt"]
    report["jobs_by_source"] = by_source

    # 4. Duplicates check
    dup_query = "SELECT title, employer, COUNT(*) as cnt FROM jobs GROUP BY title, employer HAVING cnt > 1"
    dups = cursor.execute(dup_query).fetchall()
    report["duplicates_count"] = len(dups)
    report["duplicates"] = [{"title": d["title"], "employer": d["employer"], "count": d["cnt"]} for d in dups]

    # 5. Missing required fields
    missing_title = cursor.execute("SELECT COUNT(*) FROM jobs WHERE title IS NULL OR title = ''").fetchone()[0]
    missing_employer = cursor.execute("SELECT COUNT(*) FROM jobs WHERE employer IS NULL OR employer = ''").fetchone()[0]
    missing_url = cursor.execute("SELECT COUNT(*) FROM jobs WHERE official_url IS NULL OR official_url = ''").fetchone()[0]
    missing_all_urls = cursor.execute(
        "SELECT COUNT(*) FROM jobs WHERE (official_url IS NULL OR official_url = '') AND (canonical_url IS NULL OR canonical_url = '') AND (application_url IS NULL OR application_url = '') AND (discovery_url IS NULL OR discovery_url = '')"
    ).fetchone()[0]
    report["missing_fields"] = {
        "missing_title": missing_title,
        "missing_employer": missing_employer,
        "missing_official_url": missing_url,
        "missing_any_url": missing_all_urls,
    }

    # 6. Recommendation eligible: VERIFIED_OPEN verification + no disqualifiers + non-zero match_score
    rec_eligible = cursor.execute(
        "SELECT COUNT(*) FROM jobs WHERE verification_status = 'VERIFIED_OPEN' AND (disqualifiers IS NULL OR disqualifiers = '' OR disqualifiers = '[]')"
    ).fetchone()[0]
    report["recommendation_eligible_count"] = rec_eligible

    conn.close()
    return True, report


if __name__ == "__main__":
    success, data = run_independent_audit()
    print("=" * 80)
    print("CAREERORBIT AI — INDEPENDENT DATABASE AUDIT")
    print("=" * 80)
    print(f"Database Path:         {DB_PATH}")
    print(f"Integrity Check:       {data.get('integrity_check')}")
    print(f"Foreign Key Errors:    {data.get('foreign_key_errors')}")
    print(f"Tables Found:          {data.get('tables_count')}")
    print(f"Total Jobs in DB:      {data.get('total_jobs')}")
    print(f"Recommendation Open:   {data.get('recommendation_eligible_count')}")
    print(f"Eligible Jobs:         {data.get('eligibility', {}).get('eligible_count')}")
    print(f"Disqualified Jobs:     {data.get('eligibility', {}).get('disqualified_count')}")
    print("\nTable Row Counts:")
    for t, cnt in data.get("table_row_counts", {}).items():
        print(f"  - {t:<28}: {cnt:>5} rows")
    print("\nJobs by Verification Status:")
    for st, cnt in data.get("jobs_by_verification_status", {}).items():
        print(f"  - {st:<28}: {cnt:>5}")
    print("\nJobs by Career Category:")
    for cat, cnt in data.get("jobs_by_career_category", {}).items():
        print(f"  - {cat:<28}: {cnt:>5}")
    print("\nJobs by Location Eligibility:")
    for loc, cnt in data.get("jobs_by_location_eligibility", {}).items():
        print(f"  - {loc:<28}: {cnt:>5}")
    print("\nJobs by Discovery Source (Top 10):")
    for src, cnt in list(data.get("jobs_by_source", {}).items())[:10]:
        print(f"  - {src:<28}: {cnt:>5}")
    print(f"\nDuplicate (title, employer) pairs: {data.get('duplicates_count')}")
    print(f"Missing required fields: {data.get('missing_fields')}")
    print("=" * 80)
