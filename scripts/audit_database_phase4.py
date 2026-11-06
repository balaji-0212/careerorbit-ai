"""Audit SQLite schema, integrity, foreign keys, indexes, and migration ledger."""
import json
import sqlite3
from pathlib import Path

DB_PATH = Path("data/careerorbit.db")


def audit():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("PRAGMA integrity_check;")
    integrity = [tuple(r) for r in cur.fetchall()]

    cur.execute("PRAGMA foreign_key_check;")
    fk_violations = [tuple(r) for r in cur.fetchall()]

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name;")
    tables = [r["name"] for r in cur.fetchall()]

    counts = {}
    for t in tables:
        cur.execute(f'SELECT count(*) FROM "{t}";')
        counts[t] = cur.fetchone()[0]

    cur.execute("SELECT name, tbl_name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%';")
    indexes = [{"index": r["name"], "table": r["tbl_name"]} for r in cur.fetchall()]

    cur.execute("SELECT version, applied_at FROM schema_migrations ORDER BY applied_at;")
    migrations = [{"version": r["version"], "applied_at": r["applied_at"]} for r in cur.fetchall()]

    conn.close()

    report = {
        "integrity_check": integrity,
        "foreign_key_violations": fk_violations,
        "table_count": len(tables),
        "tables": tables,
        "row_counts": counts,
        "index_count": len(indexes),
        "indexes": indexes,
        "migration_count": len(migrations),
        "migrations": migrations,
    }

    out_file = Path("reports/DATABASE_AUDIT_REPORT.json")
    out_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Database audit completed successfully:")
    print(f"  - Integrity: {integrity}")
    print(f"  - FK Violations: {len(fk_violations)}")
    print(f"  - Tables: {len(tables)}")
    print(f"  - Indexes: {len(indexes)}")
    print(f"  - Applied Migrations: {len(migrations)}")
    for t, c in counts.items():
        print(f"    * {t}: {c} rows")


if __name__ == "__main__":
    audit()
