import sqlite3
import shutil
import datetime
from pathlib import Path
from careerorbit.config.settings import SETTINGS

def create_backup():
    db_path = SETTINGS.DATABASE_PATH
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = SETTINGS.DATA_DIR / "backups" / f"careerorbit_phase2_pre_slice21_{ts}.db"
    ext_backup_dir = Path("C:/Users/Abi/.gemini/antigravity/brain/b8c7b5ae-90d7-4d99-9c58-188fac4bf40c/db_backups")
    ext_backup_dir.mkdir(parents=True, exist_ok=True)
    ext_backup_path = ext_backup_dir / f"careerorbit_phase2_safety_{ts}.db"

    # Use atomic SQLite backup API
    src = sqlite3.connect(str(db_path))
    dst = sqlite3.connect(str(backup_path))
    src.backup(dst)
    dst.close()
    src.close()

    # Also copy outside normal database path
    shutil.copy2(backup_path, ext_backup_path)

    # Verify backup integrity
    v_conn = sqlite3.connect(str(backup_path))
    v_cur = v_conn.cursor()
    integrity = v_cur.execute("PRAGMA integrity_check").fetchall()
    fk_check = v_cur.execute("PRAGMA foreign_key_check").fetchall()
    tables = [r[0] for r in v_cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()]
    counts = {t: v_cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}
    v_conn.close()

    print(f"Source DB Size: {db_path.stat().st_size}")
    print(f"Backup Path: {backup_path} Size: {backup_path.stat().st_size}")
    print(f"External Backup Path: {ext_backup_path} Size: {ext_backup_path.stat().st_size}")
    print(f"Backup Integrity: {integrity}")
    print(f"Backup FK Check: {fk_check}")
    print("Table Counts:")
    for t in sorted(counts.keys()):
        print(f"  {t}: {counts[t]}")

if __name__ == "__main__":
    create_backup()
