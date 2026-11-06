"""Unit and integration tests for Phase 4: Live Result Ranking and Status Filtering.

Verifies:
1. Active verified opportunities include ONLY:
   - record_state != 'QUARANTINED'
   - verification_status == 'VERIFIED_OPEN'
   - match_tier != 'Ineligible'
2. Roles with PENDING_VERIFICATION are excluded from active and placed in pending.
3. Roles with VERIFIED_CLOSED are strictly excluded from active opportunities.
4. Roles with QUARANTINED are strictly excluded from active opportunities.
5. Ineligible roles are excluded from active opportunities.
6. Sorting: Primary = priority_category ASC (P1 before P2, etc.).
7. Sorting: Secondary = match_score DESC.
8. Sorting: Tertiary = posting_date DESC.
"""

import sqlite3
import pytest


@pytest.fixture
def test_db():
    """Isolated in-memory SQLite database pre-populated with test job states."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employer TEXT NOT NULL,
            title TEXT NOT NULL,
            priority_category INTEGER NOT NULL,
            priority_label TEXT NOT NULL,
            location TEXT NOT NULL,
            match_score REAL NOT NULL,
            match_tier TEXT NOT NULL,
            verification_status TEXT NOT NULL,
            record_state TEXT NOT NULL DEFAULT 'ACTIVE',
            posting_date TEXT,
            official_url TEXT NOT NULL DEFAULT '',
            application_url TEXT NOT NULL DEFAULT ''
        );
    """)

    # Populate 8 test scenarios:
    jobs = [
        # 1. prime P1 open job
        ("Acme Corp", "Junior Data Analyst", 1, "Data Analyst / BI / Power BI / Reporting", "Bengaluru", 85.0, "Strong match", "VERIFIED_OPEN", "ACTIVE", "2026-03-01T10:00:00Z"),
        # 2. prime P1 closed job (like Caterpillar bug) - must NOT be in active
        ("Caterpillar", "Junior Data Analyst Closed", 1, "Data Analyst / BI / Power BI / Reporting", "Bengaluru", 95.0, "Strong match", "VERIFIED_CLOSED", "ACTIVE", "2026-03-02T10:00:00Z"),
        # 3. P1 pending verification - must be in pending, not active
        ("Beta Analytics", "BI Analyst", 1, "Data Analyst / BI / Power BI / Reporting", "Chennai", 88.0, "Strong match", "PENDING_VERIFICATION", "ACTIVE", "2026-03-01T12:00:00Z"),
        # 4. Quarantined role - must NOT be in active
        ("Overseas Ltd", "Data Analyst", 1, "Data Analyst / BI / Power BI / Reporting", "New York", 90.0, "Strong match", "VERIFIED_OPEN", "QUARANTINED", "2026-03-01T10:00:00Z"),
        # 5. Ineligible role - must NOT be in active
        ("Gamma Corp", "Creative Intern", 0, "Ineligible", "Bengaluru", 0.0, "Ineligible", "VERIFIED_OPEN", "ACTIVE", "2026-03-01T10:00:00Z"),
        # 6. P2 Data Scientist open job - lower score than Caterpillar, but open
        ("DataTech", "Junior Data Scientist", 2, "Data Scientist / Junior Data Scientist", "Bengaluru", 80.0, "Strong match", "VERIFIED_OPEN", "ACTIVE", "2026-03-01T10:00:00Z"),
        # 7. P1 open job with lower score to test match_score ordering within priority
        ("Delta Systems", "Reporting Analyst", 1, "Data Analyst / BI / Power BI / Reporting", "Bengaluru", 75.0, "Reasonable match", "VERIFIED_OPEN", "ACTIVE", "2026-03-01T10:00:00Z"),
        # 8. P1 open job with same score as Acme Corp but newer date to test tertiary sorting
        ("Epsilon BI", "Power BI Specialist", 1, "Data Analyst / BI / Power BI / Reporting", "Bengaluru", 85.0, "Strong match", "VERIFIED_OPEN", "ACTIVE", "2026-03-02T10:00:00Z"),
    ]

    for j in jobs:
        cur.execute("""
            INSERT INTO jobs (employer, title, priority_category, priority_label, location, match_score, match_tier, verification_status, record_state, posting_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, j)
    conn.commit()
    yield conn
    conn.close()


def test_active_verified_opportunities_excludes_closed_and_quarantined(test_db):
    """Test Case 1, 2, 4, 5: Active query only returns VERIFIED_OPEN, ACTIVE record_state, eligible tier."""
    cur = test_db.cursor()
    cur.execute("""
        SELECT id, employer, title, priority_category, match_score, verification_status, record_state, match_tier
        FROM jobs
        WHERE record_state != 'QUARANTINED'
          AND verification_status = 'VERIFIED_OPEN'
          AND match_tier != 'Ineligible'
        ORDER BY priority_category ASC, match_score DESC, posting_date DESC;
    """)
    rows = [dict(r) for r in cur.fetchall()]

    employers = [r["employer"] for r in rows]
    # Caterpillar (VERIFIED_CLOSED) must NOT be present
    assert "Caterpillar" not in employers
    # Overseas Ltd (QUARANTINED) must NOT be present
    assert "Overseas Ltd" not in employers
    # Beta Analytics (PENDING_VERIFICATION) must NOT be present
    assert "Beta Analytics" not in employers
    # Gamma Corp (Ineligible) must NOT be present
    assert "Gamma Corp" not in employers

    # Verified open roles must be present
    assert "Acme Corp" in employers
    assert "Epsilon BI" in employers
    assert "Delta Systems" in employers
    assert "DataTech" in employers


def test_pending_verification_query_separates_pending_jobs(test_db):
    """Test Case 3: PENDING_VERIFICATION is isolated into its own query."""
    cur = test_db.cursor()
    cur.execute("""
        SELECT employer, verification_status
        FROM jobs
        WHERE record_state != 'QUARANTINED'
          AND verification_status = 'PENDING_VERIFICATION'
          AND match_tier != 'Ineligible';
    """)
    rows = [dict(r) for r in cur.fetchall()]
    assert len(rows) == 1
    assert rows[0]["employer"] == "Beta Analytics"


def test_verified_closed_query_isolates_expired_roles(test_db):
    """Test Case 2: VERIFIED_CLOSED is isolated into closed section."""
    cur = test_db.cursor()
    cur.execute("""
        SELECT employer, verification_status
        FROM jobs
        WHERE verification_status = 'VERIFIED_CLOSED';
    """)
    rows = [dict(r) for r in cur.fetchall()]
    assert len(rows) == 1
    assert rows[0]["employer"] == "Caterpillar"


def test_active_verified_ranking_orders_priority_then_score_then_date(test_db):
    """Test Cases 6, 7, 8:
    Primary sort: priority_category ASC (P1 before P2)
    Secondary sort: match_score DESC (85.0 before 75.0)
    Tertiary sort: posting_date DESC (2026-03-02 before 2026-03-01)
    """
    cur = test_db.cursor()
    cur.execute("""
        SELECT employer, priority_category, match_score, posting_date
        FROM jobs
        WHERE record_state != 'QUARANTINED'
          AND verification_status = 'VERIFIED_OPEN'
          AND match_tier != 'Ineligible'
        ORDER BY priority_category ASC, match_score DESC, posting_date DESC;
    """)
    rows = [dict(r) for r in cur.fetchall()]

    # Expected order:
    # 1. Epsilon BI (P1, 85.0, 2026-03-02)
    # 2. Acme Corp (P1, 85.0, 2026-03-01)
    # 3. Delta Systems (P1, 75.0, 2026-03-01)
    # 4. DataTech (P2, 80.0, 2026-03-01)
    assert len(rows) == 4
    assert rows[0]["employer"] == "Epsilon BI"
    assert rows[1]["employer"] == "Acme Corp"
    assert rows[2]["employer"] == "Delta Systems"
    assert rows[3]["employer"] == "DataTech"

    # Verify P1 roles come before P2 even if P2 has a higher score than a P1 role
    # DataTech has score 80.0, Delta Systems has score 75.0, but Delta is P1, so Delta is ranked higher!
    delta_idx = next(i for i, r in enumerate(rows) if r["employer"] == "Delta Systems")
    datatech_idx = next(i for i, r in enumerate(rows) if r["employer"] == "DataTech")
    assert delta_idx < datatech_idx, "Priority 1 role must rank above Priority 2 role"
