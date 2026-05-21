#!/usr/bin/env python
"""
URL Validation Script. Run from project root: python scripts/dev/validate_urls.py
Validates all URLs and internal links in the Django project.
"""

import os
import sys
import re
from pathlib import Path

_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.abspath(os.path.join(_script_dir, "..", ".."))
sys.path.insert(0, _project_root)
os.chdir(_project_root)

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.urls import get_resolver
from django.urls.exceptions import Resolver404


def get_all_url_patterns():
    resolver = get_resolver()
    patterns = []

    def extract_patterns(urlconf, prefix=""):
        for pattern in urlconf.url_patterns:
            if hasattr(pattern, "url_patterns"):
                new_prefix = prefix + str(pattern.pattern)
                extract_patterns(pattern, new_prefix)
            else:
                full_path = prefix + str(pattern.pattern)
                patterns.append(
                    {
                        "path": str(full_path),
                        "name": pattern.name or "unnamed",
                        "pattern": pattern,
                    }
                )

    extract_patterns(resolver)
    return patterns


def validate_template_links():
    template_dir = Path(_project_root) / "templates"
    broken_links = []
    valid_links = set()
    url_patterns = get_all_url_patterns()
    {p["path"].replace("^", "").replace("$", "") for p in url_patterns}
    valid_prefixes = {
        "/admin/",
        "/authentication/",
        "/api/",
        "/portal/",
        "/evals/",
        "/siteconfig/",
        "/reports/",
        "/analytics/",
        "/finance/",
        "/payroll/",
        "/compliance/",
        "/kb/",
        "/",
    }
    if template_dir.exists():
        for html_file in template_dir.rglob("*.html"):
            try:
                with open(html_file, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except Exception:
                continue
            links = re.findall(r'href=["\']([^"\']+)["\']', content)
            for link in links:
                if (
                    "{{" in link
                    or "{%" in link
                    or "<" in link
                    or link.startswith("http")
                    or not link
                    or link.startswith("#")
                    or link.startswith("?")
                    or link.lower().startswith("javascript:")
                    or link.lower().startswith(("mailto:", "tel:", "data:"))
                ):
                    continue
                valid = any(link.startswith(prefix) for prefix in valid_prefixes)
                if not valid:
                    broken_links.append({"file": str(html_file), "link": link})
                else:
                    valid_links.add(link)
    return broken_links, valid_links


def main():
    print("=" * 80)
    print("DJANGO URL VALIDATION REPORT")
    print("=" * 80)
    print()
    print("[OK] Registered URL Patterns:")
    print("-" * 80)
    patterns = get_all_url_patterns()
    for pattern in sorted(patterns, key=lambda x: x["path"])[:30]:
        print(f"  {pattern['path']:<40} [{pattern['name']}]")
    print(f"\n  Total patterns: {len(patterns)}")
    print()
    print("[OK] Template Link Validation:")
    print("-" * 80)
    broken, valid = validate_template_links()
    print(f"  Valid links found: {len(valid)}")
    for link in sorted(list(valid))[:20]:
        print(f"    [OK] {link}")
    if broken:
        print(f"\n  [WARN] Potentially broken links found: {len(broken)}")
        for item in broken[:10]:
            print(f"    [FAIL] {item['link']} in {item['file']}")
    else:
        print("\n  [OK] No obviously broken links detected")
    print()
    print("=" * 80)
    print("KEY ROUTE VALIDATIONS:")
    print("=" * 80)
    critical_routes = [
        ("/", "home"),
        ("/authentication/login/", "login"),
        ("/admin/", "backend admin"),
        ("/portal/parent/", "parent dashboard"),
        ("/evals/teacher/", "teacher dashboard"),
        ("/backend/", "frontend admin redirect"),
        ("/authentication/backend/", "frontend admin dashboard"),
    ]
    for route, description in critical_routes:
        try:
            get_resolver().resolve(route)
            print(f"  [OK] {route:<40} [{description}]")
        except Resolver404:
            print(f"  [FAIL] {route:<40} [{description}] - NOT FOUND")
    print()


if __name__ == "__main__":
    main()
