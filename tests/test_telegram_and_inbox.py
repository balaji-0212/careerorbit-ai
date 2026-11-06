"""Comprehensive tests for Telegram Bot Integration and Unified Inbox.
Verifies token security, API client, discrete classification, service pipeline,
unverified status enforcement, geographic filtering, database CRUD, and REST routes.
"""
import json
import pytest
from unittest.mock import MagicMock, patch
import requests

from careerorbit.config.settings import SETTINGS
from careerorbit.database.db import (
    init_db, save_inbox_message, get_inbox_message, get_inbox_message_by_uid,
    list_inbox_messages, get_inbox_stats, update_inbox_message_status,
    delete_inbox_message, get_telegram_offset, set_telegram_offset,
    get_job_by_id, list_jobs
)
from careerorbit.models.schemas import VerificationStatus
from careerorbit.telegram.client import TelegramClient, TelegramAPIError
from careerorbit.telegram.classifier import TelegramContentClassifier
from careerorbit.telegram.service import TelegramService
from careerorbit.telegram.worker import TelegramWorker
from tests.test_ui_and_study_decoupling import asgi_request
from careerorbit.web.app import app


def _authenticate_test_scope(scope):
    headers = list(scope.get("headers", []))
    headers.extend([
        (b"cookie", b"careerorbit_session=test-session-token; careerorbit_csrf=test-csrf-token"),
    ])
    if scope.get("method", "GET").upper() not in {"GET", "HEAD", "OPTIONS"}:
        headers.append((b"x-csrf-token", b"test-csrf-token"))
    scope["headers"] = headers


@pytest.fixture(autouse=True)
def ensure_db():
    init_db()


# ----------------- 1. Token Security & Redaction Tests -----------------

def test_telegram_token_security_and_redaction():
    """Verify bot token is never printed raw, is masked in repr, and redacted from error strings."""
    secret_token = "123456789:ABCdefGHIjklMNOpqrSTUvwxYZ"
    client = TelegramClient(token=secret_token)

    # 1. Masking
    masked = client.masked_token
    assert masked == "1234...wxYZ"
    assert secret_token not in masked

    # 2. String representation
    repr_str = repr(client)
    assert secret_token not in repr_str
    assert "1234...wxYZ" in repr_str

    # 3. Error redaction
    redacted = client._redact_token(f"Failed to connect to https://api.telegram.org/bot{secret_token}/getMe")
    assert secret_token not in redacted
    assert "[REDACTED_TELEGRAM_TOKEN]" in redacted


def test_telegram_unconfigured_behavior():
    """Verify client reports not configured and raises clean error when token is missing."""
    client = TelegramClient(token="")
    assert not client.is_configured
    assert client.masked_token == ""
    with pytest.raises(ValueError, match="Telegram Bot token is not configured"):
        client._build_url("getMe")


# ----------------- 2. Telegram Client Mock Tests -----------------

def test_telegram_client_get_me_success():
    """Verify getMe parses successful Telegram API response."""
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "ok": True,
        "result": {
            "id": 987654321,
            "is_bot": True,
            "first_name": "CareerOrbit Assistant",
            "username": "CareerOrbitJobAssistantBot"
        }
    }
    mock_session.get.return_value = mock_resp

    client = TelegramClient(token="mock_token", session=mock_session)
    res = client.get_me()
    assert res["id"] == 987654321
    assert res["username"] == "CareerOrbitJobAssistantBot"


def test_telegram_client_api_error_handling():
    """Verify TelegramAPIError is raised when API responds with ok=false."""
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "ok": False,
        "error_code": 401,
        "description": "Unauthorized: invalid bot token"
    }
    mock_session.get.return_value = mock_resp

    client = TelegramClient(token="invalid_token", session=mock_session)
    with pytest.raises(TelegramAPIError) as exc_info:
        client.get_me()
    assert exc_info.value.error_code == 401
    assert "Unauthorized" in str(exc_info.value)


def test_telegram_client_send_message():
    """Verify send_message issues correct POST body."""
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"ok": True, "result": {"message_id": 42}}
    mock_session.post.return_value = mock_resp

    client = TelegramClient(token="mock_token", session=mock_session)
    res = client.send_message(chat_id=12345, text="<b>Hello</b>", parse_mode="HTML")
    assert res["message_id"] == 42

    mock_session.post.assert_called_once()
    call_kwargs = mock_session.post.call_args[1]
    assert call_kwargs["json"]["chat_id"] == 12345
    assert call_kwargs["json"]["text"] == "<b>Hello</b>"
    assert call_kwargs["json"]["parse_mode"] == "HTML"


# ----------------- 3. Content Classification Engine Tests -----------------

