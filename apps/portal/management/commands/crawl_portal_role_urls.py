"""
GET each URL in ``apps.portal.role_smoke_urls.PORTAL_ROLE_SMOKE_SEEDS`` for users
with the declared roles on a **tenant** HTTP host.

Usage:
  python manage.py crawl_portal_role_urls --host acme.example.com

**School resolution (required):** ``--host`` must resolve to an active ``School`` via the
same logic as tenant middleware (subdomain vs ``MULTI_TENANT_BASE_DOMAIN``, verified
custom domain, or ``SchoolDomain``). If resolution fails, the command exits with
``CommandError`` before creating users or hitting URLs.

**Prerequisites:** By default, minimal rows are ensured so teacher and finance seeds
succeed (active academic year/term, ``TeacherProfile`` for the probe teacher,
``ComplianceProfile`` if none exists). Pass ``--skip-ensure-prerequisites`` to disable
that (read-only crawl against whatever is already in the DB).

**Probe users:** Requires DEBUG=True to auto-create ``_portal_smoke_<ROLE>``, or create
those users yourself. Exit 1 on auth-wall redirects, 4xx, or 5xx.
"""

from __future__ import annotations

import sys
from collections import defaultdict

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.test import Client
from django.urls import NoReverseMatch, reverse

from apps.portal.crawl_helpers import portal_smoke_response_ok
from apps.portal.portal_smoke_prerequisites import (
    ensure_portal_smoke_prerequisites,
    ensure_portal_smoke_probe_feature_permissions,
    portal_crawl_unresolved_host_message,
    resolve_school_from_http_host,
)
from apps.portal.role_smoke_urls import PORTAL_ROLE_SMOKE_SEEDS

User = get_user_model()


class Command(BaseCommand):
    help = "Smoke-crawl portal (and related) URLs per role on a tenant host."

    def add_arguments(self, parser):
        parser.add_argument(
            "--host",
            required=True,
            help="HTTP_HOST (e.g. school.runmycampus.com)",
        )
        parser.add_argument(
            "--fail-fast",
            action="store_true",
        )
        parser.add_argument(
            "--skip-ensure-prerequisites",
            action="store_true",
            help=(
                "Do not create or update academic year, term, compliance profile, or "
                "teacher profile; crawl only against existing data."
            ),
        )

    def handle(self, *args, **options):
        host = (options["host"] or "").strip()
        if not host:
            raise CommandError("--host is required")

        school = resolve_school_from_http_host(host)
        if school is None:
            raise CommandError(portal_crawl_unresolved_host_message(host=host))

        self.stdout.write(
            f"Resolved school id={school.pk} name={school.name!r} for host {host!r}.\n"
        )

        failures: list[str] = []
        checked = 0

        role_flags: dict = defaultdict(lambda: {"staff": False, "super": False})
        for seed in PORTAL_ROLE_SMOKE_SEEDS:
            for role in seed["roles"]:
                role_flags[role]["staff"] |= bool(seed.get("requires_staff"))
                role_flags[role]["super"] |= bool(seed.get("requires_superuser"))

        users_by_role: dict = {}
        for role, flags in role_flags.items():
            slug = role.value.lower()
            username = f"_portal_smoke_{slug}"
            user = User.objects.filter(username=username).first()
            if not user:
                if not settings.DEBUG:
                    raise CommandError(
                        f"Missing user {username}; set DEBUG=True to auto-create probe users."
                    )
                user = User.objects.create_user(
                    username=username,
                    email=f"{username}@example.com",
                    password="_smoke_pw_change_me",
                    is_staff=flags["staff"],
                    is_superuser=flags["super"],
                )
            user.role = role
            user.is_active = True
            user.is_staff = flags["staff"]
            user.is_superuser = flags["super"]
            user.save()
            users_by_role[role] = user

        if options["skip_ensure_prerequisites"]:
            self.stdout.write(
                "Skipping ensure_portal_smoke_prerequisites (--skip-ensure-prerequisites).\n"
            )
        else:
            ensure_portal_smoke_prerequisites(
                school=school,
                teacher_user=users_by_role.get(User.Role.TEACHER),
            )
            self.stdout.write(
                "Ensured portal smoke prerequisites (year/term, compliance if needed, "
                "teacher profile for probe user).\n"
            )

        ensure_portal_smoke_probe_feature_permissions(users_by_role)

        for seed in PORTAL_ROLE_SMOKE_SEEDS:
            url_name = seed["url_name"]
            try:
                path = reverse(url_name, urlconf="config.tenant_urls")
            except NoReverseMatch as e:
                failures.append(f"{url_name} NoReverseMatch: {e}")
                if options["fail_fast"]:
                    break
                continue

            for role in seed["roles"]:
                user = users_by_role[role]

                client = Client(HTTP_HOST=host)
                client.force_login(user)
                response = client.get(path, follow=False)
                checked += 1
                ok, reason = portal_smoke_response_ok(response)
                if not ok:
                    msg = f"{url_name} as {role}: {reason} (status {response.status_code})"
                    failures.append(msg)
                    self.stderr.write(f"FAIL {msg}\n")
                    if options["fail_fast"]:
                        sys.exit(1)

        self.stdout.write(
            f"Checked {checked} role×URL pairs; {len(failures)} failure(s).\n"
        )
        if failures:
            sys.exit(1)
