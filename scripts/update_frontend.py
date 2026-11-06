"""Script to update and enhance careerorbit/web/static/index.html with full robustness."""
import re
from pathlib import Path

def update():
    path = Path("careerorbit/web/static/index.html")
    html = path.read_text(encoding="utf-8")

    # 1. Update Header Bar actions
    old_header_actions = """            <div class="actions">
                <button class="btn btn-secondary btn-sm" onclick="exportData('jobs')">Export CSV</button>
                <button class="btn btn-sm" id="btn-trigger-search" onclick="triggerDiscovery(this)">
                    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 0 1-9 9m9-9a9 9 0 0 0-9-9m9 9H3m9 9a9 9 0 0 1-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9"></path></svg>
                    Run Job Discovery
                </button>
            </div>
        </div>"""

    new_header_actions = """            <div class="actions">
                <div id="connection-status-pill" class="badge badge-green" style="display:inline-flex; align-items:center; gap:6px; cursor:pointer; padding:6px 12px; font-size:12px;" onclick="checkBackendHealth(true)" title="Click to verify backend connection">🟢 127.0.0.1:8000 Connected</div>
                <button class="btn btn-secondary btn-sm" onclick="exportData('jobs')">Export CSV</button>
                <button class="btn btn-sm" id="btn-trigger-search" onclick="triggerDiscovery(this)">
                    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 0 1-9 9m9-9a9 9 0 0 0-9-9m9 9H3m9 9a9 9 0 0 1-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9"></path></svg>
                    Run Job Discovery
                </button>
            </div>
        </div>

        <!-- System Connectivity & Health Notice Container -->
        <div id="backend-banner-container" style="margin-bottom: 20px;"></div>"""

    if old_header_actions in html:
        html = html.replace(old_header_actions, new_header_actions, 1)
        print("[+] Replaced Header Actions & Banner Container")
    else:
        print("[!] Could not match header actions exactly")

    # 2. Update Profile Card Header in tab-profile
    old_profile_header = """            <div class="card">
                <div class="card-header">
                    <div>
                        <h3>Candidate Career Profile & Fact Governance</h3>
                        <p>Legacy profile claims require individual source verification or candidate confirmation before use.</p>
                    </div>
                    <div style="display:flex; gap: 8px;">
                        <span class="badge badge-yellow">Original source documents required</span>
                    </div>
                </div>"""

    new_profile_header = """            <div class="card">
                <div class="card-header">
                    <div>
                        <h3>Candidate Career Profile & Fact Governance</h3>
                        <p>Candidate claims require individual source verification or candidate confirmation before use in resumes.</p>
                    </div>
                    <div style="display:flex; gap: 8px; flex-wrap:wrap;">
                        <button class="btn btn-secondary btn-sm" onclick="openProfileHistoryModal()">Audit History</button>
                        <button class="btn btn-secondary btn-sm" onclick="downloadProfileSnapshot()">Export SHA-256 Snapshot</button>
                    </div>
                </div>"""

    if old_profile_header in html:
        html = html.replace(old_profile_header, new_profile_header, 1)
        print("[+] Replaced Profile Card Header")

    # 3. Add Employer ATS Board Registry Card in tab-sources
    old_sources_tab = """        <!-- 9. DISCOVERY SOURCES TAB -->
        <section id="tab-sources" class="section-tab">
            <div class="card">
                <div class="card-header">
                    <div>
                        <h3>Multi-Source Adapter Health & Status</h3>
                        <p>Live status of all public APIs and documented employer ATS board adapters.</p>
                    </div>
                    <button class="btn btn-sm" onclick="triggerDiscovery(this)">Query All Sources Now</button>
                </div>
                <div id="sources-health-grid" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px;">
                    <!-- Populated dynamically -->
                </div>
            </div>
        </section>"""

    new_sources_tab = """        <!-- 9. DISCOVERY SOURCES TAB -->
        <section id="tab-sources" class="section-tab">
            <div class="card">
                <div class="card-header">
                    <div>
                        <h3>Multi-Source Adapter Health & Status</h3>
                        <p>Live status of all public APIs and documented employer ATS board adapters.</p>
                    </div>
                    <button class="btn btn-sm" onclick="triggerDiscovery(this)">Query All Sources Now</button>
                </div>
                <div id="sources-health-grid" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px;">
                    <!-- Populated dynamically -->
                </div>
            </div>

            <!-- Employer ATS Board Registry Card -->
            <div class="card" style="margin-top: 24px;">
                <div class="card-header">
                    <div>
                        <h3>Configured Employer ATS Boards</h3>
                        <p>Official employer Greenhouse and Lever boards for direct vacancy scraping and verification.</p>
                    </div>
                    <button class="btn btn-sm" onclick="openAddEmployerModal()">+ Register Employer Board</button>
                </div>
                <div id="employer-registry-table-container">
                    <!-- Populated dynamically from /api/sources/registry -->
                </div>
            </div>
        </section>"""

    if old_sources_tab in html:
        html = html.replace(old_sources_tab, new_sources_tab, 1)
        print("[+] Replaced Sources Tab with Employer Registry Card")

    # 4. Add the 3 new modals right before <!-- Toast Notification Container -->
    old_modals_end = """    <!-- Toast Notification Container -->"""
    new_modals = """    <!-- Edit Profile Field Modal -->
    <div id="edit-field-modal" class="modal" role="dialog" aria-modal="true" onclick="if(event.target===this)closeModal('edit-field-modal')">
        <div class="modal-content" style="max-width: 540px;">
            <div class="modal-header">
                <div>
                    <h3 id="modal-edit-field-title">Edit Candidate Profile Fact</h3>
                    <p id="modal-edit-field-path" style="font-family: monospace; font-size: 11.5px; color: var(--accent);"></p>
                </div>
                <button class="modal-close" onclick="closeModal('edit-field-modal')">&times;</button>
            </div>
            <div style="padding: 18px 24px;">
                <div style="margin-bottom: 14px;">
                    <label style="display:block; font-size: 12px; color: var(--text-secondary); margin-bottom: 5px;">Field Value</label>
                    <textarea id="modal-edit-field-value" rows="3" style="width: 100%; background: var(--bg-sidebar); border: 1px solid var(--border-subtle); color: var(--text-main); padding: 8px 12px; border-radius: var(--radius-md);"></textarea>
                </div>
                <div style="margin-bottom: 14px;">
                    <label style="display:block; font-size: 12px; color: var(--text-secondary); margin-bottom: 5px;">Verification Evidence State</label>
                    <select id="modal-edit-field-state" class="select-filter" style="width: 100%;">
                        <option value="CONFIRMED">CONFIRMED — Backed by candidate directive / official document</option>
                        <option value="NEEDS_REVIEW">NEEDS_REVIEW — Unverified / requires confirmation</option>
                        <option value="NOT_PROVIDED">NOT_PROVIDED — Left undeclared / optional</option>
                    </select>
                </div>
                <div style="margin-bottom: 18px;">
                    <label style="display:block; font-size: 12px; color: var(--text-secondary); margin-bottom: 5px;">Audit Reference / Source Note</label>
                    <input type="text" id="modal-edit-field-note" placeholder="e.g. degree certificate / Candidate confirmation" style="width: 100%; background: var(--bg-sidebar); border: 1px solid var(--border-subtle); color: var(--text-main); padding: 8px 12px; border-radius: var(--radius-md);">
                </div>
                <div style="display: flex; justify-content: flex-end; gap: 10px;">
                    <button class="btn btn-secondary btn-sm" onclick="closeModal('edit-field-modal')">Cancel</button>
                    <button class="btn btn-sm" onclick="saveFieldEdit()">Save Fact & Update Provenance</button>
                </div>
            </div>
        </div>
    </div>

    <!-- Profile Change History Modal -->
    <div id="profile-history-modal" class="modal" role="dialog" aria-modal="true" onclick="if(event.target===this)closeModal('profile-history-modal')">
        <div class="modal-content" style="max-width: 800px;">
            <div class="modal-header">
                <div>
                    <h3>Candidate Profile Change History</h3>
                    <p>Tamper-evident audit trail of all profile fact edits and evidence state changes.</p>
                </div>
                <button class="modal-close" onclick="closeModal('profile-history-modal')">&times;</button>
            </div>
            <div id="profile-history-body" style="padding: 18px 24px; max-height: 480px; overflow-y: auto;">
                <!-- Populated dynamically from /api/profile/history -->
            </div>
        </div>
    </div>

    <!-- Add Employer ATS Board Modal -->
    <div id="add-source-modal" class="modal" role="dialog" aria-modal="true" onclick="if(event.target===this)closeModal('add-source-modal')">
        <div class="modal-content" style="max-width: 520px;">
            <div class="modal-header">
                <div>
                    <h3>Register Employer ATS Board</h3>
                    <p>Configure an official employer Greenhouse or Lever public board feed.</p>
                </div>
                <button class="modal-close" onclick="closeModal('add-source-modal')">&times;</button>
            </div>
            <div style="padding: 18px 24px;">
                <div style="margin-bottom: 12px;">
                    <label style="display:block; font-size: 12px; color: var(--text-secondary); margin-bottom: 5px;">Employer Name *</label>
                    <input type="text" id="add-source-name" placeholder="e.g. Stripe, Figma, GitLab" style="width: 100%; background: var(--bg-sidebar); border: 1px solid var(--border-subtle); color: var(--text-main); padding: 8px 12px; border-radius: var(--radius-md);">
                </div>
                <div style="margin-bottom: 12px;">
                    <label style="display:block; font-size: 12px; color: var(--text-secondary); margin-bottom: 5px;">Official Domain</label>
                    <input type="text" id="add-source-domain" placeholder="e.g. stripe.com" style="width: 100%; background: var(--bg-sidebar); border: 1px solid var(--border-subtle); color: var(--text-main); padding: 8px 12px; border-radius: var(--radius-md);">
                </div>
                <div style="margin-bottom: 12px;">
                    <label style="display:block; font-size: 12px; color: var(--text-secondary); margin-bottom: 5px;">ATS Provider *</label>
                    <select id="add-source-provider" class="select-filter" style="width: 100%;">
                        <option value="Greenhouse">Greenhouse (boards-api.greenhouse.io)</option>
                        <option value="Lever">Lever (api.lever.co)</option>
                    </select>
                </div>
                <div style="margin-bottom: 14px;">
                    <label style="display:block; font-size: 12px; color: var(--text-secondary); margin-bottom: 5px;">Public Board Token / Site Slug *</label>
                    <input type="text" id="add-source-board-id" placeholder="e.g. stripe, canonical, figma" style="width: 100%; background: var(--bg-sidebar); border: 1px solid var(--border-subtle); color: var(--text-main); padding: 8px 12px; border-radius: var(--radius-md);">
                </div>
                <div style="margin-bottom: 18px;">
                    <label style="display:block; font-size: 12px; color: var(--text-secondary); margin-bottom: 5px;">Notes</label>
                    <input type="text" id="add-source-notes" placeholder="e.g. Fintech payments infrastructure leader" style="width: 100%; background: var(--bg-sidebar); border: 1px solid var(--border-subtle); color: var(--text-main); padding: 8px 12px; border-radius: var(--radius-md);">
                </div>
                <div style="display: flex; justify-content: flex-end; gap: 10px;">
                    <button class="btn btn-secondary btn-sm" onclick="closeModal('add-source-modal')">Cancel</button>
                    <button class="btn btn-sm" onclick="submitNewEmployerSource()">Register Board</button>
                </div>
            </div>
        </div>
    </div>

    <!-- Toast Notification Container -->"""

    if old_modals_end in html:
        html = html.replace(old_modals_end, new_modals, 1)
        print("[+] Added Edit, History, and Add-Source Modals")

    path.write_text(html, encoding="utf-8")
    print("[+] HTML structure updated successfully")

if __name__ == "__main__":
    update()
