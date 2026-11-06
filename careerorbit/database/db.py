"""Database operations and schema management using SQLite."""

import sqlite3

import json

import csv

import uuid

from pathlib import Path

from typing import List, Dict, Optional, Any

from datetime import datetime, timezone, timedelta

from careerorbit.config.settings import (

    SETTINGS, current_data_dir, current_database_path, current_exports_dir,

)

from careerorbit.eligibility import detect_opportunity_attributes

from careerorbit.matcher.geo import classify_geographic_priority, get_city_synonyms

from careerorbit.models.schemas import (

    Job, Application, PreparationPlan, ResumeMetadata,

    VerificationStatus, MatchTier, ApplicationStatus, RecruiterOutreachStatus, canonicalize_application_stage,

    JobSourceItem, ApplicationHistoryItem

)



# Quarantined rows are retained for auditability, but are never shown as leads.

LEGACY_UNSUPPORTED_PORTAL_SOURCES = (

    "Caterpillar Workday Portal", "Broadridge Official Career Portal",

    "Bosch SmartRecruiters Portal", "Tiger Analytics Career Portal",

    "Zoho Direct Careers", "Freshworks Lever Board", "Cognizant Global Careers",

    "NTT DATA Careers", "Virtusa Workday Portal", "Caterpillar Career Portal",

)



def get_connection() -> sqlite3.Connection:

    conn = sqlite3.connect(str(current_database_path()))

    conn.execute("PRAGMA foreign_keys = ON;")

    conn.row_factory = sqlite3.Row

    return conn



