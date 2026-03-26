"""
Seed platform data in **strict Cursor phase order** (1→12) per
``docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md`` phase_checklists index.

Each phase runs only after the previous phase completes. Child commands are the same
idempotent seeds used by ``bootstrap_platform_catalog`` and deploy runbooks; this command
adds **auditable phase boundaries** for greenfield installs and verification.

This does **not** replace ``bootstrap_platform_catalog --all`` (dependency order there is
optimized for catalogs). Use this when you need phase-by-phase traceability.

Examples::

    python manage.py seed_cursor_twelve_phases
    python manage.py seed_cursor_twelve_phases --from-phase 6 --to-phase 12
    python manage.py seed_cursor_twelve_phases --dry-run
    python manage.py seed_cursor_twelve_phases --strict-gilead-lint

Phase 12 runs ``seed_business_glossary`` then ``scripts/lint_gilead_residue.py`` (warning
only unless ``--strict-gilead-lint``).
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

from django.core.management import call_command
from django.core.management import get_commands, load_command_class
from django.core.management.base import BaseCommand
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.management.base import CommandError
from django.db import DatabaseError, IntegrityError, OperationalError

from apps.platform_runtime.structured_logging import log_exception_with_context

_SEED_CURSOR_ERRORS = (
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

# Management command name -> extra argv.
# Order within each phase is fixed; phases run 1 then 2 … then 12.
CURSOR_PHASE_PLAN: list[tuple[int, str, list[tuple[str, list[str], str]]]] = [
    (
        1,
        "Authenticated shell",
        [
            (
                "seed_render_users",
                [],
                "Platform super-admin (admin/admin) and optional tenant demo users",
            ),
        ],
    ),
    (
        2,
        "Design system",
        [
            (
                "seed_admin_dashboard_palettes",
                [],
                "Manager/admin dashboard color palettes",
            ),
        ],
    ),
    (
        3,
        "Navigation / command archetypes",
        [
            (
                "seed_platform_registries",
                [],
                "Countries, subdivisions, education levels, system types",
            ),
        ],
    ),
    (
        4,
        "Control plane UX",
        [
            (
                "seed_blueprint_policy_packs",
                [],
                "Blueprint packs and policy bundles (operator catalogs)",
            ),
        ],
    ),
    (
        5,
        "Studio OS",
        [
            (
                "seed_workflow_dashboard_packs",
                [],
                "Workflow packs and dashboard packs (Studio / automation spine)",
            ),
        ],
    ),
    (
        6,
        "Siteconfig / SiteSettings + runtime bridge",
        [
            (
                "backfill_runtime_defaults",
                [],
                "Sync RuntimeDefaults from SiteSettings (runtime-first payload)",
            ),
            (
                "normalize_ui_config",
                [],
                "Normalize PlatformGlobalBranding / ThemePack pointers (Batch 3)",
            ),
        ],
    ),
    (
        7,
        "Runtime-first (global platform data)",
        [
            (
                "seed_global_data",
                ["--skip-unesco"],
                "Global regions, country profiles, brand registry",
            ),
        ],
    ),
    (
        8,
        "Dashboards / role homes",
        [
            (
                "seed_capability_registry",
                [],
                "Marketplace capability codes (role-home / catalog density)",
            ),
        ],
    ),
    (
        9,
        "Security / trust",
        [
            (
                "seed_phase9_first_party_packages",
                [],
                "First-party package versions (blueprint/workflow/dashboard/policy packs)",
            ),
            (
                "seed_compliance_baseline",
                [],
                "Region feature rules and tenant compliance snapshots",
            ),
        ],
    ),
    (
        10,
        "Marketplace / packs / migration",
        [
            ("seed_marketplace_apps", [], "Marketplace apps and listings"),
            (
                "seed_provider_registry",
                [],
                "Provider registry (payment, email, SMS, identity, …)",
            ),
            (
                "seed_migration_profiles",
                [],
                "Migration connector profiles (SIS / finance / attendance)",
            ),
            ("seed_finance_defaults", [], "Finance compliance profiles and chart of accounts"),
        ],
    ),
    (
        11,
        "Marketing front",
        [
            ("seed_marketing_cms", [], "Marketing blog and CMS snippets"),
            ("seed_faqs", [], "Portal FAQ categories and questions"),
            ("seed_kb_articles", [], "Portal Knowledge Base articles"),
        ],
    ),
    (
        12,
        "Gilead purge + docs / metadata discipline",
        [
            (
                "seed_business_glossary",
                [],
                "Business glossary entries (metadata catalog vocabulary)",
            ),
        ],
    ),
]


class Command(BaseCommand):
    help = (
        "Run idempotent platform seeds in strict Cursor phase order (1-12). "
        "See docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md (phase_checklists)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Pass --dry-run to child commands that support it (others run normally).",
        )
        parser.add_argument(
            "--from-phase",
            type=int,
            default=1,
            help="Start at this phase number (inclusive, 1-12).",
        )
        parser.add_argument(
            "--to-phase",
            type=int,
            default=12,
            help="End at this phase number (inclusive, 1-12).",
        )
        parser.add_argument(
            "--strict-gilead-lint",
            action="store_true",
            help="After phase 12, fail if scripts/lint_gilead_residue.py exits non-zero.",
        )
        parser.add_argument(
            "--skip-gilead-lint",
            action="store_true",
            help="Skip scripts/lint_gilead_residue.py after phase 12.",
        )
        parser.add_argument(
            "--continue-on-error",
            action="store_true",
            help="Keep running later phases after a step failure; still exits non-zero.",
        )
        parser.add_argument(
            "--report-file",
            default="",
            help="Optional JSON report path (relative to repo root or absolute).",
        )

    @staticmethod
    def _command_supports_dry_run(command_name: str) -> bool:
        command_map = get_commands()
        app_name = command_map.get(command_name)
        if not app_name:
            return False
        try:
            cmd = load_command_class(app_name, command_name)
            parser = cmd.create_parser("manage.py", command_name)
        except Exception:
            return False
        for action in parser._actions:
            opts = set(getattr(action, "option_strings", []) or [])
            if "--dry-run" in opts:
                return True
        return False

    def handle(self, *args, **options):
        dry_run = bool(options.get("dry_run"))
        lo = max(1, min(12, int(options["from_phase"])))
        hi = max(1, min(12, int(options["to_phase"])))
        if lo > hi:
            raise CommandError("--from-phase must be <= --to-phase")

        verbosity = int(options.get("verbosity", 1))
        root = Path(__file__).resolve().parents[4]
        continue_on_error = bool(options.get("continue_on_error"))
        report_file = (options.get("report_file") or "").strip()
        started = time.time()
        report: dict[str, object] = {
            "from_phase": lo,
            "to_phase": hi,
            "dry_run": dry_run,
            "continue_on_error": continue_on_error,
            "steps": [],
        }
        had_failures = False

        for phase_num, title, steps in CURSOR_PHASE_PLAN:
            if phase_num < lo or phase_num > hi:
                continue
            self.stdout.write("")
            self.stdout.write(self.style.NOTICE(f"=== Cursor Phase {phase_num}: {title} ==="))
            for cmd_name, argv, blurb in steps:
                self.stdout.write(f"  -> {cmd_name}: {blurb}")
                extra = list(argv)
                if dry_run and self._command_supports_dry_run(cmd_name):
                    extra.append("--dry-run")
                elif dry_run:
                    self.stdout.write(
                        self.style.WARNING(
                            f"     (no --dry-run support for {cmd_name}; running live)"
                        )
                    )
                step_started = time.time()
                try:
                    call_command(cmd_name, *extra, verbosity=verbosity)
                except _SEED_CURSOR_ERRORS as e:
                    had_failures = True
                    elapsed_ms = int((time.time() - step_started) * 1000)
                    report["steps"].append(
                        {
                            "phase": phase_num,
                            "phase_title": title,
                            "command": cmd_name,
                            "status": "failed",
                            "elapsed_ms": elapsed_ms,
                            "error": str(e),
                        }
                    )
                    log_exception_with_context(
                        "seed_cursor_twelve_phases: step failed",
                        school_id=None,
                        extra={"phase": phase_num, "command": cmd_name, "error": str(e)},
                    )
                    if continue_on_error:
                        self.stdout.write(
                            self.style.WARNING(
                                f"     step failed; continuing because --continue-on-error is set: {e}"
                            )
                        )
                        continue
                    raise CommandError(f"Phase {phase_num} failed on {cmd_name}: {e}") from e
                elapsed_ms = int((time.time() - step_started) * 1000)
                report["steps"].append(
                    {
                        "phase": phase_num,
                        "phase_title": title,
                        "command": cmd_name,
                        "status": "ok",
                        "elapsed_ms": elapsed_ms,
                    }
                )

            if phase_num == 12 and not options.get("skip_gilead_lint"):
                script = root / "scripts" / "lint_gilead_residue.py"
                if script.is_file():
                    self.stdout.write("  -> lint_gilead_residue.py (product surface residue check)")
                    r = subprocess.run(
                        [sys.executable, str(script)],
                        cwd=str(root),
                        capture_output=True,
                        text=True,
                    )
                    if r.returncode != 0:
                        msg = (r.stdout or "") + (r.stderr or "")
                        if options.get("strict_gilead_lint"):
                            had_failures = True
                            raise CommandError(
                                f"lint_gilead_residue.py failed (exit {r.returncode}):\n{msg}"
                            )
                        self.stdout.write(
                            self.style.WARNING(
                                f"lint_gilead_residue.py reported issues (exit {r.returncode}); "
                                "fix or re-run with --strict-gilead-lint to fail hard."
                            )
                        )
                        if verbosity >= 2 and msg.strip():
                            self.stdout.write(msg)
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f"lint script missing: {script.relative_to(root)}"
                        )
                    )
        report["elapsed_ms"] = int((time.time() - started) * 1000)
        report["status"] = "failed" if had_failures else "ok"
        if report_file:
            target = Path(report_file)
            if not target.is_absolute():
                target = root / target
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(report, indent=2), encoding="utf-8")
            self.stdout.write(f"Seed report written: {target}")

        self.stdout.write("")
        if had_failures:
            raise CommandError(
                f"Cursor twelve-phase seed finished with failures (phases {lo}-{hi})."
            )
        self.stdout.write(self.style.SUCCESS(f"Cursor twelve-phase seed complete (phases {lo}-{hi})."))
