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
    blueprint_path = ROOT / "apps" / "schools" / "tenant_seed_blueprint.py"
    text = blueprint_path.read_text(encoding="utf-8")

    for token in (
        "apply_tenant_seed_blueprint",
        "DEFAULT_SLUG",
        "DEFAULT_DISPLAY_NAME",
        "tenant_manifest_snapshot",
        "seed_demo_users_for_school",
    ):
        if token not in text:
            failures.append(f"tenant_seed_blueprint missing {token}")

    from apps.schools.tenant_seed_blueprint import apply_tenant_seed_blueprint, blueprint_status
    from apps.schools.models import School

    school = apply_tenant_seed_blueprint()
    if school is None:
        failures.append("apply_tenant_seed_blueprint returned None (demo-school missing)")
    else:
        status = blueprint_status(school)
        if not status.get("has_manifest_snapshot"):
            failures.append("blueprint did not persist tenant_manifest_snapshot")
        if school.name != "New Test High School":
            failures.append(f"expected display name New Test High School, got {school.name!r}")

        # Portal toggles effective for student E2E
        from apps.platform_runtime.helpers import get_effective_site_settings

        eff = get_effective_site_settings(school=school)
        if not getattr(eff, "enable_student_portal", False):
            failures.append("enable_student_portal not true after blueprint")

    if failures:
        print("verify_tenant_seed_blueprint: FAIL")
        for f in failures:
            print(f"- {f}")
        return 1

    print("verify_tenant_seed_blueprint: TENANT_SEED_BLUEPRINT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
