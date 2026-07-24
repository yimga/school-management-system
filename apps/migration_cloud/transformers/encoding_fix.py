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
        text = str(value)
        # UTF-8 bytes decoded as latin-1 leave tell-tale '\u00c3'/'\u00c2' sequences
        # (double-encoding mojibake). Re-encode as latin-1 and decode as utf-8
        # to recover the original characters ('caf\u00c3\u00a9' \u2192 'caf\u00e9'). Guard against
        # strings that don't round-trip and fall back to the original.
        if "\u00c3" in text or "\u00c2" in text:
            try:
                text = text.encode("latin-1").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
        return text.replace("\ufeff", "").strip()


register("encoding_fix", EncodingFix())
