"""Script to update careerorbit/web/static/index.html with robust apiFetch,
WhatsApp import modal, community announcement modal, quick filters, and fixed handlers.
"""
from pathlib import Path

html_path = Path("careerorbit/web/static/index.html")
content = html_path.read_text(encoding="utf-8")

# 1. Add apiFetch right after state declarations
old_state = """        // State
        let allJobsData = [];
        let allApplicationsData = [];
        let allResumesData = [];
        let currentTab = 'overview';
        let debounceTimer = null;"""

new_state = """        // State
        let allJobsData = [];
        let allApplicationsData = [];
        let allResumesData = [];
        let currentTab = 'overview';
        let debounceTimer = null;
        let isSyncingTelegram = false;
        let whatsappPreviewItems = [];

        // Unified API Request Helper
        async function apiFetch(url, options = {}) {
            const opts = { ...options };
            opts.headers = opts.headers || {};
            if (opts.body && typeof opts.body === 'string' && !opts.headers['Content-Type']) {
                opts.headers['Content-Type'] = 'application/json';
            }

            const timeoutMs = opts.timeout || 15000;
            delete opts.timeout;

            let timeoutId = null;
            if (!opts.signal) {
                const controller = new AbortController();
                opts.signal = controller.signal;
                timeoutId = setTimeout(() => controller.abort(), timeoutMs);
            }

            try {
                const response = await fetch(url, opts);
                if (timeoutId) clearTimeout(timeoutId);

                if (!response.ok) {
                    let errorDetail = `HTTP ${response.status} ${response.statusText}`;
                    try {
                        const errData = await response.clone().json();
                        if (errData && errData.detail) {
                            errorDetail = typeof errData.detail === 'string' ? errData.detail : JSON.stringify(errData.detail);
                        } else if (errData && errData.message) {
                            errorDetail = errData.message;
                        } else if (errData && errData.error) {
                            errorDetail = errData.error;
                        }
                    } catch (_) {
                        try {
                            const txt = await response.clone().text();
                            if (txt) errorDetail += `: ${txt.slice(0, 120)}`;
                        } catch (__) {}
                    }
                    const error = new Error(errorDetail);
                    error.status = response.status;
                    error.response = response;
                    throw error;
                }

                return response;
            } catch (err) {
                if (timeoutId) clearTimeout(timeoutId);
                if (err.name === 'AbortError') {
                    throw new Error(`Request timed out after ${Math.round(timeoutMs / 1000)}s`);
                }
                throw err;
            }
        }"""

if old_state in content:
    content = content.replace(old_state, new_state, 1)
    print("1. apiFetch added")
else:
    print("1. old_state not found")

# 2. Add WhatsApp import button to header
old_hdr_btns = """                    <div style="display: flex; gap: 10px; align-items: center;">
                        <button class="btn btn-secondary btn-sm" onclick="openCommunityImportModal()" style="display: inline-flex; align-items: center; gap: 6px;">
                            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"></path></svg>
                            Paste Announcement
                        </button>
                        <button id="btn-telegram-poll" class="btn btn-primary btn-sm" onclick="triggerTelegramManualPoll()" style="display: inline-flex; align-items: center; gap: 6px;">"""

new_hdr_btns = """                    <div style="display: flex; gap: 10px; align-items: center; flex-wrap: wrap;">
                        <button class="btn btn-secondary btn-sm" onclick="openCommunityImportModal()" style="display: inline-flex; align-items: center; gap: 6px;">
                            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"></path></svg>
                            Paste Announcement
                        </button>
                        <button class="btn btn-secondary btn-sm" onclick="openWhatsAppImportModal()" style="display: inline-flex; align-items: center; gap: 6px;">
                            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"></path></svg>
                            Import WhatsApp Chat
                        </button>
                        <button id="btn-telegram-poll" class="btn btn-primary btn-sm" onclick="triggerTelegramManualPoll()" style="display: inline-flex; align-items: center; gap: 6px;">"""

if old_hdr_btns in content:
    content = content.replace(old_hdr_btns, new_hdr_btns, 1)
    print("2. WhatsApp header button added")
else:
    print("2. old_hdr_btns not found")

# 3. Add Quick Filter pills & Platform dropdown to Filter Bar
old_filter_bar = """            <!-- Filter Bar -->
            <div class="card" style="margin-bottom: 16px; padding: 14px 18px;">
                <div style="display: flex; flex-wrap: wrap; gap: 12px; align-items: center; justify-content: space-between;">
                    <div style="display: flex; flex-wrap: wrap; gap: 8px; align-items: center;">
                        <label style="font-size: 12px; color: var(--text-secondary); font-weight: 600;">Category:</label>"""

