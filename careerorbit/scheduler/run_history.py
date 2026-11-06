"""Durable workflow history and cross-process concurrency locking for CareerOrbit AI."""
import json
import logging
import os
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Dict, List

from careerorbit.config.settings import SETTINGS, current_logs_dir

logger = logging.getLogger("careerorbit.scheduler.lock")

_thread_locks: dict[str, threading.Lock] = {}
_guard = threading.Lock()


@contextmanager
def workflow_lock(workflow: str):
    """Try to acquire a process-wide and cross-process nonblocking workflow lock.
    
    Guarantees:
    - Atomically blocks overlapping runs across processes using OS kernel byte-range locking.
    - Automatically releases on process termination, unhandled exceptions, or crashes.
    - Records metadata (PID, acquired_at) for observability.
    - Safe against stale locks: if a process crashed, the kernel releases the handle lock immediately.
    """
    with _guard:
        thread_lock = _thread_locks.setdefault(workflow, threading.Lock())
    if not thread_lock.acquire(blocking=False):
        logger.info(f"Thread contention: workflow '{workflow}' is already active in another thread.")
        yield False
        return

    stream = None
    locked = False
    lock_file = current_logs_dir() / f"{workflow}.lock"
    meta_file = current_logs_dir() / f"{workflow}.lock.json"

    try:
        current_logs_dir().mkdir(parents=True, exist_ok=True)
        stream = lock_file.open("a+b")
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b"0\n")
            stream.flush()
        stream.seek(0)

        if os.name == "nt":
            import msvcrt
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                locked = True
            except OSError:
                locked = False
        else:
            import fcntl
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
            except OSError:
                locked = False

        if locked:
            # Write ownership metadata to companion metadata file
            try:
                meta = {
                    "pid": os.getpid(),
                    "acquired_at": datetime.now(timezone.utc).isoformat(),
                    "workflow": workflow,
                }
                meta_file.write_text(json.dumps(meta), encoding="utf-8")
            except Exception:
                pass
        else:
            # Inspect existing lock holder for honest logging
            holder = get_workflow_lock_info(workflow)
            logger.warning(
                "Cross-process lock contention: workflow '%s' is locked by PID %s (acquired %s).",
                workflow, holder.get("pid"), holder.get("acquired_at")
            )

        yield locked
    finally:
        if stream is not None:
            if locked:
                try:
                    meta_file.unlink(missing_ok=True)
                except Exception:
                    pass
                try:
                    if os.name == "nt":
                        stream.seek(0)
                        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass
            try:
                stream.close()
            except Exception:
                pass
        thread_lock.release()


def is_workflow_locked(workflow: str) -> bool:
    """Test if a workflow is currently locked without holding the lock."""
    with _guard:
        thread_lock = _thread_locks.get(workflow)
        if thread_lock is not None and thread_lock.locked():
            return True

    lock_file = current_logs_dir() / f"{workflow}.lock"
    if not lock_file.exists():
        return False

    try:
        with lock_file.open("r+b") as s:
            s.seek(0)
            if os.name == "nt":
                import msvcrt
                try:
                    msvcrt.locking(s.fileno(), msvcrt.LK_NBLCK, 1)
                    msvcrt.locking(s.fileno(), msvcrt.LK_UNLCK, 1)
                    return False
                except OSError:
                    return True
            else:
                import fcntl
                try:
                    fcntl.flock(s.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    fcntl.flock(s.fileno(), fcntl.LOCK_UN)
                    return False
                except OSError:
                    return True
    except OSError:
        return True
    return False


def get_workflow_lock_info(workflow: str) -> Dict[str, Any]:
    """Retrieve metadata about the current lock holder, if any."""
    is_active = is_workflow_locked(workflow)
    if not is_active:
        return {"locked": False, "pid": None, "acquired_at": None, "workflow": workflow}

    meta_file = current_logs_dir() / f"{workflow}.lock.json"
    meta = {}
    if meta_file.exists():
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    return {
        "locked": is_active,
        "pid": meta.get("pid"),
        "acquired_at": meta.get("acquired_at"),
        "workflow": workflow,
    }


def record_run(
    workflow: str,
    status: str,
    summary: Any = None,
    error: Optional[str] = None,
    trigger: Optional[str] = "scheduled",
    timestamp: Optional[str] = None,
) -> Dict[str, Any]:
    """Persist run outcome to durable workflow_runs.jsonl history."""
    current_logs_dir().mkdir(parents=True, exist_ok=True)
    record = {
        "workflow": workflow,
        "status": status,
        "trigger": trigger or "scheduled",
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "error": error,
    }
    with (current_logs_dir() / "workflow_runs.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    return record


def last_success(workflow: str) -> Optional[str]:
    """Return the UTC timestamp string of the latest successful run."""
    record = latest_success(workflow)
    return record.get("timestamp") if record else None


def latest_success(workflow: str) -> Optional[dict[str, Any]]:
    """Return the complete record dictionary of the latest successful run."""
    history = current_logs_dir() / "workflow_runs.jsonl"
    if not history.is_file():
        return None
    try:
        with history.open("r", encoding="utf-8") as stream:
            for line in reversed(stream.readlines()[-1000:]):
                row = json.loads(line)
                if row.get("workflow") == workflow and row.get("status") in ("success", "recovered"):
                    return row
    except (OSError, ValueError, TypeError):
        return None
    return None


def latest_attempt(workflow: str) -> Optional[dict[str, Any]]:
    """Return the complete record dictionary of the most recent run attempt."""
    history = current_logs_dir() / "workflow_runs.jsonl"
    if not history.is_file():
        return None
    try:
        with history.open("r", encoding="utf-8") as stream:
            lines = stream.readlines()
            for line in reversed(lines[-1000:]):
                row = json.loads(line)
                if row.get("workflow") == workflow:
                    return row
    except (OSError, ValueError, TypeError):
        return None
    return None


def count_failures_today(workflow: str, today_ist_prefix: str) -> int:
    """Count how many failed runs have been recorded today to prevent infinite retry loops."""
    history = current_logs_dir() / "workflow_runs.jsonl"
    if not history.is_file():
        return 0
    failures = 0
    try:
        with history.open("r", encoding="utf-8") as stream:
            for line in stream.readlines()[-200:]:
                row = json.loads(line)
                if row.get("workflow") == workflow and row.get("status") == "failed":
                    ts = row.get("timestamp", "")
                    # Convert UTC timestamp to IST date string for match
                    try:
                        from careerorbit.scheduler.timezone_helper import IST
                        dt = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(IST)
                        if dt.strftime("%Y-%m-%d") == today_ist_prefix:
                            failures += 1
                    except Exception:
                        pass
    except (OSError, ValueError, TypeError):
        pass
    return failures


def recent_runs(limit: int = 100) -> list[dict[str, Any]]:
    """Return the most recent run records up to limit."""
    history = current_logs_dir() / "workflow_runs.jsonl"
    if not history.is_file():
        return []
    rows = []
    try:
        with history.open("r", encoding="utf-8") as stream:
            for line in stream.readlines()[-max(1, min(limit, 500)):]:
                try:
                    item = json.loads(line)
                    if isinstance(item, dict):
                        rows.append(item)
                except ValueError:
                    continue
    except OSError:
        return []
    return list(reversed(rows))
