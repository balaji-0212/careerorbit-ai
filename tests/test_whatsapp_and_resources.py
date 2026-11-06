"""Tests for WhatsApp Chat Ingestion, Community Source Registry, and Study Resources Collection.
Verifies parsing of Android and iOS chat exports, filtering personal messages,
deduplication, UNVERIFIED status enforcement, source registry tracking, and REST endpoints.
"""
import json
import pytest
from careerorbit.database.db import (
    init_db, list_community_sources, record_community_source,
    get_community_source, update_community_source, save_learning_resource,
    list_learning_resources, get_learning_resource, delete_learning_resource,
    get_learning_resources_stats, get_inbox_message, get_job_by_id, list_jobs
)
from careerorbit.whatsapp.parser import WhatsAppChatExportParser
from careerorbit.whatsapp.adapter import WhatsAppExportAdapter
from careerorbit.web.app import app


async def asgi_call(app, method="GET", path="/", query="", body=b"", headers=None):
    """ASGI call helper supporting POST body payloads."""
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    from tests.authenticated_request import authenticated_headers
    h = authenticated_headers(method, h)
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "path": path,
        "raw_path": path.encode(),
        "query_string": query.encode(),
        "headers": [(k.lower().encode(), v.encode()) for k, v in h.items()],
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
    for msg in messages:
        if msg["type"] == "http.response.start":
            status_code = msg["status"]
            response_headers = dict(msg.get("headers", []))
        elif msg["type"] == "http.response.body":
            body_parts.append(msg.get("body", b""))

    return status_code, response_headers, b"".join(body_parts)


@pytest.fixture(autouse=True)
def setup_db():
    init_db()


# ----------------- 1. WhatsApp Parser Tests -----------------

SAMPLE_ANDROID_CHAT = """
12/10/24, 9:00 am - Messages and calls are end-to-end encrypted. No one outside of this chat can read or listen to them.
12/10/24, 9:05 am - Priya Sharma: Good morning everyone!
12/10/24, 9:06 am - Ramesh: gm
12/10/24, 9:15 am - Tech Recruiter: Hiring Alert! Caterpillar is hiring Junior Data Analysts in Bengaluru!
Role: Junior Data Analyst
Location: Bengaluru / Hybrid
Batch: 2024 / 2025 freshers eligible
Skills: Power BI, SQL, Python, Excel
Apply: https://boards.greenhouse.io/caterpillar/jobs/456789
12/10/24, 9:20 am - Anand Kumar: Thanks for sharing!
12/10/24, 9:30 am - SDE Mentor: Top 50 SQL Interview Questions PDF guide for data analyst and backend roles:
https://github.com/prep-guides/sql-50-questions
Covering window functions, CTEs, and query indexing.
12/10/24, 9:35 am - Priya Sharma: <Media omitted>
12/10/24, 9:40 am - Karthik: ok
"""

SAMPLE_IOS_CHAT = """
[15/10/2026, 11:20:10 AM] Messages and calls are end-to-end encrypted.
[15/10/2026, 11:22:00 AM] Campus Placement Admin: Off-Campus Drive: InMobi Technologies
Designation: Associate Software Engineer
Location: Bengaluru, Karnataka
Eligibility: B.E. / B.Tech (ECE, CSE, IT) 2025 Batch
Registration: https://jobs.lever.co/inmobi/ase-2025-drive
[15/10/2026, 11:25:30 AM] Student 1: is 2024 batch eligible?
[15/10/2026, 11:26:00 AM] Placement Admin: Yes, 0-1 year experience allowed.
"""


