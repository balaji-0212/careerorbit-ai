"""Repeatable tests for Telegram ingestion edge cases.

Verifies:
1. Duplicate deliveries with identical update_id are skipped.
2. Duplicate deliveries with distinct update_ids but identical message_uid are skipped.
3. Mid-batch processing errors halt offset advancement to allow graceful retries on next poll.
4. Classification matrix: Job leads vs. Community Resources vs. Commands vs. Irrelevant/Spam.
5. Forwarded announcements extract origin channel metadata and links.
6. Offset increments monotonically and persists across polling cycles.
"""
from unittest.mock import MagicMock, patch
import pytest

from careerorbit.database.db import (
    init_db,
    get_inbox_message_by_uid,
    list_inbox_messages,
    get_job_by_id,
    list_jobs,
    get_telegram_offset,
    set_telegram_offset,
)
from careerorbit.models.schemas import VerificationStatus
from careerorbit.telegram.client import TelegramClient
from careerorbit.telegram.service import TelegramService
from careerorbit.telegram.worker import TelegramWorker


@pytest.fixture(autouse=True)
def setup_test_db():
    init_db()


def test_telegram_duplicate_update_id_delivery():
    """Verify that delivering the same update_id twice is safely deduplicated."""
    mock_client = MagicMock(spec=TelegramClient)
    mock_client.is_configured = True
    service = TelegramService(client=mock_client)

    update = {
        "update_id": 501,
        "message": {
            "message_id": 100,
            "chat": {"id": 9999, "type": "private", "title": "Test Chat"},
            "from": {"id": 111, "first_name": "Test", "last_name": "User"},
            "text": "Looking for Junior Data Analyst in Bengaluru. Skills: Python, SQL. Apply: https://example.com/job1",
        }
    }

    # First delivery
    res1 = service.process_update(update)
    assert res1["status"] == "PROCESSED"
    assert res1["is_job_lead"] is True
    inbox_id_1 = res1["inbox_id"]

    # Second delivery (duplicate update)
    res2 = service.process_update(update)
    assert res2["status"] == "DUPLICATE_SKIPPED"
    assert res2["inbox_id"] == inbox_id_1

    # Database must contain exactly 1 inbox item
    all_msgs = list_inbox_messages()
    assert len(all_msgs) == 1


def test_telegram_duplicate_message_uid_across_different_update_ids():
    """Verify deduplication when Telegram redelivers the same message with a different update_id."""
    mock_client = MagicMock(spec=TelegramClient)
    mock_client.is_configured = True
    service = TelegramService(client=mock_client)

    update_1 = {
        "update_id": 601,
        "message": {
            "message_id": 200,
            "chat": {"id": 8888, "type": "group", "title": "Dev Group"},
            "from": {"id": 222, "first_name": "Alice"},
            "text": "Role: Python Backend Developer\nCompany: Tech Corp\nLocation: Chennai\nApply: https://example.com/dev2",
        }
    }

    update_2_redelivery = {
        "update_id": 602,  # Different update_id
        "message": {
            "message_id": 200,  # Same message_id
            "chat": {"id": 8888, "type": "group", "title": "Dev Group"},  # Same chat_id
            "from": {"id": 222, "first_name": "Alice"},
            "text": "Role: Python Backend Developer\nCompany: Tech Corp\nLocation: Chennai\nApply: https://example.com/dev2",
        }
    }

    res1 = service.process_update(update_1)
    assert res1["status"] == "PROCESSED"

    res2 = service.process_update(update_2_redelivery)
    assert res2["status"] == "DUPLICATE_SKIPPED"
    assert res2["message_uid"] == "tg_8888_200"

    # Only 1 job lead created
    jobs = list_jobs()
    matching_jobs = [j for j in jobs if "Python Backend Developer" in j["title"]]
    assert len(matching_jobs) == 1


def test_telegram_worker_offset_rollback_on_batch_processing_error():
    """Verify that when a message fails processing mid-batch, offset does not advance past failing update."""
    mock_client = MagicMock(spec=TelegramClient)
    mock_client.is_configured = True

    # 3 updates in batch
    updates_batch = [
        {
            "update_id": 701,
            "message": {
                "message_id": 1,
                "chat": {"id": 11, "type": "channel", "title": "Channel A"},
                "text": "Announcement 1: Python opening in Pune https://example.com/1",
            }
        },
        {
            "update_id": 702,
            "message": {
                "message_id": 2,
                "chat": {"id": 11, "type": "channel", "title": "Channel A"},
                "text": "Announcement 2: Malformed payload trigger",
            }
        },
        {
            "update_id": 703,
            "message": {
                "message_id": 3,
                "chat": {"id": 11, "type": "channel", "title": "Channel A"},
                "text": "Announcement 3: Should not be processed in this cycle",
            }
        }
    ]
    mock_client.get_updates.return_value = updates_batch
    mock_client.get_me.return_value = {"id": 1, "username": "CareerOrbitJobAssistantBot"}

    # Set initial offset to 700
    set_telegram_offset(700)

    # Mock service: update 701 succeeds, update 702 raises RuntimeError
    mock_service = MagicMock(spec=TelegramService)

    def side_effect_process(u):
        if u["update_id"] == 701:
            return {"status": "PROCESSED"}
        elif u["update_id"] == 702:
            raise RuntimeError("Database write lock error during ingestion")
        return {"status": "PROCESSED"}

    mock_service.process_update.side_effect = side_effect_process

    worker = TelegramWorker(client=mock_client, service=mock_service)
    poll_res = worker.poll_once()

    # Offset must be 701 (advanced after 701 succeeded, but NOT after 702 failed)
    assert get_telegram_offset() == 701
    assert poll_res["status"] in ("PARTIAL_ERROR", "ERROR")
    assert "Database write lock error" in poll_res["error"]

    # On next poll, worker requests offset + 1 = 702, allowing automatic retry of 702!
    next_offset = get_telegram_offset() + 1
    assert next_offset == 702


