"""Script to patch careerorbit/web/static/index.html with upgraded Telegram Ingestion Observability,
Channel Registration table, and Telegram Desktop Export Modal.
"""
from pathlib import Path

html_path = Path("careerorbit/web/static/index.html")
content = html_path.read_text(encoding="utf-8")

# 1. Add Telegram Export button next to Import WhatsApp Chat
target_buttons = """                        <button class="btn btn-secondary btn-sm" onclick="openWhatsAppImportModal()" style="display: inline-flex; align-items: center; gap: 6px;">
                            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"></path></svg>
                            Import WhatsApp Chat
                        </button>"""

replacement_buttons = """                        <button class="btn btn-secondary btn-sm" onclick="openWhatsAppImportModal()" style="display: inline-flex; align-items: center; gap: 6px;">
                            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"></path></svg>
                            Import WhatsApp Chat
                        </button>
                        <button class="btn btn-secondary btn-sm" onclick="openTelegramExportModal()" style="display: inline-flex; align-items: center; gap: 6px;">
                            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"></path></svg>
                            Import Telegram Export (.json)
                        </button>"""

assert target_buttons in content, "target_buttons not found in index.html"
content = content.replace(target_buttons, replacement_buttons, 1)

# 2. Add Sources Count badge in connection strip button
target_strip_btn = """                    <button class="btn btn-secondary btn-sm" onclick="toggleSyncPanel()" style="font-size: 11px; padding: 2px 8px; margin-left: auto;">
                        ⚙️ View Diagnostics
                    </button>"""

replacement_strip_btn = """                    <button class="btn btn-secondary btn-sm" onclick="toggleSyncPanel()" style="font-size: 11px; padding: 2px 8px; margin-left: auto;">
                        📡 Ingestion & Sources (<span id="inbox-sources-count-badge">0</span>)
                    </button>"""

assert target_strip_btn in content, "target_strip_btn not found in index.html"
content = content.replace(target_strip_btn, replacement_strip_btn, 1)

# 3. Add sync metrics text to Card 2 in diagnostics panel
target_card2 = """                                <div>Configured Channels: <strong id="diag-channels-count" style="color: var(--text-main);">0</strong></div>
                                <div>Active Accessible: <span id="diag-accessible-channels" style="color: #34d399;">0</span></div>
                                <div style="margin-top: 4px; font-size: 11px; color: #fbbf24; border-top: 1px dashed var(--border-subtle); padding-top: 4px;">
                                    ⚠️ <strong>Distinction:</strong> Bot connection proves API token validity. Receiving channel broadcasts requires adding <code>@CareerOrbitJobAssistantBot</code> as an <strong>Administrator</strong>.
                                </div>"""

replacement_card2 = """                                <div>Configured Sources: <strong id="diag-channels-count" style="color: var(--text-main);">0</strong> (Accessible: <span id="diag-accessible-channels" style="color: #34d399; font-weight: 600;">0</span>)</div>
                                <div style="margin-top: 4px; padding: 4px 6px; background: rgba(15, 23, 42, 0.4); border-radius: 4px; font-size: 11px;">
                                    <strong>Last Poll Sync:</strong> <span id="diag-sync-metrics-text" style="color: var(--text-muted);">No polls recorded</span>
                                </div>
                                <div style="margin-top: 4px; font-size: 11px; color: #fbbf24; border-top: 1px dashed var(--border-subtle); padding-top: 4px;">
                                    ⚠️ <strong>Requirement:</strong> Bot connection proves API token validity. Receiving channel broadcasts requires adding <code>@CareerOrbitJobAssistantBot</code> as an <strong>Administrator</strong>.
                                </div>"""

assert target_card2 in content, "target_card2 not found in index.html"
content = content.replace(target_card2, replacement_card2, 1)

# 4. Insert Telegram Export Modal right before Toast Container
target_modal_anchor = """    <!-- Toast Notification Container -->"""

