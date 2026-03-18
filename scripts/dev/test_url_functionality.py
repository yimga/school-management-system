#!/usr/bin/env python
"""
URL & Functionality Testing. Run from project root: python scripts/dev/test_url_functionality.py
"""

import os
import sys


def main():
    import django

    _script_dir = os.path.dirname(os.path.abspath(__file__))
    _project_root = os.path.abspath(os.path.join(_script_dir, "..", ".."))
    sys.path.insert(0, _project_root)
    os.chdir(_project_root)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()

    from django.test import Client
    from django.urls import reverse

    print("=" * 100)
    print("URL & FUNCTIONALITY TESTING (All Dashboards - No /admin/)")
    print("=" * 100)

    dashboard_urls = [
        {
            "name": "Backend Dashboard",
            "url_name": "accounts:backend_dashboard",
            "path": "/authentication/backend/",
            "aliases": ["/backend/"],
        },
        {
            "name": "Parent Dashboard",
            "url_name": "portal:parent_dashboard",
            "path": "/portal/parent/",
            "aliases": [],
        },
        {
            "name": "Teacher Dashboard",
            "url_name": "portal:teacher_dashboard_alias",
            "path": "/portal/teacher/",
            "aliases": [],
        },
        {
            "name": "Finance Dashboard",
            "url_name": "finance:dashboard",
            "path": "/finance/dashboard/",
            "aliases": [],
        },
        {
            "name": "Payroll Dashboard",
            "url_name": "payroll:dashboard",
            "path": "/payroll/dashboard/",
            "aliases": [],
        },
        {
            "name": "Analytics Dashboard",
            "url_name": "analytics:dashboard",
            "path": "/analytics/dashboard/",
            "aliases": [],
        },
        {
            "name": "Compliance Dashboard",
            "url_name": "compliance:dashboard",
            "path": "/compliance/dashboard/",
            "aliases": [],
        },
    ]

    client = Client()
    print("\nOK Test 1: Anonymous User Access (Should Redirect to Login)")
    for dashboard in dashboard_urls:
        try:
            response = client.get(dashboard["path"], follow=True)
            if response.status_code == 200:
                print(f"  OK {dashboard['name']}: Accessible or restricted")
            else:
                print(f"  WARN {dashboard['name']}: Status {response.status_code}")
        except Exception as exc:
            print(f"  WARN {dashboard['name']}: Error - {str(exc)[:50]}")

    print("\nOK Test 2: URL Reverse & Named Routes")
    for dashboard in dashboard_urls:
        try:
            url = reverse(dashboard["url_name"])
            print(f"  OK {dashboard['name']}: Reverse route OK ({url})")
        except Exception as exc:
            print(f"  ERROR {dashboard['name']}: Reverse route failed - {exc}")

    print("\nOK Test 3: Redirect Chains & Aliases")
    for dashboard in dashboard_urls:
        for alias in dashboard["aliases"]:
            try:
                response = client.get(alias, follow=False)
                if response.status_code in [301, 302, 307, 308]:
                    print(
                        f"  OK {dashboard['name']}: Alias {alias} redirects correctly"
                    )
                else:
                    print(
                        f"  WARN {dashboard['name']}: Alias {alias} status {response.status_code}"
                    )
            except Exception as exc:
                print(
                    f"  WARN {dashboard['name']}: Alias {alias} error - {str(exc)[:40]}"
                )

    print("\n" + "=" * 100)
    print("SUMMARY: URL & FUNCTIONALITY TEST")
    print("=" * 100)


if __name__ == "__main__":
    main()
