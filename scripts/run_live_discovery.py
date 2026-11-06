import logging
from careerorbit.discovery.engine import JobDiscoveryEngine
from careerorbit.database.db import get_connection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("discovery_runner")

print("Initializing discovery engine...")
engine = JobDiscoveryEngine()
print(f"Sources configured: {len(engine.sources)}")

def callback(stage, sources):
    print(f"[Progress] {stage}")

print("Running discovery across configured live sources...")
res = engine.run_discovery(initial_days=30, min_acceptable=5, progress_callback=callback)
print("\n--- DISCOVERY RESULTS ---")
print(f"Total collected: {res.get('total_collected')}")
print(f"New jobs: {res.get('new_jobs')}")
print(f"Updated jobs: {res.get('updated_jobs')}")
print(f"Partial failure: {res.get('partial_failure')}")

print("\n--- SOURCE BREAKDOWN ---")
for s_name, s_info in res.get('sources', {}).items():
    print(f" * {s_name}: status={s_info.get('status')}, accepted={s_info.get('count')}, raw={s_info.get('raw_count')}")

conn = get_connection()
c = conn.cursor()
active_rows = c.execute("SELECT id, employer, title, location, priority_label, match_score, match_tier, verification_status, official_url, application_url FROM jobs WHERE record_state != 'QUARANTINED'").fetchall()
print(f"\n--- ACTIVE DATABASE VACANCIES (Total: {len(active_rows)}) ---")
for r in active_rows:
    print(f"[{r['id']}] {r['employer']} | {r['title']} | {r['location']}")
    print(f"     Priority: {r['priority_label']} | Score: {r['match_score']} ({r['match_tier']}) | Verification: {r['verification_status']}")
    print(f"     Official URL: {r['official_url']}")
    print(f"     Application URL: {r['application_url']}")
conn.close()
