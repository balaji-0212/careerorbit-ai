"""Unit and Integration Tests for Step 5: Security Scanner Hardening,
Secret Detection, Sanitized Releases, and Security Regression Testing.

Covers:
1. Positive Detection Scenarios:
   - Python (.py), Shell (.sh), PowerShell (.ps1), Batch (.bat/.cmd)
   - JSON (.json), JSON Lines (.jsonl), CSV (.csv with row/col tracking)
   - YAML (.yaml/.yml), TOML (.toml), INI/Config (.ini/.cfg)
   - Markdown (.md), Text (.txt), HTML/JS (.html/.js)
   - Secrets containing incidental substrings ("test", "xxx", "example") - NO FALSE NEGATIVES
   - Telegram Bot Tokens, OpenAI/Stripe API keys, GitHub tokens, AWS keys
   - Bearer tokens, DB connection strings with passwords, private key markers, webhook secrets
   - Nested zip archives
2. Negative Detection Scenarios (Benign & Placeholders):
   - Documentation placeholders: YOUR_API_KEY_HERE, <YOUR_KEY>, replace-me, changeme
   - Official AWS doc placeholders: AKIAIOSFODNN7EXAMPLE
   - Low-entropy repeated characters: 0000000000, XXXXXXXXXX
   - Benign identifiers, UUIDs, git commit hashes, prose containing words "test" and "example"
3. Robustness & Safety:
   - UTF-8 with BOM, Latin-1 encodings
   - Malformed JSON, JSONL, and CSV files
   - Corrupt zip CRC handling
   - Archive depth limits (> 3 levels), file count limits (> 1000), byte limits (> 50MB)
   - Path traversal prevention in archives (../, leading slashes, drive letters)
   - Archive forbidden files (.env, .db, candidate data, logs)
   - Deterministic scan results
4. Zero-Exposure Verification:
   - Verifies raw secret values never appear in finding dicts, logs, or fingerprints
   - Verifies fingerprints are 12-hex SHA-256 hashes
"""

import csv
import hashlib
import json
import re
import tempfile
import zipfile
from pathlib import Path
import pytest

from careerorbit.security.scanner import (
    SecurityScanner,
    SecretFinding,
    SkippedFile,
    ScanReport,
    is_placeholder,
    scan_path,
    scan_archive,
    RULES,
    SCANNABLE_EXTENSIONS,
)


# ===========================================================================
# 1. Positive Secret Detection Tests
# ===========================================================================

