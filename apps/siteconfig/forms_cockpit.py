"""ModelForm for editing ``SiteSettings.cockpit_payload`` — v3.56.

The operator UI exposes the 3 cockpit blocks (footer / community_band /
newsletter_band) as a single flat form. ``__init__`` parses the existing
nested ``cockpit_payload`` dict back into flat form fields for editing,
and ``clean()`` re-builds the nested dict matching the EXACT schema that
``apps.siteconfig.cockpit_context`` reads.

Reads on ``request.SITE.cockpit_payload`` therefore receive the same
shape regardless of whether the operator just published the form or the
field is empty (defaults flow from cockpit_context.py in that case).

No value is hardcoded inside the form: every default flows from the
cockpit_context module's tenant defaults so this form stays trivially
re-syncable when the schema evolves.
"""

from __future__ import annotations

from typing import Any

from django import forms
from django.utils.translation import gettext_lazy as _


# ---------------------------------------------------------------------------
# Textarea parsers — each block-level list field is edited as one
# row-per-line in a textarea. Parsers keep clean() small and testable.
# ---------------------------------------------------------------------------


def _split_lines(value: str) -> list[str]:
    """Split a textarea value into non-empty stripped lines."""
    if not value:
        return []
    out: list[str] = []
    for raw in str(value).splitlines():
        line = raw.strip()
        if line:
            out.append(line)
    return out


def _parse_trust_pillars(value: str) -> list[dict[str, str]]:
    """One per line: ``label | tone`` — tone defaults to ``neutral``."""
    out: list[dict[str, str]] = []
    for line in _split_lines(value):
        parts = [p.strip() for p in line.split("|", 1)]
        label = parts[0]
        tone = parts[1] if len(parts) > 1 and parts[1] else "neutral"
        if tone not in {"secure", "cert", "neutral"}:
            tone = "neutral"
        out.append({"label": label, "tone": tone})
    return out


def _parse_app_badges(value: str) -> list[dict[str, str]]:
    """One per line: ``label | url | glyph`` (glyph optional)."""
    out: list[dict[str, str]] = []
    for line in _split_lines(value):
        parts = [p.strip() for p in line.split("|", 2)]
        label = parts[0]
        url = parts[1] if len(parts) > 1 else ""
        glyph = parts[2] if len(parts) > 2 else ""
        out.append({"label": label, "url": url, "glyph": glyph})
    return out


def _parse_social(value: str) -> list[dict[str, str]]:
    """One per line: ``platform | url | glyph | label`` (last 2 optional)."""
    out: list[dict[str, str]] = []
    for line in _split_lines(value):
        parts = [p.strip() for p in line.split("|", 3)]
        platform = parts[0]
        url = parts[1] if len(parts) > 1 else ""
        glyph = parts[2] if len(parts) > 2 else ""
        label = parts[3] if len(parts) > 3 else platform
        out.append({"platform": platform, "url": url, "glyph": glyph, "label": label})
    return out


def _parse_contacts(value: str) -> list[dict[str, str]]:
    """One per line: ``kind | value | href | glyph`` (last 2 optional)."""
    out: list[dict[str, str]] = []
    for line in _split_lines(value):
        parts = [p.strip() for p in line.split("|", 3)]
        kind = parts[0]
        contact_value = parts[1] if len(parts) > 1 else ""
        href = parts[2] if len(parts) > 2 else ""
        glyph = parts[3] if len(parts) > 3 else ""
        out.append(
            {"kind": kind, "value": contact_value, "href": href, "glyph": glyph}
        )
    return out


def _parse_legal_links(value: str) -> list[dict[str, str]]:
    """One per line: ``label | url``."""
    out: list[dict[str, str]] = []
    for line in _split_lines(value):
        parts = [p.strip() for p in line.split("|", 1)]
        label = parts[0]
        url = parts[1] if len(parts) > 1 else "#"
        out.append({"label": label, "url": url})
    return out


def _parse_quotes(value: str) -> list[str]:
    """One quote per line."""
    return _split_lines(value)


def _parse_lesson_resources(value: str) -> list[dict[str, str]]:
    """One per line: ``label | url`` — malformed (label-only) rows skipped.

    Pairs with ``cockpit.lesson_of_day.resources`` whose schema is
    ``list[{label, url, icon}]``. Icon is left blank here (icon picking
    is out of scope for this wave; operators can add icons via a deeper
    editor later — `_deep_merge` preserves missing-key defaults).
    """
    out: list[dict[str, str]] = []
    for line in _split_lines(value):
        parts = [p.strip() for p in line.split("|", 1)]
        if len(parts) < 2 or not parts[0] or not parts[1]:
            # Label-only or URL-only rows are skipped — both halves are
            # load-bearing for a resource link; a dead chip helps nobody.
            continue
        out.append({"label": parts[0], "url": parts[1], "icon": ""})
    return out


def _parse_suggestion_lines(value: str) -> list[dict[str, str]]:
    """One suggestion per line — bare label or ``label | url``.

    Pairs with ``cockpit.ai_study_buddy.suggestions`` whose schema is
    ``list[{icon, label, url}]``. URL defaults to empty when the line
    has no pipe — the rendering side treats empty-URL chips as text-only
    hints (rather than tappable links).
    """
    out: list[dict[str, str]] = []
    for line in _split_lines(value):
        parts = [p.strip() for p in line.split("|", 1)]
        label = parts[0]
        url = parts[1] if len(parts) > 1 else ""
        if not label:
            continue
        out.append({"icon": "", "label": label, "url": url})
    return out


def _parse_upcoming_events(value: str) -> list[dict[str, Any]]:
    """One event per line: ``YYYY-MM-DD | title`` or ``MM-DD | title``.

    Pairs with ``cockpit.upcoming_events.events`` whose schema is
    ``list[{url, day, month, pill_label, pill_tone, title, meta, is_today}]``.
    Date is split into the ``day`` (zero-stripped) and ``month``
    (3-letter abbreviation) keys the rendering side expects; year is
    discarded for display but accepted in input for clarity. Malformed
    date rows are skipped (not crash). ``url``/``meta``/``pill_*``/
    ``is_today`` are left blank — `_deep_merge` preserves the section
    defaults for those keys.
    """
    month_abbr = (
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    )
    out: list[dict[str, Any]] = []
    for line in _split_lines(value):
        parts = [p.strip() for p in line.split("|", 1)]
        if len(parts) < 2 or not parts[1]:
            # Date-only rows are skipped — title is the only load-bearing
            # field for a calendar row.
            continue
        raw_date, title = parts[0], parts[1]
        # Accept YYYY-MM-DD, MM-DD, or YYYY/MM/DD — split on - or /
        bits = [b.strip() for b in raw_date.replace("/", "-").split("-")]
        try:
            if len(bits) == 3:
                month_num = int(bits[1])
                day_num = int(bits[2])
            elif len(bits) == 2:
                month_num = int(bits[0])
                day_num = int(bits[1])
            else:
                continue
        except (ValueError, TypeError):
            # Non-numeric month/day — skip silently rather than crash.
            continue
        if not (1 <= month_num <= 12) or not (1 <= day_num <= 31):
            continue
        out.append(
            {
                "url": "",
                "day": str(day_num),
                "month": month_abbr[month_num - 1],
                "pill_label": "",
                "pill_tone": "",
                "title": title,
                "meta": "",
                "is_today": False,
            }
        )
    return out


# ---------------------------------------------------------------------------
# Serializers for the v3.57.2 rich-editor sections.
# ---------------------------------------------------------------------------


def _serialize_lesson_resources(items: list[dict[str, Any]] | None) -> str:
    if not items:
        return ""
    rows: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label", "")).strip()
        url = str(item.get("url", "")).strip()
        if not label or not url:
            continue
        rows.append(f"{label} | {url}")
    return "\n".join(rows)


def _serialize_suggestion_lines(items: list[dict[str, Any]] | None) -> str:
    if not items:
        return ""
    rows: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label", "")).strip()
        url = str(item.get("url", "")).strip()
        if not label:
            continue
        rows.append(f"{label} | {url}".rstrip(" |") if url else label)
    return "\n".join(rows)


def _parse_metric_rows(value: str) -> list[dict[str, str]]:
    """One per line: ``label | value | hint`` (hint optional).

    Pairs with ``cockpit.today_snapshot.cards`` whose richer schema
    includes ``icon``/``head``/``value``/``label``/``spark_*``/``delta_*``.
    The flat editor only exposes the 3 most-common operator-edited keys
    (label as ``head``, value as ``value``, hint as ``label``); deeper
    keys (sparkline points, deltas) round-trip untouched via
    ``_deep_merge`` so operators don't lose previously-configured chrome
    by editing the textarea.
    """
    out: list[dict[str, str]] = []
    for line in _split_lines(value):
        parts = [p.strip() for p in line.split("|", 2)]
        head = parts[0]
        if not head:
            continue
        card_value = parts[1] if len(parts) > 1 else ""
        hint = parts[2] if len(parts) > 2 else ""
        out.append({"head": head, "value": card_value, "label": hint})
    return out


def _parse_quick_actions(value: str) -> list[dict[str, str]]:
    """One per line: ``icon | label | url | description`` (description optional).

    Pairs with ``cockpit.quick_actions.tiles`` whose schema is
    ``list[{url, icon, title, sub, badge}]``. The flat editor populates
    icon/title (=label)/url/sub (=description); ``badge`` is left empty
    so the rendering side falls through to defaults. Rows missing the
    label are skipped (a tile without a label is unactionable).
    """
    out: list[dict[str, str]] = []
    for line in _split_lines(value):
        parts = [p.strip() for p in line.split("|", 3)]
        if len(parts) < 2:
            continue
        icon = parts[0]
        title = parts[1]
        if not title:
            continue
        url = parts[2] if len(parts) > 2 else ""
        sub = parts[3] if len(parts) > 3 else ""
        out.append({"url": url, "icon": icon, "title": title, "sub": sub, "badge": ""})
    return out


def _parse_activity_events(value: str) -> list[dict[str, str]]:
    """One per line: ``YYYY-MM-DD HH:MM | actor | action | target``.

    Lenient: a missing trailing column is filled with empty string. The
    timestamp itself is opaque to the parser — operators may publish
    ``"now"`` / ``"2m ago"`` / ``"2026-05-21 14:38"`` etc. Pairs with
    ``cockpit.activity_timeline.items`` whose schema is
    ``list[{icon, tone, text, text_html, meta_left, meta_right}]``.

    Flat editor maps:
        timestamp -> meta_left
        action    -> text
        actor + target are folded into ``meta_right`` so the orchestrator
        partials' single-row layout still renders meaningfully.

    Rows whose ``action`` column is missing/empty are skipped — a row
    with no action is just noise on the timeline.
    """
    out: list[dict[str, str]] = []
    for line in _split_lines(value):
        parts = [p.strip() for p in line.split("|", 3)]
        timestamp = parts[0] if len(parts) > 0 else ""
        actor = parts[1] if len(parts) > 1 else ""
        action = parts[2] if len(parts) > 2 else ""
        target = parts[3] if len(parts) > 3 else ""
        if not action:
            continue
        # Compose meta_right honestly — only join non-empty halves.
        actor_target_bits = [b for b in (actor, target) if b]
        meta_right = " · ".join(actor_target_bits)
        out.append(
            {
                "icon": "",
                "tone": "",
                "text": action,
                "text_html": "",
                "meta_left": timestamp,
                "meta_right": meta_right,
            }
        )
    return out


def _parse_achievement_badges(value: str) -> list[dict[str, str]]:
    """One per line: ``icon | label | earned_on`` (earned_on optional).

    Pairs with ``cockpit.achievements.list`` whose minimum schema is
    ``list[{icon, label}]``. The flat editor adds an ``earned_on`` key
    for operator clarity; rendering partials that don't read it ignore
    the extra key. Rows without a label are skipped.
    """
    out: list[dict[str, str]] = []
    for line in _split_lines(value):
        parts = [p.strip() for p in line.split("|", 2)]
        icon = parts[0]
        label = parts[1] if len(parts) > 1 else ""
        earned_on = parts[2] if len(parts) > 2 else ""
        if not label:
            continue
        out.append({"icon": icon, "label": label, "earned_on": earned_on})
    return out


def _parse_regional_rows(value: str) -> list[dict[str, str]]:
    """One per line: ``region | count | trend`` (trend optional).

    Pairs with ``cockpit.live_world_map.regional_breakdown`` whose
    schema is ``list[{label, count, dot_color_token}]``. The flat editor
    maps ``region``→``label``, ``count``→``count``, ``trend``→a free
    ``trend`` key (rendering partials may ignore it; persisting it is
    cheap and keeps operator intent visible). ``dot_color_token`` is
    NOT exposed here — design tokens stay code-owned; default falls
    through. Rows without a region label are skipped.
    """
    out: list[dict[str, str]] = []
    for line in _split_lines(value):
        parts = [p.strip() for p in line.split("|", 2)]
        label = parts[0]
        if not label:
            continue
        count = parts[1] if len(parts) > 1 else ""
        trend = parts[2] if len(parts) > 2 else ""
        out.append({"label": label, "count": count, "trend": trend})
    return out


def _parse_audit_events(value: str) -> list[dict[str, str]]:
    """One per line: ``severity | actor | action | timestamp``.

    Pairs with ``cockpit.audit_feed.events`` whose schema is
    ``list[{time, actor, event, scope, severity, severity_label}]``.
    Flat-editor severity is constrained to ``{ok, info, warn, danger}``;
    anything else falls back to ``info`` so a typo doesn't crash the
    rendering CSS-class lookup. ``severity_label`` is derived from
    severity (uppercase humanised). ``scope`` is left blank — operators
    who need it must edit JSON directly. Rows without ``action`` are
    skipped.
    """
    severity_allow = {"ok", "info", "warn", "danger"}
    severity_label_map = {
        "ok": "OK",
        "info": "INFO",
        "warn": "WATCH",
        "danger": "RISK",
    }
    out: list[dict[str, str]] = []
    for line in _split_lines(value):
        parts = [p.strip() for p in line.split("|", 3)]
        if len(parts) < 1:
            continue
        raw_severity = (parts[0] or "info").lower()
        severity = raw_severity if raw_severity in severity_allow else "info"
        actor = parts[1] if len(parts) > 1 else ""
        action = parts[2] if len(parts) > 2 else ""
        timestamp = parts[3] if len(parts) > 3 else ""
        if not action:
            continue
        out.append(
            {
                "time": timestamp,
                "actor": actor,
                "event": action,
                "scope": "",
                "severity": severity,
                "severity_label": severity_label_map[severity],
            }
        )
    return out


def _serialize_upcoming_events(items: list[dict[str, Any]] | None) -> str:
    if not items:
        return ""
    # Map 3-letter abbreviation back to month number for round-trip.
    month_to_num: dict[str, int] = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }
    rows: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        if not title:
            continue
        day_raw = str(item.get("day", "")).strip()
        month_raw = str(item.get("month", "")).strip()
        month_num = month_to_num.get(month_raw[:3].lower(), 0)
        try:
            day_num = int(day_raw)
        except (ValueError, TypeError):
            day_num = 0
        if month_num and day_num:
            rows.append(f"{month_num:02d}-{day_num:02d} | {title}")
        else:
            # Fall back to title-only line so operator sees their event
            # rather than silently dropping it on round-trip.
            rows.append(f"  | {title}")
    return "\n".join(rows)


def _serialize_metric_rows(items: list[dict[str, Any]] | None) -> str:
    if not items:
        return ""
    rows: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        head = str(item.get("head", "")).strip()
        if not head:
            continue
        value = str(item.get("value", "")).strip()
        hint = str(item.get("label", "")).strip()
        rows.append(f"{head} | {value} | {hint}".rstrip(" |"))
    return "\n".join(rows)


