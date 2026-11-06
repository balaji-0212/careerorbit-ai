import sqlite3
import json

con = sqlite3.connect('data/careerorbit.db')
con.row_factory = sqlite3.Row
cur = con.cursor()

tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()]
print(f"Total tables: {len(tables)}")
for t in tables:
    cnt = cur.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
    schema = cur.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{t}'").fetchone()[0]
    print(f"\n--- Table: {t} (Count: {cnt}) ---")
    # print columns
    cols = cur.execute(f'PRAGMA table_info("{t}")').fetchall()
    col_names = [f"{c['name']} ({c['type']})" for c in cols]
    print("Columns:", ", ".join(col_names))

print("\nRecent schema migrations:")
for row in cur.execute("SELECT * FROM schema_migrations ORDER BY applied_at DESC").fetchall():
    print(dict(row))

con.close()
