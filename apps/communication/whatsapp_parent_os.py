"""Wave H (v3.95.0 — 2026-05-26) — WhatsApp Parent OS conversational layer.

The differentiator vs. FoondaMate (tutor-student AI on consumer WhatsApp) is
*institutional*: messages are scoped to a school-issued Meta Business number,
the parent is auth'd against the tenant's guardian roster (phone match), and
intents resolve against the tenant's actual records (fee ledger, attendance,
report cards).

This module is the **pure routing kernel**. It does NOT perform any network
I/O. The webhook view (`views_whatsapp_webhook.py`) accepts the parsed
payload, hands the inbound message off to :func:`route_inbound_message`, and
sends whatever ``OutboundIntent`` the kernel produces.

Boundary: AI calls (intent classification beyond keywords) MUST go through
``services.ai_helpers``. No direct ``services.ai_gateway`` import here.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Callable, Optional


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Intent kernel
# ---------------------------------------------------------------------------

_INTENT_FEE_BALANCE = "fee_balance"
_INTENT_ABSENCE_REPORT = "absence_report"
_INTENT_REPORT_CARD = "report_card"
_INTENT_HOMEWORK = "homework"
_INTENT_MENU = "menu"
_INTENT_HELP = "help"
_INTENT_HUMAN = "human"
_INTENT_STOP = "stop"
_INTENT_UNKNOWN = "unknown"


_DEFAULT_INTENT_ALLOWLIST: tuple[str, ...] = (
    _INTENT_FEE_BALANCE,
    _INTENT_ABSENCE_REPORT,
    _INTENT_REPORT_CARD,
    _INTENT_HOMEWORK,
    _INTENT_MENU,
    _INTENT_HELP,
    _INTENT_HUMAN,
    _INTENT_STOP,
)


# Keyword maps — multi-locale, normalized to lower-case ASCII-fold tokens.
# Routes are deliberately broad (one short word / common phrase per locale)
# because parents type as they speak. AI fallback (Wave H+1) can classify
# longer free-form text via ``services.ai_helpers.classify_intent``.
_INTENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    _INTENT_FEE_BALANCE: (
        "fee", "fees", "balance", "owe", "owed", "school fee", "school fees",
        # FR / ES / PT
        "frais", "facture", "matricula", "matrícula", "mensalidade", "deuda",
        # Swahili / Yoruba / Igbo (Romanized common forms)
        "ada", "kara", "ego",
    ),
    _INTENT_ABSENCE_REPORT: (
        "absent", "absence", "sick", "ill", "illness", "not coming", "off today",
        "malade", "enfermo", "doente", "ugonjwa",
    ),
    _INTENT_REPORT_CARD: (
        "report", "report card", "grades", "results", "bulletin", "boletim",
        "notas", "notes",
    ),
    _INTENT_HOMEWORK: (
        "homework", "hw", "devoir", "tarea", "tarefa", "deber",
    ),
    _INTENT_MENU: ("menu", "options", "start", "hi", "hello", "hey"),
    _INTENT_HELP: ("help", "aide", "ayuda", "ajuda", "msaada"),
    _INTENT_HUMAN: (
        "human", "agent", "person", "speak", "talk", "call", "callback",
        "humain", "humano", "humana",
    ),
    _INTENT_STOP: ("stop", "unsubscribe", "remove", "quit", "arret", "parar"),
}


_NORMALIZE_RE = re.compile(r"[^\w\s]+", flags=re.UNICODE)


def _normalize(text: str) -> str:
    if not text:
        return ""
    # Lower + strip punctuation; preserve whitespace for token matching.
    out = (text or "").strip().lower()
    return _NORMALIZE_RE.sub(" ", out).strip()


# ---------------------------------------------------------------------------
# Inbound / outbound dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class InboundMessage:
    """A parsed inbound WhatsApp message from the Meta webhook payload."""

    from_phone: str
    body: str
    tenant_id: str
    locale: str = "en"
    message_id: str = ""
    button_payload: str = ""
    received_at: str = ""


@dataclass
class OutboundIntent:
    """The kernel's resolved response — what the view should send back."""

    intent: str
    template_key: str
    body_text: str = ""
    placeholders: dict[str, str] = field(default_factory=dict)
    requires_human: bool = False
    rate_limited: bool = False


