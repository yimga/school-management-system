"""Retire the dead, superseded people.NotificationPreference model (2026-06-14).

It had 0 code callers, 0 real tests (the similarly-named
apps/accounts/tests/test_notification_preferences.py actually exercises
siteconfig.models_tooling.UserPreference), and its reverse accessor
(StudentGuardian.notification_preference) was used nowhere. Coarse channel
toggles already live on StudentGuardian.receives_{email,sms,whatsapp}; the
user-level channels + weekly-digest concept already lives in the live
siteconfig UserPreference flow. Its only unique capability (per-category
method + digest cadence) was designed but never wired to any send path or UI.

Nothing FKs into it, so the DeleteModel cleanly drops the table.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("people", "0057_applicant_client_offline_id_and_more"),
    ]

    operations = [
        migrations.DeleteModel(
            name="NotificationPreference",
        ),
    ]
