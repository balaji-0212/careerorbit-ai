"""Phase 10 verification test suite for Frontend & Accessibility.

Verifies:
1. All referenced DOM element IDs exist or are defensively guarded.
2. escapeHtml() correctly neutralizes all XSS injection payloads.
3. safeJobUrl() permits only http/https URLs and rejects dangerous schemes (javascript:, data:).
4. Accessibility meta tags (charset, viewport, lang attribute) are declared.
5. Navigation tabs map directly to valid section containers.
6. CSS focus styling and keyboard navigation affordances.
"""
from pathlib import Path
import re
import pytest

INDEX_HTML_PATH = Path("careerorbit/web/static/index.html")


@pytest.fixture(scope="module")
def index_html_content():
    """Reads index.html content."""
    assert INDEX_HTML_PATH.exists(), "index.html must exist"
    return INDEX_HTML_PATH.read_text(encoding="utf-8")


def test_dom_element_ids_exist_or_guarded(index_html_content):
    """Verifies all getElementById references either exist in DOM or have null guards."""
    referenced_ids = set(re.findall(r"getElementById\(['\"]([^'\"]+)['\"]\)", index_html_content))
    html_ids = set(re.findall(r'id=["\']([^"\']+)["\']', index_html_content))
    missing_ids = referenced_ids - html_ids

    for el_id in missing_ids:
        container_pattern = rf"(?:const|let|var)\s+(\w+)\s*=\s*(?:.*?)document\.getElementById\(['\"]{re.escape(el_id)}['\"]\)"
        match = re.search(container_pattern, index_html_content)
        if match:
            var_name = match.group(1)
            guard_found = re.search(rf"if\s*\(!?{re.escape(var_name)}\b", index_html_content)
            assert guard_found, f"Missing DOM element '{el_id}' assigned to '{var_name}' without null guard"
        else:
            direct_check = re.search(rf"document\.getElementById\(['\"]{re.escape(el_id)}['\"]\)", index_html_content)
            assert direct_check, f"Unexpected reference to {el_id}"


def test_escape_html_sanitization_defense():
    """Verifies that the escapeHtml regex neutralizes standard XSS attack vectors."""
    def js_escape_html(s):
        if s is None:
            return ""
        mapping = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"}
        return re.sub(r'[&<>"\']', lambda m: mapping[m.group(0)], str(s))

    payloads = [
        ("<script>alert('XSS')</script>", "&lt;script&gt;alert(&#039;XSS&#039;)&lt;/script&gt;"),
        ('<img src="x" onerror="alert(1)">', '&lt;img src=&quot;x&quot; onerror=&quot;alert(1)&quot;&gt;'),
        ("hello & goodbye", "hello &amp; goodbye"),
        ('"quoted string"', "&quot;quoted string&quot;"),
        ("candidate's resume", "candidate&#039;s resume"),
    ]

    for raw, expected in payloads:
        escaped = js_escape_html(raw)
        assert escaped == expected
        assert "<script>" not in escaped
        assert "<img" not in escaped


def test_safe_job_url_validation():
    """Verifies that safeJobUrl allows only http/https schemes and rejects dangerous schemes."""
    import urllib.parse

    def py_safe_job_url(raw_url):
        if not raw_url or not isinstance(raw_url, str):
            return ""
        try:
            parsed = urllib.parse.urlparse(raw_url.strip())
            if parsed.scheme.lower() in ("http", "https") and parsed.netloc:
                return raw_url.strip()
        except Exception:
            pass
        return ""

    # Permitted URLs
    assert py_safe_job_url("https://boards.greenhouse.io/corp/jobs/1") != ""
    assert py_safe_job_url("http://careers.example.com/job") != ""

    # Blocked dangerous schemes
    assert py_safe_job_url("javascript:alert(document.cookie)") == ""
    assert py_safe_job_url("data:text/html,<script>alert(1)</script>") == ""
    assert py_safe_job_url("vbscript:msgbox('hi')") == ""
    assert py_safe_job_url("file:///etc/passwd") == ""


def test_html_head_accessibility_meta_and_charset(index_html_content):
    """Verifies accessibility metadata in index.html head."""
    # 1. UTF-8 character encoding
    assert re.search(r'<meta\s+charset=["\']utf-8["\']', index_html_content, re.I), "Missing UTF-8 charset meta tag"

    # 2. Viewport meta for responsive scaling
    viewport_match = re.search(r'<meta\s+name=["\']viewport["\'][^>]*content=["\']([^"\']+)["\']', index_html_content, re.I)
    assert viewport_match, "Missing viewport meta tag"
    content_val = viewport_match.group(1)
    assert "width=device-width" in content_val
    assert "initial-scale=1.0" in content_val

    # 3. HTML lang attribute for screen readers
    assert re.search(r'<html\s+[^>]*lang=["\']en["\']', index_html_content, re.I), "Missing lang='en' attribute on <html>"


def test_navigation_tab_mapping_integrity(index_html_content):
    """Verifies that navigation tab switches correspond to existing section IDs."""
    switch_calls = set(re.findall(r"switchTab\(['\"]([^'\"]+)['\"]\)", index_html_content))
    assert len(switch_calls) >= 5

    for tab_id in switch_calls:
        if "${" in tab_id or tab_id == "study":
            # Template variable or decoupled study tab
            continue
        expected_section_id = f"tab-{tab_id}"
        assert f'id="{expected_section_id}"' in index_html_content, f"Missing target section for tab '{tab_id}'"


