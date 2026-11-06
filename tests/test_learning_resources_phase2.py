"""Tests for Phase 2 Slice 2.1 — Learning Resource Library & Structured Pathways."""

from __future__ import annotations

import json
import sqlite3
import pytest

from careerorbit.database.db import (
    init_db,
    get_connection,
    save_learning_resource,
    list_learning_resources,
    get_learning_resource,
    delete_learning_resource,
    toggle_learning_resource_completion,
    get_learning_resources_stats,
)
from careerorbit.prep.curated_resources import (
    CURATED_LEARNING_RESOURCES,
    seed_curated_learning_resources,
)
from careerorbit.prep.pathways import get_learning_pathways, PATHWAY_DEFINITIONS
from careerorbit.web.app import app


@pytest.fixture(autouse=True)
def setup_test_db():
    init_db()


async def asgi_call(app, method: str, path: str, query: str = "", body: bytes = b""):
    from tests.authenticated_request import authenticated_headers
    request_headers = authenticated_headers(method, {"host": "127.0.0.1:8000", "content-type": "application/json"})
    scope = {
        "type": "http",
        "scheme": "http",
        "method": method,
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": query.encode("ascii"),
        "headers": [(key.lower().encode(), value.encode()) for key, value in request_headers.items()],
        "server": ("127.0.0.1", 8000),
        "client": ("127.0.0.1", 54321),
    }
    response_headers = []
    response_body = []
    status_code = 200

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        nonlocal status_code, response_headers, response_body
        if message["type"] == "http.response.start":
            status_code = message["status"]
            response_headers = message["headers"]
        elif message["type"] == "http.response.body":
            response_body.append(message.get("body", b""))

    await app(scope, receive, send)
    return status_code, response_headers, b"".join(response_body)


# ----------------- 1. Schema & Migration Tests -----------------

def test_learning_resources_metadata_schema_and_indexes():
    """Verify that all Phase 2 metadata columns and indexes exist on learning_resources."""
    conn = get_connection()
    cursor = conn.cursor()

    # Check migration record
    cursor.execute("SELECT applied_at FROM schema_migrations WHERE version = '2026-10-24-phase2-learning-resources-metadata'")
    row = cursor.fetchone()
    assert row is not None, "Phase 2 migration must be recorded in schema_migrations"

    # Check columns
    cols = {r["name"]: r["type"] for r in cursor.execute("PRAGMA table_info(learning_resources)").fetchall()}
    expected_cols = [
        "id", "title", "category", "sub_category", "canonical_url", "primary_url",
        "all_urls", "source", "source_message_uid", "raw_excerpt", "summary", "tags",
        "saved_at", "notes", "skill_tag", "difficulty_level", "resource_type",
        "estimated_minutes", "created_at", "is_completed", "completed_at"
    ]
    for col in expected_cols:
        assert col in cols, f"Expected column '{col}' missing from learning_resources"

    # Check performance indexes
    indexes = {r["name"] for r in cursor.execute("PRAGMA index_list(learning_resources)").fetchall()}
    assert "idx_learning_skill" in indexes or any("skill" in idx for idx in indexes)
    assert "idx_learning_difficulty" in indexes or any("difficulty" in idx for idx in indexes)
    assert "idx_learning_completed" in indexes or any("completed" in idx for idx in indexes)
    conn.close()


# ----------------- 2. Curated Catalog & Seeder Tests -----------------

def test_curated_catalog_completeness():
    """Verify curated catalog contains at least 25 high-quality resources with verified metadata."""
    assert len(CURATED_LEARNING_RESOURCES) >= 25

    categories = set()
    skills = set()
    difficulties = set()

    for r in CURATED_LEARNING_RESOURCES:
        assert r["title"], "Resource title cannot be empty"
        assert r["canonical_url"].startswith("http"), "Canonical URL must be a valid HTTP(S) URL"
        assert r["primary_url"].startswith("http"), "Primary URL must be a valid HTTP(S) URL"
        assert r["estimated_minutes"] > 0, "Estimated minutes must be positive"
        assert r["difficulty_level"] in ("BEGINNER", "INTERMEDIATE", "ADVANCED")
        assert r["resource_type"] in (
            "DOCUMENTATION", "INTERACTIVE_TUTORIAL", "CHEAT_SHEET",
            "EXERCISE_SET", "ROADMAP", "VIDEO_COURSE"
        )
        assert len(r.get("tags", [])) > 0, "Resource must have tags"
        assert r.get("notes"), "Resource must include actionable preparation guidance"

        categories.add(r["category"])
        skills.add(r["skill_tag"])
        difficulties.add(r["difficulty_level"])

    # Verify coverage across essential core areas
    assert "python" in skills
    assert "sql" in skills
    assert "power_bi" in skills
    assert "data_engineering" in skills
    assert len(difficulties) == 3, "Catalog must cover BEGINNER, INTERMEDIATE, and ADVANCED"


