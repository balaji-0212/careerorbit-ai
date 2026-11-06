"""Personalized Career Priorities Architecture for CareerOrbit AI.

Separates objective job classification taxonomy from subjective user career preferences.
Supports multi-profile preferences, atomic persistence, validation, dynamic ranking SQL,
and fallback handling.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import quote, unquote

from careerorbit.config.settings import SETTINGS, current_data_dir
from careerorbit.eligibility import (
    P1_PATTERNS,
    P2_PATTERNS,
    P3_PATTERNS,
    P4_PATTERNS,
    P5_PATTERNS,
    P6_PATTERNS,
    is_unrelated_nontechnical_role,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CareerCategory:
    """An objective career category supported by the CareerOrbit AI platform."""
    id: str
    legacy_code: int
    label: str
    short_label: str
    description: str
    resume_focus: str
    default_patterns: tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "legacy_code": self.legacy_code,
            "label": self.label,
            "short_label": self.short_label,
            "description": self.description,
            "resume_focus": self.resume_focus,
        }


# Canonical platform-supported career category taxonomy
SUPPORTED_CATEGORIES: Dict[str, CareerCategory] = {
    "data_analyst": CareerCategory(
        id="data_analyst",
        legacy_code=1,
        label="Data Analyst / BI / Power BI / Reporting",
        short_label="Data Analyst",
        description="Business intelligence, SQL/Power BI reporting, KPI modeling, and data analytics.",
        resume_focus="data_analyst",
        default_patterns=P1_PATTERNS,
    ),
    "data_scientist": CareerCategory(
        id="data_scientist",
        legacy_code=2,
        label="Data Scientist / Junior Data Scientist",
        short_label="Data Scientist",
        description="Applied machine learning, statistical modeling, data science, and exploratory analytics.",
        resume_focus="data_scientist",
        default_patterns=P2_PATTERNS,
    ),
    "software_engineer": CareerCategory(
        id="software_engineer",
        legacy_code=3,
        label="Software Engineer / Associate Software Engineer / Junior Developer",
        short_label="Software Engineer",
        description="Backend engineering, Python development, REST APIs, and full-stack software development.",
        resume_focus="software_engineer",
        default_patterns=P3_PATTERNS,
    ),
    "ai_engineer": CareerCategory(
        id="ai_engineer",
        legacy_code=4,
        label="AI / ML / Computer Vision / AI Application Engineer",
        short_label="AI Engineer",
        description="Generative AI, computer vision, deep learning models, and applied AI systems.",
        resume_focus="ai_engineer",
        default_patterns=P4_PATTERNS,
    ),
    "data_engineer": CareerCategory(
        id="data_engineer",
        legacy_code=5,
        label="Data Engineer / Analytics Engineer / ETL Developer",
        short_label="Data Engineer",
        description="Data pipelines, automated ETL/ELT workflows, data warehousing, and cloud data architecture.",
        resume_focus="data_engineer",
        default_patterns=P5_PATTERNS,
    ),
    "other_technical": CareerCategory(
        id="other_technical",
        legacy_code=6,
        label="Other relevant early-career technical roles",
        short_label="Other Technical Roles",
        description="QA automation, technical support, cloud engineering, DevOps, and related early-career technical roles.",
        resume_focus="general_technical",
        default_patterns=P6_PATTERNS,
    ),
}

# Reverse mapping from legacy code to category ID
LEGACY_CODE_TO_CATEGORY_ID: Dict[int, str] = {
    cat.legacy_code: cat.id for cat in SUPPORTED_CATEGORIES.values()
}

# Default candidate preference order (used for legacy profile migration and default fallback)
LEGACY_DEFAULT_CATEGORY_ORDER: List[str] = [
    "data_analyst",
    "data_scientist",
    "software_engineer",
    "ai_engineer",
    "data_engineer",
    "other_technical",
]


def list_supported_categories() -> List[Dict[str, Any]]:
    """Return all platform-supported career categories with metadata."""
    return [cat.to_dict() for cat in SUPPORTED_CATEGORIES.values()]


def get_category_by_id(category_id: str) -> Optional[CareerCategory]:
    """Look up a career category by its identifier."""
    if not category_id:
        return None
    return SUPPORTED_CATEGORIES.get(category_id.strip().lower())


def get_category_by_legacy_code(code: int) -> Optional[CareerCategory]:
    """Look up a career category by legacy numeric code (1-6)."""
    cat_id = LEGACY_CODE_TO_CATEGORY_ID.get(code)
    return SUPPORTED_CATEGORIES.get(cat_id) if cat_id else None


def custom_category_id(label: str) -> str:
    """Return a stable preference identifier that preserves a user's custom role label."""
    clean = " ".join(str(label or "").split())
    if not 2 <= len(clean) <= 120:
        raise ValueError("Enter a custom career role between 2 and 120 characters.")
    if any(ord(char) < 32 for char in clean):
        raise ValueError("Custom career role contains unsupported control characters.")
    return "custom:" + quote(clean, safe="")


