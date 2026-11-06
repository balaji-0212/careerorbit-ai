"""Update index.html with Phase 3 Daily Study Planner & Habit Tracking enhancements."""

from pathlib import Path

INDEX_HTML_PATH = Path("careerorbit/web/static/index.html")
content = INDEX_HTML_PATH.read_text(encoding="utf-8")

# 1. HTML Insertion: Daily Study Planner Card above Pathways
TARGET_HTML = '<div id="pathways-summary-container" style="margin-bottom: 20px;">'

STUDY_PLANNER_HTML = """<!-- Daily Study Planner & Habit Tracking Container -->
            <div id="daily-study-planner-card" class="card" style="margin-bottom: 20px; background: var(--bg-card); border: 1px solid var(--border-subtle); padding: 18px 20px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 10px;">
                    <div>
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <span style="font-size: 18px;">🎯</span>
                            <h3 style="font-size: 15px; font-weight: 700; color: var(--text-main); margin: 0;">Daily Personalized Study Planner</h3>
                            <span class="badge badge-purple" id="study-plan-date-badge">Today</span>
                            <span class="badge badge-green" id="study-streak-badge" style="display:none;">🔥 0 Day Streak</span>
                        </div>
                        <p style="font-size: 12px; color: var(--text-muted); margin: 3px 0 0 0;">
                            Dynamic schedule mapped directly to vacancy skill gaps extracted from high-match job listings.
                        </p>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <select id="study-plan-budget-select" onchange="generateCustomDailyPlan(false)" style="background: var(--bg-sidebar); border: 1px solid var(--border-subtle); color: var(--text-main); padding: 5px 10px; border-radius: var(--radius-sm); font-size: 12px;">
                            <option value="60">⏱️ 1.0 hr (60m)</option>
                            <option value="90">⏱️ 1.5 hrs (90m)</option>
                            <option value="120" selected>⏱️ 2.0 hrs (120m)</option>
                            <option value="150">⏱️ 2.5 hrs (150m)</option>
                            <option value="210">⏱️ 3.5 hrs (210m)</option>
                        </select>
                        <button class="btn btn-secondary btn-sm" onclick="generateCustomDailyPlan(true)">↻ Regenerate Plan</button>
                    </div>
                </div>

                <!-- Study Plan Tasks Grid -->
                <div id="study-tasks-list" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; margin-top: 12px;">
                    <div class="empty-state">Loading Today's Study Plan...</div>
                </div>

                <!-- Study Summary Footer -->
                <div id="study-plan-footer" style="margin-top: 14px; padding-top: 10px; border-top: 1px solid var(--border-subtle); display: flex; justify-content: space-between; align-items: center; font-size: 12px; color: var(--text-muted); flex-wrap: wrap; gap: 8px;">
                    <span id="study-stats-summary">Tasks Completed: 0 / 4</span>
                    <span id="study-focus-role" style="color: var(--accent); font-weight: 500;">Target: Data Analyst / BI</span>
                </div>
            </div>

            <!-- Structured Learning Pathways Container -->
            <div id="pathways-summary-container" style="margin-bottom: 20px;">"""

if TARGET_HTML in content and 'id="daily-study-planner-card"' not in content:
    content = content.replace(TARGET_HTML, STUDY_PLANNER_HTML, 1)
    print("Inserted daily-study-planner-card HTML.")

# 2. JavaScript logic insertion: loadDailyStudyPlan, generateCustomDailyPlan, toggleStudyTask
JS_TARGET = "        async function loadLearningResources() {"

