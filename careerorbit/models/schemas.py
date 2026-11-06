"""Data models and schemas for CareerOrbit AI."""
from enum import Enum
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime, timezone

class VerificationStatus(str, Enum):
    # 6 Canonical Statuses
    VERIFIED_OPEN = "VERIFIED_OPEN"
    VERIFIED_CLOSED = "VERIFIED_CLOSED"
    PENDING_VERIFICATION = "PENDING_VERIFICATION"
    BROKEN_LINK = "BROKEN_LINK"
    SUSPICIOUS = "SUSPICIOUS"
    VERIFICATION_ERROR = "VERIFICATION_ERROR"

    # Legacy aliases preserved for backwards compatibility
    UNVERIFIED = "UNVERIFIED"
    STATUS_UNKNOWN = "STATUS_UNKNOWN"

    @classmethod
    def _missing_(cls, value: Any):
        if isinstance(value, str):
            v = value.strip().upper()
            if v in ("PENDING",):
                return cls.PENDING_VERIFICATION
            if v in ("UNKNOWN",):
                return cls.VERIFICATION_ERROR
        return None

def canonicalize_verification_status(status: str | VerificationStatus) -> str:
    s = status.value if hasattr(status, "value") else str(status)
    s_clean = s.strip().upper()
    if s_clean in ("UNVERIFIED", "PENDING_VERIFICATION"):
        return "PENDING_VERIFICATION"
    if s_clean in ("STATUS_UNKNOWN", "VERIFICATION_ERROR"):
        return "VERIFICATION_ERROR"
    return s_clean

class MatchTier(str, Enum):
    STRONG_MATCH = "Strong match"
    REASONABLE_MATCH = "Reasonable match"
    STRETCH_OPPORTUNITY = "Stretch opportunity"
    INELIGIBLE = "Ineligible"

class ApplicationStatus(str, Enum):
    # 10 Canonical Stages
    SAVED = "SAVED"
    READY_TO_APPLY = "READY_TO_APPLY"
    APPLIED = "APPLIED"
    ASSESSMENT_RECEIVED = "ASSESSMENT_RECEIVED"
    INTERVIEW_SCHEDULED = "INTERVIEW_SCHEDULED"
    INTERVIEW_COMPLETED = "INTERVIEW_COMPLETED"
    OFFER_RECEIVED = "OFFER_RECEIVED"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"
    NO_RESPONSE = "NO_RESPONSE"

    # Legacy pipeline statuses preserved for backwards compatibility
    DISCOVERED = "DISCOVERED"
    VERIFIED = "VERIFIED"
    MATCHED = "MATCHED"
    RESUME_READY = "RESUME_READY"
    PACKAGE_READY = "PACKAGE_READY"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    SUBMITTED_CONFIRMED = "SUBMITTED_CONFIRMED"
    SUBMITTED = "SUBMITTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    ASSESSMENT = "ASSESSMENT"
    INTERVIEW = "INTERVIEW"
    OFFER = "OFFER"
    PREPARING_APPLICATION = "PREPARING_APPLICATION"
    TO_APPLY = "TO_APPLY"

    @classmethod
    def _missing_(cls, value: Any):
        if isinstance(value, str):
            v = value.strip().upper().replace(" ", "_").replace("-", "_")
            legacy_map = {
                "APPLY": cls.READY_TO_APPLY,
            }
            if v in legacy_map:
                return legacy_map[v]
        return None

def canonicalize_application_stage(status: str | ApplicationStatus) -> str:
    s = status.value if hasattr(status, "value") else str(status)
    s_clean = s.strip().upper()
    mapping = {
        "DISCOVERED": "SAVED",
        "VERIFIED": "SAVED",
        "MATCHED": "SAVED",
        "SAVED": "SAVED",
        "RESUME_READY": "READY_TO_APPLY",
        "PACKAGE_READY": "READY_TO_APPLY",
        "AWAITING_APPROVAL": "READY_TO_APPLY",
        "READY_TO_APPLY": "READY_TO_APPLY",
        "PREPARING_APPLICATION": "READY_TO_APPLY",
        "TO_APPLY": "READY_TO_APPLY",
        "SUBMITTED": "APPLIED",
        "SUBMITTED_CONFIRMED": "APPLIED",
        "UNDER_REVIEW": "APPLIED",
        "APPLIED": "APPLIED",
        "ASSESSMENT": "ASSESSMENT_RECEIVED",
        "ASSESSMENT_RECEIVED": "ASSESSMENT_RECEIVED",
        "INTERVIEW": "INTERVIEW_SCHEDULED",
        "INTERVIEW_SCHEDULED": "INTERVIEW_SCHEDULED",
        "INTERVIEW_COMPLETED": "INTERVIEW_COMPLETED",
        "OFFER": "OFFER_RECEIVED",
        "OFFER_RECEIVED": "OFFER_RECEIVED",
        "REJECTED": "REJECTED",
        "WITHDRAWN": "WITHDRAWN",
        "NO_RESPONSE": "NO_RESPONSE",
    }
    return mapping.get(s_clean, "SAVED")

class RecruiterOutreachStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    DRAFTED = "DRAFTED"
    READY_FOR_APPROVAL = "READY_FOR_APPROVAL"
    SENT = "SENT"
    REPLIED = "REPLIED"

class ScoreBreakdown(BaseModel):
    skills_and_projects: float = Field(0.0, ge=0.0, le=30.0, description="Skills & project alignment (max 30)")
    experience_compatibility: float = Field(0.0, ge=0.0, le=20.0, description="Experience compatibility (max 20)")
    eligibility: float = Field(0.0, ge=0.0, le=15.0, description="Degree, grad year, work auth (max 15)")
    freshness_and_availability: float = Field(0.0, ge=0.0, le=15.0, description="Freshness and posting age (max 15)")
    location_and_arrangement: float = Field(0.0, ge=0.0, le=10.0, description="Location & work arrangement fit (max 10)")
    evidence_and_realistic_fit: float = Field(0.0, ge=0.0, le=10.0, description="Evidence quality & realistic fit (max 10)")
    total: float = Field(0.0, ge=0.0, le=100.0)

class Job(BaseModel):
    id: Optional[int] = None
    job_uid: str
    employer: str
    title: str
    normalized_title: str
    job_id_or_req: str = ""
    priority_category: int = 1  # 1 to 6
    priority_label: str = "Data Analyst / Business Intelligence"
    career_category: Optional[str] = None
    preference_rank: Optional[int] = None
    location: str = "India"
    work_arrangement: str = "Hybrid"  # On-site, Hybrid, Remote
    employment_type: str = "Full-time"
    salary: Optional[str] = "Not Disclosed"
    shift: Optional[str] = "Day shift"
    posting_date: Optional[str] = None
    posting_date_confidence: str = "UNKNOWN"
    deadline: Optional[str] = None
    official_url: str
    official_listing_url: str = ""
    application_url: str = ""
    discovery_url: str = ""
    canonical_url: str
    discovery_source: str
    verification_source: str = ""
    verification_status: VerificationStatus = VerificationStatus.PENDING_VERIFICATION
    verification_notes: str = ""
    match_score: float = 0.0
    match_tier: MatchTier = MatchTier.INELIGIBLE
    score_breakdown: Optional[ScoreBreakdown] = None
    required_skills: List[str] = Field(default_factory=list)
    preferred_skills: List[str] = Field(default_factory=list)
    supported_skills: List[str] = Field(default_factory=list)
    missing_skills: List[str] = Field(default_factory=list)
    learnable_skills: List[str] = Field(default_factory=list)
    disqualifiers: List[str] = Field(default_factory=list)
    evidence_notes: str = ""
    recommended_action: str = ""
    description: str = ""
    geographic_priority: int = 1  # 1: South India Metros & India Remote, 2: South India Regional, 3: Other Indian Hubs, 4: International/Unconfirmed
    geographic_tier_label: str = "Priority 1 — South India Metros & India Remote"
    location_eligibility_status: str = "VERIFIED_INDIA_ELIGIBLE"
    city: str = ""
    state: str = ""
    country: str = "India"
    remote_eligibility: str = "INDIA_PERMITTED"
    geo_score: float = 10.0
    is_fresher: bool = False
    is_off_campus: bool = False
    is_internship: bool = False
    is_walkin: bool = False
    min_experience_years: Optional[float] = None
    max_experience_years: Optional[float] = None
    first_discovered_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_verified_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_observed_status: str = ""
    last_observed_status_at: str = ""

