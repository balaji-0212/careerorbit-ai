"""Conservative listing checks; page reachability alone never proves a vacancy is open."""



from __future__ import annotations



import ipaddress



import re



import socket



import urllib.parse



from typing import Optional, Tuple, Dict, Any, Callable







import requests







from careerorbit.models.schemas import VerificationStatus







CLOSURE_PATTERNS = [



    r"no\s+longer\s+accepting\s+applications",



    r"job\s+(?:is\s+)?closed",



    r"position\s+(?:has\s+been\s+)?filled",



    r"posting\s+is\s+no\s+longer\s+available",



    r"position\s+(?:is\s+|has\s+been\s+)?closed",

    r"posting\s+(?:is\s+)?closed",

    r"requisition\s+(?:is\s+)?closed",



    r"application\s+(?:is\s+)?closed",



    r"job\s+not\s+found",



    r"page\s+not\s+found",



    r"the\s+job\s+you\s+are\s+looking\s+for\s+could\s+not\s+be\s+found",



    r"job\s+you\s+are\s+looking\s+for\s+could\s+not\s+be\s+found",



    r"page\s+you\s+are\s+looking\s+for\s+doesn't\s+exist",



    r"this\s+job\s+is\s+no\s+longer\s+available",



    r"we\s+couldn't\s+find\s+that\s+page",



    r"404\s+not\s+found",



]



CAPTCHA_PATTERNS = [



    r"verify\s+you\s+are\s+(?:a\s+)?human",



    r"cf-browser-verification",



    r"cf-challenge-running",



    r"attention\s+required!\s*\|\s*cloudflare",



    r"security\s+check",



    r"cloudflare\s+(?:ray\s+id|challenge)",



    r"please\s+enable\s+cookies\s+and\s+reload",



    r"bot\s+detection\s+system",



]



OPEN_INDICATORS = [



    r"apply\s+now",



    r"submit\s+application",



    r"apply\s+for\s+this\s+job",



    r"start\s+application",



    r"apply\s+online",



    r"submit\s+your\s+application",



    r"apply\s+to\s+this\s+position",



    r"apply\s+with\s+linkedin",



    r"apply\s+today",



    r"apply[-_]btn",



    r"apply[-_]job[-_]btn",



    r"job\.apply",



]



ATS_SUFFIXES = ("greenhouse.io", "lever.co", "myworkdayjobs.com", "smartrecruiters.com", "workable.com", "icims.com", "taleo.net", "jobvite.com", "ashbyhq.com", "bamboohr.com")



AGGREGATOR_SUFFIXES = ("indeed.com", "naukri.com", "monster.com", "foundit.in", "shine.com", "linkedin.com", "glassdoor.com", "ziprecruiter.com", "timesjobs.com", "jobicy.com", "remotive.com")











def _suffix(host: str, domains: tuple[str, ...]) -> bool:



    host = host.lower().rstrip(".")



    return any(host == d or host.endswith("." + d) for d in domains)











DEFAULT_DNS_RESOLVER: Optional[Callable[[str], list]] = None











def deterministic_test_dns_resolver(host: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:



    """Deterministic DNS resolver fixture for hermetic test execution without network dependency."""



    host = host.lower().rstrip(".")



    if host in ("localhost", "127.0.0.1") or host.endswith((".localhost", ".local", ".internal")):



        return [ipaddress.ip_address("127.0.0.1")]



    if host in ("metadata.google.internal", "169.254.169.254"):



        return [ipaddress.ip_address("169.254.169.254")]



    if "private" in host or host.endswith(".lan") or host in ("10.0.0.1", "192.168.1.1"):



        return [ipaddress.ip_address("192.168.1.1")]



    if "invalid" in host or "nonexistent" in host or "fails" in host:



        raise socket.gaierror("Name or service not known")



    # Public domain names resolve to controlled global public IP



    return [ipaddress.ip_address("104.18.0.1")]











def _public_http_url(url: str, resolver: Optional[Callable] = None) -> bool:



    try:



        p = urllib.parse.urlparse(url)



        if p.scheme != "https" or not p.hostname or p.username or p.password:



            return False



        host = p.hostname.lower().rstrip(".")



        if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):



            return False



        # Hostname syntax validation (no leading dots, consecutive dots, or invalid characters)



        if host.startswith(".") or ".." in host or not re.match(r"^[a-z0-9]([a-z0-9\-_\.]*[a-z0-9])?$", host):



            return False



        try:



            ips = [ipaddress.ip_address(host)]



        except ValueError:



            res = resolver if resolver is not None else DEFAULT_DNS_RESOLVER



            if res is not None:



                ips = res(host)



            else:



                ips = [ipaddress.ip_address(row[4][0]) for row in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)]



        return bool(ips) and all(ip.is_global for ip in ips)



    except (ValueError, OSError, IndexError):



        return False











