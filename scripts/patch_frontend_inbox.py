"""Patch script to upgrade index.html with real data ingestion diagnostics and truthful provenance."""
import re

html_path = 'careerorbit/web/static/index.html'
with open(html_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update Connection Details Strip and add Ingestion Diagnostics Panel
old_strip = """                <!-- Connection Details Strip -->
                <div id="inbox-connection-strip" style="margin-top: 16px; padding-top: 12px; border-top: 1px solid var(--border-subtle); display: flex; flex-wrap: wrap; gap: 20px; font-size: 12px; color: var(--text-secondary);">
                    <div>Bot Handle: <strong id="inbox-bot-name" style="color: var(--accent);">@CareerOrbitJobAssistantBot</strong></div>
                    <div>Worker State: <span id="inbox-worker-status" class="badge badge-secondary" style="font-size: 11px;">Checking...</span></div>
                    <div>Last Synced: <span id="inbox-last-synced" style="color: var(--text-main);">Never</span></div>
                    <div>Processed Updates: <span id="inbox-updates-count" style="color: var(--text-main);">0</span></div>
                    <div>Active Token: <span id="inbox-token-masked" style="font-family: monospace; color: var(--text-secondary);">--</span></div>
                </div>"""

new_strip = """                <!-- Connection Details Strip -->
                <div id="inbox-connection-strip" style="margin-top: 16px; padding-top: 12px; border-top: 1px solid var(--border-subtle); display: flex; flex-wrap: wrap; gap: 20px; font-size: 12px; color: var(--text-secondary); align-items: center;">
                    <div>Bot Handle: <strong id="inbox-bot-name" style="color: var(--accent);">@CareerOrbitJobAssistantBot</strong></div>
                    <div>Worker State: <span id="inbox-worker-status" class="badge badge-secondary" style="font-size: 11px;">Checking...</span></div>
                    <div>Channel State: <span id="inbox-channel-status" class="badge badge-secondary" style="font-size: 11px;">Checking Channels...</span></div>
                    <div>Last Synced: <span id="inbox-last-synced" style="color: var(--text-main);">Never</span></div>
                    <div>Processed Updates: <span id="inbox-updates-count" style="color: var(--text-main);">0</span></div>
                    <div>Active Token: <span id="inbox-token-masked" style="font-family: monospace; color: var(--text-secondary);">--</span></div>
                    <button class="btn btn-secondary btn-sm" onclick="toggleSyncPanel()" style="font-size: 11px; padding: 2px 8px; margin-left: auto;">
                        ⚙️ View Diagnostics
                    </button>
                </div>

                <!-- Detailed Synchronization & Sources Diagnostic Panel (Expandable) -->
                <div id="inbox-sync-panel" style="display: none; margin-top: 16px; padding: 16px; background: rgba(15, 23, 42, 0.85); border: 1px solid var(--border-subtle); border-radius: var(--radius-md);">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; flex-wrap: wrap; gap: 10px;">
                        <h4 style="margin: 0; font-size: 14px; font-weight: 700; color: var(--text-main); display: flex; align-items: center; gap: 8px;">
                            <span>📡 Real Data Ingestion & Source Observability</span>
                            <span id="sync-panel-overall-badge" class="badge badge-green">Operational</span>
                        </h4>
                        <button class="btn btn-secondary btn-sm" onclick="loadTelegramStatus()" style="font-size: 11px;">
                            ↻ Refresh Status
                        </button>
                    </div>

                    <!-- 3 Distinction Cards Grid -->
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; margin-bottom: 16px;">
                        <!-- Card 1: Telegram Bot Connection -->
                        <div style="background: var(--bg-sidebar); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); padding: 12px 14px;">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                                <strong style="font-size: 12.5px; color: #38bdf8;">🤖 Telegram Bot Authentication</strong>
                                <span id="diag-bot-auth-badge" class="badge badge-green">Connected</span>
                            </div>
                            <div style="font-size: 12px; color: var(--text-secondary); line-height: 1.5;">
                                <div>Bot User: <strong id="diag-bot-username" style="color: var(--text-main);">@CareerOrbitJobAssistantBot</strong></div>
                                <div>Worker Status: <span id="diag-worker-state">Polling Active</span></div>
                                <div>Last Polled: <span id="diag-last-poll">--</span></div>
                                <div>Updates Processed: <span id="diag-updates-count">0</span></div>
                            </div>
                        </div>

                        <!-- Card 2: Telegram Channel Ingestion -->
                        <div style="background: var(--bg-sidebar); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); padding: 12px 14px;">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                                <strong style="font-size: 12.5px; color: #60a5fa;">📢 Channel Ingestion Status</strong>
                                <span id="diag-channel-state-badge" class="badge badge-secondary">--</span>
                            </div>
                            <div style="font-size: 12px; color: var(--text-secondary); line-height: 1.5;">
                                <div>Configured Channels: <strong id="diag-channels-count" style="color: var(--text-main);">0</strong></div>
                                <div>Active Accessible: <span id="diag-accessible-channels" style="color: #34d399;">0</span></div>
                                <div style="margin-top: 4px; font-size: 11px; color: #fbbf24; border-top: 1px dashed var(--border-subtle); padding-top: 4px;">
                                    ⚠️ <strong>Distinction:</strong> Bot connection proves API token validity. Receiving channel broadcasts requires adding <code>@CareerOrbitJobAssistantBot</code> as an <strong>Administrator</strong>.
                                </div>
                            </div>
                        </div>

                        <!-- Card 3: WhatsApp Chat Export Mode -->
                        <div style="background: var(--bg-sidebar); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); padding: 12px 14px;">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                                <strong style="font-size: 12.5px; color: #34d399;">💬 WhatsApp Ingestion Mode</strong>
                                <span class="badge" style="background:#059669;color:#fff;font-size:10px;">Export Parser</span>
                            </div>
                            <div style="font-size: 12px; color: var(--text-secondary); line-height: 1.5;">
                                <div>Ingestion Method: <strong>Manual .txt Chat Export</strong></div>
                                <div>Automated Polling: <span style="color: var(--text-muted);">Disabled (Privacy & ToS Compliant)</span></div>
                                <div>Imported Groups: <strong id="diag-wa-count" style="color: var(--text-main);">0</strong></div>
                                <div style="margin-top: 4px; font-size: 11px; color: var(--text-muted); border-top: 1px dashed var(--border-subtle); padding-top: 4px;">
                                    🔒 Ingestion preserves full message provenance, timestamps, line numbers, and deduplication without violating WhatsApp ToS.
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Configured Telegram Channels & Groups Section -->
                    <div style="margin-bottom: 16px;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px;">
                            <strong style="font-size: 12.5px; color: var(--text-main);">Configured Telegram Channels & Groups</strong>
                            <div style="display: flex; gap: 6px; align-items: center;">
                                <input type="text" id="tg-reg-chat-id" placeholder="@channel_username or -100..." style="background: var(--bg-sidebar); border: 1px solid var(--border-subtle); color: var(--text-main); padding: 5px 10px; border-radius: var(--radius-sm); font-size: 11.5px; width: 190px;">
                                <button class="btn btn-secondary btn-sm" onclick="registerTelegramChannelAction()" style="font-size: 11px; padding: 5px 10px;">
                                    + Check & Add Channel
                                </button>
                            </div>
                        </div>
                        <div id="diag-channels-table-container">
                            <!-- Populated dynamically -->
                            <div style="font-size: 12px; color: var(--text-muted); padding: 10px; text-align: center; background: var(--bg-sidebar); border-radius: var(--radius-sm);">
                                Loading configured channels...
                            </div>
                        </div>
                    </div>

                    <!-- Channel Setup Instructions Drawer -->
                    <div style="background: rgba(30, 41, 59, 0.4); border: 1px dashed var(--border-subtle); border-radius: var(--radius-sm); padding: 10px 14px; font-size: 11.5px; color: var(--text-secondary); line-height: 1.5;">
                        <strong style="color: var(--text-main);">📌 How to add @CareerOrbitJobAssistantBot to Channels & Groups:</strong>
                        <ul style="margin: 4px 0 0 16px; padding: 0;">
                            <li><strong>Broadcast Channels:</strong> Open Channel Settings → Administrators → Add Administrator → Search <code>@CareerOrbitJobAssistantBot</code> → Ensure <em>Post Messages</em> right is granted.</li>
                            <li><strong>Discussion Groups:</strong> If Telegram Privacy Mode is enabled on your bot, the bot will only see commands and mentions. Either promote the bot to Administrator in the group, or message <a href="https://t.me/BotFather" target="_blank" rel="noopener" style="color: #60a5fa;">@BotFather</a> with <code>/setprivacy → Disable</code>.</li>
                            <li><strong>Historical Posts:</strong> By design, Telegram Bot API only receives posts sent <em>after</em> the bot is added. Historical messages cannot be backfilled via the Bot API.</li>
                        </ul>
                    </div>
                </div>"""

# Normalize CRLF for matching
content_norm = content.replace('\r\n', '\n')
old_strip_norm = old_strip.replace('\r\n', '\n')
new_strip_norm = new_strip.replace('\r\n', '\n')

assert old_strip_norm in content_norm, "old_strip not found in content"
content_norm = content_norm.replace(old_strip_norm, new_strip_norm, 1)

# 2. Update Job Card Apply link
old_card_apply = """                            ${safeOfficial ? `
                                <a class="btn btn-sm ${j.verification_status === 'VERIFIED_OPEN' ? 'btn-success' : 'btn-secondary'}" href="${escapeHtml(safeOfficial)}" target="_blank" rel="noopener noreferrer">
                                    ${j.verification_status === 'VERIFIED_OPEN' ? 'Open Official Application ↗' : 'Unverified Application Destination ↗'}
                                </a>
                                <small style="width:100%;overflow-wrap:anywhere;color:var(--text-muted);">${escapeHtml(safeOfficial)}</small>
                            ` : '<span class="badge badge-gray">Application URL unverified</span>'}"""

new_card_apply = """                            ${safeOfficial ? `
                                ${j.verification_status === 'VERIFIED_OPEN' ? `
                                    <a class="btn btn-sm btn-success" href="${escapeHtml(safeOfficial)}" target="_blank" rel="noopener noreferrer">
                                        Open Official Application ↗
                                    </a>
                                ` : (j.verification_status === 'VERIFIED_CLOSED' ? `
                                    <span class="badge badge-red" style="padding: 6px 10px;">⚠️ Vacancy Closed / Inactive</span>
                                    <a class="btn btn-secondary btn-sm" href="https://www.google.com/search?q=${encodeURIComponent(j.employer + ' ' + j.title + ' careers')}" target="_blank" rel="noopener noreferrer">Search Careers ↗</a>
                                ` : `
                                    <a class="btn btn-sm btn-secondary" href="${escapeHtml(safeOfficial)}" target="_blank" rel="noopener noreferrer" style="color: #fbbf24; border-color: #f59e0b;">
                                        ⚠️ Unverified Lead Link ↗
                                    </a>
                                `)}
                                <small style="width:100%;overflow-wrap:anywhere;color:var(--text-muted);">${escapeHtml(safeOfficial)}</small>
                            ` : '<span class="badge badge-gray">Application URL unverified</span>'}"""

old_card_norm = old_card_apply.replace('\r\n', '\n')
new_card_norm = new_card_apply.replace('\r\n', '\n')
assert old_card_norm in content_norm, "old_card_apply not found"
content_norm = content_norm.replace(old_card_norm, new_card_norm, 1)

# 3. Update Modal direct application link
old_modal_link = '&nbsp; ${safeOff ? `<a href="${escapeHtml(safeOff)}" target="_blank" rel="noopener noreferrer">Direct application ↗</a>` : \'<span>Direct application URL unverified</span>\'}'
new_modal_link = '&nbsp; ${job.verification_status === \'VERIFIED_OPEN\' && safeOff ? `<a href="${escapeHtml(safeOff)}" target="_blank" rel="noopener noreferrer" class="btn btn-sm btn-primary" style="display:inline-flex;align-items:center;gap:4px;">Official Application ↗</a>` : (job.verification_status === \'VERIFIED_CLOSED\' ? `<span class="badge badge-red" style="font-size:11px;">⚠️ Vacancy Closed / Link Inactive</span>` : (safeOff ? `<a href="${escapeHtml(safeOff)}" target="_blank" rel="noopener noreferrer" class="btn btn-sm btn-secondary" style="color:#fbbf24;border-color:#f59e0b;display:inline-flex;align-items:center;gap:4px;">⚠️ Unverified Community Link ↗</a>` : \'<span>Application URL unverified</span>\'))}'
assert old_modal_link in content_norm, "old_modal_link not found"
content_norm = content_norm.replace(old_modal_link, new_modal_link, 1)

# 4. Replace renderInboxCard with truthful provenance and verified link distinctions
old_render_card_start = "        function renderInboxCard(item) {"
old_render_card_end = "        async function setInboxItemStatus(id, newStatus) {"

new_render_card = """        function renderInboxCard(item) {
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
                ? '<span class="badge" style="background:#059669;color:#fff;font-size:10px;font-weight:600;">WhatsApp Export</span>'
                : '<span class="badge" style="background:#0284c7;color:#fff;font-size:10px;font-weight:600;">Telegram Bot API</span>';

            const senderDisplay = escapeHtml(item.sender_name || item.sender_username || 'Unknown Sender');
            const chatDisplay = item.chat_title ? ` in <em>${escapeHtml(item.chat_title)}</em>` : '';
            const dateStr = item.received_at ? new Date(item.received_at).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', dateStyle: 'short', timeStyle: 'short' }) : '';

            // Truthful Provenance Block
            const provenanceBlock = channel === 'whatsapp' ? `
                <div style="margin-bottom: 10px; padding: 6px 12px; background: rgba(5, 150, 105, 0.12); border: 1px solid rgba(5, 150, 105, 0.25); border-radius: var(--radius-sm); font-size: 11.5px; color: var(--text-secondary); display: flex; flex-wrap: wrap; gap: 8px; align-items: center;">
                    <span style="font-weight: 700; color: #34d399;">📄 WhatsApp Chat Export (.txt)</span>
                    <span>•</span>
                    <span>Group: <strong style="color: var(--text-main);">${escapeHtml(item.chat_title || 'Export')}</strong></span>
                    <span>•</span>
                    <span>Sender: <strong style="color: var(--text-main);">${escapeHtml(item.sender_name || 'Admin')}</strong></span>
                    ${extracted.timestamp_raw ? `<span>•</span><span>Export Timestamp: <strong style="color: var(--text-main);">${escapeHtml(extracted.timestamp_raw)}</strong></span>` : ''}
                    ${item.message_id ? `<span>•</span><span>Line: #${item.message_id}</span>` : ''}
                </div>
            ` : `
                <div style="margin-bottom: 10px; padding: 6px 12px; background: rgba(2, 132, 199, 0.12); border: 1px solid rgba(2, 132, 199, 0.25); border-radius: var(--radius-sm); font-size: 11.5px; color: var(--text-secondary); display: flex; flex-wrap: wrap; gap: 8px; align-items: center;">
                    <span style="font-weight: 700; color: #38bdf8;">🤖 Telegram Bot API (@CareerOrbitJobAssistantBot)</span>
                    <span>•</span>
                    <span>Chat: <strong style="color: var(--text-main);">${escapeHtml(item.chat_title || item.chat_id || 'Direct')}</strong></span>
                    <span>•</span>
                    <span>Sender: <strong style="color: var(--text-main);">${escapeHtml(item.sender_name || item.sender_username || 'User')}</strong></span>
                    ${item.message_id ? `<span>•</span><span>Msg ID: #${item.message_id}</span>` : ''}
                </div>
            `;

            let jobBlock = '';
            if (isJob) {
                const title = item.linked_job_title || jobParsed.title || extracted.title || 'Role Pending';
                const employer = item.linked_job_employer || jobParsed.employer || extracted.employer || 'Employer Pending';
                const loc = jobParsed.location || extracted.location || 'India';
                const appUrl = item.linked_job_url || jobParsed.application_url || extracted.application_url || (urls[0] || '');
                const tier = item.linked_job_match_tier || 'Match Scored';
                const verStatus = item.linked_job_verification_status || (jobParsed && jobParsed.verification_status) || 'UNVERIFIED';

                let actionLinkHtml = '';
                if (verStatus === 'VERIFIED_OPEN' && appUrl) {
                    actionLinkHtml = `
                        <div style="margin-top: 8px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
                            <a href="${escapeHtml(appUrl)}" target="_blank" rel="noopener noreferrer" class="btn btn-primary btn-sm" style="display: inline-flex; align-items: center; gap: 6px; font-size: 11.5px; padding: 5px 12px; background: #059669; border-color: #047857;">
                                <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>
                                ✓ Official Direct Application ↗
                            </a>
                            <span class="badge badge-green" style="font-size: 10.5px;">✓ Verified Open</span>
                        </div>
                    `;
                } else if (verStatus === 'VERIFIED_CLOSED' && appUrl) {
                    actionLinkHtml = `
                        <div style="margin-top: 8px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
                            <span class="badge badge-red" style="font-size: 11px; padding: 4px 10px; display: inline-flex; align-items: center; gap: 5px;">
                                ⚠️ Broken / Closed Application Link (HTTP 404)
                            </span>
                            <a href="https://www.google.com/search?q=${encodeURIComponent(employer + ' ' + title + ' careers')}" target="_blank" rel="noopener noreferrer" class="btn btn-secondary btn-sm" style="font-size: 11px; padding: 4px 10px;">
                                🔍 Search Employer Careers ↗
                            </a>
                        </div>
                    `;
                } else if (appUrl) {
                    actionLinkHtml = `
                        <div style="margin-top: 8px;">
                            <div style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
                                <a href="${escapeHtml(appUrl)}" target="_blank" rel="noopener noreferrer" class="btn btn-secondary btn-sm" style="display: inline-flex; align-items: center; gap: 6px; font-size: 11.5px; padding: 4px 10px; border-color: #f59e0b; color: #fbbf24;">
                                    <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>
                                    ⚠️ Unverified Community Link ↗
                                </a>
                                <span class="badge badge-amber" style="font-size: 10.5px;">UNVERIFIED LEAD</span>
                            </div>
                            <div style="font-size: 11px; color: var(--text-muted); margin-top: 5px;">
                                ⚠️ Unconfirmed community lead. Verify employer vacancy authenticity before submitting personal details.
                            </div>
                        </div>
                    `;
                } else {
                    actionLinkHtml = `
                        <div style="margin-top: 6px; font-size: 11.5px; color: #f87171;">⚠️ No direct application link found in announcement text.</div>
                        <a href="https://www.google.com/search?q=${encodeURIComponent(employer + ' ' + title + ' careers')}" target="_blank" rel="noopener noreferrer" class="btn btn-secondary btn-sm" style="margin-top: 6px; font-size: 11px;">🔍 Search Official Careers ↗</a>
                    `;
                }

                jobBlock = `
                    <div style="background: rgba(15, 23, 42, 0.6); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); padding: 12px 14px; margin: 10px 0;">
                        <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; flex-wrap: wrap;">
                            <div>
                                <div style="font-weight: 600; color: var(--text-main); font-size: 13.5px;">${escapeHtml(title)}</div>
                                <div style="color: var(--accent); font-size: 12px;">${escapeHtml(employer)} • ${escapeHtml(loc)}</div>
                            </div>
                            <div style="display: flex; gap: 6px; align-items: center;">
                                ${renderVerificationBadge(verStatus)}
                                <span class="badge badge-secondary" style="font-size: 10.5px;">${escapeHtml(tier)}</span>
                            </div>
                        </div>
                        ${actionLinkHtml}
                    </div>
                `;
            }

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

                    ${provenanceBlock}

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
                                💼 Promote to Job Lead
                            </button>
                        ` : ''}
                        ${!isJob ? `
                            <button class="btn btn-secondary btn-sm" onclick="saveInboxAsLearningResource(${item.id})" style="font-size: 11px; background: rgba(52, 211, 153, 0.15); color: #34d399; border-color: rgba(52, 211, 153, 0.3);">
                                📚 Save to Study Collection
                            </button>
                        ` : ''}
                        ${item.status !== 'PROCESSED' && item.status !== 'DISCARDED' ? `
                            <button class="btn btn-secondary btn-sm" onclick="setInboxItemStatus(${item.id}, 'PROCESSED')" style="font-size: 11px;">
                                ✓ Mark Processed
                            </button>
                        ` : ''}
                        ${item.status !== 'NEW' ? `
                            <button class="btn btn-secondary btn-sm" onclick="setInboxItemStatus(${item.id}, 'NEW')" style="font-size: 11px;">
                                ↺ Reopen as NEW
                            </button>
                        ` : ''}
                        ${item.status !== 'ARCHIVED' && item.status !== 'DISCARDED' ? `
                            <button class="btn btn-secondary btn-sm" onclick="setInboxItemStatus(${item.id}, 'ARCHIVED')" style="font-size: 11px;">
                                📁 Archive
                            </button>
                        ` : ''}
                        ${item.status !== 'DISCARDED' ? `
                            <button class="btn btn-danger btn-sm" onclick="setInboxItemStatus(${item.id}, 'DISCARDED')" style="font-size: 11px; padding: 4px 8px;">
                                🗑️ Discard
                            </button>
                        ` : `
                            <button class="btn btn-danger btn-sm" onclick="deleteInboxItemPermanently(${item.id})" style="font-size: 11px; padding: 4px 8px;">
                                ❌ Delete Permanently
                            </button>
                        `}
                    </div>
                </div>
            `;
        }
"""

card_pattern = re.compile(re.escape(old_render_card_start) + ".*?" + re.escape(old_render_card_end), re.DOTALL)
assert card_pattern.search(content_norm), "card_pattern not matched in content"
content_norm = card_pattern.sub(new_render_card.strip() + "\n\n" + old_render_card_end, content_norm, count=1)

# 5. Add JavaScript Diagnostic functions and enhanced loadTelegramStatus
old_status_start = "        async function loadTelegramStatus() {"
old_status_end = "        async function triggerTelegramManualPoll() {"

new_status_funcs = """        function toggleSyncPanel() {
            const panel = document.getElementById('inbox-sync-panel');
            if (panel) {
                panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
            }
        }

        async function loadTelegramStatus() {
            try {
                const [tgRes, commRes, waRes] = await Promise.all([
                    apiFetch('/api/telegram/status'),
                    apiFetch('/api/community/sources'),
                    apiFetch('/api/whatsapp/status').catch(() => null)
                ]);
                const data = await tgRes.json();
                const commData = commRes.ok ? await commRes.json() : { sources: [] };
                const waData = waRes && waRes.ok ? await waRes.json() : { sources: [] };

                const badge = document.getElementById('inbox-telegram-badge');
                const warningBox = document.getElementById('inbox-token-warning');
                const botNameEl = document.getElementById('inbox-bot-name');
                const workerStatusEl = document.getElementById('inbox-worker-status');
                const channelStatusEl = document.getElementById('inbox-channel-status');
                const lastSyncedEl = document.getElementById('inbox-last-synced');
                const updatesCountEl = document.getElementById('inbox-updates-count');
                const tokenMaskedEl = document.getElementById('inbox-token-masked');

                // Diagnostics panel elements
                const diagBotUsername = document.getElementById('diag-bot-username');
                const diagBotAuthBadge = document.getElementById('diag-bot-auth-badge');
                const diagWorkerState = document.getElementById('diag-worker-state');
                const diagLastPoll = document.getElementById('diag-last-poll');
                const diagUpdatesCount = document.getElementById('diag-updates-count');
                const diagChannelStateBadge = document.getElementById('diag-channel-state-badge');
                const diagChannelsCount = document.getElementById('diag-channels-count');
                const diagAccessibleChannels = document.getElementById('diag-accessible-channels');
                const diagWaCount = document.getElementById('diag-wa-count');

                if (botNameEl) botNameEl.innerText = `@${data.bot_username || 'CareerOrbitJobAssistantBot'}`;
                if (diagBotUsername) diagBotUsername.innerText = `@${data.bot_username || 'CareerOrbitJobAssistantBot'}`;
                if (tokenMaskedEl) tokenMaskedEl.innerText = data.masked_token || 'Not Configured';
                if (updatesCountEl) updatesCountEl.innerText = data.total_updates_processed || 0;
                if (diagUpdatesCount) diagUpdatesCount.innerText = data.total_updates_processed || 0;

                const pollTimeStr = data.last_poll_time ? new Date(data.last_poll_time).toLocaleTimeString('en-IN', {
                    timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true
                }) + ' IST' : 'Never';
                if (lastSyncedEl) lastSyncedEl.innerText = pollTimeStr;
                if (diagLastPoll) diagLastPoll.innerText = pollTimeStr;

                if (diagWorkerState) {
                    diagWorkerState.innerText = data.running ? 'Polling Active (5s)' : (data.last_poll_status || 'Idle');
                }

                // Channel ingestion summary
                const chSummary = data.channel_summary || {};
                const tgChannels = (commData.sources || []).filter(s => s.source_type === 'telegram_channel' || s.source_type === 'telegram_group');
                const waSources = (commData.sources || []).filter(s => s.source_type === 'whatsapp_chat_export');

                if (diagChannelsCount) diagChannelsCount.innerText = tgChannels.length;
                if (diagAccessibleChannels) diagAccessibleChannels.innerText = tgChannels.filter(c => c.status === 'ACTIVE').length;
                if (diagWaCount) diagWaCount.innerText = waSources.length;

                if (channelStatusEl) {
                    if (data.channel_ingestion_working) {
                        channelStatusEl.className = 'badge badge-green';
                        channelStatusEl.innerText = `${chSummary.active_accessible || tgChannels.length} Channels Active`;
                    } else if (tgChannels.length > 0) {
                        channelStatusEl.className = 'badge badge-amber';
                        channelStatusEl.innerText = 'Admin Rights Needed';
                    } else {
                        channelStatusEl.className = 'badge badge-secondary';
                        channelStatusEl.innerText = 'No Channels Registered';
                    }
                }

                if (diagChannelStateBadge) {
                    if (data.channel_ingestion_working) {
                        diagChannelStateBadge.className = 'badge badge-green';
                        diagChannelStateBadge.innerText = 'Active Reception';
                    } else if (tgChannels.length > 0) {
                        diagChannelStateBadge.className = 'badge badge-amber';
                        diagChannelStateBadge.innerText = 'Permissions Required';
                    } else {
                        diagChannelStateBadge.className = 'badge badge-secondary';
                        diagChannelStateBadge.innerText = 'Not Configured';
                    }
                }

                if (data.configured) {
                    if (badge) {
                        badge.className = data.running ? 'badge badge-green' : 'badge badge-blue';
                        badge.innerText = `Connected (@${data.bot_username || 'Bot'})`;
                    }
                    if (diagBotAuthBadge) {
                        diagBotAuthBadge.className = 'badge badge-green';
                        diagBotAuthBadge.innerText = 'Authenticated';
                    }
                    if (warningBox) warningBox.style.display = 'none';
                    if (workerStatusEl) {
                        if (data.running) {
                            workerStatusEl.className = 'badge badge-green';
                            workerStatusEl.innerText = 'Polling Active';
                        } else if (data.last_poll_status === 'SUCCESS') {
                            workerStatusEl.className = 'badge badge-blue';
                            workerStatusEl.innerText = 'Connected (Manual Sync)';
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
                    if (diagBotAuthBadge) {
                        diagBotAuthBadge.className = 'badge badge-red';
                        diagBotAuthBadge.innerText = 'Unconfigured';
                    }
                    if (warningBox) warningBox.style.display = 'block';
                    if (workerStatusEl) {
                        workerStatusEl.className = 'badge badge-secondary';
                        workerStatusEl.innerText = 'Offline (No Token)';
                    }
                }

                // Render configured channels table
                renderChannelsTable(tgChannels);

            } catch (err) {
                console.error('Failed to load telegram status:', err);
                const workerStatusEl = document.getElementById('inbox-worker-status');
                if (workerStatusEl) {
                    workerStatusEl.className = 'badge badge-red';
                    workerStatusEl.innerText = 'Error Checking';
                }
            }
        }

        function renderChannelsTable(channels) {
            const container = document.getElementById('diag-channels-table-container');
            if (!container) return;

            if (!channels || !channels.length) {
                container.innerHTML = `
                    <div style="font-size: 12px; color: var(--text-muted); padding: 12px; text-align: center; background: var(--bg-sidebar); border-radius: var(--radius-sm);">
                        No Telegram channels or groups registered yet. Enter <code>@channel_username</code> above to test access.
                    </div>
                `;
                return;
            }

            container.innerHTML = `
                <div style="overflow-x: auto;">
                    <table style="width: 100%; border-collapse: collapse; font-size: 12px; background: var(--bg-sidebar); border-radius: var(--radius-sm);">
                        <thead>
                            <tr style="border-bottom: 1px solid var(--border-subtle); text-align: left; color: var(--text-secondary);">
                                <th style="padding: 8px 10px;">Source Name / Chat ID</th>
                                <th style="padding: 8px 10px;">Type</th>
                                <th style="padding: 8px 10px;">Status</th>
                                <th style="padding: 8px 10px;">Diagnosis & Guidance</th>
                                <th style="padding: 8px 10px; text-align: right;">Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${channels.map(c => `
                                <tr style="border-bottom: 1px solid var(--border-subtle);">
                                    <td style="padding: 8px 10px;">
                                        <div style="font-weight: 600; color: var(--text-main);">${escapeHtml(c.source_name || c.chat_id)}</div>
                                        <div style="font-size: 11px; color: var(--text-muted); font-family: monospace;">${escapeHtml(c.chat_id)}</div>
                                    </td>
                                    <td style="padding: 8px 10px;">
                                        <span class="badge badge-secondary" style="font-size: 10px;">${escapeHtml(c.source_type)}</span>
                                    </td>
                                    <td style="padding: 8px 10px;">
                                        <span class="badge ${c.status === 'ACTIVE' ? 'badge-green' : 'badge-amber'}" style="font-size: 10px;">
                                            ${escapeHtml(c.status)}
                                        </span>
                                    </td>
                                    <td style="padding: 8px 10px; font-size: 11px; color: var(--text-secondary); max-width: 320px;">
                                        ${escapeHtml(c.last_error || 'Access verified.')}
                                    </td>
                                    <td style="padding: 8px 10px; text-align: right; white-space: nowrap;">
                                        <button class="btn btn-secondary btn-sm" onclick="recheckCommunitySourceAction(${c.id})" style="font-size: 10px; padding: 3px 6px;">
                                            ↻ Re-check
                                        </button>
                                        <button class="btn btn-danger btn-sm" onclick="deleteCommunitySourceAction(${c.id})" style="font-size: 10px; padding: 3px 6px; margin-left: 4px;">
                                            ✕ Remove
                                        </button>
                                    </td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            `;
        }

        async function registerTelegramChannelAction() {
            const input = document.getElementById('tg-reg-chat-id');
            const chatId = input ? input.value.trim() : '';
            if (!chatId) {
                showToast('Please enter a channel username (@channel) or numeric ID', 'warning');
                return;
            }
            try {
                const res = await apiFetch('/api/community/sources/register-telegram', {
                    method: 'POST',
                    body: JSON.stringify({ chat_id: chatId })
                });
                const data = await res.json();
                if (data.status === 'SUCCESS') {
                    const check = data.access_check || {};
                    if (check.accessible && check.can_receive_messages) {
                        showToast(`Channel ${check.chat_title || chatId} registered successfully!`, 'success');
                    } else {
                        showToast(`Channel added: ${check.diagnosis || 'Permissions required'}`, 'warning');
                    }
                    if (input) input.value = '';
                    loadTelegramStatus();
                } else {
                    showToast(`Registration failed: ${data.detail || 'Error'}`, 'error');
                }
            } catch (err) {
                showToast(`Error registering channel: ${err.message}`, 'error');
            }
        }

        async function recheckCommunitySourceAction(sourceId) {
            try {
                const res = await apiFetch(`/api/community/sources/${sourceId}/recheck`, { method: 'POST' });
                const data = await res.json();
                if (data.status === 'SUCCESS') {
                    showToast(`Channel re-checked: ${data.updated_status}`, 'info');
                    loadTelegramStatus();
                } else {
                    showToast('Re-check failed', 'error');
                }
            } catch (err) {
                showToast(`Re-check failed: ${err.message}`, 'error');
            }
        }

        async function deleteCommunitySourceAction(sourceId) {
            if (!confirm('Remove this channel from CareerOrbit AI?')) return;
            try {
                const res = await apiFetch(`/api/community/sources/${sourceId}`, { method: 'DELETE' });
                if (!res.ok) throw new Error('Delete failed');
                showToast('Channel removed', 'success');
                loadTelegramStatus();
            } catch (err) {
                showToast(`Error: ${err.message}`, 'error');
            }
        }

        async function deleteInboxItemPermanently(id) {
            if (!confirm('Are you sure you want to permanently delete this message from the database?')) return;
            try {
                const res = await apiFetch(`/api/inbox/${id}`, { method: 'DELETE' });
                if (!res.ok) throw new Error('Delete failed');
                showToast('Message deleted permanently', 'success');
                loadInbox();
                fetchStats();
            } catch (err) {
                showToast(`Delete failed: ${err.message}`, 'error');
            }
        }
"""

status_pattern = re.compile(re.escape(old_status_start) + ".*?" + re.escape(old_status_end), re.DOTALL)
assert status_pattern.search(content_norm), "status_pattern not matched in content"
content_norm = status_pattern.sub(new_status_funcs.strip() + "\n\n" + old_status_end, content_norm, count=1)

# Write back preserving CRLF
with open(html_path, 'w', encoding='utf-8', newline='\r\n') as f:
    f.write(content_norm)

print("Successfully patched index.html with real data ingestion diagnostics and truthful provenance!")
