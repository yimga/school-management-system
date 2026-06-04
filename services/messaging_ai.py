"""AI leverage for the messaging/communication system (audit AI roadmap).

The platform has a mature, fully-guardrailed AI gateway (``services.ai_gateway``
→ LiteLLM → Ollama → deterministic rules, with PII redaction + per-tenant
quota + permissions) and a mature multi-channel messaging system — but until
now they were almost entirely disconnected. This module is the bridge.

Every function fails CLOSED: on any error / disabled AI / empty result it
returns a safe fallback (``""`` / ``None`` / the original text / a rules-based
answer) so messaging never depends on AI for correctness. It reuses EXISTING
``TaskType`` values (no gateway enum churn) and routes through the gateway so
PII redaction + quota + circuit-breaker all apply automatically.

This module lives under ``services/`` (not ``apps/``), so it may call
``services.ai_gateway`` directly — the ``scan_ai_gateway_boundary`` gate only
governs ``apps/`` code, which must call these helpers instead.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)

_MAX_PROMPT_CHARS = 4000
_MAX_OUT_CHARS = 2000


def _safe_invoke(task_type, prompt: str, *, school=None, user_query: str = "") -> tuple[str, dict]:
    """Route a prompt through the AI gateway; never raise."""
    try:
        from services.ai_gateway import invoke
    except ImportError:
        return "", {"error": "ai_gateway unavailable"}
    try:
        result, meta = invoke(
            task_type,
            prompt[:_MAX_PROMPT_CHARS],
            user_query=user_query,
            metadata={
                "school_id": str(getattr(school, "id", "") or ""),
                "tenant_id": str(getattr(school, "id", "") or ""),
                "sensitivity_class": "medium",
            },
        )
    except Exception as exc:  # noqa: BLE001 — closed-fail
        logger.warning("messaging_ai: gateway raised %s", type(exc).__name__)
        return "", {"error": str(exc)[:200]}
    text = (result or "").strip() if isinstance(result, str) else ""
    return text[:_MAX_OUT_CHARS], (meta or {})


# ── 1. Announcement / tone drafting ─────────────────────────────────────────
def draft_announcement(
    *,
    school,
    audience: str,
    intent: str,
    key_facts: Iterable[str] | None = None,
    tone: str = "warm",
) -> tuple[str, dict]:
    """Draft a school announcement to ``audience`` (parents/staff/students).

    Draft-only — the caller reviews before sending. ``tone`` ∈ warm/formal/
    urgent. Returns ("", meta) on failure so the UI offers "write your own".
    """
    facts = "\n".join(f"- {f}" for f in (key_facts or []) if f) or "- (no extra facts)"
    tone = (tone or "warm").lower()
    prompt = (
        f"Draft a {tone}, clear announcement from {getattr(school, 'name', 'the school')} "
        f"to {audience}.\nIntent: {intent}\nKey facts:\n{facts}\n\n"
        "120-180 words, plain prose, no headings or bullet lists, no signature "
        "line. Lead with the most important information. Do not invent facts not "
        "listed above.\n"
    )
    try:
        from services.ai_gateway import TaskType
    except ImportError:
        return "", {"error": "TaskType unavailable"}
    return _safe_invoke(TaskType.TEACHER_COMMS_DRAFT, prompt, school=school, user_query=intent)


# ── 2. Subject-line assist ──────────────────────────────────────────────────
def suggest_subject_lines(*, school, body_excerpt: str, count: int = 3) -> list[str]:
    """Return up to ``count`` candidate subject lines for an email body.

    Empty list on failure (caller keeps their own subject)."""
    n = max(1, min(int(count or 3), 5))
    prompt = (
        f"Suggest {n} concise, non-spammy email subject lines for this message. "
        "Avoid ALL CAPS, excessive punctuation, and spam-trigger words. One per "
        f"line, no numbering.\n\nMessage:\n{body_excerpt[:1500]}\n"
    )
    try:
        from services.ai_gateway import TaskType
    except ImportError:
        return []
    text, _meta = _safe_invoke(TaskType.NARRATIVE, prompt, school=school)
    if not text:
        return []
    lines = [
        ln.strip(" -*0123456789.").strip()
        for ln in text.splitlines()
        if ln.strip()
    ]
    return [ln for ln in lines if ln][:n]


# ── 3. Accessibility / plain-language rewrite ───────────────────────────────
def rewrite_plain_language(*, school, text: str, reading_level: str = "grade 6") -> tuple[str, dict]:
    """Rewrite ``text`` at a target reading level (equity for ESL/low-literacy).

    Returns (original_text, meta) on failure — never drops the message."""
    if not (text or "").strip():
        return "", {"error": "empty"}
    prompt = (
        f"Rewrite the following message in plain language at a {reading_level} "
        "reading level. Keep ALL facts, names, dates, and amounts exactly. Use "
        "short sentences and common words. Do not add new information.\n\n"
        f"Message:\n{text[:2000]}\n"
    )
    try:
        from services.ai_gateway import TaskType
    except ImportError:
        return text, {"error": "TaskType unavailable"}
    out, meta = _safe_invoke(TaskType.NARRATIVE, prompt, school=school)
    return (out or text), meta


# ── 4. Inbound intent classification (WhatsApp / email reply triage) ─────────
def classify_parent_intent(
    *,
    school,
    body: str,
    allowlist: Iterable[str],
) -> Optional[str]:
    """Classify a free-text inbound message into one of ``allowlist`` intents.

    Used as the AI fallback when keyword routing yields UNKNOWN (the gap the
    WhatsApp Parent OS docstring promised but never wired). Returns the chosen
    intent string (guaranteed ∈ allowlist) or None when the model is
    unavailable / unsure — the caller then keeps its safe default."""
    allowed = [str(a).strip() for a in allowlist if str(a).strip()]
    if not allowed or not (body or "").strip():
        return None
    prompt = (
        "Classify the parent's message into EXACTLY ONE of these intent codes: "
        f"{', '.join(allowed)}.\nReply with ONLY the single matching code and "
        "nothing else. If none clearly fits, reply UNKNOWN.\n\n"
        f"Message:\n{body[:600]}\n"
    )
    try:
        from services.ai_gateway import TaskType
    except ImportError:
        return None
    text, _meta = _safe_invoke(TaskType.SUPPORT_SUGGEST, prompt, school=school, user_query=body[:120])
    if not text:
        return None
    # Be forgiving: pick the first allowed code that appears in the response.
    norm = text.strip().lower()
    for code in allowed:
        if code.lower() == norm or code.lower() in norm.split():
            return code
    for code in allowed:
        if code.lower() in norm:
            return code
    return None


# ── 5. Smart channel selection (rules-first, no AI dependency) ──────────────
def choose_channel(
    *,
    urgency: str = "routine",
    available: Iterable[str] | None = None,
    recipient_prefs: dict | None = None,
    quiet_hours: bool = False,
) -> str:
    """Pick the best delivery channel deterministically.

    Urgent → prefer SMS/WhatsApp (instant); routine → prefer email (rich,
    cheap). Honors recipient opt-outs + quiet hours. Pure function, no AI —
    correctness never depends on a model. Returns a channel string or
    "email" as the universal fallback."""
    avail = [c.lower() for c in (available or ["email", "sms", "whatsapp", "push"])]
    prefs = recipient_prefs or {}

    def _ok(ch: str) -> bool:
        return ch in avail and prefs.get(f"{ch}_opt_out") is not True

    urgency = (urgency or "routine").lower()
    if urgency in ("urgent", "critical", "emergency") and not quiet_hours:
        for ch in ("whatsapp", "sms", "push", "email"):
            if _ok(ch):
                return ch
    # Routine (or quiet hours): non-intrusive channels first.
    for ch in ("email", "push", "whatsapp", "sms"):
        if _ok(ch):
            return ch
    return "email"


# ── 6. Outbound translation ─────────────────────────────────────────────────
_LANG_NAMES = {
    "en": "English", "fr": "French", "es": "Spanish", "pt": "Portuguese",
    "ar": "Arabic", "sw": "Swahili", "yo": "Yoruba", "ha": "Hausa",
    "de": "German", "zh": "Chinese", "hi": "Hindi", "ja": "Japanese",
}


def translate_message(*, school, body: str, target_locale: str, source_locale: str = "en") -> tuple[str, dict]:
    """Translate an outbound message into the recipient's language.

    Returns (original, meta) on failure so the message still goes out in the
    source language. Caller should restrict this to non-legal/non-payment copy
    (mistranslation risk) and skip when target == source."""
    tgt = (target_locale or "").split("-")[0].lower()
    src = (source_locale or "en").split("-")[0].lower()
    if not (body or "").strip() or not tgt or tgt == src:
        return body, {"skipped": True}
    tgt_name = _LANG_NAMES.get(tgt, tgt)
    prompt = (
        f"Translate the following message into {tgt_name}. Keep ALL names, "
        "dates, amounts, and links EXACTLY as written. Preserve tone. Output "
        "only the translation, nothing else.\n\n"
        f"Message:\n{body[:1800]}\n"
    )
    try:
        from services.ai_gateway import TaskType
    except ImportError:
        return body, {"error": "TaskType unavailable"}
    out, meta = _safe_invoke(TaskType.NARRATIVE, prompt, school=school)
    return (out or body), meta


# ── 7. Reply suggestions for staff inbox ────────────────────────────────────
def suggest_replies(*, school, inbound_text: str, context: str = "", count: int = 3) -> list[str]:
    """Suggest 2-3 short staff replies to an inbound parent message.

    Drafts only — a human sends. Empty list on failure."""
    n = max(1, min(int(count or 3), 4))
    prompt = (
        f"A parent sent a school office this message:\n\"{inbound_text[:800]}\"\n"
        + (f"\nContext: {context[:400]}\n" if context else "")
        + f"\nSuggest {n} brief, warm, professional reply options the office "
        "could send. One per line, no numbering, each under 40 words.\n"
    )
    try:
        from services.ai_gateway import TaskType
    except ImportError:
        return []
    text, _meta = _safe_invoke(TaskType.SUPPORT_SUGGEST, prompt, school=school)
    if not text:
        return []
    lines = [ln.strip(" -*0123456789.").strip() for ln in text.splitlines() if ln.strip()]
    return [ln for ln in lines if ln][:n]


# ── 8. Safeguarding signal detection (human-in-loop, never auto-acts) ────────
def detect_safeguarding_signal(*, school, body: str) -> dict:
    """Flag concerning inbound content for DSL review (audit AI roadmap #8).

    Returns ``{"flag": bool, "severity": "none|review|urgent", "rationale": str}``.
    HIGH-RECALL by design — false positives are reviewed by a human; false
    negatives are dangerous. NEVER auto-replies with advice and NEVER acts
    autonomously: the caller routes a flagged message to a human DSL. Returns
    a no-flag result on any AI error (the keyword backstop in the caller still
    applies)."""
    safe = {"flag": False, "severity": "none", "rationale": ""}
    if not (body or "").strip():
        return safe
    prompt = (
        "You are a safeguarding triage assistant for a school. Decide if the "
        "following inbound message contains any signal of a child-safety "
        "concern (self-harm, abuse, neglect, danger, distress). Reply on ONE "
        "line as: SEVERITY|reason  where SEVERITY is none, review, or urgent. "
        "Bias toward 'review' if unsure. Do NOT give advice.\n\n"
        f"Message:\n{body[:800]}\n"
    )
    try:
        from services.ai_gateway import TaskType
    except ImportError:
        return safe
    text, _meta = _safe_invoke(TaskType.RISK_EXPLAIN, prompt, school=school)
    if not text:
        return safe
    head = text.strip().splitlines()[0]
    sev, _, reason = head.partition("|")
    sev = sev.strip().lower()
    if sev not in ("none", "review", "urgent"):
        sev = "review" if any(w in text.lower() for w in ("harm", "abuse", "danger", "hurt")) else "none"
    return {
        "flag": sev in ("review", "urgent"),
        "severity": sev,
        "rationale": reason.strip()[:200],
    }


# ── 9. AI digest summary primitive ──────────────────────────────────────────
def summarize_digest(*, school, audience: str, facts: Iterable[str]) -> tuple[str, dict]:
    """Summarize pre-aggregated activity facts into a friendly digest.

    The caller MUST pass already-computed structured facts (no ORM/DB here);
    the model only narrates them — it must not invent. Returns ("", meta) on
    failure so the caller can fall back to a deterministic bullet list."""
    fact_block = "\n".join(f"- {f}" for f in (facts or []) if f)
    if not fact_block:
        return "", {"skipped": True}
    prompt = (
        f"Write a short, friendly weekly digest for {audience} at "
        f"{getattr(school, 'name', 'the school')}. Summarize ONLY these facts "
        "(do not invent anything):\n"
        f"{fact_block}\n\n"
        "80-140 words, plain prose, encouraging tone, no headings.\n"
    )
    try:
        from services.ai_gateway import TaskType
    except ImportError:
        return "", {"error": "TaskType unavailable"}
    return _safe_invoke(TaskType.NARRATIVE, prompt, school=school)


__all__ = [
    "draft_announcement",
    "suggest_subject_lines",
    "rewrite_plain_language",
    "classify_parent_intent",
    "choose_channel",
    "translate_message",
    "suggest_replies",
    "detect_safeguarding_signal",
    "summarize_digest",
]
