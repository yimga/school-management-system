#!/usr/bin/env python3
"""Export isolated manager + tenant sessions for the real-host admin browser matrix.

The database must be an explicit disposable/local evidence database. The script
never accepts an implicit production database and never writes credentials to
the repository; the generated session artifact lives under ignored artifacts/.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if not (os.environ.get("DB_FILE") or "").strip():
    raise SystemExit("DB_FILE is required (use an isolated evidence database)")

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ["REDIS_URL"] = ""
os.environ["RMC_FORCE_DB_SESSIONS"] = "1"

MANAGER_HOST = (os.environ.get("RMC_ADMIN_OPERATOR_HOST") or "manager.runmycampus.com").strip()
TENANT_HOST = (os.environ.get("RMC_ADMIN_TENANT_HOST") or "gilead-tech.runmycampus.com").strip()
SCHOOL_SLUG = (os.environ.get("RMC_ADMIN_SCHOOL_SLUG") or TENANT_HOST.split(".", 1)[0]).strip()
USER_AGENT = os.environ.get(
    "VISUAL_QA_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
)
OUTPUT = ROOT / "artifacts" / "django-admin-canvas-live" / "real-host-sessions.local.json"


def _confirmed_device(user):
    from django_otp.plugins.otp_totp.models import TOTPDevice

    device, _ = TOTPDevice.objects.update_or_create(
        user=user,
        name="real-host-browser-evidence",
        defaults={"confirmed": True},
    )
    device.confirmed = True
    device.key = "eab95095c004f245721ba0fa7ebf82d5dc73"
    device.save(update_fields=["confirmed", "key"])


def _tenant_session(user, school):
    from django.conf import settings
    from django.test import Client

    client = Client(HTTP_HOST=TENANT_HOST, HTTP_USER_AGENT=USER_AGENT)
    client.get("/authentication/login/", secure=True)
    client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
    session = client.session
    session["mfa_verified"] = True
    session["security_posture_review_nagged"] = True
    session["school_id"] = str(school.pk)
    session.save()
    client.cookies[settings.SESSION_COOKIE_NAME] = session.session_key
    response = client.get("/admin/", follow=False, secure=True)
    if response.status_code != 200:
        raise RuntimeError(
            f"tenant session probe failed: HTTP {response.status_code} "
            f"location={response.headers.get('Location', '')}"
        )
    return session.session_key


def _manager_session(user):
    from django.conf import settings
    from django.test import Client

    from apps.schools.tests.manager_client import (
        bind_manager_session,
        mark_manager_mfa_verified,
    )

    client = Client(HTTP_HOST=MANAGER_HOST, HTTP_USER_AGENT=USER_AGENT)
    client.get("/authentication/login/", secure=True)
    client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
    bind_manager_session(client)
    mark_manager_mfa_verified(client)
    response = client.get("/admin/", follow=False, secure=True)
    if response.status_code != 200:
        raise RuntimeError(
            f"manager session probe failed: HTTP {response.status_code} "
            f"location={response.headers.get('Location', '')}"
        )
    cookie_name = getattr(settings, "MANAGER_SESSION_COOKIE_NAME", "rmc_manager_sessionid")
    return client.cookies[cookie_name].value


def main() -> int:
    import django

    django.setup()
    from django.contrib.auth import get_user_model
    from django.contrib.auth.models import Permission

    from apps.schools.models import School, SchoolMembership
    from apps.siteconfig.models import SiteSettings

    school = School.objects.filter(slug=SCHOOL_SLUG, is_active=True).first()
    if school is None:
        raise RuntimeError(f"active school {SCHOOL_SLUG!r} was not found")

    User = get_user_model()
    operator, _ = User.objects.get_or_create(
        username="visualqa_operator_v17",
        defaults={"email": "visualqa-operator-v17@example.test"},
    )
    operator.is_active = True
    operator.is_staff = True
    operator.is_superuser = True
    operator.role = "SUPERADMIN"
    operator.profile_setup_completed = True
    operator.set_password("EvidenceOnly-V17!")
    operator.save()
    _confirmed_device(operator)

    tenant, _ = User.objects.get_or_create(
        username="visualqa_tenant_v17",
        defaults={"email": "visualqa-tenant-v17@example.test"},
    )
    tenant.is_active = True
    tenant.is_staff = True
    tenant.is_superuser = False
    tenant.role = "ADMIN"
    tenant.profile_setup_completed = True
    tenant.set_password("EvidenceOnly-V17!")
    tenant.save()
    tenant.user_permissions.set(Permission.objects.all())
    SchoolMembership.objects.update_or_create(
        user=tenant,
        school=school,
        defaults={"role": "ADMIN", "is_primary": True, "is_school_owner": True},
    )
    _confirmed_device(tenant)

    payload = {
        "operatorSessionId": _manager_session(operator),
        "tenantSessionId": _tenant_session(tenant, school),
        "operatorUserId": str(operator.pk),
        "tenantUserId": str(tenant.pk),
        "schoolId": str(school.pk),
        "siteSettingsId": str(SiteSettings.objects.values_list("pk", flat=True).first() or ""),
        "operatorHost": MANAGER_HOST,
        "tenantHost": TENANT_HOST,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)} for {MANAGER_HOST} and {TENANT_HOST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
