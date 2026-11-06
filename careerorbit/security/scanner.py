"""Hardened Security and Secret-Scanning Engine for CareerOrbit AI.

Features:
1. Multi-format content scanning: .py, .ps1, .sh, .bat, .cmd, .json, .jsonl, .csv,
   .yaml, .yml, .toml, .ini, .cfg, .conf, .xml, .html, .js, .ts, .sql, .md, .txt, .env.
2. Structured parsing for .csv (cell/row tracking), .jsonl (line/record tracking), and .json.
3. Expanded credential coverage: API keys, Bearer tokens, DB credentials, bot tokens,
   private keys, cloud credentials, webhook secrets, authorization headers.
4. Format-aware placeholder validation: eliminates false negatives caused by broad
   substring matching (e.g. incidental 'test', 'example', or 'xxx' inside real secrets).
5. Safe finding generation: never discloses actual secret values; provides 12-hex SHA-256
   fingerprints for deduplication and audit tracking.
6. Archive defense-in-depth: resource limits (depth <= 3, uncompressed <= 50MB, file count <= 1000),
   CRC integrity verification, path-traversal prevention, and corrupt archive handling.
7. Transparent skipped-file accounting: records binary, oversized, or encoding-error files.
"""

from __future__ import annotations

import csv
import dataclasses
import hashlib
import json
import os
import re
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class SecretFinding:
    """Safe representation of an identified credential finding without leaking secrets."""
    file: str
    line: Optional[int]
    column: Optional[int]
    category: str
    rule_id: str
    severity: str  # "CRITICAL", "HIGH", "MEDIUM"
    fingerprint: str  # Safe 12-character SHA-256 hash of secret value
    remediation: str
    blocks_release: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file": self.file,
            "line": self.line,
            "column": self.column,
            "category": self.category,
            "rule_id": self.rule_id,
            "severity": self.severity,
            "fingerprint": self.fingerprint,
            "remediation": self.remediation,
            "blocks_release": self.blocks_release,
        }


@dataclasses.dataclass(frozen=True)
class SkippedFile:
    """Record of a file skipped during scanning with explicit reason."""
    file: str
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {"file": self.file, "reason": self.reason}


@dataclasses.dataclass
class ScanReport:
    """Consolidated security scan report."""
    status: str  # "PASSED" or "FAILED"
    stage: str
    scanned_at: str
    files_scanned_count: int
    files_skipped_count: int
    violations_count: int
    findings: List[SecretFinding]
    skipped_files: List[SkippedFile]
    errors: List[str]

    def to_dict(self) -> Dict[str, Any]:
        findings_dicts = [f.to_dict() for f in self.findings]
        return {
            "status": self.status,
            "stage": self.stage,
            "scanned_at": self.scanned_at,
            "files_scanned_count": self.files_scanned_count,
            "files_skipped_count": self.files_skipped_count,
            "violations_count": self.violations_count,
            "findings": findings_dicts,
            "violations": findings_dicts,
            "skipped_files": [s.to_dict() for s in self.skipped_files],
            "errors": self.errors,
        }


# ---------------------------------------------------------------------------
# Detection Rules & Patterns
# ---------------------------------------------------------------------------

