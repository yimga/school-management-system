from __future__ import annotations

from urllib.parse import parse_qs, urlsplit


BROAD_DESTINATIONS = {
    "/authentication/backend/",
    "/school/configuration/",
    "/school/settings/",
    "/siteconfig/console/",
}


def direct_remedy_violations(actions: list[dict]) -> list[dict[str, str]]:
    """Return actionable findings whose CTA still lands on an undirected hub."""
    violations = []
    for action in actions:
        url = str(action.get("cta_url") or action.get("link") or "").strip()
        if not url or url == "#":
            violations.append({"key": str(action.get("key") or "unknown"), "reason": "missing destination"})
            continue
        parsed = urlsplit(url)
        if parsed.path in BROAD_DESTINATIONS and not (parse_qs(parsed.query) or parsed.fragment):
            violations.append({"key": str(action.get("key") or "unknown"), "reason": "broad hub destination"})
    return violations


def click_reduction(before_clicks: int, after_clicks: int) -> int:
    if before_clicks <= 0:
        return 0
    return round(((before_clicks - after_clicks) / before_clicks) * 100)
