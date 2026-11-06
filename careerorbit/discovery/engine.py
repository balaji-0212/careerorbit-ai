"""Job discovery engine coordinating multi-source searches, verification, scoring, and deduplication."""
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from careerorbit.discovery.sources import (
    BaseJobSource, JobicySource, RemotiveSource, ArbeitnowSource, EmployerDirectVerifiedSource,
    GreenhouseBoardSource, LeverSiteSource, SmartRecruitersSource, AshbyJobBoardSource, WorkableSource,
    UnstopSource, RemoteOKSource, PRIORITY_LABELS,
    screen_job_for_candidate,
)
from careerorbit.discovery.registry import list_employer_sources, record_source_check
from careerorbit.verifier.checker import VerificationEngine
from careerorbit.matcher.scorer import JobScorer
from careerorbit.dedup.deduplicator import Deduplicator
from careerorbit.database.db import save_job, get_job_by_uid, update_job_source_health
from careerorbit.models.schemas import Job, VerificationStatus
from careerorbit.config.settings import SETTINGS

logger = logging.getLogger("careerorbit.discovery")

class JobDiscoveryEngine:
    """Discovers, verifies, scores, and registers job opportunities."""

    def __init__(self):
        self.sources: List[BaseJobSource] = [
            UnstopSource(), JobicySource(), RemotiveSource(), ArbeitnowSource(),
            RemoteOKSource(), EmployerDirectVerifiedSource()
        ]
        self.sources.extend(_configured_ats_sources(SETTINGS.GREENHOUSE_BOARDS, GreenhouseBoardSource, "Greenhouse"))
        self.sources.extend(_configured_ats_sources(SETTINGS.LEVER_SITES, LeverSiteSource, "Lever"))

        # Incorporate active configured sources from the employer registry
        try:
            for entry in list_employer_sources():
                if not entry.get("enabled", True):
                    continue
                board_id = str(entry.get("board_id") or "").strip()
                company = str(entry.get("employer_name") or "").strip()
                provider = str(entry.get("ats_provider") or "").strip().lower()
                if not board_id or not company:
                    continue
                if provider == "greenhouse":
                    self.sources.append(GreenhouseBoardSource(company=company, board_token=board_id))
                elif provider == "lever":
                    self.sources.append(LeverSiteSource(company=company, site_slug=board_id))
                elif provider in ("smartrecruiters", "smart_recruiters"):
                    self.sources.append(SmartRecruitersSource(company=company, company_id=board_id))
                elif provider == "ashby":
                    self.sources.append(AshbyJobBoardSource(company=company, board_token=board_id))
                elif provider == "workable":
                    self.sources.append(WorkableSource(company=company, account_slug=board_id))
        except Exception:
            pass

        self.verifier = VerificationEngine(timeout_seconds=8)
        self.scorer = JobScorer()

    def run_discovery(
        self,
        initial_days: int = 1,
        min_acceptable: int = 5,
        progress_callback: Optional[Any] = None
    ) -> Dict[str, Any]:
        """Runs multi-window job discovery (24h -> 3d -> 7d) as specified in requirements."""
        now = datetime.now(timezone.utc)
        collected_raw: List[Dict[str, Any]] = []
        source_results: Dict[str, Dict[str, Any]] = {}
        failed_sources: set[str] = set()

        def fetch_window(days: int) -> List[Dict[str, Any]]:
            window_results: List[Dict[str, Any]] = []
            for source in self.sources:
                if not getattr(source, "configured", True):
                    source_results[source.name] = {
                        "status": "skipped", "count": 0, "raw_count": 0,
                        "reason": "No board identifier configured.", "windows": []
                    }

            active_sources = [
                s for s in self.sources
                if getattr(s, "configured", True) and s.name not in failed_sources
            ]

            def query_source(source: BaseJobSource):
                if progress_callback:
                    try:
                        progress_callback(f"Querying {source.name} (last {days}d)...", source_results)
                    except Exception:
                        pass
                try:
                    fetched = source.fetch_jobs(days_back=days)
                    accepted, filtered = [], {}
                    for raw_job in fetched:
                        reason = screen_job_for_candidate(raw_job)
                        if reason:
                            filtered[reason] = filtered.get(reason, 0) + 1
                        else:
                            accepted.append(raw_job)
                    return source.name, "ok", accepted, len(fetched), filtered, None
                except Exception as exc:
                    return source.name, "failed", [], 0, {}, type(exc).__name__

            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=min(len(active_sources) or 1, 6)) as executor:
                futures = [executor.submit(query_source, s) for s in active_sources]
                for fut in futures:
                    s_name, status, accepted, raw_count, filtered, err = fut.result()
                    if status == "ok":
                        window_results.extend(accepted)
                        _record_source_window(source_results, s_name, days, "ok", len(accepted), raw_count, filtered)
                    else:
                        failed_sources.add(s_name)
                        logger.warning("Source %s query failed (%s)", s_name, err)
                        _record_source_window(source_results, s_name, days, "failed", 0, 0, {}, err)

            return window_results

        # 1. Search last 24h first
        current_days = initial_days
        collected_raw.extend(fetch_window(current_days))

        # 2. If too few found, expand to 3 days, then 7 days, then 14 days, then 30 days
        if len(collected_raw) < min_acceptable and current_days < 3:
            current_days = 3
            collected_raw.extend(fetch_window(current_days))

        if len(collected_raw) < min_acceptable and current_days < 7:
            current_days = 7
            collected_raw.extend(fetch_window(current_days))

        if len(collected_raw) < min_acceptable and current_days < 14:
            current_days = 14
            collected_raw.extend(fetch_window(current_days))

        if len(collected_raw) < min_acceptable and current_days < 30:
            current_days = 30
            collected_raw.extend(fetch_window(current_days))

        if len(collected_raw) < min_acceptable and current_days < 90:
            current_days = 90
            collected_raw.extend(fetch_window(current_days))

        # 3. Deduplicate, Verify, Score, and Store
        if progress_callback:
            try:
                progress_callback(f"Processing, scoring, and storing {len(collected_raw)} collected leads...", source_results)
            except Exception:
                pass

        processed_jobs: List[Dict[str, Any]] = []
        seen_in_run: set[str] = set()
        new_count = 0
        updated_count = 0

        for raw in collected_raw:
            emp = str(raw.get("employer") or "").strip()
            title = str(raw.get("title") or "").strip()
            if not emp or not title:
                continue

            # Normalized title and unique ID
            norm_title = Deduplicator.normalize_job_title(title)
            job_req = raw.get("job_id_or_req", "")
            loc = raw.get("location", "India")
            official_listing_url = Deduplicator.canonicalize_url(raw.get("official_listing_url", ""))
            application_url = Deduplicator.canonicalize_url(raw.get("application_url", ""))
            official_url = Deduplicator.canonicalize_url(raw.get("official_url", "")) or application_url or official_listing_url
            discovery_url = Deduplicator.canonicalize_url(raw.get("discovery_url", ""))
            canonical_url = Deduplicator.canonicalize_url(raw.get("canonical_url", "")) or official_url or official_listing_url or discovery_url
            req_key = f"{emp.casefold()}::{raw.get('discovery_source','')}::{job_req}" if job_req else ""
            url_key = f"url::{canonical_url.casefold()}" if canonical_url else ""
            dedup_key = url_key or req_key or f"{emp.casefold()}::{norm_title}::{loc.casefold()}"
            if dedup_key in seen_in_run:
                continue
            seen_in_run.add(dedup_key)
            job_uid = Deduplicator.generate_job_uid(emp, norm_title, job_req or canonical_url, loc)

            # Verify official application destination using live HTTP check and ATS evidence
            discovery_src = raw.get("discovery_source", "")
            target_url = official_url or official_listing_url
            if target_url:
                v_status, v_notes = self.verifier.verify_listing(target_url, employer=emp)
                if v_status in (VerificationStatus.PENDING_VERIFICATION, VerificationStatus.UNVERIFIED) and raw.get("source_is_official_api") and raw.get("official_source_evidence"):
                    v_notes = f"{v_notes} (Recorded from official {discovery_src})"
            else:
                v_status = VerificationStatus.PENDING_VERIFICATION if discovery_url else VerificationStatus.VERIFICATION_ERROR
                v_notes = "No official listing/application destination was supplied; third-party discovery alone does not establish current vacancy status."
            verification_at = now.isoformat() if target_url else ""
            observed_at = now.isoformat()

            # Score vacancy
            score_input = {
                "title": title,
                "description": raw.get("description", ""),
                "location": loc,
                "work_arrangement": raw.get("work_arrangement", "Hybrid"),
                "salary": raw.get("salary", "Not Disclosed"),
                "posting_date": raw.get("posting_date"),
                "posting_date_confidence": raw.get("posting_date_confidence", "UNKNOWN"),
                "verification_status": v_status.value
            }
            score_res = self.scorer.score_job(score_input)

            # Check existing record in DB
            existing = get_job_by_uid(job_uid)
            if existing:
                # Merge records
                merged, changed = Deduplicator.merge_job_records(existing, {
                    "official_url": official_url,
                    "official_listing_url": official_listing_url,
                    "application_url": application_url,
                    "canonical_url": canonical_url,
                    "verification_status": v_status.value,
                    "verification_notes": v_notes,
                    "verification_source": raw.get("official_source_evidence") or "",
                    "discovery_url": discovery_url,
                    "posting_date": raw.get("posting_date"),
                    "posting_date_confidence": raw.get("posting_date_confidence", "UNKNOWN"),
                    "discovery_source": discovery_src,
                    "match_score": score_res["match_score"],
                    "match_tier": score_res["match_tier"].value,
                    "score_breakdown": score_res["score_breakdown"].model_dump(),
                    "last_verified_at": verification_at,
                    "last_observed_status": v_status.value,
                    "last_observed_status_at": observed_at,
                })
                if changed:
                    job_obj = Job(
                        job_uid=job_uid,
                        employer=merged["employer"],
                        title=merged["title"],
                        normalized_title=norm_title,
                        job_id_or_req=merged.get("job_id_or_req", ""),
                        priority_category=merged["priority_category"],
                        priority_label=PRIORITY_LABELS.get(merged["priority_category"], "General"),
                        location=merged["location"],
                        work_arrangement=merged.get("work_arrangement", "Hybrid"),
                        employment_type=merged.get("employment_type", "Full-time"),
                        salary=merged.get("salary", "Not Disclosed"),
                        shift=merged.get("shift", "Day shift"),
                        posting_date=merged.get("posting_date"),
                        posting_date_confidence=merged.get("posting_date_confidence", "UNKNOWN"),
                        deadline=merged.get("deadline"),
                        official_url=merged["official_url"],
                        official_listing_url=merged.get("official_listing_url", ""),
                        application_url=merged.get("application_url", ""),
                        discovery_url=discovery_url or merged.get("discovery_url", ""),
                        canonical_url=merged.get("canonical_url", canonical_url),
                        discovery_source=merged.get("discovery_source", "Aggregator"),
                        verification_source=raw.get("official_source_evidence") or merged.get("verification_source", ""),
                        verification_status=VerificationStatus(merged["verification_status"]),
                        verification_notes=merged.get("verification_notes", ""),
                        match_score=merged["match_score"],
                        match_tier=score_res["match_tier"],
                        score_breakdown=score_res["score_breakdown"],
                        required_skills=score_res["supported_skills"] + score_res["missing_skills"],
                        supported_skills=score_res["supported_skills"],
                        missing_skills=score_res["missing_skills"],
                        learnable_skills=score_res["learnable_skills"],
                        disqualifiers=score_res["disqualifiers"],
                        evidence_notes=score_res["evidence_notes"],
                        recommended_action=score_res["recommended_action"],
                        description=merged.get("description", ""),
                        is_fresher=bool(raw.get("is_fresher", False)),
                        is_off_campus=bool(raw.get("is_off_campus", False)),
                        is_internship=bool(raw.get("is_internship", False)),
                        is_walkin=bool(raw.get("is_walkin", False)),
                        min_experience_years=raw.get("min_experience_years"),
                        max_experience_years=raw.get("max_experience_years"),
                        first_discovered_at=existing["first_discovered_at"],
                        last_verified_at=verification_at,
                        last_observed_status=v_status.value,
                        last_observed_status_at=observed_at
                    )
                    save_job(job_obj)
                    updated_count += 1
            else:
                # Insert brand new record
                job_obj = Job(
                    job_uid=job_uid,
                    employer=emp,
                    title=title,
                    normalized_title=norm_title,
                    job_id_or_req=job_req,
                    priority_category=raw.get("priority_category", 1),
                    priority_label=PRIORITY_LABELS.get(raw.get("priority_category", 1), "Data Analyst"),
                    location=loc,
                    work_arrangement=raw.get("work_arrangement", "Hybrid"),
                    employment_type=raw.get("employment_type", "Full-time"),
                    salary=raw.get("salary", "Not Disclosed"),
                    shift=raw.get("shift", "Day shift"),
                    posting_date=raw.get("posting_date"),
                    posting_date_confidence=raw.get("posting_date_confidence", "UNKNOWN"),
                    deadline=raw.get("deadline"),
                    official_url=official_url,
                    official_listing_url=official_listing_url,
                    application_url=application_url,
                    discovery_url=discovery_url,
                    canonical_url=canonical_url,
                    discovery_source=raw.get("discovery_source", "Online"),
                    verification_source=raw.get("official_source_evidence") or "",
                    verification_status=v_status,
                    verification_notes=v_notes,
                    match_score=score_res["match_score"],
                    match_tier=score_res["match_tier"],
                    score_breakdown=score_res["score_breakdown"],
                    required_skills=score_res["supported_skills"] + score_res["missing_skills"],
                    supported_skills=score_res["supported_skills"],
                    missing_skills=score_res["missing_skills"],
                    learnable_skills=score_res["learnable_skills"],
                    disqualifiers=score_res["disqualifiers"],
                    evidence_notes=score_res["evidence_notes"],
                    recommended_action=score_res["recommended_action"],
                    description=raw.get("description", ""),
                    is_fresher=bool(raw.get("is_fresher", False)),
                    is_off_campus=bool(raw.get("is_off_campus", False)),
                    is_internship=bool(raw.get("is_internship", False)),
                    is_walkin=bool(raw.get("is_walkin", False)),
                    min_experience_years=raw.get("min_experience_years"),
                    max_experience_years=raw.get("max_experience_years"),
                    first_discovered_at=now.isoformat(),
                    last_verified_at=verification_at,
                    last_observed_status=v_status.value,
                    last_observed_status_at=observed_at
                )
                save_job(job_obj)
                new_count += 1

            processed_jobs.append({
                "job_uid": job_uid,
                "employer": emp,
                "title": title,
                "priority_category": raw.get("priority_category", 1),
                "match_score": score_res["match_score"],
                "match_tier": score_res["match_tier"].value,
                "verification_status": v_status.value
            })

        # Update persistent job_sources health dynamically based on real sync outcome
        for s_name, s_res in source_results.items():
            st = s_res.get("status")
            c = s_res.get("count", 0)
            rejected_c = sum(s_res.get("filtered", {}).values())
            err_msg = s_res.get("error")
            try:
                if st == "ok":
                    update_job_source_health(
                        source_id=s_name,
                        health_status="HEALTHY",
                        discovered_count=c,
                        rejected_count=rejected_c,
                        success=True
                    )
                elif st == "partial":
                    update_job_source_health(
                        source_id=s_name,
                        health_status="DEGRADED",
                        discovered_count=c,
                        rejected_count=rejected_c,
                        error_category="PARTIAL_FAILURE",
                        error_message=err_msg,
                        success=False
                    )
                elif st == "failed":
                    update_job_source_health(
                        source_id=s_name,
                        health_status="FAILING",
                        discovered_count=0,
                        error_category="SYNC_FAILURE",
                        error_message=err_msg,
                        success=False
                    )
            except Exception as e:
                logger.warning("Could not update health for source %s: %s", s_name, e)

        return {
            "search_timestamp": now.isoformat(),
            "time_window_days": current_days,
            "total_collected": len(collected_raw),
            "new_jobs_added": new_count,
            "jobs_updated": updated_count,
            "sources": source_results,
            "partial_failure": any(
                v.get("status") in ("failed", "partial") or any(w.get("status") == "failed" for w in v.get("windows", []))
                for v in source_results.values()
            ),
            "processed_jobs": processed_jobs
        }


