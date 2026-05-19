"""v3.35.0 Agent 3 — MAA v2.0 flip pre-flight tooling.

Adds two append-only platform-wide audit models that gate the MAA v2.0
promotion path:

  1. ``MigrationCloudCounselAttestation`` — operator-recorded
     attestations that counsel signoff (or other compliance gate) has
     landed. Append-only; one row per attestation event.
  2. ``MigrationCloudMAACampaignNotification`` — idempotency record for
     the re-sign campaign mgmt command. Tracks one row per
     (agreement, recipient, campaign_version) so re-running the
     command never double-sends.

Both are cross-tenant by design — the MAA promotion procedure is a
platform-wide operation. ``# tenant-isolation-allow:`` markers in
``models.py`` carry 5-part-hyphenated reasons:

  * ``platform-wide-counsel-attestation-audit-log``
  * ``cross-tenant-maa-campaign-tracking``

Operations are pure ``CreateModel`` — no live model imports, no
RunPython data migration (the v1.0 historic rows we'll later mail
remain untouched). ``scan_migration_model_imports`` clean.

NEVER logs: MAA body text, signature_text content, recipient email
bodies. Only counts + bool flags + identifiers.
"""
from __future__ import annotations

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        # v3.35.0 — chain after the v3.34.0 leaf (0015). Keeps the
        # migration leaf single + applies cleanly atop the per-tenant
        # keypair work.
        ("migration_cloud", "0015_companion_keypair_per_tenant"),
        # Needs the User model PK column settled at apply time
        # (operator FK target).
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="MigrationCloudCounselAttestation",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "attested_at",
                    models.DateTimeField(auto_now_add=True, db_index=True),
                ),
                (
                    "attestation_type",
                    models.CharField(
                        db_index=True,
                        help_text=(
                            "Stable identifier for the attestation kind, e.g. "
                            "'maa_v2_counsel_signoff_received'. Keep short, "
                            "machine-readable."
                        ),
                        max_length=64,
                    ),
                ),
                (
                    "attestation_text",
                    models.TextField(
                        help_text=(
                            "Operator-supplied narrative describing the "
                            "attestation."
                        ),
                    ),
                ),
                (
                    "related_artifact_path",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text=(
                            "Optional repo-relative path of the supporting "
                            "artifact (e.g. 'docs/legal/maa_v2_signoff.pdf')."
                        ),
                        max_length=512,
                    ),
                ),
                (
                    "operator",
                    models.ForeignKey(
                        help_text=(
                            "Staff user who recorded this attestation. Must "
                            "be a member of the legal-officers group at "
                            "attestation time."
                        ),
                        on_delete=models.deletion.PROTECT,
                        related_name="migration_cloud_counsel_attestations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Migration Cloud counsel attestation",
                "verbose_name_plural": "Migration Cloud counsel attestations",
                "ordering": ["-attested_at"],
            },
        ),
        migrations.AddIndex(
            model_name="migrationcloudcounselattestation",
            index=models.Index(
                fields=["attestation_type", "-attested_at"],
                name="migration_c_attesta_3c0a44_idx",
            ),
        ),
        migrations.CreateModel(
            name="MigrationCloudMAACampaignNotification",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "recipient_email",
                    models.EmailField(
                        help_text=(
                            "Email address that received (or was queued to "
                            "receive) the campaign email."
                        ),
                        max_length=254,
                    ),
                ),
                (
                    "sent_at",
                    models.DateTimeField(auto_now_add=True, db_index=True),
                ),
                (
                    "campaign_version",
                    models.CharField(
                        db_index=True,
                        help_text=(
                            "Campaign identifier, e.g. 'maa_v2_resign_2026Q3'."
                        ),
                        max_length=32,
                    ),
                ),
                (
                    "dispatch_mode",
                    models.CharField(
                        db_index=True,
                        default="dry_run",
                        help_text=(
                            "Either 'dry_run' or 'queued'. 'queued' rows are "
                            "the only ones operators expect a real email "
                            "send for."
                        ),
                        max_length=16,
                    ),
                ),
                (
                    "agreement",
                    models.ForeignKey(
                        help_text=(
                            "The v1.0-era MAA row that triggered the "
                            "notification."
                        ),
                        on_delete=models.deletion.CASCADE,
                        related_name="campaign_notifications",
                        to="migration_cloud.migrationauthorizationagreement",
                    ),
                ),
            ],
            options={
                "verbose_name": "Migration Cloud MAA campaign notification",
                "verbose_name_plural": (
                    "Migration Cloud MAA campaign notifications"
                ),
                "ordering": ["-sent_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="migrationcloudmaacampaignnotification",
            constraint=models.UniqueConstraint(
                fields=("agreement", "recipient_email", "campaign_version"),
                name="uniq_maa_campaign_per_agreement_recipient",
            ),
        ),
        migrations.AddIndex(
            model_name="migrationcloudmaacampaignnotification",
            index=models.Index(
                fields=["campaign_version", "-sent_at"],
                name="migration_c_campaig_8d5b22_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="migrationcloudmaacampaignnotification",
            index=models.Index(
                fields=["dispatch_mode", "-sent_at"],
                name="migration_c_dispatc_e7f199_idx",
            ),
        ),
    ]
