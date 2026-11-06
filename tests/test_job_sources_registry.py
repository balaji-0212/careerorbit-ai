"""Tests for database-backed Job Sources registry."""
import pytest
from careerorbit.database.db import (
    init_db, list_job_sources, get_job_source, save_job_source,
    update_job_source_health, delete_job_source, toggle_job_source_enabled
)
from careerorbit.web.app import (
    get_all_job_sources, get_single_job_source_endpoint,
    create_job_source_endpoint, edit_job_source_endpoint,
    remove_job_source_endpoint, toggle_job_source_endpoint,
    get_sources_health
)

@pytest.fixture(autouse=True)
def setup_db():
    init_db()

def test_list_and_get_job_sources():
    sources = list_job_sources()
    assert len(sources) >= 5
    source_ids = [s["source_id"] for s in sources]
    assert "unstop-public-api" in source_ids

    src = get_job_source("unstop-public-api")
    assert src is not None
    assert src["source_name"] == "Unstop Public API"
    assert src["category"] == "PUBLIC_AGGREGATOR"

def test_job_source_crud_operations():
    test_id = "pytest-custom-board"
    # Create
    save_job_source({
        "source_id": test_id,
        "source_name": "Pytest Test Board",
        "category": "EMPLOYER_ATS",
        "source_type": "GREENHOUSE",
        "endpoint_or_board_id": "pytest_board",
        "is_configured": True,
        "is_enabled": True,
        "health_status": "UNKNOWN"
    })

    src = get_job_source(test_id)
    assert src is not None
    assert src["source_name"] == "Pytest Test Board"

    # Update health
    update_job_source_health(
        source_id=test_id,
        health_status="HEALTHY",
        discovered_count=12,
        updated_count=3,
        rejected_count=2,
        success=True
    )
    updated = get_job_source(test_id)
    assert updated["health_status"] == "HEALTHY"
    assert updated["last_discovered_count"] == 12
    assert updated["last_rejected_count"] == 2

    # Toggle enabled
    new_state = toggle_job_source_enabled(test_id, enabled=False)
    assert new_state is False
    assert get_job_source(test_id)["is_enabled"] == 0

    # Delete
    deleted = delete_job_source(test_id)
    assert deleted is True
    assert get_job_source(test_id) is None

def test_job_sources_api_endpoints():
    data = get_all_job_sources()
    assert data["count"] >= 5
    assert len(data["sources"]) == data["count"]

    health_data = get_sources_health()
    assert "total_sources" in health_data
    assert "sources" in health_data
    assert health_data["total_sources"] >= 5
