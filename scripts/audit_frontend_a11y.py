"""Audit frontend accessibility, CSS, and DOM safety in index.html."""
import re

with open("careerorbit/web/static/index.html", "r", encoding="utf-8") as f:
    content = f.read()

has_viewport = bool(re.search(r'<meta\s+name=["\']viewport["\']', content, re.I))
has_charset = bool(re.search(r'<meta\s+charset=["\']utf-8["\']', content, re.I))
has_focus = bool(re.search(r':focus(?:-visible)?', content))
has_aria = bool(re.search(r'aria-[a-z]+=["\']', content))
has_escape = "function escapeHtml" in content
has_safe_url = "function safeJobUrl" in content

referenced_ids = set(re.findall(r"getElementById\(['\"]([^'\"]+)['\"]\)", content))
html_ids = set(re.findall(r'id=["\']([^"\']+)["\']', content))
missing_ids = referenced_ids - html_ids

print(f"Viewport meta: {has_viewport}")
print(f"UTF-8 charset: {has_charset}")
print(f"Focus styles: {has_focus}")
print(f"ARIA attributes: {has_aria}")
print(f"escapeHtml function: {has_escape}")
print(f"safeJobUrl function: {has_safe_url}")
print(f"Total HTML IDs: {len(html_ids)}")
print(f"Referenced DOM IDs: {len(referenced_ids)}")
print(f"Missing DOM IDs: {missing_ids}")
