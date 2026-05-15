"""Attendance-code rewriter.

Different countries / vendors use very different codes for the same
canonical status. The canonical platform set is::

    present | absent | late | excused | holiday | suspended

Dialects shipped in ``apps.migration_cloud.country_profiles.ATTENDANCE_DIALECTS``:

    - ``letters_paie``     (US/UK/CA P-A-T-E default)
    - ``letters_de``       (German Anwesend/Abwesend)
    - ``letters_fr``       (French Présent/Absent)
    - ``letters_es_pt``    (Spanish/Portuguese Presente/Ausente)
    - ``cjk_attendance``   (CJK 出席/欠席/遅刻)
    - ``letters_in``       (Indian English + Hindi)

Resolution order:
    1. ``ctx.options["mapping"]`` — explicit per-mapping override.
    2. ``ctx.options["dialect"]`` — slug from ``ATTENDANCE_DIALECTS``.
    3. ``ctx.hints["country"]`` → country profile → ``attendance_code_dialect``.
    4. ``letters_paie`` default.
"""

from __future__ import annotations

from typing import Any

from .base import Transformer, TransformerContext, TransformerError, register

_CANONICAL = ("present", "absent", "late", "excused", "holiday", "suspended")


class AttendanceCodeRewrite(Transformer):
    def transform(self, value: Any, ctx: TransformerContext) -> str:
        raw = str(value or "").strip()
        if not raw:
            raise TransformerError("Empty attendance code.")
        normalised = raw.upper().strip()

        dialect = self._resolve_dialect(ctx)
        if dialect is None:
            return _canonical_or_raise(normalised, raw)

        if raw in dialect:
            return dialect[raw]
        if normalised in dialect:
            return dialect[normalised]
        # Lowercase / casefold last
        for k, v in dialect.items():
            if str(k).casefold() == raw.casefold():
                return v
        return _canonical_or_raise(normalised, raw)

    def _resolve_dialect(self, ctx: TransformerContext) -> dict[str, str] | None:
        options = ctx.options or {}
        hints = ctx.hints or {}

        explicit = options.get("mapping")
        if isinstance(explicit, dict) and explicit:
            return {str(k): str(v) for k, v in explicit.items()}

        slug = options.get("dialect")
        if slug:
            from apps.migration_cloud.country_profiles import attendance_dialect
            return attendance_dialect(str(slug))

        country = hints.get("country") or options.get("country")
        if country:
            from apps.migration_cloud.country_profiles import (
                attendance_dialect, resolved_country_profile,
            )
            profile = resolved_country_profile(str(country))
            if profile is not None:
                return attendance_dialect(profile.attendance_code_dialect)
        return None


def _canonical_or_raise(normalised: str, raw: str) -> str:
    lower = raw.strip().lower()
    if lower in _CANONICAL:
        return lower
    if normalised in {"PRESENT", "P", "PR"}:
        return "present"
    if normalised in {"ABSENT", "A", "AB"}:
        return "absent"
    if normalised in {"LATE", "L", "T", "TR"}:
        return "late"
    if normalised in {"EXCUSED", "E", "EX"}:
        return "excused"
    if normalised in {"HOLIDAY", "H", "HOL"}:
        return "holiday"
    if normalised in {"SUSPENDED", "S", "SUS"}:
        return "suspended"
    raise TransformerError(f"Unrecognised attendance code {raw!r}; supply a dialect or mapping.")


register("attendance_code_rewrite", AttendanceCodeRewrite())
