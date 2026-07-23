"""create_school — one reliable, synchronous, end-to-end school creator.

WHY THIS EXISTS
---------------
The public signup → email-verify → async-provision flow has many moving parts
(Celery dispatch, two-phase provisioning, passwordless owner + token wizard,
host-split urlconfs). Each part is a place the flow can stall: "school never
finishes provisioning", "slug/URL doesn't work yet", "owner can't log in".

This command collapses the whole thing into ONE synchronous, idempotent,
self-verifying path that reuses the REAL provisioning engine (no parallel
fake codepath):

  1. Create (or reuse) the School row.
  2. Provision it SYNCHRONOUSLY via provision_school_sync() — the same engine
     signup's durable outbox drains, but run inline so it is guaranteed to
     finish in-process. No queue, no worker, no spinner-forever. (The HTTP
     path uses complete_provisioning_for_school(), which only ENQUEUES — a CLI
     has no gunicorn timeout, so it runs the migrate/seed itself.)
  3. Create the owner ADMIN and give them a REAL, usable password (operator
     path — no magic link, no token wizard).
  4. SELF-VERIFY the four things that historically break, and FAIL LOUDLY if
     any is wrong:
        a. provisioning reported portal-ready,
        b. School.is_active is True,
        c. the slug/subdomain resolves the way the tenant middleware resolves,
        d. the owner actually authenticates with the printed password.
  5. Print working credentials + the exact login URL.

USAGE
-----
  python manage.py create_school --name "Cedar High" --email owner@cedar.test
  python manage.py create_school --name "Cedar High" --email owner@cedar.test \
      --country US --password "Str0ngPass!" --school-type high

Idempotent: re-running with the same --slug/--email reuses the rows and
re-runs provisioning (safe; every step is get-or-create) and resets the
owner password to the one printed.
"""

from __future__ import annotations

import secrets

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


# Characters chosen to be unambiguous when read aloud / copied from a terminal.
_PW_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"


def _generate_password(length: int = 14) -> str:
    return "".join(secrets.choice(_PW_ALPHABET) for _ in range(length))


