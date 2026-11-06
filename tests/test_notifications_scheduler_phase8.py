"""Phase 8 verification test suite for Notifications & Background Tasks.

Verifies:
1. Telegram bot client security, masking, and token redaction.
2. Graceful unconfigured handling and classifier accuracy.
3. WhatsApp Android & iOS chat export parsing and duplicate suppression.
4. Scheduler thread lifecycle, concurrency guards, and run history.
"""
from datetime import datetime, timezone
from unittest.mock import MagicMock
import pytest
from careerorbit.database.db import init_db
from careerorbit.telegram.client import TelegramClient, TelegramAPIError
from careerorbit.telegram.classifier import TelegramContentClassifier
from careerorbit.whatsapp.parser import WhatsAppChatExportParser
from careerorbit.scheduler.runner import BackgroundScheduler
from careerorbit.scheduler.run_history import record_run, latest_success


@pytest.fixture(autouse=True)
def setup_test_db():
    """Initializes the database schema for the test."""
    init_db()


# ---------------- 1. Telegram Client Security & Redaction ----------------

def test_telegram_client_token_masking_and_redaction():
    """Verifies that Telegram bot tokens are masked and stripped from logs and URLs."""
    raw_token = "123456789:ABCdefGHIjklMNOpqrSTUvwxYZ_1234567"
    client = TelegramClient(token=raw_token)

    assert client.is_configured is True
    # Masked token shows only 4 prefix and 4 suffix characters
    assert client.masked_token.startswith("1234...")
    assert client.masked_token.endswith("4567")
    assert raw_token not in client.masked_token

    # Token redaction in strings and error messages
    error_text = f"Connection failed to https://api.telegram.org/bot{raw_token}/sendMessage"
    redacted = client._redact_token(error_text)
    assert raw_token not in redacted
    assert "[REDACTED_TELEGRAM_TOKEN]" in redacted


def test_telegram_unconfigured_safety():
    """Verifies that an unconfigured Telegram client safely reports state without crashing."""
    client = TelegramClient(token="")
    assert client.is_configured is False
    assert client.masked_token == ""

    # Building a request URL without token raises clean ValueError
    with pytest.raises(ValueError) as exc_info:
        client._build_url("getMe")
    assert "not configured" in str(exc_info.value).lower()


def test_telegram_content_classifier():
    """Verifies classification of career opportunities versus conversational noise."""
    classifier = TelegramContentClassifier()

    job_text = (
        "We are hiring a Junior Data Analyst in Bengaluru! "
        "Required: Python, SQL, Power BI. 0-1 years exp. Apply at https://example.com/careers/da1"
    )
    result = classifier.classify(job_text)
    assert result["is_job_lead"] is True
    assert result["category_group"] == "job"
    assert "data" in [t.lower() for t in result["tech_tags"]] or "python" in [t.lower() for t in result["tech_tags"]]

    noise_text = "Good morning everyone! Please check the meeting link sent yesterday."
    noise_result = classifier.classify(noise_text)
    assert noise_result["is_job_lead"] is False


# ---------------- 2. WhatsApp Chat Export Parser ----------------

def test_whatsapp_android_and_ios_chat_parsing():
    """Verifies parsing of Android and iOS exported WhatsApp message formats."""
    parser = WhatsAppChatExportParser()

    chat_content = """
12/10/24, 10:15 am - Messages and calls are end-to-end encrypted.
12/10/24, 10:20 am - Alice: Hiring Junior Software Engineer at FinScale Bengaluru. Apply: https://finscale.com/jobs/swe-1
12/10/24, 10:25 am - Bob: Thanks!
[12/10/2026, 11:00:15] Charlie: <media omitted>
[12/10/2026, 11:05:30] Charlie: Urgently looking for BI Analyst with Power BI and SQL in Chennai. Link: https://corp.com/careers/bi
[12/10/2026, 11:10:00] Dave: ok
"""
    parsed = parser.parse_text(chat_content)
    items = parsed["items"]
    # Should extract valid career messages (Alice and Charlie), filtering out system and chit-chat
    assert len(items) >= 2
    senders = [m["sender"] for m in items]
    assert "Alice" in senders
    assert "Charlie" in senders
    assert "Bob" not in senders  # "Thanks!" filtered as noise
    assert "Dave" not in senders  # "ok" filtered as noise


def test_whatsapp_duplicate_suppression():
    """Verifies that importing the same chat message twice produces zero duplicate records."""
    parser = WhatsAppChatExportParser()
    chat_content = """
14/10/24, 09:00 - Recruiter: Hiring Junior Python Developer in Coimbatore. Link: https://acme.org/jobs/py-dev
"""
    parsed = parser.parse_text(chat_content)
    items = parsed["items"]
    assert len(items) >= 1

    # First ingest
    res1 = WhatsAppChatExportParser.import_items(items, chat_title="Phase8 Group")
    assert res1["imported_inbox"] >= 1

    # Second ingest of identical items
    res2 = WhatsAppChatExportParser.import_items(items, chat_title="Phase8 Group")
    assert res2["skipped_duplicates"] >= 1
    assert res2["imported_jobs"] == 0


# ---------------- 3. Background Scheduler ----------------

def test_scheduler_lifecycle_and_status():
    """Verifies scheduler status reporting, thread startup, and shutdown."""
    scheduler = BackgroundScheduler()
    scheduler.check_and_recover_missed_run = MagicMock(return_value=False)
    scheduler.trigger_discovery_now = MagicMock(return_value={"status": "mocked"})

    status = scheduler.get_status()
    assert "scheduler_running" in status
    assert "current_ist_time" in status
    assert "target_discovery_time" in status
    assert "08:00 AM" in status["target_discovery_time"]

    # Start and stop lifecycle
    scheduler.start()
    assert scheduler.running is True
    assert scheduler._thread is not None
    assert scheduler._thread.is_alive() is True

    scheduler.stop()
    assert scheduler.running is False


def test_scheduler_run_history_tracking():
    """Verifies recording workflow execution history."""
    record_run(
        workflow="job_discovery",
        status="success",
        summary={"total_collected": 10, "new_jobs_added": 3}
    )
    latest = latest_success("job_discovery")
    assert latest is not None
    assert latest["summary"]["total_collected"] == 10
    assert latest["summary"]["new_jobs_added"] == 3
