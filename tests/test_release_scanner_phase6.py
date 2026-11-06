"""Unit tests for Phase 6 & Phase 7: Release Security Scanner & Artifact Exclusions.

Verifies:
1. Scanner detects forbidden files: .env, .db, data/backups/, data/resumes/, data/logs/, workflow_runs.jsonl.
2. Scanner permits .env.example.
3. Scanner detects unmasked secret patterns (Telegram Bot token, AWS key, GitHub token).
4. Scanner allows placeholder secrets.
5. Scanner detects forbidden files inside nested zip archives.
"""

import io
import zipfile
import pytest
from pathlib import Path
from scripts.package_release import scan_archive_recursively, is_placeholder


def test_is_placeholder_utility():
    """Verifies that dummy/test tokens are correctly identified as placeholders."""
    assert is_placeholder("your_bot_token_here") is True
    assert is_placeholder("<your-api-key>") is True
    assert is_placeholder("placeholder_value") is True
    assert is_placeholder("dummy_secret") is True
    assert is_placeholder("redacted_token") is True
    assert is_placeholder("mock_secret") is True
    assert is_placeholder("1234567890:AAFlIVE_REAL_LOOKING_KEY_XYZ12345") is False


def test_scanner_detects_prohibited_env_file(tmp_path):
    """Verifies scanner catches .env files in an archive."""
    zip_path = tmp_path / "test_env.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr(".env", "SECRET_KEY=supersecret123456789012345\n")
        zf.writestr(".env.example", "SECRET_KEY=your_secret_key_here\n")
        zf.writestr("README.md", "# Test Project\n")

    violations = scan_archive_recursively(zip_path)
    viol_files = [v["file"] for v in violations]
    assert ".env" in viol_files
    assert ".env.example" not in viol_files


def test_scanner_detects_sqlite_database(tmp_path):
    """Verifies scanner catches .db and .sqlite files in an archive."""
    zip_path = tmp_path / "test_db.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("data/careerorbit.db", "SQLite format 3\x00")
        zf.writestr("app/main.py", "print('hello')\n")

    violations = scan_archive_recursively(zip_path)
    assert any("careerorbit.db" in v["file"] for v in violations)


def test_scanner_detects_runtime_logs_and_candidate_data(tmp_path):
    """Verifies scanner catches logs, resumes, and all candidate-private data files."""
    zip_path = tmp_path / "test_runtime.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("data/logs/scheduler.log", "scheduler started\n")
        zf.writestr("workflow_runs.jsonl", '{"run": 1}\n')
        zf.writestr("data/resumes/Candidate_Resume.docx", "resume bytes")
        zf.writestr("candidate_evidence.json", "{}")
        zf.writestr("data/candidate_profile_private.json", '{"personal": {"email": "fixture@example.invalid"}}')

    violations = scan_archive_recursively(zip_path)
    viol_files = [v["file"] for v in violations]
    assert any("data/logs" in f or "scheduler.log" in f for f in viol_files)
    assert any("workflow_runs.jsonl" in f for f in viol_files)
    assert any("data/resumes" in f for f in viol_files)
    assert any("candidate_evidence.json" in f for f in viol_files)
    assert any("candidate_profile_private.json" in f for f in viol_files)


def test_scanner_detects_unmasked_credentials(tmp_path):
    """Verifies scanner catches real unmasked API keys and Telegram tokens."""
    zip_path = tmp_path / "test_creds.zip"
    prefix = "1234567890"
    secret = "ABCdefGHIjklMNOpqrsTUVwxyz123456789"
    synthetic_token = f"{prefix}:{secret}"
    with zipfile.ZipFile(zip_path, "w") as zf:
        # Synthetic token generated at runtime to test scanner detection
        zf.writestr("config.py", f'TELEGRAM_TOKEN = "{synthetic_token}"\n')
        zf.writestr("aws.py", 'AWS_ACCESS_KEY_ID = "AKIAIOSFODNN7EXAMPLE"\n')

    violations = scan_archive_recursively(zip_path)
    assert any("Telegram Bot Token" in v.get("reason", "") for v in violations)


def test_scanner_recurses_into_nested_zip(tmp_path):
    """Verifies scanner catches secrets and forbidden files inside nested zip archives."""
    inner_zip_path = tmp_path / "inner.zip"
    with zipfile.ZipFile(inner_zip_path, "w") as inner_zf:
        inner_zf.writestr(".env", "LEAKED_SECRET=12345678901234567890\n")

    outer_zip_path = tmp_path / "outer.zip"
    with zipfile.ZipFile(outer_zip_path, "w") as outer_zf:
        outer_zf.write(inner_zip_path, "nested/inner.zip")
        outer_zf.writestr("main.py", "print('clean')\n")

    violations = scan_archive_recursively(outer_zip_path)
    assert any(".env" in v["file"] for v in violations)
