"""Test Telegram Desktop Chat Export timeout fix, batch optimization, and override support."""
import json
import pytest
from pathlib import Path
from careerorbit.telegram.export_parser import TelegramChatExportParser, _flatten_telegram_json_text
from careerorbit.telegram.classifier import TelegramContentClassifier
from careerorbit.database.db import init_db, get_connection


@pytest.fixture(autouse=True)
def setup_test_db():
    init_db()


def test_flatten_telegram_json_text_edge_cases():
    """Verify text flattening handles None, strings, lists with dicts/ints, and malformed inputs."""
    assert _flatten_telegram_json_text(None) == ""
    assert _flatten_telegram_json_text("") == ""
    assert _flatten_telegram_json_text("Normal text") == "Normal text"
    assert _flatten_telegram_json_text(["Part 1 ", {"type": "bold", "text": "Part 2"}, " Part 3"]) == "Part 1 Part 2 Part 3"
    assert _flatten_telegram_json_text([None, 123, {"text": "hello"}]) == "123hello"
    assert _flatten_telegram_json_text({"text": "dict text"}) == "dict text"


def test_telegram_export_parse_json_fast_with_batch_fixture():
    """Verify Telegram export parse runs fast and respects override_title."""
    messages = []
    for i in range(500):
        messages.append({
            "id": i + 1,
            "type": "message",
            "date": "2026-10-25T10:00:00",
            "from": "Admin",
            "text": [
                f"Microsoft hiring Junior Software Engineer #{i} in Bangalore\n",
                {"type": "link", "text": f"https://careers.microsoft.com/job/{i}"},
                "\nEligibility: 0-2 years, BE/BTech 2024/2025 batch."
            ]
        })
    # Add some short personal messages (< 6 words)
    for i in range(100):
        messages.append({
            "id": 1000 + i,
            "type": "message",
            "date": "2026-10-25T10:00:00",
            "from": "Friend",
            "text": "Good morning everyone!"
        })

    fixture_data = {
        "name": "Original Channel Name",
        "type": "public_channel",
        "id": 987654321,
        "messages": messages
    }
    raw_json = json.dumps(fixture_data)

    parsed = TelegramChatExportParser.parse_json(
        raw_json,
        filename="result.json",
        override_title="Hardened Test Channel"
    )

    assert parsed["chat_name"] == "Hardened Test Channel"
    assert parsed["total_raw_messages"] == 600
    assert parsed["career_relevant"] == 500
    assert parsed["personal_skipped"] == 100
    assert parsed["job_leads_count"] == 500
    assert len(parsed["items"]) == 500


def test_telegram_export_import_idempotent():
    """Verify import_items commits correctly and skips duplicates on second run."""
    unique_channel = f"Test Export Channel {Path(__file__).stem}"
    items = [
        {
            "message_uid": f"tg_exp_unit_test_{i}",
            "message_id": i,
            "chat_id": "test_chat_1",
            "chat_name": unique_channel,
            "chat_type": "channel",
            "sender_name": "Test Poster",
            "timestamp_raw": "2026-10-25T12:00:00Z",
            "raw_text": f"Amazon hiring Graduate SDE in Chennai #{i} https://amazon.jobs/en/jobs/test{i}",
            "classification": TelegramContentClassifier.CAT_JOB_SOFTWARE_ENG,
            "category_group": "JOBS",
            "is_job_lead": True,
            "job_parsed": {
                "title": "Graduate SDE",
                "employer": f"Amazon {i}",
                "location": "Chennai",
                "experience": "0-1 years",
                "deadline": None,
                "application_url": f"https://amazon.jobs/en/jobs/test{i}",
                "all_urls": [f"https://amazon.jobs/en/jobs/test{i}"],
                "source_channel": unique_channel,
                "priority_category": 1,
                "priority_label": "High Priority",
                "geographic_priority": 1,
                "geographic_tier_label": "Priority 1",
                "location_eligibility_status": "VERIFIED_INDIA_ELIGIBLE",
                "is_fresher": True,
                "is_off_campus": False,
                "is_internship": False,
                "is_walkin": False,
                "job_uid": f"job_uid_test_exp_{i}",
                "is_duplicate": False,
                "duplicate_ref": None,
                "missing_link": False,
                "raw_text": f"Amazon hiring Graduate SDE in Chennai #{i}"
            },
            "tech_tags": ["python", "sde"],
            "candidate_matches": [],
            "urls": [f"https://amazon.jobs/en/jobs/test{i}"],
            "filename": "result.json",
            "export_format": "telegram_desktop_json"
        }
        for i in range(3)
    ]

    export_data = {
        "chat_name": unique_channel,
        "chat_id": "test_chat_1",
        "filename": "result.json",
        "items": items
    }

    # First import: should ingest all 3
    res1 = TelegramChatExportParser.import_items(export_data)
    assert res1["status"] == "SUCCESS"
    assert res1["imported_count"] == 3
    assert res1["duplicates_count"] == 0

    # Second import with exact same data: should skip all 3 as duplicates
    res2 = TelegramChatExportParser.import_items(export_data)
    assert res2["status"] == "SUCCESS"
    assert res2["imported_count"] == 0
    assert res2["duplicates_count"] == 3

    # Clean up test rows
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM inbox_messages WHERE message_uid LIKE 'tg_exp_unit_test_%'")
    c.execute("DELETE FROM jobs WHERE job_uid LIKE 'job_uid_test_exp_%'")
    conn.commit()
    conn.close()
