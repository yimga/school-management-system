# API Key model for developer platform (8.1)

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("schools", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("apicenter", "0003_unify_audit_to_integration_drop_apiservice"),
    ]

    operations = [
        migrations.CreateModel(
            name="APIKey",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(help_text="Label for this key (e.g. Production, CI)", max_length=120)),
                ("key_prefix", models.CharField(editable=False, max_length=24)),
                ("secret_hash", models.CharField(editable=False, max_length=64)),
                ("scopes", models.JSONField(blank=True, default=list, help_text="Optional list of scope strings")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_used_at", models.DateTimeField(blank=True, null=True)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_api_keys",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "school",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="api_keys",
                        to="schools.school",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
                "verbose_name": "API Key",
                "verbose_name_plural": "API Keys",
            },
        ),
    ]
