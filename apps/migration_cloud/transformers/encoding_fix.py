"""Best-effort text cleanup transformer."""

from __future__ import annotations

from typing import Any

from .base import Transformer, TransformerContext, TransformerError, register


class EncodingFix(Transformer):
    def transform(self, value: Any, ctx: TransformerContext) -> str:
        if value is None:
            raise TransformerError("Empty text value.")
        if isinstance(value, bytes):
            encoding = str((ctx.hints or {}).get("encoding") or "utf-8")
            return value.decode(encoding, errors="replace").strip()
        return str(value).replace("\ufeff", "").strip()


register("encoding_fix", EncodingFix())
