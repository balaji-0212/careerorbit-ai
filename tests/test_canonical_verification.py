"""Tests for formal canonical verification statuses and state machine."""
import pytest
from unittest.mock import MagicMock, patch
import requests

from careerorbit.models.schemas import VerificationStatus, Job
from careerorbit.verifier.checker import VerificationEngine
from careerorbit.database.db import get_job_stats, list_jobs, init_db

@pytest.fixture(autouse=True)
def setup_db():
    init_db()
    with patch("careerorbit.verifier.checker._public_http_url", return_value=True):
        yield

def test_canonical_verification_statuses_exist():
    assert VerificationStatus.VERIFIED_OPEN.value == "VERIFIED_OPEN"
    assert VerificationStatus.VERIFIED_CLOSED.value == "VERIFIED_CLOSED"
    assert VerificationStatus.PENDING_VERIFICATION.value == "PENDING_VERIFICATION"
    assert VerificationStatus.BROKEN_LINK.value == "BROKEN_LINK"
    assert VerificationStatus.SUSPICIOUS.value == "SUSPICIOUS"
    assert VerificationStatus.VERIFICATION_ERROR.value == "VERIFICATION_ERROR"

def test_legacy_status_aliases():
    from careerorbit.models.schemas import canonicalize_verification_status
    assert canonicalize_verification_status("UNVERIFIED") == "PENDING_VERIFICATION"
    assert canonicalize_verification_status("STATUS_UNKNOWN") == "VERIFICATION_ERROR"
    assert VerificationStatus.UNVERIFIED.value == "UNVERIFIED"
    assert VerificationStatus.STATUS_UNKNOWN.value == "STATUS_UNKNOWN"

def test_verify_listing_closure_patterns():
    verifier = VerificationEngine()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "<html><body>This position has been filled. No longer accepting applications.</body></html>"
    mock_resp.headers = {}

    with patch.object(verifier.session, "get", return_value=mock_resp):
        status, evidence = verifier.verify_listing("https://boards.greenhouse.io/canonical/jobs/12345", employer="Canonical")
        assert status == VerificationStatus.VERIFIED_CLOSED
        assert "closed or removed" in evidence.lower()

def test_verify_listing_http_404():
    verifier = VerificationEngine()
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.headers = {}

    with patch.object(verifier.session, "get", return_value=mock_resp):
        status, evidence = verifier.verify_listing("https://boards.greenhouse.io/canonical/jobs/99999", employer="Canonical")
        assert status == VerificationStatus.VERIFIED_CLOSED
        assert "404" in evidence

def test_verify_listing_rate_limited_or_forbidden():
    verifier = VerificationEngine()
    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_resp.headers = {}

    with patch.object(verifier.session, "get", return_value=mock_resp):
        status, evidence = verifier.verify_listing("https://boards.greenhouse.io/canonical/jobs/12345", employer="Canonical")
        assert status == VerificationStatus.VERIFICATION_ERROR
        assert "not assumed closed" in evidence.lower()

def test_verify_listing_timeout():
    verifier = VerificationEngine()
    with patch.object(verifier.session, "get", side_effect=requests.exceptions.Timeout("Read timed out")):
        status, evidence = verifier.verify_listing("https://boards.greenhouse.io/canonical/jobs/12345", employer="Canonical")
        assert status == VerificationStatus.VERIFICATION_ERROR
        assert "not assumed closed" in evidence.lower()

def test_verify_listing_broken_link():
    verifier = VerificationEngine()
    with patch.object(verifier.session, "get", side_effect=requests.exceptions.SSLError("Certificate failed")):
        status, evidence = verifier.verify_listing("https://boards.greenhouse.io/canonical/jobs/12345", employer="Canonical")
        assert status == VerificationStatus.BROKEN_LINK
        assert "broken" in evidence.lower()

def test_verify_listing_suspicious_homepage():
    verifier = VerificationEngine()
    status, evidence = verifier.verify_listing("https://canonical.com/careers", employer="Canonical")
    assert status == VerificationStatus.SUSPICIOUS
    assert "homepage or generic" in evidence.lower()

def test_verify_listing_verified_open():
    verifier = VerificationEngine()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "<html><body><h1>Data Analyst</h1><button class='apply-btn'>Apply for this job</button></body></html>"
    mock_resp.headers = {}

    with patch.object(verifier.session, "get", return_value=mock_resp):
        status, evidence = verifier.verify_listing("https://boards.greenhouse.io/canonical/jobs/12345", employer="Canonical")
        assert status == VerificationStatus.VERIFIED_OPEN
        assert "application action" in evidence.lower()

def test_db_job_stats_includes_all_six_canonical_counters():
    stats = get_job_stats()
    breakdown = stats.get("verification_breakdown", {})
    assert "VERIFIED_OPEN" in breakdown
    assert "VERIFIED_CLOSED" in breakdown
    assert "PENDING_VERIFICATION" in breakdown
    assert "BROKEN_LINK" in breakdown
    assert "SUSPICIOUS" in breakdown
    assert "VERIFICATION_ERROR" in breakdown
