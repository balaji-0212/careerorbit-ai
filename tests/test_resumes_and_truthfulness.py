"""Tests for ATS resume tailoring, truthfulness checks, PDF generation, and DOCX generation."""
from pathlib import Path
import docx
from careerorbit.resumes.tailor import ResumeTailor
from careerorbit.resumes.pdf_builder import ATSPdfResumeBuilder
from careerorbit.resumes.docx_builder import ATSDocxResumeBuilder
from careerorbit.config.candidate_evidence import get_candidate_evidence, candidate_profile_ready_for_resume
from careerorbit.config.settings import SETTINGS

def test_resume_tailor_selection():
    tailor = ResumeTailor()
    # Priority 1: Data Analyst
    res_da = tailor.analyze_tailoring("Junior Data Analyst", "Power BI, DAX, SQL Server", 1)
    assert res_da["source_type"] == "data_analyst"
    assert "Power BI" in res_da["supported_keywords"] or "Power Bi" in res_da["supported_keywords"]
    assert res_da["education"]["institution"]

    # Priority 3: Software Engineer
    res_swe = tailor.analyze_tailoring("Associate Software Engineer", "Python, FastAPI, Git, REST APIs", 3)
    assert res_swe["source_type"] == "software_engineer"
    assert "FastAPI" in res_swe["supported_keywords"] or "Python" in res_swe["supported_keywords"]

def test_candidate_claims_are_explicitly_unverified_until_a_source_is_provided():
    statuses = {item["state"] for item in get_candidate_evidence()}
    assert "REQUIRES_CONFIRMATION" in statuses
    assert "NOT_PROVIDED" in statuses
    assert any(item["field"] == "personal.email" and item["state"] == "REQUIRES_CONFIRMATION"
               for item in get_candidate_evidence())
    assert any(item["field"].startswith("documented_skills.learning_targets_cloud_data")
               and item["state"] == "CONFIRMED_BY_CANDIDATE" for item in get_candidate_evidence())
    assert candidate_profile_ready_for_resume() is False

def test_actual_pdf_and_docx_generation(tmp_path):
    tailor = ResumeTailor()
    tailored = tailor.analyze_tailoring("Power BI Developer", "Power BI, SQL, DAX, Excel", 1)

    pdf_builder = ATSPdfResumeBuilder()
    pdf_path = pdf_builder.generate_pdf(
        tailored_data=tailored,
        company_name="Bosch",
        role_title="Power BI Developer",
        output_dir=tmp_path
    )
    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 1000
    # Check valid PDF header
    with open(pdf_path, "rb") as f:
        header = f.read(5)
        assert header == b"%PDF-"

    docx_builder = ATSDocxResumeBuilder()
    docx_path = docx_builder.generate_docx(
        tailored_data=tailored,
        company_name="Bosch",
        role_title="Power BI Developer",
        output_dir=tmp_path
    )
    assert docx_path.exists()
    assert docx_path.stat().st_size > 5000

    # Verify DOCX can be opened and parsed
    doc = docx.Document(str(docx_path))
    full_text = " ".join(p.text for p in doc.paragraphs)
    assert "ALEX EXAMPLE" in full_text
    assert "Example State University" in full_text
    assert "Example Systems" in full_text