def custom_category_label(category_id: str) -> Optional[str]:
    if not isinstance(category_id, str) or not category_id.startswith("custom:"):
        return None
    try:
        label = " ".join(unquote(category_id[7:]).split())
    except Exception:
        return None
    return label if 2 <= len(label) <= 120 else None


def preference_category_dict(category_id: str) -> Optional[Dict[str, Any]]:
    category = SUPPORTED_CATEGORIES.get(category_id)
    if category:
        return category.to_dict()
    label = custom_category_label(category_id)
    if not label:
        return None
    mapped = classify_job_category(label)
    mapping_note = (
        f"Custom role preference; discovery ranking maps to {mapped.short_label}."
        if mapped else "Custom role preference; discovery uses exact job-title matches."
    )
    return {
        "id": category_id,
        "legacy_code": mapped.legacy_code if mapped else 0,
        "label": label,
        "short_label": label,
        "description": mapping_note,
        "resume_focus": mapped.resume_focus if mapped else "custom",
        "custom": True,
    }


# ---------------------------------------------------------------------------
# Classification (Objective): "What kind of role is this job?"
# ---------------------------------------------------------------------------

def classify_job_category(title: str, description: str = "") -> Optional[CareerCategory]:
    """Objective classifier: maps job title/description to a platform CareerCategory.
    
    Returns None if the role is non-technical, out-of-scope, or unclassified.
    This does NOT determine how much the candidate prefers this role.
    """
    if is_unrelated_nontechnical_role(title, description):
        return None

    import re
    t = (title or "").lower()

    if any(p in t for p in P1_PATTERNS):
        return SUPPORTED_CATEGORIES["data_analyst"]
    if any(p in t for p in P2_PATTERNS):
        return SUPPORTED_CATEGORIES["data_scientist"]
    if any(p in t for p in P3_PATTERNS) or bool(re.search(r"\bsde\b", t)):
        return SUPPORTED_CATEGORIES["software_engineer"]
    if any(p in t for p in P4_PATTERNS):
        return SUPPORTED_CATEGORIES["ai_engineer"]
    if any(p in t for p in P5_PATTERNS):
        return SUPPORTED_CATEGORIES["data_engineer"]
    if any(p in t for p in P6_PATTERNS):
        return SUPPORTED_CATEGORIES["other_technical"]

    return None


# ---------------------------------------------------------------------------
# Preference Data Model & Validation
# ---------------------------------------------------------------------------

@dataclass
class UserCareerPreferences:
    """Personalized career preferences for a candidate profile."""
    profile_id: str
    selected_categories: List[str]
    updated_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "selected_categories": list(self.selected_categories),
            "updated_at": self.updated_at,
        }

    def validate(self) -> None:
        """Validate preference data integrity.
        
        Raises ValueError on malformed data, unknown categories, or duplicate selections.
        """
        if not isinstance(self.profile_id, str) or not self.profile_id.strip():
            raise ValueError("profile_id must be a non-empty string")

        if not isinstance(self.selected_categories, (list, tuple)):
            raise ValueError("selected_categories must be a list of category identifiers")

        self.selected_categories = validate_preference_list(self.selected_categories)


