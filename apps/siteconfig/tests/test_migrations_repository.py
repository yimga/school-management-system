"""
§2.4 Tests for siteconfig.repositories.migrations_repository (raw SQL wrap).
"""

from django.test import TestCase

from apps.siteconfig.repositories.migrations_repository import is_migration_applied


class MigrationsRepositoryTests(TestCase):
    """Test is_migration_applied."""

    def test_returns_bool_or_none(self):
        result = is_migration_applied(
            "siteconfig", "0043_sitesettings_admission_number_config"
        )
        self.assertIn(result, (True, False, None))

    def test_nonexistent_migration_returns_false(self):
        result = is_migration_applied("siteconfig", "9999_nonexistent_migration")
        self.assertIs(result, False)
