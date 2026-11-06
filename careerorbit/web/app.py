"""FastAPI backend application and REST endpoints for CareerOrbit AI."""

import logging

import json

from pathlib import Path

from typing import Optional, Dict, Any, List

from contextlib import asynccontextmanager

import re

from fastapi import FastAPI, HTTPException, Query, Response, Request, status, UploadFile, File, Form

from fastapi.staticfiles import StaticFiles

from fastapi.responses import HTMLResponse, FileResponse

from fastapi.middleware.cors import CORSMiddleware

from starlette.responses import JSONResponse



logger = logging.getLogger(__name__)



from careerorbit.config.settings import (

    SETTINGS, current_data_dir, current_database_path, current_resumes_dir,

    current_logs_dir, account_storage_context, active_user_context, current_active_user,

)

from careerorbit.security.network import is_loopback_host

from careerorbit.config.profile import CANDIDATE_PROFILE, candidate_profile_context

from careerorbit.auth.store import (

    AuthUser, COOKIE_NAME, CSRF_COOKIE_NAME, account_data_dir, authenticate,

    register_user, resolve_session, revoke_session, rotate_csrf_token,

    setup_required, valid_csrf,

)

from careerorbit.config.candidate_evidence import (

    get_candidate_evidence, get_candidate_claims, candidate_evidence_summary, candidate_profile_ready_for_resume,

    set_candidate_field_evidence, export_profile_snapshot, get_profile_with_evidence,

    update_candidate_field_value, get_profile_change_history,

    list_evidence_documents, upload_evidence_document, get_evidence_document,

    delete_evidence_document, link_document_to_field,

)

from careerorbit.discovery.registry import (

    list_employer_sources, add_employer_source, update_employer_source, delete_employer_source,

    get_employer_source, record_source_check,

)

from careerorbit.database.db import (

    init_db, get_connection, list_jobs, get_job_by_id, get_job_stats,

    list_applications, get_application_by_job_id, get_application_by_id, confirm_user_submission,

    get_application_history, update_application_stage,
    delete_application, get_application_with_details, update_application_details,
    create_manual_application, export_application_history_to_csv,

    list_job_sources, get_job_source, save_job_source, update_job_source_health,

    delete_job_source, toggle_job_source_enabled,

    list_resumes, get_resume_by_id, delete_resume, list_preparation_plans, get_preparation_plan_by_job,

    export_jobs_to_csv, export_applications_to_csv, toggle_save_job, is_job_saved,

    save_job, get_job_by_uid, get_job_by_url,

    save_inbox_message, get_inbox_message, list_inbox_messages,

    get_inbox_stats, update_inbox_message_status, delete_inbox_message,

    list_community_sources, record_community_source, update_community_source,

    get_community_source_by_id, delete_community_source,

    save_learning_resource, list_learning_resources, get_learning_resource,

    delete_learning_resource, get_learning_resources_stats,

    toggle_learning_resource_completion,

    save_daily_study_plan, get_daily_study_plan, get_daily_study_plan_by_date,

    list_daily_study_plans, update_study_task_status, update_daily_study_plan,

    get_study_analytics,

    get_assessment_challenge, list_assessment_challenges,

    list_assessment_submissions, get_assessment_stats,

    get_interview_prep_session_by_job, list_interview_prep_sessions,

    update_interview_prep_session, save_interview_prep_session,

    get_interview_prep_workspace, list_interview_prep_workspaces,

    update_interview_prep_workspace,

)

from careerorbit.prep.pathways import get_learning_pathways

from careerorbit.prep.curated_resources import seed_curated_learning_resources

from careerorbit.whatsapp import WhatsAppChatExportParser, WhatsAppExportAdapter

from careerorbit.discovery.engine import JobDiscoveryEngine

from careerorbit.discovery.manager import DISCOVERY_MANAGER, DiscoveryManager

from careerorbit.discovery.sources import (

    GreenhouseBoardSource, LeverSiteSource, SmartRecruitersSource, AshbyJobBoardSource, WorkableSource,

    UnstopSource, RemoteOKSource

)

from careerorbit.discovery.community_parser import CommunityJobParser

from careerorbit.models.schemas import (

    Job, VerificationStatus, MatchTier, ApplicationStatus, MatchExplanation, canonicalize_application_stage,

    DailyStudyPlanCreate, TaskStatusUpdate, AssessmentSubmissionCreate,

    InterviewPrepNotesUpdate, InterviewChecklistUpdate, InterviewAnswerDraftCreate

)

from careerorbit.matcher.scorer import JobScorer

from careerorbit.packages.generator import ApplicationPackageGenerator

from careerorbit.prep.study_planner import DailyStudyPlanner

from careerorbit.prep.interview_coach import InterviewCoach

from careerorbit.prep.assessment_sandbox import evaluate_submission, seed_assessment_challenges

from careerorbit.resumes.generator import ResumeService

from careerorbit.verifier.checker import VerificationEngine

from careerorbit.verifier.worker import VERIFICATION_WORKER, VerificationWorker

from careerorbit.scheduler.runner import SCHEDULER

from careerorbit.scheduler.run_history import recent_runs

from careerorbit.telegram import TELEGRAM_WORKER, TelegramService, TelegramContentClassifier, TelegramClient





def _is_primary_account_storage() -> bool:

    if current_data_dir().resolve() == SETTINGS.DATA_DIR.resolve():
        return True
    user = current_active_user()
    if user:
        primary = (getattr(SETTINGS, "PRIMARY_ACCOUNT", "") or "").strip().lower()
        if primary:
            if user.email.lower() == primary or user.storage_key.lower() == primary or user.user_id.lower() == primary:
                return True
        else:
            return True
    if (current_data_dir() / ".env").exists():
        return True
    return False





def _require_primary_telegram_account() -> None:

    if not _is_primary_account_storage():

        raise HTTPException(

            status_code=403,

            detail="Live Telegram credentials are configured for the primary local workspace only.",

        )



@asynccontextmanager

async def lifespan(app: FastAPI):

    init_db()

    if not SETTINGS.TESTING and not setup_required():

        SCHEDULER.start()

        if SETTINGS.is_telegram_configured:

            TELEGRAM_WORKER.start()

    yield

    if not SETTINGS.TESTING:

        TELEGRAM_WORKER.stop()

        SCHEDULER.stop()



app = FastAPI(title="CareerOrbit AI", version="1.0.0", lifespan=lifespan)



def _u(val, default=None):

    return default if hasattr(val, "default") else val



# Security: exact-origin CORS allowlist; same-origin production UI does not need cross-origin access.

ALLOWED_CORS_ORIGINS = [

    "http://127.0.0.1:8000",

    "http://localhost:8000",

    "http://127.0.0.1:3000",

    "http://localhost:3000",

]



app.add_middleware(

    CORSMiddleware,

    allow_origins=ALLOWED_CORS_ORIGINS,

    allow_credentials=False,

    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],

    allow_headers=["*"],

)



@app.middleware("http")

async def add_security_headers(request: Request, call_next):

    client = request.client

    request_host = request.url.hostname or ""

    unsafe_method = request.method.upper() not in {"GET", "HEAD", "OPTIONS"}

    origin = request.headers.get("origin")

    fetch_site = request.headers.get("sec-fetch-site", "").lower()

    current_origin = f"{request.url.scheme}://{request.url.netloc}"

    allowed_write_origins = set(ALLOWED_CORS_ORIGINS) | {current_origin}

    remote_peer = client is None or not is_loopback_host(client.host)

    non_loopback_host = not is_loopback_host(request_host)

    cross_site_write = unsafe_method and (

        (origin is not None and origin not in allowed_write_origins)

        or fetch_site == "cross-site"

    )



    if (not SETTINGS.TESTING and remote_peer) or non_loopback_host or cross_site_write:

        response = JSONResponse(status_code=403, content={"detail": "CareerOrbit is available only from this device."})

    else:

        path = request.url.path

        auth_public_paths = {

            "/api/auth/status", "/api/auth/register", "/api/auth/login",

        }

        public_health_paths = {

            "/health", "/api/health/liveness", "/api/health/readiness",

        }

        is_protected_api = path.startswith("/api/") and path not in auth_public_paths | public_health_paths

        is_dashboard_html = path == "/" or path == "/static/index.html"

        raw_session = request.cookies.get(COOKIE_NAME)

        session = resolve_session(raw_session) if (is_protected_api or is_dashboard_html) else None



        if is_protected_api and session is None:

            response = JSONResponse(status_code=401, content={"detail": "Authentication required."})

        elif is_dashboard_html and session is None and path == "/static/index.html":

            response = JSONResponse(status_code=404, content={"detail": "Not found."})

        elif session is not None and unsafe_method:

            csrf_cookie = request.cookies.get(CSRF_COOKIE_NAME)

            csrf_header = request.headers.get("x-csrf-token")

            if not valid_csrf(csrf_cookie, session[1]) or not valid_csrf(csrf_header, session[1]):

                response = JSONResponse(status_code=403, content={"detail": "Request verification failed. Refresh and try again."})

            else:

                request.state.user = session[0]

                request.state.session_csrf_hash = session[1]

                with account_storage_context(account_data_dir(session[0])), candidate_profile_context(account_data_dir(session[0])), active_user_context(session[0]):

                    response = await call_next(request)

        elif session is not None:

            request.state.user = session[0]

            request.state.session_csrf_hash = session[1]

            with account_storage_context(account_data_dir(session[0])), candidate_profile_context(account_data_dir(session[0])), active_user_context(session[0]):

                response = await call_next(request)

        else:

            request.state.user = None

            response = await call_next(request)

    response.headers["X-Content-Type-Options"] = "nosniff"

    response.headers["X-Frame-Options"] = "DENY"

    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    response.headers["X-XSS-Protection"] = "1; mode=block"

    if request.url.path.startswith("/api/") or request.url.path == "/":

        response.headers["Cache-Control"] = "no-store"

    return response



# ----------------- UI Route -----------------



STATIC_DIR = Path(__file__).parent / "static"

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")



MAX_TELEGRAM_EXPORT_BYTES = 50 * 1024 * 1024





def _check_telegram_export_content_length(request: Request, *, required: bool = False) -> None:

    raw_length = request.headers.get("content-length")

    if raw_length is None:

        if required:

            raise HTTPException(status_code=411, detail="Content-Length is required for multipart exports.")

        return

    try:

        content_length = int(raw_length)

    except (TypeError, ValueError):

        raise HTTPException(status_code=400, detail="Invalid Content-Length header.")

    if content_length < 0:

        raise HTTPException(status_code=400, detail="Invalid Content-Length header.")

    if content_length > MAX_TELEGRAM_EXPORT_BYTES:

        raise HTTPException(status_code=413, detail="Telegram export exceeds the 50 MiB limit.")





async def _read_telegram_export_json(request: Request) -> Dict[str, Any]:

    _check_telegram_export_content_length(request)

    chunks = []

    total = 0

    async for chunk in request.stream():

        total += len(chunk)

        if total > MAX_TELEGRAM_EXPORT_BYTES:

            raise HTTPException(status_code=413, detail="Telegram export exceeds the 50 MiB limit.")

        chunks.append(chunk)

    try:

        payload = json.loads(b"".join(chunks))

    except (ValueError, UnicodeDecodeError):

        raise HTTPException(status_code=400, detail="Invalid JSON payload.")

    if not isinstance(payload, dict):

        raise HTTPException(status_code=400, detail="JSON payload must be an object.")

    return payload





def _validated_telegram_export_filename(filename: Any) -> str:

    if not isinstance(filename, str) or not filename.strip():

        raise HTTPException(status_code=400, detail="A Telegram export filename is required.")

    safe_name = Path(filename.replace("\\", "/")).name

    if len(safe_name) > 255 or Path(safe_name).suffix.lower() not in {".json", ".html", ".htm"}:

        raise HTTPException(status_code=400, detail="Telegram export must be a .json, .html, or .htm file.")

    return safe_name





async def _read_telegram_export_upload(file: Any) -> tuple[bytes, str]:

    filename = _validated_telegram_export_filename(getattr(file, "filename", None) or "export.json")

    size = getattr(file, "size", None)

    if size is not None and size > MAX_TELEGRAM_EXPORT_BYTES:

        raise HTTPException(status_code=413, detail="Telegram export exceeds the 50 MiB limit.")

    content = await file.read(MAX_TELEGRAM_EXPORT_BYTES + 1)

    if len(content) > MAX_TELEGRAM_EXPORT_BYTES:

        raise HTTPException(status_code=413, detail="Telegram export exceeds the 50 MiB limit.")

    return content, filename



@app.get("/", response_class=HTMLResponse)

