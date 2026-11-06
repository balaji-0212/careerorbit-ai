"""Python script to update all JS functions and raw fetch calls in index.html."""
import re
import sys

def patch_js():
    file_path = "careerorbit/web/static/index.html"
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Update switchTab to support 'resources'
    if "'resources': 'Career Study & Learning Resources'" not in content:
        content = content.replace(
            "'settings': 'Platform Settings & Security Posture'",
            "'settings': 'Platform Settings & Security Posture',\n                'resources': 'Career Study & Learning Resources'"
        )
        content = content.replace(
            "else if (tabId === 'scheduler') { loadSchedulerHistory(); }",
            "else if (tabId === 'scheduler') { loadSchedulerHistory(); }\n            else if (tabId === 'resources') { loadLearningResources(); }"
        )

    # 2. Add resource functions before loadOverviewJobs
    resource_funcs = """
        let resourceDebounceTimer = null;
        function debouncedLoadResources() {
            clearTimeout(resourceDebounceTimer);
            resourceDebounceTimer = setTimeout(loadLearningResources, 250);
        }

        async function loadLearningResources() {
            const container = document.getElementById('resources-list');
            if (!container) return;
            const category = (document.getElementById('resource-filter-category')?.value || '').trim();
            const query = (document.getElementById('resource-search-input')?.value || '').trim();

            let url = '/api/resources?limit=100';
            if (category) url += `&category=${encodeURIComponent(category)}`;
            if (query) url += `&q=${encodeURIComponent(query)}`;

            try {
                const res = await apiFetch(url);
                const data = await res.json();
                const items = data.resources || [];
                const badge = document.getElementById('resources-count-badge');
                if (badge) badge.innerText = `${items.length} Assets`;

                const navCount = document.getElementById('nav-resource-count');
                if (navCount) navCount.innerText = items.length;

                if (!items.length) {
                    container.innerHTML = `
                        <div class="empty-state" style="text-align: center; padding: 40px 20px;">
                            <div style="font-size: 32px; margin-bottom: 10px;">📚</div>
                            <strong style="color: var(--text-main); font-size: 15px;">No saved study materials matching this filter</strong>
                            <p style="font-size: 12.5px; color: var(--text-secondary); margin-top: 6px; max-width: 520px; margin-left: auto; margin-right: auto;">
                                When reviewing interview questions, SQL exercises, DSA problems, or cheat sheets in the <strong>Unified Inbox</strong>, click <em>Save to Study Collection</em> to curate them here.
                            </p>
                            <div style="margin-top: 14px;">
                                <button class="btn btn-secondary btn-sm" onclick="switchTab('inbox')">Open Unified Inbox &rarr;</button>
                            </div>
                        </div>
                    `;
                    return;
                }

                container.innerHTML = items.map(r => {
                    const tags = Array.isArray(r.tags) ? r.tags : [];
                    const urls = Array.isArray(r.all_urls) ? r.all_urls : (r.primary_url ? [r.primary_url] : []);
                    const primaryLink = r.primary_url && !r.primary_url.startsWith('#') ? r.primary_url : (urls[0] && !urls[0].startsWith('#') ? urls[0] : null);
                    const dateFormatted = r.saved_at ? new Date(r.saved_at).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', dateStyle: 'medium', timeStyle: 'short' }) : '';

                    return `
                        <div class="card" style="padding: 18px 20px; border-left: 3px solid var(--accent);">
                            <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; flex-wrap: wrap;">
                                <div style="flex: 1;">
                                    <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 6px;">
                                        <span class="badge badge-purple" style="font-size: 11px;">${escapeHtml(r.category)}</span>
                                        ${r.sub_category ? `<span class="badge badge-secondary" style="font-size: 10.5px;">${escapeHtml(r.sub_category)}</span>` : ''}
                                        <span style="font-size: 11.5px; color: var(--text-muted);">${dateFormatted ? 'Saved on ' + dateFormatted : ''}</span>
                                    </div>
                                    <h3 style="font-size: 15px; font-weight: 600; color: var(--text-main); margin: 4px 0 8px 0;">${escapeHtml(r.title)}</h3>
                                    ${r.raw_excerpt ? `<p style="font-size: 12.5px; color: var(--text-secondary); line-height: 1.6; white-space: pre-wrap; background: rgba(15, 23, 42, 0.5); padding: 10px 12px; border-radius: var(--radius-sm); border: 1px solid var(--border-subtle); margin-bottom: 10px;">${escapeHtml(r.raw_excerpt)}</p>` : ''}
                                    <div style="display: flex; gap: 6px; flex-wrap: wrap; align-items: center;">
                                        <span style="font-size: 11.5px; color: var(--text-muted);">Source: ${escapeHtml(r.source)}</span>
                                        ${tags.map(t => `<span class="badge badge-secondary" style="font-size: 10px;">#${escapeHtml(t)}</span>`).join('')}
                                    </div>
                                </div>
                                <div style="display: flex; flex-direction: column; gap: 8px; align-items: flex-end;">
                                    ${primaryLink ? `
                                        <a href="${escapeHtml(primaryLink)}" target="_blank" rel="noopener noreferrer" class="btn btn-secondary btn-sm" style="display: inline-flex; align-items: center; gap: 6px;">
                                            <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>
                                            Open Resource
                                        </a>
                                    ` : ''}
                                    <button class="btn btn-danger btn-sm" onclick="removeLearningResource(${r.id})" style="font-size: 11px; padding: 4px 8px;">
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

        async function removeLearningResource(resId) {
            if (!confirm('Remove this saved study asset?')) return;
            try {
                await apiFetch(`/api/resources/${resId}`, { method: 'DELETE' });
                showToast('Study resource deleted.', 'info');
                loadLearningResources();
                fetchStats();
            } catch (err) {
                showToast(`Failed to delete resource: ${err.message}`, 'error');
            }
        }
"""
    if "async function loadLearningResources" not in content:
        content = content.replace("async function loadOverviewJobs()", resource_funcs + "\n        async function loadOverviewJobs()")

    # 3. Replace triggerDiscovery with polling version
    old_trigger = re.search(r"async function triggerDiscovery\(btn\)\s*\{[\s\S]*?finally\s*\{[\s\S]*?\}\s*\}", content)
    new_trigger = """async function triggerDiscovery(btn) {
            if (!btn) btn = document.getElementById('btn-trigger-search');
            const originalText = btn ? btn.innerHTML : 'Query Sources';
            if (btn) {
                btn.disabled = true;
                btn.innerHTML = '<span class="spinner" style="display:inline-block;width:12px;height:12px;border:2px solid #fff;border-top-color:transparent;border-radius:50%;animation:spin 0.6s linear infinite;margin-right:6px;"></span> Searching APIs...';
            }
            showToast('Initiating background job discovery across all configured sources...', 'info');

            try {
                const res = await apiFetch('/api/discovery/trigger', { method: 'POST' });
                const startData = await res.json();
                const runId = startData.run_id;

                if (startData.status === 'already_running') {
                    showToast('A discovery run is already in progress. Tracking status...', 'info');
                } else {
                    showToast('Discovery started. Scanning Greenhouse, Lever, Jobicy, Remotive, Unstop...', 'info');
                }

                // Poll status until completion (max 60 seconds)
                const startTime = Date.now();
                const pollInterval = 1500;
                let finalSummary = null;

                while (Date.now() - startTime < 60000) {
                    await new Promise(r => setTimeout(r, pollInterval));
                    try {
                        const statusRes = await apiFetch(`/api/discovery/status/${runId || ''}`);
                        const statusData = await statusRes.json();

                        if (statusData.stage && btn) {
                            btn.innerHTML = `<span class="spinner" style="display:inline-block;width:12px;height:12px;border:2px solid #fff;border-top-color:transparent;border-radius:50%;animation:spin 0.6s linear infinite;margin-right:6px;"></span> ${escapeHtml(statusData.stage.slice(0, 24))}...`;
                        }

                        if (statusData.status === 'success' || statusData.status === 'partial_success') {
                            finalSummary = statusData.summary || {};
                            const added = finalSummary.new_jobs_added || 0;
                            const updated = finalSummary.jobs_updated || 0;
                            const collected = finalSummary.total_collected || 0;
                            showToast(`Discovery completed! Found: ${collected}, Added: ${added}, Updated: ${updated}`, 'success');
                            break;
                        } else if (statusData.status === 'failed') {
                            throw new Error(statusData.error || statusData.stage || 'Discovery run failed');
                        } else if (statusData.status === 'skipped_overlap') {
                            showToast('Discovery skipped: another process holds the workflow lock.', 'warning');
                            break;
                        }
                    } catch (pollErr) {
                        console.warn('Poll status error:', pollErr);
                    }
                }

                await Promise.all([fetchStats(), loadJobs(), loadOverviewJobs()]);
            } catch (err) {
                showToast(`Discovery failed: ${err.message}`, 'error');
            } finally {
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = originalText;
                }
            }
        }"""

    if old_trigger:
        content = content[:old_trigger.start()] + new_trigger + content[old_trigger.end():]

    # 4. Replace all raw fetch calls across all functions in script (excluding apiFetch itself)
    # Target specific raw fetch calls:
    replacements = [
        ("const res = await fetch('/api/stats');", "const res = await apiFetch('/api/stats');"),
        ("const res = await fetch('/api/jobs?limit=5&sort_by=score_desc');", "const res = await apiFetch('/api/jobs?limit=5&sort_by=score_desc');"),
        ("const res = await fetch(url);", "const res = await apiFetch(url);"),
        ("const res = await fetch('/api/jobs?saved_only=true&limit=100');", "const res = await apiFetch('/api/jobs?saved_only=true&limit=100');"),
        ("const res = await fetch(`/api/jobs/${jobId}/save`, { method: 'POST' });", "const res = await apiFetch(`/api/jobs/${jobId}/save`, { method: 'POST' });"),
        ("const res = await fetch(`/api/jobs/${jobId}`);", "const res = await apiFetch(`/api/jobs/${jobId}`);"),
        ("const res = await fetch(`/api/applications/prepare/${jobId}`, { method: 'POST' });", "const res = await apiFetch(`/api/applications/prepare/${jobId}`, { method: 'POST' });"),
        ("const res = await fetch(`/api/resumes/generate/${jobId}`, { method: 'POST' });", "const res = await apiFetch(`/api/resumes/generate/${jobId}`, { method: 'POST' });"),
        ("const res = await fetch(`/api/prep/interview/${jobId}`, { method: 'POST' });", "const res = await apiFetch(`/api/prep/interview/${jobId}`, { method: 'POST' });"),
        ("const res = await fetch(`/api/applications/confirm-submission/${jobId}`, {", "const res = await apiFetch(`/api/applications/confirm-submission/${jobId}`, {"),
        ("const res = await fetch('/api/applications');", "const res = await apiFetch('/api/applications');"),
        ("const res = await fetch('/api/resumes');", "const res = await apiFetch('/api/resumes');"),
        ("const res = await fetch('/api/prep/plans');", "const res = await apiFetch('/api/prep/plans');"),
        ("const res = await fetch('/api/prep/daily-plan');", "const res = await apiFetch('/api/prep/daily-plan');"),
        ("const res = await fetch('/api/profile/full');", "const res = await apiFetch('/api/profile/full');"),
        ("const res = await fetch('/api/profile/evidence', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({field, state:'CONFIRMED_BY_CANDIDATE', evidence}) });",
         "const res = await apiFetch('/api/profile/evidence', { method: 'POST', body: JSON.stringify({field, state:'CONFIRMED_BY_CANDIDATE', evidence}) });"),
        ("const res = await fetch('/api/sources/health');", "const res = await apiFetch('/api/sources/health');"),
        ("const res = await fetch('/api/scheduler/history');", "const res = await apiFetch('/api/scheduler/history');"),
        ("const res = await fetch('/api/verify-url', {", "const res = await apiFetch('/api/verify-url', {"),
    ]

    for old_s, new_s in replacements:
        if old_s in content:
            content = content.replace(old_s, new_s)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    print("[+] Patched index.html with resource functions, background polling discovery, and unified apiFetch calls.")

if __name__ == "__main__":
    patch_js()
