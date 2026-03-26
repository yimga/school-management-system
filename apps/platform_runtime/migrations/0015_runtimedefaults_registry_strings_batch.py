# Generated manually — additional global registry strings as first-class columns.

from django.db import migrations, models


def _backfill_registry_strings_from_payload(apps, schema_editor):
    RuntimeDefaults = apps.get_model("platform_runtime", "RuntimeDefaults")
    obj = RuntimeDefaults.objects.filter(pk=1).first()
    if not obj:
        return
    pl = dict(obj.payload or {})
    update_fields: list[str] = ["payload"]
    specs = (
        ("ministry", 128),
        ("default_region", 128),
        ("default_grading_scale", 128),
    )
    for fname, max_len in specs:
        if fname not in pl:
            continue
        raw = pl.pop(fname)
        s = (str(raw).strip()[:max_len] if raw is not None else "") or None
        setattr(obj, fname, s)
        update_fields.append(fname)
    obj.payload = pl
    obj.save(update_fields=update_fields)


def _noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("platform_runtime", "0014_runtimedefaults_identity_and_geo_strings"),
    ]

    operations = [
        migrations.AddField(
            model_name="runtimedefaults",
            name="default_grading_scale",
            field=models.CharField(
                blank=True,
                help_text="Platform default grading scale key for runtime/global registries.",
                max_length=128,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="default_region",
            field=models.CharField(
                blank=True,
                help_text="Platform default region profile key used by runtime/global registries.",
                max_length=128,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="ministry",
            field=models.CharField(
                blank=True,
                help_text="Platform default ministry label for public and registry-facing surfaces.",
                max_length=128,
                null=True,
            ),
        ),
        migrations.RunPython(_backfill_registry_strings_from_payload, _noop_reverse),
    ]