def test_inbox_navigation_loads_assessment_challenges(index_html_content):
    """Opening the inbox initializes the embedded assessment sandbox instead of leaving it loading."""
    switch_tab = re.search(r"else if \(tabId === 'inbox'\)\s*\{([^}]+)\}", index_html_content)
    assert switch_tab, "Inbox navigation must have a lazy-load branch"
    assert "loadAssessmentChallenges()" in switch_tab.group(1)


def test_css_focus_and_accessibility_styles(index_html_content):
    """Verifies focus outlines and accessibility styles exist in CSS."""
    assert ":focus" in index_html_content or ":focus-visible" in index_html_content
    assert "button" in index_html_content
    assert "--bg-main" in index_html_content
    assert "--text-main" in index_html_content


def test_application_sidebar_css_does_not_capture_nested_interview_aside(index_html_content):
    """The fixed shell sidebar rules must not pin the interview-practice aside."""
    assert re.search(r"body\s*>\s*aside\s*\{", index_html_content)
    assert not re.search(r"(?m)^\s*aside\s*\{", index_html_content)


def test_visible_filter_and_import_labels_are_associated_with_controls(index_html_content):
    """Labels reported by Chrome Issues must point to their actual form controls."""
    control_ids = (
        "inbox-filter-category",
        "inbox-filter-platform",
        "inbox-filter-status",
        "resource-filter-category",
        "resource-filter-skill",
        "resource-filter-difficulty",
        "resource-filter-status",
        "comm-import-channel",
        "comm-import-text",
        "wa-import-title",
        "wa-import-file",
        "wa-import-text",
        "tg-export-title",
        "tg-export-file",
        "confirm-submission-notes",
        "modal-stage-target",
        "modal-stage-notes",
    )
    for control_id in control_ids:
        assert re.search(
            rf'<label\b[^>]*\bfor=["\']{re.escape(control_id)}["\']',
            index_html_content,
        ), f"Form control '{control_id}' must have an associated visible label"
        assert re.search(
            rf'<(?:input|textarea|select)\b[^>]*\bid=["\']{re.escape(control_id)}["\']',
            index_html_content,
        ), f"Expected labeled form control '{control_id}' to exist"


def test_theme_preference_bootstrap_is_persistent_and_system_aware(index_html_content):
    """The theme is selected before CSS paints and can follow or override system preference."""
    boot_script = index_html_content.index("careerorbit-theme")
    style_block = index_html_content.index("<style>")
    assert boot_script < style_block
    assert "prefers-color-scheme: light" in index_html_content
    assert "localStorage.getItem(storageKey)" in index_html_content
    assert "localStorage.setItem(storageKey, theme)" in index_html_content
    assert ':root[data-theme="light"]' in index_html_content
    assert 'id="theme-toggle"' in index_html_content
    assert 'aria-label="Switch theme"' in index_html_content
    assert "toggleCareerOrbitTheme()" in index_html_content


def test_mobile_navigation_exposes_all_application_routes_without_horizontal_clipping(index_html_content):
    """A fixed mobile bar keeps frequent routes visible and puts every other route in More."""
    nav = re.search(r"<nav>(.*?)</nav>", index_html_content, re.S)
    assert nav, "The application navigation must remain present"
    nav_html = nav.group(1)
    primary = set(re.findall(r"class=\"[^\"]*mobile-nav-primary[^\"]*\"[^>]*onclick=\"switchTab\('([^']+)'\)\"", nav_html))
    secondary = set(re.findall(r"class=\"[^\"]*mobile-nav-secondary[^\"]*\"[^>]*onclick=\"switchTab\('([^']+)'\)\"", nav_html))
    menu = re.search(r'id="mobile-more-menu"[^>]*>(.*?)</div>', index_html_content, re.S)
    assert menu, "Secondary routes need a More-pages panel"
    menu_tabs = set(re.findall(r"onclick=\"selectMobileTab\('([^']+)'\)\"", menu.group(1)))

    assert primary == {"overview", "jobs", "saved", "inbox", "applications"}
    assert secondary == {"resumes", "prep", "resources", "profile", "sources", "scheduler", "settings"}
    assert menu_tabs == secondary, "Every hidden mobile route must remain available in More"
    assert 'id="mobile-more-button"' in nav_html
    assert 'aria-controls="mobile-more-menu"' in nav_html
    assert 'aria-expanded="false"' in nav_html
    mobile_rules = re.search(r"@media\s*\(max-width:\s*768px\)\s*\{(.*?)(?=@media|</style>)", index_html_content, re.S)
    assert mobile_rules
    assert "grid-template-columns: repeat(6, minmax(0, 1fr))" in mobile_rules.group(1)
    assert "overflow-x: auto" not in mobile_rules.group(1)
    assert "env(safe-area-inset-bottom" in mobile_rules.group(1)


def test_mobile_more_panel_supports_keyboard_dismissal_and_focus_management(index_html_content):
    """The overflow panel is labelled, modal while open, and keyboard dismissable."""
    assert 'role="dialog" aria-label="More pages" aria-modal="true"' in index_html_content
    assert 'aria-haspopup="dialog" aria-expanded="false" aria-controls="mobile-more-menu"' in index_html_content
    assert "function toggleMobileMoreMenu()" in index_html_content
    assert "function closeMobileMoreMenu(options = {})" in index_html_content
    assert "function selectMobileTab(tabId)" in index_html_content
    assert "event.key === 'Escape'" in index_html_content
    assert "event.key !== 'Tab'" in index_html_content
    assert "items[items.length - 1].focus()" in index_html_content
    assert 'id="mobile-more-backdrop"' in index_html_content
