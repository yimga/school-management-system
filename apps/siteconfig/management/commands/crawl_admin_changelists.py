"""
Crawl every registered admin changelist on the platform or tenant admin site.

Usage (repo root):
  python manage.py crawl_admin_changelists --site platform
  python manage.py crawl_admin_changelists --site tenant --host acme.runmycampus.com

Exit code 1 if any changelist returns an unexpected status (not 200/302 to login).
Superuser required; creates a temporary superuser only if none exist (DEBUG caution).
"""

from __future__ import annotations

import sys

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.test import Client
from django.urls import NoReverseMatch, reverse

User = get_user_model()


class Command(BaseCommand):
    help = "GET every admin changelist URL; report non-OK statuses (platform or tenant site)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--site",
            choices=("platform", "tenant"),
            default="platform",
            help="Which AdminSite registry to crawl",
        )
        parser.add_argument(
            "--host",
            default="",
            help="HTTP_HOST for tenant crawl (subdomain of MULTI_TENANT_BASE_DOMAIN)",
        )
        parser.add_argument(
            "--allow-codes",
            default="200",
            help="Comma-separated acceptable HTTP status codes",
        )
        parser.add_argument(
            "--fail-fast",
            action="store_true",
            help="Stop on first failing URL",
        )

    def handle(self, *args, **options):
        from config.admin import platform_admin_site, tenant_admin_site

        site_kind = options["site"]
        admin_site = platform_admin_site if site_kind == "platform" else tenant_admin_site
        allow = {int(x.strip()) for x in options["allow_codes"].split(",") if x.strip()}

        user = User.objects.filter(is_superuser=True, is_active=True).first()
        if not user:
            if not settings.DEBUG:
                raise CommandError(
                    "No active superuser found; create one or run with DEBUG=True for dev bootstrap."
                )
            user = User.objects.create_superuser(
                username="_crawl_admin_probe",
                email="crawl@example.com",
                password="_crawl_admin_probe_pw_change_me",
            )
            self.stderr.write(
                self.style.WARNING(
                    "Created temporary superuser _crawl_admin_probe — delete after use."
                )
            )

        client = Client()
        client.force_login(user)

        extra = {}
        if site_kind == "tenant":
            host = (options.get("host") or "").strip()
            if not host:
                raise CommandError("--host is required for tenant crawl (e.g. school.runmycampus.com)")
            extra["HTTP_HOST"] = host

        failures: list[tuple[str, int]] = []
        skipped = 0
        checked = 0

        urlconf = None
        if site_kind == "tenant":
            urlconf = "config.tenant_urls"

        for model in admin_site._registry:
            opts = model._meta
            name = f"admin:{opts.app_label}_{opts.model_name}_changelist"
            try:
                url = reverse(name, urlconf=urlconf)
            except NoReverseMatch:
                skipped += 1
                continue
            checked += 1
            try:
                response = client.get(url, follow=False, **extra)
                code = response.status_code
            except Exception as exc:  # command must report the failing surface, not abort opaquely
                failures.append((url, 500))
                self.stderr.write(f"ERROR {url}: {type(exc).__name__}: {exc}\n")
                if options["fail_fast"]:
                    raise CommandError(f"Admin crawl failed at {url}") from exc
                continue
            if code not in allow:
                failures.append((url, code))
                self.stderr.write(f"FAIL {code} {url}\n")
                if options["fail_fast"]:
                    sys.exit(1)

        self.stdout.write(
            f"Crawled {checked} changelists ({skipped} skipped NoReverseMatch); "
            f"{len(failures)} outside allow-list {sorted(allow)}.\n"
        )
        if failures:
            sys.exit(1)