def _serialize_quick_actions(items: list[dict[str, Any]] | None) -> str:
    if not items:
        return ""
    rows: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        if not title:
            continue
        icon = str(item.get("icon", "")).strip()
        url = str(item.get("url", "")).strip()
        sub = str(item.get("sub", "")).strip()
        rows.append(f"{icon} | {title} | {url} | {sub}".rstrip(" |"))
    return "\n".join(rows)


def _serialize_activity_events(items: list[dict[str, Any]] | None) -> str:
    if not items:
        return ""
    rows: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        action = str(item.get("text", "")).strip()
        if not action:
            continue
        timestamp = str(item.get("meta_left", "")).strip()
        meta_right = str(item.get("meta_right", "")).strip()
        # ``meta_right`` is "actor · target" on write; split on the first
        # " · " separator so the textarea round-trips cleanly. If the
        # operator-edited payload uses a different separator, the whole
        # blob lands in the actor column — that's still legible.
        if " · " in meta_right:
            actor, _, target = meta_right.partition(" · ")
        else:
            actor, target = meta_right, ""
        rows.append(f"{timestamp} | {actor} | {action} | {target}".rstrip(" |"))
    return "\n".join(rows)


def _serialize_achievement_badges(items: list[dict[str, Any]] | None) -> str:
    if not items:
        return ""
    rows: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label", "")).strip()
        if not label:
            continue
        icon = str(item.get("icon", "")).strip()
        earned_on = str(item.get("earned_on", "")).strip()
        rows.append(f"{icon} | {label} | {earned_on}".rstrip(" |"))
    return "\n".join(rows)


def _serialize_regional_rows(items: list[dict[str, Any]] | None) -> str:
    if not items:
        return ""
    rows: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label", "")).strip()
        if not label:
            continue
        count = str(item.get("count", "")).strip()
        trend = str(item.get("trend", "")).strip()
        rows.append(f"{label} | {count} | {trend}".rstrip(" |"))
    return "\n".join(rows)


def _serialize_audit_events(items: list[dict[str, Any]] | None) -> str:
    if not items:
        return ""
    rows: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        action = str(item.get("event", "")).strip()
        if not action:
            continue
        severity = str(item.get("severity", "")).strip() or "info"
        actor = str(item.get("actor", "")).strip()
        timestamp = str(item.get("time", "")).strip()
        rows.append(f"{severity} | {actor} | {action} | {timestamp}".rstrip(" |"))
    return "\n".join(rows)


# ---------------------------------------------------------------------------
# v3.57.13 parsers + serializers — 5 NEW sections (forecast_lane / slo_clocks /
# trust_nutrition / parent_teacher_thread / financial_timeline). Same forgiving
# pipe-separated textarea contract as the v3.57.12 editors above.
# ---------------------------------------------------------------------------


def _parse_forecast_cards(value: str) -> list[dict[str, str]]:
    """One per line: ``head | value | label | severity``.

    Pairs with ``cockpit.forecast_lane.cards`` whose richer schema
    includes ``slug``/``prediction``/SVG polyline coords. The flat editor
    only exposes the 4 most operator-edited keys (head/value/label/
    severity). Severity is constrained to ``{ok, info, warn, danger}``;
    anything else falls back to ``info`` so a typo doesn't crash the
    CSS-class lookup. Rows without a ``head`` are skipped (a card without
    a heading is unactionable).
    """
    severity_allow = {"ok", "info", "warn", "danger"}
    out: list[dict[str, str]] = []
    for line in _split_lines(value):
        parts = [p.strip() for p in line.split("|", 3)]
        head = parts[0]
        if not head:
            continue
        card_value = parts[1] if len(parts) > 1 else ""
        label = parts[2] if len(parts) > 2 else ""
        raw_severity = (parts[3] if len(parts) > 3 else "info").lower() or "info"
        severity = raw_severity if raw_severity in severity_allow else "info"
        out.append(
            {
                "head": head,
                "value": card_value,
                "label": label,
                "severity": severity,
            }
        )
    return out


def _serialize_forecast_cards(items: list[dict[str, Any]] | None) -> str:
    if not items:
        return ""
    rows: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        head = str(item.get("head", "")).strip()
        if not head:
            continue
        card_value = str(item.get("value", "")).strip()
        label = str(item.get("label", "")).strip()
        severity = str(item.get("severity", "")).strip() or "info"
        rows.append(f"{head} | {card_value} | {label} | {severity}".rstrip(" |"))
    return "\n".join(rows)


def _parse_slo_clocks(value: str) -> list[dict[str, str]]:
    """One per line: ``name | value | unit | severity``.

    Pairs with ``cockpit.slo_clocks.clocks`` whose richer schema includes
    ``sublabel`` and ``dot_status``. The flat editor maps:
        name      -> label
        value     -> value
        unit      -> value_suffix
        severity  -> dot_status (constrained to {ok, info, warn, danger})
    Rows without a name are skipped (an unnamed clock is meaningless).
    """
    severity_allow = {"ok", "info", "warn", "danger"}
    out: list[dict[str, str]] = []
    for line in _split_lines(value):
        parts = [p.strip() for p in line.split("|", 3)]
        name = parts[0]
        if not name:
            continue
        clock_value = parts[1] if len(parts) > 1 else ""
        unit = parts[2] if len(parts) > 2 else ""
        raw_severity = (parts[3] if len(parts) > 3 else "info").lower() or "info"
        severity = raw_severity if raw_severity in severity_allow else "info"
        out.append(
            {
                "label": name,
                "value": clock_value,
                "value_suffix": unit,
                "sublabel": "",
                "dot_status": severity,
            }
        )
    return out


def _serialize_slo_clocks(items: list[dict[str, Any]] | None) -> str:
    if not items:
        return ""
    rows: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("label", "")).strip()
        if not name:
            continue
        clock_value = str(item.get("value", "")).strip()
        unit = str(item.get("value_suffix", "")).strip()
        severity = str(item.get("dot_status", "")).strip() or "info"
        rows.append(f"{name} | {clock_value} | {unit} | {severity}".rstrip(" |"))
    return "\n".join(rows)


def _parse_trust_rows(value: str) -> list[dict[str, str]]:
    """One per line: ``metric | value | severity | note`` (note optional).

    Pairs with ``cockpit.trust_nutrition.rows`` whose schema is
    ``list[{label, value, status}]``. The flat editor adds a free
    ``note`` key (rendering partials that don't read it ignore the
    extra key cleanly). Severity is constrained to ``{ok, warn,
    danger, neutral}``; anything else falls back to ``neutral`` so a
    typo doesn't crash the CSS-class lookup. Rows without a metric
    label are skipped.
    """
    severity_allow = {"ok", "warn", "danger", "neutral"}
    out: list[dict[str, str]] = []
    for line in _split_lines(value):
        parts = [p.strip() for p in line.split("|", 3)]
        metric = parts[0]
        if not metric:
            continue
        row_value = parts[1] if len(parts) > 1 else ""
        raw_severity = (parts[2] if len(parts) > 2 else "neutral").lower() or "neutral"
        status = raw_severity if raw_severity in severity_allow else "neutral"
        note = parts[3] if len(parts) > 3 else ""
        out.append(
            {
                "label": metric,
                "value": row_value,
                "status": status,
                "note": note,
            }
        )
    return out


def _serialize_trust_rows(items: list[dict[str, Any]] | None) -> str:
    if not items:
        return ""
    rows: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        metric = str(item.get("label", "")).strip()
        if not metric:
            continue
        row_value = str(item.get("value", "")).strip()
        status = str(item.get("status", "")).strip() or "neutral"
        note = str(item.get("note", "")).strip()
        rows.append(f"{metric} | {row_value} | {status} | {note}".rstrip(" |"))
    return "\n".join(rows)


def _parse_thread_messages(value: str) -> list[dict[str, Any]]:
    """One per line: ``mine_or_theirs | author | timestamp | body``.

    Pairs with ``cockpit.parent_teacher_thread.messages`` whose schema
    is ``list[{author_initials, author_label, body, sent_iso, mine: bool}]``.
    The flat editor maps:
        mine_or_theirs   -> mine (bool: "mine" => True; else => False)
        author           -> author_label (initials derived from first 2 caps)
        timestamp        -> sent_iso
        body             -> body
    Rows without a body are skipped (an empty message helps nobody).
    """
    out: list[dict[str, Any]] = []
    for line in _split_lines(value):
        parts = [p.strip() for p in line.split("|", 3)]
        raw_mine = (parts[0] if len(parts) > 0 else "theirs").lower()
        mine = raw_mine == "mine"
        author = parts[1] if len(parts) > 1 else ""
        sent_iso = parts[2] if len(parts) > 2 else ""
        body = parts[3] if len(parts) > 3 else ""
        if not body:
            continue
        # Derive initials defensively from first-cap of each whitespace
        # token (max 2 chars). Partials may override or ignore.
        initials = "".join(
            token[0].upper() for token in author.split() if token
        )[:2]
        out.append(
            {
                "author_initials": initials,
                "author_label": author,
                "body": body,
                "sent_iso": sent_iso,
                "mine": mine,
            }
        )
    return out


def _serialize_thread_messages(items: list[dict[str, Any]] | None) -> str:
    if not items:
        return ""
    rows: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        body = str(item.get("body", "")).strip()
        if not body:
            continue
        mine = bool(item.get("mine"))
        author = str(item.get("author_label", "")).strip()
        sent_iso = str(item.get("sent_iso", "")).strip()
        mine_or_theirs = "mine" if mine else "theirs"
        rows.append(
            f"{mine_or_theirs} | {author} | {sent_iso} | {body}".rstrip(" |")
        )
    return "\n".join(rows)


def _parse_financial_events(value: str) -> list[dict[str, str]]:
    """One per line: ``date | type | description | amount``.

    Pairs with ``cockpit.financial_timeline.events`` whose schema is
    ``list[{iso, label, amount_display, tone, icon}]``. The flat editor
    maps:
        date         -> iso
        type         -> tone (constrained; falls back to "fee")
        description  -> label
        amount       -> amount_display (operator-formatted; never raw Decimal)
    Type is constrained to ``{fee, payment, discount, balance}``;
    anything else falls back to ``fee``. Rows without a description are
    skipped.
    """
    tone_allow = {"fee", "payment", "discount", "balance"}
    out: list[dict[str, str]] = []
    for line in _split_lines(value):
        parts = [p.strip() for p in line.split("|", 3)]
        iso = parts[0] if len(parts) > 0 else ""
        raw_tone = (parts[1] if len(parts) > 1 else "fee").lower() or "fee"
        tone = raw_tone if raw_tone in tone_allow else "fee"
        description = parts[2] if len(parts) > 2 else ""
        amount = parts[3] if len(parts) > 3 else ""
        if not description:
            continue
        out.append(
            {
                "iso": iso,
                "label": description,
                "amount_display": amount,
                "tone": tone,
                "icon": "",
            }
        )
    return out


def _serialize_financial_events(items: list[dict[str, Any]] | None) -> str:
    if not items:
        return ""
    rows: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        description = str(item.get("label", "")).strip()
        if not description:
            continue
        iso = str(item.get("iso", "")).strip()
        tone = str(item.get("tone", "")).strip() or "fee"
        amount = str(item.get("amount_display", "")).strip()
        rows.append(f"{iso} | {tone} | {description} | {amount}".rstrip(" |"))
    return "\n".join(rows)


# ---------------------------------------------------------------------------
# v3.57.14 parsers + serializers — 6 NEW sections (operator_presence /
# operator_notebook / tenant_heatmap / revenue_waterfall / realtime_presence /
# calendar_weather). Same forgiving pipe-separated textarea contract.
# ---------------------------------------------------------------------------


# Avatar gradient map: derive a default chip color from operator status so
# the rendering partial (which keys off ``gradient_slug``) still receives a
# valid token even though the operator only types a status word.
_OPR_STATUS_TO_GRADIENT: dict[str, str] = {
    "online": "emerald",
    "idle": "amber",
    "away": "indigo",
}


def _parse_operator_presence_avatars(value: str) -> list[dict[str, str]]:
    """One per line: ``initials | name | role | status``.

    Pairs with ``cockpit.operator_presence.avatars`` whose minimum schema
    is ``list[{initials, gradient_slug}]``. The flat editor persists the
    operator-supplied ``name``/``role`` keys verbatim (rendering partials
    that don't read them ignore the extra keys cleanly) and derives
    ``gradient_slug`` from ``status`` via ``_OPR_STATUS_TO_GRADIENT``.
    Status is constrained to ``{online, idle, away}``; anything else
    falls back to ``online`` so a typo doesn't break the chip color.
    Trailing columns are optional (lenient). Rows without ``initials``
    are skipped — a chip with no initials is meaningless.
    """
    status_allow = {"online", "idle", "away"}
    out: list[dict[str, str]] = []
    for line in _split_lines(value):
        parts = [p.strip() for p in line.split("|", 3)]
        initials = parts[0]
        if not initials:
            continue
        name = parts[1] if len(parts) > 1 else ""
        role = parts[2] if len(parts) > 2 else ""
        raw_status = (parts[3] if len(parts) > 3 else "online").lower() or "online"
        status = raw_status if raw_status in status_allow else "online"
        out.append(
            {
                "initials": initials,
                "name": name,
                "role": role,
                "status": status,
                "gradient_slug": _OPR_STATUS_TO_GRADIENT[status],
            }
        )
    return out


def _serialize_operator_presence_avatars(
    items: list[dict[str, Any]] | None,
) -> str:
    if not items:
        return ""
    # Reverse-map gradient_slug back to status when status is missing,
    # so payloads that pre-date the v3.57.14 editor round-trip cleanly.
    gradient_to_status = {v: k for k, v in _OPR_STATUS_TO_GRADIENT.items()}
    rows: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        initials = str(item.get("initials", "")).strip()
        if not initials:
            continue
        name = str(item.get("name", "")).strip()
        role = str(item.get("role", "")).strip()
        status = str(item.get("status", "")).strip().lower()
        if not status:
            gradient = str(item.get("gradient_slug", "")).strip().lower()
            status = gradient_to_status.get(gradient, "online")
        rows.append(f"{initials} | {name} | {role} | {status}".rstrip(" |"))
    return "\n".join(rows)


def _parse_heatmap_tiles(value: str) -> list[dict[str, str]]:
    """One per line: ``region | health_status | label`` (label optional).

    Pairs with ``cockpit.tenant_heatmap.tiles`` whose schema is
    ``list[{label, status}]``. The flat editor adds a free ``region``
    key (rendering partials that don't read it ignore it cleanly) and
    maps the optional 3rd column to ``label`` (data-label hover text).
    When the 3rd column is omitted, the region itself doubles as the
    hover label. health_status is constrained to
    ``{healthy, ok, warn, danger, idle}``; anything else falls back to
    ``healthy`` so the CSS-class lookup never crashes. Rows without a
    region are skipped.
    """
    status_allow = {"healthy", "ok", "warn", "danger", "idle"}
    out: list[dict[str, str]] = []
    for line in _split_lines(value):
        parts = [p.strip() for p in line.split("|", 2)]
        region = parts[0]
        if not region:
            continue
        raw_status = (parts[1] if len(parts) > 1 else "healthy").lower() or "healthy"
        status = raw_status if raw_status in status_allow else "healthy"
        label = parts[2] if len(parts) > 2 else region
        out.append({"region": region, "status": status, "label": label})
    return out


