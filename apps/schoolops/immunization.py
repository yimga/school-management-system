"""W24 — structured immunization compute service (pure, no side effects).

Reads the tenant's :class:`~apps.schoolops.models.VaccineRequirement` schedule
and a student's :class:`~apps.schoolops.models.ImmunizationRecord` doses and
reports missing / exempt / compliant status. There are NO notifications and NO
writes here — the alert sweep in :mod:`apps.schoolops.tasks` consumes this.

Vaccine codes are normalized (strip + upper) on both sides so a requirement
"MMR" matches a record "mmr". Nothing is hardcoded: every threshold comes from
the requirement rows.
"""

from __future__ import annotations

from typing import Any


def normalize_vaccine_code(value) -> str:
    """Canonical matching form for a vaccine code: strip + upper."""
    return (value or "").strip().upper()


def resolve_vaccine_requirements(school) -> list:
    """The school's active :class:`VaccineRequirement` rows (school-scoped).

    Returns an empty list when ``school`` is falsy. A school with zero rows has
    no requirements — the caller treats that as "nothing to enforce".
    """
    if school is None:
        return []
    from apps.schoolops.models import VaccineRequirement

    return list(
        VaccineRequirement.objects.filter(school=school, is_active=True)
    )


def compute_missing_immunizations(student, school) -> dict[str, Any]:
    """Compare a student's doses to the school's requirement schedule.

    Returns::

        {
          "is_compliant": bool,
          "requirements_configured": bool,
          "missing": [{"vaccine", "doses_required", "doses_on_record"}, ...],
          "exempt":  [{"vaccine", "doses_required"}, ...],
        }

    Rules:
      * No active requirements configured -> ``requirements_configured`` False,
        ``is_compliant`` True (nothing to enforce).
      * An exemption on ANY of the student's records for a required vaccine
        marks that vaccine satisfied — it is listed under ``exempt``, never
        ``missing``.
      * Otherwise the vaccine is satisfied when the DISTINCT dose numbers on
        record reach ``doses_required`` — the same dose recorded twice counts
        once.
    """
    requirements = resolve_vaccine_requirements(school)
    if not requirements:
        return {
            "is_compliant": True,
            "requirements_configured": False,
            "missing": [],
            "exempt": [],
        }

    # Aggregate the student's records by normalized vaccine code. Count the
    # DISTINCT dose numbers, not the rows: nothing stops the same dose being
    # saved twice (a double-submitted form, or a correction entered as a new
    # row rather than an edit), and counting rows would mark a one-dose child
    # compliant against a two-dose requirement and silence the guardian alert.
    doses_by_code: dict[str, set[int]] = {}
    exempt_codes: set[str] = set()
    if student is not None:
        from apps.schoolops.models import ImmunizationRecord

        records = ImmunizationRecord.objects.filter(student=student, school=school)
        for rec in records:
            code = normalize_vaccine_code(rec.vaccine)
            if not code:
                continue
            if (rec.exemption_type or "").strip():
                exempt_codes.add(code)
            try:
                dose = int(rec.dose_number or 1)
            except (TypeError, ValueError):
                dose = 1
            doses_by_code.setdefault(code, set()).add(dose)

    # Merge requirements by normalized code (defensive against duplicate rows;
    # keep the stricter dose count if two rows collide on the same code).
    required_by_code: dict[str, int] = {}
    for req in requirements:
        code = normalize_vaccine_code(req.vaccine)
        if not code:
            continue
        need = int(req.doses_required or 0)
        required_by_code[code] = max(required_by_code.get(code, 0), need)

    missing: list[dict[str, Any]] = []
    exempt: list[dict[str, Any]] = []
    for code, need in sorted(required_by_code.items()):
        if code in exempt_codes:
            exempt.append({"vaccine": code, "doses_required": need})
            continue
        on_record = len(doses_by_code.get(code, set()))
        if on_record >= need:
            continue
        missing.append(
            {
                "vaccine": code,
                "doses_required": need,
                "doses_on_record": on_record,
            }
        )

    return {
        "is_compliant": not missing,
        "requirements_configured": True,
        "missing": missing,
        "exempt": exempt,
    }
