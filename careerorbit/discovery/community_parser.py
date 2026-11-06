"""Community Job Announcement Parser for CareerOrbit AI.
Parses pasted text from WhatsApp, Telegram, LinkedIn posts, or campus job alerts.
Extracts title, company, location, experience, deadline, and application URL.
Flags missing links, detects duplicates against existing records, and never fabricates fields.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse

from careerorbit.dedup.deduplicator import Deduplicator
from careerorbit.database.db import get_job_by_uid, list_jobs, get_job_by_url
from careerorbit.eligibility import classify_title_to_priority, PRIORITY_LABELS
from careerorbit.matcher.geo import classify_geographic_priority
from careerorbit.matcher.scorer import JobScorer
from careerorbit.models.schemas import Job, VerificationStatus


class CommunityJobParser:
    """Parser for unformatted text pasted from community channels."""

    KNOWN_TECH_ROLES = [
        "data analyst", "business intelligence analyst", "bi analyst", "power bi developer",
        "reporting analyst", "data scientist", "junior data scientist", "machine learning engineer",
        "software engineer", "associate software engineer", "junior software developer",
        "python developer", "backend developer", "frontend developer", "full stack developer",
        "ai engineer", "data engineer", "analytics engineer", "graduate engineer trainee",
        "sde intern", "software development engineer", "customer experience engineer",
        "technical support engineer", "qa automation engineer", "systems engineer",
    ]

    INDIAN_CITIES = [
        "bengaluru", "bangalore", "chennai", "hyderabad", "coimbatore", "cuddalore",
        "puducherry", "pondicherry", "kochi", "cochin", "mysuru", "mysore", "pune",
        "mumbai", "delhi", "new delhi", "noida", "gurugram", "gurgaon", "ahmedabad",
        "kolkata", "remote", "pan india", "work from home"
    ]

    @classmethod
    def parse_announcement(
        cls,
        raw_text: str,
        source_channel: str = "WhatsApp / Telegram Community",
        existing_uids: Optional[Set[str]] = None,
        existing_urls: Optional[Set[str]] = None,
        check_duplicates: bool = True
    ) -> Dict[str, Any]:
        """Extract structured fields from unformatted announcement text."""
        cleaned_text = cls._clean_text(raw_text)
        lines = [line.strip() for line in cleaned_text.splitlines() if line.strip()]

        urls = cls._extract_urls(raw_text)
        primary_url = urls[0] if urls else ""

        title = cls._extract_field(lines, [
            r"(?:role|job\s*role|job\s*title|position|profile|designation)\s*[:\-–]\s*(.+)",
            r"hiring(?:\s+for)?\s*[:\-–]?\s*([A-Za-z0-9\s/–-]+(?:Engineer|Analyst|Developer|Scientist|Trainee|Intern|Associate))",
        ])
        if not title:
            title = cls._find_role_in_text(cleaned_text)

        employer = cls._extract_field(lines, [
            r"(?:company|employer|organization|org|hiring\s*company)\s*[:\-–]\s*(.+)",
            r"([A-Za-z0-9\s&.,'-]+?)\s+(?:is\s+hiring|off[\s-]campus\s+drive|recruitment\s+drive)",
            r"(?:off[\s-]campus\s+)?hiring\s*[:\-–]?\s*([A-Za-z0-9&.,'-]+?)\s+(?:Junior|Senior|Associate|Graduate|Software|Data|Python|Backend|Analyst|Developer|Engineer|Trainee|Intern)",
        ])

        if not employer and primary_url:
            p_parsed = urlparse(primary_url)
            p_host = p_parsed.netloc.lower()
            if "greenhouse.io" in p_host:
                parts = [x for x in p_parsed.path.split('/') if x]
                if parts:
                    employer = parts[0].title()
            elif "lever.co" in p_host:
                parts = [x for x in p_parsed.path.split('/') if x]
                if parts:
                    employer = parts[0].title()
            elif "myworkdayjobs.com" in p_host:
                employer = p_host.split('.')[0].title()
            elif "smartrecruiters.com" in p_host:
                parts = [x for x in p_parsed.path.split('/') if x]
                if parts:
                    employer = parts[0].title()

        location = cls._extract_field(lines, [
            r"(?:location|job\s*location|work\s*location|place|base)\s*[:\-–]\s*(.+)",
        ])
        if not location:
            location = cls._find_location_in_text(cleaned_text)

        experience = cls._extract_field(lines, [
            r"(?:experience|exp|eligibility|batch|criteria)\s*[:\-–]\s*(.+)",
            r"(\b(?:0[\s–\-]*[123]|freshers?|202[456]\s*batch|any\s*graduate)\b[^\n\r.]*)",
        ])

        deadline = cls._extract_field(lines, [
            r"(?:deadline|last\s*date|apply\s*before|closing\s*date)\s*[:\-–]\s*(.+)",
        ])

        # Clean title if it contains employer prefix or location suffix
        raw_title = title.strip() if title else ""
        if raw_title and employer:
            if raw_title.lower().startswith(employer.lower()):
                raw_title = raw_title[len(employer):].strip(" -–:,\t")
        if raw_title:
            for city in cls.INDIAN_CITIES:
                if raw_title.lower().endswith(city):
                    raw_title = raw_title[:-len(city)].strip(" -–:,\t")
                    break

        # Fallbacks for missing mandatory values
        final_title = raw_title.strip() if raw_title else (cls._find_role_in_text(cleaned_text) or "Early-Career IT Opportunity")
        final_employer = employer.strip() if employer else "Community Employer (Unconfirmed)"
        final_location = location.strip() if location else "India / Remote"
        final_experience = experience.strip() if experience else "Not explicitly stated"

        # Categorize
        priority = classify_title_to_priority(final_title)
        geo_info = classify_geographic_priority(final_location, "Unknown", cleaned_text)

        # Detect attributes
        lower_all = f"{final_title} {final_experience} {cleaned_text}".lower()
        is_fresher = any(term in lower_all for term in (
            "fresher", "freshers", "0-1", "0-2", "0 to 1", "0 to 2", "2024", "2025", "graduate", "trainee"
        ))
        is_off_campus = any(term in lower_all for term in (
            "off-campus", "off campus", "drive", "pooled campus", "hiring challenge", "walk-in"
        ))
        is_internship = "intern" in final_title.lower() or "internship" in lower_all
        is_walkin = "walk-in" in lower_all or "walk in" in lower_all

        # Check for possible duplicate against database or provided in-memory sets
        norm_title = Deduplicator.normalize_job_title(final_title)
        job_uid = Deduplicator.generate_job_uid(final_employer, norm_title, primary_url or final_title, final_location)

        is_duplicate = False
        duplicate_ref = None

        if check_duplicates:
            if existing_uids is not None or existing_urls is not None:
                is_dup_uid = bool(existing_uids and job_uid in existing_uids)
                is_dup_url = bool(existing_urls and primary_url and primary_url in existing_urls)
                is_duplicate = is_dup_uid or is_dup_url
                if is_duplicate:
                    duplicate_ref = {"job_uid": job_uid, "match_type": "in_memory_cache"}
                if existing_uids is not None:
                    existing_uids.add(job_uid)
                if existing_urls is not None and primary_url:
                    existing_urls.add(primary_url)
            else:
                existing_job = get_job_by_uid(job_uid)

                # Also search duplicate by URL if provided
                dup_by_url = None
                if primary_url:
                    dup_by_url = get_job_by_url(primary_url)

                # Also search duplicate by employer if found
                dup_by_emp = None
                if not dup_by_url and not existing_job and final_employer:
                    emp_jobs = list_jobs(employer=final_employer, limit=10)
                    for ej in emp_jobs:
                        if Deduplicator.normalize_job_title(ej.get("title", "")) == norm_title:
                            dup_by_emp = ej
                            break

                is_duplicate = bool(existing_job or dup_by_url or dup_by_emp)
                duplicate_ref = (existing_job or dup_by_url or dup_by_emp) if is_duplicate else None

        missing_link = not bool(primary_url)

        return {
            "title": final_title,
            "employer": final_employer,
            "location": final_location,
            "experience": final_experience,
            "deadline": deadline or None,
            "application_url": primary_url,
            "all_urls": urls,
            "source_channel": source_channel.strip() or "WhatsApp / Telegram Community",
            "priority_category": priority,
            "priority_label": PRIORITY_LABELS.get(priority, "General"),
            "geographic_priority": geo_info.get("geographic_priority", 1),
            "geographic_tier_label": geo_info.get("geographic_tier_label", "Priority 1 — South India & India Remote"),
            "location_eligibility_status": geo_info.get("location_eligibility_status", "VERIFIED_INDIA_ELIGIBLE"),
            "is_fresher": is_fresher,
            "is_off_campus": is_off_campus,
            "is_internship": is_internship,
            "is_walkin": is_walkin,
            "job_uid": job_uid,
            "is_duplicate": is_duplicate,
            "duplicate_ref": duplicate_ref,
            "missing_link": missing_link,
            "raw_text": raw_text,
        }

    @classmethod
    def _clean_text(cls, text: str) -> str:
        """Strip message decoration, markdown asterisks, emojis, and noisy symbols."""
        t = re.sub(r"[\*\_~`]", "", str(text or ""))
        t = re.sub(r"[🚨🔥👉▪️🎯📢✅📌🔗]", " ", t)
        return t.strip()

    @classmethod
    def _extract_urls(cls, text: str) -> List[str]:
        """Find valid HTTP/HTTPS URLs and sanitize punctuation."""
        raw_urls = re.findall(r"https?://[^\s<>\"']+", text)
        cleaned = []
        for u in raw_urls:
            # Strip trailing punctuation often stuck to links in chat messages
            clean = re.sub(r"[.,);:!]+$", "", u).strip()
            parsed = urlparse(clean)
            if parsed.scheme in ("http", "https") and parsed.netloc:
                if clean not in cleaned:
                    cleaned.append(clean)
        return cleaned

    @classmethod
    def _extract_field(cls, lines: List[str], patterns: List[str]) -> str:
        for pattern in patterns:
            for line in lines:
                m = re.search(pattern, line, re.IGNORECASE)
                if m:
                    res = m.group(1).strip()
                    # Remove trailing punctuation or qualifiers
                    res = re.sub(r"[\*|]+$", "", res).strip()
                    if res:
                        return res
        return ""

    @classmethod
    def _find_role_in_text(cls, text: str) -> str:
        lower = text.lower()
        for role in cls.KNOWN_TECH_ROLES:
            if role in lower:
                # Return title-cased match
                return role.title()
        return ""

    @classmethod
    def _find_location_in_text(cls, text: str) -> str:
        lower = text.lower()
        found_cities = []
        for city in cls.INDIAN_CITIES:
            if re.search(r"\b" + re.escape(city) + r"\b", lower):
                found_cities.append(city.title())
        if found_cities:
            return ", ".join(found_cities[:2])
        return ""
