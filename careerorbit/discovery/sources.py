"""Public job API adapters. No vacancies are synthesized or hard-coded here."""
from datetime import datetime, timedelta, timezone
from html import unescape
import re
from typing import Any, Dict, List
from urllib.parse import quote, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from careerorbit.eligibility import PRIORITY_LABELS, classify_title_to_priority, screen_job_for_candidate


class BaseJobSource:
    name = "base"
    endpoint = ""

    def __init__(self):
        retry = Retry(total=2, connect=2, read=2, status=2, backoff_factor=0.3,
                      status_forcelist=(429, 500, 502, 503, 504),
                      allowed_methods=frozenset(("GET",)), respect_retry_after_header=True)
        self.session = requests.Session()
        self.session.mount("https://", HTTPAdapter(max_retries=retry))

    def fetch_jobs(self, days_back: int = 7) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def _get_items(self, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        response = self.session.get(self.endpoint, params=params, timeout=(3.0, 5.0), headers={"User-Agent": "CareerOrbit/1.0 (public job API client)"})
        response.raise_for_status()
        payload = response.json()
        return self.extract(payload)

    def extract(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def normalize(self, item: Dict[str, Any], days_back: int) -> Dict[str, Any] | None:
        title = str(item.get("title") or "").strip()
        employer = str(item.get("company") or "").strip()
        url = str(item.get("url") or "").strip()
        parsed = urlparse(url)
        if not title or not employer or parsed.scheme not in ("https", "http") or not parsed.netloc:
            return None
        published = item.get("published")
        if published:
            try:
                dt = datetime.fromisoformat(str(published).replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if dt < datetime.now(timezone.utc) - timedelta(days=days_back):
                    return None
            except (ValueError, TypeError):
                published = None
        priority = classify_title_to_priority(title)
        return {
            "employer": employer, "title": title, "job_id_or_req": str(item.get("id") or ""),
            "priority_category": priority, "priority_label": PRIORITY_LABELS[priority],
            "location": str(item.get("location") or "Unknown"),
            "work_arrangement": str(item.get("work_arrangement") or "Unknown"),
            "employment_type": str(item.get("employment_type") or "Unknown"),
            "salary": item.get("salary"), "posting_date": published,
            "posting_date_confidence": str(item.get("posting_date_confidence") or ("SOURCE_REPORTED" if published else "UNKNOWN")),
            "deadline": item.get("deadline"),
            # Keep aggregator/source URLs in discovery_url. They are not proof of
            # an employer listing or a direct application destination.
            "official_url": str(item.get("official_url") or ""),
            "official_listing_url": str(item.get("official_listing_url") or ""),
            "application_url": str(item.get("application_url") or ""),
            "canonical_url": str(item.get("canonical_url") or item.get("official_url") or item.get("official_listing_url") or url),
            "discovery_url": str(item.get("discovery_url") or url),
            "discovery_source": self.name,
            "official_source_evidence": str(item.get("official_source_evidence") or ""),
            "source_is_official_api": bool(item.get("source_is_official_api", False)),
            "description": str(item.get("description") or ""),
            "is_fresher": bool(item.get("is_fresher", False)),
            "is_off_campus": bool(item.get("is_off_campus", False)),
            "is_internship": bool(item.get("is_internship", False)),
            "is_walkin": bool(item.get("is_walkin", False)),
            "min_experience_years": item.get("min_experience_years"),
            "max_experience_years": item.get("max_experience_years"),
        }


class JobicySource(BaseJobSource):
    name = "Jobicy Public API"
    endpoint = "https://jobicy.com/api/v2/remote-jobs"

    def extract(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [{"title": x.get("jobTitle"), "company": x.get("companyName"), "id": x.get("id"),
                 "location": x.get("jobGeo"), "work_arrangement": "Remote",
                 "employment_type": x.get("jobType"), "salary": None,
                 "published": x.get("pubDate"), "url": x.get("url"),
                 "description": x.get("jobDescription") or x.get("jobExcerpt")} for x in payload.get("jobs", [])]

    def fetch_jobs(self, days_back: int = 7) -> List[Dict[str, Any]]:
        return [j for x in self._get_items({"count": 50}) if (j := self.normalize(x, days_back))]


class RemotiveSource(BaseJobSource):
    name = "Remotive Public API"
    endpoint = "https://remotive.com/api/remote-jobs"

    def extract(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [{"title": x.get("title"), "company": x.get("company_name"), "id": x.get("id"),
                 "location": x.get("candidate_required_location"), "work_arrangement": "Remote",
                 "employment_type": x.get("job_type"), "salary": x.get("salary"),
                 "published": x.get("publication_date"), "url": x.get("url"),
                 "description": x.get("description")} for x in payload.get("jobs", [])]

    def fetch_jobs(self, days_back: int = 7) -> List[Dict[str, Any]]:
        return [j for x in self._get_items({"limit": 50}) if (j := self.normalize(x, days_back))]


class EmployerDirectVerifiedSource(BaseJobSource):
    """Placeholder adapter: no employer API is configured, so it returns no synthetic jobs."""
    name = "Employer career sites (not configured)"
    configured = False

    def fetch_jobs(self, days_back: int = 7) -> List[Dict[str, Any]]:
        return []


class ArbeitnowSource(BaseJobSource):
    """Fetches real tech and remote vacancies from Arbeitnow's public unauthenticated API."""
    name = "Arbeitnow Public API"
    endpoint = "https://www.arbeitnow.com/api/job-board-api"

    def extract(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        jobs = []
        for x in payload.get("data", []):
            created_at = x.get("created_at")
            published = None
            if isinstance(created_at, (int, float)) and created_at > 0:
                published = datetime.fromtimestamp(created_at, tz=timezone.utc).isoformat()

            desc = _plain_text(x.get("description") or "")
            is_remote = bool(x.get("remote"))
            work_arrangement = "Remote" if is_remote else _work_arrangement(f"{x.get('location', '')} {desc}")
            job_types = x.get("job_types") or []
            emp_type = ", ".join(job_types) if isinstance(job_types, list) and job_types else "Full-time"

            jobs.append({
                "title": x.get("title"),
                "company": x.get("company_name"),
                "id": x.get("slug"),
                "location": x.get("location") or ("Remote" if is_remote else "Unknown"),
                "work_arrangement": work_arrangement,
                "employment_type": emp_type,
                "salary": None,
                "published": published,
                "posting_date_confidence": "API_REPORTED" if published else "UNKNOWN",
                "url": x.get("url"),
                "discovery_url": x.get("url"),
                "description": desc,
            })
        return jobs

    def fetch_jobs(self, days_back: int = 7) -> List[Dict[str, Any]]:
        return [j for x in self._get_items({}) if (j := self.normalize(x, days_back))]


class GreenhouseBoardSource(BaseJobSource):
    """Reads public, published listings from Greenhouse's documented Job Board API."""

    def __init__(self, company: str, board_token: str):
        super().__init__()
        self.company = company.strip()
        self.board_token = board_token.strip()
        self.name = f"Greenhouse public board: {self.company}"
        self.configured = bool(re.fullmatch(r"[A-Za-z0-9_-]{1,100}", self.board_token))

    def fetch_jobs(self, days_back: int = 7) -> List[Dict[str, Any]]:
        if not self.configured:
            return []
        token = quote(self.board_token, safe="")
        board = self.session.get(f"https://boards-api.greenhouse.io/v1/boards/{token}", timeout=(3.05, 12))
        board.raise_for_status()
        board_name = str(board.json().get("name") or "").strip()
        # A configured label must match the public board identity; don't attribute another company's feed.
        b_key = _company_key(board_name)
        c_key = _company_key(self.company)
        t_key = _company_key(self.board_token)
        if not board_name or (b_key != c_key and c_key not in b_key and b_key not in c_key and t_key not in b_key):
            raise ValueError("configured Greenhouse company label does not match the public board name")
        endpoint = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
        response = self.session.get(endpoint, params={"content": "true"}, timeout=(3.05, 12))
        response.raise_for_status()
        data = response.json()
        jobs = []
        for item in data.get("jobs", []):
            loc = str((item.get("location") or {}).get("name") or "Unknown")
            desc = _plain_text(item.get("content") or "")
            url = str(item.get("absolute_url") or "")
            parsed_url = urlparse(url)
            if parsed_url.scheme != "https" or not parsed_url.hostname:
                continue
            is_gh_domain = parsed_url.hostname == "greenhouse.io" or parsed_url.hostname.endswith(".greenhouse.io")
            if is_gh_domain:
                parts = [part for part in parsed_url.path.split("/") if part]
                if len(parts) >= 2 and _company_key(parts[0]) != _company_key(self.board_token):
                    continue
            else:
                # Custom employer domain powered by Greenhouse job board
                is_custom_gh = "gh_jid=" in url or _company_key(self.company) in parsed_url.hostname.lower()
                if not is_custom_gh:
                    continue
            first_pub = item.get("first_published")
            published = None
            if first_pub:
                try:
                    p_dt = datetime.fromisoformat(str(first_pub).replace("Z", "+00:00"))
                    published = p_dt.isoformat()
                except (ValueError, TypeError):
                    published = None
            raw_req = str(item.get("requisition_id") or "").strip()
            if raw_req.lower() in ("see opening id", "n/a", "none", "null", "undefined"):
                raw_req = ""
            req_id = raw_req or str(item.get("internal_job_id") or item.get("id") or "")
            normalized = self.normalize({
                "id": req_id, "title": item.get("title"),
                "company": board_name or self.company, "location": loc,
                "work_arrangement": _work_arrangement(f"{loc} {desc}"),
                "employment_type": "Unknown", "published": published,
                "posting_date_confidence": "API_REPORTED" if published else "UNKNOWN", "url": url,
                "official_url": "", "official_listing_url": url, "application_url": "", "discovery_url": endpoint,
                "official_source_evidence": f"Public Greenhouse Job Board API for board {self.board_token}; published job record id {item.get('id')}.",
                "source_is_official_api": True,
                "description": desc,
            }, days_back)
            if normalized:
                jobs.append(normalized)
        return jobs


class LeverSiteSource(BaseJobSource):
    """Reads published postings from Lever's unauthenticated public Postings API."""

    def __init__(self, company: str, site_slug: str):
        super().__init__()
        self.company = company.strip()
        self.site_slug = site_slug.strip()
        self.name = f"Lever public postings: {self.company}"
        self.configured = bool(re.fullmatch(r"[A-Za-z0-9_-]{1,100}", self.site_slug))

    def fetch_jobs(self, days_back: int = 7) -> List[Dict[str, Any]]:
        if not self.configured:
            return []
        site = quote(self.site_slug, safe="")
        endpoint = f"https://api.lever.co/v0/postings/{site}"
        results: List[Dict[str, Any]] = []
        skip, limit, max_pages = 0, 100, 5
        for _ in range(max_pages):
            try:
                response = self.session.get(endpoint, params={"mode": "json", "skip": skip, "limit": limit}, timeout=(3.05, 10))
                if response.status_code == 429:
                    break
                response.raise_for_status()
                items = response.json()
            except Exception:
                if results:
                    break
                raise
            if not isinstance(items, list):
                raise ValueError("Lever postings response was not a JSON list")
            for item in items:
                try:
                    categories = item.get("categories") or {}
                    published = None
                    created_ms = item.get("createdAt")
                    if isinstance(created_ms, (int, float)) and created_ms > 0:
                        published = datetime.fromtimestamp(created_ms / 1000, tz=timezone.utc).isoformat()
                    hosted_url = str(item.get("hostedUrl") or "")
                    hosted = urlparse(hosted_url)
                    hosted_parts = [part for part in hosted.path.split("/") if part]
                    if hosted.hostname not in ("jobs.lever.co", "jobs.eu.lever.co") or not hosted_parts or _company_key(hosted_parts[0]) != _company_key(self.site_slug):
                        continue
                    application_url = str(item.get("applyUrl") or hosted_url)
                    apply_parsed = urlparse(application_url)
                    if (apply_parsed.scheme != "https" or apply_parsed.hostname not in ("jobs.lever.co", "jobs.eu.lever.co")
                            or not apply_parsed.path.startswith(f"/{hosted_parts[0]}/")):
                        continue
                    if len(hosted_parts) > 1 and hosted_parts[1] not in [p for p in apply_parsed.path.split("/") if p]:
                        continue
                    description = item.get("descriptionPlain") or _plain_text(item.get("description") or "")
                    location = str(categories.get("location") or categories.get("allLocations") or "Unknown")
                    normalized = self.normalize({
                        "id": item.get("id"), "title": item.get("text"), "company": self.company,
                        "location": location, "work_arrangement": _work_arrangement(f"{location} {description}"),
                        "employment_type": str(categories.get("commitment") or "Unknown"),
                        "published": published, "posting_date_confidence": "API_REPORTED" if published else "UNKNOWN",
                        "url": hosted_url or application_url, "official_url": application_url,
                        "official_listing_url": hosted_url, "application_url": application_url,
                        "discovery_url": hosted_url or endpoint,
                        "official_source_evidence": f"Public Lever Postings API for configured site {self.site_slug}; posting id {item.get('id')}.",
                        "source_is_official_api": True,
                        "description": description,
                    }, days_back)
                    if normalized:
                        results.append(normalized)
                except Exception:
                    continue
            if len(items) < limit:
                break
            skip += len(items)
        return results


def _company_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _plain_text(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", value))).strip()


def _work_arrangement(value: str) -> str:
    value = value.lower()
    if "hybrid" in value:
        return "Hybrid"
    if "remote" in value or "work from home" in value:
        return "Remote"
    if "on-site" in value or "onsite" in value or "in-office" in value:
        return "On-site"
    return "Unknown"


class SmartRecruitersSource(BaseJobSource):
    """Reads public job listings from SmartRecruiters' documented public API."""

    def __init__(self, company: str, company_id: str):
        super().__init__()
        self.company = company.strip()
        self.company_id = company_id.strip()
        self.name = f"SmartRecruiters public board: {self.company}"
        self.configured = bool(re.fullmatch(r"[A-Za-z0-9_-]{1,100}", self.company_id))

    def fetch_jobs(self, days_back: int = 7) -> List[Dict[str, Any]]:
        if not self.configured:
            return []
        token = quote(self.company_id, safe="")
        endpoint = f"https://api.smartrecruiters.com/v1/companies/{token}/postings"
        response = self.session.get(endpoint, params={"country": "in", "limit": 100}, timeout=(3.05, 12))
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("SmartRecruiters response was not a JSON object")

        jobs = []
        for item in data.get("content", []):
            try:
                job_id = str(item.get("id") or "")
                title = str(item.get("name") or "").strip()
                if not job_id or not title:
                    continue
                loc_obj = item.get("location") or {}
                city = str(loc_obj.get("city") or "India").strip()
                region = str(loc_obj.get("region") or "").strip()
                location = f"{city}, {region}, India" if region else f"{city}, India"
                is_remote = bool(loc_obj.get("remote", False))
                work_arrangement = "Remote" if is_remote else "On-site"
                emp_type_obj = item.get("typeOfEmployment") or {}
                emp_type = str(emp_type_obj.get("label") or "Full-time")

                released = item.get("releasedDate")
                published = None
                if released:
                    try:
                        p_dt = datetime.fromisoformat(str(released).replace("Z", "+00:00"))
                        published = p_dt.isoformat()
                    except (ValueError, TypeError):
                        published = None

                ref_number = str(item.get("refNumber") or job_id)
                posting_url = f"https://jobs.smartrecruiters.com/{token}/{job_id}"
                apply_url = f"https://jobs.smartrecruiters.com/{token}/{job_id}/apply"

                normalized = self.normalize({
                    "id": ref_number,
                    "title": title,
                    "company": self.company,
                    "location": location,
                    "work_arrangement": work_arrangement,
                    "employment_type": emp_type,
                    "published": published,
                    "posting_date_confidence": "API_REPORTED" if published else "UNKNOWN",
                    "url": posting_url,
                    "official_url": posting_url,
                    "official_listing_url": posting_url,
                    "application_url": apply_url,
                    "discovery_url": endpoint,
                    "official_source_evidence": f"Public SmartRecruiters API for company {self.company_id}; posting ref {ref_number}",
                    "source_is_official_api": True,
                    "description": f"{title} at {self.company} in {location}. Ref: {ref_number}.",
                }, days_back)
                if normalized:
                    jobs.append(normalized)
            except Exception:
                continue
        return jobs


class WorkableSource(BaseJobSource):
    """Reads public job listings from Workable's documented public API/widget endpoint."""

    def __init__(self, company: str, account_slug: str):
        super().__init__()
        self.company = company.strip()
        self.account_slug = account_slug.strip()
        self.name = f"Workable public board: {self.company}"
        self.configured = bool(re.fullmatch(r"[A-Za-z0-9_-]{1,100}", self.account_slug))

    def fetch_jobs(self, days_back: int = 7) -> List[Dict[str, Any]]:
        if not self.configured:
            return []
        slug = quote(self.account_slug, safe="")
        endpoint = f"https://apply.workable.com/api/v1/widget/accounts/{slug}"
        try:
            response = self.session.get(endpoint, timeout=(3.05, 12))
            if response.status_code == 404:
                endpoint = f"https://apply.workable.com/api/v1/widget/accounts/{slug}/jobs"
                response = self.session.get(endpoint, timeout=(3.05, 12))
            response.raise_for_status()
            data = response.json()
        except Exception:
            return []

        jobs = []
        raw_jobs = data.get("jobs", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
        for item in raw_jobs:
            try:
                job_id = str(item.get("id") or item.get("shortcode") or "")
                title = str(item.get("title") or "").strip()
                if not job_id or not title:
                    continue
                city = str(item.get("city") or "").strip()
                country = str(item.get("country") or "").strip()
                location_parts = [p for p in (city, country) if p]
                location = ", ".join(location_parts) if location_parts else "India"
                is_remote = bool(item.get("telecommuting", False)) or "remote" in location.lower()
                work_arrangement = "Remote" if is_remote else _work_arrangement(location)
                emp_type = str(item.get("employment_type") or "Full-time")

                published = item.get("published") or item.get("created_at")
                if published:
                    try:
                        p_dt = datetime.fromisoformat(str(published).replace("Z", "+00:00"))
                        published = p_dt.isoformat()
                    except Exception:
                        published = None

                job_url = str(item.get("url") or f"https://apply.workable.com/{slug}/j/{job_id}/")
                apply_url = str(item.get("application_url") or f"{job_url}apply/")

                normalized = self.normalize({
                    "id": job_id,
                    "title": title,
                    "company": self.company,
                    "location": location,
                    "work_arrangement": work_arrangement,
                    "employment_type": emp_type,
                    "published": published,
                    "posting_date_confidence": "API_REPORTED" if published else "UNKNOWN",
                    "url": job_url,
                    "official_url": job_url,
                    "official_listing_url": job_url,
                    "application_url": apply_url,
                    "discovery_url": endpoint,
                    "official_source_evidence": f"Public Workable widget API for account {self.account_slug}; job {job_id}",
                    "source_is_official_api": True,
                    "description": f"{title} at {self.company} in {location}.",
                }, days_back)
                if normalized:
                    jobs.append(normalized)
            except Exception:
                continue
        return jobs


class AshbyJobBoardSource(BaseJobSource):
    """Reads published listings from Ashby's public job board API."""

    def __init__(self, company: str, board_token: str):
        super().__init__()
        self.company = company.strip()
        self.board_token = board_token.strip()
        self.name = f"Ashby public board: {self.company}"
        self.configured = bool(re.fullmatch(r"[A-Za-z0-9_-]{1,100}", self.board_token))

    def fetch_jobs(self, days_back: int = 7) -> List[Dict[str, Any]]:
        if not self.configured:
            return []
        token = quote(self.board_token, safe="")
        endpoint = f"https://api.ashbyhq.com/posting-api/job-board/{token}"
        response = self.session.get(endpoint, timeout=(3.05, 12))
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Ashby response was not a JSON object")

        jobs = []
        for item in data.get("jobs", []):
            try:
                job_id = str(item.get("id") or "")
                title = str(item.get("title") or "").strip()
                if not job_id or not title:
                    continue
                location = str(item.get("location") or "India").strip()
                is_remote = bool(item.get("isRemote", False))
                work_arrangement = "Remote" if is_remote else _work_arrangement(location)
                emp_type = str(item.get("employmentType") or "Full-time")
                published_at = item.get("publishedAt")
                published = None
                if published_at:
                    try:
                        p_dt = datetime.fromisoformat(str(published_at).replace("Z", "+00:00"))
                        published = p_dt.isoformat()
                    except (ValueError, TypeError):
                        published = None

                job_url = str(item.get("jobUrl") or f"https://jobs.ashbyhq.com/{token}/{job_id}")
                apply_url = str(item.get("applyUrl") or f"{job_url}/application")
                comp = item.get("compensation") or {}
                salary = None
                if comp.get("summary"):
                    salary = str(comp.get("summary"))

                normalized = self.normalize({
                    "id": job_id,
                    "title": title,
                    "company": self.company,
                    "location": location,
                    "work_arrangement": work_arrangement,
                    "employment_type": emp_type,
                    "salary": salary,
                    "published": published,
                    "posting_date_confidence": "API_REPORTED" if published else "UNKNOWN",
                    "url": job_url,
                    "official_url": job_url,
                    "official_listing_url": job_url,
                    "application_url": apply_url,
                    "discovery_url": endpoint,
                    "official_source_evidence": f"Public Ashby Job Board API for board {self.board_token}; job id {job_id}",
                    "source_is_official_api": True,
                    "description": f"{title} at {self.company} in {location}.",
                }, days_back)
                if normalized:
                    jobs.append(normalized)
            except Exception:
                continue
        return jobs


class UnstopSource(BaseJobSource):
    """Fetches genuine Indian early-career, fresher, and off-campus recruitment opportunities from Unstop's public API."""
    name = "Unstop Campus & Fresher API"
    endpoint = "https://unstop.com/api/public/opportunity/search-result"

    def __init__(self):
        super().__init__()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
        })

    def fetch_jobs(self, days_back: int = 7) -> List[Dict[str, Any]]:
        query_configs = [
            {"opportunity": "jobs", "searchTerm": "data analyst", "per_page": 20},
            {"opportunity": "jobs", "searchTerm": "software engineer", "per_page": 20},
            {"opportunity": "jobs", "searchTerm": "python developer", "per_page": 15},
            {"opportunity": "jobs", "searchTerm": "power bi", "per_page": 15},
            {"opportunity": "jobs", "searchTerm": "data engineer", "per_page": 15},
            {"opportunity": "jobs", "searchTerm": "graduate engineer trainee", "per_page": 15},
            {"opportunity": "hiring-challenges", "per_page": 25},
        ]

        seen_uids = set()
        collected: List[Dict[str, Any]] = []
        total_queries = len(query_configs)
        failed_queries = 0
        last_error = None

        for params in query_configs:
            try:
                resp = self.session.get(self.endpoint, params=params, timeout=(3.05, 8))
                resp.raise_for_status()
                payload = resp.json()
            except Exception as exc:
                failed_queries += 1
                last_error = exc
                continue

            raw_items = payload.get("data", {}).get("data", [])
            if not isinstance(raw_items, list):
                continue

            for item in raw_items:
                try:
                    job_id = str(item.get("id") or "")
                    if not job_id or job_id in seen_uids:
                        continue
                    seen_uids.add(job_id)

                    # Only live and registration-open opportunities
                    regn_open = item.get("regn_open")
                    if regn_open not in (1, True, "1"):
                        continue

                    title = str(item.get("title") or "").strip()
                    org_obj = item.get("organisation") or {}
                    employer = str(org_obj.get("name") or "Campus Hiring Partner").strip()
                    if not title or not employer:
                        continue

                    # Direct public URL on Unstop
                    seo_url = item.get("seo_url")
                    pub_path = item.get("public_url") or ""
                    url = seo_url or (f"https://unstop.com/{pub_path}" if pub_path else "")
                    if not url or not url.startswith("http"):
                        continue

                    # Extract locations
                    loc_list = item.get("locations") or []
                    loc_parts = []
                    for loc_entry in loc_list:
                        if isinstance(loc_entry, dict):
                            city = loc_entry.get("city") or ""
                            state = loc_entry.get("state") or ""
                            c_part = f"{city}, {state}".strip(", ")
                            if c_part and c_part not in loc_parts:
                                loc_parts.append(c_part)
                    location = ", ".join(loc_parts) if loc_parts else "India / Remote"

                    job_detail = item.get("jobDetail") or {}
                    w_type = str(job_detail.get("type") or item.get("region") or "").lower()
                    work_arrangement = "Remote" if "wfh" in w_type or "online" in w_type or "remote" in w_type else _work_arrangement(location)
                    emp_type = "Full-time" if job_detail.get("timing") == "full_time" else (job_detail.get("timing") or "Full-time")

                    # Salary
                    salary = None
                    min_sal = job_detail.get("min_salary")
                    max_sal = job_detail.get("max_salary")
                    if min_sal:
                        salary = f"₹{min_sal:,} - ₹{max_sal:,} / yr" if max_sal else f"₹{min_sal:,} / yr"

                    # Publishing / end date
                    approved_date = item.get("approved_date") or item.get("updated_at")
                    published = None
                    if approved_date:
                        try:
                            clean_d = re.sub(r"\s+GMT([+-]\d{4})", r"\1", str(approved_date))
                            p_dt = datetime.fromisoformat(clean_d.replace("Z", "+00:00"))
                            published = p_dt.isoformat()
                        except Exception:
                            published = None

                    deadline = item.get("end_date")
                    details_html = item.get("details") or ""
                    description = _plain_text(details_html) or f"{title} at {employer}."

                    # Attributes
                    opp_type = str(item.get("type") or "")
                    is_challenge = opp_type == "hiring-challenges" or "challenge" in title.lower() or "drive" in title.lower()
                    min_exp = job_detail.get("min_experience")
                    max_exp = job_detail.get("max_experience")
                    is_fresher = (min_exp == 0 or (max_exp is not None and max_exp <= 2) or "fresher" in title.lower() or "graduate" in title.lower())
                    is_intern = "intern" in title.lower() or job_detail.get("timing") == "internship"

                    normalized = self.normalize({
                        "id": job_id,
                        "title": title,
                        "company": employer,
                        "location": location,
                        "work_arrangement": work_arrangement,
                        "employment_type": emp_type,
                        "salary": salary,
                        "published": published,
                        "posting_date_confidence": "API_REPORTED" if published else "UNKNOWN",
                        "deadline": deadline,
                        "url": url,
                        "official_url": url,
                        "official_listing_url": url,
                        "application_url": url,
                        "discovery_url": f"{self.endpoint}?opportunity={params.get('opportunity')}",
                        "official_source_evidence": f"Unstop verified campus/early-career vacancy id {job_id}; registration open",
                        "source_is_official_api": True,
                        "description": description,
                        "is_fresher": is_fresher,
                        "is_off_campus": is_challenge,
                        "is_internship": is_intern,
                        "min_experience_years": float(min_exp) if min_exp is not None else 0.0,
                        "max_experience_years": float(max_exp) if max_exp is not None else (2.0 if is_fresher else None),
                    }, days_back)
                    if normalized:
                        collected.append(normalized)
                except Exception:
                    continue
        if failed_queries == total_queries and last_error is not None:
            raise last_error
        return collected


class RemoteOKSource(BaseJobSource):
    """Fetches real remote tech roles from RemoteOK's public unauthenticated API."""
    name = "RemoteOK Public API"
    endpoint = "https://remoteok.com/api"

    def __init__(self):
        super().__init__()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) CareerOrbit/1.0",
            "Accept": "application/json",
        })

    def fetch_jobs(self, days_back: int = 7) -> List[Dict[str, Any]]:
        response = self.session.get(self.endpoint, timeout=(3.05, 10))
        response.raise_for_status()
        items = response.json()
        if not isinstance(items, list):
            raise ValueError("RemoteOK response was not a JSON list")

        jobs = []
        for x in items:
            if not isinstance(x, dict) or not x.get("id"):
                continue
            title = x.get("position")
            company = x.get("company")
            url = x.get("url")
            if not title or not company or not url:
                continue

            loc = x.get("location") or "Worldwide / Remote"
            published_dt = x.get("date")
            published = None
            if published_dt:
                try:
                    p_dt = datetime.fromisoformat(str(published_dt).replace("Z", "+00:00"))
                    published = p_dt.isoformat()
                except Exception:
                    published = None

            desc = _plain_text(x.get("description") or "")
            normalized = self.normalize({
                "id": str(x.get("id")),
                "title": title,
                "company": company,
                "location": loc,
                "work_arrangement": "Remote",
                "employment_type": "Full-time",
                "salary": None,
                "published": published,
                "posting_date_confidence": "API_REPORTED" if published else "UNKNOWN",
                "url": url,
                "official_url": url,
                "official_listing_url": url,
                "application_url": url,
                "discovery_url": self.endpoint,
                "official_source_evidence": f"RemoteOK public API posting id {x.get('id')}",
                "source_is_official_api": False,
                "description": desc,
            }, days_back)
            if normalized:
                jobs.append(normalized)
        return jobs
