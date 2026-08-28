"""
Canonical, idempotent public-catalog and active-tenant seed reconciliation.

This is the deployment entry point for seeding everything. It reconciles both
public catalogs and every active tenant without overwriting manual configuration.

Steps, in order:

  1. Public-schema bootstrap (delegates to ``bootstrap_platform_catalog --all``).
  2. Extra public-schema catalogs not owned by the foundational bootstrap:
     marketplace scopes, first-party + phase-9 + ultra-high-end packages,
     process definitions, business glossary, entity catalog, office documents,
     report-platform / br10 plan SKUs, regions (i18n grading scales), preview
     fixtures, cursor twelve-phase and siteconfig-to-metadata sync.
  3. Access-catalog reconciliation: permissions, global roles, SUPERADMIN grants
     and existing-user bindings. It never creates users or resets passwords.
  4. Per-tenant reconciliation (for every active ``School``):
        - geography, localization and country-derived defaults
        - education systems, levels and approved education profile
        - plan assignment and academic baseline
        - explicit demo fixtures only when DEBUG is enabled
  5. Strict registry, regional and complete seed-manifest verification.

Tenant failures retain school identity and processing continues so every tenant
receives a repair attempt. The final verifier still fails while any tenant is
incomplete. Public failures abort unless ``--continue-on-error`` is explicit.

Use ``--skip-tenants`` only for an intentional public-catalog-only operation.
Production reconciliation never installs DEBUG-only demo fixtures.

Reference-school seeds (``seed_buea_synthetic``) are intentionally NOT in
the standard fan-out. They install a specific dual-curriculum Cameroon dataset
that only some demos need. Run those manually per tenant:
``python manage.py seed_buea_synthetic --school=<slug>``.

Every value is owned by an authoritative registry, fixture or country profile;
this command only orchestrates and verifies those sources.
"""

from __future__ import annotations

from django.conf import settings
from django.core.management import CommandError, call_command
from django.core.management.base import BaseCommand
from django.db import DatabaseError, IntegrityError, OperationalError

from apps.platform_runtime.structured_logging import log_exception_with_context

_STEP_ERRORS = (
    CommandError,
    DatabaseError,
    OperationalError,
    IntegrityError,
    OSError,
    TypeError,
    ValueError,
    AttributeError,
    ImportError,
)

# Public-schema seeds NOT covered by bootstrap_platform_catalog --all.
# Order chosen so dependents follow their dependencies (packages before
# experience packs; glossary before entity catalog).
_PUBLIC_EXTRA_STEPS = [
    ("seed_studio_os", "Studio OS SetupStepDefinition master rows"),
    ("seed_marketplace_scopes", "Marketplace permission scopes"),
    ("seed_first_party_apps", "First-party PackageVersion records"),
    ("seed_marketplace_catalog_packages", "Marketplace catalog app PackageVersion payloads"),
    ("seed_phase9_first_party_packages", "Phase 9 package definitions"),
    ("seed_ultra_high_end_experience_packs", "Ultra-high-end experience packs"),
    ("seed_process_definitions", "Orchestration process definitions"),
    ("seed_business_glossary", "Business glossary entries"),
    ("seed_entity_catalog", "Entity metadata catalog"),
    ("seed_office_documents", "Operator playbook + tenant handbook templates"),
    ("seed_report_platform_plan_skus", "Report platform plan SKUs"),
    ("seed_br10_plan_skus", "Brazil region plan SKUs"),
    ("seed_regions", "i18n grading-scale defaults per region"),
    ("seed_preview_fixtures", "Preview environment fixtures"),
    ("seed_cursor_twelve_phases", "Internal twelve-phase cursor seed"),
    ("sync_siteconfig_dynamicfields_to_metadata", "Sync siteconfig fields → metadata"),
    # 2026-05-14 wave NS-6 audit: wire NS-5 catalog into the canonical orchestrator.
    ("seed_dynamic_field_recipes", "Platform-wide DynamicFieldDefinition recipes"),
]

