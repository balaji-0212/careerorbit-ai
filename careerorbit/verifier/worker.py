"""Background Verification Worker for CareerOrbit AI.

Provides durable, rate-limited, cancellable background verification of active job leads.
Tracks real-time progress across the 6 canonical verification statuses.
"""
from __future__ import annotations

import logging
import random
import threading
import time
import contextvars
import urllib.parse
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from careerorbit.database.db import get_connection
from careerorbit.models.schemas import VerificationStatus
from careerorbit.verifier.checker import VerificationEngine

logger = logging.getLogger("careerorbit.verifier.worker")


class VerificationWorker:
    """Manages background verification tasks with concurrency control and rate limiting."""

    _account_workers: dict[str, "VerificationWorker"] = {}
    _registry_lock = threading.RLock()

    def __init__(self, default_rate_limit: float = 0.5):
        self.default_rate_limit = default_rate_limit
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._cancel_requested = False

        self._status: str = "idle"  # idle, running, completed, cancelled, failed
        self._started_at: Optional[str] = None
        self._completed_at: Optional[str] = None
        self._total_jobs: int = 0
        self._checked_jobs: int = 0
        self._current_job: Optional[str] = None
        self._error: Optional[str] = None

        self._verified_open: int = 0
        self._verified_closed: int = 0
        self._pending_verification: int = 0
        self._broken_link: int = 0
        self._suspicious: int = 0
        self._verification_error: int = 0

        self._recent_details: List[Dict[str, Any]] = []
        self._last_request_per_domain: Dict[str, float] = {}

    @classmethod
    def get_current_instance(cls) -> "VerificationWorker":
        """Return a worker with status isolated to the active account storage root."""
        from careerorbit.config.settings import current_data_dir, SETTINGS

        root = current_data_dir().resolve()
        if root == SETTINGS.DATA_DIR.resolve():
            return VERIFICATION_WORKER
        key = str(root)
        with cls._registry_lock:
            worker = cls._account_workers.get(key)
            if worker is None:
                worker = cls()
                cls._account_workers[key] = worker
            return worker

    def is_running(self) -> bool:
        with self._lock:
            return self._status == "running"

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            pct = round((self._checked_jobs / self._total_jobs * 100.0), 1) if self._total_jobs > 0 else 0.0
            return {
                "status": self._status,
                "is_running": self._status == "running",
                "started_at": self._started_at,
                "completed_at": self._completed_at,
                "total_jobs": self._total_jobs,
                "checked_jobs": self._checked_jobs,
                "progress_pct": pct,
                "current_job": self._current_job,
                "error": self._error,
                "counts": {
                    "verified_open": self._verified_open,
                    "verified_closed": self._verified_closed,
                    "pending_verification": self._pending_verification,
                    "broken_link": self._broken_link,
                    "suspicious": self._suspicious,
                    "verification_error": self._verification_error,
                },
                "recent_details": list(self._recent_details[-20:]),
            }

    def cancel(self) -> bool:
        with self._lock:
            if self._status == "running":
                self._cancel_requested = True
                logger.info("Verification worker cancellation requested.")
                return True
            return False

    def start(self, max_jobs: int = 25, rate_limit_delay: Optional[float] = None, days_threshold: int = 7) -> Dict[str, Any]:
        with self._lock:
            if self._status == "running":
                return {"status": "already_running", "message": "Verification worker is already active."}

            self._status = "running"
            self._cancel_requested = False
            self._started_at = datetime.now(timezone.utc).isoformat()
            self._completed_at = None
            self._total_jobs = 0
            self._checked_jobs = 0
            self._current_job = "Initializing..."
            self._error = None

            self._verified_open = 0
            self._verified_closed = 0
            self._pending_verification = 0
            self._broken_link = 0
            self._suspicious = 0
            self._verification_error = 0
            self._recent_details = []
            self._last_request_per_domain = {}

            delay = rate_limit_delay if rate_limit_delay is not None else self.default_rate_limit

            request_context = contextvars.copy_context()
            self._thread = threading.Thread(
                target=request_context.run,
                args=(self._run, max_jobs, delay, days_threshold),
                daemon=True,
                name="verification-worker"
            )
            self._thread.start()

        return {"status": "started", "message": f"Verification worker started for up to {max_jobs} jobs."}

    def _run(self, max_jobs: int, delay: float, days_threshold: int) -> None:
        logger.info("Verification worker thread started (max_jobs=%d, delay=%.2fs).", max_jobs, delay)
        verifier = VerificationEngine(timeout_seconds=8)

        try:
            conn = get_connection()
            cursor = conn.cursor()
            now_utc = datetime.now(timezone.utc)
            cutoff = (now_utc - timedelta(days=days_threshold)).isoformat()

            cursor.execute("""
                SELECT id, employer, title, official_url, official_listing_url, application_url, verification_status, last_verified_at
                FROM jobs
                WHERE COALESCE(record_state, 'DISCOVERY_LEAD') != 'QUARANTINED'
                  AND (
                    (official_listing_url IS NOT NULL AND official_listing_url != '')
                    OR (official_url IS NOT NULL AND official_url != '')
                    OR (application_url IS NOT NULL AND application_url != '')
                  )
                  AND (
                    verification_status IN ('PENDING_VERIFICATION', 'UNVERIFIED', 'VERIFICATION_ERROR', 'STATUS_UNKNOWN', 'BROKEN_LINK', 'SUSPICIOUS')
                    OR last_verified_at IS NULL
                    OR last_verified_at <= ?
                  )
                ORDER BY 
                    CASE WHEN verification_status IN ('PENDING_VERIFICATION', 'UNVERIFIED', 'VERIFICATION_ERROR', 'STATUS_UNKNOWN', 'BROKEN_LINK', 'SUSPICIOUS') THEN 0 ELSE 1 END,
                    last_verified_at ASC NULLS FIRST
                LIMIT ?
            """, (cutoff, max_jobs))

            rows = cursor.fetchall()
            with self._lock:
                self._total_jobs = len(rows)

            for row in rows:
                with self._lock:
                    if self._cancel_requested:
                        self._status = "cancelled"
                        self._completed_at = datetime.now(timezone.utc).isoformat()
                        self._current_job = None
                        logger.info("Verification worker halted by cancellation.")
                        conn.close()
                        return

                job_id = row["id"]
                employer = row["employer"] or ""
                title = row["title"] or ""
                target_url = row["official_listing_url"] or row["official_url"] or row["application_url"]

                with self._lock:
                    self._current_job = f"{employer} — {title}"

                # Per-domain rate limiting with jitter
                self._throttle_domain(target_url, delay)

                # Execute verification check
                try:
                    status, evidence = verifier.verify_listing(target_url, employer=employer)
                    status_str = status.value if hasattr(status, "value") else str(status)
                except Exception as exc:
                    status_str = VerificationStatus.VERIFICATION_ERROR.value
                    evidence = f"Verification check threw unexpected error: {type(exc).__name__}."

                check_time = datetime.now(timezone.utc).isoformat()

                # Atomically update DB record
                cursor.execute("""
                    UPDATE jobs
                    SET verification_status = ?,
                        last_verified_at = ?,
                        verification_source = ?,
                        verification_notes = ?
                    WHERE id = ?
                """, (
                    status_str,
                    check_time,
                    "Background Verification Worker",
                    evidence,
                    job_id
                ))
                conn.commit()

                # Record statistics
                with self._lock:
                    self._checked_jobs += 1
                    if status_str == VerificationStatus.VERIFIED_OPEN.value:
                        self._verified_open += 1
                    elif status_str == VerificationStatus.VERIFIED_CLOSED.value:
                        self._verified_closed += 1
                    elif status_str in (VerificationStatus.PENDING_VERIFICATION.value, "UNVERIFIED"):
                        self._pending_verification += 1
                    elif status_str == VerificationStatus.BROKEN_LINK.value:
                        self._broken_link += 1
                    elif status_str == VerificationStatus.SUSPICIOUS.value:
                        self._suspicious += 1
                    else:
                        self._verification_error += 1

                    self._recent_details.append({
                        "job_id": job_id,
                        "employer": employer,
                        "title": title,
                        "url": target_url,
                        "status": status_str,
                        "evidence": evidence,
                        "checked_at": check_time
                    })

            conn.close()
            with self._lock:
                self._status = "completed"
                self._completed_at = datetime.now(timezone.utc).isoformat()
                self._current_job = None
            logger.info("Verification worker completed %d jobs successfully.", self._checked_jobs)

        except Exception as exc:
            logger.error("Verification worker failed with unexpected exception: %s", exc, exc_info=True)
            with self._lock:
                self._status = "failed"
                self._error = f"Worker failed: {type(exc).__name__}: {str(exc)}"
                self._completed_at = datetime.now(timezone.utc).isoformat()
                self._current_job = None

    def _throttle_domain(self, url: str, base_delay: float) -> None:
        try:
            parsed = urllib.parse.urlparse(url)
            domain = (parsed.netloc or "").lower()
            if not domain:
                return

            last_time = self._last_request_per_domain.get(domain, 0.0)
            now = time.monotonic()
            elapsed = now - last_time

            # Add 50-150ms of random jitter
            target_delay = base_delay + random.uniform(0.05, 0.15)
            if elapsed < target_delay:
                sleep_needed = target_delay - elapsed
                time.sleep(sleep_needed)

            self._last_request_per_domain[domain] = time.monotonic()
        except Exception:
            time.sleep(base_delay)


# Singleton verification worker instance
VERIFICATION_WORKER = VerificationWorker()
