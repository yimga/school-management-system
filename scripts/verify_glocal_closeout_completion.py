#!/usr/bin/env python
"""Glocal closeout completion gate — maps G-01..G-22 + NEW items to repo proofs."""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

CHECKS: list[tuple[str, str, callable]] = []


def check(name: str, desc: str):
    def deco(fn):
        CHECKS.append((name, desc, fn))
        return fn

    return deco


@check("G-06", "calendar_type_for_school reads calendar_system")
def _g06():
    from apps.platform_runtime.localization import calendar_type_for_school
    from types import SimpleNamespace

    school = SimpleNamespace(
        default_region=SimpleNamespace(calendar_system="islamic")
    )
    assert calendar_type_for_school(school) == "hijri"


@check("G-08-week", "school_week_for_date honors week_start_day")
def _g08_week():
    from datetime import date

    from apps.platform_runtime.localization import school_week_for_date

    # Sunday at year edge: Monday-anchored vs Sunday-anchored weeks diverge.
    d = date(2026, 1, 4)
    start = date(2026, 1, 1)
    monday_week = school_week_for_date(d, academic_year_start=start, week_start_day=0)
    sunday_week = school_week_for_date(d, academic_year_start=start, week_start_day=6)
    assert monday_week != sunday_week


@check("G-08-lbw", "low_bandwidth shell context + html attr")
def _g08_lbw():
    ui = (REPO / "apps/siteconfig/regional_ui.py").read_text(encoding="utf-8")
    assert "rmc_low_bandwidth" in ui
    portal = (REPO / "templates/portal_base.html").read_text(encoding="utf-8")
    cp = (REPO / "templates/control_plane_skeleton.html").read_text(encoding="utf-8")
    assert "data-rmc-low-bandwidth" in portal
    assert "data-rmc-low-bandwidth" in cp
    rtl = (REPO / "static/css/regional-rtl.css").read_text(encoding="utf-8")
    assert 'html[data-rmc-low-bandwidth="1"]' in rtl


@check("G-09", "format_school_date tenant patterns")
def _g09():
    from datetime import date

    from apps.platform_runtime.localization import format_school_date

    d = date(2026, 5, 18)
    assert format_school_date(d, date_format="DD/MM/YYYY") == "18/05/2026"
    assert format_school_date(d, date_format="YYYY-MM-DD") == "2026-05-18"


@check("G-10", "Evaluation.clean scale-aware")
def _g10():
    src = (REPO / "apps/evals/models.py").read_text(encoding="utf-8")
    assert "max_score_for_school" in src
    assert "score > 20" not in src


@check("G-11", "normalize_scale_id registry")
def _g11():
    from apps.evals.grading import normalize_scale_id

    assert normalize_scale_id("numeric_0_20") == "0-20"
    assert normalize_scale_id("uk_honours") == "uk-honours"
    assert normalize_scale_id("ib_0_7") == "ib-7"


@check("G-12", "UK honours + IB-7 scales")
def _g12():
    from apps.evals.grading import GRADING_SCALES

    assert "uk-honours" in GRADING_SCALES
    assert "ib-7" in GRADING_SCALES


@check("G-17", "recalculate_invoice uses tax_engine")
def _g17():
    src = (REPO / "apps/finance/services.py").read_text(encoding="utf-8")
    assert "resolve_vat_rate_fraction" in src


@check("G-18", "CountryMultiplier in billing")
def _g18():
    src = (REPO / "apps/billing/services.py").read_text(encoding="utf-8")
    assert "_resolve_country_multiplier_for_school" in src


@check("G-19", "Decimal FX module")
def _g19():
    from apps.finance.fx import exchange_rate_decimal

    assert exchange_rate_decimal("USD", "NGN") is not None


@check("G-20", "offline celery beat + LCA defaults")
def _g20():
    src = (REPO / "config/settings.py").read_text(encoding="utf-8")
    assert "process_offline_queues_due" in src
    packs = (REPO / "apps/siteconfig/tenant_config.py").read_text(encoding="utf-8")
    assert '"LCA"' in packs
    assert "offline_mode_default" in packs


@check("G-21", "request timeout middleware")
def _g21():
    src = (REPO / "config/middleware.py").read_text(encoding="utf-8")
    assert "class RequestTimeoutMiddleware" in src


@check("G-02", "unified language choices")
def _g02():
    from apps.siteconfig.unified_languages import get_unified_language_choices
    from django.conf import settings

    assert len(get_unified_language_choices()) == len(settings.LANGUAGES)


@check("G-04", "RTL locales he/fa/ur in LANGUAGES")
def _g04():
    from django.conf import settings

    codes = {c for c, _ in settings.LANGUAGES}
    assert {"he", "fa", "ur"}.issubset(codes)


@check("G-05", "text expansion CSS on shells")
def _g05():
    portal = (REPO / "templates/portal_base.html").read_text(encoding="utf-8")
    cp = (REPO / "templates/control_plane_skeleton.html").read_text(encoding="utf-8")
    assert "glocal-text-expansion.css" in portal
    assert "glocal-text-expansion.css" in cp


@check("G-14", "LGPD masking in privacy.py")
def _g14():
    src = (REPO / "apps/compliance/privacy.py").read_text(encoding="utf-8")
    assert "LGPD" in src
    assert "mask_pii_for_region" in src


