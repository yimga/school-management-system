"""
Handle privacy requests: export PII and anonymize user data.

Usage:
    manage.py privacy_request --user-id <id> [--export] [--anonymize] [--delete-sessions]
    manage.py privacy_request --username <username> [--export] [--anonymize] [--delete-sessions]
"""

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model

from apps.compliance.privacy import export_user_data, anonymize_user

User = get_user_model()


class Command(BaseCommand):
    help = "Process privacy requests (export/anonymize user data)"

    def add_arguments(self, parser):
        parser.add_argument("--user-id", type=int, help="User ID to process")
        parser.add_argument("--username", type=str, help="Username to process")
        parser.add_argument("--export", action="store_true", help="Export user data to JSON")
        parser.add_argument("--anonymize", action="store_true", help="Anonymize user PII")
        parser.add_argument("--delete-sessions", action="store_true", help="Delete activity sessions during anonymization")

    def handle(self, *args, **options):
        user_id = options.get("user_id")
        username = options.get("username")
        do_export = options.get("export")
        do_anonymize = options.get("anonymize")
        delete_sessions = options.get("delete_sessions")

        if not do_export and not do_anonymize:
            raise CommandError("Specify at least one action: --export or --anonymize")

        try:
            if user_id:
                user = User.objects.get(id=user_id)
            elif username:
                user = User.objects.get(username=username)
            else:
                raise CommandError("Provide --user-id or --username")
        except User.DoesNotExist as exc:
            raise CommandError(f"User not found: {exc}")

        if do_export:
            path = export_user_data(user)
            self.stdout.write(self.style.SUCCESS(f"Exported data to {path}"))

        if do_anonymize:
            anonymize_user(user, delete_sessions=delete_sessions)
            self.stdout.write(self.style.SUCCESS("Anonymization complete"))
