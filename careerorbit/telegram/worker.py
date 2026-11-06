"""Background Polling Worker for Telegram Bot API.
Runs a long-polling thread that ingests updates from @CareerOrbitJobAssistantBot,
tracks offset state in SQLite, and handles network backoffs gracefully.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from careerorbit.config.settings import SETTINGS
from careerorbit.database.db import (
    get_telegram_offset, set_telegram_offset,
    set_telegram_poll_metadata, get_telegram_poll_metadata
)
from careerorbit.telegram.client import TelegramClient, TelegramAPIError
from careerorbit.telegram.service import TelegramService

logger = logging.getLogger("careerorbit.telegram.worker")


class TelegramWorker:
    """Daemon thread for pulling Telegram Bot API updates."""

    def __init__(
        self,
        client: Optional[TelegramClient] = None,
        service: Optional[TelegramService] = None,
        poll_interval: Optional[int] = None
    ):
        self.client = client or TelegramClient()
        self.service = service or TelegramService(client=self.client)
        self.poll_interval = poll_interval or SETTINGS.TELEGRAM_POLL_INTERVAL

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.last_poll_time: Optional[str] = None
        self.last_poll_status: str = "IDLE"
        self.last_error: Optional[str] = None
        self.total_updates_processed: int = 0
        self.bot_info: Optional[Dict[str, Any]] = None
        self.recent_errors: List[Dict[str, Any]] = []
        self.last_sync_metrics: Dict[str, Any] = {
            "updates_fetched": 0,
            "messages_stored": 0,
            "duplicates_skipped": 0,
            "commands_handled": 0,
            "membership_updated": 0,
            "rejected_count": 0,
            "rejected_reasons": {},
            "timestamp": None,
            "worker_running": False
        }

    @property
    def is_running(self) -> bool:
        """True if the polling worker thread is active."""
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> bool:
        """Start background polling thread if bot token is configured."""
        if not self.client.is_configured:
            logger.info("Telegram worker not started: TELEGRAM_BOT_TOKEN is not configured.")
            self.last_poll_status = "NOT_CONFIGURED"
            return False

        if self.is_running:
            logger.warning("Telegram worker is already running.")
            return True

        # Test credentials and retrieve bot information
        try:
            self.bot_info = self.client.get_me()
            logger.info("Connected to Telegram Bot: @%s (ID: %s)", self.bot_info.get("username"), self.bot_info.get("id"))
        except Exception as exc:
            self.last_error = f"Authentication check failed: {exc}"
            self.last_poll_status = "AUTH_FAILED"
            logger.error("Failed to connect to Telegram Bot: %s", self.last_error)
            return False

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="CareerOrbit-TelegramWorker", daemon=True)
        self._thread.start()
        self.last_poll_status = "RUNNING"
        logger.info("Telegram worker polling thread started.")
        return True

    def stop(self, timeout: float = 5.0) -> None:
        """Signal thread to stop and wait for completion."""
        if not self.is_running:
            return
        logger.info("Stopping Telegram worker...")
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=timeout)
        self.last_poll_status = "STOPPED"
        logger.info("Telegram worker stopped.")

    def poll_once(self) -> Dict[str, Any]:
        """Perform a single immediate poll cycle for updates. Safe for manual sync or testing."""
        if not self.client.is_configured:
            return {"status": "NOT_CONFIGURED", "processed_count": 0, "message": "Bot token not configured."}

        # Lazy cache bot info if not yet retrieved
        if self.bot_info is None:
            try:
                self.bot_info = self.client.get_me()
            except Exception as e:
                logger.debug("Could not fetch bot details in poll_once: %s", e)

        try:
            offset = get_telegram_offset()
            fetch_offset = (offset + 1) if offset > 0 else None
            
            try:
                updates = self.client.get_updates(offset=fetch_offset, timeout=2, limit=50)
            except TelegramAPIError as api_err:
                # A polling/webhook conflict must not silently mutate external configuration.
                if api_err.error_code == 409 or "webhook is active" in str(api_err).lower():
                    self.last_error = (
                        "Telegram reports an active webhook. Polling was not started and the webhook "
                        "was left unchanged; review the configured delivery mode before switching."
                    )
                    self.last_poll_status = "WEBHOOK_CONFLICT"
                    self.last_poll_time = datetime.now(timezone.utc).isoformat()
                    self.recent_errors.append({
                        "timestamp": self.last_poll_time,
                        "error": self.last_error,
                    })
                    if len(self.recent_errors) > 10:
                        self.recent_errors.pop(0)
                    logger.warning("Telegram polling conflict: active webhook left unchanged.")
                    try:
                        set_telegram_poll_metadata(
                            self.last_poll_status,
                            self.last_poll_time,
                            processed_count=0,
                        )
                    except Exception as meta_e:
                        logger.debug("Could not persist poll metadata: %s", meta_e)
                    return {
                        "status": self.last_poll_status,
                        "error": self.last_error,
                        "processed_count": 0,
                        "webhook_changed": False,
                    }
                else:
                    raise

            updates_fetched = len(updates)
            messages_stored = 0
            duplicates_skipped = 0
            commands_handled = 0
            membership_updated = 0
            rejected_count = 0
            rejected_reasons: Dict[str, int] = {}
            encountered_error = None

            for u in updates:
                try:
                    res = self.service.process_update(u)
                    up_id = u.get("update_id", 0)
                    if up_id:
                        set_telegram_offset(up_id)
                    st = res.get("status")
                    if st == "PROCESSED":
                        messages_stored += 1
                    elif st == "COMMAND_HANDLED":
                        commands_handled += 1
                    elif st == "MEMBERSHIP_UPDATED":
                        membership_updated += 1
                    elif st == "DUPLICATE_SKIPPED":
                        duplicates_skipped += 1
                    elif st in ("IGNORED", "SKIPPED"):
                        rejected_count += 1
                        r_reason = res.get("reason", "unsupported_content")
                        rejected_reasons[r_reason] = rejected_reasons.get(r_reason, 0) + 1
                    else:
                        duplicates_skipped += 1
                except Exception as proc_exc:
                    logger.error("Error processing update %s: %s", u.get("update_id"), proc_exc, exc_info=True)
                    encountered_error = f"Update {u.get('update_id')} error: {proc_exc}"
                    # Do not advance offset past the failing update; stop batch to allow retry
                    break

            processed_total = messages_stored + commands_handled + membership_updated
            self.total_updates_processed += processed_total
            self.last_poll_time = datetime.now(timezone.utc).isoformat()

            self.last_sync_metrics = {
                "updates_fetched": updates_fetched,
                "messages_stored": messages_stored,
                "duplicates_skipped": duplicates_skipped,
                "commands_handled": commands_handled,
                "membership_updated": membership_updated,
                "rejected_count": rejected_count,
                "rejected_reasons": rejected_reasons,
                "timestamp": self.last_poll_time,
                "worker_running": self.is_running
            }

            if encountered_error:
                self.last_error = encountered_error
                self.last_poll_status = "PARTIAL_ERROR" if processed_total > 0 else "ERROR"
            else:
                self.last_poll_status = "SUCCESS"
                self.last_error = None
            try:
                set_telegram_poll_metadata(self.last_poll_status, self.last_poll_time, processed_count=processed_total)
            except Exception as meta_e:
                logger.debug("Could not persist poll metadata: %s", meta_e)
            return {
                "status": self.last_poll_status,
                "error": self.last_error,
                "received_count": updates_fetched,
                "processed_count": messages_stored,
                "duplicates_skipped": duplicates_skipped,
                "commands_handled": commands_handled,
                "membership_updated": membership_updated,
                "rejected_count": rejected_count,
                "rejected_reasons": rejected_reasons,
                "timestamp": self.last_poll_time,
                "metrics": self.last_sync_metrics
            }

        except TelegramAPIError as exc:
            self.last_error = str(exc)
            self.last_poll_status = f"API_ERROR: {exc}"
            self.recent_errors.append({"timestamp": datetime.now(timezone.utc).isoformat(), "error": str(exc)})
            if len(self.recent_errors) > 10:
                self.recent_errors.pop(0)
            logger.warning("Telegram API error during poll: %s", exc)
            try:
                set_telegram_poll_metadata(self.last_poll_status, datetime.now(timezone.utc).isoformat(), processed_count=0)
            except Exception:
                pass
            return {"status": "ERROR", "error": str(exc), "processed_count": 0}
        except Exception as exc:
            self.last_error = str(exc)
            self.last_poll_status = f"ERROR: {exc}"
            self.recent_errors.append({"timestamp": datetime.now(timezone.utc).isoformat(), "error": str(exc)})
            if len(self.recent_errors) > 10:
                self.recent_errors.pop(0)
            logger.error("Unexpected error during poll: %s", exc, exc_info=True)
            try:
                set_telegram_poll_metadata(self.last_poll_status, datetime.now(timezone.utc).isoformat(), processed_count=0)
            except Exception:
                pass
            return {"status": "ERROR", "error": str(exc), "processed_count": 0}

    def _run_loop(self) -> None:
        """Internal daemon loop for continuous updates."""
        while not self._stop_event.is_set():
            try:
                res = self.poll_once()
                if res.get("status") == "WEBHOOK_CONFLICT":
                    # This is a persistent configuration conflict; stop instead of polling in a loop.
                    self.last_poll_status = "WEBHOOK_CONFLICT"
                    self._stop_event.set()
                    break
                if res.get("status") == "ERROR":
                    # Backoff on error
                    self._stop_event.wait(10.0)
                else:
                    self._stop_event.wait(float(self.poll_interval))
            except Exception as loop_exc:
                logger.error("Unhandled exception in Telegram worker loop: %s", loop_exc)
                self._stop_event.wait(10.0)

    def get_status(self) -> Dict[str, Any]:
        """Return diagnostic health and status dictionary."""
        # Retrieve bot details if configured and not yet fetched
        if self.bot_info is None and self.client.is_configured:
            try:
                self.bot_info = self.client.get_me()
            except Exception as exc:
                logger.debug("Could not fetch bot details in get_status: %s", exc)

        bot_username = self.bot_info.get("username") if self.bot_info else SETTINGS.TELEGRAM_BOT_USERNAME
        bot_id = self.bot_info.get("id") if self.bot_info else None

        # Fallback to persisted SQLite state across restarts
        meta = {}
        try:
            meta = get_telegram_poll_metadata()
        except Exception:
            pass

        last_poll_time = self.last_poll_time or meta.get("last_poll_time")
        last_poll_status = self.last_poll_status
        if last_poll_status == "IDLE" and meta.get("last_poll_status"):
            last_poll_status = meta["last_poll_status"]

        total_processed = max(self.total_updates_processed, meta.get("total_updates_processed", 0))

        # Retrieve last successfully ingested Telegram message
        last_msg = None
        try:
            from careerorbit.database.db import get_connection
            conn = get_connection()
            c = conn.cursor()
            c.execute("""
                SELECT id, message_uid, channel, chat_title, sender_name, raw_text, classification, received_at
                FROM inbox_messages
                WHERE channel = 'telegram'
                ORDER BY id DESC LIMIT 1
            """)
            r = c.fetchone()
            conn.close()
            if r:
                last_msg = {
                    "id": r["id"],
                    "message_uid": r["message_uid"],
                    "chat_title": r["chat_title"],
                    "sender_name": r["sender_name"],
                    "classification": r["classification"],
                    "received_at": r["received_at"],
                    "excerpt": (r["raw_text"] or "")[:120]
                }
        except Exception as e:
            logger.debug("Could not fetch last Telegram message: %s", e)

        # Retrieve configured Telegram channels and groups status
        channels_summary = {
            "total_configured": 0,
            "active_accessible": 0,
            "permissions_required": 0,
            "channel_ingestion_working": False,
            "channels": []
        }
        try:
            from careerorbit.database.db import list_community_sources
            sources = [s for s in list_community_sources() if s.get("source_type") in ("telegram_channel", "telegram_group", "telegram_dm", "telegram_chat_export")]
            channels_summary["total_configured"] = len(sources)
            for s in sources:
                st = s.get("status")
                can_recv = bool(s.get("can_receive_messages", 1 if st == "ACTIVE" else 0))
                if st == "ACTIVE" and can_recv:
                    channels_summary["active_accessible"] += 1
                elif st in ("PERMISSION_REQUIRED", "PRIVACY_RESTRICTED"):
                    channels_summary["permissions_required"] += 1
                channels_summary["channels"].append({
                    "id": s["id"],
                    "chat_id": s["chat_id"],
                    "source_name": s["source_name"],
                    "source_type": s["source_type"],
                    "status": st,
                    "is_public": bool(s.get("is_public")),
                    "is_member": bool(s.get("is_member", 1)),
                    "can_receive_messages": can_recv,
                    "bot_role": s.get("bot_role") or ("administrator" if st == "ACTIVE" else "member"),
                    "chat_username": s.get("chat_username", ""),
                    "messages_count": s.get("messages_count", 0),
                    "last_message_at": s.get("last_message_at") or s.get("last_ingestion_at"),
                    "last_message_excerpt": s.get("last_message_excerpt", ""),
                    "setup_instructions": s.get("setup_instructions", ""),
                    "diagnosis": s.get("diagnosis", ""),
                    "last_error": s.get("last_error", "")
                })
            channels_summary["channel_ingestion_working"] = bool(channels_summary["active_accessible"] > 0)
        except Exception as e:
            logger.debug("Could not summarize community channels: %s", e)

        bot_authenticated = bool(self.bot_info is not None and self.client.is_configured)

        # Update last_sync_metrics worker_running flag
        self.last_sync_metrics["worker_running"] = self.is_running

        return {
            "configured": self.client.is_configured,
            "bot_connected": bot_authenticated,
            "running": self.is_running,
            "worker_running": self.is_running,
            "bot_username": bot_username,
            "bot_id": bot_id,
            "last_poll_time": last_poll_time,
            "last_poll_status": last_poll_status,
            "last_error": self.last_error,
            "total_updates_processed": total_processed,
            "current_offset": get_telegram_offset(),
            "masked_token": self.client.masked_token,
            "registered_sources_count": channels_summary["total_configured"],
            "accessible_sources_count": channels_summary["active_accessible"],
            "channel_ingestion_working": channels_summary["channel_ingestion_working"],
            "last_sync_metrics": self.last_sync_metrics,
            "distinction_note": (
                "Bot Connected confirms that @CareerOrbitJobAssistantBot is authenticated with the Telegram Bot API. "
                "Channel Ingestion Working confirms that the bot is an Administrator with permissions in active community channels."
            ),
            "last_successfully_ingested_message": last_msg,
            "recent_errors": list(self.recent_errors),
            "channel_summary": channels_summary,
        }


TELEGRAM_WORKER = TelegramWorker()
