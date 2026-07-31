from django.db import migrations, models


PAYMENT_METHOD_CHOICES = [
    ("CASH", "Cash"),
    ("BANK", "Bank Transfer"),
    ("CARD", "Credit / Debit Card"),
    ("DIRECT_DEBIT", "Direct Debit / ACH"),
    ("MTN_MOMO", "MTN MoMo"),
    ("ORANGE_MOMO", "Orange Money"),
    ("MPESA", "M-Pesa"),
    ("USSD", "USSD Payment"),
    ("QR", "QR Payment"),
    ("CHECK", "Check"),
    ("WALLET", "Digital Wallet"),
    ("VOUCHER", "Voucher / Sponsor Code"),
    ("OTHER", "Other"),
]


class Migration(migrations.Migration):
    dependencies = [("finance", "0079_fractionalpaymentledger_tax_component")]

    operations = [
        migrations.AlterField(
            model_name="invoice",
            name="preferred_payment_method",
            field=models.CharField(blank=True, choices=PAYMENT_METHOD_CHOICES, default="", max_length=20),
        ),
        migrations.AlterField(
            model_name="payment",
            name="method",
            field=models.CharField(blank=True, choices=PAYMENT_METHOD_CHOICES, default="", max_length=20),
        ),
        migrations.AlterField(
            model_name="offlinepaymentintent",
            name="payment_method",
            field=models.CharField(choices=PAYMENT_METHOD_CHOICES, default="OTHER", max_length=20),
        ),
        migrations.AlterField(
            model_name="paymentproofupload",
            name="payment_method",
            field=models.CharField(choices=PAYMENT_METHOD_CHOICES, help_text="Payment method used (CASH, BANK, etc.)", max_length=20),
        ),
    ]
