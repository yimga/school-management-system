"""Locale-aware email rendering (GAP-5).

Before this module each email call site that wanted localization hand-rolled the
same fragile pattern: build ``f"<dir>/locale/{locale}/<name>.{txt,html}"`` inside
a broad ``try/except`` that, on *any* error, silently fell back to the English
path. That inline logic lived in exactly one place (``schoolops.tasks`` for the
low-meal-balance email); every other transactional email shipped English-only.

This is the single, shared renderer those call sites should use. Given a base
directory, a template stem, and a recipient locale, it renders the
``(text, html)`` bodies from ``<dir>/locale/<locale>/<stem>.{txt,html}`` and
degrades deterministically:

    1. the requested locale (normalised, e.g. ``"fr-CA"`` → ``"fr"``),
    2. then the fallback locale (default ``"en"``),
    3. then the legacy non-locale path ``<dir>/<stem>.{txt,html}``.

Only :class:`~django.template.TemplateDoesNotExist` triggers the next candidate,
so a *real* bug inside a present template surfaces instead of being masked as a
"missing translation". The function returns which locale actually rendered, so
the caller can keep a downstream SMS/notification in the same language.

Dropping a new translation in is now a pure content task: add
``<dir>/locale/<code>/<stem>.{txt,html}`` and it is picked up automatically — no
code change. Until a locale file exists, the recipient transparently gets the
English copy (same behaviour as today, but centralised and consistent).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.template import TemplateDoesNotExist
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)

#: Locales we currently ship copy for. Advisory only — the renderer works for any
#: code that has template files; this mirrors the SMS registry's set so the two
#: localisation surfaces stay aligned.
SUPPORTED_EMAIL_LOCALES = ("en", "fr", "es", "pt", "ar")

#: Locale used when the requested one has no template (and as the legacy stem's
#: notional locale).
DEFAULT_EMAIL_LOCALE = "en"


@dataclass(frozen=True)
class LocalizedEmail:
    """The rendered bodies plus the locale that actually produced them."""

    text: str
    html: str
    locale: str


def normalize_locale(locale) -> str:
    """Reduce ``"fr_CA"`` / ``"fr-CA"`` / ``"FR"`` to a bare base code (``"fr"``).

    Returns ``""`` for a falsy / unusable value so the caller's fallback applies.
    """
    raw = (locale or "").strip().lower()
    if not raw:
        return ""
    return raw.split("-", 1)[0].split("_", 1)[0]


def render_localized_email(
    base_dir: str,
    stem: str,
    locale,
    context,
    *,
    fallback_locale: str = DEFAULT_EMAIL_LOCALE,
) -> LocalizedEmail:
    """Render a locale-subdir email's ``(text, html)`` with deterministic fallback.

    Parameters
    ----------
    base_dir:
        Template directory holding ``locale/<code>/`` subfolders, e.g.
        ``"schoolops/email"``. No trailing slash.
    stem:
        Template file stem without extension, e.g. ``"low_meal_balance"``.
    locale:
        Requested recipient locale (any case / region form; normalised here).
    context:
        Render context dict passed to both the ``.txt`` and ``.html`` templates.
    fallback_locale:
        Locale tried after the requested one (default ``"en"``).

    Returns
    -------
    LocalizedEmail
        ``text`` / ``html`` bodies and the ``locale`` that rendered them.

    Raises
    ------
    TemplateDoesNotExist
        Only if *no* candidate (requested, fallback, legacy) resolves — a genuine
        "this email has no template at all" condition the caller must handle.
    """
    candidates = []
    norm = normalize_locale(locale)
    if norm:
        candidates.append(norm)
    fb = normalize_locale(fallback_locale) or DEFAULT_EMAIL_LOCALE
    if fb not in candidates:
        candidates.append(fb)

    for loc in candidates:
        txt_name = f"{base_dir}/locale/{loc}/{stem}.txt"
        html_name = f"{base_dir}/locale/{loc}/{stem}.html"
        try:
            text_body = render_to_string(txt_name, context)
            html_body = render_to_string(html_name, context)
        except TemplateDoesNotExist:
            continue
        return LocalizedEmail(text=text_body, html=html_body, locale=loc)

    # Legacy, non-locale path: <base_dir>/<stem>.{txt,html}. If this is missing
    # too the email truly has no template — propagate so the caller can react.
    text_body = render_to_string(f"{base_dir}/{stem}.txt", context)
    html_body = render_to_string(f"{base_dir}/{stem}.html", context)
    return LocalizedEmail(text=text_body, html=html_body, locale=fb)


__all__ = [
    "SUPPORTED_EMAIL_LOCALES",
    "DEFAULT_EMAIL_LOCALE",
    "LocalizedEmail",
    "normalize_locale",
    "render_localized_email",
]
