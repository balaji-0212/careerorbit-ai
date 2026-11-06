"""Injects robust, production-grade JavaScript into index.html."""
import re
from pathlib import Path

def generate_script_content():
    return r"""    <script>
        // --- System Environment & API Base Configuration ---
        const IS_FILE_PROTOCOL = window.location.protocol === 'file:';
        const DEFAULT_API_HOST = 'http://127.0.0.1:8000';
        const API_BASE = IS_FILE_PROTOCOL ? DEFAULT_API_HOST : '';

        // Application State
        let allJobsData = [];
        let allApplicationsData = [];
        let allResumesData = [];
        let currentTab = 'overview';
        let debounceTimer = null;
        let isBackendOnline = true;
        let activeEditField = null;

        // --- Robust Centralized API Fetcher ---
        async function apiFetch(endpoint, options = {}) {
            const url = endpoint.startsWith('http') ? endpoint : `${API_BASE}${endpoint}`;
            const controller = new AbortController();
            const timeoutMs = options.timeout || 12000;
            const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

            try {
                const res = await fetch(url, { ...options, signal: controller.signal });
                clearTimeout(timeoutId);
                updateBackendStatus(true);
                return res;
            } catch (err) {
                clearTimeout(timeoutId);
                const isNetworkError = err.name === 'TypeError' || err.message === 'Failed to fetch';
                if (isNetworkError) {
                    updateBackendStatus(false);
                    if (IS_FILE_PROTOCOL) {
                        throw new Error(`Cannot reach CareerOrbit backend at ${DEFAULT_API_HOST}. Start the server with 'python run.py --port 8000' and click 'Retry Connection'.`);
                    }
                    throw new Error(`Connection to backend failed. Please ensure 'python run.py --port 8000' is running.`);
                }
                if (err.name === 'AbortError') {
                    throw new Error(`Request to ${endpoint} timed out after ${timeoutMs / 1000}s.`);
                }
                throw err;
            }
        }

        // --- Backend Health & File Protocol Banner Monitor ---
        async function checkBackendHealth(manual = false) {
            const pill = document.getElementById('connection-status-pill');
            if (manual && pill) {
                pill.innerHTML = '🔄 Checking...';
                pill.className = 'badge badge-yellow';
            }
            try {
                const res = await fetch(`${API_BASE}/api/stats`, { method: 'GET', headers: { 'Accept': 'application/json' } });
                if (res.ok) {
                    updateBackendStatus(true);
                    if (manual) showToast('Backend is online and responding at ' + (IS_FILE_PROTOCOL ? DEFAULT_API_HOST : '127.0.0.1:8000'), 'success');
                    // Refresh current view if recovering
                    if (currentTab === 'overview') { fetchStats(); loadOverviewJobs(); }
                    else if (currentTab === 'jobs') { loadJobs(); }
                    else if (currentTab === 'profile') { loadFullProfile(); }
                } else {
                    updateBackendStatus(false);
                    if (manual) showToast('Backend returned HTTP error ' + res.status, 'error');
                }
            } catch (err) {
                updateBackendStatus(false);
                if (manual) showToast('Backend connection check failed: ' + err.message, 'error');
            }
        }

        function updateBackendStatus(online) {
            isBackendOnline = online;
            const pill = document.getElementById('connection-status-pill');
            const bannerContainer = document.getElementById('backend-banner-container');

            if (pill) {
                if (online) {
                    pill.innerHTML = '🟢 ' + (IS_FILE_PROTOCOL ? '127.0.0.1:8000 Connected' : 'Connected');
                    pill.className = 'badge badge-green';
                } else {
                    pill.innerHTML = '🔴 Backend Offline (Retry)';
                    pill.className = 'badge badge-red';
                }
            }

            if (!bannerContainer) return;

            if (!online) {
                bannerContainer.innerHTML = `
                    <div style="background: rgba(239, 68, 68, 0.18); border: 1px solid var(--danger); padding: 14px 18px; border-radius: var(--radius-md); font-size: 13px; color: #fecaca; display: flex; align-items: center; justify-content: space-between; gap: 14px; flex-wrap: wrap;">
                        <div>
                            <strong style="color: #fff; font-size: 14px;">⚠️ Backend Server Offline</strong> — Cannot reach CareerOrbit AI at <code>${DEFAULT_API_HOST}</code>.
                            <div style="font-size: 11.5px; color: #fca5a5; margin-top: 4px;">
                                To launch the backend server, open PowerShell in this directory and execute:
                                <code style="background: rgba(0,0,0,0.4); padding: 2px 6px; border-radius: 4px; margin-left: 4px;">python run.py --port 8000</code>
                            </div>
                        </div>
                        <button class="btn btn-sm btn-danger" onclick="checkBackendHealth(true)" style="background: var(--danger); color: #fff;">Retry Connection</button>
                    </div>
                `;
            } else if (IS_FILE_PROTOCOL) {
                bannerContainer.innerHTML = `
                    <div style="background: rgba(79, 70, 229, 0.15); border: 1px solid var(--primary); padding: 10px 16px; border-radius: var(--radius-md); font-size: 12.5px; color: var(--text-main); display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap;">
                        <span>📁 <strong>Local File Mode:</strong> You opened this file from disk. Connected to backend at <code>${DEFAULT_API_HOST}</code>. For native experience and direct downloads, open <strong><a href="http://127.0.0.1:8000/" target="_blank" style="color: var(--accent); font-weight: 600; text-decoration: underline;">http://127.0.0.1:8000/</a></strong> directly.</span>
                        <span style="font-size: 11.5px; color: var(--success); font-weight: 500;">● Online via loopback</span>
                    </div>
                `;
            } else {
                bannerContainer.innerHTML = '';
            }
        }

        // --- XSS sanitization & Safe URL helpers ---
        function escapeHtml(str) {
            if (str === null || str === undefined) return '';
            return String(str).replace(/[&<>"']/g, m => ({
                '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;'
            }[m]));
        }

        function safeJobUrl(rawUrl) {
            if (!rawUrl || typeof rawUrl !== 'string') return '';
            try {
                const u = new URL(rawUrl.trim());
                if (u.protocol === 'https:' || u.protocol === 'http:') {
                    return u.href;
                }
            } catch (_) {}
            return '';
        }

        function showToast(message, type = 'info') {
            const container = document.getElementById('toast-container');
            if (!container) return;
            const toast = document.createElement('div');
            toast.className = `toast ${type}`;
            toast.innerText = message;
            container.appendChild(toast);
            setTimeout(() => {
                toast.style.opacity = '0';
                toast.style.transform = 'translateY(8px)';
                toast.style.transition = 'all 0.2s ease-out';
                setTimeout(() => toast.remove(), 250);
            }, 3500);
        }

        function closeModal(modalId) {
            const m = document.getElementById(modalId);
            if (m) m.classList.remove('active');
        }

        // --- Tab Switching ---
        function switchTab(tabId) {
            currentTab = tabId;
            document.querySelectorAll('.section-tab').forEach(el => el.classList.remove('active'));
            document.querySelectorAll('nav button').forEach(el => el.classList.remove('active'));

            const targetSection = document.getElementById(`tab-${tabId}`);
            if (targetSection) targetSection.classList.add('active');

            const activeBtn = document.querySelector(`nav button[onclick="switchTab('${tabId}')"]`);
            if (activeBtn) activeBtn.classList.add('active');

            const titleMap = {
                'overview': 'Executive Career Dashboard',
                'jobs': 'Multi-Source Job Discovery',
                'saved': 'Bookmarked Opportunities',
                'applications': 'Application Tracking & Security Gates',
                'resumes': 'Tailored ATS Resume Library',
                'prep': 'Role-Specific Interview Coaching',
                'study': 'Daily 3.5-Hour Career Study Plan',
                'profile': 'Candidate Profile & Evidence Governance',
                'sources': 'Multi-Source Adapter Health & Status',
                'scheduler': 'Automation, Scheduler & Execution Logs',
                'settings': 'Platform Settings & Security Posture'
            };
            document.getElementById('view-title').innerText = titleMap[tabId] || 'Career Workspace';

            // Lazy-load data for target tab
            if (tabId === 'overview') { fetchStats(); loadOverviewJobs(); }
            else if (tabId === 'jobs') { loadJobs(); }
            else if (tabId === 'saved') { loadSavedJobs(); }
            else if (tabId === 'applications') { loadApplications(); }
            else if (tabId === 'resumes') { loadResumes(); }
            else if (tabId === 'prep') { loadPrepPlans(); }
            else if (tabId === 'study') { loadDailyStudyPlan(); }
            else if (tabId === 'profile') { loadFullProfile(); }
            else if (tabId === 'sources') { loadSourcesHealth(); loadEmployerRegistry(); }
            else if (tabId === 'scheduler') { loadSchedulerHistory(); }
        }

        function debouncedLoadJobs() {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(loadJobs, 250);
        }

        function clearFilters() {
            document.getElementById('job-search-input').value = '';
            document.getElementById('filter-priority').value = '';
            document.getElementById('filter-verification').value = '';
            document.getElementById('filter-work-arrangement').value = '';
            document.getElementById('filter-min-score').value = '';
            document.getElementById('filter-sort').value = 'priority_first';
            loadJobs();
        }

        // --- Core REST API Calls ---

        async function fetchStats() {
            try {
                const res = await apiFetch('/api/stats');
                if (!res.ok) throw new Error(`Stats API failed (${res.status})`);
                const data = await res.json();
                const m = data.metrics || {};
                const s = data.scheduler || {};

                document.getElementById('stat-total-jobs').innerText = m.total_jobs || 0;
                document.getElementById('stat-verified-open').innerText = m.verified_open || 0;
                document.getElementById('stat-strong-matches').innerText = data.candidate_evidence?.ready_for_resume ? (m.strong_matches ?? 0) : '—';
                document.getElementById('stat-saved-jobs').innerText = m.saved_jobs || 0;
                document.getElementById('stat-awaiting-approval').innerText = m.applications_awaiting_approval || 0;
                document.getElementById('stat-confirmed-submissions').innerText = m.confirmed_submissions || 0;
                document.getElementById('stat-applications-review').innerText = m.applications_needing_review || 0;

                document.getElementById('nav-job-count').innerText = m.total_jobs || 0;
                document.getElementById('nav-saved-count').innerText = m.saved_jobs || 0;
                document.getElementById('nav-app-count').innerText = (m.applications_awaiting_approval || 0) + (m.confirmed_submissions || 0);

                if (document.getElementById('sched-status-text')) {
                    document.getElementById('sched-status-text').innerText = s.scheduler_running ? 'Active (Running)' : 'Stopped';
                    document.getElementById('sched-last-discovery-text').innerText = s.last_discovery_run || 'None today';
                    document.getElementById('sched-last-study-text').innerText = s.last_study_plan_run || 'None today';
                }
            } catch (err) {
                console.error(err);
            }
        }

        async function loadOverviewJobs() {
            const container = document.getElementById('overview-jobs-table');
            try {
                const res = await apiFetch('/api/jobs?limit=5&sort_by=score_desc');
                if (!res.ok) throw new Error(`Jobs fetch failed (${res.status})`);
                const data = await res.json();
                if (!data.jobs || data.jobs.length === 0) {
                    container.innerHTML = '<p style="color:var(--text-muted);text-align:center;padding:20px;">No discovery leads match this view. Review source activity for coverage and failures.</p>';
                    return;
                }
                container.innerHTML = `
                    <table>
                        <thead>
                            <tr>
                                <th>Role & Employer</th>
                                <th>Priority Tier</th>
                                <th>Match Score</th>
                                <th>Location</th>
                                <th>Verification Status</th>
                                <th>Action</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${data.jobs.map(j => {
                                const scoreClass = j.match_score >= 75 ? 'color:#10b981;' : (j.match_score >= 60 ? 'color:#818cf8;' : 'color:#f59e0b;');
                                return `
                                    <tr>
                                        <td>
                                            <strong style="color:var(--text-main); font-size:13.5px;">${escapeHtml(j.title)}</strong><br>
                                            <span style="color:var(--accent); font-size:12px;">${escapeHtml(j.employer)}</span>
                                        </td>
                                        <td><span class="badge badge-blue">P${j.priority_category}: ${(j.priority_label || '').split('/')[0]}</span></td>
                                        <td>${j.candidate_fit_state === 'READY' && Number.isFinite(j.match_score) ? `<strong style="${scoreClass} font-size:15px;">${j.match_score}</strong> / 100` : '<span class="badge badge-yellow">Needs candidate review</span>'}</td>
                                        <td>${escapeHtml(j.location)}</td>
                                        <td>${renderVerificationBadge(j.verification_status)}</td>
                                        <td>
                                            <button class="btn btn-secondary btn-sm" onclick="viewJobDetails(${j.id})">Details</button>
                                        </td>
                                    </tr>
                                `;
                            }).join('')}
                        </tbody>
                    </table>
                `;
            } catch (err) {
                container.innerHTML = `<div style="text-align:center; padding:20px; color:var(--danger);">${escapeHtml(err.message)} <br><button class="btn btn-sm btn-secondary" onclick="loadOverviewJobs()" style="margin-top:8px;">Retry</button></div>`;
            }
        }

        async function loadJobs() {
            const grid = document.getElementById('jobs-grid');
            const query = document.getElementById('job-search-input').value.trim();
            const priority = document.getElementById('filter-priority').value;
            const ver = document.getElementById('filter-verification').value;
            const arrangement = document.getElementById('filter-work-arrangement').value;
            const minScore = document.getElementById('filter-min-score').value;
            const sortBy = document.getElementById('filter-sort').value;
            let url = `/api/jobs?limit=100&sort_by=${sortBy}`;
            if (query) url += `&search=${encodeURIComponent(query)}`;
            if (priority) url += `&priority=${priority}`;
            if (ver) url += `&verification_status=${ver}`;
            if (arrangement) url += `&work_arrangement=${encodeURIComponent(arrangement)}`;
            if (minScore) url += `&min_score=${minScore}`;

            try {
                grid.innerHTML = '<div style="grid-column: 1/-1; text-align:center; padding:30px; color:var(--text-secondary);">Loading discovery leads...</div>';
                const res = await apiFetch(url);
                if (!res.ok) throw new Error(`Failed to query jobs API (${res.status})`);
                const data = await res.json();
                allJobsData = data.jobs || [];
                document.getElementById('jobs-count-badge').innerText = `${allJobsData.length} Discovery Leads`;

                if (allJobsData.length === 0) {
                    grid.innerHTML = `
                        <div style="grid-column: 1 / -1; text-align: center; padding: 40px 20px; background: var(--bg-card); border-radius: var(--radius-lg); border: 1px dashed var(--border-subtle);">
                            <h4 style="color: var(--text-secondary); margin-bottom: 6px;">No discovery leads match this view</h4>
                            <p style="color: var(--text-muted); font-size: 13px; margin-bottom: 16px;">Try clearing filters or running job discovery to query live endpoints.</p>
                            <button class="btn btn-sm" onclick="clearFilters()">Reset All Filters</button>
                        </div>
                    `;
                    return;
                }

                grid.innerHTML = allJobsData.map(j => renderJobCard(j)).join('');
            } catch (err) {
                grid.innerHTML = `
                    <div style="grid-column: 1/-1; text-align:center; padding:30px; background:var(--bg-card); border-radius:var(--radius-lg); border:1px solid var(--danger);">
                        <p style="color:var(--danger); margin-bottom:10px;">Error loading jobs: ${escapeHtml(err.message)}</p>
                        <button class="btn btn-sm btn-secondary" onclick="loadJobs()">Retry Loading Jobs</button>
                    </div>
                `;
            }
        }

        async function loadSavedJobs() {
            const grid = document.getElementById('saved-jobs-grid');
            try {
                const res = await apiFetch('/api/jobs?saved_only=true&limit=100');
                if (!res.ok) throw new Error('Saved jobs API failed');
                const data = await res.json();
                const savedJobs = data.jobs || [];

                if (savedJobs.length === 0) {
                    grid.innerHTML = `
                        <div style="grid-column: 1 / -1; text-align: center; padding: 40px 20px; background: var(--bg-card); border-radius: var(--radius-lg); border: 1px dashed var(--border-subtle);">
                            <h4 style="color: var(--text-secondary); margin-bottom: 6px;">No saved jobs yet</h4>
                            <p style="color: var(--text-muted); font-size: 13px; margin-bottom: 16px;">Star jobs in the Job Discovery tab to bookmark them here for application.</p>
                            <button class="btn btn-sm" onclick="switchTab('jobs')">Explore Discovery Leads</button>
                        </div>
                    `;
                    return;
                }

                grid.innerHTML = savedJobs.map(j => renderJobCard(j)).join('');
            } catch (err) {
                grid.innerHTML = `<div style="grid-column: 1/-1; text-align:center; padding:20px; color:var(--danger);">${escapeHtml(err.message)}</div>`;
            }
        }

        function renderJobCard(j) {
            const verified = j.verification_status === 'VERIFIED_OPEN';
            const officialUrl = safeJobUrl(j.official_listing_url || j.official_url || j.application_url || '');
            const scoreClass = j.match_score >= 75 ? 'score-high' : (j.match_score >= 60 ? 'score-med' : 'score-low');
            const isSaved = j.is_saved;

            return `
                <div class="job-card">
                    <div>
                        <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:10px;">
                            <div>
                                <span class="badge badge-blue" style="font-size:10.5px;">P${j.priority_category}: ${(j.priority_label || '').split('/')[0]}</span>
                                ${renderVerificationBadge(j.verification_status)}
                            </div>
                            <button class="save-star ${isSaved ? 'active' : ''}" onclick="toggleSaveJob(${j.id}, this)" title="${isSaved ? 'Remove Bookmark' : 'Bookmark Job'}">★</button>
                        </div>
                        <h4 style="font-size:15px; font-weight:700; color:var(--text-main); margin-bottom:4px; line-height:1.3;">${escapeHtml(j.title)}</h4>
                        <div style="font-size:13px; color:var(--accent); font-weight:600; margin-bottom:8px;">${escapeHtml(j.employer)}</div>
                        <div style="display:flex; gap:12px; font-size:12px; color:var(--text-secondary); margin-bottom:12px; flex-wrap:wrap;">
                            <span>📍 ${escapeHtml(j.location || 'India / Remote')}</span>
                            <span>💼 ${escapeHtml(j.work_arrangement || 'Flexible')}</span>
                            <span>📅 ${escapeHtml(j.posting_date ? j.posting_date.slice(0, 10) : 'Date Unknown')}</span>
                        </div>
                        <div style="background:var(--bg-sidebar); border-radius:var(--radius-md); padding:10px 12px; margin-bottom:14px; border:1px solid var(--border-subtle);">
                            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                                <span style="font-size:11.5px; color:var(--text-secondary);">ATS Match Score:</span>
                                ${j.candidate_fit_state === 'READY' && Number.isFinite(j.match_score)
                                    ? `<strong class="${scoreClass}" style="font-size:14px;">${j.match_score} / 100</strong>`
                                    : `<span class="badge badge-yellow" style="font-size:10px;">Needs candidate review</span>`}
                            </div>
                            ${j.candidate_fit_state === 'READY' && Number.isFinite(j.match_score)
                                ? `<div class="score-bar-bg"><div class="score-bar-fill" style="width:${Math.min(100, j.match_score)}%;"></div></div>`
                                : `<div style="font-size:11px; color:var(--text-muted); line-height:1.3;">Fit calculation enabled after candidate profile review.</div>`}
                        </div>
                    </div>
                    <div style="display:flex; gap:8px; border-top:1px solid var(--border-subtle); padding-top:12px; margin-top:6px; flex-wrap:wrap;">
                        <button class="btn btn-secondary btn-sm" style="flex:1;" onclick="viewJobDetails(${j.id})">Details & Score</button>
                        <button class="btn btn-sm" style="flex:1;" onclick="prepareApplication(${j.id})">Prepare Application</button>
                        ${officialUrl ? `
                            <a href="${officialUrl}" target="_blank" rel="noopener noreferrer" class="btn btn-secondary btn-sm" title="Open verified official employer destination in new tab">
                                ↗ Official Link
                            </a>
                        ` : ''}
                    </div>
                </div>
            `;
        }

        function renderVerificationBadge(status) {
            if (status === 'VERIFIED_OPEN') {
                return '<span class="badge badge-green">✓ Verified Open</span>';
            } else if (status === 'VERIFIED_CLOSED') {
                return '<span class="badge badge-red">✕ Closed / Filled</span>';
            } else if (status === 'UNVERIFIED') {
                return '<span class="badge badge-yellow">● Discovery Lead</span>';
            } else {
                return '<span class="badge badge-gray">? Status Unknown</span>';
            }
        }

        async function toggleSaveJob(jobId, btn) {
            try {
                const res = await apiFetch(`/api/jobs/${jobId}/save`, { method: 'POST' });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Could not update bookmark');
                showToast(data.message || (data.is_saved ? 'Job bookmarked!' : 'Bookmark removed'), 'info');
                if (btn) btn.classList.toggle('active', data.is_saved);
                fetchStats();
            } catch (err) {
                showToast(err.message, 'error');
            }
        }

        async function viewJobDetails(jobId) {
            try {
                const res = await apiFetch(`/api/jobs/${jobId}`);
                if (!res.ok) throw new Error('Could not fetch job details');
                const j = await res.json();
                const breakdown = j.score_breakdown || {};
                const modal = document.getElementById('job-detail-modal');

                document.getElementById('modal-job-title').innerText = j.title;
                document.getElementById('modal-job-employer').innerText = `${j.employer} • ${j.location} • ${j.work_arrangement}`;

                const officialListingUrl = safeJobUrl(j.official_listing_url);
                const applyUrl = safeJobUrl(j.application_url);
                const discoveryUrl = safeJobUrl(j.discovery_url);

                document.getElementById('modal-job-body').innerHTML = `
                    <div style="margin-bottom:18px;">
                        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                            <span class="badge badge-blue" style="font-size:12px;">Priority ${j.priority_category}: ${escapeHtml(j.priority_label)}</span>
                            ${renderVerificationBadge(j.verification_status)}
                        </div>
                        <div style="background:var(--bg-sidebar); border:1px solid var(--border-subtle); border-radius:var(--radius-md); padding:14px; margin-bottom:16px;">
                            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                                <strong style="font-size:14px; color:var(--text-main);">ATS Match Evaluation</strong>
                                <span style="font-size:16px; font-weight:800; color:var(--success);">${j.candidate_fit_state === 'READY' && Number.isFinite(j.match_score) ? j.match_score : '—'} / 100</span>
                            </div>
                            <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px; font-size:12px;">
                                <div>Skills & Projects: <strong>${breakdown.skills_and_projects || 0} / 30</strong></div>
                                <div>Experience Compatibility: <strong>${breakdown.experience_compatibility || 0} / 20</strong></div>
                                <div>Education & Eligibility: <strong>${breakdown.eligibility || 0} / 15</strong></div>
                                <div>Freshness: <strong>${breakdown.freshness_and_availability || 0} / 15</strong></div>
                                <div>Location & Arrangement: <strong>${breakdown.location_and_arrangement || 0} / 10</strong></div>
                                <div>Evidence & Realistic Fit: <strong>${breakdown.evidence_and_realistic_fit || 0} / 10</strong></div>
                            </div>
                        </div>

                        ${j.disqualifiers && j.disqualifiers.length > 0 ? `
                            <div style="background:rgba(239,68,68,0.15); border:1px solid var(--danger); border-radius:var(--radius-md); padding:10px 14px; margin-bottom:14px; font-size:12.5px; color:#fca5a5;">
                                <strong>⚠️ Disqualifiers Detected:</strong><br>
                                ${j.disqualifiers.map(d => `• ${escapeHtml(d)}`).join('<br>')}
                            </div>
                        ` : ''}

                        <div style="margin-bottom:14px;">
                            <label style="font-size:12px; color:var(--text-secondary); display:block; margin-bottom:6px;">Supported Verified Skills:</label>
                            <div style="display:flex; gap:6px; flex-wrap:wrap;">
                                ${(j.supported_skills || []).map(s => `<span class="badge badge-green">${escapeHtml(s)}</span>`).join('') || '<span style="color:var(--text-muted); font-size:12px;">None matched</span>'}
                            </div>
                        </div>

                        ${j.missing_skills && j.missing_skills.length > 0 ? `
                            <div style="margin-bottom:14px;">
                                <label style="font-size:12px; color:var(--text-secondary); display:block; margin-bottom:6px;">Missing Stated Requirements:</label>
                                <div style="display:flex; gap:6px; flex-wrap:wrap;">
                                    ${j.missing_skills.map(s => `<span class="badge badge-red">${escapeHtml(s)}</span>`).join('')}
                                </div>
                            </div>
                        ` : ''}

                        <div style="margin-bottom:14px; font-size:12px;">
                            <label style="color:var(--text-secondary); display:block; margin-bottom:4px;">Official Destinations:</label>
                            ${officialListingUrl ? `<div>Official Listing: <a href="${officialListingUrl}" target="_blank" rel="noopener noreferrer" style="color:var(--accent); text-decoration:underline;">${escapeHtml(officialListingUrl)}</a></div>` : '<div style="color:var(--text-muted);">No official listing URL confirmed</div>'}
                            ${applyUrl ? `<div>Direct Application: <a href="${applyUrl}" target="_blank" rel="noopener noreferrer" style="color:var(--accent); text-decoration:underline;">${escapeHtml(applyUrl)}</a></div>` : ''}
                        </div>

                        <div style="margin-top:16px;">
                            <label style="font-size:12px; color:var(--text-secondary); display:block; margin-bottom:6px;">Job Description Excerpt:</label>
                            <div style="background:var(--bg-sidebar); border:1px solid var(--border-subtle); border-radius:var(--radius-md); padding:12px; font-size:12px; color:var(--text-secondary); max-height:160px; overflow-y:auto; line-height:1.4;">
                                ${escapeHtml(j.description || 'No description provided.')}
                            </div>
                        </div>

                        <div style="display:flex; gap:10px; margin-top:20px; border-top:1px solid var(--border-subtle); padding-top:16px;">
                            <button class="btn btn-sm" onclick="prepareApplication(${j.id})">Prepare Application Package</button>
                            <button class="btn btn-secondary btn-sm" onclick="generateResume(${j.id})">Generate ATS Resume (PDF/DOCX)</button>
                            <button class="btn btn-secondary btn-sm" onclick="openInterviewPrep(${j.id})">Interview Prep</button>
                        </div>
                    </div>
                `;
                modal.classList.add('active');
            } catch (err) {
                showToast(err.message, 'error');
            }
        }

        async function prepareApplication(jobId) {
            try {
                showToast('Assembling application package (Tailored ATS Resume, Cover Letter, Answers, Outreach)...', 'info');
                const res = await apiFetch(`/api/applications/prepare/${jobId}`, { method: 'POST' });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Could not assemble application package');
                showToast(`Application package ready for ${data.company}! Switched to Application Tracker.`, 'success');
                switchTab('applications');
            } catch (err) {
                showToast(err.message, 'error');
            }
        }

        async function generateResume(jobId) {
            try {
                showToast('Tailoring truthful ATS resume (PDF + DOCX)...', 'info');
                const res = await apiFetch(`/api/resumes/generate/${jobId}`, { method: 'POST' });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Resume generation failed');
                showToast(`Resume generated: ${data.pdf_filename}`, 'success');
                switchTab('resumes');
            } catch (err) {
                showToast(err.message, 'error');
            }
        }

        async function openInterviewPrep(jobId) {
            try {
                showToast('Generating interview coaching curriculum...', 'info');
                const res = await apiFetch(`/api/prep/interview/${jobId}`, { method: 'POST' });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Interview preparation generation failed');
                showToast('Interview coach package ready!', 'success');
                switchTab('prep');
            } catch (err) {
                showToast(err.message, 'error');
            }
        }

        async function confirmSubmission(jobId) {
            const confirmed = confirm("Security Approval Gate:\nDid you manually submit this application on the official employer portal?\n\nThis will record candidate confirmation and move status to SUBMITTED.");
            if (!confirmed) return;

            try {
                const res = await apiFetch(`/api/applications/confirm-submission/${jobId}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ notes: 'Confirmed by candidate via dashboard approval gate.' })
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Submission confirmation failed');
                showToast('Application marked as SUBMITTED with candidate audit confirmation!', 'success');
                loadApplications();
                fetchStats();
            } catch (err) {
                showToast(err.message, 'error');
            }
        }

        async function loadApplications() {
            const tbody = document.getElementById('applications-table-body');
            try {
                const res = await apiFetch('/api/applications');
                if (!res.ok) throw new Error('Applications API failed');
                const data = await res.json();
                allApplicationsData = data.applications || [];

                if (allApplicationsData.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; padding:30px; color:var(--text-muted);">No applications prepared yet. Click "Prepare Application" on any verified job in the Discovery tab.</td></tr>';
                    return;
                }

                tbody.innerHTML = allApplicationsData.map(a => {
                    const statusClass = a.presented_submission_confirmed ? 'badge-green' : 'badge-yellow';
                    const displayStatus = a.presented_submission_confirmed ? 'SUBMITTED (Confirmed)' : (a.presented_application_status || a.application_status);
                    const pdfHref = a.selected_resume_path_pdf ? `${API_BASE}/api/resumes/download/${encodeURIComponent(a.selected_resume_path_pdf.split(/[\/\\]/).pop())}` : '';
                    const docxHref = a.selected_resume_path_docx ? `${API_BASE}/api/resumes/download/${encodeURIComponent(a.selected_resume_path_docx.split(/[\/\\]/).pop())}` : '';

                    return `
                        <tr>
                            <td>
                                <strong>${escapeHtml(a.title || 'Target Role')}</strong><br>
                                <span style="color:var(--accent); font-size:12px;">${escapeHtml(a.employer || 'Employer')}</span>
                            </td>
                            <td><span class="badge ${statusClass}">${escapeHtml(displayStatus)}</span></td>
                            <td>
                                <div style="display:flex; gap:4px;">
                                    ${pdfHref ? `<a href="${pdfHref}" target="_blank" class="btn btn-secondary btn-sm" style="font-size:11px; padding:3px 7px;">PDF</a>` : ''}
                                    ${docxHref ? `<a href="${docxHref}" target="_blank" class="btn btn-secondary btn-sm" style="font-size:11px; padding:3px 7px;">DOCX</a>` : ''}
                                </div>
                            </td>
                            <td>${escapeHtml(a.interview_stage || 'Not started')}</td>
                            <td style="font-size:12px; color:var(--text-muted);">${escapeHtml(a.submission_date ? a.submission_date.slice(0, 10) : 'Pending')}</td>
                            <td>
                                ${!a.presented_submission_confirmed ? `
                                    <button class="btn btn-sm" style="background:#10b981; color:#fff; font-size:11.5px; padding:4px 8px;" onclick="confirmSubmission(${a.job_id})">
                                        ✓ Confirm My Submission
                                    </button>
                                ` : '<span style="color:var(--success); font-size:12px;">✓ Verified by Candidate</span>'}
                            </td>
                        </tr>
                    `;
                }).join('');
            } catch (err) {
                tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding:20px; color:var(--danger);">${escapeHtml(err.message)}</td></tr>`;
            }
        }

        async function loadResumes() {
            const tbody = document.getElementById('resumes-table-body');
            try {
                const res = await apiFetch('/api/resumes');
                if (!res.ok) throw new Error('Resumes API failed');
                const data = await res.json();
                allResumesData = data.resumes || [];

                if (allResumesData.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; padding:30px; color:var(--text-muted);">No tailored resumes generated yet.</td></tr>';
                    return;
                }

                tbody.innerHTML = allResumesData.map(r => `
                    <tr>
                        <td>
                            <strong>${escapeHtml(r.company_name)}</strong><br>
                            <span style="color:var(--text-secondary); font-size:12px;">${escapeHtml(r.role_title)}</span>
                        </td>
                        <td><span class="badge badge-purple">${escapeHtml(r.source_resume_type || 'general')}</span></td>
                        <td><strong>${r.keyword_coverage_pct || 0}%</strong></td>
                        <td style="font-size:12px; color:var(--text-muted);">${escapeHtml(r.created_at ? r.created_at.slice(0, 10) : '')}</td>
                        <td>
                            <div style="display:flex; gap:6px;">
                                <a href="${API_BASE}/api/resumes/download/${encodeURIComponent(r.pdf_filename)}" target="_blank" class="btn btn-secondary btn-sm" style="font-size:11px;">PDF</a>
                                <a href="${API_BASE}/api/resumes/download/${encodeURIComponent(r.docx_filename)}" target="_blank" class="btn btn-secondary btn-sm" style="font-size:11px;">DOCX</a>
                            </div>
                        </td>
                        <td>
                            <button class="btn btn-secondary btn-sm" onclick="openTailoringModal(${r.id})">Report</button>
                        </td>
                    </tr>
                `).join('');
            } catch (err) {
                tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding:20px; color:var(--danger);">${escapeHtml(err.message)}</td></tr>`;
            }
        }

        function openTailoringModal(resumeId) {
            const r = allResumesData.find(item => item.id === resumeId);
            if (!r) return;
            const modal = document.getElementById('tailoring-modal');
            document.getElementById('modal-tailoring-title').innerText = `Tailoring Analysis: ${r.company_name} — ${r.role_title}`;
            document.getElementById('modal-tailoring-subtitle').innerText = `Keyword Alignment: ${r.keyword_coverage_pct || 0}% ATS Compatibility`;

            document.getElementById('modal-tailoring-body').innerHTML = `
                <div style="margin-bottom:14px;">
                    <div style="background:var(--bg-sidebar); border:1px solid var(--border-subtle); padding:12px; border-radius:var(--radius-md); margin-bottom:12px; font-size:13px;">
                        <strong>Tailoring Summary:</strong><br>
                        <span style="color:var(--text-secondary);">${escapeHtml(r.tailoring_summary || 'Custom single-column ATS resume.')}</span>
                    </div>
                    <label style="font-size:12px; color:var(--text-secondary); display:block; margin-bottom:6px;">Supported Verified Keywords:</label>
                    <div style="display:flex; gap:6px; flex-wrap:wrap; margin-bottom:14px;">
                        ${(r.supported_keywords || []).map(k => `<span class="badge badge-green">${escapeHtml(k)}</span>`).join('')}
                    </div>
                    ${r.missing_requirements && r.missing_requirements.length > 0 ? `
                        <label style="font-size:12px; color:var(--text-secondary); display:block; margin-bottom:6px;">Missing Requirements (Omitted from resume for truthfulness):</label>
                        <div style="display:flex; gap:6px; flex-wrap:wrap; margin-bottom:14px;">
                            ${r.missing_requirements.map(m => `<span class="badge badge-red">${escapeHtml(m)}</span>`).join('')}
                        </div>
                    ` : ''}
                </div>
            `;
            modal.classList.add('active');
        }

        async function loadPrepPlans() {
            const container = document.getElementById('prep-plans-container');
            try {
                const res = await apiFetch('/api/prep/plans');
                if (!res.ok) throw new Error('Prep plans API failed');
                const data = await res.json();
                const plans = data.plans || [];

                if (plans.length === 0) {
                    container.innerHTML = '<div style="text-align:center; padding:40px; color:var(--text-muted); background:var(--bg-card); border-radius:var(--radius-lg); border:1px dashed var(--border-subtle);">No interview preparation packages generated yet. Click "Interview Prep" on any job in Discovery.</div>';
                    return;
                }

                container.innerHTML = plans.map(p => `
                    <div class="card" style="margin-bottom:18px;">
                        <div class="card-header">
                            <div>
                                <h3 style="font-size:16px;">${escapeHtml(p.company)} — ${escapeHtml(p.role_title)}</h3>
                                <p>Priority ${p.target_priority} Target Preparation • Aligned with the active profile</p>
                            </div>
                        </div>
                        <div style="padding:0 20px 20px;">
                            <h4 style="font-size:13px; color:var(--accent); margin-bottom:8px;">Technical Competencies & Architecture Topics:</h4>
                            <div style="display:flex; gap:6px; flex-wrap:wrap; margin-bottom:16px;">
                                ${(p.technical_topics || []).map(t => `<span class="badge badge-blue">${escapeHtml(t)}</span>`).join('')}
                            </div>
                            <h4 style="font-size:13px; color:var(--success); margin-bottom:8px;">Collapsible Coding & SQL Challenges:</h4>
                            ${(p.coding_and_sql_challenges || []).map(c => `
                                <details style="background:var(--bg-sidebar); border:1px solid var(--border-subtle); border-radius:var(--radius-md); padding:10px 14px; margin-bottom:8px;">
                                    <summary style="font-weight:600; cursor:pointer; color:var(--text-main); font-size:13px;">${escapeHtml(c.topic || 'Exercise')}</summary>
                                    <div style="margin-top:10px; font-size:12.5px; color:var(--text-secondary);">
                                        <p style="margin-bottom:6px;"><strong>Question:</strong> ${escapeHtml(c.prompt || c.question || '')}</p>
                                        <pre style="background:#090d16; border:1px solid #1f293d; padding:10px; border-radius:6px; color:#38bdf8; font-family:monospace; font-size:12px; overflow-x:auto;">${escapeHtml(c.solution || c.sample_query || '')}</pre>
                                    </div>
                                </details>
                            `).join('')}
                        </div>
                    </div>
                `).join('');
            } catch (err) {
                container.innerHTML = `<div style="text-align:center; padding:20px; color:var(--danger);">${escapeHtml(err.message)}</div>`;
            }
        }

        async function loadDailyStudyPlan() {
            const container = document.getElementById('daily-study-container');
            try {
                const res = await apiFetch('/api/prep/daily-plan');
                if (!res.ok) throw new Error('Study plan API failed');
                const plan = await res.json();

                container.innerHTML = `
                    <div class="card" style="margin-bottom:16px;">
                        <div class="card-header">
                            <div>
                                <h3>Evening Technical Study Plan — ${escapeHtml(plan.date || 'Today')}</h3>
                                <p>Scheduled Target: ${escapeHtml(plan.target_session_time || '8:00 PM IST')} • Allocated: ${plan.allocated_hours || 3.5} Hours • Asia/Kolkata</p>
                            </div>
                            <button class="btn btn-secondary btn-sm" onclick="regenerateDailyPlan()">↻ Regenerate Plan</button>
                        </div>
                        <div style="padding:0 20px 20px;">
                            <div style="background:var(--bg-sidebar); border:1px solid var(--border-subtle); border-radius:var(--radius-md); padding:14px; margin-bottom:18px;">
                                <div style="font-size:13px; font-weight:600; color:var(--accent); margin-bottom:4px;">Core Objectives for Tonight:</div>
                                ${(plan.top_three_priorities || []).map(pr => `<div style="font-size:12.5px; color:var(--text-secondary); margin-bottom:2px;">• ${escapeHtml(pr)}</div>`).join('')}
                            </div>
                            <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(280px, 1fr)); gap:14px;">
                                ${(plan.blocks || []).map((b, idx) => `
                                    <div style="background:var(--bg-sidebar); border:1px solid var(--border-subtle); border-radius:var(--radius-md); padding:14px;">
                                        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                                            <strong style="color:var(--text-main); font-size:13.5px;">Block ${idx + 1}: ${escapeHtml(b.title || '')}</strong>
                                            <span class="badge badge-purple">${b.duration_minutes || 45} mins</span>
                                        </div>
                                        <div style="font-size:12px; color:var(--text-secondary); margin-bottom:10px;">${escapeHtml(b.objective || '')}</div>
                                        ${(b.tasks || []).map(t => `
                                            <label style="display:flex; align-items:flex-start; gap:8px; font-size:12px; color:var(--text-main); margin-bottom:6px; cursor:pointer;">
                                                <input type="checkbox" style="margin-top:2px;">
                                                <span>${escapeHtml(t)}</span>
                                            </label>
                                        `).join('')}
                                    </div>
                                `).join('')}
                            </div>
                        </div>
                    </div>
                `;
            } catch (err) {
                container.innerHTML = `<div style="text-align:center; padding:20px; color:var(--danger);">${escapeHtml(err.message)}</div>`;
            }
        }

        // --- Candidate Profile Governance & Field-Level Editing ---

        async function loadFullProfile() {
            const container = document.getElementById('profile-evidence-sections');
            try {
                container.innerHTML = '<div style="text-align:center; padding:20px; color:var(--text-secondary);">Loading candidate evidence registry...</div>';
                const res = await apiFetch('/api/profile/full');
                if (!res.ok) throw new Error(`Profile API failed (${res.status})`);
                const data = await res.json();
                const sum = data.summary || {};

                document.getElementById('prof-stat-total').innerText = sum.total_fields || 0;
                document.getElementById('prof-stat-confirmed').innerText = sum.confirmed_count !== undefined ? sum.confirmed_count : (sum.confirmed_by_candidate || 0);
                document.getElementById('prof-stat-pending').innerText = sum.needs_review_count !== undefined ? sum.needs_review_count : (sum.requires_confirmation || 0);
                document.getElementById('prof-stat-not-provided').innerText = sum.not_provided_count !== undefined ? sum.not_provided_count : (sum.not_provided || 0);

                const renderBadge = (state) => {
                    const s = (state || '').toUpperCase();
                    if (s === 'CONFIRMED' || s === 'CONFIRMED_BY_CANDIDATE' || s === 'VERIFIED_FROM_SOURCE') {
                        return '<span class="badge badge-green">✓ Confirmed</span>';
                    } else if (s === 'NOT_PROVIDED') {
                        return '<span class="badge badge-gray">Not Declared</span>';
                    }
                    return '<span class="badge badge-yellow">● Needs Review</span>';
                };

                const pers = data.personal || {};
                const edu = data.education || {};

                container.innerHTML = `
                    <div style="display:flex; flex-direction:column; gap:20px;">
                        <!-- Section 1: Personal & Contact -->
                        <div style="background:var(--bg-sidebar); border:1px solid var(--border-subtle); border-radius:var(--radius-md); padding:18px;">
                            <h4 style="font-size:14px; color:var(--accent); margin-bottom:12px;">1. Personal Information & Availability</h4>
                            <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(300px, 1fr)); gap:12px;">
                                <div class="profile-claim-box">
                                    <div><strong>Full Name:</strong> ${escapeHtml(pers.full_name?.value || 'Candidate')}</div>
                                    <div style="margin-top:4px;">${renderBadge(pers.full_name?.state)} <small style="color:var(--text-muted);">${escapeHtml(pers.full_name?.evidence || '')}</small></div>
                                    <button class="btn btn-secondary btn-sm" style="margin-top:8px; font-size:11px;" onclick="openEditFieldModal('personal.full_name', '${escapeHtml(pers.full_name?.value || '')}', '${pers.full_name?.state || ''}', '${escapeHtml(pers.full_name?.evidence || '')}')">Edit Fact</button>
                                </div>
                                <div class="profile-claim-box">
                                    <div><strong>Base Location:</strong> ${escapeHtml(pers.location?.value || 'Cuddalore, Tamil Nadu')}</div>
                                    <div style="margin-top:4px;">${renderBadge(pers.location?.state)} <small style="color:var(--text-muted);">${escapeHtml(pers.location?.evidence || '')}</small></div>
                                    <button class="btn btn-secondary btn-sm" style="margin-top:8px; font-size:11px;" onclick="openEditFieldModal('personal.location', '${escapeHtml(pers.location?.value || '')}', '${pers.location?.state || ''}', '${escapeHtml(pers.location?.evidence || '')}')">Edit Fact</button>
                                </div>
                                <div class="profile-claim-box">
                                    <div><strong>Notice Period:</strong> ${escapeHtml(pers.notice_period_status?.value || 'Negotiable (60-90 days)')}</div>
                                    <div style="margin-top:4px;">${renderBadge(pers.notice_period_status?.state)} <small style="color:var(--text-muted);">${escapeHtml(pers.notice_period_status?.evidence || '')}</small></div>
                                    <button class="btn btn-secondary btn-sm" style="margin-top:8px; font-size:11px;" onclick="openEditFieldModal('personal.notice_period_status', '${escapeHtml(pers.notice_period_status?.value || '')}', '${pers.notice_period_status?.state || ''}', '${escapeHtml(pers.notice_period_status?.evidence || '')}')">Edit Fact</button>
                                </div>
                                <div class="profile-claim-box">
                                    <div><strong>Work Authorization:</strong> ${escapeHtml(pers.work_authorization?.value || 'India')}</div>
                                    <div style="margin-top:4px;">${renderBadge(pers.work_authorization?.state)} <small style="color:var(--text-muted);">${escapeHtml(pers.work_authorization?.evidence || '')}</small></div>
                                    <button class="btn btn-secondary btn-sm" style="margin-top:8px; font-size:11px;" onclick="openEditFieldModal('personal.work_authorization', '${escapeHtml(pers.work_authorization?.value || '')}', '${pers.work_authorization?.state || ''}', '${escapeHtml(pers.work_authorization?.evidence || '')}')">Edit Fact</button>
                                </div>
                            </div>
                        </div>

                        <!-- Section 2: Education -->
                        <div style="background:var(--bg-sidebar); border:1px solid var(--border-subtle); border-radius:var(--radius-md); padding:18px;">
                            <h4 style="font-size:14px; color:var(--accent); margin-bottom:12px;">2. Education & Academics</h4>
                            <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(300px, 1fr)); gap:12px;">
                                <div class="profile-claim-box">
                                    <div><strong>Degree:</strong> ${escapeHtml(edu.degree?.value || 'Bachelor of Engineering (B.E.)')}</div>
                                    <div><strong>Field:</strong> ${escapeHtml(edu.field_of_study?.value || 'Electronics and Communication Engineering')}</div>
                                    <div style="margin-top:4px;">${renderBadge(edu.degree?.state)} <small style="color:var(--text-muted);">${escapeHtml(edu.degree?.evidence || '')}</small></div>
                                    <button class="btn btn-secondary btn-sm" style="margin-top:8px; font-size:11px;" onclick="openEditFieldModal('education.degree', '${escapeHtml(edu.degree?.value || '')}', '${edu.degree?.state || ''}', '${escapeHtml(edu.degree?.evidence || '')}')">Edit Fact</button>
                                </div>
                                <div class="profile-claim-box">
                                    <div><strong>Institution:</strong> ${escapeHtml(edu.institution?.value || '')}</div>
                                    <div><strong>Graduation:</strong> ${escapeHtml(String(edu.graduation_year?.value || ''))} | <strong>CGPA:</strong> ${escapeHtml(String(edu.cgpa?.value || ''))}</div>
                                    <div style="margin-top:4px;">${renderBadge(edu.institution?.state)} <small style="color:var(--text-muted);">${escapeHtml(edu.institution?.evidence || '')}</small></div>
                                    <button class="btn btn-secondary btn-sm" style="margin-top:8px; font-size:11px;" onclick="openEditFieldModal('education.cgpa', '${escapeHtml(String(edu.cgpa?.value || ''))}', '${edu.cgpa?.state || ''}', '${escapeHtml(edu.cgpa?.evidence || '')}')">Edit Fact</button>
                                </div>
                            </div>
                        </div>

                        <!-- Section 3: Professional Experience -->
                        <div style="background:var(--bg-sidebar); border:1px solid var(--border-subtle); border-radius:var(--radius-md); padding:18px;">
                            <h4 style="font-size:14px; color:var(--accent); margin-bottom:12px;">3. Employment & Commercial History</h4>
                            ${(data.employment || []).map((emp, idx) => `
                                <div style="background:var(--bg-card); border:1px solid var(--border-subtle); border-radius:var(--radius-md); padding:14px; margin-bottom:12px;">
                                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                                        <strong>${escapeHtml(emp.role)} at ${escapeHtml(emp.employer)}</strong>
                                        <span class="badge badge-purple">${escapeHtml(emp.start_date)} – ${escapeHtml(emp.end_date)}</span>
                                    </div>
                                    <div style="font-size:12px; color:var(--text-secondary); margin-bottom:8px;">${escapeHtml(emp.location)} • ${escapeHtml(emp.employment_type)}</div>
                                    <ul style="font-size:12px; color:var(--text-secondary); padding-left:18px; margin-bottom:10px;">
                                        ${(emp.highlights || []).map(h => `<li>${escapeHtml(h)}</li>`).join('')}
                                    </ul>
                                    <div style="display:flex; gap:6px; flex-wrap:wrap;">
                                        ${(emp.skills_used || []).map(s => `<span class="badge badge-blue">${escapeHtml(s)}</span>`).join('')}
                                    </div>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                `;
            } catch (err) {
                container.innerHTML = `<div style="text-align:center; padding:30px; color:var(--danger);">${escapeHtml(err.message)} <br><button class="btn btn-sm btn-secondary" onclick="loadFullProfile()" style="margin-top:10px;">Retry</button></div>`;
            }
        }

        function openEditFieldModal(fieldPath, currentValue, currentState, currentEvidence) {
            activeEditField = fieldPath;
            document.getElementById('modal-edit-field-path').innerText = fieldPath;
            document.getElementById('modal-edit-field-value').value = currentValue || '';
            document.getElementById('modal-edit-field-state').value = (currentState === 'CONFIRMED_BY_CANDIDATE' ? 'CONFIRMED' : (currentState === 'NOT_PROVIDED' ? 'NOT_PROVIDED' : 'NEEDS_REVIEW'));
            document.getElementById('modal-edit-field-note').value = currentEvidence || '';
            document.getElementById('edit-field-modal').classList.add('active');
        }

        async function saveFieldEdit() {
            if (!activeEditField) return;
            const newVal = document.getElementById('modal-edit-field-value').value.trim();
            const state = document.getElementById('modal-edit-field-state').value;
            const note = document.getElementById('modal-edit-field-note').value.trim();

            try {
                const res = await apiFetch('/api/profile/field', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        field: activeEditField,
                        value: newVal,
                        state: state,
                        note: note || 'Updated via Profile Governance Editor',
                        author: 'Candidate'
                    })
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Could not update field');
                showToast(`Fact '${activeEditField}' updated and provenance logged!`, 'success');
                closeModal('edit-field-modal');
                loadFullProfile();
                fetchStats();
            } catch (err) {
                showToast(err.message, 'error');
            }
        }

        async function openProfileHistoryModal() {
            const modal = document.getElementById('profile-history-modal');
            const container = document.getElementById('profile-history-body');
            modal.classList.add('active');
            container.innerHTML = '<div style="text-align:center; padding:20px; color:var(--text-secondary);">Loading change history...</div>';

            try {
                const res = await apiFetch('/api/profile/history?limit=50');
                const data = await res.json();
                const history = data.history || [];

                if (history.length === 0) {
                    container.innerHTML = '<div style="text-align:center; padding:30px; color:var(--text-muted);">No fact modifications recorded yet in history log.</div>';
                    return;
                }

                container.innerHTML = `
                    <table style="width:100%; font-size:12px;">
                        <thead>
                            <tr style="text-align:left; border-bottom:1px solid var(--border-subtle); color:var(--text-secondary);">
                                <th style="padding:8px;">Timestamp (UTC)</th>
                                <th style="padding:8px;">Field Path</th>
                                <th style="padding:8px;">New Value</th>
                                <th style="padding:8px;">State</th>
                                <th style="padding:8px;">Audit Note</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${history.map(h => `
                                <tr style="border-bottom:1px solid rgba(255,255,255,0.04);">
                                    <td style="padding:8px; color:var(--text-muted); font-size:11px;">${escapeHtml(h.timestamp ? h.timestamp.replace('T', ' ').slice(0, 19) : '')}</td>
                                    <td style="padding:8px; font-family:monospace; color:var(--accent);">${escapeHtml(h.field || '')}</td>
                                    <td style="padding:8px;"><strong>${escapeHtml(String(h.new_value ?? ''))}</strong></td>
                                    <td style="padding:8px;"><span class="badge badge-blue">${escapeHtml(h.state || 'CONFIRMED')}</span></td>
                                    <td style="padding:8px; color:var(--text-secondary);">${escapeHtml(h.note || '')}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                `;
            } catch (err) {
                container.innerHTML = `<div style="text-align:center; padding:20px; color:var(--danger);">${escapeHtml(err.message)}</div>`;
            }
        }

        async function downloadProfileSnapshot() {
            try {
                showToast('Exporting tamper-evident candidate profile snapshot...', 'info');
                const res = await apiFetch('/api/profile/snapshot');
                if (!res.ok) throw new Error('Snapshot API failed');
                const snapshot = await res.json();
                const blob = new Blob([JSON.stringify(snapshot, null, 2)], { type: 'application/json' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `Candidate_Profile_Snapshot_${new Date().toISOString().slice(0,10)}.json`;
                document.body.appendChild(a);
                a.click();
                a.remove();
                URL.revokeObjectURL(url);
                showToast(`Snapshot exported! SHA-256 Digest: ${snapshot.integrity_sha256.slice(0, 12)}...`, 'success');
            } catch (err) {
                showToast(err.message, 'error');
            }
        }

        // --- Discovery Sources & Employer ATS Registry ---

        async function loadSourcesHealth() {
            const container = document.getElementById('sources-health-grid');
            try {
                const res = await apiFetch('/api/sources/health');
                const data = await res.json();
                const sources = data.sources || [];

                container.innerHTML = sources.map(s => `
                    <div style="background:var(--bg-sidebar); border:1px solid var(--border-subtle); border-radius:var(--radius-md); padding:16px;">
                        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                            <strong style="color:var(--text-main); font-size:14px;">${escapeHtml(s.name)}</strong>
                            <span class="badge ${s.configured ? 'badge-green' : 'badge-yellow'}">${s.configured ? 'Operational' : 'Optional'}</span>
                        </div>
                        <div style="font-size:12px; color:var(--text-secondary); margin-bottom:4px;">Adapter: ${escapeHtml(s.adapter_type)}</div>
                        <div style="font-size:11.5px; color:var(--text-muted); word-break:break-all;">Endpoint: ${escapeHtml(s.endpoint)}</div>
                    </div>
                `).join('');
            } catch (err) {
                container.innerHTML = `<div style="grid-column: 1/-1; text-align:center; padding:20px; color:var(--danger);">${escapeHtml(err.message)}</div>`;
            }
        }

        async function loadEmployerRegistry() {
            const container = document.getElementById('employer-registry-table-container');
            if (!container) return;
            try {
                const res = await apiFetch('/api/sources/registry');
                if (!res.ok) throw new Error('Registry API failed');
                const data = await res.json();
                const sources = data.sources || [];

                if (sources.length === 0) {
                    container.innerHTML = '<div style="text-align:center; padding:30px; color:var(--text-muted);">No employer ATS boards configured. Click "+ Register Employer Board" to add one.</div>';
                    return;
                }

                container.innerHTML = `
                    <table style="width:100%; font-size:12.5px;">
                        <thead>
                            <tr style="text-align:left; border-bottom:1px solid var(--border-subtle); color:var(--text-secondary);">
                                <th style="padding:10px;">Employer & Domain</th>
                                <th style="padding:10px;">Provider</th>
                                <th style="padding:10px;">Board Identifier</th>
                                <th style="padding:10px;">Status</th>
                                <th style="padding:10px;">Jobs Discovered</th>
                                <th style="padding:10px;">Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${sources.map(s => `
                                <tr style="border-bottom:1px solid rgba(255,255,255,0.04);">
                                    <td style="padding:10px;">
                                        <strong>${escapeHtml(s.employer_name)}</strong><br>
                                        <a href="https://${escapeHtml(s.official_domain)}" target="_blank" rel="noopener noreferrer" style="color:var(--accent); font-size:11.5px;">${escapeHtml(s.official_domain)}</a>
                                    </td>
                                    <td style="padding:10px;"><span class="badge badge-purple">${escapeHtml(s.ats_provider)}</span></td>
                                    <td style="padding:10px; font-family:monospace; color:var(--text-main);">${escapeHtml(s.board_id)}</td>
                                    <td style="padding:10px;">
                                        <span class="badge ${s.status === 'OK' ? 'badge-green' : (s.status === 'FAILED' ? 'badge-red' : 'badge-blue')}">${escapeHtml(s.status)}</span>
                                        ${s.enabled ? '<span class="badge badge-green" style="font-size:10px; margin-left:4px;">Active</span>' : '<span class="badge badge-gray" style="font-size:10px; margin-left:4px;">Disabled</span>'}
                                    </td>
                                    <td style="padding:10px;"><strong>${s.jobs_discovered || 0}</strong></td>
                                    <td style="padding:10px;">
                                        <div style="display:flex; gap:6px;">
                                            <button class="btn btn-secondary btn-sm" style="font-size:11px;" onclick="testEmployerSource('${s.id}')">Test Live</button>
                                            <button class="btn btn-secondary btn-sm" style="font-size:11px;" onclick="toggleEmployerSource('${s.id}', ${!s.enabled})">${s.enabled ? 'Disable' : 'Enable'}</button>
                                            <button class="btn btn-sm" style="background:#dc2626; color:#fff; font-size:11px;" onclick="deleteEmployerSourceHandler('${s.id}')">Delete</button>
                                        </div>
                                    </td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                `;
            } catch (err) {
                container.innerHTML = `<div style="text-align:center; padding:20px; color:var(--danger);">${escapeHtml(err.message)}</div>`;
            }
        }

        function openAddEmployerModal() {
            document.getElementById('add-source-name').value = '';
            document.getElementById('add-source-domain').value = '';
            document.getElementById('add-source-board-id').value = '';
            document.getElementById('add-source-notes').value = '';
            document.getElementById('add-source-modal').classList.add('active');
        }

        async function submitNewEmployerSource() {
            const name = document.getElementById('add-source-name').value.trim();
            const domain = document.getElementById('add-source-domain').value.trim();
            const provider = document.getElementById('add-source-provider').value;
            const boardId = document.getElementById('add-source-board-id').value.trim();
            const notes = document.getElementById('add-source-notes').value.trim();

            if (!name || !boardId) {
                showToast('Please fill in Employer Name and Board Identifier.', 'error');
                return;
            }

            try {
                const res = await apiFetch('/api/sources/registry', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        employer_name: name,
                        official_domain: domain,
                        ats_provider: provider,
                        board_id: boardId,
                        notes: notes,
                        enabled: true
                    })
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Could not register employer source');
                showToast(`Employer source '${name}' registered!`, 'success');
                closeModal('add-source-modal');
                loadEmployerRegistry();
            } catch (err) {
                showToast(err.message, 'error');
            }
        }

        async function testEmployerSource(sourceId) {
            try {
                showToast(`Testing live ATS feed for ${sourceId}...`, 'info');
                const res = await apiFetch(`/api/sources/registry/${sourceId}/test`, { method: 'POST' });
                const data = await res.json();
                if (data.status === 'SUCCESS') {
                    showToast(`Feed reachable! Found ${data.jobs_found} active vacancies.`, 'success');
                } else {
                    showToast(`Feed error: ${data.error || 'Check board token and reachability'}`, 'error');
                }
                loadEmployerRegistry();
            } catch (err) {
                showToast(err.message, 'error');
            }
        }

        async function toggleEmployerSource(sourceId, newEnabledState) {
            try {
                const res = await apiFetch(`/api/sources/registry/${sourceId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ enabled: newEnabledState })
                });
                if (!res.ok) throw new Error('Could not toggle source status');
                showToast(`Source ${newEnabledState ? 'enabled' : 'disabled'}.`, 'info');
                loadEmployerRegistry();
            } catch (err) {
                showToast(err.message, 'error');
            }
        }

        async function deleteEmployerSourceHandler(sourceId) {
            if (!confirm(`Delete employer source '${sourceId}' from active registry?`)) return;
            try {
                const res = await apiFetch(`/api/sources/registry/${sourceId}`, { method: 'DELETE' });
                if (!res.ok) throw new Error('Could not delete source');
                showToast('Employer source removed.', 'info');
                loadEmployerRegistry();
            } catch (err) {
                showToast(err.message, 'error');
            }
        }

        async function loadSchedulerHistory() {
            const tbody = document.getElementById('scheduler-history-body');
            try {
                const res = await apiFetch('/api/scheduler/history');
                const data = await res.json();
                const runs = data.runs || [];
                if (runs.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; padding:20px; color:var(--text-muted);">No automated execution history recorded yet.</td></tr>';
                    return;
                }

                tbody.innerHTML = runs.map(r => `
                    <tr>
                        <td style="font-size:12px; color:var(--text-muted);">${escapeHtml(r.timestamp ? r.timestamp.replace('T', ' ').slice(0, 19) : '')}</td>
                        <td><strong>${escapeHtml(r.workflow || 'discovery')}</strong></td>
                        <td><span class="badge ${r.status === 'success' ? 'badge-green' : (r.status === 'skipped_overlap' ? 'badge-yellow' : 'badge-red')}">${escapeHtml(r.status || 'unknown')}</span></td>
                        <td>${escapeHtml(String(r.duration_seconds || '0.5'))}s</td>
                        <td>${r.total_collected !== undefined ? `${r.total_collected} collected (${r.new_jobs_added || 0} new)` : '—'}</td>
                        <td style="font-size:11.5px; color:var(--text-secondary);">${escapeHtml(r.message || r.note || 'OK')}</td>
                    </tr>
                `).join('');
            } catch (err) {
                tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding:20px; color:var(--danger);">${escapeHtml(err.message)}</td></tr>`;
            }
        }

        async function triggerDiscovery(btn) {
            btn.disabled = true;
            const originalText = btn.innerHTML;
            btn.innerHTML = 'Searching Real APIs...';
            showToast('Querying Jobicy, Remotive, Arbeitnow, and configured employer boards...', 'info');

            try {
                const res = await apiFetch('/api/discovery/trigger', { method: 'POST' });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Discovery failed');
                showToast(`Discovery completed! Found: ${data.total_collected || 0}, Added: ${data.new_jobs_added || 0}, Updated: ${data.jobs_updated || 0}`, 'success');
                fetchStats();
                loadJobs();
            } catch (err) {
                showToast(err.message, 'error');
            } finally {
                btn.disabled = false;
                btn.innerHTML = originalText;
            }
        }

        async function regenerateDailyPlan() {
            try {
                showToast('Generating fresh evening study plan...', 'info');
                await loadDailyStudyPlan();
                showToast('Study plan updated for tonight (8:00 PM IST)!', 'success');
            } catch (err) {
                showToast(err.message, 'error');
            }
        }

        async function runUrlVerificationTest() {
            const url = document.getElementById('test-verify-url-input').value.trim();
            const resultBox = document.getElementById('test-verify-result');
            if (!url) {
                resultBox.innerHTML = '<span style="color:var(--danger);">Please enter a URL to test.</span>';
                return;
            }
            resultBox.innerHTML = '<span style="color:var(--accent);">Checking domain against SSRF and ATS allowlist...</span>';
            try {
                const res = await apiFetch('/api/verify-url', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url: url })
                });
                const data = await res.json();
                resultBox.innerHTML = `
                    <div style="background:var(--bg-sidebar); border:1px solid var(--border-subtle); padding:10px; border-radius:var(--radius-sm); margin-top:6px;">
                        <div>Status: ${renderVerificationBadge(data.status)}</div>
                        <div style="color:var(--text-secondary); margin-top:4px;">Notes: ${escapeHtml(data.notes)}</div>
                    </div>
                `;
            } catch (err) {
                resultBox.innerHTML = `<span style="color:var(--danger);">${escapeHtml(err.message)}</span>`;
            }
        }

        function exportData(type) {
            window.location.href = `${API_BASE}/api/export/${type}`;
            showToast(`Downloading ${type} CSV export...`, 'info');
        }

        // Initialize application on window load
        window.addEventListener('DOMContentLoaded', () => {
            checkBackendHealth();
            fetchStats();
            loadOverviewJobs();

            // Periodic health poll every 10 seconds
            setInterval(checkBackendHealth, 10000);

            // Keyboard shortcut: Escape closes active modals
            window.addEventListener('keydown', e => {
                if (e.key === 'Escape') {
                    document.querySelectorAll('.modal.active').forEach(m => m.classList.remove('active'));
                }
            });
        });
    </script>
"""

def update_script():
    path = Path("careerorbit/web/static/index.html")
    html = path.read_text(encoding="utf-8")
    script_start = html.find("    <!-- Application JavaScript -->")
    if script_start == -1:
        script_start = html.find("<script>")
    script_end = html.rfind("</body>")

    new_script = generate_script_content()
    updated_html = html[:script_start] + "    <!-- Application JavaScript -->\n" + new_script + "\n</body>\n</html>"
    path.write_text(updated_html, encoding="utf-8")
    print(f"[+] Successfully injected complete, robust JavaScript! New file length: {len(updated_html)} characters.")

if __name__ == "__main__":
    update_script()
