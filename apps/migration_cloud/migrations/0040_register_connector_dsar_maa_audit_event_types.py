# Generated manually for audit 2026-07-24 — register connector.* hash-chain
# mirror categories (E-3) + DSAR runbook + MAA v2.0 promotion event types
# (F-Q3) so they stop masquerading as / being swallowed by other types.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("migration_cloud", "0039_bundle_lifecycle_audit_event_types"),
    ]

    operations = [
        migrations.AlterField(
            model_name="migrationcloudauditevent",
            name="event_type",
            field=models.CharField(
                choices=[
                    ("companion.upload", "Companion upload accepted"),
                    ("maa.sign", "MAA signed"),
                    (
                        "maa.sign_attempt_draft",
                        "Attempt to sign a DRAFT MAA refused",
                    ),
                    ("key.rotate", "Companion server-keypair rotated"),
                    (
                        "webhook.subscription.created",
                        "Webhook subscription created",
                    ),
                    (
                        "webhook.subscription.deleted",
                        "Webhook subscription deleted (deactivated)",
                    ),
                    (
                        "webhook.delivery.replay",
                        "Webhook delivery manually replayed",
                    ),
                    ("token.mint", "Scoped API token minted"),
                    ("token.revoke", "Scoped API token revoked"),
                    ("legacy_hash.decrypt", "Legacy SIS-hash field decrypted"),
                    (
                        "audit.retention_purge_applied",
                        "Audit retention purge applied (counsel-approved)",
                    ),
                    (
                        "migration.intake.state_advanced",
                        "Migration intake state advanced",
                    ),
                    (
                        "migration.guardian_consent.campaign_started",
                        "Guardian consent campaign started",
                    ),
                    (
                        "migration.guardian_consent.minted",
                        "Guardian consent token minted",
                    ),
                    (
                        "migration.guardian_consent.first_seen",
                        "Guardian opened the consent page for the first time",
                    ),
                    (
                        "migration.guardian_consent.consented",
                        "Guardian consented to migration",
                    ),
                    (
                        "migration.guardian_consent.declined",
                        "Guardian declined consent",
                    ),
                    (
                        "migration.guardian_consent.revoked",
                        "Guardian revoked previously-granted consent",
                    ),
                    (
                        "migration.guardian_consent.expired",
                        "Guardian consent token expired before decision",
                    ),
                    (
                        "migration.guardian_consent.resent",
                        "Guardian consent email resent",
                    ),
                    (
                        "audit.rate_limit_triggered",
                        "Audit event volume rate-limit triggered for a tenant",
                    ),
                    (
                        "migration.maa.v2_activated_by_operator",
                        "MAA v2.0 activated by operator (counsel signoff on file)",
                    ),
                    (
                        "migration.data_retention.purge_applied",
                        "Migration data retention purge applied (counsel-approved)",
                    ),
                    (
                        "lifecycle.offboarding.export",
                        "School offboarding data export generated",
                    ),
                    (
                        "lifecycle.offboarding.deactivated",
                        "School deactivated (offboarding)",
                    ),
                    (
                        "lifecycle.offboarding.purge_requested",
                        "School offboarding purge requested",
                    ),
                    (
                        "lifecycle.offboarding.purge_completed",
                        "School offboarding purge completed",
                    ),
                    (
                        "migration.bundle.advanced",
                        "Migration bundle advanced through profile/classify/map",
                    ),
                    (
                        "migration.bundle.applied",
                        "Migration bundle apply completed (live or dry-run)",
                    ),
                    (
                        "connector.connection",
                        "Connector source-connection lifecycle event",
                    ),
                    (
                        "connector.credential_access",
                        "Connector source credential accessed",
                    ),
                    ("connector.discovery", "Connector schema discovery run"),
                    ("connector.mapping", "Connector field mapping confirmed"),
                    ("connector.import", "Connector import run"),
                    ("connector.rollback", "Connector import rollback"),
                    (
                        "connector.event",
                        "Connector workflow event (uncategorized)",
                    ),
                    (
                        "migration.dsar.runbook_recorded",
                        "DSAR fulfillment runbook recorded",
                    ),
                    (
                        "maa.v2_promotion_applied",
                        "MAA v2.0 promotion applied by operator",
                    ),
                ],
                db_index=True,
                help_text="One of the registered audit event types.",
                max_length=64,
            ),
        ),
    ]
