"""Phase 2 Slice 2.1 — Learning Resources Metadata Migration.

Safely applies the schema additions to learning_resources table with pre-migration
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
from careerorbit.prep.curated_resources import seed_curated_learning_resources

MIGRATION_VERSION = "2026-10-24-phase2-learning-resources-metadata"


def create_pre_migration_backup(db_path: Path) -> Path:
    backup_dir = SETTINGS.DATA_DIR / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"careerorbit_pre_learning_resources_migration_{ts}.db"

    with sqlite3.connect(str(db_path)) as src, sqlite3.connect(str(backup_path)) as dst:
        src.backup(dst)

    with sqlite3.connect(str(backup_path)) as dst:
        res = dst.execute("PRAGMA quick_check").fetchall()
        if res != [("ok",)]:
            raise RuntimeError(f"Backup integrity check failed: {res}")

    return backup_path


def apply_migration(db_path: Path, seed: bool = True) -> None:
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
        # Check if already applied
        cursor.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
        cursor.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (MIGRATION_VERSION,))
        if cursor.fetchone():
            print(f"Migration '{MIGRATION_VERSION}' is already recorded as applied.")
        else:
            now_utc = datetime.now(timezone.utc).isoformat()
            existing_cols = {row[1] for row in cursor.execute("PRAGMA table_info(learning_resources)").fetchall()}
            new_cols = [
                ("skill_tag", "TEXT NOT NULL DEFAULT ''"),
                ("difficulty_level", "TEXT NOT NULL DEFAULT 'BEGINNER'"),
                ("resource_type", "TEXT NOT NULL DEFAULT 'DOCUMENTATION'"),
                ("estimated_minutes", "INTEGER NOT NULL DEFAULT 30"),
                ("created_at", "TEXT"),
                ("is_completed", "INTEGER NOT NULL DEFAULT 0"),
                ("completed_at", "TEXT"),
            ]
            for col_name, col_def in new_cols:
                if col_name not in existing_cols:
                    print(f"  Adding column {col_name} to learning_resources...")
                    cursor.execute(f"ALTER TABLE learning_resources ADD COLUMN {col_name} {col_def}")

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_learning_skill ON learning_resources(skill_tag)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_learning_difficulty ON learning_resources(difficulty_level)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_learning_completed ON learning_resources(is_completed)")

            cursor.execute("INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                           (MIGRATION_VERSION, now_utc))
            conn.commit()
            print(f"Successfully recorded migration '{MIGRATION_VERSION}'.")

        if seed:
            print("Seeding curated learning resources...")
            seed_res = seed_curated_learning_resources(conn=conn)
            print(f"Seed complete: {seed_res['inserted']} inserted, {seed_res['updated']} updated (Total curated: {seed_res['total_curated']}).")

    finally:
        conn.close()


def verify_migration(db_path: Path) -> bool:
    print(f"Verifying migration status on {db_path}...")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT applied_at FROM schema_migrations WHERE version = ?", (MIGRATION_VERSION,))
        mig_row = cursor.fetchone()
        if not mig_row:
            print(f"FAIL: Migration '{MIGRATION_VERSION}' not recorded in schema_migrations.")
            return False

        print(f"PASS: Migration recorded at {mig_row['applied_at']}.")

        cols = {row[1] for row in cursor.execute("PRAGMA table_info(learning_resources)").fetchall()}
        required = ["skill_tag", "difficulty_level", "resource_type", "estimated_minutes", "created_at", "is_completed", "completed_at"]
        missing = [c for c in required if c not in cols]
        if missing:
            print(f"FAIL: Missing columns: {missing}")
            return False
        print(f"PASS: All required columns present: {required}")

        cursor.execute("SELECT COUNT(*) as cnt FROM learning_resources")
        cnt = cursor.fetchone()["cnt"]
        print(f"PASS: Learning resources total count: {cnt}")
        return True
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Apply Phase 2 Learning Resources migration")
    parser.add_argument("--verify", action="store_true", help="Verify migration without modifying")
    args = parser.parse_args()

    db_path = SETTINGS.DATABASE_PATH
    if args.verify:
        ok = verify_migration(db_path)
        sys.exit(0 if ok else 1)
    else:
        apply_migration(db_path, seed=True)
        ok = verify_migration(db_path)
        sys.exit(0 if ok else 1)
