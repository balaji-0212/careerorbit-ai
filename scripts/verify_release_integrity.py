"""Independent Release Integrity Verification for CareerOrbit AI.

Verifies:
1. Presence of release archives and external manifests in dist/.
2. Exact byte size and SHA-256 hash match against authoritative manifest.
3. Zip CRC archive integrity via testzip().
4. Path traversal safety (blocks directory escape attacks).
5. Fresh temporary extraction and inspection.
6. Strict sanitization verification (confirms zero .env, zero databases, zero resumes, zero logs).
7. Required project files completeness.
8. Hermetic pytest execution against the extracted source package.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DIST_DIR = ROOT_DIR / "dist"

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    from scripts.package_release import PATTERNS, is_placeholder, private_profile_markers
except ImportError:
    from package_release import PATTERNS, is_placeholder, private_profile_markers

from careerorbit.security.scanner import SecurityScanner

PROHIBITED_SUBSTRINGS = [
    "data/resumes",
    "data/backups",
    "data/logs",
    "data/audit",
    "workflow_runs.jsonl",
    "candidate_evidence.json",
    "candidate_evidence_documents.json",
    "evidence_documents",
    "candidate_profile_history.jsonl",
    "candidate_profile_overrides.json",
    "candidate_profile_private.json",
    "scheduler.log",
    "scheduler_lock.json",
    ".git/",
    ".venv/",
]

PROHIBITED_EXTS = [
    ".db", ".sqlite", ".sqlite3", ".db-shm", ".db-wal", ".log", ".lock", ".pid", ".pyc"
]

REQUIRED_SOURCE_FILES = [
    "careerorbit/__init__.py",
    "careerorbit/web/app.py",
    "careerorbit/career_priorities.py",
    "careerorbit/eligibility.py",
    "careerorbit/matcher/scorer.py",
    "careerorbit/database/db.py",
    "careerorbit/config/settings.py",
    "careerorbit/security/__init__.py",
    "careerorbit/security/scanner.py",
    "tests/conftest.py",
    "README.md",
    ".env.example",
    "docs/RELEASE_MANIFEST.md",
]

REQUIRED_REPORT_FILES = [
    "docs/RELEASE_MANIFEST.md",
    "reports/SECURITY_SCAN_REPORT.json",
    "reports/CURRENT_RELEASE_VERIFICATION_REPORT.md",
]


def sha256_file(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def check_path_traversal(zf: zipfile.ZipFile, archive_name: str) -> list:
    """Ensure no entries in the zip file attempt directory traversal."""
    violations = []
    for info in zf.infolist():
        fn = info.filename
        fn_norm = fn.replace("\\", "/")
        if fn_norm.startswith("/") or fn_norm.startswith("\\"):
            violations.append(f"Leading slash in entry: {fn}")
        if ":" in fn_norm.split("/")[0]:
            violations.append(f"Drive letter in entry: {fn}")
        parts = fn_norm.split("/")
        if ".." in parts:
            violations.append(f"Relative traversal '..' in entry: {fn}")
    return violations


def verify_sanitization(extracted_dir: Path) -> list:
    """Verify that extracted source directory contains 0 forbidden files."""
    violations = []

    for root, dirs, files in os.walk(extracted_dir):
        rel_root = str(Path(root).relative_to(extracted_dir)).replace("\\", "/")

        for file in files:
            rel_file = f"{rel_root}/{file}" if rel_root != "." else file
            fn_lower = rel_file.lower()

            # Check .env
            if fn_lower == ".env" or fn_lower.endswith("/.env") or "/.env." in fn_lower or fn_lower.startswith(".env"):
                if not fn_lower.endswith(".env.example"):
                    violations.append(f"Forbidden environment file found: {rel_file}")

            # Check db & logs
            if any(fn_lower.endswith(ext) for ext in PROHIBITED_EXTS):
                violations.append(f"Forbidden database/log/cache file found: {rel_file}")

            # Check candidate data
            if any(sub in fn_lower for sub in PROHIBITED_SUBSTRINGS):
                violations.append(f"Forbidden candidate data/history file found: {rel_file}")

    return violations


def verify_release(skip_tests: bool = False, dist_dir: Path = None) -> bool:
    """Perform independent verification of release artifacts."""
    if dist_dir is None:
        dist_dir = DIST_DIR

    print("=" * 80)
    print("INDEPENDENT RELEASE INTEGRITY & EXTRACTION VERIFICATION")
    print("=" * 80)

    # 1. Verify existence of manifests and archives
    manifest_txt = dist_dir / "RELEASE_MANIFEST.txt"
    manifest_json = dist_dir / "RELEASE_MANIFEST.json"
    src_zip = dist_dir / "CareerOrbit_AI_Sanitized_Source.zip"
    rep_zip = dist_dir / "CareerOrbit_AI_Audit_Reports.zip"

    missing = []
    for f in [manifest_txt, manifest_json, src_zip, rep_zip]:
        if not f.exists():
            missing.append(f.name)

    if missing:
        print(f"[FAIL] Missing required release artifact(s): {', '.join(missing)}")
        return False

    print("[PASS] All release artifacts present in dist/ directory.")

    # 2. Parse JSON manifest
    try:
        manifest_data = json.loads(manifest_json.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[FAIL] Could not parse RELEASE_MANIFEST.json: {e}")
        return False

    print(f"[PASS] Parsed {manifest_json.name} successfully.")
    print(f"       Release: {manifest_data.get('release')} {manifest_data.get('version')}")
    print(f"       Built at: {manifest_data.get('build_timestamp_utc')}")

    # 3. Recalculate and compare byte sizes and SHA-256 hashes
    archives_spec = manifest_data.get("archives", {})
    src_spec = archives_spec.get("sanitized_source", {})
    rep_spec = archives_spec.get("audit_reports", {})

    # Check source archive
    actual_src_size = src_zip.stat().st_size
    actual_src_hash = sha256_file(src_zip)
    expected_src_size = src_spec.get("size_bytes")
    expected_src_hash = src_spec.get("sha256")

    print(f"\nVerifying {src_zip.name}...")
    print(f"  Actual Size:   {actual_src_size:,} bytes")
    print(f"  Expected Size: {expected_src_size:,} bytes")
    if actual_src_size != expected_src_size:
        print(f"[FAIL] Size mismatch on {src_zip.name}: expected {expected_src_size}, got {actual_src_size}")
        return False

    print(f"  Actual SHA256:   {actual_src_hash}")
    print(f"  Expected SHA256: {expected_src_hash}")
    if actual_src_hash.lower() != expected_src_hash.lower():
        print(f"[FAIL] Hash mismatch on {src_zip.name}")
        return False
    print(f"[PASS] {src_zip.name} checksum and size match authoritative manifest.")

    # Check reports archive
    actual_rep_size = rep_zip.stat().st_size
    actual_rep_hash = sha256_file(rep_zip)
    expected_rep_size = rep_spec.get("size_bytes")
    expected_rep_hash = rep_spec.get("sha256")

    print(f"\nVerifying {rep_zip.name}...")
    print(f"  Actual Size:   {actual_rep_size:,} bytes")
    print(f"  Expected Size: {expected_rep_size:,} bytes")
    if actual_rep_size != expected_rep_size:
        print(f"[FAIL] Size mismatch on {rep_zip.name}: expected {expected_rep_size}, got {actual_rep_size}")
        return False

    print(f"  Actual SHA256:   {actual_rep_hash}")
    print(f"  Expected SHA256: {expected_rep_hash}")
    if actual_rep_hash.lower() != expected_rep_hash.lower():
        print(f"[FAIL] Hash mismatch on {rep_zip.name}")
        return False
    print(f"[PASS] {rep_zip.name} checksum and size match authoritative manifest.")

    # 4. CRC and path traversal safety checks
    print("\nRunning CRC integrity (testzip) and path traversal checks...")
    with zipfile.ZipFile(src_zip, "r") as zf:
        bad_crc = zf.testzip()
        if bad_crc:
            print(f"[FAIL] Corrupt entry in {src_zip.name}: {bad_crc}")
            return False
        traversals = check_path_traversal(zf, src_zip.name)
        if traversals:
            print(f"[FAIL] Path traversal violations in {src_zip.name}: {traversals}")
            return False
        markers = private_profile_markers()
        if any(
            marker.encode("utf-8") in zf.read(info).lower()
            for info in zf.infolist()
            if not info.is_dir()
            for marker in markers
        ):
            print("[FAIL] Candidate-identifying profile data found in sanitized source archive.")
            return False

    with zipfile.ZipFile(rep_zip, "r") as zf:
        bad_crc = zf.testzip()
        if bad_crc:
            print(f"[FAIL] Corrupt entry in {rep_zip.name}: {bad_crc}")
            return False
        traversals = check_path_traversal(zf, rep_zip.name)
        if traversals:
            print(f"[FAIL] Path traversal violations in {rep_zip.name}: {traversals}")
            return False
        markers = private_profile_markers()
        if any(
            marker.encode("utf-8") in zf.read(info).lower()
            for info in zf.infolist()
            if not info.is_dir()
            for marker in markers
        ):
            print("[FAIL] Candidate-identifying profile data found in audit reports archive.")
            return False
    print("[PASS] Both archives passed CRC integrity and path traversal safety checks.")

    # 5. Extract to temporary directory and inspect contents
    print("\nExtracting archives to temporary directory for content validation...")
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        src_extract = tmp_path / "source"
        rep_extract = tmp_path / "reports"

        with zipfile.ZipFile(src_zip, "r") as zf:
            zf.extractall(src_extract)
        with zipfile.ZipFile(rep_zip, "r") as zf:
            zf.extractall(rep_extract)

        # Sanitization check
        src_violations = verify_sanitization(src_extract)
        if src_violations:
            print(f"[FAIL] Sanitization violations detected in extracted source:")
            for v in src_violations:
                print(f"  - {v}")
            return False
        print("[PASS] Sanitized source contains 0 forbidden files (.env, .db, resumes, logs excluded).")

        rep_violations = verify_sanitization(rep_extract)
        if rep_violations:
            print(f"[FAIL] Sanitization violations detected in extracted reports:")
            for v in rep_violations:
                print(f"  - {v}")
            return False
        print("[PASS] Reports archive contains 0 forbidden files.")

        # Required source files check
        missing_src_files = []
        for req in REQUIRED_SOURCE_FILES:
            if not (src_extract / req).exists():
                missing_src_files.append(req)

        if missing_src_files:
            print(f"[FAIL] Extracted source missing required files: {missing_src_files}")
            return False
        print(f"[PASS] All {len(REQUIRED_SOURCE_FILES)} required source files verified present.")

        # Required reports files check
        missing_rep_files = []
        for req in REQUIRED_REPORT_FILES:
            if not (rep_extract / req).exists():
                missing_rep_files.append(req)

        if missing_rep_files:
            print(f"[FAIL] Extracted reports missing required files: {missing_rep_files}")
            return False
        print(f"[PASS] All {len(REQUIRED_REPORT_FILES)} required report files verified present.")

        # Check placeholder in .env.example
        env_example_path = src_extract / ".env.example"
        if env_example_path.exists():
            content = env_example_path.read_text(encoding="utf-8")
            leak = False
            for line in content.splitlines():
                for regex, kind in PATTERNS:
                    for match in re.finditer(regex, line):
                        val = match.group(1)
                        if not is_placeholder(val):
                            print(f"[FAIL] Real credential leaked in .env.example: {kind}")
                            leak = True
            if leak:
                return False
            print("[PASS] .env.example verified safe (contains only placeholder credentials).")

        # Deep security scan on extracted source directory
        sec_scanner = SecurityScanner()
        sec_scanner.scan_directory(src_extract)
        if sec_scanner.findings:
            print(f"[FAIL] Security violations detected in extracted source: {len(sec_scanner.findings)} finding(s)")
            for f in sec_scanner.findings:
                print(f"  - [{f.severity}] {f.file}:{f.line} ({f.rule_id})")
            return False
        print(f"[PASS] Extracted source passed deep security scan (0 credential findings across {sec_scanner.scanned_files_count} files).")

        # 6. Execute pytest on extracted source
        if skip_tests:
            print("\n[NOTE] Pytest execution on extracted source skipped (--skip-tests).")
        else:
            print("\nExecuting test suite against extracted source package...")
            env = os.environ.copy()
            # Set isolated environment variables
            env["TESTING"] = "True"
            # Point PYTHONPATH to extracted source
            env["PYTHONPATH"] = str(src_extract)

            cmd = [sys.executable, "-m", "pytest", "-q", "--tb=short"]
            print(f"  Running: {' '.join(cmd)} in {src_extract}")
            res = subprocess.run(cmd, cwd=str(src_extract), env=env, capture_output=True, text=True)

            print(res.stdout)
            if res.stderr:
                print(res.stderr)

            if res.returncode != 0:
                print(f"[FAIL] Pytest failed on extracted source package (exit code {res.returncode})")
                return False
            print("[PASS] All tests passed on extracted sanitized source package!")

    print("\n" + "=" * 80)
    print("INDEPENDENT RELEASE VERIFICATION: ALL CHECKS PASSED")
    print("=" * 80)
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verify CareerOrbit AI release integrity.")
    parser.add_argument("--skip-tests", action="store_true", help="Skip running pytest on extracted source")
    parser.add_argument("--dist-dir", type=str, default=None, help="Custom dist directory path")
    args = parser.parse_args()

    custom_dist = Path(args.dist_dir) if args.dist_dir else None
    success = verify_release(skip_tests=args.skip_tests, dist_dir=custom_dist)
    sys.exit(0 if success else 1)
