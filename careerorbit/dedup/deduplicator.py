"""Duplicate detection and record merging engine."""
import re
import urllib.parse
from typing import Dict, Any, Optional, Tuple

from careerorbit.models.schemas import canonicalize_verification_status

class Deduplicator:
    """Detects duplicate job listings across search engines, aggregators, and career portals."""

    @staticmethod
    def normalize_company_name(name: str) -> str:
        if not name:
            return ""
        n = name.lower().strip()
        # Remove common corporate suffixes and organizational words
        n = re.sub(r'\b(inc|llc|ltd|pvt\s+ltd|private\s+limited|corporation|corp|technologies|technology|solutions|services|group|global|international|systems|india)\b', '', n)
        n = re.sub(r'[^a-z0-9]', '', n)
        return n

    @staticmethod
    def normalize_job_title(title: str) -> str:
        if not title:
            return ""
        t = title.lower().strip()
        # Remove common level or department noise
        t = re.sub(r'\(.*?\)', '', t)
        t = re.sub(r'\[.*?\]', '', t)
        # Normalize common synonyms
        t = t.replace("sr.", "senior").replace("jr.", "junior")
        t = t.replace("swe", "software engineer")
        t = t.replace("dev", "developer")
        t = re.sub(r'[^a-z0-9\s]', ' ', t)
        t = re.sub(r'\s+', ' ', t).strip()
        return t

    @staticmethod
    def canonicalize_url(url: str) -> str:
        if not url:
            return ""
        try:
            parsed = urllib.parse.urlparse(url)
            # Remove tracking query parameters (utm_*, ref, source, etc.)
            clean_query = []
            if parsed.query:
                params = urllib.parse.parse_qsl(parsed.query)
                tracking_keys = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "ref", "source", "refId"}
                clean_query = [(k, v) for k, v in params if k not in tracking_keys]
            
            new_query = urllib.parse.urlencode(clean_query)
            clean_url = urllib.parse.urlunparse((
                parsed.scheme,
                parsed.netloc.lower(),
                parsed.path.rstrip('/'),
                parsed.params,
                new_query,
                ""
            ))
            return clean_url
        except Exception:
            return url.strip().lower()

    @classmethod
    def generate_job_uid(cls, employer: str, title: str, job_id_or_req: str = "", location: str = "") -> str:
        """Generates a stable unique identifier for a vacancy."""
        norm_emp = cls.normalize_company_name(employer)
        norm_title = cls.normalize_job_title(title)
        
        clean_req = re.sub(r'[^a-zA-Z0-9]', '', (job_id_or_req or '').strip()).lower()
        if clean_req and clean_req not in ("seeopeningid", "none", "null", "na", "unknown") and len(clean_req) > 2:
            return f"{norm_emp}_{clean_req}"
        
        # Location city key
        loc_key = ""
        for city in ["coimbatore", "chennai", "bengaluru", "bangalore", "hyderabad", "kochi", "puducherry", "cuddalore", "remote"]:
            if city in location.lower():
                loc_key = city
                break
        
        return f"{norm_emp}_{norm_title.replace(' ', '_')}_{loc_key}"

    @classmethod
    def merge_job_records(cls, existing: Dict[str, Any], incoming: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
        """Merges incoming data into existing record; returns (merged_dict, changed_flag)."""
        merged = dict(existing)
        changed = False

        # Prefer official application URL over aggregator
        incoming_url = incoming.get("official_url", "")
        existing_url = existing.get("official_url", "")
        if incoming_url and not existing_url:
            merged["official_url"] = incoming_url
            changed = True
        elif incoming_url and ("greenhouse.io" in incoming_url or "lever.co" in incoming_url or "myworkdayjobs.com" in incoming_url or "careers" in incoming_url):
            if existing_url != incoming_url:
                merged["official_url"] = incoming_url
                changed = True

        for field in ("official_listing_url", "application_url"):
            incoming_value = incoming.get(field, "")
            if incoming_value and existing.get(field) != incoming_value:
                merged[field] = incoming_value
                changed = True

        existing_sources = [s.strip() for s in (existing.get("discovery_source") or "").split(";") if s.strip()]
        incoming_source = (incoming.get("discovery_source") or "").strip()
        if incoming_source and incoming_source not in existing_sources:
            merged["discovery_source"] = "; ".join(existing_sources + [incoming_source])
            changed = True
        if incoming.get("discovery_url") and not existing.get("discovery_url"):
            merged["discovery_url"] = incoming["discovery_url"]
            changed = True
        for field in ("last_observed_status", "last_observed_status_at", "last_verified_at", "verification_source"):
            incoming_value = incoming.get(field)
            if incoming_value and existing.get(field) != incoming_value:
                merged[field] = incoming_value
                changed = True

        if incoming.get("posting_date") and not existing.get("posting_date"):
            merged["posting_date"] = incoming["posting_date"]
            merged["posting_date_confidence"] = incoming.get("posting_date_confidence", "UNKNOWN")
            changed = True

        # Check verification status updates preserving evidence against transient downgrades
        incoming_v_raw = incoming.get("verification_status")
        if incoming_v_raw:
            incoming_v = canonicalize_verification_status(incoming_v_raw)
            existing_v = canonicalize_verification_status(existing.get("verification_status") or "PENDING_VERIFICATION")

            definitive_states = {"VERIFIED_OPEN", "VERIFIED_CLOSED", "BROKEN_LINK", "SUSPICIOUS"}
            transient_states = {"PENDING_VERIFICATION", "UNVERIFIED", "VERIFICATION_ERROR", "STATUS_UNKNOWN"}

            # Rule 1: A definitive state is never downgraded by a weaker transient state
            if existing_v in definitive_states and incoming_v in transient_states:
                # Retain the definitive status; transient observation is captured in last_observed_status
                pass
            # Rule 2: VERIFIED_CLOSED can only be reopened by VERIFIED_OPEN
            elif existing_v == "VERIFIED_CLOSED" and incoming_v in ("BROKEN_LINK", "SUSPICIOUS"):
                pass
            # Rule 3: Legitimate transition or status update
            elif incoming_v != existing_v:
                merged["verification_status"] = incoming_v
                merged["verification_notes"] = incoming.get("verification_notes", existing.get("verification_notes"))
                changed = True
            elif incoming.get("verification_notes") and incoming.get("verification_notes") != existing.get("verification_notes"):
                merged["verification_notes"] = incoming["verification_notes"]
                changed = True

        # Update deadline if newly known
        if incoming.get("deadline") and not existing.get("deadline"):
            merged["deadline"] = incoming["deadline"]
            changed = True

        # Update match score / requirements if refined
        if incoming.get("match_score", 0) > existing.get("match_score", 0):
            merged["match_score"] = incoming["match_score"]
            merged["match_tier"] = incoming.get("match_tier", existing.get("match_tier"))
            merged["score_breakdown"] = incoming.get("score_breakdown", existing.get("score_breakdown"))
            changed = True

        # Refresh last verified date
        if incoming.get("last_verified_at"):
            merged["last_verified_at"] = incoming["last_verified_at"]

        return merged, changed
