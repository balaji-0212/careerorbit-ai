"""Comprehensive tests for candidate evidence verification workflow.

Verifies:
1. File format, extension, and magic bytes validation.
2. File size limit enforcement (10 MB maximum).
3. Private storage, hashing, and isolation of candidate source documents.
4. Distinguishing candidate-confirmed vs. source-verified facts (anti-fabrication).
5. Document deletion downgrades linked verified fields.
6. Audit trail generation in profile change history.
7. REST API endpoints for evidence document upload, listing, retrieval, and field linking.
"""
import asyncio
import base64
import json
import pytest
from pathlib import Path

from careerorbit.config.profile import CANDIDATE_PROFILE
from careerorbit.config.settings import current_data_dir
from careerorbit.config.candidate_evidence import (
    validate_evidence_document,
    upload_evidence_document,
    list_evidence_documents,
    get_evidence_document,
    delete_evidence_document,
    link_document_to_field,
    set_candidate_field_evidence,
    get_candidate_evidence,
    candidate_evidence_summary,
    get_profile_change_history,
    MAX_EVIDENCE_FILE_SIZE,
)
from tests.authenticated_request import authenticated_headers


async def _raw_asgi_request(app, method="GET", path="/", query="", body=b"", headers=None):
    from tests.authenticated_request import authenticated_headers
    headers = authenticated_headers(method, headers)
    req_headers = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "path": path,
        "raw_path": path.encode(),
        "query_string": query.encode(),
        "headers": req_headers,
        "server": ("127.0.0.1", 8000),
        "client": ("127.0.0.1", 54321),
    }
    messages = []
    received = False

    async def receive():
        nonlocal received
        if not received:
            received = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        messages.append(message)

    await app(scope, receive, send)

    status_code = None
    response_headers = {}
    response_body = b""
    for msg in messages:
        if msg["type"] == "http.response.start":
            status_code = msg["status"]
            response_headers = {k.decode(): v.decode() for k, v in msg.get("headers", [])}
        elif msg["type"] == "http.response.body":
            response_body += msg.get("body", b"")
    return status_code, response_headers, response_body


def asgi_call(app, method="GET", path="/", query="", body=b"", headers=None):
    return asyncio.run(_raw_asgi_request(app, method=method, path=path, query=query, body=body, headers=headers))


def test_evidence_document_file_validation():
    """Verify accepted extensions, magic bytes, and size limits."""
    # 1. Valid PDF with %PDF- header
    valid_pdf = b"%PDF-1.4 sample synthetic degree certificate contents"
    ok, msg = validate_evidence_document(valid_pdf, "degree.pdf")
    assert ok is True
    assert msg == "Valid"

    # 2. Corrupt PDF without %PDF- header
    corrupt_pdf = b"NOT_A_PDF fake content"
    ok, msg = validate_evidence_document(corrupt_pdf, "degree.pdf")
    assert ok is False
    assert "Missing %PDF-" in msg

    # 3. Valid PNG
    valid_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    ok, msg = validate_evidence_document(valid_png, "cert.png")
    assert ok is True

    # 4. Valid JPEG
    valid_jpg = b"\xff\xd8\xff\xe0" + b"\x00" * 32
    ok, msg = validate_evidence_document(valid_jpg, "marksheet.jpg")
    assert ok is True

    # 5. Valid DOCX
    valid_docx = b"PK\x03\x04" + b"\x00" * 32
    ok, msg = validate_evidence_document(valid_docx, "experience.docx")
    assert ok is True

    # 6. Disallowed extension (.exe, .sh, .py)
    ok, msg = validate_evidence_document(b"echo hello", "script.sh")
    assert ok is False
    assert "not supported" in msg

    # 7. Empty file (0 bytes)
    ok, msg = validate_evidence_document(b"", "empty.pdf")
    assert ok is False
    assert "empty" in msg.lower()

    # 8. Oversized file (> 10 MB)
    oversized = b"%PDF-" + b"0" * (MAX_EVIDENCE_FILE_SIZE + 1024)
    ok, msg = validate_evidence_document(oversized, "big.pdf")
    assert ok is False
    assert "exceeds maximum allowed limit" in msg