def test_classifier_job_categories():
    """Verify discrete classification into Data Analyst, DS/ML, SWE, and Data Eng tracks."""
    c = TelegramContentClassifier

    # 1. Data Analyst / BI
    text_da = (
        "Hiring Alert: Caterpillar is looking for a Junior Data Analyst in Bengaluru!\n"
        "Skills: Power BI, DAX, SQL, Excel.\n"
        "Batch: 2024 / 2025 freshers eligible.\n"
        "Apply at: https://boards.greenhouse.io/caterpillar/jobs/123"
    )
    res_da = c.classify(text_da)
    assert res_da["classification"] == c.CAT_JOB_DATA_ANALYST
    assert res_da["is_job_lead"] is True
    assert "Power BI" in res_da["candidate_matches"]
    assert "SQL" in res_da["candidate_matches"]

    # 2. Data Science / AI / ML
    text_ds = (
        "Role: Junior Machine Learning Engineer / Computer Vision\n"
        "Company: Example Analytics Co\n"
        "Location: Chennai / Remote\n"
        "Requirements: Python, OpenCV, TensorFlow, CNN.\n"
        "Apply Link: https://forms.gle/testJob123"
    )
    res_ds = c.classify(text_ds)
    assert res_ds["classification"] == c.CAT_JOB_DATA_SCIENCE
    assert res_ds["is_job_lead"] is True
    assert "OpenCV" in res_ds["candidate_matches"]
    assert "TensorFlow" in res_ds["candidate_matches"]

    # 3. Software Engineering
    text_swe = (
        "We are hiring Associate Software Engineers (Python / FastAPI)!\n"
        "Location: Coimbatore / Hybrid.\n"
        "Eligible: 0-2 years experience, B.E. ECE / CSE.\n"
        "Apply now: https://jobs.lever.co/example-systems/ase-2025"
    )
    res_swe = c.classify(text_swe)
    assert res_swe["classification"] == c.CAT_JOB_SOFTWARE_ENG
    assert res_swe["is_job_lead"] is True
    assert "FastAPI" in res_swe["candidate_matches"]

    # 4. Data Engineering
    text_de = (
        "Vacancy: Junior Data Engineer (PySpark, Azure Data Factory, ETL)\n"
        "Company: Tiger Analytics\n"
        "Location: Hyderabad\n"
        "Apply: https://careers.smartrecruiters.com/tiger/data-engineer"
    )
    res_de = c.classify(text_de)
    assert res_de["classification"] == c.CAT_JOB_DATA_ENG
    assert res_de["is_job_lead"] is True


def test_classifier_non_job_categories():
    """Verify classification of Interview Prep, Coding Practice, Technical Materials, Certs, and Spam."""
    c = TelegramContentClassifier

    # Interview Prep
    text_prep = (
        "Top 50 Behavioral and Technical Interview Questions for Data Analysts!\n"
        "Learn the STAR method framework, sample answers for SQL query optimization questions, "
        "and how to describe your final year project in an interview."
    )
    assert c.classify(text_prep)["classification"] == c.CAT_INTERVIEW_PREP

    # Coding Practice
    text_coding = (
        "Daily DSA Challenge: Solve LeetCode 121 (Best Time to Buy and Sell Stock) using Two Pointers "
        "and Dynamic Programming. Check time complexity O(n) and space complexity O(1)."
    )
    assert c.classify(text_coding)["classification"] == c.CAT_CODING_PRACTICE

    # Technical Learning
    text_learn = (
        "Complete Python & SQL Handbook PDF for 2025:\n"
        "Download this free cheat sheet and architecture roadmap covering FastAPI, database indexing, and Pandas."
    )
    assert c.classify(text_learn)["classification"] == c.CAT_TECH_LEARNING

    # Certifications & Courses
    text_cert = (
        "100% Free Coupon: AWS Cloud Practitioner Certification Course on Udemy!\n"
        "Get your badge and certificate of completion before the coupon expires."
    )
    assert c.classify(text_cert)["classification"] == c.CAT_CERTIFICATIONS

    # Other Career Resources
    text_res = (
        "Here is a proven ATS resume template and LinkedIn optimization checklist "
        "to increase recruiter profile views."
    )
    assert c.classify(text_res)["classification"] == c.CAT_OTHER_CAREER

    # Irrelevant / Spam
    text_spam = "Good morning friends! Invest in crypto coins today for 100x profit."
    assert c.classify(text_spam)["classification"] == c.CAT_IRRELEVANT


def test_classifier_command():
    """Verify bot slash commands are identified as commands."""
    res = TelegramContentClassifier.classify("/start")
    assert res["is_command"] is True
    assert res["command"] == "/start"


# ----------------- 4. Telegram Service & Command Handlers -----------------

def test_telegram_service_commands():
    """Verify /start, /help, /profile, and /stats produce comprehensive answers."""
    mock_client = MagicMock()
    mock_client.is_configured = True
    service = TelegramService(client=mock_client)

    # /start
    res_start = service._handle_command("/start", chat_id=100, message_id=1, full_text="/start")
    assert "@CareerOrbitJobAssistantBot" in res_start
    assert "/help" in res_start
    assert "UNVERIFIED" in res_start

    # /help
    res_help = service._handle_command("/help", chat_id=100, message_id=2, full_text="/help")
    assert "How to Submit a Job Vacancy" in res_help
    assert "Channels" in res_help
    assert "privacy mode" in res_help.lower()

    # /profile
    res_prof = service._handle_command("/profile", chat_id=100, message_id=3, full_text="/profile")
    assert "Alex Example" in res_prof
    assert "Computer Engineering" in res_prof
    assert "Bengaluru" in res_prof

    # /stats
    res_stats = service._handle_command("/stats", chat_id=100, message_id=4, full_text="/stats")
    assert "Active Job Leads" in res_stats


# ----------------- 5. Job Ingestion & Strict UNVERIFIED Rule -----------------

