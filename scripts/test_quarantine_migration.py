import sqlite3
import shutil
from pathlib import Path

# Create disposable copy
src = Path("data/careerorbit.db")
test_db = Path("data/test_migration_disposable.db")
shutil.copyfile(src, test_db)

conn = sqlite3.connect(str(test_db))
conn.row_factory = sqlite3.Row
c = conn.cursor()

print("--- TESTING QUARANTINE CLASSIFICATION ON DISPOSABLE DB ---")
rows = c.execute("SELECT id, employer, title, location, discovery_source, record_state, location_eligibility_status FROM jobs").fetchall()
print(f"Total rows before: {len(rows)}")

quarantined_count = 0
for r in rows:
    job_id = r["id"]
    emp = r["employer"]
    title = r["title"]
    loc = r["location"]
    src_name = r["discovery_source"]
    state = r["record_state"]

    if state == "QUARANTINED":
        continue

    # Classify why it should be quarantined from active India results
    loc_lower = (loc or "").lower()
    is_overseas = any(k in loc_lower for k in ["usa", "united states", "canada", "germany", "japan", "singapore", "latam", "australia", "new zealand", "europe", "apac"])
    is_non_tech = any(k in title.lower() for k in ["health coach", "psychotherapist", "freelance writer", "freelance copywriter", "office assistant", "inside sales", "people business", "client advisor", "account executive"])

    notes = []
    loc_status = r["location_eligibility_status"]
    geo_p = 3

    if is_overseas:
        notes.append(f"Ineligible location: {loc} is outside India")
        loc_status = "INELIGIBLE_OVERSEAS"
    if is_non_tech:
        notes.append(f"Role title '{title}' is outside technical career priorities")
    notes.append("Lacks verified official employer listing or application URL")

    note_str = "; ".join(notes)
    c.execute("""
        UPDATE jobs 
        SET record_state = 'QUARANTINED',
            location_eligibility_status = ?,
            geographic_priority = ?,
            integrity_notes = ?
        WHERE id = ?
    """, (loc_status, geo_p, note_str, job_id))
    quarantined_count += 1

conn.commit()

c.execute("PRAGMA integrity_check")
status = c.fetchone()[0]

active = c.execute("SELECT COUNT(*) FROM jobs WHERE record_state != 'QUARANTINED'").fetchone()[0]
quarantined = c.execute("SELECT COUNT(*) FROM jobs WHERE record_state = 'QUARANTINED'").fetchone()[0]
total = c.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]

print(f"Migration completed on disposable DB. Integrity: {status}")
print(f"Rows quarantined this run: {quarantined_count}")
print(f"Total jobs: {total} | Active: {active} | Quarantined: {quarantined}")

conn.close()
test_db.unlink()
print("Disposable DB deleted cleanly after test.")
