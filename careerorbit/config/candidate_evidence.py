"""Field-level provenance and editing for candidate facts.

The profile dictionary is not treated as evidence by itself. This module records
whether each displayed fact is backed by a source document or candidate
confirmation. Missing original documents therefore fail closed for resume output.
"""
from __future__ import annotations

import json
import re
import copy
import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from collections.abc import Mapping

from careerorbit.config.profile import CANDIDATE_PROFILE
from careerorbit.config.settings import SETTINGS, current_data_dir

EVIDENCE_STATES = {
    "CONFIRMED",
    "NEEDS_REVIEW",
    "NOT_PROVIDED",
    "VERIFIED_FROM_SOURCE",
    "CONFIRMED_BY_CANDIDATE",
    "REQUIRES_CONFIRMATION",
    "VERIFIED_PROFESSIONAL",
    "VERIFIED_PROJECT",
    "VERIFIED_CERTIFICATION",
    "LEARNING",
    "ASPIRATIONAL",
    "UNVERIFIED",
}

# The user explicitly identified the priority order and named these technologies
# as learning targets in the task instructions. That confirms preference only;
# it does not attest to hands-on skill.
CONFIRMED_USER_FIELDS = {
    "priority_roles",
    "documented_skills.learning_targets_cloud_data",
}
NOT_PROVIDED_FIELDS = {
    "personal.notice_period_days",
    "personal.availability_date",
}

MAX_EVIDENCE_FILE_SIZE = 10 * 1024 * 1024  # 10 MB limit
ALLOWED_EVIDENCE_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".docx"}
ALLOWED_DOCUMENT_TYPES = {
    "EDUCATION_DEGREE",
    "TRANSCRIPT",
    "EXPERIENCE_LETTER",
    "CERTIFICATE",
    "PROJECT_REPORT",
    "GOVERNMENT_ID",
    "OTHER",
}


def normalize_evidence_state(state: str) -> str:
    """Normalize state aliases into canonical audit strings."""
    s = (state or "").strip().upper()
    if s in ("CONFIRMED", "CONFIRMED_BY_CANDIDATE"):
        return "CONFIRMED_BY_CANDIDATE"
    if s in ("NEEDS_REVIEW", "REQUIRES_CONFIRMATION"):
        return "REQUIRES_CONFIRMATION"
    if s == "NOT_PROVIDED":
        return "NOT_PROVIDED"
    if s == "VERIFIED_FROM_SOURCE":
        return "VERIFIED_FROM_SOURCE"
    if s in (
        "VERIFIED_PROFESSIONAL",
        "VERIFIED_PROJECT",
        "VERIFIED_CERTIFICATION",
        "LEARNING",
        "ASPIRATIONAL",
        "UNVERIFIED",
    ):
        return s
    return "REQUIRES_CONFIRMATION"


def _leaf_paths(value: Any, prefix: str = ""):
    if isinstance(value, Mapping):
        for key, child in value.items():
            yield from _leaf_paths(child, f"{prefix}.{key}" if prefix else str(key))
    elif isinstance(value, list):
        if not value:
            yield prefix
        for index, child in enumerate(value):
            yield from _leaf_paths(child, f"{prefix}[{index}]")
    else:
        yield prefix


def _get_nested_val(obj: Any, path: str) -> Any:
    tokens = [t for t in re.split(r'\.|\b(?=\[)', path) if t]
    curr = obj
    try:
        for token in tokens:
            if token.startswith('[') and token.endswith(']'):
                curr = curr[int(token[1:-1])]
            else:
                curr = curr[token]
        return curr
    except Exception:
        return None


def _set_nested_val(obj: Any, path: str, val: Any) -> None:
    tokens = [t for t in re.split(r'\.|\b(?=\[)', path) if t]
    curr = obj
    for token in tokens[:-1]:
        if token.startswith('[') and token.endswith(']'):
            curr = curr[int(token[1:-1])]
        else:
            curr = curr[token]
    last = tokens[-1]
    if last.startswith('[') and last.endswith(']'):
        curr[int(last[1:-1])] = val
    else:
        curr[last] = val


