#!/usr/bin/env python3
"""
DOM node budget gate (Chromebook UX) — HTML element count proxy without live Playwright.

Fetches authenticated smoke pages via Django test client and fails when element
counts exceed documented thresholds (see docs/PERFORMANCE_BUDGETS.md).
Optional Playwright CLS pass: run scripts/verify_dom_performance_budgets.mjs when
VISUAL_QA_PORT is up.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

if os.environ.get("DJANGO_SETTINGS_MODULE") is None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.contrib.auth import get_user_model
from django.test import Client, override_settings
from django.utils import timezone

# label, path, max_element_nodes, host
DOM_BUDGETS = (
    ("/siteconfig/zero-ticket/", 2800, "manager.runmycampus.com"),
    ("/siteconfig/zero-ticket/permissions/", 2200, "manager.runmycampus.com"),
    ("/siteconfig/zero-ticket/workflows/", 2400, "manager.runmycampus.com"),
    ("/authentication/backend/", 3500, "dom-budget.runmycampus.com"),
)


def _count_elements(html: str) -> int:
    return len(re.findall(r"<[a-zA-Z][^/>]*>", html))


def main() -> int:
    User = get_user_model()
    user = User.objects.filter(is_superuser=True).first()
    if user is None:
        user = User.objects.create_superuser(
            username="dom_budget_gate",
            password="Test1234",
            email="dom_budget@example.com",
        )
    if hasattr(user, "last_security_posture_review_at"):
        user.last_security_posture_review_at = timezone.now()
        user.save(update_fields=["last_security_posture_review_at"])
    from apps.schools.models import School

    School.objects.get_or_create(
        slug="dom-budget",
        defaults={
            "name": "DOM Budget School",
            "subdomain": "dom-budget",
            "is_active": True,
        },
    )
    failures: list[str] = []
    with override_settings(SECURE_SSL_REDIRECT=False, ALLOWED_HOSTS=["*"]):
        for path, max_nodes, host in DOM_BUDGETS:
            client = Client(HTTP_HOST=host, raise_request_exception=False)
            client.force_login(user)
            session = client.session
            session["mfa_verified"] = True
            session.save()
            resp = client.get(path, follow=True)
            if resp.status_code not in (200,):
                failures.append(f"{path}: HTTP {resp.status_code}")
                continue
            count = _count_elements(resp.content.decode("utf-8", errors="replace"))
            if count > max_nodes:
                failures.append(f"{path}: {count} elements > max {max_nodes}")
    if failures:
        print("verify_dom_performance_budgets: FAIL", file=sys.stderr)
        for line in failures:
            print(f"  {line}", file=sys.stderr)
        return 1
    print(
        f"verify_dom_performance_budgets: PASS ({len(DOM_BUDGETS)} routes within DOM budgets)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
