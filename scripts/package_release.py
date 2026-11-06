"""Package CareerOrbit AI sanitized source and audit reports for release.

Enforces:
1. Zero-credential tolerance and strict exclusion of private candidate/runtime data.
2. Staged atomic packaging in dist/.staging/ preventing corrupted releases.
3. Separation of authoritative external manifests (dist/RELEASE_MANIFEST.txt, dist/RELEASE_MANIFEST.json)
   from embedded documentation (docs/RELEASE_MANIFEST.md) to eliminate circular self-referential hashes.
4. Pre-packaging security scan and post-packaging recursive nested archive inspection.
5. Exit code 1 on any detected security violation or packaging defect.
"""

import argparse
import datetime
import hashlib
import json
import os
import platform
import re
import shutil
import sys
import zipfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DIST_DIR = ROOT_DIR / "dist"
STAGING_DIR = DIST_DIR / ".staging"
REPORTS_DIR = ROOT_DIR / "reports"
DOCS_DIR = ROOT_DIR / "docs"

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from careerorbit.security.scanner import (
    SecurityScanner,
    is_placeholder as hardened_is_placeholder,
    RULES,
    SCANNABLE_EXTENSIONS,
    SecretFinding,
)


SOURCE_COVERAGE_REPORT = REPORTS_DIR / "LIVE_SOURCE_COVERAGE_REPORT.json"
SOURCE_REGISTRY = ROOT_DIR / "data" / "employer_sources.json"


def validate_live_source_coverage_report(
    report: dict, registry_path: Path = SOURCE_REGISTRY,
    now_utc: datetime.datetime | None = None, max_age_hours: int = 24,
) -> dict | None:
    """Accept recent read-only coverage evidence only for the current enabled registry."""
    try:
        registry_bytes = registry_path.read_bytes()
        registry = json.loads(registry_bytes.decode("utf-8"))
        if not isinstance(registry, list):
            return None
        current_ids = sorted(
            str(item.get("id") or "") for item in registry
            if item.get("enabled", True)
            and str(item.get("board_id") or "").strip()
            and str(item.get("employer_name") or "").strip()
        )
        checked_at = datetime.datetime.fromisoformat(str(report["checked_at_utc"]).replace("Z", "+00:00"))
        if checked_at.tzinfo is None:
            return None
        checked_at = checked_at.astimezone(datetime.timezone.utc)
        now_utc = now_utc or datetime.datetime.now(datetime.timezone.utc)
        age = now_utc.astimezone(datetime.timezone.utc) - checked_at
        source_rows = report.get("sources")
        if not isinstance(source_rows, list):
            return None
        row_ids = sorted(str(row.get("id") or "") for row in source_rows)
        if (
            age < datetime.timedelta(0)
            or age > datetime.timedelta(hours=max_age_hours)
            or report.get("check_type") != "read_only_public_ats_adapter_fetch"
            or report.get("registry_sha256") != hashlib.sha256(registry_bytes).hexdigest()
            or current_ids != row_ids
            or report.get("configured_source_ids") != current_ids
            or report.get("configured_sources") != len(current_ids)
            or report.get("checked_sources") != len(current_ids)
            or report.get("succeeded_sources") != len(current_ids)
            or report.get("failed_sources") != 0
            or not report.get("all_configured_sources_succeeded")
            or any(row.get("status") != "ok" for row in source_rows)
            or not isinstance(report.get("normalized_jobs"), int)
            or report["normalized_jobs"] < 0
        ):
            return None
        return {
            "status": "PASSED_AT_CHECK_TIME",
            "checked_at_utc": checked_at.isoformat(),
            "days_back": int(report.get("days_back", 0)),
            "configured_sources": len(current_ids),
            "succeeded_sources": len(current_ids),
            "failed_sources": 0,
            "normalized_jobs": report["normalized_jobs"],
            "registry_sha256": report["registry_sha256"],
        }
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None


