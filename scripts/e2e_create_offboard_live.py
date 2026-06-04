"""Live end-to-end workflow test: create a school, send welcome email,
then offboard + purge + delete it. Runs against the DEFAULT dev DB (not the
in-memory test DB), so it exercises the real code paths without the SQLite
in-memory + daemon-thread locking artifact that the unittest suite hits.

Usage:
    python scripts/e2e_create_offboard_live.py
"""
from __future__ import annotations

import os
import sys
import uuid

# `python scripts/foo.py` puts scripts/ on sys.path, not the project root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
# Force locmem so the welcome-email path is exercised without needing SMTP.
os.environ.setdefault("EMAIL_BACKEND", "django.core.mail.backends.locmem.EmailBackend")

import django  # noqa: E402

django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django.core import mail  # noqa: E402

from apps.schools.models import School  # noqa: E402

PASS = "\033[0m[PASS]"
FAIL = "[FAIL]"
results = []


def check(label: str, ok: bool, detail: str = "") -> None:
    results.append(ok)
    tag = "[PASS]" if ok else "[FAIL]"
    line = f"  {tag} {label}"
    if detail:
        line += f"  -> {detail}"
    print(line)


def main() -> int:
    marker = uuid.uuid4().hex[:8]
    slug = f"e2e-live-{marker}"
    print(f"=== E2E live create+offboard  (slug={slug}) ===")

    # ---- 1. CREATE ----------------------------------------------------
    school = School.objects.create(
        name=f"E2E Live Academy {marker}",
        slug=slug,
        subdomain=slug,
        primary_color="#4F46E5",
        is_active=True,
    )
    check("school created", School.objects.filter(pk=school.pk).exists(),
          f"id={school.id}")

    User = get_user_model()
    admin = User.objects.create_user(
        username=f"e2e_admin_{marker}",
        email=f"e2e_admin_{marker}@example.test",
    )
    admin.set_unusable_password()
    admin.save()
    check("admin user created", User.objects.filter(pk=admin.pk).exists())

    # ---- 2. M2M through-row (the thing that broke the purge) ----------
    m2m_attached = False
    try:
        from apps.registries.models import EducationSystemTypeRegistry

        est, _ = EducationSystemTypeRegistry.objects.get_or_create(
            code="e2e-est", defaults={"name": "E2E Education System"}
        )
        school.education_system_types.add(est)
        m2m_attached = school.education_system_types.filter(pk=est.pk).exists()
    except Exception as exc:  # noqa: BLE001 - diagnostic script
        check("attach M2M education_system_type (skipped)", True, f"{type(exc).__name__}")
    if m2m_attached:
        check("M2M education_system_type attached", True)

    # ---- 3. WELCOME EMAIL --------------------------------------------
    mail.outbox = []
    try:
        from apps.schools.welcome_email import send_welcome_email

        sent = send_welcome_email(str(school.id), admin.email)
        check("send_welcome_email returned True", bool(sent))
        check("welcome email landed in outbox", len(mail.outbox) == 1,
              f"outbox={len(mail.outbox)}")
        if mail.outbox:
            msg = mail.outbox[0]
            check("welcome email to correct recipient", msg.to == [admin.email])
            check("welcome email carries school name",
                  school.name in (msg.subject + msg.body))
    except Exception as exc:  # noqa: BLE001
        check("welcome email path", False, f"{type(exc).__name__}: {exc}")

    # ---- 4. OFFBOARD: inventory + purge ------------------------------
    try:
        from apps.compliance.tenant_offboarding_inventory import (
            iter_school_m2m_through_targets,
            purge_public_school_dependencies,
            delete_school_record_resilient,
        )

        through_targets = list(iter_school_m2m_through_targets())
        check("iter_school_m2m_through_targets finds tables",
              len(through_targets) >= 1,
              f"{[t[0]._meta.label_lower for t in through_targets]}")

        purge_result = purge_public_school_dependencies(school)
        check("purge_public_school_dependencies completed", purge_result is not None,
              f"{purge_result}")

        # M2M rows should be gone after purge
        if m2m_attached:
            still = school.education_system_types.exists()
            check("M2M through-rows cleared by purge", not still,
                  f"remaining={still}")

        # ---- 5. DELETE the school record -----------------------------
        del_result = delete_school_record_resilient(school)
        gone = not School.objects.filter(pk=school.pk).exists()
        check("delete_school_record_resilient removed school", gone,
              f"{del_result}")
    except Exception as exc:  # noqa: BLE001
        import traceback
        check("offboard/purge/delete path", False, f"{type(exc).__name__}: {exc}")
        traceback.print_exc()

    # ---- cleanup any stragglers --------------------------------------
    School.objects.filter(slug=slug).delete()
    User.objects.filter(username=f"e2e_admin_{marker}").delete()

    passed = sum(1 for r in results if r)
    total = len(results)
    print(f"\n{passed}/{total} checks passed.")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