RULES: List[Tuple[str, str, str, re.Pattern, str]] = [
    # (rule_id, category, severity, regex_pattern, remediation)
    (
        "SEC-001",
        "Telegram Bot Token",
        "CRITICAL",
        re.compile(r"\b(\d{8,11}:[A-Za-z0-9_-]{35})\b"),
        "Revoke and rotate bot token via Telegram @BotFather immediately.",
    ),
    (
        "SEC-002",
        "OpenAI / Anthropic / Stripe API Key",
        "CRITICAL",
        re.compile(r"\b(sk[_-](?:ant-|proj-|live-|test-)?[a-zA-Z0-9_-]{20,})\b"),
        "Revoke and rotate API key through the provider portal.",
    ),
    (
        "SEC-003",
        "AWS Access Key ID",
        "HIGH",
        re.compile(r"\b((?:AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16})\b"),
        "Deactivate key in AWS IAM and generate a new access key.",
    ),
    (
        "SEC-004",
        "AWS Secret Access Key Assignment",
        "CRITICAL",
        re.compile(r"""(?i)(?:aws_secret_access_key|aws_secret_key)\s*[:=]\s*['"]?([A-Za-z0-9/+=]{40})['"]?"""),
        "Rotate the corresponding AWS credentials in IAM.",
    ),
    (
        "SEC-005",
        "GitHub Token",
        "CRITICAL",
        re.compile(r"\b(gh[pousr]_[A-Za-z0-9_]{36,})\b"),
        "Revoke GitHub token in GitHub Developer Settings.",
    ),
    (
        "SEC-006",
        "Generic Secret / API Key Assignment",
        "HIGH",
        re.compile(r"""(?i)(?:api_key|apikey|secret_key|private_key|auth_token|client_secret|access_token|refresh_token)\s*[:=]\s*['"]([A-Za-z0-9_\-\.]{16,})['"]"""),
        "Replace hardcoded secret with environment variable reference (.env).",
    ),
    (
        "SEC-007",
        "Bearer Token / Authorization Header",
        "HIGH",
        re.compile(r"""(?i)(?:authorization\s*:\s*Bearer\s+|Bearer\s+)([a-zA-Z0-9_\-\.]{25,})"""),
        "Move authorization header or token to secure runtime environment configuration.",
    ),
    (
        "SEC-008",
        "Database Connection String with Credentials",
        "CRITICAL",
        re.compile(r"""(?i)\b(?:postgres|postgresql|mysql|mongodb|redis|amqp|mariadb):\/\/[^:\s'"]+:([^@\s'"]+)@[^\s'"]+"""),
        "Extract database credentials into discrete environment variables.",
    ),
    (
        "SEC-009",
        "Hardcoded Password Assignment",
        "HIGH",
        re.compile(r"""(?i)(?:password|passwd|db_password|app_password)\s*[:=]\s*['"]([^'"]{8,})['"]"""),
        "Remove hardcoded password assignment; load securely from runtime environment.",
    ),
    (
        "SEC-010",
        "Private Key Material",
        "CRITICAL",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
        "Remove private key material; load from secure file or secrets manager.",
    ),
    (
        "SEC-011",
        "Google API Key",
        "HIGH",
        re.compile(r"\b(AIza[0-9A-Za-z-_]{35})\b"),
        "Restrict or rotate Google Cloud API key in GCP Console.",
    ),
    (
        "SEC-012",
        "Slack Token",
        "HIGH",
        re.compile(r"\b(xox[baprs]-[0-9A-Za-z]{10,48})\b"),
        "Revoke Slack token in Slack App Management portal.",
    ),
    (
        "SEC-013",
        "Slack Webhook URL",
        "HIGH",
        re.compile(r"https:\/\/hooks\.slack\.com\/services\/T[0-9A-Za-z_-]{8,12}\/B[0-9A-Za-z_-]{8,12}\/[0-9A-Za-z_-]{20,32}"),
        "Revoke and rotate Slack incoming webhook in Slack App Management.",
    ),
    (
        "SEC-014",
        "Generic Webhook Secret",
        "HIGH",
        re.compile(r"""(?i)(?:webhook_secret|webhook_token|signing_secret)\s*[:=]\s*['"]([A-Za-z0-9_\-\.]{16,})['"]"""),
        "Store webhook signing secret in secure runtime environment configuration.",
    ),
]


# ---------------------------------------------------------------------------
# Format-Aware Placeholder Validation
# ---------------------------------------------------------------------------

EXACT_PLACEHOLDERS: Set[str] = {
    "", "your_api_key_here", "your_api_key", "your_secret_here", "your_token_here",
    "your_telegram_bot_token", "your_bot_token", "your_aws_access_key",
    "your_aws_secret_key", "your_secret_key", "your_password", "your_password_here",
    "your_sheet_id_here", "your_client_secret", "your_access_token",
    "your_secret_key_here", "your_jwt_secret_here", "your_app_key_here",
    "your_app_id_here", "your_database_url", "replace_me", "replace-me",
    "changeme", "change_me", "placeholder", "placeholder_value", "redacted", "redacted_token",
    "dummy", "dummy_secret", "dummy_token", "fake", "fake_secret",
    "mock", "mock_secret", "mock_token", "todo", "fixme", "none", "null",
    "example_token", "example_key", "test_key", "test_token", "test_secret",
    "my_secret_token", "my_api_key",
}

