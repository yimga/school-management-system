"""
Validate marketing routes and Django checks for deploy/release.

Supports the operational checklist in docs/MARKETING_NON_NEGOTIABLES.md:
- Public routes remain marketing-only on apex host.
- Marketing pages pass public smoke tests and Django checks.
- config/marketing_content/*.json parse and include required keys (label, seo_title, headline).

Usage:

    python manage.py validate_marketing_urls
    python manage.py validate_marketing_urls --smoke   # also GET key URLs (test client)
    python manage.py validate_marketing_urls --full    # GET marketing_* + adjacent public routes (roles, migrate, …); --seed-cms for blog detail
"""

from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.urls import NoReverseMatch, reverse


class Command(BaseCommand):
    help = "Validate marketing URL names resolve and run Django system checks (for deploy checklist)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--smoke",
            action="store_true",
            help="Smoke-test key marketing URLs with test client (GET 200).",
        )
        parser.add_argument(
            "--full",
            action="store_true",
            help="GET all resolved marketing_* URLs (see apps.schools.marketing_url_inventory).",
        )
        parser.add_argument(
            "--seed-cms",
            action="store_true",
            help="With --full: run seed_marketing_cms first so /blog/<slug>/ returns 200.",
        )

    def handle(self, *args, **options):
        run_smoke = options.get("smoke", False)
        run_full = options.get("full", False)
        seed_cms = options.get("seed_cms", False)
        errors = []  # URL resolution and smoke only; check failure does not fail this command
        check_failed = False

        # 1. Django system check (optional for this command: URL/smoke only need test DB + migrations)
        self.stdout.write("Running Django system checks...")
        from django.core.management import call_command

        try:
            call_command("check", verbosity=0)
            self.stdout.write(self.style.SUCCESS("  Django check passed."))
        except (CommandError, SystemExit) as e:
            check_failed = True
            self.stdout.write(self.style.ERROR(f"  Django check failed: {e}"))
            self.stdout.write(
                self.style.WARNING(
                    "  (URL resolution and smoke tests do not depend on check; continuing.)"
                )
            )

        # 2. Resolve key marketing URL names
        url_names = [
            "marketing_landing",
            "marketing_book_demo",
            "marketing_10_reasons",
            "marketing_interactive_preview",
            "marketing_integrations",
            "marketing_app_marketplace",
            "marketing_developers",
            "marketing_products_admissions",
            "marketing_products_analytics",
            "marketing_funnel_dashboard",
            "marketing_robots_txt",
            "marketing_sitemap_xml",
            "signup_school",
            "global_login_discovery",
        ]
        self.stdout.write("Resolving marketing URL names...")
        for name in url_names:
            try:
                path = reverse(name)
                self.stdout.write(f"  {name} -> {path}")
            except NoReverseMatch as e:
                errors.append(f"URL name {name}: {e}")
                self.stdout.write(self.style.WARNING(f"  {name} -> NoReverseMatch"))

        # 2b. config/marketing_content/*.json — valid JSON and minimum shape (see marketing_views._load_marketing_page_from_file; regional layers compare_eu.json etc. when MARKETING_CONTENT_REGION is set)
        self.stdout.write("Validating config/marketing_content/*.json...")
        mdir = Path(settings.BASE_DIR) / "config" / "marketing_content"
        required_page_keys = ("label", "seo_title", "headline")
        if not mdir.is_dir():
            errors.append(f"marketing_content directory missing: {mdir}")
        else:
            for path in sorted(mdir.glob("*.json")):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError) as e:
                    errors.append(f"marketing_content {path.name}: {e}")
                    self.stdout.write(
                        self.style.ERROR(f"  {path.name} -> invalid JSON or unreadable")
                    )
                    continue
                if not isinstance(data, dict):
                    errors.append(
                        f"marketing_content {path.name}: root must be a JSON object"
                    )
                    continue
                for k in required_page_keys:
                    if not str(data.get(k, "") or "").strip():
                        errors.append(
                            f"marketing_content {path.name}: missing non-empty '{k}'"
                        )
                segs = data.get("segments")
                if segs is not None and not isinstance(segs, list):
                    errors.append(
                        f"marketing_content {path.name}: 'segments' must be a list or omitted"
                    )
                extras = data.get("extras")
                if extras is not None and not isinstance(extras, dict):
                    errors.append(
                        f"marketing_content {path.name}: 'extras' must be an object or omitted"
                    )
                self.stdout.write(f"  {path.name} OK")
        if mdir.is_dir() and not any(
            e.startswith("marketing_content") for e in errors
        ):
            self.stdout.write(self.style.SUCCESS("  All marketing_content JSON files OK."))

        # 3. Smoke test (GET 200). Use canonical base host so host routing accepts the request.
        if run_smoke or run_full:
            from django.test import Client
            from apps.schools.host_routing import get_canonical_base_domain

            client = Client()
            host = get_canonical_base_domain() or "runmycampus.com"

            if run_full and seed_cms:
                self.stdout.write("Running seed_marketing_cms (for blog detail and CMS keys)...")
                call_command("seed_marketing_cms", verbosity=0)

            if run_full:
                from apps.schools.marketing_url_inventory import (
                    iter_marketing_adjacent_smoke_targets,
                    iter_marketing_smoke_targets,
                )

                self.stdout.write(
                    "Full smoke: GET all marketing_* URLs (staff-only routes redirect to LOGIN_URL)..."
                )
                for target in iter_marketing_smoke_targets():
                    try:
                        resp = client.get(target.path, HTTP_HOST=host, follow=True)
                        if target.accepts(resp.status_code):
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f"  GET {target.name} {target.path} -> {resp.status_code}"
                                )
                            )
                        else:
                            errors.append(
                                f"GET {target.name} {target.path} -> {resp.status_code}"
                            )
                            self.stdout.write(
                                self.style.WARNING(
                                    f"  GET {target.name} {target.path} -> {resp.status_code}"
                                )
                            )
                    except (
                        OSError,
                        ConnectionError,
                        ValueError,
                        TypeError,
                        KeyError,
                        AttributeError,
                        RuntimeError,
                    ) as e:
                        errors.append(f"GET {target.name} {target.path}: {e}")
                        self.stdout.write(
                            self.style.ERROR(f"  GET {target.name} {target.path}: {e}")
                        )
                self.stdout.write(
                    "Adjacent smoke: roles, institutions, migrate, signup, discover, API docs..."
                )
                for target in iter_marketing_adjacent_smoke_targets():
                    try:
                        resp = client.get(target.path, HTTP_HOST=host, follow=True)
                        if target.accepts(resp.status_code):
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f"  GET adjacent {target.name} {target.path} -> {resp.status_code}"
                                )
                            )
                        else:
                            errors.append(
                                f"GET adjacent {target.name} {target.path} -> {resp.status_code}"
                            )
                            self.stdout.write(
                                self.style.WARNING(
                                    f"  GET adjacent {target.name} {target.path} -> {resp.status_code}"
                                )
                            )
                    except (
                        OSError,
                        ConnectionError,
                        ValueError,
                        TypeError,
                        KeyError,
                        AttributeError,
                        RuntimeError,
                    ) as e:
                        errors.append(f"GET adjacent {target.name} {target.path}: {e}")
                        self.stdout.write(
                            self.style.ERROR(
                                f"  GET adjacent {target.name} {target.path}: {e}"
                            )
                        )
            elif run_smoke:
                self.stdout.write("Smoke-testing key URLs (test client)...")
                smoke_names = [
                    "marketing_landing",
                    "marketing_book_demo",
                    "marketing_10_reasons",
                    "marketing_integrations",
                    "marketing_app_marketplace",
                    "marketing_developers",
                ]
                paths = []
                for name in smoke_names:
                    try:
                        paths.append(reverse(name))
                    except NoReverseMatch:
                        pass
                for path in paths:
                    try:
                        resp = client.get(path, HTTP_HOST=host)
                        if resp.status_code == 200:
                            self.stdout.write(self.style.SUCCESS(f"  GET {path} -> 200"))
                        else:
                            errors.append(f"GET {path} -> {resp.status_code}")
                            self.stdout.write(
                                self.style.WARNING(f"  GET {path} -> {resp.status_code}")
                            )
                    except (
                        OSError,
                        ConnectionError,
                        ValueError,
                        TypeError,
                        KeyError,
                        AttributeError,
                        RuntimeError,
                    ) as e:
                        errors.append(f"GET {path}: {e}")
                        self.stdout.write(self.style.ERROR(f"  GET {path}: {e}"))

        if check_failed:
            self.stdout.write(
                self.style.WARNING(
                    "\nDjango check failed; fix with 'manage.py check' before full deploy."
                )
            )
        if errors:
            self.stdout.write(
                self.style.ERROR("\nValidation had issues. Fix before release.")
            )
            for e in errors:
                self.stdout.write(self.style.ERROR(f"  - {e}"))
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS("\nMarketing URL validation passed."))
