# Phase B: move the three remaining operator-config JSON blobs off SiteSettings
# (cockpit_payload / email_delivery / theme_personality) into
# RuntimeDefaults.payload, restoring the slim SiteSettings contract
# (id / maintenance_mode / updated_at) enforced by
# scripts/verify_phase_b_execution.py. Reads keep working via the SiteSettings
# __getattr__ payload shim; writes go through SiteSettings.set_<blob>() accessors.
#
# Mirrors the established Phase B Batch 0 pattern (0162): snapshot the JSON-safe
# values into RuntimeDefaults.payload, then RemoveField (which updates model
# state AND drops the physical column). siteconfig is a SHARED app, so this runs
# only in the public schema; a fresh DB with no SiteSettings row early-returns.

import json

from django.core.serializers.json import DjangoJSONEncoder
from django.db import migrations

_BLOB_FIELDS = ("cockpit_payload", "email_delivery", "theme_personality")


def _snapshot_config_blobs_into_runtime_defaults(apps, schema_editor):
    """Copy the 3 blob columns into RuntimeDefaults.payload before they are dropped."""
    SiteSettings = apps.get_model("siteconfig", "SiteSettings")
    RuntimeDefaults = apps.get_model("platform_runtime", "RuntimeDefaults")
    site = SiteSettings.objects.order_by("pk").first()
    if site is None:
        # Fresh DB / fresh provisioning — nothing to migrate.
        return
    payload: dict = {}
    for name in _BLOB_FIELDS:
        try:
            value = getattr(site, name, None)
        except Exception:
            continue
        if value in (None, {}, ""):
            continue
        try:
            payload[name] = json.loads(json.dumps(value, cls=DjangoJSONEncoder))
        except TypeError:
            continue
    if not payload:
        return
    obj, _created = RuntimeDefaults.objects.get_or_create(
        pk=1, defaults={"payload": payload}
    )
    merged = dict(obj.payload or {})
    merged.update(payload)
    obj.payload = merged
    obj.save(update_fields=["payload", "updated_at"])


def _noop_reverse(*_args, **_kwargs):
    return


class Migration(migrations.Migration):

    dependencies = [
        ("siteconfig", "0193_customnuance_report_card_avg_hook"),
        ("platform_runtime", "0006_platformeventlog"),
    ]

    operations = [
        migrations.RunPython(
            _snapshot_config_blobs_into_runtime_defaults,
            _noop_reverse,
        ),
        migrations.RemoveField(
            model_name="sitesettings",
            name="cockpit_payload",
        ),
        migrations.RemoveField(
            model_name="sitesettings",
            name="email_delivery",
        ),
        migrations.RemoveField(
            model_name="sitesettings",
            name="theme_personality",
        ),
    ]
