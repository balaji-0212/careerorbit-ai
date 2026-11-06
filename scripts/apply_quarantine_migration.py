import sqlite3
from datetime import datetime, timezone
from careerorbit.matcher.geo import classify_geographic_priority

conn = sqlite3.connect("data/careerorbit.db")
conn.row_factory = sqlite3.Row
c = conn.cursor()

c.execute("SELECT 1 FROM schema_migrations WHERE version = ?", ("2026-10-22-quarantine-overseas-and-unverified-leads",))
if c.fetchone():
    print("Migration already applied!")
else:
    rows = c.execute("SELECT id, employer, title, location, work_arrangement, description, discovery_source, record_state FROM jobs WHERE record_state = 'DISCOVERY_LEAD'").fetchall()
    print(f"Total DISCOVERY_LEAD rows to evaluate: {len(rows)}")
    
    quarantined = 0
    for r in rows:
        job_id = r["id"]
        emp = r["employer"]
        tit = r["title"]
        loc = r["location"] or ""
        arr = r["work_arrangement"] or ""
        desc = r["description"] or ""
        src = r["discovery_source"]
        
        geo = classify_geographic_priority(loc, arr, desc)
        loc_status = geo["location_eligibility_status"]
        geo_p = geo["geographic_priority"]
        
        notes = []
        if loc_status in ("INELIGIBLE_OVERSEAS", "RESTRICTED_NON_INDIA"):
            notes.append(f"Ineligible location: '{loc}' is outside India")
        elif loc_status == "LOCATION_ELIGIBILITY_UNCONFIRMED":
            notes.append(f"Unconfirmed location eligibility: '{loc}'")
        
        is_non_tech = any(k in tit.lower() for k in ["health coach", "psychotherapist", "freelance writer", "freelance copywriter", "office assistant", "inside sales", "people business", "client advisor", "account executive"])
        if is_non_tech:
            notes.append(f"Role '{tit}' is outside technical career priorities")
            
        notes.append(f"Aggregator lead from {src} without corroborated direct employer ATS application destination")
        integrity_str = "; ".join(notes)
        
        c.execute("""
            UPDATE jobs
            SET record_state = 'QUARANTINED',
                location_eligibility_status = ?,
                geographic_priority = ?,
                integrity_notes = ?
            WHERE id = ?
        """, (loc_status, geo_p, integrity_str, job_id))
        quarantined += 1
        
    c.execute("INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
              ("2026-10-22-quarantine-overseas-and-unverified-leads", datetime.now(timezone.utc).isoformat()))
    conn.commit()
    print(f"Successfully quarantined {quarantined} legacy aggregator rows with full audit preservation.")

c.execute("PRAGMA integrity_check")
print("DB Integrity check:", c.fetchone()[0])
conn.close()
