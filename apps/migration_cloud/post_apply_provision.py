"""Post-apply structural gap-fill (S) — "preload by education type".

After a bundle applies, a real migration has landed the school's PEOPLE and
CATALOG (students, staff, specialties, subjects) — but rarely the structural
scaffolding a running school needs: an academic year, the default
department/specialty every ``FeePlan``/``SubjectAssignment`` FK points at, the
cycle nodes for the school's education type, and the Classroom×Subject×Term
teaching grid. This module fills ONLY those gaps.

Design constraints (local-first, meet each school at their level):

* **Never invent trades/subjects a seed doesn't contain.** The country pack
  carries no trade or subject lists for a vocational sector — those come from
  the upload itself (landed as ``Specialty``/``Subject`` rows) or the school's
  Education-DNA profile, not from here. Gap-fill scaffolds *structure*, not a
  fabricated catalog.
* **Idempotent + deduped against what landed.** Every engine it calls is
  re-runnable (``ensure_*`` / ``get_or_create`` / manual ``filter().first()``
  guards), so a tenant that exported a complete structure gets nothing new and a
  re-applied bundle never duplicates a row.
* **Everything it creates is admin-editable.** The default academic year is a
  named row ("2025/2026") the admin can rename or re-date; the General
  department can be renamed. A default, never a lock.

Invoked from the tail of ``orchestrator._apply_bundle_inner`` on a real
(non-dry-run) apply, gated so it only fires when the bundle actually landed
roster/catalog data — never on a finance-only or empty apply. Best-effort: a
failure here is logged and recorded on the bundle summary, never raised into
the apply.
"""

from __future__ import annotations

import datetime as _dt
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Platform default (layer 7 of the config contract) used ONLY when no academic
# year exists AND the tenant has set no ``default_academic_year_name`` override.
# A first-run default the admin edits afterward — see ``_ensure_academic_year``.
_DEFAULT_ACADEMIC_YEAR_NAME = "2025/2026"
# First-run academic-calendar defaults (Sept start → Aug end) for a freshly
# minted year when the upload carried no session file. Admin-editable afterward.
_ACADEMIC_YEAR_START_MONTH = 9
_ACADEMIC_YEAR_END_MONTH = 8

# Domains whose landing means the bundle carried real roster/catalog data worth
# scaffolding structure around. A finance-only / grades-only / empty apply does
# not trigger gap-fill.
_STRUCTURAL_DOMAINS = frozenset({
    "students", "staff", "specialties", "sections", "structure",
    "academics", "academic_sessions", "alumni", "enrollment",
})


def _year_bounds_from_name(name: str) -> tuple[_dt.date, _dt.date]:
    """Derive a (start, end) date window from an academic-year NAME.

    "2025/2026" / "2025-2026" → Sept 1 2025 … Aug 31 2026. A single "2025" →
    Sept 1 2025 … Aug 31 2026. Unparseable → a one-year window ending a year on
    from the first 4-digit run, or (as a last resort) a neutral pair the admin
    edits. Dates are always a first-run default, never authoritative.
    """
    years = [int(y) for y in re.findall(r"\d{4}", name or "")]
    if years:
        start_year = years[0]
        end_year = years[1] if len(years) > 1 else start_year + 1
    else:
        # No parseable year in the name — fall back to a neutral window whose
        # exact value does not matter (admin edits it); keep it internally
        # consistent (start before end).
        start_year, end_year = 2025, 2026
    start = _dt.date(start_year, _ACADEMIC_YEAR_START_MONTH, 1)
    # Aug has 31 days; keep the end just inside the month for every locale.
    end = _dt.date(end_year, _ACADEMIC_YEAR_END_MONTH, 28)
    return start, end


def ensure_default_academic_year(school):
    """Resolve the school's academic year, creating a default only if none exists.

    Never overrides an existing year (the upload's own session file, or a prior
    run, wins). When the school has NO year at all, mints one named from the
    tenant override ``settings['default_academic_year_name']`` or the platform
    default. Returns ``(year, created)`` or ``(None, False)`` when the school is
    missing. Shared by the student lander (which needs a year to scaffold a
    classroom during apply) and the gap-fill below, so both converge on the same
    row.

    Delegates the actual year window to the shared, COUNTRY-AWARE
    :func:`apps.academics.structure_provisioning.ensure_academic_year` so a
    migrated US school gets an August-start year and a Cameroonian one a
    September-start year — this path previously hardcoded Sept 1 → Aug 28 for
    every country regardless of its RegionConfig. The tenant name override is
    still honored (passed through as the year name).
    """
    if school is None:
        return None, False
    from apps.academics.structure_provisioning import ensure_academic_year

    settings_map = getattr(school, "settings", None) or {}
    name = (settings_map.get("default_academic_year_name") or _DEFAULT_ACADEMIC_YEAR_NAME).strip()
    return ensure_academic_year(school, name=name)


