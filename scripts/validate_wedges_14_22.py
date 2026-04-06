#!/usr/bin/env python3
"""
Validate Wedges 14–22 (Education systems) implementation.

Run: python scripts/validate_wedges_14_22.py [--base REPO_ROOT]

Exit 0 if all checks pass; exit 1 and print failures otherwise.
See docs/WEDGES_14_22_EDUCATION_SYSTEMS_PLAN.md.
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

    # 1. Template exists
    template_path = repo_root / "templates" / "schools" / "super_education_systems.html"
    if not template_path.exists():
        failures.append(
            "Missing template: templates/schools/super_education_systems.html"
        )

    # 2. URL and view
    urls_py = repo_root / "apps" / "schools" / "super_urls.py"
    if urls_py.exists():
        url_text = urls_py.read_text(encoding="utf-8", errors="replace")
        if (
            "education_systems" not in url_text
            or "super_education_systems" not in url_text
        ):
            failures.append("super_urls.py missing education_systems path or view")
    else:
        failures.append("Missing apps/schools/super_urls.py")

    wedge_py = repo_root / "apps" / "schools" / "super_views_wedge.py"
    if wedge_py.exists():
        wtext = wedge_py.read_text(encoding="utf-8", errors="replace")
        if (
            "super_education_systems" not in wtext
            or "list_sector_system_types_14_22" not in wtext
        ):
            failures.append(
                "super_views_wedge.py missing super_education_systems or list_sector_system_types_14_22"
            )
    else:
        failures.append("Missing apps/schools/super_views_wedge.py")

    # 3. Django checks: registry, model, list_sector_system_types_14_22
    try:
        import django

        os.chdir(repo_root)
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
        django.setup()

        from apps.registries.models import EducationSystemTypeRegistry
        from apps.registries.services import (
            WEDGE_14_22_SECTOR_CODES,
            list_sector_system_types_14_22,
        )
        from apps.schools.models import School

        # Run seed first so sector types exist (list_sector_system_types_14_22 calls ensure_taxonomy_seed)
        sector_list = list_sector_system_types_14_22()

        # All nine codes in registry and active with category=sector
        for code in WEDGE_14_22_SECTOR_CODES:
            row = EducationSystemTypeRegistry.objects.filter(
                code=code, is_active=True
            ).first()
            if not row:
                failures.append(
                    f"EducationSystemTypeRegistry missing or inactive: {code}"
                )
            elif (row.category or "").strip().lower() != "sector":
                failures.append(
                    f"EducationSystemTypeRegistry.{code} should have category=sector (got {row.category!r})"
                )
        # list_sector_system_types_14_22 returns exactly nine
        if len(sector_list) != 9:
            failures.append(
                f"list_sector_system_types_14_22() should return 9 items, got {len(sector_list)}"
            )
        else:
            codes_returned = {r["code"] for r in sector_list}
            if codes_returned != set(WEDGE_14_22_SECTOR_CODES):
                missing = set(WEDGE_14_22_SECTOR_CODES) - codes_returned
                extra = codes_returned - set(WEDGE_14_22_SECTOR_CODES)
                if missing:
                    failures.append(
                        f"list_sector_system_types_14_22 missing codes: {missing}"
                    )
                if extra:
                    failures.append(
                        f"list_sector_system_types_14_22 extra codes: {extra}"
                    )

        # School model has primary_sector
        if not hasattr(School, "primary_sector"):
            failures.append("School model missing field: primary_sector")
        else:
            f = School._meta.get_field("primary_sector")
            if f.max_length < 48:
                failures.append(
                    f"School.primary_sector max_length should be >= 48, got {f.max_length}"
                )

        # URL resolves
        from django.urls import reverse

        try:
            reverse("super:education_systems")
        except Exception as e:
            failures.append(f"super:education_systems URL did not resolve: {e}")

        from apps.registries.services import (
            build_education_system_support_accordion,
            WEDGE_14_22_SECTOR_CODES,
        )

        def _rev(n):
            try:
                return reverse(n)
            except Exception:
                return None

        acc = build_education_system_support_accordion(_rev)
        if len(acc) != 9:
            failures.append(
                f"build_education_system_support_accordion: expected 9 sectors, got {len(acc)}"
            )
        elif {x["code"] for x in acc} != set(WEDGE_14_22_SECTOR_CODES):
            failures.append(
                "build_education_system_support_accordion: sector codes mismatch WEDGE_14_22_SECTOR_CODES"
            )
        else:
            for row in acc:
                if not row.get("next_actions"):
                    failures.append(
                        f"Education systems accordion sector {row.get('code')} has no next_actions"
                    )

    except Exception as e:
        failures.append(f"Django validation failed: {e}")

    return failures


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate wedges 14–22 (education systems) implementation.",
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
        print(f"validate_wedges_14_22: {exc}", file=sys.stderr)
        return 1

    failures = _run_checks(repo_root)
    if failures:
        for f in failures:
            print(f"FAIL: {f}")
        return 1
    print("OK: All wedge 14–22 checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(None))
