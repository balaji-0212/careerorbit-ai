"""Parser for User-Exported WhatsApp Chat Files (.txt).
Extracts timestamps, senders, text, links, and filters out system/personal messages.
Feeds extracted announcements and learning resources into the CareerOrbit intelligence pipeline.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from careerorbit.database.db import (
    save_inbox_message, get_inbox_message_by_uid, save_job,
    get_job_by_uid, record_community_source
)
from careerorbit.discovery.community_parser import CommunityJobParser
from careerorbit.matcher.scorer import JobScorer
from careerorbit.models.schemas import Job, VerificationStatus
from careerorbit.telegram.classifier import TelegramContentClassifier


class WhatsAppChatExportParser:
    """Parses text-exported WhatsApp chat logs."""

    # Matches Android: "12/10/24, 10:30 am - Sender: Message" or "12/10/2026, 14:15 - Sender: Message"
    RE_ANDROID = re.compile(
        r"^(\d{1,2}/\d{1,2}/\d{2,4}),?\s+(\d{1,2}:\d{2}(?::\d{2})?(?:\s*[apAP][mM])?)\s*-\s*([^:]+?):\s*(.*)$"
    )

    # Matches iOS: "[12/10/24, 10:30:15] Sender: Message" or "[12/10/2026, 10:30:15 AM] Sender: Message"
    RE_IOS = re.compile(
        r"^\[(\d{1,2}/\d{1,2}/\d{2,4}),?\s+(\d{1,2}:\d{2}(?::\d{2})?(?:\s*[apAP][mM])?)\]\s*([^:]+?):\s*(.*)$"
    )

    # System messages without a sender
    SYSTEM_PATTERNS = [
        r"messages and calls are end-to-end encrypted",
        r"joined using this group's invite link",
        r"changed the group description",
        r"changed the subject to",
        r"security code changed",
        r"<media omitted>",
        r"image omitted",
        r"video omitted",
        r"audio omitted",
        r"document omitted",
        r"sticker omitted",
        r"this message was deleted",
        r"you deleted this message",
        r"added you",
        r"left the group",
    ]

    # Non-career noise check
    PERSONAL_CHIT_CHAT = [
        r"^ok(?:ay)?$", r"^thanks?(?: you)?$", r"^good\s*(?:morning|evening|night|afternoon)$",
        r"^gm$", r"^gn$", r"^hi+$", r"^hello+$", r"^yes$", r"^no$", r"^done$",
        r"^call me$", r"^wait$", r"^k$", r"^cool$", r"^great$", r"^congrats?$",
        r"^happy birthday", r"^happy new year", r"^welcome",
    ]

    @classmethod
    def parse_text(cls, content: str, chat_title: str = "WhatsApp Export") -> Dict[str, Any]:
        """Parse exported WhatsApp chat content into structured messages with classification preview."""
        lines = content.splitlines()
        raw_messages: List[Dict[str, Any]] = []

        current_msg: Optional[Dict[str, Any]] = None

        for line_idx, line in enumerate(lines, start=1):
            line_str = line.strip()
            if not line_str:
                if current_msg:
                    current_msg["text"] += "\n"
                continue

            match_android = cls_match = cls.RE_ANDROID.match(line)
            if not match_android:
                cls_match = cls.RE_IOS.match(line)

            if cls_match:
                # Flush previous message
                if current_msg:
                    raw_messages.append(current_msg)

                date_part, time_part, sender, text = cls_match.groups()
                current_msg = {
                    "line_number": line_idx,
                    "date_str": date_part.strip(),
                    "time_str": time_part.strip(),
                    "sender": sender.strip(),
                    "text": text.strip(),
                }
            else:
                # Continuation line
                if current_msg:
                    current_msg["text"] += "\n" + line
                # Otherwise, line before any header; ignore

        if current_msg:
            raw_messages.append(current_msg)

        # Now filter and classify messages
        candidate_items: List[Dict[str, Any]] = []
        personal_skipped = 0
        total_parsed = len(raw_messages)
        job_leads_count = 0
        career_relevant_count = 0

        for m in raw_messages:
            raw_text = m["text"].strip()
            lower = raw_text.lower()

            # 1. System message check
            if any(re.search(pat, lower) for pat in cls.SYSTEM_PATTERNS):
                personal_skipped += 1
                continue

            # 2. Personal chit-chat check (if short and no URLs or tech words)
            urls = CommunityJobParser._extract_urls(raw_text)
            if len(raw_text) < 40 and not urls:
                if any(re.search(pat, lower) for pat in cls.PERSONAL_CHIT_CHAT):
                    personal_skipped += 1
                    continue

            # 3. Classify message content
            classified = TelegramContentClassifier.classify(raw_text)
            classification = classified["classification"]
            category_group = classified["category_group"]
            is_job = bool(classified.get("is_job_lead"))

            # If classified as irrelevant and short with no URLs, skip by default
            if classification == TelegramContentClassifier.CAT_IRRELEVANT and len(raw_text) < 50 and not urls:
                personal_skipped += 1
                continue

            # Build message UID for idempotency
            date_time_key = f"{m['date_str']}_{m['time_str']}_{m['sender']}"
            text_hash = hashlib.md5(raw_text.encode("utf-8")).hexdigest()[:8]
            safe_chat = re.sub(r"[^a-zA-Z0-9]+", "_", chat_title).strip("_") or "wa_export"
            message_uid = f"wa_{safe_chat}_{date_time_key}_{text_hash}"

            # Check duplicate against inbox
            existing_inbox = get_inbox_message_by_uid(message_uid)
            is_duplicate = bool(existing_inbox)

            # If Job Lead, parse structured details
            parsed_job = None
            if is_job:
                parsed_job = CommunityJobParser.parse_announcement(raw_text, source_channel=f"WhatsApp ({chat_title})")
                job_leads_count += 1
                if parsed_job.get("is_duplicate"):
                    is_duplicate = True

            career_relevant_count += 1

            candidate_items.append({
                "line_number": m["line_number"],
                "date_str": m["date_str"],
                "time_str": m["time_str"],
                "timestamp_raw": f"{m['date_str']} {m['time_str']}",
                "sender": m["sender"],
                "raw_text": raw_text,
                "urls": urls,
                "classification": classification,
                "category_group": category_group,
                "is_job_lead": is_job,
                "job_parsed": parsed_job,
                "candidate_matches": classified.get("candidate_matches", []),
                "tech_tags": classified.get("tech_tags", []),
                "message_uid": message_uid,
                "is_duplicate": is_duplicate,
            })

        return {
            "chat_title": chat_title,
            "total_lines": len(lines),
            "total_messages_parsed": total_parsed,
            "career_relevant_count": career_relevant_count,
            "personal_skipped_count": personal_skipped,
            "job_leads_count": job_leads_count,
            "items": candidate_items,
        }

    @classmethod
    def import_items(cls, items: List[Dict[str, Any]], chat_title: str = "WhatsApp Export", filename: str = "") -> Dict[str, Any]:
        """Commit previewed WhatsApp items into database tables."""
        imported_inbox = 0
        imported_jobs = 0
        skipped_duplicates = 0
        scorer = JobScorer()

        chat_id_slug = "wa_" + (re.sub(r"[^a-zA-Z0-9]+", "_", chat_title).lower().strip("_") or "export")

        for item in items:
            raw_text = str(item.get("raw_text") or "").strip()
            if not raw_text:
                continue

            message_uid = item.get("message_uid")
            if not message_uid:
                text_hash = hashlib.md5(raw_text.encode("utf-8")).hexdigest()[:8]
                message_uid = f"wa_{chat_id_slug}_{text_hash}"

            # Check if already exists in inbox
            existing = get_inbox_message_by_uid(message_uid)
            if existing and not item.get("allow_duplicate"):
                skipped_duplicates += 1
                continue

            is_job = bool(item.get("is_job_lead"))
            classification = item.get("classification") or "Other Career Resources"
            category_group = item.get("category_group") or "career"
            job_id: Optional[int] = None

            # If Job lead, parse and ingest into jobs table strictly as UNVERIFIED
            if is_job:
                pj = item.get("job_parsed") or CommunityJobParser.parse_announcement(
                    raw_text,
                    source_channel=f"WhatsApp ({chat_title})"
                )
                job_uid = pj.get("job_uid")
                existing_job = get_job_by_uid(job_uid)
                if existing_job:
                    job_id = existing_job["id"]
                else:
                    title = pj.get("title") or "Early-Career IT Vacancy"
                    employer = pj.get("employer") or "WhatsApp Community Employer"
                    location = pj.get("location") or "India / Remote"
                    app_url = pj.get("application_url") or ""

                    score_res = scorer.score_job({
                        "title": title,
                        "description": raw_text,
                        "location": location,
                        "work_arrangement": "Hybrid",
                        "salary": "Not Disclosed",
                        "posting_date": None,
                        "posting_date_confidence": "UNKNOWN",
                        "verification_status": "UNVERIFIED",
                    })

                    job_obj = Job(
                        job_uid=job_uid,
                        employer=employer,
                        title=title,
                        normalized_title=title.lower(),
                        job_id_or_req="",
                        priority_category=pj["priority_category"],
                        priority_label=pj["priority_label"],
                        location=location,
                        work_arrangement="Hybrid",
                        employment_type="Full-time",
                        salary="Not Disclosed",
                        deadline=pj.get("deadline"),
                        official_url=app_url,
                        official_listing_url=app_url,
                        application_url=app_url,
                        discovery_url=app_url,
                        canonical_url=app_url,
                        discovery_source=f"WhatsApp: {chat_title}",
                        verification_source=f"WhatsApp export ({chat_title})",
                        verification_status=VerificationStatus.UNVERIFIED,
                        verification_notes="Imported via WhatsApp chat export. Link and active vacancy require independent verification.",
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
                        is_fresher=pj.get("is_fresher", False),
                        is_off_campus=pj.get("is_off_campus", False),
                        is_internship=pj.get("is_internship", False),
                        is_walkin=pj.get("is_walkin", False),
                    )
                    job_id = save_job(job_obj)
                    imported_jobs += 1

            # Save to unified inbox
            extracted_info = {
                "urls": item.get("urls") or [],
                "tech_tags": item.get("tech_tags") or [],
                "candidate_matches": item.get("candidate_matches") or [],
                "source_format": "whatsapp_export",
                "export_filename": filename or chat_title,
                "timestamp_raw": item.get("timestamp_raw", ""),
                "line_number": item.get("line_number"),
            }
            if item.get("job_parsed"):
                extracted_info["job_parsed"] = item["job_parsed"]

            provenance_note = f"Imported from WhatsApp chat export: {chat_title}"
            if filename:
                provenance_note += f" (File: {filename})"

            inbox_payload = {
                "message_uid": message_uid,
                "channel": "whatsapp",
                "chat_id": chat_id_slug,
                "chat_title": chat_title,
                "chat_type": "group",
                "message_id": item.get("line_number", 0),
                "sender_id": "",
                "sender_name": item.get("sender", "WhatsApp User"),
                "sender_username": "",
                "raw_text": raw_text,
                "classification": classification,
                "category_group": category_group,
                "is_job_lead": 1 if is_job else 0,
                "job_id": job_id,
                "extracted_data": extracted_info,
                "media_type": "text",
                "media_file_id": "",
                "received_at": datetime.now(timezone.utc).isoformat(),
                "status": "NEW",
                "notes": provenance_note,
            }
            save_inbox_message(inbox_payload)
            imported_inbox += 1

        # Record or update community source registry
        if imported_inbox > 0:
            record_community_source(
                chat_id=chat_id_slug,
                source_name=f"WhatsApp Export: {chat_title}",
                source_type="whatsapp_chat_export",
                status="ACTIVE",
                increment_messages=True,
            )

        return {
            "status": "SUCCESS",
            "imported_inbox": imported_inbox,
            "imported_jobs": imported_jobs,
            "skipped_duplicates": skipped_duplicates,
            "chat_title": chat_title,
        }