def _derive_school_type_codes(school) -> list[str] | None:
    """Mirror ``schools.tasks._do_provision``: read the school's declared type(s)
    from ``settings['school_type']`` / ``['school_type_raw']`` so the structure
    engine scaffolds only the relevant cycles. Returns ``None`` (all pack types)
    when the school never declared one."""
    settings_map = getattr(school, "settings", None) or {}
    raw = settings_map.get("school_type") or settings_map.get("school_type_raw") or ""
    if not isinstance(raw, str):
        return None
    codes = [c.strip().lower() for c in re.split(r"[,|]", raw) if c.strip()]
    return codes or None


def _landed_structural_data(outcomes) -> bool:
    """True when at least one applied artifact was a roster/catalog domain."""
    for outcome in outcomes or []:
        domain = getattr(outcome, "domain", "") or ""
        if domain in _STRUCTURAL_DOMAINS:
            return True
    return False


def _gap_fill_enabled(school) -> bool:
    """Tenant opt-out (default ON per the approved design). A school can disable
    structural gap-fill via ``settings['migration_gap_fill_provisioning'] =
    False`` — local-first: some tenants want ONLY exactly what they uploaded."""
    settings_map = getattr(school, "settings", None) or {}
    return bool(settings_map.get("migration_gap_fill_provisioning", True))


def _provision_country_baseline_for_bundle(school) -> dict[str, Any]:
    """Shared country-aware baseline used by mid-apply and post-apply hooks."""
    from apps.academics.structure_provisioning import provision_country_baseline

    year, year_created = ensure_default_academic_year(school)
    if year is None:
        return {"skipped": "no_academic_year"}

    summary = provision_country_baseline(
        school,
        academic_year=year,
        school_type_codes=_derive_school_type_codes(school),
    )
    if isinstance(summary.get("academic_year"), dict):
        summary["academic_year"]["created"] = bool(year_created)
    return summary


def provision_structure_before_dependent_domains(
    *, bundle, dry_run: bool = False
) -> dict[str, Any]:
    """Scaffold teaching grid BEFORE grades/attendance/finance wave.

    Post-apply gap-fill runs after wave 3, so the grades lander historically
    quarantined every row with "no subject assignment" even though repair from
    the UI re-ran the same wave order. This mid-apply hook runs after waves
    0–2 (students, enrollment, catalog) so dependent domains can resolve FKs.
    Idempotent and best-effort — never raises into the apply.
    """
    if dry_run:
        return {"skipped": "dry_run"}
    school = getattr(bundle, "school", None)
    if school is None:
        return {"skipped": "no_school"}
    if not _gap_fill_enabled(school):
        return {"skipped": "disabled"}

    summary: dict[str, Any] = {"phase": "before_dependent_domains"}
    try:
        summary.update(_provision_country_baseline_for_bundle(school))
    except Exception as exc:  # noqa: BLE001 — provisioning must never break apply
        logger.warning(
            "mid-apply structure provisioning failed for bundle %s: %s",
            getattr(bundle, "pk", "?"),
            exc,
            exc_info=True,
        )
        summary["error"] = f"{type(exc).__name__}: {exc}"
    return summary


def gap_fill_after_apply(*, bundle, outcomes, dry_run: bool = False) -> dict[str, Any]:
    """Scaffold the structural gaps a running school needs after a real apply.

    Returns a summary dict (recorded on the bundle by the orchestrator). Every
    step is best-effort and idempotent; a failure is captured in the summary,
    never raised.
    """
    if dry_run:
        return {"skipped": "dry_run"}
    school = getattr(bundle, "school", None)
    if school is None:
        return {"skipped": "no_school"}
    if not _gap_fill_enabled(school):
        return {"skipped": "disabled"}
    if not _landed_structural_data(outcomes):
        return {"skipped": "no_structural_data"}

    summary: dict[str, Any] = {"phase": "after_apply"}
    try:
        summary.update(_provision_country_baseline_for_bundle(school))
    except Exception as exc:  # noqa: BLE001 — gap-fill must never break a successful apply
        logger.warning(
            "gap-fill provisioning failed for bundle %s: %s",
            getattr(bundle, "pk", "?"),
            exc,
            exc_info=True,
        )
        summary["error"] = f"{type(exc).__name__}: {exc}"

    try:
        from apps.migration_cloud.teaching_graph import (
            ensure_teaching_graph_closure_for_bundle,
        )

        summary["teaching_graph_closure"] = ensure_teaching_graph_closure_for_bundle(
            bundle, dry_run=False
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "teaching graph closure failed for bundle %s: %s",
            getattr(bundle, "pk", "?"),
            exc,
            exc_info=True,
        )
        summary["teaching_graph_error"] = f"{type(exc).__name__}: {exc}"

    return summary
