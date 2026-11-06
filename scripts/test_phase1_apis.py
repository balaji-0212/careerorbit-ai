import urllib.request
import json

base = "http://127.0.0.1:8000"

def get(path):
    req = urllib.request.urlopen(f"{base}{path}")
    return json.loads(req.read().decode())

def post(path, data=None):
    req = urllib.request.Request(
        f"{base}{path}",
        data=json.dumps(data or {}).encode() if data else b"{}",
        headers={"Content-Type": "application/json"}
    )
    res = urllib.request.urlopen(req)
    return json.loads(res.read().decode())

print("Testing Phase 1 Endpoints against live server:")
health = get("/api/sources/health")
print("1. Sources health: total =", health.get("total_sources"), "healthy =", health.get("healthy_count"))

sources = get("/api/job-sources")
print("2. Job sources count:", len(sources["sources"]))

worker_status = get("/api/verifier/status")
print("3. Verifier status:", worker_status.get("status"))

apps = get("/api/applications")
print("4. Applications count:", len(apps.get("applications", [])))
if apps.get("applications"):
    app_id = apps["applications"][0]["id"]
    hist = get(f"/api/applications/{app_id}/history")
    print(f"5. Application {app_id} history records:", len(hist.get("history", [])))

jobs = get("/api/jobs?limit=1")
if jobs.get("jobs"):
    job_id = jobs["jobs"][0]["id"]
    single_job = get(f"/api/jobs/{job_id}")
    print(f"6. Job {job_id} match score: {single_job.get('match_score')}")
    print(f"   Matched reqs: {len(single_job.get('matched_requirements', []))}")
    print(f"   Missing reqs: {len(single_job.get('missing_requirements', []))}")
    print(f"   Disclaimer: {single_job.get('disclaimer')[:60]}...")

# Test index.html contains newly added components
index_html = urllib.request.urlopen(f"{base}/").read().decode("utf-8")
assert "Verify Active Leads" in index_html, "Verify Active Leads button missing"
assert "verification-worker-panel" in index_html, "verification-worker-panel missing"
assert "application-history-modal" in index_html, "application-history-modal missing"
assert "confirm-submission-modal" in index_html, "confirm-submission-modal missing"
assert "sources-summary-cards" in index_html, "sources-summary-cards missing"
assert "Algorithmic Evaluation Disclaimer" in index_html, "Disclaimer text missing"

print("\n7. Frontend index.html served over HTTP 200 with all new Phase 1 components verified!")
print("\nALL PHASE 1 LIVE ENDPOINT CHECKS PASSED!")
