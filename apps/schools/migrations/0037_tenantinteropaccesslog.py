# Generated manually — Phase J+ interop audit

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("schools", "0036_add_school_primary_sector"),
    ]

    operations = [
        migrations.CreateModel(
            name="TenantInteropAccessLog",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "service",
                    models.CharField(db_index=True, default="oneroster", max_length=32),
                ),
                ("endpoint", models.CharField(db_index=True, max_length=64)),
                ("integration_id", models.IntegerField(blank=True, null=True)),
                ("client_ip", models.CharField(blank=True, max_length=64)),
                ("token_prefix", models.CharField(blank=True, max_length=16)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="interop_access_logs",
                        to="schools.school",
                    ),
                ),
            ],
            options={
                "verbose_name": "Tenant interop access log",
                "verbose_name_plural": "Tenant interop access logs",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="tenantinteropaccesslog",
            index=models.Index(
                fields=["school", "created_at"], name="schools_te_school_created_idx"
            ),
        ),
    ]