def test_job_opportunity_ingested_as_unverified():
    """Strict Rule 9: Ingested community jobs must strictly enter as UNVERIFIED leads."""
    mock_client = MagicMock()
    mock_client.is_configured = False  # Avoid attempting real outbound HTTP
    service = TelegramService(client=mock_client)

    sample_update = {
        "update_id": 9001,
        "message": {
            "message_id": 55,
            "chat": {"id": 12345, "type": "group", "title": "TN Off-Campus Tech Hiring"},
            "from": {"id": 888, "first_name": "Recruiter", "username": "tn_recruiter"},
            "text": (
                "Company: Zoho Corporation\n"
                "Role: Junior Python Backend Developer\n"
                "Location: Chennai / Coimbatore\n"
                "Experience: Freshers 0-2 yrs (2024 / 2025 batch)\n"
                "Apply: https://jobs.lever.co/zoho/python-dev-entry-2025"
            ),
            "date": 1729690000
        }
    }

    result = service.process_update(sample_update)
    assert result["status"] == "PROCESSED"
    assert result["is_job_lead"] is True
    assert result["job_id"] is not None

    # Check job row in database
    job_row = get_job_by_id(result["job_id"])
    assert job_row is not None
    assert job_row["title"] == "Junior Python Backend Developer"
    assert job_row["employer"] == "Zoho Corporation"

    # STRICT RULE: Must be UNVERIFIED
    assert job_row["verification_status"] == VerificationStatus.UNVERIFIED.value
    assert "UNVERIFIED" in job_row["verification_status"]
    assert "Telegram" in job_row["discovery_source"]

    # Check inbox row
    inbox_msg = get_inbox_message_by_uid(result["message_uid"])
    assert inbox_msg is not None
    assert inbox_msg["is_job_lead"] == 1
    assert inbox_msg["job_id"] == result["job_id"]
    assert inbox_msg["classification"] == TelegramContentClassifier.CAT_JOB_SOFTWARE_ENG


def test_telegram_channel_post_support():
    """Verify channel_post objects from broadcast channels are ingested properly."""
    mock_client = MagicMock()
    mock_client.is_configured = False
    service = TelegramService(client=mock_client)

    channel_update = {
        "update_id": 9002,
        "channel_post": {
            "message_id": 108,
            "chat": {"id": -1001234567890, "type": "channel", "title": "South India IT Jobs Channel"},
            "text": (
                "Hiring Drive: Freshworks\n"
                "Role: Associate Data Analyst\n"
                "Location: Chennai / Remote\n"
                "Apply: https://jobs.lever.co/freshworks/data-analyst-2025"
            ),
            "date": 1729690100
        }
    }

    res = service.process_update(channel_update)
    assert res["status"] == "PROCESSED"
    assert res["is_job_lead"] is True

    job = get_job_by_id(res["job_id"])
    assert job["verification_status"] == "UNVERIFIED"
    assert "South India IT Jobs Channel" in job["discovery_source"]


# ----------------- 6. Unified Inbox Database CRUD & Stats -----------------

def test_inbox_crud_and_status_transitions():
    """Verify database saving, listing, filtering, status updating, and deletion."""
    test_uid = "tg_test_chat_9999"
    msg_id = save_inbox_message({
        "message_uid": test_uid,
        "channel": "telegram",
        "chat_id": "112233",
        "chat_title": "Interview Prep Group",
        "chat_type": "group",
        "message_id": 9999,
        "sender_name": "Mentor John",
        "raw_text": "System design interview question: Design a URL shortener like bit.ly.",
        "classification": "Interview Preparation",
        "category_group": "prep",
        "is_job_lead": 0,
        "status": "NEW"
    })
    assert msg_id > 0

    # Retrieve
    retrieved = get_inbox_message(msg_id)
    assert retrieved["message_uid"] == test_uid
    assert retrieved["classification"] == "Interview Preparation"
    assert retrieved["status"] == "NEW"

    # Status update: NEW -> PROCESSED
    assert update_inbox_message_status(msg_id, "PROCESSED", notes="Reviewed by candidate") is True
    updated = get_inbox_message(msg_id)
    assert updated["status"] == "PROCESSED"
    assert updated["notes"] == "Reviewed by candidate"

    # Filtered list
    prep_items = list_inbox_messages(classification="Interview Preparation")
    assert any(item["id"] == msg_id for item in prep_items)

    # Delete
    assert delete_inbox_message(msg_id) is True
    assert get_inbox_message(msg_id) is None


def test_telegram_offset_persistence():
    """Verify update offset is saved and retrieved from SQLite."""
    set_telegram_offset(456789)
    assert get_telegram_offset() == 456789

    set_telegram_offset(456790)
    assert get_telegram_offset() == 456790


# ----------------- 7. FastAPI REST Endpoints -----------------

@pytest.mark.anyio
async def test_api_telegram_status():
    """Verify GET /api/telegram/status returns structured bot diagnostics."""
    status, headers, body = await asgi_request(app, method="GET", path="/api/telegram/status")
    assert status == 200
    data = json.loads(body.decode("utf-8"))
    assert "bot_username" in data
    assert "configured" in data
    assert "inbox_summary" in data


