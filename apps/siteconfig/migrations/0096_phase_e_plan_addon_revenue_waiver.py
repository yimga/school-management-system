# Global Powerhouse Phase E: PlanAddon, CountryMultiplier, RevenueSnapshot, BillingWaiverAuditLog, WaiverRequest

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("siteconfig", "0095_backfill_tenant_systems"),
        ("schools", "0006_school_billing_type_waiver_note"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PlanAddon",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.SlugField(help_text="Feature code e.g. design_studio", max_length=80, unique=True)),
                ("name", models.CharField(help_text="Display name", max_length=120)),
                (
                    "price",
                    models.DecimalField(
                        decimal_places=2,
                        default=0,
                        help_text="Monthly price in base currency (before PPP multiplier)",
                        max_digits=10,
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Plan add-on",
                "verbose_name_plural": "Plan add-ons",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="CountryMultiplier",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("country_code", models.CharField(help_text="ISO 3166-1 alpha-2/3", max_length=3, unique=True)),
                (
                    "multiplier",
                    models.DecimalField(
                        decimal_places=4,
                        default=1,
                        help_text="Price multiplier (e.g. 0.6 for discounted region, 1.0 for base)",
                        max_digits=6,
                    ),
                ),
                ("name", models.CharField(blank=True, max_length=120)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Country price multiplier",
                "verbose_name_plural": "Country price multipliers",
                "ordering": ["country_code"],
            },
        ),
        migrations.CreateModel(
            name="RevenueSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("snapshot_date", models.DateField(help_text="First day of the month for this snapshot")),
                (
                    "actual_revenue",
                    models.DecimalField(
                        decimal_places=2,
                        default=0,
                        help_text="Actual revenue from this tenant for the period",
                        max_digits=14,
                    ),
                ),
                (
                    "waived_amount",
                    models.DecimalField(
                        decimal_places=2,
                        default=0,
                        help_text="Potential revenue waived (e.g. COMPLIMENTARY schools)",
                        max_digits=14,
                    ),
                ),
                ("billing_model", models.CharField(blank=True, max_length=20)),
                ("country_code", models.CharField(blank=True, max_length=3)),
                ("student_count", models.PositiveIntegerField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="revenue_snapshots",
                        to="schools.school",
                    ),
                ),
            ],
            options={
                "verbose_name": "Revenue snapshot",
                "verbose_name_plural": "Revenue snapshots",
                "ordering": ["-snapshot_date", "school"],
                "unique_together": {("school", "snapshot_date")},
            },
        ),
        migrations.CreateModel(
            name="BillingWaiverAuditLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("old_billing_type", models.CharField(blank=True, max_length=20)),
                ("new_billing_type", models.CharField(max_length=20)),
                ("old_waiver_note", models.CharField(blank=True, max_length=500)),
                ("new_waiver_note", models.CharField(blank=True, max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "changed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="billing_waiver_changes",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="billing_waiver_audit_logs",
                        to="schools.school",
                    ),
                ),
            ],
            options={
                "verbose_name": "Billing waiver audit log",
                "verbose_name_plural": "Billing waiver audit logs",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="WaiverRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "proof_file",
                    models.FileField(
                        blank=True,
                        help_text="Proof of NGO / non-profit status",
                        upload_to="waiver_requests/%Y/%m/",
                    ),
                ),
                ("reason", models.TextField(blank=True, help_text="Reason for waiver request")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("PENDING", "Pending"),
                            ("APPROVED", "Approved"),
                            ("DENIED", "Denied"),
                        ],
                        default="PENDING",
                        max_length=20,
                    ),
                ),
                ("decided_at", models.DateTimeField(blank=True, null=True)),
                ("decision_note", models.CharField(blank=True, max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "decided_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="waiver_decisions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="waiver_requests",
                        to="schools.school",
                    ),
                ),
            ],
            options={
                "verbose_name": "Waiver request",
                "verbose_name_plural": "Waiver requests",
                "ordering": ["-created_at"],
            },
        ),
    ]