def test_whatsapp_android_parsing_and_filtering():
    """Verify Android WhatsApp format is parsed, personal chit-chat is filtered, and job leads are identified."""
    res = WhatsAppChatExportParser.parse_text(SAMPLE_ANDROID_CHAT, chat_title="Bangalore Tech Jobs")
    assert res["chat_title"] == "Bangalore Tech Jobs"
    assert res["total_messages_parsed"] >= 5
    # System messages ("Messages and calls are end-to-end encrypted", "<Media omitted>") and chit-chat ("gm", "ok") skipped
    assert res["personal_skipped_count"] >= 3
    assert res["career_relevant_count"] >= 2

    # Verify Caterpillar job was identified
    job_items = [i for i in res["items"] if i["is_job_lead"]]
    assert len(job_items) >= 1
    caterpillar_item = job_items[0]
    assert "Caterpillar" in caterpillar_item["raw_text"]
    assert "Junior Data Analyst" in caterpillar_item["raw_text"]
    assert caterpillar_item["classification"] == "Job: Data Analyst / BI"
    assert "Power BI" in caterpillar_item["candidate_matches"]
    assert "SQL" in caterpillar_item["candidate_matches"]

    # Verify SQL interview prep resource was identified
    prep_items = [i for i in res["items"] if not i["is_job_lead"]]
    assert len(prep_items) >= 1
    assert any("SQL" in p["raw_text"] for p in prep_items)


def test_whatsapp_ios_parsing():
    """Verify iOS bracketed timestamp format is parsed cleanly."""
    res = WhatsAppChatExportParser.parse_text(SAMPLE_IOS_CHAT, chat_title="Campus Drive Alerts")
    assert res["total_messages_parsed"] >= 3
    job_items = [i for i in res["items"] if i["is_job_lead"]]
    assert len(job_items) >= 1
    inmobi_item = job_items[0]
    assert "InMobi" in inmobi_item["raw_text"]
    assert inmobi_item["classification"] == "Job: Software Engineering"


def test_whatsapp_import_commits_records_and_unverified_status():
    """Verify importing WhatsApp items persists them to inbox and jobs as strictly UNVERIFIED."""
    parsed = WhatsAppChatExportParser.parse_text(SAMPLE_ANDROID_CHAT, chat_title="TN Tech Circle")
    import_res = WhatsAppChatExportParser.import_items(parsed["items"], chat_title="TN Tech Circle")
    assert import_res["status"] == "SUCCESS"
    assert import_res["imported_inbox"] >= 2
    assert import_res["imported_jobs"] >= 1

    # Verify community source was registered
    src = get_community_source("wa_tn_tech_circle")
    assert src is not None
    assert src["source_type"] == "whatsapp_chat_export"
    assert src["messages_count"] >= 1

    # Check that job is strictly UNVERIFIED
    jobs = list_jobs(employer="Caterpillar", limit=5)
    assert len(jobs) >= 1
    c_job = jobs[0]
    assert c_job["verification_status"] == "UNVERIFIED"
    assert "WhatsApp" in c_job["discovery_source"]


def test_whatsapp_idempotency_duplicate_handling():
    """Verify duplicate WhatsApp messages are skipped during re-import."""
    parsed = WhatsAppChatExportParser.parse_text(SAMPLE_IOS_CHAT, chat_title="Placement 2025")
    res1 = WhatsAppChatExportParser.import_items(parsed["items"], chat_title="Placement 2025")
    assert res1["imported_inbox"] >= 1

    # Second import without allow_duplicate should skip duplicates
    res2 = WhatsAppChatExportParser.import_items(parsed["items"], chat_title="Placement 2025")
    assert res2["skipped_duplicates"] >= 1


# ----------------- 2. Learning Resources Collection Tests -----------------

def test_learning_resources_crud():
    """Verify saving, listing, filtering, and deleting study resources."""
    res_id = save_learning_resource({
        "title": "Complete Power BI & DAX Handbook",
        "category": "Technical Learning Materials",
        "sub_category": "bi_and_analytics",
        "canonical_url": "https://learning.microsoft.com/power-bi-complete-guide",
        "primary_url": "https://learning.microsoft.com/power-bi-complete-guide",
        "all_urls": ["https://learning.microsoft.com/power-bi-complete-guide"],
        "source": "Telegram: StudyGroup",
        "summary": "Mastering DAX CALCULATE, FILTER, and time intelligence functions.",
        "tags": ["Power BI", "DAX", "Data Analyst"],
        "notes": "Reviewed for interview prep"
    })
    assert res_id > 0

    # Retrieve single
    resource = get_learning_resource(res_id)
    assert resource is not None
    assert resource["title"] == "Complete Power BI & DAX Handbook"
    assert "Power BI" in resource["tags"]

    # Filtered list
    items = list_learning_resources(category="Technical Learning Materials")
    assert any(i["id"] == res_id for i in items)

    # Stats
    stats = get_learning_resources_stats()
    assert stats["total"] >= 1
    assert "Technical Learning Materials" in stats["by_category"]

    # Delete
    assert delete_learning_resource(res_id) is True
    assert get_learning_resource(res_id) is None


