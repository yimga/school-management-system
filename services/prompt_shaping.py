"""Viewport-aware prompt shaping (v4.00.0).

Cuts token weight on the way to LiteLLM based on the X-RMC-Viewport header
the edge Worker (or the JS bootstrap) injects. Returns a tuple of
``(shaped_prompt, system_messages, max_completion_tokens)`` that the
streaming gateway uses to construct the chat-completions payload.

The shaping rules are deliberately conservative — we never drop content
that could change the meaning of an instruction. We drop layout / schema
decoration on small viewports where the LLM only needs to emit the single
highest-probability action payload.

Wire path:
    request -> middleware reads X-RMC-Viewport -> stores on request.rmc_viewport
            -> view calls ``shape(prompt, viewport=request.rmc_viewport, ...)``
            -> services.ai_gateway streams the shaped prompt to LiteLLM
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

VALID_VIEWPORTS: frozenset[str] = frozenset({"A", "B", "C"})

# Compact system messages by viewport. The mobile (C) variant is the
# load-bearing one: it asks for a SINGLE action payload only.
SYSTEM_MESSAGES: dict[str, tuple[str, ...]] = {
    "A": (
        "You are the RunMyCampus copilot for desktop/4K command-center surfaces.",
        "You may emit rich, multi-component layouts in the structured response.",
        "Prefer streaming UI fragments that mount progressively.",
    ),
    "B": (
        "You are the RunMyCampus copilot for tablet / Chromebook surfaces.",
        "Prefer single-column, touch-friendly action cards.",
        "Hit targets must be at least 48px; avoid hover-dependent affordances.",
    ),
    "C": (
        "You are the RunMyCampus copilot for low-end mobile surfaces.",
        "Emit exactly ONE highest-probability action payload per response.",
        "No decorative layout. No multi-component schemas. No table views.",
    ),
}

MAX_COMPLETION_TOKENS: dict[str, int] = {
    "A": 2048,
    "B": 1024,
    "C": 384,
}


@dataclass(frozen=True)
class ShapedPrompt:
    prompt: str
    system_messages: tuple[str, ...]
    max_completion_tokens: int
    viewport: str


def normalize_viewport(raw: str | None) -> str:
    if not raw:
        return "A"
    upper = raw.strip().upper()
    return upper if upper in VALID_VIEWPORTS else "A"


def _strip_decorative_schema(prompt: str) -> str:
    """For viewport C: drop heavy schema/documentation blocks.

    Heuristic — segments delimited by ``<schema>...</schema>`` or
    ``<docs>...</docs>`` are removed. Plain instruction text is preserved.
    """
    out = prompt
    for tag in ("schema", "docs", "examples", "layout"):
        opener = f"<{tag}>"
        closer = f"</{tag}>"
        while opener in out and closer in out:
            start = out.find(opener)
            end = out.find(closer, start) + len(closer)
            if end <= start:
                break
            out = out[:start] + out[end:]
    return out.strip()


def shape(
    prompt: str,
    *,
    viewport: str | None = "A",
    extra_system: Iterable[str] | None = None,
) -> ShapedPrompt:
    vp = normalize_viewport(viewport)
    base = list(SYSTEM_MESSAGES[vp])
    if extra_system:
        base.extend(s for s in extra_system if s)
    body = prompt or ""
    if vp == "C":
        body = _strip_decorative_schema(body)
    return ShapedPrompt(
        prompt=body,
        system_messages=tuple(base),
        max_completion_tokens=MAX_COMPLETION_TOKENS[vp],
        viewport=vp,
    )