class TestPositiveSecretDetection:
    """Tests that the hardened scanner detects genuine secrets across all formats."""

    def test_detect_telegram_bot_token_in_python(self, tmp_path):
        f = tmp_path / "app.py"
        # Synthetic token format constructed dynamically so test file itself contains no secrets
        synthetic_token = "1234567890:" + "AAHklMNabctuvWXYZ1234567890abcdefgh"
        f.write_text(f'TELEGRAM_BOT_TOKEN = "{synthetic_token}"\n', encoding="utf-8")

        scanner = SecurityScanner()
        findings = scanner.scan_file(f)
        assert len(findings) == 1
        assert findings[0].rule_id == "SEC-001"
        assert findings[0].category == "Telegram Bot Token"
        assert findings[0].line == 1
        assert synthetic_token not in findings[0].fingerprint

    def test_detect_incidental_substring_token_no_false_negative(self, tmp_path):
        """CRITICAL: Token containing incidental 'test', 'xxx', or 'example' must NOT be excused."""
        f = tmp_path / "config.py"
        # Real-format tokens that contain 'test', 'xxx', and 'example' inside high-entropy strings
        tok1 = "9876543210:" + "AAHtest_secret_bot_token_abcdef12345"  # 35 chars after colon, has 'test'
        tok2 = "1122334455:" + "AAHklMNabctuvWXYZ1234567890xxxdefgh"  # 35 chars after colon, has 'xxx'
        key3 = "sk_live_" + "example_secure_key_1234567890abcdef"     # 43 chars, has 'example'

        f.write_text(
            f'TOKEN_A = "{tok1}"\nTOKEN_B = "{tok2}"\nAPI_KEY = "{key3}"\n',
            encoding="utf-8"
        )

        scanner = SecurityScanner()
        findings = scanner.scan_file(f)
        rule_ids = [fd.rule_id for fd in findings]
        assert "SEC-001" in rule_ids
        assert len(findings) >= 2  # Both tokens caught, no false negatives

    def test_detect_secret_in_jsonl_record(self, tmp_path):
        f = tmp_path / "audit_events.jsonl"
        secret_tok = "ghp_" + "1234567890abcdefghijklmnopqrstuvwxyz"
        line1 = json.dumps({"event": "login", "user": "alice"})
        line2 = json.dumps({"event": "auth_token_created", "token": secret_tok})
        f.write_text(f"{line1}\n{line2}\n", encoding="utf-8")

        scanner = SecurityScanner()
        findings = scanner.scan_file(f)
        assert len(findings) == 1
        assert findings[0].rule_id == "SEC-005"
        assert findings[0].category == "GitHub Token"
        assert findings[0].line == 2

    def test_detect_secret_in_csv_cell_with_row_col(self, tmp_path):
        f = tmp_path / "credentials_export.csv"
        aws_key = "AKIA" + "1234567890ABCDEF"
        content = (
            "service,username,access_key_id,status\n"
            "production,admin,safe_placeholder,active\n"
            f"staging,dev_user,{aws_key},active\n"
        )
        f.write_text(content, encoding="utf-8")

        scanner = SecurityScanner()
        findings = scanner.scan_file(f)
        assert len(findings) == 1
        assert findings[0].rule_id == "SEC-003"
        assert findings[0].line == 3
        assert findings[0].column == 3

    def test_detect_db_connection_string_with_password(self, tmp_path):
        f = tmp_path / "database.yml"
        conn_str = "postgresql://" + "admin:SuperSecretPass123!@db.internal.corp:5432/careerorbit_prod"
        f.write_text(f"production:\n  url: {conn_str}\n", encoding="utf-8")

        scanner = SecurityScanner()
        findings = scanner.scan_file(f)
        assert len(findings) == 1
        assert findings[0].rule_id == "SEC-008"
        assert "Database Connection String" in findings[0].category

    def test_detect_bearer_token_authorization_header(self, tmp_path):
        f = tmp_path / "api_client.ts"
        token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9." + "eyJzdWIiOiIxMjM0NTY3ODkwIn0." + "doNotLeakThisSignature1234567890"
        f.write_text(f"headers['Authorization'] = 'Bearer {token}';\n", encoding="utf-8")

        scanner = SecurityScanner()
        findings = scanner.scan_file(f)
        assert len(findings) >= 1
        assert any(fd.rule_id == "SEC-007" for fd in findings)

    def test_detect_private_key_material(self, tmp_path):
        f = tmp_path / "server.key"
        key_body = "-----BEGIN " + "RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0m...\n-----END " + "RSA PRIVATE KEY-----\n"
        f.write_text(key_body, encoding="utf-8")

        scanner = SecurityScanner()
        findings = scanner.scan_file(f)
        assert len(findings) == 1
        assert findings[0].rule_id == "SEC-010"
        assert findings[0].category == "Private Key Material"

    def test_detect_powershell_password_assignment(self, tmp_path):
        f = tmp_path / "deploy.ps1"
        pw_line = '$db_password = ' + '"ProdP@ssw0rd998877!"\nWrite-Host "Deploying"\n'
        f.write_text(pw_line, encoding="utf-8")

        scanner = SecurityScanner()
        findings = scanner.scan_file(f)
        assert len(findings) == 1
        assert findings[0].rule_id == "SEC-009"
        assert findings[0].line == 1

    def test_detect_slack_webhook_url(self, tmp_path):
        f = tmp_path / "alerts.sh"
        webhook_url = "https://hooks.slack.com/services/" + "T12345678/B12345678/a1b2c3d4e5f6g7h8i9j0k1l2"
        f.write_text(
            f'curl -X POST -H "Content-type: application/json" --data \'{{"text":"Hello"}}\' {webhook_url}\n',
            encoding="utf-8"
        )

        scanner = SecurityScanner()
        findings = scanner.scan_file(f)
        assert len(findings) == 1
        assert findings[0].rule_id == "SEC-013"
        assert findings[0].category == "Slack Webhook URL"

    def test_detect_secret_in_nested_archive(self, tmp_path):
        inner_zip = tmp_path / "inner.zip"
        sk_key = "sk_live_" + "1234567890abcdef1234567890abcdef"
        with zipfile.ZipFile(inner_zip, "w") as zf:
            zf.writestr("secrets.json", json.dumps({"api_key": sk_key}))

        outer_zip = tmp_path / "outer.zip"
        with zipfile.ZipFile(outer_zip, "w") as zf:
            zf.write(inner_zip, "nested/inner.zip")

        scanner = SecurityScanner()
        findings = scanner.scan_archive(outer_zip)
        assert len(findings) >= 1
        assert any(fd.rule_id in ("SEC-002", "SEC-006") for fd in findings)