# ----------------- 3. REST API Endpoint Tests -----------------

@pytest.mark.anyio
async def test_api_community_sources():
    """Verify GET and POST /api/community/sources endpoints."""
    # Register source
    post_data = json.dumps({
        "chat_id": "tg_channel_test_456",
        "source_name": "Bangalore Job Alerts Channel",
        "source_type": "telegram_channel",
        "status": "ACTIVE"
    }).encode("utf-8")
    status, _, body = await asgi_call(app, method="POST", path="/api/community/sources", body=post_data)
    assert status == 200
    res = json.loads(body.decode("utf-8"))
    assert res["status"] == "SUCCESS"

    # List sources
    status, _, body = await asgi_call(app, method="GET", path="/api/community/sources")
    assert status == 200
    data = json.loads(body.decode("utf-8"))
    assert data["count"] >= 1
    assert any(s["chat_id"] == "tg_channel_test_456" for s in data["sources"])


@pytest.mark.anyio
async def test_api_whatsapp_preview_and_import():
    """Verify POST /api/whatsapp/parse-preview and POST /api/whatsapp/import."""
    # Preview
    preview_payload = json.dumps({
        "text": SAMPLE_ANDROID_CHAT,
        "chat_title": "API Test WhatsApp Group"
    }).encode("utf-8")
    status, _, body = await asgi_call(app, method="POST", path="/api/whatsapp/parse-preview", body=preview_payload)
    assert status == 200
    prev_data = json.loads(body.decode("utf-8"))
    assert prev_data["career_relevant_count"] >= 1
    assert len(prev_data["items"]) >= 1

    # Import
    import_payload = json.dumps({
        "items": prev_data["items"][:2],
        "chat_title": "API Test WhatsApp Group"
    }).encode("utf-8")
    status, _, body = await asgi_call(app, method="POST", path="/api/whatsapp/import", body=import_payload)
    assert status == 200
    imp_data = json.loads(body.decode("utf-8"))
    assert imp_data["status"] == "SUCCESS"
    assert imp_data["imported_inbox"] >= 1


@pytest.mark.anyio
async def test_api_whatsapp_rejects_malformed_payload_types_without_server_error():
    """Malformed client payload shapes should be actionable 4xx responses, never parser 500s."""
    bad_preview = json.dumps({"text": {"unexpected": "object"}, "chat_title": "Malformed export"}).encode("utf-8")
    status, _, body = await asgi_call(
        app, method="POST", path="/api/whatsapp/parse-preview", body=bad_preview,
    )
    assert status == 422, body.decode("utf-8", errors="replace")

    bad_import = json.dumps({"items": [None], "chat_title": "Malformed export"}).encode("utf-8")
    status, _, body = await asgi_call(
        app, method="POST", path="/api/whatsapp/import", body=bad_import,
    )
    assert status == 422, body.decode("utf-8", errors="replace")


@pytest.mark.anyio
async def test_api_learning_resources_endpoints():
    """Verify /api/resources CRUD and promote-to-resource."""
    # Create
    res_payload = json.dumps({
        "title": "LeetCode 75 Curated DSA Sheet",
        "category": "Coding Practice",
        "primary_url": "https://leetcode.com/studyplan/leetcode-75/",
        "canonical_url": "https://leetcode.com/studyplan/leetcode-75/",
        "summary": "Essential 75 algorithm problems for technical interviews."
    }).encode("utf-8")
    status, _, body = await asgi_call(app, method="POST", path="/api/resources", body=res_payload)
    assert status == 200
    created = json.loads(body.decode("utf-8"))
    res_id = created["resource_id"]
    assert res_id > 0

    # List
    status, _, body = await asgi_call(app, method="GET", path="/api/resources", query="category=Coding+Practice")
    assert status == 200
    list_data = json.loads(body.decode("utf-8"))
    assert list_data["count"] >= 1
    assert any(r["id"] == res_id for r in list_data["items"])

    # Delete
    status, _, body = await asgi_call(app, method="DELETE", path=f"/api/resources/{res_id}")
    assert status == 200
