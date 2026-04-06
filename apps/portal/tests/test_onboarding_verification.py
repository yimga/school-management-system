"""
§2.4 Tests for onboarding_verification (repository delegation).
"""

from django.test import TestCase

from apps.portal.onboarding_verification import check_siteconfig_migration_applied


class OnboardingVerificationTests(TestCase):
    """Test check_siteconfig_migration_applied."""

    def test_returns_bool_or_none(self):
        # With real DB: True if migration applied, False otherwise. No exception.
        result = check_siteconfig_migration_applied(
            "siteconfig", "0043_sitesettings_admission_number_config"
        )
        self.assertIn(result, (True, False, None))

    def test_default_args(self):
        # Default app/migration name.
        result = check_siteconfig_migration_applied()
        self.assertIn(result, (True, False, None))

    def test_nonexistent_migration_returns_false(self):
        # Non-existent migration name should return False (not applied).
        result = check_siteconfig_migration_applied(
            "siteconfig", "9999_nonexistent_migration"
        )
        self.assertIs(result, False)
