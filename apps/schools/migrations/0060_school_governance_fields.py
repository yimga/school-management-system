# Generated manually for global governance Phase 2A (batch 1562).

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("governance", "0001_initial"),
        ("schools", "0059_v4_00_12_rls_audit_pass"),
    ]

    operations = [
        migrations.AddField(
            model_name="school",
            name="governance_operating_mode",
            field=models.CharField(
                choices=[
                    ("standalone", "Standalone (no group membership)"),
                    ("group_member", "Group member (inherits per governance_inherit map)"),
                    (
                        "group_member_sovereign",
                        "Group member with local sovereignty (opt-in inheritance only)",
                    ),
                ],
                db_index=True,
                default="standalone",
                help_text="standalone | group_member | group_member_sovereign (default standalone).",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="school",
            name="organization",
            field=models.ForeignKey(
                blank=True,
                help_text="Optional Organization overlay; null = standalone individual management.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="schools",
                to="governance.organization",
            ),
        ),
    ]