@check("G-15", "export destination resolver")
def _g15():
    from apps.compliance.export_destination import resolve_export_destination_region
    from types import SimpleNamespace

    school = SimpleNamespace(data_region="eu-central-1")
    dest = resolve_export_destination_region(
        school=school, params={"destination_region": "us-east-1"}
    )
    assert dest == "us-east-1"


@check("G-16", "cross_border_export DATA_RESIDENCY_ENFORCE")
def _g16():
    src = (REPO / "apps/compliance/cross_border_export.py").read_text(encoding="utf-8")
    assert "DATA_RESIDENCY_ENFORCE" in src
    exports = (REPO / "apps/reports/compliance_exports.py").read_text(encoding="utf-8")
    assert "cross_border_export_blocked" in exports


@check("PIPL", "PIPL pack exists")
def _pipl():
    from apps.siteconfig.tenant_config import REGIONAL_POLICY_PACKS

    assert "PIPL" in REGIONAL_POLICY_PACKS


@check("POPIA", "POPIA pack exists")
def _popia():
    from apps.siteconfig.tenant_config import REGIONAL_POLICY_PACKS

    assert "POPIA" in REGIONAL_POLICY_PACKS


@check("G-22", "payment catalog model")
def _g22():
    mod = importlib.import_module("payment.models")
    assert hasattr(mod, "RegionalPaymentRailCatalog")


@check("G-07", "AcademicYear dual-calendar display helpers")
def _g07():
    src = (REPO / "apps/academics/models.py").read_text(encoding="utf-8")
    assert "format_start_date_display" in src
    assert "format_dual_calendar_date" in src


@check("G-07-registry", "ensure_calendar_system_registry command")
def _g07_registry():
    path = REPO / "apps/platform_runtime/management/commands/ensure_calendar_system_registry.py"
    assert path.is_file()


@check("G-07-tag", "format_dual_date_tenant template tag")
def _g07_tag():
    src = (REPO / "apps/siteconfig/templatetags/region_format.py").read_text(encoding="utf-8")
    assert "def format_dual_date_tenant" in src


@check("G-01-partial", "people create templates use {% trans %}")
def _g01_partial():
    for name in ("backend_teacher_create.html", "backend_student_create.html"):
        text = (REPO / "templates/people" / name).read_text(encoding="utf-8")
        assert "{% load i18n" in text
        assert text.count("{% trans ") >= 5, name


@check("G-01-burndown", "priority locale burndown script")
def _g01_burndown():
    assert (REPO / "scripts/burndown_glocal_priority_locales.py").is_file()


@check("G-22-seed", "seed_payment_rail_catalog command")
def _g22_seed():
    path = REPO / "payment/management/commands/seed_payment_rail_catalog.py"
    assert path.is_file()


@check("NEW-offline", "offline conflicts route + sync drip")
def _new_offline():
    urls = (REPO / "apps/portal/urls.py").read_text(encoding="utf-8")
    assert "offline/conflicts/" in urls
    sw = (REPO / "static/js/sync-manager.js").read_text(encoding="utf-8")
    assert "dripWhenWeak" in sw or "getDripModeSync" in sw


@check("NEW-compliance-docs", "DSAR + DPA operator docs")
def _new_docs():
    assert (REPO / "docs/DSAR_RUNBOOK.md").is_file()
    assert (REPO / "docs/DPA_TEMPLATE.md").is_file()


@check("SOT-matrix", "glocal SOT matrix empty backlog")
def _sot_matrix():
    data = json.loads(
        (REPO / "docs/generated/glocal_pressure_test_sot_matrix.json").read_text(
            encoding="utf-8"
        )
    )
    assert data.get("remaining_backlog") == []


def main() -> int:
    failures: list[str] = []
    for name, desc, fn in CHECKS:
        try:
            fn()
            print(f"OK  {name} {desc}")
        except Exception as exc:
            failures.append(f"{name}: {exc}")
            print(f"FAIL {name} {desc}: {exc}")

    scripts = [
        ("scripts/verify_i18n_catalog_fresh.py", []),
        ("scripts/scan_money_float.py", []),
        ("scripts/scan_locale_coverage.py", ["--compare"]),
        ("scripts/lint_north_star_i18n.py", ["--strict"]),
        ("scripts/verify_backend_base_shell_routing.py", []),
        ("scripts/verify_theme_visibility_platform.py", []),
        ("scripts/scan_pii_logging_smell.py", []),
        ("scripts/scan_tenant_queryset_safety.py", ["--compare"]),
        ("scripts/scan_tenant_isolation_marker_quality.py", ["--compare"]),
    ]
    gate_env = os.environ.copy()
    gate_env.setdefault("USE_FILE_LOGGING", "0")
    for script, extra in scripts:
        r = subprocess.run(
            [sys.executable, str(REPO / script), *extra],
            cwd=REPO,
            capture_output=True,
            text=True,
            env=gate_env,
        )
        if r.returncode != 0:
            failures.append(f"{script}: exit {r.returncode}")
            print(f"FAIL {script}")
            if r.stderr:
                print(r.stderr[-500:])
        else:
            print(f"OK  {script}")

    if failures:
        print("\nGlocal closeout gate: FAIL", len(failures))
        return 1
    print("\nGlocal closeout gate: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
