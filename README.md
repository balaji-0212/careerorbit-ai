# CareerOrbit AI

CareerOrbit AI is a local, privacy-first, India-first career intelligence, automated job-search, and application-preparation platform built with FastAPI, SQLite 3, and vanilla HTML5/CSS/JavaScript.

It continuously searches public listing APIs (Jobicy, Remotive, Arbeitnow), plus configured official employer ATS boards (Greenhouse and Lever public endpoints), strictly enforces candidate privacy and explicit human approval, ingests community job alerts via Telegram and WhatsApp, and automates daily morning discovery via native Windows Task Scheduler.

---

## 1. Candidate Profile & Privacy

- **Candidate:** Profile details are stored in the local, ignored data directory and are not embedded in source or release archives.
- **Candidate Evidence Governance:** Field-level provenance is tracked in `data/candidate_evidence.json`, overrides in `data/candidate_profile_overrides.json`, and an immutable log in `data/candidate_profile_history.jsonl`.
- **Zero Invented Data Guarantee:** The platform never invents metrics, employers, project results, certifications, or employment history. Learning goals are treated strictly as learning targets, not demonstrated skills.
- **Contact Privacy Withholding:** Personal phone numbers and email addresses are filtered out of public dashboard endpoints (`GET /api/profile`, `GET /api/stats`).
- **Human Approval Barrier:** The platform never automatically submits applications or sends messages. Transitioning an application to `SUBMITTED` strictly requires explicit user confirmation via `POST /api/applications/confirm-submission/{job_id}`.

---

## 2. India-First Geographic Architecture

Geography influences job ranking independently from career category via a strict 3-tier hierarchy:

- **Geographic Priority 1 (Highest, 10.0 pts):** South India Primary Technology Metros (Bengaluru, Chennai, Coimbatore, Hyderabad) and confirmed India-permitted Remote roles (Worldwide, Anywhere, or explicitly stating India).
- **Geographic Priority 2 (8.5–9.0 pts):** South India Regional & Home Hubs (Cuddalore, Puducherry/Pondicherry, Kochi, Mysuru, Madurai, Salem, Trichy, and South Indian states).
- **Geographic Priority 3 (7.0 pts):** Other Indian Technology and Business Hubs (Pune, Mumbai, Delhi NCR, Noida, Gurugram, Ahmedabad, Kolkata, Indore, Chandigarh, and general India).
- **Hard Disqualification (Priority 4):** Non-India restricted regions (US-only, UK-only, EU-only) without verified visa sponsorship are screened out (`is_disqualified=True`).
- **Preserved Uncertainty:** Ambiguous remote listings lacking explicit India eligibility are flagged as `LOCATION_ELIGIBILITY_UNCONFIRMED` (0.0 pts) and ranked below India-eligible jobs.

---

## 3. Mandatory 6-Tier Career Priority Order

The primary sorting dimension follows the candidate's exact career priorities:

1. **Priority 1:** Data Analyst / BI Analyst / Power BI Developer / Reporting Analyst
2. **Priority 2:** Data Scientist / Junior Data Scientist / Applied Data Science
3. **Priority 3:** Software Engineer / Associate Software Engineer / Junior Python Backend
4. **Priority 4:** AI Engineer / Junior ML Engineer / Computer Vision
5. **Priority 5:** Data Engineer / Junior Data Engineer / Analytics Engineer / ETL
6. **Priority 6:** Other Relevant Early-Career Technical Roles

**Hierarchical Multi-Tier Sorting:** `Career Priority (1–6) ASC, Geographic Priority (1–3) ASC, Match Score DESC, Posting Date DESC`.

---

## 4. Security Architecture & Controls