def init_db() -> None:

    """Initialize tables and conservatively retire legacy URL-only open claims."""

    conn = get_connection()

    cursor = conn.cursor()



    # Back up the existing database before any DDL starts. SQLite backup from a

    # connection with uncommitted schema writes can block indefinitely on Windows.

    if current_database_path().exists() and current_database_path().stat().st_size:

        tables_now = {r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}

        has_integrity_migration = False

        if "schema_migrations" in tables_now:

            has_integrity_migration = cursor.execute(

                "SELECT 1 FROM schema_migrations WHERE version='2026-10-21-evidence-first-quarantine'"

            ).fetchone() is not None

        if "jobs" in tables_now and not has_integrity_migration:

            backup_dir = current_data_dir() / "backups"

            backup_dir.mkdir(parents=True, exist_ok=True)

            backup_path = backup_dir / f"careerorbit_pre_integrity_migration_{datetime.now(timezone.utc):%Y%m%d_%H%M%S_%f}.db"

            with sqlite3.connect(str(backup_path)) as backup_conn:

                conn.backup(backup_conn)



    cursor.execute("""

    CREATE TABLE IF NOT EXISTS jobs (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        job_uid TEXT UNIQUE NOT NULL,

        employer TEXT NOT NULL,

        title TEXT NOT NULL,

        normalized_title TEXT NOT NULL,

        job_id_or_req TEXT DEFAULT '',

        priority_category INTEGER NOT NULL,

        priority_label TEXT NOT NULL,

        career_category TEXT DEFAULT '',

        location TEXT NOT NULL,

        work_arrangement TEXT NOT NULL,

        employment_type TEXT DEFAULT 'Full-time',

        salary TEXT DEFAULT 'Not Disclosed',

        shift TEXT DEFAULT 'Day shift',

        posting_date TEXT,

        posting_date_confidence TEXT NOT NULL DEFAULT 'UNKNOWN',

        deadline TEXT,

        official_url TEXT NOT NULL,

        official_listing_url TEXT NOT NULL DEFAULT '',

        application_url TEXT NOT NULL DEFAULT '',

        discovery_url TEXT NOT NULL DEFAULT '',

        canonical_url TEXT NOT NULL,

        discovery_source TEXT NOT NULL,

        verification_source TEXT DEFAULT '',

        verification_status TEXT NOT NULL,

        verification_notes TEXT DEFAULT '',

        last_observed_status TEXT NOT NULL DEFAULT '',

        last_observed_status_at TEXT NOT NULL DEFAULT '',

        record_state TEXT NOT NULL DEFAULT 'DISCOVERY_LEAD',

        integrity_notes TEXT DEFAULT '',

        match_score REAL DEFAULT 0.0,

        match_tier TEXT NOT NULL,

        score_breakdown TEXT,

        required_skills TEXT,

        preferred_skills TEXT,

        supported_skills TEXT,

        missing_skills TEXT,

        learnable_skills TEXT,

        disqualifiers TEXT,

        evidence_notes TEXT,

        recommended_action TEXT,

        description TEXT,

        first_discovered_at TEXT NOT NULL,

        last_verified_at TEXT NOT NULL

    )

    """)



    cursor.execute("""

    CREATE TABLE IF NOT EXISTS applications (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        job_id INTEGER UNIQUE NOT NULL,

        selected_resume_path_pdf TEXT,

        selected_resume_path_docx TEXT,

        resume_type TEXT DEFAULT 'data_analyst',

        resume_status TEXT DEFAULT 'PENDING',

        application_status TEXT NOT NULL,

        submission_confirmed_by_user INTEGER DEFAULT 0,

        submission_date TEXT,

        recruiter_outreach_status TEXT NOT NULL,

        interview_stage TEXT,

        follow_up_date TEXT,

        cover_letter_text TEXT,

        application_answers TEXT,

        outreach_messages TEXT,

        notes TEXT,

        next_action TEXT,

        created_at TEXT NOT NULL,

        updated_at TEXT NOT NULL,

        candidate_review_state TEXT NOT NULL DEFAULT 'CURRENT',

        submission_evidence_state TEXT NOT NULL DEFAULT 'NOT_SUBMITTED',

        FOREIGN KEY (job_id) REFERENCES jobs (id) ON DELETE CASCADE

    )

    """)



    cursor.execute("""

    CREATE TABLE IF NOT EXISTS preparation_plans (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        job_id INTEGER UNIQUE NOT NULL,

        application_id INTEGER,

        role_title TEXT NOT NULL,

        company TEXT NOT NULL,

        target_priority INTEGER NOT NULL,

        daily_time_allocated_hours REAL DEFAULT 3.5,

        study_plan_blocks TEXT,

        technical_topics TEXT,

        practice_exercises TEXT,

        interview_questions TEXT,

        completed_tasks TEXT,

        weak_areas TEXT,

        revision_checklist TEXT,

        next_revision_date TEXT,

        created_at TEXT NOT NULL,

        updated_at TEXT NOT NULL,

        FOREIGN KEY (job_id) REFERENCES jobs (id) ON DELETE CASCADE

    )

    """)



    cursor.execute("""

    CREATE TABLE IF NOT EXISTS resumes (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        job_id INTEGER NOT NULL,

        company_name TEXT NOT NULL,

        role_title TEXT NOT NULL,

        source_resume_type TEXT NOT NULL,

        pdf_filename TEXT NOT NULL,

        pdf_path TEXT NOT NULL,

        docx_filename TEXT NOT NULL,

        docx_path TEXT NOT NULL,

        tailoring_summary TEXT NOT NULL,

        supported_keywords TEXT,

        missing_requirements TEXT,

        keyword_coverage_pct REAL DEFAULT 0.0,

        details_needing_confirmation TEXT,

        created_at TEXT NOT NULL,

        FOREIGN KEY (job_id) REFERENCES jobs (id) ON DELETE CASCADE

    )

    """)



    cursor.execute("""

    CREATE TABLE IF NOT EXISTS saved_jobs (

        job_id INTEGER PRIMARY KEY,

        saved_at TEXT NOT NULL,

        notes TEXT DEFAULT '',

        FOREIGN KEY (job_id) REFERENCES jobs (id) ON DELETE CASCADE

    )

    """)



    cursor.execute("""

    CREATE TABLE IF NOT EXISTS inbox_messages (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        message_uid TEXT UNIQUE NOT NULL,

        channel TEXT NOT NULL DEFAULT 'telegram',

        chat_id TEXT NOT NULL,

        chat_title TEXT DEFAULT '',

        chat_type TEXT DEFAULT 'private',

        message_id INTEGER NOT NULL,

        sender_id TEXT DEFAULT '',

        sender_name TEXT DEFAULT '',

        sender_username TEXT DEFAULT '',

        raw_text TEXT NOT NULL,

        classification TEXT NOT NULL,

        category_group TEXT NOT NULL,

        is_job_lead INTEGER NOT NULL DEFAULT 0,

        job_id INTEGER,

        extracted_data TEXT DEFAULT '{}',

        media_type TEXT DEFAULT 'text',

        media_file_id TEXT DEFAULT '',

        received_at TEXT NOT NULL,

        status TEXT NOT NULL DEFAULT 'NEW',

        notes TEXT DEFAULT '',

        FOREIGN KEY (job_id) REFERENCES jobs (id) ON DELETE SET NULL

    )

    """)



    cursor.execute("""

    CREATE TABLE IF NOT EXISTS telegram_state (

        key TEXT PRIMARY KEY,

        value TEXT,

        updated_at TEXT NOT NULL

    )

    """)



    cursor.execute("""

    CREATE TABLE IF NOT EXISTS community_sources (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        source_name TEXT NOT NULL,

        source_type TEXT NOT NULL,

        chat_id TEXT UNIQUE NOT NULL,

        status TEXT NOT NULL DEFAULT 'ACTIVE',

        is_enabled INTEGER NOT NULL DEFAULT 1,

        last_ingestion_at TEXT,

        last_error TEXT DEFAULT '',

        messages_count INTEGER NOT NULL DEFAULT 0,

        created_at TEXT NOT NULL,

        updated_at TEXT NOT NULL

    )

    """)



    cursor.execute("""

    CREATE TABLE IF NOT EXISTS learning_resources (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        title TEXT NOT NULL,

        category TEXT NOT NULL,

        sub_category TEXT DEFAULT '',

        canonical_url TEXT UNIQUE,

        primary_url TEXT NOT NULL,

        all_urls TEXT DEFAULT '[]',

        source TEXT NOT NULL,

        source_message_uid TEXT DEFAULT '',

        raw_excerpt TEXT DEFAULT '',

        summary TEXT DEFAULT '',

        tags TEXT DEFAULT '[]',

        saved_at TEXT NOT NULL,

        notes TEXT DEFAULT '',

        skill_tag TEXT NOT NULL DEFAULT '',

        difficulty_level TEXT NOT NULL DEFAULT 'BEGINNER',

        resource_type TEXT NOT NULL DEFAULT 'DOCUMENTATION',

        estimated_minutes INTEGER NOT NULL DEFAULT 30,

        created_at TEXT,

        is_completed INTEGER NOT NULL DEFAULT 0,

        completed_at TEXT

    )

    """)



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



    cursor.execute("""

    CREATE TABLE IF NOT EXISTS candidate_career_preferences (

        profile_id TEXT PRIMARY KEY,

        preferences_json TEXT NOT NULL,

        updated_at TEXT NOT NULL

    )

    """)



    # Indices for performance

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_uid ON jobs(job_uid)")

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_priority ON jobs(priority_category)")

    jobs_cols = {row[1] for row in cursor.execute("PRAGMA table_info(jobs)").fetchall()}

    if "career_category" not in jobs_cols:

        cursor.execute("ALTER TABLE jobs ADD COLUMN career_category TEXT DEFAULT ''")

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_career_cat ON jobs(career_category)")

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_tier ON jobs(match_tier)")

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_apps_job_id ON applications(job_id)")

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_prep_job_id ON preparation_plans(job_id)")

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_inbox_chat ON inbox_messages(chat_id)")

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_inbox_class ON inbox_messages(classification)")

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_inbox_status ON inbox_messages(status)")

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_inbox_received ON inbox_messages(received_at)")

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_comm_sources_chat ON community_sources(chat_id)")

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_comm_sources_type ON community_sources(source_type)")

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_learning_cat ON learning_resources(category)")

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_learning_canon ON learning_resources(canonical_url)")

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_learning_skill ON learning_resources(skill_tag)")

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_learning_difficulty ON learning_resources(difficulty_level)")

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_learning_completed ON learning_resources(is_completed)")

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_job_sources_type ON job_sources(source_type)")

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_job_sources_health ON job_sources(health_status)")

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_app_history_app_id ON application_history(application_id)")

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_app_history_time ON application_history(timestamp)")



    cursor.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")

    columns = {row[1] for row in cursor.execute("PRAGMA table_info(jobs)").fetchall()}

    missing_columns = []

    if "posting_date_confidence" not in columns:

        missing_columns.append(("posting_date_confidence", "TEXT NOT NULL DEFAULT 'UNKNOWN'"))

    if "discovery_url" not in columns:

        missing_columns.append(("discovery_url", "TEXT NOT NULL DEFAULT ''"))

    if "career_category" not in columns:

        missing_columns.append(("career_category", "TEXT DEFAULT ''"))

    schema_migration = "2026-10-21-job-source-evidence"

    cursor.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (schema_migration,))

    if not cursor.fetchone():

        if missing_columns and current_database_path().exists() and current_database_path().stat().st_size:

            backup_dir = current_data_dir() / "backups"

            backup_dir.mkdir(parents=True, exist_ok=True)

            backup_path = backup_dir / f"careerorbit_pre_job_source_migration_{datetime.now(timezone.utc):%Y%m%d_%H%M%S_%f}.db"

            with sqlite3.connect(str(backup_path)) as backup_conn:

                conn.backup(backup_conn)

        for column, declaration in missing_columns:

            cursor.execute(f"ALTER TABLE jobs ADD COLUMN {column} {declaration}")

        cursor.execute("INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)", (schema_migration, datetime.now(timezone.utc).isoformat()))



    migration = "2026-10-21-verification-evidence"

    cursor.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (migration,))

    if not cursor.fetchone():

        cursor.execute("SELECT COUNT(*) AS n FROM jobs WHERE verification_status = 'VERIFIED_OPEN'")

        legacy_open_count = cursor.fetchone()["n"]

        if legacy_open_count:

            # Preserve a byte-for-byte SQLite backup before correcting claims produced by

            # the former URL-fragment/HTTP-200 verification logic.

            backup_dir = current_data_dir() / "backups"

            backup_dir.mkdir(parents=True, exist_ok=True)

            backup_path = backup_dir / f"careerorbit_pre_verification_migration_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}.db"

            with sqlite3.connect(str(backup_path)) as backup_conn:

                conn.backup(backup_conn)

            cursor.execute("""

                UPDATE jobs

                SET verification_status = 'UNVERIFIED',

                    verification_notes = 'Legacy verification did not retain sufficient page evidence; reverify the listing.'

                WHERE verification_status = 'VERIFIED_OPEN'

            """)

        cursor.execute("INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)", (migration, datetime.now(timezone.utc).isoformat()))



    integrity_migration = "2026-10-21-evidence-first-quarantine"

    cursor.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (integrity_migration,))

    if not cursor.fetchone():

        job_columns = {row[1] for row in cursor.execute("PRAGMA table_info(jobs)").fetchall()}

        app_columns = {row[1] for row in cursor.execute("PRAGMA table_info(applications)").fetchall()}

        if "record_state" not in job_columns:

            cursor.execute("ALTER TABLE jobs ADD COLUMN record_state TEXT NOT NULL DEFAULT 'DISCOVERY_LEAD'")

        if "integrity_notes" not in job_columns:

            cursor.execute("ALTER TABLE jobs ADD COLUMN integrity_notes TEXT NOT NULL DEFAULT ''")

        for column in ("official_listing_url", "application_url", "last_observed_status", "last_observed_status_at"):

            if column not in job_columns:

                cursor.execute(f"ALTER TABLE jobs ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")

        if "candidate_review_state" not in app_columns:

            cursor.execute("ALTER TABLE applications ADD COLUMN candidate_review_state TEXT NOT NULL DEFAULT 'CURRENT'")

        if "submission_evidence_state" not in app_columns:

            cursor.execute("ALTER TABLE applications ADD COLUMN submission_evidence_state TEXT NOT NULL DEFAULT 'NOT_SUBMITTED'")



        # These legacy records have no raw discovery response or corroborated

        # job-specific official evidence. Retain every row and its history.

        legacy_sources = LEGACY_UNSUPPORTED_PORTAL_SOURCES

        cursor.execute(

            f"UPDATE jobs SET record_state='QUARANTINED', integrity_notes=? "

            f"WHERE discovery_source IN ({','.join('?' for _ in legacy_sources)})",

            ("Legacy portal record has no saved source response or corroborated requisition evidence; quarantine pending independent review.", *legacy_sources),

        )

        cursor.execute(

            "UPDATE jobs SET record_state='QUARANTINED', integrity_notes=? WHERE discovery_source IN ('Test','Test Unit')",

            ("Test fixture entered production storage; retained for audit, excluded from discovery results.",),

        )

        cursor.execute("""

            UPDATE applications

            SET candidate_review_state='NEEDS_CONFIRMATION',

                submission_evidence_state=CASE

                    WHEN application_status='SUBMITTED' OR submission_confirmed_by_user=1

                    THEN 'REQUIRES_CONFIRMATION' ELSE 'LEGACY_REVIEW' END

        """)

        cursor.execute("INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",

                       (integrity_migration, datetime.now(timezone.utc).isoformat()))



    fixture_cleanup_migration = "2026-10-21-fixture-source-cleanup"

    cursor.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (fixture_cleanup_migration,))

    if not cursor.fetchone():

        cursor.execute(

            "UPDATE jobs SET record_state='QUARANTINED', integrity_notes=? WHERE discovery_source='Fixture'",

            ("Fixture-source record retained for audit; excluded from genuine vacancy results.",),

        )

        cursor.execute("""

            UPDATE applications SET candidate_review_state='NEEDS_CONFIRMATION',

                submission_evidence_state=CASE

                    WHEN application_status='SUBMITTED' OR submission_confirmed_by_user=1

                    THEN 'REQUIRES_CONFIRMATION' ELSE 'LEGACY_REVIEW' END

            WHERE job_id IN (SELECT id FROM jobs WHERE record_state='QUARANTINED')

        """)

        cursor.execute("INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",

                       (fixture_cleanup_migration, datetime.now(timezone.utc).isoformat()))



    geo_migration = "2026-10-22-india-first-geographic-priorities"

    cursor.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (geo_migration,))

    if not cursor.fetchone():

        job_columns = {row[1] for row in cursor.execute("PRAGMA table_info(jobs)").fetchall()}

        geo_columns = [

            ("geographic_priority", "INTEGER NOT NULL DEFAULT 1"),

            ("geographic_tier_label", "TEXT NOT NULL DEFAULT 'Priority 1 — South India & India Remote'"),

            ("location_eligibility_status", "TEXT NOT NULL DEFAULT 'VERIFIED_INDIA_ELIGIBLE'"),

            ("city", "TEXT NOT NULL DEFAULT ''"),

            ("state", "TEXT NOT NULL DEFAULT ''"),

            ("country", "TEXT NOT NULL DEFAULT 'India'"),

            ("remote_eligibility", "TEXT NOT NULL DEFAULT 'INDIA_PERMITTED'"),

            ("geo_score", "REAL NOT NULL DEFAULT 10.0")

        ]

        for col, col_type in geo_columns:

            if col not in job_columns:

                cursor.execute(f"ALTER TABLE jobs ADD COLUMN {col} {col_type}")



        cursor.execute("SELECT id, location, work_arrangement, description FROM jobs")

        all_jobs = cursor.fetchall()

        for r in all_jobs:

            geo = classify_geographic_priority(r["location"] or "", r["work_arrangement"] or "", r["description"] or "")

            cursor.execute("""

                UPDATE jobs SET

                    geographic_priority = ?,

                    geographic_tier_label = ?,

                    location_eligibility_status = ?,

                    city = ?,

                    state = ?,

                    country = ?,

                    remote_eligibility = ?,

                    geo_score = ?

                WHERE id = ?

            """, (

                geo["geographic_priority"],

                geo["geographic_tier_label"],

                geo["location_eligibility_status"],

                geo["city"],

                geo["state"],

                geo["country"],

                geo["remote_eligibility"],

                geo["geo_score"],

                r["id"]

            ))

        cursor.execute("INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",

                       (geo_migration, datetime.now(timezone.utc).isoformat()))



    fresher_migration = "2026-10-23-fresher-offcampus-coverage"

    cursor.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (fresher_migration,))

    if not cursor.fetchone():

        job_columns = {row[1] for row in cursor.execute("PRAGMA table_info(jobs)").fetchall()}

        new_cols = [

            ("is_fresher", "INTEGER NOT NULL DEFAULT 0"),

            ("is_off_campus", "INTEGER NOT NULL DEFAULT 0"),

            ("is_internship", "INTEGER NOT NULL DEFAULT 0"),

            ("is_walkin", "INTEGER NOT NULL DEFAULT 0"),

            ("min_experience_years", "REAL"),

            ("max_experience_years", "REAL"),

        ]

        for col_name, col_def in new_cols:

            if col_name not in job_columns:

                cursor.execute(f"ALTER TABLE jobs ADD COLUMN {col_name} {col_def}")



        cursor.execute("SELECT id, title, description, employment_type FROM jobs")

        all_jobs = cursor.fetchall()

        for r in all_jobs:

            attrs = detect_opportunity_attributes(r["title"] or "", r["description"] or "", r["employment_type"] or "")

            cursor.execute("""

                UPDATE jobs SET

                    is_fresher = ?,

                    is_off_campus = ?,

                    is_internship = ?,

                    is_walkin = ?,

                    min_experience_years = ?,

                    max_experience_years = ?

                WHERE id = ?

            """, (

                1 if attrs["is_fresher"] else 0,

                1 if attrs["is_off_campus"] else 0,

                1 if attrs["is_internship"] else 0,

                1 if attrs["is_walkin"] else 0,

                attrs["min_experience_years"],

                attrs["max_experience_years"],

                r["id"]

            ))

        cursor.execute("INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",

                       (fresher_migration, datetime.now(timezone.utc).isoformat()))



    inbox_migration = "2026-10-23-unified-inbox-telegram"

    cursor.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (inbox_migration,))

    if not cursor.fetchone():

        cursor.execute("INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",

                       (inbox_migration, datetime.now(timezone.utc).isoformat()))



    sources_rich_migration = "2026-10-24-community-sources-rich-metadata"

    cursor.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (sources_rich_migration,))

    if not cursor.fetchone():

        existing_cols = {row[1] for row in cursor.execute("PRAGMA table_info(community_sources)").fetchall()}

        new_cols = [

            ("chat_username", "TEXT DEFAULT ''"),

            ("is_public", "INTEGER NOT NULL DEFAULT 0"),

            ("is_member", "INTEGER NOT NULL DEFAULT 0"),

            ("can_receive_messages", "INTEGER NOT NULL DEFAULT 0"),

            ("bot_role", "TEXT DEFAULT 'unknown'"),

            ("last_message_at", "TEXT DEFAULT ''"),

            ("last_message_excerpt", "TEXT DEFAULT ''"),

            ("setup_instructions", "TEXT DEFAULT ''"),

            ("diagnosis", "TEXT DEFAULT ''"),

        ]

        for col_name, col_def in new_cols:

            if col_name not in existing_cols:

                cursor.execute(f"ALTER TABLE community_sources ADD COLUMN {col_name} {col_def}")

        cursor.execute("INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",

                       (sources_rich_migration, datetime.now(timezone.utc).isoformat()))



    phase1_migration = "2026-10-24-phase1-canonical-verification-and-source-registry"

    cursor.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (phase1_migration,))

    if not cursor.fetchone():

        now_utc = datetime.now(timezone.utc).isoformat()

        cursor.execute("UPDATE jobs SET verification_status = 'PENDING_VERIFICATION' WHERE verification_status = 'UNVERIFIED'")

        cursor.execute("UPDATE jobs SET verification_status = 'VERIFICATION_ERROR' WHERE verification_status = 'STATUS_UNKNOWN'")



        default_sources = [

            ("unstop-public-api", "Unstop Public API", "PUBLIC_AGGREGATOR", "UNSTOP", "https://unstop.com/api/public/opportunity/search-result", "API"),

            ("remotive-public-api", "Remotive Public API", "PUBLIC_AGGREGATOR", "REMOTIVE", "https://remotive.com/api/remote-jobs", "API"),

            ("jobicy-public-api", "Jobicy Public API", "PUBLIC_AGGREGATOR", "JOBICY", "https://jobicy.com/api/v2/remote-jobs", "API"),

            ("arbeitnow-public-api", "Arbeitnow Public API", "PUBLIC_AGGREGATOR", "ARBEITNOW", "https://www.arbeitnow.com/api/job-board-api", "API"),

            ("remoteok-public-api", "RemoteOK Public API", "PUBLIC_AGGREGATOR", "REMOTEOK", "https://remoteok.com/api", "API"),

            ("employer-direct-verified", "Employer Direct Verified Feed", "VERIFIED_FEED", "EMPLOYER_DIRECT", "", "VERIFIED_FEED"),

        ]

        for sid, sname, scat, stype, send, smeth in default_sources:

            cursor.execute("""

                INSERT INTO job_sources (

                    source_id, source_name, category, source_type,

                    endpoint_or_board_id, access_method, is_configured, is_enabled,

                    health_status, created_at, updated_at

                ) VALUES (?, ?, ?, ?, ?, ?, 1, 1, 'UNKNOWN', ?, ?)

                ON CONFLICT(source_id) DO NOTHING

            """, (sid, sname, scat, stype, send, smeth, now_utc, now_utc))



        employer_sources_file = current_data_dir() / "employer_sources.json"

        if not employer_sources_file.exists():

            from pathlib import Path

            fallback_file = Path(__file__).resolve().parent.parent.parent / "data" / "employer_sources.json"

            if fallback_file.exists():

                employer_sources_file = fallback_file

        if employer_sources_file.exists():

            try:

                with open(employer_sources_file, "r", encoding="utf-8") as f:

                    employer_sources = json.load(f)

                for emp in employer_sources:

                    s_id = f"employer-{emp.get('id', emp.get('board_id', 'unknown'))}"

                    ats = str(emp.get("ats_provider") or "ATS").upper()

                    cursor.execute("""

                        INSERT INTO job_sources (

                            source_id, source_name, category, source_type,

                            endpoint_or_board_id, access_method, is_configured, is_enabled,

                            health_status, created_at, updated_at

                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'UNKNOWN', ?, ?)

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

                        now_utc,

                        now_utc

                    ))

            except Exception:

                pass



        cursor.execute("INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",

                       (phase1_migration, now_utc))



    phase2_learning_migration = "2026-10-24-phase2-learning-resources-metadata"

    cursor.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (phase2_learning_migration,))

    if not cursor.fetchone():

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

                cursor.execute(f"ALTER TABLE learning_resources ADD COLUMN {col_name} {col_def}")



        cursor.execute("CREATE INDEX IF NOT EXISTS idx_learning_skill ON learning_resources(skill_tag)")

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_learning_difficulty ON learning_resources(difficulty_level)")

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_learning_completed ON learning_resources(is_completed)")

        cursor.execute("INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",

                       (phase2_learning_migration, now_utc))



    # Auto-seed curated learning resources if collection is empty

    cursor.execute("SELECT COUNT(*) as cnt FROM learning_resources")

    if cursor.fetchone()["cnt"] == 0:

        try:

            from careerorbit.prep.curated_resources import seed_curated_learning_resources

            seed_curated_learning_resources(conn=conn)

        except Exception:

            pass



    phase3_planner_migration = "2026-10-24-phase3-daily-study-planner"

    cursor.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (phase3_planner_migration,))

    if not cursor.fetchone():

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

                       (phase3_planner_migration, now_utc))



    phase4_assessment_migration = "2026-10-24-phase4-assessment-sandbox"

    cursor.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (phase4_assessment_migration,))

    if not cursor.fetchone():

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

                       (phase4_assessment_migration, now_utc))



    # Auto-seed assessment challenges if collection is empty

    cursor.execute("SELECT COUNT(*) as cnt FROM assessment_challenges")

    if cursor.fetchone()["cnt"] == 0:

        try:

            from careerorbit.prep.assessment_sandbox import seed_assessment_challenges

            seed_assessment_challenges(conn=conn)

        except Exception:

            pass



    phase5_interview_migration = "2026-10-24-phase5-interview-prep-sessions"

    cursor.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (phase5_interview_migration,))

    if not cursor.fetchone():

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

                       (phase5_interview_migration, now_utc))



    role_workspace_migration = "2026-10-26-role-interview-workspaces-v1"

    cursor.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (role_workspace_migration,))

    if not cursor.fetchone():

        now_utc = datetime.now(timezone.utc).isoformat()

        cursor.execute("""

        CREATE TABLE IF NOT EXISTS interview_prep_workspaces (

            workspace_id TEXT PRIMARY KEY,

            source_type TEXT NOT NULL CHECK(source_type IN ('ROLE', 'JOB_DESCRIPTION')),

            role_title TEXT NOT NULL,

            job_description TEXT NOT NULL DEFAULT '',

            briefing_json TEXT NOT NULL DEFAULT '{}',

            candidate_notes TEXT NOT NULL DEFAULT '',

            confidence_rating INTEGER NOT NULL DEFAULT 0 CHECK(confidence_rating BETWEEN 0 AND 5),

            checklist_json TEXT NOT NULL DEFAULT '[]',

            answer_drafts_json TEXT NOT NULL DEFAULT '{}',

            disclaimer TEXT NOT NULL DEFAULT '',

            created_at TEXT NOT NULL,

            updated_at TEXT NOT NULL

        )

        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_interview_workspace_updated ON interview_prep_workspaces(updated_at)")

        cursor.execute("INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",

                       (role_workspace_migration, now_utc))




    app_details_migration = '2026-11-03-application-crud-details-v1'
    cursor.execute('SELECT 1 FROM schema_migrations WHERE version = ?', (app_details_migration,))
    if not cursor.fetchone():
        now_utc = datetime.now(timezone.utc).isoformat()
        app_columns = {row[1] for row in cursor.execute('PRAGMA table_info(applications)').fetchall()}
        for col_name, col_def in (
            ('recruiter_name', "TEXT DEFAULT ''"),
            ('recruiter_email', "TEXT DEFAULT ''"),
            ('interview_date', "TEXT DEFAULT ''"),
            ('deadline', "TEXT DEFAULT ''"),
        ):
            if col_name not in app_columns:
                cursor.execute(f'ALTER TABLE applications ADD COLUMN {col_name} {col_def}')
        cursor.execute('INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)',
                       (app_details_migration, now_utc))

    conn.commit()

    conn.close()



# ----------------- Job CRUD -----------------



def save_job(job: Job, conn: Optional[sqlite3.Connection] = None) -> int:

    should_close = False
    if conn is None:
        conn = get_connection()
        should_close = True

    cursor = conn.cursor()



    score_breakdown_json = json.dumps(job.score_breakdown.model_dump()) if job.score_breakdown else "{}"

    req_skills_json = json.dumps(job.required_skills)

    pref_skills_json = json.dumps(job.preferred_skills)

    supp_skills_json = json.dumps(job.supported_skills)

    miss_skills_json = json.dumps(job.missing_skills)

    learn_skills_json = json.dumps(job.learnable_skills)

    disq_json = json.dumps(job.disqualifiers)



    geo = classify_geographic_priority(job.location or "", job.work_arrangement or "", job.description or "")

    geo_p = getattr(job, "geographic_priority", None) or geo["geographic_priority"]

    geo_label = getattr(job, "geographic_tier_label", None) or geo["geographic_tier_label"]

    loc_status = getattr(job, "location_eligibility_status", None) or geo["location_eligibility_status"]

    city = getattr(job, "city", None) or geo["city"]

    state = getattr(job, "state", None) or geo["state"]

    country = getattr(job, "country", None) or geo["country"]

    remote_elig = getattr(job, "remote_eligibility", None) or geo["remote_eligibility"]

    geo_score = getattr(job, "geo_score", None) if getattr(job, "geo_score", None) is not None else geo["geo_score"]



    attrs = detect_opportunity_attributes(job.title or "", job.description or "", job.employment_type or "")

    is_fresher = 1 if (getattr(job, "is_fresher", False) or attrs["is_fresher"]) else 0

    is_off_campus = 1 if (getattr(job, "is_off_campus", False) or attrs["is_off_campus"]) else 0

    is_internship = 1 if (getattr(job, "is_internship", False) or attrs["is_internship"]) else 0

    is_walkin = 1 if (getattr(job, "is_walkin", False) or attrs["is_walkin"]) else 0

    min_exp = getattr(job, "min_experience_years", None) if getattr(job, "min_experience_years", None) is not None else attrs["min_experience_years"]

    max_exp = getattr(job, "max_experience_years", None) if getattr(job, "max_experience_years", None) is not None else attrs["max_experience_years"]



    career_cat = getattr(job, "career_category", None)

    if not career_cat:

        from careerorbit.career_priorities import get_category_by_legacy_code

        c_obj = get_category_by_legacy_code(job.priority_category)

        career_cat = c_obj.id if c_obj else ""



    cursor.execute("""

        INSERT INTO jobs (

            job_uid, employer, title, normalized_title, job_id_or_req,

            priority_category, priority_label, career_category, location, work_arrangement,

            employment_type, salary, shift, posting_date, posting_date_confidence, deadline,

            official_url, official_listing_url, application_url, discovery_url, canonical_url,

            discovery_source, verification_source,

            verification_status, verification_notes, match_score, match_tier,

            score_breakdown, required_skills, preferred_skills, supported_skills,

            missing_skills, learnable_skills, disqualifiers, evidence_notes,

            recommended_action, description, first_discovered_at, last_verified_at,

            last_observed_status, last_observed_status_at,

            record_state, integrity_notes,

            geographic_priority, geographic_tier_label, location_eligibility_status,

            city, state, country, remote_eligibility, geo_score,

            is_fresher, is_off_campus, is_internship, is_walkin, min_experience_years, max_experience_years

        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

        ON CONFLICT(job_uid) DO UPDATE SET

            employer=excluded.employer,

            title=excluded.title,

            priority_category=excluded.priority_category,

            priority_label=excluded.priority_label,

            career_category=excluded.career_category,

            location=excluded.location,

            work_arrangement=excluded.work_arrangement,

            employment_type=excluded.employment_type,

            posting_date=excluded.posting_date,

            posting_date_confidence=excluded.posting_date_confidence,

            deadline=excluded.deadline,

            official_url=excluded.official_url,

            official_listing_url=excluded.official_listing_url,

            application_url=excluded.application_url,

            discovery_url=excluded.discovery_url,

            canonical_url=excluded.canonical_url,

            discovery_source=excluded.discovery_source,

            verification_source=excluded.verification_source,

            verification_status=CASE

                WHEN jobs.verification_status IN ('VERIFIED_OPEN', 'VERIFIED_CLOSED')

                 AND excluded.verification_status IN ('PENDING_VERIFICATION', 'UNVERIFIED', 'VERIFICATION_ERROR', 'STATUS_UNKNOWN')

                THEN jobs.verification_status

                ELSE excluded.verification_status

            END,

            verification_notes=CASE

                WHEN jobs.verification_status IN ('VERIFIED_OPEN', 'VERIFIED_CLOSED')

                 AND excluded.verification_status IN ('PENDING_VERIFICATION', 'UNVERIFIED', 'VERIFICATION_ERROR', 'STATUS_UNKNOWN')

                THEN jobs.verification_notes

                ELSE excluded.verification_notes

            END,

            last_observed_status=excluded.last_observed_status,

            last_observed_status_at=excluded.last_observed_status_at,

            match_score=excluded.match_score,

            match_tier=excluded.match_tier,

            score_breakdown=excluded.score_breakdown,

            supported_skills=excluded.supported_skills,

            missing_skills=excluded.missing_skills,

            learnable_skills=excluded.learnable_skills,

            disqualifiers=excluded.disqualifiers,

            required_skills=excluded.required_skills,

            description=excluded.description,

            evidence_notes=excluded.evidence_notes,

            recommended_action=excluded.recommended_action,

            last_verified_at=excluded.last_verified_at,

            geographic_priority=excluded.geographic_priority,

            geographic_tier_label=excluded.geographic_tier_label,

            location_eligibility_status=excluded.location_eligibility_status,

            city=excluded.city,

            state=excluded.state,

            country=excluded.country,

            remote_eligibility=excluded.remote_eligibility,

            geo_score=excluded.geo_score,

            is_fresher=excluded.is_fresher,

            is_off_campus=excluded.is_off_campus,

            is_internship=excluded.is_internship,

            is_walkin=excluded.is_walkin,

            min_experience_years=excluded.min_experience_years,

            max_experience_years=excluded.max_experience_years

    """, (

        job.job_uid, job.employer, job.title, job.normalized_title, job.job_id_or_req,

        job.priority_category, job.priority_label, career_cat, job.location, job.work_arrangement,

        job.employment_type, job.salary, job.shift, job.posting_date, job.posting_date_confidence, job.deadline,

        job.official_url, job.official_listing_url, job.application_url, job.discovery_url, job.canonical_url,

        job.discovery_source, job.verification_source, job.verification_status.value,

        job.verification_notes, job.match_score, job.match_tier.value,

        score_breakdown_json, req_skills_json, pref_skills_json, supp_skills_json,

        miss_skills_json, learn_skills_json, disq_json, job.evidence_notes,

        job.recommended_action, job.description, job.first_discovered_at, job.last_verified_at,

        job.last_observed_status, job.last_observed_status_at,

        "QUARANTINED" if job.discovery_source in ("Test", "Test Unit") or job.discovery_source in LEGACY_UNSUPPORTED_PORTAL_SOURCES else "DISCOVERY_LEAD",

        ("Test fixture source; retained for audit and never returned as a lead." if job.discovery_source in ("Test", "Test Unit") else

         "Legacy portal source without raw posting evidence; quarantined pending review." if job.discovery_source in LEGACY_UNSUPPORTED_PORTAL_SOURCES else ""),

        geo_p, geo_label, loc_status, city, state, country, remote_elig, geo_score,

        is_fresher, is_off_campus, is_internship, is_walkin, min_exp, max_exp

    ))



    if should_close:
        conn.commit()

    job_id = cursor.lastrowid

    if not job_id:

        cursor.execute("SELECT id FROM jobs WHERE job_uid = ?", (job.job_uid,))

        row = cursor.fetchone()

        job_id = row["id"] if row else 0

    if should_close:
        conn.close()

    return job_id



def get_job_by_url(url: str) -> Optional[Dict[str, Any]]:

    """Look up an existing job by any matching URL representation."""

    if not url:

        return None

    clean_url = url.strip()

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("""

        SELECT * FROM jobs

        WHERE official_url = ? OR official_listing_url = ? OR application_url = ? OR canonical_url = ? OR discovery_url = ?

        LIMIT 1

    """, (clean_url, clean_url, clean_url, clean_url, clean_url))

    row = cursor.fetchone()

    conn.close()

    return _row_to_job_dict(row) if row else None



def get_job_by_uid(job_uid: str) -> Optional[Dict[str, Any]]:

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("SELECT * FROM jobs WHERE job_uid = ?", (job_uid,))

    row = cursor.fetchone()

    conn.close()

    return _row_to_job_dict(row) if row else None



def get_job_by_id(job_id: int) -> Optional[Dict[str, Any]]:

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))

    row = cursor.fetchone()

    conn.close()

    return _row_to_job_dict(row) if row else None



