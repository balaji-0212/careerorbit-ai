"""Migration script: 2026-10-24-phase1-canonical-verification-and-source-registry

Applies:
1. job_sources table for persistent source registry with dynamic health tracking.
2. application_history table for stage audit logging.
3. Migrates jobs.verification_status from UNVERIFIED -> PENDING_VERIFICATION and STATUS_UNKNOWN -> VERIFICATION_ERROR.
4. Seeds job_sources with built-in public sources and employer ATS sources from data/employer_sources.json.
5. Seeds initial application_history for existing application records.
6. Records migration in schema_migrations.
"""
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# Fix path to load careerorbit modules
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from careerorbit.config.settings import SETTINGS

MIGRATION_VERSION = "2026-10-24-phase1-canonical-verification-and-source-registry"

DEFAULT_PUBLIC_SOURCES = [
    {
        "source_id": "unstop-public-api",
        "source_name": "Unstop Public API",
        "category": "PUBLIC_AGGREGATOR",
        "source_type": "UNSTOP",
        "endpoint_or_board_id": "https://unstop.com/api/public/opportunity/search-result",
        "access_method": "API",
        "is_configured": 1,
        "is_enabled": 1,
        "health_status": "UNKNOWN",
    },
    {
        "source_id": "remotive-public-api",
        "source_name": "Remotive Public API",
        "category": "PUBLIC_AGGREGATOR",
        "source_type": "REMOTIVE",
        "endpoint_or_board_id": "https://remotive.com/api/remote-jobs",
        "access_method": "API",
        "is_configured": 1,
        "is_enabled": 1,
        "health_status": "UNKNOWN",
    },
    {
        "source_id": "jobicy-public-api",
        "source_name": "Jobicy Public API",
        "category": "PUBLIC_AGGREGATOR",
        "source_type": "JOBICY",
        "endpoint_or_board_id": "https://jobicy.com/api/v2/remote-jobs",
        "access_method": "API",
        "is_configured": 1,
        "is_enabled": 1,
        "health_status": "UNKNOWN",
    },
    {
        "source_id": "arbeitnow-public-api",
        "source_name": "Arbeitnow Public API",
        "category": "PUBLIC_AGGREGATOR",
        "source_type": "ARBEITNOW",
        "endpoint_or_board_id": "https://www.arbeitnow.com/api/job-board-api",
        "access_method": "API",
        "is_configured": 1,
        "is_enabled": 1,
        "health_status": "UNKNOWN",
    },
    {
        "source_id": "remoteok-public-api",
        "source_name": "RemoteOK Public API",
        "category": "PUBLIC_AGGREGATOR",
        "source_type": "REMOTEOK",
        "endpoint_or_board_id": "https://remoteok.com/api",
        "access_method": "API",
        "is_configured": 1,
        "is_enabled": 1,
        "health_status": "UNKNOWN",
    },
    {
        "source_id": "employer-direct-verified",
        "source_name": "Employer Direct Verified Feed",
        "category": "VERIFIED_FEED",
        "source_type": "EMPLOYER_DIRECT",
        "endpoint_or_board_id": "",
        "access_method": "VERIFIED_FEED",
        "is_configured": 1,
        "is_enabled": 1,
        "health_status": "UNKNOWN",
    },
]

