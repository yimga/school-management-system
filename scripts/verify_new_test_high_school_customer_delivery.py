from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    sys.path.insert(0, str(ROOT))

    import django

    django.setup()

    failures: list[str] = []

    from apps.schools.models import School
    from apps.schools.tenant_seed_blueprint import (
        DEFAULT_DISPLAY_NAME,
        DEFAULT_SLUG,
        apply_tenant_seed_blueprint,
        blueprint_status,
    )
    from apps.platform_runtime.tenant_operational_lifecycle import (
        resolve_operational_lifecycle_state,
    )

    school = apply_tenant_seed_blueprint()
    if school is None:
        failures.append(f"school slug {DEFAULT_SLUG!r} not found")
    else:
        if school.slug != DEFAULT_SLUG:
            failures.append(f"unexpected slug {school.slug!r}")
        if school.name != DEFAULT_DISPLAY_NAME:
            failures.append(f"display name mismatch: {school.name!r}")

        status = blueprint_status(school)
        if not status.get("ok"):
            failures.append(f"blueprint_status not ok: {status}")

        ops = resolve_operational_lifecycle_state(school)
        if not ops.get("state"):
            failures.append("operational lifecycle state missing")

        from apps.accounts.models import User

        for username in ("demo.admin", "demo.teacher", "demo.parent", "demo.student"):
            if not User.objects.filter(username=username, is_active=True).exists():
                failures.append(f"missing demo user {username}")

    if failures:
        print("verify_new_test_high_school_customer_delivery: FAIL")
        for f in failures:
            print(f"- {f}")
        return 1

    print(
        "verify_new_test_high_school_customer_delivery: "
        "NEW_TEST_HIGH_SCHOOL_CUSTOMER_DELIVERY_PASS"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
