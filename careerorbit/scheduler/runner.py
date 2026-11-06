"""Background scheduler and workflow runner with Asia/Kolkata timezone awareness and missed-run recovery."""
import logging
import os
import re
import subprocess
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, Callable

from careerorbit.config.settings import SETTINGS, current_logs_dir
from careerorbit.discovery.engine import JobDiscoveryEngine
from careerorbit.prep.study_planner import DailyStudyPlanner
from careerorbit.scheduler.run_history import (
    record_run,
    last_success,
    latest_success,
    latest_attempt,
    count_failures_today,
    workflow_lock,
    is_workflow_locked,
    get_workflow_lock_info,
)
from careerorbit.scheduler.timezone_helper import (
    IST,
    TARGET_IST_HOUR,
    TARGET_IST_MINUTE,
    get_machine_timezone_info,
    compute_local_trigger_time,
    validate_timezone_compatibility,
)

logger = logging.getLogger("careerorbit.scheduler")
if not logger.handlers:
    try:
        log_file = current_logs_dir() / "scheduler.log"
        file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
        file_handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s"))
        logger.addHandler(file_handler)
        logger.setLevel(logging.INFO)
    except Exception:
        pass

CANONICAL_TASK_NAME = SETTINGS.WINDOWS_TASK_NAME
LEGACY_TASK_NAME = "CareerOrbitJobDiscovery"


class RecoveryResult(dict):
    """Result dictionary from check_and_recover_missed_run that boolean-evaluates to whether recovery ran."""
    def __bool__(self) -> bool:
        return bool(self.get("recovered", False))


