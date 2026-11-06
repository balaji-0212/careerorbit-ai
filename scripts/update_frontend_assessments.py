"""Update index.html with Phase 4 Technical Assessment Sandbox UI and handlers."""

from pathlib import Path

INDEX_HTML_PATH = Path("careerorbit/web/static/index.html")
content = INDEX_HTML_PATH.read_text(encoding="utf-8")

# 1. HTML Insertion: Assessment Practice Sandbox Card below Pathways and above Filter Bar
TARGET_HTML = '<!-- Filter Bar -->'

ASSESSMENT_SANDBOX_HTML = """<!-- Technical Assessment Practice Sandbox Container -->
            <div id="assessment-sandbox-card" class="card" style="margin-bottom: 24px; background: var(--bg-card); border: 1px solid var(--border-subtle); padding: 18px 20px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 10px;">
                    <div>
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <span style="font-size: 18px;">⚡</span>
                            <h3 style="font-size: 15px; font-weight: 700; color: var(--text-main); margin: 0;">Technical Assessment Sandbox & Coding Practice</h3>
                            <span class="badge badge-purple" id="assess-stats-badge">14 Challenges Available</span>
                        </div>
                        <p style="font-size: 12px; color: var(--text-muted); margin: 3px 0 0 0;">
                            In-memory sandboxed evaluations for SQL queries (Window functions, joins, aggregations) and core Python/Data Engineering/ML principles.
                        </p>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <select id="assess-filter-category" onchange="filterAssessmentChallenges()" style="background: var(--bg-sidebar); border: 1px solid var(--border-subtle); color: var(--text-main); padding: 5px 10px; border-radius: var(--radius-sm); font-size: 12px;">
                            <option value="">All Categories</option>
                            <option value="SQL">SQL Queries</option>
                            <option value="PYTHON">Python & Data Analysis</option>
                            <option value="DATA_ENGINEERING">Cloud Data Engineering</option>
                            <option value="MACHINE_LEARNING">Machine Learning</option>
                        </select>
                    </div>
                </div>

                <!-- Challenge Workspace Grid -->
                <div style="display: grid; grid-template-columns: minmax(280px, 1fr) minmax(340px, 1.4fr); gap: 16px; margin-top: 12px;">
                    <!-- Challenge Selection List -->
                    <div id="assess-challenges-list" style="display: flex; flex-direction: column; gap: 8px; max-height: 420px; overflow-y: auto; padding-right: 6px;">
                        <div class="empty-state">Loading Challenges...</div>
                    </div>

                    <!-- Active Challenge Workspace -->
                    <div id="assess-active-workspace" style="background: var(--bg-sidebar); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); padding: 16px; display: flex; flex-direction: column; justify-content: space-between;">
                        <div id="assess-workspace-content">
                            <div class="empty-state" style="padding: 30px;">Select a challenge on the left to begin practice.</div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Filter Bar -->"""

if TARGET_HTML in content and 'id="assessment-sandbox-card"' not in content:
    content = content.replace(TARGET_HTML, ASSESSMENT_SANDBOX_HTML, 1)
    print("Inserted assessment-sandbox-card HTML.")

# 2. JavaScript logic insertion: loadAssessmentChallenges, selectChallenge, submitEvaluation
JS_TARGET = "        async function loadDailyStudyPlan() {"