def test_evidence_document_upload_and_storage(tmp_path):
    """Test uploading a synthetic source document and verifying metadata, SHA-256, and private storage."""
    pdf_bytes = b"%PDF-1.4 SYNTHETIC BACHELOR DEGREE CERTIFICATE - ANNA UNIVERSITY"
    doc = upload_evidence_document(
        file_bytes=pdf_bytes,
        filename="Anna_Univ_Degree.pdf",
        doc_type="EDUCATION_DEGREE",
        notes="Official provisional degree certificate",
        author="Candidate",
    )

    assert doc["id"].startswith("doc_")
    assert doc["filename"] == "Anna_Univ_Degree.pdf"
    assert doc["doc_type"] == "EDUCATION_DEGREE"
    assert doc["file_size"] == len(pdf_bytes)
    assert len(doc["sha256"]) == 64

    # Verify document listed in registry
    docs = list_evidence_documents()
    assert any(d["id"] == doc["id"] for d in docs)

    # Verify retrieval
    retrieved_meta, retrieved_bytes = get_evidence_document(doc["id"])
    assert retrieved_meta["filename"] == "Anna_Univ_Degree.pdf"
    assert retrieved_bytes == pdf_bytes


def test_anti_fabrication_cannot_mark_source_verified_without_document():
    """Verify that marking a fact as VERIFIED_FROM_SOURCE fails without an uploaded document or valid reference."""
    # Attempting to mark VERIFIED_FROM_SOURCE without any document or reference
    with pytest.raises(ValueError, match="Cannot mark field as VERIFIED_FROM_SOURCE"):
        set_candidate_field_evidence(
            field="education.degree",
            state="VERIFIED_FROM_SOURCE",
            evidence="",
        )

    # Attempting with invalid document ID
    with pytest.raises(ValueError, match="not found in candidate evidence registry"):
        set_candidate_field_evidence(
            field="education.degree",
            state="VERIFIED_FROM_SOURCE",
            evidence="Self-claimed degree",
            document_id="doc_nonexistent_123",
        )


def test_link_document_to_field_workflow():
    """Test linking an uploaded source document to verify candidate facts against source evidence."""
    # 1. Upload synthetic degree
    pdf_bytes = b"%PDF-1.4 SYNTHETIC DEGREE IN COMPUTER SCIENCE"
    doc = upload_evidence_document(
        file_bytes=pdf_bytes,
        filename="CS_Degree.pdf",
        doc_type="EDUCATION_DEGREE",
        notes="Graduation certificate",
    )

    # 2. Link to education.degree
    link_res = link_document_to_field(
        field="education.degree",
        doc_id=doc["id"],
        notes="Verified B.E. Computer Science against official degree certificate",
    )

    assert link_res["field"]["state"] == "VERIFIED_FROM_SOURCE"
    assert link_res["document"]["id"] == doc["id"]
    assert "education.degree" in link_res["document"]["verified_fields"]

    # 3. Confirm get_candidate_evidence reflects VERIFIED_FROM_SOURCE
    evidence_list = get_candidate_evidence()
    degree_ev = next(e for e in evidence_list if e["field"] == "education.degree")
    assert degree_ev["state"] == "VERIFIED_FROM_SOURCE"
    assert doc["id"] == degree_ev.get("document_id")

    # 4. Check audit log
    history = get_profile_change_history(limit=5)
    assert any(h.get("action") == "FIELD_VERIFIED_FROM_SOURCE" and h.get("field") == "education.degree" for h in history)


def test_candidate_confirmed_workflow():
    """Test candidate-confirmed facts require explicit non-empty candidate confirmation note."""
    # Attempting candidate confirmation with empty note must fail
    with pytest.raises(ValueError, match="candidate confirmation note is required"):
        set_candidate_field_evidence(
            field="personal.experience_level",
            state="CONFIRMED_BY_CANDIDATE",
            evidence="",
        )

    # Valid candidate confirmation
    res = set_candidate_field_evidence(
        field="personal.experience_level",
        state="CONFIRMED_BY_CANDIDATE",
        evidence="Candidate confirmed 0-1 years early career experience during onboarding.",
    )
    assert res["state"] == "CONFIRMED_BY_CANDIDATE"
    assert "Candidate confirmed" in res["evidence"]


