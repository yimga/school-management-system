# Generated manually — policy/reports/reminder batch (5 fields).

from django.db import migrations, models


def _as_bool_or_none(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return None


def _as_int_or_none(value):
    if value is None:
        return None
    try:
        iv = int(value)
    except (TypeError, ValueError):
        return None
    return iv if iv >= 0 else None


def _backfill_policy_reports_interval_from_payload(apps, schema_editor):
    RuntimeDefaults = apps.get_model("platform_runtime", "RuntimeDefaults")
    obj = RuntimeDefaults.objects.filter(pk=1).first()
    if not obj:
        return
    pl = dict(obj.payload or {})
    update_fields: list[str] = ["payload"]

    bool_fields = (
        "require_mfa_all_staff",
        "use_promotion_rule_for_pass",
        "notify_parent_welcome_email",
        "reports_use_approved_grades_only",
    )
    for fname in bool_fields:
        if fname not in pl:
            continue
        setattr(obj, fname, _as_bool_or_none(pl.pop(fname)))
        update_fields.append(fname)

    if "requests_reminder_interval_hours" in pl:
        obj.requests_reminder_interval_hours = _as_int_or_none(
            pl.pop("requests_reminder_interval_hours")
        )
        update_fields.append("requests_reminder_interval_hours")

    obj.payload = pl
    obj.save(update_fields=update_fields)


def _noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("platform_runtime", "0023_runtimedefaults_reports_themepack_batch"),
    ]

    operations = [
        migrations.AddField(
            model_name="runtimedefaults",
            name="notify_parent_welcome_email",
            field=models.BooleanField(
                blank=True,
                help_text="Default toggle for parent welcome-email notification.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="reports_use_approved_grades_only",
            field=models.BooleanField(
                blank=True,
                help_text="Default report policy to use approved grades only.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="requests_reminder_interval_hours",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Default request reminder interval in hours (0 disables reminders).",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="require_mfa_all_staff",
            field=models.BooleanField(
                blank=True,
                help_text="Default policy requiring MFA setup for all staff roles.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="use_promotion_rule_for_pass",
            field=models.BooleanField(
                blank=True,
                help_text="Default grading policy flag for promotion-rule pass logic.",
                null=True,
            ),
        ),
        migrations.RunPython(
            _backfill_policy_reports_interval_from_payload,
            _noop_reverse,
        ),
    ]
