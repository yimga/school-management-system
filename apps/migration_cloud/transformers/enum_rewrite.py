"""Map source enum labels to canonical values."""

from __future__ import annotations

from typing import Any

from .base import Transformer, TransformerContext, TransformerError, register


class EnumRewrite(Transformer):
    def transform(self, value: Any, ctx: TransformerContext) -> str:
        raw = str(value or "").strip()
        if not raw:
            raise TransformerError("Empty enum value.")

        mapping = (ctx.options or {}).get("mapping") or {}
        if not isinstance(mapping, dict):
            raise TransformerError("Enum rewrite mapping must be a dictionary.")

        if raw in mapping:
            return str(mapping[raw])

        lowered = raw.lower()
        for key, mapped in mapping.items():
            if str(key).strip().lower() == lowered:
                return str(mapped)

        default = (ctx.options or {}).get("default")
        if default is not None:
            return str(default)
        return raw


register("enum_rewrite", EnumRewrite())