_ACCOUNT_STEPS = [
    (
        "reconcile_access_catalog",
        "Permission, global AccessRole, SUPERADMIN, and existing-user role bindings",
    ),
]

# Gates per-tenant work on Postgres + django-tenants (provisions missing tenant
# schemas before any per-tenant migrate/seed). No-op on SQLite — the command
# prints "PostgreSQL only. Skipping." and exits zero — so it is always safe to
# include here.
_TENANT_INFRA_STEPS = [
    ("ensure_tenant_schemas", "Provision missing django-tenants schemas (Postgres only)"),
]

# Tenant steps only run when DEBUG=True (the demo seeders refuse otherwise).
_TENANT_STEPS_DEBUG_ONLY = [
    ("seed_demo_tenant_users", "demo.admin / demo.teacher / demo.parent users"),
    ("seed_demo", "Academic year + classrooms + students + evaluations"),
    ("seed_testdata_2425", "Synthetic 2024/25 academic data"),
]

_TENANT_RECONCILIATION_STEPS = [
    (
        "reconcile_tenant_seed_baseline",
        "Localization, education classification/profile, and default plan",
    ),
    ("align_tenant_config", "Compiled tenant configuration and feature projection"),
    (
        "backfill_country_baseline",
        "Academic year, terms, grading, structure, and subjects",
    ),
]

_VERIFY_STEPS = [
    ("verify_registry_coverage", [], "Verify country registry coverage"),
    ("verify_region_coverage", ["--strict"], "Verify RegionConfig coverage"),
    (
        "verify_platform_seed_completeness",
        [],
        "Verify exact catalogs and every active tenant baseline",
    ),
]


