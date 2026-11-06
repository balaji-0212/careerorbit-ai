"""Deterministic adapter tests use fixtures and never claim mock vacancies are real."""
from datetime import datetime, timedelta, timezone

import pytest

from careerorbit.discovery.sources import (
    EmployerDirectVerifiedSource, GreenhouseBoardSource, JobicySource, RemotiveSource,
    LeverSiteSource, ArbeitnowSource, classify_title_to_priority,
    screen_job_for_candidate,
)
from careerorbit.discovery.engine import JobDiscoveryEngine
from careerorbit.database.db import get_job_by_uid, init_db


def test_employer_source_does_not_synthesize_vacancies():
    assert EmployerDirectVerifiedSource().fetch_jobs() == []


def test_public_source_clients_use_timeouts_retries_and_retry_after_for_rate_limits():
    source = JobicySource()
    adapter = source.session.get_adapter("https://")
    retry = adapter.max_retries
    assert retry.total == 2
    assert retry.backoff_factor > 0
    assert retry.respect_retry_after_header is True
    assert 429 in retry.status_forcelist


def test_priority_mapping_covers_six_requested_categories():
    assert classify_title_to_priority("Junior Data Analyst") == 1
    assert classify_title_to_priority("Graduate Data Scientist") == 2
    assert classify_title_to_priority("Associate Software Engineer") == 3
    assert classify_title_to_priority("Computer Vision Engineer") == 4
    assert classify_title_to_priority("Junior Data Engineer") == 5
    assert classify_title_to_priority("Python Automation Developer") == 6


def test_overseas_location_is_not_accepted_as_india_remote():
    assert screen_job_for_candidate({"title": "Software Engineer (.NET)", "work_arrangement": "Remote", "location": "Portugal"}) == "remote_eligibility_not_india"

def test_candidate_screen_removes_unrelated_senior_and_non_india_remote_roles():
    from careerorbit.discovery.sources import screen_job_for_candidate
    assert screen_job_for_candidate({"title": "Enterprise Account Executive"}) == "title_not_in_career_priorities"
    assert screen_job_for_candidate({"title": "Senior Data Analyst"}) == "seniority_out_of_scope"
    assert screen_job_for_candidate({"title": "Junior Python Developer", "work_arrangement": "Remote", "location": "Canada only"}) == "location_restricted_outside_india"
    assert screen_job_for_candidate({"title": "Junior Data Analyst", "location": "Chennai, India"}) is None


class FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_common_normalizer_keeps_unknown_dates_and_rejects_invalid_urls():
    source = JobicySource()
    normalized = source.normalize({"title": "Junior Analyst", "company": "Acme", "url": "https://jobicy.com/jobs/1"}, 1)
    assert normalized["posting_date"] is None
    assert normalized["posting_date_confidence"] == "UNKNOWN"
    assert normalized["official_url"] == ""
    assert normalized["discovery_url"].startswith("https://jobicy.com/")
    assert source.normalize({"title": "Missing", "company": "Acme", "url": "javascript:alert(1)"}, 1) is None


def test_aggregator_listing_is_not_misrepresented_as_employer_or_apply_url():
    source_url = "https://remotive.com/remote-jobs/software-dev/fixture-role-123"
    normalized = RemotiveSource().normalize({
        "id": "fixture-role-123", "title": "Associate Software Engineer",
        "company": "Fixture Employer", "url": source_url,
        "location": "Worldwide", "work_arrangement": "Remote",
    }, 30)
    assert normalized is not None
    assert normalized["discovery_url"] == source_url
    assert normalized["canonical_url"] == source_url
    assert normalized["official_url"] == ""
    assert normalized["official_listing_url"] == ""
    assert normalized["application_url"] == ""


def test_greenhouse_adapter_parses_public_board_and_marks_date_unknown(monkeypatch):
    source = GreenhouseBoardSource("Acme", "acme")
    calls = []
    def fake_get(url, **kwargs):
        calls.append(url)
        if url.endswith("/jobs"):
            return FakeResponse({"jobs": [{"id": 42, "internal_job_id": 9001, "title": "Junior Data Analyst",
                "location": {"name": "Chennai, India"}, "absolute_url": "https://boards.greenhouse.io/acme/jobs/42",
                "content": "<p>SQL and Power BI</p>"}]})
        return FakeResponse({"name": "Acme"})
    monkeypatch.setattr(source.session, "get", fake_get)
    jobs = source.fetch_jobs()
    assert len(jobs) == 1
    assert jobs[0]["employer"] == "Acme"
    assert jobs[0]["job_id_or_req"] == "9001"
    assert jobs[0]["posting_date"] is None
    assert jobs[0]["posting_date_confidence"] == "UNKNOWN"
    assert jobs[0]["source_is_official_api"] is True
    assert jobs[0]["official_url"] == ""
    assert jobs[0]["official_listing_url"] == "https://boards.greenhouse.io/acme/jobs/42"
    assert jobs[0]["application_url"] == ""
    assert "SQL and Power BI" in jobs[0]["description"]
    assert len(calls) == 2


