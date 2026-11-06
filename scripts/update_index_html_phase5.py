"""Update index.html with Phase 5 Interview Preparation Coach UI."""
import re

INDEX_PATH = "careerorbit/web/static/index.html"

with open(INDEX_PATH, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update tab-prep markup
target_section = """        <!-- 6. INTERVIEW PREP TAB -->
        <section id="tab-prep" class="section-tab">
            <div class="card">
                <div class="card-header">
                    <div>
                        <h3>Role-Specific Interview Coaching</h3>
                        <p>Technical concepts, coding/query practice with solutions, and STAR behavioral answers.</p>
                    </div>
                </div>
                <div id="prep-plans-container">
                    <!-- Loaded dynamically -->
                </div>
            </div>
        </section>"""

replacement_section = """        <!-- 6. INTERVIEW PREP TAB -->
        <section id="tab-prep" class="section-tab">
            <!-- Active Briefing Card -->
            <div class="card" style="margin-bottom: 20px;">
                <div class="card-header" style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px;">
                    <div>
                        <h3 style="margin:0;">Interview Preparation & Rehearsal Coach</h3>
                        <p style="margin:4px 0 0 0; color:var(--text-secondary); font-size:13px;">
                            Role-specific technical questions, rubrics, STAR behavioral frameworks, and readiness checklist.
                        </p>
                    </div>
                    <div style="display:flex; gap:10px; align-items:center;">
                        <select id="interview-prep-job-select" style="min-width:240px; padding:6px 12px; border-radius:var(--radius-sm); border:1px solid var(--border-subtle); background:var(--bg-main); color:var(--text-main); font-size:13px;" onchange="if(this.value) loadInterviewBriefing(this.value)">
                            <option value="">Select a target vacancy...</option>
                        </select>
                        <button class="btn btn-primary btn-sm" onclick="triggerSelectedJobBriefing()">Open Briefing</button>
                    </div>
                </div>

                <!-- Briefing Workspace Container -->
                <div id="interview-briefing-workspace" style="padding:16px; border-top:1px solid var(--border-subtle);">
                    <div style="text-align:center; padding:32px 16px; color:var(--text-muted);">
                        Select a target vacancy from the dropdown or click "Interview Prep" on any job listing to load your role-specific briefing session.
                    </div>
                </div>
            </div>

            <div class="card">
                <div class="card-header">
                    <div>
                        <h4 style="margin:0; font-size:15px;">Generated Interview Packages & Practice Exercises</h4>
                        <p style="margin:4px 0 0 0; color:var(--text-secondary); font-size:12px;">Archived study blocks and reference exercises</p>
                    </div>
                </div>
                <div id="prep-plans-container">
                    <!-- Loaded dynamically -->
                </div>
            </div>
        </section>"""

# 2. Add JavaScript helpers for Interview Prep Coach
js_code = """
        // ----------------- Phase 5: Interview Preparation Coach -----------------
        let currentInterviewJobId = null;
        let currentInterviewBriefing = null;

        async function loadInterviewPrepJobs() {
            try {
                const select = document.getElementById('interview-prep-job-select');
                if (!select) return;
                const res = await apiFetch('/api/jobs?limit=50');
                if (!res.ok) return;
                const data = await res.json();
                const jobs = data.jobs || [];
                select.innerHTML = '<option value="">Select a target vacancy...</option>' +
                    jobs.map(j => `<option value="${j.id}">${escapeHtml(j.employer)} - ${escapeHtml(j.title)} (Match: ${Math.round(j.match_score || 0)}%)</option>`).join('');
                if (currentInterviewJobId) {
                    select.value = currentInterviewJobId;
                }
            } catch (err) {
                console.error("Failed to load interview prep jobs:", err);
            }
        }

        function triggerSelectedJobBriefing() {
            const select = document.getElementById('interview-prep-job-select');
            if (select && select.value) {
                loadInterviewBriefing(select.value);
            } else {
                showToast("Please select a target vacancy first", "info");
            }
        }

        async function loadInterviewBriefing(jobId) {
            if (!jobId) return;
            currentInterviewJobId = jobId;
            const workspace = document.getElementById('interview-briefing-workspace');
            if (!workspace) return;

            workspace.innerHTML = `<div style="text-align:center; padding:24px; color:var(--text-secondary);"><span class="spinner" style="display:inline-block; margin-right:8px;"></span>Loading role-specific interview briefing...</div>`;

            try {
                const res = await apiFetch(`/api/interview-prep/briefing/${jobId}`);
                if (!res.ok) {
                    const errData = await res.json().catch(() => ({}));
                    throw new Error(errData.detail || 'Failed to fetch interview briefing');
                }
                const session = await res.json();
                currentInterviewBriefing = session;
                renderInterviewBriefing(session);
            } catch (err) {
                workspace.innerHTML = `<div class="error-state" style="padding:16px;">Error loading briefing: ${escapeHtml(err.message)}</div>`;
            }
        }

        function renderInterviewBriefing(session) {
            const workspace = document.getElementById('interview-briefing-workspace');
            if (!workspace) return;

            const b = session.briefing || {};
            const questions = b.questions || [];
            const checklist = session.checklist || [];
            const drafts = session.answer_drafts || {};
            const notes = session.candidate_notes || '';
            const conf = session.confidence_rating || 0;

            const questionsHtml = questions.map(q => {
                const qId = q.id;
                const draftVal = drafts[String(qId)] || drafts[qId] || '';
                return `
                    <div style="background:var(--bg-main); border:1px solid var(--border-subtle); border-radius:var(--radius-sm); padding:16px; margin-bottom:14px;">
                        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                            <span class="badge badge-purple" style="font-size:11px;">${escapeHtml(q.category || 'Technical')}</span>
                            <span style="font-size:11px; color:var(--text-muted);">Question ${qId} of ${questions.length}</span>
                        </div>
                        <h4 style="margin:0 0 10px 0; font-size:14.5px; color:var(--text-main); line-height:1.4;">${escapeHtml(q.question)}</h4>
                        
                        <div style="margin-bottom:10px;">
                            <strong style="font-size:12px; color:var(--text-secondary); text-transform:uppercase;">Focus Areas:</strong>
                            <ul style="margin:4px 0 0 18px; padding:0; font-size:12.5px; color:var(--text-main);">
                                ${(q.focus_areas || []).map(f => `<li>${escapeHtml(f)}</li>`).join('')}
                            </ul>
                        </div>

                        <div style="background:var(--bg-sidebar); border-left:3px solid var(--accent); padding:10px 12px; border-radius:var(--radius-sm); margin-bottom:10px;">
                            <strong style="font-size:12px; color:var(--accent);">Model Rubric & Evaluation Criteria:</strong>
                            <p style="margin:4px 0 0 0; font-size:12px; color:var(--text-secondary); line-height:1.5;">${escapeHtml(q.model_rubric || '')}</p>
                        </div>

                        ${q.candidate_evidence_link ? `
                            <div style="font-size:12px; color:#10b981; margin-bottom:12px; display:flex; align-items:center; gap:6px;">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg>
                                <span><strong>Candidate Evidence Grounding:</strong> ${escapeHtml(q.candidate_evidence_link)}</span>
                            </div>
                        ` : ''}

                        <div style="margin-top:12px; border-top:1px dashed var(--border-subtle); padding-top:10px;">
                            <label style="display:block; font-size:12px; font-weight:600; color:var(--text-secondary); margin-bottom:4px;">Rehearsal Answer Draft:</label>
                            <textarea id="draft-q-${qId}" rows="3" style="width:100%; box-sizing:border-box; padding:8px; border-radius:var(--radius-sm); border:1px solid var(--border-subtle); background:var(--bg-sidebar); color:var(--text-main); font-size:12.5px; font-family:inherit;" placeholder="Draft your answer using the STAR method or structured technical points...">${escapeHtml(draftVal)}</textarea>
                            <div style="text-align:right; margin-top:6px;">
                                <button class="btn btn-secondary btn-sm" onclick="saveAnswerDraft(${session.job_id}, ${qId})">Save Draft</button>
                            </div>
                        </div>
                    </div>
                `;
            }).join('');

            const checklistHtml = checklist.map((item, idx) => `
                <div style="display:flex; align-items:center; gap:10px; padding:6px 0; border-bottom:1px solid var(--border-subtle);">
                    <input type="checkbox" id="check-item-${idx}" ${item.completed ? 'checked' : ''} onchange="toggleInterviewChecklist(${session.job_id}, ${idx}, this.checked)">
                    <label for="check-item-${idx}" style="font-size:13px; color:var(--text-main); cursor:pointer; ${item.completed ? 'text-decoration:line-through; opacity:0.7;' : ''}">${escapeHtml(item.task)}</label>
                </div>
            `).join('');

            let starsHtml = '';
            for (let s = 1; s <= 5; s++) {
                const filled = s <= conf;
                starsHtml += `<span onclick="setInterviewConfidence(${session.job_id}, ${s})" style="cursor:pointer; font-size:20px; color:${filled ? '#f59e0b' : 'var(--border-subtle)'};" title="${s} of 5 Stars">&#9733;</span>`;
            }

            workspace.innerHTML = `
                <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:16px; border-bottom:1px solid var(--border-subtle); padding-bottom:12px;">
                    <div>
                        <h4 style="margin:0; font-size:18px; color:var(--text-main);">${escapeHtml(session.role_title)}</h4>
                        <div style="color:var(--accent); font-weight:600; font-size:14px; margin-top:2px;">${escapeHtml(session.employer_name)}</div>
                    </div>
                    <div style="text-align:right;">
                        <div style="font-size:12px; color:var(--text-secondary); margin-bottom:4px;">Readiness Confidence:</div>
                        <div style="display:inline-flex; gap:3px;">${starsHtml}</div>
                    </div>
                </div>

                <div style="background:rgba(59, 130, 246, 0.08); border-left:4px solid #3b82f6; padding:10px 14px; border-radius:var(--radius-sm); margin-bottom:18px; font-size:12.5px; color:var(--text-main);">
                    <strong>Role Summary:</strong> ${escapeHtml(b.summary || 'Role-specific preparation package grounded in candidate profile evidence.')}
                </div>

                <div class="grid-2col" style="display:grid; grid-template-columns: 2fr 1fr; gap:20px;">
                    <div>
                        <h4 style="font-size:15px; margin:0 0 12px 0; color:var(--text-main);">Role-Specific Questions & Evaluation Rubrics (${questions.length})</h4>
                        ${questionsHtml}
                    </div>

                    <div>
                        <div style="background:var(--bg-main); border:1px solid var(--border-subtle); border-radius:var(--radius-sm); padding:16px; margin-bottom:16px;">
                            <h4 style="font-size:14px; margin:0 0 10px 0; color:var(--text-main);">Readiness Checklist</h4>
                            <div>${checklistHtml}</div>
                        </div>

                        <div style="background:var(--bg-main); border:1px solid var(--border-subtle); border-radius:var(--radius-sm); padding:16px; margin-bottom:16px;">
                            <h4 style="font-size:14px; margin:0 0 8px 0; color:var(--text-main);">Candidate Notes & Strategies</h4>
                            <textarea id="interview-notes-input" rows="4" style="width:100%; box-sizing:border-box; padding:8px; border-radius:var(--radius-sm); border:1px solid var(--border-subtle); background:var(--bg-sidebar); color:var(--text-main); font-size:12.5px; font-family:inherit;" placeholder="Add private notes on specific interviewer names, question strategy, or edge cases...">${escapeHtml(notes)}</textarea>
                            <div style="text-align:right; margin-top:8px;">
                                <button class="btn btn-primary btn-sm" onclick="saveInterviewNotes(${session.job_id})">Save Notes</button>
                            </div>
                        </div>

                        <div style="background:var(--bg-sidebar); border:1px solid var(--border-subtle); border-radius:var(--radius-sm); padding:12px; font-size:11.5px; color:var(--text-muted); line-height:1.4;">
                            <strong style="color:var(--text-secondary);">Notice:</strong> ${escapeHtml(session.disclaimer || 'Interview materials generated for candidate preparation.')}
                        </div>
                    </div>
                </div>
            `;
        }

        async function saveAnswerDraft(jobId, questionId) {
            const textarea = document.getElementById(`draft-q-${questionId}`);
            if (!textarea) return;
            try {
                const res = await apiFetch(`/api/interview-prep/briefing/${jobId}/draft`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ question_index: questionId, draft_text: textarea.value })
                });
                if (!res.ok) throw new Error('Failed to save answer draft');
                showToast(`Question ${questionId} draft saved!`, 'success');
            } catch (err) {
                showToast(err.message, 'error');
            }
        }

        async function toggleInterviewChecklist(jobId, itemIdx, completed) {
            if (!currentInterviewBriefing || !currentInterviewBriefing.checklist) return;
            const updatedChecklist = [...currentInterviewBriefing.checklist];
            if (updatedChecklist[itemIdx]) {
                updatedChecklist[itemIdx].completed = completed;
            }
            try {
                const res = await apiFetch(`/api/interview-prep/briefing/${jobId}/checklist`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ checklist: updatedChecklist })
                });
                if (!res.ok) throw new Error('Failed to update checklist');
                currentInterviewBriefing.checklist = updatedChecklist;
                showToast('Checklist updated', 'info');
            } catch (err) {
                showToast(err.message, 'error');
            }
        }

        async function saveInterviewNotes(jobId) {
            const textarea = document.getElementById('interview-notes-input');
            if (!textarea) return;
            try {
                const res = await apiFetch(`/api/interview-prep/briefing/${jobId}/notes`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ notes: textarea.value })
                });
                if (!res.ok) throw new Error('Failed to save notes');
                showToast('Interview notes saved!', 'success');
            } catch (err) {
                showToast(err.message, 'error');
            }
        }

        async function setInterviewConfidence(jobId, rating) {
            try {
                const notes = document.getElementById('interview-notes-input')?.value || '';
                const res = await apiFetch(`/api/interview-prep/briefing/${jobId}/notes`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ notes: notes, confidence_rating: rating })
                });
                if (!res.ok) throw new Error('Failed to update confidence rating');
                if (currentInterviewBriefing) {
                    currentInterviewBriefing.confidence_rating = rating;
                    renderInterviewBriefing(currentInterviewBriefing);
                }
                showToast(`Readiness confidence set to ${rating}/5`, 'success');
            } catch (err) {
                showToast(err.message, 'error');
            }
        }
"""

norm_content = content.replace("\r\n", "\n")
norm_target = target_section.replace("\r\n", "\n")

if norm_target in norm_content:
    norm_content = norm_content.replace(norm_target, replacement_section, 1)
    print("Section replaced.")
else:
    print("WARNING: Section target not found.")

# Update loadPrepPlans function to call loadInterviewPrepJobs and handle containers
old_prep_plans = """        async function loadPrepPlans() {
            try {
                const res = await apiFetch('/api/prep/plans');
                if (!res.ok) throw new Error('Prep plans API failed');
                const data = await res.json();
                const container = document.getElementById('prep-packages-container');"""

new_prep_plans = """        async function loadPrepPlans() {
            try {
                loadInterviewPrepJobs();
                const res = await apiFetch('/api/prep/plans');
                if (!res.ok) throw new Error('Prep plans API failed');
                const data = await res.json();
                const container = document.getElementById('prep-plans-container') || document.getElementById('prep-packages-container');"""

norm_old_prep = old_prep_plans.replace("\r\n", "\n")
if norm_old_prep in norm_content:
    norm_content = norm_content.replace(norm_old_prep, new_prep_plans, 1)
    print("loadPrepPlans container query updated.")
else:
    print("WARNING: loadPrepPlans target not found.")

# Append js_code before </script>
last_script_tag = "</script>"
idx = norm_content.rfind(last_script_tag)
if idx != -1:
    norm_content = norm_content[:idx] + js_code + "\n    " + norm_content[idx:]
    print("Appended JS code.")
else:
    print("WARNING: </script> not found.")

with open(INDEX_PATH, "w", encoding="utf-8") as f:
    f.write(norm_content)

print("index.html update complete!")
