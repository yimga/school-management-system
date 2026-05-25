# Ensure canonical admin user keeps break_glass PlatformOperatorProfile

from django.conf import settings
from django.db import migrations


def ensure_admin_operator_profile(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    PlatformOperatorProfile = apps.get_model(
        "platform_runtime", "PlatformOperatorProfile"
    )
    admin = User.objects.filter(username="admin").first()
    if not admin:
        return
    changed = False
    if not admin.is_superuser or not admin.is_staff or not admin.is_active:
        admin.is_superuser = True
        admin.is_staff = True
        admin.is_active = True
        changed = True
    role = getattr(admin, "role", None)
    if role is not None and str(role).upper() != "SUPERADMIN":
        admin.role = "SUPERADMIN"
        changed = True
    if changed:
        admin.save()
    PlatformOperatorProfile.objects.update_or_create(
        user_id=admin.pk,
        defaults={
            "status": "active",
            "tier": "break_glass",
            "mfa_required": True,
            "break_glass_only": False,
        },
    )


class Migration(migrations.Migration):

    dependencies = [
        ("platform_runtime", "0074_platform_operator_identity"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(ensure_admin_operator_profile, migrations.RunPython.noop),
    ]