# ---------------------------------------------------------------------------
# Rate limiter — simple per-phone token bucket (in-memory; tenant-scoped)
# ---------------------------------------------------------------------------

_RATE_BUCKETS: dict[tuple[str, str], list[float]] = {}


def _check_rate(tenant_id: str, phone: str, limit_per_hour: int, now: float) -> bool:
    """Return True if under quota; False if rate-limited."""
    key = (tenant_id, phone)
    bucket = _RATE_BUCKETS.setdefault(key, [])
    cutoff = now - 3600.0
    # Drop expired tokens.
    bucket[:] = [t for t in bucket if t > cutoff]
    if len(bucket) >= limit_per_hour:
        return False
    bucket.append(now)
    return True


def reset_rate_buckets() -> None:
    """Test helper — drops the in-process rate buckets."""
    _RATE_BUCKETS.clear()


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

def classify_intent_keyword(text: str) -> str:
    """Pure keyword classifier — no AI calls, fail-open to UNKNOWN."""
    norm = _normalize(text)
    if not norm:
        return _INTENT_UNKNOWN
    # Exact short-token matches first (avoids "fees coming Friday" → STOP false hit).
    tokens = set(norm.split())
    for intent, keywords in _INTENT_KEYWORDS.items():
        for kw in keywords:
            kw_n = _normalize(kw)
            if " " in kw_n:
                # Multi-word: substring match.
                if kw_n in norm:
                    return intent
            elif kw_n in tokens:
                return intent
    return _INTENT_UNKNOWN


# Template key map — each intent has a stable template key the view can
# resolve to actual outbound copy (multi-locale) via ``template_catalog``.
_INTENT_TEMPLATE_KEYS: dict[str, str] = {
    _INTENT_FEE_BALANCE: "parent_os_fee_balance_reply",
    _INTENT_ABSENCE_REPORT: "parent_os_absence_acknowledged",
    _INTENT_REPORT_CARD: "parent_os_report_card_link",
    _INTENT_HOMEWORK: "parent_os_homework_summary",
    _INTENT_MENU: "parent_os_menu",
    _INTENT_HELP: "parent_os_help",
    _INTENT_HUMAN: "parent_os_handoff_human",
    _INTENT_STOP: "parent_os_unsubscribed",
    _INTENT_UNKNOWN: "parent_os_unknown_intent",
}


# Per-intent stub bodies — used when the tenant has not customized the
# template_catalog entry. Real deployments override these in
# ``template_catalog.py`` (CountryRegistry / SiteSettings cascade).
_DEFAULT_BODIES: dict[str, str] = {
    _INTENT_FEE_BALANCE: "Your fee balance is {balance}. Reply MENU for options.",
    _INTENT_ABSENCE_REPORT: "Thank you. Marked {student} absent today. Get well soon.",
    _INTENT_REPORT_CARD: "Latest report card: {link}. Expires in 7 days.",
    _INTENT_HOMEWORK: "Today's homework: {summary}",
    _INTENT_MENU: "Reply: FEES, ABSENT, REPORT, HOMEWORK, HUMAN.",
    _INTENT_HELP: "Reply MENU to see options or HUMAN to reach a person.",
    _INTENT_HUMAN: "Connecting you with the school office. Reply CANCEL to stop.",
    _INTENT_STOP: "You are unsubscribed. Reply START to re-enable.",
    _INTENT_UNKNOWN: "Sorry, I didn't catch that. Reply MENU for options.",
}


