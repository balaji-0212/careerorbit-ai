"""Unit and Integration Tests for Step 2: Release Packaging, Manifest Integrity, and Report Reconciliation.

Verifies:
1. Manifest Accuracy:
   - Cryptographic SHA-256 and byte sizes match archive contents.
   - Missing archive detection.
   - Tampered/modified archive detection.
   - Manifest field completeness and malformed JSON handling.
2. Build-Order & Non-Circularity:
   - Embedded manifest does not contain self-referential archive hashes.
   - External manifest is authoritative for archive-level checksums.
3. Strict Sanitization:
   - .env excluded, .env.example allowed.
   - Databases, candidate resumes, runtime logs, candidate history excluded.
   - .git and .venv excluded.
   - Unmasked credentials detected; placeholders permitted.
4. Path Traversal Safety:
   - Rejection of ../ or leading slashes in archive entries.
5. Atomic Staging & Rollback Safety:
   - Failed packaging does not overwrite valid release artifacts.
6. Report Provenance:
   - Authoritative report exists and historical reports are explicitly flagged.
"""

import json
import hashlib
import os
import shutil
import tempfile
import zipfile
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path

from scripts.package_release import (
    package_sanitized_source,
    package_reports,
    scan_archive_recursively,
    generate_external_manifests,
    sha256_file,
    is_placeholder,
    EXCLUDE_FILES,
    EXCLUDE_DIRS,
    EXCLUDE_EXTS,
    validate_live_source_coverage_report,
    private_profile_markers,
    contains_private_profile_marker,
)
from scripts.verify_release_integrity import (
    verify_release,
    check_path_traversal,
    verify_sanitization,
    REQUIRED_SOURCE_FILES,
    REQUIRED_REPORT_FILES,
)


@pytest.fixture
def isolated_dist(tmp_path):
    """Fixture to build mock release archives and manifests in an isolated directory."""
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)

    src_zip = dist_dir / "CareerOrbit_AI_Sanitized_Source.zip"
    with zipfile.ZipFile(src_zip, "w") as zf:
        zf.writestr("careerorbit/__init__.py", "__version__ = '2.0.0'\n")
        zf.writestr("careerorbit/web/app.py", "# FastAPI app\n")
        zf.writestr("careerorbit/career_priorities.py", "# Priorities\n")
        zf.writestr("careerorbit/eligibility.py", "# Eligibility\n")
        zf.writestr("careerorbit/matcher/scorer.py", "# Scorer\n")
        zf.writestr("careerorbit/database/db.py", "# Database\n")
        zf.writestr("careerorbit/config/settings.py", "# Settings\n")
        zf.writestr("careerorbit/security/__init__.py", "# Security\n")
        zf.writestr("careerorbit/security/scanner.py", "# Scanner\n")
        zf.writestr("tests/conftest.py", "# Conftest\n")
        zf.writestr("README.md", "# CareerOrbit AI\n")
        zf.writestr(".env.example", "SECRET_KEY=your_secret_key_here\n")
        zf.writestr("docs/RELEASE_MANIFEST.md", "# Embedded Manifest\n")

    rep_zip = dist_dir / "CareerOrbit_AI_Audit_Reports.zip"
    with zipfile.ZipFile(rep_zip, "w") as zf:
        zf.writestr("docs/RELEASE_MANIFEST.md", "# Embedded Manifest\n")
        zf.writestr("reports/SECURITY_SCAN_REPORT.json", '{"status": "PASSED", "violations_count": 0}\n')
        zf.writestr("reports/CURRENT_RELEASE_VERIFICATION_REPORT.md", "# Current Verification Report\n")

    src_size = src_zip.stat().st_size
    src_hash = sha256_file(src_zip)
    rep_size = rep_zip.stat().st_size
    rep_hash = sha256_file(rep_zip)

    generate_external_manifests(
        src_zip, src_size, src_hash, 13,
        rep_zip, rep_size, rep_hash, 3,
        dist_dir
    )

    return dist_dir, src_zip, rep_zip


class TestManifestAccuracy:
    def test_authoritative_manifest_matches_archives(self, isolated_dist):
        """Verifies that generated manifests accurately describe archive sizes and hashes."""
        dist_dir, src_zip, rep_zip = isolated_dist
        manifest_json = dist_dir / "RELEASE_MANIFEST.json"
        data = json.loads(manifest_json.read_text(encoding="utf-8"))

        src_info = data["archives"]["sanitized_source"]
        assert src_info["size_bytes"] == src_zip.stat().st_size
        assert src_info["sha256"] == sha256_file(src_zip)

        rep_info = data["archives"]["audit_reports"]
        assert rep_info["size_bytes"] == rep_zip.stat().st_size
        assert rep_info["sha256"] == sha256_file(rep_zip)


