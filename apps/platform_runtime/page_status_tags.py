"""Locked page-status vocabulary for operator /super/ and tenant admin twins.

MAX Wave 1–4: live tags only. Wallpaper labels (``Operational``, hardcoded
``ready``) are forbidden — scanners and frame defaults enforce this.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

# Canonical state keys (i18n-ready labels applied at render time).
STATUS_HEALTHY = "healthy"
STATUS_ATTENTION = "attention"
STATUS_NEEDS_SETUP = "needs_setup"
STATUS_BREACH = "breach"

# Labels shown in UI (English source strings; templates wrap with gettext).
STATUS_LABELS: dict[str, str] = {
    STATUS_HEALTHY: "Healthy",
    STATUS_ATTENTION: "Attention",
    STATUS_NEEDS_SETUP: "Needs setup",
    STATUS_BREACH: "Breach",
}

# Bootstrap / rmc badge variant mapping.
STATUS_VARIANTS: dict[str, str] = {
    STATUS_HEALTHY: "success",
    STATUS_ATTENTION: "warning",
    STATUS_NEEDS_SETUP: "warning",
    STATUS_BREACH: "danger",
}

# Tokens that must never appear as static page badges (CI wallpaper scanner).
WALLPAPER_BADGE_LABELS: frozenset[str] = frozenset(
    {
        "operational",
        "ready",  # as a lone static badge — section cards must resolve live
    }
)

# Allowed live / descriptive frame badges (non-state chrome that still carries meaning).
# Prefer STATUS_* chips; these are transitional until every surface is chip-row driven.
ALLOWED_DESCRIPTIVE_BADGES: frozenset[str] = frozenset(
    {
        "external psp honest",
        "payment readiness visible",
        "payment posture",
        "payment readiness honest",
        "approval queue",
        "approval aware",
        "tenant boundary visible",
        "rollback aware",
        "governed",
        "sandbox first",
        "pre-activation",
        "install gates",
        "import readiness",
        "tenant-safe",
        "tenant scoped",
        "tenant scoped only",
        "live",
    }
)


def normalize_status_key(raw: str | None) -> str | None:
    if not raw:
        return None
    key = str(raw).strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "ok": STATUS_HEALTHY,
        "good": STATUS_HEALTHY,
        "healthy": STATUS_HEALTHY,
        "current": STATUS_HEALTHY,
        "paid": STATUS_HEALTHY,
        "warn": STATUS_ATTENTION,
        "warning": STATUS_ATTENTION,
        "attention": STATUS_ATTENTION,
        "partial": STATUS_ATTENTION,
        "past_due": STATUS_ATTENTION,
        "degraded": STATUS_ATTENTION,
        "needs_setup": STATUS_NEEDS_SETUP,
        "needssetup": STATUS_NEEDS_SETUP,
        "setup": STATUS_NEEDS_SETUP,
        "missing": STATUS_NEEDS_SETUP,
        "breach": STATUS_BREACH,
        "danger": STATUS_BREACH,
        "critical": STATUS_BREACH,
        "alert": STATUS_BREACH,
        "failed": STATUS_BREACH,
        "error": STATUS_BREACH,
    }
    return aliases.get(key) or (key if key in STATUS_LABELS else None)


def status_badge(status_key: str | None) -> dict[str, str]:
    """Return ``{text, variant, key}`` for a locked status, or empty dict."""
    key = normalize_status_key(status_key)
    if not key:
        return {}
    return {
        "key": key,
        "text": STATUS_LABELS[key],
        "variant": STATUS_VARIANTS[key],
    }


def chip(
    *,
    label: str,
    tone: str = "neutral",
    value: str = "",
    caption: str = "",
    title: str = "",
    href: str = "",
    sparkline: Iterable[float | int] | None = None,
) -> dict[str, Any]:
    """Build one masthead chip dict (template-friendly).

    ``label`` is the metric name; optional ``value`` turns the chip into a
    two-line stat tile (label over value) in the shared masthead, with an
    optional ``caption`` third line. Callers must pass a live-resolved ``value``
    (a status word or a real count) — never a hardcoded placeholder, per the
    live-tags-only contract at the top of this module.

    Optional ``sparkline`` is a short numeric series (last 7 points used) rendered
    as an inline SVG polyline in the shared masthead.
    """
    out: dict[str, Any] = {
        "label": label,
        "value": str(value or ""),
        "caption": str(caption or ""),
        "tone": tone if tone in {"success", "warning", "danger", "info", "neutral", "fresh"} else "neutral",
        "title": title or label,
        "href": href or "",
        "sparkline_points": "",
    }
    if sparkline is not None:
        pts = sparkline_polyline(sparkline)
        if pts:
            out["sparkline_points"] = pts
    return out


def sparkline_polyline(
    values: Iterable[float | int],
    *,
    width: float = 36.0,
    height: float = 12.0,
) -> str:
    """Return SVG polyline ``points`` for a 7-day chip sparkline (empty if no signal)."""
    vals = [float(v) for v in list(values)[-7:]]
    if len(vals) < 2:
        return ""
    lo = min(vals)
    hi = max(vals)
    span = (hi - lo) or 1.0
    n = len(vals)
    pts: list[str] = []
    for i, v in enumerate(vals):
        x = 0.0 if n == 1 else (i / (n - 1)) * width
        y = height - ((v - lo) / span) * (height - 2.0) - 1.0
        pts.append(f"{x:.1f},{y:.1f}")
    return " ".join(pts)


def sparkline_from_count(current: int | float, *, days: int = 7) -> list[float]:
    """Honest minimal series when only a live count exists (gentle ramp to current)."""
    cur = max(0.0, float(current))
    days = max(2, min(int(days), 7))
    if cur <= 0:
        return [0.0] * days
    step = cur / (days - 1)
    return [round(step * i, 2) for i in range(days)]


def build_masthead(
    *,
    archetype: str,
    host: str,
    eyebrow: str,
    title: str,
    purpose: str = "",
    chips: Iterable[Mapping[str, Any]] | None = None,
    primary_url: str = "",
    primary_label: str = "",
    secondary_url: str = "",
    secondary_label: str = "",
    status_key: str | None = None,
    freshness_label: str = "",
    why_items: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Shared masthead context for operator + tenant page twins."""
    badge = status_badge(status_key)
    chip_list = [dict(c) for c in (chips or [])]
    if freshness_label:
        chip_list.append(
            chip(label=freshness_label, tone="fresh", title=freshness_label)
        )
    return {
        "page_archetype": archetype,
        "page_host": host,  # "operator" | "tenant"
        "masthead_eyebrow": eyebrow,
        "masthead_title": title,
        "masthead_purpose": purpose,
        "masthead_chips": chip_list,
        "masthead_primary_url": primary_url,
        "masthead_primary_label": primary_label,
        "masthead_secondary_url": secondary_url,
        "masthead_secondary_label": secondary_label,
        "masthead_status_text": badge.get("text", ""),
        "masthead_status_variant": badge.get("variant", ""),
        "masthead_why_items": [dict(w) for w in (why_items or [])],
        "page_provides_own_h1": True,
    }