def apply_migration(db_path: Path = SETTINGS.DATABASE_PATH) -> bool:
    print(f"Applying migration '{MIGRATION_VERSION}' to: {db_path}")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Check if already applied
    cursor.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
    cursor.execute("SELECT applied_at FROM schema_migrations WHERE version = ?", (MIGRATION_VERSION,))
    row = cursor.fetchone()
    if row:
        print(f"Migration already applied at: {row['applied_at']}")
        conn.close()
        return True

    now_utc = datetime.now(timezone.utc).isoformat()

    # 1. Create job_sources table
    print("Creating job_sources table...")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS job_sources (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_id TEXT UNIQUE NOT NULL,
        source_name TEXT NOT NULL,
        category TEXT NOT NULL,
        source_type TEXT NOT NULL,
        endpoint_or_board_id TEXT NOT NULL DEFAULT '',
        access_method TEXT NOT NULL DEFAULT 'API',
        is_configured INTEGER NOT NULL DEFAULT 1,
        is_enabled INTEGER NOT NULL DEFAULT 1,
        last_attempt_at TEXT,
        last_success_at TEXT,
        last_discovered_count INTEGER NOT NULL DEFAULT 0,
        last_updated_count INTEGER NOT NULL DEFAULT 0,
        last_rejected_count INTEGER NOT NULL DEFAULT 0,
        last_deduped_count INTEGER NOT NULL DEFAULT 0,
        health_status TEXT NOT NULL DEFAULT 'UNKNOWN',
        last_error_category TEXT,
        last_error_message TEXT,
        retry_count INTEGER NOT NULL DEFAULT 0,
        next_retry_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_job_sources_type ON job_sources(source_type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_job_sources_health ON job_sources(health_status)")

    # 2. Create application_history table
    print("Creating application_history table...")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS application_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        application_id INTEGER NOT NULL,
        previous_status TEXT NOT NULL,
        new_status TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        event_source TEXT NOT NULL DEFAULT 'USER_MANUAL',
        actor TEXT NOT NULL DEFAULT 'CANDIDATE',
        notes TEXT DEFAULT '',
        evidence TEXT DEFAULT '',
        FOREIGN KEY (application_id) REFERENCES applications (id) ON DELETE CASCADE
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_app_history_app_id ON application_history(application_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_app_history_time ON application_history(timestamp)")

    # 3. Migrate jobs verification_status
    print("Migrating legacy jobs.verification_status...")
    cursor.execute("UPDATE jobs SET verification_status = 'PENDING_VERIFICATION' WHERE verification_status = 'UNVERIFIED'")
    unverified_migrated = cursor.rowcount
    cursor.execute("UPDATE jobs SET verification_status = 'VERIFICATION_ERROR' WHERE verification_status = 'STATUS_UNKNOWN'")
    unknown_migrated = cursor.rowcount
    print(f"Updated {unverified_migrated} UNVERIFIED -> PENDING_VERIFICATION and {unknown_migrated} STATUS_UNKNOWN -> VERIFICATION_ERROR.")

    # 4. Seed job_sources
    print("Seeding job_sources...")
    for src in DEFAULT_PUBLIC_SOURCES:
        cursor.execute("""
        INSERT INTO job_sources (
            source_id, source_name, category, source_type,
            endpoint_or_board_id, access_method, is_configured, is_enabled,
            health_status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source_id) DO NOTHING
        """, (
            src["source_id"], src["source_name"], src["category"], src["source_type"],
            src["endpoint_or_board_id"], src["access_method"], src["is_configured"],
            src["is_enabled"], src["health_status"], now_utc, now_utc
        ))

    # Also import employer sources from employer_sources.json if present
    employer_sources_file = SETTINGS.DATA_DIR / "employer_sources.json"
    if employer_sources_file.exists():
        try:
            with open(employer_sources_file, "r", encoding="utf-8") as f:
                employer_sources = json.load(f)
            for emp in employer_sources:
                s_id = f"employer-{emp.get('id', emp.get('board_id', 'unknown'))}"
                ats = emp.get("ats_provider", "ATS").upper()
                cursor.execute("""
                INSERT INTO job_sources (
                    source_id, source_name, category, source_type,
                    endpoint_or_board_id, access_method, is_configured, is_enabled,
                    health_status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id) DO NOTHING
                """, (
                    s_id,
                    f"{emp.get('employer_name', 'Employer')} ({emp.get('ats_provider', 'ATS')})",
                    "EMPLOYER_ATS",
                    ats,
                    emp.get("board_id", ""),
                    "API",
                    1 if emp.get("status") == "CONFIGURED" else 0,
                    1 if emp.get("enabled", True) else 0,
                    "UNKNOWN",
                    now_utc,
                    now_utc
                ))
            print(f"Imported {len(employer_sources)} employer sources into job_sources.")
        except Exception as e:
            print(f"Warning importing employer_sources.json: {e}")

    # 5. Seed initial application_history for existing applications
    print("Seeding initial application_history for existing applications...")
    cursor.execute("SELECT id, application_status, created_at, notes FROM applications")
    apps = cursor.fetchall()
    history_count = 0
    for app in apps:
        cursor.execute("SELECT 1 FROM application_history WHERE application_id = ?", (app["id"],))
        if not cursor.fetchone():
            cursor.execute("""
            INSERT INTO application_history (
                application_id, previous_status, new_status, timestamp,
                event_source, actor, notes, evidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                app["id"],
                "CREATED",
                app["application_status"],
                app["created_at"] or now_utc,
                "SYSTEM_INIT",
                "CANDIDATE",
                app["notes"] or "Initial application record preserved from audit.",
                "Original application record created"
            ))
            history_count += 1
    print(f"Seeded {history_count} initial application_history records.")

    # 6. Record migration
    cursor.execute("INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)", (MIGRATION_VERSION, now_utc))
    conn.commit()
    conn.close()
    print("Migration applied successfully!")
    return True

if __name__ == "__main__":
    apply_migration()
