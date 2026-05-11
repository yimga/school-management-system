"""
Icon compat filter — maps Font Awesome class names stored in DB to Bootstrap
Icons at render time. Bridges the gap until DB icon fields are migrated.

Background: a handful of templates render icons whose class name comes from
the database (FAQCategory.icon, KBCategory.icon, ActivityFeed.icon entries
seeded long ago as `fa-folder`, `fa-history`, etc.). The product has
standardized on Bootstrap Icons (`bi bi-*`); we don't want to migrate the DB
rows in a hurry — this filter just remaps on render.

Usage:
    {% load icon_compat %}
    <i class="{{ category.icon|fa_to_bi }}"></i>

Returns the BI class string (e.g. `bi bi-folder`) regardless of input format.
Accepts: `fa-folder`, `fas fa-folder`, `far fa-folder`, `fab fa-folder`,
bare `folder`, or already-BI `bi bi-folder`. Falls through to a safe default
if the input is empty or unrecognized.

See docs/CONFIGURABILITY.md (Layer G — compatibility shim).
"""
from django import template

register = template.Library()


# Mapping from FA name (without `fa-` prefix) → BI name (without `bi-` prefix).
# Sourced from the platform-wide Font Awesome conversion sweep (2026-05-10).
# When adding entries, prefer semantic equivalence over visual exactness.
_FA_TO_BI = {
    "shield-alt": "shield-lock",
    "shield": "shield-lock",
    "info-circle": "info-circle",
    "lock": "lock",
    "unlock": "unlock",
    "fingerprint": "fingerprint",
    "key": "key",
    "exclamation-triangle": "exclamation-triangle",
    "exclamation-circle": "exclamation-circle",
    "copy": "clipboard",
    "check": "check2",
    "check-circle": "check2-circle",
    "lightbulb": "lightbulb",
    "sync": "arrow-repeat",
    "sync-alt": "arrow-repeat",
    "spinner": "arrow-repeat",
    "redo": "arrow-clockwise",
    "plus": "plus-lg",
    "plus-circle": "plus-circle",
    "minus": "dash-lg",
    "times": "x-lg",
    "question-circle": "question-circle",
    "mobile-alt": "phone",
    "mobile": "phone",
    "sign-in-alt": "box-arrow-in-right",
    "sign-in": "box-arrow-in-right",
    "sign-out-alt": "box-arrow-left",
    "sign-out": "box-arrow-left",
    "user": "person",
    "user-plus": "person-plus",
    "user-graduate": "mortarboard",
    "users": "people",
    "users-cog": "people-fill",
    "cog": "gear",
    "cogs": "gear",
    "gear": "gear",
    "home": "house",
    "search": "search",
    "filter": "funnel",
    "edit": "pencil",
    "pen": "pencil",
    "pencil": "pencil",
    "pencil-alt": "pencil",
    "trash": "trash",
    "trash-alt": "trash",
    "bell": "bell",
    "envelope": "envelope",
    "phone": "telephone",
    "calendar": "calendar",
    "calendar-alt": "calendar",
    "calendar-plus": "calendar-plus",
    "calendar-event": "calendar-event",
    "clock": "clock",
    "history": "clock-history",
    "download": "download",
    "upload": "cloud-upload",
    "cloud-upload-alt": "cloud-upload",
    "cloud": "cloud",
    "file": "file-earmark",
    "file-alt": "file-earmark-text",
    "file-pdf": "file-earmark-pdf",
    "file-excel": "file-earmark-excel",
    "file-invoice-dollar": "receipt",
    "print": "printer",
    "save": "save",
    "eye": "eye",
    "eye-slash": "eye-slash",
    "star": "star",
    "heart": "heart",
    "thumbs-up": "hand-thumbs-up",
    "thumbs-down": "hand-thumbs-down",
    "share-alt": "share",
    "link": "link-45deg",
    "flag": "flag",
    "list": "list-ul",
    "tasks": "list-task",
    "th": "grid",
    "grid": "grid",
    "arrow-left": "arrow-left",
    "arrow-right": "arrow-right",
    "arrow-up": "arrow-up",
    "arrow-down": "arrow-down",
    "chevron-left": "chevron-left",
    "chevron-right": "chevron-right",
    "chevron-up": "chevron-up",
    "chevron-down": "chevron-down",
    "angle-right": "chevron-right",
    "angle-left": "chevron-left",
    "angle-up": "chevron-up",
    "angle-down": "chevron-down",
    "bars": "list",
    "ellipsis-h": "three-dots",
    "ellipsis-v": "three-dots-vertical",
    "ellipsis": "three-dots",
    "graduation-cap": "mortarboard",
    "school": "buildings",
    "building": "buildings",
    "book": "book",
    "chart-bar": "bar-chart",
    "chart-line": "bar-chart",
    "money-bill": "cash-coin",
    "money-bill-wave": "cash-coin",
    "dollar-sign": "cash-coin",
    "comment": "chat-dots",
    "comments": "chat-dots",
    "paper-plane": "send",
    "folder": "folder",
    "folder-open": "folder2-open",
    "inbox": "inbox",
    "level-up-alt": "arrow-up-right",
    "sliders-h": "sliders",
    "images": "images",
    "undo": "arrow-counterclockwise",
    "keyboard": "keyboard",
    "chalkboard-teacher": "easel",
    "play-circle": "play-circle",
    "bookmark": "bookmark",
    "globe": "globe",
}


def _normalize(raw: str) -> str:
    """Strip prefixes / whitespace and return the FA name without `fa-`."""
    if not raw:
        return ""
    s = raw.strip()
    # Already a BI class? Pass through.
    if s.startswith("bi "):
        return ""  # signal "already BI"
    # Strip leading `fas `/`far `/`fab `/`fa ` style prefixes
    parts = s.split()
    name = parts[-1] if parts else ""
    if name.startswith("fa-"):
        name = name[3:]
    return name


@register.filter(name="fa_to_bi")
def fa_to_bi(value, default: str = "bi-circle"):
    """Map a Font Awesome class string to its Bootstrap Icons equivalent.

    Returns the full `bi bi-NAME` class string for direct use in `<i class=...>`.
    If the input is already a `bi bi-*` string, returns it unchanged.
    If the input is empty or unrecognized, falls back to `bi <default>`.

    Usage:
        <i class="{{ category.icon|fa_to_bi }}"></i>
        <i class="{{ activity.icon|fa_to_bi:'circle-fill' }}"></i>  {# custom fallback #}
    """
    raw = str(value or "").strip()
    if not raw:
        return f"bi {default}" if not default.startswith("bi-") else f"bi {default}"
    # Pass through if already BI
    if raw.startswith("bi "):
        return raw
    if raw.startswith("bi-"):
        return f"bi {raw}"
    name = _normalize(raw)
    if not name:
        # Was already a BI prefix path — return as-is
        return raw
    bi_name = _FA_TO_BI.get(name, default if not default.startswith("bi-") else default[3:])
    # Ensure we don't double-bi
    if bi_name.startswith("bi-"):
        bi_name = bi_name[3:]
    return f"bi bi-{bi_name}"
