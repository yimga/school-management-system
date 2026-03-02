# Default payment_processor to manual (not Stripe); tenant opts in to stripe.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0043_compliance_profile_vat_report_currency'),
    ]

    operations = [
        migrations.AlterField(
            model_name='recurringpaymentsubscription',
            name='payment_processor',
            field=models.CharField(default='manual', max_length=50),
        ),
    ]
