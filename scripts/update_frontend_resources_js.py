"""Update index.html with Phase 2 Learning Resources Javascript functions."""

from pathlib import Path

INDEX_HTML_PATH = Path("careerorbit/web/static/index.html")
content = INDEX_HTML_PATH.read_text(encoding="utf-8")

idx1 = content.find("let resourceDebounceTimer = null;")
idx2 = content.find("async function removeLearningResource(resId)")

assert idx1 != -1 and idx2 != -1, "Could not find resource functions boundary"

NEW_JS = """let resourceDebounceTimer = null;
        function debouncedLoadResources() {
            clearTimeout(resourceDebounceTimer);
            resourceDebounceTimer = setTimeout(loadLearningResources, 250);
        }

        async function loadLearningPathways() {
            const grid = document.getElementById('pathways-grid');
            const totalHoursEl = document.getElementById('pathways-total-hours');
            if (!grid) return;

            try {
                const res = await apiFetch('/api/resources/pathways');
                if (!res.ok) throw new Error('Failed to fetch learning pathways');
                const data = await res.json();
                const pathways = data.pathways || [];

                let grandTotalHours = 0;
                let grandCompletedHours = 0;

                grid.innerHTML = pathways.map(pw => {
                    grandTotalHours += pw.total_hours || 0;
                    grandCompletedHours += pw.completed_hours || 0;
                    const pct = Math.round(pw.progress_pct || 0);

                    return `
                        <div class="card" style="padding: 16px; border: 1px solid var(--border-subtle); display: flex; flex-direction: column; justify-content: space-between;">
                            <div>
                                <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px;">
                                    <span style="font-size: 24px;">${escapeHtml(pw.icon || '📘')}</span>
                                    <span class="badge ${pw.is_completed ? 'badge-green' : 'badge-secondary'}" style="font-size: 10.5px;">
                                        ${pw.is_completed ? 'Completed ✓' : `${pct}% Completed`}
                                    </span>
                                </div>
                                <h4 style="font-size: 14px; font-weight: 600; color: var(--text-main); margin: 0 0 4px 0;">${escapeHtml(pw.title)}</h4>
                                <div style="font-size: 11px; color: var(--accent); margin-bottom: 8px; font-weight: 500;">${escapeHtml(pw.role_target)}</div>
                                <p style="font-size: 12px; color: var(--text-secondary); line-height: 1.4; margin: 0 0 12px 0;">${escapeHtml(pw.description)}</p>
                            </div>
                            <div>
                                <div style="margin-bottom: 8px;">
                                    <div style="display: flex; justify-content: space-between; font-size: 11px; color: var(--text-muted); margin-bottom: 4px;">
                                        <span>${pw.completed_resources} / ${pw.total_resources} Modules</span>
                                        <span>${pw.completed_hours} / ${pw.total_hours} hrs</span>
                                    </div>
                                    <div style="width: 100%; height: 6px; background: rgba(255, 255, 255, 0.08); border-radius: 3px; overflow: hidden;">
                                        <div style="width: ${pct}%; height: 100%; background: ${pw.is_completed ? '#10b981' : 'var(--accent)'}; transition: width 0.3s ease;"></div>
                                    </div>
                                </div>
                                <div style="display: flex; gap: 6px; margin-top: 10px;">
                                    <button class="btn btn-secondary btn-sm" onclick="filterByPathway('${escapeHtml(pw.id)}')" style="font-size: 11px; flex: 1; padding: 4px 8px;">
                                        Filter Modules &rarr;
                                    </button>
                                </div>
                            </div>
                        </div>
                    `;
                }).join('');

                if (totalHoursEl) {
                    totalHoursEl.innerText = `${grandCompletedHours.toFixed(1)} / ${grandTotalHours.toFixed(1)} hrs completed`;
                }
            } catch (err) {
                grid.innerHTML = `<div class="error-state" style="padding: 12px;">Failed to load pathways: ${escapeHtml(err.message)}</div>`;
            }
        }

        function filterByPathway(pathwayId) {
            const skillSelect = document.getElementById('resource-filter-skill');
            const categorySelect = document.getElementById('resource-filter-category');
            if (pathwayId === 'python-data-analysis' && skillSelect) {
                skillSelect.value = 'python';
            } else if (pathwayId === 'sql-query-mastery' && skillSelect) {
                skillSelect.value = 'sql';
            } else if (pathwayId === 'power-bi-business-intelligence' && skillSelect) {
                skillSelect.value = 'power_bi';
            } else if (pathwayId === 'cloud-data-engineering' && skillSelect) {
                skillSelect.value = 'data_engineering';
            }
            if (categorySelect) categorySelect.value = '';
            loadLearningResources();
        }

        async function toggleResourceComplete(resId) {
            try {
                const res = await apiFetch(`/api/resources/${resId}/toggle-complete`, { method: 'POST' });
                if (!res.ok) throw new Error('Toggle failed');
                const data = await res.json();
                const isNowDone = data.resource?.is_completed;
                showToast(isNowDone ? 'Resource marked as completed! ✓' : 'Resource marked as pending.', 'info');
                loadLearningResources();
                loadLearningPathways();
            } catch (err) {
                showToast(`Failed to update status: ${err.message}`, 'error');
            }
        }

        async function loadLearningResources() {
            const container = document.getElementById('resources-list');
            if (!container) return;

            // Also refresh pathways concurrently
            loadLearningPathways();

            const category = (document.getElementById('resource-filter-category')?.value || '').trim();
            const skill = (document.getElementById('resource-filter-skill')?.value || '').trim();
            const difficulty = (document.getElementById('resource-filter-difficulty')?.value || '').trim();
            const status = (document.getElementById('resource-filter-status')?.value || '').trim();
            const query = (document.getElementById('resource-search-input')?.value || '').trim();

            let url = '/api/resources?limit=100';
            if (category) url += `&category=${encodeURIComponent(category)}`;
            if (skill) url += `&skill_tag=${encodeURIComponent(skill)}`;
            if (difficulty) url += `&difficulty_level=${encodeURIComponent(difficulty)}`;
            if (status === 'completed') url += '&is_completed=true';
            if (status === 'pending') url += '&is_completed=false';
            if (query) url += `&q=${encodeURIComponent(query)}`;

            try {
                const res = await apiFetch(url);
                const data = await res.json();
                const items = data.resources || [];
                const stats = data.stats || {};

                const badge = document.getElementById('resources-count-badge');
                if (badge) {
                    const completedText = stats.completed !== undefined ? ` (${stats.completed} Done)` : '';
                    badge.innerText = `${items.length} Assets${completedText}`;
                }

                const navCount = document.getElementById('nav-resource-count');
                if (navCount) navCount.innerText = items.length;

                if (!items.length) {
                    container.innerHTML = `
                        <div class="empty-state" style="text-align: center; padding: 40px 20px;">
                            <div style="font-size: 32px; margin-bottom: 10px;">📚</div>
                            <strong style="color: var(--text-main); font-size: 15px;">No saved study materials matching this filter</strong>
                            <p style="font-size: 12.5px; color: var(--text-secondary); margin-top: 6px; max-width: 520px; margin-left: auto; margin-right: auto;">
                                Try broadening your filter criteria or switch to another skill category to discover more resources.
                            </p>
                            <div style="margin-top: 14px;">
                                <button class="btn btn-secondary btn-sm" onclick="resetResourceFilters()">Reset Filters &rarr;</button>
                            </div>
                        </div>
                    `;
                    return;
                }

                container.innerHTML = items.map(r => {
                    const tags = Array.isArray(r.tags) ? r.tags : [];
                    const urls = Array.isArray(r.all_urls) ? r.all_urls : (r.primary_url ? [r.primary_url] : []);
                    const primaryLink = r.primary_url && !r.primary_url.startsWith('#') ? r.primary_url : (urls[0] && !urls[0].startsWith('#') ? urls[0] : null);
                    const isDone = Boolean(r.is_completed);

                    let diffBadgeClass = 'badge-secondary';
                    if (r.difficulty_level === 'BEGINNER') diffBadgeClass = 'badge-green';
                    else if (r.difficulty_level === 'INTERMEDIATE') diffBadgeClass = 'badge-blue';
                    else if (r.difficulty_level === 'ADVANCED') diffBadgeClass = 'badge-purple';

                    const durationText = r.estimated_minutes ? `⏱️ ${r.estimated_minutes}m` : '';

                    return `
                        <div class="card" style="padding: 16px 20px; border-left: 4px solid ${isDone ? '#10b981' : 'var(--accent)'}; background: ${isDone ? 'rgba(16, 185, 129, 0.04)' : 'var(--bg-card)'};">
                            <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 14px; flex-wrap: wrap;">
                                <div style="flex: 1; min-width: 260px;">
                                    <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 6px;">
                                        <span class="badge ${diffBadgeClass}" style="font-size: 10px; font-weight: 700;">${escapeHtml(r.difficulty_level || 'BEGINNER')}</span>
                                        ${r.skill_tag ? `<span class="badge badge-purple" style="font-size: 10.5px;">#${escapeHtml(r.skill_tag)}</span>` : ''}
                                        <span class="badge badge-secondary" style="font-size: 10.5px;">${escapeHtml(r.resource_type || r.category)}</span>
                                        ${durationText ? `<span style="font-size: 11px; color: var(--text-muted);">${durationText}</span>` : ''}
                                        ${isDone ? `<span class="badge badge-green" style="font-size: 10px;">✓ COMPLETED</span>` : ''}
                                    </div>
                                    <h3 style="font-size: 15px; font-weight: 600; color: var(--text-main); margin: 4px 0 6px 0; text-decoration: ${isDone ? 'line-through' : 'none'}; opacity: ${isDone ? '0.85' : '1.0'};">
                                        ${escapeHtml(r.title)}
                                    </h3>
                                    ${r.summary ? `<p style="font-size: 12.5px; color: var(--text-secondary); line-height: 1.5; margin: 0 0 8px 0;">${escapeHtml(r.summary)}</p>` : ''}
                                    ${r.raw_excerpt && r.raw_excerpt !== r.summary ? `<p style="font-size: 12px; color: var(--text-muted); line-height: 1.5; background: rgba(15, 23, 42, 0.5); padding: 8px 12px; border-radius: var(--radius-sm); border: 1px solid var(--border-subtle); margin-bottom: 8px; white-space: pre-wrap;">${escapeHtml(r.raw_excerpt)}</p>` : ''}
                                    ${r.notes ? `<div style="font-size: 11.5px; color: var(--accent); margin-bottom: 6px;"><strong>💡 Preparation Tip:</strong> ${escapeHtml(r.notes)}</div>` : ''}
                                    <div style="display: flex; gap: 6px; flex-wrap: wrap; align-items: center; margin-top: 6px;">
                                        <span style="font-size: 11px; color: var(--text-muted);">Source: ${escapeHtml(r.source)}</span>
                                        ${tags.map(t => `<span class="badge badge-secondary" style="font-size: 9.5px;">#${escapeHtml(t)}</span>`).join('')}
                                    </div>
                                </div>
                                <div style="display: flex; flex-direction: column; gap: 8px; align-items: flex-end; min-width: 140px;">
                                    ${primaryLink ? `
                                        <a href="${escapeHtml(primaryLink)}" target="_blank" rel="noopener noreferrer" class="btn btn-secondary btn-sm" style="display: inline-flex; align-items: center; gap: 6px; width: 100%; justify-content: center;">
                                            <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>
                                            Open Resource
                                        </a>
                                    ` : ''}
                                    <button class="btn ${isDone ? 'btn-secondary' : 'btn-primary'} btn-sm" onclick="toggleResourceComplete(${r.id})" style="width: 100%; font-size: 11px; padding: 5px 8px; justify-content: center;">
                                        ${isDone ? '↺ Mark Pending' : '✓ Mark Complete'}
                                    </button>
                                    <button class="btn btn-danger btn-sm" onclick="removeLearningResource(${r.id})" style="font-size: 10.5px; padding: 3px 8px; width: 100%; justify-content: center; opacity: 0.7;">
                                        Delete
                                    </button>
                                </div>
                            </div>
                        </div>
                    `;
                }).join('');
            } catch (err) {
                container.innerHTML = `<div class="error-state" style="padding: 24px; text-align: center;"><strong style="color:var(--danger);">Failed to load resources:</strong> ${escapeHtml(err.message)}</div>`;
            }
        }

        function resetResourceFilters() {
            const cat = document.getElementById('resource-filter-category');
            const skill = document.getElementById('resource-filter-skill');
            const diff = document.getElementById('resource-filter-difficulty');
            const st = document.getElementById('resource-filter-status');
            const q = document.getElementById('resource-search-input');
            if (cat) cat.value = '';
            if (skill) skill.value = '';
            if (diff) diff.value = '';
            if (st) st.value = '';
            if (q) q.value = '';
            loadLearningResources();
        }

        """

new_content = content[:idx1] + NEW_JS + content[idx2:]
INDEX_HTML_PATH.write_text(new_content, encoding="utf-8")
print("Replaced JS functions successfully!")
