# v4.00.62 — dedicated LMSDiagActionAudit table (cleans up shared
# LMSPushGradeAudit table that v4.00.61 was using with a
# course_id="_diag_action" discriminator).
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('integrations_marketplace', '0003_lms_push_grade_audit'),
    ]

    operations = [
        migrations.CreateModel(
            name='LMSDiagActionAudit',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(db_index=True, help_text='force_refresh | force_rotate (or future action names).', max_length=32)),
                ('provider', models.CharField(db_index=True, max_length=24)),
                ('actor_hash', models.CharField(blank=True, default='', help_text="SHA-256[:12] of the actor's username (PII-free).", max_length=16)),
                ('actor_user_id', models.CharField(blank=True, default='', help_text='Actor user pk (string for UUID/int compatibility).', max_length=64)),
                ('considered', models.IntegerField(default=0)),
                ('ok_count', models.IntegerField(default=0)),
                ('failed_count', models.IntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={
                'verbose_name': 'LMS diag action audit',
                'verbose_name_plural': 'LMS diag action audits',
                'ordering': ('-created_at',),
                'indexes': [
                    models.Index(fields=['action', 'created_at'], name='integration_action_diag_idx'),
                    models.Index(fields=['provider', 'created_at'], name='integration_prov_diag_idx'),
                ],
            },
        ),
    ]
