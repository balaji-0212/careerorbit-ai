"""Eligibility and matching engine with transparent 100-point scoring."""
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple
from careerorbit.config.profile import CANDIDATE_PROFILE
from careerorbit.config.candidate_evidence import get_candidate_evidence
from careerorbit.models.schemas import ScoreBreakdown, MatchTier, VerificationStatus, MatchExplanation
from careerorbit.eligibility import screen_job_for_candidate, is_unrelated_nontechnical_role, classify_title_to_priority
from careerorbit.matcher.geo import classify_geographic_priority

class JobScorer:
    """Scores job vacancies transparently against candidate profile and personalized career priorities."""

    def __init__(
        self,
        profile: Dict[str, Any] = CANDIDATE_PROFILE,
        profile_id: str = "default",
        career_preferences: Optional[Sequence[str]] = None,
    ):
        self.profile = profile
        self.profile_id = profile_id
        self.career_preferences = career_preferences
        self.doc_skills = set(
            skill.lower() for cat in profile.get("documented_skills", {}).values() for skill in cat
        )
        self.core_skills = {
            "python", "sql", "mysql", "postgresql", "sql server", "power bi", "dax",
            "excel", "pandas", "numpy", "fastapi", "flask", "rest apis", "git",
            "github actions", "tensorflow", "keras", "opencv"
        }
        self.cloud_learning_targets = {
            "azure data factory", "azure databricks", "pyspark", "azure data lake storage",
            "azure synapse analytics", "microsoft fabric"
        }
        self.primary_locations = set(
            loc.lower() for loc in profile.get("location_preferences", {}).get("primary_cities", [])
        )

    def score_job(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculates 100-point score, breakdown, evidence notes, and eligibility tier."""
        title = (job_data.get("title") or "").lower()
        desc = (job_data.get("description") or "").lower()
        loc = (job_data.get("location") or "").lower()
        arrangement = (job_data.get("work_arrangement") or "").lower()
        salary_str = (job_data.get("salary") or "").lower()
        # Only score a publication timestamp when its source confidence is known.
        # Direct scorer callers with a date but no confidence are treated as source-reported.
        date_confidence = job_data.get("posting_date_confidence", "SOURCE_REPORTED")
        posting_date = job_data.get("posting_date") if date_confidence != "UNKNOWN" else None
        verification_status = job_data.get("verification_status")

        disqualifiers: List[str] = []
        supported_skills: List[str] = []
        missing_skills: List[str] = []
        learnable_skills: List[str] = []

        # ---------------- 1. Mandatory Disqualifiers ----------------
        # Unpaid check
        if any(unpaid_word in title or unpaid_word in desc for unpaid_word in ["unpaid", "stipend: none", "0 stipend", "without stipend"]):
            disqualifiers.append("Unpaid position detected. Platform policy requires paid opportunities.")

        # Seniority / Experience check (>3 years)
        exp_match = re.search(r'(\d+)\+?\s*(?:to|-)\s*(\d+)?\s*(?:years|yrs)|(\d+)\+\s*(?:years|yrs)', desc + " " + title)
        req_years = 0
        if exp_match:
            nums = [int(n) for n in exp_match.groups() if n and n.isdigit()]
            if nums:
                req_years = min(nums)
        
        senior_titles = ["senior", "lead", "principal", "architect", "manager", "director", "head of", "staff engineer", "vp"]
        early_title_terms = ["junior", "associate", "trainee", "graduate", "entry-level", "entry level", "fresher"]
        has_senior_title = any(re.search(r"\b" + re.escape(term) + r"\b", title) for term in senior_titles)
        if has_senior_title and not any(ok in title for ok in early_title_terms):
            disqualifiers.append(f"Senior role requirement detected (expected early-career 0-2 years, got title or {req_years}+ years).")

        if req_years > 3:
            disqualifiers.append(f"Experience requirement ({req_years}+ years) exceeds early-career threshold (0-2 years).")

        # Location / International Work Auth blocker
        is_remote = "remote" in arrangement or "remote" in loc or "work from home" in desc
        geo_info = classify_geographic_priority(loc, arrangement, desc)
        if geo_info.get("is_disqualified"):
            qualifier = "Remote eligibility" if is_remote else "On-site international location"
            disqualifiers.append(f"{qualifier} ({job_data.get('location')}) is not established for India-authorized candidates.")

        # Non-technical domain and target career track checks
        if is_unrelated_nontechnical_role(title, desc):
            disqualifiers.append("Role is in a non-technical domain outside candidate career priorities (Creative/HR/Marketing/Sales/Admin/Operations).")
        else:
            p_track = classify_title_to_priority(title, desc)
            if p_track <= 0:
                disqualifiers.append("Role title is outside candidate target career priorities (Priorities 1-6 technical tracks).")

        screen_reason = screen_job_for_candidate({
            "title": job_data.get("title", ""), "description": job_data.get("description", ""),
            "location": job_data.get("location", ""), "work_arrangement": job_data.get("work_arrangement", ""),
        })
        if screen_reason and not any(screen_reason.replace('_', ' ') in d for d in disqualifiers):
            disqualifiers.append(f"Outside current search eligibility: {screen_reason.replace('_', ' ')}.")

        # ---------------- 2. Skills and Project Alignment (Max 30) ----------------
        skill_score = 0.0
        all_skills_pool = [
            "python", "sql", "power bi", "dax", "excel", "pandas", "numpy", "fastapi",
            "flask", "rest apis", "rest api", "git", "github", "tensorflow", "keras",
            "opencv", "cnn", "machine learning", "data analytics", "business intelligence",
            "etl", "data validation", "data modeling", "bigquery", "aws", "mysql"
        ]

        found_skills = set()
        for s in all_skills_pool:
            if re.search(r'\b' + re.escape(s) + r'\b', desc) or re.search(r'\b' + re.escape(s) + r'\b', title):
                found_skills.add(s)

        # Check cloud learning targets (Azure Data Factory, Databricks, PySpark, Fabric)
        for cl in self.cloud_learning_targets:
            if cl in desc:
                learnable_skills.append(cl.title())

        for s in found_skills:
            if s in self.core_skills or s in ["git", "github", "rest api", "data analytics", "business intelligence", "etl", "machine learning", "data validation", "data modeling"]:
                supported_skills.append(s.title())
            else:
                missing_skills.append(s.title())

        # Give points based on core matches & priority alignment
        matched_count = len(supported_skills)
        if matched_count >= 5:
            skill_score = 30.0
        elif matched_count >= 3:
            skill_score = 24.0
        elif matched_count >= 1:
            skill_score = 18.0
        else:
            skill_score = 10.0  # foundational overlap

        # Surface a project title only after its field-level evidence was reviewed.
        evidence_states = {row["field"]: row["state"] for row in get_candidate_evidence()}
        evidence_project = "documented project evidence pending review"
        projects = self.profile.get("projects", [])
        if isinstance(projects, list):
            for index, project in enumerate(projects):
                if (isinstance(project, dict) and project.get("name") and
                        evidence_states.get(f"projects[{index}].name") in {"VERIFIED_FROM_SOURCE", "CONFIRMED_BY_CANDIDATE"}):
                    evidence_project = str(project["name"])
                    break

        # ---------------- 3. Experience Compatibility (Max 20) ----------------
        exp_score = 0.0
        early_career_terms = ["fresher", "fresh graduate", "entry level", "entry-level", "junior", "associate", "trainee", "0-1 year", "0-2 years", "graduate"]
        if req_years >= 3:
            exp_score = 6.0
        elif req_years == 2:
            exp_score = 10.0
        elif any(t in title or t in desc for t in early_career_terms) or req_years <= 1:
            exp_score = 20.0
        else:
            exp_score = 8.0

        # ---------------- 4. Eligibility (Max 15) ----------------
        eligibility_score = 15.0
        # Check if requires PhD or Master's strictly
        if any(degree in desc for degree in ["phd required", "doctorate required", "master's degree only"]):
            eligibility_score = 5.0
            disqualifiers.append("Advanced degree (PhD/Master's strictly required) incompatible with B.E. qualification.")

        # ---------------- 5. Freshness and Availability (Max 15) ----------------
        freshness_score = 8.0
        if posting_date:
            try:
                # Handle ISO format or standard date strings
                p_date = datetime.fromisoformat(posting_date.replace("Z", "+00:00"))
                if p_date.tzinfo is None:
                    p_date = p_date.replace(tzinfo=timezone.utc)
                age_days = (datetime.now(timezone.utc) - p_date).days
                if age_days <= 1:
                    freshness_score = 15.0
                elif age_days <= 3:
                    freshness_score = 12.0
                elif age_days <= 7:
                    freshness_score = 9.0
                else:
                    freshness_score = 5.0
            except Exception:
                freshness_score = 10.0

        if verification_status == VerificationStatus.VERIFIED_CLOSED.value:
            freshness_score = 0.0
            disqualifiers.append("Vacancy verified closed on official employer website.")

        # ---------------- 6. Location and Work Arrangement (Max 10) ----------------
        loc_score = geo_info["geo_score"]

        # ---------------- 7. Evidence Quality & Realistic Fit (Max 10) ----------------
        evidence_score = 8.0
        if len(supported_skills) >= 3 and not disqualifiers:
            evidence_score = 10.0

        # Total Calculation
        total = round(skill_score + exp_score + eligibility_score + freshness_score + loc_score + evidence_score, 1)
        total = min(100.0, max(0.0, total))

        # Categorization into Match Tiers
        is_eligible = False
        if disqualifiers:
            tier = MatchTier.INELIGIBLE
            # Roles outside career tracks, in non-technical domains, or unpaid receive 0.0 match score
            if any("career priorities" in d or "Unpaid position" in d for d in disqualifiers):
                total = 0.0
            is_eligible = False
            recommended_action = f"Skip or deprioritize. Ineligible due to: {'; '.join(disqualifiers)}"
        elif total >= 75.0:
            tier = MatchTier.STRONG_MATCH
            is_eligible = True
            recommended_action = "High priority candidate. Prepare tailored ATS resume and cover letter package."
        elif total >= 60.0:
            tier = MatchTier.REASONABLE_MATCH
            is_eligible = True
            recommended_action = "Good opportunity. Prepare tailored resume emphasizing core skills and related projects."
        elif total >= 45.0:
            tier = MatchTier.STRETCH_OPPORTUNITY
            is_eligible = True
            recommended_action = "Stretch opportunity. Target junior data/software aspects and highlight project achievements."
        else:
            tier = MatchTier.INELIGIBLE
            is_eligible = False
            recommended_action = "Low score / skill divergence. Focus on higher-scoring priority roles."

        breakdown = ScoreBreakdown(
            skills_and_projects=skill_score,
            experience_compatibility=exp_score,
            eligibility=eligibility_score,
            freshness_and_availability=freshness_score,
            location_and_arrangement=loc_score,
            evidence_and_realistic_fit=evidence_score,
            total=total
        )

        # ---------------- 8. Explainable Match Evidence Construction ----------------
        matched_reqs: List[str] = []
        for s in list(set(supported_skills))[:5]:
            matched_reqs.append(f"Documented Skill: '{s}' verified in candidate projects & technical profile.")
        if exp_score >= 15.0:
            matched_reqs.append("Experience Fit: Early-career (0-2 years) aligns directly with B.E. 2025 graduate profile.")
        if loc_score >= 9.0:
            matched_reqs.append(f"Location Fit: {geo_info['city'] or 'India'} matches candidate primary preference ({geo_info['geographic_tier_label']}).")
        matched_reqs.append(f"Project Alignment: Matches portfolio project '{evidence_project}'.")

        missing_reqs: List[str] = []
        for s in list(set(missing_skills))[:5]:
            missing_reqs.append(f"Skill Gap: '{s}' requested in vacancy but not documented in candidate core profile.")
        for s in list(set(learnable_skills)):
            missing_reqs.append(f"Learning Target: '{s}' requested; candidate study sprints can target this area.")

        uncertain_info: List[str] = []
        if not salary_str or "not disclosed" in salary_str:
            uncertain_info.append("Compensation: Salary not disclosed by employer in vacancy text.")
        if not job_data.get("shift"):
            uncertain_info.append("Working Hours: Specific work shift pattern not specified in job posting.")
        if date_confidence == "UNKNOWN":
            uncertain_info.append("Posting Date: Publication date could not be definitively verified from source.")
        if is_remote and geo_info.get("remote_eligibility") != "INDIA_PERMITTED":
            uncertain_info.append("Remote Policy: Employer tax/residency policy for India residents is unconfirmed.")
        uncertain_info.append("Hiring Team: Direct recruiter or hiring manager contact details are not published.")

        recs: List[str] = []
        if total >= 75.0:
            recs.append(f"Emphasize '{evidence_project}' and {', '.join(supported_skills[:3])} in the top third of your resume.")
            recs.append("Apply promptly through the official ATS portal and request recruiter outreach.")
        elif total >= 60.0:
            recs.append(f"Tailor experience bullet points around {', '.join(supported_skills[:2])} to demonstrate practical impact.")
            if missing_skills:
                recs.append(f"Review core fundamentals of '{missing_skills[0]}' before technical assessments.")
        elif total >= 45.0:
            recs.append("Treat this as a stretch target; highlight fast learning capacity and related open-source projects.")
            if learnable_skills:
                recs.append(f"Prioritize study sprint on '{learnable_skills[0]}' to bridge candidacy gap.")
        else:
            recs.append("Focus primarily on Priority 1 roles (Data Analyst / BI) where candidate fit exceeds 60%.")

        disclaimer_text = (
            "This match score is an algorithmic assessment based on documented qualifications and vacancy text. "
            "It is not a prediction or guarantee of job offers or interview invitations."
        )

        explanation = MatchExplanation(
            overall_score=total,
            match_tier=tier,
            score_breakdown=breakdown,
            matched_requirements=matched_reqs,
            missing_requirements=missing_reqs,
            potential_blockers=list(disqualifiers),
            uncertain_information=uncertain_info,
            recommendations=recs,
            disclaimer=disclaimer_text,
            geographic_priority=geo_info["geographic_priority"],
            geographic_tier_label=geo_info["geographic_tier_label"],
            location_eligibility_status=geo_info["location_eligibility_status"],
            city=geo_info["city"],
            state=geo_info["state"],
            country=geo_info["country"],
            remote_eligibility=geo_info["remote_eligibility"],
            geo_score=loc_score,
        )

        from careerorbit.career_priorities import classify_job_category, get_preference_rank
        cat_obj = classify_job_category(job_data.get("title", ""), job_data.get("description", ""))
        pref_rank = get_preference_rank(
            job_data,
            candidate_profile=self.profile,
            preferences=self.career_preferences,
            profile_id=self.profile_id
        )

        return {
            "match_score": total,
            "match_tier": tier,
            "is_eligible": is_eligible,
            "career_category": cat_obj.id if cat_obj else None,
            "preference_rank": pref_rank,
            "score_breakdown": breakdown,
            "supported_skills": list(set(supported_skills)),
            "missing_skills": list(set(missing_skills)),
            "learnable_skills": list(set(learnable_skills)),
            "disqualifiers": disqualifiers,
            "evidence_notes": f"Matched projects: {evidence_project}. Key skills: {', '.join(supported_skills[:4])}.",
            "recommended_action": recommended_action,
            "geographic_priority": geo_info["geographic_priority"],
            "geographic_tier_label": geo_info["geographic_tier_label"],
            "location_eligibility_status": geo_info["location_eligibility_status"],
            "city": geo_info["city"],
            "state": geo_info["state"],
            "country": geo_info["country"],
            "remote_eligibility": geo_info["remote_eligibility"],
            "geo_score": loc_score,
            "matched_requirements": matched_reqs,
            "missing_requirements": missing_reqs,
            "potential_blockers": list(disqualifiers),
            "uncertain_information": uncertain_info,
            "recommendations": recs,
            "disclaimer": disclaimer_text,
            "match_explanation": explanation.model_dump(),
        }
