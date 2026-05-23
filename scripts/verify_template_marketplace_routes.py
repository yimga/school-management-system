"""Verifier — every ExperienceTemplate URL route name resolves cleanly."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _bootstrap() -> None:
    here = Path(__file__).resolve().parent
    repo_root = here.parent
    sys.path.insert(0, str(repo_root))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()


def main() -> int:
    _bootstrap()
    from django.urls import NoReverseMatch, reverse

    expected_routes = [
        ("configuration:experience_template_marketplace", {}),
        ("configuration:experience_template_detail", {"key": "operator-executive-command-center"}),
        ("configuration:experience_template_preview", {"key": "operator-executive-command-center"}),
        ("configuration:experience_template_simulation", {"key": "operator-executive-command-center"}),
        ("configuration:experience_template_impact", {"key": "operator-executive-command-center"}),
        ("configuration:experience_template_apply", {"key": "operator-executive-command-center"}),
    ]
    expected_tenant_routes = [
        ("template_marketplace:browse", {}),
        ("template_marketplace:ai_recommend", {}),
        ("template_marketplace:local_catalog", {"country_code": "IN"}),
        ("template_marketplace:detail", {"key": "admin-school-command-center"}),
        ("template_marketplace:preview", {"key": "admin-school-command-center"}),
        ("template_marketplace:compare", {"key": "admin-school-command-center"}),
        ("template_marketplace:apply", {"key": "admin-school-command-center"}),
        ("template_marketplace:rollback", {"key": "admin-school-command-center"}),
        ("template_marketplace:customize", {"key": "admin-school-command-center"}),
    ]
    failures = []
    for name, kwargs in expected_routes:
        try:
            reverse(name, kwargs=kwargs)
        except NoReverseMatch as exc:
            failures.append(f"{name}: {exc}")
    for name, kwargs in expected_tenant_routes:
        try:
            reverse(name, kwargs=kwargs, urlconf="config.tenant_urls")
        except NoReverseMatch as exc:
            failures.append(f"{name} (tenant urlconf): {exc}")
    if failures:
        print("FAIL: route resolution failures")
        for f in failures:
            print(f"  {f}")
        return 1
    total = len(expected_routes) + len(expected_tenant_routes)
    print(f"TEMPLATE_MARKETPLACE_ROUTES_PASS ({total}/{total} routes resolved)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
