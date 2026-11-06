"""Telegram Processing Service for CareerOrbit AI.
Orchestrates incoming message reception, command responses (/start, /help, /profile, /stats),
content classification, job parsing, deduplication, geographic filtering, and inbox persistence.
"""
from __future__ import annotations

import html
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from careerorbit.config.settings import SETTINGS
from careerorbit.config.profile import CANDIDATE_PROFILE
from careerorbit.database.db import (
    save_inbox_message, get_inbox_message_by_uid, list_inbox_messages,
    get_inbox_stats, save_job, get_job_by_uid, get_job_stats, record_community_source
)
from careerorbit.discovery.community_parser import CommunityJobParser
from careerorbit.matcher.scorer import JobScorer
from careerorbit.models.schemas import Job, VerificationStatus
from careerorbit.telegram.client import TelegramClient, TelegramAPIError
from careerorbit.telegram.classifier import TelegramContentClassifier

logger = logging.getLogger("careerorbit.telegram.service")


class TelegramService:
    """Core intelligence engine connecting Telegram updates to CareerOrbit AI."""

    def __init__(self, client: Optional[TelegramClient] = None):
        self.client = client or TelegramClient()
        self.classifier = TelegramContentClassifier
        self.scorer = JobScorer()

    # ----------------- Update Dispatcher -----------------

    def process_update(self, update: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch a single Telegram update dict to appropriate handlers."""
        update_id = update.get("update_id", 0)

        # 1. Handle bot membership changes (my_chat_member)
        if "my_chat_member" in update:
            return self._handle_my_chat_member(update["my_chat_member"], update_id)

        # Telegram delivers message, edited_message, channel_post, or edited_channel_post
        msg = (
            update.get("message")
            or update.get("channel_post")
            or update.get("edited_message")
            or update.get("edited_channel_post")
        )
        if not msg:
            return {"status": "IGNORED", "reason": "No supported message content", "update_id": update_id}

        chat = msg.get("chat") or {}
        chat_id = chat.get("id")
        chat_type = chat.get("type", "private")
        chat_title = chat.get("title") or chat.get("username") or ""

        message_id = msg.get("message_id", 0)
        from_user = msg.get("from") or {}
        sender_id = from_user.get("id", "")
        sender_first = from_user.get("first_name", "")
        sender_last = from_user.get("last_name", "")
        sender_name = f"{sender_first} {sender_last}".strip() or (chat_title if chat_type == "channel" else "Unknown")
        sender_username = from_user.get("username", "")

        # Check for forwarded content (Telegram Bot API 7.0+ forward_origin or legacy forward_from_chat)
        fwd_origin = msg.get("forward_origin") or {}
        fwd_from_chat = msg.get("forward_from_chat") or {}
        is_forwarded = bool(fwd_origin or fwd_from_chat or msg.get("forward_date"))

        origin_channel_id = None
        origin_channel_title = ""
        origin_channel_username = ""
        origin_message_id = None
        origin_link = ""

        if fwd_origin.get("type") == "channel" and fwd_origin.get("chat"):
            fc = fwd_origin["chat"]
            origin_channel_id = str(fc.get("id"))
            origin_channel_title = fc.get("title") or fc.get("username") or origin_channel_id
            origin_channel_username = fc.get("username", "")
            origin_message_id = fwd_origin.get("message_id")
        elif fwd_from_chat:
            origin_channel_id = str(fwd_from_chat.get("id"))
            origin_channel_title = fwd_from_chat.get("title") or fwd_from_chat.get("username") or origin_channel_id
            origin_channel_username = fwd_from_chat.get("username", "")
            origin_message_id = msg.get("forward_from_message_id")

        if origin_channel_username and origin_message_id:
            origin_link = f"https://t.me/{origin_channel_username}/{origin_message_id}"
        elif chat.get("username") and message_id and chat_type == "channel":
            origin_link = f"https://t.me/{chat.get('username')}/{message_id}"

        # Extract text or caption
        raw_text = msg.get("text") or msg.get("caption") or ""
        media_type = "text"
        media_file_id = ""

        if msg.get("document"):
            media_type = "document"
            media_file_id = msg["document"].get("file_id", "")
            if not raw_text:
                raw_text = f"[Document Attachment: {msg['document'].get('file_name', 'Unnamed')}]"
        elif msg.get("photo"):
            media_type = "photo"
            media_file_id = msg["photo"][-1].get("file_id", "")
            if not raw_text:
                raw_text = "[Photo Attachment]"

        if not raw_text.strip():
            return {"status": "SKIPPED", "reason": "Empty message body", "update_id": update_id}

        # Classify message content
        classified = self.classifier.classify(raw_text, media_type=media_type)

        # Handle Bot Commands (only in non-forwarded direct/group messages)
        if classified.get("is_command") and not is_forwarded:
            cmd_result = self._handle_command(classified["command"], chat_id, message_id, raw_text)
            return {
                "status": "COMMAND_HANDLED",
                "command": classified["command"],
                "chat_id": chat_id,
                "update_id": update_id,
                "reply": cmd_result
            }

        # Determine unique message UID and deduplication key
        if origin_channel_id and origin_message_id:
            message_uid = f"tg_fwd_{origin_channel_id}_{origin_message_id}"
        elif origin_channel_id:
            message_uid = f"tg_fwd_{origin_channel_id}_{message_id}"
        else:
            message_uid = f"tg_{chat_id}_{message_id}"

        existing_inbox = get_inbox_message_by_uid(message_uid)
        if existing_inbox:
            logger.info("Duplicate Telegram message %s already present in Unified Inbox (#%s)", message_uid, existing_inbox["id"])
            return {
                "status": "DUPLICATE_SKIPPED",
                "message_uid": message_uid,
                "inbox_id": existing_inbox["id"],
                "classification": existing_inbox["classification"],
                "is_job_lead": bool(existing_inbox["is_job_lead"]),
                "job_id": existing_inbox.get("job_id"),
                "update_id": update_id
            }

        received_at = datetime.now(timezone.utc).isoformat()

        job_id: Optional[int] = None
        extracted_info: Dict[str, Any] = {
            "media_type": media_type,
            "media_file_id": media_file_id,
            "tech_tags": classified.get("tech_tags", []),
            "candidate_matches": classified.get("candidate_matches", []),
            "urls": classified.get("urls", []),
            "origin_link": origin_link,
            "is_forwarded": is_forwarded,
            "origin_channel_title": origin_channel_title,
            "origin_channel_username": origin_channel_username,
            "origin_message_id": origin_message_id,
        }

        # Determine effective source channel name for parsing and display
        effective_source_name = origin_channel_title or chat_title or (f"Telegram DM ({sender_name})" if chat_type == "private" else f"Telegram ({chat_id})")

        # If detected as a Job Lead, parse structured attributes
        if classified.get("is_job_lead"):
            parsed_job = CommunityJobParser.parse_announcement(
                raw_text,
                source_channel=f"Telegram ({effective_source_name})"
            )
            extracted_info.update({
                "job_parsed": parsed_job,
                "employer": parsed_job["employer"],
                "title": parsed_job["title"],
                "location": parsed_job["location"],
                "application_url": parsed_job["application_url"],
                "missing_link": parsed_job["missing_link"],
                "is_duplicate": parsed_job["is_duplicate"],
            })

            # Ingest job lead into database as strictly UNVERIFIED
            effective_chat_id = origin_channel_id or chat_id
            effective_msg_id = origin_message_id or message_id
            job_id = self._ingest_job_lead(parsed_job, raw_text, effective_chat_id, effective_source_name, effective_msg_id)

        # Provenance note formulation
        if is_forwarded and origin_channel_title:
            prov_note = f"Forwarded from Telegram channel: {origin_channel_title}"
            if origin_channel_username:
                prov_note += f" (@{origin_channel_username})"
            if origin_message_id:
                prov_note += f" • Msg #{origin_message_id}"
        elif chat_type == "channel":
            prov_note = f"Direct post from Telegram channel: {chat_title} • Msg #{message_id}"
        elif chat_type in ("group", "supergroup"):
            prov_note = f"Telegram group announcement: {chat_title} • Msg #{message_id} • From: {sender_name}"
        else:
            prov_note = f"Direct submission to @CareerOrbitJobAssistantBot • From: {sender_name}"

        # Save to Unified Inbox table
        inbox_status = "NEW"
        if classified["classification"] == self.classifier.CAT_IRRELEVANT:
            inbox_status = "DISCARDED"

        inbox_payload = {
            "message_uid": message_uid,
            "channel": "telegram",
            "chat_id": str(origin_channel_id or chat_id),
            "chat_title": effective_source_name,
            "chat_type": "channel" if (is_forwarded and origin_channel_id) else chat_type,
            "message_id": int(origin_message_id or message_id),
            "sender_id": str(sender_id),
            "sender_name": sender_name,
            "sender_username": sender_username,
            "raw_text": raw_text,
            "classification": classified["classification"],
            "category_group": classified["category_group"],
            "is_job_lead": 1 if classified.get("is_job_lead") else 0,
            "job_id": job_id,
            "extracted_data": extracted_info,
            "media_type": media_type,
            "media_file_id": media_file_id,
            "received_at": received_at,
            "status": inbox_status,
            "notes": prov_note
        }
        inbox_row_id = save_inbox_message(inbox_payload)

        # Track community source provenance in SQLite
        if origin_channel_id and is_forwarded:
            record_community_source(
                chat_id=str(origin_channel_id),
                source_name=f"Telegram: {origin_channel_title}",
                source_type="telegram_channel",
                status="ACTIVE",
                chat_username=origin_channel_username,
                is_public=bool(origin_channel_username),
                is_member=False,
                can_receive_messages=True,
                bot_role="forwarded",
                setup_instructions="Messages are ingested via manual forwarding to @CareerOrbitJobAssistantBot.",
                diagnosis=f"Channel active via forwarded announcements (latest: msg #{origin_message_id or message_id}).",
                last_message_at=received_at,
                last_message_excerpt=raw_text[:120],
                increment_messages=True
            )
        elif chat_type == "channel":
            record_community_source(
                chat_id=str(chat_id),
                source_name=f"Telegram: {chat_title}",
                source_type="telegram_channel",
                status="ACTIVE",
                chat_username=chat.get("username", ""),
                is_public=bool(chat.get("username")),
                is_member=True,
                can_receive_messages=True,
                bot_role="administrator",
                setup_instructions="Channel ingestion is active and verified.",
                diagnosis="Bot is an Administrator in this channel. Channel announcements will be ingested into Unified Inbox.",
                last_message_at=received_at,
                last_message_excerpt=raw_text[:120],
                increment_messages=True
            )
        elif chat_type in ("group", "supergroup"):
            record_community_source(
                chat_id=str(chat_id),
                source_name=f"Telegram: {chat_title}",
                source_type="telegram_group",
                status="ACTIVE",
                chat_username=chat.get("username", ""),
                is_public=bool(chat.get("username")),
                is_member=True,
                can_receive_messages=True,
                bot_role="member",
                setup_instructions="Group ingestion active.",
                diagnosis="Messages received from this group.",
                last_message_at=received_at,
                last_message_excerpt=raw_text[:120],
                increment_messages=True
            )
        else:
            record_community_source(
                chat_id=str(chat_id),
                source_name=f"Telegram DM: {sender_name}",
                source_type="telegram_dm",
                status="ACTIVE",
                is_public=False,
                is_member=True,
                can_receive_messages=True,
                bot_role="user",
                setup_instructions="Direct user message to bot.",
                diagnosis="Direct submissions are active.",
                last_message_at=received_at,
                last_message_excerpt=raw_text[:120],
                increment_messages=True
            )

        # In private chats, acknowledge user submissions with clean feedback
        if chat_type == "private" and self.client.is_configured:
            self._send_acknowledgment(chat_id, message_id, classified, extracted_info, job_id, is_forwarded, origin_channel_title)

        return {
            "status": "PROCESSED",
            "inbox_id": inbox_row_id,
            "message_uid": message_uid,
            "classification": classified["classification"],
            "is_job_lead": bool(classified.get("is_job_lead")),
            "job_id": job_id,
            "update_id": update_id
        }

    def _handle_my_chat_member(self, mcm: Dict[str, Any], update_id: int) -> Dict[str, Any]:
        """Handle automatic bot membership and administrator rights updates."""
        chat = mcm.get("chat") or {}
        chat_id = str(chat.get("id"))
        chat_title = chat.get("title") or chat.get("username") or chat_id
        chat_type = chat.get("type", "channel")
        chat_username = chat.get("username", "")
        new_member = mcm.get("new_chat_member") or {}
        bot_status = new_member.get("status", "unknown")

        is_admin = bot_status in ("administrator", "creator")
        is_member = bot_status in ("member", "administrator", "creator")

        bot_uname = SETTINGS.TELEGRAM_BOT_USERNAME or "CareerOrbitJobAssistantBot"

        if chat_type == "channel":
            can_recv = is_admin
            status = "ACTIVE" if is_admin else "PERMISSION_REQUIRED"
            diagnosis = "Bot is an Administrator in this channel. Channel announcements will be ingested into Unified Inbox." if is_admin else "Bot is present as a subscriber, NOT an Administrator. Promotion to Admin is required to ingest channel posts."
            setup_instructions = "Channel ingestion is active and verified." if is_admin else f"Open Channel Settings -> Administrators -> Add Administrator -> Search @{bot_uname} -> Grant Administrator rights."
        else:
            can_recv = is_admin
            status = "ACTIVE" if is_admin else "PRIVACY_RESTRICTED"
            diagnosis = "Bot is an Administrator in this group. All messages will be ingested." if is_admin else "Bot is a standard member in this group. Due to Telegram Group Privacy Mode, it only receives direct commands unless promoted to Admin or Privacy Mode is disabled in @BotFather."
            setup_instructions = "Group ingestion active." if is_admin else f"Promote bot to Administrator, or disable Privacy Mode in @BotFather (/setprivacy -> @{bot_uname} -> Disable)."

        if bot_status in ("left", "kicked"):
            status = "INACTIVE"
            can_recv = False
            is_member = False
            diagnosis = f"Bot was removed from this {chat_type}."
            setup_instructions = "Re-add bot to resume ingestion."

        source_type = "telegram_channel" if chat_type == "channel" else "telegram_group"
        source_id = record_community_source(
            chat_id=chat_id,
            source_name=f"Telegram: {chat_title}",
            source_type=source_type,
            status=status,
            chat_username=chat_username,
            is_public=bool(chat_username),
            is_member=is_member,
            can_receive_messages=can_recv,
            bot_role=bot_status,
            setup_instructions=setup_instructions,
            diagnosis=diagnosis,
            increment_messages=False
        )
        logger.info("Bot membership updated in %s (%s): status=%s, can_recv=%s", chat_title, chat_id, status, can_recv)
        return {
            "status": "MEMBERSHIP_UPDATED",
            "source_id": source_id,
            "chat_id": chat_id,
            "chat_title": chat_title,
            "bot_role": bot_status,
            "can_receive_messages": can_recv,
            "update_id": update_id
        }

    # ----------------- Command Handlers -----------------

    def _handle_command(self, command: str, chat_id: Any, message_id: int, full_text: str) -> str:
        """Process official bot commands (/start, /help, /profile, /stats)."""
        cmd = command.lower().split("@")[0]  # Strip bot handle if sent in group e.g. /start@CareerOrbitJobAssistantBot

        if cmd == "/start":
            reply_text = (
                "👋 <b>Welcome to CareerOrbit AI Assistant!</b>\n"
                "I am your automated intelligence bot (<code>@CareerOrbitJobAssistantBot</code>), "
                "supporting early-career job discovery, community intelligence, and interview preparation.\n\n"
                "🎯 <b>What I do:</b>\n"
                "• <b>Classify Messages:</b> Forward tech vacancies, interview questions, leetcode solutions, "
                "or study materials here.\n"
                "• <b>Filter Indian Tech Jobs:</b> Prioritizing Bengaluru, Chennai, Coimbatore, Hyderabad, and India Remote.\n"
                "• <b>Unified Inbox:</b> Categorizes resources into your CareerOrbit AI dashboard.\n"
                "• <b>Integrity-First Verification:</b> Jobs are logged as <code>UNVERIFIED</code> until verified directly.\n\n"
                "📋 <b>Available Commands:</b>\n"
                "/help — View formatting guide & channel setup\n"
                "/profile — Candidate profile & target roles\n"
                "/stats — Real-time database & discovery counts\n\n"
                "<i>Paste any job announcement or interview prep resource to begin!</i>"
            )

        elif cmd == "/help":
            reply_text = (
                "📖 <b>CareerOrbit AI — Bot Guide & Commands</b>\n\n"
                "<b>1. How to Submit a Job Vacancy:</b>\n"
                "Paste or forward unformatted text containing role, company, location, and apply link:\n"
                "<code>Company: InMobi\n"
                "Role: Junior Data Analyst\n"
                "Location: Bengaluru / Hybrid\n"
                "Batch: 2024 / 2025\n"
                "Apply: https://jobs.lever.co/inmobi/...</code>\n\n"
                "<b>2. Resource Classification:</b>\n"
                "The bot automatically categorizes your incoming messages into:\n"
                "• Data Analyst / BI Opportunities\n"
                "• Data Science / AI / ML Vacancies\n"
                "• Software Engineering Jobs\n"
                "• Data Engineering Jobs\n"
                "• Interview Preparation (STAR questions, system design)\n"
                "• Coding Practice (DSA, LeetCode)\n"
                "• Technical Learning Materials & Roadmaps\n"
                "• Certifications & Free Courses\n\n"
                "<b>3. Adding the Bot to Channels & Groups:</b>\n"
                "• <b>Channels:</b> Add the bot as an <b>Administrator</b> with <i>Post Messages</i> permission so it can receive channel posts.\n"
                "• <b>Groups:</b> By default, Telegram privacy mode is active. Disable privacy mode in @BotFather (<code>/setprivacy -> Disable</code>) or promote bot to Admin to capture all community alerts.\n"
                "• <b>Historical Messages:</b> Telegram Bot API only delivers messages received <i>after</i> the bot joins."
            )

        elif cmd == "/profile":
            p = CANDIDATE_PROFILE.get("personal", {})
            e = CANDIDATE_PROFILE.get("education", {})
            emp = CANDIDATE_PROFILE.get("employment", [])
            recent_role = emp[0].get("role", "Associate Software Engineer") if emp else "Associate Software Engineer"
            recent_comp = emp[0].get("employer", "") if emp else ""

            reply_text = (
                f"👤 <b>Active Candidate Profile:</b>\n"
                f"• <b>Candidate:</b> {p.get('full_name') or 'Candidate'}\n"
                f"• <b>Degree:</b> {e.get('degree', 'B.E.')} in {e.get('field_of_study', 'ECE')} ({e.get('graduation_year', '2025')})\n"
                f"• <b>Recent Experience:</b> {recent_role} at {recent_comp}\n"
                f"• <b>Core Stack:</b> Python, SQL, Power BI, DAX, FastAPI, TensorFlow/Keras, OpenCV\n"
                f"• <b>Priority 1 Locations:</b> Bengaluru, Chennai, Coimbatore, Hyderabad, India Remote\n"
                f"• <b>Priority 2 Locations:</b> Cuddalore, Puducherry, Kochi, Mysuru\n"
                f"• <b>Priority 3 Locations:</b> Pune, Mumbai, Delhi NCR, Noida, Gurugram"
            )

        elif cmd == "/stats":
            db_stats = get_job_stats()
            inbox_stats = get_inbox_stats()
            reply_text = (
                "📊 <b>CareerOrbit AI Live Metrics:</b>\n\n"
                f"💼 <b>Active Job Leads:</b> {db_stats.get('total_jobs', 0)}\n"
                f"✅ <b>Verified Open:</b> {db_stats.get('verified_open', 0)}\n"
                f"🔍 <b>Unverified / Pending Check:</b> {db_stats.get('unverified_jobs', 0)}\n"
                f"🎓 <b>Fresher / 0-2 Yrs Opportunities:</b> {db_stats.get('fresher_opportunities', 0)}\n"
                f"🚀 <b>Off-Campus Recruitment Drives:</b> {db_stats.get('off_campus_drives', 0)}\n\n"
                f"📥 <b>Unified Inbox Items:</b> {inbox_stats.get('total', 0)}\n"
                f"🔔 <b>New / Unreviewed:</b> {inbox_stats.get('new', 0)}\n"
                f"🎯 <b>Community Job Leads:</b> {inbox_stats.get('job_leads', 0)}"
            )

        else:
            reply_text = (
                f"❓ Unknown command: <code>{html.escape(cmd)}</code>\n"
                "Type /help to see all supported instructions."
            )

        if self.client.is_configured:
            try:
                self.client.send_message(chat_id=chat_id, text=reply_text, parse_mode="HTML", reply_to_message_id=message_id)
            except Exception as exc:
                logger.warning("Failed to send command response for %s: %s", cmd, exc)

        return reply_text

    # ----------------- Job Ingestion & Verification Enforcement -----------------

    def _ingest_job_lead(
        self,
        parsed_job: Dict[str, Any],
        raw_text: str,
        chat_id: Any,
        chat_title: str,
        message_id: int
    ) -> Optional[int]:
        """Ingest parsed job lead strictly as UNVERIFIED with complete provenance."""
        # If identical job UID already exists, return existing job ID without overwriting
        job_uid = parsed_job.get("job_uid")
        existing = get_job_by_uid(job_uid)
        if existing:
            return existing["id"]

        title = parsed_job.get("title") or "Early-Career IT Vacancy"
        employer = parsed_job.get("employer") or "Community Employer"
        location = parsed_job.get("location") or "India / Remote"
        app_url = parsed_job.get("application_url") or ""

        # Score alignment against candidate profile
        score_res = self.scorer.score_job({
            "title": title,
            "description": raw_text,
            "location": location,
            "work_arrangement": "Hybrid",
            "salary": "Not Disclosed",
            "posting_date": None,
            "posting_date_confidence": "UNKNOWN",
            "verification_status": "UNVERIFIED"
        })

        source_label = f"Telegram: @CareerOrbitJobAssistantBot ({chat_title or chat_id})"
        verification_source_label = f"Telegram msg #{message_id} in {chat_title or chat_id}"

        # Strict Requirement 9: NEVER label a job as verified unless its application
        # link and availability have actually been checked.
        job_obj = Job(
            job_uid=job_uid,
            employer=employer,
            title=title,
            normalized_title=title.lower(),
            job_id_or_req="",
            priority_category=parsed_job["priority_category"],
            priority_label=parsed_job["priority_label"],
            location=location,
            work_arrangement="Hybrid",
            employment_type="Full-time",
            salary="Not Disclosed",
            deadline=parsed_job.get("deadline"),
            official_url=app_url,
            official_listing_url=app_url,
            application_url=app_url,
            discovery_url=app_url,
            canonical_url=app_url,
            discovery_source=source_label,
            verification_source=verification_source_label,
            verification_status=VerificationStatus.UNVERIFIED,
            verification_notes="Imported via Telegram bot. Application URL and active vacancy require independent verification.",
            match_score=score_res["match_score"],
            match_tier=score_res["match_tier"],
            score_breakdown=score_res["score_breakdown"],
            required_skills=score_res["supported_skills"] + score_res["missing_skills"],
            supported_skills=score_res["supported_skills"],
            missing_skills=score_res["missing_skills"],
            learnable_skills=score_res["learnable_skills"],
            disqualifiers=score_res["disqualifiers"],
            evidence_notes="Community lead requires verification before creating application package.",
            description=raw_text,
            is_fresher=parsed_job["is_fresher"],
            is_off_campus=parsed_job["is_off_campus"],
            is_internship=parsed_job["is_internship"],
            is_walkin=parsed_job["is_walkin"],
        )

        job_id = save_job(job_obj)
        logger.info("Saved community job #%s (%s at %s) as UNVERIFIED from Telegram", job_id, title, employer)
        return job_id

    # ----------------- User Acknowledgments -----------------

    def _send_acknowledgment(
        self,
        chat_id: Any,
        message_id: int,
        classified: Dict[str, Any],
        extracted_info: Dict[str, Any],
        job_id: Optional[int],
        is_forwarded: bool = False,
        origin_channel_title: str = ""
    ) -> None:
        """Send a formatted confirmation reply to the sender in 1-on-1 chats."""
        cat = classified.get("classification", "Career Resource")

        if classified.get("is_job_lead"):
            jp = extracted_info.get("job_parsed", {})
            title = jp.get("title", "Job Lead")
            emp = jp.get("employer", "Employer")
            loc = jp.get("location", "India")
            tier = jp.get("priority_label", "Target Role")
            app_url = jp.get("application_url")

            reply = (
                f"💼 <b>Job Lead Detected & Ingested!</b>\n\n"
                f"• <b>Role:</b> {html.escape(title)}\n"
                f"• <b>Company:</b> {html.escape(emp)}\n"
                f"• <b>Location:</b> {html.escape(loc)}\n"
            )
            if is_forwarded and origin_channel_title:
                reply += f"• <b>Source:</b> Forwarded from <b>{html.escape(origin_channel_title)}</b>\n"
            reply += (
                f"• <b>Track:</b> {html.escape(cat)}\n"
                f"• <b>Category:</b> {html.escape(tier)}\n"
                f"• <b>Status:</b> <code>UNVERIFIED</code> (Queued for official verification)\n"
            )
            if app_url:
                reply += f"• <b>Link:</b> {html.escape(app_url)}\n"
            else:
                reply += "⚠️ <i>Note: No direct application URL was detected in the text.</i>\n"

            reply += f"\n<i>Saved as Lead #{job_id} in your CareerOrbit AI Dashboard.</i>"

        elif cat != self.classifier.CAT_IRRELEVANT:
            reply = (
                f"📥 <b>Resource Captured to Unified Inbox!</b>\n\n"
                f"• <b>Category:</b> <code>{html.escape(cat)}</code>\n"
            )
            if is_forwarded and origin_channel_title:
                reply += f"• <b>Source:</b> Forwarded from <b>{html.escape(origin_channel_title)}</b>\n"
            tags = extracted_info.get("tech_tags", [])
            if tags:
                reply += f"• <b>Topics:</b> {', '.join(html.escape(t) for t in tags)}\n"
            reply += "\n<i>Available in your Unified Inbox on the CareerOrbit AI Dashboard.</i>"
        else:
            reply = "ℹ️ <i>Message received and logged as unclassified/irrelevant.</i>"

        try:
            self.client.send_message(chat_id=chat_id, text=reply, parse_mode="HTML", reply_to_message_id=message_id)
        except Exception as exc:
            logger.debug("Could not send acknowledgment to chat %s: %s", chat_id, exc)
