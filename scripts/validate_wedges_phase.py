#!/usr/bin/env python3
"""
Line-by-line wedge execution gates (10 wedges per phase, 1–45).

Phases align with SOT §0.2.1.6 and validate_wedge_super_premium_phases.py:
  Phase 1: wedges 1–10   (Tier A beachheads + geography 7–10)
  Phase 2: wedges 11–20  (geography 11–13 + education systems 14–20)
  Phase 3: wedges 21–30  (education systems 21–22 + learning/delivery 23–30)
  Phase 4: wedges 31–40  (education types 31–40 + ministry stubs)
  Phase 5: wedges 41–45  (education types 41–43 + glue 44–45)

Each phase runs validate_wedge_super_premium_phases for the same phase number,
then applies extra assertions below (no assumptions — imports real modules).

Run: python scripts/validate_wedges_phase.py [--phase 1|2|3|4|5|all]

Exit 0 if all requested phases pass.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _django():
    os.chdir(REPO_ROOT)
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()


def _run_super_premium(phase: int, failures: list[str]) -> None:
    r = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "validate_wedge_super_premium_phases.py"),
            "--phase",
            str(phase),
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        failures.append(
            f"validate_wedge_super_premium_phases.py --phase {phase} failed:\n"
            + (r.stdout or "")
            + (r.stderr or "")
        )


def _reverse(names: list[str], failures: list[str]) -> None:
    from django.test.utils import override_settings
    from django.urls import NoReverseMatch, reverse

    with override_settings(ROOT_URLCONF="config.manager_urls"):
        for name in names:
            try:
                reverse(name)
            except NoReverseMatch as e:
                failures.append(f"manager URL {name!r} NoReverseMatch: {e}")


def validate_phase_1(failures: list[str]) -> None:
    """Wedges 1–10: core GTM + Africa→North America region packs."""
    _run_super_premium(1, failures)
    _django()

    # --- W1 International K–12: full DNA set + aliases ---
    from apps.siteconfig.education_dna import (
        EDUCATION_DNA_CODE_ALIASES,
        EDUCATION_DNA_CURRICULUMS,
    )

    required_dna = (
        "british_igcse",
        "west_african_waec",
        "francophone_bac",
        "american",
        "vocational",
        "ib",
    )
    for key in required_dna:
        if key not in EDUCATION_DNA_CURRICULUMS:
            failures.append(f"W1: EDUCATION_DNA_CURRICULUMS missing {key!r}")
    for alias in ("IB", "VOCATIONAL", "BRITISH_IGCSE", "AMERICAN"):
        if alias not in EDUCATION_DNA_CODE_ALIASES:
            failures.append(f"W1: EDUCATION_DNA_CODE_ALIASES missing {alias!r}")

    # --- W2 One SIS / LMS (surface + integration entry) ---
    _reverse(
        ["super:one_sis_any_lms", "super:curriculum_packs", "apicenter:dashboard"],
        failures,
    )

    # --- W3 UK / British: GBR pack + british DNA ---
    from apps.siteconfig.tenant_config import get_regional_policy_pack

    gbr = get_regional_policy_pack("GBR")
    if not gbr:
        failures.append("W3: get_regional_policy_pack('GBR') empty")
    if "british_igcse" not in EDUCATION_DNA_CURRICULUMS:
        failures.append("W3: british_igcse missing from DNA")

    # --- W4 District / enterprise ---
    _reverse(
        ["super:trust_center", "super:migration_cloud", "super:geography"],
        failures,
    )

    # --- W5 Advancement models ---
    from apps.schools.models import AdvancementDonor, AdvancementGift

    _ = (AdvancementDonor, AdvancementGift)  # import must succeed

    _reverse(["super:advancement_hub", "super:advancement_phase2_placeholder"], failures)

    # --- W6 Higher-ed spine in codebase ---
    he_path = REPO_ROOT / "apps" / "academics" / "degree_audit.py"
    if not he_path.exists():
        failures.append("W6: missing apps/academics/degree_audit.py")
    else:
        he_txt = he_path.read_text(encoding="utf-8", errors="replace")
        if "degree" not in he_txt.lower():
            failures.append("W6: degree_audit.py looks empty of degree logic")
    try:
        from apps.academics.models import StudentDegreeEnrollment  # noqa: F401
    except ImportError:
        failures.append("W6: StudentDegreeEnrollment import failed (apps.academics.models)")
    _reverse(["super:he_pack"], failures)

    # --- W7–W10 Geography packs (line-by-line) ---
    from apps.siteconfig.tenant_config import REGIONAL_POLICY_PACKS

    w7 = ("LCA", "WAEC", "AFR_FR")
    w8 = ("ASIA",)
    w9 = ("EU", "GBR")
    w10 = ("US", "CAN")
    for label, codes in (
        ("W7 Africa", w7),
        ("W8 Asia", w8),
        ("W9 Europe", w9),
        ("W10 North America", w10),
    ):
        for code in codes:
            if code not in REGIONAL_POLICY_PACKS:
                failures.append(f"{label}: REGIONAL_POLICY_PACKS missing {code!r}")
            elif not get_regional_policy_pack(code):
                failures.append(f"{label}: get_regional_policy_pack({code!r}) empty")


def _validate_wedges_14_22_static(failures: list[str]) -> None:
    """
    File + import checks for wedges 14–22 (no DB — avoids sqlite lock on dev default DB).
    For full registry rows, run: python scripts/validate_wedges_14_22.py or pytest.
    """
    template_path = REPO_ROOT / "templates" / "schools" / "super_education_systems.html"
    if not template_path.exists():
        failures.append("W14–22: missing templates/schools/super_education_systems.html")
    urls_py = REPO_ROOT / "apps" / "schools" / "super_urls.py"
    if urls_py.exists():
        url_text = urls_py.read_text(encoding="utf-8", errors="replace")
        if "education_systems" not in url_text or "super_education_systems" not in url_text:
            failures.append("W14–22: super_urls.py missing education_systems wiring")
    else:
        failures.append("W14–22: missing apps/schools/super_urls.py")
    wedge_py = REPO_ROOT / "apps" / "schools" / "super_views_wedge.py"
    if wedge_py.exists():
        wtext = wedge_py.read_text(encoding="utf-8", errors="replace")
        if "super_education_systems" not in wtext or "list_sector_system_types_14_22" not in wtext:
            failures.append(
                "W14–22: super_views_wedge.py missing super_education_systems / list_sector"
            )
    else:
        failures.append("W14–22: missing super_views_wedge.py")


def validate_phase_2(failures: list[str]) -> None:
    """Wedges 11–20: South America, Oceania, MENA + education systems 14–20."""
    _run_super_premium(2, failures)
    _validate_wedges_14_22_static(failures)

    _django()
    from apps.registries.services import WEDGE_14_22_SECTOR_CODES

    if len(WEDGE_14_22_SECTOR_CODES) != 9:
        failures.append(
            f"W14–22: WEDGE_14_22_SECTOR_CODES must have 9 entries, got {len(WEDGE_14_22_SECTOR_CODES)}"
        )

    from apps.siteconfig.tenant_config import get_regional_policy_pack

    # W11 South America
    for code in ("BRA", "LATAM_ES"):
        if not get_regional_policy_pack(code):
            failures.append(f"W11: pack {code!r} empty")

    # W12 Oceania
    for code in ("AUS", "NZL"):
        if not get_regional_policy_pack(code):
            failures.append(f"W12: pack {code!r} empty")

    # W13 MENA
    if not get_regional_policy_pack("MENA"):
        failures.append("W13: MENA pack empty")

    # W14–W20: static sector sequence (DB rows validated by validate_wedges_14_22.py)
    from apps.registries.services import WEDGE_14_22_SECTOR_CODES

    expected_14_20 = WEDGE_14_22_SECTOR_CODES[:7]
    if expected_14_20 != (
        "PUBLIC",
        "PRIVATE",
        "CHARTER",
        "INTERNATIONAL",
        "FAITH_BASED",
        "HOME_SCHOOL",
        "GOVERNMENT_MINISTRY",
    ):
        failures.append(f"W14–20: unexpected sector slice: {expected_14_20!r}")


def validate_phase_3(failures: list[str]) -> None:
    """Wedges 21–30: NGO, MULTI_CAMPUS + eight delivery modes."""
    _run_super_premium(3, failures)
    _django()

    from apps.registries.services import WEDGE_14_22_SECTOR_CODES

    for code in ("NGO", "MULTI_CAMPUS"):
        if code not in WEDGE_14_22_SECTOR_CODES:
            failures.append(f"W21–22: {code!r} not in WEDGE_14_22_SECTOR_CODES")
    if WEDGE_14_22_SECTOR_CODES[-2:] != ("NGO", "MULTI_CAMPUS"):
        failures.append(
            f"W21–22: expected NGO, MULTI_CAMPUS last; got {WEDGE_14_22_SECTOR_CODES!r}"
        )

    from apps.platform_runtime.learning_institution_catalog import (
        LEARNING_DELIVERY_MODES,
        delivery_wedges,
    )

    if len(LEARNING_DELIVERY_MODES) != 8:
        failures.append("W23–30: LEARNING_DELIVERY_MODES must have exactly 8 rows")
    dw = delivery_wedges()
    if dw != list(range(23, 31)):
        failures.append(f"W23–30: delivery wedges expected 23..30, got {dw!r}")

    _reverse(["super:group_campuses", "super:learning_delivery_packs"], failures)


def validate_phase_4(failures: list[str]) -> None:
    """Wedges 31–40: institution types + ministry stubs W31–W40."""
    _run_super_premium(4, failures)
    _django()

    from apps.platform_runtime.learning_institution_catalog import (
        INSTITUTION_TYPE_PACKS,
        MINISTRY_REPORT_STUBS,
        institution_wedges,
    )

    iw = institution_wedges()
    if iw != list(range(31, 44)):
        failures.append(f"W31–43: institution wedges expected 31..43, got {iw!r}")
    if len(INSTITUTION_TYPE_PACKS) != 13:
        failures.append("W31–43: INSTITUTION_TYPE_PACKS must have 13 rows")

    # W31–W40: each type code must have ministry stub list (non-empty)
    for pack in INSTITUTION_TYPE_PACKS:
        w = int(pack["wedge"])
        if w < 31 or w > 40:
            continue
        code = pack["code"]
        stubs = MINISTRY_REPORT_STUBS.get(code)
        if not stubs:
            failures.append(f"W{w}: MINISTRY_REPORT_STUBS missing or empty for {code!r}")

    _reverse(["super:ministry_report_stubs", "super:learning_institution_catalog_json"], failures)


def validate_phase_5(failures: list[str]) -> None:
    """Wedges 41–45: final institution types + federation + OneRoster glue."""
    _run_super_premium(5, failures)
    _django()

    from apps.platform_runtime.learning_institution_catalog import (
        INSTITUTION_TYPE_PACKS,
        MINISTRY_REPORT_STUBS,
    )

    for pack in INSTITUTION_TYPE_PACKS:
        w = int(pack["wedge"])
        if w < 41:
            continue
        code = pack["code"]
        if not MINISTRY_REPORT_STUBS.get(code):
            failures.append(f"W{w}: MINISTRY_REPORT_STUBS missing for {code!r}")

    # W44–45: OneRoster / OIDC — super_premium phase 5 already checked views; assert API module
    oneroster = REPO_ROOT / "apps" / "api" / "oneroster_views.py"
    if not oneroster.exists():
        failures.append("W44: missing apps/api/oneroster_views.py (expected OneRoster spine)")


def validate_phase(phase: int, failures: list[str]) -> None:
    if phase == 1:
        validate_phase_1(failures)
    elif phase == 2:
        validate_phase_2(failures)
    elif phase == 3:
        validate_phase_3(failures)
    elif phase == 4:
        validate_phase_4(failures)
    elif phase == 5:
        validate_phase_5(failures)
    else:
        failures.append(f"Unknown phase: {phase}")


def main() -> int:
    p = argparse.ArgumentParser(description="Validate wedges 1–45 by phase (10 per phase).")
    p.add_argument(
        "--phase",
        default="all",
        help="Phase 1–5 or all (default: all)",
    )
    args = p.parse_args()
    if args.phase == "all":
        phases = [1, 2, 3, 4, 5]
    else:
        try:
            phases = [int(args.phase)]
        except ValueError:
            print("Invalid --phase", file=sys.stderr)
            return 1
        if phases[0] not in (1, 2, 3, 4, 5):
            print("--phase must be 1-5 or all", file=sys.stderr)
            return 1

    failures: list[str] = []
    for ph in phases:
        validate_phase(ph, failures)

    if failures:
        print("validate_wedges_phase FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(
        "validate_wedges_phase PASSED (phases: "
        + ", ".join(str(x) for x in phases)
        + ")."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
