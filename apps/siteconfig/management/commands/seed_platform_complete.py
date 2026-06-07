"""
End-to-end platform seed: public-schema catalogs + per-tenant demo data in one
idempotent command. This is the canonical entry point for "seed everything on
the platform". It is a superset of ``bootstrap_runmycampus_platform`` (which
only seeds the public-schema catalog steps used at deploy).

Steps, in order:

  1. Public-schema bootstrap (delegates to ``bootstrap_platform_catalog --all``).
  2. Extra public-schema seeds that the bootstrap orchestrator does not include:
     marketplace scopes, first-party + phase-9 + ultra-high-end packages,
     process definitions, business glossary, entity catalog, office documents,
     report-platform / br10 plan SKUs, regions (i18n grading scales), preview
     fixtures, cursor twelve-phase, siteconfig→metadata sync.
  3. Account/role bootstrap: ensure_superadmin → ensure_default_tenant_admin →
     backfill_user_roles (idempotent role wiring for existing users).
  4. Per-tenant fan-out (for every active ``School``):
        - seed_demo_tenant_users  (demo.admin / demo.teacher / demo.parent)
        - seed_demo               (DEBUG-only: academic year + classrooms +
                                   students + teachers + evaluations)
        - seed_testdata_2425      (DEBUG-only: synthetic 2024/25 data)
  5. Health checks: verify_registry_coverage, verify_region_coverage.

Per-tenant steps that fail (e.g. seed_demo collisions when re-running across
tenants in single-schema SQLite) are logged as WARNING and skipped — the
remaining tenants still get their share. Public-schema failures abort the
run unless ``--continue-on-error`` is set.

Use ``--skip-tenants`` to seed only the public schema; useful in production
where tenant data is real and demo seeders should never run.

Reference-school seeds (``seed_buea_synthetic``) are intentionally NOT in
the standard fan-out — they install a specific dual-curriculum Cameroon
school dataset that only some demos want. Run those manually per tenant:
``python manage.py seed_buea_synthetic --school=<slug>``.

Honors [[feedback_no_hardcoding]]: every value sourced by the underlying
seed commands routes through RuntimeDefaults / registries / fixtures; this
command introduces no new hardcoded values, only orchestration.
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
    ("ensure_superadmin", "Platform super-admin user"),
    ("ensure_default_tenant_admin", "Per-tenant default admin"),
    ("backfill_user_roles", "Backfill role assignments for existing users"),
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

_VERIFY_STEPS = [
    ("verify_registry_coverage", "Verify country registry coverage"),
    ("verify_region_coverage", "Verify RegionConfig coverage"),
]


class Command(BaseCommand):
    help = (
        "End-to-end platform seed (public catalogs + per-tenant demo). "
        "Superset of bootstrap_runmycampus_platform. Idempotent. "
        "Use --skip-tenants in production."
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
            help="Skip per-tenant fan-out. Recommended in production.",
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
            self._note("Skipping per-tenant fan-out (--skip-tenants).")

        if not options["skip_verify"]:
            self._verify_phase(verbosity, continue_on_error)
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
        # Tenant schema provisioning runs regardless of DEBUG so a fresh Postgres
        # tenant gets its schema created before any per-tenant work; on SQLite
        # the command is a documented no-op.
        self._heading("Tenant infrastructure")
        for cmd_name, description in _TENANT_INFRA_STEPS:
            self._run_step(cmd_name, [], description, verbosity, continue_on_error)

        if not settings.DEBUG:
            self._note(
                "DEBUG=False; demo seeders refuse to run. "
                "Use --skip-tenants in production to silence this notice."
            )
            return

        from apps.schools.models import School

        qs = School.objects.filter(is_active=True).order_by("slug")
        if only_tenant:
            qs = qs.filter(slug=only_tenant)
        tenants = list(qs.values_list("slug", flat=True))
        if not tenants:
            self._note("No active tenants found; skipping per-tenant fan-out.")
            return

        self._heading(f"Per-tenant fan-out ({len(tenants)} tenant(s))")
        for slug in tenants:
            self.stdout.write(f"\n— tenant: {slug}")
            for cmd_name, description in _TENANT_STEPS_DEBUG_ONLY:
                args = self._tenant_args_for(cmd_name, slug)
                self._run_step(
                    cmd_name,
                    args,
                    f"{description} (tenant={slug})",
                    verbosity,
                    # Tenant collisions in shared-schema SQLite are expected;
                    # never abort the run on a per-tenant failure.
                    continue_on_error=True,
                )

    def _verify_phase(self, verbosity, continue_on_error):
        self._heading("Verification")
        for cmd_name, description in _VERIFY_STEPS:
            self._run_step(cmd_name, [], description, verbosity, continue_on_error)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _tenant_args_for(self, cmd_name, slug):
        # Different demo seeders accept the tenant slug under different flags.
        if cmd_name == "seed_demo_tenant_users":
            return [f"--school-slug={slug}"]
        if cmd_name in ("seed_demo", "seed_testdata_2425"):
            return [f"--school={slug}"]
        return []

    def _run_step(self, cmd_name, extra_args, description, verbosity, continue_on_error):
        self.stdout.write(f"  → {cmd_name}  ({description})")
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