def toggle_save_job(job_id: int, notes: str = "") -> bool:

    """Toggles bookmark status of a job. Returns True if now saved, False if removed."""

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("SELECT 1 FROM saved_jobs WHERE job_id = ?", (job_id,))

    if cursor.fetchone():

        cursor.execute("DELETE FROM saved_jobs WHERE job_id = ?", (job_id,))

        is_saved = False

    else:

        cursor.execute(

            "INSERT INTO saved_jobs (job_id, saved_at, notes) VALUES (?, ?, ?)",

            (job_id, datetime.now(timezone.utc).isoformat(), notes)

        )

        is_saved = True

    conn.commit()

    conn.close()

    return is_saved



def is_job_saved(job_id: int) -> bool:

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("SELECT 1 FROM saved_jobs WHERE job_id = ?", (job_id,))

    saved = cursor.fetchone() is not None

    conn.close()

    return saved



def list_jobs(

    priority: Optional[int] = None,

    category: Optional[str] = None,

    geographic_priority: Optional[int] = None,

    match_tier: Optional[str] = None,

    verification_status: Optional[str] = None,

    location_search: Optional[str] = None,

    city: Optional[str] = None,

    state: Optional[str] = None,

    country: Optional[str] = None,

    remote_eligibility: Optional[str] = None,

    location_eligibility_status: Optional[str] = None,

    search: Optional[str] = None,

    min_score: Optional[float] = None,

    work_arrangement: Optional[str] = None,

    employment_type: Optional[str] = None,

    employer: Optional[str] = None,

    discovery_source: Optional[str] = None,

    is_fresher: Optional[bool] = None,

    is_off_campus: Optional[bool] = None,

    is_internship: Optional[bool] = None,

    recency_days: Optional[int] = None,

    include_quarantined: bool = False,

    saved_only: bool = False,

    sort_by: str = "priority_first",

    limit: int = 100,

    offset: int = 0,

    profile_id: str = "default",

    career_preference_order: Optional[List[str]] = None,

) -> List[Dict[str, Any]]:

    conn = get_connection()

    cursor = conn.cursor()



    if saved_only:

        query = "SELECT j.* FROM jobs j INNER JOIN saved_jobs s ON j.id = s.job_id WHERE 1=1"

        if not include_quarantined:

            query += " AND COALESCE(j.record_state, 'DISCOVERY_LEAD') != 'QUARANTINED' AND j.discovery_source NOT IN ('Test','Test Unit')"

    else:

        if include_quarantined:

            query = "SELECT * FROM jobs WHERE 1=1"

        else:

            query = "SELECT * FROM jobs WHERE COALESCE(record_state, 'DISCOVERY_LEAD') != 'QUARANTINED' AND discovery_source NOT IN ('Test','Test Unit')"



    params: list[Any] = []

    prefix = "j." if saved_only else ""



    if priority is not None and not hasattr(priority, "default"):

        try:

            p_val = int(priority)

            if p_val > 0:

                query += f" AND {prefix}priority_category = ?"

                params.append(p_val)

        except (ValueError, TypeError):

            pass

    if category is not None and not hasattr(category, "default"):

        cat_str = str(category).strip().lower()

        if cat_str:

            from careerorbit.career_priorities import get_category_by_id

            cat_match = get_category_by_id(cat_str)

            if cat_match:

                query += f" AND ({prefix}career_category = ? OR {prefix}priority_category = ?)"

                params.extend([cat_match.id, cat_match.legacy_code])

            else:

                query += f" AND {prefix}career_category = ?"

                params.append(cat_str)

    if geographic_priority is not None and not hasattr(geographic_priority, "default"):

        try:

            g_val = int(geographic_priority)

            if g_val > 0:

                query += f" AND {prefix}geographic_priority = ?"

                params.append(g_val)

        except (ValueError, TypeError):

            pass

    if match_tier:

        query += f" AND {prefix}match_tier = ?"

        params.append(match_tier)

    if verification_status:

        v_norm = str(verification_status).strip().upper()

        if v_norm in ("UNVERIFIED", "PENDING_VERIFICATION"):

            query += f" AND {prefix}verification_status IN ('PENDING_VERIFICATION', 'UNVERIFIED')"

        elif v_norm in ("STATUS_UNKNOWN", "VERIFICATION_ERROR"):

            query += f" AND {prefix}verification_status IN ('VERIFICATION_ERROR', 'STATUS_UNKNOWN')"

        else:

            query += f" AND {prefix}verification_status = ?"

            params.append(v_norm)

    if location_search:

        query += f" AND {prefix}location LIKE ?"

        params.append(f"%{location_search}%")

    if city:

        city_clean = city.strip().lower()

        synonyms = get_city_synonyms(city_clean)

        clauses = []

        for s in synonyms:

            clauses.append(f"lower({prefix}city) LIKE ? OR lower({prefix}location) LIKE ?")

            params.extend([f"%{s}%", f"%{s}%"])

        if clauses:

            query += f" AND ({' OR '.join(clauses)})"

    if state:

        query += f" AND lower({prefix}state) LIKE ?"

        params.append(f"%{state.strip().lower()}%")

    if country:

        query += f" AND lower({prefix}country) LIKE ?"

        params.append(f"%{country.strip().lower()}%")

    if remote_eligibility:

        query += f" AND {prefix}remote_eligibility = ?"

        params.append(remote_eligibility)

    if location_eligibility_status:

        query += f" AND {prefix}location_eligibility_status = ?"

        params.append(location_eligibility_status)

    if employment_type:

        query += f" AND lower({prefix}employment_type) LIKE ?"

        params.append(f"%{employment_type.strip().lower()}%")

    if employer:

        query += f" AND lower({prefix}employer) LIKE ?"

        params.append(f"%{employer.strip().lower()}%")

    if discovery_source:

        query += f" AND lower({prefix}discovery_source) LIKE ?"

        params.append(f"%{discovery_source.strip().lower()}%")

    if is_fresher is not None:

        query += f" AND {prefix}is_fresher = ?"

        params.append(1 if is_fresher else 0)

    if is_off_campus is not None:

        query += f" AND {prefix}is_off_campus = ?"

        params.append(1 if is_off_campus else 0)

    if is_internship is not None:

        query += f" AND {prefix}is_internship = ?"

        params.append(1 if is_internship else 0)

    if recency_days is not None and recency_days > 0:

        cutoff = (datetime.now(timezone.utc) - timedelta(days=recency_days)).isoformat()

        query += f" AND {prefix}posting_date IS NOT NULL AND {prefix}posting_date >= ?"

        params.append(cutoff)

    if work_arrangement:

        query += f" AND lower({prefix}work_arrangement) LIKE ?"

        params.append(f"%{work_arrangement.lower()}%")

    if min_score is not None and min_score > 0:

        query += f" AND {prefix}match_score >= ?"

        params.append(min_score)

    if search:

        search_term = f"%{search.strip()}%"

        query += f" AND ({prefix}title LIKE ? OR {prefix}employer LIKE ? OR {prefix}description LIKE ? OR {prefix}location LIKE ? OR {prefix}city LIKE ?)"

        params.extend([search_term, search_term, search_term, search_term, search_term])



    # Sorting with personalized career preference ranking

    from careerorbit.career_priorities import get_personalized_priority_order_sql

    priority_order = get_personalized_priority_order_sql(

        preferences=career_preference_order,

        profile_id=profile_id,

        prefix=prefix

    )

    if sort_by == "score_desc":

        query += f" ORDER BY {prefix}match_score DESC, {priority_order}, {prefix}geographic_priority ASC, {prefix}id DESC"

    elif sort_by == "geo_first":

        query += f" ORDER BY {prefix}geographic_priority ASC, {priority_order}, {prefix}match_score DESC, ({prefix}posting_date IS NULL) ASC, {prefix}posting_date DESC"

    elif sort_by == "date_desc":

        query += f" ORDER BY ({prefix}posting_date IS NULL) ASC, {prefix}posting_date DESC, {prefix}match_score DESC"

    elif sort_by == "employer_asc":

        query += f" ORDER BY {prefix}employer ASC, {prefix}match_score DESC"

    else:  # priority_first (default: personalized career priority rank first, then geographic priority, then score, then freshness)

        query += f" ORDER BY {priority_order}, {prefix}geographic_priority ASC, {prefix}match_score DESC, ({prefix}posting_date IS NULL) ASC, {prefix}posting_date DESC"



    query += " LIMIT ? OFFSET ?"

    params.extend([limit, offset])



    cursor.execute(query, params)

    rows = cursor.fetchall()



    cursor.execute("SELECT job_id FROM saved_jobs")

    saved_ids = {r[0] for r in cursor.fetchall()}

    conn.close()



    result = []

    for r in rows:

        d = _row_to_job_dict(r, profile_id=profile_id, career_preference_order=career_preference_order)

        d["is_saved"] = d.get("id") in saved_ids

        result.append(d)

    return result






def _row_to_job_dict(

    row: sqlite3.Row,

    profile_id: str = "default",

    career_preference_order: Optional[List[str]] = None

) -> Dict[str, Any]:

    d = dict(row)

    for col in ["score_breakdown", "required_skills", "preferred_skills", "supported_skills",

                "missing_skills", "learnable_skills", "disqualifiers"]:

        if d.get(col):

            try:

                d[col] = json.loads(d[col])

            except Exception:

                d[col] = []

        else:

            d[col] = [] if "skills" in col or "disqualifiers" in col else {}

    d["geographic_priority"] = d.get("geographic_priority") if d.get("geographic_priority") is not None else 1

    d["geographic_tier_label"] = d.get("geographic_tier_label") or "Priority 1 — South India & India Remote"

    d["location_eligibility_status"] = d.get("location_eligibility_status") or "VERIFIED_INDIA_ELIGIBLE"

    d["city"] = d.get("city") or ""

    d["state"] = d.get("state") or ""

    d["country"] = d.get("country") or "India"

    d["remote_eligibility"] = d.get("remote_eligibility") or "INDIA_PERMITTED"

    d["geo_score"] = d.get("geo_score") if d.get("geo_score") is not None else 10.0

    d["is_fresher"] = bool(d.get("is_fresher"))

    d["is_off_campus"] = bool(d.get("is_off_campus"))

    d["is_internship"] = bool(d.get("is_internship"))

    d["is_walkin"] = bool(d.get("is_walkin"))

    d["min_experience_years"] = d.get("min_experience_years")

    d["max_experience_years"] = d.get("max_experience_years")



    # Add career category and personalized preference rank

    from careerorbit.career_priorities import get_category_by_legacy_code, get_preference_rank

    if not d.get("career_category"):

        c_obj = get_category_by_legacy_code(d.get("priority_category", 0))

        d["career_category"] = c_obj.id if c_obj else None

    d["preference_rank"] = get_preference_rank(

        d, profile_id=profile_id, preferences=career_preference_order

    )

    return d



