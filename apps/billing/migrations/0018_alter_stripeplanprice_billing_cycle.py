# StripePlanPrice cycle parity: allow a Stripe price to be mapped to the
# school-aligned cycles (SEMESTER / SCHOOL_YEAR / MULTI_YEAR) so those plans can
# be sold via Stripe Checkout, not only the platform ledger. Pure choices
# AlterField — no data change; existing MONTHLY/ANNUAL rows are unaffected.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0017_alter_tenantsubscription_billing_cycle'),
    ]

    operations = [
        migrations.AlterField(
            model_name='stripeplanprice',
            name='billing_cycle',
            field=models.CharField(choices=[('MONTHLY', 'Monthly'), ('SEMESTER', 'Per semester'), ('SCHOOL_YEAR', 'Per school year'), ('ANNUAL', 'Annual'), ('MULTI_YEAR', 'Multi-year')], default='MONTHLY', max_length=12),
        ),
    ]