def test_telegram_message_classification_matrix():
    """Verify discrete classification into Job Leads, Community Resources, Commands, and Discarded Spam."""
    mock_client = MagicMock(spec=TelegramClient)
    mock_client.is_configured = True
    service = TelegramService(client=mock_client)

    # 1. Technical Job Lead
    u_job = {
        "update_id": 801,
        "message": {
            "message_id": 10,
            "chat": {"id": 123, "type": "channel", "title": "Tech Jobs"},
            "text": "Hiring: Junior Data Analyst @ FinTech Solutions. Location: Bengaluru. Skills: SQL, Power BI, Excel. Apply: https://example.com/apply",
        }
    }
    res_job = service.process_update(u_job)
    assert res_job["status"] == "PROCESSED"
    assert res_job["is_job_lead"] is True
    assert res_job["job_id"] is not None
    # Strictly UNVERIFIED
    created_job = get_job_by_id(res_job["job_id"])
    assert created_job["verification_status"] == "UNVERIFIED"

    # 2. Non-Job Technical Resource
    u_res = {
        "update_id": 802,
        "message": {
            "message_id": 11,
            "chat": {"id": 123, "type": "channel", "title": "Tech Jobs"},
            "text": "Check out this great cheat sheet on Advanced Pandas & NumPy Performance Optimization: https://example.com/pandas-guide",
        }
    }
    res_resource = service.process_update(u_res)
    assert res_resource["status"] == "PROCESSED"
    assert res_resource["is_job_lead"] is False
    assert res_resource["job_id"] is None

    # 3. Bot Command
    u_cmd = {
        "update_id": 803,
        "message": {
            "message_id": 12,
            "chat": {"id": 456, "type": "private"},
            "from": {"id": 789, "first_name": "Balaji"},
            "text": "/stats",
        }
    }
    res_cmd = service.process_update(u_cmd)
    assert res_cmd["status"] == "COMMAND_HANDLED"
    assert res_cmd["command"] == "/stats"
    mock_client.send_message.assert_called()

    # 4. Irrelevant Spam
    u_spam = {
        "update_id": 804,
        "message": {
            "message_id": 13,
            "chat": {"id": 123, "type": "channel", "title": "Tech Jobs"},
            "text": "Double your crypto in 24 hours! Guaranteed 500% returns join our private VIP telegram signal group now!",
        }
    }
    res_spam = service.process_update(u_spam)
    assert res_spam["status"] == "PROCESSED"
    inbox_spam = get_inbox_message_by_uid(res_spam["message_uid"])
    assert inbox_spam["status"] == "DISCARDED"
    assert inbox_spam["is_job_lead"] == 0


def test_telegram_forwarded_announcement_attribution():
    """Verify that forwarded messages extract original channel title and t.me link."""
    mock_client = MagicMock(spec=TelegramClient)
    mock_client.is_configured = True
    service = TelegramService(client=mock_client)

    update = {
        "update_id": 901,
        "message": {
            "message_id": 55,
            "chat": {"id": 999, "type": "private", "first_name": "Direct User"},
            "forward_origin": {
                "type": "channel",
                "chat": {
                    "id": -100123456789,
                    "title": "Freshers Job Broadcast",
                    "username": "FreshersBroadcastIndia"
                },
                "message_id": 420
            },
            "text": "Urgent Requirement: Graduate Trainee Engineer at Tech Mahindra. Location: Chennai. Apply: https://example.com/tm",
        }
    }

    res = service.process_update(update)
    assert res["status"] == "PROCESSED"
    inbox_item = get_inbox_message_by_uid(res["message_uid"])
    assert inbox_item is not None
    assert "Freshers Job Broadcast" in inbox_item["chat_title"]
    assert "Forwarded from Telegram channel: Freshers Job Broadcast (@FreshersBroadcastIndia) • Msg #420" in inbox_item["notes"]
    assert inbox_item["extracted_data"]["origin_link"] == "https://t.me/FreshersBroadcastIndia/420"
