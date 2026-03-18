# Financial Aid & Scholarships (Phase 1): AwardSource, Scholarship, FinancialAidApplication, AidAuditLog

from decimal import Decimal
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0038_enable_rls_postgresql"),
        ("schools", "0001_initial"),
        ("people", "0001_initial"),
        ("requests", "0001_initial"),
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="AwardSource",
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
                    "name",
                    models.CharField(
                        help_text="e.g. Endowment Fund, Donor X Grant", max_length=200
                    ),
                ),
                (
                    "total_budget",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("0.00"),
                        max_digits=14,
                        validators=[
                            django.core.validators.MinValueValidator(Decimal("0.00"))
                        ],
                    ),
                ),
                (
                    "remaining_funds",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("0.00"),
                        max_digits=14,
                        validators=[
                            django.core.validators.MinValueValidator(Decimal("0.00"))
                        ],
                    ),
                ),
                ("currency", models.CharField(default="USD", max_length=3)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="award_sources",
                        to="schools.school",
                    ),
                ),
            ],
            options={
                "verbose_name": "Award source",
                "verbose_name_plural": "Award sources",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="Scholarship",
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
                ("title", models.CharField(max_length=200)),
                (
                    "eligibility_criteria",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="JSON-Logic rules; context: gpa, sibling_count, student_tags, custom_attributes, attendance_rate, fee_status",
                    ),
                ),
                (
                    "award_amount",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=12,
                        validators=[MinValueValidator(Decimal("0.01"))],
                    ),
                ),
                ("is_renewable", models.BooleanField(default=False)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="scholarships",
                        to="schools.school",
                    ),
                ),
                (
                    "source",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="scholarships",
                        to="finance.awardsource",
                    ),
                ),
            ],
            options={
                "verbose_name": "Scholarship",
                "verbose_name_plural": "Scholarships",
                "ordering": ["title"],
            },
        ),
        migrations.CreateModel(
            name="FinancialAidApplication",
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
                    "status",
                    models.CharField(
                        choices=[
                            ("SUBMITTED", "Submitted"),
                            ("UNDER_REVIEW", "Under review"),
                            ("APPROVED", "Approved"),
                            ("REJECTED", "Rejected"),
                            ("DISBURSED", "Disbursed"),
                            ("CANCELLED", "Cancelled"),
                        ],
                        default="SUBMITTED",
                        max_length=20,
                    ),
                ),
                (
                    "amount_approved",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=12,
                        null=True,
                        validators=[
                            django.core.validators.MinValueValidator(Decimal("0.00"))
                        ],
                    ),
                ),
                (
                    "eligibility_failure_reason",
                    models.TextField(
                        blank=True,
                        help_text="Reason from check_eligibility or AI for appeal/dispute",
                    ),
                ),
                ("disbursed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="financial_aid_applications_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "dispute_link",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="financial_aid_applications",
                        to="requests.accessrequest",
                    ),
                ),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="financial_aid_applications",
                        to="schools.school",
                    ),
                ),
                (
                    "scholarship",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="applications",
                        to="finance.scholarship",
                    ),
                ),
                (
                    "student",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="financial_aid_applications",
                        to="people.studentprofile",
                    ),
                ),
            ],
            options={
                "verbose_name": "Financial aid application",
                "verbose_name_plural": "Financial aid applications",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="AidAuditLog",
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
                    "action",
                    models.CharField(
                        help_text="e.g. disbursement, donation, adjustment, refund",
                        max_length=40,
                    ),
                ),
                (
                    "amount",
                    models.DecimalField(
                        decimal_places=2, default=Decimal("0.00"), max_digits=14
                    ),
                ),
                (
                    "balance_after",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        help_text="remaining_funds after this action",
                        max_digits=14,
                        null=True,
                    ),
                ),
                ("reason", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "application",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="audit_log_entries",
                        to="finance.financialaidapplication",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="aid_audit_log_entries",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="aid_audit_logs",
                        to="schools.school",
                    ),
                ),
                (
                    "source",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="audit_logs",
                        to="finance.awardsource",
                    ),
                ),
            ],
            options={
                "verbose_name": "Aid audit log",
                "verbose_name_plural": "Aid audit logs",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="financialaidapplication",
            index=models.Index(
                fields=["school", "status"], name="finance_fin_school__a0e0e4_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="financialaidapplication",
            index=models.Index(
                fields=["student", "scholarship"], name="finance_fin_student_7b0e8a_idx"
            ),
        ),
    ]
