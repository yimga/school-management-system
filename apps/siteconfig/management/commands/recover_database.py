"""
Management command to recover or recreate corrupted SQLite database.
§2.4 Raw SQL wrap: delegates to siteconfig.repositories.database_recovery_repository.
§2.4: Typed exception tuple and log_exception_with_context for backup (shutil.copy2) failures.
"""

import logging
import shutil
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError

from apps.platform_runtime.structured_logging import log_exception_with_context
from apps.siteconfig.repositories.database_recovery_repository import (
    run_sqlite_integrity_check,
)

logger = logging.getLogger(__name__)

# §2.4 broad-except shrink: shutil.copy2 can raise these.
_RECOVER_DATABASE_BACKUP_ERRORS = (OSError, PermissionError, shutil.Error)


class Command(BaseCommand):
    help = "Recover or recreate corrupted SQLite database"

    def add_arguments(self, parser):
        parser.add_argument(
            "--recreate",
            action="store_true",
            help="Delete and recreate database (WARNING: loses all data)",
        )
        parser.add_argument(
            "--backup",
            action="store_true",
            help="Create backup before operations",
        )
        parser.add_argument(
            "--check-only",
            action="store_true",
            help="Only check database integrity, do not fix",
        )

    def handle(self, *args, **options):
        db_path = Path(settings.DATABASES["default"]["NAME"])
        check_only = options["check_only"]

        # Check if using SQLite
        if settings.DATABASES["default"]["ENGINE"] != "django.db.backends.sqlite3":
            self.stdout.write(
                self.style.WARNING(
                    f"Database engine is {settings.DATABASES['default']['ENGINE']}, "
                    "not SQLite. This command only works with SQLite."
                )
            )
            return

        if not db_path.exists():
            self.stdout.write(self.style.WARNING(f"Database file not found: {db_path}"))
            if check_only:
                raise CommandError(f"Database file not found: {db_path}")
            self.stdout.write("Creating new database...")
            call_command("migrate", verbosity=0)
            self.stdout.write(self.style.SUCCESS("Database created successfully!"))
            return

        # Check integrity
        self.stdout.write("Checking database integrity...")
        result = run_sqlite_integrity_check(db_path)
        if result == "ok":
            self.stdout.write(
                self.style.SUCCESS("[OK] Database integrity check passed!")
            )
            if check_only:
                return
        elif result is not None:
            message = f"[ERROR] Database is corrupted: {result}"
            self.stdout.write(self.style.ERROR(message))
            if check_only:
                raise CommandError(message)
        else:
            message = "[ERROR] Cannot check database (I/O or connection error)"
            self.stdout.write(self.style.ERROR(message))
            if check_only:
                raise CommandError(message)

        # Backup if requested
        if options["backup"] or options["recreate"]:
            backup_path = db_path.parent / f"{db_path.name}.backup"
            self.stdout.write(f"Creating backup: {backup_path}")
            try:
                shutil.copy2(db_path, backup_path)
                self.stdout.write(
                    self.style.SUCCESS(f"[OK] Backup created: {backup_path}")
                )
            except _RECOVER_DATABASE_BACKUP_ERRORS as e:
                log_exception_with_context(
                    "recover_database: backup failed",
                    school_id=None,
                    extra={"backup_path": str(backup_path), "error": str(e)},
                )
                self.stdout.write(
                    self.style.ERROR(f"[ERROR] Failed to create backup: {e}")
                )
                if options["recreate"]:
                    response = input("Continue without backup? (yes/no): ")
                    if response.lower() != "yes":
                        return

        # Recreate database
        if options["recreate"]:
            self.stdout.write(self.style.WARNING("DELETING CORRUPTED DATABASE..."))
            try:
                db_path.unlink()
                self.stdout.write(self.style.SUCCESS("[OK] Corrupted database deleted"))
            except (OSError, PermissionError) as e:
                log_exception_with_context(
                    "recover_database: unlink failed",
                    school_id=None,
                    extra={
                        "command": "recover_database",
                        "db_path": str(db_path),
                        "error": str(e),
                    },
                )
                logger.warning(
                    "recover_database unlink failed: %s",
                    e,
                    extra={"command": "recover_database"},
                )
                self.stdout.write(
                    self.style.ERROR(f"[ERROR] Failed to delete database: {e}")
                )
                return

            self.stdout.write("Creating new database...")
            try:
                call_command("migrate", verbosity=1)
                self.stdout.write(
                    self.style.SUCCESS("[OK] New database created successfully!")
                )
                self.stdout.write("\nNext steps:")
                self.stdout.write(
                    "  1. Create superuser: python manage.py createsuperuser"
                )
                self.stdout.write(
                    "  2. Load fixtures (if any): python manage.py loaddata <fixture>"
                )
            except (DatabaseError, OSError, PermissionError, SystemError) as e:
                log_exception_with_context(
                    "recover_database: migrate failed",
                    school_id=None,
                    extra={"command": "recover_database", "error": str(e)},
                )
                logger.warning(
                    "recover_database migrate failed: %s",
                    e,
                    extra={"command": "recover_database"},
                )
                self.stdout.write(
                    self.style.ERROR(f"[ERROR] Failed to create database: {e}")
                )
        else:
            self.stdout.write("\nTo recreate the database, run:")
            self.stdout.write("  python manage.py recover_database --recreate --backup")
            self.stdout.write("\n[WARNING] This will delete all data!")