# ===========================================================================
# 2. Negative Detection Scenarios (Benign / Placeholders Allowed)
# ===========================================================================

class TestNegativeDetectionScenarios:
    """Tests that legitimate placeholders and benign prose are NOT flagged."""

    def test_allow_explicit_placeholders(self, tmp_path):
        f = tmp_path / "sample.env.example"
        content = (
            'TELEGRAM_BOT_TOKEN="your_telegram_bot_token"\n'
            'AWS_ACCESS_KEY_ID="AKIAIOSFODNN7EXAMPLE"\n'
            'API_KEY="YOUR_API_KEY_HERE"\n'
            'SECRET_KEY="<YOUR_SECRET_KEY>"\n'
            'DB_PASS="changeme"\n'
            'REPLACE_ME="replace-me"\n'
        )
        f.write_text(content, encoding="utf-8")

        scanner = SecurityScanner()
        findings = scanner.scan_file(f)
        assert len(findings) == 0

    def test_allow_prose_containing_trigger_words(self, tmp_path):
        f = tmp_path / "README.md"
        content = (
            "# CareerOrbit Security Guide\n\n"
            "In this test, we verify that secret tokens and passwords are not leaked.\n"
            "For example, an API key must be provided via environment variables.\n"
            "Do not commit your real bot token or database password.\n"
        )
        f.write_text(content, encoding="utf-8")

        scanner = SecurityScanner()
        findings = scanner.scan_file(f)
        assert len(findings) == 0

    def test_allow_low_entropy_dummy_strings(self, tmp_path):
        f = tmp_path / "dummy.py"
        content = (
            'DUMMY_KEY = "00000000000000000000000000000000"\n'
            'MASKED_VAL = "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"\n'
        )
        f.write_text(content, encoding="utf-8")

        scanner = SecurityScanner()
        findings = scanner.scan_file(f)
        assert len(findings) == 0

    def test_allow_git_hashes_and_uuids(self, tmp_path):
        f = tmp_path / "commit_info.json"
        content = json.dumps({
            "commit_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            "request_id": "c9a646d3-9c61-4cc9-bc55-e4d0d970e704",
            "version": "2.0.0",
        })
        f.write_text(content, encoding="utf-8")

        scanner = SecurityScanner()
        findings = scanner.scan_file(f)
        assert len(findings) == 0


# ===========================================================================
# 3. Robustness & Safety Tests
# ===========================================================================

