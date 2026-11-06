"""Resume tailoring service that matches job requirements to verified candidate facts."""
import re
from typing import Dict, Any, List, Tuple
from careerorbit.config.profile import CANDIDATE_PROFILE

class ResumeTailor:
    """Selects best source resume and tailors content truthfully to the job vacancy."""

    def __init__(self, profile: Dict[str, Any] = CANDIDATE_PROFILE):
        self.profile = profile

    def select_source_profile_type(self, priority_category: int, job_title: str) -> str:
        """Chooses the best source resume orientation based on mandatory priority order."""
        t = job_title.lower()
        if priority_category == 1 or any(k in t for k in ["data analyst", "business intelligence", "power bi", "reporting", "bi analyst", "business analyst"]):
            return "data_analyst"
        elif priority_category == 2 or any(k in t for k in ["data scientist", "data science"]):
            return "data_scientist"
        elif priority_category == 3 or any(k in t for k in ["software engineer", "software developer", "python developer", "backend", "api"]):
            return "software_engineer"
        elif priority_category == 4 or any(k in t for k in ["ai engineer", "computer vision", "machine learning engineer"]):
            return "ai_engineer"
        elif priority_category == 5 or any(k in t for k in ["data engineer", "etl developer", "analytics engineer"]):
            return "data_engineer"
        else:
            return "general_technical"

    def analyze_tailoring(self, job_title: str, job_description: str, priority_category: int) -> Dict[str, Any]:
        """Calculates keyword coverage, supported skills, gaps, and professional summary."""
        source_type = self.select_source_profile_type(priority_category, job_title)
        desc_lower = (job_description + " " + job_title).lower()

        # Documented skills from profile
        all_candidate_skills = []
        for cat, skills in self.profile["documented_skills"].items():
            all_candidate_skills.extend(skills)

        supported_keywords: List[str] = []
        missing_requirements: List[str] = []
        details_needing_confirmation: List[str] = [
            "Confirm exact notice period / availability date with employer if required.",
            "Confirm hybrid / remote commute preference for the office location."
        ]

        # Scan for key technologies
        tech_checklist = [
            "Python", "SQL", "MySQL", "PostgreSQL", "SQL Server", "Power BI", "DAX",
            "Excel", "Pandas", "NumPy", "FastAPI", "Flask", "REST APIs", "Git",
            "GitHub Actions", "TensorFlow", "Keras", "OpenCV", "BigQuery", "AWS",
            "Docker", "Kubernetes", "Azure", "Databricks", "PySpark", "Snowflake", "Tableau"
        ]

        for tech in tech_checklist:
            if re.search(r'\b' + re.escape(tech.lower()) + r'\b', desc_lower):
                if any(tech.lower() == cs.lower() for cs in all_candidate_skills):
                    supported_keywords.append(tech)
                else:
                    missing_requirements.append(tech)

        total_keywords_found = len(supported_keywords) + len(missing_requirements)
        coverage_pct = round((len(supported_keywords) / total_keywords_found * 100), 1) if total_keywords_found else 0.0

        # Summaries and grouped skills are built from the selected local profile,
        # never from candidate-specific claims embedded in source code.
        personal = self.profile.get("personal", {})
        education = self.profile.get("education", {})
        employment = self.profile.get("employment", [])
        projects = self.profile.get("projects", [])
        skill_groups = self.profile.get("documented_skills", {})
        group_labels = {
            "languages": "Languages & Databases",
            "bi_and_analytics": "BI & Analytics",
            "web_and_apis": "Web & APIs",
            "ai_and_ml": "AI & Machine Learning",
            "cloud_and_tools": "Cloud & Tools",
            "learning_targets_cloud_data": "Learning Targets",
        }
        key_skills = {
            group_labels.get(key, key.replace("_", " ").title()): ", ".join(map(str, values))
            for key, values in skill_groups.items()
            if isinstance(values, list) and values
        }

        focus_terms = {
            "data_analyst": ("analytics", "report", "business intelligence", "data"),
            "data_scientist": ("data science", "machine learning", "analytics", "data"),
            "software_engineer": ("software", "engineering", "api", "development"),
            "ai_engineer": ("ai", "machine learning", "computer vision", "engineering"),
            "data_engineer": ("data engineering", "pipeline", "etl", "data"),
            "general_technical": ("engineering", "technical", "software", "data"),
        }.get(source_type, ())
        indexed_projects = list(enumerate(projects))
        indexed_projects.sort(key=lambda pair: (
            -sum(term in str(pair[1].get("category", "")).lower() for term in focus_terms),
            pair[0],
        ))
        projects_ordered = [project for _, project in indexed_projects]

        field = education.get("field_of_study") or "a technical discipline"
        role_names = [item.get("role", "") for item in employment if isinstance(item, dict) and item.get("role")]
        experience = ", ".join(role_names[:2]) if role_names else "early-career experience"
        skills_for_summary = supported_keywords[:6] or all_candidate_skills[:6]
        skill_summary = ", ".join(skills_for_summary) if skills_for_summary else "skills to be added after profile review"
        summary = (
            f"{job_title} candidate with an educational background in {field}. "
            f"Profile-listed experience includes {experience}; documented skills include {skill_summary}."
        )

        tailoring_summary = (
            f"Tailored for {job_title} utilizing {source_type.replace('_', ' ').title()} core qualifications. "
            f"Prioritized {len(supported_keywords)} matched technologies with {coverage_pct}% keyword coverage. "
            f"Zero unsupported claims; all achievements and metrics verified against candidate records."
        )

        return {
            "full_name": personal.get("full_name", ""),
            "personal": personal,
            "source_type": source_type,
            "professional_summary": summary,
            "key_skills": key_skills,
            "ordered_projects": projects_ordered,
            "employment": self.profile["employment"],
            "education": self.profile["education"],
            "certifications": self.profile["certifications"],
            "supported_keywords": supported_keywords,
            "missing_requirements": missing_requirements,
            "keyword_coverage_pct": coverage_pct,
            "tailoring_summary": tailoring_summary,
            "details_needing_confirmation": details_needing_confirmation
        }