class Command(BaseCommand):
    help = "Create and fully provision a school synchronously, then print working login credentials."

    def add_arguments(self, parser):
        parser.add_argument("--name", required=True, help="School display name.")
        parser.add_argument(
            "--email",
            required=True,
            help="Owner (ADMIN) email — also the login identifier.",
        )
        parser.add_argument(
            "--country",
            default="US",
            help="2-letter ISO country code (default: US).",
        )
        parser.add_argument(
            "--slug",
            default="",
            help="Explicit slug/subdomain. If omitted, a memorable one is derived from the name.",
        )
        parser.add_argument(
            "--password",
            default="",
            help="Owner password. If omitted, a strong one is generated and printed.",
        )
        parser.add_argument(
            "--school-type",
            default="",
            help="Optional school-type code (e.g. high, primary) for sector mapping.",
        )

    # ------------------------------------------------------------------ #

    def handle(self, *args, **opts):
        from apps.schools.models import School
        from apps.schools.tasks import (
            ensure_admin_user_for_school,
            provision_school_sync,
        )

        name = (opts["name"] or "").strip()
        email = (opts["email"] or "").strip().lower()
        country = (opts["country"] or "US").strip().upper()[:2]
        school_type = (opts["school_type"] or "").strip()
        password = opts["password"] or _generate_password()

        if not name:
            raise CommandError("--name must not be empty.")
        if "@" not in email:
            raise CommandError("--email must be a valid email address.")

        slug = self._resolve_slug(School, opts["slug"], name, country)

        self.stdout.write(self.style.MIGRATE_HEADING(f"Creating school: {name} ({slug})"))

        # --- 1. Create or reuse the School row ----------------------------- #
        school, created = self._get_or_create_school(
            School, name=name, slug=slug, country=country, school_type=school_type
        )
        verb = "Created" if created else "Reusing existing"
        self.stdout.write(f"  {verb} School id={school.id} slug={school.slug}")

        # --- 2. Provision SYNCHRONOUSLY via the real engine ---------------- #
        # NOTE: complete_provisioning_for_school() only ENQUEUES onto the durable
        # heavy-work outbox (correct for the HTTP path — a multi-minute migrate
        # must never own gunicorn). A management command has no request timeout,
        # so it runs the same engine the outbox drain runs — provision_school_sync
        # — INLINE, and is therefore actually finished when _verify() runs below.
        self.stdout.write("  Provisioning (synchronous, full engine)…")
        provision_school_sync(str(school.id), contact_email=email)
        school.refresh_from_db()
        from apps.schools.provisioning_progress import resolve_portal_ready

        portal_ready = bool(resolve_portal_ready(school))
        self.stdout.write(f"    dispatch=sync portal_ready={portal_ready}")

        # --- 3. Owner ADMIN with a REAL, usable password ------------------ #
        admin_user, _ = ensure_admin_user_for_school(school, email)
        if admin_user is None:
            raise CommandError("Failed to create the owner admin user.")
        admin_user.set_password(password)  # overrides the unusable bootstrap password
        admin_user.is_active = True
        admin_user.save(update_fields=["password", "is_active"])
        self.stdout.write(
            f"  Owner: username={admin_user.username} email={admin_user.email} role={admin_user.role}"
        )

        # --- 4. SELF-VERIFY every historical failure point ---------------- #
        self._verify(school, admin_user, email, password, portal_ready)

        # --- 5. Hand over working credentials ----------------------------- #
        self._print_credentials(school, admin_user, email, password)

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #

    def _resolve_slug(self, School, explicit: str, name: str, country: str) -> str:
        from django.utils.text import slugify

        from apps.schools.signup_views import build_slug_suggestions

        if explicit:
            slug = slugify(explicit)[:120]
            if not slug:
                raise CommandError(f"--slug '{explicit}' is not a valid slug.")
            return slug
        # Pick the first available memorable suggestion; fall back to slugified name.
        for cand in build_slug_suggestions(name, country):
            if not (
                School.objects.filter(slug=cand).exists()
                or School.objects.filter(subdomain=cand).exists()
            ):
                return cand
        base = slugify(name)[:110] or "school"
        slug = base
        n = 2
        while School.objects.filter(slug=slug).exists() or School.objects.filter(
            subdomain=slug
        ).exists():
            slug = f"{base}-{n}"[:120]
            n += 1
        return slug

    @transaction.atomic
    def _get_or_create_school(self, School, *, name, slug, country, school_type):
        from apps.schools.school_settings_seed import (
            build_initial_school_settings,
            resolve_school_geo_create_fields,
        )

        existing = School.objects.filter(slug=slug).first() or School.objects.filter(
            subdomain=slug
        ).first()
        if existing:
            return existing, False

        # PGL-009: same localization + governance + geo defaults as public signup.
        school_settings = build_initial_school_settings(
            country_code=country,
            school_type_code=school_type,
            seed_marker="_seeded_by_create_school_command",
        )
        geo = resolve_school_geo_create_fields(country)

        create_kwargs = dict(
            name=name,
            slug=slug,
            subdomain=slug[:120],
            is_active=False,  # engine flips this to True on successful provision
            is_approved=True,
            country_code=country,
            timezone=geo["timezone"],
            currency=geo["currency"],
            default_language=geo["default_language"],
            compliance_region=geo["compliance_region"],
            settings=school_settings,
        )
        if school_type:
            try:
                from apps.siteconfig.country_localization_service import (
                    resolve_primary_sector_for_school_type,
                )

                sector = resolve_primary_sector_for_school_type(country, school_type)
                if sector:
                    create_kwargs["primary_sector"] = sector[:64]
            except (ImportError, AttributeError, TypeError, ValueError):
                pass
        school = School.objects.create(**create_kwargs)
        return school, True

    def _verify(self, school, admin_user, email, password, portal_ready):
        from django.contrib.auth import authenticate

        from apps.schools.models import School

        failures = []

        # (a) provisioning reported portal-ready
        if not portal_ready:
            failures.append("provisioning did not report portal_ready")

        # (b) is_active flipped
        school.refresh_from_db()
        if not school.is_active:
            failures.append("School.is_active is still False after provisioning")

        # (c) slug/subdomain resolves the way the tenant middleware resolves it
        #     (middleware filters is_active=True on subdomain/slug — mode #1 bug).
        resolves = (
            School.objects.filter(subdomain__iexact=school.subdomain, is_active=True).exists()
            or School.objects.filter(slug__iexact=school.slug, is_active=True).exists()
        )
        if not resolves:
            failures.append(
                f"host '{school.subdomain}' would NOT resolve to this school in tenant middleware"
            )

        # (d) the owner actually authenticates with the printed password
        authed = authenticate(username=email, password=password)
        if authed is None:
            authed = authenticate(username=admin_user.username, password=password)
        if authed is None:
            failures.append("owner could NOT authenticate with the generated password")

        if failures:
            self.stdout.write(self.style.ERROR("  SELF-VERIFY FAILED:"))
            for f in failures:
                self.stdout.write(self.style.ERROR(f"    ✗ {f}"))
            raise CommandError(
                "School was created but did not pass end-to-end verification "
                "(see ✗ above). NOT handing out credentials for a broken school."
            )
        self.stdout.write(self.style.SUCCESS("  SELF-VERIFY PASSED: active, resolvable, loginable."))

    def _print_credentials(self, school, admin_user, email, password):
        from django.conf import settings as dj_settings

        base_domain = (
            getattr(dj_settings, "MULTI_TENANT_BASE_DOMAIN", "") or "runmycampus.com"
        )
        prod_login = f"https://{school.subdomain}.{base_domain}/authentication/login/"
        dev_login = (
            f"http://{school.subdomain}.localhost:8000/authentication/login/"
        )

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=" * 64))
        self.stdout.write(self.style.SUCCESS("  SCHOOL READY — LOGIN CREDENTIALS"))
        self.stdout.write(self.style.SUCCESS("=" * 64))
        self.stdout.write(f"  School name : {school.name}")
        self.stdout.write(f"  Slug        : {school.slug}")
        self.stdout.write(f"  Login email : {email}")
        self.stdout.write(f"  Username    : {admin_user.username}")
        self.stdout.write(f"  Password    : {password}")
        self.stdout.write(f"  Login (prod): {prod_login}")
        self.stdout.write(f"  Login (dev) : {dev_login}")
        self.stdout.write(self.style.SUCCESS("=" * 64))
        self.stdout.write(
            "  Note: ADMIN role may prompt for MFA setup on first login; complete it to reach the dashboard."
        )