def get_job_stats() -> Dict[str, Any]:

    conn = get_connection()

    cursor = conn.cursor()



    cursor.execute("SELECT COUNT(*) as total FROM jobs WHERE COALESCE(record_state, 'DISCOVERY_LEAD') != 'QUARANTINED'")

    total_jobs = cursor.fetchone()["total"]



    cursor.execute("SELECT COUNT(*) as verified_open FROM jobs WHERE verification_status = 'VERIFIED_OPEN' AND COALESCE(record_state, 'DISCOVERY_LEAD') != 'QUARANTINED'")

    verified_open = cursor.fetchone()["verified_open"]



    cursor.execute("SELECT COUNT(*) as verified_closed FROM jobs WHERE verification_status IN ('VERIFIED_CLOSED', 'EXPIRED') AND COALESCE(record_state, 'DISCOVERY_LEAD') != 'QUARANTINED'")

    verified_closed = cursor.fetchone()["verified_closed"]



    cursor.execute("SELECT COUNT(*) as pending_verification FROM jobs WHERE verification_status IN ('PENDING_VERIFICATION', 'UNVERIFIED') AND COALESCE(record_state, 'DISCOVERY_LEAD') != 'QUARANTINED'")

    pending_verification = cursor.fetchone()["pending_verification"]



    cursor.execute("SELECT COUNT(*) as broken_link FROM jobs WHERE verification_status = 'BROKEN_LINK' AND COALESCE(record_state, 'DISCOVERY_LEAD') != 'QUARANTINED'")

    broken_link = cursor.fetchone()["broken_link"]



    cursor.execute("SELECT COUNT(*) as suspicious FROM jobs WHERE verification_status = 'SUSPICIOUS' AND COALESCE(record_state, 'DISCOVERY_LEAD') != 'QUARANTINED'")

    suspicious = cursor.fetchone()["suspicious"]



    cursor.execute("SELECT COUNT(*) as verification_error FROM jobs WHERE verification_status IN ('VERIFICATION_ERROR', 'STATUS_UNKNOWN') AND COALESCE(record_state, 'DISCOVERY_LEAD') != 'QUARANTINED'")

    verification_error = cursor.fetchone()["verification_error"]



    unverified_jobs = pending_verification

    expired_jobs = verified_closed



    cursor.execute("SELECT COUNT(*) as strong_matches FROM jobs WHERE match_tier = 'Strong match' AND COALESCE(record_state, 'DISCOVERY_LEAD') != 'QUARANTINED'")

    strong_matches = cursor.fetchone()["strong_matches"]



    cursor.execute("SELECT COUNT(*) as reasonable_matches FROM jobs WHERE match_tier = 'Reasonable match' AND COALESCE(record_state, 'DISCOVERY_LEAD') != 'QUARANTINED'")

    reasonable_matches = cursor.fetchone()["reasonable_matches"]



    cursor.execute("SELECT COUNT(*) as stretch FROM jobs WHERE match_tier = 'Stretch opportunity' AND COALESCE(record_state, 'DISCOVERY_LEAD') != 'QUARANTINED'")

    stretch = cursor.fetchone()["stretch"]



    # Fresher & Early-Career Breakdown

    cursor.execute("SELECT COUNT(*) as fresher_cnt FROM jobs WHERE is_fresher = 1 AND COALESCE(record_state, 'DISCOVERY_LEAD') != 'QUARANTINED'")

    fresher_count = cursor.fetchone()["fresher_cnt"]



    cursor.execute("SELECT COUNT(*) as off_campus_cnt FROM jobs WHERE is_off_campus = 1 AND COALESCE(record_state, 'DISCOVERY_LEAD') != 'QUARANTINED'")

    off_campus_count = cursor.fetchone()["off_campus_cnt"]



    cursor.execute("SELECT COUNT(*) as internship_cnt FROM jobs WHERE is_internship = 1 AND COALESCE(record_state, 'DISCOVERY_LEAD') != 'QUARANTINED'")

    internship_count = cursor.fetchone()["internship_cnt"]



    # Sources & Cities Breakdown

    cursor.execute("SELECT discovery_source, COUNT(*) as cnt FROM jobs WHERE COALESCE(record_state, 'DISCOVERY_LEAD') != 'QUARANTINED' GROUP BY discovery_source ORDER BY cnt DESC")

    sources_breakdown = {r["discovery_source"]: r["cnt"] for r in cursor.fetchall()}



    cursor.execute("SELECT city, COUNT(*) as cnt FROM jobs WHERE city != '' AND COALESCE(record_state, 'DISCOVERY_LEAD') != 'QUARANTINED' GROUP BY city ORDER BY cnt DESC LIMIT 10")

    top_cities = {r["city"]: r["cnt"] for r in cursor.fetchall()}



    # Geographic priorities

    cursor.execute("SELECT COUNT(*) as p1 FROM jobs WHERE geographic_priority = 1 AND COALESCE(record_state, 'DISCOVERY_LEAD') != 'QUARANTINED'")

    geo_p1 = cursor.fetchone()["p1"]



    cursor.execute("SELECT COUNT(*) as p2 FROM jobs WHERE geographic_priority = 2 AND COALESCE(record_state, 'DISCOVERY_LEAD') != 'QUARANTINED'")

    geo_p2 = cursor.fetchone()["p2"]



    cursor.execute("SELECT COUNT(*) as p3 FROM jobs WHERE geographic_priority = 3 AND COALESCE(record_state, 'DISCOVERY_LEAD') != 'QUARANTINED'")

    geo_p3 = cursor.fetchone()["p3"]



    # Recency windows

    now_utc = datetime.now(timezone.utc)

    t_24h = (now_utc - timedelta(days=1)).isoformat()

    t_3d = (now_utc - timedelta(days=3)).isoformat()

    t_7d = (now_utc - timedelta(days=7)).isoformat()



    cursor.execute("SELECT COUNT(*) as r24 FROM jobs WHERE posting_date IS NOT NULL AND posting_date >= ? AND COALESCE(record_state, 'DISCOVERY_LEAD') != 'QUARANTINED'", (t_24h,))

    jobs_24h = cursor.fetchone()["r24"]



    cursor.execute("SELECT COUNT(*) as r3d FROM jobs WHERE posting_date IS NOT NULL AND posting_date >= ? AND COALESCE(record_state, 'DISCOVERY_LEAD') != 'QUARANTINED'", (t_3d,))

    jobs_3d = cursor.fetchone()["r3d"]



    cursor.execute("SELECT COUNT(*) as r7d FROM jobs WHERE posting_date IS NOT NULL AND posting_date >= ? AND COALESCE(record_state, 'DISCOVERY_LEAD') != 'QUARANTINED'", (t_7d,))

    jobs_7d = cursor.fetchone()["r7d"]



    cursor.execute("SELECT COUNT(*) as pending_approvals FROM applications WHERE application_status = 'AWAITING_APPROVAL' AND candidate_review_state != 'NEEDS_CONFIRMATION'")

    pending_approvals = cursor.fetchone()["pending_approvals"]



    cursor.execute("SELECT COUNT(*) as submitted FROM applications WHERE submission_evidence_state = 'CONFIRMED_BY_CANDIDATE' AND submission_confirmed_by_user = 1")

    submitted = cursor.fetchone()["submitted"]



    cursor.execute("SELECT COUNT(*) as needs_review FROM applications WHERE candidate_review_state = 'NEEDS_CONFIRMATION'")

    applications_needing_review = cursor.fetchone()["needs_review"]



    cursor.execute("SELECT COUNT(*) as quarantined FROM jobs WHERE record_state = 'QUARANTINED'")

    quarantined = cursor.fetchone()["quarantined"]



    cursor.execute("SELECT COUNT(*) as saved FROM saved_jobs")

    saved_count = cursor.fetchone()["saved"]



    # Unified Inbox metrics

    cursor.execute("SELECT COUNT(*) as inbox_total FROM inbox_messages WHERE status != 'DISCARDED'")

    inbox_total = cursor.fetchone()["inbox_total"]



    cursor.execute("SELECT COUNT(*) as inbox_unread FROM inbox_messages WHERE status = 'NEW'")

    inbox_unread = cursor.fetchone()["inbox_unread"]



    cursor.execute("SELECT COUNT(*) as inbox_jobs FROM inbox_messages WHERE is_job_lead = 1 AND status != 'DISCARDED'")

    inbox_jobs = cursor.fetchone()["inbox_jobs"]



    conn.close()

    return {

        "total_jobs": total_jobs,

        "verified_open": verified_open,

        "verified_closed": verified_closed,

        "pending_verification": pending_verification,

        "broken_link": broken_link,

        "suspicious": suspicious,

        "verification_error": verification_error,

        "unverified_jobs": unverified_jobs,

        "expired_jobs": expired_jobs,

        "status_unknown_jobs": verification_error,

        "verification_breakdown": {

            "VERIFIED_OPEN": verified_open,

            "VERIFIED_CLOSED": verified_closed,

            "PENDING_VERIFICATION": pending_verification,

            "BROKEN_LINK": broken_link,

            "SUSPICIOUS": suspicious,

            "VERIFICATION_ERROR": verification_error,

        },

        "strong_matches": strong_matches,

        "reasonable_matches": reasonable_matches,

        "stretch_opportunities": stretch,

        "fresher_opportunities": fresher_count,

        "off_campus_drives": off_campus_count,

        "internships": internship_count,

        "sources_breakdown": sources_breakdown,

        "top_cities": top_cities,

        "geo_p1_jobs": geo_p1,

        "geo_p2_jobs": geo_p2,

        "geo_p3_jobs": geo_p3,

        "jobs_last_24h": jobs_24h,

        "jobs_last_3d": jobs_3d,

        "jobs_last_7d": jobs_7d,

        "applications_awaiting_approval": pending_approvals,

        "confirmed_submissions": submitted,

        "applications_needing_review": applications_needing_review,

        "quarantined_jobs": quarantined,

        "saved_jobs": saved_count,

        "inbox_total": inbox_total,

        "inbox_unread": inbox_unread,

        "inbox_jobs": inbox_jobs,

    }



# ----------------- Application CRUD -----------------



def create_or_update_application(app: Application) -> int:

    conn = get_connection()

    cursor = conn.cursor()



    answers_json = json.dumps(app.application_answers)

    outreach = dict(app.outreach_messages)
    for _k in ('recruiter_name', 'recruiter_email', 'interview_date', 'deadline'):
        _v = getattr(app, _k, None)
        if _v:
            outreach[_k] = _v
    outreach_json = json.dumps(outreach)



    cursor.execute("""

        INSERT INTO applications (

            job_id, selected_resume_path_pdf, selected_resume_path_docx,

            resume_type, resume_status, application_status, submission_confirmed_by_user,

            submission_date, recruiter_outreach_status, interview_stage,

            follow_up_date, cover_letter_text, application_answers, outreach_messages,

            notes, next_action, created_at, updated_at

        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

        ON CONFLICT(job_id) DO UPDATE SET

            selected_resume_path_pdf=coalesce(excluded.selected_resume_path_pdf, applications.selected_resume_path_pdf),

            selected_resume_path_docx=coalesce(excluded.selected_resume_path_docx, applications.selected_resume_path_docx),

            resume_type=excluded.resume_type,

            resume_status=excluded.resume_status,

            application_status=excluded.application_status,

            submission_confirmed_by_user=excluded.submission_confirmed_by_user,

            submission_date=excluded.submission_date,

            cover_letter_text=coalesce(excluded.cover_letter_text, applications.cover_letter_text),

            application_answers=excluded.application_answers,

            outreach_messages=excluded.outreach_messages,

            next_action=excluded.next_action,

            updated_at=excluded.updated_at

    """, (

        app.job_id, app.selected_resume_path_pdf, app.selected_resume_path_docx,

        app.resume_type, app.resume_status, app.application_status.value,

        1 if app.submission_confirmed_by_user else 0, app.submission_date,

        app.recruiter_outreach_status.value, app.interview_stage, app.follow_up_date,

        app.cover_letter_text, answers_json, outreach_json, app.notes, app.next_action,

        app.created_at, app.updated_at

    ))



    conn.commit()

    app_id = cursor.lastrowid

    if not app_id:

        cursor.execute("SELECT id FROM applications WHERE job_id = ?", (app.job_id,))

        row = cursor.fetchone()

        app_id = row["id"] if row else 0



    conn.close()

    return app_id



def get_application_by_job_id(job_id: int) -> Optional[Dict[str, Any]]:

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("SELECT * FROM applications WHERE job_id = ?", (job_id,))

    row = cursor.fetchone()

    conn.close()

    return _row_to_app_dict(row) if row else None



def list_applications() -> List[Dict[str, Any]]:

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("""

        SELECT a.*, j.employer, j.title, j.priority_label, j.location, j.official_url,

               j.official_listing_url, j.application_url, j.match_score, j.match_tier,

               j.verification_status, j.record_state, j.integrity_notes

        FROM applications a

        JOIN jobs j ON a.job_id = j.id

        ORDER BY a.updated_at DESC

    """)

    rows = cursor.fetchall()

    conn.close()

    return [_row_to_app_dict(r) for r in rows]



def confirm_user_submission(job_id: int, notes: str = "Submission confirmed by candidate.") -> bool:

    """Security Approval Gate: explicitly confirms application submission."""

    conn = get_connection()

    cursor = conn.cursor()

    now_iso = datetime.now(timezone.utc).isoformat()

    cursor.execute("""

        UPDATE applications

        SET submission_confirmed_by_user = 1,

            application_status = 'SUBMITTED',

            candidate_review_state = 'CURRENT',

            submission_evidence_state = 'CONFIRMED_BY_CANDIDATE',

            submission_date = ?,

            notes = ?,

            next_action = 'Follow up with recruiter and prepare for technical interview',

            updated_at = ?

        WHERE job_id = ? AND EXISTS (

            SELECT 1 FROM jobs j WHERE j.id = applications.job_id

              AND COALESCE(j.record_state, 'DISCOVERY_LEAD') != 'QUARANTINED'

              AND j.verification_status = 'VERIFIED_OPEN'

              AND COALESCE(j.official_listing_url, '') != ''

              AND COALESCE(j.application_url, '') != ''

        )

          AND candidate_review_state = 'CURRENT'

          AND application_status = 'AWAITING_APPROVAL'

    """, (now_iso, notes, now_iso, job_id))

    success = cursor.rowcount > 0

    if success:

        cursor.execute("SELECT id FROM applications WHERE job_id = ?", (job_id,))

        app_row = cursor.fetchone()

        if app_row:

            record_application_transition(

                application_id=app_row["id"],

                previous_status="AWAITING_APPROVAL",

                new_status="APPLIED",

                event_source="USER_CONFIRMATION",

                actor="CANDIDATE",

                notes=notes,

                evidence="Candidate confirmed manual submission on official employer portal.",

                conn=conn

            )

    conn.commit()

    conn.close()

    return success



def get_application_by_id(app_id: int) -> Optional[Dict[str, Any]]:

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("""

        SELECT a.*, j.employer, j.title, j.priority_label, j.location, j.official_url,

               j.official_listing_url, j.application_url, j.match_score, j.match_tier,

               j.verification_status, j.record_state, j.integrity_notes

        FROM applications a

        JOIN jobs j ON a.job_id = j.id

        WHERE a.id = ?

    """, (app_id,))

    row = cursor.fetchone()

    conn.close()

    return _row_to_app_dict(row) if row else None



def record_application_transition(

    application_id: int,

    previous_status: str,

    new_status: str,

    event_source: str = "USER_MANUAL",

    actor: str = "CANDIDATE",

    notes: str = "",

    evidence: str = "",

    conn: Optional[sqlite3.Connection] = None

) -> int:

    should_close = False

    if conn is None:

        conn = get_connection()

        should_close = True

    cursor = conn.cursor()

    now_utc = datetime.now(timezone.utc).isoformat()

    cursor.execute("""

        INSERT INTO application_history (

            application_id, previous_status, new_status, timestamp,

            event_source, actor, notes, evidence

        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)

    """, (application_id, previous_status, new_status, now_utc, event_source, actor, notes, evidence))

    if should_close:

        conn.commit()

    inserted_id = cursor.lastrowid

    if should_close:

        conn.close()

    return inserted_id



def get_application_history(application_id: int) -> List[Dict[str, Any]]:

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("""

        SELECT * FROM application_history

        WHERE application_id = ?

        ORDER BY timestamp ASC, id ASC

    """, (application_id,))

    rows = cursor.fetchall()

    conn.close()

    return [dict(r) for r in rows]



def update_application_stage(

    application_id: int,

    new_status: str,

    notes: str = "",

    actor: str = "CANDIDATE",

    event_source: str = "USER_MANUAL",

    evidence: str = ""

) -> Dict[str, Any]:

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("SELECT * FROM applications WHERE id = ?", (application_id,))

    app = cursor.fetchone()

    if not app:

        conn.close()

        raise ValueError(f"Application id {application_id} not found.")



    prev_status = app["application_status"]

    canonical_new = canonicalize_application_stage(new_status)

    now_utc = datetime.now(timezone.utc).isoformat()



    # Human submission barrier: APPLIED requires candidate explicit confirmation

    is_submitted = (canonical_new == ApplicationStatus.APPLIED.value)

    confirmed_by_user = 1 if is_submitted or app["submission_confirmed_by_user"] else 0

    submission_evidence = "CONFIRMED_BY_CANDIDATE" if is_submitted else app["submission_evidence_state"]

    sub_date = now_utc if (is_submitted and not app["submission_date"]) else app["submission_date"]



    cursor.execute("""

        UPDATE applications SET

            application_status = ?,

            submission_confirmed_by_user = ?,

            submission_evidence_state = ?,

            submission_date = ?,

            notes = ?,

            updated_at = ?

        WHERE id = ?

    """, (canonical_new, confirmed_by_user, submission_evidence, sub_date, notes or app["notes"], now_utc, application_id))



    record_application_transition(

        application_id=application_id,

        previous_status=prev_status,

        new_status=canonical_new,

        event_source=event_source,

        actor=actor,

        notes=notes or f"Application moved from {prev_status} to {canonical_new}.",

        evidence=evidence or ("Confirmed submission" if is_submitted else "Candidate updated stage"),

        conn=conn

    )

    conn.commit()



    cursor.execute("""

        SELECT a.*, j.employer, j.title, j.priority_label, j.location, j.official_url,

               j.official_listing_url, j.application_url, j.match_score, j.match_tier,

               j.verification_status, j.record_state, j.integrity_notes

        FROM applications a

        JOIN jobs j ON a.job_id = j.id

        WHERE a.id = ?

    """, (application_id,))

    updated_app = _row_to_app_dict(cursor.fetchone())

    conn.close()

    return updated_app



def _row_to_app_dict(row: sqlite3.Row) -> Dict[str, Any]:

    d = dict(row)

    for col in ["application_answers", "outreach_messages"]:

        if d.get(col):

            try:

                d[col] = json.loads(d[col])

            except Exception:

                d[col] = {}

        else:

            d[col] = {}

    d["submission_confirmed_by_user"] = bool(d.get("submission_confirmed_by_user", 0))

    outreach = d.get('outreach_messages') or {}
    for col in ('recruiter_name', 'recruiter_email', 'interview_date', 'deadline'):
        if not d.get(col):
            d[col] = outreach.get(col, '')

    return d



# ----------------- Preparation Plan CRUD -----------------



def save_preparation_plan(plan: PreparationPlan) -> int:

    conn = get_connection()

    cursor = conn.cursor()



    cursor.execute("""

        INSERT INTO preparation_plans (

            job_id, application_id, role_title, company, target_priority,

            daily_time_allocated_hours, study_plan_blocks, technical_topics,

            practice_exercises, interview_questions, completed_tasks, weak_areas,

            revision_checklist, next_revision_date, created_at, updated_at

        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

        ON CONFLICT(job_id) DO UPDATE SET

            role_title=excluded.role_title,

            company=excluded.company,

            target_priority=excluded.target_priority,

            daily_time_allocated_hours=excluded.daily_time_allocated_hours,

            study_plan_blocks=excluded.study_plan_blocks,

            technical_topics=excluded.technical_topics,

            practice_exercises=excluded.practice_exercises,

            interview_questions=excluded.interview_questions,

            completed_tasks=excluded.completed_tasks,

            weak_areas=excluded.weak_areas,

            revision_checklist=excluded.revision_checklist,

            next_revision_date=excluded.next_revision_date,

            updated_at=excluded.updated_at

    """, (

        plan.job_id, plan.application_id, plan.role_title, plan.company, plan.target_priority,

        plan.daily_time_allocated_hours, json.dumps(plan.study_plan_blocks),

        json.dumps(plan.technical_topics), json.dumps(plan.practice_exercises),

        json.dumps(plan.interview_questions), json.dumps(plan.completed_tasks),

        json.dumps(plan.weak_areas), json.dumps(plan.revision_checklist),

        plan.next_revision_date, plan.created_at, plan.updated_at

    ))



    conn.commit()

    plan_id = cursor.lastrowid

    if not plan_id:

        cursor.execute("SELECT id FROM preparation_plans WHERE job_id = ?", (plan.job_id,))

        row = cursor.fetchone()

        plan_id = row["id"] if row else 0



    conn.close()

    return plan_id



def get_preparation_plan_by_job(job_id: int) -> Optional[Dict[str, Any]]:

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("SELECT * FROM preparation_plans WHERE job_id = ?", (job_id,))

    row = cursor.fetchone()

    conn.close()

    return _row_to_plan_dict(row) if row else None