new_filter_bar = """            <!-- Filter Bar -->
            <div class="card" style="margin-bottom: 16px; padding: 14px 18px;">
                <!-- Quick Filter Pills -->
                <div style="display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid var(--border-subtle);">
                    <button class="btn btn-secondary btn-sm inbox-pill active" onclick="setInboxQuickFilter('')">All Messages</button>
                    <button class="btn btn-secondary btn-sm inbox-pill" onclick="setInboxQuickFilter('JOB_LEADS')">💼 Job Leads</button>
                    <button class="btn btn-secondary btn-sm inbox-pill" onclick="setInboxQuickFilter('Job: Data Analyst / BI')">📊 Data Analyst / BI</button>
                    <button class="btn btn-secondary btn-sm inbox-pill" onclick="setInboxQuickFilter('Job: Data Science / AI / ML')">🤖 DS / AI / ML</button>
                    <button class="btn btn-secondary btn-sm inbox-pill" onclick="setInboxQuickFilter('Job: Software Engineering')">💻 Software Eng</button>
                    <button class="btn btn-secondary btn-sm inbox-pill" onclick="setInboxQuickFilter('Job: Data Engineering')">⚙️ Data Eng</button>
                    <button class="btn btn-secondary btn-sm inbox-pill" onclick="setInboxQuickFilter('Interview Preparation')">🎯 Interview Prep</button>
                    <button class="btn btn-secondary btn-sm inbox-pill" onclick="setInboxQuickFilter('Coding Practice')">🧩 DSA & Coding</button>
                    <button class="btn btn-secondary btn-sm inbox-pill" onclick="setInboxQuickFilter('Technical Learning Materials')">📚 Study Materials</button>
                    <button class="btn btn-secondary btn-sm inbox-pill" onclick="setInboxQuickFilter('Certifications and Courses')">🎓 Certs & Courses</button>
                    <button class="btn btn-secondary btn-sm inbox-pill" onclick="setInboxQuickFilter('ARCHIVED')">📁 Archived</button>
                </div>

                <div style="display: flex; flex-wrap: wrap; gap: 12px; align-items: center; justify-content: space-between;">
                    <div style="display: flex; flex-wrap: wrap; gap: 8px; align-items: center;">
                        <label style="font-size: 12px; color: var(--text-secondary); font-weight: 600;">Category:</label>"""

if old_filter_bar in content:
    content = content.replace(old_filter_bar, new_filter_bar, 1)
    print("3. Quick filter pills added")
else:
    print("3. old_filter_bar not found")

# 3b. Add Platform filter dropdown
old_status_select = """                        <label style="font-size: 12px; color: var(--text-secondary); font-weight: 600; margin-left: 8px;">Status:</label>
                        <select id="inbox-filter-status" onchange="loadInbox()" style="background: var(--bg-sidebar); border: 1px solid var(--border-subtle); color: var(--text-main); padding: 6px 12px; border-radius: var(--radius-sm); font-size: 12px;">
                            <option value="">All Statuses</option>
                            <option value="NEW" selected>NEW</option>
                            <option value="PROCESSED">PROCESSED</option>
                            <option value="ARCHIVED">ARCHIVED</option>
                            <option value="DISCARDED">DISCARDED</option>
                        </select>"""

new_status_select = """                        <label style="font-size: 12px; color: var(--text-secondary); font-weight: 600; margin-left: 8px;">Platform:</label>
                        <select id="inbox-filter-platform" onchange="loadInbox()" style="background: var(--bg-sidebar); border: 1px solid var(--border-subtle); color: var(--text-main); padding: 6px 12px; border-radius: var(--radius-sm); font-size: 12px;">
                            <option value="">All Platforms</option>
                            <option value="telegram">Telegram</option>
                            <option value="whatsapp">WhatsApp</option>
                        </select>

                        <label style="font-size: 12px; color: var(--text-secondary); font-weight: 600; margin-left: 8px;">Status:</label>
                        <select id="inbox-filter-status" onchange="loadInbox()" style="background: var(--bg-sidebar); border: 1px solid var(--border-subtle); color: var(--text-main); padding: 6px 12px; border-radius: var(--radius-sm); font-size: 12px;">
                            <option value="">All Statuses</option>
                            <option value="NEW" selected>NEW</option>
                            <option value="PROCESSED">PROCESSED</option>
                            <option value="ARCHIVED">ARCHIVED</option>
                            <option value="DISCARDED">DISCARDED</option>
                        </select>"""

if old_status_select in content:
    content = content.replace(old_status_select, new_status_select, 1)
    print("3b. Platform dropdown added")
else:
    print("3b. old_status_select not found")

# 4. Add Community Import Modal & WhatsApp Import Modal
old_tailoring_modal = """    <!-- Resume Tailoring Details Modal -->
    <div id="tailoring-modal" class="modal" role="dialog" aria-modal="true" onclick="if(event.target===this)closeModal('tailoring-modal')">
        <div class="modal-content">
            <div class="modal-header">
                <div>
                    <h3 id="modal-tailoring-title">Tailoring Analysis Report</h3>
                    <p id="modal-tailoring-subtitle">ATS Keyword Coverage & Requirement Alignment</p>
                </div>
                <button class="modal-close" onclick="closeModal('tailoring-modal')">&times;</button>
            </div>
            <div id="modal-tailoring-body">
                <!-- Dynamically populated -->
            </div>
        </div>
    </div>"""

