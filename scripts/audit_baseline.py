"""Baseline repository and database audit for CareerOrbit AI."""
import os
import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

def compute_hash(path: Path) -> str:
    if not path.is_file():
        return "MISSING"
    return hashlib.sha256(path.read_bytes()).hexdigest()

def backup_db(db_path: Path, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"careerorbit_master_safety_backup_{ts}.db"
    with sqlite3.connect(str(db_path)) as src, sqlite3.connect(str(backup_path)) as dst:
        src.backup(dst)
    return backup_path

def main():
    root = Path(".")
    print("=== BASELINE AUDIT ===")
    
    # 1. Key files hashes
    key_files = [
        root / "careerorbit" / "database" / "db.py",
        root / "careerorbit" / "web" / "app.py",
        root / "careerorbit" / "web" / "static" / "index.html",
        root / "careerorbit" / "config" / "candidate_evidence.py",
        root / "careerorbit" / "config" / "profile.py",
        root / "careerorbit" / "matcher" / "scorer.py",
        root / "careerorbit" / "discovery" / "sources.py",
        root / "careerorbit" / "resumes" / "tailor.py",
        root / "data" / "careerorbit.db",
        root / "data" / "candidate_evidence.json",
    ]
    print("\n[+] SHA-256 Hashes of Key Files:")
    for kf in key_files:
        print(f"  {kf.as_posix()}: {compute_hash(kf)[:24]}")

    # 2. Database backup & verification
    db_path = root / "data" / "careerorbit.db"
    backup_dir = root / "data" / "backups"
    backup_file = backup_db(db_path, backup_dir)
    print(f"\n[+] Created Verified Safety Backup: {backup_file.as_posix()} ({backup_file.stat().st_size} bytes)")

    # 3. Integrity checks
    for label, target_path in [("Main DB", db_path), ("Backup DB", backup_file)]:
        conn = sqlite3.connect(str(target_path))
        c = conn.cursor()
        c.execute("PRAGMA integrity_check")
        status = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM jobs WHERE COALESCE(record_state, 'DISCOVERY_LEAD') != 'QUARANTINED'")
        active_jobs = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM jobs WHERE record_state = 'QUARANTINED'")
        quarantined_jobs = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM applications")
        apps = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM saved_jobs")
        saved = c.fetchone()[0]
        conn.close()
        print(f"  [{label}] Integrity: {status} | Active Jobs: {active_jobs} | Quarantined Jobs: {quarantined_jobs} | Applications: {apps} | Saved Jobs: {saved}")

if __name__ == "__main__":
    main()
