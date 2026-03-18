"""
Report app installations; optionally list those that might need an update (same app has newer version elsewhere).
Does not change data. Use refresh_installation in services or admin to re-apply manifest.
Run: python manage.py marketplace_report_updates
"""

from django.core.management.base import BaseCommand

from apps.marketplace.models import AppInstallation


class Command(BaseCommand):
    help = "Report app installations; list installations per app for update awareness."

    def add_arguments(self, parser):
        parser.add_argument(
            "--show-version-spread",
            action="store_true",
            help="Show per-app version spread (installations may be on different app versions if app was updated).",
        )

    def handle(self, *args, **options):
        active = (
            AppInstallation.objects.filter(
                status=AppInstallation.Status.ACTIVE,
                uninstalled_at__isnull=True,
            )
            .select_related("app", "school")
            .order_by("app__slug", "-installed_at")
        )
        total = active.count()
        self.stdout.write(f"Active installations: {total}")
        if options["show_version_spread"]:
            # Per app: list (version, count); if an app has multiple versions, some installs might "need update"
            from collections import defaultdict

            version_counts = defaultdict(lambda: defaultdict(int))
            for inst in active:
                version_counts[inst.app.slug][inst.app.version] += 1
            for slug in sorted(version_counts.keys()):
                vers = version_counts[slug]
                n = sum(vers.values())
                if len(vers) > 1:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  {slug}: versions {dict(vers)} (multiple versions in use)"
                        )
                    )
                else:
                    only_ver = next(iter(vers.keys()))
                    self.stdout.write(f"  {slug}: {only_ver} ({n} installs)")
        self.stdout.write(
            self.style.SUCCESS(
                "Done. Use services.refresh_installation(inst) to re-apply manifest (e.g. widget_config)."
            )
        )