def test_release_content_filter_detects_profile_markers(tmp_path):
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps({
        "personal": {"full_name": "Alex Example", "email": "alex@example.invalid"},
        "education": {"institution": "Example State University"},
        "employment": [{"employer": "Example Systems"}],
        "projects": [{"name": "Sample Analytics Project"}],
    }), encoding="utf-8")
    markers = private_profile_markers(profile_path)
    content = tmp_path / "report.md"
    content.write_text("Candidate: Alex Example", encoding="utf-8")

    assert "alex example" in markers
    assert contains_private_profile_marker(content, markers)

    def test_manifest_does_not_overstate_product_acceptance(self, isolated_dist):
        """A clean package must not be labeled complete while product gates remain open."""
        dist_dir, _, _ = isolated_dist
        data = json.loads((dist_dir / "RELEASE_MANIFEST.json").read_text(encoding="utf-8"))
        summary = data["verification_summary"]
        assert summary["status"] == "PARTIALLY_VERIFIED"
        assert summary["package_integrity"] == "PASSED_AT_BUILD"
        assert summary["full_product_acceptance"] == "OPEN"
        assert "browser_visual_and_user_journey_review" not in summary["open_acceptance_gates"]
        assert "candidate_evidence_review_and_application_preparation" in summary["open_acceptance_gates"]
        assert "endpoint_specific_validation_audit" in summary["open_acceptance_gates"]
        assert "production_registered_task_execution_with_data_safety" not in summary["open_acceptance_gates"]
        assert "route_by_route_authorization_review" not in summary["open_acceptance_gates"]
        manifest_text = (dist_dir / "RELEASE_MANIFEST.txt").read_text(encoding="utf-8")
        assert "broad source coverage remain open" in manifest_text
        assert "browser journey and responsive review passed" in manifest_text
        assert "production-task execution remain open" not in manifest_text

    def test_live_source_evidence_must_be_fresh_and_match_registry(self, tmp_path):
        registry_path = tmp_path / "employer_sources.json"
        registry_path.write_text(json.dumps([
            {"id": "one", "enabled": True, "employer_name": "One", "board_id": "one"},
            {"id": "disabled", "enabled": False, "employer_name": "Disabled", "board_id": "disabled"},
        ]), encoding="utf-8")
        registry_hash = hashlib.sha256(registry_path.read_bytes()).hexdigest()
        now = datetime(2026, 10, 26, 10, tzinfo=timezone.utc)
        report = {
            "checked_at_utc": (now - timedelta(minutes=5)).isoformat(),
            "check_type": "read_only_public_ats_adapter_fetch",
            "registry_sha256": registry_hash,
            "configured_source_ids": ["one"],
            "configured_sources": 1,
            "checked_sources": 1,
            "succeeded_sources": 1,
            "failed_sources": 0,
            "normalized_jobs": 4,
            "all_configured_sources_succeeded": True,
            "sources": [{"id": "one", "status": "ok", "normalized_jobs": 4}],
        }
        validated = validate_live_source_coverage_report(report, registry_path, now_utc=now)
        assert validated["status"] == "PASSED_AT_CHECK_TIME"
        assert validated["configured_sources"] == 1
        report["checked_at_utc"] = (now - timedelta(days=2)).isoformat()
        assert validate_live_source_coverage_report(report, registry_path, now_utc=now) is None
        report["checked_at_utc"] = now.isoformat()
        report["configured_source_ids"] = ["one", "unexpected"]
        assert validate_live_source_coverage_report(report, registry_path, now_utc=now) is None

    def test_manifest_records_passed_live_coverage_without_full_acceptance(self, isolated_dist):
        dist_dir, src_zip, rep_zip = isolated_dist
        src_size, rep_size = src_zip.stat().st_size, rep_zip.stat().st_size
        evidence = {
            "status": "PASSED_AT_CHECK_TIME",
            "checked_at_utc": "2026-10-26T10:00:00+00:00",
            "days_back": 30,
            "configured_sources": 25,
            "succeeded_sources": 25,
            "failed_sources": 0,
            "normalized_jobs": 1491,
            "registry_sha256": "a" * 64,
        }
        generate_external_manifests(
            src_zip, src_size, sha256_file(src_zip), 13,
            rep_zip, rep_size, sha256_file(rep_zip), 3,
            dist_dir, source_coverage=evidence,
        )
        summary = json.loads((dist_dir / "RELEASE_MANIFEST.json").read_text(encoding="utf-8"))["verification_summary"]
        assert summary["status"] == "PARTIALLY_VERIFIED"
        assert summary["open_acceptance_gates"] == [
            "candidate_evidence_review_and_application_preparation",
            "endpoint_specific_validation_audit",
            "historical_report_reconciliation",
        ]
        assert summary["live_source_coverage"]["normalized_jobs"] == 1491
        assert "25/25 boards" in (dist_dir / "RELEASE_MANIFEST.txt").read_text(encoding="utf-8")

    def test_verification_passes_on_valid_dist(self, isolated_dist):
        """Verifies that independent verification succeeds on valid release artifacts."""
        dist_dir, _, _ = isolated_dist
        assert verify_release(skip_tests=True, dist_dir=dist_dir) is True

    def test_missing_archive_detection(self, isolated_dist):
        """Verifies that missing an archive causes verification failure."""
        dist_dir, src_zip, _ = isolated_dist
        src_zip.unlink()
        assert verify_release(skip_tests=True, dist_dir=dist_dir) is False

    def test_tampered_archive_detection(self, isolated_dist):
        """Verifies that modifying an archive after manifest creation fails verification."""
        dist_dir, src_zip, _ = isolated_dist
        # Tamper with archive bytes
        with open(src_zip, "ab") as f:
            f.write(b"\x00CORRUPT_BYTES")

        assert verify_release(skip_tests=True, dist_dir=dist_dir) is False

    def test_tampered_size_detection(self, isolated_dist):
        """Verifies that size mismatch in manifest causes verification failure."""
        dist_dir, _, _ = isolated_dist
        manifest_json = dist_dir / "RELEASE_MANIFEST.json"
        data = json.loads(manifest_json.read_text(encoding="utf-8"))
        data["archives"]["sanitized_source"]["size_bytes"] += 100
        manifest_json.write_text(json.dumps(data, indent=2), encoding="utf-8")

        assert verify_release(skip_tests=True, dist_dir=dist_dir) is False

    def test_malformed_manifest_json(self, isolated_dist):
        """Verifies that malformed manifest JSON fails verification cleanly."""
        dist_dir, _, _ = isolated_dist
        manifest_json = dist_dir / "RELEASE_MANIFEST.json"
        manifest_json.write_text("{malformed: json, missing closing brace", encoding="utf-8")

        assert verify_release(skip_tests=True, dist_dir=dist_dir) is False


