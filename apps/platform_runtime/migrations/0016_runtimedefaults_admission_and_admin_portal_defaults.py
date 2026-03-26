# Generated manually — admission numbering + admin portal stats as first-class defaults.

import json

from django.core.serializers.json import DjangoJSONEncoder
from django.db import migrations, models


def _backfill_admission_and_admin_portal_from_payload(apps, schema_editor):
    RuntimeDefaults = apps.get_model("platform_runtime", "RuntimeDefaults")
    obj = RuntimeDefaults.objects.filter(pk=1).first()
    if not obj:
        return
    pl = dict(obj.payload or {})
    update_fields: list[str] = ["payload"]

    string_specs = (
        ("admission_number_mode", 32),
        ("admission_number_pattern", 1024),
        ("admission_number_strategy", 64),
        ("admission_number_template", 255),
    )
    for fname, max_len in string_specs:
        if fname not in pl:
            continue
        raw = pl.pop(fname)
        s = (str(raw).strip()[:max_len] if raw is not None else "") or None
        setattr(obj, fname, s)
        update_fields.append(fname)

    cfg_key = "admin_portal_stats_config"
    if cfg_key in pl:
        raw = pl.pop(cfg_key)
        cfg = None
        try:
            if raw is not None:
                cfg = json.loads(json.dumps(raw, cls=DjangoJSONEncoder))
        except TypeError:
            cfg = None
        obj.admin_portal_stats_config = cfg
        update_fields.append(cfg_key)

    obj.payload = pl
    obj.save(update_fields=update_fields)


def _noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("platform_runtime", "0015_runtimedefaults_registry_strings_batch"),
    ]

    operations = [
        migrations.AddField(
            model_name="runtimedefaults",
            name="admin_portal_stats_config",
            field=models.JSONField(
                blank=True,
                help_text="Default admin portal statistics configuration map.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="admission_number_mode",
            field=models.CharField(
                blank=True,
                help_text="Default admissions numbering mode (AUTO, MANUAL, AUTO_OR_MANUAL).",
                max_length=32,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="admission_number_pattern",
            field=models.CharField(
                blank=True,
                help_text="Default regex pattern for validating generated/admitted numbers.",
                max_length=1024,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="admission_number_strategy",
            field=models.CharField(
                blank=True,
                help_text="Default admissions numbering strategy key.",
                max_length=64,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="admission_number_template",
            field=models.CharField(
                blank=True,
                help_text="Default admissions numbering template with placeholders.",
                max_length=255,
                null=True,
            ),
        ),
        migrations.RunPython(
            _backfill_admission_and_admin_portal_from_payload,
            _noop_reverse,
        ),
    ]