def load_live_source_coverage_evidence() -> dict | None:
    """Load and validate the recent source sweep report used to close its release gate."""
    try:
        report = json.loads(SOURCE_COVERAGE_REPORT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return validate_live_source_coverage_report(report)

PATTERNS = [
    (r"\b(\d{8,11}:[A-Za-z0-9_-]{35})\b", "Telegram Bot Token"),
    (r"""(?i)(?:api_key|apikey|secret_key|private_key|auth_token)\s*[:=]\s*['"]([A-Za-z0-9_\-\.]{20,})['"]""", "API/Secret Key"),
    (r"\b(AKIA[0-9A-Z]{16})\b", "AWS Access Key"),
    (r"\b(gh[pousr]_[A-Za-z0-9_]{36,})\b", "GitHub Token"),
]

PLACEHOLDER_SUBSTRINGS = {
    "example", "placeholder", "your_", "<your", "redacted", "dummy", "fake", "test", "xxx", "mock"
}

EXCLUDE_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    "backups",
    ".pytest_cache",
    ".system_generated",
    "dist",
    ".idea",
    ".vscode",
    "logs",
    "data/logs",
    "data/backups",
    "data/resumes",
    "data/audit",
    "data/evidence_documents",
    "evidence_documents",
}

EXCLUDE_EXTS = {
    ".pyc", ".pyo", ".pyd", ".log", ".db", ".sqlite", ".sqlite3",
    ".db-shm", ".db-wal", ".zip", ".lock", ".pid"
}

EXCLUDE_FILES = {
    ".env",
    ".env.local",
    ".env.production",
    "careerorbit.db",
    "careerorbit.db-shm",
    "careerorbit.db-wal",
    "candidate_evidence.json",
    "candidate_evidence_documents.json",
    "candidate_profile_history.jsonl",
    "candidate_profile_overrides.json",
    "candidate_profile_private.json",
    "workflow_runs.jsonl",
    "scheduler.log",
    "scheduler_lock.json",
}


def sha256_file(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def private_profile_markers(profile_path: Path = ROOT_DIR / "data" / "candidate_profile_private.json") -> set[str]:
    """Return candidate-identifying strings for release content filtering."""
    try:
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    markers: set[str] = set()
    personal = profile.get("personal", {})
    for key in ("full_name", "email", "phone", "linkedin", "github"):
        value = personal.get(key)
        if isinstance(value, str) and len(value.strip()) >= 4:
            markers.add(value.strip().casefold())
    education = profile.get("education", {})
    value = education.get("institution")
    if isinstance(value, str) and len(value.strip()) >= 6:
        markers.add(value.strip().casefold())
    for record in [*profile.get("employment", []), *profile.get("projects", [])]:
        if isinstance(record, dict):
            for key in ("employer", "name"):
                value = record.get(key)
                if isinstance(value, str) and len(value.strip()) >= 6:
                    markers.add(value.strip().casefold())
    return markers


def contains_private_profile_marker(path: Path, markers: set[str]) -> bool:
    if not markers:
        return False
    try:
        content = path.read_text(encoding="utf-8", errors="ignore").casefold()
    except OSError:
        return False
    return any(marker in content for marker in markers)


def is_placeholder(secret: str) -> bool:
    """Format-aware placeholder detection that eliminates false negatives."""
    return hardened_is_placeholder(secret)


def run_prepackaging_security_scan() -> dict:
    """Scan working tree files before packaging to generate fresh SECURITY_SCAN_REPORT.json."""
    print("\n[Step 2/9] Executing pre-packaging working tree security scan...")
    scanner = SecurityScanner()

    for root, dirs, files in os.walk(ROOT_DIR):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".git")]
        rel_root = Path(root).relative_to(ROOT_DIR)

        # Skip private or ignored parts
        if any(p in rel_root.parts for p in ("backups", "dist", ".system_generated", "logs", ".venv")):
            continue

        for file in files:
            # Check for forbidden files in source tree that might be accidentally packaged
            if file in EXCLUDE_FILES or (file.startswith(".env") and file != ".env.example"):
                continue

            full_path = Path(root) / file
            rel_path = str(full_path.relative_to(ROOT_DIR)).replace("\\", "/")
            scanner.scan_file(full_path, rel_path=rel_path)

    report_obj = scanner.build_report(stage="pre_packaging_working_tree")
    report = report_obj.to_dict()

    violations = report["violations"]

    report_path = REPORTS_DIR / "SECURITY_SCAN_REPORT.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"  -> Pre-packaging security scan: {len(violations)} violations found across {report['files_scanned_count']} files.")
    print(f"  -> Report written to {report_path.relative_to(ROOT_DIR)}")

    if violations:
        print("\nCRITICAL SECURITY VIOLATIONS DETECTED IN WORKING TREE:")
        for v in violations:
            print(f"  [FAIL] File: {v.get('file')} | Line: {v.get('line')} | Reason: {v.get('category')} ({v.get('rule_id')})")
        sys.exit(1)

    return report

    return report


