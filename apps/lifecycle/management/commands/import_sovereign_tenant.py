"""import_sovereign_tenant — migrate a cloud tenant onto a fresh edge box, correctly.

The stock ``import_tenant_bundle`` command is a pure data load: it assumes the
School already exists at the bundle's UUID, does nothing about RLS, and creates
no owner/entitlements. On a real edge box that is not enough — and one gap is a
hard failure:

  * IDENTITY: the bundle EXCLUDES the public parents (School, User,
    SchoolMembership, Plan, Entitlement, SiteSettings). The importer is
    pk-preserving, so a School row MUST already exist carrying the bundle's exact
    UUID or every tenant FK dangles. Neither ``create_school`` nor
    ``provision_sovereign_school`` can pin a UUID (they mint a random one), and
    ``create_school`` additionally seeds a whole CM academic baseline — which then
    COLLIDES on unique keys with the imported academic rows ("EMPTY target" is the
    importer's stated contract).

  * RLS (the hard blocker): on a PostgreSQL edge box tenant tables are FORCE
    RLS + default-deny. ``import_tenant_bundle`` sets neither ``app.rls_bypass``
    nor ``app.current_school_id``, so every INSERT is rejected and the whole load
    rolls back. It must run inside ``rls_context.rls_bypass()``.

  * FINISH: a loginable owner needs a User + SchoolMembership (both excluded from
    the bundle); the school needs entitlements; and it must be activated WITHOUT
    re-running ``provision_school_sync`` (which would reconcile/deactivate the
    imported academic year).

This command does the whole thing as one atomic, RLS-bypassed, self-verifying
operation:

  1. read the bundle, take its school UUID (the pin);
  2. create the School PARENT at that exact UUID (no academic seeding), or reuse
     it if it already exists — refusing a slug that resolves to a DIFFERENT id;
  3. refuse a non-empty target (unless --allow-nonempty) so a re-run can't collide;
  4. seed the sovereign plan catalog if missing;
  5. import the bundle (RLS-bypassed, pk-preserving);
  6. entitle (ensure_gilead_sovereignty_entitlements) + optional offline bundle;
  7. create the owner (ensure_admin_user_for_school) with a real password;
  8. activate, then SELF-VERIFY: active, slug resolves, owner authenticates.

Everything is inside a single transaction: any failure rolls the whole migration
back, so the box is never left half-migrated.

    python manage.py import_sovereign_tenant \
        --in /srv/rmc/gilead-tech.rmcbundle \
        --slug gilead-tech --owner-email owner@gilead.school.lan

--fresh: when the source is an EMPTY cloud shell, its ``people`` rows still carry
a required, non-nullable ``TeacherProfile.user`` FK to a cloud User that the
bundle excludes (Users live in the public/shared schema). A pk-preserving load
of those rows can never satisfy that FK on the box, so ``--fresh`` pins the UUID
and provisions clean (plan + entitlements + owner + activate + verify) WITHOUT
importing the bundle's data. The real roster then arrives via the ingest pipeline.

Requires the SAME SECRET_KEY as the exporting cloud (the bundle is encrypted +
HMAC-signed with SECRET_KEY bound to the school id); a mismatch fails closed.
"""
from __future__ import annotations

import json
import secrets
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

# Unambiguous when read aloud / copied from a terminal.
_PW_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"

# Representative direct-``school``-FK tenant models used to assert an EMPTY target
# before a pk-preserving load (a non-empty target risks unique-key collisions).
_EMPTINESS_PROBE = (
    ("academics", "AcademicYear"),
    ("academics", "Term"),
    ("academics", "Subject"),
    ("academics", "Classroom"),
    ("people", "StudentProfile"),
    ("evals", "Evaluation"),
)


def _generate_password(length: int = 14) -> str:
    return "".join(secrets.choice(_PW_ALPHABET) for _ in range(length))


