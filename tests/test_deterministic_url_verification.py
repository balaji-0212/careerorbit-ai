"""Comprehensive deterministic test suite for URL verification engine and SSRF defense.

Verifies all 21 distinct network and verification scenarios mandated by Section 5.3.
Uses deterministic DNS resolver and mocked HTTP sessions without external dependencies.
"""
import ipaddress
import socket
from unittest.mock import MagicMock, patch
import pytest
import requests

from careerorbit.models.schemas import VerificationStatus
from careerorbit.verifier.checker import (
    VerificationEngine,
    _public_http_url,
    deterministic_test_dns_resolver,
)


def custom_dns_resolver(host: str):
    """Custom resolver mapping hosts to specific test IP addresses."""
    host = host.lower().rstrip(".")
    if host == "loopback.test":
        return [ipaddress.ip_address("127.0.0.1")]
    if host == "private-rfc1918.test":
        return [ipaddress.ip_address("192.168.1.50")]
    if host == "private-10.test":
        return [ipaddress.ip_address("10.0.0.1")]
    if host == "link-local.test":
        return [ipaddress.ip_address("169.254.1.1")]
    if host == "cloud-metadata.test":
        return [ipaddress.ip_address("169.254.169.254")]
    if host in ("dns-fails.test", "nonexistent.domain"):
        raise socket.gaierror("Name resolution failed")
    if host in ("public-ats.test", "boards.greenhouse.io", "jobs.lever.co", "canonical.com", "apex.com"):
        return [ipaddress.ip_address("104.18.0.1")]
    return [ipaddress.ip_address("104.18.0.1")]


@pytest.fixture
def engine():
    return VerificationEngine(timeout_seconds=5, dns_resolver=custom_dns_resolver)


def test_case_01_valid_public_https_url(engine):
    """1. Valid public HTTPS URL passes public safety check."""
    assert _public_http_url("https://boards.greenhouse.io/canonical/jobs/123", resolver=custom_dns_resolver) is True


def test_case_02_http_404_not_found(engine):
    """2. HTTP 404 marks vacancy as VERIFIED_CLOSED."""
    resp = MagicMock()
    resp.status_code = 404
    with patch.object(engine.session, "get", return_value=resp):
        status, evidence = engine.verify_listing("https://boards.greenhouse.io/canonical/jobs/404", employer="Canonical")
        assert status == VerificationStatus.VERIFIED_CLOSED
        assert "404" in evidence


def test_case_03_http_410_gone(engine):
    """3. HTTP 410 Gone marks vacancy as VERIFIED_CLOSED."""
    resp = MagicMock()
    resp.status_code = 410
    with patch.object(engine.session, "get", return_value=resp):
        status, evidence = engine.verify_listing("https://boards.greenhouse.io/canonical/jobs/410", employer="Canonical")
        assert status == VerificationStatus.VERIFIED_CLOSED
        assert "410" in evidence


def test_case_04_http_403_forbidden(engine):
    """4. HTTP 403 Forbidden is a VERIFICATION_ERROR (not assumed closed)."""
    resp = MagicMock()
    resp.status_code = 403
    with patch.object(engine.session, "get", return_value=resp):
        status, evidence = engine.verify_listing("https://boards.greenhouse.io/canonical/jobs/403", employer="Canonical")
        assert status == VerificationStatus.VERIFICATION_ERROR
        assert "not assumed closed" in evidence.lower()


def test_case_05_http_429_rate_limited(engine):
    """5. HTTP 429 Rate Limited is a VERIFICATION_ERROR (not assumed closed)."""
    resp = MagicMock()
    resp.status_code = 429
    with patch.object(engine.session, "get", return_value=resp):
        status, evidence = engine.verify_listing("https://boards.greenhouse.io/canonical/jobs/429", employer="Canonical")
        assert status == VerificationStatus.VERIFICATION_ERROR
        assert "rate limited" in evidence.lower()


