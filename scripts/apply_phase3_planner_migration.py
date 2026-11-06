"""Phase 3 — Daily Study Planner & Habit Tracking Migration.

Safely applies the schema additions for daily_study_plans table with pre-migration
backup verification and schema check.
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

MIGRATION_VERSION = "2026-10-24-phase3-daily-study-planner"


def create_pre_migration_backup(db_path: Path) -> Path:
    backup_dir = SETTINGS.DATA_DIR / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"careerorbit_pre_phase3_planner_migration_{ts}.db"

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
            CREATE TABLE IF NOT EXISTS daily_study_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_date TEXT NOT NULL,
                target_role TEXT NOT NULL,
                daily_budget_minutes INTEGER NOT NULL DEFAULT 120,
                target_priority INTEGER NOT NULL DEFAULT 1,
                skill_gaps_json TEXT NOT NULL DEFAULT '[]',
                user_skills_json TEXT NOT NULL DEFAULT '{}',
                tasks_json TEXT NOT NULL DEFAULT '[]',
                schedule_blocks_json TEXT NOT NULL DEFAULT '[]',
                top_three_priorities_json TEXT NOT NULL DEFAULT '[]',
                allocated_hours REAL DEFAULT 2.0,
                notes TEXT DEFAULT '',
                is_completed INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_study_plans_date ON daily_study_plans(plan_date)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_study_plans_role ON daily_study_plans(target_role)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_study_plans_completed ON daily_study_plans(is_completed)")
            cursor.execute("INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                           (MIGRATION_VERSION, now_utc))
            conn.commit()
            print(f"Migration '{MIGRATION_VERSION}' applied successfully.")

        # Verification
        cursor.execute("SELECT COUNT(*) FROM daily_study_plans")
        print(f"daily_study_plans row count: {cursor.fetchone()[0]}")

        res = cursor.execute("PRAGMA quick_check").fetchall()
        print(f"Database PRAGMA quick_check: {res}")
        fks = cursor.execute("PRAGMA foreign_key_check").fetchall()
        print(f"Database PRAGMA foreign_key_check: {fks}")

    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Apply Phase 3 Daily Study Planner Migration")
    parser.add_argument("--db", type=str, default=str(SETTINGS.DATABASE_PATH), help="Path to database")
    args = parser.parse_args()

    db_path = Path(args.db)
    apply_migration(db_path)


if __name__ == "__main__":
    main()
