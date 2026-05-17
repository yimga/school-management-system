"""Tier 1 + 2 model surface for the sms-v3.7 / v3.8 migration cloud waves.

Adds:
    * ``MigrationBundle.expected_totals`` (financial guardrail control totals)
    * ``MigrationBundle.progress_snapshot`` (DAG view live progress)
    * ``MigrationBundle.diff_mode`` + ``diff_since`` (diff-mode re-ingest)
    * ``MigrationBundle.apply_atomic`` (all-or-nothing apply opt-in)
    * ``MigrationBundle.parity_drift_rollback_pct`` (auto-rollback threshold)
    * ``MigrationBundle.sandbox_of`` (sandbox tenant clone lineage)
    * ``MigrationIdMapping`` (legacy → canonical audit table)
    * ``MigrationAsset`` (binary asset pipeline rows)
    * ``MigrationProgressEvent`` (SSE-streamed event log)
    * ``MigrationConflict`` (operator-reviewable upsert conflicts)
"""

from __future__ import annotations

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('migration_cloud', '0002_alter_migrationbundle_intake_method'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('schools', '0048_force_rls_on_all_enabled_tables'),
    ]

    operations = [
        migrations.AddField(
            model_name='migrationbundle',
            name='expected_totals',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text=(
                    "Operator-supplied financial control totals enforced before APPLIED. "
                    "Shape: {'finance.invoice_total_amount': '125000.00', 'students.count': 1240}. "
                    "Mismatch aborts the apply with a FinancialMismatchError."
                ),
            ),
        ),
        migrations.AddField(
            model_name='migrationbundle',
            name='progress_snapshot',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text=(
                    "Live per-stage progress for the DAG view: "
                    "{'stages': [{'name': 'INGESTING', 'pct': 100, 'rows': 1240, 'started': ..., "
                    "'finished': ...}, ...], 'updated_at': iso}."
                ),
            ),
        ),
        migrations.AddField(
            model_name='migrationbundle',
            name='diff_mode',
            field=models.CharField(
                choices=[
                    ('full', 'Full re-ingest (default)'),
                    ('since', 'Diff mode: only rows changed since last successful bundle'),
                ],
                default='full',
                help_text="Diff-mode re-ingest: 'since' uses last_successful_apply_at to skip unchanged rows.",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name='migrationbundle',
            name='diff_since',
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text="When diff_mode='since', source rows older than this timestamp are skipped.",
            ),
        ),
        migrations.AddField(
            model_name='migrationbundle',
            name='apply_atomic',
            field=models.BooleanField(
                default=False,
                help_text=(
                    "All-or-nothing apply opt-in. When True, the orchestrator wraps the whole apply "
                    "in a single transaction so any quarantine-bearing artifact rolls back the bundle."
                ),
            ),
        ),
        migrations.AddField(
            model_name='migrationbundle',
            name='parity_drift_rollback_pct',
            field=models.FloatField(
                default=0.0,
                help_text=(
                    "Auto-rollback threshold. When > 0, reconciliation that yields overall parity below "
                    "this percentage triggers an automatic rollback of the apply's MigrationRun rows."
                ),
            ),
        ),
        migrations.AddField(
            model_name='migrationbundle',
            name='sandbox_of',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='sandbox_clones',
                to='migration_cloud.migrationbundle',
                help_text='When set, this bundle is a sandbox copy of another bundle, isolated under a throwaway schema.',
            ),
        ),
        migrations.CreateModel(
            name='MigrationIdMapping',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('legacy_namespace', models.CharField(db_index=True, max_length=64)),
                ('legacy_id', models.CharField(db_index=True, max_length=128)),
                ('canonical_model', models.CharField(db_index=True, max_length=128)),
                ('canonical_pk', models.CharField(db_index=True, max_length=64)),
                ('domain', models.CharField(blank=True, db_index=True, max_length=32)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('bundle', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='id_mappings',
                    to='migration_cloud.migrationbundle',
                )),
                ('school', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='migration_id_mappings',
                    to='schools.school',
                )),
            ],
            options={
                'verbose_name': 'Migration ID mapping',
                'verbose_name_plural': 'Migration ID mappings',
                'indexes': [
                    models.Index(fields=['legacy_namespace', 'legacy_id'], name='mc_idmap_ns_lid_idx'),
                    models.Index(fields=['canonical_model', 'canonical_pk'], name='mc_idmap_model_pk_idx'),
                    models.Index(fields=['bundle', 'domain'], name='mc_idmap_bundle_dom_idx'),
                ],
                'constraints': [
                    models.UniqueConstraint(
                        fields=['legacy_namespace', 'legacy_id', 'canonical_model', 'school'],
                        name='uniq_id_mapping_per_school_namespace',
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name='MigrationAsset',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('entity_kind', models.CharField(db_index=True, max_length=64)),
                ('legacy_id', models.CharField(db_index=True, max_length=128)),
                ('asset_kind', models.CharField(db_index=True, max_length=32)),
                ('source_uri', models.TextField(blank=True)),
                ('stored_path', models.TextField(blank=True)),
                ('sha256', models.CharField(blank=True, db_index=True, max_length=64)),
                ('byte_size', models.BigIntegerField(default=0)),
                ('mime_type', models.CharField(blank=True, max_length=128)),
                ('status', models.CharField(
                    choices=[('PENDING', 'Pending'), ('FETCHING', 'Fetching from source'),
                             ('STORED', 'Stored'), ('FAILED', 'Failed')],
                    db_index=True, default='PENDING', max_length=16,
                )),
                ('error', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('bundle', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='assets',
                    to='migration_cloud.migrationbundle',
                )),
                ('school', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='migration_assets',
                    to='schools.school',
                )),
            ],
            options={
                'verbose_name': 'Migration asset',
                'verbose_name_plural': 'Migration assets',
                'ordering': ['-created_at'],
                'indexes': [
                    models.Index(fields=['bundle', 'status'], name='mc_asset_bundle_status_idx'),
                    models.Index(fields=['entity_kind', 'legacy_id'], name='mc_asset_entity_lid_idx'),
                    models.Index(fields=['sha256'], name='mc_asset_sha256_idx'),
                ],
            },
        ),
        migrations.CreateModel(
            name='MigrationProgressEvent',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(
                    choices=[
                        ('stage_started', 'Stage started'),
                        ('stage_finished', 'Stage finished'),
                        ('artifact_progress', 'Artifact progress'),
                        ('rollback', 'Rollback'),
                        ('warning', 'Warning'),
                        ('info', 'Info'),
                    ],
                    db_index=True, max_length=32,
                )),
                ('stage', models.CharField(blank=True, db_index=True, max_length=32)),
                ('message', models.TextField(blank=True)),
                ('detail', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('bundle', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='progress_events',
                    to='migration_cloud.migrationbundle',
                )),
            ],
            options={
                'verbose_name': 'Migration progress event',
                'verbose_name_plural': 'Migration progress events',
                'ordering': ['created_at'],
                'indexes': [
                    models.Index(fields=['bundle', 'created_at'], name='mc_evt_bundle_at_idx'),
                    models.Index(fields=['bundle', 'stage'], name='mc_evt_bundle_stage_idx'),
                ],
            },
        ),
        migrations.CreateModel(
            name='MigrationConflict',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('domain', models.CharField(db_index=True, max_length=32)),
                ('canonical_model', models.CharField(db_index=True, max_length=128)),
                ('canonical_pk', models.CharField(db_index=True, max_length=64)),
                ('legacy_id', models.CharField(blank=True, db_index=True, max_length=128)),
                ('existing_values', models.JSONField(blank=True, default=dict)),
                ('incoming_values', models.JSONField(blank=True, default=dict)),
                ('changed_fields', models.JSONField(blank=True, default=list)),
                ('resolution', models.CharField(
                    choices=[
                        ('PENDING', 'Pending operator review'),
                        ('OVERWRITE', 'Overwrite existing'),
                        ('PRESERVE', 'Preserve existing (skip)'),
                        ('MERGE', 'Merge fields'),
                    ],
                    db_index=True, default='PENDING', max_length=16,
                )),
                ('resolved_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('bundle', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='conflicts',
                    to='migration_cloud.migrationbundle',
                )),
                ('resolved_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='resolved_migration_conflicts',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Migration conflict',
                'verbose_name_plural': 'Migration conflicts',
                'ordering': ['-created_at'],
                'indexes': [
                    models.Index(fields=['bundle', 'resolution'], name='mc_conf_bundle_res_idx'),
                    models.Index(fields=['canonical_model', 'canonical_pk'], name='mc_conf_model_pk_idx'),
                ],
            },
        ),
    ]