class VerificationEngine:



    def __init__(self, timeout_seconds: int = 10, dns_resolver: Optional[Callable] = None):



        self.timeout = timeout_seconds



        self.dns_resolver = dns_resolver or DEFAULT_DNS_RESOLVER



        self.session = requests.Session()



        self.session.headers.update({"User-Agent": "CareerOrbit/1.0 (job listing verification)", "Accept": "text/html,application/xhtml+xml"})







    def is_official_employer_url(self, url: str) -> bool:



        try:



            host = urllib.parse.urlparse(url).hostname or ""



            return _suffix(host, ATS_SUFFIXES) and not _suffix(host, AGGREGATOR_SUFFIXES)



        except ValueError:



            return False







    def verify_listing(self, url: str, is_official: Optional[bool] = None, employer: str = "") -> Tuple[VerificationStatus, str]:



        if not _public_http_url(url, resolver=self.dns_resolver):



            return VerificationStatus.STATUS_UNKNOWN, "URL must use HTTPS and resolve to a public host; no request was made."



        parsed_init = urllib.parse.urlparse(url)



        host = (parsed_init.hostname or "").lower()



        path = parsed_init.path or ""



        is_aggregator = _suffix(host, AGGREGATOR_SUFFIXES)







        # Deducing employer from ATS tenant if not provided or unconfirmed



        if not employer or "unconfirmed" in employer.lower():



            if "greenhouse.io" in host:



                parts = [p for p in parsed_init.path.split('/') if p]



                if parts:



                    employer = parts[0].title()



            elif "lever.co" in host:



                parts = [p for p in parsed_init.path.split('/') if p]



                if parts:



                    employer = parts[0].title()



            elif "myworkdayjobs.com" in host:



                employer = host.split('.')[0].title()



            elif "smartrecruiters.com" in host:



                parts = [p for p in parsed_init.path.split('/') if p]



                if parts:



                    employer = parts[0].title()



            elif "workable.com" in host:



                parts = [p for p in parsed_init.path.split('/') if p]



                if parts:



                    employer = parts[0].title()



            elif "ashbyhq.com" in host:



                parts = [p for p in parsed_init.path.split('/') if p]



                if parts:



                    employer = parts[0].title()







        official = self.is_official_employer_url(url) if is_official is None else bool(is_official)



        if not official and employer:



            emp_tokens = [t for t in re.findall(r"[a-z0-9]+", employer.lower()) if len(t) >= 3]



            host_tokens = re.findall(r"[a-z0-9]+", host)



            if any(t in host_tokens for t in emp_tokens):



                official = True







        if official and employer:



            # Lever and SmartRecruiters often identify the tenant in the path; Workday



            # and Greenhouse commonly identify it in the host.



            tenant_text = (parsed_init.hostname or "") + " " + " ".join(parsed_init.path.split("/")[:4])



            tenant = re.findall(r"[a-z0-9]+", tenant_text.lower())



            employer_tokens = re.findall(r"[a-z0-9]+", employer.lower())



            official = any(len(token) >= 3 and any(token in t or t in token for t in tenant) for token in employer_tokens)







        # Check for generic employer homepage without vacancy requisition context



        if not is_aggregator and path in ("", "/", "/careers", "/jobs", "/careers/", "/jobs/"):



            return VerificationStatus.SUSPICIOUS, "URL resolves to employer homepage or generic careers directory rather than a specific vacancy requisition."







        try:



            curr_url = url



            code = 200



            resp = None



            for _ in range(4):



                parsed_curr = urllib.parse.urlparse(curr_url)



                resp = self.session.get(curr_url, timeout=self.timeout, allow_redirects=False)



                code = resp.status_code



                if code in (404, 410):



                    return VerificationStatus.VERIFIED_CLOSED, f"Application URL returned HTTP {code} (Not Found / Gone); vacancy is closed or removed."



                if code in (301, 302, 303, 307, 308):



                    redirect_loc = resp.headers.get("location")



                    if not redirect_loc:



                        return VerificationStatus.PENDING_VERIFICATION, "Listing redirects; destination was not followed automatically."



                    resolved_redirect = urllib.parse.urljoin(curr_url, redirect_loc)



                    parsed_red = urllib.parse.urlparse(resolved_redirect)



                    same_host = (parsed_red.hostname == parsed_curr.hostname)



                    is_ats = self.is_official_employer_url(resolved_redirect)



                    is_emp = bool(employer and any(



                        len(token) >= 3 and token in (parsed_red.hostname or "").lower()



                        for token in re.findall(r"[a-z0-9]+", employer.lower())



                    ))



                    # Check if redirected to root / homepage



                    red_path = parsed_red.path or ""



                    if red_path in ("", "/", "/careers", "/jobs", "/careers/"):



                        return VerificationStatus.SUSPICIOUS, "Listing redirects to employer homepage or generic portal without vacancy context."



                    if _public_http_url(resolved_redirect, resolver=self.dns_resolver) and (same_host or is_ats or is_emp):



                        curr_url = resolved_redirect



                        continue



                    else:



                        return VerificationStatus.SUSPICIOUS, "Listing redirects to external or unverified host; destination not followed."



                break







            if code in (404, 410):



                return VerificationStatus.VERIFIED_CLOSED, f"Application URL returned HTTP {code} (Not Found / Gone); vacancy is closed or removed."



            if code in (403, 429):



                return VerificationStatus.VERIFICATION_ERROR, f"Automated access blocked or rate limited (HTTP {code}); manual review required, vacancy not assumed closed."



            if code != 200:



                return VerificationStatus.VERIFICATION_ERROR, f"Unexpected HTTP status {code}; automated verification inconclusive, vacancy not assumed closed."







            body = resp.text[:2_000_000].lower()



            if any(re.search(p, body) for p in CAPTCHA_PATTERNS):



                return VerificationStatus.VERIFICATION_ERROR, "Page presents a security challenge; manual review required, vacancy not assumed closed."



            if any(re.search(p, body) for p in CLOSURE_PATTERNS):



                return VerificationStatus.VERIFIED_CLOSED, "Page contains explicit vacancy closure text (job closed or removed)."



            if is_aggregator:



                return VerificationStatus.PENDING_VERIFICATION, "Third-party discovery page; reachability confirmed (HTTP 200), but a confirmed employer or authorized ATS URL is required."



            if not official:



                return VerificationStatus.PENDING_VERIFICATION, "Page is accessible (HTTP 200), but employer domain or authorized ATS tenancy could not be confirmed."



            has_apply = any(re.search(p, body) for p in OPEN_INDICATORS)



            if has_apply:



                return VerificationStatus.VERIFIED_OPEN, "Authorized ATS page is accessible and contains an application action; vacancy content should still be reviewed."



            return VerificationStatus.PENDING_VERIFICATION, "Authorized ATS page is accessible, but no application action or closure evidence was found; manual review recommended."



        except requests.exceptions.Timeout:



            return VerificationStatus.VERIFICATION_ERROR, "Automated check timed out; manual review required, vacancy not assumed closed."



        except requests.exceptions.SSLError:



            return VerificationStatus.BROKEN_LINK, "TLS certificate validation failed; connection cannot be secured, link is broken."



        except requests.exceptions.ConnectionError as exc:



            return VerificationStatus.BROKEN_LINK, f"Connection failed ({type(exc).__name__}); server unreachable or DNS resolution failed."



        except requests.exceptions.RequestException as exc:



            return VerificationStatus.VERIFICATION_ERROR, f"Request failed: {type(exc).__name__}; automated verification inconclusive, vacancy not assumed closed."



        except Exception as exc:



            return VerificationStatus.VERIFICATION_ERROR, f"Unexpected error ({type(exc).__name__}): {exc}; automated verification inconclusive, vacancy not assumed closed."











