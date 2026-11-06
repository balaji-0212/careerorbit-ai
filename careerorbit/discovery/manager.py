"""Asynchronous Discovery Run Manager for CareerOrbit AI.
Provides background execution, thread-safety, cross-process lock coordination,
and real-time stage/status reporting.
"""
from __future__ import annotations

import logging
import threading
import contextvars
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from careerorbit.discovery.engine import JobDiscoveryEngine
from careerorbit.scheduler.run_history import record_run, latest_success, recent_runs, workflow_lock

logger = logging.getLogger("careerorbit.discovery.manager")


class DiscoveryManager:
    """Singleton manager tracking the active background discovery run."""

    _instance: Optional["DiscoveryManager"] = None
    _lock = threading.RLock()
    _account_instances: Dict[str, "DiscoveryManager"] = {}

    def __init__(self):
        self._current_run: Optional[Dict[str, Any]] = None
        self._worker_thread: Optional[threading.Thread] = None

    @classmethod
    def get_instance(cls) -> "DiscoveryManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @classmethod
    def get_current_instance(cls) -> "DiscoveryManager":
        """Return a manager whose status and worker belong to the active account."""
        from careerorbit.config.settings import current_data_dir, SETTINGS

        root = current_data_dir().resolve()
        if root == SETTINGS.DATA_DIR.resolve():
            return cls.get_instance()
        key = str(root)
        with cls._lock:
            manager = cls._account_instances.get(key)
            if manager is None:
                manager = cls()
                cls._account_instances[key] = manager
            return manager

    def is_running(self) -> bool:
        with self._lock:
            if not self._current_run:
                return False
            status = self._current_run.get("status")
            return status in ("queued", "running")

    def start_discovery(self, initial_days: int = 1, min_acceptable: int = 30) -> Dict[str, Any]:
        """Initiates an asynchronous background discovery run.
        Returns immediately with run metadata and accepted state.
        """
        with self._lock:
            if self.is_running():
                return {
                    "status": "already_running",
                    "run_id": self._current_run.get("run_id"),
                    "message": "A discovery workflow is already in progress.",
                    "started_at": self._current_run.get("started_at"),
                }

            now_utc = datetime.now(timezone.utc)
            run_id = f"disc_{now_utc.strftime('%Y%m%d_%H%M%S')}"

            self._current_run = {
                "run_id": run_id,
                "status": "running",
                "stage": "Initializing multi-source job discovery...",
                "started_at": now_utc.isoformat(),
                "completed_at": None,
                "sources": {},
                "summary": {},
                "error": None,
                "partial_failure": False,
            }

            request_context = contextvars.copy_context()
            thread = threading.Thread(
                target=request_context.run,
                args=(self._run_worker, run_id, initial_days, min_acceptable),
                name=f"DiscoveryWorker-{run_id}",
                daemon=True,
            )
            self._worker_thread = thread
            thread.start()

            return {
                "status": "accepted",
                "run_id": run_id,
                "message": "Job discovery initiated in background.",
                "started_at": now_utc.isoformat(),
            }

    def _update_stage(self, stage: str, sources_info: Optional[Dict[str, Any]] = None) -> None:
        with self._lock:
            if self._current_run:
                self._current_run["stage"] = stage
                if sources_info:
                    self._current_run["sources"] = sources_info

    def _run_worker(self, run_id: str, initial_days: int, min_acceptable: int) -> None:
        logger.info("Starting background discovery run %s", run_id)
        with workflow_lock("job_discovery") as acquired:
            if not acquired:
                logger.warning("Discovery run %s skipped: lock held by another process", run_id)
                with self._lock:
                    if self._current_run and self._current_run.get("run_id") == run_id:
                        self._current_run["status"] = "skipped_overlap"
                        self._current_run["stage"] = "Skipped: another discovery process is currently executing."
                        self._current_run["completed_at"] = datetime.now(timezone.utc).isoformat()
                        self._current_run["error"] = "Lock contention: another job discovery process is running."
                record_run("job_discovery", "skipped_overlap")
                return

            try:
                engine = JobDiscoveryEngine()

                def progress_cb(stage: str, sources_dict: Dict[str, Any]):
                    self._update_stage(stage, sources_dict)

                res = engine.run_discovery(
                    initial_days=initial_days,
                    min_acceptable=min_acceptable,
                    progress_callback=progress_cb,
                )

                now_utc = datetime.now(timezone.utc)
                summary = {
                    "total_collected": res.get("total_collected", 0),
                    "new_jobs_added": res.get("new_jobs_added", 0),
                    "jobs_updated": res.get("jobs_updated", 0),
                    "time_window_days": res.get("time_window_days", initial_days),
                    "sources": res.get("sources", {}),
                }

                partial_failure = bool(res.get("partial_failure"))
                final_status = "partial_success" if partial_failure else "success"

                with self._lock:
                    if self._current_run and self._current_run.get("run_id") == run_id:
                        self._current_run["status"] = final_status
                        self._current_run["stage"] = (
                            f"Discovery completed with {summary['total_collected']} leads collected "
                            f"({summary['new_jobs_added']} new, {summary['jobs_updated']} updated)."
                        )
                        self._current_run["summary"] = summary
                        self._current_run["sources"] = res.get("sources", {})
                        self._current_run["partial_failure"] = partial_failure
                        self._current_run["completed_at"] = now_utc.isoformat()

                record_run("job_discovery", final_status, summary=summary)
                logger.info("Background discovery run %s finished with status %s", run_id, final_status)

            except Exception as exc:
                logger.exception("Background discovery run %s failed with exception: %s", run_id, exc)
                now_utc = datetime.now(timezone.utc)
                with self._lock:
                    if self._current_run and self._current_run.get("run_id") == run_id:
                        self._current_run["status"] = "failed"
                        self._current_run["stage"] = f"Discovery run failed: {type(exc).__name__}"
                        self._current_run["error"] = f"{type(exc).__name__}: {str(exc)}"
                        self._current_run["completed_at"] = now_utc.isoformat()

                record_run("job_discovery", "failed", error=type(exc).__name__)

    def get_status(self, run_id: Optional[str] = None) -> Dict[str, Any]:
        """Returns the status of the requested or current discovery run."""
        with self._lock:
            if self._current_run:
                if run_id is None or run_id == self._current_run.get("run_id"):
                    return dict(self._current_run)

        # Fallback to history if run_id is not the current active in-memory run
        recent = recent_runs(limit=10)
        for r in recent:
            if r.get("workflow") == "job_discovery":
                summary = r.get("summary") or {}
                return {
                    "run_id": run_id or "history_last",
                    "status": r.get("status", "unknown"),
                    "stage": f"Historical run: {r.get('status')}",
                    "started_at": r.get("timestamp"),
                    "completed_at": r.get("timestamp"),
                    "sources": summary.get("sources", {}),
                    "summary": summary,
                    "error": r.get("error"),
                    "partial_failure": r.get("status") == "partial_success",
                }

        return {
            "run_id": run_id or "none",
            "status": "idle",
            "stage": "No discovery run has been executed yet.",
            "started_at": None,
            "completed_at": None,
            "sources": {},
            "summary": {},
            "error": None,
            "partial_failure": False,
        }


DISCOVERY_MANAGER = DiscoveryManager.get_instance()
