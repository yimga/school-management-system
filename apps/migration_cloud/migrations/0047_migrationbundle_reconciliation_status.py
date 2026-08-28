# Generated manually — zero-touch import closure state on MigrationBundle.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("migration_cloud", "0046_tenant_fk_tables_rls"),
    ]

    operations = [
        migrations.AddField(
            model_name="migrationbundle",
            name="reconciliation_status",
            field=models.CharField(
                blank=True,
                choices=[
                    ("CLOSED", "Import closed — no human action required"),
                    ("PENDING_HUMAN", "Rows still need a human decision"),
                    ("BLOCKED", "Import blocked — repair or fix source required"),
                ],
                db_index=True,
                default="",
                help_text="Zero-touch closure state: CLOSED | PENDING_HUMAN | BLOCKED.",
                max_length=20,
            ),
        ),
    ]
