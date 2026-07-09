"""Seed platform-baseline PDP parity allow-rules for the three IAM surfaces
promoted from advisory to ENFORCE (2026-07-09): the tenant RBAC dashboard,
the tenant identity hub, and the regulator time-boxed grant page.

Each rule allows exactly the population the surface's own canonical RBAC gate
admits: ``apps/policies/enforcement.py`` computes that gate's verdict into the
PDP subject as ``subject.rbac_allowed`` (parity probe), and these rules
condition on it. Flipping ``POLICY_PDP_ENFORCEMENT_MODE`` to ``enforce``
therefore preserves access exactly, while tenant/operator deny rules (default
priority 100, evaluated ahead of these priority-500 baselines) now actually
bind — and deactivating a baseline rule fail-closes its surface (platform
superusers keep god-mode).
"""

from django.db import migrations

# Deliberately BELOW tenant-authored rules (model default priority 100; lower
# number wins): a tenant deny rule always outranks the platform baseline.
_BASELINE_PRIORITY = 500  # magic-number-allow: baseline-parity-rule-priority-behind-tenant-default-100

_PARITY_CONDITION = [{"attr": "subject.rbac_allowed", "op": "eq", "value": True}]

_RULES = (
    {
        "code": "iam-baseline-access-role-manage",
        "name": "IAM baseline: RBAC dashboard parity allow",
        "action_match": {"actions": ["manage"]},
        "resource_match": {"entity": "access_role"},
        "description": (
            "Platform baseline for the ENFORCED tenant RBAC dashboard: allows exactly "
            "the population the surface's canonical RBAC union admits "
            "(subject.rbac_allowed, computed by apps/policies/enforcement.py from the "
            "surface's parity probe). Deactivating this rule fail-closes the surface; "
            "tenant deny rules with a lower priority number override it."
        ),
    },
    {
        "code": "iam-baseline-tenant-identity-manage",
        "name": "IAM baseline: tenant identity hub parity allow",
        "action_match": {"actions": ["manage"]},
        "resource_match": {"entity": "tenant_identity"},
        "description": (
            "Platform baseline for the ENFORCED tenant identity hub (staff roster / "
            "offboard): allows exactly the population _can_manage_tenant_identity "
            "admits via the subject.rbac_allowed parity probe. Deactivating this rule "
            "fail-closes the surface; tenant deny rules override it."
        ),
    },
    {
        "code": "iam-baseline-regulatory-access-grant",
        "name": "IAM baseline: regulator grant parity allow",
        "action_match": {"actions": ["grant"]},
        "resource_match": {"entity": "regulatory_access"},
        "description": (
            "Platform baseline for the ENFORCED regulator time-boxed access grant "
            "page: allows exactly the population _can_manage_tenant_identity admits "
            "via the subject.rbac_allowed parity probe. Deactivating this rule "
            "fail-closes the surface; tenant deny rules override it."
        ),
    },
)


def _seed(apps, schema_editor):
    PolicyRule = apps.get_model("policies", "PolicyRule")
    for row in _RULES:
        PolicyRule.objects.get_or_create(
            school=None,
            code=row["code"],
            defaults={
                "name": row["name"],
                "description": row["description"],
                "effect": "allow",
                "subject_match": {},
                "action_match": row["action_match"],
                "resource_match": row["resource_match"],
                "conditions": _PARITY_CONDITION,
                "priority": _BASELINE_PRIORITY,
                "is_active": True,
            },
        )


def _unseed(apps, schema_editor):
    PolicyRule = apps.get_model("policies", "PolicyRule")
    PolicyRule.objects.filter(
        school__isnull=True, code__in=[row["code"] for row in _RULES]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("policies", "0009_rls_policy_default_deny"),
    ]

    operations = [
        migrations.RunPython(_seed, _unseed),
    ]
