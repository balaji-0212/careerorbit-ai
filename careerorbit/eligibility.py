"""Shared candidate role and location eligibility rules.

Note: Career classification categorizes what domain a role belongs to (legacy codes 1-6).
User preferences determine the personalized priority rank of those categories for each candidate.
"""
import re
from typing import Any, Dict, Optional

# Supported technical career tracks (legacy code mapping):
# 1. Data Analyst / BI / Power BI / Reporting
# 2. Data Scientist / Junior Data Scientist
# 3. Software Engineer / Associate Software Engineer / Junior Developer
# 4. AI / ML / Computer Vision / AI Application Engineer
# 5. Data Engineer / Analytics Engineer / ETL Developer
# 6. Other relevant early-career technical roles
PRIORITY_LABELS = {
    0: "Ineligible / Out of Scope",
    1: "Data Analyst / BI / Power BI / Reporting",
    2: "Data Scientist / Junior Data Scientist",
    3: "Software Engineer / Associate Software Engineer / Junior Developer",
    4: "AI / ML / Computer Vision / AI Application Engineer",
    5: "Data Engineer / Analytics Engineer / ETL Developer",
    6: "Other relevant early-career technical roles",
}

# Positive technical patterns for Priorities 1 to 5
P1_PATTERNS = (
    "data analyst", "bi analyst", "business intelligence", "power bi", "reporting analyst",
    "analytics associate", "reporting developer", "data analytics", "sql analyst",
    "junior data analyst", "bi developer", "business data analyst", "data visualization",
    "tableau developer", "tableau analyst", "data quality analyst", "junior analyst",
    "financial data analyst", "operations data analyst"
)

P2_PATTERNS = (
    "data scientist", "junior data scientist", "data science", "applied scientist",
    "applied data scientist", "machine learning scientist", "ai scientist", "ml scientist"
)

P3_PATTERNS = (
    "software engineer", "software developer", "python developer", "backend developer",
    "frontend developer", "full stack developer", "full-stack developer", "api developer",
    "associate software", "graduate software", "junior software", "junior developer",
    "junior engineer", "software development engineer", "software development",
    "python backend", "developer intern", "software intern", "sde intern",
    "software associate", "software engineer trainee", "graduate engineer trainee",
    "systems engineer", "sde 1", "sde i", "sde-1", "sde-i"
)

P4_PATTERNS = (
    "ai engineer", "machine learning engineer", "ml engineer", "junior ml",
    "computer vision", "generative ai", "mlops", "ai solution engineer",
    "ai application", "ai software", "applied ai", "nlp engineer", "deep learning"
)

P5_PATTERNS = (
    "data engineer", "junior data engineer", "analytics engineer", "etl developer",
    "pipeline developer", "cloud data engineer", "database developer", "sql developer",
    "bi engineer", "data warehouse engineer"
)

# Priority 6: Explicit positive technical keywords required for early-career technical roles
P6_PATTERNS = (
    "qa automation", "quality assurance automation", "automation test", "sdet",
    "software test", "technical support", "application support", "production support",
    "cloud associate", "cloud support", "junior cloud", "devops", "junior devops",
    "platform engineer", "site reliability", "junior sre", "python automation",
    "automation engineer", "solution engineer", "solutions engineer", "technical consultant",
    "technology analyst", "technical analyst", "data operations", "database administrator",
    "junior dba", "network engineer", "systems administrator", "firmware engineer",
    "embedded software", "iot engineer"
)