JS_STUDY_CODE = """        async function loadDailyStudyPlan() {
            const container = document.getElementById('study-tasks-list');
            if (!container) return;

            try {
                const res = await apiFetch('/api/study/plan/today');
                if (!res.ok) throw new Error('Failed to load study plan');
                const plan = await res.json();

                const dateBadge = document.getElementById('study-plan-date-badge');
                if (dateBadge && plan.plan_date) {
                    dateBadge.innerText = `${plan.plan_date} • ${plan.allocated_hours || 2.0} hrs`;
                }

                const roleEl = document.getElementById('study-focus-role');
                if (roleEl && plan.target_role) {
                    roleEl.innerText = `Target: ${plan.target_role}`;
                }

                // Check streak analytics
                try {
                    const aRes = await apiFetch('/api/study/analytics/progress');
                    if (aRes.ok) {
                        const analytics = await aRes.json();
                        const streakBadge = document.getElementById('study-streak-badge');
                        if (streakBadge && analytics.current_streak_days > 0) {
                            streakBadge.style.display = 'inline-block';
                            streakBadge.innerText = `🔥 ${analytics.current_streak_days} Day Streak`;
                        }
                    }
                } catch (e) {}

                const tasks = plan.tasks || [];
                const completedCount = tasks.filter(t => t.status === 'COMPLETED').length;

                const summaryEl = document.getElementById('study-stats-summary');
                if (summaryEl) {
                    summaryEl.innerText = `Tasks Completed: ${completedCount} / ${tasks.length} (${plan.allocated_hours || 2.0} hrs scheduled)`;
                }

                if (tasks.length === 0) {
                    container.innerHTML = '<div class="empty-state" style="padding:16px;">No study tasks scheduled for today. Click Regenerate to build one.</div>';
                    return;
                }

                container.innerHTML = tasks.map(t => {
                    const isDone = t.status === 'COMPLETED';
                    const isInProgress = t.status === 'IN_PROGRESS';
                    const stageBadge = t.stage === 'CONCEPT_MASTERY' ? '📖 Concept'
                                     : t.stage === 'HANDS_ON_CODING' ? '💻 Practice'
                                     : t.stage === 'PROJECT_ARCHITECTURE' ? '🏗️ Architecture'
                                     : '🗣️ Behavioral';

                    return `
                        <div class="card" style="padding: 14px; border: 1px solid ${isDone ? 'rgba(52, 211, 153, 0.4)' : 'var(--border-subtle)'}; background: ${isDone ? 'rgba(5, 150, 105, 0.08)' : 'var(--bg-sidebar)'}; display: flex; flex-direction: column; justify-content: space-between;">
                            <div>
                                <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 6px;">
                                    <span class="badge badge-purple" style="font-size: 10px;">${stageBadge}</span>
                                    <span class="badge ${isDone ? 'badge-green' : isInProgress ? 'badge-yellow' : 'badge-secondary'}" style="font-size: 10px;">
                                        ${isDone ? '✓ Completed' : isInProgress ? '⏳ In Progress' : 'Pending'}
                                    </span>
                                </div>
                                <h4 style="font-size: 13px; font-weight: 600; color: var(--text-main); margin: 0 0 4px 0; text-decoration: ${isDone ? 'line-through' : 'none'};">
                                    ${escapeHtml(t.title)}
                                </h4>
                                <div style="font-size: 11px; color: var(--accent); margin-bottom: 6px;">
                                    ⏱️ ${t.duration_minutes}m &bull; ${escapeHtml(t.skill_tag || 'Core Skill')}
                                </div>
                                <p style="font-size: 11.5px; color: var(--text-secondary); line-height: 1.4; margin: 0 0 10px 0;">
                                    ${escapeHtml(t.explanation || '')}
                                </p>
                            </div>
                            <div style="display: flex; gap: 6px; align-items: center; margin-top: 8px;">
                                ${t.resource_url ? `
                                    <a href="${escapeHtml(t.resource_url)}" target="_blank" rel="noopener noreferrer" class="btn btn-secondary btn-sm" style="font-size: 10.5px; padding: 4px 8px; flex: 1; text-align: center; justify-content: center;">
                                        Open Link ↗
                                    </a>
                                ` : ''}
                                <button class="btn ${isDone ? 'btn-secondary' : 'btn-primary'} btn-sm" onclick="toggleStudyTask(${plan.id}, '${t.task_id}', '${t.status}')" style="font-size: 10.5px; padding: 4px 8px; flex: 1; justify-content: center;">
                                    ${isDone ? '↺ Reset' : isInProgress ? '✓ Complete' : '▶ Start'}
                                </button>
                            </div>
                        </div>
                    `;
                }).join('');
            } catch (err) {
                container.innerHTML = `<div class="error-state" style="padding:14px;">Failed to load daily plan: ${escapeHtml(err.message)}</div>`;
            }
        }

        async function generateCustomDailyPlan(forceRegenerate) {
            const budgetSelect = document.getElementById('study-plan-budget-select');
            const budget = budgetSelect ? parseInt(budgetSelect.value) : 120;

            try {
                if (forceRegenerate) {
                    const res = await apiFetch('/api/study/plan/generate', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ daily_budget_minutes: budget, target_priority: 1 })
                    });
                    if (!res.ok) throw new Error('Regeneration failed');
                    showToast('Generated fresh daily study plan!', 'success');
                }
                loadDailyStudyPlan();
            } catch (err) {
                showToast(`Failed: ${err.message}`, 'error');
            }
        }

        async function toggleStudyTask(planId, taskId, currentStatus) {
            const nextStatus = currentStatus === 'NOT_STARTED' ? 'IN_PROGRESS'
                             : currentStatus === 'IN_PROGRESS' ? 'COMPLETED'
                             : 'NOT_STARTED';

            try {
                const res = await apiFetch(`/api/study/plan/${planId}/tasks/${taskId}/status`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ status: nextStatus })
                });
                if (!res.ok) throw new Error('Failed to update task');
                showToast(`Task updated to ${nextStatus}`, 'info');
                loadDailyStudyPlan();
            } catch (err) {
                showToast(`Update error: ${err.message}`, 'error');
            }
        }

        async function loadLearningResources() {
            // Refresh daily study plan alongside library
            loadDailyStudyPlan();"""

if JS_TARGET in content and "async function loadDailyStudyPlan()" not in content:
    content = content.replace(JS_TARGET, JS_STUDY_CODE, 1)
    print("Inserted daily-study-planner JS functions.")

INDEX_HTML_PATH.write_text(content, encoding="utf-8")
print("Successfully updated index.html.")