def test_seeder_idempotency_and_preservation():
    """Verify seeder runs idempotently and preserves candidate completion state and personal notes."""
    # First seed
    seed_res1 = seed_curated_learning_resources()
    assert seed_res1["status"] == "SUCCESS"
    assert seed_res1["total_curated"] >= 25

    # Find one curated resource to modify
    items = list_learning_resources(limit=5)
    assert len(items) > 0
    target_id = items[0]["id"]

    # Candidate marks as complete and adds personal notes
    toggled = toggle_learning_resource_completion(target_id, completed=True)
    assert toggled is not None
    assert toggled["is_completed"] is True
    assert toggled["completed_at"] is not None

    conn = get_connection()
    conn.cursor().execute("UPDATE learning_resources SET notes = 'Candidate custom note' WHERE id = ?", (target_id,))
    conn.commit()
    conn.close()

    # Re-run seeder
    seed_res2 = seed_curated_learning_resources()
    assert seed_res2["status"] == "SUCCESS"
    assert seed_res2["inserted"] == 0, "Second seed should not insert duplicate resources"

    # Verify candidate completion state and custom notes were preserved
    preserved = get_learning_resource(target_id)
    assert preserved is not None
    assert preserved["is_completed"] is True, "User completion status must not be erased on re-seed"
    assert preserved["notes"] == "Candidate custom note", "User personal notes must not be overwritten"


# ----------------- 3. Filtering & Querying Tests -----------------

def test_list_learning_resources_filters():
    """Verify filtering by category, skill_tag, difficulty_level, is_completed, and search query."""
    # Filter by skill
    python_items = list_learning_resources(skill_tag="python")
    assert len(python_items) >= 2
    for r in python_items:
        assert r["skill_tag"] == "python"

    # Filter by difficulty
    beg_items = list_learning_resources(difficulty_level="BEGINNER")
    assert len(beg_items) >= 2
    for r in beg_items:
        assert r["difficulty_level"] == "BEGINNER"

    # Filter by completion status
    pending_items = list_learning_resources(is_completed=False)
    assert len(pending_items) >= 1
    for r in pending_items:
        assert r["is_completed"] is False

    # Search query
    sql_search = list_learning_resources(query="Window")
    assert len(sql_search) >= 1
    assert any("window" in r["title"].lower() or "window" in r["summary"].lower() for r in sql_search)


def test_completion_toggle():
    """Verify toggling and explicit setting of completion status."""
    res_id = save_learning_resource({
        "title": "Temporary Test Resource for Toggle",
        "category": "Technical Learning Materials",
        "primary_url": "https://example.com/test-toggle",
        "canonical_url": "https://example.com/test-toggle",
        "skill_tag": "python",
        "difficulty_level": "BEGINNER"
    })
    assert res_id > 0

    try:
        # Default is not completed
        item = get_learning_resource(res_id)
        assert item["is_completed"] is False
        assert item["completed_at"] is None

        # Toggle to completed
        toggled_on = toggle_learning_resource_completion(res_id)
        assert toggled_on["is_completed"] is True
        assert toggled_on["completed_at"] is not None

        # Toggle back to pending
        toggled_off = toggle_learning_resource_completion(res_id)
        assert toggled_off["is_completed"] is False
        assert toggled_off["completed_at"] is None

        # Explicit set True
        explicit_on = toggle_learning_resource_completion(res_id, completed=True)
        assert explicit_on["is_completed"] is True

        # Explicit set True again (idempotent)
        explicit_on2 = toggle_learning_resource_completion(res_id, completed=True)
        assert explicit_on2["is_completed"] is True
    finally:
        delete_learning_resource(res_id)


