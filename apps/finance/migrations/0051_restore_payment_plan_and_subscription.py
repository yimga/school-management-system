# Section 15.3: Re-introduce PaymentPlan and RecurringPaymentSubscription (removed in 0045).
# Required; integrated with Invoice/Payment per section_15_scope_implemented_and_roadmap.md.

from decimal import Decimal

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0050_alter_bankaccount_currency_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PaymentPlan",
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
                ("name", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=10)),
                (
                    "frequency",
                    models.CharField(
                        choices=[
                            ("WEEKLY", "Weekly"),
                            ("BIWEEKLY", "Bi-Weekly"),
                            ("MONTHLY", "Monthly"),
                            ("QUARTERLY", "Quarterly"),
                            ("ANNUALLY", "Annually"),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    "max_installments",
                    models.IntegerField(
                        help_text="Total number of payments, 0 for unlimited"
                    ),
                ),
                ("grace_period_days", models.IntegerField(default=0)),
                (
                    "late_fee_amount",
                    models.DecimalField(
                        decimal_places=2, default=Decimal("0.00"), max_digits=10
                    ),
                ),
                (
                    "early_payment_discount_percent",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("0.00"),
                        help_text="Discount for paying before due date",
                        max_digits=5,
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="RecurringPaymentSubscription",
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
                ("start_date", models.DateField()),
                ("next_payment_date", models.DateField()),
                ("last_payment_date", models.DateField(blank=True, null=True)),
                ("end_date", models.DateField(blank=True, null=True)),
                ("payments_made", models.IntegerField(default=0)),
                (
                    "total_paid",
                    models.DecimalField(
                        decimal_places=2, default=Decimal("0.00"), max_digits=10
                    ),
                ),
                ("missed_payments", models.IntegerField(default=0)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("ACTIVE", "Active"),
                            ("PAUSED", "Paused"),
                            ("CANCELLED", "Cancelled"),
                            ("COMPLETED", "Completed"),
                            ("DEFAULTED", "Defaulted"),
                        ],
                        default="ACTIVE",
                        max_length=20,
                    ),
                ),
                (
                    "payment_processor",
                    models.CharField(default="manual", max_length=50),
                ),
                (
                    "customer_payment_method_id",
                    models.CharField(blank=True, max_length=255),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "plan",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        to="finance.paymentplan",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="payment_subscriptions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(
            model_name="recurringpaymentsubscription",
            index=models.Index(
                fields=["status", "next_payment_date"],
                name="finance_rec_status_8a1b2c_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="recurringpaymentsubscription",
            index=models.Index(
                fields=["user", "status"], name="finance_rec_user_i_9d2e3f_idx"
            ),
        ),
    ]
