#!/usr/bin/env python3
"""
Validate RunMyCampus wedge super-premium phased execution (§0.2.1.5–§0.2.1.6 SOT).

Phases (10 wedges each, wedges 1–45):
  Phase 1: wedges 1–10   — world-class script + packs (WAEC…CAN) + key super URLs + proof partial file
  Phase 2: wedges 11–20 — BRA/LATAM_ES/AUS/NZL/MENA + education_systems + geography
  Phase 3: wedges 21–30 — learning_delivery + catalog JSON + catalog/runtime modules + wedge views
  Phase 4: wedges 31–40 — ministry stubs + group_campuses + proof partial in ministry/group templates
  Phase 5: wedges 41–45 — OIDC/SAML modules + federation URL reverses (tenant_urls) + one_sis + trust

Run: python scripts/validate_wedge_super_premium_phases.py [--base REPO_ROOT] [--phase N|all]

Exit 0 if all requested phases pass; exit 1 otherwise.
Phase 1 also runs scripts/validate_wedge_world_class.py with matching --base.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parent.parent


def _resolve_base(base: str) -> Path:
    root = Path(base).resolve()
    if not root.is_dir():
        raise ValueError(f"--base path does not exist or is not a directory: {base}")
    return root


def _django(repo_root: Path) -> None:
    os.chdir(repo_root)
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()


def _packs_exist(codes: list[str], failures: list[str]) -> None:
    from apps.siteconfig.tenant_config import REGIONAL_POLICY_PACKS, get_regional_policy_pack

    for code in codes:
        if code not in REGIONAL_POLICY_PACKS:
            failures.append(f"REGIONAL_POLICY_PACKS missing {code!r} (phase pack list)")
        elif not get_regional_policy_pack(code):
            failures.append(f"get_regional_policy_pack({code!r}) empty")


def _reverse_urls(names: list[str], failures: list[str]) -> None:
    from django.test.utils import override_settings
    from django.urls import NoReverseMatch, reverse

    with override_settings(ROOT_URLCONF="config.manager_urls"):
        for name in names:
            try:
                reverse(name)
            except NoReverseMatch as e:
                failures.append(f"URL {name!r} NoReverseMatch: {e}")


def _reverse_accounts_federation(failures: list[str]) -> None:
    """Phase 5 (Glue 44–45): OIDC/SAML routes must reverse on tenant URLconf."""
    from django.test.utils import override_settings
    from django.urls import NoReverseMatch, reverse

    specs: list[tuple[str, tuple, dict | None]] = [
        ("accounts:oidc_start", ("0",), None),
        ("accounts:saml_start", ("0",), None),
        ("accounts:oidc_callback", (), {"integration_id": 1}),
        ("accounts:saml_acs", (), {"integration_id": 1}),
        ("accounts:saml_metadata", (), {"integration_id": 1}),
        ("accounts:oidc_logout", (), {"integration_id": 1}),
    ]
    with override_settings(ROOT_URLCONF="config.tenant_urls"):
        for name, args, kwargs in specs:
            try:
                if kwargs:
                    reverse(name, kwargs=kwargs)
                else:
                    reverse(name, args=args)
            except NoReverseMatch as e:
                failures.append(f"Federation URL {name!r} NoReverseMatch: {e}")


def _view_module_has_defs(
    path: Path, required: list[str], failures: list[str], repo_root: Path
) -> None:
    text = path.read_text(encoding="utf-8", errors="replace")
    for fn in required:
        if f"def {fn}" not in text:
            failures.append(f"{path.relative_to(repo_root)} missing def {fn}()")


def _files_exist(paths: list[Path], failures: list[str], repo_root: Path) -> None:
    for p in paths:
        if not p.exists():
            failures.append(f"Missing file: {p.relative_to(repo_root)}")


def validate_phase(phase: int, failures: list[str], repo_root: Path) -> None:
    if phase == 1:
        # Reuse world-class script (templates, nav, AUS/NZL, views)
        r = subprocess.run(
            [
                sys.executable,
                str(repo_root / "scripts" / "validate_wedge_world_class.py"),
                "--base",
                str(repo_root),
            ],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            failures.append(
                "validate_wedge_world_class.py failed:\n" + (r.stdout or "") + (r.stderr or "")
            )
        _django(repo_root)
        # Wedges 7–10 geography: Africa (WAEC, AFR_FR), Asia (ASIA), Europe (GBR, EU), North America (US, CAN)
        _packs_exist(
            ["WAEC", "AFR_FR", "ASIA", "GBR", "EU", "US", "CAN"],
            failures,
        )
        _reverse_urls(
            [
                "super:curriculum_packs",
                "super:one_sis_any_lms",
                "super:advancement_hub",
                "super:he_pack",
                "super:geography",
                "super:trust_center",
            ],
            failures,
        )
        _files_exist(
            [
                repo_root
                / "templates"
                / "schools"
                / "partials"
                / "wedge_super_premium_proof.html",
            ],
            failures,
            repo_root,
        )
        return

    if phase == 2:
        _django(repo_root)
        _packs_exist(["BRA", "LATAM_ES", "AUS", "NZL", "MENA"], failures)
        _reverse_urls(["super:education_systems", "super:geography"], failures)
        return

    if phase == 3:
        _django(repo_root)
        _reverse_urls(
            ["super:learning_delivery_packs", "super:learning_institution_catalog_json"],
            failures,
        )
        cat = repo_root / "apps" / "platform_runtime" / "learning_institution_catalog.py"
        runtime = (
            repo_root / "apps" / "platform_runtime" / "learning_institution_runtime.py"
        )
        _files_exist([cat, runtime], failures, repo_root)
        wedge_py = repo_root / "apps" / "schools" / "super_views_wedge.py"
        if wedge_py.exists():
            wtxt = wedge_py.read_text(encoding="utf-8", errors="replace")
            for sym in (
                "super_learning_delivery_packs",
                "super_learning_institution_catalog_json",
            ):
                if sym not in wtxt:
                    failures.append(f"super_views_wedge.py missing view {sym!r}")
        else:
            failures.append("Missing apps/schools/super_views_wedge.py")
        return

    if phase == 4:
        _django(repo_root)
        _reverse_urls(
            [
                "super:ministry_report_stubs",
                "super:ministry_stub_pdf",
                "super:group_campuses",
                "super:district_enterprise",
            ],
            failures,
        )
        stub = repo_root / "templates" / "schools" / "super_ministry_report_stubs.html"
        grp = repo_root / "templates" / "schools" / "super_group_campuses.html"
        dist = repo_root / "templates" / "schools" / "super_district_enterprise.html"
        partial = (
            repo_root
            / "templates"
            / "schools"
            / "partials"
            / "wedge_super_premium_proof.html"
        )
        _files_exist([stub, grp, dist, partial], failures, repo_root)
        for path, needle in (
            (stub, "wedge_super_premium_proof"),
            (grp, "wedge_super_premium_proof"),
            (dist, "wedge_super_premium_proof"),
        ):
            if path.exists():
                t = path.read_text(encoding="utf-8", errors="replace")
                if needle not in t:
                    failures.append(
                        f"{path.relative_to(repo_root)} must include {needle!r} (§0.2.1.5 proof bar)"
                    )
        return

    if phase == 5:
        oidc = repo_root / "apps" / "accounts" / "views_oidc.py"
        saml = repo_root / "apps" / "accounts" / "views_saml.py"
        _files_exist([oidc, saml], failures, repo_root)
        _view_module_has_defs(
            oidc,
            ["oidc_start", "oidc_callback", "oidc_logout"],
            failures,
            repo_root,
        )
        _view_module_has_defs(
            saml,
            ["saml_start", "saml_acs", "saml_metadata"],
            failures,
            repo_root,
        )
        _django(repo_root)
        _reverse_accounts_federation(failures)
        _reverse_urls(["super:one_sis_any_lms", "super:trust_center"], failures)
        return

    failures.append(f"Unknown phase: {phase}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Validate wedge super-premium phases.")
    p.add_argument(
        "--base",
        default=str(DEFAULT_ROOT),
        help="Repository root (default: directory containing this script's parent).",
    )
    p.add_argument(
        "--phase",
        default="all",
        help="Phase 1–5 or 'all' (default: all)",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        repo_root = _resolve_base(args.base)
    except ValueError as exc:
        print(f"validate_wedge_super_premium_phases: {exc}", file=sys.stderr)
        return 1
    failures: list[str] = []
    if args.phase == "all":
        phases = [1, 2, 3, 4, 5]
    else:
        try:
            phases = [int(args.phase)]
        except ValueError:
            print("Invalid --phase; use 1-5 or all", file=sys.stderr)
            return 1
        if phases[0] not in (1, 2, 3, 4, 5):
            print("--phase must be 1-5 or all", file=sys.stderr)
            return 1

    for ph in phases:
        validate_phase(ph, failures, repo_root)

    if failures:
        print("validate_wedge_super_premium_phases FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(
        "validate_wedge_super_premium_phases PASSED (phases: "
        + ", ".join(str(x) for x in phases)
        + ")."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(None))