def validate_preference_list(categories: Sequence[str]) -> List[str]:
    """Validate and normalize a list of category IDs."""
    if not isinstance(categories, (list, tuple)):
        raise ValueError("Categories must be a list of category identifiers")

    normalized: List[str] = []
    seen = set()
    for idx, item in enumerate(categories):
        if not isinstance(item, str):
            raise ValueError(f"Category at index {idx} must be a string identifier")
        clean_item = item.strip()
        if clean_item.startswith("custom:"):
            label = custom_category_label(clean_item)
            if not label:
                raise ValueError(f"Custom career role at index {idx} is malformed.")
            cid = custom_category_id(label)
            duplicate_key = "custom:" + label.casefold()
        else:
            cid = clean_item.lower()
            duplicate_key = cid
        if cid not in SUPPORTED_CATEGORIES and not custom_category_label(cid):
            raise ValueError(
                f"Unknown career category '{item}'. Supported categories: {list(SUPPORTED_CATEGORIES.keys())}"
            )
        if duplicate_key in seen:
            raise ValueError(f"Duplicate career category '{item}' is not allowed in preferences")
        seen.add(duplicate_key)
        normalized.append(cid)
    return normalized


# ---------------------------------------------------------------------------
# Preference Ranking: "How important is this kind of role to this user?"
# ---------------------------------------------------------------------------

def get_preference_rank(
    job: Dict[str, Any] | Any,
    candidate_profile: Optional[Dict[str, Any]] = None,
    preferences: Optional[UserCareerPreferences | Sequence[str]] = None,
    profile_id: str = "default",
) -> Optional[int]:
    """Determines the 1-based personalized preference rank for a job and candidate.
    
    Args:
        job: Job dictionary or schema object.
        candidate_profile: Optional profile dictionary.
        preferences: Optional explicit UserCareerPreferences or list of category IDs.
        profile_id: Target profile identifier (defaults to "default").
        
    Returns:
        1-based integer rank (1 = candidate's top choice, 2 = 2nd choice, etc.)
        None if the category is unsupported, unselected by the user, or job is ineligible.
    """
    # 1. Resolve job's career category
    cat_id: Optional[str] = None
    job_title = ""
    if isinstance(job, dict):
        job_title = str(job.get("title") or "")
        cat_id = job.get("career_category")
        if not cat_id and "priority_category" in job:
            p_code = job.get("priority_category")
            if isinstance(p_code, int) and p_code > 0:
                cat = get_category_by_legacy_code(p_code)
                if cat:
                    cat_id = cat.id
        if not cat_id:
            classified = classify_job_category(job.get("title", ""), job.get("description", ""))
            if classified:
                cat_id = classified.id
    else:
        # Schema object
        job_title = str(getattr(job, "title", "") or "")
        cat_id = getattr(job, "career_category", None)
        if not cat_id and hasattr(job, "priority_category"):
            p_code = getattr(job, "priority_category")
            if isinstance(p_code, int) and p_code > 0:
                cat = get_category_by_legacy_code(p_code)
                if cat:
                    cat_id = cat.id
        if not cat_id:
            classified = classify_job_category(getattr(job, "title", ""), getattr(job, "description", ""))
            if classified:
                cat_id = classified.id

    # 2. Resolve candidate's ordered preference list
    ordered_cats: List[str] = []
    if preferences is not None:
        if isinstance(preferences, UserCareerPreferences):
            ordered_cats = preferences.selected_categories
        elif isinstance(preferences, (list, tuple)):
            ordered_cats = list(preferences)
    elif candidate_profile and "career_preferences" in candidate_profile:
        cp_prefs = candidate_profile["career_preferences"]
        if isinstance(cp_prefs, dict):
            ordered_cats = cp_prefs.get("selected_categories", [])
        elif isinstance(cp_prefs, (list, tuple)):
            ordered_cats = list(cp_prefs)
    else:
        # Load from persisted store
        loaded = load_user_career_preferences(profile_id=profile_id)
        ordered_cats = loaded.selected_categories

    # 3. Match canonical preferences and user-defined role aliases in order.
    normalized_title = " ".join(job_title.casefold().split())
    for idx, preference_id in enumerate(ordered_cats, 1):
        if preference_id == cat_id and cat_id:
            return idx
        custom_label = custom_category_label(preference_id)
        if not custom_label:
            continue
        if normalized_title == " ".join(custom_label.casefold().split()):
            return idx
        custom_category = classify_job_category(custom_label)
        if cat_id and custom_category and custom_category.id == cat_id:
            return idx
    return None


# ---------------------------------------------------------------------------
# Dynamic SQL Ordering Builder
# ---------------------------------------------------------------------------

