"""CareerOrbit AI — Autonomous Job Search and Career Automation Platform
CLI and Dashboard Server Entry Point.
"""
import sys
import argparse
import logging
import uvicorn
from pathlib import Path
from careerorbit.config.settings import SETTINGS
from careerorbit.database.db import init_db
from careerorbit.discovery.engine import JobDiscoveryEngine
from careerorbit.prep.study_planner import DailyStudyPlanner
from careerorbit.scheduler.windows_task import generate_windows_task_script
from careerorbit.scheduler.run_history import record_run, workflow_lock
from careerorbit.security.network import is_loopback_host

logging.basicConfig(
    filename=str(SETTINGS.LOGS_DIR / "careerorbit_cli.log"),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

def banner():
    print(r"""
========================================================================
   ____                             ___       _     _ _         _    ___ 
  / ___|__ _ _ __ ___  ___ _ __    / _ \ _ __| |__ (_) |_      / \  |_ _|
 | |   / _` | '__/ _ \/ _ \ '__|  | | | | '__| '_ \| | __|    / _ \  | |  
 | |__| (_| | | |  __/  __/ |     | |_| | |  | |_) | | |_    / ___ \ | |  
  \____\__,_|_|  \___|\___|_|      \___/|_|  |_.__/|_|\__|  /_/   \_\___| 
========================================================================
  Autonomous Job Search, ATS Resume Tailoring & Career Automation
  Candidate facts remain subject to source review
========================================================================
""")

def main():
    parser = argparse.ArgumentParser(description="CareerOrbit AI Platform Launcher")
    parser.add_argument("--job-discovery", action="store_true", help="Run automated job discovery workflow immediately")
    parser.add_argument("--study-plan", action="store_true", help="Generate daily 8:00 PM IST study plan")
    parser.add_argument("--recheck-links", action="store_true", help="Recheck validity and freshness of active job listing links")
    parser.add_argument("--scheduler-status", action="store_true", help="Print scheduler status and Windows task inspection")
    parser.add_argument("--scheduler-diagnose", action="store_true", help="Run comprehensive scheduler self-diagnostics")
    parser.add_argument("--install-windows-tasks", action="store_true", help="Generate Windows Task Scheduler registration script")
    parser.add_argument("--daily-report", action="store_true", help="Print comprehensive daily job-search intelligence report")
    parser.add_argument("--port", type=int, default=SETTINGS.PORT, help="Port to bind dashboard server (default: 8000)")
    parser.add_argument("--host", type=str, default=SETTINGS.HOST, help="Host to bind dashboard server (default: 127.0.0.1)")

    args = parser.parse_args()
    if not is_loopback_host(args.host):
        parser.error(
            "CareerOrbit is a local-only application; bind only to localhost, 127.0.0.1, or ::1."
        )
    banner()

    # 1. Initialize SQLite database
    init_db()

    if args.job_discovery:
        print("[*] Running automated job discovery workflow across all 6 priority tiers...")
        with workflow_lock("job_discovery") as acquired:
            if not acquired:
                record_run("job_discovery", "skipped_overlap")
                print("[!] Another job-discovery workflow is running; this run was skipped.")
                sys.exit(0)
            try:
                result = JobDiscoveryEngine().run_discovery(initial_days=1, min_acceptable=30)
                summary = {k: result[k] for k in ("total_collected", "new_jobs_added", "jobs_updated", "time_window_days", "sources")}
                record_run("job_discovery", "success", summary=summary)
                logging.info("Job discovery succeeded: %s", summary)
                print(f"[+] Discovery completed! Found: {result['total_collected']}, Added: {result['new_jobs_added']}, Updated: {result['jobs_updated']}")
            except Exception as exc:
                record_run("job_discovery", "failed", error=type(exc).__name__)
                logging.exception("Job discovery failed")
                raise
        sys.exit(0)

    if args.study_plan:
        print("[*] Generating daily career study plan (Asia/Kolkata timezone)...")
        with workflow_lock("study_plan") as acquired:
            if not acquired:
                record_run("study_plan", "skipped_overlap")
                print("[!] Another study-plan workflow is running; this run was skipped.")
                sys.exit(0)
            try:
                plan = DailyStudyPlanner().generate_daily_plan()
                record_run("study_plan", "success", summary={"date": plan.get("date"), "target_session_time": plan.get("target_session_time")})
                logging.info("Study plan succeeded for %s", plan.get("date"))
            except Exception as exc:
                record_run("study_plan", "failed", error=type(exc).__name__)
                logging.exception("Study plan failed")
                raise
        print(f"[+] Study Plan Ready for {plan['date']} at {plan['target_session_time']}")
        print(f"[+] Top Priority: {plan['top_three_priorities'][0]}")
        sys.exit(0)

    if args.recheck_links:
        from careerorbit.verifier.checker import recheck_active_leads
        print("[*] Rechecking active job links against official employer & ATS endpoints...")
        with workflow_lock("recheck_links") as acquired:
            if not acquired:
                record_run("recheck_links", "skipped_overlap")
                print("[!] Another link verification workflow is running; this run was skipped.")
                sys.exit(0)
            try:
                res = recheck_active_leads(max_jobs=15, days_threshold=7)
                record_run("recheck_links", "success", summary={"checked": res["checked"], "open": res["verified_open"], "closed": res["verified_closed"]})
                print(f"[+] Link recheck complete. Checked: {res['checked']}, Open: {res['verified_open']}, Closed: {res['verified_closed']}, Unverified: {res['unverified']}")
            except Exception as exc:
                record_run("recheck_links", "failed", error=type(exc).__name__)
                logging.exception("Link recheck failed")
                raise
        sys.exit(0)

    if args.scheduler_status:
        from careerorbit.scheduler.runner import SCHEDULER
        status = SCHEDULER.get_status()
        print("=" * 72)
        print("CAREERORBIT AI — SCHEDULER & RUNNER STATUS")
        print("=" * 72)
        print(f"Current Time (IST):      {status['current_ist_time']}")
        print(f"Target Discovery Time:   {status['target_discovery_time']}")
        print(f"Canonical Task Name:     {status['canonical_task_name']}")
        print(f"In-Process Thread:       {'Running' if status['scheduler_running'] else 'Stopped / Idle'}")
        print(f"Last Successful Run:     {status['last_successful_discovery']}")

        last_att = status.get("last_attempt", {})
        print(f"Last Run Attempt:        Status: {last_att.get('status')}, Trigger: {last_att.get('trigger')}, Time: {last_att.get('timestamp')}")

        lock_info = status.get("active_workflow_lock", {})
        lock_status = f"LOCKED (PID {lock_info.get('pid')})" if lock_info.get("locked") else "UNLOCKED / IDLE"
        print(f"Workflow Lock (Active):  {lock_status}")

        recovery = status.get("missed_run_recovery", {})
        print(f"Missed-Run Recovery:     Needed: {recovery.get('recovery_needed_today')}, Window: {recovery.get('recovery_window_hours')}h, Today's Failures: {recovery.get('failures_recorded_today')}/{recovery.get('max_allowed_failures')}")

        win_task = status.get("windows_task_scheduler", {})
        print("-" * 72)
        print("Windows Task Scheduler (OS-Level):")
        print(f"  Configured:            {win_task.get('configured')}")
        print(f"  Task Name:             {win_task.get('task_name')}")
        print(f"  Task State:            {win_task.get('task_state')}")
        print(f"  Next Run Time:         {win_task.get('next_run_time')}")
        print(f"  Last Run Time:         {win_task.get('last_run_time')}")
        print(f"  Last Result Code:      {win_task.get('last_task_result')}")

        tz_compat = win_task.get("timezone_compatibility", {})
        print(f"  Timezone Alignment:    {tz_compat.get('status')} ({tz_compat.get('note', '')})")
        print("=" * 72)
        sys.exit(0)

    if args.scheduler_diagnose:
        import os
        from careerorbit.scheduler.runner import SCHEDULER
        from careerorbit.scheduler.timezone_helper import get_machine_timezone_info, validate_timezone_compatibility

        print("=" * 72)
        print("CAREERORBIT AI — SCHEDULER DIAGNOSTIC VERIFICATION")
        print("=" * 72)
        diag_failures = 0

        # Check 1: Python environment
        venv_py = SETTINGS.BASE_DIR / ".venv" / "Scripts" / "python.exe"
        if venv_py.exists():
            print(f"[PASS] Python executable exists: {venv_py}")
        else:
            print(f"[WARN] Virtualenv python not found at {venv_py}; current interpreter: {sys.executable}")

        # Check 2: Entry point
        run_file = SETTINGS.BASE_DIR / "run.py"
        if run_file.exists():
            print(f"[PASS] Launcher entry point exists: {run_file}")
        else:
            print(f"[FAIL] Entry point missing: {run_file}")
            diag_failures += 1

        # Check 3: Timezone compatibility
        tz_info = get_machine_timezone_info()
        tz_compat = validate_timezone_compatibility()
        print(f"[PASS] Machine timezone detected: {tz_info['timezone_name']} (UTC{tz_info['utc_offset_string']})")
        if tz_compat["is_compatible"]:
            print(f"[PASS] Timezone alignment: {tz_compat['status']} — executes at 08:00 AM IST")
        else:
            print(f"[FAIL] Timezone mismatch: {tz_compat['note']}")
            diag_failures += 1

        # Check 4: Cross-process concurrency lock
        with workflow_lock("test_diagnostic") as acquired:
            if acquired:
                print("[PASS] Cross-process kernel locking: functional (acquired and released cleanly)")
            else:
                print("[FAIL] Cross-process kernel locking: failed to acquire test lock")
                diag_failures += 1

        # Check 5: Windows Task Scheduler
        win_task = SCHEDULER.get_windows_task_status()
        if win_task.get("configured"):
            print(f"[PASS] Windows Task Scheduler: '{win_task.get('task_name')}' is registered ({win_task.get('task_state')})")
            print(f"       Next run: {win_task.get('next_run_time')} | Last result: {win_task.get('last_task_result')}")
        else:
            if os.name == "nt":
                print(f"[WARN] Windows task '{SETTINGS.WINDOWS_TASK_NAME}' is not registered. Run setup_windows_scheduler.ps1 to register.")
            else:
                print("[INFO] Non-Windows OS: Task Scheduler not applicable; in-process scheduler active.")

        # Check 6: Durable run history file
        runs_file = SETTINGS.LOGS_DIR / "workflow_runs.jsonl"
        if runs_file.exists():
            print(f"[PASS] Durable run history file exists: {runs_file}")
        else:
            print(f"[INFO] Run history file {runs_file} will be initialized on first workflow run.")

        print("=" * 72)
        if diag_failures == 0:
            print("[SUCCESS] All scheduler diagnostic checks passed!")
            sys.exit(0)
        else:
            print(f"[ERROR] {diag_failures} diagnostic check(s) failed.")
            sys.exit(1)

    if args.install_windows_tasks:
        ps1_file = SETTINGS.BASE_DIR / "setup_windows_scheduler.ps1"
        generate_windows_task_script(ps1_file)
        print(f"[+] Windows Task Scheduler registration script generated at: {ps1_file}")
        print("[!] Inspect the generated script, then run it in PowerShell as the current user:")
        print(f"    & '{ps1_file}'")
        print("[!] Task Scheduler uses the computer's local timezone; confirm it is India Standard Time.")
        sys.exit(0)

    if args.daily_report:
        from careerorbit.database.db import get_job_stats, list_jobs
        import json
        from datetime import datetime, timezone, timedelta
        
        # Determine Asia/Kolkata local time (UTC+05:30)
        ist_now = datetime.now(timezone(timedelta(hours=5, minutes=30)))
        stats = get_job_stats()
        jobs = list_jobs(sort_by="priority_first", limit=100)
        
        # Read last discovery run metadata
        last_run = None
        runs_file = SETTINGS.LOGS_DIR / "workflow_runs.jsonl"
        if runs_file.exists():
            for line in runs_file.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    try:
                        record = json.loads(line)
                        if record.get("workflow") == "job_discovery":
                            last_run = record
                    except Exception:
                        pass

        print("=" * 72)
        print("   CAREERORBIT AI — DAILY JOB-SEARCH INTELLIGENCE REPORT")
        print("=" * 72)
        print("Candidate profile: locally configured private data")
        print(f"Report Generated: {ist_now.strftime('%A, %B %d, %Y at %I:%M:%S %p')} IST")
        
        print("\n--- 1. SEARCH METADATA ---")
        if last_run:
            print(f"Last Discovery Run: {last_run.get('timestamp')} UTC")
            print(f"Workflow Status: {last_run.get('status')}")
            summary = last_run.get("summary") or {}
            print(f"Time Window: Last {summary.get('time_window_days', 7)} days")
            sources = summary.get("sources") or {}
            for src_name, src_info in sources.items():
                status = src_info.get("status", "unknown")
                raw = src_info.get("raw_count", 0)
                accepted = src_info.get("count", 0)
                print(f"  • {src_name}: status={status}, raw_fetched={raw}, accepted={accepted}")
        else:
            print("No recorded discovery run found in workflow_runs.jsonl.")

        print("\n--- 2. OPPORTUNITY SUMMARY & METRICS ---")
        print(f"Total Active Discovery Leads: {stats.get('total_jobs')}")
        print(f"Verified Open Vacancies:     {stats.get('verified_open')}")
        print(f"Unverified Discovery Leads:  {stats.get('unverified_jobs')}")
        print(f"Quarantined Legacy Records:  {stats.get('quarantined_jobs')} (isolated from active results)")
        print(f"Saved / Bookmarked Jobs:     {stats.get('saved_jobs')}")
        print(f"Fresh in Last 24 Hours:      {stats.get('jobs_last_24h')}")
        print(f"Fresh in Last 7 Days:        {stats.get('jobs_last_7d')}")

        print("\n--- 3. INDIA-FIRST GEOGRAPHIC DISTRIBUTION ---")
        print(f"Priority 1 (South India & India Remote): {stats.get('geo_p1_jobs')} leads (Bengaluru, Chennai, Coimbatore, Hyderabad, etc.)")
        print(f"Priority 2 (Other Indian Tech Hubs):     {stats.get('geo_p2_jobs')} leads (Pune, Mumbai, Delhi NCR, Noida, etc.)")
        print(f"Priority 3 (International / Unconfirmed): {stats.get('geo_p3_jobs')} leads (Ranked below India-eligible)")

        print("\n--- 4. CAREER PRIORITY DISTRIBUTION ---")
        tier_names = {
            1: "Data Analyst / BI / Power BI",
            2: "Data Scientist / Junior Data Scientist",
            3: "Software Engineer / Associate Software Engineer",
            4: "AI Engineer / Machine Learning",
            5: "Data Engineer / ETL / Analytics Engineer",
            6: "Other Early Career Technical Roles"
        }
        tier_counts = {i: 0 for i in range(1, 7)}
        for j in jobs:
            cat = j.get("priority_category", 6)
            tier_counts[cat] = tier_counts.get(cat, 0) + 1
        for tier in range(1, 7):
            print(f"  Priority {tier} [{tier_names[tier]}]: {tier_counts[tier]} active leads")

        print("\n--- 5. TOP DISCOVERY LEADS (Priority & Geo Ranked) ---")
        eligible_leads = [
            j for j in jobs
            if j.get("match_tier") != "Ineligible"
            and j.get("verification_status") != "VERIFIED_CLOSED"
            and j.get("priority_category", 0) > 0
        ]
        top_leads = eligible_leads[:10]
        for idx, j in enumerate(top_leads, 1):
            geo_tier = f"Geo P{j.get('geographic_priority', 1)}"
            pref_rank = j.get("preference_rank")
            rank_str = f"Preference #{pref_rank}" if pref_rank else f"Tier {j.get('priority_category', 1)}"
            score = f"{j.get('match_score')}/100" if j.get('match_score') is not None else "Needs review"
            print(f"  {idx}. [{rank_str} | {geo_tier}] {j.get('title')} @ {j.get('employer')}")
            print(f"     Location: {j.get('location')} ({j.get('work_arrangement')}) | ATS Score: {score}")
            print(f"     Status: {j.get('verification_status')} | Official URL: {j.get('official_listing_url') or j.get('application_url') or j.get('discovery_url')}")

        print("\n--- 6. APPLICATION TRACKER & HUMAN APPROVAL ---")
        print(f"Applications Awaiting Candidate Approval: {stats.get('applications_awaiting_approval')}")
        print(f"Confirmed Submissions (Explicit):         {stats.get('confirmed_submissions')}")
        print(f"Applications Requiring Review:            {stats.get('applications_needing_review')}")
        print("\n--- 7. RECOMMENDED NEXT ACTIONS ---")
        print("  1. Review Priority 1 (South India & India Remote) discovery leads in dashboard.")
        print("  2. Generate tailored PDF/DOCX resume for target applications.")
        print("  3. Access on-demand interview prep or study planner for target roles as needed.")
        print("=" * 72)
        sys.exit(0)

    # Default action: launch dashboard server with background scheduler
    print(f"[*] Starting CareerOrbit AI Dashboard at http://{args.host}:{args.port}")
    print("[*] Background scheduler starts after a local account is registered (Job discovery: 08:00 AM IST | Study plan: On-Demand Only)")
    uvicorn.run("careerorbit.web.app:app", host=args.host, port=args.port, reload=False)

if __name__ == "__main__":
    main()
