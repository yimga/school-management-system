"""Enable safe self-healing for new-school provisioning.

Creates the platform-wide ``WorkflowAutopilotPolicy`` row that lets the stuck-
workflow sweep auto-apply the ``requeue_provision`` fix for
``tenant_school_provision`` runs. The re-drive is idempotent and now RESUMES
Phase B (migrates the tenant schema to HEAD + completes seeding), so a stalled
or failed provision self-repairs without an operator. Still bounded by the
per-school circuit breaker (3 applies/hour) in the autopilot, and every apply is
recorded in ``WorkflowAutopilotApplyLog``.

Idempotent + reversible: re-running only ensures the row exists/enabled; the
reverse removes the platform-wide row (per-tenant overrides, if any, are left
untouched).
"""

from django.db import migrations

WORKFLOW_KEY = "tenant_school_provision"
ALLOWED_KIND = "requeue_provision"


def enable_provisioning_autopilot(apps, schema_editor):
    Policy = apps.get_model("platform_runtime", "WorkflowAutopilotPolicy")
    pol, created = Policy.objects.get_or_create(
        workflow_key=WORKFLOW_KEY,
        tenant_schema="",
        defaults={"allowed_auto_fix_kinds": [ALLOWED_KIND], "enabled": True},
    )
    if created:
        return
    kinds = list(pol.allowed_auto_fix_kinds or [])
    changed = False
    if ALLOWED_KIND not in kinds:
        kinds.append(ALLOWED_KIND)
        pol.allowed_auto_fix_kinds = kinds
        changed = True
    if not pol.enabled:
        pol.enabled = True
        changed = True
    if changed:
        pol.save(update_fields=["allowed_auto_fix_kinds", "enabled", "updated_at"])


def disable_provisioning_autopilot(apps, schema_editor):
    Policy = apps.get_model("platform_runtime", "WorkflowAutopilotPolicy")
    Policy.objects.filter(workflow_key=WORKFLOW_KEY, tenant_schema="").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("platform_runtime", "0085_health_remediation_log"),
    ]

    operations = [
        migrations.RunPython(
            enable_provisioning_autopilot, disable_provisioning_autopilot
        ),
    ]
