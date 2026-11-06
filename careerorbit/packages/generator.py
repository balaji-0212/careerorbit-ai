"""Application package generator creating truthful cover letters, application answers, outreach drafts, and approval gates."""
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from careerorbit.config.profile import CANDIDATE_PROFILE
from careerorbit.resumes.generator import ResumeService
from careerorbit.database.db import (
    create_or_update_application, get_application_by_job_id, confirm_user_submission
)
from careerorbit.models.schemas import Application, ApplicationStatus, RecruiterOutreachStatus
from careerorbit.config.candidate_evidence import candidate_profile_ready_for_resume, get_candidate_evidence

class ApplicationPackageGenerator:
    """Prepares complete job application packages under strict candidate approval controls."""

    def __init__(self):
        self.profile = CANDIDATE_PROFILE
        self.resume_service = ResumeService()

    def _confirmed(self, field: str) -> bool:
        verified_states = {"VERIFIED_FROM_SOURCE", "CONFIRMED_BY_CANDIDATE"}
        return any(row.get("field") == field and row.get("state") in verified_states
                   for row in get_candidate_evidence())

    def _profile_summary(self) -> str:
        education = self.profile.get("education", {})
        employment = self.profile.get("employment", [])
        details = []
        for key, label in (("degree", ""), ("field_of_study", "in "), ("institution", "from ")):
            value = education.get(key)
            if value and self._confirmed(f"education.{key}"):
                details.append(f"{label}{value}" if label else str(value))
        if employment and isinstance(employment[0], dict):
            role, employer = employment[0].get("role", ""), employment[0].get("employer", "")
            if role and employer and self._confirmed("employment[0].role") and self._confirmed("employment[0].employer"):
                details.append(f"experience as {role} at {employer}")
        return ", ".join(details) if details else "an early-career candidate with a profile under review"

    def build_cover_letter(self, company: str, role_title: str, priority_category: int, supported_skills: list) -> str:
        """Drafts a concise, professional, truthful cover letter."""
        skills_str = ", ".join(supported_skills[:4]) if supported_skills else "the skills documented in my reviewed profile"
        projects = self.profile.get("projects", [])
        project_name = "a relevant project in my reviewed profile"
        project_highlight = "Project details can be discussed during an interview."
        if candidate_profile_ready_for_resume() and projects:
            project = next((p for p in projects if priority_category == 1 and
                            any(word in str(p.get("category", "")).lower() for word in ("analytics", "data", "business"))), projects[0])
            project_name = project.get("name", project_name)
            highlights = project.get("highlights", [])
            if highlights:
                project_highlight = highlights[0]
        personal = self.profile.get("personal", {})
        candidate_name = personal.get("full_name", "") if self._confirmed("personal.full_name") else "Candidate"

        return (
            f"Dear Hiring Team at {company},\n\n"
            f"I am writing to express my strong interest in the {role_title} role at {company}. "
            f"My background includes {self._profile_summary()}. Relevant reviewed skills include {skills_str}.\n\n"
            f"A project in my profile, {project_name}, demonstrates this work: {project_highlight}\n\n"
            f"I would welcome the opportunity to discuss how my documented experience aligns with your team's needs.\n\n"
            f"Thank you for your time and consideration. I look forward to discussing how my experience aligns with your team's goals.\n\n"
            f"Sincerely,\n"
            f"{candidate_name}"
        )

    def build_application_answers(self, company: str, role_title: str) -> Dict[str, Any]:
        """Provides verified answers to standard job application questions."""
        education = self.profile.get("education", {})
        employment = self.profile.get("employment", [])
        work_auth = self.profile.get("personal", {}).get("work_authorization", "")
        work_auth_confirmed = bool(work_auth) and self._confirmed("personal.work_authorization")
        edu_keys = ("degree", "field_of_study", "institution", "graduation_year")
        education_confirmed = all(education.get(k) and self._confirmed(f"education.{k}") for k in edu_keys)
        education_answer = ", ".join(str(education[k]) for k in edu_keys) if education_confirmed else ""
        if education_confirmed and education.get("cgpa") and self._confirmed("education.cgpa"):
            education_answer += f", {education['cgpa']}"
        employment_answer = ""
        employment_confirmed = False
        if employment and isinstance(employment[0], dict):
            role, employer = employment[0].get("role", ""), employment[0].get("employer", "")
            employment_confirmed = bool(role and employer) and self._confirmed("employment[0].role") and self._confirmed("employment[0].employer")
            if employment_confirmed:
                employment_answer = f"{role} at {employer}"
        return {
            "work_authorization": {
                "question": "Are you legally authorized to work in the country of this position?",
                "answer": f"Work authorization: {work_auth}" if work_auth_confirmed else "",
                "verified": work_auth_confirmed,
                "note_to_user": "Confirm position-specific authorization requirements before submitting."
            },
            "visa_sponsorship": {
                "question": "Will you now or in the future require visa sponsorship?",
                "answer": "",
                "verified": False,
                "note_to_user": "Confirm visa sponsorship requirements for this position before submitting."
            },
            "notice_period": {
                "question": "What is your notice period / availability date?",
            "answer": "",
            "verified": False,
            "note_to_user": "Confirm the exact notice period and availability date before submitting."
            },
            "salary_expectations": {
                "question": "What are your salary expectations?",
            "answer": "",
            "verified": False,
            "note_to_user": "Add a salary expectation only after deciding what to disclose for this role."
            },
            "education": {
                "question": "Highest degree attained and year of graduation?",
                "answer": education_answer,
                "verified": education_confirmed,
                "note_to_user": "Confirm education details before submission." if not education_confirmed else ""
            },
            "current_employment": {
                "question": "Current employment status?",
                "answer": employment_answer,
                "verified": employment_confirmed,
                "note_to_user": "Confirm current employment details before submission." if not employment_confirmed else ""
            },
            "relocation": {
                "question": "Are you willing to relocate or work hybrid?",
                "answer": "",
                "verified": False,
                "note_to_user": "Confirm relocation and work arrangement preferences for this role."
            }
        }

    def build_recruiter_and_referral_drafts(self, company: str, role_title: str, official_url: str) -> Dict[str, Any]:
        """Creates personalized outreach drafts for recruiters and potential referrers."""
        personal = self.profile.get("personal", {})
        candidate_name = personal.get("full_name", "") if self._confirmed("personal.full_name") else "Candidate"
        skills = [skill for values in self.profile.get("documented_skills", {}).values()
                  if isinstance(values, list) for skill in values]
        skills_text = ", ".join(skills[:4]) if skills else "the reviewed skills in my profile"
        background = self._profile_summary()
        return {
            "referral_request": {
                "target_audience": f"Employees, alumni, or connections at {company}",
                "subject": f"Inquiry regarding {role_title} role at {company}",
                "message": (
                    f"Hi [Name],\n\n"
                    f"I hope you are having a productive week! I came across the {role_title} opening at {company} "
                    f"and was interested in learning more. My background includes {background}, with relevant skills in {skills_text}.\n\n"
                    f"If you feel comfortable, would you be open to providing an internal referral or pointing me toward the hiring manager? "
                    f"Here is the role link: {official_url}\n\n"
                    f"I would be glad to share my tailored resume and brief project portfolio. Thank you very much for your time and guidance!\n\n"
                    f"Best regards,\n{candidate_name}"
                ),
                "approval_status": "DRAFTED_AWAITING_USER_APPROVAL"
            },
            "recruiter_outreach": {
                "target_audience": f"Talent Acquisition / Technical Recruiter at {company}",
                "subject": f"Application for {role_title} - {candidate_name}",
                "message": (
                    f"Dear [Recruiter Name],\n\n"
                    f"I am interested in the {role_title} position at {company} and wanted to briefly introduce myself. "
                    f"My documented background includes {background}; relevant skills include {skills_text}.\n\n"
                    f"I would welcome the opportunity to connect for a quick 10-minute introductory call to discuss how my hands-on "
                    f"experience aligns with your team's immediate needs.\n\n"
                    f"Thank you for your consideration,\n{candidate_name}"
                ),
                "approval_status": "DRAFTED_AWAITING_USER_APPROVAL"
            },
            "follow_up_message": {
                "timing": "Send 5 business days after initial application if no response received",
                "message": (
                    f"Hi [Recruiter Name],\n\n"
                    f"I wanted to follow up on my recent application for the {role_title} role at {company}. "
                    f"I remain very enthusiastic about the opportunity to contribute to {company}'s projects and would be delighted "
                    f"to provide any further details or work samples.\n\n"
                    f"Thank you again for your time,\n{candidate_name}"
                )
            }
        }

    def prepare_package_for_job(self, job_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Generates resumes, cover letter, application answers, and registers application in database."""
        if not candidate_profile_ready_for_resume():
            raise ValueError("Candidate data needs source verification or candidate confirmation before package generation.")
        job_id = job_dict["id"]
        company = job_dict["employer"]
        title = job_dict["title"]
        desc = job_dict.get("description", "")
        p_cat = job_dict.get("priority_category", 1)
        supported_skills = job_dict.get("supported_skills", [])

        # 1. Generate tailored PDF and DOCX resumes
        resumes = self.resume_service.generate_resumes_for_job(
            job_id=job_id,
            company_name=company,
            role_title=title,
            job_description=desc,
            priority_category=p_cat
        )

        # 2. Build Cover Letter
        cover_letter = self.build_cover_letter(company, title, p_cat, supported_skills)

        # 3. Build Application Answers
        answers = self.build_application_answers(company, title)

        # 4. Build Outreach Drafts
        outreach = self.build_recruiter_and_referral_drafts(company, title, job_dict.get("official_url", ""))

        # 5. Persist to Applications table in AWAITING_APPROVAL state (strictly requiring user confirmation)
        now_iso = datetime.now(timezone.utc).isoformat()
        app_model = Application(
            job_id=job_id,
            selected_resume_path_pdf=resumes["pdf_path"],
            selected_resume_path_docx=resumes["docx_path"],
            resume_type=resumes["source_type"],
            resume_status="GENERATED",
            application_status=ApplicationStatus.AWAITING_APPROVAL,
            submission_confirmed_by_user=False,
            recruiter_outreach_status=RecruiterOutreachStatus.DRAFTED,
            cover_letter_text=cover_letter,
            application_answers=answers,
            outreach_messages=outreach,
            notes="Application package generated. Awaiting candidate explicit review and submission confirmation.",
            next_action="Review tailored resume and application package; submit via official employer portal; confirm in CareerOrbit.",
            created_at=now_iso,
            updated_at=now_iso
        )

        app_id = create_or_update_application(app_model)

        return {
            "application_id": app_id,
            "job_id": job_id,
            "company": company,
            "title": title,
            "resumes": resumes,
            "cover_letter": cover_letter,
            "application_answers": answers,
            "outreach_messages": outreach,
            "submission_status": "AWAITING_APPROVAL",
            "submission_confirmed_by_user": False
        }
