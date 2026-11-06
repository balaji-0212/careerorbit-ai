import requests
import json

base = 'http://127.0.0.1:8000'

# 1. Job listing retrieval
jobs_res = requests.get(f'{base}/api/jobs?limit=5')
assert jobs_res.status_code == 200
jobs_data = jobs_res.json()
jobs = jobs_data['jobs']
print(f'[Phase 8.4] Job listing: Total={jobs_data["count"]}, Fetched={len(jobs)}. Top job: "{jobs[0]["title"]}" at {jobs[0]["employer"]}')

# 2. Job detail access
first_job_id = jobs[0]['id']
detail_res = requests.get(f'{base}/api/jobs/{first_job_id}')
assert detail_res.status_code == 200
job_detail = detail_res.json()
print(f'[Phase 8.5] Job detail: ID={first_job_id}, Title="{job_detail["title"]}", WorkArrangement={job_detail.get("work_arrangement")}')

# 3. Match explanation & scoring
match_expl = job_detail.get('match_explanation', {})
score = job_detail.get('match_score')
tier = job_detail.get('match_tier')
geo_p = job_detail.get('geographic_priority')
print(f'[Phase 8.6] Job match: Score={score}, Tier={tier}, GeoTier={geo_p}, MatchedReqCount={len(match_expl.get("matched_requirements", []))}')

# 4. Profile & Career Preferences
prof_res = requests.get(f'{base}/api/profile')
assert prof_res.status_code == 200
prof_data = prof_res.json()
has_email_or_phone = any(k in prof_data for k in ['email', 'phone', 'contact'])
print(f'[Phase 8.7] Profile: Candidate={prof_data.get("name")}, Roles={prof_data.get("target_roles", [])[:2]}, SensitiveContactWithheld={not has_email_or_phone}')

# 5. Application Tracking
apps_res = requests.get(f'{base}/api/applications')
assert apps_res.status_code == 200
apps_data = apps_res.json()
apps = apps_data['applications']
print(f'[Phase 8.8] Applications: Count={apps_data["count"]}, First stage={apps[0].get("status") if apps else "None"}')

# 6. Resume & Packages
resumes_res = requests.get(f'{base}/api/resumes')
assert resumes_res.status_code == 200
resumes = resumes_res.json()
print(f'[Phase 8.9] Resumes: Count={len(resumes)}')

# 7. Scheduler status
sched_res = requests.get(f'{base}/api/scheduler/status')
assert sched_res.status_code == 200
sched = sched_res.json()
print(f'[Phase 8.10] Scheduler: Running={sched.get("scheduler_running")}, TaskName={sched.get("canonical_task_name")}')

# 8. External sources / Registry
srcs_res = requests.get(f'{base}/api/job-sources')
assert srcs_res.status_code == 200
srcs = srcs_res.json()
print(f'[Phase 8.11] Sources: Count={srcs.get("count")}')

# 9. CSV Exports
exp_jobs = requests.get(f'{base}/api/export/jobs')
assert exp_jobs.status_code == 200 and 'text/csv' in exp_jobs.headers.get('content-type', '')
print(f'[Phase 8.12] CSV export: Jobs CSV bytes={len(exp_jobs.content)}')

# 10. Resource Library
res_res = requests.get(f'{base}/api/resources')
assert res_res.status_code == 200
print(f'[Phase 8.13] Resource Library: Count={res_res.json().get("count")}')

# 11. Study Analytics
study_res = requests.get(f'{base}/api/study/analytics/progress')
assert study_res.status_code == 200
print(f'[Phase 8.14] Study Analytics: Streak={study_res.json().get("current_streak")}, CompletionRate={study_res.json().get("completion_rate")}')

# 12. Assessment Challenges
chal_res = requests.get(f'{base}/api/assessments/challenges')
assert chal_res.status_code == 200
print(f'[Phase 8.15] Assessment Challenges: Count={len(chal_res.json().get("challenges", []))}')

print('\n[ALL CORE FEATURES VERIFIED SUCCESSFULLY!]')
