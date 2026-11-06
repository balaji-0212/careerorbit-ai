"""Hermetic test environment configuration for CareerOrbit AI.

Isolates tests from production database, candidate private documents, real Telegram polling,
and external network/DNS dependencies.
"""
import pytest
import copy
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone
import hashlib
import sqlite3

from careerorbit.config.settings import SETTINGS
from careerorbit.scheduler.runner import SCHEDULER
from careerorbit.telegram.worker import TELEGRAM_WORKER
from careerorbit.verifier.checker import deterministic_test_dns_resolver
import careerorbit.verifier.checker as verifier_module
from careerorbit.config.profile import CANDIDATE_PROFILE
from careerorbit.config.candidate_evidence import load_candidate_profile_overrides

TEST_CANDIDATE_PROFILE = json.loads(
    (Path(__file__).parent / "fixtures" / "candidate_profile.json").read_text(encoding="utf-8")
)
TEST_CANDIDATE_PROFILE["priority_roles"] = {
    int(key): value for key, value in TEST_CANDIDATE_PROFILE["priority_roles"].items()
}


@pytest.fixture(autouse=True)
def isolate_careerorbit_storage(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    resumes_dir = data_dir / "resumes"
    exports_dir = data_dir / "exports"
    logs_dir = data_dir / "logs"
    for directory in (data_dir, resumes_dir, exports_dir, logs_dir):
        directory.mkdir(parents=True, exist_ok=True)

    # 1. Isolate filesystem paths
    monkeypatch.setenv("CAREERORBIT_DATA_DIR", str(data_dir))
    monkeypatch.setenv("CAREERORBIT_LOGS_DIR", str(logs_dir))
    monkeypatch.setattr(SETTINGS, "DATA_DIR", data_dir)
    monkeypatch.setattr(SETTINGS, "DATABASE_PATH", data_dir / "careerorbit_test.db")
    monkeypatch.setattr(SETTINGS, "RESUMES_DIR", resumes_dir)
    monkeypatch.setattr(SETTINGS, "EXPORTS_DIR", exports_dir)
    monkeypatch.setattr(SETTINGS, "LOGS_DIR", logs_dir)

    # Use an explicitly synthetic candidate profile in every test. The local
    # installation's private profile is never used as test input or output.
    CANDIDATE_PROFILE.clear()
    CANDIDATE_PROFILE.update(copy.deepcopy(TEST_CANDIDATE_PROFILE))
    load_candidate_profile_overrides()

    # 2. Set hermetic testing flags
    monkeypatch.setattr(SETTINGS, "TESTING", True)
    monkeypatch.setenv("CAREERORBIT_TESTING", "true")

    # Existing endpoint tests operate as one synthetic account. Authentication
    # focused tests opt out explicitly with X-Test-Unauthenticated.
    from careerorbit.auth.store import init_auth_store
    init_auth_store()
    auth_path = data_dir / "auth.db"
    token = "test-session-token"
    csrf = "test-csrf-token"
    now = datetime.now(timezone.utc).isoformat()
    expires = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    digest = lambda value: hashlib.sha256(value.encode("utf-8")).hexdigest()
    with sqlite3.connect(auth_path) as auth_conn:
        auth_conn.execute(
            "INSERT OR IGNORE INTO users(id,email,display_name,password_hash,storage_key,created_at) "
            "VALUES('test-user','test@example.test','Test User','test-only-hash','legacy',?)", (now,)
        )
        auth_conn.execute(
            "INSERT OR IGNORE INTO sessions(user_id,token_hash,csrf_hash,created_at,last_seen_at,expires_at) "
            "VALUES('test-user',?,?,?,?,?)",
            (digest(token), digest(csrf), now, now, expires),
        )

    # 3. Inject deterministic DNS resolver for hermetic offline test execution
    monkeypatch.setattr(verifier_module, "DEFAULT_DNS_RESOLVER", deterministic_test_dns_resolver)

    # 4. Ensure background workers do not poll external network
    monkeypatch.setattr(TELEGRAM_WORKER, "start", lambda: False)
    monkeypatch.setattr(SCHEDULER, "start", lambda: None)

    yield

    # Teardown safety: ensure any lingering threads are stopped
    if TELEGRAM_WORKER.is_running:
        TELEGRAM_WORKER.stop()
    if SCHEDULER.running:
        SCHEDULER.stop()
