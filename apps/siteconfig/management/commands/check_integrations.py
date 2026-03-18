from django.core.management import BaseCommand

from apps.siteconfig.models import Integration


REQUIRED_KEYS = {
    "sms": ["api_key", "sender_id"],
    "payments": ["api_key", "secret", "webhook_secret"],
    "analytics": ["tracking_id"],
    "other": [],
}


class Command(BaseCommand):
    help = "Verify that enabled integrations have minimal required configuration."

    def handle(self, *args, **options):
        integrations = Integration.objects.filter(enabled=True)
        if not integrations.exists():
            self.stdout.write(self.style.WARNING("No enabled integrations found."))
            return

        ok = 0
        warn = 0
        for integ in integrations:
            required = REQUIRED_KEYS.get(integ.provider, [])
            missing = [
                key
                for key in required
                if key not in integ.config or integ.config.get(key) in (None, "")
            ]
            if missing:
                warn += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"{integ.name} ({integ.provider}) missing keys: {', '.join(missing)}"
                    )
                )
            else:
                ok += 1
                self.stdout.write(
                    self.style.SUCCESS(f"{integ.name} ({integ.provider}) OK")
                )

        self.stdout.write(
            self.style.NOTICE(
                f"Checked {integrations.count()} integrations: {ok} OK, {warn} warnings."
            )
        )
