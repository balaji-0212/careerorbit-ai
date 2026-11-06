import sqlite3
import shutil
import datetime
from pathlib import Path

db_path = Path("data/careerorbit.db")
timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
backup_path = Path(f"data/careerorbit_backup_{timestamp}.db")
shutil.copy2(db_path, backup_path)
print(f"Backup created at: {backup_path}")

conn = sqlite3.connect(backup_path)
c = conn.cursor()
tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print(f"Tables ({len(tables)}):", tables)
for t in tables:
    count = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f"  {t}: {count} rows")
conn.close()