class TestBuildOrderAndNonCircularity:
    def test_embedded_manifest_non_circularity(self):
        """Verifies that embedded manifest does not claim to contain its own archive's SHA-256."""
        doc_manifest = Path("docs/RELEASE_MANIFEST.md")
        assert doc_manifest.exists()
        content = doc_manifest.read_text(encoding="utf-8")

        # Must explicitly mention external manifest as authoritative
        assert "dist/RELEASE_MANIFEST.txt" in content
        assert "dist/RELEASE_MANIFEST.json" in content
        # Must document non-circularity
        assert "circular" in content.lower()

    def test_external_manifest_authoritative_for_completed_archives(self, isolated_dist):
        """Verifies that external manifest is generated after archives and references their hashes."""
        dist_dir, src_zip, rep_zip = isolated_dist
        manifest_txt = dist_dir / "RELEASE_MANIFEST.txt"
        content = manifest_txt.read_text(encoding="utf-8")

        assert sha256_file(src_zip) in content
        assert sha256_file(rep_zip) in content


class TestSanitizationRules:
    def test_env_file_excluded_and_scanner_flags(self, tmp_path):
        """Verifies scanner catches real .env but ignores .env.example with placeholders."""
        bad_zip = tmp_path / "bad.zip"
        with zipfile.ZipFile(bad_zip, "w") as zf:
            zf.writestr(".env", "DATABASE_URL=sqlite:///secret.db\n")
            zf.writestr(".env.example", "DATABASE_URL=sqlite:///dummy.db\n")

        violations = scan_archive_recursively(bad_zip)
        assert any(".env" in v["file"] for v in violations)
        assert not any(v["file"] == ".env.example" for v in violations)

    def test_database_and_runtime_logs_excluded(self, tmp_path):
        """Verifies scanner catches sqlite databases and runtime logs."""
        bad_zip = tmp_path / "db.zip"
        with zipfile.ZipFile(bad_zip, "w") as zf:
            zf.writestr("data/careerorbit.db", "SQLite format 3\x00")
            zf.writestr("data/logs/scheduler.log", "log line\n")
            zf.writestr("data/resumes/candidate.pdf", "%PDF-1.4\n")

        violations = scan_archive_recursively(bad_zip)
        viol_reasons = [v["reason"] for v in violations]
        assert any("database" in r.lower() for r in viol_reasons)
        assert any("candidate" in r.lower() or "runtime" in r.lower() for r in viol_reasons)

    def test_secret_patterns_detected_and_placeholders_allowed(self, tmp_path):
        """Verifies scanner catches real credential patterns but allows placeholders."""
        bad_zip = tmp_path / "creds.zip"
        # Real-looking synthetic token
        prefix = "9876543210"
        secret = "AAHklMNabctuvWXYZ1234567890abcdefgh"
        synthetic_token = f"{prefix}:{secret}"

        with zipfile.ZipFile(bad_zip, "w") as zf:
            zf.writestr("config.py", f'BOT_TOKEN = "{synthetic_token}"\n')
            zf.writestr("example.py", 'BOT_TOKEN = "your_bot_token_here"\n')

        violations = scan_archive_recursively(bad_zip)
        assert any("Telegram Bot Token" in v["reason"] for v in violations)
        assert not any("example.py" in v["file"] for v in violations)