class Application(BaseModel):
    id: Optional[int] = None
    job_id: int
    selected_resume_path_pdf: Optional[str] = None
    selected_resume_path_docx: Optional[str] = None
    resume_type: str = "data_analyst"
    resume_status: str = "PENDING"
    application_status: ApplicationStatus = ApplicationStatus.SAVED
    submission_confirmed_by_user: bool = False
    submission_date: Optional[str] = None
    recruiter_outreach_status: RecruiterOutreachStatus = RecruiterOutreachStatus.NOT_STARTED
    interview_stage: Optional[str] = None
    interview_date: Optional[str] = None
    follow_up_date: Optional[str] = None
    deadline: Optional[str] = None
    recruiter_name: Optional[str] = None
    recruiter_email: Optional[str] = None
    cover_letter_text: Optional[str] = None
    application_answers: Dict[str, Any] = Field(default_factory=dict)
    outreach_messages: Dict[str, Any] = Field(default_factory=dict)
    notes: Optional[str] = ""
    next_action: Optional[str] = "Review job and tailor resume"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class PreparationPlan(BaseModel):
    id: Optional[int] = None
    job_id: int
    application_id: Optional[int] = None
    role_title: str
    company: str
    target_priority: int = 1
    daily_time_allocated_hours: float = 3.5
    study_plan_blocks: List[Dict[str, Any]] = Field(default_factory=list)
    technical_topics: List[str] = Field(default_factory=list)
    practice_exercises: List[Dict[str, Any]] = Field(default_factory=list)
    interview_questions: List[Dict[str, Any]] = Field(default_factory=list)
    completed_tasks: List[str] = Field(default_factory=list)
    weak_areas: List[str] = Field(default_factory=list)
    revision_checklist: List[Dict[str, Any]] = Field(default_factory=list)
    next_revision_date: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class ResumeMetadata(BaseModel):
    id: Optional[int] = None
    job_id: int
    company_name: str
    role_title: str
    source_resume_type: str
    pdf_filename: str
    pdf_path: str
    docx_filename: str
    docx_path: str
    tailoring_summary: str
    supported_keywords: List[str] = Field(default_factory=list)
    missing_requirements: List[str] = Field(default_factory=list)
    keyword_coverage_pct: float = 0.0
    details_needing_confirmation: List[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class JobSourceItem(BaseModel):
    id: Optional[int] = None
    source_id: str
    source_name: str
    category: str
    source_type: str
    endpoint_or_board_id: str = ""
    access_method: str = "API"
    is_configured: bool = True
    is_enabled: bool = True
    last_attempt_at: Optional[str] = None
    last_success_at: Optional[str] = None
    last_discovered_count: int = 0
    last_updated_count: int = 0
    last_rejected_count: int = 0
    last_deduped_count: int = 0
    health_status: str = "UNKNOWN"
    last_error_category: Optional[str] = None
    last_error_message: Optional[str] = None
    retry_count: int = 0
    next_retry_at: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class ApplicationHistoryItem(BaseModel):
    id: Optional[int] = None
    application_id: int
    previous_status: str
    new_status: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    event_source: str = "USER_MANUAL"
    actor: str = "CANDIDATE"
    notes: Optional[str] = ""
    evidence: Optional[str] = ""

class MatchExplanation(BaseModel):
    overall_score: float = Field(0.0, ge=0.0, le=100.0)
    match_tier: MatchTier
    score_breakdown: ScoreBreakdown
    matched_requirements: List[str] = Field(default_factory=list)
    missing_requirements: List[str] = Field(default_factory=list)
    potential_blockers: List[str] = Field(default_factory=list)
    uncertain_information: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    disclaimer: str = (
        "This match score is an algorithmic assessment based on documented qualifications and vacancy text. "
        "It is not a prediction or guarantee of job offers or interview invitations."
    )
    geographic_priority: int = 1
    geographic_tier_label: str = "Priority 1 — South India Metros & India Remote"
    location_eligibility_status: str = "VERIFIED_INDIA_ELIGIBLE"
    city: str = ""
    state: str = ""
    country: str = "India"
    remote_eligibility: str = "INDIA_PERMITTED"
    geo_score: float = 10.0


# ----------------- Learning Resources & Pathways Models -----------------

class LearningResourceCreate(BaseModel):
    title: str
    category: str = "Technical Learning Materials"
    sub_category: str = ""
    canonical_url: Optional[str] = None
    primary_url: str
    all_urls: List[str] = Field(default_factory=list)
    source: str = "Manual Entry"
    raw_excerpt: str = ""
    summary: str = ""
    tags: List[str] = Field(default_factory=list)
    skill_tag: str = ""
    difficulty_level: str = "BEGINNER"
    resource_type: str = "DOCUMENTATION"
    estimated_minutes: int = 30
    notes: str = ""


class LearningResourceUpdate(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    sub_category: Optional[str] = None
    canonical_url: Optional[str] = None
    primary_url: Optional[str] = None
    all_urls: Optional[List[str]] = None
    source: Optional[str] = None
    raw_excerpt: Optional[str] = None
    summary: Optional[str] = None
    tags: Optional[List[str]] = None
    skill_tag: Optional[str] = None
    difficulty_level: Optional[str] = None
    resource_type: Optional[str] = None
    estimated_minutes: Optional[int] = None
    notes: Optional[str] = None
    is_completed: Optional[bool] = None


class LearningResourceItem(BaseModel):
    id: int
    title: str
    category: str
    sub_category: str = ""
    canonical_url: Optional[str] = None
    primary_url: str
    all_urls: List[str] = Field(default_factory=list)
    source: str = "Curated Catalog"
    source_message_uid: str = ""
    raw_excerpt: str = ""
    summary: str = ""
    tags: List[str] = Field(default_factory=list)
    saved_at: str
    notes: str = ""
    skill_tag: str = ""
    difficulty_level: str = "BEGINNER"
    resource_type: str = "DOCUMENTATION"
    estimated_minutes: int = 30
    created_at: Optional[str] = None
    is_completed: bool = False
    completed_at: Optional[str] = None


# ----------------- Daily Study Planner Models -----------------

class StudyTaskItem(BaseModel):
    task_id: str
    stage: str
    title: str
    duration_minutes: int
    skill_tag: str
    status: str = "NOT_STARTED"
    completed_at: Optional[str] = None
    explanation: str = ""
    resource_id: Optional[int] = None
    resource_title: Optional[str] = None
    resource_url: Optional[str] = None


class DailyStudyPlanCreate(BaseModel):
    target_role: Optional[str] = None
    daily_budget_minutes: int = 120
    target_priority: int = 1
    notes: Optional[str] = None


class TaskStatusUpdate(BaseModel):
    status: str
    notes: Optional[str] = None


class DailyStudyPlanItem(BaseModel):
    id: int
    plan_date: str
    target_role: str
    daily_budget_minutes: int
    target_priority: int
    skill_gaps: List[Dict[str, Any]] = Field(default_factory=list)
    user_skills: Dict[str, Any] = Field(default_factory=dict)
    tasks: List[StudyTaskItem] = Field(default_factory=list)
    schedule_blocks: List[Dict[str, Any]] = Field(default_factory=list)
    notes: str = ""
    is_completed: bool = False
    created_at: str
    updated_at: str


# ----------------- Assessment Sandbox Models -----------------

class AssessmentChallengeItem(BaseModel):
    id: int
    challenge_uid: str
    title: str
    category: str
    difficulty: str
    question_type: str = "QUERY"
    prompt_markdown: str
    initial_code: str
    test_fixtures: Dict[str, Any] = Field(default_factory=dict)
    options: List[Dict[str, str]] = Field(default_factory=list)
    time_limit_minutes: int = 30
    explanation: str = ""
    created_at: Optional[str] = None


class AssessmentChallengeCreate(BaseModel):
    challenge_uid: str
    title: str
    category: str
    difficulty: str
    question_type: str = "QUERY"
    prompt_markdown: str
    initial_code: str
    test_fixtures: Dict[str, Any] = Field(default_factory=dict)
    expected_output: Any = Field(default_factory=list)
    options: List[Dict[str, str]] = Field(default_factory=list)
    explanation: str = ""
    time_limit_minutes: int = 30


class AssessmentSubmissionCreate(BaseModel):
    submitted_code: str


class AssessmentSubmissionResult(BaseModel):
    id: Optional[int] = None
    challenge_id: int
    submitted_code: str
    is_passed: bool
    execution_time_ms: int = 0
    tests_passed: int = 0
    total_tests: int = 1
    score: float = 0.0
    feedback_notes: str = ""
    output: Any = Field(default_factory=list)
    expected_output: Optional[Any] = None
    explanation: str = ""
    created_at: Optional[str] = None


# ----------------- Interview Coach Models -----------------

class InterviewPrepNotesUpdate(BaseModel):
    notes: str = ""
    confidence_rating: Optional[int] = None


class InterviewChecklistUpdate(BaseModel):
    checklist: List[Dict[str, Any]]


class InterviewAnswerDraftCreate(BaseModel):
    question_index: int
    draft_text: str


class InterviewPrepSessionItem(BaseModel):
    id: int
    job_id: int
    employer_name: str
    role_title: str
    briefing: Dict[str, Any] = Field(default_factory=dict)
    candidate_notes: str = ""
    confidence_rating: int = 0
    checklist: List[Dict[str, Any]] = Field(default_factory=list)
    answer_drafts: Dict[str, str] = Field(default_factory=dict)
    disclaimer: str = ""
    created_at: str
    updated_at: str


# ----------------- Personalized Career Preferences Models -----------------

class CareerPreferencesUpdate(BaseModel):
    selected_categories: List[str]
    profile_id: str = "default"


class CareerPreferencesResponse(BaseModel):
    profile_id: str
    selected_categories: List[str]
    available_categories: List[Dict[str, Any]]
    updated_at: str






