# Generated manually for Stripe plan price mapping

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0004_add_quote_model"),
    ]

    operations = [
        migrations.CreateModel(
            name="StripePlanPrice",
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
                ("plan_code", models.SlugField(db_index=True, max_length=80)),
                ("stripe_price_id", models.CharField(max_length=120)),
                (
                    "billing_cycle",
                    models.CharField(
                        choices=[
                            ("MONTHLY", "Monthly"),
                            ("ANNUAL", "Annual"),
                        ],
                        default="MONTHLY",
                        max_length=12,
                    ),
                ),
                ("currency", models.CharField(default="USD", max_length=3)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Stripe plan price",
                "verbose_name_plural": "Stripe plan prices",
                "ordering": ["plan_code", "billing_cycle", "currency"],
            },
        ),
        migrations.AddConstraint(
            model_name="stripeplanprice",
            constraint=models.UniqueConstraint(
                fields=("plan_code", "billing_cycle", "currency"),
                name="billing_stripeplanprice_plan_cycle_currency_uniq",
            ),
        ),
    ]
