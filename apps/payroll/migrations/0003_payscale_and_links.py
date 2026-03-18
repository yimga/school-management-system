# Generated manually for PayScale system
# Date: 2026-01-28

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from django.core.validators import MinValueValidator
from decimal import Decimal


class Migration(migrations.Migration):
    dependencies = [
        ("payroll", "0002_alter_payrollrun_status_payrollrunapproval"),
        ("academics", "0004_classroom_academic_year_repair"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PayScale",
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
                        help_text="Name of the pay scale (e.g., 'Grade 1', 'Senior Teacher', 'Administrative Staff')",
                        max_length=100,
                    ),
                ),
                (
                    "code",
                    models.CharField(
                        help_text="Short code for the pay scale (e.g., 'GR1', 'SEN', 'ADM')",
                        max_length=20,
                        unique=True,
                    ),
                ),
                (
                    "description",
                    models.TextField(
                        blank=True,
                        help_text="Description of this pay scale and who it applies to",
                    ),
                ),
                (
                    "min_salary",
                    models.DecimalField(
                        decimal_places=2,
                        help_text="Minimum salary for this pay scale",
                        max_digits=12,
                        validators=[MinValueValidator(Decimal("0.00"))],
                    ),
                ),
                (
                    "max_salary",
                    models.DecimalField(
                        decimal_places=2,
                        help_text="Maximum salary for this pay scale",
                        max_digits=12,
                        validators=[MinValueValidator(Decimal("0.00"))],
                    ),
                ),
                (
                    "default_salary",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        help_text="Default starting salary when applying this scale (optional)",
                        max_digits=12,
                        null=True,
                        validators=[MinValueValidator(Decimal("0.00"))],
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        default=True,
                        help_text="Only active scales can be applied to new employees",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_pay_scales",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "department",
                    models.ForeignKey(
                        blank=True,
                        help_text="Optional: Restrict this scale to a specific department",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="pay_scales",
                        to="academics.department",
                    ),
                ),
            ],
            options={
                "verbose_name": "Pay Scale",
                "verbose_name_plural": "Pay Scales",
                "ordering": ["code", "name"],
            },
        ),
        migrations.AddIndex(
            model_name="payscale",
            index=models.Index(
                fields=["code", "is_active"], name="payroll_pay_code_is_a_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="payscale",
            index=models.Index(
                fields=["department", "is_active"], name="payroll_pay_departm_idx"
            ),
        ),
        migrations.AddField(
            model_name="payrollemployee",
            name="pay_scale",
            field=models.ForeignKey(
                blank=True,
                help_text="Pay scale/grade assigned to this employee",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="employees",
                to="payroll.payscale",
            ),
        ),
        migrations.AddField(
            model_name="employmentcontract",
            name="pay_scale",
            field=models.ForeignKey(
                blank=True,
                help_text="Pay scale for this contract period",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="contracts",
                to="payroll.payscale",
            ),
        ),
    ]
