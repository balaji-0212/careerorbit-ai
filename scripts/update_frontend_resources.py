"""Update index.html with Phase 2 Learning Resources Library enhancements."""

from pathlib import Path

INDEX_HTML_PATH = Path("careerorbit/web/static/index.html")

content = INDEX_HTML_PATH.read_text(encoding="utf-8")

# 1. Update HTML filter bar and pathways container
TARGET_HTML = """            <!-- Filter Bar -->
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
            </div>"""

NEW_HTML = """            <!-- Structured Learning Pathways Container -->
            <div id="pathways-summary-container" style="margin-bottom: 20px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                    <div>
                        <h3 style="font-size: 14px; font-weight: 700; color: var(--text-main); margin: 0; text-transform: uppercase; letter-spacing: 0.5px;">Structured Role Pathways</h3>
                        <p style="font-size: 12px; color: var(--text-muted); margin: 2px 0 0 0;">Step-by-step curriculum with progressive difficulty from foundational concepts to advanced production skills.</p>
                    </div>
                    <span id="pathways-total-hours" style="font-size: 12px; color: var(--accent); font-weight: 600;"></span>
                </div>
                <div id="pathways-grid" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 14px;">
                    <div class="empty-state">Loading Pathways...</div>
                </div>
            </div>

            <!-- Filter Bar -->
            <div class="card" style="margin-bottom: 16px; padding: 14px 18px;">
                <div style="display: flex; flex-wrap: wrap; gap: 12px; align-items: center; justify-content: space-between;">
                    <div style="display: flex; flex-wrap: wrap; gap: 8px; align-items: center;">
                        <label style="font-size: 12px; color: var(--text-secondary); font-weight: 600;">Category:</label>
                        <select id="resource-filter-category" onchange="loadLearningResources()" style="background: var(--bg-sidebar); border: 1px solid var(--border-subtle); color: var(--text-main); padding: 6px 12px; border-radius: var(--radius-sm); font-size: 12px;">
                            <option value="">All Categories</option>
                            <option value="Technical Learning Materials">Technical Learning & Docs</option>
                            <option value="Coding Practice">Coding Practice & DSA</option>
                            <option value="Interview Preparation">Interview Preparation</option>
                            <option value="Certifications and Courses">Certifications & Courses</option>
                        </select>

                        <label style="font-size: 12px; color: var(--text-secondary); font-weight: 600; margin-left: 6px;">Skill:</label>
                        <select id="resource-filter-skill" onchange="loadLearningResources()" style="background: var(--bg-sidebar); border: 1px solid var(--border-subtle); color: var(--text-main); padding: 6px 12px; border-radius: var(--radius-sm); font-size: 12px;">
                            <option value="">All Skills</option>
                            <option value="python">Python</option>
                            <option value="sql">SQL</option>
                            <option value="power_bi">Power BI</option>
                            <option value="dax">DAX</option>
                            <option value="data_engineering">Data Engineering</option>
                            <option value="pyspark">PySpark</option>
                            <option value="fastapi">FastAPI</option>
                            <option value="data_modeling">Data Modeling</option>
                            <option value="dsa">DSA & Algorithms</option>
                            <option value="data_analysis">Data Analysis</option>
                        </select>

                        <label style="font-size: 12px; color: var(--text-secondary); font-weight: 600; margin-left: 6px;">Difficulty:</label>
                        <select id="resource-filter-difficulty" onchange="loadLearningResources()" style="background: var(--bg-sidebar); border: 1px solid var(--border-subtle); color: var(--text-main); padding: 6px 12px; border-radius: var(--radius-sm); font-size: 12px;">
                            <option value="">All Levels</option>
                            <option value="BEGINNER">Beginner</option>
                            <option value="INTERMEDIATE">Intermediate</option>
                            <option value="ADVANCED">Advanced</option>
                        </select>

                        <label style="font-size: 12px; color: var(--text-secondary); font-weight: 600; margin-left: 6px;">Status:</label>
                        <select id="resource-filter-status" onchange="loadLearningResources()" style="background: var(--bg-sidebar); border: 1px solid var(--border-subtle); color: var(--text-main); padding: 6px 12px; border-radius: var(--radius-sm); font-size: 12px;">
                            <option value="">All Statuses</option>
                            <option value="pending">Incomplete Only</option>
                            <option value="completed">Completed Only</option>
                        </select>
                    </div>

                    <div style="display: flex; gap: 8px; flex: 1; max-width: 320px;">
                        <input type="text" id="resource-search-input" placeholder="Search title, tags, description..." oninput="debouncedLoadResources()" style="width: 100%; background: var(--bg-sidebar); border: 1px solid var(--border-subtle); color: var(--text-main); padding: 6px 12px; border-radius: var(--radius-sm); font-size: 12px;">
                    </div>
                </div>
            </div>"""

# Standardize line endings for matching
target_crlf = TARGET_HTML.replace("\r\n", "\n").replace("\n", "\r\n")
target_lf = TARGET_HTML.replace("\r\n", "\n")

if target_crlf in content:
    content = content.replace(target_crlf, NEW_HTML.replace("\n", "\r\n"), 1)
    print("Replaced HTML section (CRLF)")
elif target_lf in content:
    content = content.replace(target_lf, NEW_HTML, 1)
    print("Replaced HTML section (LF)")
else:
    print("WARNING: Could not find TARGET_HTML")

INDEX_HTML_PATH.write_text(content, encoding="utf-8")
print("Saved HTML update")