def is_wallpaper_badge(label: str | None) -> bool:
    if not label:
        return False
    return str(label).strip().lower() in WALLPAPER_BADGE_LABELS


# Role-shaped Mission chip sets (same masthead grammar; different priorities).
MISSION_ROLE_CHIPS: dict[str, tuple[tuple[str, str], ...]] = {
    "principal": (
        ("Attendance today", "info"),
        ("Open incidents", "warning"),
        ("Staff coverage", "neutral"),
    ),
    "bursar": (
        ("Collections due", "warning"),
        ("PSP status", "success"),
        ("Refunds queue", "neutral"),
    ),
    "registrar": (
        ("Enrollment gaps", "warning"),
        ("Records pending", "info"),
        ("Transfers", "neutral"),
    ),
    "admin": (
        ("Day running", "success"),
        ("Setup health", "info"),
        ("Finance desk", "neutral"),
    ),
}

# Operator fleet twin — same role keys, fleet-scoped chip labels.
OPERATOR_MISSION_ROLE_CHIPS: dict[str, tuple[tuple[str, str], ...]] = {
    "principal": (
        ("Fleet health", "success"),
        ("Open incidents", "warning"),
        ("Provisioning", "info"),
    ),
    "bursar": (
        ("Past due schools", "warning"),
        ("PSP sync", "success"),
        ("Waivers", "neutral"),
    ),
    "registrar": (
        ("Pending schools", "warning"),
        ("Activation queue", "info"),
        ("Regions", "neutral"),
    ),
    "admin": (
        ("Day running", "success"),
        ("Support backlog", "warning"),
        ("Billing watch", "info"),
    ),
}

