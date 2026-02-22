# Phase I: Initial migration for Client (TenantMixin) and Domain (DomainMixin).
# Run this only when USE_DJANGO_TENANTS=1 and after migrate_schemas --shared.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("schools", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Client",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("schema_name", models.CharField(db_index=True, max_length=63, unique=True)),
                ("name", models.CharField(max_length=255)),
                ("created_on", models.DateField(auto_now_add=True)),
                ("school", models.OneToOneField(
                    blank=True,
                    help_text="Existing School record in public schema",
                    null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="tenant_client",
                    to="schools.school",
                )),
            ],
            options={
                "verbose_name": "Tenant (Client)",
                "verbose_name_plural": "Tenants (Clients)",
            },
        ),
        migrations.CreateModel(
            name="Domain",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("domain", models.CharField(db_index=True, max_length=253, unique=True)),
                ("is_primary", models.BooleanField(db_index=True, default=True)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="domains", to="customers.client")),
            ],
            options={
                "abstract": False,
            },
        ),
    ]
