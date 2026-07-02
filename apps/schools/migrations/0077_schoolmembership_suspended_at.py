"""Add SchoolMembership.suspended_at — reversible suspension of a member's
management/ownership authority (T7 owner/superadmin lifecycle).

Pure AddField, nullable + indexed. Existing rows default to NULL (not suspended).
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("schools", "0076_alter_school_currency"),
    ]

    operations = [
        migrations.AddField(
            model_name="schoolmembership",
            name="suspended_at",
            field=models.DateTimeField(
                blank=True,
                db_index=True,
                help_text=(
                    "When set, this membership is suspended: the member keeps their "
                    "row (so ownership/history is preserved and they can be "
                    "reactivated) but loses management + ownership authority on this "
                    "school and their active sessions are revoked. Reversible — clear "
                    "it to reactivate."
                ),
                null=True,
            ),
        ),
    ]
