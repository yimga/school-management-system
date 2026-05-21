"""Apply the canonical offline-mode feature bundle to one or all active schools."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.platform_runtime.offline_mode_bundle import apply_offline_mode_bundle_for_school


class Command(BaseCommand):
    help = (
        "Enable enable_offline_mode and related backend_feature_flags for field-work resilience "
        "(online Render or edge LAN hub). See docs/LOCAL_HUB_MODE.md."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--school-id",
            dest="school_id",
            default="",
            help="UUID of a single school to update.",
        )
        parser.add_argument(
            "--all-active",
            action="store_true",
            help="Apply to every active school.",
        )
        parser.add_argument(
            "--hub-base-url",
            default="",
            help="Optional hub_base_url for hybrid profile (e.g. http://192.168.1.10:8000).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print actions without writing.",
        )

    def handle(self, *args, **options):
        from apps.schools.models import School

        school_id = (options.get("school_id") or "").strip()
        all_active = bool(options.get("all_active"))
        hub = (options.get("hub_base_url") or "").strip()
        dry_run = bool(options.get("dry_run"))

        if not school_id and not all_active:
            self.stderr.write("Provide --school-id or --all-active.")
            return

        if school_id:
            schools = School.objects.filter(pk=school_id)
        else:
            schools = School.objects.filter(is_active=True).order_by("name")

        if not schools.exists():
            self.stderr.write("No matching schools.")
            return

        for school in schools.iterator():
            result = apply_offline_mode_bundle_for_school(
                school,
                hub_base_url=hub,
                dry_run=dry_run,
            )
            label = "dry-run" if dry_run else "applied"
            self.stdout.write(
                f"{label}: {school.slug} enable_offline_mode={result.get('enable_offline_mode')} "
                f"hub={result.get('hub_base_url', '') or '-'}"
            )
