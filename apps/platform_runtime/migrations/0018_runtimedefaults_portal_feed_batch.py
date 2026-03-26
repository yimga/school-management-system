# Generated manually — portal feed defaults batch (5 fields) as first-class columns.

import json

from django.core.serializers.json import DjangoJSONEncoder
from django.db import migrations, models


def _to_int_or_none(raw):
    if raw is None:
        return None
    try:
        val = int(raw)
    except (TypeError, ValueError):
        return None
    return val if val >= 0 else None


def _json_safe(raw):
    try:
        if raw is None:
            return None
        return json.loads(json.dumps(raw, cls=DjangoJSONEncoder))
    except TypeError:
        return None


def _backfill_portal_feed_from_payload(apps, schema_editor):
    RuntimeDefaults = apps.get_model("platform_runtime", "RuntimeDefaults")
    obj = RuntimeDefaults.objects.filter(pk=1).first()
    if not obj:
        return
    pl = dict(obj.payload or {})
    update_fields: list[str] = ["payload"]

    json_keys = (
        "portal_announcements",
        "portal_quick_actions",
        "portal_recent_grades",
        "portal_upcoming_assessments",
    )
    for key in json_keys:
        if key not in pl:
            continue
        raw = pl.pop(key)
        setattr(obj, key, _json_safe(raw))
        update_fields.append(key)

    limit_key = "top_students_default_limit"
    if limit_key in pl:
        raw = pl.pop(limit_key)
        obj.top_students_default_limit = _to_int_or_none(raw)
        update_fields.append(limit_key)

    obj.payload = pl
    obj.save(update_fields=update_fields)


def _noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("platform_runtime", "0017_runtimedefaults_brand_runtime_dashboard_batch"),
    ]

    operations = [
        migrations.AddField(
            model_name="runtimedefaults",
            name="portal_announcements",
            field=models.JSONField(
                blank=True,
                help_text="Default portal announcements cards list.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="portal_quick_actions",
            field=models.JSONField(
                blank=True,
                help_text="Default portal quick action items list.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="portal_recent_grades",
            field=models.JSONField(
                blank=True,
                help_text="Default portal recent grades cards list.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="portal_upcoming_assessments",
            field=models.JSONField(
                blank=True,
                help_text="Default portal upcoming assessments cards list.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="top_students_default_limit",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Default top-students list limit for runtime dashboards.",
                null=True,
            ),
        ),
        migrations.RunPython(_backfill_portal_feed_from_payload, _noop_reverse),
    ]
