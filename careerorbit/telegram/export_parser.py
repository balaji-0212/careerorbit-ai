"""Telegram Desktop Chat Export Parser and Ingestion Engine.
Parses JSON and HTML chat exports from Telegram Desktop (Three dots -> Export chat history -> JSON/HTML).
Enforces SHA-256 cryptographic deduplication, UNVERIFIED status, and rich provenance tracking.
"""
from __future__ import annotations

import json
import re
import hashlib
import logging
from typing import Any, Dict, List, Optional, Union
from datetime import datetime, timezone
from pathlib import Path

from careerorbit.database.db import (
    save_inbox_message, get_inbox_message_by_uid, save_job, get_job_by_uid,
    record_community_source, get_connection
)
from careerorbit.discovery.community_parser import CommunityJobParser
from careerorbit.matcher.scorer import JobScorer
from careerorbit.models.schemas import Job, VerificationStatus
from careerorbit.telegram.classifier import TelegramContentClassifier

logger = logging.getLogger("careerorbit.telegram.export_parser")


def _flatten_telegram_json_text(text_val: Any) -> str:
    """Telegram JSON exports represent text as either a string or a list of mixed strings/dicts."""
    if text_val is None:
        return ""
    if isinstance(text_val, str):
        return text_val
    if isinstance(text_val, (int, float)):
        return str(text_val)
    if isinstance(text_val, list):
        parts = []
        for item in text_val:
            if item is None:
                continue
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                val = item.get("text", "")
                if isinstance(val, str):
                    parts.append(val)
                elif val is not None:
                    parts.append(str(val))
            elif isinstance(item, (int, float)):
                parts.append(str(item))
        return "".join(parts)
    if isinstance(text_val, dict):
        val = text_val.get("text", "")
        return str(val) if val is not None else ""
    return str(text_val)