def get_dashboard(request: Request):

    if getattr(request.state, "user", None) is None:

        login_file = STATIC_DIR / "login.html"

        if login_file.exists():

            return HTMLResponse(content=login_file.read_text(encoding="utf-8"))

        return HTMLResponse("<h1>CareerOrbit AI</h1><p>Login page unavailable.</p>", status_code=503)

    index_file = STATIC_DIR / "index.html"

    if index_file.exists():

        return HTMLResponse(content=index_file.read_text(encoding="utf-8"))

    return HTMLResponse("<h1>CareerOrbit AI Dashboard</h1><p>Static index.html not found.</p>")





def _set_auth_cookies(response: Response, request: Request, session_token: str, csrf_token: str) -> None:

    secure = request.url.scheme.lower() == "https"

    response.set_cookie(

        COOKIE_NAME, session_token, max_age=12 * 60 * 60, httponly=True,

        secure=secure, samesite="strict", path="/",

    )

    response.set_cookie(

        CSRF_COOKIE_NAME, csrf_token, max_age=12 * 60 * 60, httponly=False,

        secure=secure, samesite="strict", path="/",

    )





@app.get("/api/auth/status")

def get_auth_status():

    return {"setup_required": setup_required(), "registration_enabled": True}





@app.post("/api/auth/register")

def register_account(payload: Dict[str, Any], request: Request, response: Response):

    try:

        user, session_token, csrf_token = register_user(

            email=str(payload.get("email", "")),

            password=payload.get("password", ""),

            display_name=str(payload.get("display_name", "")),

            ip_address=request.client.host if request.client else "local",

        )

    except ValueError as exc:

        raise HTTPException(status_code=400, detail=str(exc))

    except Exception:

        logger.exception("Local account registration failed")

        raise HTTPException(status_code=500, detail="Could not create the account. Check local storage and try again.")

    _set_auth_cookies(response, request, session_token, csrf_token)

    return {"status": "success", "user": user.public_dict()}





@app.post("/api/auth/login")

def login_account(payload: Dict[str, Any], request: Request, response: Response):

    result = authenticate(

        str(payload.get("email", "")),

        payload.get("password", ""),

        ip_address=request.client.host if request.client else "local",

    )

    if result is None:

        raise HTTPException(status_code=401, detail="Email or password is incorrect, or sign-in is temporarily limited.")

    user, session_token, csrf_token = result

    _set_auth_cookies(response, request, session_token, csrf_token)

    return {"status": "success", "user": user.public_dict()}





@app.get("/api/auth/me")

def get_current_account(request: Request, response: Response):

    user = getattr(request.state, "user", None)

    if user is None:

        raise HTTPException(status_code=401, detail="Authentication required.")

    csrf_token = request.cookies.get(CSRF_COOKIE_NAME)

    csrf_hash = getattr(request.state, "session_csrf_hash", "")

    if not valid_csrf(csrf_token, csrf_hash):

        csrf_token = rotate_csrf_token(request.cookies.get(COOKIE_NAME, ""))

        if csrf_token is None:

            raise HTTPException(status_code=401, detail="Session expired. Sign in again.")

        _set_auth_cookies(response, request, request.cookies[COOKIE_NAME], csrf_token)

    return {"authenticated": True, "user": user.public_dict(), "csrf_token": csrf_token}





@app.post("/api/auth/logout")

def logout_account(request: Request, response: Response):

    revoke_session(request.cookies.get(COOKIE_NAME))

    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, samesite="strict")

    response.delete_cookie(CSRF_COOKIE_NAME, path="/", samesite="strict")

    return {"status": "success"}



@app.get("/api/health")

@app.get("/health")

def get_health():

    db_ok = True

    try:

        with get_connection() as conn:

            conn.execute("SELECT 1").fetchone()

    except Exception:

        db_ok = False



    return {

        "status": "healthy" if db_ok else "degraded",

        "app": "CareerOrbit AI",

        "version": "2.0.0",

        "environment": "production",

        "liveness": "alive",

        "readiness": "ready" if db_ok else "unready",

        "database": {"connected": db_ok},

        "discovery": {

            "is_running": DiscoveryManager.get_current_instance().is_running(),

            "latest_run": DiscoveryManager.get_current_instance().get_status(),

        },

        "telegram": {

            "configured": SETTINGS.is_telegram_configured if _is_primary_account_storage() else False,

            "running": TELEGRAM_WORKER.is_running if _is_primary_account_storage() else False,

            "masked_token": SETTINGS.masked_telegram_token if _is_primary_account_storage() else "",

            "last_poll_status": TELEGRAM_WORKER.last_poll_status if _is_primary_account_storage() else "ACCOUNT_SCOPED_UNAVAILABLE",

        },

        "whatsapp": {

            "import_capability": "ready",

            "supported_formats": ["android_txt", "ios_txt", "desktop_txt"],

        },

        "scheduler": {

            "running": SCHEDULER.running,

            "canonical_task_name": getattr(SETTINGS, "WINDOWS_TASK_NAME", "CareerOrbit_Daily_Job_Search"),

            "target_discovery_time": f"08:00 AM {SETTINGS.TIMEZONE}",

            "study_plan_automation": "disabled_on_demand_only",

            "windows_task_configured": SCHEDULER.get_windows_task_status().get("configured", False),

        }

    }



@app.get("/api/health/liveness")

def get_liveness():

    return {

        "status": "alive",

        "app": "CareerOrbit AI",

        "version": "2.0.0"

    }



@app.get("/api/health/readiness")

def get_readiness():

    try:

        with get_connection() as conn:

            conn.execute("SELECT 1").fetchone()

        return {

            "status": "ready",

            "database": "connected",

            "storage": "accessible"

        }

    except Exception as exc:

        raise HTTPException(status_code=503, detail=f"Service Not Ready: {exc}")



@app.get("/api/health/db")

def get_db_health():

    try:

        with get_connection() as conn:

            cur = conn.cursor()

            cur.execute("PRAGMA quick_check")

            integrity = cur.fetchone()[0]

            cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")

            tables = [r[0] for r in cur.fetchall() if not r[0].startswith("sqlite_")]

            table_counts = {}

            for t in tables:

                cur.execute(f'SELECT count(*) FROM "{t}"')

                table_counts[t] = cur.fetchone()[0]

            cur.execute("SELECT version, applied_at FROM schema_migrations ORDER BY applied_at DESC LIMIT 1")

            last_mig = cur.fetchone()

            last_mig_dict = {"version": last_mig[0], "applied_at": last_mig[1]} if last_mig else None



        db_file = current_database_path()

        size_bytes = db_file.stat().st_size if db_file.exists() else 0

        return {

            "status": "healthy" if integrity == "ok" else "corrupt",

            "integrity": integrity,

            "database_file": db_file.name,

            "size_bytes": size_bytes,

            "tables": table_counts,

            "last_migration": last_mig_dict,

        }

    except Exception as exc:

        raise HTTPException(status_code=500, detail=f"Database health check failed: {exc}")



@app.get("/api/health/sources")

def get_sources_health():

    engine = JobDiscoveryEngine()

    sources_status = []

    for s in engine.sources:

        is_cfg = getattr(s, "configured", True)

        sources_status.append({

            "name": s.name,

            "configured": is_cfg,

            "endpoint": getattr(s, "endpoint", "N/A"),

            "geo_coverage": "India / Worldwide Remote" if "Remote" in s.name or "Unstop" in s.name else "Configured Employer",

            "role_coverage": "Tiers 1-6 (Data / Software / AI / Tech)",

        })

    return {

        "count": len(sources_status),

        "configured_count": sum(1 for s in sources_status if s["configured"]),

        "sources": sources_status

    }



@app.get("/api/health/telegram")

def get_telegram_health():

    if not _is_primary_account_storage():

        return {"status": "ACCOUNT_SCOPED_UNAVAILABLE", "configured": False, "running": False}

    return TELEGRAM_WORKER.get_status()



@app.get("/api/health/scheduler")

@app.get("/api/scheduler/status")

def get_scheduler_health():

    return SCHEDULER.get_status()



# ----------------- REST API Endpoints -----------------



@app.get("/api/profile")

def get_profile():

    from careerorbit.career_priorities import load_user_career_preferences

    return {

        # Legacy values are individually paired with evidence state. Contact

        # values are always withheld from the dashboard API.

        "candidate_evidence": get_candidate_evidence(),

        "candidate_claims": get_candidate_claims(),

        "candidate_evidence_summary": candidate_evidence_summary(),

        "career_preferences": load_user_career_preferences("default").to_dict(),

    }



@app.get("/api/stats")

def get_stats():

    stats = get_job_stats()

    if not candidate_profile_ready_for_resume():

        stats["strong_matches"] = None

        stats["reasonable_matches"] = None

        stats["stretch_opportunities"] = None

    scheduler_status = SCHEDULER.get_status()

    return {

        "metrics": stats,

        "scheduler": scheduler_status,

        "candidate_evidence": candidate_evidence_summary(),

    }



@app.get("/api/jobs")

def get_jobs(

    priority: Optional[int] = Query(None),

    category: Optional[str] = Query(None),

    profile_id: str = Query("default"),

    geographic_priority: Optional[int] = Query(None),

    match_tier: Optional[str] = Query(None),

    verification_status: Optional[str] = Query(None),

    location: Optional[str] = Query(None),

    city: Optional[str] = Query(None),

    state: Optional[str] = Query(None),

    country: Optional[str] = Query(None),

    remote_eligibility: Optional[str] = Query(None),

    location_eligibility_status: Optional[str] = Query(None),

    search: Optional[str] = Query(None),

    min_score: Optional[float] = Query(None),

    work_arrangement: Optional[str] = Query(None),

    employment_type: Optional[str] = Query(None),

    employer: Optional[str] = Query(None),

    discovery_source: Optional[str] = Query(None),

    is_fresher: Optional[bool] = Query(None),

    is_off_campus: Optional[bool] = Query(None),

    is_internship: Optional[bool] = Query(None),

    recency_days: Optional[int] = Query(None),

    saved_only: bool = Query(False),

    sort_by: str = Query("priority_first"),

    limit: int = 100,

    offset: int = 0

):

    def _u(val, default=None):

        return default if hasattr(val, "default") else val



    priority = _u(priority)

    category = _u(category)

    profile_id = _u(profile_id, "default")

    geographic_priority = _u(geographic_priority)

    match_tier = _u(match_tier)

    verification_status = _u(verification_status)

    location = _u(location)

    city = _u(city)

    state = _u(state)

    country = _u(country)

    remote_eligibility = _u(remote_eligibility)

    location_eligibility_status = _u(location_eligibility_status)

    search = _u(search)

    min_score = _u(min_score)

    work_arrangement = _u(work_arrangement)

    employment_type = _u(employment_type)

    employer = _u(employer)

    discovery_source = _u(discovery_source)

    is_fresher = _u(is_fresher)

    is_off_campus = _u(is_off_campus)

    is_internship = _u(is_internship)

    recency_days = _u(recency_days)

    saved_only = _u(saved_only, False)

    sort_by = _u(sort_by, "priority_first")

    limit = _u(limit, 100)

    offset = _u(offset, 0)



    fit_ready = candidate_profile_ready_for_resume()

    if (match_tier or min_score is not None) and not fit_ready:

        raise HTTPException(status_code=409, detail="Candidate-fit filtering is unavailable until candidate facts are reviewed.")

    jobs = list_jobs(

        priority=priority,

        category=category,

        geographic_priority=geographic_priority,

        match_tier=match_tier,

        verification_status=verification_status,

        location_search=location,

        city=city,

        state=state,

        country=country,

        remote_eligibility=remote_eligibility,

        location_eligibility_status=location_eligibility_status,

        search=search,

        min_score=min_score,

        work_arrangement=work_arrangement,

        employment_type=employment_type,

        employer=employer,

        discovery_source=discovery_source,

        is_fresher=is_fresher,

        is_off_campus=is_off_campus,

        is_internship=is_internship,

        recency_days=recency_days,

        include_quarantined=False,

        saved_only=saved_only,

        sort_by=sort_by,

        limit=limit,

        offset=offset,

        profile_id=profile_id,

    )

    for job in jobs:

        _present_candidate_fit(job, fit_ready)

    return {"count": len(jobs), "jobs": jobs}



@app.post("/api/jobs/{job_id}/save")

def save_or_unsave_job(job_id: int):

    job = get_job_by_id(job_id)

    if not job:

        raise HTTPException(status_code=404, detail="Job not found")

    if job.get("record_state") == "QUARANTINED":

        raise HTTPException(status_code=404, detail="Quarantined records cannot be saved as job leads.")

    saved = toggle_save_job(job_id)

    return {"job_id": job_id, "is_saved": saved, "message": "Job bookmarked" if saved else "Bookmark removed"}



@app.get("/api/jobs/{job_id}")

