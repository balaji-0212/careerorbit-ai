"""Unit tests for Phase 9: Scheduler Recovery and Catch-up Logic.

Verifies:
1. Missed 08:00 AM IST discovery run is automatically triggered on restart / catch-up.
2. If already executed today, duplicate execution is strictly prevented.
3. If current time is before 08:00 AM IST, recovery is not prematurely triggered.
4. Windows Task Scheduler status is honestly reported with configured, mode, and details.
"""

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
import pytest

from careerorbit.scheduler.runner import BackgroundScheduler, IST


@pytest.fixture
def scheduler():
    sched = BackgroundScheduler()
    sched.discovery_engine = MagicMock()
    sched.discovery_engine.run_discovery.return_value = {
        "status": "success",
        "total_collected": 5,
        "new_jobs": 2,
        "updated_jobs": 0,
    }
    return sched


def test_recovery_not_triggered_before_8am(scheduler):
    """If current IST time is 07:30 AM, scheduled 08:00 AM has not arrived yet."""
    morning_730 = datetime(2026, 3, 1, 7, 30, tzinfo=IST)
    with patch.object(scheduler, "get_ist_now", return_value=morning_730):
        with patch.object(scheduler, "trigger_discovery_now") as mock_trigger:
            recovered = scheduler.check_and_recover_missed_run()
            assert recovered is False
            mock_trigger.assert_not_called()


def test_missed_run_recovered_after_8am(scheduler):
    """If machine boots at 09:30 AM IST and no run completed today, recovery is triggered."""
    morning_930 = datetime(2026, 3, 1, 9, 30, tzinfo=IST)
    with patch.object(scheduler, "get_ist_now", return_value=morning_930):
        with patch("careerorbit.scheduler.runner.latest_success", return_value=None):
            with patch.object(scheduler, "trigger_discovery_now") as mock_trigger:
                recovered = scheduler.check_and_recover_missed_run()
                assert recovered is True
                mock_trigger.assert_called_once()


def test_no_duplicate_run_if_already_executed_today(scheduler):
    """If today's 08:00 AM discovery already completed today, catch-up is skipped."""
    afternoon_1400 = datetime(2026, 3, 1, 14, 0, tzinfo=IST)
    today_utc_timestamp = datetime(2026, 3, 1, 2, 30, tzinfo=timezone.utc).isoformat()  # 08:00 AM IST
    record = {
        "workflow": "job_discovery",
        "status": "success",
        "timestamp": today_utc_timestamp,
    }
    with patch.object(scheduler, "get_ist_now", return_value=afternoon_1400):
        with patch("careerorbit.scheduler.runner.latest_success", return_value=record):
            with patch.object(scheduler, "trigger_discovery_now") as mock_trigger:
                recovered = scheduler.check_and_recover_missed_run()
                assert recovered is False
                mock_trigger.assert_not_called()
                assert scheduler.last_discovery_run_date == "2026-03-01"


def test_no_duplicate_if_in_memory_date_matches_today(scheduler):
    """If scheduler already executed in memory today, check_and_recover skips."""
    afternoon = datetime(2026, 3, 1, 15, 0, tzinfo=IST)
    scheduler.last_discovery_run_date = "2026-03-01"
    with patch.object(scheduler, "get_ist_now", return_value=afternoon):
        with patch.object(scheduler, "trigger_discovery_now") as mock_trigger:
            recovered = scheduler.check_and_recover_missed_run()
            assert recovered is False
            mock_trigger.assert_not_called()


def test_windows_task_scheduler_honest_reporting(scheduler):
    """Verifies that get_windows_task_status() reports valid metadata structure."""
    status = scheduler.get_windows_task_status()
    assert isinstance(status, dict)
    assert "configured" in status
    assert "mode" in status
    assert status["mode"] in ("WINDOWS_TASK_SCHEDULER", "STANDALONE_DAEMON_PROCESS", "NON_WINDOWS_OS")

    full_status = scheduler.get_status()
    assert "windows_task_scheduler" in full_status
    assert "target_discovery_time" in full_status