def test_learning_resources_stats():
    """Verify stats calculation including difficulty, skill, completion counts, and hours."""
    stats = get_learning_resources_stats()
    assert stats["total"] >= 25
    assert "completed" in stats
    assert "pending" in stats
    assert stats["total"] == stats["completed"] + stats["pending"]
    assert stats["total_estimated_hours"] > 0
    assert "by_category" in stats
    assert "by_difficulty" in stats
    assert "by_skill" in stats
    assert "python" in stats["by_skill"]
    assert "sql" in stats["by_skill"]


# ----------------- 4. Structured Pathways Tests -----------------

def test_structured_pathways_calculation():
    """Verify pathway calculation, stages, and dynamic completion tracking."""
    resources = list_learning_resources(limit=200)
    pathways = get_learning_pathways(resources)

    assert len(pathways) == 4
    pw_ids = {p["id"] for p in pathways}
    assert pw_ids == {
        "python-data-analysis",
        "sql-query-mastery",
        "power-bi-business-intelligence",
        "cloud-data-engineering"
    }

    for pw in pathways:
        assert pw["total_stages"] >= 3
        assert pw["total_resources"] >= 2
        assert pw["total_minutes"] > 0
        assert pw["total_hours"] > 0
        assert 0.0 <= pw["progress_pct"] <= 100.0
        assert isinstance(pw["is_completed"], bool)

        for st in pw["stages"]:
            assert st["stage_number"] >= 1
            assert st["title"]
            assert st["difficulty_level"] in ("BEGINNER", "INTERMEDIATE", "ADVANCED")
            assert len(st["resources"]) == st["total_resources"]


# ----------------- 5. REST API Integration Tests -----------------

@pytest.mark.anyio
async def test_api_resources_get_with_filters():
    """Verify GET /api/resources supports all query filters."""
    status, _, body = await asgi_call(app, method="GET", path="/api/resources", query="skill_tag=python&difficulty_level=BEGINNER")
    assert status == 200
    data = json.loads(body.decode("utf-8"))
    assert "items" in data
    assert "resources" in data
    assert "stats" in data
    assert data["count"] >= 1
    for item in data["items"]:
        assert item["skill_tag"] == "python"
        assert item["difficulty_level"] == "BEGINNER"


@pytest.mark.anyio
async def test_api_resources_pathways_endpoint():
    """Verify GET /api/resources/pathways returns structured curriculum with progress metrics."""
    status, _, body = await asgi_call(app, method="GET", path="/api/resources/pathways")
    assert status == 200
    data = json.loads(body.decode("utf-8"))
    assert data["status"] == "SUCCESS"
    assert data["count"] == 4
    assert len(data["pathways"]) == 4

    p_ids = [p["id"] for p in data["pathways"]]
    assert "python-data-analysis" in p_ids
    assert "sql-query-mastery" in p_ids


@pytest.mark.anyio
async def test_api_resources_single_and_toggle_endpoint():
    """Verify GET /api/resources/{id} and POST /api/resources/{id}/toggle-complete."""
    # List to get an existing item ID
    status, _, body = await asgi_call(app, method="GET", path="/api/resources", query="limit=1")
    assert status == 200
    items = json.loads(body.decode("utf-8"))["items"]
    assert len(items) > 0
    res_id = items[0]["id"]

    # GET single
    status, _, body = await asgi_call(app, method="GET", path=f"/api/resources/{res_id}")
    assert status == 200
    item = json.loads(body.decode("utf-8"))
    assert item["id"] == res_id

    # Toggle complete
    status, _, body = await asgi_call(app, method="POST", path=f"/api/resources/{res_id}/toggle-complete")
    assert status == 200
    res_toggle = json.loads(body.decode("utf-8"))
    assert res_toggle["status"] == "SUCCESS"
    new_state = res_toggle["resource"]["is_completed"]

    # Toggle back to restore original state
    status, _, body = await asgi_call(app, method="POST", path=f"/api/resources/{res_id}/toggle-complete")
    assert status == 200
    res_toggle2 = json.loads(body.decode("utf-8"))
    assert res_toggle2["resource"]["is_completed"] != new_state

    # 404 test
    status, _, _ = await asgi_call(app, method="GET", path="/api/resources/9999999")
    assert status == 404

    status, _, _ = await asgi_call(app, method="POST", path="/api/resources/9999999/toggle-complete")
    assert status == 404