def list_preparation_plans() -> List[Dict[str, Any]]:

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("""SELECT p.* FROM preparation_plans p JOIN jobs j ON j.id=p.job_id

        WHERE COALESCE(j.record_state, 'DISCOVERY_LEAD') != 'QUARANTINED'

          AND j.discovery_source NOT IN ('Test','Test Unit')

        ORDER BY p.updated_at DESC""")

    rows = cursor.fetchall()

    conn.close()

    return [_row_to_plan_dict(r) for r in rows]



def _row_to_plan_dict(row: sqlite3.Row) -> Dict[str, Any]:

    d = dict(row)

    for col in ["study_plan_blocks", "technical_topics", "practice_exercises",

                "interview_questions", "completed_tasks", "weak_areas", "revision_checklist"]:

        if d.get(col):

            try:

                d[col] = json.loads(d[col])

            except Exception:

                d[col] = []

        else:

            d[col] = []

    return d



# ----------------- Resume Metadata CRUD -----------------



def save_resume_metadata(meta: ResumeMetadata) -> int:

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("""

        INSERT INTO resumes (

            job_id, company_name, role_title, source_resume_type,

            pdf_filename, pdf_path, docx_filename, docx_path,

            tailoring_summary, supported_keywords, missing_requirements,

            keyword_coverage_pct, details_needing_confirmation, created_at

        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

    """, (

        meta.job_id, meta.company_name, meta.role_title, meta.source_resume_type,

        meta.pdf_filename, meta.pdf_path, meta.docx_filename, meta.docx_path,

        meta.tailoring_summary, json.dumps(meta.supported_keywords),

        json.dumps(meta.missing_requirements), meta.keyword_coverage_pct,

        json.dumps(meta.details_needing_confirmation), meta.created_at

    ))

    conn.commit()

    res_id = cursor.lastrowid or 0

    conn.close()

    return res_id



def list_resumes() -> List[Dict[str, Any]]:

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("SELECT r.*, j.record_state FROM resumes r LEFT JOIN jobs j ON j.id=r.job_id ORDER BY r.created_at DESC")

    rows = cursor.fetchall()

    conn.close()

    result = []

    for r in rows:

        d = dict(r)

        for col in ["supported_keywords", "missing_requirements", "details_needing_confirmation"]:

            if d.get(col):

                try:

                    d[col] = json.loads(d[col])

                except Exception:

                    d[col] = []

            else:

                d[col] = []

        result.append(d)

    return result


def get_resume_by_id(resume_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT r.*, j.record_state FROM resumes r LEFT JOIN jobs j ON j.id=r.job_id WHERE r.id = ?", (resume_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    for col in ["supported_keywords", "missing_requirements", "details_needing_confirmation"]:
        if d.get(col):
            try:
                d[col] = json.loads(d[col])
            except Exception:
                d[col] = []
        else:
            d[col] = []
    return d


def delete_resume(resume_id: int) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT pdf_filename, docx_filename FROM resumes WHERE id = ?", (resume_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False
    from careerorbit.config.settings import current_resumes_dir
    resumes_dir = current_resumes_dir()
    for col in ("pdf_filename", "docx_filename"):
        fn = row[col]
        if fn:
            p = resumes_dir / fn
            if p.exists() and p.is_file():
                try:
                    p.unlink()
                except Exception:
                    pass
    cursor.execute("DELETE FROM resumes WHERE id = ?", (resume_id,))
    conn.commit()
    conn.close()
    return True








# ----------------- Export Utilities -----------------



def export_jobs_to_csv(filepath: Optional[str] = None) -> str:

    out_path = Path(filepath) if filepath else current_exports_dir() / f"jobs_export_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"

    jobs = list_jobs(limit=1000)

    if not jobs:

        with open(out_path, "w", newline="", encoding="utf-8") as f:

            f.write("No jobs found\n")

        return str(out_path)



    from careerorbit.config.candidate_evidence import candidate_profile_ready_for_resume

    fit_ready = candidate_profile_ready_for_resume()

    keys = [

        "id", "employer", "title", "job_id_or_req", "priority_category", "priority_label",

        "location", "work_arrangement", "candidate_fit_state", "candidate_fit_score", "match_tier",

        "verification_status", "posting_date", "posting_date_confidence", "first_discovered_at",

        "last_verified_at", "last_observed_status", "last_observed_status_at",

        "record_state", "discovery_source", "discovery_url", "official_listing_url", "application_url", "verification_source"

    ]

    with open(out_path, "w", newline="", encoding="utf-8") as f:

        writer = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")

        writer.writeheader()

        for j in jobs:

            out = dict(j)

            out["candidate_fit_state"] = "READY" if fit_ready else "NEEDS_CANDIDATE_REVIEW"

            out["candidate_fit_score"] = j.get("match_score") if fit_ready else ""

            out["match_tier"] = j.get("match_tier") if fit_ready else "NEEDS_CANDIDATE_REVIEW"

            writer.writerow({key: _safe_csv_cell(value) for key, value in out.items()})

    return str(out_path)



def export_applications_to_csv(filepath: Optional[str] = None) -> str:

    out_path = Path(filepath) if filepath else current_exports_dir() / f"applications_export_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"

    apps = list_applications()

    if not apps:

        with open(out_path, "w", newline="", encoding="utf-8") as f:

            f.write("No applications found\n")

        return str(out_path)



    keys = [

        "id", "job_id", "employer", "title", "priority_label",

        "application_status", "submission_confirmed_by_user", "submission_date",

        "submission_evidence_state", "candidate_review_state", "record_state", "legacy_application_status",

        "recruiter_outreach_status", "interview_stage", "follow_up_date", "next_action"

    ]

    with open(out_path, "w", newline="", encoding="utf-8") as f:

        writer = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")

        writer.writeheader()

        for a in apps:

            out = dict(a)

            if a.get("candidate_review_state") == "NEEDS_CONFIRMATION":

                out["legacy_application_status"] = a.get("application_status", "")

                out["application_status"] = "NEEDS_CANDIDATE_REVIEW"

                out["submission_confirmed_by_user"] = False

                out["submission_date"] = ""

            if a.get("record_state") == "QUARANTINED":

                out["employer"] = f"QUARANTINED — {a.get('employer', '')}"

                out["title"] = f"QUARANTINED — {a.get('title', '')}"

            writer.writerow({key: _safe_csv_cell(value) for key, value in out.items()})

    return str(out_path)





def _safe_csv_cell(value: Any) -> Any:

    """Neutralize spreadsheet formula prefixes in untrusted source/candidate text."""

    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):

        return "'" + value

    return value





# ----------------- Unified Inbox & Telegram State Operations -----------------



def save_inbox_message(msg: Dict[str, Any], conn: Optional[sqlite3.Connection] = None) -> int:

    """Insert or update a unified inbox message. Returns the row ID."""

    should_close = False
    if conn is None:
        conn = get_connection()
        should_close = True

    cursor = conn.cursor()



    message_uid = msg.get("message_uid") or f"{msg.get('channel', 'telegram')}_{msg.get('chat_id', '')}_{msg.get('message_id', '')}"

    extracted_json = json.dumps(msg.get("extracted_data") or {})



    cursor.execute("""

        INSERT INTO inbox_messages (

            message_uid, channel, chat_id, chat_title, chat_type, message_id,

            sender_id, sender_name, sender_username, raw_text, classification,

            category_group, is_job_lead, job_id, extracted_data, media_type,

            media_file_id, received_at, status, notes

        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

        ON CONFLICT(message_uid) DO UPDATE SET

            raw_text = excluded.raw_text,

            classification = excluded.classification,

            category_group = excluded.category_group,

            is_job_lead = excluded.is_job_lead,

            job_id = COALESCE(excluded.job_id, inbox_messages.job_id),

            extracted_data = excluded.extracted_data,

            notes = excluded.notes

    """, (

        message_uid,

        msg.get("channel", "telegram"),

        str(msg.get("chat_id", "")),

        msg.get("chat_title", ""),

        msg.get("chat_type", "private"),

        int(msg.get("message_id", 0)),

        str(msg.get("sender_id", "")),

        msg.get("sender_name", ""),

        msg.get("sender_username", ""),

        msg.get("raw_text", ""),

        msg.get("classification", "Other Career Resources"),

        msg.get("category_group", "other"),

        1 if msg.get("is_job_lead") else 0,

        msg.get("job_id"),

        extracted_json,

        msg.get("media_type", "text"),

        msg.get("media_file_id", ""),

        msg.get("received_at") or datetime.now(timezone.utc).isoformat(),

        msg.get("status", "NEW"),

        msg.get("notes", "")

    ))

    if should_close:
        conn.commit()

    msg_id = cursor.lastrowid

    if not msg_id:

        cursor.execute("SELECT id FROM inbox_messages WHERE message_uid = ?", (message_uid,))

        row = cursor.fetchone()

        msg_id = row["id"] if row else 0

    if should_close:
        conn.close()

    return msg_id





def get_inbox_message(msg_id: int) -> Optional[Dict[str, Any]]:

    """Retrieve an inbox message by primary key."""

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("SELECT * FROM inbox_messages WHERE id = ?", (msg_id,))

    row = cursor.fetchone()

    conn.close()

    if not row:

        return None

    d = dict(row)

    try:

        d["extracted_data"] = json.loads(d.get("extracted_data") or "{}")

    except Exception:

        d["extracted_data"] = {}

    return d





def get_inbox_message_by_uid(uid: str) -> Optional[Dict[str, Any]]:

    """Retrieve an inbox message by message_uid."""

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("SELECT * FROM inbox_messages WHERE message_uid = ?", (uid,))

    row = cursor.fetchone()

    conn.close()

    if not row:

        return None

    d = dict(row)

    try:

        d["extracted_data"] = json.loads(d.get("extracted_data") or "{}")

    except Exception:

        d["extracted_data"] = {}

    return d





def list_inbox_messages(

    classification: Optional[str] = None,

    category_group: Optional[str] = None,

    channel: Optional[str] = None,

    status: Optional[str] = None,

    is_job_lead: Optional[bool] = None,

    query: Optional[str] = None,

    limit: int = 50,

    offset: int = 0

) -> List[Dict[str, Any]]:

    """List inbox messages with optional filtering and pagination."""

    conn = get_connection()

    cursor = conn.cursor()



    sql = """

        SELECT m.*, j.title as linked_job_title, j.employer as linked_job_employer,

               j.official_url as linked_job_url, j.verification_status as linked_job_verification_status,

               j.match_tier as linked_job_match_tier

        FROM inbox_messages m

        LEFT JOIN jobs j ON m.job_id = j.id

        WHERE 1=1

    """

    params = []



    if classification:

        sql += " AND m.classification = ?"

        params.append(classification)

    if category_group:

        sql += " AND m.category_group = ?"

        params.append(category_group)

    if channel:

        sql += " AND m.channel = ?"

        params.append(channel)

    if status:

        sql += " AND m.status = ?"

        params.append(status)

    if is_job_lead is not None:

        sql += " AND m.is_job_lead = ?"

        params.append(1 if is_job_lead else 0)

    if query:

        sql += " AND (m.raw_text LIKE ? OR m.sender_name LIKE ? OR m.chat_title LIKE ?)"

        wild = f"%{query}%"

        params.extend([wild, wild, wild])



    sql += " ORDER BY m.received_at DESC LIMIT ? OFFSET ?"

    params.extend([limit, offset])



    cursor.execute(sql, tuple(params))

    rows = cursor.fetchall()

    conn.close()



    result = []

    for r in rows:

        d = dict(r)

        try:

            d["extracted_data"] = json.loads(d.get("extracted_data") or "{}")

        except Exception:

            d["extracted_data"] = {}

        result.append(d)

    return result






def get_inbox_stats() -> Dict[str, Any]:

    """Return categorized breakdown of unified inbox messages."""

    conn = get_connection()

    cursor = conn.cursor()



    cursor.execute("SELECT COUNT(*) as total FROM inbox_messages")

    total = cursor.fetchone()["total"]



    cursor.execute("SELECT COUNT(*) as new_cnt FROM inbox_messages WHERE status = 'NEW'")

    new_cnt = cursor.fetchone()["new_cnt"]



    cursor.execute("SELECT COUNT(*) as processed_cnt FROM inbox_messages WHERE status = 'PROCESSED'")

    processed_cnt = cursor.fetchone()["processed_cnt"]



    cursor.execute("SELECT COUNT(*) as archived_cnt FROM inbox_messages WHERE status = 'ARCHIVED'")

    archived_cnt = cursor.fetchone()["archived_cnt"]



    cursor.execute("SELECT COUNT(*) as discarded_cnt FROM inbox_messages WHERE status = 'DISCARDED'")

    discarded_cnt = cursor.fetchone()["discarded_cnt"]



    cursor.execute("SELECT COUNT(*) as job_leads FROM inbox_messages WHERE is_job_lead = 1 AND status != 'DISCARDED'")

    job_leads = cursor.fetchone()["job_leads"]



    cursor.execute("""

        SELECT classification, COUNT(*) as cnt

        FROM inbox_messages

        WHERE status != 'DISCARDED'

        GROUP BY classification

        ORDER BY cnt DESC

    """)

    classification_breakdown = {row["classification"]: row["cnt"] for row in cursor.fetchall()}



    cursor.execute("""

        SELECT category_group, COUNT(*) as cnt

        FROM inbox_messages

        WHERE status != 'DISCARDED'

        GROUP BY category_group

        ORDER BY cnt DESC

    """)

    category_group_breakdown = {row["category_group"]: row["cnt"] for row in cursor.fetchall()}



    conn.close()

    return {

        "total": total,

        "new": new_cnt,

        "processed": processed_cnt,

        "archived": archived_cnt,

        "discarded": discarded_cnt,

        "job_leads": job_leads,

        "by_classification": classification_breakdown,

        "by_category_group": category_group_breakdown,

    }





def update_inbox_message_status(msg_id: int, new_status: str, notes: Optional[str] = None) -> bool:

    """Update status ('NEW', 'PROCESSED', 'ARCHIVED', 'DISCARDED') of an inbox item."""

    conn = get_connection()

    cursor = conn.cursor()

    if notes is not None:

        cursor.execute("UPDATE inbox_messages SET status = ?, notes = ? WHERE id = ?", (new_status, notes, msg_id))

    else:

        cursor.execute("UPDATE inbox_messages SET status = ? WHERE id = ?", (new_status, msg_id))

    updated = cursor.rowcount > 0

    conn.commit()

    conn.close()

    return updated





def delete_inbox_message(msg_id: int) -> bool:

    """Permanently delete an inbox message."""

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("DELETE FROM inbox_messages WHERE id = ?", (msg_id,))

    deleted = cursor.rowcount > 0

    conn.commit()

    conn.close()

    return deleted





def get_telegram_offset() -> int:

    """Retrieve the current update offset for Telegram polling."""

    try:

        conn = get_connection()

        cursor = conn.cursor()

        cursor.execute("SELECT value FROM telegram_state WHERE key = 'last_update_offset'")

        row = cursor.fetchone()

        conn.close()

        if row and row["value"]:

            try:

                return int(row["value"])

            except ValueError:

                return 0

        return 0

    except Exception:

        return 0





def set_telegram_offset(offset: int) -> None:

    """Persist the current update offset for Telegram polling."""

    conn = get_connection()

    cursor = conn.cursor()

    now_iso = datetime.now(timezone.utc).isoformat()

    cursor.execute("""

        INSERT INTO telegram_state (key, value, updated_at) VALUES ('last_update_offset', ?, ?)

        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at

    """, (str(offset), now_iso))

    conn.commit()

    conn.close()





def set_telegram_poll_metadata(status: str, timestamp: str, processed_count: int = 0) -> None:

    """Persist the last poll status, poll time, and increment processed updates in SQLite."""

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("""

        INSERT INTO telegram_state (key, value, updated_at) VALUES ('last_poll_status', ?, ?)

        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at

    """, (status, timestamp))

    cursor.execute("""

        INSERT INTO telegram_state (key, value, updated_at) VALUES ('last_poll_time', ?, ?)

        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at

    """, (timestamp, timestamp))

    if processed_count > 0:

        cursor.execute("SELECT value FROM telegram_state WHERE key = 'total_updates_processed'")

        row = cursor.fetchone()

        current_total = int(row["value"]) if (row and row["value"]) else 0

        new_total = current_total + processed_count

        cursor.execute("""

            INSERT INTO telegram_state (key, value, updated_at) VALUES ('total_updates_processed', ?, ?)

            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at

        """, (str(new_total), timestamp))

    conn.commit()

    conn.close()





def get_telegram_poll_metadata() -> Dict[str, Any]:

    """Retrieve persisted telegram polling metadata across server restarts."""

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("SELECT key, value FROM telegram_state WHERE key IN ('last_poll_status', 'last_poll_time', 'total_updates_processed')")

    rows = cursor.fetchall()

    conn.close()

    meta = {r["key"]: r["value"] for r in rows}

    return {

        "last_poll_status": meta.get("last_poll_status", "IDLE"),

        "last_poll_time": meta.get("last_poll_time"),

        "total_updates_processed": int(meta.get("total_updates_processed") or 0)

    }





# ----------------- Community Source Registry Operations -----------------