def _serialize_heatmap_tiles(items: list[dict[str, Any]] | None) -> str:
    if not items:
        return ""
    rows: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        # Prefer the explicit ``region`` key (round-trip from this editor);
        # fall back to ``label`` for payloads that pre-date the editor.
        region = str(item.get("region", "")).strip() or str(
            item.get("label", "")
        ).strip()
        if not region:
            continue
        status = str(item.get("status", "")).strip() or "healthy"
        label = str(item.get("label", "")).strip()
        # Suppress redundant 3rd column when it duplicates the region.
        if label and label != region:
            rows.append(f"{region} | {status} | {label}".rstrip(" |"))
        else:
            rows.append(f"{region} | {status}".rstrip(" |"))
    return "\n".join(rows)


def _parse_waterfall_bars(value: str) -> list[dict[str, str]]:
    """One per line: ``category | delta | severity``.

    Pairs with ``cockpit.revenue_waterfall.bars`` whose richer schema
    includes ``slug``/``x``/``y``/``width``/``height``/``gradient_id``
    (SVG geometry). The flat editor only exposes the 3 operator-edited
    keys: category (mapped to ``label``), delta (mapped to ``value`` —
    operator-formatted so the sign stays explicit, e.g. ``+$3.8k``),
    and severity. Severity is constrained to
    ``{start, gain, loss, end}``; anything else falls back to ``gain``
    so a typo doesn't crash the CSS-class lookup. SVG geometry stays
    code-owned and falls through from section defaults via
    ``_deep_merge``. Rows without a category are skipped.
    """
    severity_allow = {"start", "gain", "loss", "end"}
    out: list[dict[str, str]] = []
    for line in _split_lines(value):
        parts = [p.strip() for p in line.split("|", 2)]
        category = parts[0]
        if not category:
            continue
        delta = parts[1] if len(parts) > 1 else ""
        raw_severity = (parts[2] if len(parts) > 2 else "gain").lower() or "gain"
        severity = raw_severity if raw_severity in severity_allow else "gain"
        out.append(
            {
                "label": category,
                "value": delta,
                "severity": severity,
                "slug": severity,
            }
        )
    return out


def _serialize_waterfall_bars(items: list[dict[str, Any]] | None) -> str:
    if not items:
        return ""
    rows: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        category = str(item.get("label", "")).strip()
        if not category:
            continue
        delta = str(item.get("value", "")).strip()
        # Prefer the explicit ``severity`` key from this editor; fall back
        # to ``slug`` for payloads that pre-date the v3.57.14 wave.
        severity = (
            str(item.get("severity", "")).strip()
            or str(item.get("slug", "")).strip()
            or "gain"
        )
        rows.append(f"{category} | {delta} | {severity}".rstrip(" |"))
    return "\n".join(rows)


def _parse_realtime_presence_dots(value: str) -> list[dict[str, Any]]:
    """One per line: ``initials | status`` (status optional; lenient).

    Pairs with ``cockpit.realtime_presence.presence`` whose schema is
    ``list[{initials, online: bool, tone}]``. The flat editor maps:
        initials  -> initials
        status    -> online (bool: "online" => True; else => False)
                  -> tone   ("focus" when status=="online" so the
                             rendering partial highlights focused
                             classmates; empty otherwise — keeps the
                             schema's intent intact without forcing
                             operators to learn the ``tone`` vocab)
    Status is constrained to ``{online, idle, away}``; anything else
    falls back to ``away`` (safest — neither online nor highlighted).
    Rows without initials are skipped.
    """
    status_allow = {"online", "idle", "away"}
    out: list[dict[str, Any]] = []
    for line in _split_lines(value):
        parts = [p.strip() for p in line.split("|", 1)]
        initials = parts[0]
        if not initials:
            continue
        raw_status = (parts[1] if len(parts) > 1 else "online").lower() or "online"
        status = raw_status if raw_status in status_allow else "away"
        out.append(
            {
                "initials": initials,
                "online": status == "online",
                "tone": "focus" if status == "online" else "",
                "status": status,
            }
        )
    return out


def _serialize_realtime_presence_dots(
    items: list[dict[str, Any]] | None,
) -> str:
    if not items:
        return ""
    rows: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        initials = str(item.get("initials", "")).strip()
        if not initials:
            continue
        # Prefer explicit ``status`` from this editor; fall back to the
        # ``online`` bool from pre-v3.57.14 payloads (online=>"online",
        # else=>"idle" as the most-charitable default).
        status = str(item.get("status", "")).strip().lower()
        if not status:
            status = "online" if item.get("online") else "idle"
        rows.append(f"{initials} | {status}".rstrip(" |"))
    return "\n".join(rows)


def _parse_calendar_weather_days(value: str) -> list[dict[str, str]]:
    """One per line: ``date | weather_emoji | events``.

    Pairs with ``cockpit.calendar_weather.days`` whose schema is
    ``list[{day_short, day_num, is_today: bool, weather_icon,
    temp_display, event_label}]``. The flat editor maps:
        date           -> day_num (numeric day extracted from input)
                       -> day_short (3-letter weekday derived if input
                          parses as YYYY-MM-DD; else echoed raw input)
        weather_emoji  -> weather_icon
        events         -> event_label (free-form; one entry per line)
    Date input is forgiving: ``YYYY-MM-DD`` / ``MM-DD`` / a bare label
    (e.g. ``Mon 21``) all work. ``temp_display`` is not exposed here
    (operators who need it edit JSON directly); ``is_today`` is left
    False (the runtime context processor flips it). Rows without a date
    are skipped.
    """
    weekday_abbr = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
    out: list[dict[str, str]] = []
    for line in _split_lines(value):
        parts = [p.strip() for p in line.split("|", 2)]
        raw_date = parts[0]
        if not raw_date:
            continue
        weather_emoji = parts[1] if len(parts) > 1 else ""
        event_label = parts[2] if len(parts) > 2 else ""
        # Try to extract day_num + day_short from ISO-ish input;
        # otherwise echo the raw string into day_short and leave
        # day_num empty (the partial defaults visibly).
        day_short = raw_date
        day_num = ""
        bits = [b.strip() for b in raw_date.replace("/", "-").split("-")]
        try:
            if len(bits) == 3:
                year_num = int(bits[0])
                month_num = int(bits[1])
                day_int = int(bits[2])
                import datetime as _dt

                weekday = _dt.date(year_num, month_num, day_int).weekday()
                day_short = weekday_abbr[weekday]
                day_num = str(day_int)
            elif len(bits) == 2:
                day_int = int(bits[1])
                day_num = str(day_int)
                # Leave day_short as raw_date — caller-provided abbrev.
        except (ValueError, TypeError):
            # Non-numeric — echo raw input as the visible day label.
            pass
        out.append(
            {
                "day_short": day_short,
                "day_num": day_num,
                "weather_icon": weather_emoji,
                "temp_display": "",
                "event_label": event_label,
                "is_today": False,
            }
        )
    return out


def _serialize_calendar_weather_days(
    items: list[dict[str, Any]] | None,
) -> str:
    if not items:
        return ""
    rows: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        day_short = str(item.get("day_short", "")).strip()
        day_num = str(item.get("day_num", "")).strip()
        # Compose the date column from the parts the parser writes —
        # fall back to whichever half is present so operator input never
        # vanishes on round-trip.
        if day_short and day_num:
            date_label = f"{day_short} {day_num}"
        else:
            date_label = day_short or day_num
        if not date_label:
            continue
        weather_emoji = str(item.get("weather_icon", "")).strip()
        event_label = str(item.get("event_label", "")).strip()
        rows.append(
            f"{date_label} | {weather_emoji} | {event_label}".rstrip(" |")
        )
    return "\n".join(rows)


# ---------------------------------------------------------------------------
# Serializers — flatten nested dict back into textarea-friendly strings
# for ``__init__`` (round-trip).
# ---------------------------------------------------------------------------


def _serialize_trust_pillars(items: list[dict[str, Any]] | None) -> str:
    if not items:
        return ""
    rows: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label", "")).strip()
        tone = str(item.get("tone", "neutral")).strip() or "neutral"
        if not label:
            continue
        rows.append(f"{label} | {tone}")
    return "\n".join(rows)


def _serialize_app_badges(items: list[dict[str, Any]] | None) -> str:
    if not items:
        return ""
    rows: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label", "")).strip()
        url = str(item.get("url", "")).strip()
        glyph = str(item.get("glyph", "")).strip()
        if not label:
            continue
        rows.append(f"{label} | {url} | {glyph}".rstrip(" |"))
    return "\n".join(rows)


def _serialize_social(items: list[dict[str, Any]] | None) -> str:
    if not items:
        return ""
    rows: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        platform = str(item.get("platform", "")).strip()
        url = str(item.get("url", "")).strip()
        glyph = str(item.get("glyph", "")).strip()
        label = str(item.get("label", "")).strip()
        if not platform:
            continue
        rows.append(f"{platform} | {url} | {glyph} | {label}".rstrip(" |"))
    return "\n".join(rows)


def _serialize_contacts(items: list[dict[str, Any]] | None) -> str:
    if not items:
        return ""
    rows: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind", "")).strip()
        value = str(item.get("value", "")).strip()
        href = str(item.get("href", "")).strip()
        glyph = str(item.get("glyph", "")).strip()
        if not kind and not value:
            continue
        rows.append(f"{kind} | {value} | {href} | {glyph}".rstrip(" |"))
    return "\n".join(rows)


def _serialize_legal_links(items: list[dict[str, Any]] | None) -> str:
    if not items:
        return ""
    rows: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label", "")).strip()
        url = str(item.get("url", "")).strip()
        if not label:
            continue
        rows.append(f"{label} | {url}".rstrip(" |"))
    return "\n".join(rows)


def _serialize_quotes(items: list[Any] | None) -> str:
    if not items:
        return ""
    return "\n".join(str(quote).strip() for quote in items if str(quote).strip())


# ---------------------------------------------------------------------------
# The form. Three fieldsets: footer, community_band, newsletter_band.
# ---------------------------------------------------------------------------


_TEXTAREA_SMALL = forms.Textarea(attrs={"rows": 3, "class": "form-control"})
_TEXTAREA_MEDIUM = forms.Textarea(attrs={"rows": 5, "class": "form-control"})
_TEXTAREA_LARGE = forms.Textarea(attrs={"rows": 6, "class": "form-control"})
_TEXT = forms.TextInput(attrs={"class": "form-control"})
_NUMBER = forms.NumberInput(attrs={"class": "form-control"})
_URL = forms.URLInput(attrs={"class": "form-control"})
_CHECK = forms.CheckboxInput(attrs={"class": "form-check-input"})


