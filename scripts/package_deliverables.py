"""Package CareerOrbit AI sanitized source and audit reports."""

import hashlib
import os
import sys
import zipfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
REPORTS_DIR = ROOT_DIR / "reports"
DOCS_DIR = ROOT_DIR / "docs"

REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def sha256_file(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def package_reports():
    zip_path = REPORTS_DIR / "CareerOrbit_AI_Audit_And_Verification_Reports.zip"
    print(f"Packaging reports into {zip_path.name}...")

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # Add all markdown files in docs/
        for p in DOCS_DIR.glob("*.md"):
            arcname = f"docs/{p.name}"
            zf.write(p, arcname)
            print(f"  + {arcname}")

        # Add root audit reports
        for p in ROOT_DIR.glob("careerorbit_*.md"):
            arcname = f"reports/{p.name}"
            zf.write(p, arcname)
            print(f"  + {arcname}")

    size = zip_path.stat().st_size
    h = sha256_file(zip_path)
    print(f"Reports ZIP created: {size:,} bytes | SHA256: {h}\n")
    return zip_path, size, h


def package_source():
    zip_path = REPORTS_DIR / "CareerOrbit_AI_Phase2_Slice21_Source.zip"
    print(f"Packaging sanitized source into {zip_path.name}...")

    EXCLUDE_DIRS = {
        ".git", ".venv", "__pycache__", "backups", ".pytest_cache", ".system_generated"
    }
    EXCLUDE_EXTS = {".pyc", ".pyo", ".pyd", ".log"}
    EXCLUDE_FILES = {".env", "careerorbit.db"}

    added_count = 0
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(ROOT_DIR):
            # Prune excluded directories
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".git")]

            rel_root = Path(root).relative_to(ROOT_DIR)

            # Skip data directory subfolders like backups, or reports directory to avoid self-nesting
            if "backups" in rel_root.parts or "reports" in rel_root.parts:
                continue

            for file in files:
                if file in EXCLUDE_FILES:
                    continue
                if any(file.endswith(ext) for ext in EXCLUDE_EXTS):
                    continue
                if file.endswith(".db"):
                    continue

                full_path = Path(root) / file
                arcname = str(full_path.relative_to(ROOT_DIR))
                zf.write(full_path, arcname)
                added_count += 1

    size = zip_path.stat().st_size
    h = sha256_file(zip_path)
    print(f"Sanitized Source ZIP created: {size:,} bytes ({added_count} files) | SHA256: {h}\n")
    return zip_path, size, h


if __name__ == "__main__":
    rep_path, rep_size, rep_hash = package_reports()
    src_path, src_size, src_hash = package_source()

    print("=" * 60)
    print("DELIVERABLES PACKAGE SUMMARY")
    print("=" * 60)
    print(f"1. Reports Archive:  {rep_path.name}")
    print(f"   Size:             {rep_size:,} bytes")
    print(f"   SHA256:           {rep_hash}")
    print(f"2. Source Archive:   {src_path.name}")
    print(f"   Size:             {src_size:,} bytes")
    print(f"   SHA256:           {src_hash}")
    print("=" * 60)