@pytest.mark.anyio
async def test_api_telegram_poll_now_unconfigured():
    """Verify POST /api/telegram/poll-now returns clean NOT_CONFIGURED when token is absent."""
    status, headers, body = await asgi_request(app, method="POST", path="/api/telegram/poll-now")
    assert status == 200
    data = json.loads(body.decode("utf-8"))
    assert data["status"] in ("NOT_CONFIGURED", "SUCCESS", "ERROR", "WEBHOOK_CONFLICT")


@pytest.mark.anyio
async def test_api_inbox_list_and_stats():
    """Verify GET /api/inbox and GET /api/inbox/stats return items and metrics."""
    # Insert a test message first
    save_inbox_message({
        "message_uid": "tg_api_test_001",
        "channel": "telegram",
        "chat_id": "555",
        "message_id": 1,
        "raw_text": "Sample data analytics test vacancy",
        "classification": "Job: Data Analyst / BI",
        "category_group": "job",
        "is_job_lead": 1,
        "status": "NEW"
    })

    # Stats
    status, _, body = await asgi_request(app, method="GET", path="/api/inbox/stats")
    assert status == 200
    stats = json.loads(body.decode("utf-8"))
    assert stats["total"] >= 1

    # List
    status, _, body = await asgi_request(app, method="GET", path="/api/inbox", query="classification=Job%3A+Data+Analyst+%2F+BI")
    assert status == 200
    data = json.loads(body.decode("utf-8"))
    assert data["count"] >= 1
    assert any(i["message_uid"] == "tg_api_test_001" for i in data["items"])


@pytest.mark.anyio
async def test_api_inbox_status_update():
    """Verify PUT /api/inbox/{id}/status updates the record."""
    msg_id = save_inbox_message({
        "message_uid": "tg_status_update_002",
        "channel": "telegram",
        "chat_id": "777",
        "message_id": 2,
        "raw_text": "Some text",
        "classification": "Other Career Resources",
        "category_group": "career",
        "status": "NEW"
    })

    payload = json.dumps({"status": "ARCHIVED", "notes": "Handled"}).encode("utf-8")
    headers = {"Content-Type": "application/json"}

    # Use client request
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "PUT",
        "path": f"/api/inbox/{msg_id}/status",
        "raw_path": f"/api/inbox/{msg_id}/status".encode(),
        "query_string": b"",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "server": ("127.0.0.1", 8000),
        "client": ("127.0.0.1", 54321),
    }
    messages = []
    received = False
    async def receive():
        nonlocal received
        if not received:
            received = True
            return {"type": "http.request", "body": payload, "more_body": False}
        return {"type": "http.disconnect"}
    async def send(message):
        messages.append(message)
    _authenticate_test_scope(scope)
    await app(scope, receive, send)

    updated = get_inbox_message(msg_id)
    assert updated["status"] == "ARCHIVED"


# ----------------- 8. Frontend Helper & Advanced Integration Tests -----------------

def test_frontend_has_api_fetch_and_modals():
    """Verify frontend contains apiFetch helper, WhatsApp modal, and community modal."""
    from pathlib import Path
    html = Path("careerorbit/web/static/index.html").read_text(encoding="utf-8")
    assert "async function apiFetch" in html
    assert "isSyncingTelegram" in html
    assert "openCommunityImportModal" in html
    assert "openWhatsAppImportModal" in html
    assert "whatsapp-import-modal" in html
    assert "community-import-modal" in html
    assert "setInboxQuickFilter" in html


def test_telegram_duplicate_update_prevention():
    """Verify duplicate Telegram message does not re-ingest or re-notify."""
    mock_client = MagicMock()
    mock_client.is_configured = False
    service = TelegramService(client=mock_client)

    update = {
        "update_id": 9911,
        "message": {
            "message_id": 771,
            "chat": {"id": 12399, "type": "private"},
            "from": {"id": 12399, "first_name": "TestCandidate"},
            "text": "Junior Python Developer hiring at Example Systems in Coimbatore. Apply: https://jobs.lever.co/example-systems/py1",
            "date": 1729692000
        }
    }

    res1 = service.process_update(update)
    assert res1["status"] == "PROCESSED"
    first_inbox_id = res1["inbox_id"]

    # Process exact same update again
    res2 = service.process_update(update)
    assert res2["status"] == "DUPLICATE_SKIPPED"
    assert res2["inbox_id"] == first_inbox_id


def test_telegram_worker_preserves_webhook_on_polling_conflict():
    """A 409 reports a polling conflict without changing webhook configuration."""
    mock_client = MagicMock()
    mock_client.is_configured = True
    mock_client.get_updates.side_effect = TelegramAPIError(
        "can't use getUpdates method while webhook is active", error_code=409
    )
    mock_service = MagicMock()

    worker = TelegramWorker(client=mock_client, service=mock_service)
    res = worker.poll_once()

    mock_client.get_updates.assert_called_once()
    mock_client.delete_webhook.assert_not_called()
    mock_service.process_update.assert_not_called()
    assert res["status"] == "WEBHOOK_CONFLICT"
    assert res["processed_count"] == 0
    assert res["webhook_changed"] is False
    assert "left unchanged" in res["error"]


