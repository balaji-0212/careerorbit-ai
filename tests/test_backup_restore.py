"""Automated Backup Creation, Restoration, and Integrity Verification Test.
Ensures SQLite database backups can be taken online, restored to an isolated directory,
and verified for full schema, table, and row data preservation.
"""
import sqlite3
import shutil
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from careerorbit.config.settings import SETTINGS
from careerorbit.database.db import init_db, save_job, get_connection
from careerorbit.models.schemas import (
    Job, Application, ApplicationStatus, RecruiterOutreachStatus,
    VerificationStatus, MatchTier, ScoreBreakdown
)

def test_database_backup_and_restoration_lifecycle(tmp_path):
    """Test full backup, restoration, and integrity check on an active database."""
    # 1. Initialize schema and insert test rows
    init_db()
    
    test_uid = f"backup_test_{int(datetime.now(timezone.utc).timestamp())}"
    test_job = Job(
        job_uid=test_uid,
        title="Data Analyst - Backup Verification Test",
        employer="Test Corp",
        normalized_title="data analyst backup verification test",
        official_url="https://testcorp.com/jobs/da-backup",
        canonical_url="https://testcorp.com/jobs/da-backup",
        location="Bengaluru, Karnataka, India",
        work_arrangement="Hybrid",
        description="Verify backup restoration and recovery procedures.",
        discovery_source="Backup Verification Suite",
        verification_status=VerificationStatus.UNVERIFIED,
        priority_category=1,
        priority_label="Data Analyst / BI",
        match_score=88.0,
        match_tier=MatchTier.STRONG_MATCH,
        score_breakdown=ScoreBreakdown(
            skills_and_projects=28.0,
            experience_compatibility=18.0,
            eligibility=14.0,
            freshness_and_availability=12.0,
            location_and_arrangement=9.0,
            evidence_and_realistic_fit=7.0
        )
    )
    saved_id = save_job(test_job)
    assert saved_id is not None

    db_path = SETTINGS.DATABASE_PATH
    assert db_path.exists()

    # 2. Take online SQLite backup
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / "test_backup.db"

    with sqlite3.connect(str(db_path)) as conn, sqlite3.connect(str(backup_path)) as bck_conn:
        conn.backup(bck_conn)

    assert backup_path.exists()
    assert backup_path.stat().st_size > 0

    # 3. Restore to a completely separate temporary directory
    restored_dir = tmp_path / "restored_dir"
    restored_dir.mkdir(parents=True, exist_ok=True)
    restored_db = restored_dir / "restored_careerorbit.db"
    shutil.copy2(str(backup_path), str(restored_db))

    # 4. Verify integrity and data preservation in restored database
    with sqlite3.connect(str(restored_db)) as r_conn:
        r_conn.row_factory = sqlite3.Row
        cur = r_conn.cursor()

        integrity = cur.execute("PRAGMA integrity_check;").fetchone()[0]
        assert integrity == "ok", f"Integrity check failed: {integrity}"

        tables = [row[0] for row in cur.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()]
        assert "jobs" in tables
        assert "applications" in tables
        assert "saved_jobs" in tables

        row = cur.execute("SELECT * FROM jobs WHERE id = ?", (saved_id,)).fetchone()
        assert row is not None
        assert row["title"] == "Data Analyst - Backup Verification Test"
        assert row["employer"] == "Test Corp"
        assert row["match_score"] == 88.0


def test_production_database_integrity_and_backup_preservation():
    """Verify that the production database file has valid integrity and existing backups are readable."""
    prod_db = SETTINGS.BASE_DIR / "data" / "careerorbit.db"
    if not prod_db.exists():
        return

    # Check PRAGMA integrity on actual production file
    with sqlite3.connect(str(prod_db)) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        integrity = cur.execute("PRAGMA integrity_check;").fetchone()[0]
        assert integrity == "ok"

        # Check that jobs and applications exist
        job_count = cur.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        app_count = cur.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
        assert job_count >= 60, f"Expected >= 60 jobs, got {job_count}"
        assert app_count >= 8, f"Expected >= 8 applications, got {app_count}"

    # Verify that backups in data/backups are valid SQLite databases
    backup_dir = SETTINGS.BASE_DIR / "data" / "backups"
    if backup_dir.exists():
        backups = list(backup_dir.glob("*.db"))
        assert len(backups) > 0, "No backups found in data/backups!"
        # Check latest backup
        latest_backup = max(backups, key=lambda p: p.stat().st_mtime)
        with sqlite3.connect(str(latest_backup)) as b_conn:
            b_cur = b_conn.cursor()
            b_integrity = b_cur.execute("PRAGMA integrity_check;").fetchone()[0]
            assert b_integrity == "ok"
