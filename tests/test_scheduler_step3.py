"""Comprehensive Automated Test Suite for Step 3:
Windows Task Scheduler, Timezone Correctness, Reliability, and Missed-Run Recovery.

Verifies:
1. Canonical task name consistency (CareerOrbit_Daily_Job_Search).
2. Timezone interpretation, trigger computation, and compatibility across IST, UTC, EST, and PST.
3. Cross-process concurrency locking, metadata recording, and contention handling.
4. Missed-run recovery scenarios:
   - Before 08:00 AM IST (no recovery).
   - After 08:00 AM IST without prior run (recovery executes).
   - Repeated calls on same day (idempotent, no repeated runs).
   - Durable history already has success today (skips).
   - Active concurrent execution (skips overlap).
   - Expired recovery window (skips after window).
   - Failure throttling (stops retrying after max daily attempts).
5. Observability and honest status reporting.
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from careerorbit.config.settings import SETTINGS
from careerorbit.scheduler.runner import (
    BackgroundScheduler,
    CANONICAL_TASK_NAME,
    LEGACY_TASK_NAME,
    RecoveryResult,
)
from careerorbit.scheduler.timezone_helper import (
    IST,
    TARGET_IST_HOUR,
    TARGET_IST_MINUTE,
    get_machine_timezone_info,
    compute_local_trigger_time,
    validate_timezone_compatibility,
)
from careerorbit.scheduler.run_history import (
    workflow_lock,
    is_workflow_locked,
    get_workflow_lock_info,
    record_run,
    latest_success,
    latest_attempt,
    count_failures_today,
)
from careerorbit.scheduler.windows_task import generate_windows_task_script


# ==============================================================================
# 1. Canonical Task Name & Registration Consistency Tests
# ==============================================================================

class TestCanonicalTaskName:
    def test_canonical_task_name_centralized(self):
        """Verifies canonical task name is centrally defined in settings and runner."""
        assert CANONICAL_TASK_NAME == "CareerOrbit_Daily_Job_Search"
        assert SETTINGS.WINDOWS_TASK_NAME == "CareerOrbit_Daily_Job_Search"

    def test_generated_script_uses_canonical_name(self, tmp_path):
        """Verifies generate_windows_task_script generates script with canonical task name."""
        out_script = tmp_path / "test_scheduler.ps1"
        generate_windows_task_script(out_script)
        content = out_script.read_text(encoding="utf-8")

        assert "CareerOrbit_Daily_Job_Search" in content
        assert "CareerOrbitJobDiscovery" in content  # To clean up legacy task
        assert "08:00 AM" in content
        assert "--job-discovery" in content

    def test_setup_ps1_contains_canonical_name(self):
        """Verifies root setup_windows_scheduler.ps1 uses canonical name."""
        setup_script = Path("setup_windows_scheduler.ps1")
        assert setup_script.exists()
        content = setup_script.read_text(encoding="utf-8")
        assert "CareerOrbit_Daily_Job_Search" in content
        assert "DryRun" in content
        assert "Force" in content

    def test_windows_task_status_queries_canonical_name(self):
        """Verifies get_windows_task_status queries canonical name and includes canonical flag."""
        sched = BackgroundScheduler()
        status = sched.get_windows_task_status()
        assert "canonical_name" in status
        assert status["canonical_name"] == "CareerOrbit_Daily_Job_Search"


# ==============================================================================
# 2. Timezone Correctness & Trigger Calculation Tests
# ==============================================================================

class TestTimezoneCorrectness:
    def test_ist_timezone_offset_exact(self):
        """Verifies that IST timezone is strictly UTC+05:30 with no daylight saving shifts."""
        now = datetime.now(IST)
        assert now.utcoffset() == timedelta(hours=5, minutes=30)
        assert str(now.tzinfo) == "Asia/Kolkata"

    def test_native_ist_trigger_computation(self):
        """On an India Standard Time machine (+05:30), 08:00 IST maps directly to 08:00 AM local."""
        # 19800 seconds = 5.5 hours
        calc = compute_local_trigger_time(target_ist_hour=8, target_ist_minute=0, system_offset_seconds=19800)
        assert calc["local_trigger_time_12h"] == "08:00 AM"
        assert calc["local_trigger_time_24h"] == "08:00"
        assert calc["is_native_ist"] is True
        assert "India Standard Time" in calc["diagnostic_message"]

    def test_utc_machine_trigger_computation(self):
        """On a UTC machine (+00:00), 08:00 IST (UTC 02:30) maps to 02:30 AM local."""
        calc = compute_local_trigger_time(target_ist_hour=8, target_ist_minute=0, system_offset_seconds=0)
        assert calc["local_trigger_time_12h"] == "02:30 AM"
        assert calc["local_trigger_time_24h"] == "02:30"
        assert calc["is_native_ist"] is False
        assert "02:30 AM" in calc["diagnostic_message"]

    def test_us_eastern_trigger_computation(self):
        """On US Eastern (UTC-05:00), 08:00 IST (UTC 02:30) maps to 21:30 (09:30 PM previous day)."""
        est_offset_sec = -5 * 3600
        calc = compute_local_trigger_time(target_ist_hour=8, target_ist_minute=0, system_offset_seconds=est_offset_sec)
        assert calc["local_trigger_time_12h"] == "09:30 PM"
        assert calc["local_trigger_time_24h"] == "21:30"
        assert calc["is_native_ist"] is False

    def test_us_pacific_trigger_computation(self):
        """On US Pacific (UTC-08:00), 08:00 IST (UTC 02:30) maps to 18:30 (06:30 PM previous day)."""
        pst_offset_sec = -8 * 3600
        calc = compute_local_trigger_time(target_ist_hour=8, target_ist_minute=0, system_offset_seconds=pst_offset_sec)
        assert calc["local_trigger_time_12h"] == "06:30 PM"
        assert calc["local_trigger_time_24h"] == "18:30"

    def test_timezone_validation_matching(self):
        """validate_timezone_compatibility passes when trigger matches expected IST equivalent."""
        res_ist = validate_timezone_compatibility("08:00 AM", custom_offset_seconds=19800)
        assert res_ist["is_compatible"] is True
        assert res_ist["status"] == "NATIVE_IST"

        res_utc = validate_timezone_compatibility("02:30 AM", custom_offset_seconds=0)
        assert res_utc["is_compatible"] is True
        assert res_utc["status"] == "OFFSET_ADJUSTED"

    def test_timezone_validation_mismatch(self):
        """validate_timezone_compatibility flags mismatch when trigger does not match expected IST equivalent."""
        # On UTC machine, setting 08:00 AM would be 13:30 IST (5.5h late)
        res_mismatch = validate_timezone_compatibility("08:00 AM", custom_offset_seconds=0)
        assert res_mismatch["is_compatible"] is False
        assert res_mismatch["status"] == "TIMEZONE_MISMATCH"
        assert "02:30 AM" in res_mismatch["note"]


# ==============================================================================
# 3. Cross-Process Concurrency & Lock Handling Tests
# ==============================================================================

class TestConcurrencyAndLocking:
    def test_workflow_lock_acquisition_and_release(self, tmp_path):
        """Verifies lock can be acquired, reports is_workflow_locked=True while held, and releases."""
        with patch.object(SETTINGS, "LOGS_DIR", tmp_path):
            assert is_workflow_locked("test_flow") is False
            with workflow_lock("test_flow") as acquired:
                assert acquired is True
                assert is_workflow_locked("test_flow") is True
                info = get_workflow_lock_info("test_flow")
                assert info["locked"] is True
                assert info["pid"] == os.getpid()

            assert is_workflow_locked("test_flow") is False

    def test_thread_contention_blocked(self, tmp_path):
        """Verifies two blocks in the same process cannot concurrently hold the same workflow lock."""
        with patch.object(SETTINGS, "LOGS_DIR", tmp_path):
            with workflow_lock("test_flow") as acquired1:
                assert acquired1 is True
                with workflow_lock("test_flow") as acquired2:
                    assert acquired2 is False

    def test_stale_lock_safe_recovery(self, tmp_path):
        """Verifies that an abandoned lock file with dead PID does not prevent new lock acquisition."""
        with patch.object(SETTINGS, "LOGS_DIR", tmp_path):
            lock_file = tmp_path / "test_flow.lock"
            meta_file = tmp_path / "test_flow.lock.json"
            # Write a dead lock file with dead PID
            lock_file.write_text("0\n", encoding="utf-8")
            meta_file.write_text(json.dumps({"pid": 999999, "acquired_at": "2020-01-01T00:00:00Z"}), encoding="utf-8")

            # Acquiring should succeed because no live process holds the kernel byte-range lock
            with workflow_lock("test_flow") as acquired:
                assert acquired is True
                info = get_workflow_lock_info("test_flow")
                assert info["pid"] == os.getpid()

    def test_record_run_stores_trigger_type(self, tmp_path):
        """Verifies record_run correctly records trigger type ('scheduled', 'recovered', 'manual')."""
        with patch.object(SETTINGS, "LOGS_DIR", tmp_path):
            rec = record_run("job_discovery", "success", summary={"jobs": 5}, trigger="recovered")
            assert rec["trigger"] == "recovered"
            assert rec["status"] == "success"

            att = latest_attempt("job_discovery")
            assert att is not None
            assert att["trigger"] == "recovered"


# ==============================================================================
# 4. Missed-Run Recovery Logic Tests (Deterministic Injectable Clock)
# ==============================================================================

class TestMissedRunRecovery:
    @pytest.fixture
    def mock_scheduler(self):
        sched = BackgroundScheduler()
        sched.discovery_engine = MagicMock()
        sched.discovery_engine.run_discovery.return_value = {
            "status": "success",
            "total_collected": 10,
            "new_jobs_added": 3,
            "jobs_updated": 2,
        }
        return sched

    def test_recovery_not_triggered_before_8am(self, mock_scheduler):
        """At 07:45 AM IST, the 08:00 AM scheduled run has not passed yet."""
        clock = lambda: datetime(2026, 4, 15, 7, 45, tzinfo=IST)
        mock_scheduler._clock = clock

        # Test boolean return
        assert mock_scheduler.check_and_recover_missed_run() is False
        # Test detailed return
        res = mock_scheduler.check_and_recover_missed_run(return_details=True)
        assert res["recovered"] is False
        assert res["reason"] == "BEFORE_SCHEDULED_TIME"
        mock_scheduler.discovery_engine.run_discovery.assert_not_called()

    def test_recovery_triggered_after_8am_when_missed(self, mock_scheduler, tmp_path):
        """At 09:15 AM IST on boot without prior run today, recovery triggers."""
        clock = lambda: datetime(2026, 4, 15, 9, 15, tzinfo=IST)
        mock_scheduler._clock = clock

        with patch.object(SETTINGS, "LOGS_DIR", tmp_path):
            res = mock_scheduler.check_and_recover_missed_run(return_details=True)
            assert res["recovered"] is True
            assert res["reason"] == "RECOVERY_EXECUTED"
            mock_scheduler.discovery_engine.run_discovery.assert_called_once()
            assert mock_scheduler.last_discovery_run_date == "2026-04-15"

    def test_recovery_idempotent_no_duplicate_on_same_day(self, mock_scheduler, tmp_path):
        """Calling check_and_recover_missed_run multiple times on the same day skips after first run."""
        clock = lambda: datetime(2026, 4, 15, 10, 0, tzinfo=IST)
        mock_scheduler._clock = clock

        with patch.object(SETTINGS, "LOGS_DIR", tmp_path):
            # First call triggers recovery
            res1 = mock_scheduler.check_and_recover_missed_run(return_details=True)
            assert res1["recovered"] is True
            assert res1["reason"] == "RECOVERY_EXECUTED"

            # Second call immediately skips
            res2 = mock_scheduler.check_and_recover_missed_run(return_details=True)
            assert res2["recovered"] is False
            assert res2["reason"] == "ALREADY_EXECUTED_TODAY"
            assert mock_scheduler.discovery_engine.run_discovery.call_count == 1

    def test_recovery_skips_if_durable_history_shows_success_today(self, mock_scheduler, tmp_path):
        """If another process ran discovery successfully at 08:00 AM IST today, in-process recovery skips."""
        clock = lambda: datetime(2026, 4, 15, 11, 30, tzinfo=IST)
        mock_scheduler._clock = clock

        with patch.object(SETTINGS, "LOGS_DIR", tmp_path):
            # Simulate earlier run at 08:01 AM IST (02:31 UTC)
            record_run(
                "job_discovery", "success", summary={"jobs": 5},
                trigger="scheduled"
            )
            # Patch datetime in record to be today 08:01 IST
            today_utc_dt = datetime(2026, 4, 15, 2, 31, tzinfo=timezone.utc)
            runs_file = tmp_path / "workflow_runs.jsonl"
            runs_file.write_text(json.dumps({
                "workflow": "job_discovery",
                "status": "success",
                "trigger": "scheduled",
                "timestamp": today_utc_dt.isoformat(),
            }) + "\n", encoding="utf-8")

            res = mock_scheduler.check_and_recover_missed_run(return_details=True)
            assert res["recovered"] is False
            assert res["reason"] == "ALREADY_EXECUTED_TODAY"
            mock_scheduler.discovery_engine.run_discovery.assert_not_called()

    def test_recovery_skips_if_concurrent_run_active(self, mock_scheduler, tmp_path):
        """If another discovery process holds the workflow lock, recovery skips overlap."""
        clock = lambda: datetime(2026, 4, 15, 9, 30, tzinfo=IST)
        mock_scheduler._clock = clock

        with patch.object(SETTINGS, "LOGS_DIR", tmp_path):
            with workflow_lock("job_discovery") as acquired:
                assert acquired is True
                res = mock_scheduler.check_and_recover_missed_run(return_details=True)
                assert res["recovered"] is False
                assert res["reason"] == "CONCURRENT_RUN_ACTIVE"

    def test_recovery_expires_after_configured_window(self, mock_scheduler):
        """If elapsed hours exceeds SCHEDULER_RECOVERY_WINDOW_HOURS, recovery is expired."""
        # 08:00 AM + 17 hours = 01:00 AM next day or late night
        late_night = datetime(2026, 4, 15, 23, 30, tzinfo=IST)
        mock_scheduler._clock = lambda: late_night

        with patch.object(SETTINGS, "SCHEDULER_RECOVERY_WINDOW_HOURS", 12):
            res = mock_scheduler.check_and_recover_missed_run(return_details=True)
            assert res["recovered"] is False
            assert res["reason"] == "RECOVERY_WINDOW_EXPIRED"

    def test_recovery_throttled_after_max_failures(self, mock_scheduler, tmp_path):
        """If today has already reached MAX_RECOVERY_ATTEMPTS_PER_DAY failures, stops retrying."""
        clock = lambda: datetime(2026, 4, 15, 10, 0, tzinfo=IST)
        mock_scheduler._clock = clock

        with patch.object(SETTINGS, "LOGS_DIR", tmp_path):
            # Write 3 failures for today (2026-04-15 03:30 UTC = 09:00 AM IST)
            for _ in range(3):
                record_run(
                    "job_discovery", "failed", error="ConnectionError",
                    timestamp="2026-04-15T03:30:00Z"
                )

            with patch.object(SETTINGS, "MAX_RECOVERY_ATTEMPTS_PER_DAY", 3):
                res = mock_scheduler.check_and_recover_missed_run(return_details=True)
                assert res["recovered"] is False
                assert res["reason"] == "MAX_RECOVERY_ATTEMPTS_REACHED"


# ==============================================================================
# 5. Observability and Status Schema Tests
# ==============================================================================

class TestSchedulerObservability:
    def test_scheduler_get_status_complete_schema(self):
        """Verifies get_status returns all expected honest reporting fields."""
        sched = BackgroundScheduler()
        status = sched.get_status()

        assert "canonical_task_name" in status
        assert status["canonical_task_name"] == "CareerOrbit_Daily_Job_Search"
        assert "target_discovery_time" in status
        assert "current_ist_time" in status
        assert "windows_task_scheduler" in status
        assert "timezone_info" in status
        assert "missed_run_recovery" in status
        assert "active_workflow_lock" in status

    def test_real_windows_task_query_on_windows(self):
        """If running on Windows, verifies actual Task Scheduler query succeeds."""
        if os.name != "nt":
            pytest.skip("Windows-only Task Scheduler integration test.")

        sched = BackgroundScheduler()
        win_status = sched.get_windows_task_status()
        assert win_status["mode"] == "WINDOWS_TASK_SCHEDULER"
        assert win_status["task_name"] == "CareerOrbit_Daily_Job_Search"
        assert win_status["configured"] is True
        assert win_status["task_state"] in ("Ready", "Running")

    def test_cli_job_discovery_respects_workflow_lock(self):
        """Verifies run.py --job-discovery exits cleanly without exception if another process holds the lock."""
        import subprocess
        with workflow_lock("job_discovery") as acquired:
            assert acquired
            proc = subprocess.run(
                [sys.executable, "run.py", "--job-discovery"],
                capture_output=True,
                text=True,
                cwd=str(SETTINGS.BASE_DIR),
                env=os.environ.copy(),
                timeout=15,
            )
            assert proc.returncode == 0
            assert "Another job-discovery workflow is running" in proc.stdout




