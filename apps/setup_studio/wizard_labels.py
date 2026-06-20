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


# Validator error tokens (``wizards.errors.*``) emitted by ``wizard_validators``.
# These are the single closed set of error slugs the engine can produce; without
# resolution they render raw ("wizards.errors.required") to the user. Mapped to
# real, full-sentence English (which doubles as a gettext msgid so the i18n path
# stays intact); unmapped tokens fall back to ``humanize_wizard_token``.
_WIZARD_ERROR_MESSAGES = {
    "wizards.errors.required": "This field is required.",
    "wizards.errors.max_length": "This value is too long.",
    "wizards.errors.text_too_long": "This value is too long.",
    "wizards.errors.min_length": "This value is too short.",
    "wizards.errors.pattern_mismatch": "This value isn't in the expected format.",
    "wizards.errors.pattern_invalid": "This value isn't in the expected format.",
    "wizards.errors.choice_not_in_set": "Choose one of the available options.",
    "wizards.errors.decimal_invalid": "Enter a valid number.",
    "wizards.errors.decimal_below_min": "This value is below the allowed minimum.",
    "wizards.errors.decimal_above_max": "This value is above the allowed maximum.",
    "wizards.errors.integer_invalid": "Enter a whole number.",
    "wizards.errors.integer_below_min": "This value is below the allowed minimum.",
    "wizards.errors.integer_above_max": "This value is above the allowed maximum.",
    "wizards.errors.domain_invalid": "Enter a valid domain name.",
    "wizards.errors.color_hex_invalid": "Enter a valid hex color (for example, #4F46E5).",
    "wizards.errors.file_extension_invalid": "This file type isn't supported.",
    "wizards.errors.file_extension_not_allowed": "This file type isn't allowed.",
    "wizards.errors.file_size_invalid": "This file's size couldn't be read.",
    "wizards.errors.file_too_large": "This file is too large.",
    "wizards.errors.csv_header_missing": "The CSV file is missing its header row.",
    "wizards.errors.csv_header_invalid": "The CSV header row is invalid.",
    "wizards.errors.csv_header_required_missing": "A required column is missing from the CSV header.",
    "wizards.errors.pfx_not_bytes": "Upload a valid certificate file.",
    "wizards.errors.pfx_too_small": "This certificate file looks incomplete.",
    "wizards.errors.pfx_magic_invalid": "This doesn't look like a valid PFX certificate.",
    "wizards.errors.country_code_invalid": "Enter a valid country code.",
    "wizards.errors.currency_code_invalid": "Enter a valid currency code.",
    "wizards.errors.email_invalid": "Enter a valid email address.",
}


def humanize_wizard_error(token: object) -> str:
    """Resolve a validator error token to a human-readable, translated message.

    Safe for any input: non-strings / empty -> ``""``. Known ``wizards.errors.*``
    slugs map to a full sentence; anything else (an unmapped error key, or a
    validator that already returned a human string) falls back to
    ``humanize_wizard_token``.
    """
    if not isinstance(token, str) or not token:
        return ""
    message = _WIZARD_ERROR_MESSAGES.get(token)
    if message is not None:
        return gettext(message)
    return humanize_wizard_token(token)
