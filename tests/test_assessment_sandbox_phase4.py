"""Phase 4 — Technical Assessment Sandbox & Evaluator Tests.

Tests challenge seeding, safe in-memory SQL execution, query validation,
security constraint enforcement, multiple-choice evaluation, attempt persistence,
and REST API endpoints.
"""

from __future__ import annotations

import json
import pytest

from careerorbit.database.db import (
    init_db,
    get_assessment_challenge,
    list_assessment_challenges,
    list_assessment_submissions,
    get_assessment_stats
)
from careerorbit.prep.assessment_sandbox import (
    seed_assessment_challenges,
    evaluate_sql_submission,
    evaluate_conceptual_submission,
    evaluate_submission
)
from careerorbit.web.app import app


async def asgi_request(app, method="GET", path="/", query="", body=b"", headers=None):
    from tests.authenticated_request import authenticated_headers
    headers = authenticated_headers(method, headers)
    """Simple in-process ASGI test helper."""
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "path": path,
        "raw_path": path.encode(),
        "query_string": query.encode(),
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "server": ("127.0.0.1", 8000),
        "client": ("127.0.0.1", 54321),
    }
    messages = []
    received = False

    async def receive():
        nonlocal received
        if not received:
            received = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        messages.append(message)

    await app(scope, receive, send)

    status_code = None
    response_headers = {}
    body_parts = []
    for m in messages:
        if m["type"] == "http.response.start":
            status_code = m["status"]
            response_headers = {k.decode().lower(): v.decode() for k, v in m.get("headers", [])}
        elif m["type"] == "http.response.body":
            body_parts.append(m.get("body", b""))

    return status_code, response_headers, b"".join(body_parts)


@pytest.fixture(autouse=True)
def setup_test_db():
    init_db()


def test_assessment_challenges_seeding_and_coverage():
    """Verify curated assessment challenge bank seeds with full topic and difficulty coverage."""
    init_db()
    seed_assessment_challenges()

    challenges = list_assessment_challenges()
    assert len(challenges) >= 12

    categories = {c["category"] for c in challenges}
    assert "SQL" in categories
    assert "PYTHON" in categories
    assert "DATA_ENGINEERING" in categories
    assert "MACHINE_LEARNING" in categories

    difficulties = {c["difficulty"] for c in challenges}
    assert "EASY" in difficulties
    assert "MEDIUM" in difficulties
    assert "HARD" in difficulties

    # Verify SQL challenges include test fixtures
    sql_chall = next(c for c in challenges if c["category"] == "SQL")
    assert "schema_sql" in sql_chall["test_fixtures"]
    assert "seed_sql" in sql_chall["test_fixtures"]


def test_sql_sandbox_correct_query():
    """Verify safe in-memory SQL evaluation correctly matches benchmark outputs."""
    init_db()
    seed_assessment_challenges()

    challenges = list_assessment_challenges(category="SQL", include_solution=True)
    repeat_order_chall = next(c for c in challenges if c["challenge_uid"] == "sql-customer-repeat-orders")

    # Correct query
    correct_sql = """
        SELECT customer_id, COUNT(*) as total_orders, SUM(order_amount) as total_spend
        FROM orders
        GROUP BY customer_id
        HAVING COUNT(*) >= 3 AND SUM(order_amount) >= 1000
        ORDER BY total_spend DESC;
    """
    result = evaluate_sql_submission(repeat_order_chall, correct_sql)

    assert result["is_passed"] is True
    assert result["tests_passed"] == 1
    assert result["score"] == 100.0
    assert "matches expected benchmark" in result["feedback_notes"]
    assert len(result["output"]) == 2
    assert result["output"][0]["customer_id"] == 103


def test_sql_sandbox_incorrect_query_returns_clean_feedback():
    """Verify incorrect SQL query does not crash and provides actionable feedback."""
    init_db()
    seed_assessment_challenges()

    challenges = list_assessment_challenges(category="SQL", include_solution=True)
    repeat_order_chall = next(c for c in challenges if c["challenge_uid"] == "sql-customer-repeat-orders")

    # Incorrect query (wrong group condition)
    incorrect_sql = "SELECT customer_id, 1 as total_orders, 500.0 as total_spend FROM orders LIMIT 1;"
    result = evaluate_sql_submission(repeat_order_chall, incorrect_sql)

    assert result["is_passed"] is False
    assert result["score"] == 0.0
    assert "mismatch" in result["feedback_notes"].lower()


def test_sql_sandbox_security_rules_enforcement():
    """Verify sandbox rejects non-SELECT statements and multiple queries."""
    init_db()
    seed_assessment_challenges()

    challenges = list_assessment_challenges(category="SQL", include_solution=True)
    chall = challenges[0]

    # 1. DROP TABLE rejection
    drop_attempt = "DROP TABLE employees; SELECT 1;"
    res1 = evaluate_sql_submission(chall, drop_attempt)
    assert res1["is_passed"] is False
    assert "Security Rule" in res1["feedback_notes"]

    # 2. Multiple statements rejection
    multi_attempt = "SELECT * FROM employees; SELECT * FROM employees;"
    res2 = evaluate_sql_submission(chall, multi_attempt)
    assert res2["is_passed"] is False
    assert "Multiple SQL statements" in res2["feedback_notes"]

    # 3. Non-SELECT rejection
    insert_attempt = "INSERT INTO employees VALUES (99, 'Bad', 'Dept', 10);"
    res3 = evaluate_sql_submission(chall, insert_attempt)
    assert res3["is_passed"] is False
    assert "Only read-only SELECT" in res3["feedback_notes"]


