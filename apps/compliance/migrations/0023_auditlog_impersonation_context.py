"""Wave C #4 Phase 2: operator-impersonation provenance on AuditLog.

Pure additive AddField (BooleanField default False + nullable-ish CharField with a
blank default), so it is safe on the append-only AuditLog table and requires no data
backfill — existing rows take the column defaults.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("compliance", "0022_rls_policy_default_deny"),
    ]

    operations = [
        migrations.AddField(
            model_name="auditlog",
            name="during_impersonation",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name="auditlog",
            name="impersonated_school_id",
            field=models.CharField(
                blank=True,
                default="",
                help_text="School PK impersonated when during_impersonation is True.",
                max_length=64,
            ),
        ),
    ]
