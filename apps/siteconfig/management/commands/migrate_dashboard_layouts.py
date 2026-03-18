from django.core.management.base import BaseCommand

from apps.siteconfig.models_dashboard import (
    DashboardLayout,
    DashboardUserPreference,
    PAGE_CHOICES,
)


class Command(BaseCommand):
    help = (
        "Migrate legacy DashboardUserPreference layouts into the DashboardLayout table."
    )

    def handle(self, *args, **options):
        created = 0
        for pref in DashboardUserPreference.objects.all():
            legacy_layout = pref.dashboard_layout or {}
            if not isinstance(legacy_layout, dict) or not legacy_layout:
                continue
            payload = {
                "items": [],
                "__settings__": {"legacy_layout": legacy_layout},
            }
            role = (getattr(pref.user, "role", "") or "").upper()
            for page, _ in PAGE_CHOICES:
                defaults = {
                    "role": role,
                    "layout": payload,
                    "is_default": False,
                }
                layout_obj, was_created = DashboardLayout.objects.get_or_create(
                    user=pref.user,
                    page=page,
                    defaults=defaults,
                )
                if was_created:
                    created += 1
            pref.dashboard_layout = {}
            pref.save(update_fields=["dashboard_layout", "updated_at"])
        self.stdout.write(
            self.style.SUCCESS(f"Migrated {created} legacy dashboard layouts.")
        )
