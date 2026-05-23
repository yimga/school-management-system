"""
Platform /admin/ model catalog — section grouping + super bridge lookup for operator UX.
"""

from __future__ import annotations

from typing import Any

from django.urls import reverse


def _admin_url_to_bridge_key() -> dict[str, str]:
    try:
        from apps.schools.super_admin_bridge_registry import PLATFORM_ADMIN_BRIDGES
    except ImportError:
        return {}
    out: dict[str, str] = {}
    for bridge_key, cfg in PLATFORM_ADMIN_BRIDGES.items():
        admin_url_name = cfg.get("admin_url")
        if not isinstance(admin_url_name, str) or not admin_url_name:
            continue
        out[admin_url_name] = bridge_key
        try:
            path = reverse(admin_url_name)
            out[path] = bridge_key
            if not path.endswith("/"):
                out[f"{path}/"] = bridge_key
        except Exception:
            continue
    return out


def build_platform_admin_catalog(
    app_list: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Flatten Unfold app_list into searchable catalog entries grouped by platform IA section.
    """
    bridge_by_admin_url = _admin_url_to_bridge_key()
    entries: list[dict[str, Any]] = []
    sections: dict[str, list[dict[str, Any]]] = {}

    for app in app_list or []:
        app_label = app.get("app_label") or ""
        app_name = app.get("name") or app_label
        section = app.get("section") or "Advanced System Objects"
        sections.setdefault(section, [])
        app_entry = {
            "app_label": app_label,
            "app_name": app_name,
            "app_url": app.get("app_url") or "",
            "section": section,
            "models": [],
        }
        for model in app.get("models") or []:
            if model.get("hidden"):
                continue
            admin_url = model.get("admin_url") or ""
            if not admin_url:
                continue
            bridge_key = bridge_by_admin_url.get(admin_url)
            super_url = ""
            if bridge_key:
                try:
                    super_url = reverse(
                        "super:admin_bridge", kwargs={"bridge_key": bridge_key}
                    )
                except Exception:
                    super_url = ""
            row = {
                "name": model.get("name") or "",
                "object_name": model.get("object_name") or "",
                "admin_url": admin_url,
                "add_url": model.get("add_url") or "",
                "app_label": app_label,
                "app_name": app_name,
                "section": section,
                "bridge_key": bridge_key,
                "super_url": super_url,
                "search_blob": " ".join(
                    filter(
                        None,
                        [
                            section.lower(),
                            app_name.lower(),
                            app_label.lower(),
                            (model.get("name") or "").lower(),
                            (model.get("object_name") or "").lower(),
                        ],
                    )
                ),
            }
            entries.append(row)
            app_entry["models"].append(row)
        if app_entry["models"]:
            sections[section].append(app_entry)

    section_order = [
        "Platform Configuration",
        "Catalog Records",
        "Content & Templates",
        "Integrations & Providers",
        "Marketplace Records",
        "Migration Records",
        "Maintenance & Repair",
        "Access & Permissions",
        "Advanced System Objects",
    ]
    ordered_sections: list[dict[str, Any]] = []
    seen = set()
    def _preview_models_for_apps(apps: list[dict[str, Any]], limit: int = 6) -> list[dict[str, Any]]:
        preview: list[dict[str, Any]] = []
        for app in apps:
            for model in app.get("models") or []:
                preview.append(model)
                if len(preview) >= limit:
                    return preview
        return preview

    for title in section_order:
        if title in sections:
            apps = sections[title]
            ordered_sections.append(
                {
                    "title": title,
                    "apps": apps,
                    "model_count": sum(len(a["models"]) for a in apps),
                    "preview_models": _preview_models_for_apps(apps),
                }
            )
            seen.add(title)
    for title, apps in sorted(sections.items()):
        if title not in seen:
            ordered_sections.append(
                {
                    "title": title,
                    "apps": apps,
                    "model_count": sum(len(a["models"]) for a in apps),
                    "preview_models": _preview_models_for_apps(apps),
                }
            )

    return {
        "entries": entries,
        "sections": ordered_sections,
        "model_count": len(entries),
        "app_count": len(app_list or []),
        "section_count": len(ordered_sections),
    }


def _super_url_for_admin_url(admin_url: str, bridge_by_admin_url: dict[str, str]) -> str:
    bridge_key = bridge_by_admin_url.get(admin_url)
    if not bridge_key:
        return ""
    try:
        return reverse("super:admin_bridge", kwargs={"bridge_key": bridge_key})
    except Exception:
        return ""


def _super_first_url_for_bridge(bridge_key: str) -> str:
    try:
        from apps.schools.super_admin_paired_surfaces import super_first_spec_for_bridge_key
    except ImportError:
        return ""
    spec = super_first_spec_for_bridge_key(bridge_key)
    super_url_name = (spec or {}).get("super_url_name", "").strip()
    if not super_url_name:
        return ""
    try:
        return reverse(super_url_name)
    except Exception:
        return ""


def enrich_app_index_models(app_info: dict[str, Any]) -> list[dict[str, Any]]:
    """Enrich Unfold app_index model rows with super-first URLs."""
    bridge_by_admin_url = _admin_url_to_bridge_key()
    enriched: list[dict[str, Any]] = []
    for model in app_info.get("models") or []:
        if model.get("hidden"):
            continue
        admin_url = model.get("admin_url") or ""
        if not admin_url:
            continue
        bridge_key = bridge_by_admin_url.get(admin_url)
        super_url = ""
        if bridge_key:
            super_url = _super_first_url_for_bridge(bridge_key) or _super_url_for_admin_url(
                admin_url, bridge_by_admin_url
            )
        row = dict(model)
        row["bridge_key"] = bridge_key
        row["super_url"] = super_url
        enriched.append(row)
    return enriched
