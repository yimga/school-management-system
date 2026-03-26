# Generated manually — platform tagline + school code as first-class columns (shrink payload).

from django.db import migrations, models


def _backfill_tagline_school_code_from_payload(apps, schema_editor):
    RuntimeDefaults = apps.get_model("platform_runtime", "RuntimeDefaults")
    obj = RuntimeDefaults.objects.filter(pk=1).first()
    if not obj:
        return
    pl = dict(obj.payload or {})
    update_fields: list[str] = ["payload"]
    if "tagline" in pl:
        raw = pl.pop("tagline")
        s = (str(raw).strip()[:512] if raw is not None else "") or None
        obj.tagline = s
        update_fields.append("tagline")
    if "school_code" in pl:
        raw = pl.pop("school_code")
        s = (str(raw).strip()[:32] if raw is not None else "") or None
        obj.school_code = s
        update_fields.append("school_code")
    obj.payload = pl
    obj.save(update_fields=update_fields)


def _noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("platform_runtime", "0011_runtimedefaults_meta_description_branded_domain"),
    ]

    operations = [
        migrations.AddField(
            model_name="runtimedefaults",
            name="school_code",
            field=models.CharField(
                blank=True,
                help_text="Short institution code (e.g. stock ticker style) for labels and integrations.",
                max_length=32,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="tagline",
            field=models.CharField(
                blank=True,
                help_text="Public marketing / platform tagline (short phrase).",
                max_length=512,
                null=True,
            ),
        ),
        migrations.RunPython(_backfill_tagline_school_code_from_payload, _noop_reverse),
    ]
