# Section 5.6: Workflow Hub — certified packs and versioning

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("siteconfig", "0134_add_dynamic_field_models"),
    ]

    operations = [
        migrations.AddField(
            model_name="workflowtemplate",
            name="certified",
            field=models.BooleanField(
                default=False,
                help_text="Section 5.6: Certified pack — platform-provided, safe to activate.",
            ),
        ),
        migrations.AddField(
            model_name="workflowtemplate",
            name="version",
            field=models.CharField(
                blank=True,
                default="1.0",
                help_text="Declarative version for upgrade-safety and rollback.",
                max_length=32,
            ),
        ),
    ]
