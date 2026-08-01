"""Turnkey sovereign-tenant bootstrap — every feature + offline mode, in one shot.

Idempotent and safe to re-run. Chains the existing pieces so an operator does not
have to remember the order or look up a UUID:

  1. ensure the plan catalog exists (seed_subscription_catalog) if the
     ``sovereign-self-hosted`` plan is missing;
  2. ensure_gilead_sovereignty_entitlements — COMPLIMENTARY billing + every
     feature/module code + entitlement rows (Gilead-scoped, cannot leak);
  3. apply_offline_mode_bundle for that school — enable_offline_mode + the offline
     backend flags for field-work resilience.

Runs the same on the CLOUD (make the live gilead-tech tenant fully-featured now)
and on an on-prem EDGE box (bring a fresh sovereign install to parity). Resolves
the school by slug, so no UUID is needed.

    python manage.py provision_sovereign_school
    python manage.py provision_sovereign_school --dry-run
    python manage.py provision_sovereign_school --no-offline
    python manage.py provision_sovereign_school --hub-base-url http://192.168.1.10:8000
"""
from __future__ import annotations

from django.core.management import call_command
from django.core.management.base import BaseCommand

# Same allow-list the sovereignty entitlements command uses.
from apps.billing.management.commands.ensure_gilead_sovereignty_entitlements import (
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

        school = self._resolve_school()
        if school is None:
            self.stderr.write(
                self.style.ERROR(
                    "Sovereign school not found (tried: %s). Create the tenant first."
                    % ", ".join(GILEAD_SLUGS)
                )
            )
            return

        plan_present = Plan.objects.filter(slug="sovereign-self-hosted").exists()

        if dry_run:
            self.stdout.write("DRY RUN — would:")
            self.stdout.write(
                f"  1. {'skip (plan present)' if plan_present else 'seed_subscription_catalog (plan missing)'}"
            )
            self.stdout.write(f"  2. ensure_gilead_sovereignty_entitlements  → {school.slug} COMPLIMENTARY + all features")
            self.stdout.write(
                "  3. " + ("skip offline bundle (--no-offline)" if no_offline
                          else f"apply_offline_mode_bundle --school-id {school.id}")
            )
            return

        if not plan_present:
            self.stdout.write("→ seeding subscription catalog (sovereign-self-hosted plan missing)…")
            call_command("seed_subscription_catalog")

        self.stdout.write("→ ensuring sovereignty entitlements (every feature)…")
        call_command("ensure_gilead_sovereignty_entitlements")

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
