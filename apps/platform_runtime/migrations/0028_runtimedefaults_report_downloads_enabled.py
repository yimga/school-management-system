# Promote report_downloads_enabled (reports domain) from JSON payload to first-class column.

from django.db import migrations, models


def _coerce_bool(val):
    if isinstance(val, bool):
        return val
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return bool(val)
    s = str(val).strip().lower()
    if s in ("true", "1", "yes", "on"):
        return True
    if s in ("false", "0", "no", "off", ""):
        return False
    return bool(val)


def backfill_report_downloads_from_payload(apps, schema_editor):
    RD = apps.get_model("platform_runtime", "RuntimeDefaults")
    rd = RD.objects.filter(pk=1).first()
    if rd is None:
        return
    pl = dict(rd.payload or {})
    key = "report_downloads_enabled"
    if key not in pl:
        return
    raw = pl.pop(key)
    coerced = _coerce_bool(raw)
    if coerced is not None:
        rd.report_downloads_enabled = coerced
    rd.payload = pl
    rd.save(
        update_fields=["payload", "report_downloads_enabled", "updated_at"],
    )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("platform_runtime", "0027_platformphasebdomainsnapshot_key_checksums"),
    ]

    operations = [
        migrations.AddField(
            model_name="runtimedefaults",
            name="report_downloads_enabled",
            field=models.BooleanField(
                blank=True,
                help_text="Default toggle for parent/report download surfaces (reports domain).",
                null=True,
            ),
        ),
        migrations.RunPython(
            backfill_report_downloads_from_payload,
            noop_reverse,
        ),
    ]