new_modals = """    <!-- Resume Tailoring Details Modal -->
    <div id="tailoring-modal" class="modal" role="dialog" aria-modal="true" onclick="if(event.target===this)closeModal('tailoring-modal')">
        <div class="modal-content">
            <div class="modal-header">
                <div>
                    <h3 id="modal-tailoring-title">Tailoring Analysis Report</h3>
                    <p id="modal-tailoring-subtitle">ATS Keyword Coverage & Requirement Alignment</p>
                </div>
                <button class="modal-close" onclick="closeModal('tailoring-modal')">&times;</button>
            </div>
            <div id="modal-tailoring-body">
                <!-- Dynamically populated -->
            </div>
        </div>
    </div>

    <!-- Community Import Modal -->
    <div id="community-import-modal" class="modal" role="dialog" aria-modal="true" onclick="if(event.target===this)closeModal('community-import-modal')">
        <div class="modal-content" style="max-width: 650px;">
            <div class="modal-header">
                <div>
                    <h3 style="margin:0; font-size:16px;">Paste Community Announcement</h3>
                    <p style="margin:2px 0 0 0; font-size:12px; color:var(--text-secondary);">Paste raw text from Telegram, WhatsApp, LinkedIn, or placement portals.</p>
                </div>
                <button class="modal-close" onclick="closeModal('community-import-modal')">&times;</button>
            </div>
            <div style="padding: 16px 20px;">
                <label style="font-size: 12px; color: var(--text-secondary); font-weight: 600; display: block; margin-bottom: 6px;">Source Channel / Group Name:</label>
                <input type="text" id="comm-import-channel" placeholder="e.g. TN Tech Hiring Alert" style="width: 100%; margin-bottom: 14px; background: var(--bg-sidebar); border: 1px solid var(--border-subtle); color: var(--text-main); padding: 8px 12px; border-radius: var(--radius-sm); font-size: 13px;">

                <label style="font-size: 12px; color: var(--text-secondary); font-weight: 600; display: block; margin-bottom: 6px;">Announcement Text:</label>
                <textarea id="comm-import-text" rows="7" placeholder="Paste vacancy details, role, company, location, batch, eligibility, apply link..." style="width: 100%; background: var(--bg-sidebar); border: 1px solid var(--border-subtle); color: var(--text-main); padding: 10px 12px; border-radius: var(--radius-sm); font-size: 13px; font-family: inherit; line-height: 1.5;"></textarea>

                <div id="comm-import-preview-box" style="display: none; margin-top: 14px; padding: 12px; background: rgba(15, 23, 42, 0.6); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm);"></div>

                <div style="display: flex; justify-content: flex-end; gap: 10px; margin-top: 16px;">
                    <button class="btn btn-secondary btn-sm" onclick="closeModal('community-import-modal')">Cancel</button>
                    <button class="btn btn-secondary btn-sm" onclick="previewCommunityImport()">Preview Extraction</button>
                    <button class="btn btn-primary btn-sm" id="btn-comm-import-confirm" onclick="confirmCommunityImport()">Import as UNVERIFIED Lead</button>
                </div>
            </div>
        </div>
    </div>

    <!-- WhatsApp Import Modal -->
    <div id="whatsapp-import-modal" class="modal" role="dialog" aria-modal="true" onclick="if(event.target===this)closeModal('whatsapp-import-modal')">
        <div class="modal-content" style="max-width: 750px; max-height: 85vh; overflow-y: auto;">
            <div class="modal-header">
                <div>
                    <h3 style="margin:0; font-size:16px;">Import WhatsApp Chat Export (.txt)</h3>
                    <p style="margin:2px 0 0 0; font-size:12px; color:var(--text-secondary);">Parses exported WhatsApp chats, filters personal messages, and ingests verified career resources.</p>
                </div>
                <button class="modal-close" onclick="closeModal('whatsapp-import-modal')">&times;</button>
            </div>
            <div style="padding: 16px 20px;">
                <div style="display: flex; gap: 12px; align-items: center; margin-bottom: 12px; flex-wrap: wrap;">
                    <div style="flex: 1; min-width: 200px;">
                        <label style="font-size: 12px; color: var(--text-secondary); font-weight: 600; display: block; margin-bottom: 4px;">Chat / Group Name:</label>
                        <input type="text" id="wa-import-title" placeholder="e.g. Bangalore Fresher IT Group" style="width: 100%; background: var(--bg-sidebar); border: 1px solid var(--border-subtle); color: var(--text-main); padding: 8px 12px; border-radius: var(--radius-sm); font-size: 13px;">
                    </div>
                    <div>
                        <label style="font-size: 12px; color: var(--text-secondary); font-weight: 600; display: block; margin-bottom: 4px;">Select .txt File:</label>
                        <input type="file" id="wa-import-file" accept=".txt" onchange="handleWhatsAppFileSelect(event)" style="font-size: 12px; color: var(--text-secondary);">
                    </div>
                </div>

                <label style="font-size: 12px; color: var(--text-secondary); font-weight: 600; display: block; margin-bottom: 4px;">Or Paste Exported Chat Text:</label>
                <textarea id="wa-import-text" rows="6" placeholder="Paste exported chat content (with timestamps)..." style="width: 100%; background: var(--bg-sidebar); border: 1px solid var(--border-subtle); color: var(--text-main); padding: 8px 12px; border-radius: var(--radius-sm); font-size: 12px; font-family: monospace;"></textarea>

                <div style="margin-top: 10px; display: flex; justify-content: flex-end; gap: 10px;">
                    <button class="btn btn-secondary btn-sm" onclick="previewWhatsAppImport()">Preview & Filter Chat</button>
                </div>

                <div id="wa-import-results" style="display: none; margin-top: 16px;">
                    <div id="wa-import-stats" style="margin-bottom: 12px; padding: 10px 14px; background: rgba(15, 23, 42, 0.7); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); font-size: 12.5px;"></div>
                    <div id="wa-import-items-list" style="max-height: 250px; overflow-y: auto; display: flex; flex-direction: column; gap: 8px; margin-bottom: 14px;"></div>
                    <div style="display: flex; justify-content: flex-end; gap: 10px;">
                        <button class="btn btn-secondary btn-sm" onclick="closeModal('whatsapp-import-modal')">Cancel</button>
                        <button class="btn btn-primary btn-sm" id="btn-wa-confirm-import" onclick="confirmWhatsAppImport()">Import Selected Items</button>
                    </div>
                </div>
            </div>
        </div>
    </div>"""

if old_tailoring_modal in content:
    content = content.replace(old_tailoring_modal, new_modals, 1)
    print("4. Modals added")
else:
    print("4. old_tailoring_modal not found")

