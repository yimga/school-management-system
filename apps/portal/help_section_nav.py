"""Curated in-page section nav for help hubs (manager + tenant)."""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _


def manager_help_section_nav_items(
    help_sections: list[dict],
    *,
    include_quickstart: bool = True,
    include_featured: bool = False,
) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    if include_quickstart:
        items.append(
            {
                "id": "rmc-persona-help-heading",
                "label": str(_("Quick start by role")),
            }
        )
    if include_featured:
        items.append(
            {
                "id": "rmc-help-featured-heading",
                "label": str(_("Featured runbooks")),
            }
        )
    for section in help_sections:
        sid = section.get("id")
        title = section.get("title")
        if not sid or not title:
            continue
        items.append(
            {
                "id": f"rmc-help-section-{sid}",
                "label": str(title),
            }
        )
    return items


def tenant_help_section_nav_items() -> list[dict[str, str]]:
    return [
        {"id": "rmc-help-quick-lane", "label": str(_("Quick links"))},
        {"id": "rmc-help-search", "label": str(_("Search help"))},
        {"id": "rmc-help-release-notes", "label": str(_("What's new"))},
        {"id": "rmc-help-you-said", "label": str(_("You said. We did."))},
    ]


def admin_catalog_section_nav_items() -> list[dict[str, str]]:
    """On-page anchors for operator Discover index (catalog + live surface sections)."""
    return [
        {"id": "rmc-admin-sec-catalog", "label": str(_("Model catalog"))},
        {"id": "rmc-admin-sec-tags", "label": str(_("Platform tags"))},
        {"id": "rmc-admin-sec-changelist", "label": str(_("Changelist"))},
        {"id": "rmc-admin-sec-changeform", "label": str(_("Change form"))},
    ]
