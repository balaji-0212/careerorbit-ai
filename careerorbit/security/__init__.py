"""Security and secret-detection package for CareerOrbit AI."""
from careerorbit.security.scanner import (
    SecurityScanner,
    SecretFinding,
    ScanReport,
    SkippedFile,
    is_placeholder,
    scan_path,
    scan_archive,
)

__all__ = [
    "SecurityScanner",
    "SecretFinding",
    "ScanReport",
    "SkippedFile",
    "is_placeholder",
    "scan_path",
    "scan_archive",
]