def test_case_06_network_timeout(engine):
    """6. Network timeout returns VERIFICATION_ERROR (not assumed closed)."""
    with patch.object(engine.session, "get", side_effect=requests.exceptions.Timeout("Connection timed out")):
        status, evidence = engine.verify_listing("https://boards.greenhouse.io/canonical/jobs/timeout", employer="Canonical")
        assert status == VerificationStatus.VERIFICATION_ERROR
        assert "not assumed closed" in evidence.lower()


def test_case_07_dns_failure(engine):
    """7. DNS failure blocks request and returns STATUS_UNKNOWN."""
    status, evidence = engine.verify_listing("https://dns-fails.test/job/1", employer="Canonical")
    assert status == VerificationStatus.STATUS_UNKNOWN
    assert "public host" in evidence.lower()


def test_case_08_invalid_hostname(engine):
    """8. Invalid hostnames reject before making HTTP request."""
    assert _public_http_url("https://.invalid..hostname/job", resolver=custom_dns_resolver) is False


def test_case_09_loopback_address(engine):
    """9. Loopback addresses (127.0.0.1, localhost) rejected for SSRF protection."""
    assert _public_http_url("https://127.0.0.1/admin", resolver=custom_dns_resolver) is False
    assert _public_http_url("https://localhost/admin", resolver=custom_dns_resolver) is False
    assert _public_http_url("https://loopback.test/admin", resolver=custom_dns_resolver) is False


def test_case_10_private_ip_address(engine):
    """10. RFC 1918 private IP addresses (10.x, 192.168.x) rejected for SSRF protection."""
    assert _public_http_url("https://192.168.1.1/secret", resolver=custom_dns_resolver) is False
    assert _public_http_url("https://10.0.0.1/secret", resolver=custom_dns_resolver) is False
    assert _public_http_url("https://private-rfc1918.test/secret", resolver=custom_dns_resolver) is False


def test_case_11_link_local_address(engine):
    """11. Link-local addresses (169.254.x.x) rejected for SSRF protection."""
    assert _public_http_url("https://169.254.1.1/data", resolver=custom_dns_resolver) is False
    assert _public_http_url("https://link-local.test/data", resolver=custom_dns_resolver) is False


def test_case_12_cloud_metadata_address(engine):
    """12. Cloud metadata IP 169.254.169.254 rejected for SSRF protection."""
    assert _public_http_url("https://169.254.169.254/latest/meta-data/", resolver=custom_dns_resolver) is False
    assert _public_http_url("https://cloud-metadata.test/computeMetadata/v1/", resolver=custom_dns_resolver) is False


def test_case_13_redirect_to_approved_public_ats(engine):
    """13. Redirect to an approved official ATS is followed and evaluated."""
    resp1 = MagicMock()
    resp1.status_code = 302
    resp1.headers = {"location": "https://boards.greenhouse.io/canonical/jobs/555"}

    resp2 = MagicMock()
    resp2.status_code = 200
    resp2.headers = {}
    resp2.text = "<html><body><h1>Software Engineer</h1><button id='apply_button'>Apply Now</button></body></html>"

    with patch.object(engine.session, "get", side_effect=[resp1, resp2]):
        status, evidence = engine.verify_listing("https://canonical.com/careers/se-555", employer="Canonical")
        assert status == VerificationStatus.VERIFIED_OPEN
        assert "application action" in evidence.lower()


def test_case_14_redirect_to_disallowed_destination(engine):
    """14. Redirect to untrusted external aggregator is flagged as SUSPICIOUS."""
    resp1 = MagicMock()
    resp1.status_code = 302
    resp1.headers = {"location": "https://suspicious-unknown-site.org/track"}

    with patch.object(engine.session, "get", return_value=resp1):
        status, evidence = engine.verify_listing("https://canonical.com/careers/job1", employer="Canonical")
        assert status == VerificationStatus.SUSPICIOUS
        assert "destination not followed" in evidence.lower()


