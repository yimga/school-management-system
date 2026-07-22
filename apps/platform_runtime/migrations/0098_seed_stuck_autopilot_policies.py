"""Seed autopilot policies for every stuck-default executable workflow kind.

0086 only enabled ``requeue_provision`` for ``tenant_school_provision``. The
Flight Deck UI claims self-heal for every ``STUCK_DEFAULT_FIX_BY_WORKFLOW`` row;
without matching ``WorkflowAutopilotPolicy`` rows, unattended heal is theater.
"""

from django.db import migrations

# Keep in sync with workflow_fix_handlers.STUCK_DEFAULT_FIX_BY_WORKFLOW.
STUCK_DEFAULT_FIX_BY_WORKFLOW = {
    "tenant_school_provision": "requeue_provision",
    "tenant_school_create": "requeue_provision",
    "migration_bundle_apply": "retry_failed_step",
    "migration_bundle_advance": "retry_failed_step",
    "migration_bundle_fetch_assets": "retry_failed_step",
    "marketplace_webhook_deliver_due": "replay_webhook",
    "orchestration_process_due": "retry_failed_step",
    "evals_bulk_grades": "retry_failed_step",
    "finance_auto_generate_fee_invoices": "retry_failed_step",
    "finance_auto_copy_fee_plans": "retry_failed_step",
    "tenant_school_purge": "retry_failed_step",
    "tenant_school_offboard_purge": "retry_failed_step",
}


def seed_stuck_autopilot_policies(apps, schema_editor):
    Policy = apps.get_model("platform_runtime", "WorkflowAutopilotPolicy")
    for workflow_key, kind in STUCK_DEFAULT_FIX_BY_WORKFLOW.items():
        pol, created = Policy.objects.get_or_create(
            workflow_key=workflow_key,
            tenant_schema="",
            defaults={"allowed_auto_fix_kinds": [kind], "enabled": True},
        )
        if created:
            continue
        kinds = list(pol.allowed_auto_fix_kinds or [])
        changed = False
        if kind not in kinds:
            kinds.append(kind)
            pol.allowed_auto_fix_kinds = kinds
            changed = True
        if not pol.enabled:
            pol.enabled = True
            changed = True
        if changed:
            pol.save(
                update_fields=["allowed_auto_fix_kinds", "enabled", "updated_at"]
            )


def unseed_stuck_autopilot_policies(apps, schema_editor):
    Policy = apps.get_model("platform_runtime", "WorkflowAutopilotPolicy")
    # Leave tenant_school_provision — owned by 0086 reverse.
    keys = [
        k
        for k in STUCK_DEFAULT_FIX_BY_WORKFLOW
        if k != "tenant_school_provision"
    ]
    Policy.objects.filter(workflow_key__in=keys, tenant_schema="").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("platform_runtime", "0097_offlineaction_migration_cloud_upload"),
    ]

    operations = [
        migrations.RunPython(
            seed_stuck_autopilot_policies, unseed_stuck_autopilot_policies
        ),
    ]
