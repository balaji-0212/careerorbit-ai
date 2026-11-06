"""Live server probe verification script.
Tests live HTTP endpoints on running CareerOrbit AI instance at http://127.0.0.1:8000.
"""

import json
import urllib.request
import sys

BASE_URL = "http://127.0.0.1:8000"

def test_live_server():
    endpoints = [
        "/api/health",
        "/api/stats",
        "/api/jobs?limit=5",
        "/api/study/plan/today",
        "/api/scheduler/status",
        "/api/assessments/challenges",
        "/api/resources?limit=5",
    ]

    all_passed = True
    print(f"Connecting to live server at {BASE_URL}...\n")

    for ep in endpoints:
        url = BASE_URL + ep
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=5) as resp:
                status = resp.status
                payload = json.loads(resp.read().decode("utf-8"))
                print(f"[OK] {ep} -> HTTP {status}")
                if ep == "/api/health":
                    print(f"     Status: {payload.get('status')} | Service: {payload.get('service')}")
                elif ep == "/api/stats":
                    print(f"     Active Leads: {payload.get('total_jobs')} | Verified Open: {payload.get('verified_open')}")
                elif ep.startswith("/api/jobs"):
                    jobs = payload if isinstance(payload, list) else payload.get("jobs", [])
                    print(f"     Retrieved {len(jobs)} active jobs:")
                    for j in jobs[:3]:
                        print(f"       • [{j.get('priority_label')}] {j.get('employer')} - {j.get('title')} ({j.get('match_score')}/100, {j.get('verification_status')})")
                elif ep == "/api/study/plan/today":
                    print(f"     Date: {payload.get('plan_date')} | Target Role: {payload.get('target_role')} | Tasks: {len(payload.get('tasks', []))}")
                elif ep == "/api/scheduler/status":
                    print(f"     Scheduler Active: {payload.get('scheduler_running')} | IST: {payload.get('current_ist_time')}")
                elif ep == "/api/assessments/challenges":
                    print(f"     Assessment Challenges Available: {len(payload)}")
                elif ep.startswith("/api/resources"):
                    print(f"     Learning Resources Available: {len(payload)}")
        except Exception as exc:
            print(f"[FAIL] {ep} -> {type(exc).__name__}: {exc}")
            all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("ALL LIVE ENDPOINTS RESPONDED WITH HTTP 200 OK — PERFECTLY HEALTHY!")
    else:
        print("SOME ENDPOINTS RETURNED ERRORS")
        sys.exit(1)

if __name__ == "__main__":
    test_live_server()