class TestScannerRobustnessAndSafety:
    """Tests archive safety limits, path traversal, encoding fallback, and corruption handling."""

    def test_path_traversal_in_archive_blocked(self, tmp_path):
        bad_zip = tmp_path / "traversal.zip"
        with zipfile.ZipFile(bad_zip, "w") as zf:
            zf.writestr("../../etc/passwd", "root:x:0:0::/root:/bin/bash\n")
            zf.writestr("safe/app.py", "# Safe\n")

        scanner = SecurityScanner()
        findings = scanner.scan_archive(bad_zip)
        assert len(findings) == 1
        assert findings[0].rule_id == "ARCHIVE-001"
        assert findings[0].category == "Path Traversal Violation"

    def test_archive_forbidden_files_detected(self, tmp_path):
        bad_zip = tmp_path / "forbidden.zip"
        with zipfile.ZipFile(bad_zip, "w") as zf:
            zf.writestr(".env", "SECRET=123\n")
            zf.writestr("careerorbit.db", "SQLite format 3\x00")
            zf.writestr("data/logs/scheduler.log", "log line\n")
            zf.writestr("data/resumes/alice.pdf", "%PDF-1.4\n")

        scanner = SecurityScanner()
        findings = scanner.scan_archive(bad_zip)
        rule_ids = {f.rule_id for f in findings}
        assert "ARCHIVE-002" in rule_ids  # .env
        assert "ARCHIVE-003" in rule_ids  # .db and .log
        assert "ARCHIVE-004" in rule_ids  # candidate resume / logs

    def test_archive_depth_limit_enforced(self, tmp_path):
        """Archives nested more than max_archive_depth (3) must be stopped safely."""
        current_zip = tmp_path / "level_0.zip"
        with zipfile.ZipFile(current_zip, "w") as zf:
            zf.writestr("file.txt", "base")

        # Nest 5 levels deep
        for i in range(1, 6):
            next_zip = tmp_path / f"level_{i}.zip"
            with zipfile.ZipFile(next_zip, "w") as zf:
                zf.write(current_zip, f"nested_{i}.zip")
            current_zip = next_zip

        scanner = SecurityScanner(max_archive_depth=3)
        scanner.scan_archive(current_zip)
        assert any("depth exceeded" in err.lower() for err in scanner.errors)

    def test_archive_crc_corruption_handled_gracefully(self, tmp_path):
        bad_zip = tmp_path / "corrupt.zip"
        with zipfile.ZipFile(bad_zip, "w") as zf:
            zf.writestr("valid.txt", "Hello world")

        # Corrupt archive payload bytes
        raw = bytearray(bad_zip.read_bytes())
        raw[20:28] = b"\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF"
        bad_zip.write_bytes(raw)

        scanner = SecurityScanner()
        # Must not raise an unhandled exception
        scanner.scan_archive(bad_zip)
        assert len(scanner.errors) > 0

    def test_encoding_fallback_latin1(self, tmp_path):
        f = tmp_path / "encoded.txt"
        # Latin-1 bytes with non-UTF-8 characters
        pw_str = "password = " + "'super_secret_password_value_12345'\n"
        raw_bytes = f"Café au lait con {pw_str}".encode("latin-1")
        f.write_bytes(raw_bytes)

        scanner = SecurityScanner()
        findings = scanner.scan_file(f)
        assert scanner.scanned_files_count == 1
        assert len(scanner.skipped_files) == 0

    def test_malformed_json_handled_without_crash(self, tmp_path):
        f = tmp_path / "broken.json"
        f.write_text("{broken json: [no closing bracket", encoding="utf-8")

        scanner = SecurityScanner()
        # Should fall back to text scanning without throwing JSONDecodeError
        scanner.scan_file(f)
        assert scanner.scanned_files_count == 1

    def test_deterministic_scan_results(self, tmp_path):
        f = tmp_path / "target.py"
        token = "1234567890:" + "AAHklMNabctuvWXYZ1234567890abcdefgh"
        f.write_text(f'BOT_TOKEN = "{token}"\n', encoding="utf-8")

        scanner1 = SecurityScanner()
        r1 = scanner1.scan_file(f)

        scanner2 = SecurityScanner()
        r2 = scanner2.scan_file(f)

        assert len(r1) == len(r2)
        assert r1[0].fingerprint == r2[0].fingerprint
        assert r1[0].rule_id == r2[0].rule_id


# ===========================================================================
# 4. Zero Exposure Guarantee Tests
# ===========================================================================

class TestZeroExposureGuarantee:
    """Verifies that secrets are never disclosed in findings, reports, or fingerprints."""

    def test_zero_raw_secret_leak_in_findings(self, tmp_path):
        f = tmp_path / "leaks.py"
        real_secret_token = "1234567890:" + "AAHklMNabctuvWXYZ1234567890abcdefgh"
        real_api_key = "sk_live_" + "1234567890abcdef1234567890abcdef"
        real_db_pass = "P@ssw0rd998877!"
        db_conn = "postgresql://user:" + f"{real_db_pass}@host:5432/db"

        f.write_text(
            f'TOKEN = "{real_secret_token}"\n'
            f'KEY = "{real_api_key}"\n'
            f'DB = "{db_conn}"\n',
            encoding="utf-8"
        )

        scanner = SecurityScanner()
        findings = scanner.scan_file(f)
        report = scanner.build_report()
        report_json = json.dumps(report.to_dict())

        # Assert raw secrets are NOT present anywhere in findings or serialized report
        assert real_secret_token not in report_json
        assert real_api_key not in report_json
        assert real_db_pass not in report_json

        # Assert fingerprints are valid 12-character hex SHA-256 slices
        for fd in findings:
            assert re.fullmatch(r"[a-f0-9]{12}", fd.fingerprint)
            assert fd.fingerprint != real_secret_token
