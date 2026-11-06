import sys
import os
import sqlite3
from pathlib import Path

def inspect_baseline():
    print("=" * 60)
    print("PHASE A: BASELINE SYSTEM & DATABASE INSPECTION")
    print("=" * 60)
    print(f"Python Version: {sys.version}")
    print(f"Executable:     {sys.executable}")
    print(f"CWD:            {os.getcwd()}")
    
    db_path = Path("data/careerorbit.db")
    print(f"\nDatabase File:  {db_path.resolve()}")
    if not db_path.exists():
        print("ERROR: Database file does not exist!")
        return
        
    print(f"Database Size:  {db_path.stat().st_size:,} bytes")
    
    con = sqlite3.connect(str(db_path))
    cur = con.cursor()
    
    cur.execute("PRAGMA integrity_check;")
    integrity = cur.fetchall()
    print(f"Integrity Check: {integrity}")
    
    cur.execute("PRAGMA journal_mode;")
    journal_mode = cur.fetchone()[0]
    print(f"Journal Mode:    {journal_mode}")
    
    cur.execute("PRAGMA foreign_key_check;")
    fk_violations = cur.fetchall()
    print(f"FK Violations:   {len(fk_violations)} violations")
    if fk_violations:
        for v in fk_violations:
            print(f"   Violation: {v}")
            
    cur.execute("PRAGMA user_version;")
    user_version = cur.fetchone()[0]
    print(f"User Version:    {user_version}")
    
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name;")
    tables = [r[0] for r in cur.fetchall()]
    print(f"\nTotal Relational Tables: {len(tables)}")
    total_rows = 0
    for t in tables:
        cur.execute(f'SELECT count(*) FROM "{t}";')
        cnt = cur.fetchone()[0]
        total_rows += cnt
        print(f"  * {t:<25} {cnt:>6} rows")
    print(f"Total Database Rows: {total_rows}")
    
    # Check schema_migrations
    if "schema_migrations" in tables:
        print("\nRecorded Schema Migrations:")
        cur.execute("SELECT version, applied_at FROM schema_migrations ORDER BY applied_at;")
        for mver, applied_at in cur.fetchall():
            print(f"  * {mver:<60} applied at {applied_at}")
            
    con.close()

if __name__ == "__main__":
    inspect_baseline()