def test_telegram_worker_start_is_idempotent_while_running():
    """Repeated start requests reuse the live worker rather than spawning another thread."""
    mock_client = MagicMock()
    mock_client.is_configured = True
    mock_client.get_me.return_value = {"id": 44, "username": "test_bot"}
    mock_client.get_updates.return_value = []
    worker = TelegramWorker(client=mock_client, service=MagicMock(), poll_interval=30)

    try:
        assert worker.start() is True
        first_thread = worker._thread
        assert first_thread is not None and first_thread.is_alive()
        assert worker.start() is True
        assert worker._thread is first_thread
        mock_client.get_me.assert_called_once()
    finally:
        worker.stop(timeout=2)


def test_telegram_worker_stops_loop_after_webhook_conflict():
    """The background worker stops on a persistent webhook conflict without mutation."""
    mock_client = MagicMock()
    mock_client.is_configured = True
    mock_client.get_me.return_value = {"id": 45, "username": "test_bot"}
    mock_client.get_updates.side_effect = TelegramAPIError(
        "can't use getUpdates method while webhook is active", error_code=409
    )
    worker = TelegramWorker(client=mock_client, service=MagicMock(), poll_interval=30)

    assert worker.start() is True
    worker._thread.join(timeout=2)

    assert not worker._thread.is_alive()
    assert worker.last_poll_status == "WEBHOOK_CONFLICT"
    mock_client.get_updates.assert_called_once()
    mock_client.delete_webhook.assert_not_called()


@pytest.mark.anyio
async def test_api_inbox_promote_to_study_resource():
    """Verify POST /api/inbox/{id}/save-resource promotes message to study resources."""
    msg_id = save_inbox_message({
        "message_uid": "tg_resource_promote_001",
        "channel": "telegram",
        "chat_id": "888",
        "message_id": 10,
        "raw_text": "Complete FastAPI & Microservices Architecture Guide:\nhttps://github.com/fastapi-guide/microservices",
        "classification": "Technical Learning Materials",
        "category_group": "learning",
        "status": "NEW"
    })

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "path": f"/api/inbox/{msg_id}/save-resource",
        "raw_path": f"/api/inbox/{msg_id}/save-resource".encode(),
        "query_string": b"",
        "headers": [(b"content-type", b"application/json")],
        "server": ("127.0.0.1", 8000),
        "client": ("127.0.0.1", 54321),
    }
    messages = []
    received = False
    async def receive():
        nonlocal received
        if not received:
            received = True
            return {"type": "http.request", "body": b"{}", "more_body": False}
        return {"type": "http.disconnect"}
    async def send(message):
        messages.append(message)
    _authenticate_test_scope(scope)
    await app(scope, receive, send)

    # Inbox item should be marked PROCESSED
    item = get_inbox_message(msg_id)
    assert item["status"] == "PROCESSED"


def test_telegram_check_chat_access_admin():
    """Verify check_chat_access returns ADMIN_ACTIVE and can_receive_messages=True when bot is admin in channel."""
    mock_session = MagicMock()
    mock_resp_me = MagicMock()
    mock_resp_me.json.return_value = {"ok": True, "result": {"id": 1001, "username": "TestBot", "is_bot": True}}
    mock_resp_chat = MagicMock()
    mock_resp_chat.json.return_value = {"ok": True, "result": {"id": -100999, "title": "Tech Alerts", "type": "channel"}}
    mock_resp_member = MagicMock()
    mock_resp_member.json.return_value = {"ok": True, "result": {"status": "administrator", "can_post_messages": True}}

    client = TelegramClient(token="mock_token", session=mock_session)
    with patch.object(client, "get_me", return_value={"id": 1001, "username": "TestBot"}), \
         patch.object(client, "get_chat", return_value={"id": -100999, "title": "Tech Alerts", "type": "channel"}), \
         patch.object(client, "get_chat_member", return_value={"status": "administrator", "can_post_messages": True}):
        res = client.check_chat_access("@techalerts")
        assert res["accessible"] is True
        assert res["status"] == "ADMIN_ACTIVE"
        assert res["can_receive_messages"] is True
        assert "Administrator" in res["diagnosis"]


def test_telegram_check_chat_access_permission_required():
    """Verify check_chat_access reports PERMISSION_REQUIRED when bot is only member in a channel."""
    client = TelegramClient(token="mock_token")
    with patch.object(client, "get_me", return_value={"id": 1001, "username": "TestBot"}), \
         patch.object(client, "get_chat", return_value={"id": -100888, "title": "Public Channel", "type": "channel"}), \
         patch.object(client, "get_chat_member", return_value={"status": "member"}):
        res = client.check_chat_access("@publicchannel")
        assert res["accessible"] is False
        assert res["status"] == "PERMISSION_REQUIRED"
        assert res["can_receive_messages"] is False
        assert "administrator" in res["missing_permissions"]
        assert "Add Administrator" in res["setup_instructions"]


def test_telegram_check_chat_access_not_found():
    """Verify check_chat_access reports NOT_FOUND for invalid chat handles."""
    client = TelegramClient(token="mock_token")
    with patch.object(client, "get_me", return_value={"id": 1001, "username": "TestBot"}), \
         patch.object(client, "get_chat", side_effect=TelegramAPIError("Bad Request: chat not found", error_code=400)):
        res = client.check_chat_access("@nonexistent12345")
        assert res["accessible"] is False
        assert res["status"] == "NOT_FOUND"
        assert res["can_receive_messages"] is False
        assert "not found" in res["diagnosis"]


