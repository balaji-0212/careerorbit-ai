"""Editable Employer ATS Source Registry for CareerOrbit AI.

Manages employer-specific Greenhouse, Lever, and official ATS board integrations.
Stores persistent configurations in data/employer_sources.json.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from careerorbit.config.settings import SETTINGS, current_data_dir

REGISTRY_PATH = SETTINGS.DATA_DIR / "employer_sources.json"


def _registry_path() -> Path:
    return current_data_dir() / "employer_sources.json"

DEFAULT_SEEDS = [
    {
        "id": "canonical-greenhouse",
        "employer_name": "Canonical",
        "official_domain": "canonical.com",
        "ats_provider": "Greenhouse",
        "board_id": "canonical",
        "status": "CONFIGURED",
        "enabled": True,
        "last_check_time": None,
        "last_successful_check": None,
        "error_details": None,
        "jobs_discovered": 0,
        "notes": "Global open-source technology employer with India/remote roles.",
    },
    {
        "id": "automattic-lever",
        "employer_name": "Automattic",
        "official_domain": "automattic.com",
        "ats_provider": "Lever",
        "board_id": "automattic",
        "status": "CONFIGURED",
        "enabled": False,
        "last_check_time": None,
        "last_successful_check": None,
        "error_details": "Public Lever endpoint returned 404; disabled pending new career endpoint configuration.",
        "jobs_discovered": 0,
        "notes": "Global distributed WordPress technology employer.",
    },
    {
        "id": "gitlab-greenhouse",
        "employer_name": "GitLab",
        "official_domain": "gitlab.com",
        "ats_provider": "Greenhouse",
        "board_id": "gitlab",
        "status": "CONFIGURED",
        "enabled": True,
        "last_check_time": None,
        "last_successful_check": None,
        "error_details": None,
        "jobs_discovered": 0,
        "notes": "Remote-first DevOps platform.",
    },
    {
        "id": "groww-greenhouse",
        "employer_name": "Groww",
        "official_domain": "groww.in",
        "ats_provider": "Greenhouse",
        "board_id": "groww",
        "status": "CONFIGURED",
        "enabled": True,
        "last_check_time": None,
        "last_successful_check": None,
        "error_details": None,
        "jobs_discovered": 0,
        "notes": "India fintech investment platform headquartered in Bengaluru, Karnataka.",
    },
    {
        "id": "inmobi-greenhouse",
        "employer_name": "InMobi",
        "official_domain": "inmobi.com",
        "ats_provider": "Greenhouse",
        "board_id": "inmobi",
        "status": "CONFIGURED",
        "enabled": True,
        "last_check_time": None,
        "last_successful_check": None,
        "error_details": None,
        "jobs_discovered": 0,
        "notes": "Global mobile advertising and technology platform headquartered in Bengaluru, Karnataka.",
    },
]


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return s or "source"


def load_registry() -> List[Dict[str, Any]]:
    """Loads configured employer sources, initializing seeds if not present."""
    registry_path = _registry_path()
    if not registry_path.is_file():
        save_registry(DEFAULT_SEEDS)
        return DEFAULT_SEEDS.copy()
    try:
        data = json.loads(registry_path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        return DEFAULT_SEEDS.copy()
    except Exception:
        return DEFAULT_SEEDS.copy()


def save_registry(sources: List[Dict[str, Any]]) -> None:
    """Safely saves employer sources list with atomic file replacement."""
    registry_path = _registry_path()
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    temp = registry_path.with_suffix(".tmp")
    temp.write_text(json.dumps(sources, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(registry_path)


def list_employer_sources() -> List[Dict[str, Any]]:
    """Returns all employer sources."""
    return load_registry()


def get_employer_source(source_id: str) -> Optional[Dict[str, Any]]:
    """Finds an employer source by ID."""
    for s in load_registry():
        if s["id"] == source_id:
            return s
    return None


def add_employer_source(
    employer_name: str,
    official_domain: str,
    ats_provider: str,
    board_id: str,
    enabled: bool = True,
    notes: str = "",
) -> Dict[str, Any]:
    """Adds a new employer source to the registry."""
    sources = load_registry()
    p_lower = ats_provider.strip().lower()
    provider_map = {
        "greenhouse": "Greenhouse",
        "lever": "Lever",
        "smartrecruiters": "SmartRecruiters",
        "ashby": "Ashby",
        "workable": "Workable",
    }
    if p_lower not in provider_map:
        raise ValueError(f"Supported public ATS providers are: {', '.join(provider_map.values())}.")
    provider_clean = provider_map[p_lower]

    base_id = _slugify(f"{employer_name}-{provider_clean}")
    source_id = base_id
    counter = 1
    existing_ids = {s["id"] for s in sources}
    while source_id in existing_ids:
        source_id = f"{base_id}-{counter}"
        counter += 1

    new_source = {
        "id": source_id,
        "employer_name": employer_name.strip(),
        "official_domain": official_domain.strip().lower(),
        "ats_provider": provider_clean,
        "board_id": board_id.strip(),
        "status": "CONFIGURED" if board_id.strip() else "UNCONFIGURED",
        "enabled": bool(enabled),
        "last_check_time": None,
        "last_successful_check": None,
        "error_details": None,
        "jobs_discovered": 0,
        "notes": notes.strip(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    sources.append(new_source)
    save_registry(sources)
    return new_source


def update_employer_source(source_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    """Updates fields of an existing employer source."""
    sources = load_registry()
    target_idx = -1
    for i, s in enumerate(sources):
        if s["id"] == source_id:
            target_idx = i
            break
    if target_idx == -1:
        raise KeyError(f"Source with id '{source_id}' not found.")

    allowed = {
        "employer_name", "official_domain", "ats_provider", "board_id",
        "enabled", "notes", "status", "last_check_time", "last_successful_check",
        "error_details", "jobs_discovered",
    }
    for k, v in updates.items():
        if k in allowed:
            sources[target_idx][k] = v

    if "board_id" in updates:
        sources[target_idx]["status"] = "CONFIGURED" if updates["board_id"].strip() else "UNCONFIGURED"

    save_registry(sources)
    return sources[target_idx]


def delete_employer_source(source_id: str) -> bool:
    """Removes an employer source from the registry."""
    sources = load_registry()
    initial_len = len(sources)
    sources = [s for s in sources if s["id"] != source_id]
    if len(sources) < initial_len:
        save_registry(sources)
        return True
    return False


def record_source_check(
    source_id: str, success: bool, jobs_found: int = 0, error_message: str = ""
) -> None:
    """Updates operational statistics for an employer source check."""
    now_iso = datetime.now(timezone.utc).isoformat()
    sources = load_registry()
    for s in sources:
        if s["id"] == source_id:
            s["last_check_time"] = now_iso
            if success:
                s["last_successful_check"] = now_iso
                s["error_details"] = None
                s["jobs_discovered"] = jobs_found
                s["status"] = "OK"
            else:
                s["error_details"] = error_message
                s["status"] = "FAILED"
            break
    save_registry(sources)
