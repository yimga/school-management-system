# Generated manually — public brand colors as first-class columns (shrink payload).

from django.db import migrations, models


def _backfill_public_brand_from_payload(apps, schema_editor):
    RuntimeDefaults = apps.get_model("platform_runtime", "RuntimeDefaults")
    obj = RuntimeDefaults.objects.filter(pk=1).first()
    if not obj:
        return
    pl = dict(obj.payload or {})
    update_fields: list[str] = ["payload"]
    for fname in ("public_brand_primary_color", "public_brand_accent_color"):
        if fname not in pl:
            continue
        raw = pl.pop(fname)
        s = (str(raw).strip()[:32] if raw is not None else "") or None
        setattr(obj, fname, s)
        update_fields.append(fname)
    obj.payload = pl
    obj.save(update_fields=update_fields)


def _noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("platform_runtime", "0009_runtimedefaults_preview_integration_columns"),
    ]

    operations = [
        migrations.AddField(
            model_name="runtimedefaults",
            name="public_brand_accent_color",
            field=models.CharField(
                blank=True,
                help_text="CTAs and links on public shells (e.g. #f59e0b).",
                max_length=32,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="public_brand_primary_color",
            field=models.CharField(
                blank=True,
                help_text="Marketing / control-plane navbar + hero (e.g. #0f172a).",
                max_length=32,
                null=True,
            ),
        ),
        migrations.RunPython(_backfill_public_brand_from_payload, _noop_reverse),
    ]
