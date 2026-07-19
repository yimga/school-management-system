from __future__ import annotations

from django import template

from apps.siteconfig.admin_page_aware_rail import (
    build_app_index_rail,
    build_change_form_rail,
    build_changelist_rail,
    build_guided_surface_rail,
    build_index_rail,
)

register = template.Library()


@register.inclusion_tag(
    "admin/includes/admin_page_aware_rail_cards.html",
    takes_context=True,
)
def admin_page_aware_rail(context, surface: str = "change-form"):
    """Render page-aware rail cards for all Django admin surface families."""
    request = context.get("request")
    is_manager = bool(context.get("is_manager_host"))
    deck = context.get("admin_outcome_deck")

    if surface == "change-list":
        payload = build_changelist_rail(
            request=request,
            opts=context.get("opts") or getattr(context.get("cl"), "opts", None),
            cl=context.get("cl"),
            is_manager_host=is_manager,
            admin_outcome_deck=deck,
        )
    elif surface == "index":
        catalog = context.get("admin_catalog")
        if catalog is not None and hasattr(catalog, "sections"):
            catalog = getattr(catalog, "sections", catalog)
        payload = build_index_rail(
            request=request,
            is_manager_host=is_manager,
            admin_catalog=catalog
            or context.get("app_list")
            or context.get("admin_sections"),
        )
    elif surface == "app-index":
        models = context.get("admin_app_index_models")
        if not models:
            models = []
            for app in context.get("app_list") or []:
                rows = getattr(app, "models", None)
                if rows is None and isinstance(app, dict):
                    rows = app.get("models")
                models.extend(list(rows or []))
        payload = build_app_index_rail(
            request=request,
            is_manager_host=is_manager,
            app_label=str(context.get("app_label") or ""),
            title=str(context.get("title") or ""),
            models=models,
        )
    elif surface == "guided":
        payload = build_guided_surface_rail(
            request=request,
            is_manager_host=is_manager,
            page_title=str(context.get("guided_rail_title") or context.get("title") or ""),
            page_lede=str(context.get("guided_rail_lede") or ""),
            facts=list(context.get("guided_rail_facts") or []),
            links=list(context.get("guided_rail_links") or []),
        )
    else:
        payload = build_change_form_rail(
            request=request,
            opts=context.get("opts"),
            original=context.get("original"),
            add=bool(context.get("add")),
            change=bool(context.get("change")),
            has_absolute_url=bool(context.get("has_absolute_url")),
            absolute_url=context.get("absolute_url") or "",
            is_manager_host=is_manager,
            admin_outcome_deck=deck,
        )
    return {"rail": payload, "request": request}
