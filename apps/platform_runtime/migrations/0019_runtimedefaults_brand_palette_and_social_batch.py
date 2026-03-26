# Generated manually — brand palette/social defaults batch (5 fields) as first-class columns.

import json

from django.core.serializers.json import DjangoJSONEncoder
from django.db import migrations, models


def _json_safe(raw):
    try:
        if raw is None:
            return None
        return json.loads(json.dumps(raw, cls=DjangoJSONEncoder))
    except TypeError:
        return None


def _backfill_brand_palette_social_from_payload(apps, schema_editor):
    RuntimeDefaults = apps.get_model("platform_runtime", "RuntimeDefaults")
    obj = RuntimeDefaults.objects.filter(pk=1).first()
    if not obj:
        return
    pl = dict(obj.payload or {})
    update_fields: list[str] = ["payload"]

    string_specs = (
        ("site_name", 255),
        ("primary_color", 32),
        ("success_color", 32),
        ("warning_color", 32),
    )
    for fname, max_len in string_specs:
        if fname not in pl:
            continue
        raw = pl.pop(fname)
        s = (str(raw).strip()[:max_len] if raw is not None else "") or None
        setattr(obj, fname, s)
        update_fields.append(fname)

    links_key = "social_links"
    if links_key in pl:
        raw = pl.pop(links_key)
        obj.social_links = _json_safe(raw)
        update_fields.append(links_key)

    obj.payload = pl
    obj.save(update_fields=update_fields)


def _noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("platform_runtime", "0018_runtimedefaults_portal_feed_batch"),
    ]

    operations = [
        migrations.AddField(
            model_name="runtimedefaults",
            name="primary_color",
            field=models.CharField(
                blank=True,
                help_text="Default primary brand color for runtime-resolved surfaces.",
                max_length=32,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="site_name",
            field=models.CharField(
                blank=True,
                help_text="Default public site/school display name.",
                max_length=255,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="social_links",
            field=models.JSONField(
                blank=True,
                help_text="Default public social links collection.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="success_color",
            field=models.CharField(
                blank=True,
                help_text="Default success color token for runtime-resolved surfaces.",
                max_length=32,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="warning_color",
            field=models.CharField(
                blank=True,
                help_text="Default warning color token for runtime-resolved surfaces.",
                max_length=32,
                null=True,
            ),
        ),
        migrations.RunPython(_backfill_brand_palette_social_from_payload, _noop_reverse),
    ]
