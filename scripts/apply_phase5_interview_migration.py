"""Phase 5 — Role-Specific Interview Preparation Coach Migration.

Safely applies the schema additions for interview_prep_sessions table,
verifies foreign keys, and runs pre-migration database integrity checks.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from careerorbit.config.settings import SETTINGS

MIGRATION_VERSION = "2026-10-24-phase5-interview-prep-sessions"


def create_pre_migration_backup(db_path: Path) -> Path:
    backup_dir = SETTINGS.DATA_DIR / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"careerorbit_pre_phase5_interview_migration_{ts}.db"

    with sqlite3.connect(str(db_path)) as src, sqlite3.connect(str(backup_path)) as dst:
        src.backup(dst)

    with sqlite3.connect(str(backup_path)) as dst:
        res = dst.execute("PRAGMA quick_check").fetchall()
        if res != [("ok",)]:
            raise RuntimeError(f"Backup integrity check failed: {res}")

    return backup_path


def apply_migration(db_path: Path) -> None:
    if not db_path.exists():
        print(f"Database file does not exist at {db_path}. Run application init first.")
        return

    print(f"Applying migration '{MIGRATION_VERSION}' to {db_path}...")
    backup_path = create_pre_migration_backup(db_path)
    print(f"Created verified pre-migration backup at: {backup_path}")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        cursor.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
        cursor.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (MIGRATION_VERSION,))
        if cursor.fetchone():
            print(f"Migration '{MIGRATION_VERSION}' is already recorded in schema_migrations.")
        else:
            now_utc = datetime.now(timezone.utc).isoformat()
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS interview_prep_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL UNIQUE,
                employer_name TEXT NOT NULL,
                role_title TEXT NOT NULL,
                briefing_json TEXT NOT NULL DEFAULT '{}',
                candidate_notes TEXT DEFAULT '',
                confidence_rating INTEGER DEFAULT 0,
                checklist_json TEXT NOT NULL DEFAULT '[]',
                answer_drafts_json TEXT NOT NULL DEFAULT '{}',
                disclaimer TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (job_id) REFERENCES jobs (id) ON DELETE CASCADE
            )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_interview_job_id ON interview_prep_sessions(job_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_interview_conf ON interview_prep_sessions(confidence_rating)")
            cursor.execute("INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                           (MIGRATION_VERSION, now_utc))
            conn.commit()
            print(f"Migration '{MIGRATION_VERSION}' applied successfully.")

        # Verification
        cursor.execute("SELECT COUNT(*) FROM interview_prep_sessions")
        s_count = cursor.fetchone()[0]
        print(f"interview_prep_sessions count: {s_count}")

        res = cursor.execute("PRAGMA quick_check").fetchall()
        print(f"Database PRAGMA quick_check: {res}")
        fks = cursor.execute("PRAGMA foreign_key_check").fetchall()
        print(f"Database PRAGMA foreign_key_check: {fks}")

    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Apply Phase 5 Interview Preparation Migration")
    parser.add_argument("--db", type=str, default=str(SETTINGS.DATABASE_PATH), help="Path to database")
    args = parser.parse_args()

    db_path = Path(args.db)
    apply_migration(db_path)


if __name__ == "__main__":
    main()