def record_community_source(

    chat_id: str,

    source_name: str,

    source_type: str,

    status: str = "ACTIVE",

    last_error: str = "",

    increment_messages: bool = True,

    chat_username: str = "",

    is_public: bool = False,

    is_member: bool = True,

    can_receive_messages: bool = True,

    bot_role: str = "unknown",

    last_message_at: Optional[str] = None,

    last_message_excerpt: Optional[str] = None,

    setup_instructions: str = "",

    diagnosis: str = ""

) -> int:

    """Record or update a community source (Telegram channel/group/DM, WhatsApp export, etc.)."""

    conn = get_connection()

    cursor = conn.cursor()

    now_iso = datetime.now(timezone.utc).isoformat()



    cursor.execute("SELECT id, messages_count FROM community_sources WHERE chat_id = ?", (str(chat_id),))

    existing = cursor.fetchone()



    msg_at = last_message_at or (now_iso if increment_messages else None)



    if existing:

        new_cnt = (existing["messages_count"] + 1) if increment_messages else existing["messages_count"]

        cursor.execute("""

            UPDATE community_sources

            SET source_name = ?,

                source_type = ?,

                status = ?,

                last_error = ?,

                messages_count = ?,

                last_ingestion_at = COALESCE(?, last_ingestion_at),

                chat_username = CASE WHEN ? != '' THEN ? ELSE chat_username END,

                is_public = ?,

                is_member = ?,

                can_receive_messages = ?,

                bot_role = CASE WHEN ? != 'unknown' THEN ? ELSE bot_role END,

                last_message_at = COALESCE(?, last_message_at),

                last_message_excerpt = COALESCE(?, last_message_excerpt),

                setup_instructions = CASE WHEN ? != '' THEN ? ELSE setup_instructions END,

                diagnosis = CASE WHEN ? != '' THEN ? ELSE diagnosis END,

                updated_at = ?

            WHERE id = ?

        """, (

            source_name, source_type, status, last_error, new_cnt,

            now_iso if increment_messages else None,

            chat_username, chat_username,

            1 if is_public else 0,

            1 if is_member else 0,

            1 if can_receive_messages else 0,

            bot_role, bot_role,

            msg_at,

            last_message_excerpt,

            setup_instructions, setup_instructions,

            diagnosis, diagnosis,

            now_iso, existing["id"]

        ))

        source_id = existing["id"]

    else:

        cnt = 1 if increment_messages else 0

        cursor.execute("""

            INSERT INTO community_sources (

                source_name, source_type, chat_id, status, is_enabled,

                last_ingestion_at, last_error, messages_count,

                chat_username, is_public, is_member, can_receive_messages, bot_role,

                last_message_at, last_message_excerpt, setup_instructions, diagnosis,

                created_at, updated_at

            ) VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

        """, (

            source_name, source_type, str(chat_id), status,

            now_iso if increment_messages else None, last_error, cnt,

            chat_username, 1 if is_public else 0, 1 if is_member else 0,

            1 if can_receive_messages else 0, bot_role,

            msg_at, last_message_excerpt, setup_instructions, diagnosis,

            now_iso, now_iso

        ))

        source_id = cursor.lastrowid



    conn.commit()

    conn.close()

    return source_id





def list_community_sources(source_type: Optional[str] = None) -> List[Dict[str, Any]]:

    """List all registered community sources."""

    conn = get_connection()

    cursor = conn.cursor()

    if source_type:

        cursor.execute("SELECT * FROM community_sources WHERE source_type = ? ORDER BY messages_count DESC, updated_at DESC", (source_type,))

    else:

        cursor.execute("SELECT * FROM community_sources ORDER BY messages_count DESC, updated_at DESC")

    rows = cursor.fetchall()

    conn.close()

    return [dict(r) for r in rows]





def get_community_source(chat_id: str) -> Optional[Dict[str, Any]]:

    """Get a single community source by chat_id."""

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("SELECT * FROM community_sources WHERE chat_id = ?", (str(chat_id),))

    row = cursor.fetchone()

    conn.close()

    return dict(row) if row else None





def update_community_source(

    source_id: int,

    status: Optional[str] = None,

    is_enabled: Optional[bool] = None,

    last_error: Optional[str] = None,

    can_receive_messages: Optional[bool] = None,

    is_member: Optional[bool] = None,

    bot_role: Optional[str] = None,

    setup_instructions: Optional[str] = None,

    diagnosis: Optional[str] = None,

    last_message_at: Optional[str] = None,

    last_message_excerpt: Optional[str] = None,

) -> bool:

    """Update community source attributes."""

    conn = get_connection()

    cursor = conn.cursor()

    now_iso = datetime.now(timezone.utc).isoformat()

    updates = ["updated_at = ?"]

    params = [now_iso]



    if status is not None:

        updates.append("status = ?")

        params.append(status)

    if is_enabled is not None:

        updates.append("is_enabled = ?")

        params.append(1 if is_enabled else 0)

    if last_error is not None:

        updates.append("last_error = ?")

        params.append(last_error)

    if can_receive_messages is not None:

        updates.append("can_receive_messages = ?")

        params.append(1 if can_receive_messages else 0)

    if is_member is not None:

        updates.append("is_member = ?")

        params.append(1 if is_member else 0)

    if bot_role is not None:

        updates.append("bot_role = ?")

        params.append(bot_role)

    if setup_instructions is not None:

        updates.append("setup_instructions = ?")

        params.append(setup_instructions)

    if diagnosis is not None:

        updates.append("diagnosis = ?")

        params.append(diagnosis)

    if last_message_at is not None:

        updates.append("last_message_at = ?")

        params.append(last_message_at)

    if last_message_excerpt is not None:

        updates.append("last_message_excerpt = ?")

        params.append(last_message_excerpt)



    params.append(source_id)

    cursor.execute(f"UPDATE community_sources SET {', '.join(updates)} WHERE id = ?", tuple(params))

    updated = cursor.rowcount > 0

    conn.commit()

    conn.close()

    return updated





def get_community_source_by_id(source_id: int) -> Optional[Dict[str, Any]]:

    """Get a single community source by its database ID."""

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("SELECT * FROM community_sources WHERE id = ?", (source_id,))

    row = cursor.fetchone()

    conn.close()

    return dict(row) if row else None





def delete_community_source(source_id: int) -> bool:

    """Delete a community source by ID."""

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("DELETE FROM community_sources WHERE id = ?", (source_id,))

    deleted = cursor.rowcount > 0

    conn.commit()

    conn.close()

    return deleted





# ----------------- Learning Resources Library Operations -----------------



def save_learning_resource(res: Dict[str, Any]) -> int:

    """Insert or update a career study/learning resource."""

    conn = get_connection()

    cursor = conn.cursor()



    canonical_url = res.get("canonical_url") or res.get("primary_url") or ""

    all_urls = res.get("all_urls") or ([res["primary_url"]] if res.get("primary_url") else [])

    all_urls_json = json.dumps(all_urls) if isinstance(all_urls, list) else str(all_urls)

    tags = res.get("tags") or []

    tags_json = json.dumps(tags) if isinstance(tags, list) else str(tags)

    now_iso = datetime.now(timezone.utc).isoformat()

    saved_at = res.get("saved_at") or now_iso

    created_at = res.get("created_at") or now_iso

    is_completed = 1 if res.get("is_completed") else 0

    completed_at = res.get("completed_at") if is_completed else None



    cursor.execute("""

        INSERT INTO learning_resources (

            title, category, sub_category, canonical_url, primary_url,

            all_urls, source, source_message_uid, raw_excerpt, summary,

            tags, saved_at, notes, skill_tag, difficulty_level, resource_type,

            estimated_minutes, created_at, is_completed, completed_at

        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

        ON CONFLICT(canonical_url) DO UPDATE SET

            title = excluded.title,

            category = excluded.category,

            sub_category = excluded.sub_category,

            primary_url = excluded.primary_url,

            all_urls = excluded.all_urls,

            source = excluded.source,

            raw_excerpt = excluded.raw_excerpt,

            summary = excluded.summary,

            tags = excluded.tags,

            skill_tag = excluded.skill_tag,

            difficulty_level = excluded.difficulty_level,

            resource_type = excluded.resource_type,

            estimated_minutes = excluded.estimated_minutes,

            notes = CASE WHEN learning_resources.notes != '' THEN learning_resources.notes ELSE excluded.notes END,

            is_completed = CASE WHEN learning_resources.is_completed = 1 THEN 1 ELSE excluded.is_completed END,

            completed_at = CASE WHEN learning_resources.completed_at IS NOT NULL THEN learning_resources.completed_at ELSE excluded.completed_at END

    """, (

        res.get("title", "Untitled Resource"),

        res.get("category", "Technical Learning Materials"),

        res.get("sub_category", ""),

        canonical_url,

        res.get("primary_url", canonical_url),

        all_urls_json,

        res.get("source", "Community"),

        res.get("source_message_uid", ""),

        res.get("raw_excerpt", ""),

        res.get("summary", ""),

        tags_json,

        saved_at,

        res.get("notes", ""),

        res.get("skill_tag", ""),

        res.get("difficulty_level", "BEGINNER"),

        res.get("resource_type", "DOCUMENTATION"),

        int(res.get("estimated_minutes") or 30),

        created_at,

        is_completed,

        completed_at

    ))

    conn.commit()

    res_id = cursor.lastrowid

    if not res_id:

        cursor.execute("SELECT id FROM learning_resources WHERE canonical_url = ?", (canonical_url,))

        row = cursor.fetchone()

        res_id = row["id"] if row else 0

    conn.close()

    return res_id





def list_learning_resources(

    category: Optional[str] = None,

    skill_tag: Optional[str] = None,

    difficulty_level: Optional[str] = None,

    resource_type: Optional[str] = None,

    is_completed: Optional[bool] = None,

    query: Optional[str] = None,

    limit: int = 50,

    offset: int = 0

) -> List[Dict[str, Any]]:

    """List study materials and career learning resources with multi-criteria filters."""

    conn = get_connection()

    cursor = conn.cursor()



    sql = "SELECT * FROM learning_resources WHERE 1=1"

    params: List[Any] = []



    if category:

        sql += " AND category = ?"

        params.append(category)

    if skill_tag:

        sql += " AND skill_tag = ?"

        params.append(skill_tag)

    if difficulty_level:

        sql += " AND difficulty_level = ?"

        params.append(difficulty_level)

    if resource_type:

        sql += " AND resource_type = ?"

        params.append(resource_type)

    if is_completed is not None:

        sql += " AND is_completed = ?"

        params.append(1 if is_completed else 0)

    if query:

        sql += " AND (title LIKE ? OR summary LIKE ? OR raw_excerpt LIKE ? OR notes LIKE ? OR tags LIKE ?)"

        wild = f"%{query}%"

        params.extend([wild, wild, wild, wild, wild])



    sql += " ORDER BY saved_at DESC LIMIT ? OFFSET ?"

    params.extend([limit, offset])



    cursor.execute(sql, tuple(params))

    rows = cursor.fetchall()

    conn.close()



    result = []

    for r in rows:

        d = dict(r)

        try:

            d["all_urls"] = json.loads(d.get("all_urls") or "[]")

        except Exception:

            d["all_urls"] = []

        try:

            d["tags"] = json.loads(d.get("tags") or "[]")

        except Exception:

            d["tags"] = []

        d["is_completed"] = bool(d.get("is_completed"))

        result.append(d)

    return result








def get_learning_resource(res_id: int) -> Optional[Dict[str, Any]]:

    """Retrieve a single learning resource by ID."""

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("SELECT * FROM learning_resources WHERE id = ?", (res_id,))

    row = cursor.fetchone()

    conn.close()

    if not row:

        return None

    d = dict(row)

    try:

        d["all_urls"] = json.loads(d.get("all_urls") or "[]")

    except Exception:

        d["all_urls"] = []

    try:

        d["tags"] = json.loads(d.get("tags") or "[]")

    except Exception:

        d["tags"] = []

    d["is_completed"] = bool(d.get("is_completed"))

    return d





def toggle_learning_resource_completion(res_id: int, completed: Optional[bool] = None) -> Optional[Dict[str, Any]]:

    """Toggle or explicitly set completion status for a learning resource."""

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("SELECT id, is_completed FROM learning_resources WHERE id = ?", (res_id,))

    row = cursor.fetchone()

    if not row:

        conn.close()

        return None



    current_status = bool(row["is_completed"])

    new_status = (not current_status) if completed is None else bool(completed)

    new_is_completed = 1 if new_status else 0

    now_utc = datetime.now(timezone.utc).isoformat() if new_is_completed else None



    cursor.execute("""

        UPDATE learning_resources

        SET is_completed = ?, completed_at = ?

        WHERE id = ?

    """, (new_is_completed, now_utc, res_id))

    conn.commit()

    conn.close()

    return get_learning_resource(res_id)





def delete_learning_resource(res_id: int) -> bool:

    """Delete a saved learning resource by ID."""

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("DELETE FROM learning_resources WHERE id = ?", (res_id,))

    deleted = cursor.rowcount > 0

    conn.commit()

    conn.close()

    return deleted





def get_learning_resources_stats() -> Dict[str, Any]:

    """Retrieve comprehensive metrics for saved learning resources."""

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) as total FROM learning_resources")

    total = cursor.fetchone()["total"]



    cursor.execute("SELECT category, COUNT(*) as cnt FROM learning_resources GROUP BY category ORDER BY cnt DESC")

    by_cat = {r["category"]: r["cnt"] for r in cursor.fetchall()}



    cursor.execute("SELECT difficulty_level, COUNT(*) as cnt FROM learning_resources WHERE difficulty_level IS NOT NULL GROUP BY difficulty_level")

    by_diff = {r["difficulty_level"]: r["cnt"] for r in cursor.fetchall()}



    cursor.execute("SELECT skill_tag, COUNT(*) as cnt FROM learning_resources WHERE skill_tag != '' GROUP BY skill_tag ORDER BY cnt DESC")

    by_skill = {r["skill_tag"]: r["cnt"] for r in cursor.fetchall()}



    cursor.execute("SELECT COUNT(*) as completed FROM learning_resources WHERE is_completed = 1")

    completed = cursor.fetchone()["completed"]



    cursor.execute("SELECT SUM(estimated_minutes) as total_min FROM learning_resources")

    row_min = cursor.fetchone()

    total_minutes = row_min["total_min"] or 0



    conn.close()

    return {

        "total": total,

        "completed": completed,

        "pending": total - completed,

        "completion_rate_pct": round((completed / total * 100.0) if total else 0.0, 1),

        "total_estimated_hours": round(total_minutes / 60.0, 1),

        "by_category": by_cat,

        "by_difficulty": by_diff,

        "by_skill": by_skill

    }





# ----------------- Job Sources Operations -----------------



def list_job_sources(

    category: Optional[str] = None,

    source_type: Optional[str] = None,

    is_enabled: Optional[bool] = None,

    health_status: Optional[str] = None,

    limit: int = 100,

    offset: int = 0

) -> List[Dict[str, Any]]:

    conn = get_connection()

    cursor = conn.cursor()

    query = "SELECT * FROM job_sources WHERE 1=1"

    params: list[Any] = []

    if category:

        query += " AND category = ?"

        params.append(category)

    if source_type:

        query += " AND source_type = ?"

        params.append(source_type)

    if is_enabled is not None:

        query += " AND is_enabled = ?"

        params.append(1 if is_enabled else 0)

    if health_status:

        query += " AND health_status = ?"

        params.append(health_status)

    query += " ORDER BY is_enabled DESC, source_name ASC LIMIT ? OFFSET ?"

    params.extend([limit, offset])

    cursor.execute(query, params)

    rows = cursor.fetchall()

    conn.close()

    return [dict(r) for r in rows]





def get_job_source(source_id: str) -> Optional[Dict[str, Any]]:

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("SELECT * FROM job_sources WHERE source_id = ?", (source_id,))

    row = cursor.fetchone()

    conn.close()

    return dict(row) if row else None





def save_job_source(data: Dict[str, Any]) -> int:

    conn = get_connection()

    cursor = conn.cursor()

    now_utc = datetime.now(timezone.utc).isoformat()

    cursor.execute("""

        INSERT INTO job_sources (

            source_id, source_name, category, source_type,

            endpoint_or_board_id, access_method, is_configured, is_enabled,

            last_attempt_at, last_success_at, last_discovered_count, last_updated_count,

            last_rejected_count, last_deduped_count, health_status,

            last_error_category, last_error_message, retry_count, next_retry_at,

            created_at, updated_at

        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

        ON CONFLICT(source_id) DO UPDATE SET

            source_name = excluded.source_name,

            category = excluded.category,

            source_type = excluded.source_type,

            endpoint_or_board_id = excluded.endpoint_or_board_id,

            access_method = excluded.access_method,

            is_configured = excluded.is_configured,

            is_enabled = excluded.is_enabled,

            updated_at = excluded.updated_at

    """, (

        data["source_id"],

        data["source_name"],

        data.get("category", "EMPLOYER_ATS"),

        data.get("source_type", "CUSTOM"),

        data.get("endpoint_or_board_id", ""),

        data.get("access_method", "API"),

        1 if data.get("is_configured", True) else 0,

        1 if data.get("is_enabled", True) else 0,

        data.get("last_attempt_at"),

        data.get("last_success_at"),

        data.get("last_discovered_count", 0),

        data.get("last_updated_count", 0),

        data.get("last_rejected_count", 0),

        data.get("last_deduped_count", 0),

        data.get("health_status", "UNKNOWN"),

        data.get("last_error_category"),

        data.get("last_error_message"),

        data.get("retry_count", 0),

        data.get("next_retry_at"),

        data.get("created_at", now_utc),

        now_utc,

    ))

    conn.commit()

    inserted_id = cursor.lastrowid

    conn.close()

    return inserted_id





def update_job_source_health(

    source_id: str,

    health_status: str,

    discovered_count: int = 0,

    updated_count: int = 0,

    rejected_count: int = 0,

    deduped_count: int = 0,

    error_category: Optional[str] = None,

    error_message: Optional[str] = None,

    success: bool = True

) -> bool:

    conn = get_connection()

    cursor = conn.cursor()

    now_utc = datetime.now(timezone.utc).isoformat()

    if success:

        cursor.execute("""

            UPDATE job_sources SET

                health_status = ?,

                last_attempt_at = ?,

                last_success_at = ?,

                last_discovered_count = ?,

                last_updated_count = ?,

                last_rejected_count = ?,

                last_deduped_count = ?,

                last_error_category = NULL,

                last_error_message = NULL,

                retry_count = 0,

                updated_at = ?

            WHERE source_id = ? OR source_name = ?

        """, (health_status, now_utc, now_utc, discovered_count, updated_count, rejected_count, deduped_count, now_utc, source_id, source_id))

    else:

        cursor.execute("""

            UPDATE job_sources SET

                health_status = ?,

                last_attempt_at = ?,

                last_error_category = ?,

                last_error_message = ?,

                retry_count = retry_count + 1,

                updated_at = ?

            WHERE source_id = ? OR source_name = ?

        """, (health_status, now_utc, error_category, error_message, now_utc, source_id, source_id))

    conn.commit()

    updated = cursor.rowcount > 0

    conn.close()

    return updated





