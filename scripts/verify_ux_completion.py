#!/usr/bin/env python3
"""
Executable UX completion audit for the zero-backlog dashboard/setup/marketplace/marketing pass.

This script verifies the core contract rather than relying on historical docs:
- role-home dashboard contract
- Setup Studio product payload
- required private-surface template markers
- required public proof-page route markers
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.db import OperationalError
from django.test import RequestFactory
from django.test.utils import override_settings

from apps.dashboard.context import build_dashboard_extras
from apps.schools.models import School
from apps.schools.marketing_views import (
    compare_marketing_page,
    developer_marketing_page,
    marketplace_marketing_page,
    migrate_marketing_page,
    setup_simulator_page,
)
from apps.setup_studio.services import get_setup_studio_payload


User = get_user_model()


def _check(condition: bool, label: str, detail: str, failures: list[str]) -> None:
    if condition:
        print(f"OK   {label}")
        return
    failures.append(f"{label}: {detail}")
    print(f"FAIL {label}: {detail}", file=sys.stderr)


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def audit_dashboard_contract(failures: list[str]) -> None:
    factory = RequestFactory()
    suffix = uuid.uuid4().hex[:8]
    user = User.objects.create_user(
        username=f"ux-audit-{suffix}",
        password="test-pass-123",
        email=f"ux-audit-{suffix}@example.com",
        role=User.Role.ADMIN,
    )
    user.is_staff = True
    user.save(update_fields=["is_staff"])

    try:
        request = factory.get("/authentication/backend/")
        request.user = user
        request.session = {}
        extras = build_dashboard_extras(
            request, base={"stats": {}, "gce_enabled": False}
        )

        contract = extras.get("dashboard_contract") or {}
        role_home = extras.get("role_home") or {}
        destinations = extras.get("role_home_destinations") or []

        _check(
            bool(role_home),
            "dashboard.role_home",
            "role home payload missing",
            failures,
        )
        _check(
            role_home.get("default_intent") == "setup",
            "dashboard.default_intent",
            f"expected setup, got {role_home.get('default_intent')!r}",
            failures,
        )
        _check(
            contract.get("primary_action_count") == 1,
            "dashboard.primary_action_band",
            f"expected 1 dominant CTA, got {contract.get('primary_action_count')!r}",
            failures,
        )
        _check(
            3 <= int(contract.get("metric_count") or 0) <= 6,
            "dashboard.metric_limit",
            f"expected 3-6 metrics, got {contract.get('metric_count')!r}",
            failures,
        )
        _check(
            int(contract.get("urgent_queue_count") or 0) >= 1,
            "dashboard.urgent_queue",
            "urgent queue is empty",
            failures,
        )
        _check(
            int(contract.get("recommended_count") or 0) >= 1,
            "dashboard.recommended_next",
            "recommended-next block is empty",
            failures,
        )
        _check(
            int(contract.get("recent_count") or 0) >= 1,
            "dashboard.recent_activity",
            "recent-activity block is empty",
            failures,
        )
        _check(
            1 <= len(destinations) <= 5,
            "dashboard.role_destinations",
            f"expected 1-5 role destinations, got {len(destinations)}",
            failures,
        )
    finally:
        try:
            user.delete()
        except OperationalError as e:
            # Stale test DB (e.g. --keepdb from before automation.exception_ack_by migration)
            if "no such column" in str(e).lower():
                import warnings
                warnings.warn(
                    f"verify_ux_completion: could not delete audit user (stale test DB): {e}. "
                    "Run gate with fresh DB (PRE_GATE_FRESH_TEST_DB=1) or apply migrations.",
                    UserWarning,
                    stacklevel=2,
                )
            else:
                raise


def audit_setup_studio_contract(failures: list[str]) -> None:
    suffix = uuid.uuid4().hex[:8]
    school = School.objects.create(
        name=f"UX Audit School {suffix}",
        slug=f"ux-audit-{suffix}",
        subdomain=f"uxaudit{suffix}",
        is_active=True,
    )

    try:
        payload = get_setup_studio_payload(school)
        preview_titles = {item["title"] for item in payload.get("preview_cards", [])}
        role_codes = {item["role"] for item in payload.get("role_previews", [])}

        _check(
            bool(payload.get("current_step")),
            "setup.current_step",
            "current step missing",
            failures,
        )
        _check(
            bool(payload.get("health_summary")),
            "setup.health_summary",
            "health summary missing",
            failures,
        )
        _check(
            bool(payload.get("launch_checklist")),
            "setup.launch_checklist",
            "launch checklist missing",
            failures,
        )
        _check(
            bool(payload.get("launch_blockers")),
            "setup.launch_blockers",
            "launch blockers missing",
            failures,
        )
        _check(
            {"School website", "Admin shell", "Teacher dashboard", "Parent portal"}
            <= preview_titles,
            "setup.live_previews",
            f"preview cards missing: {sorted({'School website', 'Admin shell', 'Teacher dashboard', 'Parent portal'} - preview_titles)}",
            failures,
        )
        _check(
            role_codes == {"admin", "teacher", "parent", "finance", "student"},
            "setup.role_previews",
            f"unexpected role previews: {sorted(role_codes)}",
            failures,
        )
    finally:
        school.delete()


def audit_template_markers(failures: list[str]) -> None:
    template_expectations = {
        "templates/accounts/backend_dashboard.html": [
            "Command center",
            "backend-role-home-panel",
            "backend-role-home-destinations",
            "backendCommandPalette",
        ],
        "templates/customersuccess/guided_onboarding.html": [
            "Setup Studio",
            "Live previews",
            "Launch blockers",
            "Launch checklist",
        ],
        "templates/marketplace/app_catalog.html": [
            "Install with trust, not guesswork.",
            "Sandbox-first rollout available for every install from this page.",
            "Rollback and safety posture",
        ],
        "templates/marketplace/tenant_app_catalog.html": [
            "Install with confidence.",
            "Install to sandbox",
            "Rollback expectations",
        ],
        "templates/marketing/marketing_migrate_page.html": [
            "Migration cloud",
            "Why schools switch now",
        ],
        "templates/marketing/marketing_marketplace_page.html": [
            "Curated ecosystem",
            "Why switch to this model",
        ],
        "templates/marketing/marketing_setup_simulator.html": [
            "Preview the launch studio before you sign in.",
            "Role previews",
        ],
        "templates/marketing/marketing_compare_page.html": [
            "Why switch now",
            "proof-compare-table",
        ],
        "templates/marketing/marketing_developer_page.html": [
            "Developer platform",
            "Why this matters for the platform story",
        ],
        "templates/marketing/marketing_role_page.html": [
            "Role home",
            "Role home mockup",
            "Why this role should switch",
        ],
        "static/marketing/css/proof-pages.css": [
            ".proof-page",
            ".proof-hero",
            ".proof-card-grid",
        ],
    }

    for relative_path, markers in template_expectations.items():
        content = _read(relative_path)
        missing = [marker for marker in markers if marker not in content]
        _check(
            not missing,
            f"template.{relative_path}",
            f"missing markers: {missing}",
            failures,
        )


def audit_public_routes(failures: list[str]) -> None:
    factory = RequestFactory()
    route_expectations = [
        (
            "route.migrate",
            "/migrate/",
            migrate_marketing_page,
            {"source_slug": None},
            "Why schools switch now",
        ),
        (
            "route.marketplace",
            "/marketplace/",
            marketplace_marketing_page,
            {},
            "Curated ecosystem",
        ),
        (
            "route.setup_simulator",
            "/getting-started/simulator/",
            setup_simulator_page,
            {},
            "Preview the launch studio before you sign in.",
        ),
        (
            "route.compare",
            "/compare/power-school/",
            compare_marketing_page,
            {"competitor_slug": "power-school"},
            "Why switch now",
        ),
        (
            "route.developer",
            "/developers/api/",
            developer_marketing_page,
            {"section_slug": "api"},
            "Developer platform",
        ),
    ]
    with override_settings(ROOT_URLCONF="config.public_urls"):
        for label, path, view, kwargs, marker in route_expectations:
            request = factory.get(path, HTTP_HOST="localhost")
            request.user = AnonymousUser()
            request.session = {}
            response = view(request, **kwargs)
            if hasattr(response, "render"):
                response = response.render()
            body = response.content.decode("utf-8", errors="ignore")
            _check(
                response.status_code == 200,
                f"{label}.status",
                f"expected 200, got {response.status_code}",
                failures,
            )
            _check(
                marker in body,
                f"{label}.marker",
                f"missing marker {marker!r}",
                failures,
            )


def main() -> int:
    failures: list[str] = []
    audit_dashboard_contract(failures)
    audit_setup_studio_contract(failures)
    audit_template_markers(failures)
    audit_public_routes(failures)

    if failures:
        print("\nUX completion audit failed:", file=sys.stderr)
        for item in failures:
            print(f" - {item}", file=sys.stderr)
        return 1

    print("\nUX completion audit passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
