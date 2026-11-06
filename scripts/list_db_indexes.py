"""List all SQLite indexes in data/careerorbit.db."""
import sqlite3

conn = sqlite3.connect("data/careerorbit.db")
c = conn.cursor()
c.execute("SELECT tbl_name, name FROM sqlite_master WHERE type='index' ORDER BY tbl_name, name")
indexes = c.fetchall()
print(f"Total indexes in DB: {len(indexes)}")
for tbl, idx in indexes:
    print(f"  {tbl}: {idx}")
conn.close()
