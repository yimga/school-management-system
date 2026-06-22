# Generated for the per-tenant MFA enforcement / grace-window cascade.
#
# Plain nullable AddField (the deploy-safe migration class — never a CreateModel,
# so it cannot DuplicateTable-freeze a predeploy). Pre-migrate reads degrade to
# the platform default ("strict" / platform grace days) via the SiteSettings
# façade + RuntimeDefaults.get_singleton DatabaseError guard, so code may lead
# this migration with zero behavior change. Mirrors 0091 (ai_mode).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('platform_runtime', '0092_scheduledjobheartbeat'),
    ]

    operations = [
        migrations.AddField(
            model_name='runtimedefaults',
            name='mfa_enforcement_mode',
            field=models.CharField(
                blank=True,
                null=True,
                max_length=16,
                choices=[
                    ('strict', 'Strict (require MFA before access — hard wall)'),
                    ('grace', 'Grace (allow access, nudge, enforce after grace window)'),
                    ('optional', 'Optional (never block — nudge only)'),
                ],
                help_text=(
                    'How required-role MFA is enforced when the user has no device. '
                    'Blank/None = strict (platform default, current behavior). Tenants '
                    'may override per-school via SiteSettings. Resolved by '
                    'apps.accounts.mfa_defaults.resolve_mfa_enforcement.'
                ),
            ),
        ),
        migrations.AddField(
            model_name='runtimedefaults',
            name='mfa_grace_period_days',
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                help_text=(
                    'Days a required-role user may access without MFA before the grace '
                    'window closes (grace mode only). Blank/None = platform default. '
                    'Measured from the user\'s date_joined.'
                ),
            ),
        ),
    ]
