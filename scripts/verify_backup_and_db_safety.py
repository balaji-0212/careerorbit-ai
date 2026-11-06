import sys
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

def verify_backups():
    print("=" * 60)
    print("PHASE B: DATABASE SAFETY & BACKUP VERIFICATION")
    print("=" * 60)
    
    backup_file = Path("data/backups/careerorbit_phase1_pre_migration_20261024_115515.db")
    active_db = Path("data/careerorbit.db")
    
    print(f"Target Backup: {backup_file.resolve()}")
    if not backup_file.exists():
        print(f"ERROR: Backup file {backup_file} does not exist!")
        return
        
    print(f"Backup Size:   {backup_file.stat().st_size:,} bytes")
    print(f"Active DB:     {active_db.resolve()} ({active_db.stat().st_size:,} bytes)")
    
    # 1. Read-only integrity check on backup
    uri_backup = f"file:{backup_file.resolve().as_posix()}?mode=ro"
    b_con = sqlite3.connect(uri_backup, uri=True)
    b_cur = b_con.cursor()
    
    b_cur.execute("PRAGMA integrity_check;")
    b_integrity = b_cur.fetchall()
    print(f"\n1. Backup Integrity Check: {b_integrity}")
    assert b_integrity == [("ok",)], "Backup failed integrity check!"
    
    # 2. Foreign-key check on backup
    b_cur.execute("PRAGMA foreign_key_check;")
    b_fk = b_cur.fetchall()
    print(f"2. Backup Foreign-Key Violations: {len(b_fk)}")
    
    # 3. Active DB read-only connection
    uri_active = f"file:{active_db.resolve().as_posix()}?mode=ro"
    a_con = sqlite3.connect(uri_active, uri=True)
    a_cur = a_con.cursor()
    
    a_cur.execute("PRAGMA integrity_check;")
    a_integrity = a_cur.fetchall()
    print(f"3. Active DB Integrity Check: {a_integrity}")
    assert a_integrity == [("ok",)], "Active DB failed integrity check!"
    
    a_cur.execute("PRAGMA foreign_key_check;")
    a_fk = a_cur.fetchall()
    print(f"4. Active DB Foreign-Key Violations: {len(a_fk)}")
    
    # 4. Compare tables & row counts between Backup (Pre-Migration) and Active DB (Post-Migration)
    b_cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name;")
    b_tables = {r[0] for r in b_cur.fetchall()}
    
    a_cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name;")
    a_tables = {r[0] for r in a_cur.fetchall()}
    
    all_tables = sorted(list(b_tables | a_tables))
    print(f"\n5. Schema & Table Comparison (Pre-Migration Backup vs Active DB):")
    print(f"{'Table Name':<25} | {'Backup (Pre)':<12} | {'Active (Post)':<12} | {'Delta':<8}")
    print("-" * 65)
    
    for t in all_tables:
        b_cnt = "N/A"
        if t in b_tables:
            b_cur.execute(f'SELECT count(*) FROM "{t}";')
            b_cnt = b_cur.fetchone()[0]
            
        a_cnt = "N/A"
        if t in a_tables:
            a_cur.execute(f'SELECT count(*) FROM "{t}";')
            a_cnt = a_cur.fetchone()[0]
            
        delta = (a_cnt - b_cnt) if (isinstance(b_cnt, int) and isinstance(a_cnt, int)) else "NEW" if b_cnt == "N/A" else "REMOVED"
        print(f"{t:<25} | {str(b_cnt):<12} | {str(a_cnt):<12} | {str(delta):<8}")
        
    # 6. Verify historical application and resume records remain present
    a_cur.execute("SELECT count(*) FROM applications;")
    app_cnt = a_cur.fetchone()[0]
    print(f"\n6. Historical Applications in Active DB: {app_cnt} (Must be >= 10)")
    assert app_cnt >= 10, "Historical application records lost!"
    
    a_cur.execute("SELECT count(*) FROM resumes;")
    res_cnt = a_cur.fetchone()[0]
    print(f"   Historical Resumes in Active DB:      {res_cnt} (Must be >= 12)")
    assert res_cnt >= 12, "Historical resume records lost!"
    
    # 7. Confirm application_history records reference valid application records
    a_cur.execute("""
        SELECT h.id, h.application_id, h.previous_status, h.new_status, a.id
        FROM application_history h
        LEFT JOIN applications a ON h.application_id = a.id
        WHERE a.id IS NULL;
    """)
    orphans = a_cur.fetchall()
    print(f"\n7. Orphaned application_history records: {len(orphans)}")
    if orphans:
        print(f"   ERROR: Found orphaned history rows: {orphans}")
    assert len(orphans) == 0, "application_history references nonexistent applications!"
    
    # Check that application_history has valid records
    a_cur.execute("SELECT count(*) FROM application_history;")
    hist_cnt = a_cur.fetchone()[0]
    print(f"   Total application_history records:    {hist_cnt}")
    assert hist_cnt > 0, "application_history has no records!"
    
    # 8. Create a new timestamped validation backup before any testing
    backup_dir = Path("data/backups")
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    new_backup_path = backup_dir / f"careerorbit_audit_safety_backup_{ts}.db"
    
    full_con = sqlite3.connect(str(active_db))
    with sqlite3.connect(str(new_backup_path)) as new_b_con:
        full_con.backup(new_b_con)
    full_con.close()
    
    print(f"\n8. Created Safety Audit Backup: {new_backup_path.resolve()}")
    print(f"   New Backup Size: {new_backup_path.stat().st_size:,} bytes")
    
    # Check new backup integrity
    with sqlite3.connect(f"file:{new_backup_path.resolve().as_posix()}?mode=ro", uri=True) as chk_con:
        chk_res = chk_con.execute("PRAGMA integrity_check;").fetchall()
        print(f"   New Backup Integrity: {chk_res}")
        assert chk_res == [("ok",)], "New backup failed integrity check!"
        
    b_con.close()
    a_con.close()
    print("\nALL PHASE B DATABASE SAFETY VERIFICATIONS COMPLETED SUCCESSFULLY!")

if __name__ == "__main__":
    verify_backups()
