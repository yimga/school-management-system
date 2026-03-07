# Phase 2: Notifications – configurable in-app and optional email to guardians

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('siteconfig', '0069_userpreference_preferred_language_region'),
    ]

    operations = [
        migrations.AddField(
            model_name='sitesettings',
            name='finance_notify_guardians_new_invoice',
            field=models.BooleanField(
                default=True,
                help_text='When a new invoice is issued, send in-app notification to guardians with finance access.',
            ),
        ),
        migrations.AddField(
            model_name='sitesettings',
            name='finance_notify_guardians_payment_received',
            field=models.BooleanField(
                default=True,
                help_text='When a payment is recorded, send in-app notification to guardians with finance access.',
            ),
        ),
        migrations.AddField(
            model_name='sitesettings',
            name='finance_notify_new_invoice_email',
            field=models.BooleanField(
                default=False,
                help_text='Also send email when a new invoice is issued (in addition to in-app notification).',
            ),
        ),
        migrations.AddField(
            model_name='sitesettings',
            name='finance_notify_payment_received_email',
            field=models.BooleanField(
                default=False,
                help_text='Also send email when a payment is recorded (in addition to in-app notification).',
            ),
        ),
    ]
