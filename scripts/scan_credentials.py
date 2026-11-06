"""Credential and Secret Scanner for CareerOrbit AI.

Scans project files for potential credentials, API tokens, passwords, and secrets.
Reports findings by file and line number with masked values to prevent exposure.
Delegates to the hardened careerorbit.security.scanner engine.
"""

import json
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from careerorbit.security.scanner import (
    SecurityScanner,
    is_placeholder,
    RULES,
    SCANNABLE_EXTENSIONS,
    DEFAULT_EXCLUDE_DIRS,
)

EXCLUDE_DIRS = DEFAULT_EXCLUDE_DIRS
PATTERNS = [
    (r"\b(\d{8,11}:[A-Za-z0-9_-]{35})\b", "Telegram Bot Token"),
    (r"""(?i)(?:api_key|apikey|secret_key|private_key|auth_token)\s*[:=]\s*['"]([A-Za-z0-9_\-\.]{20,})['"]""", "API/Secret Key"),
    (r"\b(AKIA[0-9A-Z]{16})\b", "AWS Access Key"),
    (r"\b(gh[pousr]_[A-Za-z0-9_]{36,})\b", "GitHub Token"),
]


def mask_secret(secret: str) -> str:
    """Mask secret using safe 12-char SHA-256 fingerprint."""
    import hashlib
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()[:12]


def scan_file(path: Path):
    """Scan a single file using hardened security scanner."""
    scanner = SecurityScanner()
    rel = str(path.relative_to(ROOT_DIR)).replace("\\", "/") if path.is_relative_to(ROOT_DIR) else str(path)
    findings = scanner.scan_file(path, rel_path=rel)
    return [
        {
            "file": f.file,
            "line": f.line,
            "type": f.category,
            "masked_token": f.fingerprint,
            "rule_id": f.rule_id,
            "severity": f.severity,
        }
        for f in findings
    ]


def scan_repository():
    """Scan repository using hardened security scanner."""
    scanner = SecurityScanner()
    scanner.scan_directory(
        ROOT_DIR,
        exclude_dirs=DEFAULT_EXCLUDE_DIRS,
        exclude_files={".env", ".env.local", ".env.production", "careerorbit.db"},
    )
    return [
        {
            "file": f.file,
            "line": f.line,
            "type": f.category,
            "masked_token": f.fingerprint,
            "rule_id": f.rule_id,
            "severity": f.severity,
        }
        for f in scanner.findings
    ]


if __name__ == "__main__":
    findings = scan_repository()
    out_path = ROOT_DIR / "reports" / "SECURITY_SCAN_REPORT.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    report_data = {
        "status": "PASSED" if not findings else "FAILED",
        "violations_count": len(findings),
        "violations": findings,
    }
    out_path.write_text(json.dumps(report_data, indent=2), encoding="utf-8")

    print(f"Total potential credentials found: {len(findings)}")
    for f in findings:
        print(f"  [CRITICAL] {f['file']}:{f['line']} -> {f['type']} ({f['masked_token']})")
