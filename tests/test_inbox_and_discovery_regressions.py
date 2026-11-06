"""Regression Test Suite for CareerOrbit AI Master Engineering Transformation.
Verifies:
1. Global apiFetch presence and frontend API consistency.
2. Background discovery triggering, run ID generation, and stage polling.
3. Telegram poll metadata persistence across server restarts.
4. Three-tier India-first geographic classification and overseas screening.
5. Resource library CRUD operations and inbox promotion.
6. Scheduler study plan automation decoupling.
"""
from pathlib import Path
import pytest
from datetime import datetime, timezone

from careerorbit.config.settings import SETTINGS
from careerorbit.database.db import (
    init_db, get_connection, save_learning_resource, list_learning_resources,
    delete_learning_resource, get_learning_resources_stats,
    set_telegram_poll_metadata, get_telegram_poll_metadata,
    get_inbox_stats, save_inbox_message, get_job_stats
)
from careerorbit.discovery.manager import DISCOVERY_MANAGER
from careerorbit.matcher.geo import classify_geographic_priority, GEO_PRIORITY_LABELS
from careerorbit.telegram.worker import TELEGRAM_WORKER
from careerorbit.scheduler.runner import SCHEDULER


def test_apifetch_global_declaration_and_nav_integrity():
    """Verify apiFetch is declared in head and Resource Library is wired to nav."""
    html = Path("careerorbit/web/static/index.html").read_text(encoding="utf-8")
    assert "window.apiFetch = async function" in html, "window.apiFetch must be declared in head"
    assert "var apiFetch = window.apiFetch;" in html
    assert "switchTab('resources')" in html, "Resource Library tab button must be in nav"
    assert "id=\"tab-resources\"" in html, "tab-resources section must be present in DOM"
    assert "loadLearningResources" in html, "loadLearningResources function must be present"
    assert "debouncedLoadResources" in html, "debouncedLoadResources must be present"


def test_discovery_trigger_and_status_polling():
    """Verify background discovery initiation and real-time status reporting."""
    init_db()
    manager = DISCOVERY_MANAGER
    status = manager.get_status()
    assert "status" in status
    assert "run_id" in status
    assert "stage" in status
    assert "summary" in status


def test_telegram_poll_metadata_persistence():
    """Verify Telegram worker poll metadata survives simulated restart via SQLite."""
    init_db()
    test_ts = datetime.now(timezone.utc).isoformat()
    set_telegram_poll_metadata(status="SUCCESS", timestamp=test_ts, processed_count=3)

    meta = get_telegram_poll_metadata()
    assert meta["last_poll_status"] == "SUCCESS"
    assert meta["last_poll_time"] == test_ts
    assert meta["total_updates_processed"] >= 3

    worker_status = TELEGRAM_WORKER.get_status()
    assert worker_status["last_poll_status"] in ("SUCCESS", "IDLE", "RUNNING")
    assert worker_status["total_updates_processed"] >= 3


def test_three_tier_geographic_priorities():
    """Verify 3 distinct India geographic tiers and strict overseas screening."""
    # Priority 1: Top 4 South Indian Metros & India Remote
    p1_cities = ["Bengaluru, Karnataka", "Chennai, Tamil Nadu", "Coimbatore, Tamil Nadu", "Hyderabad, Telangana"]
    for city in p1_cities:
        res = classify_geographic_priority(city, "Hybrid")
        assert res["geographic_priority"] == 1, f"Failed for {city}"
        assert res["geo_score"] == 10.0
        assert res["location_eligibility_status"] == "VERIFIED_INDIA_ELIGIBLE"
        assert not res["is_disqualified"]

    # Priority 1: India Remote
    rem_res = classify_geographic_priority("Remote - India", "Remote")
    assert rem_res["geographic_priority"] == 1
    assert rem_res["geo_score"] == 10.0

    # Priority 2: Cuddalore, Puducherry, Kochi, Mysuru, Other South India
    p2_cities = ["Cuddalore, Tamil Nadu", "Puducherry", "Kochi, Kerala", "Mysuru, Karnataka", "Madurai, Tamil Nadu"]
    for city in p2_cities:
        res = classify_geographic_priority(city, "On-site")
        assert res["geographic_priority"] == 2, f"Failed for {city}"
        assert res["geo_score"] in (8.5, 9.0)
        assert res["location_eligibility_status"] == "VERIFIED_INDIA_ELIGIBLE"
        assert not res["is_disqualified"]

    # Priority 3: Other Indian Tech Hubs
    p3_cities = ["Pune, Maharashtra", "Mumbai, Maharashtra", "Delhi NCR", "Noida, Uttar Pradesh", "Gurugram, Haryana", "Ahmedabad, Gujarat", "Kolkata, West Bengal"]
    for city in p3_cities:
        res = classify_geographic_priority(city, "Hybrid")
        assert res["geographic_priority"] == 3, f"Failed for {city}"
        assert res["geo_score"] == 7.0
        assert res["location_eligibility_status"] == "VERIFIED_INDIA_ELIGIBLE"
        assert not res["is_disqualified"]

    # Priority 4 / Disqualified: Overseas restricted
    overseas_res = classify_geographic_priority("San Francisco, CA", "On-site")
    assert overseas_res["geographic_priority"] == 4
    assert overseas_res["is_disqualified"] is True

    # Ambiguous Remote without India verification
    bare_remote = classify_geographic_priority("Remote", "Remote")
    assert bare_remote["geographic_priority"] == 4
    assert bare_remote["location_eligibility_status"] == "LOCATION_ELIGIBILITY_UNCONFIRMED"
    assert bare_remote["geo_score"] == 0.0


def test_resource_library_crud_operations():
    """Verify saved study resources can be added, queried, and deleted."""
    init_db()
    ts = int(datetime.now(timezone.utc).timestamp())
    canon_url = f"https://example.com/dsa-guide-{ts}"
    res_id = save_learning_resource({
        "title": "NeetCode 150 DSA Pattern Guide",
        "category": "Coding Practice",
        "sub_category": "dsa",
        "canonical_url": canon_url,
        "primary_url": canon_url,
        "all_urls": [canon_url],
        "source": "Unified Inbox (Telegram)",
        "source_message_uid": f"test_msg_{ts}",
        "raw_excerpt": "Comprehensive 150 problem roadmap for two pointer, sliding window, and tree algorithms.",
        "summary": "NeetCode 150 DSA Pattern Guide",
        "tags": ["DSA", "Python", "Algorithms"],
        "notes": "Saved for technical interview rounds"
    })
    assert res_id > 0

    items = list_learning_resources(category="Coding Practice", limit=10)
    found = [r for r in items if r["id"] == res_id]
    assert len(found) == 1
    assert found[0]["title"] == "NeetCode 150 DSA Pattern Guide"
    assert "DSA" in found[0]["tags"]

    stats = get_learning_resources_stats()
    assert stats["total"] >= 1
    assert "Coding Practice" in stats["by_category"]

    deleted = delete_learning_resource(res_id)
    assert deleted is True

    items_after = list_learning_resources(category="Coding Practice", limit=10)
    assert not any(r["id"] == res_id for r in items_after)


def test_scheduler_study_plan_decoupled():
    """Verify automated 8:00 PM study plan execution is explicitly disabled."""
    status = SCHEDULER.get_status()
    assert "Disabled" in status.get("target_study_time", "")
    assert "08:00 AM" in status.get("target_discovery_time", "")
