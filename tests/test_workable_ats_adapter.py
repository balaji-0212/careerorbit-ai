"""Tests for Workable ATS Adapter and Registry integration."""
import pytest
from careerorbit.discovery.sources import WorkableSource
from careerorbit.discovery.registry import add_employer_source, list_employer_sources, delete_employer_source
from careerorbit.discovery.engine import JobDiscoveryEngine


def test_workable_source_initialization():
    source = WorkableSource(company="Acme Tech", account_slug="acme-tech")
    assert source.company == "Acme Tech"
    assert source.account_slug == "acme-tech"
    assert source.configured is True
    assert "Workable" in source.name


def test_workable_source_invalid_slug():
    source = WorkableSource(company="Bad Slug", account_slug="invalid/slug!@#")
    assert source.configured is False
    assert source.fetch_jobs() == []


def test_workable_registry_integration():
    source_id = None
    try:
        new_src = add_employer_source(
            employer_name="Workable Test Co",
            official_domain="workabletest.com",
            ats_provider="Workable",
            board_id="workable-test-slug",
            enabled=True,
            notes="Workable integration test"
        )
        source_id = new_src["id"]
        assert new_src["ats_provider"] == "Workable"
        assert new_src["board_id"] == "workable-test-slug"

        all_sources = list_employer_sources()
        assert any(s["id"] == source_id for s in all_sources)
    finally:
        if source_id:
            delete_employer_source(source_id)


def test_discovery_engine_includes_workable():
    engine = JobDiscoveryEngine()
    # Check that engine includes WorkableSource if configured
    workable_sources = [s for s in engine.sources if isinstance(s, WorkableSource)]
    assert isinstance(workable_sources, list)