# Negative domain patterns to explicitly reject non-technical domains
# even if accompanied by intern, trainee, associate, fresher
NON_TECHNICAL_PATTERNS = [
    # Creative communications, copy, social media, PR, design
    r"\bcreative\b", r"\bcommunications?\b", r"\bcopywriter\b", r"\bcopywriting\b",
    r"\bcontent writ(er|ing)\b", r"\bsocial media\b", r"\bpublic relations\b", r"\bpr\b",
    r"\bgraphic design(er)?\b", r"\bui/ux design(er)?\b", r"\bux design(er)?\b",
    r"\bvideo edit(or|ing)\b", r"\banimat(or|ion)\b", r"\bmultimedia\b",

    # HR, recruiter, talent acquisition, people team
    r"\bhuman resources?\b", r"\bhr\b", r"\brecruit(er|ment|ing)\b",
    r"\btalent acquisition\b", r"\bpeople team\b", r"\bpeople operations?\b",
    r"\bemployee relations?\b", r"\bonboarding\b",

    # General marketing, digital marketing, SEO, brand
    r"\bmarketing\b", r"\bdigital marketing\b", r"\bseo\b", r"\bsem\b",
    r"\bbrand(ing)?\b", r"\bgrowth market(ing|er)\b", r"\bmarket research\b",
    r"\bcampaign manager\b", r"\bperformance marketing\b",

    # Sales, B2B sales, business development, telecalling
    r"\bsales\b", r"\bb2b\b", r"\bbusiness development\b", r"\bbde\b", r"\bbda\b",
    r"\btelecall(er|ing)\b", r"\btelesales\b", r"\btelemarketing\b",
    r"\binside sales\b", r"\bfield sales\b", r"\baccount executive\b",

    # Non-technical administrative, clerical, executive assistant
    r"\badministrat(ive|or|ion)\b", r"\bclerk\b", r"\bclerical\b",
    r"\bexecutive assistant\b", r"\bpersonal assistant\b", r"\boffice assistant\b",
    r"\breceptionist\b", r"\bfront desk\b", r"\bdata entry\b",

    # Unrelated finance, accounting, payroll, billing
    r"\baccounting\b", r"\baccountant\b", r"\bchartered accountant\b",
    r"\bbookkeep(er|ing)\b", r"\bbilling\b", r"\bpayroll\b",
    r"\baccounts payable\b", r"\baccounts receivable\b", r"\btax(ation)?\b", r"\baudit(or|ing)?\b",

    # Customer support, call center, customer care, operations
    r"\bcustomer support\b", r"\bcustomer care\b", r"\bcustomer service\b",
    r"\bcall cent(er|re)\b", r"\bhelpdesk agent\b", r"\bvoice process\b",
    r"\bnon-voice process\b", r"\bbpo\b", r"\bkpo\b", r"\btelecom agent\b",
    r"\bwarehouse operat(ions?|or)\b", r"\bstore operat(ions?|or)\b", r"\bfield operat(ions?|or)\b",
    r"\boperations?\s+(trainee|intern|associate|executive|coordinator|assistant|clerk)\b",
]


def is_unrelated_nontechnical_role(title: str, description: str = "") -> bool:
    """Identify roles in non-technical domains (Creative, HR, Marketing, Sales, Admin, etc.)."""
    t = (title or "").lower()
    d = (description or "").lower()

    # If title explicitly matches core technical tracks (P1-P5), it is technical
    all_core_tech = P1_PATTERNS + P2_PATTERNS + P3_PATTERNS + P4_PATTERNS + P5_PATTERNS
    if any(p in t for p in all_core_tech) or bool(re.search(r"\bsde\b", t)):
        return False

    # Check for non-technical domain patterns in title
    for pat in NON_TECHNICAL_PATTERNS:
        if re.search(pat, t, re.IGNORECASE):
            return True

    # Check if title is purely generic (e.g. "Intern", "Trainee") with non-technical description
    generic_words = {"intern", "internship", "trainee", "associate", "fresher", "graduate"}
    tokens = set(re.findall(r"\b\w+\b", t))
    if tokens and tokens.issubset(generic_words):
        for pat in NON_TECHNICAL_PATTERNS:
            if re.search(pat, d, re.IGNORECASE):
                return True

    return False