def load_candidate_profile_overrides() -> None:
    """Apply persistent overrides from candidate edits onto CANDIDATE_PROFILE."""
    overrides_path = current_data_dir() / "candidate_profile_overrides.json"
    if overrides_path.is_file():
        try:
            overrides = json.loads(overrides_path.read_text(encoding="utf-8"))
            for path, val in overrides.items():
                _set_nested_val(CANDIDATE_PROFILE, path, val)
        except Exception:
            pass


# Automatically load overrides on import
load_candidate_profile_overrides()


def get_candidate_evidence() -> list[dict[str, str]]:
    """Return an explicit state for every current profile leaf and known omission."""
    persisted: dict[str, dict[str, str]] = {}
    registry_path = current_data_dir() / "candidate_evidence.json"
    try:
        if registry_path.is_file():
            persisted = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        persisted = {}
    if not isinstance(persisted, dict):
        persisted = {}
    fields: list[dict[str, str]] = []
    for path in _leaf_paths(CANDIDATE_PROFILE):
        if path in CONFIRMED_USER_FIELDS or (
            path.startswith("priority_roles.") and path.rsplit(".", 1)[-1] == "category"
        ):
            state = "CONFIRMED_BY_CANDIDATE"
            evidence = "Explicitly stated priority category in the user's task."
        elif path.startswith("documented_skills.learning_targets_cloud_data["):
            state = "CONFIRMED_BY_CANDIDATE"
            evidence = "Explicitly identified as a learning target in the user's task."
        else:
            state = "REQUIRES_CONFIRMATION"
            evidence = "No original candidate source document is present; the legacy profile is not independent evidence."
        fields.append({"field": path, **persisted.get(path, {"state": state, "evidence": evidence})})
    for path in sorted(NOT_PROVIDED_FIELDS):
        fields.append({"field": path, "state": "NOT_PROVIDED", "evidence": "No value supplied."})
    return fields