def get_single_job(job_id: int):

    job = get_job_by_id(job_id)

    if not job:

        raise HTTPException(status_code=404, detail="Job not found")

    if job.get("record_state") == "QUARANTINED":

        raise HTTPException(status_code=404, detail="This record is quarantined pending evidence review.")

    ready = candidate_profile_ready_for_resume()

    _present_candidate_fit(job, ready)

    job["is_saved"] = is_job_saved(job_id)

    if ready:

        scored = JobScorer().score_job(job)

        job["matched_requirements"] = scored.get("matched_requirements", [])

        job["missing_requirements"] = scored.get("missing_requirements", [])

        job["potential_blockers"] = scored.get("potential_blockers", [])

        job["uncertain_information"] = scored.get("uncertain_information", [])

        job["recommendations"] = scored.get("recommendations", [])

        job["disclaimer"] = scored.get("disclaimer", "")

        job["match_explanation"] = scored.get("match_explanation", {})

    return job



def _present_candidate_fit(job: dict[str, Any], ready: bool) -> None:

    job["candidate_fit_state"] = "READY" if ready else "NEEDS_CANDIDATE_REVIEW"

    job["candidate_fit_score"] = job.get("match_score") if ready else None

    disqualifiers = job.get("disqualifiers") or []

    job["mandatory_eligibility_result"] = (

        ("INELIGIBLE" if disqualifiers else "ELIGIBLE") if ready else "NEEDS_CANDIDATE_REVIEW"

    )

    job["candidate_fit_tier"] = job.get("match_tier") if ready else "NEEDS_CANDIDATE_REVIEW"

    job["application_url_verification_status"] = (

        "VERIFIED" if job.get("verification_status") == "VERIFIED_OPEN"

        and job.get("official_listing_url") and job.get("application_url")

        else ("UNVERIFIED" if job.get("application_url") else "UNAVAILABLE")

    )

    job["source_evidence_quality"] = (

        "JOB_SPECIFIC_OFFICIAL_ATS" if job.get("verification_source") and job.get("official_listing_url")

        else ("THIRD_PARTY_DISCOVERY" if job.get("discovery_source") in {

            "Jobicy Public API", "Remotive Public API", "Arbeitnow Public API"

        } else "INSUFFICIENT")

    )

    if not ready:

        job["match_score"] = None

        job["match_tier"] = "NEEDS_CANDIDATE_REVIEW"

        job["score_breakdown"] = {}

        job["supported_skills"] = []

        job["missing_skills"] = []

        job["learnable_skills"] = []

        job["evidence_notes"] = "Candidate profile facts are not yet source-verified or confirmed."



@app.get("/api/dashboard")

def get_dashboard_stats():

    return get_stats()



@app.get("/api/profile/full")

def get_full_profile():

    return get_profile_with_evidence()



@app.get("/api/profile/snapshot")

def get_profile_snapshot():

    return export_profile_snapshot()



@app.post("/api/profile/field")

def edit_candidate_field(payload: Dict[str, Any]):

    field = (payload or {}).get("field") or (payload or {}).get("field_name") or ""

    value = (payload or {}).get("value")

    state = (payload or {}).get("state") or (payload or {}).get("evidence_state") or "CONFIRMED"

    note = (payload or {}).get("note") or (payload or {}).get("notes") or (payload or {}).get("source") or ""

    author = (payload or {}).get("author", "Candidate")

    if not field:

        raise HTTPException(status_code=400, detail="Field path is required")

    try:

        res = update_candidate_field_value(field=field, new_value=value, state=state, note=note, author=author)

        return {"status": "success", **res}

    except KeyError as exc:

        raise HTTPException(status_code=404, detail=str(exc))

    except Exception as exc:

        raise HTTPException(status_code=400, detail=str(exc))



@app.get("/api/profile/history")

def get_profile_history(limit: int = 50):

    return {"history": get_profile_change_history(limit=limit)}



@app.post("/api/profile/evidence")

def update_candidate_evidence(payload: Dict[str, Any]):

    field = str((payload or {}).get("field") or "").strip()

    state = str((payload or {}).get("state") or "").strip()

    evidence = str((payload or {}).get("evidence") or "").strip()

    doc_id = (payload or {}).get("document_id")

    if doc_id is not None:

        doc_id = str(doc_id).strip()

    try:

        updated = set_candidate_field_evidence(field, state, evidence, document_id=doc_id)

    except KeyError:

        raise HTTPException(status_code=404, detail="Unknown candidate field")

    except ValueError as exc:

        raise HTTPException(status_code=400, detail=str(exc))

    return {"field": updated, "summary": candidate_evidence_summary()}





@app.get("/api/profile/evidence/documents")

def get_evidence_documents():

    """List all candidate source evidence documents."""

    return {"documents": list_evidence_documents()}





@app.post("/api/profile/evidence/documents")

def upload_evidence_document_endpoint(payload: Dict[str, Any]):

    """Upload a candidate source evidence document via JSON payload with base64 data."""

    filename = str((payload or {}).get("filename") or "").strip()

    file_b64 = str((payload or {}).get("file_base64") or "").strip()

    doc_type = str((payload or {}).get("doc_type") or "OTHER").strip()

    notes = str((payload or {}).get("notes") or "").strip()

    author = str((payload or {}).get("author") or "Candidate").strip()



    if not filename or not file_b64:

        raise HTTPException(status_code=400, detail="Filename and base64 file data are required.")



    import base64

    try:

        file_bytes = base64.b64decode(file_b64)

    except Exception as exc:

        raise HTTPException(status_code=400, detail=f"Invalid base64 encoding: {exc}")



    try:

        doc = upload_evidence_document(file_bytes=file_bytes, filename=filename, doc_type=doc_type, notes=notes, author=author)

        return {"status": "success", "document": doc}

    except ValueError as exc:

        raise HTTPException(status_code=400, detail=str(exc))

    except Exception as exc:

        raise HTTPException(status_code=500, detail=f"Failed to save document: {exc}")





@app.get("/api/profile/evidence/documents/{doc_id}")

def retrieve_evidence_document(doc_id: str):

    """Retrieve evidence document metadata and base64 contents."""

    import base64

    try:

        doc, content = get_evidence_document(doc_id)

        return {

            "document": doc,

            "content_base64": base64.b64encode(content).decode("ascii"),

        }

    except KeyError:

        raise HTTPException(status_code=404, detail="Document not found.")

    except FileNotFoundError:

        raise HTTPException(status_code=404, detail="Document file missing on disk.")





@app.delete("/api/profile/evidence/documents/{doc_id}")

def delete_evidence_document_endpoint(doc_id: str):

    """Delete an evidence document and downgrade any linked fields."""

    success = delete_evidence_document(doc_id)

    if not success:

        raise HTTPException(status_code=404, detail="Document not found.")

    return {"status": "deleted", "document_id": doc_id, "summary": candidate_evidence_summary()}





@app.post("/api/profile/evidence/verify-field")

def verify_field_with_document_endpoint(payload: Dict[str, Any]):

    """Link a candidate profile field to a source document, verifying it from source."""

    field = str((payload or {}).get("field") or "").strip()

    doc_id = str((payload or {}).get("document_id") or "").strip()

    notes = str((payload or {}).get("notes") or "").strip()

    author = str((payload or {}).get("author") or "Candidate").strip()



    if not field or not doc_id:

        raise HTTPException(status_code=400, detail="Field and document_id are required.")



    try:

        res = link_document_to_field(field=field, doc_id=doc_id, notes=notes, author=author)

        return {"status": "success", **res}

    except KeyError as exc:

        raise HTTPException(status_code=404, detail=str(exc))

    except ValueError as exc:

        raise HTTPException(status_code=400, detail=str(exc))





# ----------------- Personalized Career Preferences Endpoints -----------------



@app.get("/api/career-categories")

def get_career_categories():

    """Returns platform-supported career category taxonomy."""

    from careerorbit.career_priorities import list_supported_categories

    return {"categories": list_supported_categories()}





@app.get("/api/profile/preferences")

def get_career_preferences(profile_id: str = Query("default")):

    """Returns current saved career priorities for candidate profile."""

    from careerorbit.career_priorities import (

        load_user_career_preferences, list_supported_categories, preference_category_dict,

    )

    prefs = load_user_career_preferences(profile_id=profile_id)

    available = list_supported_categories()

    known_ids = {item["id"] for item in available}

    for category_id in prefs.selected_categories:

        if category_id not in known_ids:

            custom_category = preference_category_dict(category_id)

            if custom_category:

                available.append(custom_category)

                known_ids.add(category_id)

    return {

        "profile_id": prefs.profile_id,

        "selected_categories": prefs.selected_categories,

        "available_categories": available,

        "updated_at": prefs.updated_at,

    }





@app.post("/api/profile/preferences")

def update_career_preferences(payload: Dict[str, Any]):

    """Saves candidate personalized career priority ordering."""

    from careerorbit.career_priorities import UserCareerPreferences, save_user_career_preferences

    profile_id = (payload or {}).get("profile_id", "default")

    selected = (payload or {}).get("selected_categories")

    if selected is None:

        raise HTTPException(status_code=400, detail="selected_categories is required")

    try:

        user_prefs = UserCareerPreferences(

            profile_id=profile_id,

            selected_categories=selected,

            updated_at=""

        )

        saved = save_user_career_preferences(user_prefs)

        return {

            "status": "success",

            "profile_id": saved.profile_id,

            "selected_categories": saved.selected_categories,

            "updated_at": saved.updated_at,

        }

    except ValueError as exc:

        raise HTTPException(status_code=400, detail=str(exc))

    except Exception as exc:

        raise HTTPException(status_code=500, detail=f"Failed to persist career preferences: {exc}")





@app.post("/api/profile/preferences/reset")

def reset_career_preferences(payload: Optional[Dict[str, Any]] = None):

    """Resets candidate career priorities to platform default order."""

    from careerorbit.career_priorities import reset_user_career_preferences

    profile_id = (payload or {}).get("profile_id", "default") if payload else "default"

    try:

        reset_prefs = reset_user_career_preferences(profile_id=profile_id)

        return {

            "status": "success",

            "profile_id": reset_prefs.profile_id,

            "selected_categories": reset_prefs.selected_categories,

            "updated_at": reset_prefs.updated_at,

        }

    except Exception as exc:

        raise HTTPException(status_code=500, detail=f"Failed to reset preferences: {exc}")





@app.post("/api/discovery/trigger")

def trigger_discovery(response: Response):

    result = DiscoveryManager.get_current_instance().start_discovery()

    if result.get("status") == "accepted":

        response.status_code = status.HTTP_202_ACCEPTED

    return result



@app.get("/api/discovery/status")

@app.get("/api/discovery/status/{run_id}")

def get_discovery_status(run_id: Optional[str] = None):

    return DiscoveryManager.get_current_instance().get_status(run_id)



@app.get("/api/applications")

def get_applications():

    apps = list_applications()

    for row in apps:

        needs_review = row.get("candidate_review_state") == "NEEDS_CONFIRMATION"

        row["presented_application_status"] = "NEEDS_CANDIDATE_REVIEW" if needs_review else row.get("application_status")

        row["presented_submission_confirmed"] = bool(

            not needs_review and row.get("submission_evidence_state") == "CONFIRMED_BY_CANDIDATE"

            and row.get("submission_confirmed_by_user")

        )

        row["cover_letter_text"] = _redact_contact_text(row.get("cover_letter_text") or "")

        row["outreach_messages"] = _redact_private_values(row.get("outreach_messages") or {})

        row["application_answers"] = _redact_private_values(row.get("application_answers") or {})

        row["notes"] = _redact_contact_text(row.get("notes") or "")

        if needs_review:

            row["presented_notes"] = "Legacy application record requires candidate review; stored notes and status are not confirmed."

        else:

            row["presented_notes"] = row["notes"]

    return {"count": len(apps), "applications": apps}





@app.post("/api/interview-prep/from-application/{application_id}")

def prepare_role_interview_from_application(application_id: int):

    """Start general interview practice from a saved application, without resume or match gates."""

    application = get_application_by_id(application_id)

    if not application:

        raise HTTPException(status_code=404, detail="Application not found.")

    job = get_job_by_id(int(application["job_id"]))

    if not job:

        raise HTTPException(status_code=404, detail="The job linked to this application was not found.")

    role_title = str(job.get("title") or application.get("title") or "").strip()

    if not role_title:

        raise HTTPException(status_code=409, detail="This application has no role title to prepare for.")

    stage = application.get("stage") or application.get("application_status") or application.get("status") or ""

    try:

        return InterviewCoach.create_role_workspace(

            role_title,

            str(job.get("description") or ""),

            application_context={

                "application_id": application_id,

                "employer": job.get("employer") or application.get("employer") or "",

                "stage": stage,

            },

        )

    except ValueError as exc:

        raise HTTPException(status_code=422, detail=str(exc))