def classify_title_to_priority(title: str, description: str = "") -> int:
    """Classifies job title into 1-6 technical priority tracks, or 0 (ineligible)."""
    t = (title or "").lower()

    # 1. Reject explicit non-technical roles
    if is_unrelated_nontechnical_role(title, description):
        return 0

    # Priority 1: Data Analyst / BI / Power BI / Reporting
    if any(p in t for p in P1_PATTERNS):
        return 1

    # Priority 2: Data Scientist / Junior Data Scientist
    if any(p in t for p in P2_PATTERNS):
        return 2

    # Priority 3: Software Engineer / Associate Software Engineer / Junior Developer
    if any(p in t for p in P3_PATTERNS) or bool(re.search(r"\bsde\b", t)):
        return 3

    # Priority 4: AI / ML / Computer Vision / AI Application Engineer
    if any(p in t for p in P4_PATTERNS):
        return 4

    # Priority 5: Data Engineer / Analytics Engineer / ETL Developer
    if any(p in t for p in P5_PATTERNS):
        return 5

    # Priority 6: Other relevant early-career technical roles
    # Must match a positive technical keyword list AND not be non-technical
    if any(p in t for p in P6_PATTERNS):
        return 6

    # Anything else is unclassified / out of scope (0)
    return 0


def detect_opportunity_attributes(title: str, description: str = "", employment_type: str = "") -> Dict[str, Any]:
    """Detect fresher, off-campus, internship, walk-in, and experience range attributes."""
    t = (title or "").lower()
    d = (description or "").lower()
    e = (employment_type or "").lower()
    combined = f"{t} {d} {e}"

    fresher_markers = (
        "fresher", "freshers", "0-1", "0-2", "0 to 1", "0 to 2", "0 - 1", "0 - 2",
        "entry level", "entry-level", "graduate", "trainee", "associate", "junior",
        "2024", "2025", "2026", "college graduate", "campus", "get", "sde-1", "sde 1", "sde i"
    )
    is_fresher = any(re.search(r"\b" + re.escape(m) + r"\b", t) for m in ("junior", "associate", "graduate", "trainee", "fresher", "entry level", "intern")) or \
                 any(re.search(r"\b" + re.escape(m) + r"\b", combined) for m in fresher_markers)

    off_campus_markers = (
        "off-campus", "off campus", "offcampus", "pooled campus", "hiring challenge",
        "coding challenge", "recruitment drive", "national qualifier", "hackathon",
        "assessment-based", "walk-in", "walk in"
    )
    is_off_campus = any(m in combined for m in off_campus_markers)

    is_internship = "intern" in t or "internship" in t or "intern" in e
    is_walkin = "walk-in" in t or "walk in" in t or "walk in" in d or "walk-in" in d

    min_exp = None
    max_exp = None
    m = re.search(r"\b(\d+)\s*(?:to|-)\s*(\d+)\s*(?:years?|yrs?)\b", combined)
    if m:
        try:
            min_exp = float(m.group(1))
            max_exp = float(m.group(2))
        except (ValueError, TypeError):
            pass
    else:
        m_single = re.search(r"\b(?:minimum|at least)?\s*(\d+)\+?\s*(?:years?|yrs?)\b", combined)
        if m_single:
            try:
                min_exp = float(m_single.group(1))
            except (ValueError, TypeError):
                pass

    if is_fresher and min_exp is None:
        min_exp = 0.0
        if max_exp is None:
            max_exp = 2.0

    return {
        "is_fresher": is_fresher,
        "is_off_campus": is_off_campus,
        "is_internship": is_internship,
        "is_walkin": is_walkin,
        "min_experience_years": min_exp,
        "max_experience_years": max_exp,
    }