class Command(BaseCommand):
    help = (
        "End-to-end platform seed (public catalogs + tenant reconciliation). "
        "Superset of bootstrap_runmycampus_platform. Idempotent. "
        "DEBUG additionally receives demo fixtures."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--skip-public",
            action="store_true",
            help="Skip the public-schema bootstrap + extra public seeds.",
        )
        parser.add_argument(
            "--skip-tenants",
            action="store_true",
            help="Explicitly skip active-tenant reconciliation and DEBUG demo fan-out.",
        )
        parser.add_argument(
            "--skip-verify",
            action="store_true",
            help="Skip post-run coverage verification.",
        )
        parser.add_argument(
            "--continue-on-error",
            action="store_true",
            help="Log + continue on step failure instead of aborting.",
        )
        parser.add_argument(
            "--only-tenant",
            help="Limit per-tenant fan-out to a single tenant slug.",
        )

    def handle(self, *args, **options):
        verbosity = options["verbosity"]
        continue_on_error = options["continue_on_error"]
        only_tenant = options["only_tenant"]

        if not options["skip_public"]:
            self._public_phase(verbosity, continue_on_error)
        else:
            self._note("Skipping public-schema seeds (--skip-public).")

        self._account_phase(verbosity, continue_on_error)

        if not options["skip_tenants"]:
            self._tenant_phase(verbosity, continue_on_error, only_tenant)
        else:
            self._note("Skipping active-tenant reconciliation (--skip-tenants).")

        if not options["skip_verify"]:
            self._verify_phase(verbosity, continue_on_error, only_tenant)
        else:
            self._note("Skipping verification (--skip-verify).")

        self.stdout.write(
            self.style.SUCCESS("seed_platform_complete: end-to-end seed finished.")
        )

    # ------------------------------------------------------------------
    # Phases
    # ------------------------------------------------------------------

    def _public_phase(self, verbosity, continue_on_error):
        self._heading("Public-schema bootstrap (bootstrap_platform_catalog --all)")
        self._run_step(
            "bootstrap_platform_catalog",
            ["--all"],
            "Catalog + registries + portal + compliance",
            verbosity,
            continue_on_error,
        )
        self._heading("Extra public-schema seeds")
        for cmd_name, description in _PUBLIC_EXTRA_STEPS:
            self._run_step(cmd_name, [], description, verbosity, continue_on_error)

    def _account_phase(self, verbosity, continue_on_error):
        self._heading("Accounts + role wiring")
        for cmd_name, description in _ACCOUNT_STEPS:
            self._run_step(cmd_name, [], description, verbosity, continue_on_error)

    def _tenant_phase(self, verbosity, continue_on_error, only_tenant):
        self._heading("Tenant infrastructure")
        for cmd_name, description in _TENANT_INFRA_STEPS:
            self._run_step(cmd_name, [], description, verbosity, continue_on_error)

        from apps.schools.models import School

        qs = School.objects.filter(is_active=True).order_by("slug")
        if only_tenant:
            qs = qs.filter(slug=only_tenant)
        tenants = list(qs.values_list("slug", flat=True))
        if not tenants:
            self._note("No active tenants found; skipping tenant reconciliation.")
            return

        self._heading(f"Active-tenant reconciliation ({len(tenants)} tenant(s))")
        for slug in tenants:
            self.stdout.write(f"\ntenant: {slug}")
            for cmd_name, description in _TENANT_RECONCILIATION_STEPS:
                self._run_step(
                    cmd_name,
                    self._tenant_args_for(cmd_name, slug),
                    f"{description} (tenant={slug})",
                    verbosity,
                    continue_on_error,
                )

        if not settings.DEBUG:
            self._note(
                "DEBUG=False; production-safe tenant reconciliation completed; "
                "demo fixture seeders were not run."
            )
            return

        self._heading(f"DEBUG demo fan-out ({len(tenants)} tenant(s))")
        for slug in tenants:
            self.stdout.write(f"\ndemo tenant: {slug}")
            for cmd_name, description in _TENANT_STEPS_DEBUG_ONLY:
                self._run_step(
                    cmd_name,
                    self._tenant_args_for(cmd_name, slug),
                    f"{description} (tenant={slug})",
                    verbosity,
                    # Demo fixtures are optional and can collide in shared-schema SQLite.
                    continue_on_error=True,
                )

    def _verify_phase(self, verbosity, continue_on_error, only_tenant=""):
        self._heading("Verification")
        for cmd_name, args, description in _VERIFY_STEPS:
            step_args = list(args)
            if cmd_name == "verify_platform_seed_completeness" and only_tenant:
                step_args.append(f"--only-tenant={only_tenant}")
            self._run_step(
                cmd_name, step_args, description, verbosity, continue_on_error
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _tenant_args_for(self, cmd_name, slug):
        # Different demo seeders accept the tenant slug under different flags.
        if cmd_name == "seed_demo_tenant_users":
            return [f"--school-slug={slug}"]
        if cmd_name in ("seed_demo", "seed_testdata_2425"):
            return [f"--school={slug}"]
        if cmd_name == "reconcile_tenant_seed_baseline":
            return [f"--school={slug}"]
        if cmd_name == "align_tenant_config":
            return [f"--slug={slug}"]
        if cmd_name == "backfill_country_baseline":
            return [f"--school={slug}", "--strict"]
        return []

    def _run_step(self, cmd_name, extra_args, description, verbosity, continue_on_error):
        self.stdout.write(f"  -> {cmd_name}  ({description})")
        try:
            call_command(cmd_name, *extra_args, verbosity=max(verbosity - 1, 0))
        except _STEP_ERRORS as exc:
            log_exception_with_context(
                "seed_platform_complete: step failed",
                school_id=None,
                extra={"command": cmd_name, "extra_args": extra_args, "error": str(exc)},
            )
            self.stdout.write(self.style.WARNING(f"    ! {cmd_name} failed: {exc}"))
            if not continue_on_error:
                raise

    def _heading(self, text):
        self.stdout.write(self.style.MIGRATE_HEADING(f"\n== {text} =="))

    def _note(self, text):
        self.stdout.write(self.style.NOTICE(text))
