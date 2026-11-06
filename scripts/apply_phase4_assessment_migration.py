"""Phase 4 — Technical Assessment Sandbox Migration.

Safely applies the schema additions for assessment_challenges and assessment_submissions tables,
seeds the curated technical challenge bank, and runs database integrity checks.
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
from careerorbit.prep.assessment_sandbox import seed_assessment_challenges

MIGRATION_VERSION = "2026-10-24-phase4-assessment-sandbox"


def create_pre_migration_backup(db_path: Path) -> Path:
    backup_dir = SETTINGS.DATA_DIR / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"careerorbit_pre_phase4_assessment_migration_{ts}.db"

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
            CREATE TABLE IF NOT EXISTS assessment_challenges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                challenge_uid TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                difficulty TEXT NOT NULL,
                question_type TEXT NOT NULL DEFAULT 'QUERY',
                prompt_markdown TEXT NOT NULL,
                initial_code TEXT NOT NULL,
                test_fixtures_json TEXT NOT NULL DEFAULT '{}',
                expected_output_json TEXT NOT NULL DEFAULT '[]',
                options_json TEXT NOT NULL DEFAULT '[]',
                explanation TEXT NOT NULL DEFAULT '',
                time_limit_minutes INTEGER DEFAULT 30,
                created_at TEXT NOT NULL
            )
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS assessment_submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                challenge_id INTEGER NOT NULL,
                submitted_code TEXT NOT NULL,
                is_passed INTEGER NOT NULL DEFAULT 0,
                execution_time_ms INTEGER DEFAULT 0,
                tests_passed INTEGER DEFAULT 0,
                total_tests INTEGER DEFAULT 1,
                score REAL DEFAULT 0.0,
                feedback_notes TEXT DEFAULT '',
                output_json TEXT DEFAULT '[]',
                created_at TEXT NOT NULL,
                FOREIGN KEY (challenge_id) REFERENCES assessment_challenges (id) ON DELETE CASCADE
            )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_assess_chall_uid ON assessment_challenges(challenge_uid)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_assess_chall_cat ON assessment_challenges(category)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_assess_chall_diff ON assessment_challenges(difficulty)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_assess_sub_chall ON assessment_submissions(challenge_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_assess_sub_time ON assessment_submissions(created_at)")
            cursor.execute("INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                           (MIGRATION_VERSION, now_utc))
            conn.commit()
            print(f"Migration '{MIGRATION_VERSION}' applied successfully.")

        # Seed challenges
        seeded = seed_assessment_challenges(conn)
        print(f"Seeded {seeded} curated assessment challenges.")

        # Verification
        cursor.execute("SELECT COUNT(*) FROM assessment_challenges")
        c_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM assessment_submissions")
        s_count = cursor.fetchone()[0]
        print(f"assessment_challenges count: {c_count}, assessment_submissions count: {s_count}")

        res = cursor.execute("PRAGMA quick_check").fetchall()
        print(f"Database PRAGMA quick_check: {res}")
        fks = cursor.execute("PRAGMA foreign_key_check").fetchall()
        print(f"Database PRAGMA foreign_key_check: {fks}")

    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Apply Phase 4 Assessment Sandbox Migration")
    parser.add_argument("--db", type=str, default=str(SETTINGS.DATABASE_PATH), help="Path to database")
    args = parser.parse_args()

    db_path = Path(args.db)
    apply_migration(db_path)


if __name__ == "__main__":
    main()
