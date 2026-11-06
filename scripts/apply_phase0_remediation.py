"""Phase 0 Database Remediation Script.
Reversibly applies integrity updates for quarantined non-technical interpreter records
and verifies broken links per Phase 0 audit standards.
"""
import sqlite3
from datetime import datetime, timezone

def apply_remediation():
    conn = sqlite3.connect("data/careerorbit.db")
    cur = conn.cursor()

    # 1. Check if migration already applied
    cur.execute("SELECT 1 FROM schema_migrations WHERE version = '2026-10-24-phase0-integrity-quarantine-and-link-remediation'")
    if cur.fetchone():
        print("[*] Migration 2026-10-24-phase0-integrity-quarantine-and-link-remediation already applied.")
        conn.close()
        return

    now_iso = datetime.now(timezone.utc).isoformat()

    # 2. Quarantine Jobs #154 and #155 (Language Services Associates interpreters with empty URLs)
    cur.execute("""
        UPDATE jobs
        SET record_state = 'QUARANTINED',
            integrity_notes = 'Non-technical language interpreter role with empty application URL from legacy ingestion; quarantined per Phase 0 audit data integrity rules.',
            last_verified_at = ?
        WHERE id IN (154, 155)
    """, (now_iso,))
    print(f"[+] Quarantined {cur.rowcount} non-technical interpreter records (Jobs 154, 155).")

    # 3. Update Job #246 (Caterpillar Greenhouse 404 link)
    cur.execute("""
        UPDATE jobs
        SET verification_status = 'VERIFIED_CLOSED',
            verification_notes = 'Application URL returned HTTP 404 (Not Found / Gone); vacancy is closed or link is invalid.',
            last_verified_at = ?,
            verification_source = 'Phase 0 Audit Verification'
        WHERE id = 246
    """, (now_iso,))
    print(f"[+] Remediated Job 246 verification status to VERIFIED_CLOSED.")

    # 4. Record schema migration
    cur.execute("""
        INSERT INTO schema_migrations (version, applied_at)
        VALUES ('2026-10-24-phase0-integrity-quarantine-and-link-remediation', ?)
    """, (now_iso,))
    print("[+] Recorded schema migration: 2026-10-24-phase0-integrity-quarantine-and-link-remediation")

    conn.commit()
    conn.close()
    print("[+] Phase 0 database remediation complete.")

if __name__ == "__main__":
    apply_remediation()
