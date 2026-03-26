from django.core.management.base import BaseCommand

from apps.portal.models_kb import HelpAudience, HostedOfficeDocument


class Command(BaseCommand):
    help = "Seed sample hosted office documents for Collabora/WOPI smoke checks."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        if options.get("dry_run"):
            self.stdout.write(self.style.SUCCESS("Dry run: would create sample hosted office docs."))
            return

        samples = [
            ("Operator Playbook", HelpAudience.OPERATOR),
            ("Tenant Handbook", HelpAudience.TENANT),
        ]
        for title, aud in samples:
            obj, created = HostedOfficeDocument.objects.get_or_create(
                title=title,
                defaults={"help_audience": aud, "mime_type": "application/vnd.oasis.opendocument.text"},
            )
            if created and not obj.file:
                from django.core.files.base import ContentFile

                obj.file.save(f"{title.lower().replace(' ', '_')}.txt", ContentFile(b"Sample office content"), save=True)
            self.stdout.write(self.style.SUCCESS(f"{'CREATED' if created else 'EXISTS'}: {title}"))
