import re

with open('careerorbit/web/static/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update Overview Career Priority Cards
target1 = """            <!-- Career Priority Focus Cards -->
            <div class="card">
                <div class="card-header">
                    <div>
                        <h3>Mandatory Career Priority Order</h3>
                        <p>Roles ranked exactly according to candidate target profile.</p>
                    </div>
                    <button class="btn btn-secondary btn-sm" onclick="switchTab('jobs')">Explore All Roles &rarr;</button>
                </div>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px;">
                    <div style="background: var(--bg-sidebar); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 14px;">
                        <span class="badge badge-blue">Priority 1</span>
                        <strong style="display:block; margin-top: 6px; font-size: 14px;">Data Analyst / BI / Power BI / Reporting Analyst</strong>
                        <div style="font-size: 12px; color: var(--text-secondary); margin-top: 4px;">Candidate-stated priority category</div>
                    </div>
                    <div style="background: var(--bg-sidebar); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 14px;">
                        <span class="badge badge-cyan">Priority 2</span>
                        <strong style="display:block; margin-top: 6px; font-size: 14px;">Data Scientist / Applied Data Science</strong>
                        <div style="font-size: 12px; color: var(--text-secondary); margin-top: 4px;">Candidate-stated priority category</div>
                    </div>
                    <div style="background: var(--bg-sidebar); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 14px;">
                        <span class="badge badge-purple">Priority 3</span>
                        <strong style="display:block; margin-top: 6px; font-size: 14px;">Software Engineer / Associate Software Engineer / Junior Developer</strong>
                        <div style="font-size: 12px; color: var(--text-secondary); margin-top: 4px;">Candidate-stated priority category</div>
                    </div>
                    <div style="background: var(--bg-sidebar); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 14px;">
                        <span class="badge badge-green">Priority 4</span>
                        <strong style="display:block; margin-top: 6px; font-size: 14px;">AI Engineer / Junior ML / Computer Vision / AI Application Developer</strong>
                        <div style="font-size: 12px; color: var(--text-secondary); margin-top: 4px;">Candidate-stated priority category</div>
                    </div>
                    <div style="background: var(--bg-sidebar); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 14px;">
                        <span class="badge badge-yellow">Priority 5</span>
                        <strong style="display:block; margin-top: 6px; font-size: 14px;">Data Engineer / Analytics Engineer</strong>
                        <div style="font-size: 12px; color: var(--text-secondary); margin-top: 4px;">Candidate-stated priority category</div>
                    </div>
                    <div style="background: var(--bg-sidebar); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 14px;">
                        <span class="badge badge-gray">Priority 6</span>
                        <strong style="display:block; margin-top: 6px; font-size: 14px;">Other relevant early-career technical roles</strong>
                        <div style="font-size: 12px; color: var(--text-secondary); margin-top: 4px;">Candidate-stated priority category</div>
                    </div>
                </div>
            </div>"""

replacement1 = """            <!-- Career Priority Focus Cards -->
            <div class="card">
                <div class="card-header">
                    <div>
                        <h3>Personalized Career Priority Order</h3>
                        <p>Roles ranked dynamically according to candidate's own configured career preferences.</p>
                    </div>
                    <div style="display:flex; gap: 8px;">
                        <button class="btn btn-secondary btn-sm" onclick="switchTab('settings'); setTimeout(() => document.getElementById('settings-career-priorities-card')?.scrollIntoView({behavior:'smooth'}), 100);">⚙️ Configure Priorities</button>
                        <button class="btn btn-secondary btn-sm" onclick="switchTab('jobs')">Explore All Roles &rarr;</button>
                    </div>
                </div>
                <div id="overview-career-priority-cards" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px;">
                    <div style="background: var(--bg-sidebar); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 14px;">
                        <span class="badge badge-blue">Loading Priorities...</span>
                    </div>
                </div>
            </div>"""

assert target1 in content, "target1 not found in index.html"
content = content.replace(target1, replacement1, 1)

# 2. Add Personalized Career Priorities Manager in tab-settings
target2 = """        <section id="tab-settings" class="section-tab">
            <div class="card">"""

replacement2 = """        <section id="tab-settings" class="section-tab">
            <!-- Personalized Career Priorities Manager -->
            <div class="card" id="settings-career-priorities-card" style="margin-bottom: 24px;">
                <div class="card-header">
                    <div>
                        <h3>Personalized Career Priorities</h3>
                        <p>Select which career categories you want to pursue and arrange your preferred priority order. Ranking is dynamically applied to all discovery leads, recommendations, and reports.</p>
                    </div>
                    <div style="display: flex; gap: 8px; align-items: center;">
                        <button class="btn btn-secondary btn-sm" onclick="resetCareerPriorities()">Reset to Default</button>
                        <button class="btn btn-primary btn-sm" onclick="saveCareerPriorities()">Save Preferences</button>
                    </div>
                </div>

                <div id="career-priorities-status-banner" style="display:none; padding: 10px 14px; border-radius: var(--radius-md); margin-bottom: 16px; font-size: 13px;"></div>

                <div style="display: grid; grid-template-columns: 1fr 340px; gap: 24px;">
                    <div>
                        <h4 style="font-size: 14px; margin-bottom: 10px; color: var(--text-main);">Active Priority Order (Ranked 1st to Last)</h4>
                        <p style="font-size: 12.5px; color: var(--text-secondary); margin-bottom: 12px;">Top-ranked categories receive highest preference. Use the accessible Move Up (▲) and Move Down (▼) buttons to reorder, or ✕ to remove.</p>
                        <div id="career-priorities-list" style="display: flex; flex-direction: column; gap: 10px;">
                            <p style="color: var(--text-muted);">Loading preferences...</p>
                        </div>
                    </div>

                    <div style="background: var(--bg-sidebar); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 16px;">
                        <h4 style="font-size: 14px; margin-bottom: 10px; color: var(--text-main);">Add Supported Career Category</h4>
                        <p style="font-size: 12px; color: var(--text-secondary); margin-bottom: 12px;">Select from available career categories supported by the platform taxonomy to add to your personalized priority list.</p>
                        <div style="display: flex; gap: 8px; margin-bottom: 16px;">
                            <select id="add-career-category-select" class="select-filter" style="flex: 1; padding: 8px 10px;">
                                <option value="">Select category...</option>
                            </select>
                            <button class="btn btn-secondary btn-sm" onclick="addSelectedCareerCategory()">+ Add</button>
                        </div>

                        <div style="border-top: 1px solid var(--border-subtle); padding-top: 14px;">
                            <h5 style="font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-muted); margin-bottom: 8px;">Key Rules & Integrity</h5>
                            <ul style="font-size: 12px; color: var(--text-secondary); line-height: 1.6; padding-left: 18px; margin: 0;">
                                <li><strong>Independent Preferences:</strong> Each profile configures its own preferences.</li>
                                <li><strong>Mandatory Eligibility:</strong> High priority never overrides disqualifications (unpaid, experience > 3 yrs, work auth).</li>
                                <li><strong>Full Consideration:</strong> Selected lower-priority roles are considered and never automatically rejected.</li>
                                <li><strong>Unselected Roles:</strong> Unselected categories are ranked after all selected categories.</li>
                            </ul>
                        </div>
                    </div>
                </div>
            </div>

            <div class="card">"""

assert target2 in content, "target2 not found in index.html"
content = content.replace(target2, replacement2, 1)

# 3. Update overview table row to show preference rank
target3 = '<td><span class="badge badge-blue">P${j.priority_category}: ${(j.priority_label || \'\').split(\'/\')[0]}</span></td>'
replacement3 = '<td>${j.preference_rank ? `<span class="badge badge-blue" style="font-weight:600;">Rank #${j.preference_rank}</span><br>` : \'\'}<span style="font-size:11.5px;color:var(--text-secondary);">${escapeHtml((j.priority_label || \'\').split(\'/\')[0])}</span></td>'

assert target3 in content, "target3 not found in index.html"
content = content.replace(target3, replacement3, 1)

# 4. Update job card to show preference rank + category
target4 = '<span class="badge badge-blue">P${j.priority_category}: ${(j.priority_label || \'\').split(\'/\')[0]}</span>'
replacement4 = '${j.preference_rank ? `<span class="badge badge-blue" title="Candidate preference rank">★ Rank #${j.preference_rank}</span>` : \'\'}<span class="badge badge-gray" title="Role category">${escapeHtml((j.priority_label || \'\').split(\'/\')[0])}</span>'

assert target4 in content, "target4 not found in index.html"
content = content.replace(target4, replacement4, 1)

# 5. Add JavaScript for Career Preferences
js_code = """
        // ----------------- Personalized Career Preferences JS -----------------
        let currentCareerPreferences = {
            selected_categories: [],
            available_categories: [],
        };

        async function loadCareerPreferences() {
            try {
                const res = await apiFetch('/api/profile/preferences');
                if (!res.ok) throw new Error('Failed to fetch career preferences');
                const data = await res.json();
                currentCareerPreferences = data;
                renderOverviewCareerPriorities();
                renderCareerPrioritiesSettings();
                updateFilterPriorityDropdown();
            } catch (err) {
                console.error('Error loading career preferences:', err);
            }
        }

        function renderOverviewCareerPriorities() {
            const container = document.getElementById('overview-career-priority-cards');
            if (!container) return;
            const selected = currentCareerPreferences.selected_categories || [];
            const available = currentCareerPreferences.available_categories || [];
            const catMap = {};
            available.forEach(c => { catMap[c.id] = c; });

            if (selected.length === 0) {
                container.innerHTML = `
                    <div style="grid-column: 1 / -1; background: var(--bg-sidebar); border: 1px dashed var(--border-subtle); border-radius: var(--radius-md); padding: 16px; text-align: center;">
                        <span class="badge badge-yellow">No Career Priorities Configured</span>
                        <p style="font-size: 13px; color: var(--text-secondary); margin-top: 6px;">Configure your personalized career priorities in Settings to rank discovery leads.</p>
                        <button class="btn btn-secondary btn-sm" style="margin-top: 8px;" onclick="switchTab('settings'); document.getElementById('settings-career-priorities-card')?.scrollIntoView();">Configure Priorities &rarr;</button>
                    </div>
                `;
                return;
            }

            const badgeColors = ['badge-blue', 'badge-cyan', 'badge-purple', 'badge-green', 'badge-yellow', 'badge-gray'];

            container.innerHTML = selected.map((catId, idx) => {
                const cat = catMap[catId] || { short_label: catId, label: catId, description: '' };
                const badgeColor = badgeColors[idx % badgeColors.length];
                return `
                    <div style="background: var(--bg-sidebar); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 14px; display: flex; flex-direction: column; justify-content: space-between;">
                        <div>
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <span class="badge ${badgeColor}">Priority ${idx + 1}</span>
                                <span style="font-size: 11px; color: var(--text-muted); font-weight: 600;">Personal Choice</span>
                            </div>
                            <strong style="display:block; margin-top: 8px; font-size: 14px; color: var(--text-main);">${escapeHtml(cat.label || cat.short_label)}</strong>
                            <div style="font-size: 12px; color: var(--text-secondary); margin-top: 6px; line-height: 1.4;">${escapeHtml(cat.description || '')}</div>
                        </div>
                    </div>
                `;
            }).join('');
        }

        function renderCareerPrioritiesSettings() {
            const listContainer = document.getElementById('career-priorities-list');
            const selectEl = document.getElementById('add-career-category-select');
            if (!listContainer || !selectEl) return;

            const selected = currentCareerPreferences.selected_categories || [];
            const available = currentCareerPreferences.available_categories || [];
            const catMap = {};
            available.forEach(c => { catMap[c.id] = c; });

            const unselected = available.filter(c => !selected.includes(c.id));
            selectEl.innerHTML = '<option value="">-- Choose Category to Add --</option>' +
                unselected.map(c => `<option value="${escapeHtml(c.id)}">${escapeHtml(c.label)}</option>`).join('');

            if (selected.length === 0) {
                listContainer.innerHTML = `
                    <div style="padding: 16px; border: 1px dashed var(--border-subtle); border-radius: var(--radius-md); text-align: center; color: var(--text-muted);">
                        No career categories selected. Add categories using the dropdown on the right.
                    </div>
                `;
                return;
            }

            const badgeColors = ['badge-blue', 'badge-cyan', 'badge-purple', 'badge-green', 'badge-yellow', 'badge-gray'];

            listContainer.innerHTML = selected.map((catId, idx) => {
                const cat = catMap[catId] || { short_label: catId, label: catId, description: '' };
                const badgeColor = badgeColors[idx % badgeColors.length];
                const isFirst = idx === 0;
                const isLast = idx === selected.length - 1;
                return `
                    <div style="display: flex; align-items: center; justify-content: space-between; gap: 12px; background: var(--bg-card); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 12px 16px;">
                        <div style="display: flex; align-items: center; gap: 12px; flex: 1;">
                            <span class="badge ${badgeColor}" style="min-width: 80px; text-align: center;">Priority ${idx + 1}</span>
                            <div>
                                <strong style="color: var(--text-main); font-size: 14px;">${escapeHtml(cat.label)}</strong>
                                <div style="font-size: 12px; color: var(--text-secondary); margin-top: 2px;">${escapeHtml(cat.description || '')}</div>
                            </div>
                        </div>
                        <div style="display: flex; gap: 6px; align-items: center;">
                            <button class="btn btn-secondary btn-sm" onclick="moveCareerPriorityUp(${idx})" ${isFirst ? 'disabled style="opacity:0.4; cursor:not-allowed;"' : ''} title="Move up" aria-label="Move ${escapeHtml(cat.short_label)} up">▲</button>
                            <button class="btn btn-secondary btn-sm" onclick="moveCareerPriorityDown(${idx})" ${isLast ? 'disabled style="opacity:0.4; cursor:not-allowed;"' : ''} title="Move down" aria-label="Move ${escapeHtml(cat.short_label)} down">▼</button>
                            <button class="btn btn-danger btn-sm" onclick="removeCareerPriority(${idx})" title="Remove category" aria-label="Remove ${escapeHtml(cat.short_label)}">✕</button>
                        </div>
                    </div>
                `;
            }).join('');
        }

        function moveCareerPriorityUp(index) {
            if (index <= 0) return;
            const selected = [...(currentCareerPreferences.selected_categories || [])];
            const temp = selected[index - 1];
            selected[index - 1] = selected[index];
            selected[index] = temp;
            currentCareerPreferences.selected_categories = selected;
            renderCareerPrioritiesSettings();
            showPreferenceStatus('Preference order changed locally. Click "Save Preferences" to persist.', 'info');
        }

        function moveCareerPriorityDown(index) {
            const selected = [...(currentCareerPreferences.selected_categories || [])];
            if (index >= selected.length - 1) return;
            const temp = selected[index + 1];
            selected[index + 1] = selected[index];
            selected[index] = temp;
            currentCareerPreferences.selected_categories = selected;
            renderCareerPrioritiesSettings();
            showPreferenceStatus('Preference order changed locally. Click "Save Preferences" to persist.', 'info');
        }

        function removeCareerPriority(index) {
            const selected = [...(currentCareerPreferences.selected_categories || [])];
            selected.splice(index, 1);
            currentCareerPreferences.selected_categories = selected;
            renderCareerPrioritiesSettings();
            showPreferenceStatus('Category removed locally. Click "Save Preferences" to persist.', 'info');
        }

        function addSelectedCareerCategory() {
            const selectEl = document.getElementById('add-career-category-select');
            const catId = selectEl.value;
            if (!catId) return;
            const selected = [...(currentCareerPreferences.selected_categories || [])];
            if (selected.includes(catId)) return;
            selected.push(catId);
            currentCareerPreferences.selected_categories = selected;
            renderCareerPrioritiesSettings();
            showPreferenceStatus('Category added locally. Click "Save Preferences" to persist.', 'info');
        }

        async function saveCareerPriorities() {
            try {
                const payload = {
                    profile_id: 'default',
                    selected_categories: currentCareerPreferences.selected_categories || []
                };
                const res = await apiFetch('/api/profile/preferences', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                if (!res.ok) {
                    const errData = await res.json().catch(() => ({}));
                    throw new Error(errData.detail || 'Failed to save preferences');
                }
                const data = await res.json();
                currentCareerPreferences.selected_categories = data.selected_categories;
                showPreferenceStatus('✓ Career priorities saved successfully! Discovery leads ranking updated.', 'success');
                renderOverviewCareerPriorities();
                renderCareerPrioritiesSettings();
                updateFilterPriorityDropdown();
                loadOverviewJobs();
                loadJobs();
            } catch (err) {
                showPreferenceStatus('Error saving preferences: ' + err.message, 'error');
            }
        }

        async function resetCareerPriorities() {
            if (!confirm('Reset career priorities back to the platform default order?')) return;
            try {
                const res = await apiFetch('/api/profile/preferences/reset', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ profile_id: 'default' })
                });
                if (!res.ok) throw new Error('Failed to reset preferences');
                const data = await res.json();
                currentCareerPreferences.selected_categories = data.selected_categories;
                showPreferenceStatus('✓ Career priorities reset to default successfully.', 'success');
                renderOverviewCareerPriorities();
                renderCareerPrioritiesSettings();
                updateFilterPriorityDropdown();
                loadOverviewJobs();
                loadJobs();
            } catch (err) {
                showPreferenceStatus('Error resetting preferences: ' + err.message, 'error');
            }
        }

        function showPreferenceStatus(msg, type) {
            const banner = document.getElementById('career-priorities-status-banner');
            if (!banner) return;
            banner.style.display = 'block';
            if (type === 'success') {
                banner.style.background = 'rgba(16, 185, 129, 0.15)';
                banner.style.color = '#34d399';
                banner.style.border = '1px solid rgba(16, 185, 129, 0.3)';
            } else if (type === 'error') {
                banner.style.background = 'rgba(239, 68, 68, 0.15)';
                banner.style.color = '#f87171';
                banner.style.border = '1px solid rgba(239, 68, 68, 0.3)';
            } else {
                banner.style.background = 'rgba(59, 130, 246, 0.15)';
                banner.style.color = '#60a5fa';
                banner.style.border = '1px solid rgba(59, 130, 246, 0.3)';
            }
            banner.innerText = msg;
        }

        function updateFilterPriorityDropdown() {
            const sel = document.getElementById('filter-priority');
            if (!sel) return;
            const selected = currentCareerPreferences.selected_categories || [];
            const available = currentCareerPreferences.available_categories || [];
            const catMap = {};
            available.forEach(c => { catMap[c.id] = c; });

            let html = '<option value="">All Career Priorities</option>';
            selected.forEach((catId, idx) => {
                const cat = catMap[catId];
                if (cat) {
                    html += `<option value="${cat.legacy_code}">Priority ${idx + 1} · ${escapeHtml(cat.short_label)}</option>`;
                }
            });
            sel.innerHTML = html;
        }
"""

# Insert js_code before "// Initialize application on window load"
target_init = "// Initialize application on window load"
assert target_init in content, "target_init not found in index.html"
content = content.replace(target_init, js_code + "\n        " + target_init, 1)

# Update DOMContentLoaded to also loadCareerPreferences()
target_dom = "window.addEventListener('DOMContentLoaded', () => {\n            fetchStats();\n            loadOverviewJobs();"
replacement_dom = "window.addEventListener('DOMContentLoaded', () => {\n            fetchStats();\n            loadOverviewJobs();\n            loadCareerPreferences();"
assert target_dom in content, "target_dom not found in index.html"
content = content.replace(target_dom, replacement_dom, 1)

# Update switchTab for settings and overview
target_switch = "if (tabId === 'overview') { fetchStats(); loadOverviewJobs(); }"
replacement_switch = "if (tabId === 'overview') { fetchStats(); loadOverviewJobs(); loadCareerPreferences(); }\n            else if (tabId === 'settings') { loadCareerPreferences(); }"
assert target_switch in content, "target_switch not found in index.html"
content = content.replace(target_switch, replacement_switch, 1)

with open('careerorbit/web/static/index.html', 'w', encoding='utf-8') as f:
    f.write(content)
print("Successfully patched index.html with personalized career priority system UI and JS!")
