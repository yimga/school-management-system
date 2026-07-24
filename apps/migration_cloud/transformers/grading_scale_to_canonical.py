"""Normalize vendor grading values with an optional scale map.

Resolution order (each step yields a *list* of candidate scales to try):
    1. ``ctx.options["scale_map"]`` or ``ctx.options["mapping"]`` —
       explicit per-mapping override (highest precedence).
    2. ``ctx.options["scale_slug"]`` or ``ctx.options["scale"]`` —
       looked up in ``apps.migration_cloud.country_profiles.GRADING_SCALES``
       (e.g. ``"UK_A_STAR"``, ``"FR_0_20"``, ``"NG_WAEC"``).
    3. ``ctx.hints["country"]`` / ``ctx.options["country"]`` — *all* of that
       country's ``grading_scales`` (per ``COUNTRY_PROFILES``), tried in order.

Value resolution:
    a. Discrete-key lookup across every candidate scale (letter grades, GPA
       labels, WAEC codes, …).
    b. Numeric fallback — comma-decimals are normalized (``'12,5'`` → ``12.5``)
       and a trailing ``%`` stripped before parsing. A value that exceeds the
       resolved scale's numeric maximum raises ``TransformerError`` so the
       orchestrator quarantines it instead of silently accepting an
       out-of-range grade (e.g. ``25`` on a ``/20`` scale, ``150`` on a
       percentage). See docs/MIGRATION_CLOUD_AUDIT_2026_07_24.md (B-4).
    c. Uppercased letter fallback (e.g. ``'a-'`` → ``'A-'``) when no scale is
       known and the value is not numeric.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from .base import Transformer, TransformerContext, TransformerError, register


class GradingScaleToCanonical(Transformer):
    def transform(self, value: Any, ctx: TransformerContext) -> str:
        raw = str(value or "").strip()
        if not raw:
            raise TransformerError("Empty grade value.")

        options = ctx.options or {}
        hints = ctx.hints or {}

        scales = self._resolve_scale_maps(options, hints)

        # (a) Discrete-key lookup across every candidate scale.
        for scale in scales:
            if raw in scale:
                return str(scale[raw])
            lowered = raw.lower()
            for key, mapped in scale.items():
                if str(key).strip().lower() == lowered:
                    return str(mapped)

        # (b) Numeric fallback with an out-of-range ceiling check.
        numeric = self._parse_numeric(raw)
        if numeric is not None:
            ceiling = self._numeric_ceiling(scales)
            if ceiling is not None and numeric > ceiling:
                raise TransformerError(
                    f"Grade {raw!r} exceeds the scale maximum of {ceiling}."
                )
            return str(numeric)

        # (c) Letter fallback.
        return raw.upper()

    def _resolve_scale_maps(
        self, options: dict[str, Any], hints: dict[str, Any]
    ) -> list[dict[str, str]]:
        """Return the ordered list of candidate scale maps to try."""
        explicit = options.get("scale_map") or options.get("mapping")
        if isinstance(explicit, dict) and explicit:
            return [{str(k): str(v) for k, v in explicit.items()}]

        slug = options.get("scale_slug") or options.get("scale")
        if slug:
            from apps.migration_cloud.country_profiles import grading_scale

            scale = grading_scale(str(slug))
            if scale:
                return [scale]

        country = hints.get("country") or options.get("country")
        if country:
            from apps.migration_cloud.country_profiles import grading_scale, resolved_country_profile

            profile = resolved_country_profile(str(country))
            if profile and profile.grading_scales:
                resolved = [grading_scale(s) for s in profile.grading_scales]
                scales = [s for s in resolved if s]
                if scales:
                    return scales
        return []

    @staticmethod
    def _parse_numeric(raw: str) -> Decimal | None:
        cleaned = raw.replace("%", "").strip()
        # Comma-as-decimal-separator (e.g. French '12,5'). Only convert a lone
        # comma with no dot so grouped values are never silently rescaled.
        if "," in cleaned and "." not in cleaned and cleaned.count(",") == 1:
            cleaned = cleaned.replace(",", ".")
        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return None

    @staticmethod
    def _numeric_ceiling(scales: list[dict[str, str]]) -> Decimal | None:
        """Highest numeric key across the candidate scales (the max grade)."""
        best: Decimal | None = None
        for scale in scales:
            for key in scale:
                try:
                    val = Decimal(str(key))
                except InvalidOperation:
                    continue
                if best is None or val > best:
                    best = val
        return best


register("grading_scale_to_canonical", GradingScaleToCanonical())
