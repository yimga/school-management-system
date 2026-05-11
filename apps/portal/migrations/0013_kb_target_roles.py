# Generated manually for role-based KB visibility (PARENT / TEACHER)
# Idempotent: this migration lives on a parallel branch from the main 0013 line.
# In environments where the main branch ran first (0024/0025 added target_roles
# via duplicate_column-safe SeparateDatabaseAndState), the column already exists
# when this migration is reached. Mirror that idempotency so Django's state
# converges without re-running the DDL.

from django.db import connection, migrations, models


def _add_target_roles(table_name):
    def runner(apps, schema_editor):
        with connection.cursor() as cursor:
            if connection.vendor == "postgresql":
                cursor.execute(
                    f"""
                    DO $$
                    BEGIN
                        ALTER TABLE {table_name}
                        ADD COLUMN target_roles JSONB NOT NULL DEFAULT '[]'::jsonb;
                    EXCEPTION WHEN duplicate_column THEN NULL;
                    END $$;
                    """
                )
            else:
                cursor.execute(f"PRAGMA table_info({table_name})")
                cols = [row[1] for row in cursor.fetchall()]
                if "target_roles" not in cols:
                    cursor.execute(
                        f"ALTER TABLE {table_name} ADD COLUMN target_roles TEXT NOT NULL DEFAULT '[]'"
                    )

    return runner


def _noop_reverse(apps, schema_editor):
    pass


_TARGET_ROLES_FIELD = models.JSONField(
    blank=True,
    default=list,
    help_text="Leave empty to show to everyone. Or list roles e.g. ['PARENT', 'TEACHER'] to show only to those roles.",
    verbose_name="Target roles",
)


class Migration(migrations.Migration):

    dependencies = [
        ('portal', '0012_merge_20260128_1924'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='kbcategory',
                    name='target_roles',
                    field=_TARGET_ROLES_FIELD,
                ),
            ],
            database_operations=[
                migrations.RunPython(_add_target_roles("portal_kbcategory"), _noop_reverse),
            ],
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='kbarticle',
                    name='target_roles',
                    field=_TARGET_ROLES_FIELD,
                ),
            ],
            database_operations=[
                migrations.RunPython(_add_target_roles("portal_kbarticle"), _noop_reverse),
            ],
        ),
    ]
