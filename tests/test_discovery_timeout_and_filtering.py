"""Tests for asynchronous discovery execution, timeout repair, and robust city filtering."""
import json
import time
from unittest.mock import patch
import pytest

from careerorbit.web.app import app
from careerorbit.discovery.manager import DiscoveryManager
from careerorbit.matcher.geo import get_city_synonyms
from careerorbit.database.db import init_db, save_job, list_jobs
from careerorbit.models.schemas import Job, VerificationStatus


async def asgi_request(app, method="GET", path="/", query="", headers=None):
    from tests.authenticated_request import authenticated_headers
    headers = authenticated_headers(method, headers)
    """Simple in-process ASGI test helper without external dependencies."""
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
            return {"type": "http.request", "body": b"", "more_body": False}
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


def test_city_synonyms_resolution():
    blr = get_city_synonyms("Bengaluru")
    assert "bangalore" in blr
    assert "bengaluru" in blr

    bgl = get_city_synonyms("Bangalore")
    assert "bengaluru" in bgl

    chn = get_city_synonyms("Chennai")
    assert "madras" in chn

    hyd = get_city_synonyms("Hyderabad")
    assert "secunderabad" in hyd

    dlh = get_city_synonyms("Delhi")
    assert "noida" in dlh
    assert "gurugram" in dlh

    unknown = get_city_synonyms("NonExistentCity")
    assert unknown == ["nonexistentcity"]


def test_city_filter_matches_both_canonical_and_aliases():
    # Insert job 1: city='Bengaluru', location='Bengaluru, Karnataka'
    j1 = Job(
        job_uid="test_blr_canonical_1",
        employer="Groww",
        title="Associate Data Analyst",
        normalized_title="associate data analyst",
        priority_category=1,
        priority_label="Data Analyst",
        location="Bengaluru, Karnataka",
        city="Bengaluru",
        state="Karnataka",
        country="India",
        work_arrangement="Hybrid",
        official_url="https://groww.in/careers/1",
        canonical_url="https://groww.in/careers/1",
        discovery_source="Employer Direct",
        verification_status=VerificationStatus.UNVERIFIED,
        record_state="DISCOVERY_LEAD"
    )
    save_job(j1)

    # Insert job 2: city='Bengaluru', location='Bangalore, India'
    j2 = Job(
        job_uid="test_blr_alias_2",
        employer="InMobi",
        title="Junior Software Engineer",
        normalized_title="junior software engineer",
        priority_category=3,
        priority_label="Software Engineer",
        location="Bangalore, India",
        city="Bengaluru",
        state="Karnataka",
        country="India",
        work_arrangement="On-site",
        official_url="https://inmobi.com/careers/2",
        canonical_url="https://inmobi.com/careers/2",
        discovery_source="Employer Direct",
        verification_status=VerificationStatus.UNVERIFIED,
        record_state="DISCOVERY_LEAD"
    )
    save_job(j2)

    # Query using 'Bengaluru'
    results_blr = list_jobs(city="Bengaluru")
    uids_blr = [j["job_uid"] for j in results_blr]
    assert "test_blr_canonical_1" in uids_blr
    assert "test_blr_alias_2" in uids_blr

    # Query using 'Bangalore'
    results_bgl = list_jobs(city="Bangalore")
    uids_bgl = [j["job_uid"] for j in results_bgl]
    assert "test_blr_canonical_1" in uids_bgl
    assert "test_blr_alias_2" in uids_bgl

    # Query for Chennai should NOT match these jobs
    results_chn = list_jobs(city="Chennai")
    uids_chn = [j["job_uid"] for j in results_chn]
    assert "test_blr_canonical_1" not in uids_chn
    assert "test_blr_alias_2" not in uids_chn


@pytest.mark.anyio
async def test_api_jobs_city_filtering():
    status_code, _, body = await asgi_request(app, method="GET", path="/api/jobs", query="city=Bengaluru")
    assert status_code == 200
    data = json.loads(body.decode("utf-8"))
    assert "jobs" in data
    for j in data["jobs"]:
        city_loc = f"{j.get('city', '')} {j.get('location', '')}".lower()
        assert "bengaluru" in city_loc or "bangalore" in city_loc or "blr" in city_loc


@pytest.mark.anyio
async def test_discovery_trigger_returns_promptly_202():
    with patch.object(DiscoveryManager, "_run_worker"):
        start_time = time.time()
        status_code, _, body = await asgi_request(app, method="POST", path="/api/discovery/trigger")
        elapsed = time.time() - start_time

        assert elapsed < 1.0, f"Trigger took {elapsed}s; must respond promptly"
        assert status_code in (200, 202)
        data = json.loads(body.decode("utf-8"))
        assert "status" in data
        assert data["status"] in ("accepted", "already_running")
        assert "run_id" in data
        run_id = data["run_id"]
        assert run_id is not None

        # Status endpoint check
        st_code, _, st_body = await asgi_request(app, method="GET", path=f"/api/discovery/status/{run_id}")
        assert st_code == 200
        st_data = json.loads(st_body.decode("utf-8"))
        assert st_data["run_id"] == run_id
        assert st_data["status"] in ("running", "success", "partial_success", "failed", "idle")


def test_discovery_manager_prevents_duplicate_concurrent_runs():
    dm = DiscoveryManager()
    with patch.object(dm, "is_running", return_value=True):
        dm._current_run = {"run_id": "disc_mock_active", "started_at": "2026-10-22T10:00:00Z"}
        res = dm.start_discovery()
        assert res["status"] == "already_running"
        assert res["run_id"] == "disc_mock_active"


def test_source_isolation_one_failing_source_does_not_abort_run():
    from careerorbit.discovery.engine import JobDiscoveryEngine
    from careerorbit.discovery.sources import BaseJobSource

    class BrokenSource(BaseJobSource):
        name = "Broken Mock Source"
        def fetch_jobs(self, days_back=7):
            raise ConnectionError("Simulated network outage")

    class HealthySource(BaseJobSource):
        name = "Healthy Mock Source"
        def fetch_jobs(self, days_back=7):
            return [{
                "employer": "TechCorp",
                "title": "Data Analyst",
                "job_id_or_req": "TC-900",
                "priority_category": 1,
                "priority_label": "Data Analyst",
                "location": "Bengaluru, Karnataka",
                "work_arrangement": "Remote",
                "employment_type": "Full-time",
                "official_url": "https://techcorp.com/jobs/900",
                "canonical_url": "https://techcorp.com/jobs/900",
                "discovery_source": "Healthy Mock Source",
                "description": "SQL and Python data analyst opening in Bengaluru"
            }]

    engine = JobDiscoveryEngine()
    engine.sources = [BrokenSource(), HealthySource()]

    stages = []
    def on_progress(stage, sources):
        stages.append(stage)

    res = engine.run_discovery(initial_days=1, min_acceptable=1, progress_callback=on_progress)
    assert res["total_collected"] >= 1
    assert res["partial_failure"] is True
    assert res["sources"]["Broken Mock Source"]["status"] == "failed"
    assert res["sources"]["Healthy Mock Source"]["status"] == "ok"
    assert len(stages) > 0