JobVerifier = VerificationEngine











def detect_stale_listings(days_since_verified: int = 14, days_since_posted: int = 30) -> list[dict[str, Any]]:



    """Detect active job listings that are overdue for verification or have aged past freshness limits."""



    from datetime import datetime, timezone, timedelta



    from careerorbit.database.db import get_connection







    now_utc = datetime.now(timezone.utc)



    verified_cutoff = (now_utc - timedelta(days=days_since_verified)).isoformat()



    posting_cutoff = (now_utc - timedelta(days=days_since_posted)).isoformat()







    conn = get_connection()



    cursor = conn.cursor()



    cursor.execute("""



        SELECT id, employer, title, official_url, official_listing_url, application_url,



               verification_status, posting_date, first_discovered_at, last_verified_at



        FROM jobs



        WHERE COALESCE(record_state, 'DISCOVERY_LEAD') != 'QUARANTINED'



          AND (



            verification_status != 'VERIFIED_CLOSED'



          )



          AND (



            last_verified_at IS NULL



            OR last_verified_at <= ?



            OR (posting_date IS NOT NULL AND posting_date != '' AND posting_date <= ?)



          )



        ORDER BY last_verified_at ASC NULLS FIRST



    """, (verified_cutoff, posting_cutoff))







    rows = cursor.fetchall()



    stale = []



    for r in rows:



        reasons = []



        if not r["last_verified_at"]:



            reasons.append("NEVER_VERIFIED")



        elif r["last_verified_at"] <= verified_cutoff:



            reasons.append("VERIFICATION_STALE")



        if r["posting_date"] and r["posting_date"] <= posting_cutoff:



            reasons.append("POSTING_AGE_STALE")







        stale.append({



            "id": r["id"],



            "employer": r["employer"],



            "title": r["title"],



            "verification_status": r["verification_status"],



            "last_verified_at": r["last_verified_at"],



            "posting_date": r["posting_date"],



            "stale_reasons": reasons,



        })



    conn.close()



    return stale