def _redact_contact_text(value: str) -> str:

    value = re.sub(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", "[contact withheld]", value)

    return re.sub(r"(?<!\w)(?:\+?\d[\d .()\-]{7,}\d)(?!\w)", "[contact withheld]", value)



def _redact_private_values(value: Any) -> Any:

    if isinstance(value, str):

        return _redact_contact_text(value)

    if isinstance(value, dict):

        hidden_keys = {"email", "phone", "linkedin", "github"}

        return {key: ("[withheld]" if key.lower() in hidden_keys else _redact_private_values(item)) for key, item in value.items()}

    if isinstance(value, list):

        return [_redact_private_values(item) for item in value]

    return value



@app.post("/api/applications/prepare/{job_id}")

def prepare_application_package(job_id: int):

    job = get_job_by_id(job_id)

    if not job:

        raise HTTPException(status_code=404, detail="Job not found")

    if job.get("record_state") == "QUARANTINED":

        raise HTTPException(status_code=409, detail="Quarantined records cannot be used to prepare an application.")

    if (job.get("verification_status") != "VERIFIED_OPEN" or not job.get("official_listing_url")

            or not job.get("application_url")):

        raise HTTPException(status_code=409, detail="Application preparation requires a verified-open job and verified application destination.")

    if not candidate_profile_ready_for_resume():

        raise HTTPException(status_code=409, detail="Application preparation is paused until candidate facts are verified or confirmed.")

    

    pkg_gen = ApplicationPackageGenerator()

    pkg = pkg_gen.prepare_package_for_job(job)

    

    # Also generate interview prep package

    coach = InterviewCoach()

    coach.generate_prep_package(job, application_id=pkg["application_id"])



    return pkg



@app.post("/api/resumes/generate/{job_id}")

def generate_tailored_resume(job_id: int):

    job = get_job_by_id(job_id)

    if not job:

        raise HTTPException(status_code=404, detail="Job not found")

    if job.get("record_state") == "QUARANTINED":

        raise HTTPException(status_code=409, detail="Quarantined records cannot generate candidate materials.")

    if (job.get("verification_status") != "VERIFIED_OPEN" or not job.get("official_listing_url")

            or not job.get("application_url") or job.get("match_tier") not in ("Strong match", "Reasonable match")):

        raise HTTPException(status_code=409, detail="Resume generation requires a verified-open job, application URL, and eligible fit.")

    if not candidate_profile_ready_for_resume():

        raise HTTPException(status_code=409, detail="Resume generation is paused: candidate facts require source verification or explicit candidate confirmation.")

    generated = ResumeService().generate_resumes_for_job(

        job_id=job_id, company_name=job["employer"], role_title=job["title"],

        job_description=job.get("description") or "", priority_category=job["priority_category"]

    )

    return generated



@app.get("/api/prep/interview/{job_id}")

@app.post("/api/prep/interview/{job_id}")

def prepare_interview(job_id: int):

    job = get_job_by_id(job_id)

    if not job:

        raise HTTPException(status_code=404, detail="Job not found")

    if job.get("record_state") == "QUARANTINED":

        raise HTTPException(status_code=409, detail="Quarantined records cannot start interview preparation.")

    try:

        # Interview practice is a role-learning workflow. Vacancy verification and

        # candidate-evidence gates apply to application/resume generation, not to

        # preparing for a role from its title and supplied description.

        return InterviewCoach.create_role_workspace(

            str(job.get("title") or ""),

            str(job.get("description") or ""),

        )

    except ValueError as exc:

        raise HTTPException(status_code=422, detail=str(exc))



@app.post("/api/applications/confirm-submission/{job_id}")

def confirm_submission(job_id: int, payload: Dict[str, Any] = None):

    notes = (payload or {}).get("notes", "Candidate confirmed manual submission on official employer portal.")

    success = confirm_user_submission(job_id, notes=notes)

    if not success:

        raise HTTPException(status_code=400, detail="Could not confirm submission. Make sure package was generated.")

    return {"status": "SUCCESS", "message": "Application confirmed as SUBMITTED.", "job_id": job_id}



@app.get("/api/applications/{app_id}/history")

def get_application_history_endpoint(app_id: int):

    app = get_application_by_id(app_id)

    if not app:

        raise HTTPException(status_code=404, detail="Application not found.")

    history = get_application_history(app_id)

    for h in history:

        if isinstance(h, dict):

            h["to_stage"] = h.get("new_status")

            h["from_stage"] = h.get("previous_status")

            h["changed_by"] = h.get("actor")

    return {"application_id": app_id, "count": len(history), "history": history}



@app.put("/api/applications/{app_id}/status")

def update_application_status_endpoint(app_id: int, payload: Dict[str, Any]):

    new_status = (payload or {}).get("status") or (payload or {}).get("stage")

    if not new_status:

        raise HTTPException(status_code=400, detail="Status or stage is required.")

    notes = (payload or {}).get("notes", "")

    actor = (payload or {}).get("actor", "CANDIDATE")

    evidence = (payload or {}).get("evidence", "")



    # Human submission barrier: Cannot mark submitted / applied without explicit confirmation

    try:

        canonical_stage = canonicalize_application_stage(new_status)
        ApplicationStatus(canonical_stage)

    except (ValueError, KeyError):

        raise HTTPException(status_code=400, detail=f"Invalid application status: '{new_status}'.")



    if canonical_stage == ApplicationStatus.APPLIED.value:

        confirmed = (payload or {}).get("confirmed_by_user", False)

        if not confirmed:

            raise HTTPException(

                status_code=400,

                detail="Explicit human confirmation is required to transition an application to APPLIED/SUBMITTED stage."

            )

    try:

        updated = update_application_stage(

            application_id=app_id,

            new_status=canonical_stage,

            notes=notes,

            actor=actor,

            event_source="USER_MANUAL",

            evidence=evidence

        )

        return {"status": "SUCCESS", "message": f"Application stage updated to {canonical_stage}.", "application": updated}

    except ValueError as e:

        raise HTTPException(status_code=404, detail=str(e))

    except Exception as e:

        raise HTTPException(status_code=400, detail=str(e))




@app.post('/api/applications')
def add_application_endpoint(payload: Dict[str, Any]):
    """Add a new application manually or track an opportunity directly."""
    job_data = payload.get('job') or payload
    app_data = payload.get('application') or payload
    try:
        app_id = create_manual_application(job_data=job_data, app_data=app_data)
        app_item = get_application_with_details(app_id)
        return {'status': 'SUCCESS', 'application_id': app_id, 'application': app_item}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.get('/api/applications/{app_id}')
def get_single_application_endpoint(app_id: int):
    """Retrieve full application details, recruiter contacts, and history timeline."""
    app_item = get_application_with_details(app_id)
    if not app_item:
        raise HTTPException(status_code=404, detail='Application not found.')
    return app_item

@app.put('/api/applications/{app_id}')
def edit_application_endpoint(app_id: int, payload: Dict[str, Any]):
    """Edit application metadata including recruiter contacts, notes, and deadlines."""
    new_status = payload.get('status') or payload.get('application_status') or payload.get('stage')
    if new_status:
        try:
            canonical_stage = canonicalize_application_stage(new_status)
            ApplicationStatus(canonical_stage)
            if canonical_stage == ApplicationStatus.APPLIED.value:
                if not payload.get('confirmed_by_user', False):
                    raise HTTPException(
                        status_code=400,
                        detail='Explicit human confirmation is required to transition an application to APPLIED/SUBMITTED stage.'
                    )
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=400, detail=f'Invalid application status: "{new_status}".')

    updated = update_application_details(app_id, payload)
    if not updated:
        raise HTTPException(status_code=404, detail='Application not found.')
    return {'status': 'SUCCESS', 'application': updated}

@app.delete('/api/applications/{app_id}')
def delete_application_endpoint(app_id: int, confirm: bool = Query(False)):
    """Delete an application with candidate confirmation safety check."""
    if not confirm:
        raise HTTPException(status_code=400, detail='Application deletion requires explicit candidate confirmation (?confirm=true).')
    success = delete_application(app_id)
    if not success:
        raise HTTPException(status_code=404, detail='Application not found.')
    return {'status': 'SUCCESS', 'message': f'Application {app_id} deleted.'}

@app.get('/api/applications/{app_id}/history/export')
def export_single_application_history_endpoint(app_id: int):
    """Export audit timeline for a specific application to CSV."""
    app_item = get_application_by_id(app_id)
    if not app_item:
        raise HTTPException(status_code=404, detail='Application not found.')
    file_path = export_application_history_to_csv(application_id=app_id)
    return FileResponse(path=file_path, media_type='text/csv', filename=Path(file_path).name)

@app.get('/api/export/applications/history')
def export_all_applications_history_endpoint():
    """Export complete application audit timeline across all applications to CSV."""
    file_path = export_application_history_to_csv(application_id=None)
    return FileResponse(path=file_path, media_type='text/csv', filename=Path(file_path).name)

@app.get("/api/resumes")

def get_resumes():

    resumes = list_resumes()

    for resume in resumes:

        resume["candidate_evidence_state"] = "NEEDS_CANDIDATE_REVIEW"

        resume["keyword_coverage_pct"] = None

        resume["supported_keywords"] = []

        resume["tailoring_summary"] = "Legacy generated artifact; not validated against an original candidate source resume."

        resume["evidence_note"] = "Content and candidate facts require source review before reuse."

        if resume.get("record_state") == "QUARANTINED":

            resume["record_review_note"] = "Associated job record is quarantined; this resume artifact is retained for audit only."

    return {"count": len(resumes), "resumes": resumes}



@app.get("/api/resumes/download/{filename}")

def download_resume(filename: str):

    if Path(filename).name != filename or filename in (".", "..") or Path(filename).suffix.lower() not in (".pdf", ".docx"):

        raise HTTPException(status_code=400, detail="Invalid resume filename")

    file_path = current_resumes_dir() / filename

    if not file_path.is_file() or file_path.resolve().parent != current_resumes_dir().resolve():

        raise HTTPException(status_code=404, detail="File not found")

    

    media_type = "application/pdf" if filename.endswith(".pdf") else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    return FileResponse(path=str(file_path), media_type=media_type, filename=filename)