def screen_job_for_candidate(job: Dict[str, Any]) -> str | None:
    """Reject obviously unrelated roles and postings with ineligible locations."""
    title = str(job.get("title") or "").strip()
    desc = str(job.get("description") or "").strip()
    title_lower = title.lower()
    desc_lower = desc.lower()

    # 1. Reject non-technical domains explicitly (Creative, HR, Marketing, Sales, Admin, etc.)
    if is_unrelated_nontechnical_role(title, desc):
        return "title_not_in_career_priorities"

    # 2. Require qualification in one of Priorities 1 to 6
    p = classify_title_to_priority(title, desc)
    if p <= 0:
        return "title_not_in_career_priorities"

    if any(term in (title_lower + " " + desc_lower) for term in ("unpaid", "stipend: none", "0 stipend", "without stipend")):
        return "unpaid_role"

    early_level_terms = (
        "junior", "associate", "graduate", "trainee", "entry level", "entry-level",
        "fresher", "intern", "sde i", "sde 1", "engineer 1", "engineer i", "level 1",
        "l1", "0-1", "0-2"
    )
    hard_senior_terms = (
        "principal", "staff", "director", "architect", "head of", "vp",
        "sde iii", "sde 3", "sde iv", "sde 4", "sde-iii", "sde-iv",
        "applied scientist iii", "scientist iii"
    )
    if any(re.search(r"\b" + re.escape(term) + r"\b", title_lower) for term in hard_senior_terms):
        return "seniority_out_of_scope"

    senior_terms = (
        "senior", "lead", "manager"
    )
    is_early_level = any(re.search(r"\b" + re.escape(ok) + r"\b", title_lower) for ok in early_level_terms)

    # Disqualify senior titles unless explicitly accompanied by early career markers
    if any(re.search(r"\b" + re.escape(term) + r"\b", title_lower) for term in senior_terms) and not is_early_level:
        return "seniority_out_of_scope"

    # Evaluate experience requirement: only screen out roles with explicit >3 year minimum requirement
    if not is_early_level:
        req_match = re.search(
            r"(?:require[sd]?|minimum|at least|\bhave\b)\s*(\d+)\+?\s*(?:to|-)?\s*(\d+)?\s*(?:years|yrs)\s*(?:of\s*)?(?:experience|exp)",
            title + " " + desc,
            re.IGNORECASE
        )
        if req_match:
            try:
                min_years = int(req_match.group(1))
                if min_years > 3:
                    return "experience_requirement_over_3_years"
            except (ValueError, TypeError):
                pass

    # Location eligibility: delegate to comprehensive geographic classifier
    from careerorbit.matcher.geo import classify_geographic_priority
    loc = str(job.get("location") or "")
    arr = str(job.get("work_arrangement") or "")
    geo_info = classify_geographic_priority(loc, arr, desc)
    if geo_info.get("is_disqualified"):
        if geo_info.get("location_eligibility_status") == "RESTRICTED_NON_INDIA":
            return "location_restricted_outside_india"
        is_remote = "remote" in arr.lower() or "remote" in loc.lower() or "work from home" in desc
        if is_remote and "india" not in loc.lower():
            return "remote_eligibility_not_india"
        return "location_restricted_outside_india"

    if geo_info.get("location_eligibility_status") == "LOCATION_ELIGIBILITY_UNCONFIRMED":
        is_remote = "remote" in arr.lower() or "remote" in loc.lower() or "work from home" in desc
        if is_remote and "india" not in loc.lower():
            return "remote_eligibility_not_india"
        return "location_restricted_outside_india"

    return None


RECOMMENDABLE_SQL_PREDICATE = (
    "COALESCE(record_state, 'DISCOVERY_LEAD') != 'QUARANTINED' "
    "AND verification_status = 'VERIFIED_OPEN' "
    "AND match_tier != 'Ineligible'"
)


def is_recommendable(job: Dict[str, Any]) -> bool:
    """Evaluates whether a job posting meets the single, definitive recommendation criteria:
    1. Active lead (not quarantined).
    2. Verified open on employer portal / authorized ATS.
    3. Eligible candidate match (match_tier is not Ineligible).
    """
    record_state = str(job.get("record_state") or "DISCOVERY_LEAD").strip().upper()
    if record_state == "QUARANTINED":
        return False
    v_status = str(job.get("verification_status") or "").strip().upper()
    if v_status != "VERIFIED_OPEN":
        return False
    tier = str(job.get("match_tier") or "").strip()
    if tier in ("Ineligible", "Ineligible / Out of Scope", ""):
        return False
    return True