def get_personalized_priority_order_sql(
    preferences: Optional[UserCareerPreferences | Sequence[str]] = None,
    profile_id: str = "default",
    prefix: str = "",
) -> str:
    """Generates a dynamic SQL CASE statement for personalized preference ranking.
    
    Translates the candidate's custom category order into an SQLite ordering expression.
    Selected categories receive their personalized ranks (1, 2, 3...).
    Unselected categories and ineligible rows evaluate to 999.
    
    Example output:
        CASE
            WHEN priority_category = 3 THEN 1
            WHEN priority_category = 4 THEN 2
            WHEN priority_category = 1 THEN 3
            ELSE 999
        END ASC
    """
    ordered_cats: List[str] = []
    if preferences is not None:
        if isinstance(preferences, UserCareerPreferences):
            ordered_cats = preferences.selected_categories
        elif isinstance(preferences, (list, tuple)):
            ordered_cats = list(preferences)
    else:
        loaded = load_user_career_preferences(profile_id=profile_id)
        ordered_cats = loaded.selected_categories

    col = f"{prefix}priority_category"
    if not ordered_cats:
        # Fallback if no preferences are selected
        return f"CASE WHEN {col} <= 0 THEN 999 ELSE 999 END ASC"

    when_clauses = []
    seen_priority_codes = set()
    for rank, cat_id in enumerate(ordered_cats, 1):
        category = SUPPORTED_CATEGORIES.get(cat_id)
        custom_label = custom_category_label(cat_id)
        if custom_label:
            safe_title = " ".join(custom_label.casefold().split()).replace("'", "''")
            when_clauses.append(f"WHEN LOWER({prefix}title) = '{safe_title}' THEN {rank}")
            category = classify_job_category(custom_label)
        if category and category.legacy_code not in seen_priority_codes:
            when_clauses.append(f"WHEN {col} = {category.legacy_code} THEN {rank}")
            seen_priority_codes.add(category.legacy_code)

    if not when_clauses:
        return f"CASE WHEN {col} <= 0 THEN 999 ELSE 999 END ASC"

    clauses_str = " ".join(when_clauses)
    return f"CASE {clauses_str} ELSE 999 END ASC"


# ---------------------------------------------------------------------------
# Persistence Architecture (Database + Candidate Profile Overrides)
# ---------------------------------------------------------------------------