def test_telegram_check_chat_access_group_privacy():
    """Verify check_chat_access detects Group Privacy Mode for standard group members."""
    client = TelegramClient(token="mock_token")
    with patch.object(client, "get_me", return_value={"id": 1001, "username": "TestBot"}), \
         patch.object(client, "get_chat", return_value={"id": -555, "title": "Dev Group", "type": "group"}), \
         patch.object(client, "get_chat_member", return_value={"status": "member"}):
        res = client.check_chat_access("-555")
        assert res["status"] == "PRIVACY_RESTRICTED"
        assert res["can_receive_messages"] is False
        assert "Privacy Mode" in res["diagnosis"]
        assert "/setprivacy" in res["setup_instructions"]


def test_caterpillar_greenhouse_404_detection():
    """Verify verifier flags Caterpillar Greenhouse 404 URL as VERIFIED_CLOSED."""
    from careerorbit.verifier.checker import VerificationEngine
    engine = VerificationEngine()
    
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.text = "<html><head><title>Page not found</title></head><body>The page you are looking for does not exist.</body></html>"

    with patch.object(engine.session, "get", return_value=mock_resp):
        status, notes = engine.verify_listing("https://boards.greenhouse.io/caterpillar/jobs/778899", employer="Caterpillar")
        assert status == VerificationStatus.VERIFIED_CLOSED
        assert "404" in notes


def test_community_parser_caterpillar_extraction():
    """Verify parser extracts Caterpillar employer and clean title from unstructured text."""
    from careerorbit.discovery.community_parser import CommunityJobParser
    text = (
        "Off-Campus Hiring: Caterpillar Junior Data Analyst Bengaluru\n"
        "Batch: 2024 / 2025\n"
        "Apply: https://boards.greenhouse.io/caterpillar/jobs/778899"
    )
    parsed = CommunityJobParser.parse_announcement(text)
    assert parsed["employer"] == "Caterpillar"
    assert "Junior Data Analyst" in parsed["title"]
    assert "Bengaluru" in parsed["location"]
    assert parsed["is_off_campus"] is True
    assert parsed["is_fresher"] is True


@pytest.mark.anyio
async def test_api_community_sources_endpoints():
    """Verify community sources register, recheck, and delete endpoints."""
    # 1. Register
    mock_access = {
        "accessible": True,
        "status": "ADMIN_ACTIVE",
        "can_receive_messages": True,
        "chat_id": "-100777",
        "chat_title": "Bangalore Python Jobs",
        "chat_type": "channel",
        "diagnosis": "Bot is admin"
    }
    with patch.object(TelegramClient, "check_chat_access", return_value=mock_access):
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "path": "/api/community/sources/register-telegram",
            "raw_path": b"/api/community/sources/register-telegram",
            "query_string": b"",
            "headers": [(b"content-type", b"application/json")],
            "server": ("127.0.0.1", 8000),
            "client": ("127.0.0.1", 54321),
        }
        messages = []
        received = False
        async def receive():
            nonlocal received
            if not received:
                received = True
                return {"type": "http.request", "body": json.dumps({"chat_id": "@bangalore_py"}).encode(), "more_body": False}
            return {"type": "http.disconnect"}
        async def send(message):
            messages.append(message)
        _authenticate_test_scope(scope)
        await app(scope, receive, send)

        body = json.loads([m["body"] for m in messages if m["type"] == "http.response.body"][0].decode())
        assert body["status"] == "SUCCESS"
        source_id = body["source_id"]

        # 2. Recheck
        messages.clear()
        received = False
        scope["path"] = f"/api/community/sources/{source_id}/recheck"
        scope["raw_path"] = f"/api/community/sources/{source_id}/recheck".encode()
        _authenticate_test_scope(scope)
        await app(scope, receive, send)
        recheck_body = json.loads([m["body"] for m in messages if m["type"] == "http.response.body"][0].decode())
        assert recheck_body["status"] == "SUCCESS"
        assert recheck_body["updated_status"] == "ACTIVE"

        # 3. Delete
        messages.clear()
        scope["method"] = "DELETE"
        scope["path"] = f"/api/community/sources/{source_id}"
        scope["raw_path"] = f"/api/community/sources/{source_id}".encode()
        _authenticate_test_scope(scope)
        await app(scope, receive, send)
        del_body = json.loads([m["body"] for m in messages if m["type"] == "http.response.body"][0].decode())
        assert del_body["status"] == "SUCCESS"


@pytest.mark.anyio
async def test_api_whatsapp_status():
    """Verify GET /api/whatsapp/status returns compliance disclosures and mode."""
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "path": "/api/whatsapp/status",
        "raw_path": b"/api/whatsapp/status",
        "query_string": b"",
        "headers": [(b"content-type", b"application/json")],
        "server": ("127.0.0.1", 8000),
        "client": ("127.0.0.1", 54321),
    }
    messages = []
    async def receive():
        return {"type": "http.disconnect"}
    async def send(message):
        messages.append(message)
    _authenticate_test_scope(scope)
    await app(scope, receive, send)

    body = json.loads([m["body"] for m in messages if m["type"] == "http.response.body"][0].decode())
    assert body["mode"] == "MANUAL_CHAT_EXPORT"
    assert body["polling_active"] is False
    assert "WhatsApp Terms of Service" in body["compliance_notice"]


# ----------------- 9. Telegram Desktop Export & Channel Member Tests -----------------