class CockpitPayloadForm(forms.ModelForm):
    """Flat form whose ``clean()`` writes the nested ``cockpit_payload`` dict.

    The ``Meta.fields`` includes only ``cockpit_payload`` so that the
    underlying JSON column is the sole persisted field. The flat fields
    declared on the class are unbound from the model — they exist only
    to drive the editing UX and are re-read from / written to the JSON
    payload in ``__init__`` / ``clean()``.
    """

    # ---- Footer fieldset (mirrors cockpit.footer.*) -------------------
    footer_wordmark = forms.CharField(required=False, widget=_TEXT, label=_("Wordmark"))
    footer_motto = forms.CharField(required=False, widget=_TEXT, label=_("Motto"))
    footer_founded_year = forms.IntegerField(
        required=False, widget=_NUMBER, label=_("Founded year"), min_value=0
    )
    footer_descriptor = forms.CharField(
        required=False, widget=_TEXT, label=_("Descriptor")
    )
    footer_trust_pillars = forms.CharField(
        required=False,
        widget=_TEXTAREA_SMALL,
        label=_("Trust pillars"),
        help_text=_("One per line: label | tone   (tone: secure / cert / neutral)"),
    )
    footer_language_label = forms.CharField(
        required=False, widget=_TEXT, label=_("Language switcher label")
    )
    footer_app_badges = forms.CharField(
        required=False,
        widget=_TEXTAREA_MEDIUM,
        label=_("App badges"),
        help_text=_("One per line: label | url | glyph"),
    )
    footer_social = forms.CharField(
        required=False,
        widget=_TEXTAREA_MEDIUM,
        label=_("Social links"),
        help_text=_("One per line: platform | url | glyph | label"),
    )
    footer_contacts = forms.CharField(
        required=False,
        widget=_TEXTAREA_MEDIUM,
        label=_("Contacts"),
        help_text=_("One per line: kind | value | href | glyph"),
    )
    footer_stat_line = forms.CharField(
        required=False, widget=_TEXT, label=_("Stat line")
    )
    footer_legal_links = forms.CharField(
        required=False,
        widget=_TEXTAREA_MEDIUM,
        label=_("Legal links"),
        help_text=_("One per line: label | url"),
    )
    footer_copyright_holder = forms.CharField(
        required=False, widget=_TEXT, label=_("Copyright holder")
    )
    footer_powered_by_label = forms.CharField(
        required=False, widget=_TEXT, label=_("Powered-by label")
    )
    footer_powered_by_url = forms.CharField(
        required=False, widget=_TEXT, label=_("Powered-by URL")
    )

    # ---- Community band fieldset (mirrors cockpit.community_band.*) ---
    community_enabled = forms.BooleanField(
        required=False, widget=_CHECK, label=_("Enable community band")
    )

    achievement_enabled = forms.BooleanField(
        required=False, widget=_CHECK, label=_("Achievement block enabled")
    )
    achievement_title = forms.CharField(
        required=False, widget=_TEXT, label=_("Achievement title")
    )
    achievement_period_label = forms.CharField(
        required=False, widget=_TEXT, label=_("Achievement period label")
    )
    achievement_student_initials = forms.CharField(
        required=False, widget=_TEXT, label=_("Student initials")
    )
    achievement_student_name = forms.CharField(
        required=False, widget=_TEXT, label=_("Student name")
    )
    achievement_student_subline = forms.CharField(
        required=False, widget=_TEXT, label=_("Student subline")
    )
    achievement_teacher_quote = forms.CharField(
        required=False, widget=_TEXTAREA_SMALL, label=_("Teacher quote")
    )
    achievement_teacher_cite = forms.CharField(
        required=False, widget=_TEXT, label=_("Teacher citation")
    )

    testimonial_enabled = forms.BooleanField(
        required=False, widget=_CHECK, label=_("Testimonial block enabled")
    )
    testimonial_title = forms.CharField(
        required=False, widget=_TEXT, label=_("Testimonial title")
    )
    testimonial_quotes = forms.CharField(
        required=False,
        widget=_TEXTAREA_LARGE,
        label=_("Rotating quotes"),
        help_text=_("One per line."),
    )
    testimonial_interval_ms = forms.IntegerField(
        required=False, widget=_NUMBER, label=_("Rotation interval (ms)"), min_value=0
    )

    map_enabled = forms.BooleanField(
        required=False, widget=_CHECK, label=_("Map block enabled")
    )
    map_title = forms.CharField(required=False, widget=_TEXT, label=_("Map title"))
    map_period_label = forms.CharField(
        required=False, widget=_TEXT, label=_("Map period label")
    )
    map_address_line_1 = forms.CharField(
        required=False, widget=_TEXT, label=_("Address line 1")
    )
    map_address_line_2 = forms.CharField(
        required=False, widget=_TEXT, label=_("Address line 2")
    )
    map_maps_url = forms.CharField(required=False, widget=_TEXT, label=_("Maps URL"))
    map_cta_label = forms.CharField(
        required=False, widget=_TEXT, label=_("Map CTA label")
    )

    # ---- Newsletter band fieldset (mirrors cockpit.newsletter_band.*) -
    newsletter_enabled = forms.BooleanField(
        required=False, widget=_CHECK, label=_("Enable newsletter band")
    )
    newsletter_title = forms.CharField(required=False, widget=_TEXT, label=_("Title"))
    newsletter_subtitle = forms.CharField(
        required=False, widget=_TEXT, label=_("Subtitle")
    )
    newsletter_placeholder = forms.CharField(
        required=False, widget=_TEXT, label=_("Email placeholder")
    )
    newsletter_cta_label = forms.CharField(
        required=False, widget=_TEXT, label=_("CTA label")
    )
    newsletter_submit_url = forms.CharField(
        required=False, widget=_TEXT, label=_("Submit URL")
    )
    newsletter_privacy_url = forms.CharField(
        required=False, widget=_TEXT, label=_("Privacy URL")
    )
    newsletter_privacy_label = forms.CharField(
        required=False, widget=_TEXT, label=_("Privacy label")
    )

    # ---- v3.57 Tenant dashboard fieldset (7 sections) -----------------
    # Mirrors TENANT_DASHBOARD_DEFAULTS in cockpit_tenant_dashboard.py.
    # Master enable + a small set of leaf attributes per section. Deep
    # list/dict editing (e.g. cards/tiles/events) is intentionally
    # deferred to a follow-up wave — operators get the headline knobs
    # here and the JSON column carries any list-of-dicts data they
    # publish through other means.
    #
    # workspace_context_tenant
    dash_wsctx_enabled = forms.BooleanField(
        required=False, widget=_CHECK, label=_("Workspace context (child)")
    )
    dash_wsctx_label = forms.CharField(
        required=False, widget=_TEXT, label=_("Workspace context label")
    )
    dash_wsctx_live_chip = forms.CharField(
        required=False, widget=_TEXT, label=_("Live chip text")
    )
    dash_wsctx_child_initials = forms.CharField(
        required=False, widget=_TEXT, label=_("Child initials")
    )
    dash_wsctx_child_name = forms.CharField(
        required=False, widget=_TEXT, label=_("Child name")
    )
    dash_wsctx_child_subline = forms.CharField(
        required=False, widget=_TEXT, label=_("Child subline")
    )
    dash_wsctx_child_online = forms.BooleanField(
        required=False, widget=_CHECK, label=_("Child online")
    )
    dash_wsctx_siblings_label = forms.CharField(
        required=False, widget=_TEXT, label=_("Siblings label")
    )
    dash_wsctx_add_child_label = forms.CharField(
        required=False, widget=_TEXT, label=_("Add child label")
    )
    dash_wsctx_add_child_url = forms.CharField(
        required=False, widget=_TEXT, label=_("Add child URL")
    )
    # today_snapshot
    dash_today_enabled = forms.BooleanField(
        required=False, widget=_CHECK, label=_("Today snapshot")
    )
    dash_today_section_label = forms.CharField(
        required=False, widget=_TEXT, label=_("Today section label")
    )
    dash_today_live_dot = forms.BooleanField(
        required=False, widget=_CHECK, label=_("Today live dot")
    )
    dash_today_switch_label = forms.CharField(
        required=False, widget=_TEXT, label=_("Today switch link label")
    )
    dash_today_switch_url = forms.CharField(
        required=False, widget=_TEXT, label=_("Today switch link URL")
    )
    # quick_actions
    dash_qa_enabled = forms.BooleanField(
        required=False, widget=_CHECK, label=_("Quick actions")
    )
    dash_qa_section_label = forms.CharField(
        required=False, widget=_TEXT, label=_("Quick actions label")
    )
    # upcoming_events
    dash_events_enabled = forms.BooleanField(
        required=False, widget=_CHECK, label=_("Upcoming events")
    )
    dash_events_section_label = forms.CharField(
        required=False, widget=_TEXT, label=_("Upcoming events label")
    )
    dash_events_view_all_label = forms.CharField(
        required=False, widget=_TEXT, label=_("View all events label")
    )
    dash_events_view_all_url = forms.CharField(
        required=False, widget=_TEXT, label=_("View all events URL")
    )
    # activity_timeline
    dash_activity_enabled = forms.BooleanField(
        required=False, widget=_CHECK, label=_("Recent activity timeline")
    )
    dash_activity_title = forms.CharField(
        required=False, widget=_TEXT, label=_("Activity timeline title")
    )
    dash_activity_title_suffix = forms.CharField(
        required=False, widget=_TEXT, label=_("Activity title suffix")
    )
    dash_activity_view_all_label = forms.CharField(
        required=False, widget=_TEXT, label=_("Activity view all label")
    )
    dash_activity_view_all_url = forms.CharField(
        required=False, widget=_TEXT, label=_("Activity view all URL")
    )
    # achievements
    dash_ach_enabled = forms.BooleanField(
        required=False, widget=_CHECK, label=_("Achievements card")
    )
    dash_ach_title = forms.CharField(
        required=False, widget=_TEXT, label=_("Achievements title")
    )
    dash_ach_count_label = forms.CharField(
        required=False, widget=_TEXT, label=_("Achievements count label")
    )
    # teacher_spotlight
    dash_ts_enabled = forms.BooleanField(
        required=False, widget=_CHECK, label=_("Teacher spotlight")
    )
    dash_ts_title = forms.CharField(
        required=False, widget=_TEXT, label=_("Teacher spotlight title")
    )
    dash_ts_sub = forms.CharField(
        required=False, widget=_TEXT, label=_("Teacher spotlight subline")
    )
    dash_ts_avatar_initials = forms.CharField(
        required=False, widget=_TEXT, label=_("Teacher avatar initials")
    )
    dash_ts_teacher_name = forms.CharField(
        required=False, widget=_TEXT, label=_("Teacher name")
    )
    dash_ts_teacher_role = forms.CharField(
        required=False, widget=_TEXT, label=_("Teacher role")
    )
    dash_ts_quote = forms.CharField(
        required=False, widget=_TEXTAREA_SMALL, label=_("Teacher spotlight quote")
    )

    # ---- v3.57 Manager 200x fieldset (10 sections) --------------------
    # Mirrors manager_200x_defaults() in cockpit_manager_200x.py. As with
    # the tenant-dashboard fieldset, headline leaf attributes are
    # operator-editable here; list-of-dict bodies (messages, cards, tiles,
    # rows, etc.) are managed via separate code paths that write the JSON
    # column. Master enable + i18n-relevant leaves are exposed.
    #
    # ai_copilot_rail
    mgr_aic_enabled = forms.BooleanField(
        required=False, widget=_CHECK, label=_("AI Copilot rail")
    )
    mgr_aic_default_state = forms.CharField(
        required=False, widget=_TEXT, label=_("AI Copilot default state")
    )
    mgr_aic_title = forms.CharField(
        required=False, widget=_TEXT, label=_("AI Copilot title")
    )
    mgr_aic_title_em = forms.CharField(
        required=False, widget=_TEXT, label=_("AI Copilot title em")
    )
    mgr_aic_insight_text = forms.CharField(
        required=False, widget=_TEXTAREA_SMALL, label=_("AI Copilot insight text")
    )
    mgr_aic_insight_em = forms.CharField(
        required=False, widget=_TEXT, label=_("AI Copilot insight em")
    )
    mgr_aic_input_placeholder = forms.CharField(
        required=False, widget=_TEXT, label=_("AI Copilot input placeholder")
    )
    mgr_aic_cmdk_hint = forms.CharField(
        required=False, widget=_TEXT, label=_("AI Copilot ⌘K hint")
    )
    mgr_aic_send_label = forms.CharField(
        required=False, widget=_TEXT, label=_("AI Copilot send label")
    )
    # live_world_map
    mgr_map_enabled = forms.BooleanField(
        required=False, widget=_CHECK, label=_("Live world map")
    )
    mgr_map_eyebrow = forms.CharField(
        required=False, widget=_TEXT, label=_("World map eyebrow")
    )
    mgr_map_schools_live = forms.CharField(
        required=False, widget=_TEXT, label=_("Schools-live mega number")
    )
    mgr_map_schools_live_label = forms.CharField(
        required=False, widget=_TEXT, label=_("Schools live label")
    )
    mgr_map_subline = forms.CharField(
        required=False, widget=_TEXT, label=_("World map subline")
    )
    # forecast_lane
    mgr_forecast_enabled = forms.BooleanField(
        required=False, widget=_CHECK, label=_("Forecast lane")
    )
    mgr_forecast_label = forms.CharField(
        required=False, widget=_TEXT, label=_("Forecast section label")
    )
    # operator_notebook
    mgr_notebook_enabled = forms.BooleanField(
        required=False, widget=_CHECK, label=_("Operator notebook")
    )
    mgr_notebook_title = forms.CharField(
        required=False, widget=_TEXT, label=_("Notebook title")
    )
    mgr_notebook_placeholder = forms.CharField(
        required=False, widget=_TEXT, label=_("Notebook placeholder")
    )
    mgr_notebook_mic_enabled = forms.BooleanField(
        required=False, widget=_CHECK, label=_("Notebook mic enabled")
    )
    mgr_notebook_save_url = forms.CharField(
        required=False, widget=_TEXT, label=_("Notebook save URL")
    )
    mgr_notebook_save_label = forms.CharField(
        required=False, widget=_TEXT, label=_("Notebook save label")
    )
    mgr_notebook_hint_text = forms.CharField(
        required=False, widget=_TEXT, label=_("Notebook hint text")
    )
    mgr_notebook_hint_em = forms.CharField(
        required=False, widget=_TEXT, label=_("Notebook hint em")
    )
    # tenant_heatmap
    mgr_heatmap_enabled = forms.BooleanField(
        required=False, widget=_CHECK, label=_("Tenant heatmap")
    )
    mgr_heatmap_eyebrow = forms.CharField(
        required=False, widget=_TEXT, label=_("Heatmap eyebrow")
    )
    mgr_heatmap_title = forms.CharField(
        required=False, widget=_TEXT, label=_("Heatmap title")
    )
    mgr_heatmap_title_em = forms.CharField(
        required=False, widget=_TEXT, label=_("Heatmap title em")
    )
    mgr_heatmap_meta_text = forms.CharField(
        required=False, widget=_TEXT, label=_("Heatmap meta text")
    )
    mgr_heatmap_legend_hint = forms.CharField(
        required=False, widget=_TEXT, label=_("Heatmap legend hint")
    )
    # revenue_waterfall
    mgr_wf_enabled = forms.BooleanField(
        required=False, widget=_CHECK, label=_("Revenue waterfall")
    )
    mgr_wf_eyebrow = forms.CharField(
        required=False, widget=_TEXT, label=_("Waterfall eyebrow")
    )
    mgr_wf_title = forms.CharField(
        required=False, widget=_TEXT, label=_("Waterfall title")
    )
    mgr_wf_title_em = forms.CharField(
        required=False, widget=_TEXT, label=_("Waterfall title em")
    )
    mgr_wf_title_end = forms.CharField(
        required=False, widget=_TEXT, label=_("Waterfall title end")
    )
    mgr_wf_meta_text = forms.CharField(
        required=False, widget=_TEXT, label=_("Waterfall meta text")
    )
    # audit_feed
    mgr_audit_enabled = forms.BooleanField(
        required=False, widget=_CHECK, label=_("Audit feed")
    )
    mgr_audit_title = forms.CharField(
        required=False, widget=_TEXT, label=_("Audit feed title")
    )
    mgr_audit_title_em = forms.CharField(
        required=False, widget=_TEXT, label=_("Audit feed title em")
    )
    mgr_audit_filter_text = forms.CharField(
        required=False, widget=_TEXT, label=_("Audit feed filter text")
    )
    # trust_nutrition
    mgr_trust_enabled = forms.BooleanField(
        required=False, widget=_CHECK, label=_("Trust nutrition")
    )
    mgr_trust_title = forms.CharField(
        required=False, widget=_TEXT, label=_("Trust nutrition title")
    )
    mgr_trust_caption = forms.CharField(
        required=False, widget=_TEXT, label=_("Trust nutrition caption")
    )
    mgr_trust_footer = forms.CharField(
        required=False, widget=_TEXT, label=_("Trust nutrition footer")
    )
    # slo_clocks
    mgr_slo_enabled = forms.BooleanField(
        required=False, widget=_CHECK, label=_("SLO clocks")
    )
    # operator_presence
    mgr_presence_enabled = forms.BooleanField(
        required=False, widget=_CHECK, label=_("Operator presence")
    )
    mgr_presence_count = forms.IntegerField(
        required=False, widget=_NUMBER, label=_("Operators online count"), min_value=0
    )
    mgr_presence_label = forms.CharField(
        required=False, widget=_TEXT, label=_("Operators online label")
    )
    mgr_presence_status_pill = forms.CharField(
        required=False, widget=_TEXT, label=_("Status pill text")
    )
    mgr_presence_aria = forms.CharField(
        required=False, widget=_TEXT, label=_("Presence aria label")
    )

    # ---- v3.57.1 Front-office 200x enable toggles (10 sections) -------
    # Mirrors front_office_200x_defaults() in cockpit_front_office_200x.py.
    # Minimal-viable surface for the v3.57 adoption wave: master `enabled`
    # flag per section so operators can flip them on/off without editing
    # the deeper schemas (cohort matrices, deploy pipelines, etc.) until a
    # follow-up wave adds rich editors per section.
    fo_revenue_cohort_enabled = forms.BooleanField(
        required=False, widget=_CHECK, label=_("Revenue cohort retention chart")
    )
    fo_nps_ticker_enabled = forms.BooleanField(
        required=False, widget=_CHECK, label=_("NPS sentiment ticker")
    )
    fo_support_burndown_enabled = forms.BooleanField(
        required=False, widget=_CHECK, label=_("Support queue burndown")
    )
    fo_deploy_pipeline_enabled = forms.BooleanField(
        required=False, widget=_CHECK, label=_("Deploy pipeline status")
    )
    fo_churn_scorecard_enabled = forms.BooleanField(
        required=False, widget=_CHECK, label=_("Tenant churn-risk scorecard")
    )
    fo_ai_fixes_feed_enabled = forms.BooleanField(
        required=False, widget=_CHECK, label=_("AI-suggested fixes feed")
    )
    fo_capacity_planning_enabled = forms.BooleanField(
        required=False, widget=_CHECK, label=_("Automated capacity planning")
    )
    fo_regional_clocks_enabled = forms.BooleanField(
        required=False, widget=_CHECK, label=_("Regional time-zone clocks")
    )
    fo_onboarding_pipeline_enabled = forms.BooleanField(
        required=False, widget=_CHECK, label=_("Tenant onboarding pipeline")
    )
    fo_audit_wordcloud_enabled = forms.BooleanField(
        required=False, widget=_CHECK, label=_("Audit-event word cloud")
    )

    # ---- v3.57.1 Tenant v3 100x enable toggles (10 sections) ----------
    # Mirrors TENANT_V3_EXTENDED_DEFAULTS in cockpit_tenant_v3_extended.py.
    # Sibling-compare retains its own privacy-gate `opt_in` flag inside
    # the section payload — this top-level `enabled` toggles the section
    # entirely; opt-in remains opt-in even after enable.
    tv3_ai_study_buddy_enabled = forms.BooleanField(
        required=False, widget=_CHECK, label=_("AI study buddy chip")
    )
    tv3_parent_teacher_thread_enabled = forms.BooleanField(
        required=False, widget=_CHECK, label=_("Parent-teacher inline thread")
    )
    tv3_realtime_presence_enabled = forms.BooleanField(
        required=False, widget=_CHECK, label=_("Realtime presence (classmates online)")
    )
    tv3_gradebook_trend_enabled = forms.BooleanField(
        required=False, widget=_CHECK, label=_("Gradebook trend sparkline")
    )
    tv3_attendance_heatmap_enabled = forms.BooleanField(
        required=False, widget=_CHECK, label=_("Attendance heatmap")
    )
    tv3_financial_timeline_enabled = forms.BooleanField(
        required=False, widget=_CHECK, label=_("Financial timeline")
    )
    tv3_sibling_compare_enabled = forms.BooleanField(
        required=False,
        widget=_CHECK,
        label=_("Sibling compare (opt-in gated separately)"),
    )
    tv3_life_event_timeline_enabled = forms.BooleanField(
        required=False, widget=_CHECK, label=_("Life event timeline")
    )
    tv3_calendar_weather_enabled = forms.BooleanField(
        required=False, widget=_CHECK, label=_("Calendar + weather overlay")
    )
    tv3_lesson_of_day_enabled = forms.BooleanField(
        required=False, widget=_CHECK, label=_("Lesson of the day")
    )

    # ---- v3.57.2 Rich editors (4 high-value sections) -----------------
    # Promotes 4 sections from "enable toggle only" to full content editor.
    # Each section's flat fields write into the SAME nested key the
    # enable toggle targets (e.g. ``cockpit.lesson_of_day.*``), so the
    # enable + content fields stack cleanly via ``_deep_merge`` in
    # cockpit_context.py — operators can enable + populate in one save.
    #
    # 1) tenant_v3_extended.lesson_of_day
    lod_title = forms.CharField(
        required=False,
        widget=_TEXT,
        label=_("Lesson card title"),
        help_text=_("Heading shown above the lesson body (e.g. 'Today's lesson')."),
    )
    lod_subject = forms.CharField(
        required=False,
        widget=_TEXT,
        label=_("Lesson subject"),
        help_text=_("Subject label shown on the chip (e.g. 'Mathematics', 'Biology')."),
    )
    lod_summary = forms.CharField(
        required=False,
        max_length=240,
        widget=_TEXTAREA_SMALL,
        label=_("Lesson summary"),
        help_text=_(
            "Plain-text 1-2 sentence summary of today's lesson (max 240 chars). "
            "Operator-published; never auto-rendered from student data."
        ),
    )
    lod_resources = forms.CharField(
        required=False,
        widget=_TEXTAREA_MEDIUM,
        label=_("Lesson resources"),
        help_text=_(
            "One per line: label | url. Rows missing a URL are skipped. "
            "Renders as a list of resource chips beneath the lesson card."
        ),
    )

    # 2) tenant_v3_extended.ai_study_buddy
    asb_title = forms.CharField(
        required=False,
        widget=_TEXT,
        label=_("AI study buddy label"),
        help_text=_(
            "Short chip label (e.g. 'Study buddy'). Maps to "
            "cockpit.ai_study_buddy.label."
        ),
    )
    asb_intro = forms.CharField(
        required=False,
        max_length=120,
        widget=_TEXT,
        label=_("AI study buddy intro"),
        help_text=_(
            "Greeting line shown when the chip opens (max 120 chars). "
            "Maps to cockpit.ai_study_buddy.greeting."
        ),
    )
    asb_suggestions = forms.CharField(
        required=False,
        widget=_TEXTAREA_MEDIUM,
        label=_("AI study buddy suggestions"),
        help_text=_(
            "One per line — bare label, or label | url for tappable. "
            "Empty lines skipped. Renders as starter-prompt chips."
        ),
    )

    # 3) tenant_dashboard.teacher_spotlight_card
    tsc_name = forms.CharField(
        required=False,
        widget=_TEXT,
        label=_("Teacher spotlight: name"),
        help_text=_("Full teacher name displayed in the spotlight card."),
    )
    tsc_subject = forms.CharField(
        required=False,
        widget=_TEXT,
        label=_("Teacher spotlight: subject / role"),
        help_text=_(
            "Role or subject line under the teacher's name "
            "(e.g. 'Grade 5 mathematics')."
        ),
    )
    tsc_quote = forms.CharField(
        required=False,
        max_length=200,
        widget=_TEXTAREA_SMALL,
        label=_("Teacher spotlight: quote"),
        help_text=_(
            "Pull-quote shown in italic serif (max 200 chars). "
            "Operator-published copy only — never auto-rendered."
        ),
    )
    tsc_photo_url = forms.URLField(
        required=False,
        widget=_URL,
        label=_("Teacher spotlight: photo URL (optional)"),
        help_text=_(
            "Optional full URL to a teacher photo. Empty = fall back to "
            "the avatar-initials block. Must be HTTPS."
        ),
    )

    # 4) tenant_dashboard.upcoming_events_strip
    ues_label = forms.CharField(
        required=False,
        widget=_TEXT,
        label=_("Upcoming events: section label"),
        help_text=_("Header shown above the strip (e.g. 'Upcoming · next 14 days')."),
    )
    ues_events = forms.CharField(
        required=False,
        widget=_TEXTAREA_LARGE,
        label=_("Upcoming events: events"),
        help_text=_(
            "One per line: YYYY-MM-DD | title  (or MM-DD | title). "
            "Year discarded for display; malformed dates skipped. "
            "Renders as horizontal-scrolling event cards."
        ),
    )

    # ---- v3.57.12 Rich editors (6 NEW high-value sections) ------------
    # Extends the v3.57.2 rich-editor pattern (lod_/asb_/tsc_/ues_) with
    # 6 more sections. Each section's flat fields write into the SAME
    # nested key the enable toggle targets — operator-supplied empties
    # are filtered out of the overlay so `_deep_merge` in cockpit_context
    # preserves the defaults from the helper modules.

    # 5) tenant_dashboard.today_snapshot
    tsn_label = forms.CharField(
        required=False,
        widget=_TEXT,
        label=_("Today snapshot: label"),
        help_text=_(
            "Section header above the snapshot row "
            "(e.g. 'Today · live'). Maps to cockpit.today_snapshot.section_label."
        ),
    )
    tsn_greeting = forms.CharField(
        required=False,
        max_length=120,
        widget=_TEXT,
        label=_("Today snapshot: greeting"),
        help_text=_(
            "Short personalised greeting line (max 120 chars). "
            "Operator-published — never auto-rendered from user data."
        ),
    )
    tsn_metric_rows = forms.CharField(
        required=False,
        widget=_TEXTAREA_MEDIUM,
        label=_("Today snapshot: metric rows"),
        help_text=_(
            "One per line: label | value | hint. Renders as KPI cards "
            "(label = header, value = big number, hint = sublabel). "
            "Empty lines and label-only rows skipped."
        ),
    )

    # 6) tenant_dashboard.quick_actions_grid
    qag_label = forms.CharField(
        required=False,
        widget=_TEXT,
        label=_("Quick actions: label"),
        help_text=_(
            "Section header above the action grid "
            "(e.g. 'Quick actions'). Maps to cockpit.quick_actions.section_label."
        ),
    )
    qag_actions = forms.CharField(
        required=False,
        widget=_TEXTAREA_LARGE,
        label=_("Quick actions: actions"),
        help_text=_(
            "One per line: icon | label | url | description. "
            "Renders as a 6-tile grid; rows without a label are skipped. "
            "Icon may be a single glyph or empty."
        ),
    )

    # 7) tenant_dashboard.activity_timeline
    atl_label = forms.CharField(
        required=False,
        widget=_TEXT,
        label=_("Activity timeline: label"),
        help_text=_(
            "Title shown above the recent activity rail "
            "(e.g. 'Recent activity'). Maps to cockpit.activity_timeline.title."
        ),
    )
    atl_events = forms.CharField(
        required=False,
        widget=_TEXTAREA_LARGE,
        label=_("Activity timeline: events"),
        help_text=_(
            "One per line: YYYY-MM-DD HH:MM | actor | action | target. "
            "Lenient — trailing columns may be omitted. Rows without an "
            "action are skipped. Timestamp string is opaque (operators may "
            "use '2m ago' / 'now' / ISO)."
        ),
    )

    # 8) tenant_dashboard.achievements_card
    ach_label = forms.CharField(
        required=False,
        widget=_TEXT,
        label=_("Achievements: label"),
        help_text=_(
            "Title shown on the achievements card "
            "(e.g. 'Achievements'). Maps to cockpit.achievements.title."
        ),
    )
    ach_current_streak = forms.IntegerField(
        required=False,
        min_value=0,
        widget=_NUMBER,
        label=_("Achievements: current streak"),
        help_text=_(
            "Optional integer streak count (days). Persisted under "
            "cockpit.achievements.current_streak; rendering partials that "
            "ignore the key are unaffected."
        ),
    )
    ach_badges = forms.CharField(
        required=False,
        widget=_TEXTAREA_MEDIUM,
        label=_("Achievements: badges"),
        help_text=_(
            "One per line: icon | label | earned_on. Renders as a chip list; "
            "rows without a label are skipped. ``earned_on`` is free-form "
            "(e.g. '2026-05-21' or 'last week')."
        ),
    )

    # 9) manager_200x.live_world_map
    lwm_label = forms.CharField(
        required=False,
        widget=_TEXT,
        label=_("Live world map: label"),
        help_text=_(
            "Eyebrow caption above the hero count "
            "(e.g. 'GLOBAL FOOTPRINT'). Maps to cockpit.live_world_map.eyebrow."
        ),
    )
    lwm_hero_value = forms.CharField(
        required=False,
        widget=_TEXT,
        label=_("Live world map: hero value"),
        help_text=_(
            "Mega-number + suffix as a single string "
            "(e.g. '127 schools live'). Stored as schools_live + "
            "schools_live_label split on the first space, or as a single "
            "value if no space."
        ),
    )
    lwm_regional_rows = forms.CharField(
        required=False,
        widget=_TEXTAREA_MEDIUM,
        label=_("Live world map: regional rows"),
        help_text=_(
            "One per line: region | count | trend. Renders as the legend "
            "table beneath the map. Trend column is optional (free-form, "
            "e.g. '+3 wk-on-wk'). Rows without a region label are skipped."
        ),
    )

    # 10) manager_200x.audit_feed
    auf_label = forms.CharField(
        required=False,
        widget=_TEXT,
        label=_("Audit feed: label"),
        help_text=_(
            "Title shown above the audit table "
            "(e.g. 'AUDIT FEED · LIVE'). Maps to cockpit.audit_feed.title."
        ),
    )
    auf_events = forms.CharField(
        required=False,
        widget=_TEXTAREA_LARGE,
        label=_("Audit feed: events"),
        help_text=_(
            "One per line: severity | actor | action | timestamp. "
            "Severity ∈ {ok, info, warn, danger}; anything else falls back "
            "to 'info'. Rows without an action are skipped. "
            "severity_label is derived automatically."
        ),
    )

    # ---- v3.57.13 Rich editors (5 NEW sections) -----------------------
    # Extends the v3.57.12 pattern to 5 more high-value sections drawn
    # from manager_200x (forecast_lane / slo_clocks / trust_nutrition)
    # and tenant_v3_extended (parent_teacher_thread / financial_timeline).
    # Same forgiving parser contract: empty/malformed rows skipped;
    # operator-supplied empties filtered from the overlay before
    # `.update()` so `_deep_merge` preserves defaults from the helper
    # modules.

    # 11) manager_200x.forecast_lane
    fcl_label = forms.CharField(
        required=False,
        widget=_TEXT,
        label=_("Forecast lane: label"),
        help_text=_(
            "Section header above the forecast cards "
            "(e.g. 'Forecast · next 7 days'). Maps to cockpit.forecast_lane.label."
        ),
    )
    fcl_cards = forms.CharField(
        required=False,
        widget=_TEXTAREA_LARGE,
        label=_("Forecast lane: cards"),
        help_text=_(
            "One per line: head | value | label | severity. "
            "Severity ∈ {ok, info, warn, danger}; anything else falls "
            "back to 'info'. Rows without a head are skipped. "
            "Polyline coords + confidence bands stay code-owned and "
            "fall through from section defaults."
        ),
    )

    # 12) manager_200x.slo_clocks
    slo_label = forms.CharField(
        required=False,
        widget=_TEXT,
        label=_("SLO clocks: label"),
        help_text=_(
            "Header copy for the SLO clocks card (free-form). "
            "Persisted under cockpit.slo_clocks.label; rendering partials "
            "that don't read it ignore the extra key cleanly."
        ),
    )
    slo_clocks_rows = forms.CharField(
        required=False,
        widget=_TEXTAREA_MEDIUM,
        label=_("SLO clocks: clocks"),
        help_text=_(
            "One per line: name | value | unit | severity. "
            "Severity ∈ {ok, info, warn, danger}; anything else falls "
            "back to 'info'. Rows without a name are skipped. "
            "Renders as monospace-digit dark cards with pulse dots."
        ),
    )

    # 13) manager_200x.trust_nutrition
    tnt_label = forms.CharField(
        required=False,
        widget=_TEXT,
        label=_("Trust nutrition: label"),
        help_text=_(
            "Italic-serif title for the nutrition-label trust card "
            "(e.g. 'Trust nutrition'). Maps to cockpit.trust_nutrition.title."
        ),
    )
    tnt_rows = forms.CharField(
        required=False,
        widget=_TEXTAREA_MEDIUM,
        label=_("Trust nutrition: rows"),
        help_text=_(
            "One per line: metric | value | severity | note. "
            "Note column optional. Severity ∈ {ok, warn, danger, neutral}; "
            "anything else falls back to 'neutral'. Rows without a metric "
            "label are skipped."
        ),
    )

    # 14) tenant_v3_extended.parent_teacher_thread
    ptt_label = forms.CharField(
        required=False,
        widget=_TEXT,
        label=_("Parent-teacher thread: label"),
        help_text=_(
            "Title shown above the inline message thread "
            "(e.g. 'Teacher thread'). Maps to cockpit.parent_teacher_thread.title."
        ),
    )
    ptt_messages = forms.CharField(
        required=False,
        widget=_TEXTAREA_LARGE,
        label=_("Parent-teacher thread: messages"),
        help_text=_(
            "One per line: mine_or_theirs | author | timestamp | body. "
            "mine_or_theirs ∈ {mine, theirs} (controls bubble alignment). "
            "Author initials are derived from the first capital of each "
            "name token. Rows without a body are skipped. Reply-box URL "
            "+ placeholder fall through to section defaults."
        ),
    )

    # 15) tenant_v3_extended.financial_timeline
    ftl_label = forms.CharField(
        required=False,
        widget=_TEXT,
        label=_("Financial timeline: label"),
        help_text=_(
            "Title shown above the fees/payments timeline "
            "(e.g. 'Financial timeline'). Maps to cockpit.financial_timeline.title."
        ),
    )
    ftl_current_balance = forms.CharField(
        required=False,
        widget=_TEXT,
        label=_("Financial timeline: current balance"),
        help_text=_(
            "Operator-formatted balance string (e.g. '$2,450.00'). "
            "Stored under cockpit.financial_timeline.balance_display; "
            "raw Decimals are never rendered — the operator owns the "
            "currency symbol + locale formatting."
        ),
    )
    ftl_events = forms.CharField(
        required=False,
        widget=_TEXTAREA_LARGE,
        label=_("Financial timeline: events"),
        help_text=_(
            "One per line: date | type | description | amount. "
            "Type ∈ {fee, payment, discount, balance}; anything else "
            "falls back to 'fee'. Rows without a description are skipped. "
            "Amount is operator-formatted (e.g. '+$120.00', '-$50.00')."
        ),
    )

    # ---- v3.57.14 Rich editors (6 NEW sections) -----------------------
    # Extends the v3.57.13 pattern to 6 more sections drawn from
    # manager_200x (operator_presence / operator_notebook /
    # tenant_heatmap / revenue_waterfall) and tenant_v3_extended
    # (realtime_presence / calendar_weather). Same forgiving parser
    # contract: empty/malformed rows skipped; operator-supplied empties
    # filtered from the overlay before `.update()` so `_deep_merge`
    # preserves defaults from the helper modules.

    # 16) manager_200x.operator_presence
    opr_label = forms.CharField(
        required=False,
        widget=_TEXT,
        label=_("Operator presence: label"),
        help_text=_(
            "Aria-label string for the operator-presence capsule "
            "(e.g. 'Operators online and platform status'). Maps to "
            "cockpit.operator_presence.aria_label."
        ),
    )
    opr_online_count = forms.IntegerField(
        required=False,
        min_value=0,
        widget=_NUMBER,
        label=_("Operator presence: online count"),
        help_text=_(
            "Number of operators currently online. Rendered via blocktrans "
            "(singular/plural). Maps to "
            "cockpit.operator_presence.operators_online_count."
        ),
    )
    opr_avatars = forms.CharField(
        required=False,
        widget=_TEXTAREA_MEDIUM,
        label=_("Operator presence: avatars"),
        help_text=_(
            "One per line: initials | name | role | status. "
            "Status ∈ {online, idle, away}; anything else falls back to "
            "'online'. Trailing columns are optional. Rows without "
            "initials are skipped. Gradient chip color is derived from "
            "status (online=emerald, idle=amber, away=indigo)."
        ),
    )

    # 17) manager_200x.operator_notebook
    opn_label = forms.CharField(
        required=False,
        widget=_TEXT,
        label=_("Operator notebook: label"),
        help_text=_(
            "Uppercase tiny title shown on the floating notebook "
            "(e.g. 'Add to notebook'). Maps to "
            "cockpit.operator_notebook.title."
        ),
    )
    opn_mic_enabled = forms.BooleanField(
        required=False,
        widget=_CHECK,
        label=_("Operator notebook: dictation mic enabled"),
        help_text=_(
            "When checked, the notebook shows a dictation mic button. "
            "Maps to cockpit.operator_notebook.mic_enabled."
        ),
    )
    opn_placeholder = forms.CharField(
        required=False,
        max_length=240,
        widget=_TEXT,
        label=_("Operator notebook: placeholder"),
        help_text=_(
            "Serif-italic textarea placeholder (max 240 chars). "
            "Maps to cockpit.operator_notebook.placeholder."
        ),
    )

    # 18) manager_200x.tenant_heatmap
    thm_label = forms.CharField(
        required=False,
        widget=_TEXT,
        label=_("Tenant heatmap: label"),
        help_text=_(
            "Title shown on the heatmap card "
            "(e.g. 'Every school'). Maps to cockpit.tenant_heatmap.title."
        ),
    )
    thm_tile_rows = forms.CharField(
        required=False,
        widget=_TEXTAREA_LARGE,
        label=_("Tenant heatmap: tile rows"),
        help_text=_(
            "One per line: region | health_status | label. "
            "Label column optional (region doubles as hover label). "
            "health_status ∈ {healthy, ok, warn, danger, idle}; anything "
            "else falls back to 'healthy'. Rows without a region are "
            "skipped. Renders as a 20-col dense grid of tinted tiles."
        ),
    )

    # 19) manager_200x.revenue_waterfall
    rwf_label = forms.CharField(
        required=False,
        widget=_TEXT,
        label=_("Revenue waterfall: label"),
        help_text=_(
            "Eyebrow caption above the waterfall chart "
            "(e.g. 'MRR waterfall · this month'). Maps to "
            "cockpit.revenue_waterfall.eyebrow."
        ),
    )
    rwf_start_value = forms.CharField(
        required=False,
        widget=_TEXT,
        label=_("Revenue waterfall: start value"),
        help_text=_(
            "Opening value shown in the title prefix "
            "(e.g. 'From $39.2k'). Maps to cockpit.revenue_waterfall.title."
        ),
    )
    rwf_end_value = forms.CharField(
        required=False,
        widget=_TEXT,
        label=_("Revenue waterfall: end value"),
        help_text=_(
            "Closing value shown in the title suffix "
            "(e.g. '$42.1k'). Maps to cockpit.revenue_waterfall.title_end."
        ),
    )
    rwf_bars = forms.CharField(
        required=False,
        widget=_TEXTAREA_LARGE,
        label=_("Revenue waterfall: bars"),
        help_text=_(
            "One per line: category | delta | severity. "
            "Severity ∈ {start, gain, loss, end}; anything else falls "
            "back to 'gain'. Delta is operator-formatted (e.g. "
            "'+$3.8k', '-$2.1k'). Rows without a category are skipped. "
            "SVG geometry (x/y/width/height) stays code-owned and falls "
            "through from section defaults."
        ),
    )

    # 20) tenant_v3_extended.realtime_presence
    rtp_label = forms.CharField(
        required=False,
        widget=_TEXT,
        label=_("Realtime presence: label"),
        help_text=_(
            "Title shown above the presence dots "
            "(e.g. 'Classmates online'). Maps to "
            "cockpit.realtime_presence.title."
        ),
    )
    rtp_classmates_online = forms.IntegerField(
        required=False,
        min_value=0,
        widget=_NUMBER,
        label=_("Realtime presence: classmates online"),
        help_text=_(
            "Number of classmates currently online (display only — "
            "websocket presence channel is a8-wire-pending). Maps to "
            "cockpit.realtime_presence.online_count."
        ),
    )
    rtp_dots = forms.CharField(
        required=False,
        widget=_TEXTAREA_MEDIUM,
        label=_("Realtime presence: dots"),
        help_text=_(
            "One per line: initials | status. "
            "Status ∈ {online, idle, away}; anything else falls back to "
            "'away'. Status column optional. Rows without initials are "
            "skipped. Initials only — full names never appear here."
        ),
    )

    # 21) tenant_v3_extended.calendar_weather
    cwt_label = forms.CharField(
        required=False,
        widget=_TEXT,
        label=_("Calendar weather: label"),
        help_text=_(
            "Title shown above the 7-day strip "
            "(e.g. 'Week ahead'). Maps to cockpit.calendar_weather.title."
        ),
    )
    cwt_days = forms.CharField(
        required=False,
        widget=_TEXTAREA_LARGE,
        label=_("Calendar weather: days"),
        help_text=_(
            "One per line: date | weather_emoji | events. "
            "Date may be YYYY-MM-DD (weekday auto-derived), MM-DD, "
            "or a bare label (e.g. 'Mon 21'). Weather emoji is a "
            "single glyph. Events is a free-form short label. Rows "
            "without a date are skipped."
        ),
    )

    class Meta:
        # Imported lazily inside ``Meta`` to keep the import surface narrow.
        from apps.siteconfig.models import SiteSettings as _SiteSettings

        model = _SiteSettings
        fields: list[str] = ["cockpit_payload"]
        # Hide the raw JSON column from rendering — operators edit the
        # flat fields above; ``clean()`` rebuilds the nested dict.
        widgets = {"cockpit_payload": forms.HiddenInput()}

    # ----- helpers for declarative fieldset grouping (templates / admin) ---
    FOOTER_FIELDS: tuple[str, ...] = (
        "footer_wordmark",
        "footer_motto",
        "footer_founded_year",
        "footer_descriptor",
        "footer_trust_pillars",
        "footer_language_label",
        "footer_app_badges",
        "footer_social",
        "footer_contacts",
        "footer_stat_line",
        "footer_legal_links",
        "footer_copyright_holder",
        "footer_powered_by_label",
        "footer_powered_by_url",
    )
    COMMUNITY_FIELDS: tuple[str, ...] = (
        "community_enabled",
        "achievement_enabled",
        "achievement_title",
        "achievement_period_label",
        "achievement_student_initials",
        "achievement_student_name",
        "achievement_student_subline",
        "achievement_teacher_quote",
        "achievement_teacher_cite",
        "testimonial_enabled",
        "testimonial_title",
        "testimonial_quotes",
        "testimonial_interval_ms",
        "map_enabled",
        "map_title",
        "map_period_label",
        "map_address_line_1",
        "map_address_line_2",
        "map_maps_url",
        "map_cta_label",
    )
    NEWSLETTER_FIELDS: tuple[str, ...] = (
        "newsletter_enabled",
        "newsletter_title",
        "newsletter_subtitle",
        "newsletter_placeholder",
        "newsletter_cta_label",
        "newsletter_submit_url",
        "newsletter_privacy_url",
        "newsletter_privacy_label",
    )
    # v3.57.1 adoption-wave fieldsets — enable toggles only (rich editors land
    # in a follow-up wave; the JSON column carries the deeper schema).
    FRONT_OFFICE_FIELDS: tuple[str, ...] = (
        "fo_revenue_cohort_enabled",
        "fo_nps_ticker_enabled",
        "fo_support_burndown_enabled",
        "fo_deploy_pipeline_enabled",
        "fo_churn_scorecard_enabled",
        "fo_ai_fixes_feed_enabled",
        "fo_capacity_planning_enabled",
        "fo_regional_clocks_enabled",
        "fo_onboarding_pipeline_enabled",
        "fo_audit_wordcloud_enabled",
    )
    TENANT_V3_EXTENDED_FIELDS: tuple[str, ...] = (
        "tv3_ai_study_buddy_enabled",
        "tv3_parent_teacher_thread_enabled",
        "tv3_realtime_presence_enabled",
        "tv3_gradebook_trend_enabled",
        "tv3_attendance_heatmap_enabled",
        "tv3_financial_timeline_enabled",
        "tv3_sibling_compare_enabled",
        "tv3_life_event_timeline_enabled",
        "tv3_calendar_weather_enabled",
        "tv3_lesson_of_day_enabled",
    )
    # v3.57.2 rich-editor fieldsets — promote 4 sections from
    # enable-toggle-only to full content editor.
    LESSON_OF_DAY_FIELDS: tuple[str, ...] = (
        "lod_title",
        "lod_subject",
        "lod_summary",
        "lod_resources",
    )
    AI_STUDY_BUDDY_FIELDS: tuple[str, ...] = (
        "asb_title",
        "asb_intro",
        "asb_suggestions",
    )
    TEACHER_SPOTLIGHT_FIELDS: tuple[str, ...] = (
        "tsc_name",
        "tsc_subject",
        "tsc_quote",
        "tsc_photo_url",
    )
    UPCOMING_EVENTS_FIELDS: tuple[str, ...] = (
        "ues_label",
        "ues_events",
    )
    # v3.57.12 rich-editor fieldsets — 6 NEW sections.
    TODAY_SNAPSHOT_FIELDS: tuple[str, ...] = (
        "tsn_label",
        "tsn_greeting",
        "tsn_metric_rows",
    )
    QUICK_ACTIONS_GRID_FIELDS: tuple[str, ...] = (
        "qag_label",
        "qag_actions",
    )
    ACTIVITY_TIMELINE_FIELDS: tuple[str, ...] = (
        "atl_label",
        "atl_events",
    )
    ACHIEVEMENTS_CARD_FIELDS: tuple[str, ...] = (
        "ach_label",
        "ach_current_streak",
        "ach_badges",
    )
    LIVE_WORLD_MAP_FIELDS: tuple[str, ...] = (
        "lwm_label",
        "lwm_hero_value",
        "lwm_regional_rows",
    )
    AUDIT_FEED_FIELDS: tuple[str, ...] = (
        "auf_label",
        "auf_events",
    )
    # v3.57.13 rich-editor fieldsets — 5 NEW sections.
    FORECAST_LANE_FIELDS: tuple[str, ...] = (
        "fcl_label",
        "fcl_cards",
    )
    SLO_CLOCKS_FIELDS: tuple[str, ...] = (
        "slo_label",
        "slo_clocks_rows",
    )
    TRUST_NUTRITION_FIELDS: tuple[str, ...] = (
        "tnt_label",
        "tnt_rows",
    )
    PARENT_TEACHER_THREAD_FIELDS: tuple[str, ...] = (
        "ptt_label",
        "ptt_messages",
    )
    FINANCIAL_TIMELINE_FIELDS: tuple[str, ...] = (
        "ftl_label",
        "ftl_current_balance",
        "ftl_events",
    )
    # v3.57.14 rich-editor fieldsets — 6 NEW sections.
    OPERATOR_PRESENCE_FIELDS: tuple[str, ...] = (
        "opr_label",
        "opr_online_count",
        "opr_avatars",
    )
    OPERATOR_NOTEBOOK_FIELDS: tuple[str, ...] = (
        "opn_label",
        "opn_mic_enabled",
        "opn_placeholder",
    )
    TENANT_HEATMAP_FIELDS: tuple[str, ...] = (
        "thm_label",
        "thm_tile_rows",
    )
    REVENUE_WATERFALL_FIELDS: tuple[str, ...] = (
        "rwf_label",
        "rwf_start_value",
        "rwf_end_value",
        "rwf_bars",
    )
    REALTIME_PRESENCE_FIELDS: tuple[str, ...] = (
        "rtp_label",
        "rtp_classmates_online",
        "rtp_dots",
    )
    CALENDAR_WEATHER_FIELDS: tuple[str, ...] = (
        "cwt_label",
        "cwt_days",
    )

    # Form-field-name → cockpit_payload key mapping for the v3.57.1 sections.
    # Used by both _seed_initial_from_payload and _build_payload so the round
    # trip stays in lockstep when sections are added/removed.
    _FRONT_OFFICE_FIELD_TO_KEY: tuple[tuple[str, str], ...] = (
        ("fo_revenue_cohort_enabled", "revenue_cohort"),
        ("fo_nps_ticker_enabled", "nps_ticker"),
        ("fo_support_burndown_enabled", "support_burndown"),
        ("fo_deploy_pipeline_enabled", "deploy_pipeline"),
        ("fo_churn_scorecard_enabled", "churn_scorecard"),
        ("fo_ai_fixes_feed_enabled", "ai_fixes_feed"),
        ("fo_capacity_planning_enabled", "capacity_planning"),
        ("fo_regional_clocks_enabled", "regional_clocks"),
        ("fo_onboarding_pipeline_enabled", "onboarding_pipeline"),
        ("fo_audit_wordcloud_enabled", "audit_wordcloud"),
    )
    _TENANT_V3_EXTENDED_FIELD_TO_KEY: tuple[tuple[str, str], ...] = (
        ("tv3_ai_study_buddy_enabled", "ai_study_buddy"),
        ("tv3_parent_teacher_thread_enabled", "parent_teacher_thread"),
        ("tv3_realtime_presence_enabled", "realtime_presence"),
        ("tv3_gradebook_trend_enabled", "gradebook_trend"),
        ("tv3_attendance_heatmap_enabled", "attendance_heatmap"),
        ("tv3_financial_timeline_enabled", "financial_timeline"),
        ("tv3_sibling_compare_enabled", "sibling_compare"),
        ("tv3_life_event_timeline_enabled", "life_event_timeline"),
        ("tv3_calendar_weather_enabled", "calendar_weather"),
        ("tv3_lesson_of_day_enabled", "lesson_of_day"),
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        payload = self._read_existing_payload()
        self._seed_initial_from_payload(payload)

    # ------------------------------------------------------------------
    # Existing-payload -> flat-form-initial round trip.
    # ------------------------------------------------------------------

    def _read_existing_payload(self) -> dict[str, Any]:
        instance_payload = getattr(self.instance, "cockpit_payload", None)
        if isinstance(instance_payload, dict):
            return instance_payload
        return {}

    def _seed_initial_from_payload(self, payload: dict[str, Any]) -> None:
        footer = payload.get("footer") or {}
        community = payload.get("community_band") or {}
        newsletter = payload.get("newsletter_band") or {}

        brand = footer.get("brand") or {}
        self.fields["footer_wordmark"].initial = brand.get("wordmark", "")
        self.fields["footer_motto"].initial = brand.get("motto", "")
        self.fields["footer_founded_year"].initial = brand.get("founded_year")
        self.fields["footer_descriptor"].initial = brand.get("descriptor", "")

        self.fields["footer_trust_pillars"].initial = _serialize_trust_pillars(
            footer.get("trust_pillars")
        )

        language = footer.get("language") or {}
        self.fields["footer_language_label"].initial = language.get("label", "")

        self.fields["footer_app_badges"].initial = _serialize_app_badges(
            footer.get("app_badges")
        )
        self.fields["footer_social"].initial = _serialize_social(footer.get("social"))
        self.fields["footer_contacts"].initial = _serialize_contacts(
            footer.get("contacts")
        )
        self.fields["footer_stat_line"].initial = footer.get("stat_line", "")
        self.fields["footer_legal_links"].initial = _serialize_legal_links(
            footer.get("legal_links")
        )
        self.fields["footer_copyright_holder"].initial = footer.get(
            "copyright_holder", ""
        )

        powered_by = footer.get("powered_by") or {}
        self.fields["footer_powered_by_label"].initial = powered_by.get("label", "")
        self.fields["footer_powered_by_url"].initial = powered_by.get("url", "")

        # ---- community ------------------------------------------------
        self.fields["community_enabled"].initial = bool(community.get("enabled"))

        achievement = community.get("achievement") or {}
        self.fields["achievement_enabled"].initial = bool(achievement.get("enabled"))
        self.fields["achievement_title"].initial = achievement.get("title", "")
        self.fields["achievement_period_label"].initial = achievement.get(
            "period_label", ""
        )
        self.fields["achievement_student_initials"].initial = achievement.get(
            "student_initials", ""
        )
        self.fields["achievement_student_name"].initial = achievement.get(
            "student_name", ""
        )
        self.fields["achievement_student_subline"].initial = achievement.get(
            "student_subline", ""
        )
        self.fields["achievement_teacher_quote"].initial = achievement.get(
            "teacher_quote", ""
        )
        self.fields["achievement_teacher_cite"].initial = achievement.get(
            "teacher_cite", ""
        )

        testimonial = community.get("testimonial") or {}
        self.fields["testimonial_enabled"].initial = bool(testimonial.get("enabled"))
        self.fields["testimonial_title"].initial = testimonial.get("title", "")
        self.fields["testimonial_quotes"].initial = _serialize_quotes(
            testimonial.get("quotes")
        )
        self.fields["testimonial_interval_ms"].initial = testimonial.get(
            "interval_ms"
        )

        map_block = community.get("map") or {}
        self.fields["map_enabled"].initial = bool(map_block.get("enabled"))
        self.fields["map_title"].initial = map_block.get("title", "")
        self.fields["map_period_label"].initial = map_block.get("period_label", "")
        self.fields["map_address_line_1"].initial = map_block.get("address_line_1", "")
        self.fields["map_address_line_2"].initial = map_block.get("address_line_2", "")
        self.fields["map_maps_url"].initial = map_block.get("maps_url", "")
        self.fields["map_cta_label"].initial = map_block.get("cta_label", "")

        # ---- newsletter ----------------------------------------------
        self.fields["newsletter_enabled"].initial = bool(newsletter.get("enabled"))
        self.fields["newsletter_title"].initial = newsletter.get("title", "")
        self.fields["newsletter_subtitle"].initial = newsletter.get("subtitle", "")
        self.fields["newsletter_placeholder"].initial = newsletter.get(
            "placeholder", ""
        )
        self.fields["newsletter_cta_label"].initial = newsletter.get("cta_label", "")
        self.fields["newsletter_submit_url"].initial = newsletter.get("submit_url", "")
        self.fields["newsletter_privacy_url"].initial = newsletter.get(
            "privacy_url", ""
        )
        self.fields["newsletter_privacy_label"].initial = newsletter.get(
            "privacy_label", ""
        )

        # ---- v3.57.1 front-office 200x enable toggles --------------------
        for field_name, payload_key in self._FRONT_OFFICE_FIELD_TO_KEY:
            section = payload.get(payload_key) or {}
            self.fields[field_name].initial = bool(section.get("enabled"))

        # ---- v3.57.1 tenant v3 100x enable toggles ------------------------
        for field_name, payload_key in self._TENANT_V3_EXTENDED_FIELD_TO_KEY:
            section = payload.get(payload_key) or {}
            self.fields[field_name].initial = bool(section.get("enabled"))

        # ---- v3.57.2 rich-editor seeds ------------------------------------
        # tenant_v3_extended.lesson_of_day
        lesson = payload.get("lesson_of_day") or {}
        self.fields["lod_title"].initial = lesson.get("title", "")
        self.fields["lod_subject"].initial = lesson.get("subject", "")
        self.fields["lod_summary"].initial = lesson.get("summary", "")
        self.fields["lod_resources"].initial = _serialize_lesson_resources(
            lesson.get("resources")
        )

        # tenant_v3_extended.ai_study_buddy
        buddy = payload.get("ai_study_buddy") or {}
        self.fields["asb_title"].initial = buddy.get("label", "")
        self.fields["asb_intro"].initial = buddy.get("greeting", "")
        self.fields["asb_suggestions"].initial = _serialize_suggestion_lines(
            buddy.get("suggestions")
        )

        # tenant_dashboard.teacher_spotlight
        spotlight = payload.get("teacher_spotlight") or {}
        self.fields["tsc_name"].initial = spotlight.get("teacher_name", "")
        self.fields["tsc_subject"].initial = spotlight.get("teacher_role", "")
        self.fields["tsc_quote"].initial = spotlight.get("quote", "")
        self.fields["tsc_photo_url"].initial = spotlight.get("photo_url", "")

        # tenant_dashboard.upcoming_events
        events_section = payload.get("upcoming_events") or {}
        self.fields["ues_label"].initial = events_section.get("section_label", "")
        self.fields["ues_events"].initial = _serialize_upcoming_events(
            events_section.get("events")
        )

        # ---- v3.57.12 rich-editor seeds (6 NEW sections) ------------------
        # tenant_dashboard.today_snapshot
        today = payload.get("today_snapshot") or {}
        self.fields["tsn_label"].initial = today.get("section_label", "")
        self.fields["tsn_greeting"].initial = today.get("greeting", "")
        self.fields["tsn_metric_rows"].initial = _serialize_metric_rows(
            today.get("cards")
        )

        # tenant_dashboard.quick_actions
        quick = payload.get("quick_actions") or {}
        self.fields["qag_label"].initial = quick.get("section_label", "")
        self.fields["qag_actions"].initial = _serialize_quick_actions(
            quick.get("tiles")
        )

        # tenant_dashboard.activity_timeline
        activity = payload.get("activity_timeline") or {}
        self.fields["atl_label"].initial = activity.get("title", "")
        self.fields["atl_events"].initial = _serialize_activity_events(
            activity.get("items")
        )

        # tenant_dashboard.achievements
        achievements = payload.get("achievements") or {}
        self.fields["ach_label"].initial = achievements.get("title", "")
        self.fields["ach_current_streak"].initial = achievements.get(
            "current_streak"
        )
        self.fields["ach_badges"].initial = _serialize_achievement_badges(
            achievements.get("list")
        )

        # manager_200x.live_world_map
        world_map = payload.get("live_world_map") or {}
        self.fields["lwm_label"].initial = world_map.get("eyebrow", "")
        # Round-trip the hero value by joining schools_live + label on space.
        schools_live = str(world_map.get("schools_live", "")).strip()
        schools_label = str(world_map.get("schools_live_label", "")).strip()
        if schools_live and schools_label:
            hero_value_initial = f"{schools_live} {schools_label}"
        else:
            hero_value_initial = schools_live or schools_label
        self.fields["lwm_hero_value"].initial = hero_value_initial
        self.fields["lwm_regional_rows"].initial = _serialize_regional_rows(
            world_map.get("regional_breakdown")
        )

        # manager_200x.audit_feed
        audit = payload.get("audit_feed") or {}
        self.fields["auf_label"].initial = audit.get("title", "")
        self.fields["auf_events"].initial = _serialize_audit_events(
            audit.get("events")
        )

        # ---- v3.57.13 rich-editor seeds (5 NEW sections) ------------------
        # manager_200x.forecast_lane
        forecast = payload.get("forecast_lane") or {}
        self.fields["fcl_label"].initial = forecast.get("label", "")
        self.fields["fcl_cards"].initial = _serialize_forecast_cards(
            forecast.get("cards")
        )

        # manager_200x.slo_clocks
        slo = payload.get("slo_clocks") or {}
        # ``label`` is not in the helper defaults but is operator-editable
        # here; round-trip cleanly via .get() with empty fallback.
        self.fields["slo_label"].initial = slo.get("label", "")
        self.fields["slo_clocks_rows"].initial = _serialize_slo_clocks(
            slo.get("clocks")
        )

        # manager_200x.trust_nutrition
        trust = payload.get("trust_nutrition") or {}
        self.fields["tnt_label"].initial = trust.get("title", "")
        self.fields["tnt_rows"].initial = _serialize_trust_rows(
            trust.get("rows")
        )

        # tenant_v3_extended.parent_teacher_thread
        thread = payload.get("parent_teacher_thread") or {}
        self.fields["ptt_label"].initial = thread.get("title", "")
        self.fields["ptt_messages"].initial = _serialize_thread_messages(
            thread.get("messages")
        )

        # tenant_v3_extended.financial_timeline
        financial = payload.get("financial_timeline") or {}
        self.fields["ftl_label"].initial = financial.get("title", "")
        self.fields["ftl_current_balance"].initial = financial.get(
            "balance_display", ""
        )
        self.fields["ftl_events"].initial = _serialize_financial_events(
            financial.get("events")
        )

        # ---- v3.57.14 rich-editor seeds (6 NEW sections) ------------------
        # manager_200x.operator_presence
        opr = payload.get("operator_presence") or {}
        self.fields["opr_label"].initial = opr.get("aria_label", "")
        self.fields["opr_online_count"].initial = opr.get("operators_online_count")
        self.fields["opr_avatars"].initial = _serialize_operator_presence_avatars(
            opr.get("avatars")
        )

        # manager_200x.operator_notebook
        opn = payload.get("operator_notebook") or {}
        self.fields["opn_label"].initial = opn.get("title", "")
        # ``mic_enabled`` defaults to True in the helper; round-trip the
        # explicit-False operator save honestly via .get() with None
        # fallback so the checkbox renders unchecked iff the operator
        # cleared it.
        if "mic_enabled" in opn:
            self.fields["opn_mic_enabled"].initial = bool(opn.get("mic_enabled"))
        self.fields["opn_placeholder"].initial = opn.get("placeholder", "")

        # manager_200x.tenant_heatmap
        heatmap = payload.get("tenant_heatmap") or {}
        self.fields["thm_label"].initial = heatmap.get("title", "")
        self.fields["thm_tile_rows"].initial = _serialize_heatmap_tiles(
            heatmap.get("tiles")
        )

        # manager_200x.revenue_waterfall
        waterfall = payload.get("revenue_waterfall") or {}
        self.fields["rwf_label"].initial = waterfall.get("eyebrow", "")
        self.fields["rwf_start_value"].initial = waterfall.get("title", "")
        self.fields["rwf_end_value"].initial = waterfall.get("title_end", "")
        self.fields["rwf_bars"].initial = _serialize_waterfall_bars(
            waterfall.get("bars")
        )

        # tenant_v3_extended.realtime_presence
        rtp = payload.get("realtime_presence") or {}
        self.fields["rtp_label"].initial = rtp.get("title", "")
        self.fields["rtp_classmates_online"].initial = rtp.get("online_count")
        self.fields["rtp_dots"].initial = _serialize_realtime_presence_dots(
            rtp.get("presence")
        )

        # tenant_v3_extended.calendar_weather
        cwt = payload.get("calendar_weather") or {}
        self.fields["cwt_label"].initial = cwt.get("title", "")
        self.fields["cwt_days"].initial = _serialize_calendar_weather_days(
            cwt.get("days")
        )

    # ------------------------------------------------------------------
    # Flat-form -> nested-payload assembly.
    # ------------------------------------------------------------------

    def _build_payload(self, cleaned: dict[str, Any]) -> dict[str, Any]:
        """Reassemble the nested ``cockpit_payload`` dict from flat fields."""
        footer: dict[str, Any] = {
            "brand": {
                "wordmark": (cleaned.get("footer_wordmark") or "").strip(),
                "motto": (cleaned.get("footer_motto") or "").strip(),
                "founded_year": cleaned.get("footer_founded_year"),
                "descriptor": (cleaned.get("footer_descriptor") or "").strip(),
            },
            "trust_pillars": _parse_trust_pillars(
                cleaned.get("footer_trust_pillars") or ""
            ),
            "language": {
                "label": (cleaned.get("footer_language_label") or "").strip(),
                # current_locale + has_switcher remain runtime-driven
                # (set by the cockpit context processor + active i18n).
                "current_locale": "",
                "has_switcher": True,
            },
            "app_badges": _parse_app_badges(cleaned.get("footer_app_badges") or ""),
            "social": _parse_social(cleaned.get("footer_social") or ""),
            "contacts": _parse_contacts(cleaned.get("footer_contacts") or ""),
            "stat_line": (cleaned.get("footer_stat_line") or "").strip(),
            "legal_links": _parse_legal_links(cleaned.get("footer_legal_links") or ""),
            "copyright_holder": (
                cleaned.get("footer_copyright_holder") or ""
            ).strip(),
            "powered_by": {
                "label": (cleaned.get("footer_powered_by_label") or "").strip(),
                "url": (cleaned.get("footer_powered_by_url") or "").strip(),
            },
        }

        community: dict[str, Any] = {
            "enabled": bool(cleaned.get("community_enabled")),
            "achievement": {
                "enabled": bool(cleaned.get("achievement_enabled")),
                "title": (cleaned.get("achievement_title") or "").strip(),
                "period_label": (
                    cleaned.get("achievement_period_label") or ""
                ).strip(),
                "student_initials": (
                    cleaned.get("achievement_student_initials") or ""
                ).strip(),
                "student_name": (
                    cleaned.get("achievement_student_name") or ""
                ).strip(),
                "student_subline": (
                    cleaned.get("achievement_student_subline") or ""
                ).strip(),
                "teacher_quote": (
                    cleaned.get("achievement_teacher_quote") or ""
                ).strip(),
                "teacher_cite": (
                    cleaned.get("achievement_teacher_cite") or ""
                ).strip(),
            },
            "testimonial": {
                "enabled": bool(cleaned.get("testimonial_enabled")),
                "title": (cleaned.get("testimonial_title") or "").strip(),
                "quotes": _parse_quotes(cleaned.get("testimonial_quotes") or ""),
                "interval_ms": cleaned.get("testimonial_interval_ms") or 7000,
            },
            "map": {
                "enabled": bool(cleaned.get("map_enabled")),
                "title": (cleaned.get("map_title") or "").strip(),
                "period_label": (cleaned.get("map_period_label") or "").strip(),
                "address_line_1": (
                    cleaned.get("map_address_line_1") or ""
                ).strip(),
                "address_line_2": (
                    cleaned.get("map_address_line_2") or ""
                ).strip(),
                "maps_url": (cleaned.get("map_maps_url") or "").strip(),
                "cta_label": (cleaned.get("map_cta_label") or "").strip(),
            },
        }

        newsletter: dict[str, Any] = {
            "enabled": bool(cleaned.get("newsletter_enabled")),
            "title": (cleaned.get("newsletter_title") or "").strip(),
            "subtitle": (cleaned.get("newsletter_subtitle") or "").strip(),
            "placeholder": (cleaned.get("newsletter_placeholder") or "").strip(),
            "cta_label": (cleaned.get("newsletter_cta_label") or "").strip(),
            "submit_url": (cleaned.get("newsletter_submit_url") or "").strip(),
            "privacy_url": (cleaned.get("newsletter_privacy_url") or "").strip(),
            "privacy_label": (cleaned.get("newsletter_privacy_label") or "").strip(),
        }

        # v3.57.1 adoption-wave: 20 enable toggles round-tripped as nested
        # {section: {"enabled": bool}} dicts. _deep_merge in
        # apps.siteconfig.cockpit_context overlays these on top of the
        # defaults from the helper modules, so an `enabled=True` toggle
        # surfaces the full default schema for that section without the
        # operator having to fill in every field.
        payload: dict[str, Any] = {
            "footer": footer,
            "community_band": community,
            "newsletter_band": newsletter,
        }
        for field_name, payload_key in self._FRONT_OFFICE_FIELD_TO_KEY:
            payload[payload_key] = {"enabled": bool(cleaned.get(field_name))}
        for field_name, payload_key in self._TENANT_V3_EXTENDED_FIELD_TO_KEY:
            payload[payload_key] = {"enabled": bool(cleaned.get(field_name))}

        # v3.57.2 rich-editor merges. _deep_merge in cockpit_context.py
        # already overlays operator values on top of section defaults;
        # here we only need to assemble the operator-supplied subset.
        # We .update() the dicts the enable-toggle loops just wrote so
        # the `enabled` flag survives alongside the new content keys.
        lesson_resources = _parse_lesson_resources(
            cleaned.get("lod_resources") or ""
        )
        lesson_overlay = {
            "title": (cleaned.get("lod_title") or "").strip(),
            "subject": (cleaned.get("lod_subject") or "").strip(),
            "summary": (cleaned.get("lod_summary") or "").strip(),
            "resources": lesson_resources,
        }
        payload.setdefault("lesson_of_day", {}).update(
            {k: v for k, v in lesson_overlay.items() if v not in ("", [], None)}
        )

        buddy_overlay = {
            "label": (cleaned.get("asb_title") or "").strip(),
            "greeting": (cleaned.get("asb_intro") or "").strip(),
            "suggestions": _parse_suggestion_lines(
                cleaned.get("asb_suggestions") or ""
            ),
        }
        payload.setdefault("ai_study_buddy", {}).update(
            {k: v for k, v in buddy_overlay.items() if v not in ("", [], None)}
        )

        spotlight_overlay = {
            "teacher_name": (cleaned.get("tsc_name") or "").strip(),
            "teacher_role": (cleaned.get("tsc_subject") or "").strip(),
            "quote": (cleaned.get("tsc_quote") or "").strip(),
            "photo_url": (cleaned.get("tsc_photo_url") or "").strip(),
        }
        # ``teacher_spotlight`` is a tenant_dashboard section — not driven by
        # a v3.57.1 enable toggle here, so seed an empty dict first.
        payload.setdefault("teacher_spotlight", {}).update(
            {k: v for k, v in spotlight_overlay.items() if v}
        )

        events_overlay: dict[str, Any] = {}
        section_label = (cleaned.get("ues_label") or "").strip()
        if section_label:
            events_overlay["section_label"] = section_label
        parsed_events = _parse_upcoming_events(cleaned.get("ues_events") or "")
        if parsed_events:
            events_overlay["events"] = parsed_events
        if events_overlay:
            payload.setdefault("upcoming_events", {}).update(events_overlay)

        # v3.57.12 rich-editor overlays (6 NEW sections). Same pattern as
        # the v3.57.2 overlays above: build a dict from the operator
        # inputs, filter empty values so `_deep_merge` preserves the
        # defaults, then `.update()` onto a `setdefault()` dict so any
        # existing keys (enable toggles, headline leaf attributes from
        # the v3.57 cockpit fieldset) survive alongside the new content.

        # 5) tenant_dashboard.today_snapshot
        today_overlay: dict[str, Any] = {}
        tsn_label = (cleaned.get("tsn_label") or "").strip()
        if tsn_label:
            today_overlay["section_label"] = tsn_label
        tsn_greeting = (cleaned.get("tsn_greeting") or "").strip()
        if tsn_greeting:
            today_overlay["greeting"] = tsn_greeting
        tsn_cards = _parse_metric_rows(cleaned.get("tsn_metric_rows") or "")
        if tsn_cards:
            today_overlay["cards"] = tsn_cards
        if today_overlay:
            payload.setdefault("today_snapshot", {}).update(today_overlay)

        # 6) tenant_dashboard.quick_actions
        quick_overlay: dict[str, Any] = {}
        qag_label = (cleaned.get("qag_label") or "").strip()
        if qag_label:
            quick_overlay["section_label"] = qag_label
        qag_tiles = _parse_quick_actions(cleaned.get("qag_actions") or "")
        if qag_tiles:
            quick_overlay["tiles"] = qag_tiles
        if quick_overlay:
            payload.setdefault("quick_actions", {}).update(quick_overlay)

        # 7) tenant_dashboard.activity_timeline
        activity_overlay: dict[str, Any] = {}
        atl_label = (cleaned.get("atl_label") or "").strip()
        if atl_label:
            activity_overlay["title"] = atl_label
        atl_items = _parse_activity_events(cleaned.get("atl_events") or "")
        if atl_items:
            activity_overlay["items"] = atl_items
        if activity_overlay:
            payload.setdefault("activity_timeline", {}).update(activity_overlay)

        # 8) tenant_dashboard.achievements
        ach_overlay: dict[str, Any] = {}
        ach_label = (cleaned.get("ach_label") or "").strip()
        if ach_label:
            ach_overlay["title"] = ach_label
        ach_streak = cleaned.get("ach_current_streak")
        if ach_streak is not None and ach_streak != "":
            ach_overlay["current_streak"] = ach_streak
        ach_list = _parse_achievement_badges(cleaned.get("ach_badges") or "")
        if ach_list:
            ach_overlay["list"] = ach_list
        if ach_overlay:
            payload.setdefault("achievements", {}).update(ach_overlay)

        # 9) manager_200x.live_world_map — hero_value splits on first
        # space into (schools_live, schools_live_label) so the partial's
        # mega-number + suffix layout still works. Single-token input
        # is treated as the mega-number alone (label falls through to
        # the default from cockpit_manager_200x.py).
        world_overlay: dict[str, Any] = {}
        lwm_label = (cleaned.get("lwm_label") or "").strip()
        if lwm_label:
            world_overlay["eyebrow"] = lwm_label
        lwm_hero_raw = (cleaned.get("lwm_hero_value") or "").strip()
        if lwm_hero_raw:
            head, sep, tail = lwm_hero_raw.partition(" ")
            world_overlay["schools_live"] = head
            if sep and tail.strip():
                world_overlay["schools_live_label"] = tail.strip()
        lwm_regional = _parse_regional_rows(cleaned.get("lwm_regional_rows") or "")
        if lwm_regional:
            world_overlay["regional_breakdown"] = lwm_regional
        if world_overlay:
            payload.setdefault("live_world_map", {}).update(world_overlay)

        # 10) manager_200x.audit_feed
        audit_overlay: dict[str, Any] = {}
        auf_label = (cleaned.get("auf_label") or "").strip()
        if auf_label:
            audit_overlay["title"] = auf_label
        auf_events = _parse_audit_events(cleaned.get("auf_events") or "")
        if auf_events:
            audit_overlay["events"] = auf_events
        if audit_overlay:
            payload.setdefault("audit_feed", {}).update(audit_overlay)

        # v3.57.13 rich-editor overlays (5 NEW sections). Same pattern as
        # the v3.57.12 overlays above: build dict from operator inputs,
        # filter empty values so `_deep_merge` preserves defaults, then
        # `.update()` onto a `setdefault()` dict so any pre-existing keys
        # survive alongside the new content.

        # 11) manager_200x.forecast_lane
        forecast_overlay: dict[str, Any] = {}
        fcl_label = (cleaned.get("fcl_label") or "").strip()
        if fcl_label:
            forecast_overlay["label"] = fcl_label
        fcl_cards = _parse_forecast_cards(cleaned.get("fcl_cards") or "")
        if fcl_cards:
            forecast_overlay["cards"] = fcl_cards
        if forecast_overlay:
            payload.setdefault("forecast_lane", {}).update(forecast_overlay)

        # 12) manager_200x.slo_clocks
        slo_overlay: dict[str, Any] = {}
        slo_label = (cleaned.get("slo_label") or "").strip()
        if slo_label:
            slo_overlay["label"] = slo_label
        slo_clocks = _parse_slo_clocks(cleaned.get("slo_clocks_rows") or "")
        if slo_clocks:
            slo_overlay["clocks"] = slo_clocks
        if slo_overlay:
            payload.setdefault("slo_clocks", {}).update(slo_overlay)

        # 13) manager_200x.trust_nutrition
        trust_overlay: dict[str, Any] = {}
        tnt_label = (cleaned.get("tnt_label") or "").strip()
        if tnt_label:
            trust_overlay["title"] = tnt_label
        tnt_rows = _parse_trust_rows(cleaned.get("tnt_rows") or "")
        if tnt_rows:
            trust_overlay["rows"] = tnt_rows
        if trust_overlay:
            payload.setdefault("trust_nutrition", {}).update(trust_overlay)

        # 14) tenant_v3_extended.parent_teacher_thread
        thread_overlay: dict[str, Any] = {}
        ptt_label = (cleaned.get("ptt_label") or "").strip()
        if ptt_label:
            thread_overlay["title"] = ptt_label
        ptt_messages = _parse_thread_messages(cleaned.get("ptt_messages") or "")
        if ptt_messages:
            thread_overlay["messages"] = ptt_messages
        if thread_overlay:
            payload.setdefault("parent_teacher_thread", {}).update(thread_overlay)

        # 15) tenant_v3_extended.financial_timeline
        financial_overlay: dict[str, Any] = {}
        ftl_label = (cleaned.get("ftl_label") or "").strip()
        if ftl_label:
            financial_overlay["title"] = ftl_label
        ftl_balance = (cleaned.get("ftl_current_balance") or "").strip()
        if ftl_balance:
            financial_overlay["balance_display"] = ftl_balance
        ftl_events = _parse_financial_events(cleaned.get("ftl_events") or "")
        if ftl_events:
            financial_overlay["events"] = ftl_events
        if financial_overlay:
            payload.setdefault("financial_timeline", {}).update(financial_overlay)

        # v3.57.14 rich-editor overlays (6 NEW sections). Same pattern as
        # the v3.57.13 overlays above: build dict from operator inputs,
        # filter empty values so `_deep_merge` preserves defaults, then
        # `.update()` onto a `setdefault()` dict so any pre-existing keys
        # survive alongside the new content.

        # 16) manager_200x.operator_presence
        opr_overlay: dict[str, Any] = {}
        opr_label = (cleaned.get("opr_label") or "").strip()
        if opr_label:
            opr_overlay["aria_label"] = opr_label
        opr_count = cleaned.get("opr_online_count")
        if opr_count is not None and opr_count != "":
            opr_overlay["operators_online_count"] = opr_count
        opr_avatars = _parse_operator_presence_avatars(
            cleaned.get("opr_avatars") or ""
        )
        if opr_avatars:
            opr_overlay["avatars"] = opr_avatars
        if opr_overlay:
            payload.setdefault("operator_presence", {}).update(opr_overlay)

        # 17) manager_200x.operator_notebook
        opn_overlay: dict[str, Any] = {}
        opn_label = (cleaned.get("opn_label") or "").strip()
        if opn_label:
            opn_overlay["title"] = opn_label
        # ``mic_enabled`` is a BooleanField — always send the bool so the
        # operator's explicit choice (incl. unchecked=False) round-trips,
        # otherwise the helper default (True) would always win.
        opn_overlay["mic_enabled"] = bool(cleaned.get("opn_mic_enabled"))
        opn_placeholder = (cleaned.get("opn_placeholder") or "").strip()
        if opn_placeholder:
            opn_overlay["placeholder"] = opn_placeholder
        if opn_overlay:
            payload.setdefault("operator_notebook", {}).update(opn_overlay)

        # 18) manager_200x.tenant_heatmap
        heatmap_overlay: dict[str, Any] = {}
        thm_label = (cleaned.get("thm_label") or "").strip()
        if thm_label:
            heatmap_overlay["title"] = thm_label
        thm_tiles = _parse_heatmap_tiles(cleaned.get("thm_tile_rows") or "")
        if thm_tiles:
            heatmap_overlay["tiles"] = thm_tiles
        if heatmap_overlay:
            payload.setdefault("tenant_heatmap", {}).update(heatmap_overlay)

        # 19) manager_200x.revenue_waterfall — start_value/end_value map to
        # the helper's split title/title_end fields so the partial's
        # "From $X to a closing $Y" layout stays intact.
        waterfall_overlay: dict[str, Any] = {}
        rwf_label = (cleaned.get("rwf_label") or "").strip()
        if rwf_label:
            waterfall_overlay["eyebrow"] = rwf_label
        rwf_start = (cleaned.get("rwf_start_value") or "").strip()
        if rwf_start:
            waterfall_overlay["title"] = rwf_start
        rwf_end = (cleaned.get("rwf_end_value") or "").strip()
        if rwf_end:
            waterfall_overlay["title_end"] = rwf_end
        rwf_bars = _parse_waterfall_bars(cleaned.get("rwf_bars") or "")
        if rwf_bars:
            waterfall_overlay["bars"] = rwf_bars
        if waterfall_overlay:
            payload.setdefault("revenue_waterfall", {}).update(waterfall_overlay)

        # 20) tenant_v3_extended.realtime_presence
        rtp_overlay: dict[str, Any] = {}
        rtp_label = (cleaned.get("rtp_label") or "").strip()
        if rtp_label:
            rtp_overlay["title"] = rtp_label
        rtp_count = cleaned.get("rtp_classmates_online")
        if rtp_count is not None and rtp_count != "":
            rtp_overlay["online_count"] = rtp_count
        rtp_dots = _parse_realtime_presence_dots(cleaned.get("rtp_dots") or "")
        if rtp_dots:
            rtp_overlay["presence"] = rtp_dots
        if rtp_overlay:
            payload.setdefault("realtime_presence", {}).update(rtp_overlay)

        # 21) tenant_v3_extended.calendar_weather
        cwt_overlay: dict[str, Any] = {}
        cwt_label = (cleaned.get("cwt_label") or "").strip()
        if cwt_label:
            cwt_overlay["title"] = cwt_label
        cwt_days = _parse_calendar_weather_days(cleaned.get("cwt_days") or "")
        if cwt_days:
            cwt_overlay["days"] = cwt_days
        if cwt_overlay:
            payload.setdefault("calendar_weather", {}).update(cwt_overlay)

        return payload

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        payload = self._build_payload(cleaned)
        cleaned["cockpit_payload"] = payload
        # Mirror onto the model instance so save() picks it up via the
        # ModelForm machinery's normal cleaned_data -> instance flow.
        if self.instance is not None:
            self.instance.cockpit_payload = payload
        return cleaned


# Back-compat alias: a few callers prefer the more explicit name.
SiteSettingsCockpitForm = CockpitPayloadForm
