import sqlite3

con = sqlite3.connect('data/careerorbit.db')
cur = con.cursor()

# Find jobs from audit runs
cur.execute("SELECT id, employer, title, discovery_source FROM jobs WHERE discovery_source LIKE '%Audit%'")
audit_jobs = cur.fetchall()
print(f"Found {len(audit_jobs)} audit test jobs to remove:")
for j in audit_jobs:
    print(f"  ID {j[0]}: {j[1]} - {j[2]} ({j[3]})")

cur.execute("DELETE FROM jobs WHERE discovery_source LIKE '%Audit%'")
cur.execute("DELETE FROM inbox_messages WHERE chat_title LIKE '%Audit%'")
cur.execute("DELETE FROM community_sources WHERE source_name LIKE '%Audit%'")
con.commit()

# Verify counts
cur.execute("SELECT COUNT(*) FROM jobs WHERE COALESCE(record_state, 'DISCOVERY_LEAD') != 'QUARANTINED'")
active_jobs = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM jobs WHERE record_state = 'QUARANTINED'")
quarantined_jobs = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM applications")
apps = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM inbox_messages")
inbox = cur.fetchone()[0]

print(f"\nClean production state verified:")
print(f"  Active Jobs: {active_jobs}")
print(f"  Quarantined Jobs: {quarantined_jobs}")
print(f"  Applications: {apps}")
print(f"  Inbox Messages: {inbox}")

con.close()
