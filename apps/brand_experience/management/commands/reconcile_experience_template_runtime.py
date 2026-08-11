"""Repair runtime state for templates applied before the activation bridge."""

from __future__ import annotations

from uuid import UUID

from django.core.management.base import BaseCommand, CommandError

from apps.brand_experience.template_runtime import (
    ExperienceRuntimeError,
    reconcile_latest_experience_template,
)
from apps.platform_runtime.models import PackInstallation
from apps.schools.models import School


class Command(BaseCommand):
    help = (
        "Audit or repair active ExperienceTemplate runtime assignments for "
        "existing tenant schools. The default mode is read-only."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Persist missing TemplateAssignment and school runtime state.",
        )
        parser.add_argument(
            "--school",
            default="",
            help="Limit to one school slug, subdomain, or primary-key UUID.",
        )

    def handle(self, *args, **options):
        queryset = School.objects.order_by("slug")
        school_ref = str(options.get("school") or "").strip()
        if school_ref:
            queryset = queryset.filter(slug=school_ref)
            if not queryset.exists():
                queryset = School.objects.filter(subdomain=school_ref)
            if not queryset.exists():
                try:
                    school_id = UUID(school_ref)
                except (TypeError, ValueError):
                    school_id = None
                queryset = (
                    School.objects.filter(pk=school_id)
                    if school_id is not None
                    else School.objects.none()
                )
            if not queryset.exists():
                raise CommandError(f"School {school_ref!r} was not found.")

        scanned = applied = healthy = repaired = failed = 0
        for school in queryset.iterator(chunk_size=100):
            scanned += 1
            has_applied = PackInstallation.objects.filter(
                school=school,
                pack_type="experience_template",
                status=PackInstallation.Status.APPLIED,
            ).exists()
            if not has_applied:
                continue
            applied += 1
            if not options["apply"]:
                from apps.brand_experience.models_template import TemplateAssignment

                if TemplateAssignment.objects.filter(
                    installed_package__school=school,
                    installed_package__is_active=True,
                ).exists() and (school.settings or {}).get("active_experience_templates"):
                    healthy += 1
                else:
                    self.stdout.write(
                        self.style.WARNING(f"NEEDS_REPAIR school={school.slug}")
                    )
                continue
            try:
                result = reconcile_latest_experience_template(school=school)
            except (ExperienceRuntimeError, TypeError, ValueError) as exc:
                failed += 1
                self.stderr.write(
                    self.style.ERROR(f"FAILED school={school.slug} error={exc}")
                )
                continue
            if result is None:
                failed += 1
                self.stderr.write(
                    self.style.ERROR(
                        f"FAILED school={school.slug} error=no compatible installed package"
                    )
                )
                continue
            if result.reconciled:
                repaired += 1
            else:
                healthy += 1

        mode = "APPLY" if options["apply"] else "AUDIT"
        summary = (
            f"{mode}: scanned={scanned} applied={applied} healthy={healthy} "
            f"repaired={repaired} failed={failed}"
        )
        if failed:
            raise CommandError(summary)
        self.stdout.write(self.style.SUCCESS(summary))
