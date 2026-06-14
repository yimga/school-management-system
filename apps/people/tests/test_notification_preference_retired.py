"""Retirement guard (2026-06-14) — people.NotificationPreference is gone.

Plain ``unittest`` (no DB) so it runs where the Django test runner can't.

The model was dead + superseded (0 callers, 0 real tests, unused reverse
accessor; coarse channel toggles live on StudentGuardian.receives_*, and
user-level channels + weekly digest live in siteconfig.UserPreference). It was
removed in migration 0058_delete_notificationpreference.
"""

from __future__ import annotations

import os
import pathlib
import unittest

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

REPO = pathlib.Path(__file__).resolve().parent.parent.parent.parent


class NotificationPreferenceRetiredTests(unittest.TestCase):

    def test_model_attribute_is_gone(self) -> None:
        from apps.people import models

        self.assertFalse(hasattr(models, "NotificationPreference"))

    def test_reverse_accessor_removed_from_guardian(self) -> None:
        from apps.people.models import StudentGuardian

        names = {f.name for f in StudentGuardian._meta.get_fields()}
        self.assertNotIn("notification_preference", names)

    def test_delete_migration_exists(self) -> None:
        mig = (
            REPO
            / "apps"
            / "people"
            / "migrations"
            / "0058_delete_notificationpreference.py"
        ).read_text(encoding="utf-8", errors="replace")
        self.assertIn("migrations.DeleteModel", mig)
        self.assertIn('name="NotificationPreference"', mig)

    def test_live_userpreference_flow_untouched(self) -> None:
        # The superseding live mechanism must still exist.
        from apps.siteconfig.models_tooling import UserPreference

        names = {f.name for f in UserPreference._meta.get_fields()}
        self.assertIn("notification_channels", names)
        self.assertIn("receive_weekly_summary", names)


if __name__ == "__main__":
    unittest.main()
