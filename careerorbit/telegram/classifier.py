"""Content Classifier for Incoming Telegram Messages and Resources.
Classifies text and attachments into 11 discrete career categories:
  1. Job: Data Analyst / BI
  2. Job: Data Science / AI / ML
  3. Job: Software Engineering
  4. Job: Data Engineering
  5. Job: Other Technical Role
  6. Interview Preparation
  7. Coding Practice
  8. Technical Learning Materials
  9. Certifications and Courses
  10. Other Career Resources
  11. Irrelevant Content
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse


class TelegramContentClassifier:
    """Categorizes community messages into targeted career opportunities and learning assets."""

    # Category constants
    CAT_JOB_DATA_ANALYST = "Job: Data Analyst / BI"
    CAT_JOB_DATA_SCIENCE = "Job: Data Science / AI / ML"
    CAT_JOB_SOFTWARE_ENG = "Job: Software Engineering"
    CAT_JOB_DATA_ENG = "Job: Data Engineering"
    CAT_JOB_OTHER_TECH = "Job: Other Technical Role"

    CAT_INTERVIEW_PREP = "Interview Preparation"
    CAT_CODING_PRACTICE = "Coding Practice"
    CAT_TECH_LEARNING = "Technical Learning Materials"
    CAT_CERTIFICATIONS = "Certifications and Courses"
    CAT_OTHER_CAREER = "Other Career Resources"
    CAT_IRRELEVANT = "Irrelevant Content"

    ALL_CATEGORIES = [
        CAT_JOB_DATA_ANALYST,
        CAT_JOB_DATA_SCIENCE,
        CAT_JOB_SOFTWARE_ENG,
        CAT_JOB_DATA_ENG,
        CAT_JOB_OTHER_TECH,
        CAT_INTERVIEW_PREP,
        CAT_CODING_PRACTICE,
        CAT_TECH_LEARNING,
        CAT_CERTIFICATIONS,
        CAT_OTHER_CAREER,
        CAT_IRRELEVANT,
    ]

    # Keyword sets for job discovery detection
    JOB_INDICATOR_KEYWORDS = [
        r"\bhiring\b", r"\bjob\s*opening\b", r"\bjob\s*vacancy\b", r"\bvacanc(?:y|ies)\b",
        r"\brole\s*[:\-–]", r"\bposition\s*[:\-–]", r"\bdesignation\s*[:\-–]",
        r"\bapply\s*(?:link|here|now|at|before)\b", r"\bregistration\s*link\b",
        r"\bexperience\s*[:\-–]", r"\beligibility\s*[:\-–]", r"\bbatch\s*[:\-–]",
        r"\boff[\s-]campus\b", r"\bwalk[\s-]in\b", r"\brecruitment\s*drive\b",
        r"\bstipend\s*[:\-–]", r"\bsalary\s*[:\-–]", r"\bctc\s*[:\-–]", r"\blpa\b",
        r"\blooking\s+for\s+[a-zA-Z\s]+(?:engineer|analyst|developer|intern|trainee)\b"
    ]

    JOB_DOMAINS = [
        "greenhouse.io", "lever.co", "myworkdayjobs.com", "smartrecruiters.com",
        "ashbyhq.com", "unstop.com", "linkedin.com/jobs", "naukri.com",
        "internshala.com", "wellfound.com", "foundit.in", "instahyre.com",
        "cuvette.tech", "hirist.tech"
    ]

    # Generic technology signals used to classify job related messages.
    PROFILE_MATCH_KEYWORDS = {
        "python": "Python",
        "sql": "SQL",
        "power bi": "Power BI",
        "powerbi": "Power BI",
        "dax": "DAX",
        "fastapi": "FastAPI",
        "flask": "Flask",
        "tensorflow": "TensorFlow",
        "keras": "Keras",
        "opencv": "OpenCV",
        "pandas": "Pandas",
        "numpy": "NumPy",
        "excel": "Excel",
        "git": "Git",
        "mysql": "MySQL",
        "postgresql": "PostgreSQL",
        "sql server": "SQL Server",
        "ece": "B.E. ECE",
        "electronics": "Electronics",
        "fresher": "Fresher / 0-2 Years",
        "2025": "2025 Batch",
    }

    PROFILE_MATCH_PATTERNS = [
        (re.compile(rf"\b{re.escape(kw)}\b", re.IGNORECASE), label)
        for kw, label in PROFILE_MATCH_KEYWORDS.items()
    ]

    JOB_INDICATOR_PATTERNS = [
        re.compile(pattern, re.IGNORECASE)
        for pattern in JOB_INDICATOR_KEYWORDS
    ]

    URL_PATTERN = re.compile(r"https?://[^\s<>\"'()]+")

    TECH_TAGS = [
        "python", "sql", "power bi", "dax", "excel", "fastapi", "flask",
        "tensorflow", "keras", "opencv", "scikit-learn", "pandas", "numpy",
        "mysql", "postgresql", "sql server", "aws", "gcp", "azure",
        "git", "docker", "pyspark", "databricks", "dsa", "c++", "java"
    ]
    TECH_TAG_PATTERNS = [
        (re.compile(rf"\b{re.escape(t)}\b", re.IGNORECASE), t.title() if len(t) > 3 else t.upper())
        for t in TECH_TAGS
    ]

    @classmethod
    def classify(cls, text: str, media_type: str = "text") -> Dict[str, Any]:
        """Classify incoming raw text and return detailed category breakdown."""
        raw = text.strip()
        lower = raw.lower()

        urls = cls._extract_urls(raw)
        matched_candidate_skills = [
            label for pat, label in cls.PROFILE_MATCH_PATTERNS
            if pat.search(lower)
        ]

        # 1. Command check
        if raw.startswith("/"):
            cmd = raw.split()[0].lower()
            return {
                "classification": "COMMAND",
                "category_group": "command",
                "is_command": True,
                "command": cmd,
                "is_job_lead": False,
                "confidence": 1.0,
                "candidate_matches": [],
                "urls": urls,
                "tech_tags": [],
            }

        # 2. Check if text is a job vacancy
        is_job, job_cat = cls._detect_job_opportunity(lower, urls)
        if is_job:
            return {
                "classification": job_cat,
                "category_group": "job",
                "is_command": False,
                "is_job_lead": True,
                "confidence": 0.92,
                "candidate_matches": matched_candidate_skills,
                "urls": urls,
                "tech_tags": cls._extract_tech_tags(lower),
            }

        # 3. Check for Interview Preparation
        if cls._is_interview_prep(lower):
            return {
                "classification": cls.CAT_INTERVIEW_PREP,
                "category_group": "prep",
                "is_command": False,
                "is_job_lead": False,
                "confidence": 0.88,
                "candidate_matches": matched_candidate_skills,
                "urls": urls,
                "tech_tags": cls._extract_tech_tags(lower),
            }

        # 4. Check for Coding Practice
        if cls._is_coding_practice(lower):
            return {
                "classification": cls.CAT_CODING_PRACTICE,
                "category_group": "practice",
                "is_command": False,
                "is_job_lead": False,
                "confidence": 0.88,
                "candidate_matches": matched_candidate_skills,
                "urls": urls,
                "tech_tags": cls._extract_tech_tags(lower),
            }

        # 5. Check for Technical Learning Materials
        if cls._is_technical_learning(lower):
            return {
                "classification": cls.CAT_TECH_LEARNING,
                "category_group": "learning",
                "is_command": False,
                "is_job_lead": False,
                "confidence": 0.85,
                "candidate_matches": matched_candidate_skills,
                "urls": urls,
                "tech_tags": cls._extract_tech_tags(lower),
            }

        # 6. Check for Certifications and Courses
        if cls._is_certification_or_course(lower):
            return {
                "classification": cls.CAT_CERTIFICATIONS,
                "category_group": "cert",
                "is_command": False,
                "is_job_lead": False,
                "confidence": 0.85,
                "candidate_matches": matched_candidate_skills,
                "urls": urls,
                "tech_tags": cls._extract_tech_tags(lower),
            }

        # 7. Check for Other Career Resources
        if cls._is_other_career_resource(lower):
            return {
                "classification": cls.CAT_OTHER_CAREER,
                "category_group": "career",
                "is_command": False,
                "is_job_lead": False,
                "confidence": 0.80,
                "candidate_matches": matched_candidate_skills,
                "urls": urls,
                "tech_tags": cls._extract_tech_tags(lower),
            }

        # 8. Fallback: Irrelevant Content
        return {
            "classification": cls.CAT_IRRELEVANT,
            "category_group": "irrelevant",
            "is_command": False,
            "is_job_lead": False,
            "confidence": 0.95 if len(raw) < 40 else 0.70,
            "candidate_matches": [],
            "urls": urls,
            "tech_tags": [],
        }

    @classmethod
    def _detect_job_opportunity(cls, lower: str, urls: List[str]) -> Tuple[bool, str]:
        """Detect whether text describes a job vacancy and classify its role track."""
        job_score = 0

        # Check job indicators using pre-compiled regexes
        for pattern in cls.JOB_INDICATOR_PATTERNS:
            if pattern.search(lower):
                job_score += 2

        # Check job domains
        for u in urls:
            parsed = urlparse(u).netloc.lower()
            if any(d in parsed or d in u.lower() for d in cls.JOB_DOMAINS):
                job_score += 4
            elif "forms.gle" in u or "docs.google.com/forms" in u:
                job_score += 2

        # If not enough job indicators, return False
        if job_score < 2:
            return False, ""

        # Classify tech role track
        # Priority 1: Data Analyst / BI
        if any(term in lower for term in [
            "data analyst", "business intelligence", "bi analyst", "power bi", "powerbi",
            "reporting analyst", "mis analyst", "tableau", "dashboard developer",
            "data analytics intern", "analytics associate"
        ]):
            return True, cls.CAT_JOB_DATA_ANALYST

        # Priority 2: Data Science / AI / ML
        if any(term in lower for term in [
            "data scientist", "data science", "machine learning", "ml engineer",
            "deep learning", "nlp engineer", "computer vision", "opencv",
            "ai engineer", "artificial intelligence", "junior data scientist"
        ]):
            return True, cls.CAT_JOB_DATA_SCIENCE

        # Priority 3: Software Engineering
        if any(term in lower for term in [
            "software engineer", "software developer", "sde", "associate software engineer",
            "backend developer", "frontend developer", "full stack", "python developer",
            "graduate software engineer", "systems engineer", "web developer", "trainee engineer"
        ]):
            return True, cls.CAT_JOB_SOFTWARE_ENG

        # Priority 4: Data Engineering
        if any(term in lower for term in [
            "data engineer", "data engineering", "etl developer", "pyspark",
            "databricks", "azure data factory", "data pipeline", "analytics engineer", "dbt"
        ]):
            return True, cls.CAT_JOB_DATA_ENG

        # Priority 5: Other Technical IT Opportunity
        return True, cls.CAT_JOB_OTHER_TECH

    @classmethod
    def _is_interview_prep(cls, lower: str) -> bool:
        indicators = [
            "interview question", "interview questions", "mock interview", "hr questions",
            "behavioral interview", "star method", "system design interview", "interview experience",
            "crack the interview", "interview preparation", "interview cheat sheet", "technical round",
            "frequently asked interview", "interview tips", "top 50 questions", "top 100 questions"
        ]
        return any(term in lower for term in indicators)

    @classmethod
    def _is_coding_practice(cls, lower: str) -> bool:
        indicators = [
            "leetcode", "hackerrank", "codechef", "codeforces", "geeksforgeeks", "gfg",
            "data structures and algorithms", "dsa problem", "dsa sheet", "striver", "neetcode",
            "binary tree", "dynamic programming", "two pointers", "graph algorithm",
            "daily coding problem", "coding challenge", "time complexity", "space complexity"
        ]
        return any(term in lower for term in indicators)

    @classmethod
    def _is_technical_learning(cls, lower: str) -> bool:
        indicators = [
            "tutorial", "handbook", "roadmap", "notes pdf", "guide pdf", "cheat sheet",
            "cheatsheet", "free book", "documentation", "learn python", "sql guide",
            "fastapi tutorial", "architecture overview", "study material", "complete guide",
            "mastering", "deep dive into", "learning path", "github repo for learning"
        ]
        return any(term in lower for term in indicators)

    @classmethod
    def _is_certification_or_course(cls, lower: str) -> bool:
        indicators = [
            "certification", "free course", "coursera", "udemy", "edx", "aws certified",
            "cloud practitioner", "exam voucher", "coupon code", "free enrollment",
            "badge", "diploma course", "training program", "nptel", "skill india", "free certificate"
        ]
        return any(term in lower for term in indicators)

    @classmethod
    def _is_other_career_resource(cls, lower: str) -> bool:
        indicators = [
            "resume review", "ats resume", "resume template", "portfolio project",
            "cover letter", "linkedin optimization", "networking tip", "referral available",
            "salary negotiation", "career advice", "career roadmap", "tech event", "hackathon"
        ]
        return any(term in lower for term in indicators)

    @classmethod
    def _extract_urls(cls, text: str) -> List[str]:
        return cls.URL_PATTERN.findall(text)

    @classmethod
    def _extract_tech_tags(cls, lower: str) -> List[str]:
        return [
            label for pat, label in cls.TECH_TAG_PATTERNS
            if pat.search(lower)
        ]
