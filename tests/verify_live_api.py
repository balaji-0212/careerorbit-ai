"""Live Acceptance Verification Script for CareerOrbit AI.
Verifies all backend endpoints, data contracts, and response schemas against the running server.
"""
import requests
import json
import sys

BASE = 'http://127.0.0.1:8000'

def check(name, url, method='GET', data=None, status_code=200):
    if method == 'GET':
        r = requests.get(f'{BASE}{url}')
    elif method == 'POST':
        r = requests.post(f'{BASE}{url}', json=data)
    elif method == 'PUT':
        r = requests.put(f'{BASE}{url}', json=data)
    elif method == 'DELETE':
        r = requests.delete(f'{BASE}{url}')
    assert r.status_code == status_code, f"{name} failed: {r.status_code} - {r.text}"
    print(f"PASS: {name} ({r.status_code})")
    return r

def run():
    print("=" * 60)
    print("CAREERORBIT AI — LIVE ENDPOINT ACCEPTANCE TEST")
    print("=" * 60)

    # 1. Root & Health
    r_root = check('Root HTML', '/', status_code=200)
    assert '<!DOCTYPE html>' in r_root.text
    assert 'CareerOrbit AI' in r_root.text
    check('Health Check', '/api/health')

    # 2. Summary & Stats
    r_sum = check('Stats & Metrics', '/api/stats')
    sum_data = r_sum.json()
    metrics = sum_data.get('metrics', {})
    print(f"  [+] Active Leads: {metrics.get('total_jobs')}")
    print(f"  [+] South India / Remote (P1): {metrics.get('geo_p1_jobs')}")
    print(f"  [+] Other Indian Tech Hubs (P2): {metrics.get('geo_p2_jobs')}")
    print(f"  [+] Quarantined Records: {metrics.get('quarantined_jobs')}")
    print(f"  [+] Posted Last 24 Hours: {metrics.get('jobs_last_24h')}")
    print(f"  [+] Posted Last 7 Days: {metrics.get('jobs_last_7d')}")
    assert metrics.get('total_jobs', 0) > 0
    assert 'geo_p1_jobs' in metrics
    assert 'geo_p2_jobs' in metrics

    # Verify Security Headers
    assert r_sum.headers.get('x-content-type-options') == 'nosniff', "Missing X-Content-Type-Options: nosniff"
    assert r_sum.headers.get('x-frame-options') == 'DENY', "Missing X-Frame-Options: DENY"
    assert r_sum.headers.get('referrer-policy') == 'strict-origin-when-cross-origin', "Missing Referrer-Policy"
    print("  [+] Security headers verified: nosniff, DENY, strict-origin-when-cross-origin")

    # 3. Jobs Listing & Geographic Multi-Tier Filtering
    r_jobs = check('Jobs API (Default Priority)', '/api/jobs?limit=5')
    jobs = r_jobs.json().get('jobs', [])
    assert len(jobs) > 0
    top = jobs[0]
    print(f"  [+] Top Job: '{top.get('title')}' at '{top.get('employer')}'")
    print(f"      Score: {top.get('match_score')}/100 | Priority Category: {top.get('priority_category')} | Geo Priority: {top.get('geographic_priority')}")

    # Check P1 South India / India-Remote Filter
    r_p1 = check('Jobs API (Geo Priority 1)', '/api/jobs?geographic_priority=1&limit=5')
    p1_jobs = r_p1.json().get('jobs', [])
    assert all(j['geographic_priority'] == 1 for j in p1_jobs), "All returned jobs must have geographic_priority == 1"
    print(f"  [+] Verified {len(p1_jobs)} leads under Geographic Priority 1 (South India & India Remote)")

    # Check P2 Other Indian Hubs Filter
    r_p2 = check('Jobs API (Geo Priority 2)', '/api/jobs?geographic_priority=2&limit=5')
    p2_jobs = r_p2.json().get('jobs', [])
    assert all(j['geographic_priority'] == 2 for j in p2_jobs), "All returned jobs must have geographic_priority == 2"
    print(f"  [+] Verified {len(p2_jobs)} leads under Geographic Priority 2 (Other Indian Tech Hubs)")

    # Check City Filter
    r_blr = check('Jobs API (City: Bengaluru)', '/api/jobs?city=Bengaluru&limit=5')
    blr_jobs = r_blr.json().get('jobs', [])
    assert all('bengaluru' in (j.get('city') or '').lower() or 'bengaluru' in j.get('location', '').lower() for j in blr_jobs)
    print(f"  [+] Verified {len(blr_jobs)} leads filtered by City (Bengaluru)")

    # 4. Profile & Privacy
    r_prof = check('Candidate Profile', '/api/profile')
    prof = r_prof.json()
    assert 'phone' not in prof, "Candidate phone MUST NOT be exposed"
    assert 'email' not in prof, "Candidate email MUST NOT be exposed"
    evidence_summary = prof.get('candidate_evidence_summary', {})
    print(f"  [+] Evidence Summary: {evidence_summary}")
    assert 'confirmed_count' in evidence_summary
    assert evidence_summary.get('confirmed_count', 0) >= 12

    # 5. Field update & Audit History
    r_up = check('Field Level Update', '/api/profile/field', method='POST', data={
        'field_name': 'target_role',
        'value': 'Data Analyst & Associate Software Engineer',
        'evidence_state': 'CONFIRMED',
        'source': 'Live Acceptance Verification Suite',
        'notes': 'Verified field-level provenance audit trail'
    })
    up_data = r_up.json()
    assert up_data.get('status') == 'success' or up_data.get('ok') is True, f"Unexpected update response: {up_data}"

    r_hist = check('Profile Audit History', '/api/profile/history')
    history = r_hist.json().get('history', [])
    print(f"  [+] Audit history entries: {len(history)}")
    assert len(history) > 0
    latest_hist = history[-1]
    assert latest_hist.get('field') == 'target_role' or latest_hist.get('field_name') == 'target_role'

    # 6. Employer Registry CRUD
    r_reg = check('Registry List', '/api/sources/registry')
    sources = r_reg.json().get('sources', [])
    print(f"  [+] Configured employer sources: {len(sources)}")
    assert len(sources) >= 3

    # Add test source
    r_add = check('Registry Add', '/api/sources/registry', method='POST', data={
        'name': 'Live Acceptance Test Source',
        'type': 'greenhouse',
        'board_token': 'gusto',
        'company': 'Gusto',
        'enabled': False,
        'notes': 'Temporary source for live verification'
    })
    test_src = r_add.json().get('source')
    src_id = test_src['id']
    print(f"  [+] Created test source id: {src_id}")

    # Test connectivity
    r_conn = check('Registry Test Connectivity', f'/api/sources/registry/{src_id}/test', method='POST')
    conn_data = r_conn.json()
    print(f"  [+] Live connectivity check: Reachable={conn_data.get('reachable')}, Msg={conn_data.get('message')}")

    # Delete test source
    check('Registry Delete', f'/api/sources/registry/{src_id}', method='DELETE')
    print(f"  [+] Deleted test source id: {src_id}")

    # 7. Applications
    r_apps = check('Applications API', '/api/applications')
    apps = r_apps.json().get('applications', [])
    print(f"  [+] Existing applications count: {len(apps)}")

    # 8. Prep & Scheduler
    r_prep = check('Daily Study Plan', '/api/prep/daily-plan')
    prep_data = r_prep.json()
    print(f"  [+] Study Plan: {prep_data.get('date')} ({prep_data.get('target_session_time')})")

    r_coach = check('Interview Coach', '/api/interview-prep')
    coach_data = r_coach.json()
    print(f"  [+] Interview modules available: {len(coach_data.get('modules', []))}")

    r_sched = check('Scheduler Status', '/api/scheduler/status')
    sched_data = r_sched.json()
    print(f"  [+] Scheduler Active: {sched_data.get('scheduler_active')} | Timezone: {sched_data.get('timezone')}")

    print("=" * 60)
    print("ALL 14 REST ENDPOINTS VERIFIED AND PASSING SUCCESSFULLY!")
    print("=" * 60)

if __name__ == '__main__':
    run()
