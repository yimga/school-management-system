"""
Bootstrap platform catalogs so Manager surfaces (Blueprint marketplace, App catalog,
registries, workflow/dashboard packs, portal FAQs/KB, etc.) are not empty.
Idempotent. Run at deploy or manually: python manage.py bootstrap_platform_catalog [--all]
§2.4: Typed exception tuple and log_exception_with_context for call_command failures.
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.core.exceptions import ImproperlyConfigured
from django.db import DatabaseError, OperationalError, IntegrityError
from django.core.exceptions import ValidationError

from apps.platform_runtime.structured_logging import log_exception_with_context
from django.core.management.base import CommandError

# §2.4 broad-except shrink: call_command can raise these from nested commands.
_BOOTSTRAP_PLATFORM_CATALOG_ERRORS = (
    CommandError,
    ImproperlyConfigured,
    DatabaseError,
    OperationalError,
    IntegrityError,
    ValidationError,
    OSError,
    TypeError,
    ValueError,
    AttributeError,
    ImportError,
)

# Order matters: global/regions first, then registries, then catalogs, then portal/compliance.
BOOTSTRAP_STEPS = [
    (
        "seed_global_data",
        ["--skip-unesco"],
        "Global regions, country profiles, brand registry",
    ),
    (
        "seed_platform_registries",
        [],
        "Countries, subdivisions, education levels, system types",
    ),
    ("seed_admin_dashboard_palettes", [], "Admin dashboard color palettes"),
    ("seed_blueprint_policy_packs", [], "Blueprint packs and policy bundles"),
    ("seed_workflow_dashboard_packs", [], "Workflow packs and dashboard packs"),
    ("seed_capability_registry", [], "Marketplace capability codes"),
    ("seed_marketplace_apps", [], "First-party marketplace apps and listings"),
    (
        "seed_provider_registry",
        [],
        "Platform provider registry (payment, email, SMS, document AI, identity, storage)",
    ),
    (
        "seed_migration_profiles",
        [],
        "Migration connector profiles (CSV/XLSX, student/finance/attendance/grades, generic SIS)",
    ),
    ("seed_finance_defaults", [], "Finance compliance profiles and chart of accounts"),
    ("seed_faqs", [], "Portal FAQ categories and questions"),
    ("seed_kb_articles", [], "Portal Knowledge Base articles"),
    (
        "seed_compliance_baseline",
        [],
        "Region feature rules and tenant compliance snapshots",
    ),
    (
        "seed_marketing_cms",
        [],
        "Marketing blog posts and CMS snippets for public site",
    ),
]


class Command(BaseCommand):
    help = (
        "Bootstrap platform catalogs: blueprint packs, marketplace apps, and optionally "
        "all applicable seeds (global data, registries, workflow/dashboard packs, portal, etc.). "
        "Use --all to run every applicable seed in dependency order."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--all",
            action="store_true",
            help="Run every applicable platform seed in dependency order (global data, registries, catalogs, portal, compliance).",
        )
        parser.add_argument(
            "--blueprint-only",
            action="store_true",
            help="Run only seed_blueprint_policy_packs.",
        )
        parser.add_argument(
            "--marketplace-only",
            action="store_true",
            help="Run only seed_marketplace_apps.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Pass --dry-run to seed commands that support it (e.g. marketplace, capability_registry).",
        )
        # Skip flags when using --all
        parser.add_argument(
            "--skip-global-data",
            action="store_true",
            help="With --all: skip seed_global_data.",
        )
        parser.add_argument(
            "--skip-registries",
            action="store_true",
            help="With --all: skip seed_platform_registries.",
        )
        parser.add_argument(
            "--skip-palettes",
            action="store_true",
            help="With --all: skip seed_admin_dashboard_palettes.",
        )
        parser.add_argument(
            "--skip-workflow-dashboard",
            action="store_true",
            help="With --all: skip seed_workflow_dashboard_packs.",
        )
        parser.add_argument(
            "--skip-capability-registry",
            action="store_true",
            help="With --all: skip seed_capability_registry.",
        )
        parser.add_argument(
            "--skip-finance-defaults",
            action="store_true",
            help="With --all: skip seed_finance_defaults.",
        )
        parser.add_argument(
            "--skip-portal",
            action="store_true",
            help="With --all: skip seed_faqs and seed_kb_articles.",
        )
        parser.add_argument(
            "--skip-compliance-baseline",
            action="store_true",
            help="With --all: skip seed_compliance_baseline.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        blueprint_only = options["blueprint_only"]
        marketplace_only = options["marketplace_only"]
        run_all = options["all"]

        if run_all:
            self._run_all_bootstrap(options)
            return

        # Default: only blueprint + marketplace (backward compatible)
        if not marketplace_only:
            self.stdout.write("Seeding blueprint packs…")
            call_command("seed_blueprint_policy_packs", verbosity=options["verbosity"])
        if not blueprint_only:
            self.stdout.write("Seeding marketplace apps…")
            extra = ["--dry-run"] if dry_run else []
            call_command(
                "seed_marketplace_apps", *extra, verbosity=options["verbosity"]
            )

        self.stdout.write(self.style.SUCCESS("Platform catalog bootstrap complete."))

    def _run_all_bootstrap(self, options):
        dry_run = options["dry_run"]
        verbosity = options["verbosity"]
        skips = {
            "seed_global_data": options["skip_global_data"],
            "seed_platform_registries": options["skip_registries"],
            "seed_admin_dashboard_palettes": options["skip_palettes"],
            "seed_workflow_dashboard_packs": options["skip_workflow_dashboard"],
            "seed_capability_registry": options["skip_capability_registry"],
            "seed_finance_defaults": options["skip_finance_defaults"],
            "seed_faqs": options["skip_portal"],
            "seed_kb_articles": options["skip_portal"],
            "seed_compliance_baseline": options["skip_compliance_baseline"],
        }
        for cmd_name, extra_args, description in BOOTSTRAP_STEPS:
            if skips.get(cmd_name, False):
                if verbosity >= 2:
                    self.stdout.write(f"Skipping {cmd_name} ({description}).")
                continue
            self.stdout.write(f"Running {cmd_name}… ({description})")
            extra = list(extra_args)
            if dry_run and cmd_name in (
                "seed_marketplace_apps",
                "seed_capability_registry",
                "seed_provider_registry",
                "seed_migration_profiles",
                "seed_blueprint_policy_packs",
                "seed_workflow_dashboard_packs",
                "seed_finance_defaults",
                "seed_faqs",
                "seed_kb_articles",
            ):
                extra.append("--dry-run")
            try:
                call_command(cmd_name, *extra, verbosity=verbosity)
            except _BOOTSTRAP_PLATFORM_CATALOG_ERRORS as e:
                log_exception_with_context(
                    "bootstrap_platform_catalog: step failed",
                    school_id=None,
                    extra={"command": cmd_name, "extra_args": extra, "error": str(e)},
                )
                self.stdout.write(self.style.WARNING(f"{cmd_name} failed: {e}"))
                if verbosity >= 1:
                    raise
        self.stdout.write(self.style.SUCCESS("Full platform bootstrap complete."))