def package_sanitized_source(zip_path: Path):
    """Package sanitized source into zip with deterministic entry order and strict exclusions."""
    print(f"\n[Step 4/9] Packaging sanitized source into {zip_path.name}...")

    added_files = []
    # Collect all qualifying files first, then sort deterministically
    candidates = []
    private_markers = private_profile_markers()

    for root, dirs, files in os.walk(ROOT_DIR):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".git")]
        rel_root = Path(root).relative_to(ROOT_DIR)

        if any(p in rel_root.parts for p in ("backups", "dist", ".system_generated", "logs", ".venv")):
            continue

        for file in files:
            if file in EXCLUDE_FILES or (file.startswith(".env") and file != ".env.example"):
                continue
            if any(file.endswith(ext) for ext in EXCLUDE_EXTS):
                continue

            full_path = Path(root) / file
            arcname = str(full_path.relative_to(ROOT_DIR)).replace("\\", "/")

            if contains_private_profile_marker(full_path, private_markers):
                continue

            if (
                "data/careerorbit.db" in arcname
                or "data/backups" in arcname
                or "data/resumes" in arcname
                or "data/logs" in arcname
                or "data/audit" in arcname
                or arcname == "data/candidate_profile_private.json"
                or arcname.endswith(".lock")
                or arcname.endswith(".pid")
            ):
                continue

            candidates.append((arcname, full_path))

    # Sort deterministically by arcname
    candidates.sort(key=lambda x: x[0])

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for arcname, full_path in candidates:
            zf.write(full_path, arcname)
            added_files.append(arcname)

    size = zip_path.stat().st_size
    h = sha256_file(zip_path)
    print(f"  -> Sanitized Source ZIP created: {size:,} bytes ({len(added_files)} files)")
    print(f"  -> SHA256: {h}")
    return zip_path, size, h, len(added_files)


def package_reports(zip_path: Path):
    """Package docs and reports into zip with deterministic entry order."""
    print(f"\n[Step 5/9] Packaging documentation & audit reports into {zip_path.name}...")

    candidates = []
    private_markers = private_profile_markers()

    if DOCS_DIR.exists():
        for p in DOCS_DIR.glob("**/*"):
            if p.is_file() and not p.name.endswith(".pyc") and not p.name.endswith(".zip"):
                if contains_private_profile_marker(p, private_markers):
                    continue
                arcname = f"docs/{p.relative_to(DOCS_DIR)}".replace("\\", "/")
                candidates.append((arcname, p))

    if REPORTS_DIR.exists():
        for p in REPORTS_DIR.glob("**/*"):
            if p.is_file() and not p.name.endswith(".pyc") and not p.name.endswith(".zip"):
                if contains_private_profile_marker(p, private_markers):
                    continue
                arcname = f"reports/{p.relative_to(REPORTS_DIR)}".replace("\\", "/")
                candidates.append((arcname, p))

    # Sort deterministically by arcname
    candidates.sort(key=lambda x: x[0])

    added_files = []
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for arcname, p in candidates:
            zf.write(p, arcname)
            added_files.append(arcname)

    size = zip_path.stat().st_size
    h = sha256_file(zip_path)
    print(f"  -> Reports ZIP created: {size:,} bytes ({len(added_files)} files)")
    print(f"  -> SHA256: {h}")
    return zip_path, size, h, len(added_files)