JS_ASSESS_CODE = """        let allAssessmentChallenges = [];
        let activeChallengeId = null;

        async function loadAssessmentChallenges() {
            const container = document.getElementById('assess-challenges-list');
            if (!container) return;

            try {
                const res = await apiFetch('/api/assessments/challenges');
                if (!res.ok) throw new Error('Failed to load challenges');
                const data = await res.json();
                allAssessmentChallenges = data.challenges || [];

                const statsBadge = document.getElementById('assess-stats-badge');
                if (statsBadge) {
                    statsBadge.innerText = `${allAssessmentChallenges.length} Challenges Available`;
                }

                renderAssessmentChallengesList();
                if (allAssessmentChallenges.length > 0 && !activeChallengeId) {
                    selectAssessmentChallenge(allAssessmentChallenges[0].id);
                }
            } catch (err) {
                container.innerHTML = `<div class="error-state" style="padding:14px;">Error: ${escapeHtml(err.message)}</div>`;
            }
        }

        function filterAssessmentChallenges() {
            renderAssessmentChallengesList();
        }

        function renderAssessmentChallengesList() {
            const container = document.getElementById('assess-challenges-list');
            if (!container) return;

            const cat = (document.getElementById('assess-filter-category')?.value || '').trim();
            const filtered = allAssessmentChallenges.filter(c => !cat || c.category === cat);

            if (filtered.length === 0) {
                container.innerHTML = '<div class="empty-state" style="padding:16px;">No challenges found for selected category.</div>';
                return;
            }

            container.innerHTML = filtered.map(c => {
                const isActive = (c.id === activeChallengeId);
                const diffBadge = c.difficulty === 'EASY' ? 'badge-green' : c.difficulty === 'MEDIUM' ? 'badge-purple' : 'badge-amber';

                return `
                    <div onclick="selectAssessmentChallenge(${c.id})" style="padding: 10px 12px; border-radius: var(--radius-sm); border: 1px solid ${isActive ? 'var(--accent)' : 'var(--border-subtle)'}; background: ${isActive ? 'rgba(99, 102, 241, 0.12)' : 'var(--bg-sidebar)'}; cursor: pointer; transition: all 0.2s ease;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                            <span class="badge ${diffBadge}" style="font-size: 9.5px;">${c.difficulty}</span>
                            <span style="font-size: 10.5px; color: var(--text-muted); font-weight: 600;">${escapeHtml(c.category)}</span>
                        </div>
                        <div style="font-size: 12px; font-weight: 600; color: ${isActive ? 'var(--accent)' : 'var(--text-main)'}; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                            ${escapeHtml(c.title)}
                        </div>
                    </div>
                `;
            }).join('');
        }

        async function selectAssessmentChallenge(challengeId) {
            activeChallengeId = challengeId;
            renderAssessmentChallengesList();

            const workspace = document.getElementById('assess-workspace-content');
            if (!workspace) return;

            const c = allAssessmentChallenges.find(item => item.id === challengeId);
            if (!c) return;

            const isQuery = (c.question_type === 'QUERY');

            workspace.innerHTML = `
                <div>
                    <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px;">
                        <h4 style="font-size: 14.5px; font-weight: 700; color: var(--text-main); margin: 0;">${escapeHtml(c.title)}</h4>
                        <span class="badge badge-purple" style="font-size: 10px;">${c.category} &bull; ${c.difficulty}</span>
                    </div>
                    <p style="font-size: 12px; color: var(--text-secondary); line-height: 1.5; margin: 0 0 12px 0;">
                        ${escapeHtml(c.prompt_markdown)}
                    </p>

                    ${isQuery ? `
                        <div style="margin-bottom: 12px;">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                                <label style="font-size: 11px; color: var(--text-muted); font-weight: 600;">SQL Query Editor (In-Memory Sandbox):</label>
                                <span style="font-size: 10.5px; color: var(--accent);">SELECT / WITH only</span>
                            </div>
                            <textarea id="assess-submission-input" rows="7" style="width: 100%; font-family: monospace; font-size: 12px; background: rgba(15, 23, 42, 0.6); color: #38bdf8; border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); padding: 8px; resize: vertical;">${escapeHtml(c.initial_code || '')}</textarea>
                        </div>
                    ` : `
                        <div style="margin-bottom: 14px;">
                            <label style="font-size: 11.5px; color: var(--text-muted); font-weight: 600; display: block; margin-bottom: 8px;">Select Correct Answer Option:</label>
                            <div style="display: flex; flex-direction: column; gap: 6px;">
                                ${(c.options || []).map(opt => `
                                    <label style="display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--text-main); background: rgba(15, 23, 42, 0.4); padding: 8px 10px; border-radius: var(--radius-sm); border: 1px solid var(--border-subtle); cursor: pointer;">
                                        <input type="radio" name="assess-mc-opt" value="${opt.key}" style="cursor: pointer;">
                                        <strong style="color: var(--accent); min-width: 16px;">${opt.key}.</strong>
                                        <span>${escapeHtml(opt.text)}</span>
                                    </label>
                                `).join('')}
                            </div>
                        </div>
                    `}

                    <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 10px;">
                        <button class="btn btn-primary btn-sm" onclick="runAssessmentEvaluation(${c.id}, '${c.question_type}')" style="display: inline-flex; align-items: center; gap: 6px;">
                            ▶ Run & Evaluate Sandbox
                        </button>
                        <span id="assess-timer-notice" style="font-size: 11px; color: var(--text-muted);">⏱️ ${c.time_limit_minutes}m time limit</span>
                    </div>

                    <!-- Evaluation Result Output Box -->
                    <div id="assess-eval-result" style="margin-top: 14px; display: none;"></div>
                </div>
            `;
        }

        async function runAssessmentEvaluation(challengeId, questionType) {
            let submittedCode = '';
            if (questionType === 'QUERY') {
                const textarea = document.getElementById('assess-submission-input');
                submittedCode = textarea ? textarea.value.trim() : '';
                if (!submittedCode) {
                    showToast('Please enter an SQL query to evaluate.', 'warning');
                    return;
                }
            } else {
                const selected = document.querySelector('input[name="assess-mc-opt"]:checked');
                submittedCode = selected ? selected.value.trim() : '';
                if (!submittedCode) {
                    showToast('Please select one of the options.', 'warning');
                    return;
                }
            }

            const resultEl = document.getElementById('assess-eval-result');
            if (resultEl) {
                resultEl.style.display = 'block';
                resultEl.innerHTML = '<div class="card" style="padding: 10px; font-size: 12px; color: var(--text-muted);">Executing in isolated sandbox...</div>';
            }

            try {
                const res = await apiFetch(`/api/assessments/challenges/${challengeId}/evaluate`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ submitted_code: submittedCode })
                });

                if (!res.ok) {
                    const err = await res.json();
                    throw new Error(err.detail || 'Evaluation failed');
                }

                const data = await res.json();
                const isPassed = data.is_passed;

                if (resultEl) {
                    resultEl.innerHTML = `
                        <div class="card" style="padding: 12px; border: 1px solid ${isPassed ? 'rgba(52, 211, 153, 0.5)' : 'rgba(239, 68, 68, 0.5)'}; background: ${isPassed ? 'rgba(5, 150, 105, 0.08)' : 'rgba(239, 68, 68, 0.08)'};">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                                <strong style="font-size: 13px; color: ${isPassed ? 'var(--success)' : 'var(--danger)'};">
                                    ${isPassed ? '✓ PASSED (100% Score)' : '✕ FAILED'}
                                </strong>
                                <span style="font-size: 11px; color: var(--text-muted);">${data.execution_time_ms}ms runtime</span>
                            </div>
                            <p style="font-size: 12px; color: var(--text-main); margin: 0 0 8px 0;">
                                ${escapeHtml(data.feedback_notes || '')}
                            </p>
                            ${data.explanation ? `
                                <div style="font-size: 11.5px; color: var(--text-secondary); border-top: 1px dashed var(--border-subtle); padding-top: 6px;">
                                    <strong>Explanation:</strong> ${escapeHtml(data.explanation)}
                                </div>
                            ` : ''}
                        </div>
                    `;
                }

                showToast(isPassed ? 'Challenge passed successfully! ✓' : 'Incorrect submission. Review feedback.', isPassed ? 'success' : 'warning');
            } catch (err) {
                if (resultEl) {
                    resultEl.innerHTML = `<div class="card" style="padding: 10px; border: 1px solid var(--danger); color: var(--danger); font-size: 12px;">Error: ${escapeHtml(err.message)}</div>`;
                }
                showToast(`Sandbox error: ${err.message}`, 'error');
            }
        }

        async function loadDailyStudyPlan() {"""

if JS_TARGET in content and "async function loadAssessmentChallenges()" not in content:
    content = content.replace(JS_TARGET, JS_ASSESS_CODE, 1)
    print("Inserted assessment sandbox JS functions.")

# Call loadAssessmentChallenges inside loadLearningResources
LOAD_RES_TARGET = "loadDailyStudyPlan();"
LOAD_RES_REPLACEMENT = "loadDailyStudyPlan(); loadAssessmentChallenges();"

if LOAD_RES_TARGET in content and "loadAssessmentChallenges();" not in content:
    content = content.replace(LOAD_RES_TARGET, LOAD_RES_REPLACEMENT, 1)
    print("Linked loadAssessmentChallenges to loadLearningResources.")

INDEX_HTML_PATH.write_text(content, encoding="utf-8")
print("Successfully updated index.html for Phase 4.")
