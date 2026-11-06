"""Load a private, local candidate profile without embedding it in source code.

The default profile contains only empty fields and public schema structure. A
personal installation stores its claims in ``data/candidate_profile_private.json``;
that file is ignored by Git and excluded from release archives.
"""
from __future__ import annotations

import copy
import json
import logging
import re
from collections.abc import MutableMapping
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Iterator

from careerorbit.config.settings import SETTINGS, current_data_dir


PROFILE_DATA_FILENAME = "candidate_profile_private.json"

DEFAULT_CANDIDATE_PROFILE: dict[str, Any] = {
    "personal": {
        "full_name": "",
        "email": "",
        "phone": "",
        "location": "",
        "linkedin": "",
        "github": "",
        "work_authorization": "",
        "notice_period_status": "",
        "experience_level": "",
        "salary_expectation": "",
        "daily_study_hours": 0,
    },
    "education": {
        "degree": "",
        "field_of_study": "",
        "institution": "",
        "start_year": "",
        "graduation_month": "",
        "graduation_year": "",
        "cgpa": "",
    },
    "employment": [],
    "documented_skills": {
        "languages": [],
        "bi_and_analytics": [],
        "web_and_apis": [],
        "ai_and_ml": [],
        "cloud_and_tools": [],
        "learning_targets_cloud_data": [],
    },
    "projects": [],
    "certifications": [],
    "priority_roles": {},
    "location_preferences": {},
}


def _merge_profile(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Merge profile values while retaining required empty schema fields."""
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge_profile(base[key], value)
        else:
            base[key] = value
    return base


def load_candidate_profile(profile_path: Path | None = None) -> dict[str, Any]:
    """Load private profile data from the configured local data directory."""
    path = profile_path or (current_data_dir() / PROFILE_DATA_FILENAME)
    profile = copy.deepcopy(DEFAULT_CANDIDATE_PROFILE)
    if not path.is_file():
        return profile
    try:
        with path.open("r", encoding="utf-8") as stream:
            stored = json.load(stream)
    except (OSError, json.JSONDecodeError) as exc:
        logging.error("Could not load private candidate profile from %s: %s", path, exc)
        return profile
    if not isinstance(stored, dict):
        logging.error("Private candidate profile must contain a JSON object: %s", path)
        return profile
    profile = _merge_profile(profile, stored)
    roles = profile.get("priority_roles")
    if isinstance(roles, dict):
        profile["priority_roles"] = {
            int(key) if isinstance(key, str) and key.isdigit() else key: value
            for key, value in roles.items()
        }
    return profile


def _apply_overrides(profile: dict[str, Any], overrides_path: Path) -> None:
    """Apply profile edits from one account's private override file."""
    try:
        overrides = json.loads(overrides_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(overrides, dict):
        return
    for path, value in overrides.items():
        tokens = [token for token in re.split(r"\.|\b(?=\[)", str(path)) if token]
        target: Any = profile
        try:
            for token in tokens[:-1]:
                target = target[int(token[1:-1])] if token.startswith("[") else target[token]
            last = tokens[-1]
            if last.startswith("[") and last.endswith("]"):
                target[int(last[1:-1])] = value
            else:
                target[last] = value
        except (KeyError, IndexError, TypeError, ValueError):
            logging.warning("Ignoring invalid candidate-profile override path")


_DEFAULT_PROFILE = load_candidate_profile()
_ACTIVE_PROFILE: ContextVar[dict[str, Any] | None] = ContextVar("careerorbit_candidate_profile", default=None)


def active_candidate_profile() -> dict[str, Any]:
    return _ACTIVE_PROFILE.get() or _DEFAULT_PROFILE


@contextmanager
def candidate_profile_context(data_dir: Path) -> Iterator[None]:
    """Select and restore one account's profile for the current request context."""
    root = Path(data_dir)
    profile = load_candidate_profile(root / PROFILE_DATA_FILENAME)
    _apply_overrides(profile, root / "candidate_profile_overrides.json")
    token = _ACTIVE_PROFILE.set(profile)
    try:
        yield
    finally:
        _ACTIVE_PROFILE.reset(token)


class CandidateProfileProxy(MutableMapping[str, Any]):
    """Compatibility mapping that resolves profile data per async request."""

    def __getitem__(self, key: str) -> Any:
        return active_candidate_profile()[key]

    def __setitem__(self, key: str, value: Any) -> None:
        active_candidate_profile()[key] = value

    def __delitem__(self, key: str) -> None:
        del active_candidate_profile()[key]

    def __iter__(self):
        return iter(active_candidate_profile())

    def __len__(self) -> int:
        return len(active_candidate_profile())


# Preserve the existing dict-like API while routing requests to isolated profiles.
CANDIDATE_PROFILE: MutableMapping[str, Any] = CandidateProfileProxy()
