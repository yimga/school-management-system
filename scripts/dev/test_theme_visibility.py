#!/usr/bin/env python
"""
Comprehensive Theme Testing - Check all dashboards for dark/light mode visibility.
Run from project root: python scripts/dev/test_theme_visibility.py
"""

import os
import re
import sys


def main():
    import django

    _script_dir = os.path.dirname(os.path.abspath(__file__))
    _project_root = os.path.abspath(os.path.join(_script_dir, "..", ".."))
    sys.path.insert(0, _project_root)
    os.chdir(_project_root)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()

    from django.template.loader import get_template

    print("=" * 100)
    print("COMPREHENSIVE THEME VISIBILITY TEST (Light & Dark Mode)")
    print("=" * 100)

    dashboard_templates = [
        "accounts/backend_dashboard.html",
        "parent/dashboard.html",
        "teacher/dashboard.html",
        "finance/dashboard.html",
        "payroll/dashboard.html",
        "analytics/dashboard.html",
        "compliance/dashboard.html",
        "siteconfig/theme_colors.html",  # Theme & Experience
    ]
    base_templates_with_guard = [
        "base.html",
        "portal_base.html",
        "admin/base_site.html",
        "admin/login.html",
    ]

    print("\nOK Test 1: Template Syntax for Theme Support")
    for template_name in dashboard_templates:
        try:
            get_template(template_name)
            print(f"  OK {template_name}: Loads successfully")
        except Exception as exc:
            print(f"  ERROR {template_name}: Error - {exc}")

    print("\nOK Test 1b: Base Templates Load theme-visibility-guard.css")
    for template_name in base_templates_with_guard:
        try:
            t = get_template(template_name)
            content = t.origin.loader.get_contents(t.origin)
            if isinstance(content, bytes):
                content = content.decode("utf-8", errors="replace")
            if "theme-visibility-guard.css" in content:
                print(f"  OK {template_name}: Loads guard")
            else:
                print(
                    f"  WARN {template_name}: Does not reference theme-visibility-guard.css"
                )
        except Exception as exc:
            print(f"  ERROR {template_name}: {exc}")

    print("\nOK Test 1c: Guard CSS File (--vis-* and .theme-experience-page)")
    guard_path = os.path.join(
        _project_root, "static", "css", "theme-visibility-guard.css"
    )
    if os.path.isfile(guard_path):
        with open(guard_path, "r", encoding="utf-8") as f:
            guard_content = f.read()
        checks = [
            ("--vis-text", "Guard defines --vis-text"),
            ("--vis-text-muted", "Guard defines --vis-text-muted"),
            (".theme-experience-page", "Guard styles .theme-experience-page"),
        ]
        for pattern, label in checks:
            if pattern in guard_content:
                print(f"  OK {label}")
            else:
                print(f"  WARN {label}: not found in theme-visibility-guard.css")
    else:
        print(f"  WARN theme-visibility-guard.css not found at {guard_path}")

    print("\nOK Test 2: CSS Color Definitions (Dark & Light Mode)")
    color_checks = {
        "Primary Blue": "#3b82f6",
        "Dark Background": "#1e293b",
        "Light Background": "#f8fafc",
        "Text on Light": "#1e293b",
        "Text on Dark": "#e2e8f0",
        "Button Visibility": ["rgba(59, 130, 246", "#3b82f6", "#0d6efd"],
    }

    backend_template_path = os.path.join(
        _project_root,
        "templates/accounts/backend_dashboard.html",
    )
    with open(backend_template_path, "r", encoding="utf-8") as handle:
        content = handle.read()

    for name, colors in color_checks.items():
        if isinstance(colors, list):
            found = any(color in content for color in colors)
        else:
            found = colors in content
        if found:
            print(f"  OK {name}: Defined")
        else:
            print(f"  WARN {name}: Not explicitly defined (using defaults)")

    print("\nOK Test 3: Button Styling for Both Themes")
    for selector, name in [
        (".btn-primary", "Primary buttons"),
        (".btn-outline-primary", "Outline primary buttons"),
        (".btn-outline-secondary", "Outline secondary buttons"),
        (".btn-success", "Success buttons"),
        (".btn-danger", "Danger buttons"),
    ]:
        if selector in content:
            print(f"  OK {name}: Styled")
        else:
            print(f"  WARN {name}: Using defaults")

    print("\nOK Test 4: Form Controls (Input, Select, etc.)")
    for check, name in [
        (".form-control", "Text inputs"),
        (".form-select", "Select dropdowns"),
        (".form-label", "Form labels"),
        ("focus", "Focus states"),
        ("border", "Border visibility"),
    ]:
        if check in content:
            print(f"  OK {name}: Styled")
        else:
            print(f"  WARN {name}: Using defaults")

    print("\nOK Test 5: Floating Sidebar Theme Support")
    for pattern, name in [
        ("floating-sidebar", "Sidebar container"),
        ("background: linear-gradient", "Sidebar background"),
        ("color: #e2e8f0", "Sidebar text color"),
        ("sidebar-nav-link", "Navigation links"),
    ]:
        if pattern in content:
            print(f"  OK {name}: Properly defined")
        else:
            print(f"  WARN {name}: May need theme support")

    print("\nOK Test 6: Responsive Design & Media Queries")
    for pattern, name in [
        ("@media", "Media queries"),
        ("(max-width:", "Breakpoints"),
        ("display: none", "Responsive hiding"),
        ("transform:", "Mobile animations"),
    ]:
        if pattern in content:
            print(f"  OK {name}: Implemented")
        else:
            print(f"  WARN {name}: Not found")

    print("\nOK Test 7: Contrast & Readability")
    if "background: linear-gradient" in content:
        print("  OK Gradients used (better contrast)")
    else:
        print("  WARN Solid colors only (ensure sufficient contrast)")
    if "#fff" in content or "#ffffff" in content or "white" in content:
        print("  OK White text for dark backgrounds")
    else:
        print("  WARN May need white text addition")
    if "#000" in content or "#1e293b" in content or "black" in content:
        print("  OK Dark text for light backgrounds")
    else:
        print("  WARN May need dark text addition")

    print("\nOK Test 8: AI Copilot Component Theme Support")
    if "ai-copilot" in content:
        print("  OK AI Copilot included")
        if "background: linear-gradient(135deg, #6366f1" in content:
            print("  OK Copilot has gradient styling")
        else:
            print("  WARN Copilot styling may need review")
    else:
        print("  ERROR AI Copilot not included in backend dashboard")

    print("\nOK Test 9: KPI Cards Theme Support")
    if ".kpi-card" in content:
        print("  OK KPI cards styled")
        if "box-shadow" in content:
            print("  OK Cards have shadows (good depth)")
        if "border" in content:
            print("  OK Cards have borders (good definition)")
    else:
        print("  WARN KPI cards styling not found")

    print("\nOK Test 10: Analytics Filters Theme Support")
    if ".analytics-filters" in content:
        print("  OK Analytics filters styled")
    else:
        print("  WARN Analytics filters styling not found")

    print("\nOK Test 11: Link & URL Visibility")
    if "color: " not in content and "a {" not in content:
        print("  WARN Link colors not explicitly defined")
    else:
        print("  OK Link colors properly defined")

    print("\nOK Test 12: Bootstrap Framework Integration")
    if "bootstrap" in content.lower() or "btn-" in content:
        print("  OK Bootstrap classes used")
    else:
        print("  WARN Bootstrap may not be fully utilized")

    print("\n" + "=" * 100)
    print("SUMMARY: THEME VISIBILITY TESTING")
    print("=" * 100)


if __name__ == "__main__":
    main()
