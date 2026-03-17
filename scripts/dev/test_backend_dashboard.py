#!/usr/bin/env python
"""Backend dashboard validation helper.
Run from project root: python scripts/dev/test_backend_dashboard.py
"""
import os
import re
import sys

script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, "..", ".."))
sys.path.insert(0, project_root)
os.chdir(project_root)

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.template.loader import get_template
from django.urls import reverse


def ok(msg: str) -> None:
    print(f"  [OK] {msg}")


def warn(msg: str) -> None:
    print(f"  [WARN] {msg}")


print("=" * 80)
print("BACKEND DASHBOARD VALIDATION")
print("=" * 80)

print("\n1) Template loading")
try:
    get_template("accounts/backend_dashboard.html")
    ok("accounts/backend_dashboard.html loads")
except Exception as exc:
    print(f"  [ERROR] template loading failed: {exc}")
    sys.exit(1)

print("\n2) Core structure markers")
template_path = os.path.join(project_root, "templates", "accounts", "backend_dashboard.html")
with open(template_path, "r", encoding="utf-8") as fh:
    content = fh.read()

required_markers = {
    "overview block": "backend-v2-overview",
    "welcome block": "backend-v2-welcome",
    "kpi strip": "backend-v2-kpi-strip",
    "admin portal side card": "backend-v2-side-card",
    "workspace grid": "backend-v2-main-grid",
    "ops watch card": "backend-ops-watch-card",
    "quick links card": "backend-quick-links-card",
}
for label, marker in required_markers.items():
    if marker in content:
        ok(f"{label}: found ({marker})")
    else:
        warn(f"{label}: missing ({marker})")

print("\n3) Basic HTML/style balance")
div_open = content.count("<div")
div_close = content.count("</div>")
style_open = content.count("<style")
style_close = content.count("</style>")
print(f"  div: {div_open} open / {div_close} close")
print(f"  style: {style_open} open / {style_close} close")
if div_open == div_close:
    ok("div tags balanced")
else:
    warn("div tags are not balanced")
if style_open == style_close:
    ok("style tags balanced")
else:
    warn("style tags are not balanced")

print("\n4) Inline script sanity")
script_blocks = re.findall(r"<script(?:[^>]*)>(.*?)</script>", content, re.DOTALL)
if script_blocks:
    ok(f"found {len(script_blocks)} inline script block(s)")
else:
    warn("no inline script blocks found")

print("\n5) URL reverse smoke")
url_names = [
    "accounts:backend_dashboard",
    "studio_os:workflow_center",
    "siteconfig:user_preferences",
    "studio_os:experience",
    "accounts:backend_ops_watch_data",
]
for name in url_names:
    try:
        reverse(name)
        ok(f"{name} resolves")
    except Exception as exc:
        warn(f"{name} unresolved ({exc})")

print("\n6) Regression guards")
if "backend-v2-chip-row" in content and "backend-v2-action-grid" in content:
    ok("welcome action rows are present")
else:
    warn("welcome action rows may be incomplete")

if "backend-status-fragment" in content:
    ok("status fragment placeholder present")
else:
    warn("status fragment placeholder missing")

print("\n" + "=" * 80)
print("VALIDATION COMPLETE")
print("=" * 80)
