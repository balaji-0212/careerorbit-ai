"""Python script to surgically and safely update careerorbit/web/static/index.html."""
import re
import sys

def patch_index_html():
    file_path = "careerorbit/web/static/index.html"
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Inject global apiFetch into <head> if not already in head
    head_helper = """    <!-- Core API Client Helper (Loaded early in head to guarantee global availability) -->
    <script>
        window.apiFetch = async function(url, options = {}) {
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
        };
        var apiFetch = window.apiFetch;
    </script>
</head>"""

    if "window.apiFetch = async function" not in content:
        content = content.replace("</head>", head_helper, 1)

    # 2. Add Resource Library to navigation
    nav_resources_btn = """            <button onclick="switchTab('resources')">
                <span class="nav-left">
                    <svg viewBox="0 0 24 24"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path></svg>
                    Resource Library
                </span>
                <span class="counter-pill" id="nav-resource-count">0</span>
            </button>
            <div class="nav-section-label">Evidence & Governance</div>"""

    if "switchTab('resources')" not in content:
        content = content.replace('<div class="nav-section-label">Evidence & Governance</div>', nav_resources_btn, 1)

    # 3. Add tab-resources section
    resources_section_html = """
        <!-- Resource Library Section -->
        <section id="tab-resources" class="section-tab">
            <div class="card" style="margin-bottom: 20px; background: linear-gradient(135deg, rgba(30, 41, 59, 0.7), rgba(15, 23, 42, 0.9)); border: 1px solid var(--border-subtle);">
                <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 16px;">
                    <div>
                        <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 6px;">
                            <h2 style="font-size: 20px; font-weight: 700; margin: 0;">Career Study & Technical Resource Library</h2>
                            <span class="badge badge-green" id="resources-count-badge">0 Assets</span>
                        </div>
                        <p style="font-size: 13px; color: var(--text-secondary); margin: 0; max-width: 680px;">
                            Curated repository of DSA problems, SQL exercises, Power BI blueprints, Python guides, cheat sheets, and interview preparation assets saved from Telegram and community intelligence.
                        </p>
                    </div>
                    <div style="display: flex; gap: 10px; align-items: center;">
                        <button class="btn btn-secondary btn-sm" onclick="switchTab('inbox')">
                            &larr; Unified Inbox
                        </button>
                    </div>
                </div>
            </div>

            <!-- Filter Bar -->
            <div class="card" style="margin-bottom: 16px; padding: 14px 18px;">
                <div style="display: flex; flex-wrap: wrap; gap: 12px; align-items: center; justify-content: space-between;">
                    <div style="display: flex; flex-wrap: wrap; gap: 8px; align-items: center;">
                        <label style="font-size: 12px; color: var(--text-secondary); font-weight: 600;">Category:</label>
                        <select id="resource-filter-category" onchange="loadLearningResources()" style="background: var(--bg-sidebar); border: 1px solid var(--border-subtle); color: var(--text-main); padding: 6px 12px; border-radius: var(--radius-sm); font-size: 12px;">
                            <option value="">All Categories</option>
                            <option value="Interview Preparation">Interview Preparation</option>
                            <option value="Coding Practice">Coding Practice & DSA</option>
                            <option value="Technical Learning Materials">Technical Learning & Cheat Sheets</option>
                            <option value="Certifications and Courses">Certifications & Courses</option>
                            <option value="Other Career Resources">Other Career Resources</option>
                        </select>
                    </div>

                    <div style="display: flex; gap: 8px; flex: 1; max-width: 340px;">
                        <input type="text" id="resource-search-input" placeholder="Search title, tags, description..." oninput="debouncedLoadResources()" style="width: 100%; background: var(--bg-sidebar); border: 1px solid var(--border-subtle); color: var(--text-main); padding: 6px 12px; border-radius: var(--radius-sm); font-size: 12px;">
                    </div>
                </div>
            </div>

            <!-- Resource Cards Container -->
            <div id="resources-list" style="display: flex; flex-direction: column; gap: 12px;">
                <div class="empty-state">Loading Resource Library...</div>
            </div>
        </section>
"""
    if 'id="tab-resources"' not in content:
        content = content.replace('</main>', resources_section_html + '\n    </main>', 1)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    print("[+] Patched index.html with head helper, resource nav, and tab-resources section.")

if __name__ == "__main__":
    patch_index_html()
