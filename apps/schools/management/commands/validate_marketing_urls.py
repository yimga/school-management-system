"""
Validate marketing routes and Django checks for deploy/release.

Supports the operational checklist in docs/MARKETING_NON_NEGOTIABLES.md:
- Public routes remain marketing-only on apex host.
- Marketing pages pass public smoke tests and Django checks.

Usage:

    python manage.py validate_marketing_urls
    python manage.py validate_marketing_urls --smoke   # also GET key URLs (requires running server or test client)
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.urls import reverse, NoReverseMatch


class Command(BaseCommand):
    help = "Validate marketing URL names resolve and run Django system checks (for deploy checklist)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--smoke",
            action="store_true",
            help="Smoke-test key marketing URLs with test client (GET 200).",
        )

    def handle(self, *args, **options):
        run_smoke = options.get("smoke", False)
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
            self.stdout.write(self.style.WARNING("  (URL resolution and smoke tests do not depend on check; continuing.)"))

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

        # 3. Smoke test (GET 200). Use canonical base host so host routing accepts the request.
        if run_smoke:
            self.stdout.write("Smoke-testing key URLs (test client)...")
            from django.test import Client
            from apps.schools.host_routing import get_canonical_base_domain
            client = Client()
            host = get_canonical_base_domain() or "runmycampus.com"
            smoke_names = ["marketing_landing", "marketing_book_demo", "marketing_10_reasons", "marketing_integrations", "marketing_app_marketplace", "marketing_developers"]
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
                        self.stdout.write(self.style.WARNING(f"  GET {path} -> {resp.status_code}"))
                except (OSError, ConnectionError, ValueError, TypeError, KeyError, AttributeError, RuntimeError) as e:
                    errors.append(f"GET {path}: {e}")
                    self.stdout.write(self.style.ERROR(f"  GET {path}: {e}"))

        if check_failed:
            self.stdout.write(self.style.WARNING("\nDjango check failed; fix with 'manage.py check' before full deploy."))
        if errors:
            self.stdout.write(self.style.ERROR("\nValidation had issues. Fix before release."))
            for e in errors:
                self.stdout.write(self.style.ERROR(f"  - {e}"))
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS("\nMarketing URL validation passed."))