class BackgroundScheduler:
    """Runs scheduled workflows at 08:00 AM Asia/Kolkata with automatic missed-run recovery."""

    def __init__(self, clock: Optional[Callable[[], datetime]] = None):
        self._clock = clock
        self.running = False
        self._thread: Optional[threading.Thread] = None
        self._discovery_lock = threading.Lock()
        self._study_lock = threading.Lock()
        self.last_discovery_run_date: Optional[str] = None
        self.last_study_plan_run_date: Optional[str] = None
        self.discovery_engine = JobDiscoveryEngine()
        self.study_planner = DailyStudyPlanner()
        self.last_discovery_result: Optional[Dict[str, Any]] = None
        self.last_study_plan_result: Optional[Dict[str, Any]] = None
        self.last_recovery_result: Dict[str, Any] = {}
        self.consecutive_failures = 0
        self.max_failures = 5

    def get_ist_now(self) -> datetime:
        """Return the current datetime in Asia/Kolkata timezone (injectable clock supported)."""
        if self._clock is not None:
            return self._clock()
        return datetime.now(IST)

    def trigger_discovery_now(self, trigger_type: str = "manual") -> Dict[str, Any]:
        """Manually or automatically triggers job discovery with cross-process concurrency protection."""
        if not self._discovery_lock.acquire(blocking=False):
            logger.warning("Job discovery trigger requested while a discovery run is already active in memory.")
            return {"status": "busy", "message": "Discovery workflow is currently executing. Please wait."}

        now = self.get_ist_now()
        logger.info(f"Triggering Job Discovery (trigger={trigger_type}) at {now.isoformat()} IST")
        try:
            with workflow_lock("job_discovery") as acquired:
                if not acquired:
                    record_run("job_discovery", "skipped_overlap", trigger=trigger_type)
                    return {"status": "busy", "message": "Discovery workflow is already running in another process."}

                res = self.discovery_engine.run_discovery(initial_days=1, min_acceptable=5)
                self.last_discovery_run_date = now.strftime("%Y-%m-%d")
                self.last_discovery_result = res
                self.consecutive_failures = 0
                summary = {
                    k: res.get(k)
                    for k in ("total_collected", "new_jobs_added", "jobs_updated", "time_window_days", "sources")
                }
                record_run("job_discovery", "success", summary=summary, trigger=trigger_type)
                return res
        except Exception as e:
            self.consecutive_failures += 1
            logger.error("Discovery run failed (%s): %s", type(e).__name__, e)
            record_run("job_discovery", "failed", error=type(e).__name__, trigger=trigger_type)
            return {"error": type(e).__name__, "timestamp": now.isoformat()}
        finally:
            self._discovery_lock.release()

    def trigger_study_plan_now(self, trigger_type: str = "manual") -> Dict[str, Any]:
        """Manually triggers daily study plan generation with concurrency protection."""
        if not self._study_lock.acquire(blocking=False):
            logger.warning("Study plan generation requested while a study run is already in progress.")
            return {"status": "busy", "message": "Study plan generation is currently executing. Please wait."}

        now = self.get_ist_now()
        logger.info(f"Triggering Daily Study Plan at {now.isoformat()} IST")
        try:
            with workflow_lock("study_plan") as acquired:
                if not acquired:
                    record_run("study_plan", "skipped_overlap", trigger=trigger_type)
                    return {"status": "busy", "message": "Study plan workflow is already running in another process."}

                res = self.study_planner.generate_daily_plan()
                self.last_study_plan_run_date = now.strftime("%Y-%m-%d")
                self.last_study_plan_result = res
                record_run(
                    "study_plan", "success",
                    summary={"date": res.get("date"), "target_session_time": res.get("target_session_time")},
                    trigger=trigger_type
                )
                return res
        except Exception as e:
            logger.error("Study plan generation failed (%s)", type(e).__name__)
            record_run("study_plan", "failed", error=type(e).__name__, trigger=trigger_type)
            return {"error": type(e).__name__, "timestamp": now.isoformat()}
        finally:
            self._study_lock.release()

    def check_and_recover_missed_run(self, return_details: bool = False) -> Any:
        """Evaluates whether today's 08:00 AM IST discovery run was missed and executes recovery.

        Guarantees:
        - If current IST time is before 08:00 AM IST, no recovery is performed.
        - If current IST time exceeds the configured recovery window, recovery is expired.
        - If discovery already succeeded today in memory or durable history, skips idempotently.
        - If an active discovery is currently running, skips without launching duplicate work.
        - Limits consecutive daily recovery failures to prevent runaway execution.
        """
        now_ist = self.get_ist_now()
        today_str = now_ist.strftime("%Y-%m-%d")

        # 1. Scheduled 08:00 AM has not arrived yet today
        if now_ist.hour < TARGET_IST_HOUR:
            outcome = {
                "recovered": False,
                "reason": "BEFORE_SCHEDULED_TIME",
                "message": f"Current IST time ({now_ist.strftime('%H:%M')}) is before scheduled 08:00 AM IST.",
            }
            self.last_recovery_result = outcome
            return outcome if return_details else False

        # 2. Check recovery window (e.g., 16 hours after 08:00 AM, up to midnight)
        hours_since_scheduled = now_ist.hour - TARGET_IST_HOUR
        if hours_since_scheduled >= SETTINGS.SCHEDULER_RECOVERY_WINDOW_HOURS:
            logger.info("Missed run recovery window expired (%s hours elapsed today).", hours_since_scheduled)
            outcome = {
                "recovered": False,
                "reason": "RECOVERY_WINDOW_EXPIRED",
                "message": f"Recovery window of {SETTINGS.SCHEDULER_RECOVERY_WINDOW_HOURS}h expired for {today_str}.",
            }
            self.last_recovery_result = outcome
            return outcome if return_details else False

        # 3. Already run in this in-memory session today
        if self.last_discovery_run_date == today_str:
            outcome = {
                "recovered": False,
                "reason": "ALREADY_EXECUTED_TODAY",
                "message": f"Discovery already executed in-memory today ({today_str}).",
            }
            self.last_recovery_result = outcome
            return outcome if return_details else False

        # 4. Check durable run history to see if discovery already completed successfully today
        rec = latest_success("job_discovery")
        if rec and rec.get("timestamp"):
            try:
                dt_utc = datetime.fromisoformat(rec["timestamp"].replace("Z", "+00:00"))
                dt_ist = dt_utc.astimezone(IST)
                if dt_ist.strftime("%Y-%m-%d") == today_str:
                    self.last_discovery_run_date = today_str
                    logger.info("Today's job discovery executed successfully at %s IST; skipping recovery.", dt_ist.strftime("%H:%M:%S"))
                    outcome = {
                        "recovered": False,
                        "reason": "ALREADY_EXECUTED_TODAY",
                        "message": f"Discovery already succeeded at {dt_ist.strftime('%H:%M:%S IST')} today.",
                    }
                    self.last_recovery_result = outcome
                    return outcome if return_details else False
            except Exception:
                pass

        # 5. Check if another discovery process is actively holding the workflow lock
        if is_workflow_locked("job_discovery"):
            logger.info("Discovery workflow is actively running in another process; skipping recovery trigger.")
            outcome = {
                "recovered": False,
                "reason": "CONCURRENT_RUN_ACTIVE",
                "message": "Another discovery process is currently active.",
            }
            self.last_recovery_result = outcome
            return outcome if return_details else False

        # 6. Limit daily recovery failures to prevent infinite looping
        failures_today = count_failures_today("job_discovery", today_str)
        if failures_today >= SETTINGS.MAX_RECOVERY_ATTEMPTS_PER_DAY:
            logger.warning(
                "Maximum daily recovery attempts (%s) reached for %s; aborting automated recovery.",
                failures_today, today_str
            )
            outcome = {
                "recovered": False,
                "reason": "MAX_RECOVERY_ATTEMPTS_REACHED",
                "message": f"Reached max daily failure threshold ({failures_today}/{SETTINGS.MAX_RECOVERY_ATTEMPTS_PER_DAY}).",
            }
            self.last_recovery_result = outcome
            return outcome if return_details else False

        # 7. Execute recovery run
        logger.info(
            "Missed 08:00 AM IST scheduled job discovery detected for %s (current time: %s IST). Triggering automatic recovery run.",
            today_str,
            now_ist.strftime("%H:%M:%S")
        )
        res = self.trigger_discovery_now(trigger_type="recovered")
        outcome = {
            "recovered": True,
            "reason": "RECOVERY_EXECUTED",
            "message": f"Automatic recovery run completed at {now_ist.strftime('%H:%M:%S IST')}.",
            "result": res,
        }
        self.last_recovery_result = outcome
        return outcome if return_details else True

    def get_windows_task_status(self) -> Dict[str, Any]:
        """Inspects if an OS-level Windows Task Scheduler task is configured, enabled, and healthy."""
        if os.name != "nt":
            return {
                "configured": False,
                "mode": "NON_WINDOWS_OS",
                "task_name": None,
                "notes": "Non-Windows operating system; in-process scheduler daemon active."
            }

        target_task = CANONICAL_TASK_NAME
        try:
            # Query canonical task name first
            res = subprocess.run(
                ["schtasks", "/query", "/tn", target_task, "/fo", "LIST", "/v"],
                capture_output=True, text=True, timeout=5
            )

            # Fallback to legacy task name if canonical is not yet registered
            if res.returncode != 0:
                res_legacy = subprocess.run(
                    ["schtasks", "/query", "/tn", LEGACY_TASK_NAME, "/fo", "LIST", "/v"],
                    capture_output=True, text=True, timeout=5
                )
                if res_legacy.returncode == 0:
                    res = res_legacy
                    target_task = LEGACY_TASK_NAME

            if res.returncode == 0:
                lines = res.stdout.splitlines()
                info = {}
                for line in lines:
                    if ":" in line:
                        parts = line.split(":", 1)
                        info[parts[0].strip()] = parts[1].strip()

                status = info.get("Status", "Unknown")
                next_run = info.get("Next Run Time", "N/A")
                last_run = info.get("Last Run Time", "N/A")
                last_result = info.get("Last Result", "N/A")

                # Parse timezone compatibility
                tz_calc = compute_local_trigger_time()
                tz_status = validate_timezone_compatibility()

                return {
                    "configured": True,
                    "mode": "WINDOWS_TASK_SCHEDULER",
                    "task_name": target_task,
                    "canonical_name": CANONICAL_TASK_NAME,
                    "is_canonical": (target_task == CANONICAL_TASK_NAME),
                    "task_state": status,
                    "enabled": (status != "Disabled"),
                    "next_run_time": next_run,
                    "last_run_time": last_run,
                    "last_task_result": last_result,
                    "timezone_compatibility": tz_status,
                    "details": res.stdout[:300].strip(),
                }
        except Exception as exc:
            logger.debug("schtasks inspection error: %s", exc)

        return {
            "configured": False,
            "mode": "STANDALONE_DAEMON_PROCESS",
            "task_name": None,
            "canonical_name": CANONICAL_TASK_NAME,
            "notes": "Scheduler operates via in-process background thread and FastAPI lifespan."
        }

    def _loop(self):
        logger.info(f"CareerOrbit Background Scheduler started. Target: 08:00 AM {SETTINGS.TIMEZONE}")
        if SETTINGS.TESTING:
            # During hermetic test runs, do not trigger background discovery loops
            while self.running:
                time.sleep(0.05)
            return

        # Run startup catch-up recovery check if started after 08:00 AM IST
        try:
            self.check_and_recover_missed_run()
        except Exception as e:
            logger.error("Startup missed-run recovery check failed (%s): %s", type(e).__name__, e)

        while self.running:
            try:
                now_ist = self.get_ist_now()
                today_str = now_ist.strftime("%Y-%m-%d")
                curr_hour = now_ist.hour
                curr_minute = now_ist.minute

                # 8:00 AM IST Job Discovery
                if curr_hour == TARGET_IST_HOUR and curr_minute == TARGET_IST_MINUTE and self.last_discovery_run_date != today_str:
                    logger.info("Executing 8:00 AM IST scheduled job search...")
                    self.trigger_discovery_now(trigger_type="scheduled")
                elif curr_hour >= TARGET_IST_HOUR and self.last_discovery_run_date != today_str:
                    self.check_and_recover_missed_run()

            except Exception as e:
                logger.error("Scheduler loop error (%s): %s", type(e).__name__, e)

            # Sleep up to 30 seconds before next polling iteration in short responsive slices
            for _ in range(150):
                if not self.running:
                    break
                time.sleep(0.2)

    def start(self):
        if not self.running or (self._thread is not None and not self._thread.is_alive()):
            self.running = True
            self._thread = threading.Thread(target=self._loop, daemon=True, name="CareerOrbitScheduler")
            self._thread.start()
            logger.info("Background scheduler thread started.")
        else:
            logger.debug("Background scheduler already running.")

    def stop(self):
        self.running = False
        if self._thread:
            self._thread.join(timeout=2)
            logger.info("Background scheduler thread stopped.")

    def get_status(self) -> Dict[str, Any]:
        """Produce comprehensive, honest diagnostic status of in-process and OS scheduling."""
        now_ist = self.get_ist_now()
        recorded_discovery = latest_success("job_discovery") or {}
        last_att = latest_attempt("job_discovery") or {}
        lock_info = get_workflow_lock_info("job_discovery")
        today_str = now_ist.strftime("%Y-%m-%d")

        # Determine recovery needed state
        recovery_needed = (
            now_ist.hour >= TARGET_IST_HOUR
            and (now_ist.hour - TARGET_IST_HOUR) < SETTINGS.SCHEDULER_RECOVERY_WINDOW_HOURS
            and self.last_discovery_run_date != today_str
            and (not recorded_discovery.get("timestamp") or not recorded_discovery["timestamp"].startswith(today_str))
        )

        return {
            "scheduler_running": self.running,
            "canonical_task_name": CANONICAL_TASK_NAME,
            "current_ist_time": now_ist.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "target_discovery_time": f"{TARGET_IST_HOUR:02d}:{TARGET_IST_MINUTE:02d} AM {SETTINGS.TIMEZONE}",
            "target_study_time": f"08:00 PM {SETTINGS.TIMEZONE} (Disabled / On-Demand Only)",
            "last_successful_discovery": last_success("job_discovery") or self.last_discovery_run_date or "None yet",
            "last_attempt": {
                "status": last_att.get("status", "none"),
                "trigger": last_att.get("trigger", "none"),
                "timestamp": last_att.get("timestamp"),
                "error": last_att.get("error"),
            },
            "active_workflow_lock": lock_info,
            "missed_run_recovery": {
                "recovery_needed_today": recovery_needed,
                "recovery_window_hours": SETTINGS.SCHEDULER_RECOVERY_WINDOW_HOURS,
                "failures_recorded_today": count_failures_today("job_discovery", today_str),
                "max_allowed_failures": SETTINGS.MAX_RECOVERY_ATTEMPTS_PER_DAY,
            },
            "consecutive_failures": self.consecutive_failures,
            "latest_discovery_summary": self.last_discovery_result or recorded_discovery.get("summary") or "No automated run recorded yet",
            "timezone_info": get_machine_timezone_info(),
            "windows_task_scheduler": self.get_windows_task_status(),
        }


SCHEDULER = BackgroundScheduler()
