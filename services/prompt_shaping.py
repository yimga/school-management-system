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
            -> view calls ``shape(prompt, viewport=request.rmc_viewport,
              country_code=..., institution_type=...)``
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
    "B": 1024,  # magic-number-allow: token-budget-size
    "C": 384,  # magic-number-allow: token-budget-size
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


def institution_terminology_system_lines(
    country_code: str | None,
    institution_type: str | None = None,
) -> tuple[str, ...]:
    """
    Build LiteLLM system-message lines from the country governance matrix.

    Pulls ``local_terminology`` (and optional ``school_type_labels`` match for
    ``institution_type``) via ``apps.governance.country_matrix_service``.
    """
    from apps.governance.country_matrix_service import get_matrix_row

    row = get_matrix_row(country_code)
    if not row:
        return ()

    lines: list[str] = []
    name_en = row.get("name_en") or str(country_code or "").upper()
    if name_en:
        lines.append(
            f"Institution locale: {name_en} ({str(country_code or '').upper()})."
        )

    local_term = row.get("local_terminology")
    if not isinstance(local_term, dict):
        return tuple(lines)

    for key in ("student", "teacher", "principal", "term", "report_card", "grade_level"):
        entry = local_term.get(key)
        if not isinstance(entry, dict):
            continue
        label = entry.get("en")
        if not label:
            for value in entry.values():
                if isinstance(value, str) and value.strip():
                    label = value.strip()
                    break
        if label:
            human_key = key.replace("_", " ")
            lines.append(f"Prefer local term for {human_key}: {label}.")

    if institution_type:
        school_types = local_term.get("school_type_labels")
        if isinstance(school_types, list):
            for item in school_types:
                if not isinstance(item, dict):
                    continue
                if str(item.get("code", "")).lower() == str(institution_type).lower():
                    label = item.get("label") or institution_type
                    lines.append(f"Institution type context: {label}.")
                    break

    return tuple(lines)


def shape(
    prompt: str,
    *,
    viewport: str | None = "A",
    extra_system: Iterable[str] | None = None,
    country_code: str | None = None,
    institution_type: str | None = None,
) -> ShapedPrompt:
    vp = normalize_viewport(viewport)
    base = list(SYSTEM_MESSAGES[vp])
    base.extend(
        institution_terminology_system_lines(country_code, institution_type=institution_type)
    )
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