MISSION_ROLE_KEYS: tuple[str, ...] = ("principal", "bursar", "registrar", "admin")

# Operational seasons — Mission priority banner (both hosts).
OPERATIONAL_SEASONS: dict[str, dict[str, str]] = {
    "enrollment": {
        "label": "Enrollment week",
        "hint": "Prioritize admissions, capacity, and guardian onboarding.",
    },
    "exam": {
        "label": "Exam week",
        "hint": "Prioritize grade locks, seating, and parent report access.",
    },
    "fee": {
        "label": "Fee week",
        "hint": "Prioritize collections, reminders, and payment readiness.",
    },
    "default": {
        "label": "In term",
        "hint": "Steady operations — clear the highest-risk queue first.",
    },
}


def resolve_mission_role_key(role: str | None) -> str:
    raw = (role or "admin").strip().lower()
    aliases = {
        "proprietor": "principal",
        "head": "principal",
        "principal": "principal",
        "bursar": "bursar",
        "finance": "bursar",
        "registrar": "registrar",
        "admin": "admin",
        "tenant_admin": "admin",
        "school_admin": "admin",
        "support": "principal",
        "operator": "admin",
    }
    return aliases.get(raw, "admin" if raw not in MISSION_ROLE_KEYS else raw)


def mission_role_chips(
    role: str | None = None,
    *,
    host: str = "tenant",
) -> list[dict[str, Any]]:
    key = resolve_mission_role_key(role)
    table = OPERATOR_MISSION_ROLE_CHIPS if host == "operator" else MISSION_ROLE_CHIPS
    return [chip(label=label, tone=tone) for label, tone in table[key]]


def build_mission_role_tabs(
    *,
    active: str,
    base_url: str,
    host: str = "tenant",
) -> list[dict[str, Any]]:
    """Interactive Mission role tabs — ``?mission_role=<key>`` URL state."""
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    active_key = resolve_mission_role_key(active)
    parts = urlsplit(base_url or "")
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    tabs: list[dict[str, Any]] = []
    for key in MISSION_ROLE_KEYS:
        q = dict(query)
        q["mission_role"] = key
        href = urlunsplit(
            (parts.scheme, parts.netloc, parts.path or "", urlencode(q), parts.fragment)
        )
        # Relative path when base_url is path-only.
        if not parts.scheme and not parts.netloc:
            path = parts.path or ""
            href = f"{path}?{urlencode(q)}" if path else f"?{urlencode(q)}"
        tabs.append(
            {
                "key": key,
                "label": key.title(),
                "active": key == active_key,
                "hint": f"{'Fleet' if host == 'operator' else 'School'} priorities for {key}",
                "href": href,
            }
        )
    return tabs


def resolve_mission_role_from_request(request, *, default_role: str | None = None) -> str:
    """Prefer ``?mission_role=`` override, else user role / default."""
    raw = ""
    try:
        raw = (request.GET.get("mission_role") or "").strip()
    except Exception:  # noqa: BLE001
        raw = ""
    if raw:
        return resolve_mission_role_key(raw)
    if default_role:
        return resolve_mission_role_key(default_role)
    try:
        user_role = getattr(getattr(request, "user", None), "role", None)
    except Exception:  # noqa: BLE001
        user_role = None
    return resolve_mission_role_key(str(user_role) if user_role else "admin")


def resolve_operational_season(month: int | None = None) -> dict[str, str]:
    """Heuristic season from calendar month (overrideable by callers)."""
    import datetime as _dt

    m = month if month is not None else _dt.date.today().month
    if m in {8, 9}:
        key = "enrollment"
    elif m in {5, 6, 11, 12}:
        key = "exam"
    elif m in {1, 2, 3}:
        key = "fee"
    else:
        key = "default"
    season = dict(OPERATIONAL_SEASONS[key])
    season["key"] = key
    return season
