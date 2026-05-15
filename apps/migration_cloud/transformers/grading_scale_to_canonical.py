"""Normalize vendor grading values with an optional scale map.

Resolution order:
    1. ``ctx.options["scale_map"]`` or ``ctx.options["mapping"]`` —
       explicit per-mapping override (highest precedence).
    2. ``ctx.options["scale_slug"]`` or ``ctx.options["scale"]`` —
       looked up in ``apps.migration_cloud.country_profiles.GRADING_SCALES``
       (e.g. ``"UK_A_STAR"``, ``"FR_0_20"``, ``"NG_WAEC"``).
    3. ``ctx.hints["country"]`` — first scale from that country's
       ``grading_scales`` tuple (per ``COUNTRY_PROFILES``).
    4. Numeric fallback (parse as Decimal, e.g. "85.5" → "85.5").
    5. Uppercased letter fallback (e.g. "a-" → "A-").
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

        scale = self._resolve_scale_map(options, hints)
        if scale:
            if raw in scale:
                return str(scale[raw])
            lowered = raw.lower()
            for key, mapped in scale.items():
                if str(key).strip().lower() == lowered:
                    return str(mapped)

        try:
            return str(Decimal(raw.replace("%", "")))
        except InvalidOperation:
            return raw.upper()

    def _resolve_scale_map(self, options: dict[str, Any], hints: dict[str, Any]) -> dict[str, str] | None:
        explicit = options.get("scale_map") or options.get("mapping")
        if isinstance(explicit, dict) and explicit:
            return {str(k): str(v) for k, v in explicit.items()}

        slug = options.get("scale_slug") or options.get("scale")
        if slug:
            from apps.migration_cloud.country_profiles import grading_scale

            scale = grading_scale(str(slug))
            if scale:
                return scale

        country = hints.get("country") or options.get("country")
        if country:
            from apps.migration_cloud.country_profiles import grading_scale, resolved_country_profile

            profile = resolved_country_profile(str(country))
            if profile and profile.grading_scales:
                scale = grading_scale(profile.grading_scales[0])
                if scale:
                    return scale
        return None


register("grading_scale_to_canonical", GradingScaleToCanonical())
