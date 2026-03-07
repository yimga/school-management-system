from django.db import migrations


DEFAULT_METHODS = [
    "MTN_MOMO",
    "ORANGE_MOMO",
    "BANK",
    "CASH",
]


def populate_available_methods(apps, schema_editor):
    ComplianceProfile = apps.get_model('finance', 'ComplianceProfile')
    for profile in ComplianceProfile.objects.all():
        methods = profile.available_payment_methods or []
        if not methods:
            profile.available_payment_methods = DEFAULT_METHODS
            profile.save(update_fields=["available_payment_methods"])


def reverse_noop(apps, schema_editor):
    # No reverse change; keep administrator edits if any.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0012_add_available_payment_methods'),
    ]

    operations = [
        migrations.RunPython(populate_available_methods, reverse_noop),
    ]
