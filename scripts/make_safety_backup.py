import sqlite3
import datetime
import os
import sys

def main():
    src_db = "data/careerorbit.db"
    if not os.path.exists(src_db):
        print(f"ERROR: {src_db} does not exist!")
        sys.exit(1)
    
    os.makedirs("data/backups", exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    dst_db = f"data/backups/careerorbit_master_safety_backup_{ts}.db"

    src = sqlite3.connect(src_db)
    dst = sqlite3.connect(dst_db)
    src.backup(dst)
    dst.close()
    src.close()

    verify = sqlite3.connect(dst_db)
    check = verify.execute("PRAGMA integrity_check;").fetchall()
    tables = [r[0] for r in verify.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()]
    counts = {}
    for t in tables:
        counts[t] = verify.execute(f"SELECT COUNT(*) FROM [{t}];").fetchone()[0]
    verify.close()

    print(f"Backup created: {dst_db}")
    print(f"Integrity check: {check}")
    print(f"Tables ({len(tables)}):")
    for t, c in counts.items():
        print(f"  - {t}: {c} rows")

if __name__ == "__main__":
    main()
