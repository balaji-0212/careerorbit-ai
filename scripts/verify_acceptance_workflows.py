import requests
import sys

base = 'http://127.0.0.1:8000'

print("[*] Testing CareerOrbit critical workflows against live server...")

# 1. Test Job Search & Filters
r1 = requests.get(f'{base}/api/jobs?limit=5&sort_by=score_desc')
assert r1.status_code == 200, f'Job search failed: {r1.status_code}'
jobs = r1.json().get('jobs', [])
assert len(jobs) > 0, 'No jobs returned'
job_id = jobs[0]['id']
print(f"[1] Job search OK, found {len(jobs)} jobs. Top job #{job_id}: {jobs[0]['employer']} - {jobs[0]['title']}")

# 2. Test Save Job Toggle
r_save = requests.post(f'{base}/api/jobs/{job_id}/save')
assert r_save.status_code == 200, f'Save job failed: {r_save.status_code}'
save_res = r_save.json()
print(f"[2] Save job toggle 1: is_saved={save_res.get('is_saved')}")

# Verify it appears in saved jobs
r_saved = requests.get(f'{base}/api/jobs?saved_only=true')
assert r_saved.status_code == 200
saved_list = r_saved.json().get('jobs', [])
assert any(j['id'] == job_id for j in saved_list), 'Saved job not in saved_jobs list'
print(f"    Saved jobs query verified: {len(saved_list)} saved leads found.")

# Unsave job to restore state
r_unsave = requests.post(f'{base}/api/jobs/{job_id}/save')
assert r_unsave.status_code == 200
print(f"    Unsave job toggle 2: is_saved={r_unsave.json().get('is_saved')}")

# 3. Test Export Jobs CSV
r_csv_jobs = requests.get(f'{base}/api/export/jobs')
assert r_csv_jobs.status_code == 200, f"Export jobs failed: {r_csv_jobs.status_code}"
assert 'text/csv' in r_csv_jobs.headers.get('Content-Type', '')
lines_jobs = r_csv_jobs.text.splitlines()
print(f"[3] Export Jobs CSV OK: {len(lines_jobs)} lines returned.")

# 4. Test Export Applications CSV
r_csv_apps = requests.get(f'{base}/api/export/applications')
assert r_csv_apps.status_code == 200, f"Export applications failed: {r_csv_apps.status_code}"
assert 'text/csv' in r_csv_apps.headers.get('Content-Type', '')
lines_apps = r_csv_apps.text.splitlines()
print(f"[4] Export Applications CSV OK: {len(lines_apps)} lines returned.")

# 5. Test Candidate Profile and Evidence Confirmation
r_prof = requests.get(f'{base}/api/profile/full')
assert r_prof.status_code == 200
pdata = r_prof.json()
cand_name = pdata.get('personal', {}).get('full_name', {}).get('value')
print(f"[5] Profile OK: Candidate={cand_name}")

r_ev = requests.post(f'{base}/api/profile/evidence', json={
    'field': 'personal.full_name',
    'state': 'CONFIRMED_BY_CANDIDATE',
    'evidence': 'Verified from degree certificate B.E. ECE 2025'
})
assert r_ev.status_code == 200
print(f"    Profile evidence confirmation OK: status={r_ev.json().get('field', {}).get('state')}")

# 6. Test Resumes Listing & Details
r_resumes = requests.get(f'{base}/api/resumes')
assert r_resumes.status_code == 200
res_data = r_resumes.json()
print(f"[6] Resumes listing OK: {len(res_data.get('resumes', []))} resumes present.")

# 7. Test Application Tracker Listing
r_apps = requests.get(f'{base}/api/applications')
assert r_apps.status_code == 200
apps_list = r_apps.json().get('applications', [])
print(f"[7] Applications listing OK: {len(apps_list)} tracked applications.")

# 8. Test Scheduler History
r_sched = requests.get(f'{base}/api/scheduler/history')
assert r_sched.status_code == 200
history = r_sched.json()
print(f"[8] Scheduler history OK: {len(history.get('runs', []))} recorded workflow runs.")

# 9. Test Sources Health
r_src_health = requests.get(f'{base}/api/sources/health')
assert r_src_health.status_code == 200
print(f"[9] Sources health OK: {len(r_src_health.json().get('sources', []))} configured source boards.")

# 10. Test Telegram Bot status
r_tg = requests.get(f'{base}/api/telegram/status')
assert r_tg.status_code == 200
tg_stat = r_tg.json()
print(f"[10] Telegram status OK: @{tg_stat.get('bot_username')} configured={tg_stat.get('configured')}")

# 11. Test URL Verification Engine
r_verify = requests.post(f'{base}/api/verify-url', json={'url': 'https://jobs.lever.co/hevodata'})
assert r_verify.status_code == 200
vdata = r_verify.json()
print(f"[11] Live URL verification OK: status={vdata.get('status')}, notes={vdata.get('notes')[:60]}...")

print("\n[SUCCESS] ALL 11 WORKFLOW VERIFICATION CHECKS PASSED WITH ZERO ERRORS!")
