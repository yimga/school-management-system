# Generated manually — company identity strings as first-class columns (shrink payload).

from django.db import migrations, models


def _backfill_company_identity_from_payload(apps, schema_editor):
    RuntimeDefaults = apps.get_model("platform_runtime", "RuntimeDefaults")
    obj = RuntimeDefaults.objects.filter(pk=1).first()
    if not obj:
        return
    pl = dict(obj.payload or {})
    update_fields: list[str] = ["payload"]
    for fname, max_len in (("company_name", 255), ("company_email", 255)):
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
        ("platform_runtime", "0012_runtimedefaults_tagline_school_code"),
    ]

    operations = [
        migrations.AddField(
            model_name="runtimedefaults",
            name="company_email",
            field=models.CharField(
                blank=True,
                help_text="Public contact email shown on branded surfaces.",
                max_length=255,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="company_name",
            field=models.CharField(
                blank=True,
                help_text="Public company/school display name for branded shells and comms.",
                max_length=255,
                null=True,
            ),
        ),
        migrations.RunPython(_backfill_company_identity_from_payload, _noop_reverse),
    ]
