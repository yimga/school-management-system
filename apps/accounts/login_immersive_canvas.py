"""Configurable anonymous login canvas — payload defaults, resolvers, entitlements."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

from django.utils import timezone
from django.utils.translation import gettext_lazy as _

LAYOUT_PRESETS = frozenset(
    {"civic_editorial", "campus_hero", "calm_command", "family_first", "minimal_glass"}
)
HERO_MODES = frozenset({"carousel", "marquee", "static", "hybrid"})
THEME_VARIANTS = frozenset({"brand", "dark", "light", "high_contrast"})

METRIC_CATALOG: dict[str, dict[str, str]] = {
    "students_active": {
        "label": _("Students"),
        "sub": _("Enrolled"),
    },
    "today_date": {
        "label": _("Today"),
        "sub": _("Local date"),
    },
    "portal_secure": {
        "label": _("Portal"),
        "sub": _("Encrypted sign-in"),
    },
    "support_help": {
        "label": _("Support"),
        "sub": _("Office or IT desk"),
    },
    "events_this_week": {
        "label": _("Events"),
        "sub": _("This week"),
    },
    "attendance_rate_7d": {
        "label": _("Attendance"),
        "sub": _("7-day rate"),
    },
    "staff_active": {
        "label": _("Staff"),
        "sub": _("Active accounts"),
    },
    "languages_count": {
        "label": _("Languages"),
        "sub": _("Supported"),
    },
}

# Free tier shows the full built-in rotation (the 3 default slides
# portal/staff/families) + a filled 3-up gallery, so every school's login looks
# intentional out of the box — the login is the platform's first impression, not
# a paywalled surface. Login Canvas Pro differentiates on DEPTH, not presence:
# large custom decks (12 slides / 6 gallery), animated marquee/hybrid hero modes,
# per-slide scheduling, and sponsored/network monetization slots.
FREE_MAX_SLIDES = 3
FREE_MAX_GALLERY = 3
PRO_MAX_SLIDES = 12
PRO_MAX_GALLERY = 6


def _default_dash_preview(*, is_manager: bool = False) -> dict[str, Any]:
    if is_manager:
        return {
            "default": {
                "mini_cards": [
                    {"k": str(_("Console")), "v": str(_("Live")), "s": str(_("Operator tools")), "tone": "hot"},
                    {"k": str(_("Schools")), "v": "—", "s": str(_("Provisioned tenants")), "tone": ""},
                    {"k": str(_("Support")), "v": str(_("Ready")), "s": str(_("Help desk")), "tone": "green"},
                ],
                "note": "",
            },
            "staff": {"mini_cards": [], "note": ""},
            "parent": {"mini_cards": [], "note": ""},
            "student": {"mini_cards": [], "note": ""},
        }
    return {
        "default": {
            "mini_cards": [
                {"k": str(_("Portal")), "v": str(_("Secure")), "s": str(_("Encrypted sign-in")), "tone": "hot"},
                {"k": str(_("Families")), "v": str(_("Linked")), "s": str(_("Invite-based access")), "tone": "green"},
                {"k": str(_("Staff")), "v": str(_("Ready")), "s": str(_("Gradebook & attendance")), "tone": "blue"},
            ],
            "note": "",
        },
        "staff": {
            "mini_cards": [
                {"k": str(_("Class")), "v": "—", "s": str(_("Sample roster")), "tone": "hot"},
                {"k": str(_("Pending")), "v": "—", "s": str(_("Grades after sign-in")), "tone": ""},
                {"k": str(_("Today")), "v": str(_("Live")), "s": str(_("Attendance register")), "tone": "green"},
            ],
            "note": str(
                _("Teachers land on the teacher dashboard with gradebook and class tools.")
            ),
        },
        "parent": {
            "mini_cards": [],
            "child_card": {
                "avatar": str(_("FG")),
                "title": str(_("Family portal preview")),
                "subtitle": str(
                    _("Fees, report cards, and teacher messages after you sign in.")
                ),
            },
            "note": str(
                _("First time? Use Family invite below to claim your school token.")
            ),
        },
        "student": {
            "mini_cards": [],
            "schedule_rows": [
                {
                    "time": str(_("Now")),
                    "title": str(_("Your timetable")),
                    "subtitle": str(_("Classes and rooms after sign-in")),
                },
                {
                    "time": str(_("Due")),
                    "title": str(_("Assignments")),
                    "subtitle": str(_("Homework and results in one place")),
                },
            ],
            "note": str(
                _("Students use school email or student ID — not the school name.")
            ),
        },
    }


def login_canvas_defaults(*, is_manager: bool = False) -> dict[str, Any]:
    """Factory defaults for ``cockpit_payload.login_immersive_canvas``."""
    if is_manager:
        slides = [
            {
                "eyebrow": str(_("Platform")),
                "title": str(_("One console for every school and operator workflow.")),
                "body": str(_("Provisioning, billing, and support in one surface.")),
                "role_hint": "",
            },
        ]
    else:
        slides = [
            {
                "eyebrow": str(_("Portal")),
                "title": str(
                    _("Attendance, marks, fees, and messages — one secure place.")
                ),
                "body": str(_("Sign in with your school email.")),
                "role_hint": "",
            },
            {
                "eyebrow": str(_("Staff")),
                "title": str(_("Gradebook, attendance, and announcements in one workspace.")),
                "body": str(_("Everything your team needs during the school day.")),
                "role_hint": "staff",
            },
            {
                "eyebrow": str(_("Families")),
                "title": str(_("Report cards and fee balances the same day they post.")),
                "body": str(_("Parents see updates without waiting for paper slips.")),
                "role_hint": "parent",
            },
        ]
    return {
        "enabled": True,
        "layout_preset": "civic_editorial",
        "theme_variant": "brand",
        "pro_enabled": False,
        "hero_banner": {
            "mode": "carousel",
            "full_bleed": True,
            "scroll_seconds": 32,
            "slides": slides,
        },
        "metrics": {
            "enabled": True,
            "tile_keys": [
                "students_active",
                "today_date",
                "portal_secure",
                "support_help",
            ],
        },
        "feed": {
            "source": "tenant_activity_ticker",
            "max_items": 5,
            "section_label": str(_("After you sign in")),
            "dash_title": str(_("Today at your school")),
        },
        "gallery": {
            "enabled": True,
            "items": [],
        },
        "trust_chips": [
            {"icon": "", "label": str(_("FERPA-safe"))},
            {"icon": "", "label": str(_("Encrypted"))},
            {"icon": "", "label": str(_("SSO ready"))},
            {"icon": "", "label": str(_("Tenant branded"))},
        ],
        "role_preview": {
            "staff": {"pill": str(_("Staff dashboard"))},
            "parent": {"pill": str(_("Family portal"))},
            "student": {"pill": str(_("Student hub"))},
            "default": {"pill": str(_("School pulse"))},
        },
        "dash_preview": _default_dash_preview(is_manager=is_manager),
        "monetization": {
            "allow_sponsored_slot": False,
            "sponsored_slots": [],
            "hide_when_offline": True,
            "max_visible": 1,
        },
        "local_first": {
            "enabled": True,
            "cache_safe_content": True,
            "status_label": str(_("Local-first front door")),
            "status_detail": str(
                _("School identity and essential notices remain available during an outage")
            ),
        },
        "zones": {
            "show_ticker": True,
            "show_bento": True,
            "show_feed": True,
            "show_gallery": True,
            "show_trust": True,
            "compact_on_short_viewport": True,
        },
    }


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, val in (override or {}).items():
        if key in out and isinstance(out[key], dict) and isinstance(val, dict):
            out[key] = _deep_merge(out[key], val)
        else:
            out[key] = val
    return out


def _resolve_cockpit_payload(request: Any) -> dict[str, Any]:
    site = getattr(request, "site_settings", None) or getattr(request, "SITE", None)
    if site is None:
        return {}
    payload = getattr(site, "cockpit_payload", None)
    return payload if isinstance(payload, dict) else {}


def login_canvas_pro_enabled(request: Any, section: dict[str, Any]) -> bool:
    if bool(section.get("pro_enabled")):
        return True
    school = getattr(request, "school", None)
    if school is not None:
        has_feature = getattr(school, "has_feature", None)
        if callable(has_feature) and has_feature("login_canvas_pro"):
            return True
        features = getattr(school, "features", None) or {}
        if isinstance(features, dict) and features.get("login_canvas_pro"):
            return True
        addons = features.get("addons") if isinstance(features.get("addons"), list) else []
        if "login_canvas_pro" in addons:
            return True
    return str(section.get("tier") or "").lower() == "pro"


def _slide_is_active(slide: dict[str, Any], now: datetime) -> bool:
    start_raw = slide.get("publish_start_iso") or slide.get("start_iso") or ""
    end_raw = slide.get("publish_end_iso") or slide.get("end_iso") or ""
    try:
        if start_raw:
            start = datetime.fromisoformat(str(start_raw).replace("Z", "+00:00"))
            if timezone.is_naive(start):
                start = timezone.make_aware(start)
            if now < start:
                return False
        if end_raw:
            end = datetime.fromisoformat(str(end_raw).replace("Z", "+00:00"))
            if timezone.is_naive(end):
                end = timezone.make_aware(end)
            if now > end:
                return False
    except (TypeError, ValueError):
        pass
    return True


def _filter_slides(slides: list[dict[str, Any]], *, pro: bool) -> list[dict[str, Any]]:
    now = timezone.localtime(timezone.now())
    active: list[dict[str, Any]] = []
    for slide in slides:
        if not isinstance(slide, dict):
            continue
        title = str(slide.get("title") or "").strip()
        if not title:
            continue
        if not _slide_is_active(slide, now):
            continue
        active.append(
            {
                "eyebrow": str(slide.get("eyebrow") or "").strip(),
                "title": title,
                "body": str(slide.get("body") or "").strip(),
                "cta_label": str(slide.get("cta_label") or "").strip(),
                "cta_url": _safe_public_url(slide.get("cta_url")),
                "image_url": _safe_public_url(slide.get("image_url")),
                "role_hint": str(slide.get("role_hint") or "").strip().lower(),
                "sponsored": bool(slide.get("sponsored")),
            }
        )
    cap = PRO_MAX_SLIDES if pro else FREE_MAX_SLIDES
    return active[:cap]


def _resolve_metric(key: str, request: Any, school: Any, now: datetime) -> dict[str, str]:
    meta = METRIC_CATALOG.get(key) or {"label": key, "sub": ""}
    label = str(meta.get("label") or key)
    sub = str(meta.get("sub") or "")
    value = "—"
    if key == "students_active":
        try:
            from apps.people.models import StudentProfile

            if school:
                count = StudentProfile.objects.filter(school=school, is_active=True).count()
                value = str(count)
                sub = str(_("Enrolled"))
        except Exception:
            value = "—"
            sub = str(_("Live data after sign-in"))
    elif key == "today_date":
        value = now.strftime("%a")
        sub = now.strftime("%b %d")
    elif key == "portal_secure":
        value = str(_("Secure"))
        sub = str(_("Encrypted sign-in"))
    elif key == "support_help":
        value = str(_("Help"))
        sub = str(_("Office or IT desk"))
    elif key == "events_this_week":
        try:
            from apps.school_events.models import SchoolEvent

            if school:
                start = now.date()
                end = start + timedelta(days=7)
                # tenant-isolation-allow: login-canvas-anonymous-event-count
                count = SchoolEvent.objects.filter(
                    school=school, start_at__date__gte=start, start_at__date__lte=end
                ).count()
                value = str(count)
                sub = str(_("Scheduled"))
        except Exception:
            value = "—"
    elif key == "attendance_rate_7d":
        try:
            from apps.academics.models import Attendance

            if school:
                start = now.date() - timedelta(days=7)
                qs = Attendance.objects.filter(school=school, date__gte=start)
                total = qs.count()
                if total:
                    present = qs.filter(
                        status__in=[
                            Attendance.Status.PRESENT,
                            Attendance.Status.LATE,
                            Attendance.Status.EXCUSED,
                        ]
                    ).count()
                    pct = round((present / total) * 100)
                    value = f"{pct}%"
                    sub = str(_("7-day aggregate"))
                else:
                    value = "—"
                    sub = str(_("After sign-in"))
        except Exception:
            value = "—"
            sub = str(_("After sign-in"))
    elif key == "staff_active":
        try:
            from apps.accounts.models import User

            if school:
                # tenant-isolation-allow: login-canvas-anonymous-staff-count
                count = User.objects.filter(
                    school_memberships__school=school, is_active=True
                ).distinct().count()
                value = str(count)
                sub = str(_("Active"))
        except Exception:
            value = "—"
    elif key == "languages_count":
        try:
            from apps.siteconfig.translations import SUPPORTED_LANGUAGES

            value = str(len(SUPPORTED_LANGUAGES))
            sub = str(_("Locales"))
        except Exception:
            value = "—"
    return {"label": label, "value": value, "sub": sub, "key": key}


# Metric tiles whose value never depends on tenant data — a safe backfill when a
# live metric resolves to a bare "—" (Students on the manager host / anonymous
# session / a query failure), so the bento grid never shows a dead tile.
_ALWAYS_RESOLVABLE_TILE_KEYS = (
    "today_date",
    "portal_secure",
    "support_help",
    "languages_count",
)


def _tile_has_value(tile: dict[str, str]) -> bool:
    """True when a tile carries a real value (``0`` counts; a bare em dash does not)."""
    return str(tile.get("value") or "").strip() not in ("", "—", "-")


def _finalize_bento(
    tiles: list[dict[str, str]], request: Any, school: Any, now: datetime
) -> list[dict[str, str]]:
    """Replace any tile that resolved to a dead "—" with the next always-resolvable
    tile, keeping the tile count + positions stable so the 4-up grid never gaps."""
    used = {t.get("key") for t in tiles if _tile_has_value(t)}
    fallbacks = [k for k in _ALWAYS_RESOLVABLE_TILE_KEYS if k not in used]
    out: list[dict[str, str]] = []
    for tile in tiles:
        if _tile_has_value(tile):
            out.append(tile)
            continue
        replacement = None
        while fallbacks:
            candidate = _resolve_metric(fallbacks.pop(0), request, school, now)
            if _tile_has_value(candidate):
                used.add(candidate["key"])
                replacement = candidate
                break
        out.append(replacement or tile)
    return out


def _default_gallery(request: Any, wallpaper_url: str) -> list[dict[str, str]]:
    from django.templatetags.static import static

    items = [
        {
            "url": static("images/marketing/platform-teacher-workspace.svg"),
            "caption": str(_("Teacher workspace")),
            "alt": str(_("Teacher workspace preview")),
            "link_url": "",
        },
        {
            "url": static("images/marketing/platform-parent-mobile-portal.svg"),
            "caption": str(_("Family portal")),
            "alt": str(_("Family portal preview")),
            "link_url": "",
        },
        {
            "url": static("images/marketing/platform-student-self-service.svg"),
            "caption": str(_("Student hub")),
            "alt": str(_("Student hub preview")),
            "link_url": "",
        },
    ]
    if wallpaper_url:
        items[0] = {
            "url": wallpaper_url,
            "caption": str(_("Campus")),
            "alt": str(_("Campus")),
            "link_url": "",
        }
    return items


def _ticker_items(section: dict[str, Any]) -> list[str]:
    items: list[str] = []
    for card in section.get("cards") or []:
        if not isinstance(card, dict):
            continue
        text = str(card.get("text") or "").strip()
        if text:
            items.append(text)
    for ann in section.get("announcements") or []:
        if not isinstance(ann, dict):
            continue
        text = str(ann.get("text") or "").strip()
        if text and text not in items:
            items.append(text)
    return items[:12]


def _dash_feed(
    section: dict[str, Any], *, max_items: int, is_manager: bool = False
) -> list[dict[str, str]]:
    feed: list[dict[str, str]] = []
    for card in (section.get("cards") or [])[:max_items]:
        if not isinstance(card, dict):
            continue
        text = str(card.get("text") or "").strip()
        if not text:
            continue
        severity = str(card.get("severity") or "info").lower()
        tag = _("Info")
        tag_class = "info"
        if severity in {"danger", "critical"}:
            tag = _("Urgent")
            tag_class = "warn"
        elif severity in {"success", "ok"}:
            tag = _("Update")
            tag_class = "ok"
        icon = str(card.get("icon") or "📢").strip() or "📢"
        feed.append(
            {
                "icon": icon,
                "title": text.split("·")[0].strip()[:80],
                "subtitle": text if "·" in text else "",
                "tag": str(tag),
                "tag_class": tag_class,
            }
        )
    if not feed:
        # No live announcements yet — orient the visitor with what's inside
        # instead of one lonely placeholder card in a tall panel. Host-aware so
        # the operator console never shows parent/fees copy.
        if is_manager:
            feed = [
                {
                    "icon": "🏫",
                    "title": str(_("Provisioning")),
                    "subtitle": str(_("New schools onboarded in minutes")),
                    "tag": str(_("Console")),
                    "tag_class": "ok",
                },
                {
                    "icon": "💳",
                    "title": str(_("Billing & plans")),
                    "subtitle": str(_("Subscriptions, invoices, and regional pricing")),
                    "tag": str(_("Portal")),
                    "tag_class": "info",
                },
                {
                    "icon": "🛟",
                    "title": str(_("Support desk")),
                    "subtitle": str(_("Tenant health and operator tickets")),
                    "tag": str(_("Info")),
                    "tag_class": "info",
                },
            ]
        else:
            feed = [
                {
                    "icon": "📣",
                    "title": str(_("School announcements")),
                    "subtitle": str(_("Current notices · cached locally when allowed")),
                    "tag": str(_("Today")),
                    "tag_class": "ok",
                },
                {
                    "icon": "🚌",
                    "title": str(_("Transport")),
                    "subtitle": str(_("Campus routes and timing after sign-in")),
                    "tag": str(_("Today")),
                    "tag_class": "info",
                },
                {
                    "icon": "🛡️",
                    "title": str(_("Campus status")),
                    "subtitle": str(_("Open · support hours on this school")),
                    "tag": str(_("Today")),
                    "tag_class": "info",
                },
            ]
    return feed


def merge_operator_sponsored_slots(
    section: dict[str, Any], operator_payload: dict[str, Any]
) -> list[dict[str, Any]]:
    if not section.get("monetization", {}).get("allow_sponsored_slot"):
        return []
    tenant_slots = section.get("monetization", {}).get("sponsored_slots") or []
    operator_slots = operator_payload.get("login_immersive_canvas", {}).get(
        "network_sponsored_slots"
    ) or []
    merged: list[dict[str, Any]] = []
    for raw in list(operator_slots) + list(tenant_slots):
        if not isinstance(raw, dict):
            continue
        label = str(raw.get("label") or raw.get("title") or "").strip()[:120]
        if not label:
            continue
        cta_url = _safe_public_url(raw.get("cta_url"))
        if raw.get("cta_url") and not cta_url:
            continue
        merged.append(
            {
                "eyebrow": str(_("Local partner · Sponsored")),
                "title": label,
                "body": str(raw.get("body") or "").strip()[:280],
                "cta_label": str(raw.get("cta_label") or _("Learn more"))[:60],
                "cta_url": cta_url,
                "sponsored": True,
                "source": "tenant" if raw in tenant_slots else "operator",
            }
        )
    max_visible = section.get("monetization", {}).get("max_visible", 1)
    try:
        max_visible = max(0, min(int(max_visible), 2))
    except (TypeError, ValueError):
        max_visible = 1
    return merged[:max_visible]


def _safe_public_url(value: Any) -> str:
    """Allow same-site paths and HTTP(S) links on the anonymous login surface."""
    candidate = str(value or "").strip()
    if not candidate:
        return ""
    if candidate.startswith("/") and not candidate.startswith("//"):
        return candidate
    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return ""
    return (
        candidate
        if parsed.scheme in {"http", "https"}
        and parsed.netloc
        and not parsed.username
        and not parsed.password
        else ""
    )


def resolve_login_immersive_section(request: Any) -> dict[str, Any]:
    """Merge defaults + tenant payload + apply tier limits."""
    is_manager = getattr(request, "public_host_kind", None) == "manager"
    section = login_canvas_defaults(is_manager=is_manager)
    payload = _resolve_cockpit_payload(request)
    tenant_overlay = payload.get("login_immersive_canvas")
    if isinstance(tenant_overlay, dict):
        section = _deep_merge(section, tenant_overlay)

    pro = login_canvas_pro_enabled(request, section)
    if not pro:
        hero = section.setdefault("hero_banner", {})
        mode = str(hero.get("mode") or "carousel").lower()
        if mode in {"marquee", "hybrid"}:
            hero["mode"] = "carousel"
        slides = _filter_slides(hero.get("slides") or [], pro=False)
        hero["slides"] = slides or _filter_slides(
            login_canvas_defaults(is_manager=is_manager)["hero_banner"]["slides"],
            pro=False,
        )

    layout = str(section.get("layout_preset") or "civic_editorial").lower()
    if layout not in LAYOUT_PRESETS:
        section["layout_preset"] = "civic_editorial"

    theme = str(section.get("theme_variant") or "brand").lower()
    if theme not in THEME_VARIANTS:
        section["theme_variant"] = "brand"

    hero = section.setdefault("hero_banner", {})
    mode = str(hero.get("mode") or "carousel").lower()
    if mode not in HERO_MODES:
        hero["mode"] = "carousel"
    hero["slides"] = _filter_slides(
        hero.get("slides") or login_canvas_defaults(is_manager=is_manager)["hero_banner"]["slides"],
        pro=pro,
    )
    sponsored = merge_operator_sponsored_slots(section, payload)
    section["resolved_sponsored_slots"] = sponsored if pro else []

    return section


def build_login_immersive_render_context(request: Any) -> dict[str, Any]:
    """Anonymous-safe render dict for ``templates/auth/login.html``."""
    is_manager = getattr(request, "public_host_kind", None) == "manager"
    school = getattr(request, "school", None)
    section = resolve_login_immersive_section(request)

    if not section.get("enabled", True):
        section = login_canvas_defaults(is_manager=is_manager)

    site_tagline = ""
    wallpaper = ""
    try:
        from apps.platform_runtime.config_resolver import get_effective_config

        site_tagline = str(
            get_effective_config(key="login_hero_subtext", request=request, school=school)
            or get_effective_config(key="tagline", request=request, school=school)
            or ""
        )
    except Exception:
        site_tagline = ""
    try:
        from apps.siteconfig.context_processors import site_settings

        ctx = site_settings(request)
        wallpaper = (ctx.get("TENANT_WALLPAPER_URL") or "").strip()
    except Exception:
        wallpaper = ""

    ticker_section: dict[str, Any] = {"cards": [], "announcements": []}
    try:
        from apps.siteconfig.cockpit_context import _resolve_cockpit_payload
        from apps.siteconfig.cockpit_live_banner_program import finalize_live_banner_section

        payload = _resolve_cockpit_payload(request)
        if is_manager:
            ticker_section = dict(payload.get("activity_ticker") or {})
        else:
            ticker_section = dict(payload.get("tenant_activity_ticker") or {})
        ticker_section = finalize_live_banner_section(ticker_section, request)
    except Exception:
        pass

    now = timezone.localtime(timezone.now())
    pro = login_canvas_pro_enabled(request, section)
    hero = section.get("hero_banner") or {}
    requested_mode = str(hero.get("mode") or "carousel").lower()
    pro_downgraded = not pro and requested_mode in {"marquee", "hybrid"}
    metrics_cfg = section.get("metrics") or {}
    feed_cfg = section.get("feed") or {}
    gallery_cfg = section.get("gallery") or {}
    zones = section.get("zones") or {}
    local_first = section.get("local_first") or {}
    monetization = section.get("monetization") or {}

    tile_keys = list(metrics_cfg.get("tile_keys") or [])[:4]
    if not tile_keys:
        tile_keys = login_canvas_defaults(is_manager=is_manager)["metrics"]["tile_keys"]
    bento = (
        _finalize_bento(
            [_resolve_metric(k, request, school, now) for k in tile_keys],
            request,
            school,
            now,
        )
        if metrics_cfg.get("enabled", True)
        else []
    )

    gallery_items = []
    for item in gallery_cfg.get("items") or []:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or item.get("image_url") or "").strip()
        if not url:
            continue
        gallery_items.append(
            {
                "url": url,
                "caption": str(item.get("caption") or "").strip(),
                "alt": str(item.get("alt") or item.get("caption") or "").strip(),
                "link_url": str(item.get("link_url") or "").strip(),
            }
        )
    if not gallery_items:
        gallery_items = _default_gallery(request, wallpaper)
    cap = PRO_MAX_GALLERY if pro else FREE_MAX_GALLERY
    gallery_items = gallery_items[:cap]

    trust_chips = []
    for chip in section.get("trust_chips") or []:
        if isinstance(chip, str) and chip.strip():
            trust_chips.append({"icon": "", "label": chip.strip()})
        elif isinstance(chip, dict) and str(chip.get("label") or "").strip():
            trust_chips.append(
                {
                    "icon": str(chip.get("icon") or "").strip(),
                    "label": str(chip.get("label") or "").strip(),
                }
            )

    role_preview = section.get("role_preview") or {}
    dash_preview = _deep_merge(
        _default_dash_preview(is_manager=is_manager),
        section.get("dash_preview") or {},
    )
    ticker_items = _ticker_items(ticker_section)
    if not ticker_items:
        ticker_items = [
            str(_("Welcome — sign in to reach your school workspace.")),
            str(_("Secure local-first access for staff, families, and students.")),
        ]

    return {
        "canvas": section,
        "layout_preset": section.get("layout_preset", "civic_editorial"),
        "theme_variant": section.get("theme_variant", "brand"),
        "pro_enabled": pro,
        "hero_mode": hero.get("mode", "carousel"),
        "hero_full_bleed": bool(hero.get("full_bleed", True)),
        "hero_scroll_seconds": int(hero.get("scroll_seconds") or 32),
        "carousel_slides": hero.get("slides") or [],
        "marquee_lines": [
            s.get("title") for s in (hero.get("slides") or []) if s.get("title")
        ],
        "ticker_items": ticker_items if zones.get("show_ticker", True) else [],
        "bento_stats": bento if zones.get("show_bento", True) else [],
        "dash_feed": _dash_feed(
            ticker_section,
            max_items=int(feed_cfg.get("max_items") or 5),
            is_manager=is_manager,
        )
        if zones.get("show_feed", True)
        else [],
        "feed_section_label": str(
            feed_cfg.get("section_label") or _("After you sign in")
        ),
        "dash_title": str(feed_cfg.get("dash_title") or _("Today at your school")),
        "moments": gallery_items if zones.get("show_gallery", True) else [],
        "trust_chips": trust_chips if zones.get("show_trust", True) else [],
        "sponsored_slots": section.get("resolved_sponsored_slots") or [],
        # Tenant front doors may advertise the governed placement even before
        # a campaign exists. Operator authentication remains promotion-free.
        "partner_surface_enabled": not is_manager,
        "hide_sponsored_offline": bool(monetization.get("hide_when_offline", True)),
        "local_first_enabled": bool(local_first.get("enabled", True)),
        "local_first_cache_safe": bool(local_first.get("cache_safe_content", True)),
        "local_first_status_label": str(
            local_first.get("status_label") or _("Local-first front door")
        ),
        "local_first_status_detail": str(
            local_first.get("status_detail")
            or _("School identity and essential notices remain available during an outage")
        ),
        "role_preview_labels": {
            "staff": str(
                (role_preview.get("staff") or {}).get("pill") or _("Staff dashboard")
            ),
            "parent": str(
                (role_preview.get("parent") or {}).get("pill") or _("Family portal")
            ),
            "student": str(
                (role_preview.get("student") or {}).get("pill") or _("Student hub")
            ),
            "default": str(
                (role_preview.get("default") or {}).get("pill") or _("School pulse")
            ),
        },
        "dash_preview": dash_preview,
        "pro_downgraded_hero": pro_downgraded,
        "compact_on_short_viewport": bool(zones.get("compact_on_short_viewport", True)),
        "clock_label": now.strftime("%H:%M"),
        "date_label": now.strftime("%a, %b %d"),
        "site_tagline": site_tagline,
    }


def build_login_canvas_cockpit_preview(section: dict[str, Any], request: Any) -> dict[str, Any]:
    """Compact operator preview dict for cockpit configure."""
    hero = section.get("hero_banner") or {}
    slides = hero.get("slides") or []
    zones = section.get("zones") or {}
    metrics = section.get("metrics") or {}
    gallery = section.get("gallery") or {}
    pro = login_canvas_pro_enabled(request, section)
    return {
        "enabled": bool(section.get("enabled", True)),
        "layout_preset": section.get("layout_preset", "civic_editorial"),
        "theme_variant": section.get("theme_variant", "brand"),
        "hero_mode": hero.get("mode", "carousel"),
        "hero_scroll_seconds": int(hero.get("scroll_seconds") or 32),
        "slide_count": len(slides),
        "slide_titles": [str(s.get("title") or "") for s in slides[:4] if s.get("title")],
        "metric_keys": list(metrics.get("tile_keys") or [])[:4],
        "gallery_count": len(gallery.get("items") or []),
        "trust_count": len(section.get("trust_chips") or []),
        "zones": zones,
        "pro_enabled": pro,
        "sponsored_count": len(
            (section.get("monetization") or {}).get("sponsored_slots") or []
        ),
    }
