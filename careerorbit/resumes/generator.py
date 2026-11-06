"""Resume generator coordinator that builds PDF and DOCX files and records metadata."""
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Tuple

from careerorbit.config.settings import current_resumes_dir
from careerorbit.resumes.tailor import ResumeTailor
from careerorbit.resumes.pdf_builder import ATSPdfResumeBuilder
from careerorbit.resumes.docx_builder import ATSDocxResumeBuilder
from careerorbit.database.db import save_resume_metadata
from careerorbit.models.schemas import ResumeMetadata
from careerorbit.config.candidate_evidence import candidate_profile_ready_for_resume

class ResumeService:
    """Manages tailored ATS resume creation across PDF and DOCX."""

    def __init__(self):
        self.tailor = ResumeTailor()
        self.pdf_builder = ATSPdfResumeBuilder()
        self.docx_builder = ATSDocxResumeBuilder()

    def generate_resumes_for_job(
        self,
        job_id: int,
        company_name: str,
        role_title: str,
        job_description: str,
        priority_category: int
    ) -> Dict[str, Any]:
        """Generates role-specific PDF and DOCX resumes and stores audit metadata."""
        if not candidate_profile_ready_for_resume():
            raise ValueError("Candidate data needs source verification or candidate confirmation before resume generation.")
        tailored = self.tailor.analyze_tailoring(role_title, job_description, priority_category)

        pdf_path = self.pdf_builder.generate_pdf(
            tailored_data=tailored,
            company_name=company_name,
            role_title=role_title,
            output_dir=current_resumes_dir()
        )

        docx_path = self.docx_builder.generate_docx(
            tailored_data=tailored,
            company_name=company_name,
            role_title=role_title,
            output_dir=current_resumes_dir()
        )

        meta = ResumeMetadata(
            job_id=job_id,
            company_name=company_name,
            role_title=role_title,
            source_resume_type=tailored["source_type"],
            pdf_filename=pdf_path.name,
            pdf_path=str(pdf_path),
            docx_filename=docx_path.name,
            docx_path=str(docx_path),
            tailoring_summary=tailored["tailoring_summary"],
            supported_keywords=tailored["supported_keywords"],
            missing_requirements=tailored["missing_requirements"],
            keyword_coverage_pct=tailored["keyword_coverage_pct"],
            details_needing_confirmation=tailored["details_needing_confirmation"],
            created_at=datetime.now(timezone.utc).isoformat()
        )

        save_resume_metadata(meta)

        return {
            "pdf_path": str(pdf_path),
            "docx_path": str(docx_path),
            "pdf_filename": pdf_path.name,
            "docx_filename": docx_path.name,
            "source_type": tailored["source_type"],
            "tailoring_summary": tailored["tailoring_summary"],
            "supported_keywords": tailored["supported_keywords"],
            "missing_requirements": tailored["missing_requirements"],
            "keyword_coverage_pct": tailored["keyword_coverage_pct"],
            "details_needing_confirmation": tailored["details_needing_confirmation"]
        }
