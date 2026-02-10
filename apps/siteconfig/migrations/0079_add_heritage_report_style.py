# Stub migration so 0080_merge can depend on it (heritage report style placeholder).

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("siteconfig", "0076_normalize_themepack_defaults_and_constraint"),
    ]

    operations = [
        # No-op: report style fields already exist; this resolves merge 0080 dependency.
    ]
