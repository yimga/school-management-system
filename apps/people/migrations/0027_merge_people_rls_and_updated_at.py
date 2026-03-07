# Generated merge migration to resolve conflicting leaves:
# - 0024_studentprofile_updated_at (from main)
# - 0026_enable_rls_postgresql (multi-tenant RLS)

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("people", "0024_studentprofile_updated_at"),
        ("people", "0026_enable_rls_postgresql"),
    ]

    operations = []
