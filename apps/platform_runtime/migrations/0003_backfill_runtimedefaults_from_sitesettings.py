from __future__ import annotations

import json

from django.core.serializers.json import DjangoJSONEncoder
from django.db import migrations


def _build_payload(site) -> dict:
    payload = {}
    for field in site._meta.concrete_fields:
        if getattr(field, "primary_key", False):
            continue
        if field.get_internal_type() in {"FileField", "ImageField"}:
            continue
        attr_name = getattr(field, "attname", field.name)
        value = getattr(site, attr_name, None)
        try:
            payload[attr_name] = json.loads(json.dumps(value, cls=DjangoJSONEncoder))
        except TypeError:
            continue
    return payload


def backfill_runtime_defaults(apps, schema_editor):
    SiteSettings = apps.get_model("siteconfig", "SiteSettings")
    RuntimeDefaults = apps.get_model("platform_runtime", "RuntimeDefaults")

    site = SiteSettings.objects.order_by("pk").first()
    if site is None:
        return

    payload = _build_payload(site)
    obj, _created = RuntimeDefaults.objects.get_or_create(
        pk=1, defaults={"payload": payload}
    )
    if obj.payload != payload:
        obj.payload = payload
        obj.save(update_fields=["payload", "updated_at"])


def noop(_apps, _schema_editor):
    return


class Migration(migrations.Migration):
    dependencies = [
        ("siteconfig", "0152_aigatewaymetric_review_fields"),
        ("platform_runtime", "0002_aiactionauditlog"),
    ]

    operations = [
        migrations.RunPython(backfill_runtime_defaults, noop),
    ]