def delete_job_source(source_id: str) -> bool:

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("DELETE FROM job_sources WHERE source_id = ?", (source_id,))

    conn.commit()

    deleted = cursor.rowcount > 0

    conn.close()

    return deleted





def toggle_job_source_enabled(source_id: str, enabled: Optional[bool] = None) -> Optional[bool]:

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("SELECT is_enabled FROM job_sources WHERE source_id = ?", (source_id,))

    row = cursor.fetchone()

    if not row:

        conn.close()

        return None

    new_state = (not bool(row["is_enabled"])) if enabled is None else bool(enabled)

    now_utc = datetime.now(timezone.utc).isoformat()

    cursor.execute("UPDATE job_sources SET is_enabled = ?, updated_at = ? WHERE source_id = ?",

                   (1 if new_state else 0, now_utc, source_id))

    conn.commit()

    conn.close()

    return new_state





# ----------------- Phase 3 Daily Study Planner CRUD -----------------



def _row_to_study_plan_dict(row: sqlite3.Row) -> Dict[str, Any]:

    d = dict(row)

    for col, default in [

        ("skill_gaps_json", []),

        ("tasks_json", []),

        ("schedule_blocks_json", []),

        ("top_three_priorities_json", []),

        ("user_skills_json", {})

    ]:

        val = d.pop(col, None)

        target_key = col.replace("_json", "")

        if val:

            try:

                d[target_key] = json.loads(val)

            except Exception:

                d[target_key] = default

        else:

            d[target_key] = default

    d["is_completed"] = bool(d.get("is_completed", 0))

    return d





def save_daily_study_plan(plan_data: Dict[str, Any]) -> int:

    conn = get_connection()

    cursor = conn.cursor()

    now_utc = datetime.now(timezone.utc).isoformat()



    plan_date = plan_data.get("plan_date") or datetime.now().strftime("%Y-%m-%d")

    target_role = plan_data.get("target_role") or "Data Analyst / BI / Power BI"

    daily_budget_minutes = int(plan_data.get("daily_budget_minutes") or 120)

    target_priority = int(plan_data.get("target_priority") or 1)

    allocated_hours = float(plan_data.get("allocated_hours") or round(daily_budget_minutes / 60.0, 1))

    notes = plan_data.get("notes") or ""

    is_completed = 1 if plan_data.get("is_completed") else 0



    skill_gaps_json = json.dumps(plan_data.get("skill_gaps") or [])

    user_skills_json = json.dumps(plan_data.get("user_skills") or {})

    tasks_json = json.dumps(plan_data.get("tasks") or [])

    schedule_blocks_json = json.dumps(plan_data.get("schedule_blocks") or [])

    top_three_priorities_json = json.dumps(plan_data.get("top_three_priorities") or [])



    # Check if a plan already exists for this date and target role

    cursor.execute("""

        SELECT id FROM daily_study_plans WHERE plan_date = ? AND target_role = ?

    """, (plan_date, target_role))

    row = cursor.fetchone()



    if row:

        plan_id = row["id"]

        cursor.execute("""

            UPDATE daily_study_plans SET

                daily_budget_minutes = ?,

                target_priority = ?,

                skill_gaps_json = ?,

                user_skills_json = ?,

                tasks_json = ?,

                schedule_blocks_json = ?,

                top_three_priorities_json = ?,

                allocated_hours = ?,

                notes = ?,

                is_completed = ?,

                updated_at = ?

            WHERE id = ?

        """, (

            daily_budget_minutes, target_priority, skill_gaps_json, user_skills_json,

            tasks_json, schedule_blocks_json, top_three_priorities_json, allocated_hours,

            notes, is_completed, now_utc, plan_id

        ))

    else:

        cursor.execute("""

            INSERT INTO daily_study_plans (

                plan_date, target_role, daily_budget_minutes, target_priority,

                skill_gaps_json, user_skills_json, tasks_json, schedule_blocks_json,

                top_three_priorities_json, allocated_hours, notes, is_completed,

                created_at, updated_at

            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

        """, (

            plan_date, target_role, daily_budget_minutes, target_priority,

            skill_gaps_json, user_skills_json, tasks_json, schedule_blocks_json,

            top_three_priorities_json, allocated_hours, notes, is_completed,

            now_utc, now_utc

        ))

        plan_id = cursor.lastrowid



    conn.commit()

    conn.close()

    return plan_id





def get_daily_study_plan(plan_id: int) -> Optional[Dict[str, Any]]:

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("SELECT * FROM daily_study_plans WHERE id = ?", (plan_id,))

    row = cursor.fetchone()

    conn.close()

    return _row_to_study_plan_dict(row) if row else None





def get_daily_study_plan_by_date(plan_date: str, target_role: Optional[str] = None) -> Optional[Dict[str, Any]]:

    conn = get_connection()

    cursor = conn.cursor()

    if target_role:

        cursor.execute("""

            SELECT * FROM daily_study_plans WHERE plan_date = ? AND target_role = ?

            ORDER BY updated_at DESC LIMIT 1

        """, (plan_date, target_role))

    else:

        cursor.execute("""

            SELECT * FROM daily_study_plans WHERE plan_date = ?

            ORDER BY updated_at DESC LIMIT 1

        """, (plan_date,))

    row = cursor.fetchone()

    conn.close()

    return _row_to_study_plan_dict(row) if row else None





def list_daily_study_plans(limit: int = 30) -> List[Dict[str, Any]]:

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("SELECT * FROM daily_study_plans ORDER BY plan_date DESC, updated_at DESC LIMIT ?", (limit,))

    rows = cursor.fetchall()

    conn.close()

    return [_row_to_study_plan_dict(r) for r in rows]





def update_study_task_status(plan_id: int, task_id: str, new_status: str, notes: Optional[str] = None) -> Optional[Dict[str, Any]]:

    plan = get_daily_study_plan(plan_id)

    if not plan:

        return None



    tasks = plan.get("tasks", [])

    task_found = False

    now_utc = datetime.now(timezone.utc).isoformat()



    for task in tasks:

        if task.get("task_id") == task_id:

            task["status"] = new_status

            if new_status == "COMPLETED":

                task["completed_at"] = now_utc

            elif new_status in ("NOT_STARTED", "IN_PROGRESS"):

                task["completed_at"] = None

            task_found = True

            break



    if not task_found:

        return None



    # Check if all tasks completed

    all_completed = len(tasks) > 0 and all(t.get("status") == "COMPLETED" for t in tasks)

    is_completed_flag = 1 if all_completed else 0



    if notes is not None:

        plan["notes"] = notes



    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("""

        UPDATE daily_study_plans SET

            tasks_json = ?,

            is_completed = ?,

            notes = ?,

            updated_at = ?

        WHERE id = ?

    """, (json.dumps(tasks), is_completed_flag, plan.get("notes", ""), now_utc, plan_id))

    conn.commit()

    conn.close()



    plan["tasks"] = tasks

    plan["is_completed"] = bool(is_completed_flag)

    plan["updated_at"] = now_utc

    return plan





