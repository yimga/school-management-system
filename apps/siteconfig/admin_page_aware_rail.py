"""
Page-aware Django admin context rail facts.

Fills the Operator/School boundary column with model/object/list-aware content
instead of static prose. Used by ``admin_page_aware`` template tags.
"""

from __future__ import annotations

from typing import Any

from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext as _


def _safe_str(value: Any, *, limit: int = 72) -> str:
    try:
        text = str(value or "").strip()
    except Exception:  # noqa: BLE001
        text = ""
    if len(text) > limit:
        return text[: limit - 1] + "…"
    return text


def _school_label(request) -> str:
    school = getattr(request, "school", None) if request is not None else None
    if school is None:
        return ""
    for attr in ("name", "display_name", "site_name", "slug"):
        try:
            val = getattr(school, attr, None)
        except Exception:  # noqa: BLE001
            val = None
        if val:
            return _safe_str(val, limit=48)
    return ""


def _boundary_title(*, is_manager_host: bool) -> str:
    return _("Operator boundary") if is_manager_host else _("School boundary")


def _boundary_fallback(*, is_manager_host: bool, request=None) -> str:
    if is_manager_host:
        return _("Platform backoffice")
    school = _school_label(request)
    return school or _("School configuration")


def _attr_first(obj: Any, names: tuple[str, ...]) -> Any:
    for name in names:
        if obj is None:
            return None
        try:
            if hasattr(obj, name):
                val = getattr(obj, name)
                if callable(val):
                    continue
                if val not in (None, ""):
                    return val
        except Exception:  # noqa: BLE001
            continue
    return None