def get_candidate_claims() -> list[dict[str, Any]]:
    """Return legacy profile values for local review, excluding contact values."""
    hidden = {"personal.email", "personal.phone", "personal.linkedin", "personal.github"}
    evidence = {row["field"]: row for row in get_candidate_evidence()}
    claims: list[dict[str, Any]] = []

    def walk(value: Any, prefix: str = "") -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                path = f"{prefix}.{key}" if prefix else str(key)
                walk(child, path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{prefix}[{index}]")
        else:
            claims.append({
                "field": prefix,
                "legacy_value": "[withheld]" if prefix in hidden else value,
                "state": evidence.get(prefix, {}).get("state", "REQUIRES_CONFIRMATION"),
                "evidence": evidence.get(prefix, {}).get("evidence", "No original candidate source document is present."),
            })

    walk(CANDIDATE_PROFILE)
    return claims


def candidate_profile_ready_for_resume() -> bool:
    return all(row["state"] in {"VERIFIED_FROM_SOURCE", "CONFIRMED_BY_CANDIDATE", "NOT_PROVIDED"}
               for row in get_candidate_evidence())



def validate_evidence_document(file_bytes: bytes, filename: str) -> tuple[bool, str]:
    """Validates candidate evidence document format, magic bytes, and size."""
    if not file_bytes:
        return False, "File is empty (0 bytes)."
    if len(file_bytes) > MAX_EVIDENCE_FILE_SIZE:
        return False, f"File size exceeds maximum allowed limit of {MAX_EVIDENCE_FILE_SIZE // (1024 * 1024)} MB."
    
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EVIDENCE_EXTENSIONS:
        return False, f"File extension '{ext}' is not supported. Allowed formats: {sorted(ALLOWED_EVIDENCE_EXTENSIONS)}"
    
    # Magic bytes check
    if ext == ".pdf" and not file_bytes.startswith(b"%PDF-"):
        return False, "Invalid PDF file: Missing %PDF- file header."
    elif ext == ".png" and not file_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return False, "Invalid PNG file: Missing PNG signature."
    elif ext in (".jpg", ".jpeg") and not file_bytes.startswith(b"\xff\xd8\xff"):
        return False, "Invalid JPEG file: Missing JPEG SOI marker."
    elif ext == ".docx" and not file_bytes.startswith(b"PK\x03\x04"):
        return False, "Invalid DOCX file: Missing ZIP archive header."

    return True, "Valid"


def get_evidence_documents_dir() -> Path:
    d = current_data_dir() / "evidence_documents"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _get_evidence_documents_registry_path() -> Path:
    return current_data_dir() / "candidate_evidence_documents.json"


def list_evidence_documents() -> list[dict[str, Any]]:
    """List all source documents in the candidate evidence registry."""
    reg_path = _get_evidence_documents_registry_path()
    if not reg_path.exists():
        return []
    try:
        data = json.loads(reg_path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def upload_evidence_document(
    file_bytes: bytes,
    filename: str,
    doc_type: str = "OTHER",
    notes: str = "",
    author: str = "Candidate"
) -> dict[str, Any]:
    """Saves a verified candidate source document to private storage and registers it."""
    valid, err_msg = validate_evidence_document(file_bytes, filename)
    if not valid:
        raise ValueError(err_msg)
    
    norm_doc_type = doc_type.upper().strip() if doc_type else "OTHER"
    if norm_doc_type not in ALLOWED_DOCUMENT_TYPES:
        norm_doc_type = "OTHER"
    
    doc_id = f"doc_{uuid.uuid4().hex[:12]}"
    clean_fn = re.sub(r'[^a-zA-Z0-9_\.-]', '_', Path(filename).name)
    stored_fn = f"{doc_id}_{clean_fn}"
    
    docs_dir = get_evidence_documents_dir()
    file_path = docs_dir / stored_fn
    file_path.write_bytes(file_bytes)
    
    sha256 = hashlib.sha256(file_bytes).hexdigest()
    now_iso = datetime.now(timezone.utc).isoformat()
    
    doc_record = {
        "id": doc_id,
        "filename": Path(filename).name,
        "stored_filename": stored_fn,
        "file_size": len(file_bytes),
        "sha256": sha256,
        "doc_type": norm_doc_type,
        "notes": (notes or "").strip()[:500],
        "uploaded_at": now_iso,
        "uploaded_by": author,
        "verified_fields": []
    }
    
    docs = list_evidence_documents()
    docs.append(doc_record)
    reg_path = _get_evidence_documents_registry_path()
    temp_path = reg_path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(docs, indent=2, ensure_ascii=False), encoding="utf-8")
    temp_path.replace(reg_path)
    
    # Audit log
    history_path = current_data_dir() / "candidate_profile_history.jsonl"
    audit_entry = {
        "timestamp": now_iso,
        "action": "DOCUMENT_UPLOAD",
        "document_id": doc_id,
        "filename": doc_record["filename"],
        "doc_type": norm_doc_type,
        "sha256": sha256,
        "author": author,
    }
    with open(history_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(audit_entry, ensure_ascii=False) + "\n")
        
    return doc_record


def get_evidence_document(doc_id: str) -> tuple[dict[str, Any], bytes]:
    """Retrieve document metadata and binary contents from private storage."""
    docs = list_evidence_documents()
    for d in docs:
        if d.get("id") == doc_id:
            file_path = get_evidence_documents_dir() / d["stored_filename"]
            if not file_path.exists():
                raise FileNotFoundError(f"Document file {d['stored_filename']} not found on disk.")
            return d, file_path.read_bytes()
    raise KeyError(f"Document with ID '{doc_id}' not found.")


def delete_evidence_document(doc_id: str, author: str = "Candidate") -> bool:
    """Deletes an evidence document and downgrades any linked verified fields to REQUIRES_CONFIRMATION."""
    docs = list_evidence_documents()
    doc_to_delete = None
    remaining = []
    for d in docs:
        if d.get("id") == doc_id:
            doc_to_delete = d
        else:
            remaining.append(d)
    if not doc_to_delete:
        return False
        
    # Delete file from disk
    stored_fn = doc_to_delete.get("stored_filename")
    if stored_fn:
        file_path = get_evidence_documents_dir() / stored_fn
        if file_path.exists():
            try:
                file_path.unlink()
            except OSError:
                pass
                
    # Update registry
    reg_path = _get_evidence_documents_registry_path()
    temp_path = reg_path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(remaining, indent=2, ensure_ascii=False), encoding="utf-8")
    temp_path.replace(reg_path)
    
    # Downgrade linked fields in candidate_evidence.json
    ev_path = current_data_dir() / "candidate_evidence.json"
    if ev_path.exists():
        try:
            ev_data = json.loads(ev_path.read_text(encoding="utf-8"))
            modified = False
            for f, record in ev_data.items():
                if record.get("document_id") == doc_id:
                    record["state"] = "REQUIRES_CONFIRMATION"
                    record["evidence"] = f"Supporting document '{doc_to_delete.get('filename')}' was deleted; requires re-verification."
                    record["document_id"] = None
                    record["reviewed_at"] = datetime.now(timezone.utc).isoformat()
                    modified = True
            if modified:
                ev_path.write_text(json.dumps(ev_data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
            
    # Audit log
    now_iso = datetime.now(timezone.utc).isoformat()
    history_path = current_data_dir() / "candidate_profile_history.jsonl"
    audit_entry = {
        "timestamp": now_iso,
        "action": "DOCUMENT_DELETION",
        "document_id": doc_id,
        "filename": doc_to_delete.get("filename"),
        "author": author,
    }
    with open(history_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(audit_entry, ensure_ascii=False) + "\n")
        
    return True


def link_document_to_field(
    field: str,
    doc_id: str,
    notes: str = "",
    author: str = "Candidate"
) -> dict[str, Any]:
    """Links an uploaded source document to a profile field, marking it VERIFIED_FROM_SOURCE."""
    docs = list_evidence_documents()
    doc_record = None
    for d in docs:
        if d.get("id") == doc_id:
            doc_record = d
            break
    if not doc_record:
        raise KeyError(f"Document with ID '{doc_id}' not found.")
        
    current = {row["field"] for row in get_candidate_evidence()}
    if field not in current:
        raise KeyError(f"Unknown candidate field '{field}'")
        
    reference = f"Verified from document: {doc_record['filename']} ({doc_record['doc_type']})"
    if notes:
        reference += f" — {notes.strip()}"
        
    ev_result = set_candidate_field_evidence(
        field=field,
        state="VERIFIED_FROM_SOURCE",
        evidence=reference,
        document_id=doc_id,
    )
    
    # Record linked field in document record
    if field not in doc_record.get("verified_fields", []):
        doc_record.setdefault("verified_fields", []).append(field)
        reg_path = _get_evidence_documents_registry_path()
        reg_path.write_text(json.dumps(docs, indent=2, ensure_ascii=False), encoding="utf-8")
        
    # Audit log
    now_iso = datetime.now(timezone.utc).isoformat()
    history_path = current_data_dir() / "candidate_profile_history.jsonl"
    audit_entry = {
        "timestamp": now_iso,
        "action": "FIELD_VERIFIED_FROM_SOURCE",
        "field": field,
        "document_id": doc_id,
        "filename": doc_record["filename"],
        "author": author,
        "notes": notes,
    }
    with open(history_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(audit_entry, ensure_ascii=False) + "\n")
        
    return {
        "field": ev_result,
        "document": doc_record,
        "summary": candidate_evidence_summary()
    }


def set_candidate_field_evidence(
    field: str, state: str, evidence: str, document_id: str | None = None
) -> dict[str, str]:
    """Persist a user's field review without changing or inventing the claim value."""
    norm_state = normalize_evidence_state(state)
    current = {row["field"] for row in get_candidate_evidence()}
    if field not in current:
        raise KeyError(f"Unknown candidate field '{field}'")
    if norm_state == "NOT_PROVIDED" and field not in NOT_PROVIDED_FIELDS:
        raise ValueError("A field with a stored claim cannot be marked not provided")
    reference = (evidence or "").strip()[:500]
    if norm_state == "CONFIRMED_BY_CANDIDATE" and not reference:
        raise ValueError("A candidate confirmation note is required")
    if norm_state == "VERIFIED_FROM_SOURCE":
        if document_id:
            docs = list_evidence_documents()
            if not any(d.get("id") == document_id for d in docs):
                raise ValueError(f"Document ID '{document_id}' not found in candidate evidence registry.")
        elif not reference or reference == "No original candidate source document is present; the legacy profile is not independent evidence.":
            raise ValueError("Cannot mark field as VERIFIED_FROM_SOURCE without an uploaded source document or verified reference note.")

    registry_path = current_data_dir() / "candidate_evidence.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    saved: dict[str, dict[str, Any]] = {}
    if registry_path.exists():
        try:
            saved = json.loads(registry_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            saved = {}
    saved[field] = {
        "state": norm_state,
        "evidence": reference or "No value supplied.",
        "document_id": document_id,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
    }
    temporary = registry_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(registry_path)
    return {"field": field, **saved[field]}


def update_candidate_field_value(
    field: str, new_value: Any, state: str = "CONFIRMED", note: str = "", author: str = "Candidate"
) -> dict[str, Any]:
    """Updates candidate field value, records edit history, and marks evidence state."""
    if not isinstance(field, str) or not field:
        raise ValueError("A candidate profile field is required")
    if not isinstance(state, str):
        raise ValueError("Evidence state must be text")
    if not isinstance(note, str) or not isinstance(author, str):
        raise ValueError("Evidence note and author must be text")

    # Validate the target and evidence transition before changing the shared
    # profile or writing its override. In particular, NOT_PROVIDED is only
    # valid for the explicitly absent fields; rejecting it after mutation used
    # to leave a changed value behind even though the endpoint returned 400.
    existing_fields = {row["field"] for row in get_candidate_evidence()}
    if field not in existing_fields:
        raise KeyError(f"Unknown candidate field '{field}'")
    normalized_state = normalize_evidence_state(state)
    if normalized_state == "NOT_PROVIDED" and field not in NOT_PROVIDED_FIELDS:
        raise ValueError("A field with a stored claim cannot be marked not provided")

    old_val = _get_nested_val(CANDIDATE_PROFILE, field)
    proposed_profile = copy.deepcopy(CANDIDATE_PROFILE)
    try:
        _set_nested_val(proposed_profile, field, new_value)
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ValueError("The updated value does not fit the existing candidate field") from exc
    if field not in {path for path in _leaf_paths(proposed_profile)}:
        raise ValueError("The updated value must preserve the existing candidate field structure")

    # Evidence persistence is now safe from user-input validation failures;
    # apply the profile value only after the evidence transition is accepted.
    evidence_res = set_candidate_field_evidence(
        field, state=normalized_state, evidence=note or f"Updated and confirmed by {author}"
    )

    _set_nested_val(CANDIDATE_PROFILE, field, new_value)

    # Persist override
    overrides_path = current_data_dir() / "candidate_profile_overrides.json"
    overrides_path.parent.mkdir(parents=True, exist_ok=True)
    overrides: dict[str, Any] = {}
    if overrides_path.exists():
        try:
            overrides = json.loads(overrides_path.read_text(encoding="utf-8"))
        except Exception:
            overrides = {}
    overrides[field] = new_value
    temp_ov = overrides_path.with_suffix(".tmp")
    temp_ov.write_text(json.dumps(overrides, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_ov.replace(overrides_path)

    # Append to change history log
    history_path = current_data_dir() / "candidate_profile_history.jsonl"
    now_iso = datetime.now(timezone.utc).isoformat()
    record = {
        "timestamp": now_iso,
        "field": field,
        "old_value": old_val,
        "new_value": new_value,
        "state": evidence_res.get("state"),
        "note": note or f"Edited by {author}",
        "author": author,
    }
    with open(history_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return {
        "field": field,
        "new_value": new_value,
        "evidence": evidence_res,
        "summary": candidate_evidence_summary(),
    }


def get_profile_change_history(limit: int = 50) -> list[dict[str, Any]]:
    """Return recent candidate profile edits from history log."""
    history_path = current_data_dir() / "candidate_profile_history.jsonl"
    if not history_path.exists():
        return []
    records = []
    try:
        lines = history_path.read_text(encoding="utf-8").splitlines()
        for line in reversed(lines[-limit:]):
            if line.strip():
                try:
                    records.append(json.loads(line))
                except Exception:
                    pass
    except Exception:
        pass
    return records


def candidate_evidence_summary() -> dict[str, Any]:
    fields = get_candidate_evidence()
    v_src = sum(row["state"] == "VERIFIED_FROM_SOURCE" for row in fields)
    c_cand = sum(row["state"] == "CONFIRMED_BY_CANDIDATE" for row in fields)
    r_conf = sum(row["state"] == "REQUIRES_CONFIRMATION" for row in fields)
    n_prov = sum(row["state"] == "NOT_PROVIDED" for row in fields)
    last_reviewed = max((row.get("reviewed_at") for row in fields if row.get("reviewed_at")), default=None)
    return {
        "ready_for_resume": candidate_profile_ready_for_resume(),
        "total_fields": len(fields),
        "confirmed_count": v_src + c_cand,
        "needs_review_count": r_conf,
        "not_provided_count": n_prov,
        "verified_from_source": v_src,
        "confirmed_by_candidate": c_cand,
        "requires_confirmation": r_conf,
        "not_provided": n_prov,
        "last_reviewed_at": last_reviewed,
    }


def export_profile_snapshot() -> dict[str, Any]:
    """Export a verifiable, tamper-evident snapshot of candidate facts and verification states."""
    import hashlib
    summary = candidate_evidence_summary()
    fields = get_candidate_evidence()
    claims = get_candidate_claims()
    now_iso = datetime.now(timezone.utc).isoformat()

    snapshot_payload = {
        "project": "CareerOrbit AI",
        "candidate": CANDIDATE_PROFILE["personal"]["full_name"],
        "exported_at": now_iso,
        "summary": summary,
        "claims": claims,
        "evidence_audit": fields,
    }
    canonical_bytes = json.dumps(snapshot_payload, sort_keys=True).encode("utf-8")
    integrity_hash = hashlib.sha256(canonical_bytes).hexdigest()
    snapshot_payload["integrity_sha256"] = integrity_hash
    return snapshot_payload


def get_profile_with_evidence() -> dict[str, Any]:
    """Returns a rich view of candidate profile sections with field-level evidence states."""
    evidence_map = {row["field"]: row for row in get_candidate_evidence()}
    return {
        "personal": {
            "full_name": {"value": CANDIDATE_PROFILE["personal"]["full_name"], **evidence_map.get("personal.full_name", {})},
            "location": {"value": CANDIDATE_PROFILE["personal"]["location"], **evidence_map.get("personal.location", {})},
            "work_authorization": {"value": CANDIDATE_PROFILE["personal"]["work_authorization"], **evidence_map.get("personal.work_authorization", {})},
            "experience_level": {"value": CANDIDATE_PROFILE["personal"]["experience_level"], **evidence_map.get("personal.experience_level", {})},
            "notice_period_status": {"value": CANDIDATE_PROFILE["personal"]["notice_period_status"], **evidence_map.get("personal.notice_period_status", {})},
            "salary_expectation": {"value": CANDIDATE_PROFILE["personal"]["salary_expectation"], **evidence_map.get("personal.salary_expectation", {})},
            "daily_study_hours": {"value": CANDIDATE_PROFILE["personal"]["daily_study_hours"], **evidence_map.get("personal.daily_study_hours", {})},
        },
        "education": {
            "degree": {"value": CANDIDATE_PROFILE["education"]["degree"], **evidence_map.get("education.degree", {})},
            "field_of_study": {"value": CANDIDATE_PROFILE["education"]["field_of_study"], **evidence_map.get("education.field_of_study", {})},
            "institution": {"value": CANDIDATE_PROFILE["education"]["institution"], **evidence_map.get("education.institution", {})},
            "graduation_year": {"value": CANDIDATE_PROFILE["education"]["graduation_year"], **evidence_map.get("education.graduation_year", {})},
            "cgpa": {"value": CANDIDATE_PROFILE["education"]["cgpa"], **evidence_map.get("education.cgpa", {})},
        },
        "employment": CANDIDATE_PROFILE["employment"],
        "documented_skills": CANDIDATE_PROFILE["documented_skills"],
        "projects": CANDIDATE_PROFILE["projects"],
        "certifications": CANDIDATE_PROFILE["certifications"],
        "priority_roles": CANDIDATE_PROFILE["priority_roles"],
        "summary": candidate_evidence_summary(),
    }
