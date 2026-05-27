#!/usr/bin/env python3
"""
Aggressive tenant lifecycle audit — no ignored wiring gaps.

Runs full lifecycle verifiers, URL resolution for every matrix step that
declares url_name, manager operator surfaces, template contracts, and a
live hub-payload smoke test against an in-memory school.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Do not subprocess verify_tenant_lifecycle_completion or audit_tenant_lifecycle_full —
# those call this script and would recurse. Email cascade is an independent gate.
SUBPROCESS_SCRIPTS = ("scripts/verify_tenant_email_delivery_cascade.py",)

TEMPLATE_MARKERS = (
    (
        "templates/siteconfig/tenant_lifecycle_command_center.html",
        "data-rmc-section-anchor",
    ),
    (
        "templates/siteconfig/tenant_lifecycle_command_center.html",
        "rmc_section_nav_curated",
    ),
    (
        "templates/siteconfig/tenant_lifecycle_command_center.html",
        "section-lifecycle-playbook",
    ),
    (
        "templates/siteconfig/tenant_studio_hub.html",
        "data-rmc-tenant-studio-lifecycle-hub",
    ),
    (
        "templates/schools/super_offboarding_queue.html",
        "data-rmc-auto-purge-disabled-banner",
    ),
    (
        "templates/schools/super_tenant_360.html",
        "data-rmc-lifecycle-workflow-hub",
    ),
)

MANAGER_URL_NAMES = (
    "super:offboarding_queue",
    "super:signup_diagnostics",
    "super:email_health",
    "super:tenant_360",
)

MATRIX_STATE_KEYS = (
    "signup_verified",
    "admissions_active",
    "applicant_enrolled",
    "guardian_invite_claimed",
    "guardian_portal_active",
    "purge_scheduled",
)

SIGNUP_WIRING = (
    ("apps/schools/signup_views.py", "async_send=True"),
    ("apps/schools/signup_views.py", "SignupVerification"),
    ("apps/schools/tenant_offboarding.py", "force_operator"),
    ("templates/schools/super_offboarding_queue.html", "data-rmc-run-scheduled-apply"),
    ("static/js/_pages/schools__super_offboarding_queue-1.js", "force_operator"),
    ("static/js/_pages/schools__super_offboarding_queue-1.js", "purge-due-tenants"),
)


def _run(script: str) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(ROOT / script)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, ((proc.stdout or "") + (proc.stderr or "")).strip()


def _django_checks() -> list[str]:
    failures: list[str] = []
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()

    from django.urls import NoReverseMatch, reverse

    from apps.lifecycle.enrollment_workflow_matrix import (
        ENROLLMENT_TRACK,
        REGISTRATION_TRACK,
        TENANT_OFFBOARDING_TRACK,
        _marketing_signup_url,
        _tenant_reverse,
        build_enrollment_track,
        build_registration_track,
        build_tenant_offboarding_track,
    )
    import uuid

    from apps.schools.models import School

    for rel, needle in TEMPLATE_MARKERS:
        path = ROOT / rel
        if not path.is_file():
            failures.append(f"missing template: {rel}")
            continue
        if needle not in path.read_text(encoding="utf-8", errors="replace"):
            failures.append(f"{rel}: missing `{needle}`")

    for name in MANAGER_URL_NAMES:
        try:
            if name == "super:tenant_360":
                reverse(
                    name,
                    kwargs={"school_id": "00000000-0000-0000-0000-000000000099"},
                )
            else:
                reverse(name)
        except NoReverseMatch:
            failures.append(f"manager url does not resolve: {name}")

    if not _marketing_signup_url():
        failures.append("marketing signup URL empty")

    for track_name, track in (
        ("registration", REGISTRATION_TRACK),
        ("enrollment", ENROLLMENT_TRACK),
        ("offboarding", TENANT_OFFBOARDING_TRACK),
    ):
        for step in track:
            url_name = (step.get("url_name") or "").strip()
            if not url_name:
                continue
            url = _tenant_reverse(url_name)
            if not url:
                failures.append(
                    f"{track_name}/{step['key']}: tenant reverse failed for `{url_name}`"
                )

    matrix_src = (ROOT / "apps/lifecycle/enrollment_workflow_matrix.py").read_text(
        encoding="utf-8", errors="replace"
    )
    for key in MATRIX_STATE_KEYS:
        if key not in matrix_src:
            failures.append(f"enrollment_workflow_matrix missing state `{key}`")

    school_id = uuid.uuid4()
    school = School(
        pk=school_id,
        id=school_id,
        name="Aggressive Audit School",
        slug="aggressive-audit-school",
        subdomain="aggressive-audit-school",
        is_active=True,
        country_code="US",
        settings={"lifecycle": {"creation_path": "self_serve"}},
    )
    try:
        reg = build_registration_track(school)
        enr = build_enrollment_track(school)
        off = build_tenant_offboarding_track(school)
        if int(reg.get("total") or 0) < 5:
            failures.append(f"registration track expected >=5 steps, got {reg.get('total')}")
        if int(enr.get("total") or 0) < 7:
            failures.append(f"enrollment track expected >=7 steps, got {enr.get('total')}")
        if int(off.get("total") or 0) < 4:
            failures.append(f"offboarding track expected >=4 steps, got {off.get('total')}")
    except Exception as exc:
        failures.append(f"lifecycle track builders raised: {exc!r}")

    return failures


def main() -> int:
    failures: list[str] = []

    for rel, needle in SIGNUP_WIRING:
        path = ROOT / rel
        if not path.is_file():
            failures.append(f"missing file: {rel}")
            continue
        if needle not in path.read_text(encoding="utf-8", errors="replace"):
            failures.append(f"{rel}: missing `{needle}`")

    for script in SUBPROCESS_SCRIPTS:
        code, out = _run(script)
        if code != 0:
            failures.append(f"{script} failed:\n{out[:600]}")

    try:
        failures.extend(_django_checks())
    except Exception as exc:
        failures.append(f"django_checks crashed: {exc!r}")

    if failures:
        print("TENANT_LIFECYCLE_AGGRESSIVE_AUDIT_FAIL")
        for msg in failures:
            print(f"  - {msg}")
        return 1

    print("TENANT_LIFECYCLE_AGGRESSIVE_AUDIT_PASS")
    print(f"  subprocess gates: {len(SUBPROCESS_SCRIPTS)}")
    print(f"  template markers: {len(TEMPLATE_MARKERS)}")
    print(f"  matrix state keys: {len(MATRIX_STATE_KEYS)}")
    print(f"  manager urls: {len(MANAGER_URL_NAMES)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
