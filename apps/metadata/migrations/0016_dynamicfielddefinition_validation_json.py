# Generated for metric 5 (EAV) — validation/masking rules on dynamic field defs.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('metadata', '0015_derived_value_lineage'),
    ]

    operations = [
        migrations.AddField(
            model_name='dynamicfielddefinition',
            name='validation_json',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text=(
                    'Optional validation / handling rules carried from the country '
                    'EAV catalog, e.g. {"pattern": "^\\\\d{4}-\\\\d{4}-\\\\d{4}$", '
                    '"store_masked": true}. "pattern" attaches a RegexValidator at '
                    'form clean; "store_masked" persists a masked form only so raw '
                    'PII (e.g. an Aadhaar number) is never stored in plaintext.'
                ),
            ),
        ),
    ]