# Standard documentation placeholders recognized globally
DOC_PLACEHOLDERS: Set[str] = {
    "akiaiosfodnn7example",      # AWS official documentation access key placeholder
    "wjalrxutnfemi/k7mdeng/bpxrficyexamplekey", # AWS official documentation secret key placeholder
    "akiaxexample12345678",      # AWS test placeholder
}

PLACEHOLDER_STRUCTURE_REGEXES = [
    re.compile(r"^<[^>]+>$"),  # Bracketed tokens: <YOUR_KEY>, <API_KEY>, <TOKEN>, <your-api-key>
    re.compile(r"^(?:YOUR|MY|THE)[-_][A-Z0-9_-]+$", re.IGNORECASE),  # Prefix templates: YOUR_API_KEY, your-api-key
    re.compile(r"^(?:dummy|fake|sample|example|test|placeholder|redacted|mock)[-_]?(?:token|key|secret|password|credential|value)?[-_]?[0-9]*$", re.IGNORECASE),
    re.compile(r"^(?:token|key|secret|password|credential|value)[-_]?(?:placeholder|dummy|fake|sample|example|test|mock)?[-_]?[0-9]*$", re.IGNORECASE),
    re.compile(r"^[xX]{3,}$"),  # e.g. xxx, XXXX, XXXXXXXXXX
    re.compile(r"^(.)\1{7,}$"),  # Repeated characters: 00000000, 11111111, aaaaaaaa
]


def is_placeholder(secret: str, rule_id: Optional[str] = None) -> bool:
    """Format-aware placeholder validation.
    
    Eliminates false negatives caused by broad substring checks (e.g. incidental
    'test', 'example', or 'xxx' inside a real high-entropy credential).
    """
    if not secret:
        return True

    s_clean = secret.strip().strip("'\"`")
    s_lower = s_clean.lower()

    # 1. Exact match against known placeholder dictionaries
    if s_lower in EXACT_PLACEHOLDERS or s_lower in DOC_PLACEHOLDERS:
        return True

    # 2. Structural placeholder templates
    for pattern in PLACEHOLDER_STRUCTURE_REGEXES:
        if pattern.match(s_clean):
            return True

    # 3. Rule-specific format awareness
    if rule_id == "SEC-001":
        # Telegram Bot Token format: <bot_id>:<token_hash_35>
        if ":" in s_clean:
            _, token_part = s_clean.split(":", 1)
            t_clean = token_part.strip()
            # If the token portion is obviously repeated characters or template
            if t_clean.lower() in ("your_bot_token_here", "dummy_token", "placeholder") or re.fullmatch(r"[xX0]{35}", t_clean):
                return True
            # Real tokens have high entropy; incidental 'test' or 'xxx' within hash does NOT excuse them
            return False

    elif rule_id in ("SEC-003", "SEC-004"):
        # AWS Key format
        if s_lower in DOC_PLACEHOLDERS or re.fullmatch(r"akia[x0]{16}", s_lower):
            return True
        return False

    elif rule_id == "SEC-008":
        # Database connection passwords
        if s_lower in ("password", "pass", "secret", "user", "admin", "root", "changeme", "your_password"):
            return True

    # 4. Low-entropy threshold: strings with fewer than 3 unique characters are likely placeholders
    if len(set(s_lower)) <= 2 and len(s_lower) >= 8:
        return True

    return False


# ---------------------------------------------------------------------------
# Security Scanner Engine
# ---------------------------------------------------------------------------

SCANNABLE_EXTENSIONS: Set[str] = {
    ".py", ".ps1", ".sh", ".bat", ".cmd",
    ".json", ".jsonl", ".csv",
    ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
    ".xml", ".html", ".js", ".ts", ".sql", ".md", ".txt",
    ".env", ".example", ".key", ".pem", ".crt",
}

