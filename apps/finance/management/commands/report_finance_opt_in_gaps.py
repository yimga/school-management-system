from django.core.management.base import BaseCommand

from apps.siteconfig.models import SiteSettings, default_backend_feature_flags
from apps.people.models import StudentGuardian


class Command(BaseCommand):
    help = "Report guardians who cannot view finance when opt-in is required."

    def handle(self, *args, **options):
        site = SiteSettings.get_solo()
        flags = {**default_backend_feature_flags(), **(site.backend_feature_flags or {})}
        require = bool(flags.get("require_guardian_finance_opt_in"))

        total_guardians = StudentGuardian.objects.count()
        missing_opt_in = StudentGuardian.objects.filter(can_view_finance=False).count()

        self.stdout.write(f"Opt-in required: {require}")
        self.stdout.write(f"Total guardian links: {total_guardians}")
        self.stdout.write(f"Guardians without finance access: {missing_opt_in}")

        if require and missing_opt_in:
            self.stdout.write(
                self.style.WARNING(
                    "Finance opt-in is ON and some guardians lack finance visibility. "
                    "Consider updating can_view_finance or temporarily disabling the flag."
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS("No gaps detected for current opt-in setting."))
