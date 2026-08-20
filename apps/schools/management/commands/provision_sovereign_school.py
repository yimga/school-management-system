"""Turnkey sovereign-tenant bootstrap — every feature + offline mode, in one shot.

Idempotent and safe to re-run. Chains the existing pieces so an operator does not
have to remember the order or look up a UUID:

  0. (``--create`` only) if the sovereign school does not exist yet, create it +
     a loginable owner via the REAL, self-verifying ``create_school`` engine,
     using the canonical ``gilead-tech`` slug so step 2 can resolve it. This is
     the fresh-box path: an empty edge database has no School and no login until
     something creates them, and ``create_school`` is the one command that does
     it synchronously + proves the owner can authenticate before returning.
  1. ensure the plan catalog exists (seed_subscription_catalog) if the
     ``sovereign-self-hosted`` plan is missing;
  2. ensure_showcase_tenant_entitlements — COMPLIMENTARY billing + every
     feature/module code + entitlement rows (Gilead-scoped, cannot leak);
  3. apply_offline_mode_bundle for that school — enable_offline_mode + the offline
     backend flags for field-work resilience.

Runs the same on the CLOUD (make the live gilead-tech tenant fully-featured now)
and on an on-prem EDGE box (bring a fresh sovereign install to parity). Resolves
the school by slug, so no UUID is needed.

    # Existing school (cloud, or an edge box where the tenant already exists):
    python manage.py provision_sovereign_school
    python manage.py provision_sovereign_school --dry-run
    python manage.py provision_sovereign_school --no-offline
    python manage.py provision_sovereign_school --hub-base-url http://192.168.1.10:8000

    # Fresh edge box (empty DB, no school yet) — create + entitle in one shot:
    python manage.py provision_sovereign_school --create --email owner@gilead.school.lan
    python manage.py provision_sovereign_school --create --email owner@gilead.school.lan \
        --name "Gilead Tech High" --country CM --password "StrongPass"
"""
from __future__ import annotations

from django.core.management import call_command
from django.core.management.base import BaseCommand

# Same allow-list the sovereignty entitlements command uses.
from apps.billing.management.commands.ensure_showcase_tenant_entitlements import (
    GILEAD_SLUGS,
)