def recheck_active_leads(max_jobs: int = 15, days_threshold: int = 7) -> Dict[str, Any]:



    """Safely rechecks older active leads against official employer/ATS pages.



    Respects rate limits, uses bounded timeouts, preserves historical records,



    and updates verification status without crashing or losing data.



    """



    from datetime import datetime, timezone, timedelta



    from careerorbit.database.db import get_connection







    verifier = JobVerifier(timeout_seconds=8)



    conn = get_connection()



    cursor = conn.cursor()







    now_utc = datetime.now(timezone.utc)



    cutoff = (now_utc - timedelta(days=days_threshold)).isoformat()







    cursor.execute("""



        SELECT id, employer, title, official_url, official_listing_url, application_url, verification_status, last_verified_at



        FROM jobs



        WHERE COALESCE(record_state, 'DISCOVERY_LEAD') != 'QUARANTINED'



          AND (



            (official_listing_url IS NOT NULL AND official_listing_url != '')



            OR (official_url IS NOT NULL AND official_url != '')



            OR (application_url IS NOT NULL AND application_url != '')



          )



          AND (



            verification_status IN ('PENDING_VERIFICATION', 'UNVERIFIED', 'VERIFICATION_ERROR', 'STATUS_UNKNOWN', 'BROKEN_LINK', 'SUSPICIOUS')



            OR last_verified_at IS NULL



            OR last_verified_at <= ?



          )



        ORDER BY 



            CASE WHEN verification_status IN ('PENDING_VERIFICATION', 'UNVERIFIED', 'VERIFICATION_ERROR', 'STATUS_UNKNOWN', 'BROKEN_LINK', 'SUSPICIOUS') THEN 0 ELSE 1 END,



            last_verified_at ASC NULLS FIRST



        LIMIT ?



    """, (cutoff, max_jobs))







    rows = cursor.fetchall()



    results = {



        "checked": len(rows),



        "verified_open": 0,



        "verified_closed": 0,



        "pending_verification": 0,



        "broken_link": 0,



        "suspicious": 0,



        "verification_error": 0,



        "unverified": 0,



        "status_unknown": 0,



        "details": []



    }







    for row in rows:



        job_id = row["id"]



        employer = row["employer"] or ""



        target_url = row["official_listing_url"] or row["official_url"] or row["application_url"]







        status, evidence = verifier.verify_listing(target_url, employer=employer)



        status_str = status.value if hasattr(status, "value") else str(status)







        new_status = status_str



        if new_status == "VERIFIED_OPEN":



            results["verified_open"] += 1



        elif new_status == "VERIFIED_CLOSED":



            results["verified_closed"] += 1



        elif new_status in ("PENDING_VERIFICATION", "UNVERIFIED"):



            results["pending_verification"] += 1



            results["unverified"] += 1



        elif new_status == "BROKEN_LINK":



            results["broken_link"] += 1



        elif new_status == "SUSPICIOUS":



            results["suspicious"] += 1



        else:



            results["verification_error"] += 1



            results["status_unknown"] += 1







        cursor.execute("""



            UPDATE jobs



            SET verification_status = ?,



                last_verified_at = ?,



                verification_source = ?,



                verification_notes = ?



            WHERE id = ?



        """, (



            new_status,



            now_utc.isoformat(),



            "Weekly Link Verification",



            evidence,



            job_id



        ))







        # Preserve applications and record audit history if job closes



        if new_status == "VERIFIED_CLOSED":



            cursor.execute("SELECT id, application_status FROM applications WHERE job_id = ?", (job_id,))



            app_rows = cursor.fetchall()



            for app_r in app_rows:



                now_str = datetime.now(timezone.utc).isoformat()



                cursor.execute("""



                    INSERT INTO application_history (



                        application_id, previous_status, new_status, timestamp,



                        event_source, actor, notes, evidence



                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)



                """, (



                    app_r["id"],



                    app_r["application_status"],



                    app_r["application_status"],



                    now_str,



                    "JOB_VERIFIER",



                    "SYSTEM_VERIFIER",



                    "Underlying vacancy was confirmed closed or removed from source.",



                    evidence



                ))







        conn.commit()







        results["details"].append({



            "job_id": job_id,



            "employer": employer,



            "url": target_url,



            "status": new_status,



            "evidence": evidence



        })







    conn.close()



    return results