class Command(BaseCommand):
    help = "Migrate a cloud tenant bundle onto a fresh edge box (pin UUID, RLS-safe, self-verifying)."

    def add_arguments(self, parser):
        parser.add_argument("--in", dest="in_path", required=True, help="Source .rmcbundle path.")
        parser.add_argument(
            "--owner-email",
            dest="owner_email",
            required=True,
            help="Owner (ADMIN) login email — created on the box (excluded from the bundle).",
        )
        parser.add_argument(
            "--slug",
            default="gilead-tech",
            help="Slug for the School parent (default: gilead-tech). MUST be a Gilead slug.",
        )
        parser.add_argument(
            "--name",
            default="",
            help="Display name for the School parent if it must be created (default: from bundle / a sensible fallback).",
        )
        parser.add_argument(
            "--country",
            default="CM",
            help="2-letter ISO country for the School parent's localization defaults (default: CM).",
        )
        parser.add_argument(
            "--password",
            default="",
            help="Owner password. If omitted, a strong one is generated and printed.",
        )
        parser.add_argument(
            "--expect-school-id",
            dest="expect_school_id",
            default="",
            help="Optional guard: refuse unless the bundle is for this school UUID.",
        )
        parser.add_argument(
            "--no-offline",
            action="store_true",
            help="Skip the offline-mode bundle (edge boxes normally want it on).",
        )
        parser.add_argument(
            "--allow-nonempty",
            action="store_true",
            help="Permit import even if the target school already has tenant rows (collision risk).",
        )
        parser.add_argument(
            "--fresh",
            action="store_true",
            help=(
                "Provision a CLEAN tenant at the bundle's pinned UUID WITHOUT importing "
                "the bundle's data. Use when the source is an empty cloud shell whose "
                "people rows reference cloud Users that don't exist on the box (a "
                "TeacherProfile.user is a required, non-nullable FK the box can't satisfy). "
                "Still pins the UUID, entitles, creates the owner, activates, and verifies."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report the plan (bundle UUID, target school state, counts) without writing.",
        )

    # ------------------------------------------------------------------ #

    def handle(self, *args, **opts):
        from apps.billing.management.commands.ensure_gilead_sovereignty_entitlements import (
            GILEAD_SLUGS,
        )
        from apps.schools.models import School
        from apps.schools.rls_context import rls_bypass

        in_path = Path(opts["in_path"])
        if not in_path.exists():
            raise CommandError(f"Bundle not found: {in_path}")

        slug = (opts["slug"] or "gilead-tech").strip().lower()
        if slug not in GILEAD_SLUGS:
            raise CommandError(
                "--slug %r is not a Gilead slug; sovereignty entitlements could never "
                "resolve it. Use one of: %s" % (slug, ", ".join(GILEAD_SLUGS))
            )

        owner_email = (opts["owner_email"] or "").strip().lower()
        if "@" not in owner_email:
            raise CommandError("--owner-email must be a valid email address.")

        country = (opts["country"] or "CM").strip().upper()[:2]
        password = opts["password"] or _generate_password()
        no_offline = bool(opts["no_offline"])
        allow_nonempty = bool(opts["allow_nonempty"])
        fresh = bool(opts["fresh"])
        dry_run = bool(opts["dry_run"])

        # --- Read the bundle envelope to learn the pin UUID (no decrypt yet) --- #
        bundle_bytes = in_path.read_bytes()
        try:
            container = json.loads(bundle_bytes)
            bundle_uuid = str(container["school_id"])
        except (ValueError, KeyError) as exc:
            raise CommandError(f"Not a readable .rmcbundle (missing school_id): {exc}")

        expect = (opts.get("expect_school_id") or "").strip()
        if expect and expect != bundle_uuid:
            raise CommandError(
                f"Bundle is for school {bundle_uuid}, not --expect-school-id {expect}."
            )

        name = (opts["name"] or "").strip() or container.get("tenant_slug") or "Gilead Technical High School"

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"Sovereign import -> school {bundle_uuid} (slug {slug})"
            )
        )

        # --- Pre-flight: resolve the target School WITHOUT writing ------------- #
        with rls_bypass():
            existing_by_id = School.objects.filter(id=bundle_uuid).first()
            existing_by_slug = School.objects.filter(slug=slug).first()

            if existing_by_slug and str(existing_by_slug.id) != bundle_uuid:
                raise CommandError(
                    "A School with slug %r already exists at id=%s, which is NOT the "
                    "bundle's id=%s. Refusing to guess. Rename/remove that school or "
                    "pick a different --slug before importing."
                    % (slug, existing_by_slug.id, bundle_uuid)
                )

            nonempty = self._probe_nonempty(existing_by_id) if existing_by_id else {}

            self.stdout.write(
                "  target: %s | nonempty: %s"
                % (
                    "REUSE existing" if existing_by_id else "CREATE new parent",
                    (", ".join(f"{k}={v}" for k, v in nonempty.items()) or "empty"),
                )
            )

            # In --fresh mode nothing is imported, so a non-empty target carries no
            # pk-collision risk — the guard is only about the pk-preserving load.
            if nonempty and not allow_nonempty and not fresh:
                raise CommandError(
                    "Target school already has tenant rows (%s). A pk-preserving import "
                    "into a non-empty target risks unique-key collisions. Re-run with "
                    "--allow-nonempty only if you know these are the SAME identities."
                    % ", ".join(f"{k}={v}" for k, v in nonempty.items())
                )

            if dry_run:
                self.stdout.write(
                    self.style.WARNING(
                        "DRY RUN - would %s School id=%s slug=%s, %s, "
                        "entitle%s, create owner %s, activate + verify."
                        % (
                            "reuse" if existing_by_id else "create",
                            bundle_uuid,
                            slug,
                            "SKIP bundle import (--fresh)" if fresh else "import the bundle",
                            "" if no_offline else " + offline bundle",
                            owner_email,
                        )
                    )
                )
                return

            # --- Do the migration: one atomic, RLS-bypassed unit -------------- #
            with transaction.atomic():
                school = existing_by_id or self._create_parent(
                    School, school_id=bundle_uuid, slug=slug, name=name, country=country
                )
                verb = "Reusing" if existing_by_id else "Created"
                self.stdout.write(f"  {verb} School parent id={school.id} slug={school.slug}")

                self._ensure_plan_catalog()

                if fresh:
                    # Empty cloud shell: its people rows reference cloud Users (a
                    # non-nullable TeacherProfile.user FK) that don't exist on the box,
                    # so a pk-preserving load can't satisfy the constraint. Pin the
                    # UUID and provision clean; the real roster arrives via ingest.
                    self.stdout.write(
                        "  FRESH mode: SKIP bundle data import - clean provision at pinned UUID."
                    )
                    result = {
                        "school_id": bundle_uuid,
                        "tenant_slug": name,
                        "mode": "fresh",
                        "imported": {},
                        "total": 0,
                        "skipped": [],
                        "errored": {},
                    }
                else:
                    self.stdout.write("  Importing bundle (RLS-bypassed, pk-preserving)...")
                    result = self._import(bundle_bytes, expected_school_id=bundle_uuid)
                    self.stdout.write(
                        "    imported %d rows across %d tables%s"
                        % (
                            result["total"],
                            len(result["imported"]),
                            f" (skipped {len(result['skipped'])})" if result.get("skipped") else "",
                        )
                    )

                self.stdout.write("  Entitling (sovereignty: every feature)...")
                call_command("ensure_gilead_sovereignty_entitlements")
                if not no_offline:
                    call_command("apply_offline_mode_bundle", school_id=str(school.id))

                admin_user = self._ensure_owner(school, owner_email, password)
                self.stdout.write(
                    f"  Owner: username={admin_user.username} email={admin_user.email}"
                )

                school.is_active = True
                school.save(update_fields=["is_active"])

                # Self-verify INSIDE the transaction so a failure rolls back the
                # whole migration — never leave the box half-provisioned.
                self._verify(school, admin_user, owner_email, password, result)

        self._print_credentials(school, admin_user, owner_email, password, result)

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #

    def _probe_nonempty(self, school) -> dict[str, int]:
        from django.apps import apps as dj_apps

        counts: dict[str, int] = {}
        for app_label, model_name in _EMPTINESS_PROBE:
            model = dj_apps.get_model(app_label, model_name)
            n = model.objects.filter(school=school).count()
            if n:
                counts[f"{app_label}.{model_name}"] = n
        return counts

    def _create_parent(self, School, *, school_id, slug, name, country):
        from apps.schools.school_settings_seed import (
            build_initial_school_settings,
            resolve_school_geo_create_fields,
        )

        geo = resolve_school_geo_create_fields(country)
        school_settings = build_initial_school_settings(
            country_code=country,
            seed_marker="_seeded_by_import_sovereign_tenant",
        )
        # is_active flips True only at the end, after a successful import + verify.
        return School.objects.create(
            id=school_id,
            name=name,
            slug=slug,
            subdomain=slug[:120],
            is_active=False,
            is_approved=True,
            country_code=country,
            timezone=geo["timezone"],
            currency=geo["currency"],
            default_language=geo["default_language"],
            compliance_region=geo["compliance_region"],
            settings=school_settings,
        )

    def _ensure_plan_catalog(self):
        from apps.siteconfig.models_platform_catalog import Plan

        if not Plan.objects.filter(slug="sovereign-self-hosted").exists():
            self.stdout.write("  Seeding subscription catalog (sovereign plan missing)...")
            call_command("seed_subscription_catalog")

    def _import(self, bundle_bytes, *, expected_school_id):
        from apps.lifecycle.tenant_portability import import_tenant_bundle

        try:
            return import_tenant_bundle(bundle_bytes, expected_school_id=expected_school_id)
        except ValueError as exc:
            # signature/school mismatch, etc. — fail closed
            raise CommandError(f"Import refused: {exc}")

    def _ensure_owner(self, school, email, password):
        from apps.schools.tasks import ensure_admin_user_for_school

        admin_user, _ = ensure_admin_user_for_school(school, email)
        if admin_user is None:
            raise CommandError("Failed to create the owner admin user.")
        admin_user.set_password(password)
        admin_user.is_active = True
        admin_user.save(update_fields=["password", "is_active"])
        return admin_user

    def _verify(self, school, admin_user, email, password, result):
        from django.contrib.auth import authenticate

        from apps.schools.models import School

        failures = []
        school.refresh_from_db()
        if not school.is_active:
            failures.append("School.is_active is still False")

        resolves = (
            School.objects.filter(subdomain__iexact=school.subdomain, is_active=True).exists()
            or School.objects.filter(slug__iexact=school.slug, is_active=True).exists()
        )
        if not resolves:
            failures.append(f"host '{school.subdomain}' would NOT resolve in tenant middleware")

        authed = authenticate(username=email, password=password) or authenticate(
            username=admin_user.username, password=password
        )
        if authed is None:
            failures.append("owner could NOT authenticate with the set password")

        if failures:
            for f in failures:
                self.stdout.write(self.style.ERROR(f"    x {f}"))
            raise CommandError(
                "Import completed but did not pass end-to-end verification (see errors above). "
                "Rolling back — NOT leaving a half-migrated box."
            )
        self.stdout.write(self.style.SUCCESS("  SELF-VERIFY PASSED: active, resolvable, loginable."))

    def _print_credentials(self, school, admin_user, email, password, result):
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=" * 64))
        self.stdout.write(self.style.SUCCESS("  SOVEREIGN TENANT IMPORTED - LOGIN CREDENTIALS"))
        self.stdout.write(self.style.SUCCESS("=" * 64))
        self.stdout.write(f"  School name : {school.name}")
        self.stdout.write(f"  Slug / UUID : {school.slug}  /  {school.id}")
        self.stdout.write(f"  Rows loaded : {result['total']} across {len(result['imported'])} tables")
        self.stdout.write(f"  Login email : {email}")
        self.stdout.write(f"  Username    : {admin_user.username}")
        self.stdout.write(f"  Password    : {password}")
        self.stdout.write(self.style.SUCCESS("=" * 64))
        self.stdout.write(
            "  Reach it on the box's host (ALLOWED_HOSTS) at /authentication/login/. "
            "ADMIN may prompt for MFA setup on first login."
        )
