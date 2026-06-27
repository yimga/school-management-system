# Adds the school-aligned billing cycles (SEMESTER / SCHOOL_YEAR / MULTI_YEAR) to
# TenantSubscription.billing_cycle so they are billable, not just selectable. Pure
# choices AlterField — no data change; existing MONTHLY/ANNUAL/MANUAL rows are unaffected.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0016_seed_country_billing_profiles'),
    ]

    operations = [
        migrations.AlterField(
            model_name='tenantsubscription',
            name='billing_cycle',
            field=models.CharField(choices=[('MONTHLY', 'Monthly'), ('SEMESTER', 'Per semester'), ('SCHOOL_YEAR', 'Per school year'), ('ANNUAL', 'Annual'), ('MULTI_YEAR', 'Multi-year'), ('MANUAL', 'Manual')], default='MONTHLY', max_length=12),
        ),
    ]
