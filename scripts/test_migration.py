"""Test Migration Script on Disposable Database Copy.
Verifies column additions and backfill without touching production DB.
"""
import sqlite3
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from careerorbit.matcher.geo import classify_geographic_priority

temp_db = Path("data/temp_test_migration.db")
shutil.copy2("data/careerorbit.db", temp_db)

conn = sqlite3.connect(temp_db)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# 1. Add columns
job_columns = {row[1] for row in cur.execute("PRAGMA table_info(jobs)").fetchall()}
migrations = [
    ("geographic_priority", "INTEGER NOT NULL DEFAULT 1"),
    ("geographic_tier_label", "TEXT NOT NULL DEFAULT 'Priority 1 — South India & India Remote'"),
    ("location_eligibility_status", "TEXT NOT NULL DEFAULT 'VERIFIED_INDIA_ELIGIBLE'"),
    ("city", "TEXT NOT NULL DEFAULT ''"),
    ("state", "TEXT NOT NULL DEFAULT ''"),
    ("country", "TEXT NOT NULL DEFAULT 'India'"),
    ("remote_eligibility", "TEXT NOT NULL DEFAULT 'INDIA_PERMITTED'"),
    ("geo_score", "REAL NOT NULL DEFAULT 10.0")
]

for col, col_type in migrations:
    if col not in job_columns:
        cur.execute(f"ALTER TABLE jobs ADD COLUMN {col} {col_type}")

# 2. Backfill existing jobs
rows = cur.execute("SELECT id, location, work_arrangement, description FROM jobs").fetchall()
print(f"Backfilling {len(rows)} jobs in disposable test copy...")
for r in rows:
    geo = classify_geographic_priority(r["location"] or "", r["work_arrangement"] or "", r["description"] or "")
    cur.execute("""
        UPDATE jobs SET
            geographic_priority = ?,
            geographic_tier_label = ?,
            location_eligibility_status = ?,
            city = ?,
            state = ?,
            country = ?,
            remote_eligibility = ?,
            geo_score = ?
        WHERE id = ?
    """, (
        geo["geographic_priority"],
        geo["geographic_tier_label"],
        geo["location_eligibility_status"],
        geo["city"],
        geo["state"],
        geo["country"],
        geo["remote_eligibility"],
        geo["geo_score"],
        r["id"]
    ))
conn.commit()

# 3. Check distribution
stats = cur.execute("""
    SELECT geographic_priority, geographic_tier_label, COUNT(*) 
    FROM jobs 
    WHERE COALESCE(record_state, 'DISCOVERY_LEAD') != 'QUARANTINED'
    GROUP BY geographic_priority
""").fetchall()

for row in stats:
    print(f"  Priority {row[0]}: {row[1]} -> {row[2]} jobs")

# 4. Check city distribution
city_stats = cur.execute("""
    SELECT city, COUNT(*)
    FROM jobs
    WHERE COALESCE(record_state, 'DISCOVERY_LEAD') != 'QUARANTINED'
    GROUP BY city
    ORDER BY COUNT(*) DESC
    LIMIT 10
""").fetchall()
print("\nTop cities in active leads:")
for c, cnt in city_stats:
    print(f"  {c}: {cnt}")

conn.close()
temp_db.unlink()
print("\nMigration test on disposable copy succeeded cleanly!")
