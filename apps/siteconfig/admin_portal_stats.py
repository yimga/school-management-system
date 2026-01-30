"""
Resolve admin portal stats from section counts and config.
Used by admin index (config) and backend dashboard (accounts) so logic lives in one place.
"""


def resolve_admin_portal_stats(section_stats, config):
    """
    Filter and limit section_stats using admin_portal_stats_config.
    Returns dict: section_name -> { label: value, ... }.
    """
    if not isinstance(config, dict):
        config = {}

    def _to_int(value, fallback):
        try:
            return int(value)
        except (TypeError, ValueError):
            return fallback

    sections = config.get("sections") or list(section_stats.keys())
    max_sections = _to_int(config.get("max_sections"), 3)
    max_items = _to_int(config.get("max_items"), 3)
    items = config.get("items") if isinstance(config.get("items"), dict) else {}

    selected = {}
    for section in sections:
        if max_sections and len(selected) >= max_sections:
            break
        stats = section_stats.get(section)
        if not isinstance(stats, dict):
            continue
        preferred_items = items.get(section)
        if isinstance(preferred_items, list) and preferred_items:
            filtered = {label: stats[label] for label in preferred_items if label in stats}
        else:
            filtered = dict(stats)
            if max_items and max_items > 0:
                filtered = dict(list(filtered.items())[:max_items])
        if filtered:
            selected[section] = filtered

    if selected:
        return selected

    if not section_stats:
        return {}

    fallback = {}
    for section, stats in section_stats.items():
        if max_sections and len(fallback) >= max_sections:
            break
        if not isinstance(stats, dict):
            continue
        filtered = dict(stats)
        if max_items and max_items > 0:
            filtered = dict(list(filtered.items())[:max_items])
        fallback[section] = filtered
    return fallback