def _record_source_window(
    source_results: Dict[str, Dict[str, Any]], name: str, days: int,
    status: str, count: int, raw_count: int, filtered: Dict[str, int], error: str = ""
) -> None:
    """Retain independent source status for each recency window and aggregate failures."""
    result = source_results.setdefault(name, {"status": status, "count": 0, "raw_count": 0,
                                               "filtered": {}, "windows": []})
    result["windows"].append({"days_back": days, "status": status, "count": count,
                              "raw_count": raw_count, "filtered": filtered, **({"error": error} if error else {})})
    result["count"] += count
    result["raw_count"] += raw_count
    for reason, number in filtered.items():
        result["filtered"][reason] = result["filtered"].get(reason, 0) + number
    statuses = [window["status"] for window in result["windows"]]
    if all(item == "failed" for item in statuses):
        result["status"] = "failed"
        result["error"] = error or result["windows"][-1].get("error", "source failed")
    elif any(item == "failed" for item in statuses):
        result["status"] = "partial"
    else:
        result["status"] = "ok"


def _configured_ats_sources(value: str, source_type: type[BaseJobSource], platform: str) -> List[BaseJobSource]:
    entries = [entry.strip() for entry in (value or "").split(",") if entry.strip()]
    if not entries:
        source = source_type("", "")
        source.name = f"{platform} public board API (not configured)"
        source.configured = False
        return [source]
    sources: List[BaseJobSource] = []
    for entry in entries:
        company, sep, token = entry.partition("=")
        if not sep or not company.strip() or not token.strip():
            class InvalidConfiguredSource(BaseJobSource):
                def fetch_jobs(self, days_back: int = 7) -> List[Dict[str, Any]]:
                    return []
            invalid = InvalidConfiguredSource()
            invalid.name = f"{platform} invalid config: {entry[:40]}"
            invalid.configured = False
            sources.append(invalid)
            continue
        sources.append(source_type(company.strip(), token.strip()))
    return sources
