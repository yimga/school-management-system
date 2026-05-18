"""Seed Studio OS platform-wide rows + per-tenant SetupProgress scaffolds.

  python manage.py seed_studio_os                          # platform-wide rows only
  python manage.py seed_studio_os --all-active-schools     # + SetupProgress for every active school
  python manage.py seed_studio_os --school <slug>          # + SetupProgress for one school
  python manage.py seed_studio_os --dry-run                # report-only, no writes

Platform-wide rows are taken from `apps.setup_studio.services.STEP_DEFINITIONS`
so the seed cannot drift from the runtime contract that powers Setup/Launch Studio.

Multi-tenancy contract:
  - `SetupStepDefinition` is platform-wide master data (no tenant scope by design).
  - `SetupProgress` is tenant-scoped (FK → schools.School, unique per school).
    SetupProgress rows are created empty here; first call to
    `compile_setup_studio(school)` populates them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.setup_studio.models import SetupProgress, SetupStepDefinition
from apps.setup_studio.services import STEP_DEFINITIONS


@dataclass
class SweepRow:
    key: str
    action: str  # "created" | "updated" | "unchanged"
    label: str
    group: str
    order: int


class Command(BaseCommand):
    help = (
        "Seed Studio OS platform-wide SetupStepDefinition rows (8 canonical "
        "steps) and optionally scaffold per-tenant SetupProgress rows."
    )

    def add_arguments(self, parser):
        scope = parser.add_mutually_exclusive_group()
        scope.add_argument(
            "--school",
            help="School slug to scaffold an empty SetupProgress for.",
        )
        scope.add_argument(
            "--all-active-schools",
            action="store_true",
            help="Scaffold SetupProgress for every active school.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report planned writes; do not commit.",
        )

    def handle(self, *args, **options):
        dry = bool(options.get("dry_run"))

        step_sweep = self._seed_step_definitions(dry_run=dry)
        progress_sweep = self._seed_progress(
            slug=(options.get("school") or "").strip() or None,
            all_active=bool(options.get("all_active_schools")),
            dry_run=dry,
        )

        self._print_sweep_log(step_sweep, progress_sweep, dry=dry)

    def _seed_step_definitions(self, *, dry_run: bool) -> list[SweepRow]:
        rows: list[SweepRow] = []
        for order, definition in enumerate(STEP_DEFINITIONS, start=1):
            defaults = {
                "label": definition["label"],
                "description": definition["description"],
                "step_group": definition["step_group"],
                "order": order,
                "link": definition["link_name"],
                "is_active": True,
            }
            existing = SetupStepDefinition.objects.filter(key=definition["key"]).first()
            if existing is None:
                if not dry_run:
                    SetupStepDefinition.objects.create(
                        key=definition["key"], **defaults
                    )
                rows.append(
                    SweepRow(
                        key=definition["key"],
                        action="created",
                        label=defaults["label"],
                        group=defaults["step_group"],
                        order=order,
                    )
                )
                continue

            drift_fields = [
                f for f, v in defaults.items() if getattr(existing, f) != v
            ]
            if drift_fields:
                if not dry_run:
                    for field, value in defaults.items():
                        setattr(existing, field, value)
                    existing.save(update_fields=list(defaults.keys()))
                rows.append(
                    SweepRow(
                        key=existing.key,
                        action="updated",
                        label=defaults["label"],
                        group=defaults["step_group"],
                        order=order,
                    )
                )
            else:
                rows.append(
                    SweepRow(
                        key=existing.key,
                        action="unchanged",
                        label=defaults["label"],
                        group=defaults["step_group"],
                        order=order,
                    )
                )
        return rows

    def _seed_progress(
        self, *, slug: str | None, all_active: bool, dry_run: bool
    ) -> list[tuple[str, str]]:
        if not slug and not all_active:
            return []

        from apps.schools.models import School

        if slug:
            schools: Iterable[School] = School.objects.filter(slug=slug)
            if not schools.exists():
                raise CommandError(f"No school with slug {slug!r}")
        else:
            schools = School.objects.filter(is_active=True)

        sweep: list[tuple[str, str]] = []
        for school in schools:
            existing = SetupProgress.objects.filter(school=school).first()
            if existing is not None:
                sweep.append((school.slug, "exists"))
                continue
            if not dry_run:
                with transaction.atomic():
                    SetupProgress.objects.get_or_create(school=school)
            sweep.append((school.slug, "scaffolded"))
        return sweep

    def _print_sweep_log(
        self,
        step_sweep: list[SweepRow],
        progress_sweep: list[tuple[str, str]],
        *,
        dry: bool,
    ) -> None:
        banner = "DRY-RUN" if dry else "APPLIED"
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"[seed_studio_os] {banner} — SetupStepDefinition"
        ))
        for row in step_sweep:
            style = {
                "created": self.style.SUCCESS,
                "updated": self.style.WARNING,
                "unchanged": self.style.NOTICE,
            }[row.action]
            self.stdout.write(style(
                f"  [{row.action:>9}] #{row.order} {row.key:<22} "
                f"group={row.group:<12} label={row.label!r}"
            ))

        created = sum(1 for r in step_sweep if r.action == "created")
        updated = sum(1 for r in step_sweep if r.action == "updated")
        unchanged = sum(1 for r in step_sweep if r.action == "unchanged")
        self.stdout.write(
            f"  totals: created={created} updated={updated} unchanged={unchanged} "
            f"(expected total={len(STEP_DEFINITIONS)})"
        )

        if progress_sweep:
            self.stdout.write(self.style.MIGRATE_HEADING(
                f"[seed_studio_os] {banner} — SetupProgress (per-tenant)"
            ))
            for slug, action in progress_sweep:
                style = (
                    self.style.SUCCESS if action == "scaffolded" else self.style.NOTICE
                )
                self.stdout.write(style(f"  [{action:>10}] school={slug}"))
            scaffolded = sum(1 for _, a in progress_sweep if a == "scaffolded")
            already = sum(1 for _, a in progress_sweep if a == "exists")
            self.stdout.write(
                f"  totals: scaffolded={scaffolded} already-present={already} "
                f"(touched={len(progress_sweep)} tenant(s))"
            )

        self.stdout.write(self.style.SUCCESS(
            f"[seed_studio_os] {banner} complete."
        ))
