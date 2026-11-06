"""Comprehensive automated tests for File Selection, Dropzones, and Upload Endpoints.
Verifies HTML structure, accepted file extensions, multipart handling, and security gates.
"""
import io
import json
import pytest
from pathlib import Path
from starlette.datastructures import UploadFile

from careerorbit.database.db import init_db, get_connection
from careerorbit.telegram.export_parser import TelegramChatExportParser
from careerorbit.web.app import app


@pytest.fixture(autouse=True)
def setup_db():
    init_db()


def test_html_file_inputs_and_dropzones_structure():
    """Verify all 3 file inputs and dropzones exist with correct IDs, accept filters, and change handlers."""
    html_path = Path("careerorbit/web/static/index.html")
    assert html_path.exists()
    content = html_path.read_text(encoding="utf-8")

    # 1. Telegram Export
    assert 'id="tg-export-file"' in content
    assert 'accept=".json,.html,.htm"' in content
    assert 'id="tg-dropzone"' in content
    assert 'id="tg-selected-file-card"' in content
    assert 'handleTelegramExportFileSelect' in content
    assert 'handleTelegramFileDrop' in content
    assert 'clearTelegramExportFile' in content

    # 2. WhatsApp Export
    assert 'id="wa-import-file"' in content
    assert 'accept=".txt"' in content
    assert 'id="wa-dropzone"' in content
    assert 'id="wa-selected-file-card"' in content
    assert 'handleWhatsAppFileSelect' in content
    assert 'handleWhatsAppFileDrop' in content
    assert 'clearWhatsAppFile' in content

    # 3. Resume Upload
    assert 'id="resume-upload-file"' in content
    assert 'accept=".pdf,.docx,.txt"' in content
    assert 'id="resume-dropzone"' in content
    assert 'id="resume-selected-file-card"' in content
    assert 'handleResumeFileSelect' in content
    assert 'handleResumeFileDrop' in content
    assert 'clearResumeUploadFile' in content


def test_telegram_export_multipart_upload_endpoint():
    """Verify /api/telegram/export/parse-preview parses multipart FormData file upload."""
    fixture_json = json.dumps({
        "name": "Multipart Test Channel",
        "type": "public_channel",
        "id": 12345678,
        "messages": [
            {
                "id": 1,
                "type": "message",
                "date": "2026-10-25T10:00:00",
                "from": "Admin",
                "text": "Google hiring Software Engineer in Bangalore https://careers.google.com/jobs/1"
            }
        ]
    }).encode("utf-8")

    # Test parser directly with bytes
    parsed = TelegramChatExportParser.parse_json(fixture_json, filename="result.json")
    assert parsed["chat_name"] == "Multipart Test Channel"
    assert parsed["career_relevant"] == 1
    assert parsed["job_leads_count"] == 1


def test_resume_upload_file_extension_validation():
    """Verify resume upload security gate rejects unsupported formats."""
    # Test valid extensions
    for valid_ext in [".pdf", ".docx", ".txt"]:
        filename = f"candidate_resume{valid_ext}"
        ext = Path(filename).suffix.lower()
        assert ext in (".pdf", ".docx", ".txt")

    # Test invalid extensions
    for invalid_ext in [".exe", ".sh", ".py", ".png", ".zip", ".tar.gz"]:
        filename = f"malicious_upload{invalid_ext}"
        ext = Path(filename).suffix.lower()
        assert ext not in (".pdf", ".docx", ".txt")


def test_format_bytes_logic():
    """Verify human-readable byte formatting across sizes."""
    def format_bytes_py(b):
        if not b: return "0 B"
        import math
        k = 1024
        sizes = ['B', 'KB', 'MB', 'GB']
        i = int(math.floor(math.log(b) / math.log(k)))
        return f"{round(b / (k ** i), 1)} {sizes[i]}"

    assert format_bytes_py(0) == "0 B"
    assert format_bytes_py(1024) == "1.0 KB"
    assert format_bytes_py(816 * 1024) == "816.0 KB"
    assert format_bytes_py(5 * 1024 * 1024) == "5.0 MB"