class TelegramChatExportParser:
    """Parser for Telegram Desktop JSON (`result.json`) and HTML exports."""

    @classmethod
    def parse_json(cls, content: Union[str, bytes, dict], filename: str = "result.json", override_title: Optional[str] = None) -> Dict[str, Any]:
        """Parse Telegram Desktop JSON export (`result.json`)."""
        if isinstance(content, (str, bytes)):
            try:
                data = json.loads(content)
            except Exception as e:
                raise ValueError(f"Invalid JSON format for Telegram export: {e}")
        else:
            data = content

        chat_name = override_title.strip() if override_title and override_title.strip() else (
            data.get("name") or data.get("title") or Path(filename).stem or "Telegram Channel"
        )
        chat_id = str(data.get("id") or abs(hash(chat_name)) % 1000000000)
        chat_type = data.get("type", "public_channel")

        # Pre-load existing job UIDs and official URLs once to eliminate N+1 database queries
        existing_uids: set[str] = set()
        existing_urls: set[str] = set()
        try:
            conn = get_connection()
            c = conn.cursor()
            c.execute("SELECT job_uid, official_url FROM jobs WHERE job_uid IS NOT NULL")
            for r in c.fetchall():
                if r["job_uid"]:
                    existing_uids.add(r["job_uid"])
                if r["official_url"]:
                    existing_urls.add(r["official_url"])
            conn.close()
        except Exception as e:
            logger.warning(f"Could not pre-load existing jobs for deduplication: {e}")

        raw_messages = data.get("messages", [])
        parsed_items: List[Dict[str, Any]] = []
        personal_skipped = 0
        career_relevant = 0

        for msg in raw_messages:
            # Skip system / service messages (joins, pins, title changes)
            if msg.get("type") != "message":
                personal_skipped += 1
                continue

            raw_text = _flatten_telegram_json_text(msg.get("text")).strip()
            if not raw_text:
                personal_skipped += 1
                continue

            # Classify content
            classified = TelegramContentClassifier.classify(raw_text)
            if classified.get("is_command"):
                personal_skipped += 1
                continue

            # Check if relevant
            if classified["classification"] == TelegramContentClassifier.CAT_IRRELEVANT and len(raw_text.split()) < 6:
                personal_skipped += 1
                continue

            career_relevant += 1
            msg_id = msg.get("id", len(parsed_items) + 1)
            raw_date = msg.get("date") or datetime.now(timezone.utc).isoformat()
            sender = msg.get("from") or chat_name

            # Generate deduplication UID
            text_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()[:12]
            message_uid = f"tg_exp_{chat_id}_{msg_id}_{text_hash}"

            is_job = classified.get("is_job_lead", False)
            parsed_job = None
            if is_job:
                parsed_job = CommunityJobParser.parse_announcement(
                    raw_text,
                    source_channel=f"Telegram Export ({chat_name})",
                    existing_uids=existing_uids,
                    existing_urls=existing_urls,
                    check_duplicates=True
                )

            item = {
                "message_uid": message_uid,
                "message_id": msg_id,
                "chat_id": chat_id,
                "chat_name": chat_name,
                "chat_type": chat_type,
                "sender_name": sender,
                "timestamp_raw": raw_date,
                "raw_text": raw_text,
                "classification": classified["classification"],
                "category_group": classified["category_group"],
                "is_job_lead": is_job,
                "job_parsed": parsed_job,
                "tech_tags": classified.get("tech_tags", []),
                "candidate_matches": classified.get("candidate_matches", []),
                "urls": classified.get("urls", []),
                "filename": filename,
                "export_format": "telegram_desktop_json"
            }
            parsed_items.append(item)

        return {
            "chat_name": chat_name,
            "chat_id": chat_id,
            "chat_type": chat_type,
            "filename": filename,
            "total_raw_messages": len(raw_messages),
            "personal_skipped": personal_skipped,
            "career_relevant": career_relevant,
            "job_leads_count": sum(1 for i in parsed_items if i["is_job_lead"]),
            "items": parsed_items
        }

    @classmethod
    def parse_html(cls, content: Union[str, bytes], filename: str = "messages.html", override_title: Optional[str] = None) -> Dict[str, Any]:
        """Parse Telegram Desktop HTML export (`messages.html`)."""
        if isinstance(content, bytes):
            html_text = content.decode("utf-8", errors="replace")
        else:
            html_text = str(content)

        # Extract title from <div class="page_header"><div class="text bold">Title</div>
        title_m = re.search(r'<div class="page_header">.*?<div class="text bold">([^<]+)</div>', html_text, re.DOTALL)
        chat_name = override_title.strip() if override_title and override_title.strip() else (
            title_m.group(1).strip() if title_m else Path(filename).stem
        )

        chat_id = str(abs(hash(chat_name)) % 1000000000)

        # Pre-load existing job UIDs and official URLs once
        existing_uids: set[str] = set()
        existing_urls: set[str] = set()
        try:
            conn = get_connection()
            c = conn.cursor()
            c.execute("SELECT job_uid, official_url FROM jobs WHERE job_uid IS NOT NULL")
            for r in c.fetchall():
                if r["job_uid"]:
                    existing_uids.add(r["job_uid"])
                if r["official_url"]:
                    existing_urls.add(r["official_url"])
            conn.close()
        except Exception as e:
            logger.warning(f"Could not pre-load existing jobs for deduplication: {e}")

        parsed_items: List[Dict[str, Any]] = []
        personal_skipped = 0
        career_relevant = 0

        # Match message blocks by message ID
        msg_blocks = re.findall(
            r'id="message(\d+)"[^>]*>([\s\S]*?)(?=<div[^>]*id="message\d+"|\s*</body>|\s*</html>|$)',
            html_text
        )

        for msg_id_str, block in msg_blocks:
            msg_id = int(msg_id_str)
            # Extract date
            date_m = re.search(r'<div class="date details"[^>]*title="([^"]+)"', block)
            date_str = date_m.group(1) if date_m else datetime.now(timezone.utc).isoformat()

            # Extract from
            from_m = re.search(r'<div class="from_name">([^<]+)</div>', block)
            sender = from_m.group(1).strip() if from_m else chat_name

            # Extract text (handling either closed div or end of block)
            text_m = re.search(r'<div class="text">([\s\S]*?)(?:</div>|$)', block)
            if not text_m:
                personal_skipped += 1
                continue

            raw_html_body = text_m.group(1)
            # Strip tags and normalize line breaks
            raw_text = re.sub(r'<br\s*/?>', '\n', raw_html_body)
            raw_text = re.sub(r'<[^>]+>', '', raw_text).strip()
            if not raw_text or len(raw_text.split()) < 4:
                personal_skipped += 1
                continue

            classified = TelegramContentClassifier.classify(raw_text)
            if classified.get("is_command"):
                personal_skipped += 1
                continue

            career_relevant += 1
            text_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()[:12]
            message_uid = f"tg_exp_{chat_id}_{msg_id}_{text_hash}"

            is_job = classified.get("is_job_lead", False)
            parsed_job = None
            if is_job:
                parsed_job = CommunityJobParser.parse_announcement(
                    raw_text,
                    source_channel=f"Telegram Export ({chat_name})",
                    existing_uids=existing_uids,
                    existing_urls=existing_urls,
                    check_duplicates=True
                )

            item = {
                "message_uid": message_uid,
                "message_id": msg_id,
                "chat_id": chat_id,
                "chat_name": chat_name,
                "chat_type": "channel",
                "sender_name": sender,
                "timestamp_raw": date_str,
                "raw_text": raw_text,
                "classification": classified["classification"],
                "category_group": classified["category_group"],
                "is_job_lead": is_job,
                "job_parsed": parsed_job,
                "tech_tags": classified.get("tech_tags", []),
                "candidate_matches": classified.get("candidate_matches", []),
                "urls": classified.get("urls", []),
                "filename": filename,
                "export_format": "telegram_desktop_html"
            }
            parsed_items.append(item)

        return {
            "chat_name": chat_name,
            "chat_id": chat_id,
            "chat_type": "channel",
            "filename": filename,
            "total_raw_messages": len(msg_blocks),
            "personal_skipped": personal_skipped,
            "career_relevant": career_relevant,
            "job_leads_count": sum(1 for i in parsed_items if i["is_job_lead"]),
            "items": parsed_items
        }

    @classmethod
    def import_items(cls, parsed_data: Dict[str, Any]) -> Dict[str, Any]:
        """Commit parsed Telegram export items to database (inbox_messages and jobs) with deduplication."""
        items = parsed_data.get("items", [])
        chat_name = parsed_data.get("chat_name", "Telegram Channel")
        chat_id = str(parsed_data.get("chat_id", "tg_export"))
        filename = parsed_data.get("filename", "export")
        now_iso = datetime.now(timezone.utc).isoformat()

        imported_count = 0
        duplicates_count = 0
        jobs_created = 0

        # Pre-load existing message UIDs and existing jobs to prevent N+1 database roundtrips
        existing_msg_uids: set[str] = set()
        existing_job_map: Dict[str, int] = {}
        
        # Instantiate JobScorer once outside loop to avoid reloading profile preferences per lead
        scorer = JobScorer()

        conn = get_connection()
        try:
            c = conn.cursor()
            c.execute("SELECT message_uid FROM inbox_messages WHERE message_uid IS NOT NULL")
            for r in c.fetchall():
                if r["message_uid"]:
                    existing_msg_uids.add(r["message_uid"])
            c.execute("SELECT id, job_uid FROM jobs WHERE job_uid IS NOT NULL")
            for r in c.fetchall():
                if r["job_uid"]:
                    existing_job_map[r["job_uid"]] = r["id"]

            with conn:  # Atomic SQLite batch transaction
                for item in items:
                    uid = item["message_uid"]
                    if uid in existing_msg_uids:
                        duplicates_count += 1
                        continue

                    job_id = None
                    if item.get("is_job_lead"):
                        p_job = item.get("job_parsed")
                        if not p_job and item.get("raw_text"):
                            p_job = CommunityJobParser.parse_announcement(
                                item["raw_text"],
                                source_channel=f"Telegram Export ({chat_name})"
                            )
                        if p_job:
                            j_uid = p_job.get("job_uid")
                            ex_job_id = existing_job_map.get(j_uid) if j_uid else None
                            if ex_job_id:
                                job_id = ex_job_id
                            else:
                                try:
                                    sc = scorer.score_job({
                                        "title": p_job["title"],
                                        "description": item["raw_text"],
                                        "location": p_job.get("location", ""),
                                        "required_skills": p_job.get("required_skills", [])
                                    })
                                    job_obj = Job(
                                        title=p_job["title"],
                                        normalized_title=p_job.get("normalized_title", p_job["title"].lower()),
                                        employer=p_job["employer"],
                                        location=p_job["location"],
                                        work_arrangement="Unknown",
                                        employment_type="Full-time",
                                        priority_category=p_job["priority_category"],
                                        priority_label=p_job["priority_label"],
                                        geographic_priority=p_job["geographic_priority"],
                                        geographic_tier_label=p_job["geographic_tier_label"],
                                        location_eligibility_status=p_job["location_eligibility_status"],
                                        job_uid=p_job["job_uid"],
                                        official_url=p_job["application_url"],
                                        official_listing_url=p_job["application_url"],
                                        application_url=p_job["application_url"],
                                        discovery_url=p_job["application_url"],
                                        canonical_url=p_job["application_url"],
                                        discovery_source=f"Telegram Export: {chat_name}",
                                        verification_source=f"Telegram Chat Export ({filename})",
                                        verification_status=VerificationStatus.UNVERIFIED,
                                        verification_notes="Imported from Telegram Desktop chat export. Vacancy link requires verification.",
                                        match_score=sc["match_score"],
                                        match_tier=sc["match_tier"],
                                        score_breakdown=sc["score_breakdown"],
                                        required_skills=sc["supported_skills"] + sc["missing_skills"],
                                        supported_skills=sc["supported_skills"],
                                        missing_skills=sc["missing_skills"],
                                        learnable_skills=sc["learnable_skills"],
                                        disqualifiers=sc["disqualifiers"],
                                        evidence_notes="Candidate facts require review for tailored materials.",
                                        description=item["raw_text"],
                                        is_fresher=p_job.get("is_fresher", False),
                                        is_off_campus=p_job.get("is_off_campus", False),
                                        is_internship=p_job.get("is_internship", False),
                                        is_walkin=p_job.get("is_walkin", False),
                                    )
                                    job_id = save_job(job_obj, conn=conn)
                                    if j_uid and job_id:
                                        existing_job_map[j_uid] = job_id
                                    jobs_created += 1
                                except Exception as e:
                                    logger.error(f"Error scoring/saving job {j_uid}: {e}")

                    inbox_payload = {
                        "message_uid": uid,
                        "channel": "telegram",
                        "chat_id": f"tg_export_{chat_id}",
                        "chat_title": chat_name,
                        "chat_type": item.get("chat_type", "channel"),
                        "message_id": item["message_id"],
                        "sender_id": "",
                        "sender_name": item["sender_name"],
                        "sender_username": "",
                        "raw_text": item["raw_text"],
                        "classification": item["classification"],
                        "category_group": item["category_group"],
                        "is_job_lead": 1 if item["is_job_lead"] else 0,
                        "job_id": job_id,
                        "extracted_data": {
                            "export_filename": filename,
                            "export_format": item.get("export_format", "telegram_desktop"),
                            "timestamp_raw": item.get("timestamp_raw", now_iso),
                            "urls": item.get("urls", []),
                            "tech_tags": item.get("tech_tags", []),
                            "candidate_matches": item.get("candidate_matches", []),
                            "job_parsed": item.get("job_parsed")
                        },
                        "media_type": "text",
                        "media_file_id": "",
                        "received_at": now_iso,
                        "status": "NEW",
                        "notes": f"Imported from Telegram Desktop chat export: {chat_name} (File: {filename})"
                    }
                    save_inbox_message(inbox_payload, conn=conn)
                    imported_count += 1
                    existing_msg_uids.add(uid)
        finally:
            conn.close()

        # Record or update community source
        source_id = record_community_source(
            chat_id=f"tg_export_{chat_id}",
            source_name=f"Telegram Export: {chat_name}",
            source_type="telegram_chat_export",
            status="ACTIVE",
            is_public=True,
            is_member=False,
            can_receive_messages=True,
            bot_role="export_parser",
            setup_instructions="Chat history imported from Telegram Desktop. Re-import latest export anytime to refresh.",
            diagnosis=f"Successfully imported {imported_count} messages from {filename}.",
            last_message_at=now_iso,
            last_message_excerpt=items[-1]["raw_text"][:120] if items else "",
            increment_messages=False
        )
        if imported_count > 0:
            # Update messages count
            conn = get_connection()
            c = conn.cursor()
            c.execute("UPDATE community_sources SET messages_count = messages_count + ? WHERE id = ?", (imported_count, source_id))
            conn.commit()
            conn.close()

        return {
            "status": "SUCCESS",
            "chat_name": chat_name,
            "filename": filename,
            "imported_count": imported_count,
            "duplicates_count": duplicates_count,
            "jobs_created": jobs_created,
            "source_id": source_id
        }
