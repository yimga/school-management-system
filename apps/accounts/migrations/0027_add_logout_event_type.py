# Add LOGOUT to SecurityAuditLog.EventType (Workstream 1.5: auth/security)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0026_remove_rolloverproposalitem_proposal_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="securityauditlog",
            name="event_type",
            field=models.CharField(
                choices=[
                    ("LOGIN", "Login"),
                    ("LOGOUT", "Logout"),
                    ("LOGIN_FAILED", "Login failed"),
                    ("MFA_CHANGE", "MFA changed"),
                    ("PWD_RESET", "Password reset"),
                    ("DATA_EXPORT", "Data export"),
                    ("LOCKDOWN_TRIGGERED", "Emergency lockdown"),
                    ("SESSION_REVOKED", "Sessions revoked"),
                    ("IMPOSSIBLE_TRAVEL", "Impossible travel (login from distant location)"),
                ],
                max_length=40,
            ),
        ),
    ]