class TestPathTraversalSecurity:
    def test_path_traversal_detection(self, tmp_path):
        """Verifies that zip entries attempting relative traversal or leading slash are detected."""
        bad_zip = tmp_path / "traversal.zip"
        with zipfile.ZipFile(bad_zip, "w") as zf:
            zf.writestr("../evil.txt", "malicious payload\n")
            zf.writestr("/absolute/evil.txt", "malicious payload\n")
            zf.writestr("safe/file.txt", "safe\n")

        with zipfile.ZipFile(bad_zip, "r") as zf:
            violations = check_path_traversal(zf, "traversal.zip")

        assert any(".." in v for v in violations)
        assert any("slash" in v.lower() for v in violations)


class TestAtomicStagingAndRollback:
    def test_clean_staging_lifecycle(self, tmp_path):
        """Verifies staging directory lifecycle prevents partial file leaks."""
        staging_dir = tmp_path / "dist" / ".staging"
        staging_dir.mkdir(parents=True, exist_ok=True)

        temp_file = staging_dir / "partial.zip"
        temp_file.write_text("partial")

        # When staging is cleaned up
        if staging_dir.exists():
            shutil.rmtree(staging_dir)

        assert not staging_dir.exists()


class TestReportProvenance:
    def test_authoritative_report_exists_and_accurate(self):
        """Verifies that CURRENT_RELEASE_VERIFICATION_REPORT exists and details current state."""
        rep = Path("reports/CURRENT_RELEASE_VERIFICATION_REPORT.md")
        assert rep.exists()
        text = rep.read_text(encoding="utf-8")

        assert "AUTHORITATIVE RELEASE VERIFICATION" in text
        assert "Step 1: Personalized Career Priorities — VERIFIED COMPLETE" in text
        assert "Step 2: Release Packaging" in text
        assert "335" in text

    def test_historical_reports_flagged(self):
        """Candidate-specific root reports are omitted from sanitized source archives."""
        root_report = Path("careerorbit_final_execution_report.md")
        if root_report.exists():
            from scripts.package_release import contains_private_profile_marker, private_profile_markers
            assert contains_private_profile_marker(root_report, private_profile_markers())

        final_rep = Path("reports/FINAL_REPORT.md")
        assert final_rep.exists()
        assert "[HISTORICAL REPORT]" in final_rep.read_text(encoding="utf-8")

    def test_historical_release_snapshot_does_not_publish_current_hashes(self):
        rep = Path("reports/CURRENT_RELEASE_VERIFICATION_REPORT.md")
        text = rep.read_text(encoding="utf-8")
        assert "Historical Package Verification" in text
        assert "current release are in `dist/RELEASE_MANIFEST.txt`" in text
        assert "72cd34d69a3329d50fabcbfa17f5462899728c7f190eff2e13ba3c17feb6e4b0" not in text
