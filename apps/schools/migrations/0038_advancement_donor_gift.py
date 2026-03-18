# Wedge 5 Phase 2 — advancement donors and gifts

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("schools", "0037_tenantinteropaccesslog"),
    ]

    operations = [
        migrations.CreateModel(
            name="AdvancementDonor",
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
                ("display_name", models.CharField(max_length=200)),
                ("email", models.EmailField(blank=True, max_length=254)),
                (
                    "external_ref",
                    models.CharField(
                        blank=True, help_text="External CRM id", max_length=120
                    ),
                ),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="advancement_donors",
                        to="schools.school",
                    ),
                ),
            ],
            options={
                "verbose_name": "Advancement donor",
                "verbose_name_plural": "Advancement donors",
                "ordering": ["-updated_at"],
            },
        ),
        migrations.CreateModel(
            name="AdvancementGift",
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
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("currency", models.CharField(default="USD", max_length=3)),
                ("received_at", models.DateField()),
                ("receipt_sent", models.BooleanField(default=False)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "donor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="gifts",
                        to="schools.advancementdonor",
                    ),
                ),
            ],
            options={
                "verbose_name": "Advancement gift",
                "verbose_name_plural": "Advancement gifts",
                "ordering": ["-received_at", "-pk"],
            },
        ),
    ]