- **Loopback CORS Allowlist:** Cross-origin access is limited to the exact local development origins (`http://127.0.0.1:8000`, `http://localhost:8000`, `http://127.0.0.1:3000`, `http://localhost:3000`); credentialed CORS and arbitrary localhost ports are disabled.
- **Defensive HTTP Headers:** Middleware injects `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, and `X-XSS-Protection: 1; mode=block`.
- **SSRF Defense:** URL verification checks resolve hostnames and block private, loopback, and cloud metadata IP ranges (`127.0.0.1`, `10.x.x.x`, `169.254.x.x`).
- **Path Traversal Defense:** Resume downloads validate file paths strictly against `SETTINGS.RESUMES_DIR` and reject directory traversal attempts (`403 Forbidden`).
- **Credential Protection:** All tokens and API keys are stored in private `.env` and masked in all UI views, logs, and API payloads (`8963...HH3M`).
- **CSV Formula Injection Defense:** Neutralizes spreadsheet formula prefixes (`=`, `+`, `-`, `@`) in application and job CSV exports.

---

## 5. Quickstart & Operating Instructions

### Start the Dashboard Server
```powershell
cd "D:\Job Search"
.\.venv\Scripts\Activate.ps1
python run.py --port 8000
```
Open **[http://127.0.0.1:8000](http://127.0.0.1:8000)** in your browser.

### Run Automated Tests (136/136 Passing)
```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

### Run Live Integration Verification
```powershell
.\.venv\Scripts\python.exe scripts/test_served_app.py
```

### Run Job Discovery Manually
```powershell
.\.venv\Scripts\python.exe run.py --job-discovery
```

### Print Daily Intelligence Summary
```powershell
.\.venv\Scripts\python.exe run.py --daily-report
```

### Generate Technical Study Plan (On-Demand)
```powershell
.\.venv\Scripts\python.exe run.py --study-plan
```

### Recheck Active Job Listing Links
```powershell
.\.venv\Scripts\python.exe run.py --recheck-links
```

### Register Daily Windows Scheduled Task
```powershell
# Safe Dry-Run (preview configuration and timezone trigger computation without changes):
powershell.exe -ExecutionPolicy Bypass -File setup_windows_scheduler.ps1 -DryRun

# Register or cleanly reinstall the canonical Windows Scheduled Task:
powershell.exe -ExecutionPolicy Bypass -File setup_windows_scheduler.ps1 -Force
```

---

## 6. Daily Windows Scheduled Automation

Background tasks run via native Windows Task Scheduler targeting strictly **08:00 AM Asia/Kolkata** (IST, UTC+05:30):

1. **`CareerOrbit_Daily_Job_Search`:** Runs `run.py --job-discovery` daily at **08:00 AM IST**.
   - **Timezone Awareness:** The installer automatically detects host machine timezone and computes an offset-adjusted local trigger (e.g., `08:00` for IST, `02:30` for UTC, `21:30` previous evening for US Eastern) to ensure daily discovery always executes at 08:00 AM India time.
   - **Kernel Concurrency Locking:** Cross-process atomic byte-range locks (`workflow.lock` and `workflow.lock.json`) prevent overlapping executions between scheduled tasks, CLI commands, and the web server. Abandoned locks from crashed processes are automatically reclaimed.
   - **Missed-Run Recovery:** If the computer is asleep or off at 08:00 AM, the scheduler detects the missed run upon boot/wake, checks durable run history in `data/logs/workflow_runs.jsonl`, enforces a 16-hour recovery window (`CAREERORBIT_RECOVERY_WINDOW_HOURS`), throttles retries (`CAREERORBIT_MAX_RECOVERY_ATTEMPTS=3`), and executes recovery without creating duplicate entries.
2. **Technical Study Plan Generation (Decoupled & On-Demand):** Automated 8:00 PM study-plan generation is decoupled and disabled in daily background runs to prevent unnecessary token consumption and redundant plans. Interview study plans are triggered on-demand via the Web Dashboard or `run.py --study-plan`.

### Operational Diagnostics & Health
```powershell
# Inspect scheduler status, next run time, and timezone compatibility:
python run.py --scheduler-status

# Run 6-point comprehensive self-diagnostics:
python run.py --scheduler-diagnose
```
Real-time telemetry is also available via the REST API at `GET /api/scheduler/status` and `GET /api/health`.