# 5. Replace Unified Inbox JS block
old_inbox_js_start = "        // ----------------- Unified Inbox & Telegram Integration -----------------"
old_inbox_js_end = "        function toggleInboxGuide() {"

idx_start = content.find(old_inbox_js_start)
idx_end = content.find(old_inbox_js_end)

if idx_start != -1 and idx_end != -1:
    new_inbox_js = '''        // ----------------- Unified Inbox & Telegram Integration -----------------

        let inboxDebounceTimer = null;
        let activeQuickFilter = '';

        function debouncedLoadInbox() {
            clearTimeout(inboxDebounceTimer);
            inboxDebounceTimer = setTimeout(loadInbox, 300);
        }

        function setInboxQuickFilter(filterVal) {
            activeQuickFilter = filterVal;
            document.querySelectorAll('.inbox-pill').forEach(btn => btn.classList.remove('active'));
            if (window.event && window.event.target && window.event.target.classList.contains('inbox-pill')) {
                window.event.target.classList.add('active');
            }
            const catSelect = document.getElementById('inbox-filter-category');
            const statusSelect = document.getElementById('inbox-filter-status');

            if (filterVal === 'JOB_LEADS') {
                if (catSelect) catSelect.value = '';
                if (statusSelect) statusSelect.value = '';
            } else if (filterVal === 'ARCHIVED') {
                if (catSelect) catSelect.value = '';
                if (statusSelect) statusSelect.value = 'ARCHIVED';
            } else if (filterVal) {
                if (catSelect) catSelect.value = filterVal;
                if (statusSelect) statusSelect.value = '';
            } else {
                if (catSelect) catSelect.value = '';
                if (statusSelect) statusSelect.value = 'NEW';
            }
            loadInbox();
        }

        async function loadTelegramStatus() {
            try {
                const res = await apiFetch('/api/telegram/status');
                const data = await res.json();

                const badge = document.getElementById('inbox-telegram-badge');
                const warningBox = document.getElementById('inbox-token-warning');
                const botNameEl = document.getElementById('inbox-bot-name');
                const workerStatusEl = document.getElementById('inbox-worker-status');
                const lastSyncedEl = document.getElementById('inbox-last-synced');
                const updatesCountEl = document.getElementById('inbox-updates-count');
                const tokenMaskedEl = document.getElementById('inbox-token-masked');

                if (botNameEl) botNameEl.innerText = `@${data.bot_username || 'CareerOrbitJobAssistantBot'}`;
                if (tokenMaskedEl) tokenMaskedEl.innerText = data.masked_token || 'Not Configured';
                if (updatesCountEl) updatesCountEl.innerText = data.total_updates_processed || 0;

                if (lastSyncedEl) {
                    if (data.last_poll_time) {
                        try {
                            lastSyncedEl.innerText = new Date(data.last_poll_time).toLocaleTimeString('en-IN', {
                                timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true
                            }) + ' IST';
                        } catch (_) {
                            lastSyncedEl.innerText = data.last_poll_time;
                        }
                    } else {
                        lastSyncedEl.innerText = 'Never';
                    }
                }

                if (data.configured) {
                    if (badge) {
                        badge.className = data.running ? 'badge badge-green' : 'badge badge-blue';
                        badge.innerText = `Connected (@${data.bot_username || 'Bot'})`;
                    }
                    if (warningBox) warningBox.style.display = 'none';
                    if (workerStatusEl) {
                        if (data.running) {
                            workerStatusEl.className = 'badge badge-green';
                            workerStatusEl.innerText = 'Polling Active';
                        } else if (data.last_poll_status === 'SUCCESS') {
                            workerStatusEl.className = 'badge badge-blue';
                            workerStatusEl.innerText = 'Connected (Manual Sync)';
                        } else if (data.last_poll_status && data.last_poll_status.startsWith('API_ERROR')) {
                            workerStatusEl.className = 'badge badge-red';
                            workerStatusEl.innerText = data.last_poll_status;
                        } else {
                            workerStatusEl.className = 'badge badge-amber';
                            workerStatusEl.innerText = data.last_poll_status || 'Idle';
                        }
                    }
                } else {
                    if (badge) {
                        badge.className = 'badge badge-amber';
                        badge.innerText = 'Token Not Configured';
                    }
                    if (warningBox) warningBox.style.display = 'block';
                    if (workerStatusEl) {
                        workerStatusEl.className = 'badge badge-secondary';
                        workerStatusEl.innerText = 'Offline (No Token)';
                    }
                }
            } catch (err) {
                console.error('Failed to load telegram status:', err);
                const workerStatusEl = document.getElementById('inbox-worker-status');
                if (workerStatusEl) {
                    workerStatusEl.className = 'badge badge-red';
                    workerStatusEl.innerText = 'Error Checking';
                }
            }
        }

        async function triggerTelegramManualPoll() {
            if (isSyncingTelegram) return;
            const btn = document.getElementById('btn-telegram-poll');
            const origHtml = btn ? btn.innerHTML : '';
            isSyncingTelegram = true;

            if (btn) {
                btn.disabled = true;
                btn.innerHTML = '<span class="spinner" style="display:inline-block;width:12px;height:12px;border:2px solid #fff;border-top-color:transparent;border-radius:50%;animation:spin 0.6s linear infinite;margin-right:6px;"></span> Syncing...';
            }

            try {
                const res = await apiFetch('/api/telegram/poll-now', { method: 'POST' });
                const data = await res.json();

                if (data.status === 'NOT_CONFIGURED') {
                    showToast('Telegram bot token not configured. Set TELEGRAM_BOT_TOKEN in .env', 'warning');
                } else if (data.status === 'SUCCESS') {
                    const proc = data.processed_count || 0;
                    const skipped = data.skipped_count || 0;
                    const rec = data.received_count || proc;
                    if (rec > 0) {
                        showToast(`Telegram sync complete: ${proc} processed, ${skipped} duplicate/skipped.`, 'success');
                    } else {
                        showToast('Telegram sync complete: No new updates pending.', 'info');
                    }
                } else if (data.status === 'ERROR') {
                    showToast(`Sync failed: ${data.error || 'API error'}`, 'error');
                } else {
                    showToast(`Sync finished: ${data.status || 'OK'}`, 'info');
                }

                const lastSyncedEl = document.getElementById('inbox-last-synced');
                if (lastSyncedEl) {
                    lastSyncedEl.innerText = new Date().toLocaleTimeString('en-IN', {
                        timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true
                    }) + ' IST';
                }

                await Promise.all([
                    loadTelegramStatus(),
                    loadInbox(),
                    fetchStats()
                ]);
            } catch (err) {
                showToast(`Sync failed: ${err.message}`, 'error');
            } finally {
                isSyncingTelegram = false;
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = origHtml;
                }
            }
        }

        async function loadInbox() {
            const container = document.getElementById('inbox-messages-list');
            if (!container) return;

            const category = (document.getElementById('inbox-filter-category')?.value || '').trim();
            const status = (document.getElementById('inbox-filter-status')?.value || '').trim();
            const platform = (document.getElementById('inbox-filter-platform')?.value || '').trim();
            const query = (document.getElementById('inbox-search-input')?.value || '').trim();

            let url = `/api/inbox?limit=50`;
            if (activeQuickFilter === 'JOB_LEADS') {
                url += `&is_job_lead=true`;
            } else if (category) {
                url += `&classification=${encodeURIComponent(category)}`;
            }
            if (status) url += `&status=${encodeURIComponent(status)}`;
            if (platform) url += `&channel=${encodeURIComponent(platform)}`;
            if (query) url += `&q=${encodeURIComponent(query)}`;

            try {
                // Fetch stats and list in parallel
                const [statsRes, listRes] = await Promise.all([
                    apiFetch('/api/inbox/stats'),
                    apiFetch(url)
                ]);

                if (statsRes.ok) {
                    const stats = await statsRes.json();
                    if (document.getElementById('stat-inbox-total')) document.getElementById('stat-inbox-total').innerText = stats.total || 0;
                    if (document.getElementById('stat-inbox-jobs')) document.getElementById('stat-inbox-jobs').innerText = stats.job_leads || 0;
                    if (document.getElementById('stat-inbox-prep')) document.getElementById('stat-inbox-prep').innerText = (stats.by_category_group?.prep || 0) + (stats.by_category_group?.practice || 0);
                    if (document.getElementById('stat-inbox-learning')) document.getElementById('stat-inbox-learning').innerText = (stats.by_category_group?.learning || 0) + (stats.by_category_group?.cert || 0);
                    if (document.getElementById('stat-inbox-new')) document.getElementById('stat-inbox-new').innerText = stats.new || 0;
                }

                if (!listRes.ok) throw new Error('Failed to load inbox items');
                const listData = await listRes.json();
                const items = listData.items || [];

                if (!items.length) {
                    container.innerHTML = `
                        <div class="empty-state" style="text-align: center; padding: 36px 20px;">
                            <div style="font-size: 28px; margin-bottom: 8px;">📬</div>
                            <strong style="color: var(--text-main); font-size: 15px;">No messages matching current filter</strong>
                            <p style="font-size: 12.5px; color: var(--text-secondary); margin-top: 4px;">
                                Forward vacancies or interview prep to <code>@CareerOrbitJobAssistantBot</code>, or use "Paste Announcement" / "Import WhatsApp Chat".
                            </p>
                            <div style="margin-top: 12px;">
                                <button class="btn btn-secondary btn-sm" onclick="setInboxQuickFilter('')">Clear Filters</button>
                            </div>
                        </div>
                    `;
                    return;
                }

                container.innerHTML = items.map(renderInboxCard).join('');
            } catch (err) {
                container.innerHTML = `
                    <div class="error-state" style="padding: 24px; text-align: center;">
                        <strong style="color: var(--danger);">Failed to load inbox</strong>
                        <p style="font-size: 12px; color: var(--text-secondary); margin: 6px 0 12px 0;">${escapeHtml(err.message)}</p>
                        <button class="btn btn-secondary btn-sm" onclick="loadInbox()">Retry</button>
                    </div>
                `;
            }
        }

        function renderInboxCard(item) {
            const isJob = Boolean(item.is_job_lead);
            const extracted = item.extracted_data || {};
            const jobParsed = extracted.job_parsed || {};
            const urls = extracted.urls || [];
            const tags = extracted.tech_tags || [];
            const matches = extracted.candidate_matches || [];
            const channel = (item.channel || 'telegram').toLowerCase();

            let classBadgeClass = 'badge-secondary';
            if (item.classification && item.classification.startsWith('Job: Data Analyst')) classBadgeClass = 'badge-blue';
            else if (item.classification && item.classification.startsWith('Job: Data Science')) classBadgeClass = 'badge-purple';
            else if (item.classification && item.classification.startsWith('Job: Software')) classBadgeClass = 'badge-blue';
            else if (item.classification && item.classification.startsWith('Job: Data Engineering')) classBadgeClass = 'badge-cyan';
            else if (item.classification === 'Interview Preparation') classBadgeClass = 'badge-green';
            else if (item.classification === 'Coding Practice') classBadgeClass = 'badge-purple';
            else if (item.classification === 'Technical Learning Materials') classBadgeClass = 'badge-amber';
            else if (item.classification === 'Certifications and Courses') classBadgeClass = 'badge-green';

            let statusBadge = 'badge-amber';
            if (item.status === 'PROCESSED') statusBadge = 'badge-green';
            else if (item.status === 'ARCHIVED') statusBadge = 'badge-secondary';
            else if (item.status === 'DISCARDED') statusBadge = 'badge-red';

            const platformBadge = channel === 'whatsapp'
                ? '<span class="badge" style="background:#059669;color:#fff;font-size:10px;font-weight:600;">WhatsApp</span>'
                : '<span class="badge" style="background:#0284c7;color:#fff;font-size:10px;font-weight:600;">Telegram</span>';

            const senderDisplay = escapeHtml(item.sender_name || item.sender_username || 'Unknown Sender');
            const chatDisplay = item.chat_title ? ` in <em>${escapeHtml(item.chat_title)}</em>` : '';
            const dateStr = item.received_at ? new Date(item.received_at).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', dateStyle: 'short', timeStyle: 'short' }) : '';

            let jobBlock = '';
            if (isJob) {
                const title = item.linked_job_title || jobParsed.title || extracted.title || 'Role Pending';
                const employer = item.linked_job_employer || jobParsed.employer || extracted.employer || 'Employer Pending';
                const loc = jobParsed.location || extracted.location || 'India';
                const appUrl = item.linked_job_url || jobParsed.application_url || extracted.application_url || (urls[0] || '');
                const tier = item.linked_job_match_tier || 'Match Scored';

                jobBlock = `
                    <div style="background: rgba(15, 23, 42, 0.6); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); padding: 12px 14px; margin: 10px 0;">
                        <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; flex-wrap: wrap;">
                            <div>
                                <div style="font-weight: 600; color: var(--text-main); font-size: 13.5px;">${escapeHtml(title)}</div>
                                <div style="color: var(--accent); font-size: 12px;">${escapeHtml(employer)} • ${escapeHtml(loc)}</div>
                            </div>
                            <div style="display: flex; gap: 6px; align-items: center;">
                                <span class="badge badge-amber" style="font-size: 10.5px;">UNVERIFIED</span>
                                <span class="badge badge-secondary" style="font-size: 10.5px;">${escapeHtml(tier)}</span>
                            </div>
                        </div>
                        ${appUrl ? `
                            <div style="margin-top: 8px;">
                                <a href="${escapeHtml(appUrl)}" target="_blank" rel="noopener noreferrer" class="btn btn-secondary btn-sm" style="display: inline-flex; align-items: center; gap: 6px; font-size: 11.5px; padding: 4px 10px;">
                                    <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>
                                    Direct Application Link
                                </a>
                            </div>
                        ` : `
                            <div style="margin-top: 6px; font-size: 11.5px; color: #f87171;">⚠️ No direct application link found in announcement text.</div>
                        `}
                    </div>
                `;
            }

            const isStudyResource = !isJob && (
                item.category_group === 'learning' || item.category_group === 'prep' ||
                item.category_group === 'practice' || item.category_group === 'cert' ||
                (item.classification && (item.classification.includes('Prep') || item.classification.includes('Practice') || item.classification.includes('Learning') || item.classification.includes('Cert')))
            );

            return `
                <div class="card" style="padding: 16px 20px; transition: transform 0.15s ease; border-left: 3px solid ${isJob ? 'var(--primary)' : 'var(--accent)'};">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; flex-wrap: wrap; margin-bottom: 8px;">
                        <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                            ${platformBadge}
                            <span class="badge ${classBadgeClass}" style="font-weight: 600;">${escapeHtml(item.classification)}</span>
                            <span class="badge ${statusBadge}" style="font-size: 10px;">${escapeHtml(item.status)}</span>
                            <span style="font-size: 12px; color: var(--text-secondary);">${senderDisplay}${chatDisplay}</span>
                        </div>
                        <span style="font-size: 11.5px; color: var(--text-muted);">${dateStr}</span>
                    </div>

                    ${jobBlock}

                    <div style="font-size: 12.5px; color: var(--text-main); white-space: pre-wrap; line-height: 1.5; max-height: 180px; overflow-y: auto; background: var(--bg-sidebar); padding: 10px 14px; border-radius: var(--radius-sm); border: 1px solid var(--border-subtle); font-family: inherit;">${escapeHtml(item.raw_text)}</div>

                    ${urls.length ? `
                        <div style="margin-top: 8px; display: flex; gap: 8px; flex-wrap: wrap;">
                            ${urls.map((u, i) => `
                                <a href="${escapeHtml(u)}" target="_blank" rel="noopener noreferrer" style="font-size: 11.5px; color: var(--accent); text-decoration: underline; display: inline-flex; align-items: center; gap: 4px;">
                                    🔗 Link ${i + 1}
                                </a>
                            `).join('')}
                        </div>
                    ` : ''}

                    ${(tags.length || matches.length) ? `
                        <div style="margin-top: 8px; display: flex; gap: 6px; flex-wrap: wrap;">
                            ${tags.map(t => `<span class="badge badge-secondary" style="font-size: 10.5px;">#${escapeHtml(t)}</span>`).join('')}
                            ${matches.map(m => `<span class="badge badge-green" style="font-size: 10.5px;">✓ ${escapeHtml(m)}</span>`).join('')}
                        </div>
                    ` : ''}

                    <div style="display: flex; justify-content: flex-end; align-items: center; gap: 8px; margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--border-subtle); flex-wrap: wrap;">
                        ${!isJob && item.status !== 'DISCARDED' ? `
                            <button class="btn btn-secondary btn-sm" onclick="promoteInboxToJob(${item.id})" style="font-size: 11px;">
                                Promote to Job Lead
                            </button>
                        ` : ''}
                        ${isStudyResource ? `
                            <button class="btn btn-secondary btn-sm" onclick="saveInboxAsLearningResource(${item.id})" style="font-size: 11px; background: rgba(52, 211, 153, 0.15); color: #34d399; border-color: rgba(52, 211, 153, 0.3);">
                                📚 Save to Study Collection
                            </button>
                        ` : ''}
                        ${item.status !== 'PROCESSED' ? `
                            <button class="btn btn-secondary btn-sm" onclick="setInboxItemStatus(${item.id}, 'PROCESSED')" style="font-size: 11px;">
                                Mark Processed
                            </button>
                        ` : ''}
                        ${item.status !== 'ARCHIVED' ? `
                            <button class="btn btn-secondary btn-sm" onclick="setInboxItemStatus(${item.id}, 'ARCHIVED')" style="font-size: 11px;">
                                Archive
                            </button>
                        ` : ''}
                        ${item.status !== 'DISCARDED' ? `
                            <button class="btn btn-danger btn-sm" onclick="setInboxItemStatus(${item.id}, 'DISCARDED')" style="font-size: 11px; padding: 4px 8px;">
                                Discard
                            </button>
                        ` : ''}
                    </div>
                </div>
            `;
        }

        async function setInboxItemStatus(id, newStatus) {
            try {
                const res = await apiFetch(`/api/inbox/${id}/status`, {
                    method: 'PUT',
                    body: JSON.stringify({ status: newStatus })
                });
                if (!res.ok) throw new Error('Status update failed');
                showToast(`Message marked as ${newStatus}`, 'success');
                loadInbox();
                fetchStats();
            } catch (err) {
                showToast(`Error: ${err.message}`, 'error');
            }
        }

        async function promoteInboxToJob(id) {
            try {
                const res = await apiFetch(`/api/inbox/${id}/promote-to-job`, { method: 'POST' });
                if (!res.ok) throw new Error('Failed to promote inbox item to job lead');
                const data = await res.json();
                showToast(`Promoted to Job #${data.job_id}: ${data.lead?.employer} - ${data.lead?.title}`, 'success');
                loadInbox();
                fetchStats();
                loadJobs();
            } catch (err) {
                showToast(`Promotion failed: ${err.message}`, 'error');
            }
        }

        async function saveInboxAsLearningResource(id) {
            try {
                const res = await apiFetch(`/api/inbox/${id}/save-resource`, { method: 'POST' });
                const data = await res.json();
                showToast(`Saved to Study Collection as Resource #${data.resource_id}`, 'success');
                loadInbox();
                fetchStats();
            } catch (err) {
                showToast(`Failed to save resource: ${err.message}`, 'error');
            }
        }

        // Community Import Functions
        function openCommunityImportModal() {
            document.getElementById('comm-import-channel').value = '';
            document.getElementById('comm-import-text').value = '';
            const box = document.getElementById('comm-import-preview-box');
            if (box) {
                box.style.display = 'none';
                box.innerHTML = '';
            }
            document.getElementById('community-import-modal').classList.add('active');
        }

        async function previewCommunityImport() {
            const text = document.getElementById('comm-import-text').value.trim();
            const channel = document.getElementById('comm-import-channel').value.trim() || 'Community Alert';
            const box = document.getElementById('comm-import-preview-box');
            if (!text) {
                showToast('Please paste announcement text.', 'warning');
                return;
            }
            try {
                const res = await apiFetch('/api/community/parse-preview', {
                    method: 'POST',
                    body: JSON.stringify({ raw_text: text, source_channel: channel })
                });
                const data = await res.json();
                box.style.display = 'block';
                box.innerHTML = `
                    <div style="font-size: 13px; font-weight: 600; color: var(--text-main); margin-bottom: 4px;">Extracted Preview:</div>
                    <div style="font-size: 12px; color: var(--text-secondary); line-height: 1.6;">
                        <div><strong>Role:</strong> ${escapeHtml(data.title)}</div>
                        <div><strong>Company:</strong> ${escapeHtml(data.employer)}</div>
                        <div><strong>Location:</strong> ${escapeHtml(data.location)} (${escapeHtml(data.geographic_tier_label || 'India')})</div>
                        <div><strong>Category:</strong> ${escapeHtml(data.priority_label)}</div>
                        <div><strong>Apply URL:</strong> ${data.application_url ? `<a href="${escapeHtml(data.application_url)}" target="_blank" style="color:var(--accent);">${escapeHtml(data.application_url)}</a>` : '<span style="color:#f87171;">None found</span>'}</div>
                        <div><strong>Duplicate Status:</strong> ${data.is_duplicate ? '<span style="color:#f87171;">⚠️ Potential duplicate detected</span>' : '<span style="color:#34d399;">✓ Unique Opportunity</span>'}</div>
                    </div>
                `;
            } catch (err) {
                showToast(`Preview failed: ${err.message}`, 'error');
            }
        }

        async function confirmCommunityImport() {
            const text = document.getElementById('comm-import-text').value.trim();
            const channel = document.getElementById('comm-import-channel').value.trim() || 'Community Alert';
            if (!text) {
                showToast('Please paste announcement text.', 'warning');
                return;
            }
            try {
                const res = await apiFetch('/api/community/import', {
                    method: 'POST',
                    body: JSON.stringify({ raw_text: text, source_channel: channel, allow_duplicate: true })
                });
                const data = await res.json();
                showToast(`Imported Lead #${data.job_id}: ${data.lead?.employer} - ${data.lead?.title}`, 'success');
                closeModal('community-import-modal');
                loadInbox();
                fetchStats();
                loadJobs();
            } catch (err) {
                showToast(`Import failed: ${err.message}`, 'error');
            }
        }

        // WhatsApp Import Functions
        function openWhatsAppImportModal() {
            document.getElementById('wa-import-title').value = '';
            document.getElementById('wa-import-text').value = '';
            document.getElementById('wa-import-file').value = '';
            document.getElementById('wa-import-results').style.display = 'none';
            whatsappPreviewItems = [];
            document.getElementById('whatsapp-import-modal').classList.add('active');
        }

        function handleWhatsAppFileSelect(e) {
            const file = e.target.files[0];
            if (!file) return;
            const reader = new FileReader();
            reader.onload = function(evt) {
                document.getElementById('wa-import-text').value = evt.target.result;
                if (!document.getElementById('wa-import-title').value) {
                    const cleanName = file.name.replace(/\\.txt$/i, '').replace(/WhatsApp Chat - /i, '');
                    document.getElementById('wa-import-title').value = cleanName;
                }
            };
            reader.readAsText(file);
        }

        async function previewWhatsAppImport() {
            const text = document.getElementById('wa-import-text').value.trim();
            const title = document.getElementById('wa-import-title').value.trim() || 'WhatsApp Group Export';
            if (!text) {
                showToast('Please select a .txt file or paste exported chat content.', 'warning');
                return;
            }
            try {
                const res = await apiFetch('/api/whatsapp/parse-preview', {
                    method: 'POST',
                    body: JSON.stringify({ text: text, chat_title: title })
                });
                const data = await res.json();
                whatsappPreviewItems = data.items || [];

                document.getElementById('wa-import-results').style.display = 'block';
                document.getElementById('wa-import-stats').innerHTML = `
                    <div style="font-weight: 600; color: var(--text-main); margin-bottom: 4px;">Chat Analysis Summary:</div>
                    <div style="display: flex; gap: 16px; flex-wrap: wrap; color: var(--text-secondary); font-size: 12px;">
                        <div>Total Messages: <strong>${data.total_messages_parsed || 0}</strong></div>
                        <div>Career Relevant: <strong style="color: #34d399;">${data.career_relevant_count || 0}</strong></div>
                        <div>Job Leads: <strong style="color: #60a5fa;">${data.job_leads_count || 0}</strong></div>
                        <div>Personal Skipped: <strong style="color: var(--text-muted);">${data.personal_skipped_count || 0}</strong></div>
                    </div>
                `;

                const listEl = document.getElementById('wa-import-items-list');
                if (!whatsappPreviewItems.length) {
                    listEl.innerHTML = '<div style="font-size: 12px; color: var(--text-secondary); padding: 12px;">No career or learning opportunities found in this chat excerpt.</div>';
                    return;
                }

                listEl.innerHTML = whatsappPreviewItems.map((item, idx) => `
                    <div style="background: rgba(15, 23, 42, 0.5); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); padding: 8px 12px; font-size: 12px;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                            <label style="display: flex; align-items: center; gap: 6px; cursor: pointer;">
                                <input type="checkbox" id="wa-chk-${idx}" checked style="accent-color: var(--primary);">
                                <span class="badge ${item.is_job_lead ? 'badge-blue' : 'badge-green'}" style="font-size: 10px;">${escapeHtml(item.classification)}</span>
                                <strong style="color: var(--text-main);">${escapeHtml(item.sender)}</strong>
                            </label>
                            <span style="color: var(--text-muted); font-size: 11px;">${escapeHtml(item.timestamp_raw)}</span>
                        </div>
                        <div style="color: var(--text-secondary); white-space: pre-wrap; font-size: 11.5px; max-height: 60px; overflow-y: auto;">${escapeHtml(item.raw_text.slice(0, 180))}</div>
                    </div>
                `).join('');
            } catch (err) {
                showToast(`WhatsApp preview failed: ${err.message}`, 'error');
            }
        }

        async function confirmWhatsAppImport() {
            if (!whatsappPreviewItems.length) {
                showToast('No items available to import.', 'warning');
                return;
            }
            const selectedItems = [];
            whatsappPreviewItems.forEach((item, idx) => {
                const chk = document.getElementById(`wa-chk-${idx}`);
                if (chk && chk.checked) {
                    selectedItems.push(item);
                }
            });

            if (!selectedItems.length) {
                showToast('Please select at least one item to import.', 'warning');
                return;
            }

            const title = document.getElementById('wa-import-title').value.trim() || 'WhatsApp Export';
            try {
                const res = await apiFetch('/api/whatsapp/import', {
                    method: 'POST',
                    body: JSON.stringify({ items: selectedItems, chat_title: title })
                });
                const data = await res.json();
                showToast(`WhatsApp import complete: ${data.imported_inbox} messages ingested (${data.imported_jobs} job leads).`, 'success');
                closeModal('whatsapp-import-modal');
                loadInbox();
                fetchStats();
            } catch (err) {
                showToast(`Import failed: ${err.message}`, 'error');
            }
        }

'''
    content = content[:idx_start] + new_inbox_js + content[idx_end:]
    print("5. Inbox JS updated successfully")
else:
    print(f"5. Failed to find markers: start={idx_start}, end={idx_end}")

html_path.write_text(content, encoding="utf-8")
print("All index.html updates completed successfully!")