def scan_archive_recursively(zip_path: Path, parent_path: str = "") -> list:
    """Recursively scan zip file and any nested zip archives for credentials and forbidden files."""
    scanner = SecurityScanner()
    scanner.scan_archive(zip_path, parent_loc=parent_path)

    violations = []
    for f in scanner.findings:
        archive_part, sep, file_part = f.file.partition("::")
        if not sep:
            archive_part = zip_path.name
            file_part = f.file

        if f.rule_id == "ARCHIVE-001":
            reason = f"Path traversal attempt detected in archive entry: {file_part}"
        elif f.rule_id == "ARCHIVE-002":
            reason = "Forbidden environment / secrets file (.env) included in release package"
        elif f.rule_id == "ARCHIVE-003":
            reason = f"Forbidden database or runtime lock/log file ({file_part}) included in release package"
        elif f.rule_id == "ARCHIVE-004":
            reason = f"Private candidate data / runtime history ({file_part}) included in release package"
        else:
            reason = f"Potential exposed credential ({f.category})"

        violations.append({
            "archive": archive_part,
            "file": file_part,
            "line": f.line,
            "column": f.column,
            "reason": reason,
            "category": f.category,
            "rule_id": f.rule_id,
            "severity": f.severity,
            "fingerprint": f.fingerprint,
            "remediation": f.remediation,
            "blocks_release": f.blocks_release,
        })
    return violations


def verify_sanitization_and_audit(source_zip: Path, reports_zip: Path):
    """Run recursive scan on staged packages before promotion."""
    print("\n[Step 6/9] Validating package sanitization integrity & recursive security scan...")
    all_violations = []

    src_violations = scan_archive_recursively(source_zip)
    all_violations.extend(src_violations)

    rep_violations = scan_archive_recursively(reports_zip)
    all_violations.extend(rep_violations)

    scan_report = {
        "status": "PASSED" if not all_violations else "FAILED",
        "violations_count": len(all_violations),
        "violations": all_violations,
        "findings": all_violations,
        "scanned_archives": [
            str(source_zip.name),
            str(reports_zip.name),
        ],
        "scanned_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "stage": "post_packaging_archive_scan",
    }

    report_path = REPORTS_DIR / "SECURITY_SCAN_REPORT.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(scan_report, indent=2), encoding="utf-8")
    print(f"  -> Post-packaging security scan report saved to {report_path.relative_to(ROOT_DIR)}")

    if all_violations:
        print("\nCRITICAL SECURITY VIOLATIONS DETECTED IN RELEASE PACKAGES:")
        for v in all_violations:
            print(f"  [FAIL] Archive: {v.get('archive')} | File: {v.get('file')} | Reason: {v.get('reason')}")
        # Clean up staging on failure
        if STAGING_DIR.exists():
            shutil.rmtree(STAGING_DIR)
        sys.exit(1)

    print("  -> ALL RELEASE PACKAGES VERIFIED CLEAN: 0 secrets, 0 forbidden files, 0 private documents.")