telegram_modal_html = """    <!-- Telegram Desktop Export Modal -->
    <div id="telegram-export-modal" class="modal" role="dialog" aria-modal="true" onclick="if(event.target===this)closeModal('telegram-export-modal')">
        <div class="modal-content" style="max-width: 780px; max-height: 85vh; overflow-y: auto;">
            <div class="modal-header">
                <div>
                    <h3 style="margin:0; font-size:16px;">Import Telegram Desktop Chat Export (.json / .html)</h3>
                    <p style="margin:2px 0 0 0; font-size:12px; color:var(--text-secondary);">
                        Import historical job posts and learning resources from Telegram channels you belong to.
                    </p>
                </div>
                <button class="modal-close" onclick="closeModal('telegram-export-modal')">&times;</button>
            </div>
            <div style="padding: 16px 20px;">
                <div style="background: rgba(30, 41, 59, 0.4); border: 1px dashed var(--border-subtle); border-radius: var(--radius-sm); padding: 10px 14px; font-size: 11.5px; color: var(--text-secondary); line-height: 1.5; margin-bottom: 14px;">
                    <strong style="color: var(--text-main);">💡 How to export a Telegram channel (Work From Home JOBS, FoundtheInternship, etc.):</strong>
                    <ol style="margin: 4px 0 0 16px; padding: 0;">
                        <li>Open the channel in <strong>Telegram Desktop</strong>.</li>
                        <li>Click the <strong>⋮ (three dots)</strong> menu in the upper right header → Select <strong>Export chat history</strong>.</li>
                        <li>Format: Choose <strong>Machine-readable JSON</strong> (or HTML) → Click <strong>Export</strong>.</li>
                        <li>Upload the exported <code>result.json</code> (or <code>messages.html</code>) below.</li>
                    </ol>
                </div>

                <div style="display: flex; gap: 12px; align-items: center; margin-bottom: 12px; flex-wrap: wrap;">
                    <div style="flex: 1; min-width: 220px;">
                        <label style="font-size: 12px; color: var(--text-secondary); font-weight: 600; display: block; margin-bottom: 4px;">Channel Name (optional override):</label>
                        <input type="text" id="tg-export-title" placeholder="Auto-detected from export file" style="width: 100%; background: var(--bg-sidebar); border: 1px solid var(--border-subtle); color: var(--text-main); padding: 8px 12px; border-radius: var(--radius-sm); font-size: 13px;">
                    </div>
                    <div>
                        <label style="font-size: 12px; color: var(--text-secondary); font-weight: 600; display: block; margin-bottom: 4px;">Select result.json or messages.html:</label>
                        <input type="file" id="tg-export-file" accept=".json,.html,.htm" onchange="handleTelegramExportFileSelect(event)" style="font-size: 12px; color: var(--text-secondary);">
                    </div>
                </div>

                <div id="tg-export-file-info" style="display: none; margin-bottom: 10px; font-size: 12px; color: #60a5fa;"></div>

                <div style="margin-top: 10px; display: flex; justify-content: flex-end; gap: 10px;">
                    <button class="btn btn-secondary btn-sm" id="btn-tg-export-preview" onclick="previewTelegramExport()">Preview & Classify Messages</button>
                </div>

                <div id="tg-export-results" style="display: none; margin-top: 16px;">
                    <div id="tg-export-stats" style="margin-bottom: 12px; padding: 10px 14px; background: rgba(15, 23, 42, 0.7); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); font-size: 12.5px;"></div>
                    <div id="tg-export-items-list" style="max-height: 250px; overflow-y: auto; display: flex; flex-direction: column; gap: 8px; margin-bottom: 14px;"></div>
                    <div style="display: flex; justify-content: flex-end; gap: 10px;">
                        <button class="btn btn-secondary btn-sm" onclick="closeModal('telegram-export-modal')">Cancel</button>
                        <button class="btn btn-primary btn-sm" id="btn-tg-confirm-import" onclick="confirmTelegramExportImport()">Commit & Ingest Items</button>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Toast Notification Container -->"""

assert target_modal_anchor in content, "target_modal_anchor not found in index.html"
content = content.replace(target_modal_anchor, telegram_modal_html, 1)

# Write updated file with CRLF
html_path.write_text(content, encoding="utf-8", newline="\r\n")
print("index.html successfully updated!")
