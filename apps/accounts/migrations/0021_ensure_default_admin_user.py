# Ensure default main platform admin user (username: admin, password: admin).
# In production, change the password immediately: python manage.py changepassword admin

from django.db import migrations
from django.contrib.auth.hashers import make_password


def ensure_default_admin(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    user, _ = User.objects.get_or_create(
        username="admin",
        defaults={
            "email": "admin@example.com",
            "password": make_password("admin"),
            "is_staff": True,
            "is_superuser": True,
            "is_active": True,
            "role": "SUPERADMIN",
        },
    )
    user.password = make_password("admin")
    user.is_staff = True
    user.is_superuser = True
    user.is_active = True
    if getattr(user, "role", None) is not None:
        user.role = "SUPERADMIN"
    user.save()


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0020_security_powerhouse_audit_passkey"),
    ]

    operations = [
        migrations.RunPython(ensure_default_admin, noop),
    ]