def test_case_15_redirect_to_private_or_loopback_destination(engine):
    """15. Redirect targeting loopback or private network is blocked."""
    resp1 = MagicMock()
    resp1.status_code = 302
    resp1.headers = {"location": "https://127.0.0.1:8000/internal-api"}

    with patch.object(engine.session, "get", return_value=resp1):
        status, evidence = engine.verify_listing("https://canonical.com/careers/job1", employer="Canonical")
        assert status == VerificationStatus.SUSPICIOUS


def test_case_16_generic_employer_homepage(engine):
    """16. Resolving to root homepage or generic careers directory is SUSPICIOUS."""
    status, evidence = engine.verify_listing("https://canonical.com/careers/", employer="Canonical")
    assert status == VerificationStatus.SUSPICIOUS
    assert "generic" in evidence.lower() or "homepage" in evidence.lower()


def test_case_17_generic_aggregator_page(engine):
    """17. Third-party aggregator page without official ATS confirmation is PENDING_VERIFICATION."""
    resp = MagicMock()
    resp.status_code = 200
    resp.headers = {}
    resp.text = "<html><body><h1>Job Postings on Indeed</h1></body></html>"
    with patch.object(engine.session, "get", return_value=resp):
        status, evidence = engine.verify_listing("https://indeed.com/viewjob?jk=123", employer="Apex")
        assert status == VerificationStatus.PENDING_VERIFICATION
        assert "third-party" in evidence.lower() or "confirmed employer" in evidence.lower()


def test_case_18_captcha_or_antibot_response(engine):
    """18. Security challenge / CAPTCHA returns VERIFICATION_ERROR (not assumed closed)."""
    resp = MagicMock()
    resp.status_code = 200
    resp.headers = {}
    resp.text = "<html><body>Please complete the security check to continue. Cloudflare Ray ID...</body></html>"
    with patch.object(engine.session, "get", return_value=resp):
        status, evidence = engine.verify_listing("https://boards.greenhouse.io/canonical/jobs/123", employer="Canonical")
        assert status == VerificationStatus.VERIFICATION_ERROR
        assert "security challenge" in evidence.lower()


def test_case_19_explicit_job_closure_text(engine):
    """19. Page containing explicit closure phrases marks vacancy as VERIFIED_CLOSED."""
    resp = MagicMock()
    resp.status_code = 200
    resp.headers = {}
    resp.text = "<html><body>We are no longer accepting applications for this job. Position has been filled.</body></html>"
    with patch.object(engine.session, "get", return_value=resp):
        status, evidence = engine.verify_listing("https://boards.greenhouse.io/canonical/jobs/123", employer="Canonical")
        assert status == VerificationStatus.VERIFIED_CLOSED
        assert "closure text" in evidence.lower()


def test_case_20_application_page_with_action(engine):
    """20. Requisition page with visible application action marks vacancy as VERIFIED_OPEN."""
    resp = MagicMock()
    resp.status_code = 200
    resp.headers = {}
    resp.text = "<html><body><h1>Junior Data Analyst</h1><a href='#apply'>Apply Now</a></body></html>"
    with patch.object(engine.session, "get", return_value=resp):
        status, evidence = engine.verify_listing("https://boards.greenhouse.io/canonical/jobs/123", employer="Canonical")
        assert status == VerificationStatus.VERIFIED_OPEN
        assert "application action" in evidence.lower()


def test_case_21_accessible_page_uncertain_status(engine):
    """21. Requisition page lacking explicit application action or closure returns PENDING_VERIFICATION."""
    resp = MagicMock()
    resp.status_code = 200
    resp.headers = {}
    resp.text = "<html><body><h1>About Our Team</h1><p>We build open source technology for Linux.</p></body></html>"
    with patch.object(engine.session, "get", return_value=resp):
        status, evidence = engine.verify_listing("https://boards.greenhouse.io/canonical/jobs/123", employer="Canonical")
        assert status == VerificationStatus.PENDING_VERIFICATION
        assert "no application action" in evidence.lower() or "uncertain" in evidence.lower()
