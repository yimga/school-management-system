"""
Seed local QA fixtures required by tests/e2e/apple-class-authenticated.spec.js:
  - Platform superuser: appleqa_platform / AppleQaPass123!
  - Tenant School: subdomain=apple-class-qa, slug=apple-class-qa
  - Tenant admin: appleqa_tenant / AppleQaPass123! linked to that school via SchoolMembership

Idempotent: safe to re-run. Targets DEFAULT_DB only (single-tenant SQLite/local).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.contrib.auth import get_user_model

from apps.schools.models import School, SchoolMembership

User = get_user_model()

PLATFORM_USERNAME = os.environ.get("APPLE_QA_PLATFORM_USERNAME", "appleqa_platform")
PLATFORM_PASSWORD = os.environ.get("APPLE_QA_PLATFORM_PASSWORD", "AppleQaPass123!")
TENANT_USERNAME = os.environ.get("APPLE_QA_TENANT_USERNAME", "appleqa_tenant")
TENANT_PASSWORD = os.environ.get("APPLE_QA_TENANT_PASSWORD", "AppleQaPass123!")
TENANT_SUBDOMAIN = "apple-class-qa"
TENANT_SLUG = "apple-class-qa"
TENANT_NAME = "Apple Class QA"
# Fixed hex secret for django_otp TOTPDevice.key (local QA only; see scripts/apple_class_qa_totp.py).
APPLE_CLASS_QA_TOTP_HEX = os.environ.get(
    "APPLE_CLASS_QA_TOTP_HEX", "31323334353637383930313233343536"
)
TOTP_DEVICE_NAME = "apple-class-qa"


def ensure_qa_totp(user) -> None:
    from django_otp.plugins.otp_totp.models import TOTPDevice

    device, _ = TOTPDevice.objects.update_or_create(
        user=user,
        name=TOTP_DEVICE_NAME,
        defaults={"confirmed": True, "key": APPLE_CLASS_QA_TOTP_HEX},
    )
    if device.key != APPLE_CLASS_QA_TOTP_HEX or not device.confirmed:
        device.key = APPLE_CLASS_QA_TOTP_HEX
        device.confirmed = True
        device.save(update_fields=["key", "confirmed"])


def ensure_platform_user() -> None:
    user, created = User.objects.get_or_create(
        username=PLATFORM_USERNAME,
        defaults={
            "email": f"{PLATFORM_USERNAME}@example.com",
            "role": "ADMIN",
            "is_staff": True,
            "is_superuser": True,
            "is_active": True,
        },
    )
    user.role = "ADMIN"
    user.is_staff = True
    user.is_superuser = True
    user.is_active = True
    user.email = user.email or f"{PLATFORM_USERNAME}@example.com"
    user.set_password(PLATFORM_PASSWORD)
    user.save()
    ensure_qa_totp(user)
    print(f"platform user: {PLATFORM_USERNAME} ({'created' if created else 'updated'})")


def ensure_tenant_school() -> School:
    school = School.objects.filter(subdomain__iexact=TENANT_SUBDOMAIN).first()
    if school is None:
        school = School.objects.filter(slug__iexact=TENANT_SLUG).first()
    if school is None:
        school = School.objects.create(
            slug=TENANT_SLUG,
            subdomain=TENANT_SUBDOMAIN,
            name=TENANT_NAME,
            is_active=True,
        )
        print(f"tenant school: created {school.slug} (subdomain={school.subdomain})")
    else:
        changed = False
        if school.subdomain != TENANT_SUBDOMAIN:
            school.subdomain = TENANT_SUBDOMAIN
            changed = True
        if school.slug != TENANT_SLUG:
            school.slug = TENANT_SLUG
            changed = True
        if not school.is_active:
            school.is_active = True
            changed = True
        if not school.name:
            school.name = TENANT_NAME
            changed = True
        if changed:
            school.save()
            print(f"tenant school: updated {school.slug}")
        else:
            print(f"tenant school: present {school.slug} (subdomain={school.subdomain})")
    return school


def ensure_local_browser_mfa_policy() -> None:
    """Apple-class Playwright cannot complete MFA setup; relax staff MFA for local QA only."""
    from apps.platform_runtime.models import RuntimeDefaults

    defaults, _ = RuntimeDefaults.objects.get_or_create(pk=1)
    if defaults.require_mfa_all_staff:
        defaults.require_mfa_all_staff = False
        defaults.save(update_fields=["require_mfa_all_staff"])
        print("require_mfa_all_staff: disabled for local Apple-class QA")
    else:
        print("require_mfa_all_staff: already off")


def ensure_settings_manage_permission(user) -> None:
    from apps.accounts.models import Permission

    perm, _ = Permission.objects.get_or_create(
        code="settings.manage",
        defaults={"name": "Manage settings"},
    )
    user.feature_permissions.add(perm)


def ensure_tenant_user(school: School) -> None:
    user, created = User.objects.get_or_create(
        username=TENANT_USERNAME,
        defaults={
            "email": f"{TENANT_USERNAME}@example.com",
            "first_name": "Apple",
            "last_name": "QA",
            "role": "ADMIN",
            "is_staff": True,
            "is_superuser": False,
            "is_active": True,
        },
    )
    user.role = "ADMIN"
    user.is_staff = True
    user.is_active = True
    user.email = user.email or f"{TENANT_USERNAME}@example.com"
    user.set_password(TENANT_PASSWORD)
    user.save()

    membership, _ = SchoolMembership.objects.get_or_create(
        user=user,
        school=school,
        defaults={"role": "ADMIN", "is_primary": True},
    )
    if membership.role != "ADMIN" or not membership.is_primary:
        membership.role = "ADMIN"
        membership.is_primary = True
        membership.save(update_fields=["role", "is_primary"])
    ensure_qa_totp(user)
    ensure_settings_manage_permission(user)
    print(f"tenant user: {TENANT_USERNAME} ({'created' if created else 'updated'}) -> {school.slug}")


if __name__ == "__main__":
    ensure_local_browser_mfa_policy()
    ensure_platform_user()
    school = ensure_tenant_school()
    ensure_tenant_user(school)
    print("seed_apple_class_qa: OK")