def load_user_career_preferences(profile_id: str = "default") -> UserCareerPreferences:
    """Loads career preferences for a candidate profile.
    
    Checks in sequence:
    1. Database `candidate_career_preferences` table.
    2. Candidate profile overrides (`data/candidate_profile_overrides.json`).
    3. In-memory `CANDIDATE_PROFILE["career_preferences"]`.
    4. Fallback: For "default" profile, safely migrates from legacy default order;
       for other profiles, returns empty preferences.
    """
    # 1. Check SQLite database
    try:
        from careerorbit.database.db import get_connection
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT preferences_json, updated_at FROM candidate_career_preferences WHERE profile_id = ?",
                (profile_id,)
            )
            row = cur.fetchone()
            if row:
                data = json.loads(row[0])
                if isinstance(data, list):
                    return UserCareerPreferences(
                        profile_id=profile_id,
                        selected_categories=data,
                        updated_at=row[1] or datetime.now(timezone.utc).isoformat(),
                    )
                elif isinstance(data, dict):
                    return UserCareerPreferences(
                        profile_id=profile_id,
                        selected_categories=data.get("selected_categories", []),
                        updated_at=data.get("updated_at", row[1] or datetime.now(timezone.utc).isoformat()),
                    )
    except Exception as e:
        logger.debug("Database load for career preferences failed or table not ready: %s", e)

    # 2. Check candidate_profile_overrides.json (for default profile)
    if profile_id == "default":
        overrides_path = current_data_dir() / "candidate_profile_overrides.json"
        if overrides_path.is_file():
            try:
                overrides = json.loads(overrides_path.read_text(encoding="utf-8"))
                if "career_preferences" in overrides:
                    prefs_val = overrides["career_preferences"]
                    if isinstance(prefs_val, list):
                        return UserCareerPreferences(
                            profile_id="default",
                            selected_categories=prefs_val,
                            updated_at=datetime.now(timezone.utc).isoformat(),
                        )
                    elif isinstance(prefs_val, dict):
                        return UserCareerPreferences(
                            profile_id="default",
                            selected_categories=prefs_val.get("selected_categories", []),
                            updated_at=prefs_val.get("updated_at", datetime.now(timezone.utc).isoformat()),
                        )
            except Exception:
                pass

    # 3. Check CANDIDATE_PROFILE in-memory
    if profile_id == "default":
        try:
            from careerorbit.config.profile import CANDIDATE_PROFILE
            if "career_preferences" in CANDIDATE_PROFILE:
                cp_val = CANDIDATE_PROFILE["career_preferences"]
                if isinstance(cp_val, list):
                    return UserCareerPreferences(
                        profile_id="default",
                        selected_categories=list(cp_val),
                        updated_at=datetime.now(timezone.utc).isoformat(),
                    )
                elif isinstance(cp_val, dict):
                    return UserCareerPreferences(
                        profile_id="default",
                        selected_categories=cp_val.get("selected_categories", []),
                        updated_at=cp_val.get("updated_at", datetime.now(timezone.utc).isoformat()),
                    )
        except Exception:
            pass

    # 4. Safe migration fallback
    if profile_id == "default":
        # For the existing candidate profile, preserve legacy candidate preferences
        return UserCareerPreferences(
            profile_id="default",
            selected_categories=list(LEGACY_DEFAULT_CATEGORY_ORDER),
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

    # New or unconfigured profile: returns empty selected categories
    return UserCareerPreferences(
        profile_id=profile_id,
        selected_categories=[],
        updated_at=datetime.now(timezone.utc).isoformat(),
    )


def save_user_career_preferences(preferences: UserCareerPreferences) -> UserCareerPreferences:
    """Saves career preferences atomically to database and candidate profile overrides.
    
    Validates input before persisting.
    Updates CANDIDATE_PROFILE in memory for default profile.
    Records audit entry in candidate_profile_history.jsonl.
    """
    preferences.validate()
    now_iso = datetime.now(timezone.utc).isoformat()
    preferences.updated_at = now_iso

    # 1. Save to SQLite database atomically
    try:
        from careerorbit.database.db import get_connection
        with get_connection() as conn:
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS candidate_career_preferences (
                        profile_id TEXT PRIMARY KEY,
                        preferences_json TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                """)
                conn.execute("""
                    INSERT INTO candidate_career_preferences (profile_id, preferences_json, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(profile_id) DO UPDATE SET
                        preferences_json = excluded.preferences_json,
                        updated_at = excluded.updated_at
                """, (
                    preferences.profile_id,
                    json.dumps(preferences.selected_categories),
                    now_iso
                ))
    except Exception as e:
        logger.error("Failed to persist career preferences to database: %s", e)
        raise

    # 2. Persist to candidate_profile_overrides.json (for default profile)
    if preferences.profile_id == "default":
        try:
            overrides_path = current_data_dir() / "candidate_profile_overrides.json"
            overrides_path.parent.mkdir(parents=True, exist_ok=True)
            overrides: Dict[str, Any] = {}
            if overrides_path.exists():
                try:
                    overrides = json.loads(overrides_path.read_text(encoding="utf-8"))
                except Exception:
                    overrides = {}
            old_prefs = overrides.get("career_preferences")
            overrides["career_preferences"] = preferences.selected_categories

            temp_path = overrides_path.with_suffix(".tmp")
            temp_path.write_text(json.dumps(overrides, ensure_ascii=False, indent=2), encoding="utf-8")
            temp_path.replace(overrides_path)

            # Update in-memory CANDIDATE_PROFILE
            from careerorbit.config.profile import CANDIDATE_PROFILE
            CANDIDATE_PROFILE["career_preferences"] = preferences.selected_categories

            # Audit record in candidate_profile_history.jsonl
            history_path = current_data_dir() / "candidate_profile_history.jsonl"
            history_path.parent.mkdir(parents=True, exist_ok=True)
            record = {
                "timestamp": now_iso,
                "field": "career_preferences",
                "old_value": old_prefs,
                "new_value": preferences.selected_categories,
                "author": "Candidate",
                "note": "Updated personalized career priorities",
                "evidence_state": "CONFIRMED_BY_CANDIDATE",
            }
            with open(history_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning("Failed to update candidate profile overrides file: %s", e)

    return preferences


def reset_user_career_preferences(profile_id: str = "default") -> UserCareerPreferences:
    """Reset candidate preferences back to platform default order."""
    default_prefs = UserCareerPreferences(
        profile_id=profile_id,
        selected_categories=list(LEGACY_DEFAULT_CATEGORY_ORDER),
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
    return save_user_career_preferences(default_prefs)