def test_document_deletion_downgrades_linked_fields():
    """Verify that deleting a source document automatically downgrades linked verified fields to REQUIRES_CONFIRMATION."""
    # 1. Upload document and link to cgpa
    pdf_bytes = b"%PDF-1.4 SYNTHETIC TRANSCRIPT CGPA"
    doc = upload_evidence_document(
        file_bytes=pdf_bytes,
        filename="Transcript.pdf",
        doc_type="TRANSCRIPT",
        notes="Official semester transcript",
    )
    link_document_to_field("education.cgpa", doc["id"], notes="Verified CGPA 8.4")

    # Verify verified
    evidence_before = next(e for e in get_candidate_evidence() if e["field"] == "education.cgpa")
    assert evidence_before["state"] == "VERIFIED_FROM_SOURCE"

    # 2. Delete document
    deleted = delete_evidence_document(doc["id"])
    assert deleted is True

    # 3. Field must now be downgraded to REQUIRES_CONFIRMATION
    evidence_after = next(e for e in get_candidate_evidence() if e["field"] == "education.cgpa")
    assert evidence_after["state"] == "REQUIRES_CONFIRMATION"
    assert "was deleted; requires re-verification" in evidence_after["evidence"]
    assert evidence_after.get("document_id") is None


def test_api_candidate_evidence_document_endpoints():
    """Test REST API routes for uploading, retrieving, linking, and deleting candidate evidence documents."""
    from careerorbit.web.app import app

    # 1. GET /api/profile/evidence/documents (initially empty or list)
    code, _, resp_bytes = asgi_call(
        app, "GET", "/api/profile/evidence/documents",
        headers=authenticated_headers("GET")
    )
    assert code == 200
    initial_docs = json.loads(resp_bytes.decode("utf-8"))["documents"]
    assert isinstance(initial_docs, list)

    # 2. POST /api/profile/evidence/documents (upload via base64 JSON)
    pdf_bytes = b"%PDF-1.4 SYNTHETIC API EXPERIENCE LETTER - PYTHON DEVELOPER"
    payload = {
        "filename": "Experience_Letter.pdf",
        "file_base64": base64.b64encode(pdf_bytes).decode("ascii"),
        "doc_type": "EXPERIENCE_LETTER",
        "notes": "Relieving and experience letter",
    }
    code, _, resp_bytes = asgi_call(
        app, "POST", "/api/profile/evidence/documents",
        headers=authenticated_headers("POST", {"content-type": "application/json"}),
        body=json.dumps(payload).encode("utf-8"),
    )
    assert code == 200
    res = json.loads(resp_bytes.decode("utf-8"))
    assert res["status"] == "success"
    doc_id = res["document"]["id"]

    # 3. GET /api/profile/evidence/documents/{doc_id}
    code, _, resp_bytes = asgi_call(
        app, "GET", f"/api/profile/evidence/documents/{doc_id}",
        headers=authenticated_headers("GET")
    )
    assert code == 200
    doc_data = json.loads(resp_bytes.decode("utf-8"))
    assert doc_data["document"]["filename"] == "Experience_Letter.pdf"
    assert base64.b64decode(doc_data["content_base64"]) == pdf_bytes

    # 4. POST /api/profile/evidence/verify-field
    verify_payload = {
        "field": "education.degree",
        "document_id": doc_id,
        "notes": "Verified degree from official experience letter",
    }
    code, _, resp_bytes = asgi_call(
        app, "POST", "/api/profile/evidence/verify-field",
        headers=authenticated_headers("POST", {"content-type": "application/json"}),
        body=json.dumps(verify_payload).encode("utf-8"),
    )
    assert code == 200, f"Failed with {code}: {resp_bytes.decode('utf-8')}"
    v_res = json.loads(resp_bytes.decode("utf-8"))
    assert v_res["field"]["state"] == "VERIFIED_FROM_SOURCE"

    # 5. DELETE /api/profile/evidence/documents/{doc_id}
    code, _, resp_bytes = asgi_call(
        app, "DELETE", f"/api/profile/evidence/documents/{doc_id}",
        headers=authenticated_headers("DELETE")
    )
    assert code == 200
    del_res = json.loads(resp_bytes.decode("utf-8"))
    assert del_res["status"] == "deleted"

    # 6. Verify field downgraded
    evidence_list = get_candidate_evidence()
    deg_ev = next(e for e in evidence_list if e["field"] == "education.degree")
    assert deg_ev["state"] == "REQUIRES_CONFIRMATION"
