# Generated manually — policy maps + compliance/referral batch (7 fields).

from decimal import Decimal, InvalidOperation

from django.db import migrations, models


def _as_json_like_or_none(value):
    if isinstance(value, (dict, list)):
        return value
    return None


def _as_str_or_none(value, max_len):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:max_len]


def _as_int_or_none(value):
    if value is None:
        return None
    try:
        iv = int(value)
    except (TypeError, ValueError):
        return None
    return iv if iv >= 0 else None


def _as_decimal_or_none(value):
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _backfill_policy_maps_and_compliance_from_payload(apps, schema_editor):
    RuntimeDefaults = apps.get_model("platform_runtime", "RuntimeDefaults")
    obj = RuntimeDefaults.objects.filter(pk=1).first()
    if not obj:
        return
    pl = dict(obj.payload or {})
    update_fields: list[str] = ["payload"]

    if "backend_feature_flags" in pl:
        obj.backend_feature_flags = _as_json_like_or_none(pl.pop("backend_feature_flags"))
        update_fields.append("backend_feature_flags")
    if "portal_features" in pl:
        obj.portal_features = _as_json_like_or_none(pl.pop("portal_features"))
        update_fields.append("portal_features")
    if "notification_channels" in pl:
        raw = pl.pop("notification_channels")
        obj.notification_channels = raw if isinstance(raw, list) else None
        update_fields.append("notification_channels")
    if "require_mfa_roles" in pl:
        raw = pl.pop("require_mfa_roles")
        obj.require_mfa_roles = raw if isinstance(raw, list) else None
        update_fields.append("require_mfa_roles")
    if "offline_sync_conflict_resolution" in pl:
        obj.offline_sync_conflict_resolution = _as_str_or_none(
            pl.pop("offline_sync_conflict_resolution"), 32
        )
        update_fields.append("offline_sync_conflict_resolution")
    if "compliance_profile_id" in pl:
        obj.compliance_profile_id = _as_int_or_none(pl.pop("compliance_profile_id"))
        update_fields.append("compliance_profile_id")
    if "referral_bonus_amount" in pl:
        obj.referral_bonus_amount = _as_decimal_or_none(pl.pop("referral_bonus_amount"))
        update_fields.append("referral_bonus_amount")

    obj.payload = pl
    obj.save(update_fields=update_fields)


def _noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("platform_runtime", "0024_runtimedefaults_policy_reports_interval_batch"),
    ]

    operations = [
        migrations.AddField(
            model_name="runtimedefaults",
            name="backend_feature_flags",
            field=models.JSONField(
                blank=True,
                help_text="Default backend feature-flag map.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="compliance_profile_id",
            field=models.PositiveBigIntegerField(
                blank=True,
                help_text="Default compliance profile pointer id (finance.ComplianceProfile).",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="notification_channels",
            field=models.JSONField(
                blank=True,
                help_text="Default enabled notification channels list.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="offline_sync_conflict_resolution",
            field=models.CharField(
                blank=True,
                help_text="Default offline-sync conflict strategy (for example: show_both).",
                max_length=32,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="portal_features",
            field=models.JSONField(
                blank=True,
                help_text="Default portal feature-flag map.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="referral_bonus_amount",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Default referral bonus amount.",
                max_digits=10,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="runtimedefaults",
            name="require_mfa_roles",
            field=models.JSONField(
                blank=True,
                help_text="Default role codes requiring MFA setup.",
                null=True,
            ),
        ),
        migrations.RunPython(
            _backfill_policy_maps_and_compliance_from_payload,
            _noop_reverse,
        ),
    ]
