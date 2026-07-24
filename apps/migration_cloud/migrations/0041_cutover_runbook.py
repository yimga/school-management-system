# Audit G-3 (2026-07-24) — CutoverRunbook: the rehearsal → real → sign-off
# record with a reconciliation-scorecard integrity anchor. Two operations:
#   * CreateModel CutoverRunbook (school + rehearsal/real bundle FKs +
#     status + reconciliation_scorecard_sha256 + verbatim signer fields).
#   * AlterField on migrationcloudauditevent.event_type — appends the new
#     ``migration.cutover.signed_off`` choice so record_signoff's lifecycle
#     audit event is a registered type (not a masquerading fallback).

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('migration_cloud', '0040_register_connector_dsar_maa_audit_event_types'),
        ('schools', '0081_rls_backfill_unenumerated_tenant_tables'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name='migrationcloudauditevent',
            name='event_type',
            field=models.CharField(choices=[('companion.upload', 'Companion upload accepted'), ('maa.sign', 'MAA signed'), ('maa.sign_attempt_draft', 'Attempt to sign a DRAFT MAA refused'), ('key.rotate', 'Companion server-keypair rotated'), ('webhook.subscription.created', 'Webhook subscription created'), ('webhook.subscription.deleted', 'Webhook subscription deleted (deactivated)'), ('webhook.delivery.replay', 'Webhook delivery manually replayed'), ('token.mint', 'Scoped API token minted'), ('token.revoke', 'Scoped API token revoked'), ('legacy_hash.decrypt', 'Legacy SIS-hash field decrypted'), ('audit.retention_purge_applied', 'Audit retention purge applied (counsel-approved)'), ('migration.intake.state_advanced', 'Migration intake state advanced'), ('migration.guardian_consent.campaign_started', 'Guardian consent campaign started'), ('migration.guardian_consent.minted', 'Guardian consent token minted'), ('migration.guardian_consent.first_seen', 'Guardian opened the consent page for the first time'), ('migration.guardian_consent.consented', 'Guardian consented to migration'), ('migration.guardian_consent.declined', 'Guardian declined consent'), ('migration.guardian_consent.revoked', 'Guardian revoked previously-granted consent'), ('migration.guardian_consent.expired', 'Guardian consent token expired before decision'), ('migration.guardian_consent.resent', 'Guardian consent email resent'), ('audit.rate_limit_triggered', 'Audit event volume rate-limit triggered for a tenant'), ('migration.maa.v2_activated_by_operator', 'MAA v2.0 activated by operator (counsel signoff on file)'), ('migration.data_retention.purge_applied', 'Migration data retention purge applied (counsel-approved)'), ('lifecycle.offboarding.export', 'School offboarding data export generated'), ('lifecycle.offboarding.deactivated', 'School deactivated (offboarding)'), ('lifecycle.offboarding.purge_requested', 'School offboarding purge requested'), ('lifecycle.offboarding.purge_completed', 'School offboarding purge completed'), ('migration.bundle.advanced', 'Migration bundle advanced through profile/classify/map'), ('migration.bundle.applied', 'Migration bundle apply completed (live or dry-run)'), ('connector.connection', 'Connector source-connection lifecycle event'), ('connector.credential_access', 'Connector source credential accessed'), ('connector.discovery', 'Connector schema discovery run'), ('connector.mapping', 'Connector field mapping confirmed'), ('connector.import', 'Connector import run'), ('connector.rollback', 'Connector import rollback'), ('connector.event', 'Connector workflow event (uncategorized)'), ('migration.dsar.runbook_recorded', 'DSAR fulfillment runbook recorded'), ('maa.v2_promotion_applied', 'MAA v2.0 promotion applied by operator'), ('migration.cutover.signed_off', 'Cutover runbook signed off (rehearsal→real→sign-off)')], db_index=True, help_text='One of the registered audit event types.', max_length=64),
        ),
        migrations.CreateModel(
            name='CutoverRunbook',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('label', models.CharField(blank=True, default='', help_text="Operator-readable label (e.g. 'Sept 2026 district cutover').", max_length=200)),
                ('status', models.CharField(choices=[('draft', 'Draft'), ('rehearsed', 'Rehearsed (dry-run cutover completed)'), ('executed', 'Executed (real cutover applied)'), ('signed_off', 'Signed off')], db_index=True, default='draft', max_length=16)),
                ('reconciliation_scorecard_sha256', models.CharField(blank=True, default='', help_text="SHA-256 of the real_bundle's reconciliation scorecard (reconciliation_summary) captured at sign-off. Integrity anchor: a later scorecard mutation no longer matches this digest.", max_length=64)),
                ('signed_off_at', models.DateTimeField(blank=True, db_index=True, help_text='When the sign-off was recorded. NULL until signed.', null=True)),
                ('signer_name', models.CharField(blank=True, default='', help_text='Verbatim name of the person signing off, captured at sign time.', max_length=256)),
                ('signer_title', models.CharField(blank=True, default='', help_text='Verbatim role/title of the signer, captured at sign time.', max_length=256)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, help_text='Operator who created the runbook.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='cutover_runbooks_created', to=settings.AUTH_USER_MODEL)),
                ('real_bundle', models.ForeignKey(blank=True, help_text='The live cutover bundle whose reconciliation is signed off.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='cutover_runbooks_as_real', to='migration_cloud.migrationbundle')),
                ('rehearsal_bundle', models.ForeignKey(blank=True, help_text='The dry-run bundle used to rehearse the cutover.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='cutover_runbooks_as_rehearsal', to='migration_cloud.migrationbundle')),
                ('school', models.ForeignKey(help_text='The district this cutover runbook belongs to.', on_delete=django.db.models.deletion.CASCADE, related_name='cutover_runbooks', to='schools.school')),
                ('signed_off_by', models.ForeignKey(blank=True, help_text='Operator who recorded the sign-off. NULL for system sign-offs.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='cutover_runbooks_signed', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Cutover runbook',
                'verbose_name_plural': 'Cutover runbooks',
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['school', '-created_at'], name='migration_c_school__e59553_idx'), models.Index(fields=['status', '-created_at'], name='migration_c_status_0b5b11_idx')],
            },
        ),
    ]
