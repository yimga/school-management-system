# -*- coding: utf-8 -*-
"""
Ensure the platform control-plane operator account exists: username **admin**, password **admin**.

This is a thin wrapper around **ensure_superuser** with fixed credentials so deploy scripts and
runbooks can call a clearly named command. **seed_render_users** already invokes
``ensure_superuser --username admin --password admin``; use this command when you only need the
platform admin without tenant seeding.

See docs/CONFIG_AND_USERNAMES_REFERENCE.md (platform vs tenant credentials).
"""

from django.core.management import BaseCommand, call_command


class Command(BaseCommand):
    help = (
        "Ensure platform super-admin admin/admin exists (SUPERADMIN role). "
        "Does not use ADMIN_PASSWORD; tenant demo users are not created."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--no-input",
            action="store_true",
            help="Non-interactive (default for this command).",
        )

    def handle(self, *args, **options):
        call_command(
            "ensure_superuser",
            "--username",
            "admin",
            "--password",
            "admin",
            "--email",
            "admin@example.com",
            "--no-input",
            verbosity=options.get("verbosity", 1),
        )
        self.stdout.write(
            self.style.SUCCESS(
                "Platform super-admin ready: admin / admin (manager host /super/; not tenant credentials)."
            )
        )
