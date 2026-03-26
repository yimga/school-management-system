# Generated manually — larger identity/geo string batch as first-class columns.

from django.db import migrations, models


def _backfill_identity_geo_from_payload(apps, schema_editor):
    RuntimeDefaults = apps.get_model("platform_runtime", "RuntimeDefaults")
    obj = RuntimeDefaults.objects.filter(pk=1).first()
    if not obj:
        return
    pl = dict(obj.payload or {})
    update_fields: list[str] = ["payload"]
    specs = (
        ("company_phone", 64),
        ("company_address", 255),
        ("company_slug", 128),
        ("country", 64),
        ("region", 64),
        ("ministry_registration_code", 128),
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
        ("platform_runtime", "0013_runtimedefaults_company_identity_strings"),
    ]

    operations = [
        migrations.AddField(
            model_name="runtimedefaults",
            name="company_address",
            field=models.CharField(
                blank=True,
                help_text="Public mailing/address line used on branded pages and exports.",
                max_length=255,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="company_phone",
            field=models.CharField(
                blank=True,
                help_text="Public contact phone shown on branded surfaces.",
                max_length=64,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="company_slug",
            field=models.CharField(
                blank=True,
                help_text="Public short slug/identifier for links and headers.",
                max_length=128,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="country",
            field=models.CharField(
                blank=True,
                help_text="Platform default country code/name for public context.",
                max_length=64,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="ministry_registration_code",
            field=models.CharField(
                blank=True,
                help_text="Public ministry registration identifier when applicable.",
                max_length=128,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="region",
            field=models.CharField(
                blank=True,
                help_text="Platform default region label for public context.",
                max_length=64,
                null=True,
            ),
        ),
        migrations.RunPython(_backfill_identity_geo_from_payload, _noop_reverse),
    ]