def test_greenhouse_adapter_parses_published_date_when_present(monkeypatch):
    source = GreenhouseBoardSource("Acme", "acme")
    pub_iso = datetime.now(timezone.utc).isoformat()
    def fake_get(url, **kwargs):
        if url.endswith("/jobs"):
            return FakeResponse({"jobs": [{
                "id": 100, "internal_job_id": 9002, "title": "Associate Software Engineer",
                "location": {"name": "Bengaluru, India"}, "absolute_url": "https://boards.greenhouse.io/acme/jobs/100",
                "content": "<p>Python and FastAPI</p>", "first_published": pub_iso, "requisition_id": "REQ-100"
            }]})
        return FakeResponse({"name": "Acme"})
    monkeypatch.setattr(source.session, "get", fake_get)
    jobs = source.fetch_jobs(days_back=7)
    assert len(jobs) == 1
    assert jobs[0]["posting_date_confidence"] == "API_REPORTED"
    assert jobs[0]["posting_date"] is not None
    assert jobs[0]["job_id_or_req"] == "REQ-100"



def test_greenhouse_rejects_company_label_mismatch(monkeypatch):
    source = GreenhouseBoardSource("Acme", "other-board")
    monkeypatch.setattr(source.session, "get", lambda *args, **kwargs: FakeResponse({"name": "Different Company"}))
    with pytest.raises(ValueError, match="does not match"):
        source.fetch_jobs()


def test_lever_adapter_paginates_and_preserves_api_timestamp(monkeypatch):
    source = LeverSiteSource("Acme", "acme")
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    page_one = [{"id": f"id-{i}", "text": "Associate Software Engineer", "createdAt": now_ms,
                 "hostedUrl": f"https://jobs.lever.co/acme/id-{i}",
                 "applyUrl": f"https://jobs.lever.co/acme/id-{i}/apply",
                 "categories": {"location": "Bengaluru, India", "commitment": "Full-time"},
                 "descriptionPlain": "Python and REST APIs"} for i in range(100)]
    page_two = [{"id": "id-last", "text": "Associate Software Engineer", "createdAt": now_ms,
                 "hostedUrl": "https://jobs.lever.co/acme/id-last",
                 "categories": {"location": "Remote - India"}, "descriptionPlain": "Python"}]
    calls = []
    def fake_get(url, **kwargs):
        calls.append(kwargs["params"]["skip"])
        return FakeResponse(page_one if kwargs["params"]["skip"] == 0 else page_two)
    monkeypatch.setattr(source.session, "get", fake_get)
    jobs = source.fetch_jobs(days_back=1)
    assert len(jobs) == 101
    assert calls == [0, 100]
    assert jobs[0]["posting_date_confidence"] == "API_REPORTED"
    assert jobs[0]["official_url"].endswith("/apply")


def test_common_normalizer_filters_old_publication_dates():
    source = JobicySource()
    old = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    assert source.normalize({"title": "Junior Analyst", "company": "Acme", "url": "https://jobicy.com/1", "published": old}, 1) is None


def test_source_failure_is_reported_without_losing_successful_records():
    init_db()
    class GoodSource:
        name = "Fixture public feed"
        configured = True
        def fetch_jobs(self, days_back=7):
            return [{"employer": "Fixture Employer", "title": "Junior Data Analyst", "job_id_or_req": "fixture-4242",
                     "priority_category": 1, "location": "Chennai, India", "work_arrangement": "Hybrid",
                     "posting_date": None, "posting_date_confidence": "UNKNOWN", "official_url": "",
                     "discovery_url": "https://jobs.example.org/fixture-4242", "discovery_source": self.name,
                     "description": "SQL, Power BI, Python"}]
    class FailingSource:
        name = "Fixture unavailable feed"
        configured = True
        def fetch_jobs(self, days_back=7):
            raise TimeoutError("fixture timeout")
    engine = JobDiscoveryEngine()
    engine.sources = [GoodSource(), FailingSource()]
    result = engine.run_discovery(initial_days=1, min_acceptable=1)
    assert result["partial_failure"] is True
    assert result["sources"]["Fixture public feed"]["status"] == "ok"
    assert result["sources"]["Fixture unavailable feed"]["status"] == "failed"
    saved = get_job_by_uid(result["processed_jobs"][0]["job_uid"])
    assert saved["discovery_url"] == "https://jobs.example.org/fixture-4242"
    assert saved["application_url"] == ""
    assert saved["verification_status"] == "PENDING_VERIFICATION"
    assert result["new_jobs_added"] == 1


def test_arbeitnow_adapter_extracts_and_converts_epoch_timestamp(monkeypatch):
    source = ArbeitnowSource()
    epoch_now = int(datetime.now(timezone.utc).timestamp())
    fake_payload = {
        "data": [
            {
                "slug": "arbeitnow-test-da-101",
                "company_name": "CloudTech Solutions",
                "title": "Junior Data Analyst",
                "description": "<p>Build dashboards using SQL and Power BI.</p>",
                "remote": True,
                "url": "https://www.arbeitnow.com/jobs/companies/cloudtech/junior-data-analyst",
                "location": "Worldwide",
                "created_at": epoch_now
            }
        ]
    }
    monkeypatch.setattr(source.session, "get", lambda *args, **kwargs: FakeResponse(fake_payload))
    jobs = source.fetch_jobs(days_back=7)
    assert len(jobs) == 1
    assert jobs[0]["employer"] == "CloudTech Solutions"
    assert jobs[0]["title"] == "Junior Data Analyst"
    assert jobs[0]["priority_category"] == 1
    assert jobs[0]["work_arrangement"] == "Remote"
    assert jobs[0]["posting_date_confidence"] == "API_REPORTED"
    assert jobs[0]["posting_date"] is not None
    assert "SQL and Power BI" in jobs[0]["description"]