def generate_external_manifests(
    src_path: Path, src_size: int, src_hash: str, src_count: int,
    rep_path: Path, rep_size: int, rep_hash: str, rep_count: int,
    target_dir: Path, source_coverage: dict | None = None,
):
    """Generate authoritative external manifests (both TXT and JSON) in target directory."""
    print(f"\n[Step 8/9] Generating authoritative external manifests in {target_dir.name}...")

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    now_ist = now_utc.astimezone(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
    ui_report = REPORTS_DIR / "USER_JOURNEY_ACCEPTANCE_REPORT.md"
    try:
        ui_report_text = ui_report.read_text(encoding="utf-8")
        browser_review_passed = "**Status:** VERIFIED" in ui_report_text
    except OSError:
        browser_review_passed = False
    open_gates = []
    if not browser_review_passed:
        open_gates.append("browser_visual_and_user_journey_review")
    open_gates.extend([
        "telegram_continuous_polling_duplicate_delivery_and_chat_permissions",
        "all_result_freshness_and_closure_verification",
        "candidate_evidence_review_and_application_preparation",
        "endpoint_specific_validation_audit",
        "historical_report_reconciliation",
    ])
    if source_coverage is None:
        open_gates.append("full_live_source_board_coverage")
        browser_status = (
            "isolated sign-in, private-data boundary, role-practice, and responsive browser checks passed"
            if browser_review_passed else "browser review remains open"
        )
        acceptance_text = (
            f"Full Product Acceptance: OPEN — {browser_status}; Telegram continuous polling, duplicate delivery, "
            "and chat permissions (one bounded live inbox write was verified), all-result "
            "freshness/closure, candidate evidence, endpoint validation, historical report reconciliation, "
            "and broad source coverage remain open"
        )
    else:
        browser_status = (
            "isolated sign-in, private-data boundary, role-practice, and responsive browser checks passed"
            if browser_review_passed else "browser review remains open"
        )
        acceptance_text = (
            f"Full Product Acceptance: OPEN — {browser_status}; Telegram continuous polling, duplicate delivery, "
            "and chat permissions (one bounded live inbox write was verified), all-result "
            "freshness/closure, candidate evidence review, endpoint validation, and historical report reconciliation "
            "remain open; "
            f"live source coverage passed at {source_coverage['checked_at_utc']} "
            f"({source_coverage['succeeded_sources']}/{source_coverage['configured_sources']} boards)"
        )

    # 1. Text Manifest
    txt_content = f"""================================================================================
CAREERORBIT AI — PRODUCTION RELEASE PACKAGES MANIFEST
================================================================================

Release Name:        CareerOrbit AI Production Release Candidate
Release Version:     v2.0.0
Build Timestamp UTC: {now_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}
Build Timestamp IST: {now_ist.strftime('%Y-%m-%d %H:%M:%S IST')}
Environment:         Python {platform.python_version()} on {platform.system()} {platform.machine()}
Verification Status: PARTIALLY_VERIFIED
Package Integrity & Sanitization: PASSED
{acceptance_text}

1. Sanitized Source Package:
   File:             {src_path.name}
   Size:             {src_size:,} bytes
   Files Count:      {src_count}
   SHA256:           {src_hash}
   Sanitization:     Verified clean. Strictly zero credentials (.env excluded),
                     zero active/backup SQLite databases, zero private candidate records.

2. Audit & Verification Reports Package:
   File:             {rep_path.name}
   Size:             {rep_size:,} bytes
   Files Count:      {rep_count}
   SHA256:           {rep_hash}
   Contents:         Sanitized documentation and engineering reports from docs/ and
                     reports/; candidate-identifying files are omitted.

================================================================================
Security Audit: Passed recursive nested archive scan with 0 violations.
Manifest Architecture: This external manifest is the authoritative record of
final archive SHA-256 hashes and byte sizes. Embedded documentation in docs/
records release structure and inputs to avoid circular self-hash dependencies.
Verification Command: python scripts/verify_release_integrity.py
================================================================================
"""

    txt_path = target_dir / "RELEASE_MANIFEST.txt"
    txt_path.write_text(txt_content, encoding="utf-8")

    # 2. JSON Manifest
    json_data = {
        "release": "CareerOrbit AI Production Release",
        "version": "2.0.0",
        "build_timestamp_utc": now_utc.isoformat(),
        "build_timestamp_ist": now_ist.isoformat(),
        "environment": {
            "os": platform.system(),
            "os_release": platform.release(),
            "architecture": platform.machine(),
            "python_version": platform.python_version(),
        },
        "verification_summary": {
            "status": "PARTIALLY_VERIFIED",
            "package_integrity": "PASSED_AT_BUILD",
            "security_scanner_status": "PASSED",
            "security_violations_count": 0,
            "full_product_acceptance": "OPEN",
            "open_acceptance_gates": open_gates,
            "live_source_coverage": source_coverage,
        },
        "archives": {
            "sanitized_source": {
                "filename": src_path.name,
                "size_bytes": src_size,
                "sha256": src_hash,
                "files_count": src_count,
                "sanitization_status": "VERIFIED_CLEAN",
            },
            "audit_reports": {
                "filename": rep_path.name,
                "size_bytes": rep_size,
                "sha256": rep_hash,
                "files_count": rep_count,
                "sanitization_status": "VERIFIED_CLEAN",
            },
        },
        "manifest_architecture": {
            "external_manifest": "Authoritative record of archive sizes and SHA-256 hashes.",
            "embedded_manifest": "docs/RELEASE_MANIFEST.md records build inputs and components without self-referential archive hashes.",
        },
        "verification_command": "python scripts/verify_release_integrity.py",
    }

    json_path = target_dir / "RELEASE_MANIFEST.json"
    json_path.write_text(json.dumps(json_data, indent=2), encoding="utf-8")
    print(f"  -> Generated {txt_path.name} and {json_path.name}")
    return txt_content, json_data


def promote_staging_to_dist():
    """Atomically promote staged artifacts to final dist directory."""
    print("\n[Step 9/9] Atomically promoting staged artifacts to dist/...")
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    for item in STAGING_DIR.glob("*"):
        if item.is_file():
            dest = DIST_DIR / item.name
            shutil.copy2(item, dest)
            print(f"  -> Published {item.name} ({dest.stat().st_size:,} bytes)")

    # Clean up staging directory
    shutil.rmtree(STAGING_DIR, ignore_errors=True)
    print("  -> Staging directory cleaned.")


def build_release(verify_after: bool = False):
    """Execute complete staged release packaging process."""
    print("=" * 80)
    print("CAREERORBIT AI — PRODUCTION RELEASE PACKAGING WORKFLOW")
    print("=" * 80)

    # Step 1: Pre-packaging inspection
    print(f"\n[Step 1/9] Inspecting environment and pre-packaging requirements...")
    print(f"  -> Root directory: {ROOT_DIR}")
    print(f"  -> Python: {platform.python_version()} ({sys.executable})")
    print(f"  -> Platform: {platform.system()} {platform.machine()}")

    # Prepare clean staging area
    if STAGING_DIR.exists():
        shutil.rmtree(STAGING_DIR)
    STAGING_DIR.mkdir(parents=True, exist_ok=True)

    # Step 2: Pre-packaging working tree security scan
    run_prepackaging_security_scan()

    # Step 3: Verify embedded documentation is ready
    print("\n[Step 3/9] Verifying embedded documentation (docs/RELEASE_MANIFEST.md)...")
    if not (DOCS_DIR / "RELEASE_MANIFEST.md").exists():
        print("  [ERROR] docs/RELEASE_MANIFEST.md is missing!")
        sys.exit(1)
    print("  -> Embedded release specification confirmed present.")

    # Step 4: Package sanitized source in staging
    staged_src_zip = STAGING_DIR / "CareerOrbit_AI_Sanitized_Source.zip"
    src_path, src_size, src_hash, src_count = package_sanitized_source(staged_src_zip)

    # Step 5: Package reports in staging
    staged_rep_zip = STAGING_DIR / "CareerOrbit_AI_Audit_Reports.zip"
    rep_path, rep_size, rep_hash, rep_count = package_reports(staged_rep_zip)

    # Step 6: Recursive security & integrity scan on staged packages
    verify_sanitization_and_audit(src_path, rep_path)

    # Step 7: Recalculate sizes and hashes (already confirmed)
    print("\n[Step 7/9] Computing cryptographic hashes & exact sizes...")
    print(f"  -> {src_path.name}: {src_size:,} bytes | SHA256: {src_hash}")
    print(f"  -> {rep_path.name}: {rep_size:,} bytes | SHA256: {rep_hash}")

    # Step 8: Generate authoritative external manifests in staging
    source_coverage = load_live_source_coverage_evidence()
    if source_coverage:
        print(
            "  -> Fresh live-source evidence accepted: "
            f"{source_coverage['succeeded_sources']}/{source_coverage['configured_sources']} boards "
            f"at {source_coverage['checked_at_utc']}"
        )
    else:
        print("  -> Live-source gate remains open: no fresh complete report matches the current registry.")
    txt_content, json_data = generate_external_manifests(
        src_path, src_size, src_hash, src_count,
        rep_path, rep_size, rep_hash, rep_count,
        STAGING_DIR, source_coverage=source_coverage,
    )

    # Step 9: Promote staging to dist
    promote_staging_to_dist()

    print("\n" + txt_content)
    print("=" * 80)
    print("RELEASE PACKAGING COMPLETED SUCCESSFULLY!")
    print("=" * 80)

    if verify_after:
        print("\n[VERIFY] Executing independent release integrity verification...")
        from scripts.verify_release_integrity import verify_release
        res = verify_release(skip_tests=False)
        if not res:
            print("  [ERROR] Post-packaging release verification failed!")
            sys.exit(1)
        print("  -> Post-packaging release verification: PASSED")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Package CareerOrbit AI release artifacts.")
    parser.add_argument("--verify", action="store_true", help="Run independent verification after build")
    args = parser.parse_args()

    build_release(verify_after=args.verify)