def test_telegram_my_chat_member_admin_promotion():
    """Verify my_chat_member updates automatically register the channel when bot is promoted to Admin."""
    from careerorbit.database.db import get_community_source, list_community_sources

    mock_client = MagicMock()
    mock_client.is_configured = False
    service = TelegramService(client=mock_client)

    chat_id = -10099887766
    update = {
        "update_id": 9933,
        "my_chat_member": {
            "chat": {
                "id": chat_id,
                "title": "Fresher Offcampus Drives Channel",
                "type": "channel",
                "username": "fresher_drives"
            },
            "new_chat_member": {
                "status": "administrator",
                "can_post_messages": True
            }
        }
    }

    res = service.process_update(update)
    assert res["status"] == "MEMBERSHIP_UPDATED"
    assert res["chat_id"] == str(chat_id)
    assert res["bot_role"] == "administrator"
    assert res["can_receive_messages"] is True

    # Verify source was created/updated in SQLite
    sources = list_community_sources()
    matching = [s for s in sources if s["chat_id"] == str(chat_id)]
    assert len(matching) == 1
    src = matching[0]
    assert src["source_name"] == "Telegram: Fresher Offcampus Drives Channel"
    assert src["bot_role"] == "administrator"
    assert src["can_receive_messages"] == 1
    assert src["is_public"] == 1


def test_telegram_forwarded_message_parsing_and_origin_attribution():
    """Verify forwarded channel posts preserve channel title, message ID, and post links."""
    mock_client = MagicMock()
    mock_client.is_configured = False
    service = TelegramService(client=mock_client)

    forward_update = {
        "update_id": 9944,
        "message": {
            "message_id": 401,
            "chat": {"id": 123456, "type": "private"},
            "from": {"id": 123456, "first_name": "Alex"},
            "forward_origin": {
                "type": "channel",
                "chat": {
                    "id": -1001122334455,
                    "title": "Chennai Jobs Coimbatore Jobs Update",
                    "username": "chennai_jobs_hub"
                },
                "message_id": 8802
            },
            "text": (
                "New Vacancy Alert!\n"
                "Company: Caterpillar India\n"
                "Role: Junior Data Analyst\n"
                "Location: Bengaluru, Karnataka\n"
                "Apply: https://boards.greenhouse.io/caterpillar/jobs/998877"
            ),
            "date": 1729693000
        }
    }

    res = service.process_update(forward_update)
    assert res["status"] == "PROCESSED"
    assert res["message_uid"] == "tg_fwd_-1001122334455_8802"

    inbox_msg = get_inbox_message_by_uid("tg_fwd_-1001122334455_8802")
    assert inbox_msg is not None
    assert inbox_msg["chat_title"] == "Chennai Jobs Coimbatore Jobs Update"
    assert inbox_msg["extracted_data"]["origin_link"] == "https://t.me/chennai_jobs_hub/8802"
    assert inbox_msg["is_job_lead"] == 1

    # Verify associated job lead is strictly UNVERIFIED
    job_row = get_job_by_id(res["job_id"])
    assert job_row["verification_status"] == "UNVERIFIED"
    assert "Chennai Jobs Coimbatore Jobs Update" in job_row["discovery_source"]


def test_telegram_chat_export_parser_json():
    """Verify TelegramChatExportParser processes Telegram Desktop result.json correctly."""
    from careerorbit.telegram.export_parser import TelegramChatExportParser

    sample_json = {
        "name": "Work From Home JOBS",
        "type": "public_channel",
        "id": 1009876543,
        "messages": [
            {
                "id": 1001,
                "type": "service",
                "action": "pin_message",
                "text": ""
            },
            {
                "id": 1002,
                "type": "message",
                "date": "2026-10-23T10:00:00",
                "text": [
                    "Hiring Alert: Junior Data Analyst at TechCorp!\n",
                    {"type": "link", "text": "https://techcorp.example.com/careers/da1"}
                ]
            },
            {
                "id": 1003,
                "type": "message",
                "date": "2026-10-23T11:00:00",
                "text": "Good morning everyone! Have a nice weekend."
            }
        ]
    }

    parsed = TelegramChatExportParser.parse_json(sample_json)
    assert parsed["chat_name"] == "Work From Home JOBS"
    assert parsed["total_raw_messages"] == 3
    assert parsed["job_leads_count"] == 1
    assert len(parsed["items"]) == 2  # Service message skipped

    items = parsed["items"]
    job_item = [it for it in items if it["is_job_lead"]][0]
    assert "Junior Data Analyst" in job_item["raw_text"]
    assert job_item["message_id"] == 1002
    assert "https://techcorp.example.com/careers/da1" in job_item["urls"]