---

## 7. Unified Inbox & Telegram Bot Integration

CareerOrbit AI connects directly to the official Telegram Bot API via `@CareerOrbitJobAssistantBot` to ingest community vacancies, interview questions, coding problems, and technical resources into a **Unified Inbox**.

### Setup & Credentials
1. Obtain a bot token securely from [@BotFather](https://t.me/BotFather) on Telegram.
2. Add your token to your local `.env` file:
   ```env
   TELEGRAM_BOT_TOKEN=<YOUR_TELEGRAM_BOT_TOKEN>
   TELEGRAM_POLL_INTERVAL=60
   ```
3. The platform polls for updates using persistent HTTP long-polling (`getUpdates`), requiring no public webhooks or tunnels.
4. **Token Security:** Tokens are never logged, printed, or exposed in API endpoints (only safely masked strings are returned).
5. **State Persistence:** Polling offsets, timestamps, and processed message counts survive server reboots via durable storage in SQLite `telegram_state`.
6. **Conflict Resolution:** HTTP 409 Conflict errors (caused by lingering webhooks) are automatically resolved by invoking `deleteWebhook()`.

### Supported Commands
- `/start`: Welcomes candidate/recruiter, outlines capabilities, and explains intake rules.
- `/help`: Detailed reference manual for formatting job alerts and channel permissions.
- `/profile`: Quick summary of the locally configured candidate profile and preferences.
- `/stats`: Real-time database metrics (active jobs, verified open, unverified leads, fresher drives).

### Channel & Group Permission Boundaries
- **Telegram Channels:** The bot must be added as an **Administrator** with *Post Messages* permission.
- **Telegram Groups:** Disable Privacy Mode in `@BotFather` (`/setprivacy -> Disable`) or promote the bot to Group Administrator so it can read general job postings without direct mentions.

---

## 8. WhatsApp Chat Export Ingestion

CareerOrbit features a built-in WhatsApp Chat Export parser (`WhatsAppChatExportParser`) supporting Android and iOS text export formats:
- Supports both `dd/MM/yy, hh:mm - Sender: msg` and `[dd/MM/yyyy, hh:mm:ss] Sender: msg` styles.
- Strips system notices (`"Messages and calls are end-to-end encrypted"`, `"<Media omitted>"`).
- Automatically extracts URLs, detects job vacancies, and categorizes study materials.
- All imported vacancies enter as `UNVERIFIED` community leads with full provenance (`source_type='whatsapp'`).

---

## 9. Resource Library

The Resource Library (`#tab-resources`) is a dedicated workspace for organizing learning materials, interview questions, algorithmic cheat sheets, and technical documentation:
- Accessible directly via the top navigation bar with a live item counter badge.
- Real-time search by keyword and category filtering (Interview Prep, Coding Practice & DSA, Technical Learning Materials, Certifications).
- Messages in the Unified Inbox can be promoted to the Resource Library with a single click.

---

## 10. Database Safety & Integrity

- **Database:** `data/careerorbit.db` (SQLite 3).
- **Integrity Verified:** `PRAGMA integrity_check` returns `ok`.
- **Automatic Backups:** Every migration automatically creates an online SQLite backup in `data/backups/` before modifying schema.
- **Safety Backup Verified:** `data/backups/careerorbit_master_safety_backup_20261023_175709.db` (Passed `PRAGMA integrity_check`).
- **Quarantine Isolation:** Unsupported legacy portal records and test fixtures are safely isolated under `record_state = 'QUARANTINED'` for audit compliance, keeping active discovery leads completely clean.

---

## 11. Limitations & Boundaries

- No scraping of LinkedIn, Naukri, or Indeed in violation of platform terms of service.
- All resume and application materials (PDF, DOCX, cover letters, answers) are drafts for candidate review. External submissions strictly require explicit user action.
- Employer ATS boards (Greenhouse, Lever) require configured company tokens in `data/employer_sources.json` or `.env`.
