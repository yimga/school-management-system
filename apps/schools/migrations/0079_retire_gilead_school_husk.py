"""Retire the single-tenant-era ``gilead-school`` seed so it stops living as an
active-but-unprovisioned husk (provisioning audit 2026-07-19, G5).

``schools/0012_seed_default_gilead_school`` get_or_creates ``gilead-school``
is_active=True on every fresh database. It has no tenant schema seed and no owner,
so it reads "ready" to every healer and 500s on its subdomain -- the husk class
the audit centres on. We cannot edit an applied migration, so this forward
migration neutralises the row: if it is still an UNPROVISIONED husk (active, no
Phase-A completion marker) it is flipped inactive -- the normal pre-provision
state, invisible to readiness reporting and to the reconcile/watchdog "settled"
checks. A gilead-school that was genuinely provisioned later (``phase_a_complete``
set) is left untouched.

Deactivate, not delete: the row may have FK'd data and a delete could cascade real
rows or hit a PROTECT (the audit's DELETE-safety note). ``is_active=False`` is the
minimal, cascade-free, reversible retirement.

No swallowed DB op: a plain filtered UPDATE that fails aborts the deploy loudly
rather than poisoning the transaction (the 0078 / portal-0006 class this repo has
paid for; enforced by scripts/scan_migration_transaction_side_effects.py).

The Postgres-only Client / Domain / empty schema that
``customers/0003_ensure_gilead_tenant_domain`` creates for this slug are left in
place: an inactive School is not served, dropping a schema risks data loss, and
none of it exists on the non-Postgres test backend. Retiring the School row is the
portable, testable core of the fix.
"""
from django.db import migrations

LEGACY_HUSK_SLUG = "gilead-school"


def retire_legacy_husk(apps, schema_editor):
    School = apps.get_model("schools", "School")
    for school in School.objects.filter(
        slug=LEGACY_HUSK_SLUG, is_active=True
    ).iterator():
        settings_blob = school.settings if isinstance(school.settings, dict) else {}
        prov = settings_blob.get("provisioning")
        phase_a_complete = (
            bool(prov.get("phase_a_complete")) if isinstance(prov, dict) else False
        )
        if phase_a_complete:
            # Genuinely provisioned -> a real tenant, not a husk. Leave it.
            continue
        # Re-assert is_active=True in the filter so a concurrent activation between
        # the read and the write does not get clobbered.
        School.objects.filter(pk=school.pk, is_active=True).update(is_active=False)


def noop_reverse(apps, schema_editor):
    # Reactivating a retired husk on reverse would resurrect the exact problem.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("schools", "0078_dispatch_gilead_tech_setup_email"),
    ]

    operations = [
        migrations.RunPython(retire_legacy_husk, noop_reverse),
    ]