def test_conceptual_multiple_choice_evaluator():
    """Verify deterministic multiple-choice evaluation for Python, Data Engineering, and ML."""
    init_db()
    seed_assessment_challenges()

    challenges = list_assessment_challenges(category="PYTHON", include_solution=True)
    dsa_chall = next(c for c in challenges if c["challenge_uid"] == "py-dsa-lookup-complexity")

    # Correct answer: C (List: O(N), Set: O(1))
    res_correct = evaluate_conceptual_submission(dsa_chall, "C")
    assert res_correct["is_passed"] is True
    assert res_correct["score"] == 100.0
    assert "Correct" in res_correct["feedback_notes"]

    # Incorrect answer: A
    res_wrong = evaluate_conceptual_submission(dsa_chall, "A")
    assert res_wrong["is_passed"] is False
    assert res_wrong["score"] == 0.0
    assert "Incorrect" in res_wrong["feedback_notes"]


def test_universal_evaluate_submission_and_persistence():
    """Verify evaluate_submission records submission history and updates overall stats."""
    init_db()
    seed_assessment_challenges()

    challenges = list_assessment_challenges(category="SQL", include_solution=True)
    chall = next(c for c in challenges if c["challenge_uid"] == "sql-customer-repeat-orders")
    cid = chall["id"]

    query = """
        SELECT customer_id, COUNT(*) as total_orders, SUM(order_amount) as total_spend
        FROM orders
        GROUP BY customer_id
        HAVING COUNT(*) >= 3 AND SUM(order_amount) >= 1000
        ORDER BY total_spend DESC;
    """
    res = evaluate_submission(cid, query)
    assert res["is_passed"] is True
    assert res["id"] is not None

    # Check persistence in assessment_submissions
    subs = list_assessment_submissions(challenge_id=cid)
    assert len(subs) == 1
    assert subs[0]["is_passed"] is True
    assert subs[0]["score"] == 100.0

    # Check overall stats
    stats = get_assessment_stats()
    assert stats["total_challenges"] >= 12
    assert stats["completed_challenges"] >= 1
    assert stats["total_submissions"] >= 1
    assert "SQL" in stats["by_category"]


@pytest.mark.anyio
async def test_api_assessments_endpoints():
    """Verify all /api/assessments/ REST endpoints function with valid status codes and contracts."""
    init_db()
    seed_assessment_challenges()

    # 1. GET /api/assessments/challenges
    st, _, body = await asgi_request(app, method="GET", path="/api/assessments/challenges")
    assert st == 200
    data = json.loads(body.decode())
    assert "challenges" in data
    assert len(data["challenges"]) >= 12

    first_chall = data["challenges"][0]
    cid = first_chall["id"]
    # Verify expected_output is NOT disclosed in public listing
    assert "expected_output" not in first_chall

    # 2. Filter challenges by category
    st_filter, _, body_filter = await asgi_request(app, method="GET", path="/api/assessments/challenges", query="category=SQL")
    assert st_filter == 200
    sql_data = json.loads(body_filter.decode())
    assert all(c["category"] == "SQL" for c in sql_data["challenges"])

    # 3. GET /api/assessments/challenges/{id}
    st_single, _, body_single = await asgi_request(app, method="GET", path=f"/api/assessments/challenges/{cid}")
    assert st_single == 200
    single_data = json.loads(body_single.decode())
    assert single_data["id"] == cid
    assert "expected_output" not in single_data

    # 4. POST /api/assessments/challenges/{id}/evaluate
    eval_payload = json.dumps({"submitted_code": "SELECT 1;"}).encode()
    st_eval, _, body_eval = await asgi_request(
        app, method="POST", path=f"/api/assessments/challenges/{cid}/evaluate",
        body=eval_payload, headers={"content-type": "application/json"}
    )
    assert st_eval == 200
    eval_resp = json.loads(body_eval.decode())
    assert "is_passed" in eval_resp
    assert "score" in eval_resp
    assert "explanation" in eval_resp

    # 5. GET /api/assessments/submissions
    st_subs, _, body_subs = await asgi_request(app, method="GET", path="/api/assessments/submissions")
    assert st_subs == 200
    subs_resp = json.loads(body_subs.decode())
    assert len(subs_resp["submissions"]) >= 1

    # 6. GET /api/assessments/stats
    st_stats, _, body_stats = await asgi_request(app, method="GET", path="/api/assessments/stats")
    assert st_stats == 200
    stats_resp = json.loads(body_stats.decode())
    assert "total_challenges" in stats_resp
    assert "completion_rate_pct" in stats_resp

    # 7. Nonexistent challenge returns 404
    st_404, _, _ = await asgi_request(app, method="GET", path="/api/assessments/challenges/999999")
    assert st_404 == 404
