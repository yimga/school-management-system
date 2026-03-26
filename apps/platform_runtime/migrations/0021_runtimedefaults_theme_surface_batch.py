# Generated manually — theme surface defaults batch (5 fields) as first-class columns.

from django.db import migrations, models


def _backfill_theme_surface_from_payload(apps, schema_editor):
    RuntimeDefaults = apps.get_model("platform_runtime", "RuntimeDefaults")
    obj = RuntimeDefaults.objects.filter(pk=1).first()
    if not obj:
        return
    pl = dict(obj.payload or {})
    update_fields: list[str] = ["payload"]
    specs = (
        ("backend_console_theme", 64),
        ("header_bg_color", 32),
        ("footer_bg_color", 32),
        ("theme_brightness", 32),
        ("theme_harmony", 64),
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
        ("platform_runtime", "0020_runtimedefaults_portal_theme_policy_batch"),
    ]

    operations = [
        migrations.AddField(
            model_name="runtimedefaults",
            name="backend_console_theme",
            field=models.CharField(
                blank=True,
                help_text="Default backend console theme mode.",
                max_length=64,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="footer_bg_color",
            field=models.CharField(
                blank=True,
                help_text="Default footer background color token.",
                max_length=32,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="header_bg_color",
            field=models.CharField(
                blank=True,
                help_text="Default header background color token.",
                max_length=32,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="theme_brightness",
            field=models.CharField(
                blank=True,
                help_text="Default theme brightness mode.",
                max_length=32,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="theme_harmony",
            field=models.CharField(
                blank=True,
                help_text="Default theme harmony palette mode.",
                max_length=64,
                null=True,
            ),
        ),
        migrations.RunPython(_backfill_theme_surface_from_payload, _noop_reverse),
    ]