@app.post("/api/resumes/upload")
async def upload_resume_endpoint(
    file: UploadFile = File(...),
    job_id: Optional[int] = Form(None),
    company_name: Optional[str] = Form(None),
    role_title: Optional[str] = Form(None),
):
    """Securely upload a candidate resume file (.pdf, .docx, .txt) and record metadata."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename cannot be empty.")

    orig_name = Path(file.filename).name
    ext = Path(orig_name).suffix.lower()
    if ext not in (".pdf", ".docx", ".txt"):
        raise HTTPException(status_code=400, detail="Only .pdf, .docx, and .txt files are supported.")

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File size exceeds maximum allowed limit of 10MB.")

    import time
    clean_stem = re.sub(r"[^a-zA-Z0-9_\-]", "_", Path(orig_name).stem)[:40]
    safe_filename = f"{clean_stem}_{int(time.time())}{ext}"
    resumes_dir = current_resumes_dir()
    resumes_dir.mkdir(parents=True, exist_ok=True)
    target_path = resumes_dir / safe_filename
    with open(target_path, "wb") as f:
        f.write(content)

    from datetime import datetime, timezone
    from careerorbit.models.schemas import ResumeMetadata
    from careerorbit.database.db import save_resume_metadata, get_job_by_id, save_job
    from careerorbit.models.schemas import Job

    resolved_job_id = job_id
    resolved_company = (company_name or "").strip() or "Candidate Profile"
    resolved_role = (role_title or "").strip() or "Uploaded Resume"

    if resolved_job_id:
        existing_job = get_job_by_id(resolved_job_id)
        if existing_job:
            resolved_company = existing_job.get("employer", resolved_company)
            resolved_role = existing_job.get("title", resolved_role)
    else:
        from careerorbit.database.db import get_connection
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT id FROM jobs WHERE job_uid = 'candidate_master_resume_source' LIMIT 1")
        row = c.fetchone()
        conn.close()
        if row:
            resolved_job_id = row[0]
        else:
            resolved_job_id = save_job(Job(
                job_uid="candidate_master_resume_source",
                employer="Candidate Source",
                title="Master Resume / Base Profile",
                normalized_title="master resume",
                priority_category=1,
                priority_label="Master Profile",
                location="India / Remote",
                official_url="",
                official_listing_url="",
                application_url="",
                canonical_url="",
                discovery_source="Direct Upload",
                verification_status=VerificationStatus.VERIFIED_OPEN,
            ))

    is_pdf = ext == ".pdf"
    pdf_fn = safe_filename if is_pdf else ""
    docx_fn = safe_filename if not is_pdf else ""
    pdf_p = str(target_path) if is_pdf else ""
    docx_p = str(target_path) if not is_pdf else ""

    meta = ResumeMetadata(
        job_id=resolved_job_id,
        company_name=resolved_company,
        role_title=resolved_role,
        source_resume_type="Candidate Upload",
        pdf_filename=pdf_fn,
        pdf_path=pdf_p,
        docx_filename=docx_fn,
        docx_path=docx_p,
        tailoring_summary=f"Candidate-uploaded source document: {orig_name}",
        supported_keywords=[],
        missing_requirements=[],
        keyword_coverage_pct=0.0,
        details_needing_confirmation=[],
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    resume_id = save_resume_metadata(meta)

    return {
        "status": "SUCCESS",
        "message": f"Resume '{orig_name}' successfully uploaded.",
        "resume_id": resume_id,
        "filename": safe_filename,
    }


@app.delete("/api/resumes/{resume_id}")
def delete_resume_endpoint(resume_id: int):
    """Delete a resume artifact and its associated metadata."""
    success = delete_resume(resume_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Resume {resume_id} not found.")
    return {"status": "SUCCESS", "message": f"Resume {resume_id} deleted."}



@app.get("/api/prep/plans")

@app.get("/api/interview-prep")

def get_prep_plans():

    plans = list_preparation_plans()

    for plan in plans:

        plan["candidate_evidence_state"] = "NEEDS_CANDIDATE_REVIEW"

    return {"count": len(plans), "plans": plans}



@app.get("/api/prep/daily-plan")

@app.get("/api/study-plan")

def get_daily_study_plan():

    planner = DailyStudyPlanner()

    return planner.generate_daily_plan()





@app.get("/api/study/plan/today")

def get_today_study_plan(target_role: Optional[str] = None, budget_minutes: Optional[int] = None):

    planner = DailyStudyPlanner()

    now_local = planner.get_current_local_time()

    today_str = now_local.strftime("%Y-%m-%d")



    plan = get_daily_study_plan_by_date(today_str, target_role=target_role)

    if not plan:

        plan = planner.generate_daily_plan(

            target_role=target_role,

            daily_budget_minutes=budget_minutes or 120,

            save_to_db=True

        )

    return plan





@app.post("/api/study/plan/generate")

def generate_study_plan_endpoint(payload: Optional[DailyStudyPlanCreate] = None):

    planner = DailyStudyPlanner()

    role = payload.target_role if payload else None

    budget = payload.daily_budget_minutes if payload else 120

    priority = payload.target_priority if payload else 1



    plan = planner.generate_daily_plan(

        target_role=role,

        daily_budget_minutes=budget,

        target_priority=priority,

        save_to_db=True

    )

    if payload and payload.notes:

        plan = update_daily_study_plan(plan["id"], {"notes": payload.notes}) or plan

    return plan





@app.get("/api/study/plan/{plan_id}")

def get_study_plan_by_id(plan_id: int):

    plan = get_daily_study_plan(plan_id)

    if not plan:

        raise HTTPException(status_code=404, detail=f"Study plan {plan_id} not found")

    return plan





@app.put("/api/study/plan/{plan_id}")

def update_study_plan_endpoint(plan_id: int, payload: Dict[str, Any]):

    updated = update_daily_study_plan(plan_id, payload)

    if not updated:

        raise HTTPException(status_code=404, detail=f"Study plan {plan_id} not found")

    return updated





@app.put("/api/study/plan/{plan_id}/tasks/{task_id}/status")

def update_study_task_status_endpoint(plan_id: int, task_id: str, payload: TaskStatusUpdate):

    valid_statuses = ("NOT_STARTED", "IN_PROGRESS", "COMPLETED")

    new_status = payload.status.strip().upper()

    if new_status not in valid_statuses:

        raise HTTPException(

            status_code=400,

            detail=f"Invalid task status '{payload.status}'. Must be one of {valid_statuses}"

        )



    updated_plan = update_study_task_status(plan_id, task_id, new_status, payload.notes)

    if not updated_plan:

        raise HTTPException(

            status_code=404,

            detail=f"Study plan {plan_id} or task '{task_id}' not found"

        )

    return updated_plan





@app.get("/api/study/skill-gaps")

def get_study_skill_gaps(target_priority: int = 1, target_role: Optional[str] = None):

    planner = DailyStudyPlanner()

    return planner.extract_skill_gaps(target_priority=target_priority, target_role=target_role)





@app.get("/api/study/analytics/progress")

def get_study_analytics_endpoint():

    return get_study_analytics()





# ----------------- Assessment Sandbox Endpoints -----------------



@app.get("/api/assessments/challenges")

def list_assessment_challenges_endpoint(

    category: Optional[str] = None,

    difficulty: Optional[str] = None,

    question_type: Optional[str] = None

):

    challenges = list_assessment_challenges(

        category=category,

        difficulty=difficulty,

        question_type=question_type,

        include_solution=False

    )

    return {"count": len(challenges), "challenges": challenges}





@app.get("/api/assessments/challenges/{challenge_id}")

def get_assessment_challenge_endpoint(challenge_id: int):

    challenge = get_assessment_challenge(challenge_id, include_solution=False)

    if not challenge:

        raise HTTPException(status_code=404, detail=f"Challenge {challenge_id} not found")

    return challenge





@app.post("/api/assessments/challenges/{challenge_id}/evaluate")

def evaluate_assessment_submission_endpoint(challenge_id: int, payload: AssessmentSubmissionCreate):

    try:

        result = evaluate_submission(challenge_id, payload.submitted_code)

        return result

    except ValueError as e:

        raise HTTPException(status_code=404, detail=str(e))

    except Exception as e:

        raise HTTPException(status_code=500, detail=f"Sandbox evaluation error: {str(e)}")





@app.get("/api/assessments/submissions")

def list_assessment_submissions_endpoint(challenge_id: Optional[int] = None, limit: int = 50):

    subs = list_assessment_submissions(challenge_id=challenge_id, limit=limit)

    return {"count": len(subs), "submissions": subs}





@app.get("/api/assessments/stats")

def get_assessment_stats_endpoint():

    return get_assessment_stats()





@app.post("/api/assessments/seed")

def seed_assessments_endpoint():

    count = seed_assessment_challenges()

    return {"status": "success", "seeded_count": count}





# ----------------- Interview Coach Endpoints -----------------



@app.get("/api/interview-prep/briefing/{job_id}")

def get_interview_prep_briefing_endpoint(job_id: int):

    job = get_job_by_id(job_id)

    if not job:

        raise HTTPException(status_code=404, detail=f"Job with ID {job_id} not found.")

    coach = InterviewCoach()

    try:

        briefing = coach.get_or_create_briefing(job_id)

        return briefing

    except Exception as e:

        raise HTTPException(status_code=500, detail=f"Failed to load interview briefing: {str(e)}")





@app.put("/api/interview-prep/briefing/{job_id}/notes")

def update_interview_prep_notes_endpoint(job_id: int, payload: InterviewPrepNotesUpdate):

    coach = InterviewCoach()

    try:

        updated = coach.update_notes(job_id, notes=payload.notes, confidence_rating=payload.confidence_rating)

        return updated

    except ValueError as e:

        raise HTTPException(status_code=404, detail=str(e))

    except Exception as e:

        raise HTTPException(status_code=500, detail=f"Failed to update prep notes: {str(e)}")





@app.put("/api/interview-prep/briefing/{job_id}/checklist")

def update_interview_prep_checklist_endpoint(job_id: int, payload: InterviewChecklistUpdate):

    coach = InterviewCoach()

    try:

        updated = coach.update_checklist(job_id, payload.checklist)

        return updated

    except ValueError as e:

        raise HTTPException(status_code=404, detail=str(e))

    except Exception as e:

        raise HTTPException(status_code=500, detail=f"Failed to update checklist: {str(e)}")





@app.post("/api/interview-prep/briefing/{job_id}/draft")

def save_interview_answer_draft_endpoint(job_id: int, payload: InterviewAnswerDraftCreate):

    coach = InterviewCoach()

    try:

        updated = coach.save_answer_draft(job_id, payload.question_index, payload.draft_text)

        return updated

    except ValueError as e:

        raise HTTPException(status_code=404, detail=str(e))

    except Exception as e:

        raise HTTPException(status_code=500, detail=f"Failed to save answer draft: {str(e)}")





@app.get("/api/interview-prep/sessions")

def list_interview_prep_sessions_endpoint(limit: int = 50):

    coach = InterviewCoach()

    sessions = coach.list_sessions(limit=limit)

    return {"count": len(sessions), "sessions": sessions}





@app.post("/api/interview-prep/role-workspaces")

def create_role_interview_workspace(payload: Dict[str, Any]):

    role_title = payload.get("role_title")

    job_description = payload.get("job_description", "")

    if not isinstance(role_title, str) or not isinstance(job_description, str):

        raise HTTPException(status_code=422, detail="Role title and job description must be text.")

    try:

        return InterviewCoach.create_role_workspace(role_title, job_description)

    except ValueError as exc:

        raise HTTPException(status_code=422, detail=str(exc))





@app.get("/api/interview-prep/role-workspaces")

def list_role_interview_workspaces(limit: int = 50):

    workspaces = list_interview_prep_workspaces(limit)

    return {"count": len(workspaces), "workspaces": workspaces}





@app.get("/api/interview-prep/role-workspaces/{workspace_id}")

def get_role_interview_workspace(workspace_id: str):

    workspace = get_interview_prep_workspace(workspace_id)

    if workspace is None:

        raise HTTPException(status_code=404, detail="Interview workspace not found.")

    return workspace





@app.put("/api/interview-prep/role-workspaces/{workspace_id}")

def update_role_interview_workspace(workspace_id: str, payload: Dict[str, Any]):

    if not isinstance(payload, dict):

        raise HTTPException(status_code=422, detail="Request body must be an object.")

    if "candidate_notes" in payload and (not isinstance(payload["candidate_notes"], str) or len(payload["candidate_notes"]) > 20000):

        raise HTTPException(status_code=422, detail="Notes must be text of 20,000 characters or fewer.")

    if "checklist" in payload and (not isinstance(payload["checklist"], list) or len(payload["checklist"]) > 50):

        raise HTTPException(status_code=422, detail="Checklist must be a list of no more than 50 items.")

    if "answer_drafts" in payload and (not isinstance(payload["answer_drafts"], dict) or len(payload["answer_drafts"]) > 50):

        raise HTTPException(status_code=422, detail="Answer drafts must be an object with no more than 50 entries.")

    try:

        workspace = update_interview_prep_workspace(workspace_id, payload)

    except (ValueError, TypeError) as exc:

        raise HTTPException(status_code=422, detail=str(exc))

    if workspace is None:

        raise HTTPException(status_code=404, detail="Interview workspace not found.")

    return workspace









@app.post("/api/verify-url")

def verify_external_url(payload: Dict[str, Any]):

    url = str((payload or {}).get("url") or "").strip()

    employer = str((payload or {}).get("employer") or "").strip()

    job_id = (payload or {}).get("job_id")

    if not url:

        raise HTTPException(status_code=400, detail="URL is required")

    v_engine = VerificationEngine()

    status, notes = v_engine.verify_listing(url, employer=employer)

    if job_id is not None:

        try:

            job_id_int = int(job_id)

        except (ValueError, TypeError):

            raise HTTPException(status_code=400, detail="job_id must be a valid integer")

        try:

            with get_connection() as conn:

                c = conn.cursor()

                now_iso = datetime.now(timezone.utc).isoformat()

                c.execute("""

                    UPDATE jobs

                    SET verification_status = ?,

                        verification_notes = ?,

                        last_verified_at = ?

                    WHERE id = ?

                """, (status.value, notes, now_iso, job_id_int))

                conn.commit()

        except Exception as e:

            logger.debug("Could not update job #%s status: %s", job_id, e)

    return {"url": url, "status": status.value, "notes": notes, "job_id": job_id}



# ----------------- Community Alert Import Endpoints -----------------



@app.post("/api/community/parse-preview")

def preview_community_announcement(payload: Dict[str, Any]):

    raw_text = str((payload or {}).get("raw_text") or (payload or {}).get("text") or "").strip()

    channel = str((payload or {}).get("source_channel") or "WhatsApp / Telegram Community").strip()

    if not raw_text:

        raise HTTPException(status_code=400, detail="Announcement text is required.")

    parsed = CommunityJobParser.parse_announcement(raw_text, source_channel=channel)

    return parsed



@app.post("/api/community/import")

def import_community_announcement(payload: Dict[str, Any]):

    raw_text = str((payload or {}).get("raw_text") or (payload or {}).get("text") or "").strip()

    channel = str((payload or {}).get("source_channel") or "Community Channel").strip()

    allow_duplicate = bool((payload or {}).get("allow_duplicate", False))



    if not raw_text:

        raise HTTPException(status_code=400, detail="Announcement text is required.")



    parsed = CommunityJobParser.parse_announcement(raw_text, source_channel=channel)

    title = str((payload or {}).get("title") or parsed["title"]).strip()

    employer = str((payload or {}).get("employer") or parsed["employer"]).strip()

    location = str((payload or {}).get("location") or parsed["location"]).strip()

    app_url = str((payload or {}).get("application_url") or parsed["application_url"]).strip()

    priority_category = (payload or {}).get("priority_category") or parsed["priority_category"]



    if parsed["is_duplicate"] and not allow_duplicate:

        dup_title = (parsed["duplicate_ref"] or {}).get("title", title)

        dup_emp = (parsed["duplicate_ref"] or {}).get("employer", employer)

        raise HTTPException(

            status_code=409,

            detail=f"Potential duplicate job detected: '{dup_emp} — {dup_title}'. Pass allow_duplicate=true to import anyway."

        )



    # Score lead

    scorer = JobScorer()

    score_res = scorer.score_job({

        "title": title,

        "description": raw_text,

        "location": location,

        "work_arrangement": "Hybrid",

        "salary": "Not Disclosed",

        "posting_date": None,

        "posting_date_confidence": "UNKNOWN",

        "verification_status": "UNVERIFIED"

    })



    job_uid = parsed["job_uid"]

    if get_job_by_uid(job_uid):

        import time

        job_uid = f"{job_uid}_{int(time.time())}"



    job_obj = Job(

        job_uid=job_uid,

        employer=employer,

        title=title,

        normalized_title=title.lower(),

        job_id_or_req="",

        priority_category=priority_category,

        priority_label=parsed["priority_label"],

        location=location,

        work_arrangement="Hybrid",

        employment_type="Full-time",

        salary="Not Disclosed",

        deadline=parsed.get("deadline"),

        official_url=app_url,

        official_listing_url=app_url,

        application_url=app_url,

        discovery_url=app_url,

        canonical_url=app_url,

        discovery_source=f"Community: {channel}",

        verification_source=f"Community announcement ({channel})",

        verification_status=VerificationStatus.UNVERIFIED,

        verification_notes="Imported from community announcement. Application link and vacancy status require verification.",

        match_score=score_res["match_score"],

        match_tier=score_res["match_tier"],

        score_breakdown=score_res["score_breakdown"],

        required_skills=score_res["supported_skills"] + score_res["missing_skills"],

        supported_skills=score_res["supported_skills"],

        missing_skills=score_res["missing_skills"],

        learnable_skills=score_res["learnable_skills"],

        disqualifiers=score_res["disqualifiers"],

        evidence_notes="Candidate facts require review for tailored materials.",

        description=raw_text,

        is_fresher=parsed["is_fresher"],

        is_off_campus=parsed["is_off_campus"],

        is_internship=parsed["is_internship"],

        is_walkin=parsed["is_walkin"],

    )

    job_id = save_job(job_obj)

    saved_lead = get_job_by_id(job_id)

    return {

        "status": "SUCCESS",

        "job_id": job_id,

        "job_uid": job_uid,

        "lead": saved_lead,

        "missing_link": parsed["missing_link"],

    }



@app.get("/api/export/jobs")

def export_jobs():

    file_path = export_jobs_to_csv()

    return FileResponse(path=file_path, media_type="text/csv", filename=Path(file_path).name)



@app.get("/api/export/applications")

def export_applications():

    file_path = export_applications_to_csv()

    return FileResponse(path=file_path, media_type="text/csv", filename=Path(file_path).name)



@app.get("/api/scheduler/status")

def get_scheduler_status():

    return SCHEDULER.get_status()



@app.get("/api/workflows/history")

def get_workflow_history(limit: int = 100):

    return {"runs": recent_runs(limit)}



@app.post("/api/scheduler/trigger-discovery")

def trigger_scheduled_discovery():

    return SCHEDULER.trigger_discovery_now()



@app.post("/api/scheduler/trigger-study-plan")

def trigger_scheduled_study_plan():

    return SCHEDULER.trigger_study_plan_now()



@app.get("/api/sources/health")

def get_sources_health():

    sources = list_job_sources()

    healthy_count = sum(1 for s in sources if s.get("health_status") == "HEALTHY")

    degraded_count = sum(1 for s in sources if s.get("health_status") == "DEGRADED")

    failing_count = sum(1 for s in sources if s.get("health_status") == "FAILING")

    unknown_count = sum(1 for s in sources if s.get("health_status") == "UNKNOWN")

    return {

        "total_sources": len(sources),

        "healthy_count": healthy_count,

        "degraded_count": degraded_count,

        "failing_count": failing_count,

        "unknown_count": unknown_count,

        "sources": sources,

        "latest_discovery_summary": SCHEDULER.last_discovery_result or "No discovery run executed yet in this session."

    }



# ----------------- Job Sources Registry Endpoints -----------------



@app.get("/api/job-sources")

def get_all_job_sources(

    category: Optional[str] = Query(None),

    source_type: Optional[str] = Query(None),

    is_enabled: Optional[bool] = Query(None),

    health_status: Optional[str] = Query(None)

):

    cat = _u(category, None)

    st = _u(source_type, None)

    en = _u(is_enabled, None)

    hs = _u(health_status, None)

    sources = list_job_sources(category=cat, source_type=st, is_enabled=en, health_status=hs)

    return {"count": len(sources), "sources": sources}



@app.get("/api/job-sources/{source_id}")

def get_single_job_source_endpoint(source_id: str):

    source = get_job_source(source_id)

    if not source:

        raise HTTPException(status_code=404, detail="Job source not found.")

    return source



@app.post("/api/job-sources")

def create_job_source_endpoint(payload: Dict[str, Any]):

    s_id = str((payload or {}).get("source_id") or "").strip()

    s_name = str((payload or {}).get("source_name") or "").strip()

    if not s_id or not s_name:

        raise HTTPException(status_code=400, detail="source_id and source_name are required.")

    inserted_id = save_job_source(payload)

    return {"status": "SUCCESS", "id": inserted_id, "source_id": s_id, "source": get_job_source(s_id)}



@app.put("/api/job-sources/{source_id}")

def edit_job_source_endpoint(source_id: str, payload: Dict[str, Any]):

    existing = get_job_source(source_id)

    if not existing:

        raise HTTPException(status_code=404, detail="Job source not found.")

    data = {**existing, **payload, "source_id": source_id}

    save_job_source(data)

    return {"status": "SUCCESS", "source_id": source_id, "source": get_job_source(source_id)}



@app.delete("/api/job-sources/{source_id}")

def remove_job_source_endpoint(source_id: str):

    deleted = delete_job_source(source_id)

    if not deleted:

        raise HTTPException(status_code=404, detail="Job source not found.")

    return {"status": "SUCCESS", "source_id": source_id}



@app.post("/api/job-sources/{source_id}/toggle")

def toggle_job_source_endpoint(source_id: str, payload: Optional[Dict[str, Any]] = None):

    enabled = (payload or {}).get("enabled")

    res = toggle_job_source_enabled(source_id, enabled=enabled)

    if res is None:

        raise HTTPException(status_code=404, detail="Job source not found.")

    return {"status": "SUCCESS", "source_id": source_id, "is_enabled": res}



# ----------------- Verification Worker Endpoints -----------------



@app.post("/api/verifier/start")

def start_verification_worker_endpoint(payload: Optional[Dict[str, Any]] = None):

    max_jobs = int((payload or {}).get("max_jobs", 25))

    rate_limit_delay = float((payload or {}).get("rate_limit_delay", 0.5))

    days_threshold = int((payload or {}).get("days_threshold", 7))

    return VerificationWorker.get_current_instance().start(max_jobs=max_jobs, rate_limit_delay=rate_limit_delay, days_threshold=days_threshold)



@app.get("/api/verifier/status")

def get_verification_worker_status_endpoint():

    return VerificationWorker.get_current_instance().get_status()



@app.post("/api/verifier/cancel")

def cancel_verification_worker_endpoint():

    cancelled = VerificationWorker.get_current_instance().cancel()

    return {

        "status": "cancelled" if cancelled else "not_running",

        "message": "Verification cancellation requested." if cancelled else "Worker was not running."

    }



@app.get("/api/scheduler/history")

def get_scheduler_history(limit: int = 20):

    import json

    log_file = current_logs_dir() / "workflow_runs.jsonl"

    runs = []

    if log_file.exists():

        try:

            lines = log_file.read_text(encoding="utf-8").splitlines()

            for line in reversed(lines[-limit:]):

                if line.strip():

                    try:

                        runs.append(json.loads(line))

                    except Exception:

                        pass

        except Exception:

            pass

    return {"count": len(runs), "runs": runs}



# ----------------- Employer ATS Registry Endpoints -----------------



@app.get("/api/sources/registry")

def get_employer_source_registry():

    return {"sources": list_employer_sources()}



@app.post("/api/sources/registry")

def create_employer_source(payload: Dict[str, Any]):

    name = str(((payload or {}).get("employer_name") or (payload or {}).get("name") or "")).strip()

    domain = str(((payload or {}).get("official_domain") or (payload or {}).get("domain") or "")).strip()

    provider = str(((payload or {}).get("ats_provider") or (payload or {}).get("type") or (payload or {}).get("provider") or "")).strip()

    board_id = str(((payload or {}).get("board_id") or (payload or {}).get("board_token") or (payload or {}).get("slug") or "")).strip()

    enabled = bool((payload or {}).get("enabled", True))

    notes = str(((payload or {}).get("notes") or (payload or {}).get("note") or "")).strip()

    if not name or not provider or not board_id:

        raise HTTPException(status_code=400, detail="Employer name, ATS provider, and Board ID are required.")

    try:

        new_source = add_employer_source(name, domain, provider, board_id, enabled=enabled, notes=notes)

        return {"status": "SUCCESS", "source": new_source, **new_source}

    except Exception as exc:

        raise HTTPException(status_code=400, detail=str(exc))



@app.put("/api/sources/registry/{source_id}")

def edit_employer_source(source_id: str, payload: Dict[str, Any]):

    try:

        updated = update_employer_source(source_id, payload)

        return updated

    except KeyError as exc:

        raise HTTPException(status_code=404, detail=str(exc))

    except Exception as exc:

        raise HTTPException(status_code=400, detail=str(exc))



@app.delete("/api/sources/registry/{source_id}")

def remove_employer_source(source_id: str):

    success = delete_employer_source(source_id)

    if not success:

        raise HTTPException(status_code=404, detail="Source not found.")

    return {"status": "SUCCESS", "message": f"Source {source_id} deleted."}



@app.post("/api/sources/registry/{source_id}/test")

def test_employer_source(source_id: str):

    source = get_employer_source(source_id)

    if not source:

        raise HTTPException(status_code=404, detail="Source not found.")

    provider = str(source.get("ats_provider") or "").lower()

    board_id = source.get("board_id", "")

    company = source.get("employer_name", "")

    try:

        if provider == "greenhouse":

            adapter = GreenhouseBoardSource(company=company, board_token=board_id)

        elif provider == "lever":

            adapter = LeverSiteSource(company=company, site_slug=board_id)

        elif provider in ("smartrecruiters", "smart_recruiters"):

            adapter = SmartRecruitersSource(company=company, company_id=board_id)

        elif provider == "ashby":

            adapter = AshbyJobBoardSource(company=company, board_token=board_id)
        elif provider == "workable":
            adapter = WorkableSource(company=company, account_slug=board_id)

        else:

            raise ValueError(f"Testing unsupported for provider: {provider}")

        jobs = adapter.fetch_jobs(days_back=7)

        record_source_check(source_id, success=True, jobs_found=len(jobs))

        return {

            "status": "SUCCESS",

            "source_id": source_id,

            "jobs_found": len(jobs),

            "sample_jobs": [{"title": j["title"], "location": j["location"], "url": j["official_url"]} for j in jobs[:3]]

        }

    except Exception as exc:

        record_source_check(source_id, success=False, error_message=str(exc))

        return {

            "status": "FAILED",

            "source_id": source_id,

            "error": str(exc),

            "jobs_found": 0

        }





# ----------------- Telegram Bot & Unified Inbox Endpoints -----------------



@app.get("/api/telegram/status")

def get_telegram_status():

    """Retrieve runtime state of Telegram bot connection and polling worker."""

    if not _is_primary_account_storage():

        return {

            "status": "ACCOUNT_SCOPED_UNAVAILABLE",

            "configured": False,

            "running": False,

            "message": "Live Telegram credentials are configured for the primary local workspace only.",

            "inbox_summary": get_inbox_stats(),

        }

    status_info = TELEGRAM_WORKER.get_status()

    inbox_metrics = get_inbox_stats()

    res = dict(status_info)

    res["poll_interval_seconds"] = SETTINGS.TELEGRAM_POLL_INTERVAL

    res["inbox_summary"] = inbox_metrics

    return res





@app.post("/api/telegram/poll-now")

def trigger_telegram_poll():

    """Trigger an immediate single polling cycle against the Telegram Bot API."""

    _require_primary_telegram_account()

    if not SETTINGS.is_telegram_configured:

        return {

            "status": "NOT_CONFIGURED",

            "message": "TELEGRAM_BOT_TOKEN is not set in environment or .env file.",

            "processed_count": 0

        }

    res = TELEGRAM_WORKER.poll_once()

    return res





@app.post("/api/telegram/webhook")

async def telegram_webhook(request: Request):

    """Receive live webhook events dispatched by Telegram Bot API."""

    _require_primary_telegram_account()

    # Validate secret token header if configured

    if SETTINGS.TELEGRAM_WEBHOOK_SECRET:

        secret_header = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")

        if secret_header != SETTINGS.TELEGRAM_WEBHOOK_SECRET:

            raise HTTPException(status_code=403, detail="Forbidden: Invalid webhook secret token.")



    try:

        payload = await request.json()

    except Exception:

        raise HTTPException(status_code=400, detail="Invalid JSON payload.")



    service = TelegramService()

    result = service.process_update(payload)

    return {"ok": True, "result": result}





@app.get("/api/inbox")

def get_inbox_items(

    classification: Optional[str] = None,

    category_group: Optional[str] = None,

    channel: Optional[str] = None,

    status: Optional[str] = None,

    is_job_lead: Optional[bool] = None,

    q: Optional[str] = None,

    limit: int = Query(50, ge=1, le=200),

    offset: int = Query(0, ge=0)

):

    """List inbox messages with filtering, text search, and pagination."""

    items = list_inbox_messages(

        classification=classification,

        category_group=category_group,

        channel=channel,

        status=status,

        is_job_lead=is_job_lead,

        query=q,

        limit=limit,

        offset=offset

    )

    return {"count": len(items), "items": items}





@app.get("/api/inbox/stats")

def get_inbox_statistics():

    """Retrieve aggregated metrics of the Unified Inbox."""

    return get_inbox_stats()





@app.get("/api/inbox/{item_id}")

def get_single_inbox_item(item_id: int):

    """Fetch an individual inbox message by ID."""

    item = get_inbox_message(item_id)

    if not item:

        raise HTTPException(status_code=404, detail="Inbox message not found.")

    return item





@app.put("/api/inbox/{item_id}/status")

def set_inbox_item_status(item_id: int, payload: Dict[str, Any]):

    """Update status ('NEW', 'PROCESSED', 'ARCHIVED', 'DISCARDED') of an inbox item."""

    new_status = str(((payload or {}).get("status") or "")).strip().upper()

    valid_statuses = ("NEW", "PROCESSED", "ARCHIVED", "DISCARDED")

    if new_status not in valid_statuses:

        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}")



    notes = str((payload or {}).get("notes") or "") if (payload or {}).get("notes") else None

    success = update_inbox_message_status(item_id, new_status, notes=notes)

    if not success:

        raise HTTPException(status_code=404, detail="Inbox item not found.")

    return {"status": "SUCCESS", "item_id": item_id, "new_status": new_status}





@app.delete("/api/inbox/{item_id}")

def remove_inbox_item(item_id: int):

    """Permanently delete an inbox item."""

    success = delete_inbox_message(item_id)

    if not success:

        raise HTTPException(status_code=404, detail="Inbox item not found.")

    return {"status": "SUCCESS", "message": f"Inbox item {item_id} deleted."}





@app.post("/api/inbox/{item_id}/promote-to-job")

def promote_inbox_item_to_job(item_id: int):

    """Promote an inbox item to an official UNVERIFIED Job lead."""

    item = get_inbox_message(item_id)

    if not item:

        raise HTTPException(status_code=404, detail="Inbox item not found.")



    raw_text = item.get("raw_text", "")

    if not raw_text.strip():

        raise HTTPException(status_code=400, detail="Cannot promote an empty message to a job.")



    parsed = CommunityJobParser.parse_announcement(

        raw_text,

        source_channel=f"Unified Inbox (Msg #{item_id})"

    )



    # Score lead

    scorer = JobScorer()

    score_res = scorer.score_job({

        "title": parsed["title"],

        "description": raw_text,

        "location": parsed["location"],

        "work_arrangement": "Hybrid",

        "salary": "Not Disclosed",

        "posting_date": None,

        "posting_date_confidence": "UNKNOWN",

        "verification_status": "UNVERIFIED"

    })



    job_uid = parsed["job_uid"]

    if get_job_by_uid(job_uid):

        import time

        job_uid = f"{job_uid}_{int(time.time())}"



    job_obj = Job(

        job_uid=job_uid,

        employer=parsed["employer"],

        title=parsed["title"],

        normalized_title=parsed["title"].lower(),

        job_id_or_req="",

        priority_category=parsed["priority_category"],

        priority_label=parsed["priority_label"],

        location=parsed["location"],

        work_arrangement="Hybrid",

        employment_type="Full-time",

        salary="Not Disclosed",

        deadline=parsed.get("deadline"),

        official_url=parsed.get("application_url", ""),

        official_listing_url=parsed.get("application_url", ""),

        application_url=parsed.get("application_url", ""),

        discovery_url=parsed.get("application_url", ""),

        canonical_url=parsed.get("application_url", ""),

        discovery_source=f"Unified Inbox ({item.get('channel', 'telegram')})",

        verification_source=f"Inbox message #{item_id}",

        verification_status=VerificationStatus.UNVERIFIED,

        verification_notes="Promoted from Unified Inbox. Application URL and active status require independent verification.",

        match_score=score_res["match_score"],

        match_tier=score_res["match_tier"],

        score_breakdown=score_res["score_breakdown"],

        required_skills=score_res["supported_skills"] + score_res["missing_skills"],

        supported_skills=score_res["supported_skills"],

        missing_skills=score_res["missing_skills"],

        learnable_skills=score_res["learnable_skills"],

        disqualifiers=score_res["disqualifiers"],

        evidence_notes="Promoted from community resource; candidate facts require review.",

        description=raw_text,

        is_fresher=parsed["is_fresher"],

        is_off_campus=parsed["is_off_campus"],

        is_internship=parsed["is_internship"],

        is_walkin=parsed["is_walkin"],

    )



    job_id = save_job(job_obj)

    # Link job to inbox message and mark PROCESSED

    update_inbox_message_status(item_id, "PROCESSED", notes=f"Promoted to Job #{job_id}")



    # Update job_id in inbox message

    from careerorbit.database.db import get_connection

    with get_connection() as conn:

        conn.cursor().execute("UPDATE inbox_messages SET job_id = ?, is_job_lead = 1 WHERE id = ?", (job_id, item_id))

        conn.commit()



    return {

        "status": "SUCCESS",

        "job_id": job_id,

        "job_uid": job_uid,

        "lead": get_job_by_id(job_id)

    }





# ----------------- Community Source Registry Endpoints -----------------



@app.get("/api/community/sources")

def get_community_sources_endpoint(source_type: Optional[str] = None):

    """List all registered Telegram and WhatsApp community sources."""

    sources = list_community_sources(source_type=source_type)

    return {"count": len(sources), "sources": sources}





@app.post("/api/community/sources")

def register_community_source_endpoint(payload: Dict[str, Any]):

    """Register or update a community channel or chat."""

    chat_id = str((payload or {}).get("chat_id", "")).strip()

    source_name = str((payload or {}).get("source_name", "")).strip()

    source_type = str((payload or {}).get("source_type", "telegram_channel")).strip()

    status = str((payload or {}).get("status", "ACTIVE")).strip()



    if not chat_id or not source_name:

        raise HTTPException(status_code=400, detail="chat_id and source_name are required.")



    source_id = record_community_source(

        chat_id=chat_id,

        source_name=source_name,

        source_type=source_type,

        status=status,

        increment_messages=False

    )

    return {"status": "SUCCESS", "source_id": source_id}





@app.put("/api/community/sources/{source_id}")

def update_community_source_endpoint(source_id: int, payload: Dict[str, Any]):

    """Update community source status or enable/disable flag."""

    status = (payload or {}).get("status")

    is_enabled = (payload or {}).get("is_enabled")

    notes = (payload or {}).get("notes")



    success = update_community_source(source_id, status=status, is_enabled=is_enabled, last_error=notes)

    if not success:

        raise HTTPException(status_code=404, detail="Community source not found.")

    return {"status": "SUCCESS", "source_id": source_id}





@app.post("/api/community/sources/check-access")

def check_community_chat_access(payload: Dict[str, Any]):

    """Verify live bot access and permissions in a Telegram channel or group."""

    _require_primary_telegram_account()

    chat_id = str((payload or {}).get("chat_id", "")).strip()

    if not chat_id:

        raise HTTPException(status_code=400, detail="chat_id is required.")

    client = TelegramClient()

    return client.check_chat_access(chat_id)





@app.post("/api/community/sources/register-telegram")

def register_telegram_channel_source(payload: Dict[str, Any]):

    """Verify and register a Telegram channel or group into community sources."""

    _require_primary_telegram_account()

    chat_id = str((payload or {}).get("chat_id", "")).strip()

    custom_name = str((payload or {}).get("source_name", "")).strip()

    if not chat_id:

        raise HTTPException(status_code=400, detail="chat_id is required.")



    client = TelegramClient()

    access = client.check_chat_access(chat_id)



    name = custom_name or f"Telegram: {access.get('chat_title') or chat_id}"

    st_type = "telegram_channel" if access.get("chat_type") == "channel" else "telegram_group"

    st = "ACTIVE" if (access.get("accessible") and access.get("can_receive_messages")) else "PERMISSION_REQUIRED"

    notes = access.get("diagnosis", "")

    if access.get("setup_instructions"):

        notes += f" | Action: {access['setup_instructions']}"



    resolved_chat_id = access.get("chat_id") or chat_id

    source_id = record_community_source(

        chat_id=resolved_chat_id,

        source_name=name,

        source_type=st_type,

        status=st,

        last_error=notes,

        chat_username=access.get("chat_username", ""),

        is_public=bool(access.get("is_public")),

        is_member=bool(access.get("is_member")),

        can_receive_messages=bool(access.get("can_receive_messages")),

        bot_role=access.get("role") or access.get("bot_role") or "unknown",

        setup_instructions=access.get("setup_instructions", ""),

        diagnosis=access.get("diagnosis", ""),

        increment_messages=False

    )



    return {

        "status": "SUCCESS",

        "source_id": source_id,

        "source": get_community_source_by_id(source_id),

        "access_check": access

    }





@app.post("/api/community/sources/{source_id}/recheck")

def recheck_community_source_access(source_id: int):

    """Re-verify access and permissions for a registered community source."""

    _require_primary_telegram_account()

    source = get_community_source_by_id(source_id)

    if not source:

        raise HTTPException(status_code=404, detail="Community source not found.")



    chat_id = source.get("chat_id")

    client = TelegramClient()

    access = client.check_chat_access(chat_id)



    st = "ACTIVE" if (access.get("accessible") and access.get("can_receive_messages")) else "PERMISSION_REQUIRED"

    notes = access.get("diagnosis", "")

    if access.get("setup_instructions"):

        notes += f" | Action: {access['setup_instructions']}"



    update_community_source(

        source_id,

        status=st,

        last_error=notes,

        can_receive_messages=bool(access.get("can_receive_messages")),

        is_member=bool(access.get("is_member")),

        bot_role=access.get("role") or access.get("bot_role") or "unknown",

        setup_instructions=access.get("setup_instructions", ""),

        diagnosis=access.get("diagnosis", "")

    )

    return {

        "status": "SUCCESS",

        "source_id": source_id,

        "updated_status": st,

        "access_check": access

    }





# ----------------- Telegram Desktop Export Endpoints -----------------



@app.post("/api/telegram/export/parse-preview")

async def preview_telegram_desktop_export(request: Request):

    """Preview Telegram Desktop JSON or HTML export without database commits."""

    content_type = request.headers.get("content-type", "")

    from careerorbit.telegram.export_parser import TelegramChatExportParser



    is_multipart = "multipart/form-data" in content_type

    _check_telegram_export_content_length(request, required=is_multipart)

    override_title = None

    if is_multipart:

        form = await request.form(max_files=1, max_fields=4, max_part_size=MAX_TELEGRAM_EXPORT_BYTES)

        file = form.get("file")

        if not file:

            raise HTTPException(status_code=400, detail="File upload is required.")

        file_bytes, filename = await _read_telegram_export_upload(file)

        override_title = form.get("title") or form.get("override_title")

    else:

        payload = await _read_telegram_export_json(request)

        raw_content = payload.get("content") or payload.get("data")

        filename = _validated_telegram_export_filename(payload.get("filename", "result.json"))

        override_title = payload.get("override_title") or payload.get("title")

        if not raw_content:

            raise HTTPException(status_code=400, detail="Export content is required.")

        file_bytes = raw_content



    try:

        fn_lower = filename.lower()

        if fn_lower.endswith(".html") or fn_lower.endswith(".htm") or (isinstance(file_bytes, (str, bytes)) and b"<html" in (file_bytes if isinstance(file_bytes, bytes) else file_bytes.encode())):

            parsed = TelegramChatExportParser.parse_html(file_bytes, filename=filename, override_title=override_title)

        else:

            parsed = TelegramChatExportParser.parse_json(file_bytes, filename=filename, override_title=override_title)

    except Exception as e:

        raise HTTPException(status_code=400, detail=f"Failed to parse Telegram export: {e}")



    return parsed





@app.post("/api/telegram/export/import")

async def import_telegram_desktop_export(request: Request):

    """Import Telegram Desktop JSON or HTML export into Unified Inbox & Jobs database."""

    content_type = request.headers.get("content-type", "")

    from careerorbit.telegram.export_parser import TelegramChatExportParser



    is_multipart = "multipart/form-data" in content_type

    _check_telegram_export_content_length(request, required=is_multipart)

    override_title = None

    if is_multipart:

        form = await request.form(max_files=1, max_fields=4, max_part_size=MAX_TELEGRAM_EXPORT_BYTES)

        file = form.get("file")

        if not file:

            raise HTTPException(status_code=400, detail="File upload is required.")

        file_bytes, filename = await _read_telegram_export_upload(file)

        override_title = form.get("title") or form.get("override_title")

        try:

            fn_lower = filename.lower()

            if fn_lower.endswith(".html") or fn_lower.endswith(".htm"):

                parsed = TelegramChatExportParser.parse_html(file_bytes, filename=filename, override_title=override_title)

            else:

                parsed = TelegramChatExportParser.parse_json(file_bytes, filename=filename, override_title=override_title)

        except Exception as e:

            raise HTTPException(status_code=400, detail=f"Failed to parse Telegram export: {e}")

    else:

        payload = await _read_telegram_export_json(request)

        if "items" in payload and "chat_name" in payload:

            parsed = payload

        else:

            raw_content = payload.get("content") or payload.get("data")

            filename = _validated_telegram_export_filename(payload.get("filename", "result.json"))

            override_title = payload.get("override_title") or payload.get("title")

            if not raw_content:

                raise HTTPException(status_code=400, detail="Export content is required.")

            try:

                parsed = TelegramChatExportParser.parse_json(raw_content, filename=filename, override_title=override_title)

            except Exception as e:

                raise HTTPException(status_code=400, detail=f"Failed to parse Telegram export: {e}")



    result = TelegramChatExportParser.import_items(parsed)

    return result





@app.get("/api/telegram/export/status")

def get_telegram_export_status():

    """Diagnostic status for Telegram Desktop chat export ingestion mode."""

    sources = [s for s in list_community_sources() if s.get("source_type") == "telegram_chat_export"]

    return {

        "mode": "MANUAL_TELEGRAM_EXPORT",

        "supported_formats": [".json (Telegram Desktop result.json)", ".html (messages.html)"],

        "compliance_notice": (

            "In strict compliance with Telegram Terms of Service and user privacy standards, "

            "automated session hijacking or unauthorized scraping is prohibited. Ingestion operates "

            "safely via user-provided Telegram Desktop chat export files (.json / .html) or official Bot API."

        ),

        "imported_sources_count": len(sources),

        "sources": sources

    }





@app.delete("/api/community/sources/{source_id}")

def delete_community_source_endpoint(source_id: int):

    """Delete a registered community source by ID."""

    success = delete_community_source(source_id)

    if not success:

        raise HTTPException(status_code=404, detail="Community source not found.")

    return {"status": "SUCCESS", "message": f"Community source {source_id} deleted."}





# ----------------- WhatsApp Chat Ingestion Endpoints -----------------



MAX_WHATSAPP_EXPORT_BYTES = 50 * 1024 * 1024

MAX_WHATSAPP_IMPORT_ITEMS = 10000





def _validate_whatsapp_text(value: Any, *, field: str) -> str:

    if not isinstance(value, str):

        raise HTTPException(status_code=422, detail=f"{field} must be text.")

    if len(value.encode("utf-8")) > MAX_WHATSAPP_EXPORT_BYTES:

        raise HTTPException(status_code=413, detail="WhatsApp export exceeds the 50 MiB limit.")

    return value





def _validate_whatsapp_chat_title(value: Any) -> str:

    if not isinstance(value, str) or not value.strip() or len(value) > 255:

        raise HTTPException(status_code=422, detail="Chat title must be text between 1 and 255 characters.")

    return value.strip()



@app.get("/api/whatsapp/status")

def get_whatsapp_status_endpoint():

    """Retrieve runtime state, compliance disclosures, and import history for WhatsApp ingestion."""

    sources = list_community_sources(source_type="whatsapp_chat_export")

    return {

        "mode": "MANUAL_CHAT_EXPORT",

        "official_meta_api_configured": False,

        "polling_active": False,

        "compliance_notice": (

            "In strict compliance with WhatsApp Terms of Service and user privacy standards, "

            "automated web scraping or session emulation is prohibited. "

            "Ingestion operates exclusively via user-provided chat export (.txt) files with cryptographic deduplication."

        ),

        "imported_sources_count": len(sources),

        "sources": sources

    }





@app.post("/api/whatsapp/parse-preview")

def whatsapp_parse_preview_endpoint(payload: Dict[str, Any]):

    """Parse exported WhatsApp chat text and return structured preview before committing."""

    raw_text = (payload or {}).get("text")

    if raw_text is None or raw_text == "":

        raw_text = (payload or {}).get("raw_text", "")

    raw_text = _validate_whatsapp_text(raw_text, field="WhatsApp chat text")

    chat_title_value = (payload or {}).get("chat_title", "WhatsApp Export")

    if chat_title_value is None or chat_title_value == "":

        chat_title_value = "WhatsApp Export"

    chat_title = _validate_whatsapp_chat_title(chat_title_value)



    if not raw_text.strip():

        raise HTTPException(status_code=400, detail="WhatsApp chat text is required.")



    preview = WhatsAppChatExportParser.parse_text(raw_text, chat_title=chat_title)

    return preview





@app.post("/api/whatsapp/import")

def whatsapp_import_endpoint(payload: Dict[str, Any]):

    """Import previewed WhatsApp items into Unified Inbox and Jobs tables."""

    items = (payload or {}).get("items") or []

    chat_title_value = (payload or {}).get("chat_title", "WhatsApp Export")

    if chat_title_value is None or chat_title_value == "":

        chat_title_value = "WhatsApp Export"

    chat_title = _validate_whatsapp_chat_title(chat_title_value)

    filename = (payload or {}).get("filename") or (payload or {}).get("export_filename") or ""



    if not isinstance(filename, str) or len(filename) > 255:

        raise HTTPException(status_code=422, detail="Export filename must be text of 255 characters or fewer.")



    if not items:

        raise HTTPException(status_code=400, detail="No items provided for import.")

    if not isinstance(items, list) or len(items) > MAX_WHATSAPP_IMPORT_ITEMS:

        raise HTTPException(status_code=422, detail="Items must be a list of no more than 10,000 messages.")



    total_bytes = 0

    for index, item in enumerate(items):

        if not isinstance(item, dict):

            raise HTTPException(status_code=422, detail=f"Imported item {index + 1} must be an object.")

        raw_text = item.get("raw_text", "")

        if not isinstance(raw_text, str):

            raise HTTPException(status_code=422, detail=f"Imported item {index + 1} raw_text must be text.")

        total_bytes += len(raw_text.encode("utf-8"))

        if total_bytes > MAX_WHATSAPP_EXPORT_BYTES:

            raise HTTPException(status_code=413, detail="WhatsApp import exceeds the 50 MiB limit.")

        if "is_job_lead" in item and not isinstance(item["is_job_lead"], bool):

            raise HTTPException(status_code=422, detail=f"Imported item {index + 1} has an invalid job-lead flag.")

        if "job_parsed" in item and item["job_parsed"] is not None and not isinstance(item["job_parsed"], dict):

            raise HTTPException(status_code=422, detail=f"Imported item {index + 1} parsed job data must be an object.")

        for field in ("message_uid", "classification", "category_group"):

            if field in item and item[field] is not None and not isinstance(item[field], str):

                raise HTTPException(status_code=422, detail=f"Imported item {index + 1} {field} must be text.")



    result = WhatsAppChatExportParser.import_items(items, chat_title=chat_title, filename=filename)

    return result







# ----------------- Career Study Materials & Resources Library -----------------



@app.get("/api/resources")

def get_learning_resources_endpoint(

    category: Optional[str] = None,

    skill_tag: Optional[str] = None,

    difficulty_level: Optional[str] = None,

    resource_type: Optional[str] = None,

    is_completed: Optional[bool] = None,

    q: Optional[str] = None,

    limit: int = Query(50, ge=1, le=200),

    offset: int = Query(0, ge=0)

):

    """List saved learning resources and career preparation materials with filtering."""

    items = list_learning_resources(

        category=category,

        skill_tag=skill_tag,

        difficulty_level=difficulty_level,

        resource_type=resource_type,

        is_completed=is_completed,

        query=q,

        limit=limit,

        offset=offset

    )

    stats = get_learning_resources_stats()

    return {"count": len(items), "items": items, "resources": items, "stats": stats}





@app.get("/api/resources/pathways")

def get_learning_pathways_endpoint():

    """Retrieve structured role-aligned learning pathways with progress tracking."""

    resources = list_learning_resources(limit=500)

    pathways = get_learning_pathways(resources)

    return {"status": "SUCCESS", "count": len(pathways), "pathways": pathways}





@app.post("/api/resources/seed")

def seed_learning_resources_endpoint():

    """Seed or update curated learning resources catalog idempotently."""

    result = seed_curated_learning_resources()

    stats = get_learning_resources_stats()

    return {"status": "SUCCESS", "seed_result": result, "stats": stats}





@app.get("/api/resources/{resource_id}")

def get_single_learning_resource_endpoint(resource_id: int):

    """Retrieve details for a single study resource."""

    item = get_learning_resource(resource_id)

    if not item:

        raise HTTPException(status_code=404, detail="Resource not found.")

    return item





@app.post("/api/resources/{resource_id}/toggle-complete")

def toggle_resource_completion_endpoint(resource_id: int, payload: Optional[Dict[str, Any]] = None):

    """Toggle completion status of a learning resource."""

    explicit_val = None

    if payload and "completed" in payload:

        explicit_val = bool(payload["completed"])

    updated = toggle_learning_resource_completion(resource_id, completed=explicit_val)

    if not updated:

        raise HTTPException(status_code=404, detail="Resource not found.")

    return {"status": "SUCCESS", "resource": updated}





@app.post("/api/resources")

def save_learning_resource_endpoint(payload: Dict[str, Any]):

    """Save a learning resource directly into the study collection."""

    title = str((payload or {}).get("title") or "").strip()

    primary_url = str((payload or {}).get("primary_url") or "").strip()

    if not title:

        raise HTTPException(status_code=400, detail="Resource title is required.")



    res_id = save_learning_resource(payload)

    saved_item = get_learning_resource(res_id)

    return {"status": "SUCCESS", "resource_id": res_id, "resource": saved_item}





@app.delete("/api/resources/{resource_id}")

def delete_learning_resource_endpoint(resource_id: int):

    """Delete a saved learning resource by ID."""

    success = delete_learning_resource(resource_id)

    if not success:

        raise HTTPException(status_code=404, detail="Resource not found.")

    return {"status": "SUCCESS", "message": f"Resource {resource_id} deleted."}





@app.post("/api/inbox/{item_id}/save-resource")

def save_inbox_item_as_learning_resource(item_id: int):

    """Promote an inbox message into the saved Career Study Resources library."""

    item = get_inbox_message(item_id)

    if not item:

        raise HTTPException(status_code=404, detail="Inbox item not found.")



    raw_text = item.get("raw_text", "")

    extracted = item.get("extracted_data") or {}

    urls = extracted.get("urls") or []

    primary_url = urls[0] if urls else f"#inbox-item-{item_id}"



    first_line = raw_text.splitlines()[0][:80] if raw_text else "Saved Resource"



    res_id = save_learning_resource({

        "title": first_line,

        "category": item.get("classification", "Technical Learning Materials"),

        "sub_category": item.get("category_group", "learning"),

        "canonical_url": primary_url,

        "primary_url": primary_url,

        "all_urls": urls,

        "source": f"Unified Inbox ({item.get('channel', 'telegram')})",

        "source_message_uid": item.get("message_uid", ""),

        "raw_excerpt": raw_text[:500],

        "summary": first_line,

        "tags": extracted.get("tech_tags") or [],

        "notes": f"Saved from Inbox item #{item_id}"

    })



    update_inbox_message_status(item_id, "PROCESSED", notes=f"Saved as Learning Resource #{res_id}")

    return {"status": "SUCCESS", "resource_id": res_id, "item_id": item_id}