class Command(BaseCommand):
    help = "Bootstrap a sovereign tenant: every feature + offline mode (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("--no-offline", action="store_true", help="Skip the offline-mode bundle.")
        parser.add_argument("--dry-run", action="store_true", help="Report the plan without writing.")
        parser.add_argument(
            "--hub-base-url",
            default="",
            help="Optional hub_base_url passed to the offline bundle (hybrid profile).",
        )
        # --- Fresh-box creation (--create) ---------------------------------
        parser.add_argument(
            "--create",
            action="store_true",
            help=(
                "If the sovereign school does not exist yet, create it + a loginable owner "
                "via create_school before entitling (the fresh-edge-box path). Requires --email."
            ),
        )
        parser.add_argument(
            "--email",
            default="",
            help="Owner (ADMIN) login email — REQUIRED with --create.",
        )
        parser.add_argument(
            "--name",
            default="Gilead Tech High",
            help="School display name when creating (default: 'Gilead Tech High').",
        )
        parser.add_argument(
            "--slug",
            default="gilead-tech",
            help=(
                "Slug to create under (default: gilead-tech). MUST be one of the Gilead "
                "slugs so sovereignty entitlements can resolve it afterwards."
            ),
        )
        parser.add_argument(
            "--country",
            default="CM",
            help="2-letter ISO country code when creating (default: CM / Cameroon).",
        )
        parser.add_argument(
            "--password",
            default="",
            help="Owner password when creating. If omitted, create_school generates + prints one.",
        )

    def _resolve_school(self):
        from apps.schools.models import School

        for slug in GILEAD_SLUGS:
            school = School.objects.filter(slug=slug).first()
            if school is not None:
                return school
        return None

    def handle(self, *args, **options):
        from apps.siteconfig.models_platform_catalog import Plan

        dry_run = bool(options.get("dry_run"))
        no_offline = bool(options.get("no_offline"))
        hub = (options.get("hub_base_url") or "").strip()
        create = bool(options.get("create"))

        school = self._resolve_school()

        # --- Step 0: fresh-box creation (only if absent AND --create) --------
        if school is None and create:
            email = (options.get("email") or "").strip()
            slug = (options.get("slug") or "gilead-tech").strip().lower()
            name = (options.get("name") or "Gilead Tech High").strip()
            country = (options.get("country") or "CM").strip().upper()[:2]
            password = (options.get("password") or "").strip()

            if not email:
                self.stderr.write(self.style.ERROR("--create requires --email (the owner login)."))
                return
            # The sovereignty entitlements resolve ONLY the Gilead slugs; refuse to
            # create under a slug that step 2 could never find (would leave an
            # un-entitled school + a misleading "not found" on the next run).
            if slug not in GILEAD_SLUGS:
                self.stderr.write(
                    self.style.ERROR(
                        "--slug %r is not a Gilead slug; sovereignty could not resolve it. "
                        "Use one of: %s" % (slug, ", ".join(GILEAD_SLUGS))
                    )
                )
                return

            if dry_run:
                self.stdout.write(
                    "DRY RUN — would create school slug=%s name=%r owner=%s country=%s "
                    "(via create_school), then entitle." % (slug, name, email, country)
                )
            else:
                self.stdout.write("→ creating sovereign school + owner (create_school, self-verifying)…")
                create_kwargs = dict(name=name, email=email, slug=slug, country=country)
                if password:
                    create_kwargs["password"] = password
                call_command("create_school", **create_kwargs)
                school = self._resolve_school()

        if school is None:
            if create and dry_run:
                # In a create dry-run the school legitimately does not exist yet; the
                # plan above already described what would happen. Nothing more to report.
                return
            hint = (
                "Create the tenant first, or re-run with --create --email <owner-email>."
                if not create
                else "create_school did not yield a resolvable Gilead school (see errors above)."
            )
            self.stderr.write(
                self.style.ERROR(
                    "Sovereign school not found (tried: %s). %s"
                    % (", ".join(GILEAD_SLUGS), hint)
                )
            )
            return

        plan_present = Plan.objects.filter(slug="sovereign-self-hosted").exists()

        if dry_run:
            self.stdout.write("DRY RUN — would:")
            self.stdout.write(
                f"  1. {'skip (plan present)' if plan_present else 'seed_subscription_catalog (plan missing)'}"
            )
            self.stdout.write(f"  2. ensure_showcase_tenant_entitlements  → {school.slug} COMPLIMENTARY + all features")
            self.stdout.write(
                "  3. " + ("skip offline bundle (--no-offline)" if no_offline
                          else f"apply_offline_mode_bundle --school-id {school.id}")
            )
            return

        if not plan_present:
            self.stdout.write("→ seeding subscription catalog (sovereign-self-hosted plan missing)…")
            call_command("seed_subscription_catalog")

        self.stdout.write("→ ensuring sovereignty entitlements (every feature)…")
        call_command("ensure_showcase_tenant_entitlements")

        if not no_offline:
            self.stdout.write("→ applying offline-mode bundle…")
            call_command("apply_offline_mode_bundle", school_id=str(school.id), hub_base_url=hub)

        school.refresh_from_db()
        feature_count = sum(1 for v in (getattr(school, "features", None) or {}).values() if v)
        self.stdout.write(
            self.style.SUCCESS(
                "Sovereign bootstrap complete: %s billing_type=%s, %d features enabled%s."
                % (
                    school.slug,
                    getattr(school, "billing_type", "?"),
                    feature_count,
                    "" if no_offline else ", offline mode on",
                )
            )
        )