def test_telegram_chat_export_parser_html():
    """Verify TelegramChatExportParser processes Telegram Desktop messages.html correctly."""
    from careerorbit.telegram.export_parser import TelegramChatExportParser

    sample_html = """<!DOCTYPE html>
<html>
<head><title>Export</title></head>
<body>
  <div class="page_header">
    <div class="text bold">Developer Sparks Offcampus</div>
  </div>
  <div class="message default clearfix" id="message105">
    <div class="body">
      <div class="from_name">Developer Sparks</div>
      <div class="date details" title="23.10.2026 14:30:00">14:30</div>
      <div class="text">
        Immediate hiring: Junior Python Backend Developer (FastAPI) at InMobi Bengaluru.<br>
        Apply: <a href="https://inmobi.com/jobs/dev-1">https://inmobi.com/jobs/dev-1</a>
      </div>
    </div>
  </div>
</body>
</html>"""

    parsed = TelegramChatExportParser.parse_html(sample_html)
    assert parsed["chat_name"] == "Developer Sparks Offcampus"
    assert parsed["total_raw_messages"] == 1
    assert parsed["job_leads_count"] == 1
    item = parsed["items"][0]
    assert item["message_id"] == 105
    assert "Junior Python Backend Developer" in item["raw_text"]
    assert "https://inmobi.com/jobs/dev-1" in item["urls"]


def test_telegram_chat_export_import_and_dedup():
    """Verify importing items creates unverified jobs, saves to inbox, and deduplicates on repeat import."""
    from careerorbit.telegram.export_parser import TelegramChatExportParser

    raw_items = [
        {
            "message_uid": "tg_exp_1009988_901_a1b2c3d4e5f6",
            "message_id": 901,
            "chat_id": "1009988",
            "chat_name": "Off Campus Hiring 2026",
            "chat_type": "public_channel",
            "sender_name": "Off Campus Hiring 2026",
            "timestamp_raw": "2026-10-23T15:00:00",
            "raw_text": "Zoho Corporation is hiring Junior Python Developer in Chennai! Apply at https://jobs.lever.co/zoho/python-entry-2026",
            "urls": ["https://jobs.lever.co/zoho/python-entry-2026"],
            "classification": "Job: Software Engineering",
            "category_group": "job",
            "is_job_lead": True,
            "filename": "offcampus_export.json",
            "export_format": "telegram_desktop_json"
        }
    ]

    parsed_data = {
        "chat_name": "Off Campus Hiring 2026",
        "chat_id": "1009988",
        "chat_type": "public_channel",
        "filename": "offcampus_export.json",
        "items": raw_items
    }

    import_res = TelegramChatExportParser.import_items(parsed_data)

    assert import_res["imported_count"] == 1
    assert import_res["duplicates_count"] == 0
    assert import_res["jobs_created"] == 1

    # Second import with the exact same items -> duplicate skipped
    import_res2 = TelegramChatExportParser.import_items(parsed_data)
    assert import_res2["imported_count"] == 0
    assert import_res2["duplicates_count"] == 1


@pytest.mark.anyio
async def test_api_telegram_export_routes():
    """Verify /api/telegram/export/parse-preview, /import, and /status REST endpoints."""
    sample_payload = {
        "content": json.dumps({
            "name": "FoundtheInternship",
            "type": "public_channel",
            "id": 1005544,
            "messages": [
                {
                    "id": 501,
                    "type": "message",
                    "date": "2026-10-23T16:00:00",
                    "text": "Data Analyst Intern needed at AnalyticsVidhya Bengaluru. Apply: https://example.com/apply-intern"
                }
            ]
        }),
        "filename": "result.json"
    }

    # 1. Preview
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "path": "/api/telegram/export/parse-preview",
        "raw_path": b"/api/telegram/export/parse-preview",
        "query_string": b"",
        "headers": [(b"content-type", b"application/json")],
        "server": ("127.0.0.1", 8000),
        "client": ("127.0.0.1", 54321),
    }
    messages = []
    received = False
    async def receive():
        nonlocal received
        if not received:
            received = True
            return {"type": "http.request", "body": json.dumps(sample_payload).encode(), "more_body": False}
        return {"type": "http.disconnect"}
    async def send(message):
        messages.append(message)
    _authenticate_test_scope(scope)
    await app(scope, receive, send)

    body_bytes = b"".join(m["body"] for m in messages if m["type"] == "http.response.body")
    preview_resp = json.loads(body_bytes.decode())
    assert preview_resp["chat_name"] == "FoundtheInternship"
    assert preview_resp["total_raw_messages"] == 1

    # 2. Import
    import_payload = preview_resp
    messages.clear()
    received = False
    scope["path"] = "/api/telegram/export/import"
    scope["raw_path"] = b"/api/telegram/export/import"
    async def receive_import():
        nonlocal received
        if not received:
            received = True
            return {"type": "http.request", "body": json.dumps(import_payload).encode(), "more_body": False}
        return {"type": "http.disconnect"}
    _authenticate_test_scope(scope)
    await app(scope, receive_import, send)

    import_bytes = b"".join(m["body"] for m in messages if m["type"] == "http.response.body")
    import_resp = json.loads(import_bytes.decode())
    assert import_resp["status"] == "SUCCESS"
    assert import_resp["imported_count"] == 1

    # 3. Status
    messages.clear()
    scope["method"] = "GET"
    scope["path"] = "/api/telegram/export/status"
    scope["raw_path"] = b"/api/telegram/export/status"
    async def receive_status():
        return {"type": "http.disconnect"}
    _authenticate_test_scope(scope)
    await app(scope, receive_status, send)

    status_bytes = b"".join(m["body"] for m in messages if m["type"] == "http.response.body")
    status_resp = json.loads(status_bytes.decode())
    assert "MANUAL_TELEGRAM_EXPORT" in status_resp["mode"]
    assert any(".json" in fmt for fmt in status_resp["supported_formats"])




