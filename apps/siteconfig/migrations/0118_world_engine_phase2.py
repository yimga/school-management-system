# World Engine Phase 2. Idempotent AddFields for Render (zone, is_vip, upvote_count).

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def _col_exists_pg(cursor, table, column):
    cursor.execute(
        "SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
        [table, column],
    )
    return cursor.fetchone() is not None


def _col_exists_sqlite(cursor, table, column):
    cursor.execute("PRAGMA table_info(%s)" % table)
    return any(row[1] == column for row in cursor.fetchall())


def add_phase2_columns_if_missing(apps, schema_editor):
    conn = schema_editor.connection
    with conn.cursor() as cursor:
        if conn.vendor == "postgresql":
            if not _col_exists_pg(cursor, "siteconfig_countrymultiplier", "zone"):
                cursor.execute(
                    "ALTER TABLE siteconfig_countrymultiplier ADD COLUMN zone varchar(1) NOT NULL DEFAULT ''"
                )
            if not _col_exists_pg(cursor, "siteconfig_customfeatureticket", "is_vip"):
                cursor.execute(
                    "ALTER TABLE siteconfig_customfeatureticket ADD COLUMN is_vip boolean NOT NULL DEFAULT false"
                )
            if not _col_exists_pg(cursor, "siteconfig_customfeatureticket", "upvote_count"):
                cursor.execute(
                    "ALTER TABLE siteconfig_customfeatureticket ADD COLUMN upvote_count integer NOT NULL DEFAULT 0"
                )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS siteconfig__is_vip_ae86c4_idx ON siteconfig_customfeatureticket (is_vip, upvote_count DESC)"
            )
        else:
            # SQLite (local/CI tests)
            if not _col_exists_sqlite(cursor, "siteconfig_countrymultiplier", "zone"):
                cursor.execute(
                    "ALTER TABLE siteconfig_countrymultiplier ADD COLUMN zone varchar(1) NOT NULL DEFAULT ''"
                )
            if not _col_exists_sqlite(cursor, "siteconfig_customfeatureticket", "is_vip"):
                cursor.execute(
                    "ALTER TABLE siteconfig_customfeatureticket ADD COLUMN is_vip integer NOT NULL DEFAULT 0"
                )
            if not _col_exists_sqlite(cursor, "siteconfig_customfeatureticket", "upvote_count"):
                cursor.execute(
                    "ALTER TABLE siteconfig_customfeatureticket ADD COLUMN upvote_count integer NOT NULL DEFAULT 0"
                )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS siteconfig__is_vip_ae86c4_idx ON siteconfig_customfeatureticket (is_vip, upvote_count DESC)"
            )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("schools", "0024_world_engine_phase2"),
        ("siteconfig", "0117_world_engine"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='BreakGlassOverride',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('scope', models.CharField(db_index=True, max_length=80)),
                ('target_id', models.CharField(blank=True, help_text='e.g. user_id, school_id.', max_length=255)),
                ('reason', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='BroadcastCampaign',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('subject', models.CharField(max_length=255)),
                ('body', models.TextField()),
                ('status', models.CharField(choices=[('DRAFT', 'Draft'), ('QUEUED', 'Queued'), ('SENDING', 'Sending'), ('COMPLETED', 'Completed'), ('CANCELLED', 'Cancelled')], default='DRAFT', max_length=20)),
                ('slide_confirm_required', models.BooleanField(default=True, help_text='Recipient must slide-to-confirm.')),
                ('target_count', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='LearningPassport',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('external_id', models.CharField(blank=True, db_index=True, max_length=255)),
                ('credentials', models.JSONField(blank=True, default=dict, help_text='Achievements, badges, mapped syllabus nodes.')),
                ('country_code', models.CharField(blank=True, db_index=True, max_length=10)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Learning passport',
                'verbose_name_plural': 'Learning passports',
                'ordering': ['-updated_at'],
            },
        ),
        migrations.AlterModelOptions(
            name='customfeatureticket',
            options={'ordering': ['-is_vip', '-upvote_count', '-created_at']},
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='countrymultiplier',
                    name='zone',
                    field=models.CharField(blank=True, choices=[('A', 'Zone A (premium)'), ('B', 'Zone B (standard)'), ('C', 'Zone C (discounted)')], help_text='PPP zone for display (A/B/C).', max_length=1),
                ),
                migrations.AddField(
                    model_name='customfeatureticket',
                    name='is_vip',
                    field=models.BooleanField(default=False, help_text='VIP / high-priority feature request for roadmap.'),
                ),
                migrations.AddField(
                    model_name='customfeatureticket',
                    name='upvote_count',
                    field=models.PositiveIntegerField(default=0, help_text='Upvotes from school admins (Vision Board).'),
                ),
                migrations.AddIndex(
                    model_name='customfeatureticket',
                    index=models.Index(fields=['is_vip', '-upvote_count'], name='siteconfig__is_vip_ae86c4_idx'),
                ),
            ],
            database_operations=[
                migrations.RunPython(add_phase2_columns_if_missing, noop),
            ],
        ),
        migrations.AddField(
            model_name='breakglassoverride',
            name='actor',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='broadcastcampaign',
            name='created_by',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='broadcastcampaign',
            name='school',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='broadcast_campaigns', to='schools.school'),
        ),
        migrations.AddField(
            model_name='learningpassport',
            name='school',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='learning_passports', to='schools.school'),
        ),
        migrations.AddField(
            model_name='learningpassport',
            name='user',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='learning_passports', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddIndex(
            model_name='breakglassoverride',
            index=models.Index(fields=['scope', 'target_id'], name='siteconfig__scope_63f107_idx'),
        ),
        migrations.AlterUniqueTogether(
            name='learningpassport',
            unique_together={('user', 'school')},
        ),
    ]
