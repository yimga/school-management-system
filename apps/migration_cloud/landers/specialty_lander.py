"""Specialty lander — persists a specialties / trades / streams catalog.

Real vocational / TVET schools export a ``specialties`` file (``NAME, CODE,
DEPARTMENT``) listing the trade programs they run — ELECTRICAL POWER SYSTEMS,
PLUMBING, BUILDING CONSTRUCTION. Before this lander that file had no home: it
mis-classified as the subjects catalog (both share name/code/department) and
landed as ``apps.academics.Subject`` rows — the WRONG entity — so students
could never be placed on a specialty and the trade structure was lost.

This lander lands each row into ``apps.academics.Specialty`` (create-if-missing,
deduped by ``(school, name)``) and provisions its REQUIRED parent
``apps.academics.Department`` the same reuse-by-(school,name) way the structure
lander does. ``Department.code`` / ``Specialty.code`` are GLOBALLY unique, so a
minted target-scoped code is used when the source code is already taken (or
absent); the human-meaningful source code (``EPS``) is kept when it is free and
preserved in the DynamicFieldValue engine otherwise — no data loss.

Canonical row shape::

    {"name": "ELECTRICAL POWER SYSTEMS", "code": "EPS",
     "department": "ELECTRICAL POWER", "description": ""}
"""

from __future__ import annotations

import re
from typing import Any, Iterator

from ._helpers import (
    get_or_create_named,
    mint_scoped_code,
    persist_dfv_extras,
    record_id_mapping,
    record_row_error,
)
from .base import Lander, LanderContext, LanderError, LanderResult, register

_NAME_MAX = 120  # magic-number-allow: Specialty/Department.name CharField max_length
_CODE_MAX = 30   # magic-number-allow: Specialty/Department.code CharField max_length


class SpecialtyLander(Lander):
    domain = "specialties"

    def land(
        self,
        *,
        canonical_rows: Iterator[dict[str, Any]],
        ctx: LanderContext,
    ) -> LanderResult:
        try:
            from apps.academics.models import Department, Specialty
        except ImportError as exc:
            raise LanderError(
                f"SpecialtyLander could not import Specialty/Department: {exc!s}"
            ) from exc

        result = LanderResult()
        for row in canonical_rows:
            name = (row.get("name") or "").strip()
            if not name:
                record_row_error(result, row, f"specialty row missing name: {row!r}")
                continue
            source_code = (row.get("code") or "").strip()
            # Trade files append the code to the department ("FASHION DESIGN - FD");
            # strip it so the department dedups cleanly. Fall back to the specialty
            # name when there is no department column (Specialty.department is
            # required, so every specialty must anchor on one).
            dept_name = _clean_department(
                (row.get("department") or "").strip(), source_code
            ) or name

            if ctx.dry_run:
                result.created += 1
                continue

            try:
                department, _ = get_or_create_named(
                    model=Department,
                    school=ctx.school,
                    name=dept_name[:_NAME_MAX],
                    create_kwargs=lambda dn=dept_name: {
                        "code": mint_scoped_code(
                            prefix="DPT", name=dn, school=ctx.school, model=Department
                        )
                    },
                    result=result,
                )
                specialty, created = get_or_create_named(
                    model=Specialty,
                    school=ctx.school,
                    name=name[:_NAME_MAX],
                    create_kwargs=lambda dep=department, nm=name, sc=source_code: {
                        "department": dep,
                        "code": _pick_code(
                            model=Specialty, source_code=sc, prefix="SPC",
                            name=nm, school=ctx.school,
                        ),
                    },
                    result=result,
                )
                if created:
                    result.created += 1
                else:
                    # Existing (school, name) specialty — reused, never mutated
                    # (the target's own config wins). Count as skipped, not created.
                    result.skipped += 1
                # Preserve the source code + description with no data loss.
                persist_dfv_extras(
                    ctx=ctx, entity_type="specialty", entity_id=specialty.pk,
                    extras={
                        "source_code": source_code,
                        "description": (row.get("description") or "").strip(),
                    },
                    result=result,
                )
                record_id_mapping(
                    ctx=ctx, legacy_id=(source_code or name),
                    canonical_obj=specialty, domain="specialties",
                )
            except Exception as exc:  # noqa: BLE001 — per-row quarantine
                record_row_error(
                    result, row,
                    f"specialty upsert failed for {name!r}: {type(exc).__name__}: {exc}",
                )
        return result


def _pick_code(*, model, source_code: str, prefix: str, name: str, school) -> str:
    """Keep the human-meaningful source code (``EPS``) when it is globally free;
    otherwise mint a target-scoped globally-unique code so the ``unique=True``
    column never collides with another school's row on a re-import / shared code."""
    sc = (source_code or "").strip()[:_CODE_MAX]
    if sc and not model.objects.filter(code=sc).exists():  # tenant-isolation-allow: code is a GLOBALLY-unique column; global existence check is intentional
        return sc
    return mint_scoped_code(prefix=prefix, name=name, school=school, model=model)


def _clean_department(dept: str, code: str) -> str:
    """Strip a trailing source code the department often carries
    ("FASHION DESIGN - FD" -> "FASHION DESIGN")."""
    d = (dept or "").strip()
    if not d:
        return d
    if code:
        suffix = f"- {code.strip()}".upper()
        if d.upper().endswith(suffix):
            return d[: -len(suffix)].strip(" -")
    # Generic: a trailing " - <2-5 uppercase letters>" is almost always a code.
    return re.sub(r"\s+-\s+[A-Z]{2,5}$", "", d).strip()


register("specialties", SpecialtyLander())
