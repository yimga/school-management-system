"""Verifier — operator_only ExperienceTemplates are never tenant_safe.

If a template is in the operator category, it MUST have tenant_safe=False and
platform_only=True on its PackContract. Catches the leak risk where an operator
template accidentally becomes visible to tenants.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _bootstrap() -> None:
    here = Path(__file__).resolve().parent
    repo_root = here.parent
    sys.path.insert(0, str(repo_root))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()


def main() -> int:
    _bootstrap()
    from apps.brand_experience import experience_templates as et
    from apps.platform_runtime import pack_contract as pc

    pack_by_key = {p.key: p for p in pc.EXPERIENCE_TEMPLATE_PACKS}
    failures = []
    for o in et.OVERLAYS:
        pack = pack_by_key.get(o.key)
        if pack is None:
            failures.append(f"{o.key}: missing PackContract")
            continue
        if o.category == "operator":
            if pack.tenant_safe:
                failures.append(f"{o.key}: operator category template MUST have tenant_safe=False")
            if not pack.platform_only:
                failures.append(f"{o.key}: operator category template MUST have platform_only=True")
        else:
            if pack.platform_only:
                failures.append(f"{o.key}: non-operator template MUST NOT have platform_only=True")
    tenant_packs = pc.list_packs(pack_type="experience_template", tenant_safe_only=True)
    tenant_keys = {p["key"] for p in tenant_packs}
    operator_in_tenant = [
        o.key for o in et.OVERLAYS if o.category == "operator" and o.key in tenant_keys
    ]
    if operator_in_tenant:
        failures.append(
            f"tenant_safe_only filter leaked {len(operator_in_tenant)} operator templates: {operator_in_tenant[:3]}"
        )
    if failures:
        print("FAIL: tenant-boundary violations")
        for f in failures:
            print(f"  {f}")
        return 1
    print(
        f"TEMPLATE_TENANT_BOUNDARIES_PASS "
        f"(operator: 10 hidden / tenant_safe pool: {len(tenant_packs)})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
