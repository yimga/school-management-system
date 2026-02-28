# Parent Wallet: balance and transactions for "Pay with wallet" at checkout

from decimal import Decimal
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0041_invoicepayershare_invoicepayersharepaymentallocation"),
        ("schools", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ParentWallet",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("currency_code", models.CharField(default="XAF", max_length=3)),
                (
                    "balance",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("0.00"),
                        max_digits=12,
                        validators=[MinValueValidator(Decimal("0.00"))],
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="parent_wallets",
                        to="schools.school",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        help_text="Guardian/parent user who owns this wallet.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="parent_wallets",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["school_id", "user_id"],
                "unique_together": {("school", "user")},
            },
        ),
        migrations.CreateModel(
            name="WalletTransaction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "amount",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=12,
                        help_text="Positive = credit (top-up, refund); negative = debit (payment).",
                    ),
                ),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("top_up", "Top-up"),
                            ("payment", "Payment"),
                            ("refund", "Refund"),
                            ("adjustment", "Adjustment"),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    "balance_after",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        help_text="Wallet balance after this transaction.",
                        max_digits=12,
                        null=True,
                    ),
                ),
                ("reference", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "payment",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="wallet_transactions",
                        to="finance.payment",
                    ),
                ),
                (
                    "wallet",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="transactions",
                        to="finance.parentwallet",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
    ]
