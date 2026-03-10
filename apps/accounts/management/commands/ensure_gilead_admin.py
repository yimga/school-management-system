"""
Deprecated alias: use ensure_default_tenant_admin instead.
Calls ensure_default_tenant_admin with the same arguments for backward compatibility.
"""
from django.core.management import BaseCommand, call_command


class Command(BaseCommand):
    help = "Deprecated. Use ensure_default_tenant_admin with --slug/--username/--password."

    def add_arguments(self, parser):
        parser.add_argument("--slug", default="", help="Tenant slug.")
        parser.add_argument("--username", default="", help="Tenant admin username.")
        parser.add_argument("--password", default="", help="Tenant admin password.")
        parser.add_argument("--use-admin-user", action="store_true")

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.WARNING(
                "ensure_gilead_admin is deprecated. Use: python manage.py ensure_default_tenant_admin"
            )
        )
        kwargs = {"verbosity": options.get("verbosity", 1)}
        if options.get("slug"):
            kwargs["slug"] = options["slug"]
        if options.get("username"):
            kwargs["username"] = options["username"]
        if options.get("password"):
            kwargs["password"] = options["password"]
        if options.get("use_admin_user"):
            kwargs["use_admin_user"] = True
        call_command("ensure_default_tenant_admin", **kwargs)
