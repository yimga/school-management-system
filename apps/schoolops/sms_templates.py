"""v3.33.0 — Per-locale SMS short-form templates for low-balance alerts.

These are PRE-FORMATTED short forms (<=160 chars each). They intentionally
do NOT include the dollar amount in plaintext when the balance is
critically low (< $1) — at that point the SMS just says "low" so the
160-char surface is not used as a side-channel for PII exfiltration.

Public API:
  :func:`render_low_balance_sms` — given (locale, student_first_name,
  balance, currency, threshold), returns a single SMS-ready string
  guaranteed to be <=160 chars. Locale falls back to 'en' when unknown.

Contract:
  * NEVER include the student's LAST name in SMS (PII minimization;
    the email surface carries first+last, the SMS surface carries first).
  * NEVER include the balance numeric in plaintext when
    ``balance < Decimal("1.00")``. Use the locale-specific "very low"
    phrase instead.
  * Currency code is appended ONLY when the amount IS included.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Mapping


# Short-form bodies per locale. Each template MUST resolve to <=160 chars
# after substitution. We carry separate "normal" and "very low" forms
# because the very-low form omits the numeric.
SMS_LOW_BALANCE_BY_LOCALE: Mapping[str, Mapping[str, str]] = {
    "en": {
        "normal": "Low meal plan balance for {first}: {amount} {currency}. "
                  "Top up to avoid service interruption.",
        "very_low": "Meal plan balance for {first} is low. "
                    "Please top up to avoid service interruption.",
    },
    "fr": {
        "normal": "Solde repas bas pour {first} : {amount} {currency}. "
                  "Rechargez pour éviter une interruption.",
        "very_low": "Le solde du plan de repas de {first} est bas. "
                    "Veuillez recharger pour éviter une interruption.",
    },
    "es": {
        "normal": "Saldo bajo del plan de comidas de {first}: "
                  "{amount} {currency}. Recargue para evitar interrupciones.",
        "very_low": "El saldo del plan de comidas de {first} es bajo. "
                    "Recargue para evitar interrupciones.",
    },
    "pt": {
        "normal": "Saldo baixo no plano de refeições de {first}: "
                  "{amount} {currency}. Recarregue para evitar interrupção.",
        "very_low": "O saldo do plano de refeições de {first} está baixo. "
                    "Recarregue para evitar interrupção.",
    },
    "ar": {
        "normal": "رصيد منخفض لخطة وجبات {first}: {amount} {currency}. "
                  "يُرجى الشحن لتفادي انقطاع الخدمة.",
        "very_low": "رصيد خطة وجبات {first} منخفض. "
                    "يُرجى الشحن لتفادي انقطاع الخدمة.",
    },
}

# Hard cap per the GSM-7 single-segment SMS surface.
SMS_MAX_CHARS = 160

# Privacy threshold: when balance is below this we never include the
# numeric in plaintext SMS.
_VERY_LOW_AMOUNT = Decimal("1.00")


def _normalize_locale(locale: str | None) -> str:
    """Return one of the supported locale keys; default 'en'.

    Accepts BCP-47-ish inputs like 'fr-FR', 'pt-BR' and strips down to
    the base language tag. Unknown codes fall back to English.
    """
    if not locale:
        return "en"
    base = str(locale).strip().lower().split("-", 1)[0].split("_", 1)[0]
    if base in SMS_LOW_BALANCE_BY_LOCALE:
        return base
    return "en"


def render_low_balance_sms(
    *,
    locale: str | None,
    first_name: str,
    balance,
    currency: str,
    threshold=None,  # noqa: ARG001 -- accepted for API parity with email ctx
) -> str:
    """Render the short-form SMS body. Guaranteed <=160 chars.

    Args:
      locale: BCP-47 or 2-letter locale code. Unknown → 'en'.
      first_name: Student's first name (last name NEVER included in SMS).
      balance: Decimal balance for the row.
      currency: 3-letter ISO 4217 currency code.

    Returns:
      A single SMS-ready string, <=160 chars.
    """
    code = _normalize_locale(locale)
    forms = SMS_LOW_BALANCE_BY_LOCALE.get(
        code, SMS_LOW_BALANCE_BY_LOCALE["en"],
    )
    first = (first_name or "student").strip() or "student"
    # Trim long first names so we always fit. Most first names are <=20.
    first = first[:20]
    cur = (currency or "").strip().upper()[:3]

    # Privacy gate: very-low balances never leak the numeric.
    try:
        is_very_low = (
            balance is not None and Decimal(str(balance)) < _VERY_LOW_AMOUNT
        )
    except Exception:  # noqa: BLE001 -- non-Decimal coerce path
        is_very_low = False

    if is_very_low:
        body = forms["very_low"].format(first=first)
    else:
        # Format the amount without float conversion. Decimal -> str
        # preserves precision; ``scan_money_float`` is satisfied.
        amount_str = str(balance) if balance is not None else "0"
        body = forms["normal"].format(
            first=first, amount=amount_str, currency=cur,
        )

    # Hard-cap to GSM-7 single-segment length. If we overflow (e.g. ar
    # is wider per char in practice but we measure in code points here),
    # truncate cleanly at the last word break we can find before 160.
    if len(body) > SMS_MAX_CHARS:
        truncated = body[:SMS_MAX_CHARS]
        # Try to land on a word boundary if one exists in the last 20
        # chars of the truncated string. Otherwise hard-cut.
        cut = truncated.rfind(" ", SMS_MAX_CHARS - 20, SMS_MAX_CHARS)
        if cut > 0:
            body = truncated[:cut]
        else:
            body = truncated
    return body
