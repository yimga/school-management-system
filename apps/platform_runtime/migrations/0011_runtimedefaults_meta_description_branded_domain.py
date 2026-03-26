# Generated manually — SEO / domain strings as first-class columns (shrink payload).

from django.db import migrations, models


def _backfill_meta_and_domain_from_payload(apps, schema_editor):
    RuntimeDefaults = apps.get_model("platform_runtime", "RuntimeDefaults")
    obj = RuntimeDefaults.objects.filter(pk=1).first()
    if not obj:
        return
    pl = dict(obj.payload or {})
    update_fields: list[str] = ["payload"]
    if "meta_description" in pl:
        raw = pl.pop("meta_description")
        s = (str(raw).strip()[:320] if raw is not None else "") or None
        obj.meta_description = s
        update_fields.append("meta_description")
    if "branded_domain" in pl:
        raw = pl.pop("branded_domain")
        s = (str(raw).strip()[:255] if raw is not None else "") or None
        obj.branded_domain = s
        update_fields.append("branded_domain")
    obj.payload = pl
    obj.save(update_fields=update_fields)


def _noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("platform_runtime", "0010_runtimedefaults_public_brand_colors"),
    ]

    operations = [
        migrations.AddField(
            model_name="runtimedefaults",
            name="branded_domain",
            field=models.CharField(
                blank=True,
                help_text="Canonical branded hostname for public links (no scheme).",
                max_length=255,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="meta_description",
            field=models.CharField(
                blank=True,
                help_text="Default meta description for public marketing shells.",
                max_length=320,
                null=True,
            ),
        ),
        migrations.RunPython(_backfill_meta_and_domain_from_payload, _noop_reverse),
    ]
