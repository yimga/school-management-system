"""Verifier — ExperienceTemplate registry shape + uniqueness + composition refs.

Exits 1 on regression. Reads the registries WITHOUT booting Django app config.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _import_django_stack() -> tuple[object, object, object]:
    """Bootstrap Django for ORM-free registry reads.

    The registries are pure Python dataclasses but live inside apps/. We need
    sys.path to include the repo root.
    """
    here = Path(__file__).resolve().parent
    repo_root = here.parent
    sys.path.insert(0, str(repo_root))
    import os

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django  # noqa: E402

    django.setup()
    from apps.brand_experience import experience_templates  # noqa: E402
    from apps.platform_runtime import pack_contract  # noqa: E402
    from apps.siteconfig import local_experience_profiles  # noqa: E402

    return experience_templates, pack_contract, local_experience_profiles


def main() -> int:
    et, pc, lep = _import_django_stack()
    try:
        et.assert_registry_invariants()
        lep.assert_registry_invariants()
    except AssertionError as exc:
        print(f"FAIL: {exc}")
        return 1

    pack_keys = {p.key for p in pc.EXPERIENCE_TEMPLATE_PACKS}
    overlay_keys = set(et.overlay_keys())
    missing_overlay = pack_keys - overlay_keys
    missing_pack = overlay_keys - pack_keys
    if missing_overlay:
        print(f"FAIL: {len(missing_overlay)} pack contracts have no overlay: {sorted(missing_overlay)[:5]}")
        return 1
    if missing_pack:
        print(f"FAIL: {len(missing_pack)} overlays have no pack contract: {sorted(missing_pack)[:5]}")
        return 1

    profile_keys = set(lep.profile_keys())
    for o in et.OVERLAYS:
        if o.local_profile_ref and o.local_profile_ref not in profile_keys:
            print(f"FAIL: Template {o.key} references unknown LocalExperienceProfile {o.local_profile_ref}")
            return 1

    counts = {}
    for o in et.OVERLAYS:
        counts[o.category] = counts.get(o.category, 0) + 1
    expected = {
        "operator": 10,
        "tenant-admin": 8,
        "teacher": 8,
        "parent": 6,
        "student": 6,
        "staff": 4,
        "specialized": 8,
        "local-first": 25,
    }
    for cat, n in expected.items():
        actual = counts.get(cat, 0)
        if actual != n:
            print(f"FAIL: Category '{cat}' expected {n} templates, found {actual}")
            return 1

    report = {
        "status": "EXPERIENCE_TEMPLATE_REGISTRY_PASS",
        "template_count": len(et.OVERLAYS),
        "pack_contract_count": len(pc.EXPERIENCE_TEMPLATE_PACKS),
        "profile_count": len(lep.PROFILES),
        "category_counts": counts,
        "palette_families": list(et.PALETTE_FAMILIES),
    }
    out_dir = Path(__file__).resolve().parent.parent / "docs" / "generated"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "experience_template_registry.json").write_text(json.dumps(report, indent=2, sort_keys=True))
    print("EXPERIENCE_TEMPLATE_REGISTRY_PASS")
    print(f"  templates: {len(et.OVERLAYS)}  profiles: {len(lep.PROFILES)}")
    print(f"  categories: {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