@dataclass
class RoutingConfig:
    """Plumbing config — passed by the view, never hard-coded here."""

    allowlist: tuple[str, ...] = _DEFAULT_INTENT_ALLOWLIST
    rate_limit_per_hour: int = 30
    now_fn: Callable[[], float] = field(default_factory=lambda: __import__("time").time)
    placeholder_resolver: Callable[[InboundMessage, str], dict[str, str]] | None = None
    # AI fallback (audit AI roadmap): a callable ``(body, allowlist) -> intent
    # | None`` consulted ONLY when keyword classification yields UNKNOWN. The
    # kernel stays pure — the view injects the real classifier (which routes
    # through the guardrailed AI gateway). None = keyword-only (legacy default).
    ai_classifier: Callable[[str, tuple[str, ...]], Optional[str]] | None = None


def route_inbound_message(
    inbound: InboundMessage,
    config: RoutingConfig | None = None,
) -> OutboundIntent:
    """Kernel — classify intent + assemble outbound response.

    Pure function (modulo the in-memory rate bucket and `now_fn` clock).
    No I/O — the view layer is responsible for actually sending the result.
    """
    cfg = config or RoutingConfig()

    # Button payload wins over body text — Meta's interactive replies send
    # both, and the button is unambiguous.
    raw_intent = (inbound.button_payload or "").strip().lower()
    if raw_intent and raw_intent in _INTENT_TEMPLATE_KEYS:
        intent = raw_intent
    else:
        intent = classify_intent_keyword(inbound.body)
        # AI fallback (audit) — only when the cheap keyword path gives up.
        # Bounded to the tenant's allowlist; the classifier returns None when
        # unavailable/unsure, so we keep the safe UNKNOWN→menu default.
        if intent == _INTENT_UNKNOWN and cfg.ai_classifier is not None and (inbound.body or "").strip():
            try:
                ai_intent = cfg.ai_classifier(inbound.body, tuple(cfg.allowlist))
            except Exception as exc:  # noqa: BLE001 — AI never breaks routing
                logger.warning("whatsapp_parent_os ai_classifier failed err=%s", type(exc).__name__)
                ai_intent = None
            if ai_intent and ai_intent in _INTENT_TEMPLATE_KEYS:
                intent = ai_intent

    if intent not in cfg.allowlist and intent != _INTENT_UNKNOWN:
        # Tenant disabled this intent — degrade to UNKNOWN (which always
        # routes to a safe menu response).
        intent = _INTENT_UNKNOWN

    # Rate-limit per phone per hour. STOP is exempt — must always succeed.
    if intent != _INTENT_STOP:
        ok = _check_rate(
            inbound.tenant_id,
            inbound.from_phone,
            cfg.rate_limit_per_hour,
            cfg.now_fn(),
        )
        if not ok:
            return OutboundIntent(
                intent=intent,
                template_key="parent_os_rate_limited",
                body_text=(
                    "Too many messages this hour. Please wait, or reply HUMAN "
                    "to reach the office."
                ),
                rate_limited=True,
            )

    template_key = _INTENT_TEMPLATE_KEYS[intent]
    placeholders: dict[str, str] = {}
    if cfg.placeholder_resolver is not None:
        try:
            placeholders = cfg.placeholder_resolver(inbound, intent) or {}
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "whatsapp_parent_os placeholder_resolver failed intent=%s err=%s",
                intent, exc,
            )
    body = _DEFAULT_BODIES[intent]
    # Best-effort placeholder substitution — missing keys remain as literal.
    for k, v in placeholders.items():
        body = body.replace("{" + k + "}", str(v))

    return OutboundIntent(
        intent=intent,
        template_key=template_key,
        body_text=body,
        placeholders=placeholders,
        requires_human=(intent == _INTENT_HUMAN),
    )


# ---------------------------------------------------------------------------
# Public introspection (for admin / verifier scripts)
# ---------------------------------------------------------------------------

def known_intents() -> tuple[str, ...]:
    """Snapshot of all intents the kernel can resolve (excludes UNKNOWN)."""
    return tuple(k for k in _INTENT_TEMPLATE_KEYS if k != _INTENT_UNKNOWN)


def template_key_for(intent: str) -> str:
    return _INTENT_TEMPLATE_KEYS.get(intent, _INTENT_TEMPLATE_KEYS[_INTENT_UNKNOWN])
