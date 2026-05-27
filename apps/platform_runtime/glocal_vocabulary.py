"""Unified UI token resolver — lexicon + IAM localization (batch 1531)."""

from __future__ import annotations


from django.utils.translation import gettext as _


def resolve_ui_token(key: str, school=None, *, fallback: str | None = None) -> str:
    """
    Resolve a display token from tenant lexicon / IAM mappings.

    Keys:
      - ``role.ADMIN`` → localized role label
      - ``action.<code>`` → localized permission label
      - other keys → lexicon dict lookup, then fallback
    """
    token = (key or "").strip()
    if not token:
        return fallback or ""

    if token.startswith("role."):
        from apps.accounts.iam_localization import localized_role_label

        code = token.split(".", 1)[1].strip().upper()
        return localized_role_label(code, school, fallback=fallback or code)

    if token.startswith("action."):
        from apps.accounts.iam_localization import localized_permission_label

        code = token.split(".", 1)[1].strip()
        return localized_permission_label(code, school) or (fallback or code)

    try:
        from apps.siteconfig.terminology_service import lexicon_payload

        school_obj = school
        if school_obj is not None:
            compact = lexicon_payload(school_obj)
            if token in compact:
                return str(compact[token])
    except Exception:
        pass

    if fallback:
        return fallback
    return _(token.replace("_", " ").replace(".", " ").title())


__all__ = ["resolve_ui_token"]