SPECIAL_TEXT_FILES: Set[str] = {
    "dockerfile", "makefile", "procfile", "requirements.txt",
    ".gitignore", ".dockerignore", ".env.example",
}

BINARY_EXTENSIONS: Set[str] = {
    ".pdf", ".docx", ".doc", ".png", ".jpg", ".jpeg", ".gif", ".ico",
    ".exe", ".dll", ".so", ".dylib", ".bin", ".dat",
    ".pyc", ".pyo", ".pyd", ".db", ".sqlite", ".sqlite3",
    ".db-wal", ".db-shm", ".tar", ".gz", ".bz2", ".7z",
}

DEFAULT_EXCLUDE_DIRS: Set[str] = {
    ".git", ".venv", "__pycache__", ".pytest_cache", ".system_generated",
    "node_modules", ".idea", ".vscode", "dist", "backups",
}

DEFAULT_MAX_ARCHIVE_DEPTH = 3
DEFAULT_MAX_ARCHIVE_BYTES = 50 * 1024 * 1024  # 50 MB
DEFAULT_MAX_ARCHIVE_FILES = 1000
DEFAULT_MAX_FILE_BYTES = 10 * 1024 * 1024     # 10 MB


class SecurityScanner:
    """Hardened secret and security detection scanner."""

    def __init__(
        self,
        max_archive_depth: int = DEFAULT_MAX_ARCHIVE_DEPTH,
        max_archive_bytes: int = DEFAULT_MAX_ARCHIVE_BYTES,
        max_archive_files: int = DEFAULT_MAX_ARCHIVE_FILES,
        max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    ):
        self.max_archive_depth = max_archive_depth
        self.max_archive_bytes = max_archive_bytes
        self.max_archive_files = max_archive_files
        self.max_file_bytes = max_file_bytes

        self.findings: List[SecretFinding] = []
        self.skipped_files: List[SkippedFile] = []
        self.scanned_files_count = 0
        self.errors: List[str] = []

    def reset(self) -> None:
        self.findings.clear()
        self.skipped_files.clear()
        self.scanned_files_count = 0
        self.errors.clear()

    # -----------------------------------------------------------------------
    # Content Checking Logic
    # -----------------------------------------------------------------------

    def check_string_for_secrets(
        self,
        text: str,
        rel_path: str,
        line_num: Optional[int] = None,
        col_num: Optional[int] = None,
    ) -> List[SecretFinding]:
        """Evaluates a text segment against all security detection rules."""
        findings = []
        for rule_id, category, severity, regex, remediation in RULES:
            for match in regex.finditer(text):
                # Candidate secret value is either captured group or full match
                candidate = match.group(1) if match.groups() else match.group(0)
                if not is_placeholder(candidate, rule_id=rule_id):
                    # Compute safe 12-hex SHA-256 fingerprint without disclosing secret
                    fp = hashlib.sha256(candidate.encode("utf-8")).hexdigest()[:12]
                    calculated_col = col_num if col_num is not None else (match.start() + 1)
                    finding = SecretFinding(
                        file=rel_path,
                        line=line_num,
                        column=calculated_col,
                        category=category,
                        rule_id=rule_id,
                        severity=severity,
                        fingerprint=fp,
                        remediation=remediation,
                        blocks_release=severity in ("CRITICAL", "HIGH"),
                    )
                    findings.append(finding)
        return findings

    # -----------------------------------------------------------------------
    # Format-Specific Scanners
    # -----------------------------------------------------------------------

    def _scan_csv(self, content: str, rel_path: str) -> List[SecretFinding]:
        """Scans CSV tabular content cell-by-cell with row and column tracking."""
        findings = []
        try:
            reader = csv.reader(content.splitlines())
            for row_idx, row in enumerate(reader, 1):
                for col_idx, cell in enumerate(row, 1):
                    if cell and len(cell) >= 8:
                        cell_findings = self.check_string_for_secrets(
                            cell, rel_path, line_num=row_idx, col_num=col_idx
                        )
                        findings.extend(cell_findings)
        except Exception:
            # Fallback to plain text scan if CSV parser encounters formatting issue
            findings.extend(self._scan_plain_text(content, rel_path))
        return findings

    def _scan_jsonl(self, content: str, rel_path: str) -> List[SecretFinding]:
        """Scans JSONL records line-by-line with structured JSON inspection."""
        findings = []
        for line_num, line in enumerate(content.splitlines(), 1):
            line_str = line.strip()
            if not line_str:
                continue
            try:
                data = json.loads(line_str)
                findings.extend(self._scan_structured_data(data, rel_path, line_num=line_num))
            except Exception:
                # Raw text scan for non-JSON lines in JSONL
                findings.extend(self.check_string_for_secrets(line, rel_path, line_num=line_num))
        return findings

    def _scan_json(self, content: str, rel_path: str) -> List[SecretFinding]:
        """Scans structured JSON key/value elements."""
        findings = []
        try:
            data = json.loads(content)
            findings.extend(self._scan_structured_data(data, rel_path))
        except Exception:
            # Fallback to plain text scan on malformed JSON
            findings.extend(self._scan_plain_text(content, rel_path))
        return findings

    def _scan_structured_data(
        self,
        data: Any,
        rel_path: str,
        line_num: Optional[int] = None,
    ) -> List[SecretFinding]:
        """Recursively traverses dictionaries, lists, and scalar string values."""
        findings = []
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(k, str):
                    findings.extend(self.check_string_for_secrets(k, rel_path, line_num=line_num))
                findings.extend(self._scan_structured_data(v, rel_path, line_num=line_num))
        elif isinstance(data, list):
            for item in data:
                findings.extend(self._scan_structured_data(item, rel_path, line_num=line_num))
        elif isinstance(data, str) and len(data) >= 8:
            findings.extend(self.check_string_for_secrets(data, rel_path, line_num=line_num))
        return findings

    def _scan_plain_text(self, content: str, rel_path: str) -> List[SecretFinding]:
        """Scans plain text line by line."""
        findings = []
        for line_num, line in enumerate(content.splitlines(), 1):
            if line and len(line) >= 8:
                findings.extend(self.check_string_for_secrets(line, rel_path, line_num=line_num))
        return findings

    # -----------------------------------------------------------------------
    # File Scanning
    # -----------------------------------------------------------------------

    def scan_file(self, file_path: Path, rel_path: Optional[str] = None) -> List[SecretFinding]:
        """Scans an individual file with size, binary, and format checks."""
        rel = rel_path or str(file_path).replace("\\", "/")
        p = Path(file_path)

        if not p.is_file():
            self.skipped_files.append(SkippedFile(file=rel, reason="Not a regular file"))
            return []

        # Size check
        size = p.stat().st_size
        if size > self.max_file_bytes:
            self.skipped_files.append(SkippedFile(file=rel, reason=f"File exceeds size limit ({size:,} bytes)"))
            return []

        # Format qualification check
        suffix = p.suffix.lower()
        fn_lower = p.name.lower()
        is_scannable = (
            suffix in SCANNABLE_EXTENSIONS
            or fn_lower in SPECIAL_TEXT_FILES
            or fn_lower.startswith(".env")
        )

        if not is_scannable:
            if suffix in BINARY_EXTENSIONS:
                self.skipped_files.append(SkippedFile(file=rel, reason=f"Binary file ({suffix})"))
            else:
                self.skipped_files.append(SkippedFile(file=rel, reason=f"Unsupported text format ({suffix or 'no extension'})"))
            return []

        # Content reading with encoding fallback
        content: Optional[str] = None
        for enc in ("utf-8", "utf-8-sig", "latin-1"):
            try:
                content = p.read_text(encoding=enc)
                break
            except Exception:
                continue

        if content is None:
            self.skipped_files.append(SkippedFile(file=rel, reason="Failed to decode text with supported encodings"))
            return []

        self.scanned_files_count += 1

        # Dispatch to format-specific scanner
        if suffix == ".csv":
            file_findings = self._scan_csv(content, rel)
        elif suffix == ".jsonl":
            file_findings = self._scan_jsonl(content, rel)
        elif suffix == ".json":
            file_findings = self._scan_json(content, rel)
        else:
            file_findings = self._scan_plain_text(content, rel)

        self.findings.extend(file_findings)
        return file_findings

    # -----------------------------------------------------------------------
    # Directory Scanning
    # -----------------------------------------------------------------------

    def scan_directory(
        self,
        target_dir: Path,
        exclude_dirs: Optional[Set[str]] = None,
        exclude_files: Optional[Set[str]] = None,
    ) -> List[SecretFinding]:
        """Recursively scans all qualifying files in a directory."""
        t_dir = Path(target_dir).resolve()
        ex_dirs = exclude_dirs or DEFAULT_EXCLUDE_DIRS
        ex_files = exclude_files or set()

        for root, dirs, files in os.walk(t_dir):
            dirs[:] = [d for d in dirs if d not in ex_dirs and not d.startswith(".git")]
            for file in files:
                if file in ex_files:
                    continue
                full_path = Path(root) / file
                rel_path = str(full_path.relative_to(t_dir)).replace("\\", "/")
                self.scan_file(full_path, rel_path=rel_path)

        return self.findings

    # -----------------------------------------------------------------------
    # Hardened Archive Scanning
    # -----------------------------------------------------------------------

    def scan_archive(
        self,
        archive_path: Path,
        parent_loc: str = "",
        depth: int = 0,
        cumulative_bytes: int = 0,
    ) -> List[SecretFinding]:
        """Recursively scans zip archives and nested archives with resource limits."""
        zip_p = Path(archive_path)
        current_loc = f"{parent_loc}/{zip_p.name}" if parent_loc else zip_p.name

        if depth > self.max_archive_depth:
            err = f"Maximum nested archive depth exceeded ({depth} > {self.max_archive_depth}) at {current_loc}"
            self.errors.append(err)
            self.skipped_files.append(SkippedFile(file=current_loc, reason=err))
            return []

        if not zipfile.is_zipfile(zip_p):
            err = f"Invalid or corrupt zip archive: {current_loc}"
            self.errors.append(err)
            self.skipped_files.append(SkippedFile(file=current_loc, reason=err))
            return []

        try:
            with zipfile.ZipFile(zip_p, "r") as zf:
                # 1. CRC Integrity Check
                bad_crc = zf.testzip()
                if bad_crc:
                    err = f"CRC integrity failure on entry '{bad_crc}' in {current_loc}"
                    self.errors.append(err)
                    self.skipped_files.append(SkippedFile(file=f"{current_loc}::{bad_crc}", reason=err))
                    return []

                infolist = zf.infolist()
                if len(infolist) > self.max_archive_files:
                    err = f"Archive entry count exceeds safety limit ({len(infolist)} > {self.max_archive_files}) at {current_loc}"
                    self.errors.append(err)
                    self.skipped_files.append(SkippedFile(file=current_loc, reason=err))
                    return []

                for info in infolist:
                    fn = info.filename
                    fn_norm = fn.replace("\\", "/")
                    entry_loc = f"{current_loc}::{fn_norm}"

                    # 2. Path Traversal Safety
                    if fn_norm.startswith("/") or fn_norm.startswith("\\") or ":" in fn_norm.split("/")[0] or ".." in fn_norm.split("/"):
                        self.findings.append(SecretFinding(
                            file=entry_loc,
                            line=None,
                            column=None,
                            category="Path Traversal Violation",
                            rule_id="ARCHIVE-001",
                            severity="CRITICAL",
                            fingerprint="path_traversal",
                            remediation="Remove path-traversal entry from archive immediately.",
                            blocks_release=True,
                        ))
                        continue

                    # Resource limit check
                    cumulative_bytes += info.file_size
                    if cumulative_bytes > self.max_archive_bytes:
                        err = f"Archive uncompressed byte limit exceeded ({cumulative_bytes:,} > {self.max_archive_bytes:,} bytes)"
                        self.errors.append(err)
                        self.skipped_files.append(SkippedFile(file=entry_loc, reason=err))
                        break

                    # 3. Prohibited File Names
                    fn_lower = fn_norm.lower()
                    if (fn_lower == ".env" or fn_lower.endswith("/.env") or "/.env." in fn_lower or fn_lower.startswith(".env")) and not fn_lower.endswith(".env.example"):
                        self.findings.append(SecretFinding(
                            file=entry_loc,
                            line=None,
                            column=None,
                            category="Forbidden Environment File",
                            rule_id="ARCHIVE-002",
                            severity="CRITICAL",
                            fingerprint="forbidden_env",
                            remediation="Remove .env files from release archive.",
                            blocks_release=True,
                        ))
                        continue

                    if any(fn_lower.endswith(ext) for ext in (".db", ".db-wal", ".db-shm", ".sqlite", ".sqlite3", ".lock", ".pid", ".log")):
                        self.findings.append(SecretFinding(
                            file=entry_loc,
                            line=None,
                            column=None,
                            category="Forbidden Database, Lock, or Log File",
                            rule_id="ARCHIVE-003",
                            severity="CRITICAL",
                            fingerprint="forbidden_db_or_log",
                            remediation="Remove runtime database, lock, or log files from release package.",
                            blocks_release=True,
                        ))
                        continue

                    if any(term in fn_lower for term in (
                        "data/resumes", "data/backups", "data/logs", "data/audit", "workflow_runs.jsonl",
                        "candidate_evidence.json", "candidate_profile_history.jsonl", "candidate_profile_overrides.json",
                        "candidate_profile_private.json",
                        "scheduler.log", "scheduler_lock.json"
                    )):
                        self.findings.append(SecretFinding(
                            file=entry_loc,
                            line=None,
                            column=None,
                            category="Forbidden Candidate Data / Runtime History",
                            rule_id="ARCHIVE-004",
                            severity="CRITICAL",
                            fingerprint="forbidden_candidate_data",
                            remediation="Exclude private candidate data and runtime history from release package.",
                            blocks_release=True,
                        ))
                        continue

                    # 4. Nested Archive Recursion
                    if fn_lower.endswith(".zip"):
                        import tempfile
                        with tempfile.TemporaryDirectory() as tmpdir:
                            nested_p = Path(tmpdir) / Path(fn).name
                            nested_p.write_bytes(zf.read(fn))
                            self.scan_archive(
                                nested_p,
                                parent_loc=current_loc,
                                depth=depth + 1,
                                cumulative_bytes=cumulative_bytes,
                            )
                        continue

                    # 5. Content Inspection
                    suffix = Path(fn).suffix.lower()
                    is_scannable = (
                        suffix in SCANNABLE_EXTENSIONS
                        or Path(fn).name.lower() in SPECIAL_TEXT_FILES
                    )
                    if is_scannable:
                        try:
                            raw_bytes = zf.read(fn)
                            text = raw_bytes.decode("utf-8", errors="ignore")
                            self.scanned_files_count += 1

                            if suffix == ".csv":
                                self.findings.extend(self._scan_csv(text, entry_loc))
                            elif suffix == ".jsonl":
                                self.findings.extend(self._scan_jsonl(text, entry_loc))
                            elif suffix == ".json":
                                self.findings.extend(self._scan_json(text, entry_loc))
                            else:
                                self.findings.extend(self._scan_plain_text(text, entry_loc))
                        except Exception as exc:
                            self.skipped_files.append(SkippedFile(file=entry_loc, reason=f"Failed to read archive entry: {exc}"))
                    else:
                        if suffix in BINARY_EXTENSIONS:
                            self.skipped_files.append(SkippedFile(file=entry_loc, reason=f"Binary archive entry ({suffix})"))
                        else:
                            self.skipped_files.append(SkippedFile(file=entry_loc, reason=f"Unsupported format ({suffix})"))

        except Exception as exc:
            err = f"Failed to open archive {current_loc}: {exc}"
            self.errors.append(err)
            self.skipped_files.append(SkippedFile(file=current_loc, reason=err))

        return self.findings

    # -----------------------------------------------------------------------
    # Report Generation
    # -----------------------------------------------------------------------

    def build_report(self, stage: str = "security_scan") -> ScanReport:
        """Constructs a consolidated ScanReport."""
        from datetime import datetime, timezone
        has_violations = bool(self.findings)
        status = "FAILED" if has_violations or bool(self.errors) else "PASSED"

        return ScanReport(
            status=status,
            stage=stage,
            scanned_at=datetime.now(timezone.utc).isoformat(),
            files_scanned_count=self.scanned_files_count,
            files_skipped_count=len(self.skipped_files),
            violations_count=len(self.findings),
            findings=list(self.findings),
            skipped_files=list(self.skipped_files),
            errors=list(self.errors),
        )


