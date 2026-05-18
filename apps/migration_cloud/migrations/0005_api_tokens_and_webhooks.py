"""v3.29 — REST API completion: scoped tokens + webhook subscriptions/deliveries.

Adds three new models that back Agent 3's REST API completion wave:

  * ``MigrationCloudAPIToken``           — opaque scoped API tokens with
    per-token scope list, optional tenant binding, expiry, and revocation.
    We store only ``sha256(token)`` — plaintext is returned **once** at mint
    time and never persisted or logged.
  * ``MigrationCloudWebhookSubscription`` — partner-registered outbound
    webhook endpoint. We store the HMAC secret as plaintext bytes for now
    (operators receive it once at creation); a follow-up migration will
    wrap the column with ``django-cryptography`` once Agent 5's auth/crypto
    layer lands. Marker:
        # crypto-pending: agent-5-django-cryptography-encrypt-wrap-after-merge
  * ``MigrationCloudWebhookDelivery``    — append-only delivery log with
    exponential-backoff retry state (pending → delivered / failed →
    exhausted).

Pure ``CreateModel`` migration — `scan_migration_model_imports` clean
(no live-model imports, only ``models.*`` field types and string FKs).
"""

from __future__ import annotations

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('migration_cloud', '0004_rename_mc_asset_bundle_status_idx_migration_c_bundle__99d7cf_idx_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('schools', '0051_add_default_language'),
    ]

    operations = [
        migrations.CreateModel(
            name='MigrationCloudAPIToken',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('token_hash', models.CharField(
                    db_index=True,
                    help_text='sha256 hex digest of the opaque token; plaintext is returned ONCE at mint time and never stored.',
                    max_length=64,
                    unique=True,
                )),
                ('name', models.CharField(
                    help_text='Operator/partner-supplied label for token identification in the UI.',
                    max_length=128,
                )),
                ('scopes', models.JSONField(
                    blank=True,
                    default=list,
                    help_text="List of scope strings, e.g. ['bundles:read', 'bundles:write', 'templates:read'].",
                )),
                ('expires_at', models.DateTimeField(
                    blank=True,
                    db_index=True,
                    help_text='Optional expiry. Null means no time-based expiry (revoke explicitly).',
                    null=True,
                )),
                ('last_used_at', models.DateTimeField(
                    blank=True,
                    db_index=True,
                    help_text='Updated by the auth backend on each successful authenticate(). Best-effort.',
                    null=True,
                )),
                ('revoked_at', models.DateTimeField(
                    blank=True,
                    db_index=True,
                    help_text='Set by DELETE /tokens/<id>/ — once set the token is permanently rejected.',
                    null=True,
                )),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('tenant_scope', models.ForeignKey(
                    blank=True,
                    help_text='Optional tenant-binding. Null = all tenants the user can access.',
                    null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='migration_cloud_api_tokens',
                    to='schools.school',
                )),
                ('user', models.ForeignKey(
                    help_text='User this token authenticates as.',
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='migration_cloud_api_tokens',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Migration Cloud API token',
                'verbose_name_plural': 'Migration Cloud API tokens',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='MigrationCloudWebhookSubscription',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('url', models.URLField(
                    help_text='HTTPS endpoint the platform POSTs delivery payloads to.',
                    max_length=512,
                )),
                ('secret_hash', models.CharField(
                    blank=True,
                    help_text='sha256 hex digest of the HMAC secret (verification aid only).',
                    max_length=64,
                )),
                # crypto-pending: agent-5-django-cryptography-encrypt-wrap-after-merge
                ('secret_ciphertext', models.BinaryField(
                    blank=True,
                    help_text=(
                        'Raw HMAC secret material (used by webhook_dispatch to sign outbound deliveries). '
                        'TODO: wrap with django-cryptography encrypt() after Agent 5 lands the auth/crypto layer.'
                    ),
                    null=True,
                )),
                ('event_types', models.JSONField(
                    blank=True,
                    default=list,
                    help_text="List of event-type strings, e.g. ['bundle.advanced', 'bundle.completed', 'bundle.failed'].",
                )),
                ('active', models.BooleanField(db_index=True, default=True)),
                ('last_delivery_status', models.CharField(blank=True, max_length=32)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='migration_cloud_webhook_subscriptions',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('tenant', models.ForeignKey(
                    help_text='Owning tenant — webhook delivery is tenant-scoped end to end.',
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='migration_cloud_webhook_subscriptions',
                    to='schools.school',
                )),
            ],
            options={
                'verbose_name': 'Migration Cloud webhook subscription',
                'verbose_name_plural': 'Migration Cloud webhook subscriptions',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='MigrationCloudWebhookDelivery',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('event_type', models.CharField(db_index=True, max_length=64)),
                ('payload_json', models.JSONField(default=dict)),
                ('request_signature', models.CharField(
                    blank=True,
                    help_text='hex HMAC-SHA256(secret, payload_json_canonical_bytes).',
                    max_length=128,
                )),
                ('attempt_count', models.PositiveIntegerField(default=0)),
                ('next_retry_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('status', models.CharField(
                    choices=[
                        ('pending', 'Pending'),
                        ('delivered', 'Delivered'),
                        ('failed', 'Failed'),
                        ('exhausted', 'Exhausted'),
                    ],
                    db_index=True,
                    default='pending',
                    max_length=32,
                )),
                ('last_response_code', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('last_error', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('delivered_at', models.DateTimeField(blank=True, null=True)),
                ('subscription', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='deliveries',
                    to='migration_cloud.migrationcloudwebhooksubscription',
                )),
            ],
            options={
                'verbose_name': 'Migration Cloud webhook delivery',
                'verbose_name_plural': 'Migration Cloud webhook deliveries',
                'ordering': ['-created_at'],
            },
        ),
    ]
