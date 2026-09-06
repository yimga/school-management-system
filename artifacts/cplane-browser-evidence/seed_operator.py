#!/usr/bin/env python3
"""Seed the operator account + a real confirmed TOTP device for browser evidence.

Deliberately does NOT touch sessions, does NOT set ``mfa_verified``, and does NOT
disable any middleware. The browser must do a real password login and a real TOTP
step-up; this only ENROLLS an MFA device for a throwaway QA operator, which is
exactly what a human operator does on first login.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

USERNAME = os.environ.get("VISUAL_QA_USERNAME", "visualqa_admin")
PASSWORD = os.environ.get("VISUAL_QA_PASSWORD", "VisualQaPass123!")
DEVICE_NAME = os.environ.get("VISUAL_QA_TOTP_DEVICE", "e2e-playwright")
TOTP_HEX_KEY = os.environ.get(
    "VISUAL_QA_TOTP_HEX_KEY", "eab95095c004f245721ba0fa7ebf82d5dc73"
)


def main() -> int:
    import django

    django.setup()

    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django_otp.plugins.otp_totp.models import TOTPDevice

    print(f"DB = {settings.DATABASES['default']['NAME']}")
    print(f"SESSION_ENGINE = {settings.SESSION_ENGINE}")
    print(f"SESSION_PINNING_ENABLED = {settings.SESSION_PINNING_ENABLED}")

    User = get_user_model()
    user, created = User.objects.get_or_create(
        username=USERNAME,
        defaults={
            "email": f"{USERNAME}@example.com",
            "is_staff": True,
            "is_superuser": True,
            "is_active": True,
            "role": "SUPERADMIN",
        },
    )
    user.is_staff = True
    user.is_superuser = True
    user.is_active = True
    user.role = "SUPERADMIN"
    user.set_password(PASSWORD)
    user.save()
    print(f"user {user.username} pk={user.pk} created={created} role={user.role}")

    TOTPDevice.objects.filter(user=user).delete()
    device = TOTPDevice.objects.create(user=user, name=DEVICE_NAME, confirmed=True)
    device.key = TOTP_HEX_KEY
    device.save()
    print(f"TOTP device {device.name} confirmed={device.confirmed} pk={device.pk}")

    # One school so control-plane list surfaces have a real row to render.
    from apps.schools.models import School

    school, s_created = School.objects.get_or_create(
        subdomain="demo-school",
        defaults={
            "slug": "demo-school",
            "name": "Demo School",
            "is_active": True,
        },
    )
    print(f"school {school.name} pk={school.pk} created={s_created}")
    print(f"School.objects.count() = {School.objects.count()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
