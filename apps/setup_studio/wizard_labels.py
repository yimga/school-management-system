"""Human-readable label resolution for wizard tokens.

The JSON-driven wizard engine stores ``label_token`` / ``description_token``
strings. By convention (see ``wizard_resolvers_*.py``) these hold human English
that *doubles* as a gettext msgid — e.g. ``"Mother"``, ``"PowerSchool"``. But
when a wizard JSON omits an explicit label, ``wizard_engine._parse_step`` /
``_parse_wizard`` synthesize a fallback slug like
``wizards.mfa_setup.step.choose_channel.label``. Those slugs were never added to
any ``.po`` catalog, so without a resolution layer they render *raw* to the user
(the "wizards.mfa_setup.step.choose_channel.label" bug seen on the MFA wizard).

``humanize_wizard_token`` is the single resolution point:

1. Run the token through ``gettext`` — honors any real catalog entry and keeps
   the i18n path intact for future translations.
2. If the token is already human (anything NOT starting with ``wizards.``),
   return it unchanged — this is the resolver-supplied label convention.
3. Otherwise it's a synthesized ``wizards.*`` slug — humanize its meaningful
   segment (``choose_channel`` -> ``"Choose Channel"``) with acronym awareness
   (``sms_verify`` -> ``"SMS Verify"``).

This makes EVERY wizard readable immediately — not just the ones whose JSON
remembered to supply labels.
"""

from __future__ import annotations

from django.utils.translation import gettext

# Segments that are uppercased whole when they appear as a humanized word.
_ACRONYMS = {
    "mfa": "MFA", "sms": "SMS", "qr": "QR", "totp": "TOTP", "otp": "OTP",
    "ai": "AI", "id": "ID", "url": "URL", "api": "API", "sso": "SSO",
    "kpi": "KPI", "pos": "POS", "csv": "CSV", "pdf": "PDF", "dob": "DOB",
    "sis": "SIS", "lms": "LMS", "pin": "PIN", "2fa": "2FA",
}

# Trailing token segments that are structural, not content.
_STRIP_SUFFIXES = frozenset(
    {"label", "description", "title", "subtitle", "help", "name"}
)


def _titlecase_with_acronyms(text: str) -> str:
    words = []
    for raw in text.split():
        low = raw.lower()
        if low in _ACRONYMS:
            words.append(_ACRONYMS[low])
        elif raw:
            words.append(raw[:1].upper() + raw[1:])
    return " ".join(words)


def humanize_wizard_token(token: object) -> str:
    """Resolve a wizard label/description token to human-readable text.

    Safe for any input: non-strings -> ``""``; human labels pass through
    unchanged; only synthesized ``wizards.*`` slugs are transformed.
    """
    if not isinstance(token, str) or not token:
        return ""
    translated = gettext(token)
    if translated and translated != token:
        return translated
    if not token.startswith("wizards."):
        # Already human (resolver-supplied label, explicit JSON label, etc.).
        return token
    parts = [p for p in token.split(".") if p]
    if parts and parts[-1] in _STRIP_SUFFIXES:
        parts = parts[:-1]
    segment = parts[-1] if parts else token
    humanized = _titlecase_with_acronyms(
        segment.replace("_", " ").replace("-", " ").strip()
    )
    return humanized or token
