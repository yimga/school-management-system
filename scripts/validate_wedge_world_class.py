#!/usr/bin/env python3
"""
Validate Wedge 1–6 world-class implementation (no Django DB required).

Run: python scripts/validate_wedge_world_class.py [--base REPO_ROOT]

Exit 0 if all checks pass; exit 1 and print failures otherwise.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parent.parent


def _resolve_base(base: str) -> Path:
    root = Path(base).resolve()
    if not root.is_dir():
        raise ValueError(f"--base path does not exist or is not a directory: {base}")
    return root


def _run_checks(repo_root: Path) -> list[str]:
    failures: list[str] = []
    templates = repo_root / "templates"

    # 1. Wedge templates exist
    wedge_templates = [
        "schools/super_curriculum_packs.html",
        "schools/super_geography.html",
        "schools/super_one_sis_any_lms.html",
        "schools/super_advancement_hub.html",
        "schools/super_advancement_phase2_placeholder.html",
        "schools/super_he_pack.html",
    ]
    for rel in wedge_templates:
        if not (templates / rel).exists():
            failures.append(f"Missing template: templates/{rel}")

    # 2. Trust center has world-class cards
    trust_path = templates / "schools" / "super_trust_center.html"
    if not trust_path.exists():
        failures.append("Missing templates/schools/super_trust_center.html")
    else:
        text = trust_path.read_text(encoding="utf-8", errors="replace")
        for phrase in ("Data residency", "Resilience", "District"):
            if phrase not in text:
                failures.append(f"Trust center template missing phrase: {phrase!r}")

    # 3. Region packs: AUS, NZL, and Wedges 7–13 (WAEC, AFR_FR, ASIA, CAN, LATAM_ES, MENA)
    try:
        import django

        os.chdir(repo_root)
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
        django.setup()
        from apps.siteconfig.tenant_config import (
            REGIONAL_POLICY_PACKS,
            get_regional_policy_pack,
        )

        required_packs = [
            "AUS",
            "NZL",
            "WAEC",
            "AFR_FR",
            "ASIA",
            "CAN",
            "LATAM_ES",
            "MENA",
        ]
        for code in required_packs:
            if code not in REGIONAL_POLICY_PACKS:
                failures.append(f"REGIONAL_POLICY_PACKS missing '{code}'")
            elif not get_regional_policy_pack(code):
                failures.append(f"get_regional_policy_pack('{code}') returned empty")
    except Exception as e:
        failures.append(f"Could not validate REGIONAL_POLICY_PACKS: {e}")

    # 4. Nav references (control_plane_nav.py)
    nav_path = repo_root / "apps" / "schools" / "control_plane_nav.py"
    if nav_path.exists():
        nav_text = nav_path.read_text(encoding="utf-8", errors="replace")
        if (
            "Curriculum & region packs" not in nav_text
            or "super:curriculum_packs" not in nav_text
        ):
            failures.append(
                "Nav missing Curriculum & region packs / super:curriculum_packs"
            )
        if (
            "One SIS, any LMS" not in nav_text
            or "super:one_sis_any_lms" not in nav_text
        ):
            failures.append("Nav missing One SIS, any LMS / super:one_sis_any_lms")
    else:
        failures.append("Missing apps/schools/control_plane_nav.py")

    # 5. Wedge views and URLs
    wedge_py = repo_root / "apps" / "schools" / "super_views_wedge.py"
    if not wedge_py.exists():
        failures.append("Missing apps/schools/super_views_wedge.py")
    else:
        wtext = wedge_py.read_text(encoding="utf-8", errors="replace")
        for name in (
            "super_curriculum_packs",
            "super_geography",
            "super_one_sis_any_lms",
            "super_advancement_hub",
            "super_he_pack",
        ):
            if name not in wtext:
                failures.append(f"super_views_wedge.py missing view: {name}")

    urls_py = repo_root / "apps" / "schools" / "super_urls.py"
    if urls_py.exists():
        utext = urls_py.read_text(encoding="utf-8", errors="replace")
        if (
            "curriculum-packs" not in utext
            or "geography" not in utext
            or "one-sis-any-lms" not in utext
        ):
            failures.append("super_urls.py missing wedge path(s)")
    else:
        failures.append("Missing apps/schools/super_urls.py")

    return failures


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate wedge 1–6 world-class implementation (static + Django config reads).",
    )
    parser.add_argument(
        "--base",
        default=str(DEFAULT_ROOT),
        help="Repository root (default: directory containing this script's parent).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        repo_root = _resolve_base(args.base)
    except ValueError as exc:
        print(f"validate_wedge_world_class: {exc}", file=sys.stderr)
        return 1

    failures = _run_checks(repo_root)
    if failures:
        print("Wedge world-class validation FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(
        "Wedge world-class validation passed (templates, trust center, AUS/NZL, nav, views, URLs)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(None))