def update_daily_study_plan(plan_id: int, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:

    plan = get_daily_study_plan(plan_id)

    if not plan:

        return None



    now_utc = datetime.now(timezone.utc).isoformat()

    conn = get_connection()

    cursor = conn.cursor()



    if "notes" in updates:

        plan["notes"] = updates["notes"]

    if "is_completed" in updates:

        plan["is_completed"] = bool(updates["is_completed"])



    cursor.execute("""

        UPDATE daily_study_plans SET

            notes = ?,

            is_completed = ?,

            updated_at = ?

        WHERE id = ?

    """, (plan.get("notes", ""), 1 if plan.get("is_completed") else 0, now_utc, plan_id))

    conn.commit()

    conn.close()

    plan["updated_at"] = now_utc

    return plan





def get_study_analytics() -> Dict[str, Any]:

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("SELECT * FROM daily_study_plans ORDER BY plan_date ASC")

    rows = cursor.fetchall()

    conn.close()



    plans = [_row_to_study_plan_dict(r) for r in rows]



    total_plans = len(plans)

    completed_plans = sum(1 for p in plans if p.get("is_completed"))

    total_tasks_scheduled = 0

    total_tasks_completed = 0

    total_minutes_studied = 0

    mastered_skills = set()



    for p in plans:

        for t in p.get("tasks", []):

            total_tasks_scheduled += 1

            if t.get("status") == "COMPLETED":

                total_tasks_completed += 1

                total_minutes_studied += int(t.get("duration_minutes") or 0)

                if t.get("skill_tag"):

                    mastered_skills.add(t["skill_tag"])



    # Calculate streak days

    dates_with_completions = sorted({

        p["plan_date"] for p in plans

        if any(t.get("status") == "COMPLETED" for t in p.get("tasks", []))

    })



    current_streak = 0

    if dates_with_completions:

        today_str = datetime.now().strftime("%Y-%m-%d")

        yesterday_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        check_date = datetime.strptime(dates_with_completions[-1], "%Y-%m-%d").date()

        today_date = datetime.now().date()

        if (today_date - check_date).days <= 1:

            current_streak = 1

            prev = check_date

            for d_str in reversed(dates_with_completions[:-1]):

                d = datetime.strptime(d_str, "%Y-%m-%d").date()

                if (prev - d).days == 1:

                    current_streak += 1

                    prev = d

                else:

                    break



    task_completion_rate = round((total_tasks_completed / total_tasks_scheduled * 100), 1) if total_tasks_scheduled > 0 else 0.0



    return {

        "total_plans": total_plans,

        "completed_plans": completed_plans,

        "total_tasks_scheduled": total_tasks_scheduled,

        "total_tasks_completed": total_tasks_completed,

        "total_minutes_studied": total_minutes_studied,

        "total_hours_studied": round(total_minutes_studied / 60.0, 1),

        "task_completion_rate_pct": task_completion_rate,

        "current_streak_days": current_streak,

        "mastered_skills": sorted(list(mastered_skills)),

        "active_days_count": len(dates_with_completions),

    }





# ----------------- Phase 4 Assessment Sandbox CRUD -----------------



def _row_to_challenge_dict(row: sqlite3.Row, include_solution: bool = True) -> Dict[str, Any]:

    d = dict(row)

    for col, default in [

        ("test_fixtures_json", {}),

        ("expected_output_json", []),

        ("options_json", [])

    ]:

        val = d.pop(col, None)

        target_key = col.replace("_json", "")

        if val:

            try:

                d[target_key] = json.loads(val)

            except Exception:

                d[target_key] = default

        else:

            d[target_key] = default



    if not include_solution:

        # Hide solution output from public challenge detail

        d.pop("expected_output", None)

    return d





def _row_to_submission_dict(row: sqlite3.Row) -> Dict[str, Any]:

    d = dict(row)

    val = d.pop("output_json", None)

    if val:

        try:

            d["output"] = json.loads(val)

        except Exception:

            d["output"] = []

    else:

        d["output"] = []

    d["is_passed"] = bool(d.get("is_passed", 0))

    return d





def save_assessment_challenge(data: Dict[str, Any]) -> int:

    conn = get_connection()

    cursor = conn.cursor()

    now_utc = datetime.now(timezone.utc).isoformat()



    uid = data["challenge_uid"]

    title = data["title"]

    category = data["category"]

    difficulty = data.get("difficulty", "MEDIUM")

    question_type = data.get("question_type", "QUERY")

    prompt = data["prompt_markdown"]

    initial_code = data.get("initial_code", "")

    test_fixtures = json.dumps(data.get("test_fixtures", {}))

    expected_output = json.dumps(data.get("expected_output", []))

    options = json.dumps(data.get("options", []))

    explanation = data.get("explanation", "")

    time_limit = int(data.get("time_limit_minutes", 30))



    cursor.execute("SELECT id FROM assessment_challenges WHERE challenge_uid = ?", (uid,))

    row = cursor.fetchone()



    if row:

        cid = row["id"]

        cursor.execute("""

            UPDATE assessment_challenges SET

                title = ?, category = ?, difficulty = ?, question_type = ?,

                prompt_markdown = ?, initial_code = ?, test_fixtures_json = ?,

                expected_output_json = ?, options_json = ?, explanation = ?,

                time_limit_minutes = ?

            WHERE id = ?

        """, (

            title, category, difficulty, question_type, prompt, initial_code,

            test_fixtures, expected_output, options, explanation, time_limit, cid

        ))

    else:

        cursor.execute("""

            INSERT INTO assessment_challenges (

                challenge_uid, title, category, difficulty, question_type,

                prompt_markdown, initial_code, test_fixtures_json,

                expected_output_json, options_json, explanation,

                time_limit_minutes, created_at

            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

        """, (

            uid, title, category, difficulty, question_type, prompt, initial_code,

            test_fixtures, expected_output, options, explanation, time_limit, now_utc

        ))

        cid = cursor.lastrowid



    conn.commit()

    conn.close()

    return cid





def get_assessment_challenge(challenge_id: int, include_solution: bool = True) -> Optional[Dict[str, Any]]:

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("SELECT * FROM assessment_challenges WHERE id = ?", (challenge_id,))

    row = cursor.fetchone()

    conn.close()

    return _row_to_challenge_dict(row, include_solution=include_solution) if row else None





def get_assessment_challenge_by_uid(uid: str, include_solution: bool = True) -> Optional[Dict[str, Any]]:

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("SELECT * FROM assessment_challenges WHERE challenge_uid = ?", (uid,))

    row = cursor.fetchone()

    conn.close()

    return _row_to_challenge_dict(row, include_solution=include_solution) if row else None





def list_assessment_challenges(

    category: Optional[str] = None,

    difficulty: Optional[str] = None,

    question_type: Optional[str] = None,

    include_solution: bool = False

) -> List[Dict[str, Any]]:

    conn = get_connection()

    cursor = conn.cursor()

    query = "SELECT * FROM assessment_challenges WHERE 1=1"

    params: List[Any] = []



    if category:

        query += " AND category = ?"

        params.append(category)

    if difficulty:

        query += " AND difficulty = ?"

        params.append(difficulty.upper())

    if question_type:

        query += " AND question_type = ?"

        params.append(question_type.upper())



    query += " ORDER BY id ASC"

    cursor.execute(query, params)

    rows = cursor.fetchall()

    conn.close()

    return [_row_to_challenge_dict(r, include_solution=include_solution) for r in rows]





def save_assessment_submission(sub_data: Dict[str, Any]) -> int:

    conn = get_connection()

    cursor = conn.cursor()

    now_utc = datetime.now(timezone.utc).isoformat()



    challenge_id = int(sub_data["challenge_id"])

    submitted_code = sub_data.get("submitted_code", "")

    is_passed = 1 if sub_data.get("is_passed") else 0

    exec_time = int(sub_data.get("execution_time_ms", 0))

    tests_passed = int(sub_data.get("tests_passed", 0))

    total_tests = int(sub_data.get("total_tests", 1))

    score = float(sub_data.get("score", 0.0))

    feedback = sub_data.get("feedback_notes", "")

    output_json = json.dumps(sub_data.get("output", []))



    cursor.execute("""

        INSERT INTO assessment_submissions (

            challenge_id, submitted_code, is_passed, execution_time_ms,

            tests_passed, total_tests, score, feedback_notes, output_json, created_at

        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

    """, (

        challenge_id, submitted_code, is_passed, exec_time,

        tests_passed, total_tests, score, feedback, output_json, now_utc

    ))

    sub_id = cursor.lastrowid

    conn.commit()

    conn.close()

    return sub_id





def list_assessment_submissions(challenge_id: Optional[int] = None, limit: int = 50) -> List[Dict[str, Any]]:

    conn = get_connection()

    cursor = conn.cursor()

    if challenge_id:

        cursor.execute("""

            SELECT s.*, c.title as challenge_title, c.category, c.difficulty

            FROM assessment_submissions s

            JOIN assessment_challenges c ON c.id = s.challenge_id

            WHERE s.challenge_id = ?

            ORDER BY s.created_at DESC LIMIT ?

        """, (challenge_id, limit))

    else:

        cursor.execute("""

            SELECT s.*, c.title as challenge_title, c.category, c.difficulty

            FROM assessment_submissions s

            JOIN assessment_challenges c ON c.id = s.challenge_id

            ORDER BY s.created_at DESC LIMIT ?

        """, (limit,))

    rows = cursor.fetchall()

    conn.close()

    return [_row_to_submission_dict(r) for r in rows]





def get_assessment_stats() -> Dict[str, Any]:

    conn = get_connection()

    cursor = conn.cursor()



    cursor.execute("SELECT COUNT(*) as total FROM assessment_challenges")

    total_challenges = cursor.fetchone()["total"]



    cursor.execute("SELECT COUNT(*) as total FROM assessment_submissions")

    total_submissions = cursor.fetchone()["total"]



    cursor.execute("SELECT COUNT(DISTINCT challenge_id) as completed FROM assessment_submissions WHERE is_passed = 1")

    completed_challenges = cursor.fetchone()["completed"]



    cursor.execute("""

        SELECT c.category,

               COUNT(DISTINCT c.id) as total_challenges,

               COUNT(DISTINCT CASE WHEN s.is_passed = 1 THEN c.id END) as passed_challenges

        FROM assessment_challenges c

        LEFT JOIN assessment_submissions s ON s.challenge_id = c.id

        GROUP BY c.category

    """)

    by_category = {r["category"]: {"total": r["total_challenges"], "passed": r["passed_challenges"]} for r in cursor.fetchall()}



    cursor.execute("""

        SELECT c.difficulty,

               COUNT(DISTINCT c.id) as total_challenges,

               COUNT(DISTINCT CASE WHEN s.is_passed = 1 THEN c.id END) as passed_challenges

        FROM assessment_challenges c

        LEFT JOIN assessment_submissions s ON s.challenge_id = c.id

        GROUP BY c.difficulty

    """)

    by_difficulty = {r["difficulty"]: {"total": r["total_challenges"], "passed": r["passed_challenges"]} for r in cursor.fetchall()}



    conn.close()



    rate = round((completed_challenges / total_challenges * 100), 1) if total_challenges > 0 else 0.0



    return {

        "total_challenges": total_challenges,

        "completed_challenges": completed_challenges,

        "pending_challenges": max(0, total_challenges - completed_challenges),

        "completion_rate_pct": rate,

        "total_submissions": total_submissions,

        "by_category": by_category,

        "by_difficulty": by_difficulty

    }





# ----------------- Phase 5 Interview Preparation Sessions CRUD -----------------



def _row_to_interview_prep_dict(row: sqlite3.Row) -> Dict[str, Any]:

    d = dict(row)

    for col, default in [

        ("briefing_json", {}),

        ("checklist_json", []),

        ("answer_drafts_json", {})

    ]:

        val = d.pop(col, None)

        target_key = col.replace("_json", "")

        if val:

            try:

                d[target_key] = json.loads(val)

            except Exception:

                d[target_key] = default

        else:

            d[target_key] = default

    return d





def save_interview_prep_session(data: Dict[str, Any]) -> int:

    conn = get_connection()

    cursor = conn.cursor()

    now_utc = datetime.now(timezone.utc).isoformat()



    job_id = int(data["job_id"])

    employer = data.get("employer_name", "")

    role_title = data.get("role_title", "")

    briefing = json.dumps(data.get("briefing", {}))

    notes = data.get("candidate_notes", "")

    conf = int(data.get("confidence_rating", 0))

    checklist = json.dumps(data.get("checklist", []))

    drafts = json.dumps(data.get("answer_drafts", {}))

    disclaimer = data.get("disclaimer", (

        "Algorithmic interview preparation briefing grounded in vacancy text and verified candidate profile. "

        "Questions are designed for technical readiness and are not guaranteed to appear in live interviews."

    ))



    cursor.execute("SELECT id FROM interview_prep_sessions WHERE job_id = ?", (job_id,))

    row = cursor.fetchone()



    if row:

        sid = row["id"]

        cursor.execute("""

            UPDATE interview_prep_sessions SET

                employer_name = ?, role_title = ?, briefing_json = ?,

                candidate_notes = ?, confidence_rating = ?, checklist_json = ?,

                answer_drafts_json = ?, disclaimer = ?, updated_at = ?

            WHERE id = ?

        """, (employer, role_title, briefing, notes, conf, checklist, drafts, disclaimer, now_utc, sid))

    else:

        cursor.execute("""

            INSERT INTO interview_prep_sessions (

                job_id, employer_name, role_title, briefing_json, candidate_notes,

                confidence_rating, checklist_json, answer_drafts_json, disclaimer,

                created_at, updated_at

            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

        """, (job_id, employer, role_title, briefing, notes, conf, checklist, drafts, disclaimer, now_utc, now_utc))

        sid = cursor.lastrowid



    conn.commit()

    conn.close()

    return sid





def get_interview_prep_session_by_job(job_id: int) -> Optional[Dict[str, Any]]:

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("SELECT * FROM interview_prep_sessions WHERE job_id = ?", (job_id,))

    row = cursor.fetchone()

    conn.close()

    return _row_to_interview_prep_dict(row) if row else None





def update_interview_prep_session(job_id: int, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:

    session = get_interview_prep_session_by_job(job_id)

    if not session:

        return None



    now_utc = datetime.now(timezone.utc).isoformat()

    conn = get_connection()

    cursor = conn.cursor()



    if "candidate_notes" in updates:

        session["candidate_notes"] = str(updates["candidate_notes"])

    if "confidence_rating" in updates:

        session["confidence_rating"] = int(updates["confidence_rating"])

    if "checklist" in updates:

        session["checklist"] = updates["checklist"]

    if "answer_drafts" in updates:

        session["answer_drafts"] = updates["answer_drafts"]



    cursor.execute("""

        UPDATE interview_prep_sessions SET

            candidate_notes = ?,

            confidence_rating = ?,

            checklist_json = ?,

            answer_drafts_json = ?,

            updated_at = ?

        WHERE job_id = ?

    """, (

        session["candidate_notes"],

        session["confidence_rating"],

        json.dumps(session["checklist"]),

        json.dumps(session["answer_drafts"]),

        now_utc,

        job_id

    ))

    conn.commit()

    conn.close()

    session["updated_at"] = now_utc

    return session





def list_interview_prep_sessions(limit: int = 50) -> List[Dict[str, Any]]:

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("""

        SELECT s.*, j.location, j.work_arrangement, j.priority_category

        FROM interview_prep_sessions s

        JOIN jobs j ON j.id = s.job_id

        ORDER BY s.updated_at DESC LIMIT ?

    """, (limit,))

    rows = cursor.fetchall()

    conn.close()

    return [_row_to_interview_prep_dict(r) for r in rows]





def _row_to_interview_workspace(row: sqlite3.Row) -> Dict[str, Any]:

    workspace = dict(row)

    for column, default in (("briefing_json", {}), ("checklist_json", []), ("answer_drafts_json", {})):

        raw = workspace.pop(column, None)

        try:

            workspace[column.removesuffix("_json")] = json.loads(raw) if raw else default

        except (TypeError, ValueError):

            workspace[column.removesuffix("_json")] = default

    return workspace





def create_interview_prep_workspace(data: Dict[str, Any]) -> Dict[str, Any]:

    workspace_id = str(uuid.uuid4())

    now = datetime.now(timezone.utc).isoformat()

    conn = get_connection()

    conn.execute("""

        INSERT INTO interview_prep_workspaces (

            workspace_id, source_type, role_title, job_description, briefing_json,

            candidate_notes, confidence_rating, checklist_json, answer_drafts_json,

            disclaimer, created_at, updated_at

        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

    """, (

        workspace_id, data["source_type"], data["role_title"], data.get("job_description", ""),

        json.dumps(data.get("briefing", {}), ensure_ascii=False), data.get("candidate_notes", ""),

        int(data.get("confidence_rating", 0)), json.dumps(data.get("checklist", []), ensure_ascii=False),

        json.dumps(data.get("answer_drafts", {}), ensure_ascii=False), data.get("disclaimer", ""), now, now,

    ))

    conn.commit()

    row = conn.execute("SELECT * FROM interview_prep_workspaces WHERE workspace_id=?", (workspace_id,)).fetchone()

    conn.close()

    return _row_to_interview_workspace(row)





def get_interview_prep_workspace(workspace_id: str) -> Optional[Dict[str, Any]]:

    conn = get_connection()

    row = conn.execute("SELECT * FROM interview_prep_workspaces WHERE workspace_id=?", (workspace_id,)).fetchone()

    conn.close()

    return _row_to_interview_workspace(row) if row else None





def list_interview_prep_workspaces(limit: int = 50) -> List[Dict[str, Any]]:

    conn = get_connection()

    rows = conn.execute(

        "SELECT * FROM interview_prep_workspaces ORDER BY updated_at DESC LIMIT ?",

        (max(1, min(int(limit), 100)),),

    ).fetchall()

    conn.close()

    return [_row_to_interview_workspace(row) for row in rows]





def update_interview_prep_workspace(workspace_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:

    allowed = {"candidate_notes", "confidence_rating", "checklist", "answer_drafts"}

    if not updates or set(updates) - allowed:

        raise ValueError("Only notes, confidence, checklist, and answer drafts can be updated.")

    workspace = get_interview_prep_workspace(workspace_id)

    if workspace is None:

        return None

    if "candidate_notes" in updates:

        workspace["candidate_notes"] = str(updates["candidate_notes"])

    if "confidence_rating" in updates:

        rating = int(updates["confidence_rating"])

        if rating < 0 or rating > 5:

            raise ValueError("Confidence rating must be between 0 and 5.")

        workspace["confidence_rating"] = rating

    if "checklist" in updates:

        workspace["checklist"] = updates["checklist"]

    if "answer_drafts" in updates:

        workspace["answer_drafts"] = updates["answer_drafts"]

    now = datetime.now(timezone.utc).isoformat()

    conn = get_connection()

    conn.execute("""

        UPDATE interview_prep_workspaces

        SET candidate_notes=?, confidence_rating=?, checklist_json=?, answer_drafts_json=?, updated_at=?

        WHERE workspace_id=?

    """, (

        workspace["candidate_notes"], workspace["confidence_rating"],

        json.dumps(workspace["checklist"], ensure_ascii=False),

        json.dumps(workspace["answer_drafts"], ensure_ascii=False), now, workspace_id,

    ))

    conn.commit()

    conn.close()

    workspace["updated_at"] = now

    return workspace





# ----------------- Personalized Career Preferences DB Methods -----------------



def save_career_preferences_db(profile_id: str, categories: List[str]) -> Dict[str, Any]:

    """Persists candidate career preferences to database."""

    from careerorbit.career_priorities import validate_preference_list

    valid_cats = validate_preference_list(categories)

    now_iso = datetime.now(timezone.utc).isoformat()

    conn = get_connection()

    with conn:

        conn.execute("""

            CREATE TABLE IF NOT EXISTS candidate_career_preferences (

                profile_id TEXT PRIMARY KEY,

                preferences_json TEXT NOT NULL,

                updated_at TEXT NOT NULL

            )

        """)

        conn.execute("""

            INSERT INTO candidate_career_preferences (profile_id, preferences_json, updated_at)

            VALUES (?, ?, ?)

            ON CONFLICT(profile_id) DO UPDATE SET

                preferences_json = excluded.preferences_json,

                updated_at = excluded.updated_at

        """, (profile_id, json.dumps(valid_cats), now_iso))

    conn.close()

    return {"profile_id": profile_id, "selected_categories": valid_cats, "updated_at": now_iso}





def get_career_preferences_db(profile_id: str = "default") -> Optional[List[str]]:

    """Retrieves candidate career preferences from database."""

    conn = get_connection()

    cur = conn.cursor()

    try:

        cur.execute(

            "SELECT preferences_json FROM candidate_career_preferences WHERE profile_id = ?",

            (profile_id,)

        )

        row = cur.fetchone()

        if row:

            try:

                return json.loads(row[0])

            except Exception:

                return None

    except sqlite3.OperationalError:

        return None

    finally:

        conn.close()

    return None















def delete_application(application_id: int) -> bool:
    """Permanently deletes an application and its audit history."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM applications WHERE id = ?", (application_id,))
    if not cursor.fetchone():
        conn.close()
        return False
    cursor.execute("DELETE FROM application_history WHERE application_id = ?", (application_id,))
    cursor.execute("DELETE FROM applications WHERE id = ?", (application_id,))
    conn.commit()
    conn.close()
    return True


def get_application_with_details(app_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve application joined with job and complete audit timeline."""
    app = get_application_by_id(app_id)
    if not app:
        return None
    app["history"] = get_application_history(app_id)
    return app


def update_application_details(application_id: int, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Updates editable metadata on an existing application."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM applications WHERE id = ?", (application_id,))
    app = cursor.fetchone()
    if not app:
        conn.close()
        return None

    now_utc = datetime.now(timezone.utc).isoformat()
    app_dict = dict(app)

    fields: Dict[str, Any] = {}
    for k in ("notes", "interview_stage", "follow_up_date", "cover_letter_text", "next_action",
              "recruiter_name", "recruiter_email", "interview_date", "deadline"):
        if k in updates and updates[k] is not None:
            fields[k] = str(updates[k])

    outreach = app_dict.get("outreach_messages") or "{}"
    if isinstance(outreach, str):
        try:
            outreach = json.loads(outreach)
        except Exception:
            outreach = {}
    if "recruiter_name" in fields:
        outreach["recruiter_name"] = fields["recruiter_name"]
    if "recruiter_email" in fields:
        outreach["recruiter_email"] = fields["recruiter_email"]
    if "interview_date" in fields:
        outreach["interview_date"] = fields["interview_date"]
    if "deadline" in fields:
        outreach["deadline"] = fields["deadline"]
    fields["outreach_messages"] = json.dumps(outreach)

    if "application_answers" in updates and isinstance(updates["application_answers"], dict):
        fields["application_answers"] = json.dumps(updates["application_answers"])

    fields["updated_at"] = now_utc

    set_clauses = [f"{k} = ?" for k in fields]
    vals = list(fields.values()) + [application_id]

    cursor.execute(f"UPDATE applications SET {', '.join(set_clauses)} WHERE id = ?", vals)
    conn.commit()
    conn.close()

    new_status = updates.get("status") or updates.get("application_status") or updates.get("stage")
    if new_status and new_status != app["application_status"]:
        return update_application_stage(
            application_id=application_id,
            new_status=new_status,
            notes=fields.get("notes", "Status updated"),
            actor=str(updates.get("actor") or "CANDIDATE"),
            event_source=str(updates.get("event_source") or "USER_MANUAL")
        )

    return get_application_with_details(application_id)


def create_manual_application(job_data: Dict[str, Any], app_data: Dict[str, Any]) -> int:
    """Creates a candidate-managed application, creating a job lead if job_id is not provided."""
    import re
    import time
    from careerorbit.eligibility import classify_title_to_priority, PRIORITY_LABELS
    from careerorbit.matcher.scorer import JobScorer

    job_id = job_data.get("job_id") or app_data.get("job_id")
    if not job_id:
        employer = str(job_data.get("employer") or app_data.get("employer") or "Direct Employer").strip()
        title = str(job_data.get("title") or app_data.get("title") or "Technical Candidate Opportunity").strip()
        location = str(job_data.get("location") or app_data.get("location") or "India / Remote").strip()
        official_url = str(job_data.get("official_url") or app_data.get("official_url") or "").strip()
        work_arrangement = str(job_data.get("work_arrangement") or "Hybrid").strip()
        salary = str(job_data.get("salary") or "Not Disclosed").strip()

        scorer = JobScorer()
        score_res = scorer.score_job({
            "title": title, "employer": employer, "location": location,
            "work_arrangement": work_arrangement, "description": job_data.get("description", title),
            "salary": salary, "verification_status": "VERIFIED_MANUAL",
        })

        job_uid = f"manual_{re.sub(r'[^a-zA-Z0-9]+', '_', employer.lower())}_{re.sub(r'[^a-zA-Z0-9]+', '_', title.lower())}_{int(time.time())}"
        p_cat = classify_title_to_priority(title)
        manual_job = Job(
            job_uid=job_uid,
            employer=employer,
            title=title,
            normalized_title=title.lower(),
            priority_category=p_cat,
            priority_label=PRIORITY_LABELS[p_cat],
            location=location,
            work_arrangement=work_arrangement,
            salary=salary,
            official_url=official_url or "https://manual-application.local",
            official_listing_url=official_url,
            application_url=official_url,
            canonical_url=official_url or f"https://manual-application.local/{job_uid}",
            discovery_source="Candidate Added",
            verification_status=VerificationStatus.VERIFIED_OPEN,
            verification_notes="Candidate directly initiated application tracking.",
            match_score=score_res["match_score"],
            match_tier=score_res["match_tier"],
            score_breakdown=score_res["score_breakdown"],
            required_skills=score_res["supported_skills"] + score_res["missing_skills"],
            supported_skills=score_res["supported_skills"],
            missing_skills=score_res["missing_skills"],
            description=job_data.get("description") or f"Manually tracked application at {employer} for {title}.",
        )
        job_id = save_job(manual_job)

    status_str = str(app_data.get("application_status") or app_data.get("status") or "SAVED")
    try:
        app_status = ApplicationStatus(status_str)
    except Exception:
        app_status = ApplicationStatus.SAVED

    app_obj = Application(
        job_id=job_id,
        application_status=app_status,
        recruiter_name=str(app_data.get("recruiter_name") or ""),
        recruiter_email=str(app_data.get("recruiter_email") or ""),
        interview_stage=str(app_data.get("interview_stage") or ""),
        interview_date=str(app_data.get("interview_date") or ""),
        follow_up_date=str(app_data.get("follow_up_date") or ""),
        deadline=str(app_data.get("deadline") or ""),
        notes=str(app_data.get("notes") or "Manually tracked application."),
    )
    app_id = create_or_update_application(app_obj)
    update_application_details(app_id, app_data)

    record_application_transition(
        application_id=app_id,
        previous_status="NEW",
        new_status=app_status.value,
        notes=app_data.get("notes") or "Application added to tracker.",
        actor="CANDIDATE",
        event_source="USER_MANUAL",
        evidence="Manual candidate entry"
    )
    return app_id


def export_application_history_to_csv(application_id: Optional[int] = None, filepath: Optional[str] = None) -> str:
    """Exports immutable application audit history records to CSV."""
    out_path = Path(filepath) if filepath else current_exports_dir() / f"application_history_export_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    conn = get_connection()
    cursor = conn.cursor()
    if application_id:
        cursor.execute("""
            SELECT h.*, a.job_id, j.employer, j.title
            FROM application_history h
            JOIN applications a ON h.application_id = a.id
            JOIN jobs j ON a.job_id = j.id
            WHERE h.application_id = ?
            ORDER BY h.timestamp ASC, h.id ASC
        """, (application_id,))
    else:
        cursor.execute("""
            SELECT h.*, a.job_id, j.employer, j.title
            FROM application_history h
            JOIN applications a ON h.application_id = a.id
            JOIN jobs j ON a.job_id = j.id
            ORDER BY h.timestamp DESC, h.id DESC
        """)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    fields = ["id", "application_id", "job_id", "employer", "title", "previous_status", "new_status", "timestamp", "actor", "event_source", "notes", "evidence"]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow({k: _safe_csv_cell(r.get(k, "")) for k in fields})
    return str(out_path)
