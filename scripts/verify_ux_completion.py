#!/usr/bin/env python3
"""
Executable UX completion audit for the zero-backlog dashboard/setup/marketplace/marketing pass.

This script verifies the core contract rather than relying on historical docs:
- role-home dashboard contract
- Setup Studio product payload
- required private-surface template markers
- required public proof-page route markers

Gate / E2E database (SQLite): when **DJANGO_UX_AUDIT_USE_GATE_DB=1**, the default connection
uses **DJANGO_UX_AUDIT_DB_FILE** or **DJANGO_TEST_DB_FILE** (same discipline as
``migrate_gate_test_db.py``) so this audit runs against a migrated file-backed DB instead
of an unmigrated dev ``db_working.sqlite3``. Example::

    export DJANGO_UX_AUDIT_USE_GATE_DB=1
    export DJANGO_TEST_DB_FILE=.django_test_dbs/operator_phase1011_e2e.sqlite3
    python scripts/migrate_gate_test_db.py
    python scripts/verify_ux_completion.py

Run (CLI): ``raise SystemExit(main(None))`` (default ``--base`` is this repository root).
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from pathlib import Path

# Project root (parent of scripts/); may be overridden per-run via ``_configure_root``.
ROOT = Path(__file__).resolve().parent.parent


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        default=str(ROOT),
        help="Repository root to inspect (default: this repository root).",
    )
    return parser.parse_args(argv)


def _resolve_base(raw_base: str) -> Path:
    base = Path(raw_base).resolve()
    if not base.is_dir():
        raise ValueError(f"Base path is not a directory: {base}")
    return base


def _configure_root(base: Path) -> None:
    global ROOT
    ROOT = base
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))


def _bootstrap_django() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    import django
    from django.conf import settings

    use_gate = (os.environ.get("DJANGO_UX_AUDIT_USE_GATE_DB") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    raw_gate = (
        os.environ.get("DJANGO_UX_AUDIT_DB_FILE")
        or os.environ.get("DJANGO_TEST_DB_FILE")
        or ""
    ).strip()
    if use_gate and raw_gate:
        engine = settings.DATABASES.get("default", {}).get("ENGINE", "")
        if engine == "django.db.backends.sqlite3":
            path = Path(os.path.expanduser(os.path.expandvars(raw_gate)))
            if not path.is_absolute():
                path = ROOT / path
            path.parent.mkdir(parents=True, exist_ok=True)
            settings.DATABASES["default"]["NAME"] = str(path)

    django.setup()


def _check(condition: bool, label: str, detail: str, failures: list[str]) -> None:
    if condition:
        print(f"OK   {label}")
        return
    failures.append(f"{label}: {detail}")
    print(f"FAIL {label}: {detail}", file=sys.stderr)


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def audit_dashboard_contract(failures: list[str]) -> None:
    from django.contrib.auth import get_user_model
    from django.db import OperationalError
    from django.test import RequestFactory

    from apps.dashboard.context import build_dashboard_extras

    User = get_user_model()
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
    from apps.schools.models import School
    from apps.setup_studio.services import get_setup_studio_payload

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
            # Repointed from the raw, UNTRANSLATED per-card line
            # "Sandbox-first rollout available for every install from this page."
            # that 9983d01d7 dropped when it extracted the card markup into
            # marketplace/partials/app_catalog_card.html. The sandbox-first promise
            # it carried is now made in three translated places ("3. Sandbox first",
            # the line below, and the promotion line under it); this pins the
            # load-bearing one. It went unnoticed because a SECOND
            # "templates/marketplace/app_catalog.html" key further down this dict
            # silently replaced this entry -- see scan_duplicate_dict_keys.py.
            "Sandbox install keeps rollout deliberate instead of instantly live.",
            "Rollback and safety posture",
            "data-phase9-listing-trust",
            "data-listing-compatibility",
        ],
        "templates/marketplace/tenant_app_catalog.html": [
            # Repointed from the marketing hero title "Install with confidence.",
            # which 8b03d9307 replaced with the shared operational-center frame.
            # The headline and purpose line now come from
            # tenant_app_catalog_frame_context() in
            # apps/platform_runtime/operational_center_nav.py, so pin the frame
            # wiring that supplies them rather than a string the page no longer owns.
            'os_center_key="tenant_app_catalog"',
            "Install to sandbox",
            "Rollback expectations",
            "data-phase9-ecosystem-hub",
            "Migration & interoperability hub",
            "data-phase9-listing-trust",
            "data-listing-compatibility",
            # catalog-placeholder.svg moved to the card-partial entry below. This
            # page's cards render a bi-box-seam glyph, not an <img>, so there is no
            # broken-image surface left here to protect.
        ],
        # The placeholder contract lives here now (extracted by 9983d01d7): a
        # listing with no preview still renders something instead of a broken image.
        "templates/marketplace/partials/app_catalog_card.html": [
            "catalog-placeholder.svg",
        ],
        "templates/accounts/migration_wizard.html": [
            "data-decision-engine",
            "Staged rollout & safety",
            "Migration run history",
            "data-migration-source-detection",
            "data-migration-confidence",
        ],
        "templates/accounts/district_lms_interop.html": [
            "data-phase9-interop-workbench",
            "data-phase9-connector-health",
        ],
        "templates/siteconfig/installed_packages_rollback.html": [
            "data-phase9-pack-staged-rollout",
            "Staged rollout",
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
        "templates/schools/marketing_landing.html": [
            "data-phase10-marketing-narrative",
            "mkt-narrative-phase10",
            "Why schools switch",
            "Studio OS — one shell for every mode",
            "Marketplace & packs",
            "data-phase10-role-visuals",
        ],
        "static/marketing/css/proof-pages.css": [
            ".proof-page",
            ".proof-hero",
            ".proof-card-grid",
        ],
        # Repointed off a hard contradiction: this gate required two strings that
        # apps/finance/tests/test_finance_dashboard_consolidation_2026_08_02.py
        # ::test_duplicate_bands_removed_from_template forbids by exact string, so
        # the gate and the test could not both pass. The 2026-08-02 consolidation
        # merged the decision surface INTO the masthead (the removed band's metrics
        # were a literal re-projection of the hero band). The sealing test is the
        # authority; these pin the band that is the decision surface now, and match
        # that test's own positive assertions.
        "templates/finance/dashboard.html": [
            'data-decision-engine="masthead"',
            "components/rmc_page_masthead.html",
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
    from django.contrib.auth.models import AnonymousUser
    from django.test import RequestFactory
    from django.test.utils import override_settings

    from apps.schools.marketing_views import (
        compare_marketing_page,
        developer_marketing_page,
        marketplace_marketing_page,
        migrate_marketing_page,
        setup_simulator_page,
    )

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


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        _configure_root(_resolve_base(args.base))
    except ValueError as exc:
        print(f"verify_ux_completion: {exc}", file=sys.stderr)
        return 1

    _bootstrap_django()

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
    raise SystemExit(main(None))
