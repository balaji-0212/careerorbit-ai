"""Tests for background verification worker."""
import pytest
import time

from careerorbit.database.db import init_db, save_job
from careerorbit.models.schemas import Job, VerificationStatus
from careerorbit.verifier.worker import VerificationWorker, VERIFICATION_WORKER
from careerorbit.web.app import (
    start_verification_worker_endpoint,
    get_verification_worker_status_endpoint,
    cancel_verification_worker_endpoint
)

@pytest.fixture(autouse=True)
def setup_db():
    init_db()
    save_job(Job(
        job_uid="worker_test_uid",
        employer="Canonical",
        title="Software Engineer",
        normalized_title="software engineer",
        official_url="https://canonical.com/careers/1",
        official_listing_url="https://canonical.com/careers/1",
        canonical_url="https://canonical.com/careers/1",
        discovery_source="Direct",
        verification_status=VerificationStatus.PENDING_VERIFICATION
    ))

def test_verification_worker_initial_status():
    status = VERIFICATION_WORKER.get_status()
    assert "status" in status
    assert "counts" in status
    assert "verified_open" in status["counts"]
    assert "verified_closed" in status["counts"]
    assert "pending_verification" in status["counts"]
    assert "broken_link" in status["counts"]
    assert "suspicious" in status["counts"]
    assert "verification_error" in status["counts"]

def test_verification_worker_lifecycle():
    worker = VerificationWorker(default_rate_limit=0.01)
    # Start on small batch
    res = worker.start(max_jobs=2, rate_limit_delay=0.01)
    assert res["status"] == "started"

    # Cancel if running and join thread
    worker.cancel()
    if worker._thread:
        worker._thread.join(timeout=2.0)
    st = worker.get_status()
    assert st["status"] in ("cancelled", "completed")

def test_verification_worker_api_endpoints():
    data = get_verification_worker_status_endpoint()
    assert "status" in data
    assert "counts" in data