def build_change_form_rail(
    *,
    request,
    opts,
    original=None,
    add: bool = False,
    change: bool = False,
    has_absolute_url: bool = False,
    absolute_url: str = "",
    is_manager_host: bool = False,
    admin_outcome_deck: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Facts for change-form rail: this object + mode + related guided paths."""
    if opts is None:
        return {
            "surface": "change-form",
            "is_manager_host": bool(is_manager_host),
            "boundary_title": _boundary_title(is_manager_host=is_manager_host),
            "boundary_strong": _boundary_fallback(is_manager_host=is_manager_host, request=request),
            "boundary_hint": _("Open a model to see page-aware context."),
            "page_title": _("Admin form"),
            "page_lede": _("Page-aware facts appear when a model form is loaded."),
            "facts": [],
            "links": [],
            "guided": _guided_from_deck(admin_outcome_deck)[:5],
            "pulse_enabled": False,
        }
    app_label = getattr(opts, "app_label", "") or ""
    model_name = getattr(opts, "model_name", "") or ""
    verbose = _safe_str(getattr(opts, "verbose_name", "") or model_name, limit=48)
    verbose_plural = _safe_str(
        getattr(opts, "verbose_name_plural", "") or verbose, limit=48
    )

    if add:
        mode_label = _("Adding")
        mode_hint = _("New %(name)s — save creates the first row.") % {"name": verbose}
        object_title = _("New %(name)s") % {"name": verbose}
        object_id = ""
    else:
        mode_label = _("Editing")
        mode_hint = _("Change %(name)s — save updates this row only.") % {"name": verbose}
        object_title = _safe_str(original, limit=56) or verbose
        object_id = _safe_str(getattr(original, "pk", ""), limit=36)

    facts: list[dict[str, str]] = [
        {"label": _("App"), "value": app_label or "—"},
        {"label": _("Model"), "value": model_name or "—"},
        {"label": _("Mode"), "value": mode_label},
    ]
    if object_id:
        facts.append({"label": _("Primary key"), "value": object_id})

    stamp = _attr_first(
        original,
        ("updated_at", "modified", "modified_at", "last_login", "date_joined", "created_at"),
    )
    if stamp is not None:
        facts.append({"label": _("Timestamp"), "value": _safe_str(stamp, limit=40)})

    status = _attr_first(original, ("status", "state", "is_active", "role"))
    if status is not None:
        if isinstance(status, bool):
            facts.append(
                {
                    "label": _("Active"),
                    "value": _("Yes") if status else _("No"),
                }
            )
        else:
            facts.append({"label": _("Status"), "value": _safe_str(status, limit=40)})

    links: list[dict[str, str]] = []
    try:
        changelist_url = reverse(f"admin:{app_label}_{model_name}_changelist")
        links.append({"label": _("All %(name)s") % {"name": verbose_plural}, "url": changelist_url})
    except NoReverseMatch:
        pass
    # History / View on site live in workspace head — not duplicated here.

    # v15 I9: no related-outcome wall on Edit — tip lives in command-band ⓘ.
    return {
        "surface": "change-form",
        "is_manager_host": bool(is_manager_host),
        "boundary_title": _boundary_title(is_manager_host=is_manager_host),
        "boundary_strong": (
            _("%(app)s · %(model)s") % {"app": app_label, "model": model_name}
            if app_label and model_name
            else _boundary_fallback(is_manager_host=is_manager_host, request=request)
        ),
        "boundary_hint": mode_hint,
        "page_title": object_title,
        "page_lede": mode_hint,
        "facts": facts,
        "links": links[:5],
        "guided": [],
        "pulse_enabled": True,
    }


def build_changelist_rail(
    *,
    request,
    opts,
    cl,
    is_manager_host: bool = False,
    admin_outcome_deck: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Facts for changelist rail: result counts, filters, model identity."""
    if opts is None and cl is not None:
        opts = getattr(cl, "opts", None)
    if opts is None or cl is None:
        return {
            "surface": "change-list",
            "is_manager_host": bool(is_manager_host),
            "boundary_title": _boundary_title(is_manager_host=is_manager_host),
            "boundary_strong": _boundary_fallback(is_manager_host=is_manager_host, request=request),
            "boundary_hint": _("Open a changelist to see page-aware list context."),
            "page_title": _("Records list"),
            "page_lede": _("Counts and filters appear when a list is loaded."),
            "facts": [],
            "links": [],
            "guided": _guided_from_deck(admin_outcome_deck)[:5],
            "pulse_enabled": False,
        }
    app_label = getattr(opts, "app_label", "") or ""
    model_name = getattr(opts, "model_name", "") or ""
    verbose = _safe_str(getattr(opts, "verbose_name", "") or model_name, limit=48)
    verbose_plural = _safe_str(
        getattr(opts, "verbose_name_plural", "") or verbose, limit=48
    )

    result_count = int(getattr(cl, "result_count", 0) or 0)
    full_count = getattr(cl, "full_result_count", None)
    try:
        full_count_i = int(full_count) if full_count is not None else None
    except (TypeError, ValueError):
        full_count_i = None

    has_filters = bool(getattr(cl, "has_filters", False))
    has_active = bool(getattr(cl, "has_active_filters", False))
    page_num = getattr(getattr(cl, "page_num", None), "number", None) or getattr(
        cl, "page_num", None
    )

    facts: list[dict[str, str]] = [
        {"label": _("App"), "value": app_label or "—"},
        {"label": _("Model"), "value": model_name or "—"},
        {
            "label": _("On this page"),
            "value": _("%(n)s shown") % {"n": result_count},
        },
    ]
    if full_count_i is not None and full_count_i != result_count:
        facts.append(
            {
                "label": _("Total matching"),
                "value": str(full_count_i),
            }
        )
    if has_filters:
        facts.append(
            {
                "label": _("Filters"),
                "value": _("Active") if has_active else _("Available"),
            }
        )
    if page_num not in (None, "", 1, "1"):
        facts.append({"label": _("Page"), "value": _safe_str(page_num, limit=12)})

    links: list[dict[str, str]] = []
    # v15: Add lives in the Scan command band — do not duplicate in the rail.

    lede = _("Native list for %(name)s.") % {"name": verbose_plural}
    if has_active:
        lede = _("Filtered %(name)s list — clear filters to see the full set.") % {
            "name": verbose_plural
        }

    # v15 I9: list rail = live counts/filters only (no guided CTA wall).
    return {
        "surface": "change-list",
        "is_manager_host": bool(is_manager_host),
        "boundary_title": _boundary_title(is_manager_host=is_manager_host),
        "boundary_strong": (
            _("%(app)s · %(model)s") % {"app": app_label, "model": model_name}
            if app_label and model_name
            else _boundary_fallback(is_manager_host=is_manager_host, request=request)
        ),
        "boundary_hint": lede,
        "page_title": verbose_plural,
        "page_lede": lede,
        "facts": facts,
        "links": links[:4],
        "guided": [],
        "pulse_enabled": False,
    }


def build_index_rail(
    *,
    request,
    is_manager_host: bool = False,
    admin_catalog: Any = None,
) -> dict[str, Any]:
    """Facts for admin index rail: catalog density + guided paths already on page."""
    section_count = 0
    model_count = 0
    try:
        sections = list(admin_catalog or [])
        section_count = len(sections)
        for sec in sections:
            models = getattr(sec, "models", None) or (sec.get("models") if isinstance(sec, dict) else None) or []
            model_count += len(models)
    except Exception:  # noqa: BLE001
        section_count = 0
        model_count = 0

    facts = [
        {
            "label": _("Catalog sections"),
            "value": str(section_count) if section_count else _("—"),
        },
        {
            "label": _("Models listed"),
            "value": str(model_count) if model_count else _("—"),
        },
        {
            "label": _("Surface"),
            "value": _("Operator index") if is_manager_host else _("School index"),
        },
    ]
    return {
        "surface": "index",
        "is_manager_host": bool(is_manager_host),
        "boundary_title": _boundary_title(is_manager_host=is_manager_host),
        "boundary_strong": (
            _("Platform backoffice catalog")
            if is_manager_host
            else (_("%(school)s · configuration") % {"school": _school_label(request)} if _school_label(request) else _("School configuration catalog"))
        ),
        "boundary_hint": _(
            "Jump via Guided paths above; this rail tracks what is on the catalog."
        ),
        "page_title": _("Admin catalog"),
        "page_lede": _("Page-aware index — section and model counts from this host."),
        "facts": facts,
        "links": [],
        "guided": [],
        "pulse_enabled": False,
    }


def build_app_index_rail(
    *,
    request,
    is_manager_host: bool = False,
    app_label: str = "",
    title: str = "",
    models: Any = None,
) -> dict[str, Any]:
    """Facts for /admin/<app>/ app index — model density for this app."""
    model_rows = list(models or [])
    model_count = len(model_rows)
    addable = 0
    for row in model_rows:
        if isinstance(row, dict):
            if row.get("add_url"):
                addable += 1
        elif getattr(row, "add_url", None):
            addable += 1

    label = _safe_str(app_label or title, limit=40) or _("app")
    facts = [
        {"label": _("App"), "value": label},
        {"label": _("Models"), "value": str(model_count) if model_count else _("—")},
        {"label": _("Addable"), "value": str(addable)},
        {
            "label": _("Surface"),
            "value": _("Operator app") if is_manager_host else _("School app"),
        },
    ]
    links: list[dict[str, str]] = []
    try:
        links.append({"label": _("Full catalog"), "url": reverse("admin:index")})
    except NoReverseMatch:
        pass

    return {
        "surface": "app-index",
        "is_manager_host": bool(is_manager_host),
        "boundary_title": _boundary_title(is_manager_host=is_manager_host),
        "boundary_strong": _("App · %(label)s") % {"label": label},
        "boundary_hint": _("Models in this app — prefer guided surfaces when linked."),
        "page_title": _safe_str(title, limit=56) or label,
        "page_lede": _("Page-aware app catalog for %(label)s.") % {"label": label},
        "facts": facts,
        "links": links,
        "guided": [],
        "pulse_enabled": False,
    }


def build_guided_surface_rail(
    *,
    request,
    is_manager_host: bool = False,
    page_title: str = "",
    page_lede: str = "",
    facts: list[dict[str, str]] | None = None,
    links: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Page-aware rail for special admin actions (waive, guided delete, etc.)."""
    fact_rows = list(facts or [])
    if not fact_rows:
        fact_rows = [
            {
                "label": _("Surface"),
                "value": _("Operator action") if is_manager_host else _("School action"),
            },
            {"label": _("Workflow"), "value": _("Guided")},
        ]
    link_rows = list(links or [])
    if not link_rows:
        try:
            link_rows.append({"label": _("Admin home"), "url": reverse("admin:index")})
        except NoReverseMatch:
            pass
    return {
        "surface": "guided",
        "is_manager_host": bool(is_manager_host),
        "boundary_title": _boundary_title(is_manager_host=is_manager_host),
        "boundary_strong": _("Guided admin action"),
        "boundary_hint": page_lede or _("Complete this workflow, then return to the list."),
        "page_title": page_title or _("Guided action"),
        "page_lede": page_lede or _("Page-aware context for this admin workflow."),
        "facts": fact_rows,
        "links": link_rows[:5],
        "guided": [],
        "pulse_enabled": False,
    }


def _guided_from_deck(deck: dict[str, Any] | None) -> list[dict[str, str]]:
    if not deck:
        return []
    out: list[dict[str, str]] = []
    for link in list(deck.get("admin_deck_links") or [])[:6]:
        url = (link.get("url") or "").strip()
        label = _safe_str(link.get("label"), limit=42)
        if url and label:
            out.append({"label": label, "url": url})
    return out
