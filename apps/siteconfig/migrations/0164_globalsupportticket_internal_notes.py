# Generated manually for support desk operator notes.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("siteconfig", "0163_phase_b_batch3_drop_sitesettings_branding_columns"),
    ]

    operations = [
        migrations.AddField(
            model_name="globalsupportticket",
            name="internal_notes",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Operator-only notes (not shown to tenants); minimize PII.",
            ),
        ),
    ]