# ---------------------------------------------------------------------------
# Convenience Functions
# ---------------------------------------------------------------------------

def scan_path(target_path: Path | str) -> ScanReport:
    """Scans a file or directory path and returns a ScanReport."""
    scanner = SecurityScanner()
    p = Path(target_path)
    if p.is_file():
        if p.suffix.lower() == ".zip":
            scanner.scan_archive(p)
        else:
            scanner.scan_file(p)
    elif p.is_dir():
        scanner.scan_directory(p)
    return scanner.build_report()


def scan_archive(archive_path: Path | str) -> ScanReport:
    """Scans an archive file and returns a ScanReport."""
    scanner = SecurityScanner()
    scanner.scan_archive(Path(archive_path))
    return scanner.build_report()


def main() -> int:
    """CLI entry point for CareerOrbit AI Security Scanner."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="CareerOrbit AI Hardened Security and Secret Scanner")
    parser.add_argument("target", nargs="?", default=".", help="Target path to scan (file, directory, or archive)")
    parser.add_argument("--json", action="store_true", help="Output report in JSON format")
    parser.add_argument("--stage", default="cli_scan", help="Scan stage identifier")
    parser.add_argument("--exclude-dirs", nargs="*", default=None, help="Directories to exclude from scanning")
    parser.add_argument("--exclude-files", nargs="*", default=None, help="Files to exclude from scanning")
    parser.add_argument("--include-env", action="store_true", default=False, help="Include local .env file in directory scan")
    parser.add_argument("--fail-on-findings", action="store_true", default=True, help="Exit with code 1 if findings exist (default: True)")
    parser.add_argument("--no-fail", dest="fail_on_findings", action="store_false", help="Always exit with code 0 regardless of findings")
    args = parser.parse_args()

    scanner = SecurityScanner()
    target = Path(args.target)
    if target.is_file():
        if target.suffix.lower() == ".zip":
            scanner.scan_archive(target)
        else:
            scanner.scan_file(target)
    elif target.is_dir():
        ex_dirs = set(args.exclude_dirs) if args.exclude_dirs else DEFAULT_EXCLUDE_DIRS
        ex_files = set(args.exclude_files) if args.exclude_files else set()
        if not args.include_env:
            ex_files.update({".env", ".env.local", ".env.production"})
        scanner.scan_directory(target, exclude_dirs=ex_dirs, exclude_files=ex_files)
    else:
        print(f"Error: Target path '{args.target}' does not exist.", file=sys.stderr)
        return 1

    report = scanner.build_report(stage=args.stage)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print("=" * 80)
        print("CAREERORBIT AI — SECURITY SCAN SUMMARY")
        print("=" * 80)
        print(f"Status:        {report.status}")
        print(f"Stage:         {report.stage}")
        print(f"Scanned At:    {report.scanned_at}")
        print(f"Files Scanned: {report.files_scanned_count}")
        print(f"Files Skipped: {report.files_skipped_count}")
        print(f"Violations:    {report.violations_count}")
        print("=" * 80)

        if report.findings:
            print("\nIDENTIFIED SECURITY FINDINGS:")
            for f in report.findings:
                loc = f"{f.file}:{f.line}" if f.line else f.file
                if f.column:
                    loc += f":{f.column}"
                print(f"  [{f.severity}] {loc} — {f.category} ({f.rule_id})")
                print(f"         Fingerprint: {f.fingerprint} (masked)")
                print(f"         Remediation: {f.remediation}")
                print(f"         Blocks Release: {f.blocks_release}")

        if report.errors:
            print("\nSCAN ERRORS:")
            for err in report.errors:
                print(f"  [ERROR] {err}")

    if args.fail_on_findings and (report.violations_count > 0 or bool(report.errors)):
        return 1
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

