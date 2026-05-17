# Guided tour: body, selector, context, ordering, roles, is_active

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("siteconfig", "0175_serviceintegration_campus_and_connector_slug"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="tourstep",
            options={"ordering": ["context", "sort_order", "code"]},
        ),
        migrations.AddField(
            model_name="tourstep",
            name="body",
            field=models.TextField(
                blank=True,
                help_text="Optional longer copy shown in the tour tooltip.",
            ),
        ),
        migrations.AddField(
            model_name="tourstep",
            name="context",
            field=models.CharField(
                db_index=True,
                default="backend_dashboard",
                help_text="Tour context key, e.g. backend_dashboard, studio_os.",
                max_length=80,
            ),
        ),
        migrations.AddField(
            model_name="tourstep",
            name="is_active",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="tourstep",
            name="roles",
            field=models.CharField(
                blank=True,
                help_text="Optional comma-separated roles (ADMIN, TEACHER, …). Empty = all roles.",
                max_length=255,
            ),
        ),
        migrations.AddField(
            model_name="tourstep",
            name="selector",
            field=models.CharField(
                blank=True,
                help_text="CSS selector for spotlight; defaults to [data-tour='<code>'] when blank.",
                max_length=255,
            ),
        ),
        migrations.AddField(
            model_name="tourstep",
            name="sort_order",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AlterUniqueTogether(
            name="tourstep",
            unique_together={("school", "context", "code")},
        ),
    ]
