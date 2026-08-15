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

import uuid
from typing import Any

from django import forms
from django.apps import apps as django_apps
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
# v3.57.16 parsers + serializers — 5 NEW sections (final-batch wave).
# Closes 5 of the 7 remaining un-editorialized cockpit sections:
#   tenant_dashboard.workspace_context_tenant   (wct_*)
#   manager_200x.activity_ticker                (atk_*)
#   tenant_v3_extended.gradebook_trend          (gbt_*)
#   tenant_v3_extended.attendance_heatmap       (ahm_*)
#   tenant_v3_extended.life_event_timeline      (let_*)
# Sibling_compare (privacy) + ai_copilot_rail (complexity) remain honest
# deferrals. Same forgiving pipe-separated textarea contract as the
# v3.57.12 / v3.57.13 / v3.57.14 editors above.
# ---------------------------------------------------------------------------


def _parse_scope_chips(value: str) -> list[dict[str, str]]:
    """One per line: ``chip_label | chip_url`` (url optional).

    Pairs with ``cockpit.workspace_context_tenant.scope_chips`` — an
    operator-published list of scope shortcuts displayed alongside the
    child-context card. The helper module's defaults expose ``stats``
    and ``siblings`` but neither matches the {label, url} shape cleanly,
    so the editor writes a separate ``scope_chips`` list that the
    partial may render alongside the existing chips. ``_deep_merge``
    preserves the existing keys (stats/siblings/add_child) untouched.
    Rows without a label are skipped (a chip with no label is unactionable).
    """
    out: list[dict[str, str]] = []
    for line in _split_lines(value):
        parts = [p.strip() for p in line.split("|", 1)]
        label = parts[0]
        if not label:
            continue
        url = parts[1] if len(parts) > 1 else ""
        out.append({"label": label, "url": url})
    return out


def _serialize_scope_chips(items: list[dict[str, Any]] | None) -> str:
    if not items:
        return ""
    rows: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label", "")).strip()
        if not label:
            continue
        url = str(item.get("url", "")).strip()
        rows.append(f"{label} | {url}".rstrip(" |"))
    return "\n".join(rows)


def _parse_activity_ticker_cards(value: str) -> list[dict[str, str]]:
    """One per line: ``text | timestamp | icon | severity``.

    Pairs with ``cockpit.activity_ticker.cards`` whose schema is
    ``list[{text, timestamp, icon, severity}]``. The flat editor exposes
    all 4 keys. Severity is constrained to ``{ok, info, warn, danger}``;
    anything else falls back to ``info`` so a typo doesn't crash the
    CSS-class lookup. Icon is optional (single glyph or empty). Trailing
    columns are lenient. Rows without ``text`` are skipped (an empty
    headline is meaningless on a scrolling ticker).
    """
    severity_allow = {"ok", "info", "warn", "danger"}
    out: list[dict[str, str]] = []
    for line in _split_lines(value):
        parts = [p.strip() for p in line.split("|", 3)]
        text = parts[0]
        if not text:
            continue
        timestamp = parts[1] if len(parts) > 1 else ""
        icon = parts[2] if len(parts) > 2 else ""
        raw_severity = (parts[3] if len(parts) > 3 else "info").lower() or "info"
        severity = raw_severity if raw_severity in severity_allow else "info"
        out.append(
            {
                "text": text,
                "timestamp": timestamp,
                "icon": icon,
                "severity": severity,
            }
        )
    return out


def _serialize_activity_ticker_cards(
    items: list[dict[str, Any]] | None,
) -> str:
    if not items:
        return ""
    rows: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        timestamp = str(item.get("timestamp", "")).strip()
        icon = str(item.get("icon", "")).strip()
        severity = str(item.get("severity", "")).strip() or "info"
        rows.append(f"{text} | {timestamp} | {icon} | {severity}".rstrip(" |"))
    return "\n".join(rows)


def _parse_live_banner_announcements(value: str) -> list[dict[str, Any]]:
    """One per line: text | kind | severity | pin | starts_at | ends_at | audiences."""
    kind_allow = {"info", "alert", "emergency"}
    severity_allow = {"ok", "info", "warn", "danger"}
    out: list[dict[str, Any]] = []
    for line in _split_lines(value):
        parts = [p.strip() for p in line.split("|", 6)]
        text = parts[0]
        if not text:
            continue
        kind = (parts[1] if len(parts) > 1 else "info").lower() or "info"
        if kind not in kind_allow:
            kind = "info"
        raw_severity = (parts[2] if len(parts) > 2 else "").lower()
        severity = raw_severity if raw_severity in severity_allow else ""
        pin_raw = (parts[3] if len(parts) > 3 else "").lower()
        pin = pin_raw in {"1", "yes", "true", "y", "pin"}
        starts_at = parts[4] if len(parts) > 4 else ""
        ends_at = parts[5] if len(parts) > 5 else ""
        audiences_raw = parts[6] if len(parts) > 6 else "all"
        audiences = [
            item.strip().lower()
            for item in audiences_raw.split(",")
            if item.strip()
        ] or ["all"]
        row: dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "text": text,
            "kind": kind,
            "pin": pin,
            "audiences": audiences,
        }
        if severity:
            row["severity"] = severity
        if starts_at:
            row["starts_at"] = starts_at
        if ends_at:
            row["ends_at"] = ends_at
        out.append(row)
    return out


def _serialize_live_banner_announcements(
    items: list[dict[str, Any]] | None,
) -> str:
    if not items:
        return ""
    rows: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        kind = str(item.get("kind", "info")).strip() or "info"
        severity = str(item.get("severity", "")).strip()
        pin = "yes" if item.get("pin") else "no"
        starts_at = str(item.get("starts_at", "")).strip()
        ends_at = str(item.get("ends_at", "")).strip()
        audiences = item.get("audiences") or ["all"]
        if isinstance(audiences, (list, tuple)):
            audience_text = ",".join(str(a).strip() for a in audiences if str(a).strip())
        else:
            audience_text = str(audiences).strip()
        rows.append(
            f"{text} | {kind} | {severity} | {pin} | {starts_at} | {ends_at} | {audience_text or 'all'}"
        )
    return "\n".join(rows)


def _parse_gradebook_subjects(value: str) -> list[dict[str, str]]:
    """One per line: ``subject_name | current_grade | trend_direction | sparkline_csv``.

    Pairs with ``cockpit.gradebook_trend.subjects`` whose schema is
    ``list[{subject, current_value, delta_text, delta_tone, spark_points}]``.
    The flat editor maps:
        subject_name      -> subject
        current_grade     -> current_value
        trend_direction   -> delta_tone (constrained; ∈ {up, flat, down}
                             — anything else falls back to 'flat'; the
                             value is also echoed under ``trend_direction``
                             so partials that read either key are honored)
        sparkline_csv     -> spark_points (composed as "0,Y0 1,Y1 …" with
                             integer x indices; the raw CSV is also
                             persisted under ``sparkline_csv`` for clean
                             round-trip)
    Comma-separated CSV is forgiving: non-numeric tokens are skipped. A
    subject with no name is skipped. ``delta_text`` is left empty so the
    section defaults flow through cleanly.
    """
    trend_allow = {"up", "flat", "down"}
    out: list[dict[str, str]] = []
    for line in _split_lines(value):
        parts = [p.strip() for p in line.split("|", 3)]
        subject_name = parts[0]
        if not subject_name:
            continue
        current_grade = parts[1] if len(parts) > 1 else ""
        raw_trend = (parts[2] if len(parts) > 2 else "flat").lower() or "flat"
        trend = raw_trend if raw_trend in trend_allow else "flat"
        sparkline_csv = parts[3] if len(parts) > 3 else ""
        # Compose spark_points from comma-separated numbers — non-numeric
        # tokens are skipped silently rather than crashing the polyline.
        point_tokens: list[str] = []
        for idx, raw_token in enumerate(sparkline_csv.split(",")):
            token = raw_token.strip()
            if not token:
                continue
            try:
                # Accept ints or floats; preserve operator formatting via str().
                float(token)
            except ValueError:
                continue
            point_tokens.append(f"{idx},{token}")
        spark_points = " ".join(point_tokens)
        out.append(
            {
                "subject": subject_name,
                "current_value": current_grade,
                "delta_text": "",
                "delta_tone": trend,
                "trend_direction": trend,
                "spark_points": spark_points,
                "sparkline_csv": sparkline_csv,
            }
        )
    return out


def _serialize_gradebook_subjects(
    items: list[dict[str, Any]] | None,
) -> str:
    if not items:
        return ""
    rows: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        subject_name = str(item.get("subject", "")).strip()
        if not subject_name:
            continue
        current_grade = str(item.get("current_value", "")).strip()
        # Prefer the explicit ``trend_direction`` key (round-trip from
        # this editor); fall back to ``delta_tone`` for payloads that
        # pre-date the v3.57.16 wave.
        trend = (
            str(item.get("trend_direction", "")).strip().lower()
            or str(item.get("delta_tone", "")).strip().lower()
            or "flat"
        )
        # Prefer the explicit ``sparkline_csv`` key for round-trip; fall
        # back to deriving CSV from ``spark_points`` (strip x-coords).
        sparkline_csv = str(item.get("sparkline_csv", "")).strip()
        if not sparkline_csv:
            spark_points = str(item.get("spark_points", "")).strip()
            if spark_points:
                csv_tokens: list[str] = []
                for pair in spark_points.split():
                    if "," in pair:
                        _, _, y = pair.partition(",")
                        if y.strip():
                            csv_tokens.append(y.strip())
                sparkline_csv = ",".join(csv_tokens)
        rows.append(
            f"{subject_name} | {current_grade} | {trend} | {sparkline_csv}".rstrip(" |")
        )
    return "\n".join(rows)


def _parse_attendance_pattern(value: str) -> list[dict[str, Any]]:
    """One per line: ``day_iso | status``.

    Pairs with ``cockpit.attendance_heatmap.cells`` whose schema is
    ``list[{day, tone, tooltip, is_today: bool}]``. The flat editor maps:
        day_iso  -> day (zero-stripped day-of-month extracted from input)
                 -> ``iso`` key persisted verbatim for round-trip
        status   -> tone (constrained ∈ {present, absent, late, holiday};
                    holiday maps to the partial's 'weekend' tone since
                    the rendering enum is {present, absent, late, excused,
                    weekend, ""}; anything else falls back to "")
    ``day_iso`` is forgiving: ``YYYY-MM-DD`` / ``MM-DD`` / a bare numeric
    day all work. Rows without a date are skipped. ``tooltip`` is left
    empty so the section default flows through cleanly; ``is_today`` is
    False (runtime layers flip it).
    """
    status_allow = {"present", "absent", "late", "holiday"}
    # Map operator-friendly status -> rendering-partial tone vocabulary.
    status_to_tone = {
        "present": "present",
        "absent": "absent",
        "late": "late",
        "holiday": "weekend",
    }
    out: list[dict[str, Any]] = []
    for line in _split_lines(value):
        parts = [p.strip() for p in line.split("|", 1)]
        raw_date = parts[0]
        if not raw_date:
            continue
        raw_status = (parts[1] if len(parts) > 1 else "").lower()
        status = raw_status if raw_status in status_allow else ""
        tone = status_to_tone.get(status, "")
        # Extract day-of-month from a YYYY-MM-DD / MM-DD / bare-day input.
        day_str = ""
        bits = [b.strip() for b in raw_date.replace("/", "-").split("-")]
        try:
            if len(bits) == 3:
                day_str = str(int(bits[2]))
            elif len(bits) == 2:
                day_str = str(int(bits[1]))
            elif len(bits) == 1:
                day_str = str(int(bits[0]))
        except (ValueError, TypeError):
            day_str = ""
        out.append(
            {
                "day": day_str,
                "iso": raw_date,
                "tone": tone,
                "status": status,
                "tooltip": "",
                "is_today": False,
            }
        )
    return out


def _serialize_attendance_pattern(
    items: list[dict[str, Any]] | None,
) -> str:
    if not items:
        return ""
    # Reverse-map partial tone vocabulary back to operator-friendly status
    # when ``status`` is missing (pre-v3.57.16 payloads).
    tone_to_status = {
        "present": "present",
        "absent": "absent",
        "late": "late",
        "weekend": "holiday",
    }
    rows: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        # Prefer explicit ``iso`` from this editor; fall back to ``day``
        # (bare day-of-month) for payloads that pre-date the v3.57.16 wave.
        date_label = str(item.get("iso", "")).strip() or str(
            item.get("day", "")
        ).strip()
        if not date_label:
            continue
        status = str(item.get("status", "")).strip().lower()
        if not status:
            tone = str(item.get("tone", "")).strip().lower()
            status = tone_to_status.get(tone, "")
        rows.append(f"{date_label} | {status}".rstrip(" |"))
    return "\n".join(rows)


def _parse_life_events(value: str) -> list[dict[str, str]]:
    """One per line: ``date | category | title | description``.

    Pairs with ``cockpit.life_event_timeline.events`` whose schema is
    ``list[{iso, day_label, icon, title, sub, tone}]``. The flat editor
    maps:
        date         -> iso + day_label (derived "DD Mon" abbreviation
                        when iso parses as YYYY-MM-DD / MM-DD; else
                        echoed raw input)
        category     -> tone (constrained ∈ {milestone, achievement,
                        transition, certificate}; anything else falls
                        back to "milestone")
        title        -> title
        description  -> sub (optional)
    Description column is optional (lenient). Rows without a title are
    skipped (an unnamed life event is meaningless). ``icon`` is left
    empty so the section defaults flow through.
    """
    category_allow = {"milestone", "achievement", "transition", "certificate"}
    month_abbr = (
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    )
    out: list[dict[str, str]] = []
    for line in _split_lines(value):
        parts = [p.strip() for p in line.split("|", 3)]
        raw_date = parts[0] if len(parts) > 0 else ""
        raw_category = (parts[1] if len(parts) > 1 else "milestone").lower() or "milestone"
        category = raw_category if raw_category in category_allow else "milestone"
        title = parts[2] if len(parts) > 2 else ""
        description = parts[3] if len(parts) > 3 else ""
        if not title:
            continue
        # Derive a "DD Mon" day_label when the date parses; otherwise
        # echo the operator's raw input into day_label so nothing vanishes.
        day_label = raw_date
        bits = [b.strip() for b in raw_date.replace("/", "-").split("-")]
        try:
            if len(bits) == 3:
                month_num = int(bits[1])
                day_num = int(bits[2])
                if 1 <= month_num <= 12 and 1 <= day_num <= 31:
                    day_label = f"{day_num} {month_abbr[month_num - 1]}"
            elif len(bits) == 2:
                month_num = int(bits[0])
                day_num = int(bits[1])
                if 1 <= month_num <= 12 and 1 <= day_num <= 31:
                    day_label = f"{day_num} {month_abbr[month_num - 1]}"
        except (ValueError, TypeError):
            # Non-numeric — keep raw_date as day_label.
            pass
        out.append(
            {
                "iso": raw_date,
                "day_label": day_label,
                "icon": "",
                "title": title,
                "sub": description,
                "tone": category,
                "category": category,
            }
        )
    return out


def _serialize_life_events(items: list[dict[str, Any]] | None) -> str:
    if not items:
        return ""
    rows: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        if not title:
            continue
        # Prefer explicit ``iso``; fall back to ``day_label`` for payloads
        # that pre-date the v3.57.16 wave.
        raw_date = str(item.get("iso", "")).strip() or str(
            item.get("day_label", "")
        ).strip()
        # Prefer explicit ``category`` from this editor; fall back to
        # ``tone`` for pre-existing payloads.
        category = (
            str(item.get("category", "")).strip().lower()
            or str(item.get("tone", "")).strip().lower()
            or "milestone"
        )
        description = str(item.get("sub", "")).strip()
        rows.append(
            f"{raw_date} | {category} | {title} | {description}".rstrip(" |")
        )
    return "\n".join(rows)


# ---------------------------------------------------------------------------
# v3.57.17 parsers + serializers — final cockpit editor: AI Copilot rail
# (manager_200x.ai_copilot_rail). Multi-block textarea pattern: messages +
# suggestion pills. Closes the last complex-schema deferral; only
# sibling_compare (privacy-gated; deliberately code-only) remains
# un-editorialised by design.
#
# Operator-facing vocab uses ``assistant`` / ``user`` for messages; we
# translate ``assistant → ai`` on write because the rendering partial
# (templates/partials/cockpit/_ai_copilot_rail.html) reads ``msg.role``
# as a CSS modifier and the helper defaults + partial defaults treat
# the AI-side role as ``ai``. Keeping the operator vocab familiar while
# emitting the partial's expected token is the most charitable round-trip.
# ---------------------------------------------------------------------------


# Operator-facing role vocab -> persisted role token (partial CSS modifier).
# Anything outside {assistant, user} falls back to ``assistant`` per spec.
_COPILOT_ROLE_TO_PARTIAL: dict[str, str] = {
    "assistant": "ai",
    "user": "user",
}


def _parse_copilot_messages(value: str) -> list[dict[str, str]]:
    """One per line: ``role | body`` — role ∈ {assistant, user}.

    Pairs with ``cockpit.ai_copilot_rail.messages`` whose schema is
    ``list[{role, text, em_text}]``. The flat editor maps:
        role  -> role (enum-whitelisted to {assistant, user}; anything
                 else falls back to 'assistant'. Persisted token is
                 translated 'assistant' -> 'ai' so the rendering
                 partial's CSS modifier (lx-copilot__msg--ai) lights up.)
        body  -> text
    Rows without a body are skipped (an empty bubble helps nobody).
    ``em_text`` is left blank — the section default flows through cleanly
    via ``_deep_merge`` in cockpit_context.py; operators who need italic
    serif tails on individual messages can edit JSON directly.
    """
    out: list[dict[str, str]] = []
    for line in _split_lines(value):
        parts = [p.strip() for p in line.split("|", 1)]
        raw_role = (parts[0] if len(parts) > 0 else "assistant").lower() or "assistant"
        # Enum whitelist — anything outside {assistant, user} falls back
        # to 'assistant' per spec.
        operator_role = raw_role if raw_role in _COPILOT_ROLE_TO_PARTIAL else "assistant"
        body = parts[1] if len(parts) > 1 else ""
        if not body:
            continue
        out.append(
            {
                "role": _COPILOT_ROLE_TO_PARTIAL[operator_role],
                "text": body,
                "em_text": "",
            }
        )
    return out


def _serialize_copilot_messages(items: list[dict[str, Any]] | None) -> str:
    if not items:
        return ""
    # Reverse-map persisted role token back to operator-facing vocab so the
    # textarea round-trips cleanly. Pre-v3.57.17 payloads that already use
    # 'ai' or 'user' map straight back to 'assistant'/'user'.
    partial_to_operator = {v: k for k, v in _COPILOT_ROLE_TO_PARTIAL.items()}
    rows: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        body = str(item.get("text", "")).strip()
        if not body:
            continue
        partial_role = str(item.get("role", "")).strip().lower() or "ai"
        operator_role = partial_to_operator.get(partial_role, "assistant")
        rows.append(f"{operator_role} | {body}".rstrip(" |"))
    return "\n".join(rows)


def _parse_copilot_suggestions(value: str) -> list[str]:
    """One per line: ``label | command`` — command optional and discarded.

    Pairs with ``cockpit.ai_copilot_rail.suggested_actions`` whose schema
    is ``list[str]`` — the rendering partial iterates and emits the bare
    string. The flat editor accepts an optional ``command`` column for
    operator forward-compat (e.g. a future ``data-rmc-copilot-cmd`` hook)
    but discards it on write because storing dicts would break the
    partial. Rows without a label are skipped (a chip with no label is
    unactionable).
    """
    out: list[str] = []
    for line in _split_lines(value):
        parts = [p.strip() for p in line.split("|", 1)]
        label = parts[0]
        if not label:
            continue
        # parts[1] (command) is intentionally discarded — partial reads
        # bare strings; persisting a dict here would crash the {{ action }}
        # render.
        out.append(label)
    return out


def _serialize_copilot_suggestions(items: list[Any] | None) -> str:
    if not items:
        return ""
    rows: list[str] = []
    for item in items:
        # Support both bare-string (post-v3.57.17 writes) and dict (forward-
        # compat / hand-edited JSON) shapes so the textarea round-trips
        # cleanly either way.
        if isinstance(item, dict):
            label = str(item.get("label", "")).strip()
        else:
            label = str(item).strip()
        if not label:
            continue
        rows.append(label)
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


# ---------------------------------------------------------------------------
# v3.57.18 Wave 8 — public school-signup form trust-pill parser/serializer.
# ---------------------------------------------------------------------------


def _parse_trust_pill_lines(value: str) -> list[dict[str, str]]:
    """One per line: ``icon | label`` — icon defaults to ✓ when omitted.

    Pairs with ``cockpit.signup_form.trust_pill_lines`` whose schema is
    ``list[{icon, label}]``. Lenient: lines missing the pipe are treated
    as label-only (icon defaults to "✓"). Rows whose label resolves to
    empty after stripping are skipped.
    """
    out: list[dict[str, str]] = []
    for line in _split_lines(value):
        parts = [p.strip() for p in line.split("|", 1)]
        if len(parts) == 1:
            icon = "✓"
            label = parts[0]
        else:
            icon = parts[0] or "✓"
            label = parts[1]
        if not label:
            continue
        out.append({"icon": icon, "label": label})
    return out


def _serialize_trust_pill_lines(items: list[dict[str, Any]] | None) -> str:
    if not items:
        return ""
    rows: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label", "")).strip()
        if not label:
            continue
        icon = str(item.get("icon", "")).strip() or "✓"
        rows.append(f"{icon} | {label}")
    return "\n".join(rows)


def _parse_lic_hero_slides(value: str) -> list[dict[str, str]]:
    """One per line: ``eyebrow | title | body | role_hint``."""
    out: list[dict[str, str]] = []
    for line in _split_lines(value):
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 2:
            continue
        title = parts[1] if len(parts) > 1 else ""
        if not title:
            continue
        slide: dict[str, str] = {
            "eyebrow": parts[0] if len(parts) > 0 else "",
            "title": title,
            "body": parts[2] if len(parts) > 2 else "",
            "role_hint": (parts[3] if len(parts) > 3 else "").lower(),
        }
        if len(parts) > 4 and parts[4].strip():
            slide["publish_start_iso"] = parts[4].strip()
        if len(parts) > 5 and parts[5].strip():
            slide["publish_end_iso"] = parts[5].strip()
        out.append(slide)
    return out


def _serialize_lic_hero_slides(items: list[dict[str, Any]] | None) -> str:
    if not items:
        return ""
    rows: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        eyebrow = str(item.get("eyebrow") or "").strip()
        body = str(item.get("body") or "").strip()
        role_hint = str(item.get("role_hint") or "").strip()
        row_parts = [eyebrow, title]
        if body:
            row_parts.append(body)
        if role_hint:
            row_parts.append(role_hint)
        rows.append(" | ".join(row_parts))
    return "\n".join(rows)


def _parse_lic_trust_chip_lines(value: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for line in _split_lines(value):
        label = line.strip()
        if label:
            out.append({"icon": "", "label": label})
    return out


def _serialize_lic_trust_chip_lines(items: list[dict[str, Any]] | None) -> str:
    if not items:
        return ""
    rows: list[str] = []
    for item in items:
        if isinstance(item, str) and item.strip():
            rows.append(item.strip())
        elif isinstance(item, dict):
            label = str(item.get("label") or "").strip()
            if label:
                rows.append(label)
    return "\n".join(rows)


def _parse_lic_gallery_lines(value: str) -> list[dict[str, str]]:
    """One per line: ``url | caption | alt | link_url``."""
    out: list[dict[str, str]] = []
    for line in _split_lines(value):
        parts = [p.strip() for p in line.split("|")]
        if not parts or not parts[0]:
            continue
        out.append(
            {
                "url": parts[0],
                "caption": parts[1] if len(parts) > 1 else "",
                "alt": parts[2] if len(parts) > 2 else parts[1] if len(parts) > 1 else "",
                "link_url": parts[3] if len(parts) > 3 else "",
            }
        )
    return out


def _serialize_lic_gallery_lines(items: list[dict[str, Any]] | None) -> str:
    if not items:
        return ""
    rows: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or item.get("image_url") or "").strip()
        if not url:
            continue
        caption = str(item.get("caption") or "").strip()
        alt = str(item.get("alt") or "").strip()
        link = str(item.get("link_url") or "").strip()
        row = " | ".join(p for p in (url, caption, alt, link) if p)
        rows.append(row)
    return "\n".join(rows)


def _parse_lic_sponsored_lines(value: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for line in _split_lines(value):
        parts = [p.strip() for p in line.split("|")]
        title = parts[1] if len(parts) > 1 else (parts[0] if parts else "")
        if not title:
            continue
        out.append(
            {
                "eyebrow": parts[0] if len(parts) > 1 else "",
                "title": title,
                "body": parts[2] if len(parts) > 2 else "",
                "cta_label": parts[3] if len(parts) > 3 else "",
                "cta_url": parts[4] if len(parts) > 4 else "",
                "sponsored": True,
            }
        )
    return out


def _serialize_lic_sponsored_lines(items: list[dict[str, Any]] | None) -> str:
    if not items:
        return ""
    rows: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or item.get("label") or "").strip()
        if not title:
            continue
        eyebrow = str(item.get("eyebrow") or "").strip()
        body = str(item.get("body") or "").strip()
        cta_label = str(item.get("cta_label") or "").strip()
        cta_url = str(item.get("cta_url") or "").strip()
        row_parts = [p for p in (eyebrow, title, body, cta_label, cta_url) if p]
        rows.append(" | ".join(row_parts))
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


def build_tenant_experience_policy_from_cleaned(cleaned: dict[str, Any]) -> dict[str, Any]:
    """Build ``tenant_experience_policy`` storage dict from flat ``txp_*`` keys."""
    from apps.siteconfig.tenant_experience_presets import detect_matching_preset

    policy = {
        "use_v3_shell": bool(cleaned.get("txp_use_v3_shell", True)),
        "show_mission_strip": bool(cleaned.get("txp_show_mission_strip", True)),
        "hide_mission_strip_after_launch": bool(
            cleaned.get("txp_hide_mission_strip_after_launch")
        ),
        "show_experience_command_strip": bool(
            cleaned.get("txp_show_experience_command_strip", True)
        ),
        "show_security_posture_inline": bool(
            cleaned.get("txp_show_security_posture_inline")
        ),
        "show_mfa_nudge": bool(cleaned.get("txp_show_mfa_nudge")),
        "show_legacy_explain_strip": bool(cleaned.get("txp_show_legacy_explain_strip")),
        "show_next_action_strip": bool(cleaned.get("txp_show_next_action_strip")),
        "show_community_band_on_v3": bool(cleaned.get("txp_show_community_band_on_v3")),
        "show_newsletter_band_on_v3": bool(
            cleaned.get("txp_show_newsletter_band_on_v3")
        ),
        "show_proactive_help_nudge": bool(cleaned.get("txp_show_proactive_help_nudge")),
        "show_lifecycle_concierge": bool(cleaned.get("txp_show_lifecycle_concierge")),
        "show_kb_ai_panel": bool(cleaned.get("txp_show_kb_ai_panel")),
        "show_legacy_ai_copilot_dock": bool(
            cleaned.get("txp_show_legacy_ai_copilot_dock")
        ),
        "ai_layer_strip_mode": (cleaned.get("txp_ai_layer_strip_mode") or "inherit"),
        "ai_copilot_rail_mode": (cleaned.get("txp_ai_copilot_rail_mode") or "inherit"),
        "sidebar_default_width": cleaned.get("txp_sidebar_default_width") or 280,
        "sidebar_min_width": cleaned.get("txp_sidebar_min_width") or 200,
        "sidebar_max_width": cleaned.get("txp_sidebar_max_width") or 420,
        "sidebar_rail_width": cleaned.get("txp_sidebar_rail_width") or 44,
        "mission_eyebrow": (cleaned.get("txp_mission_eyebrow") or "").strip(),
        "mission_cta_label": (cleaned.get("txp_mission_cta_label") or "").strip(),
        "experience_score_label": (
            cleaned.get("txp_experience_score_label") or ""
        ).strip(),
        "setup_surface_enabled": bool(cleaned.get("txp_setup_surface_enabled", True)),
        "hidden_setup_wizard_keys": [
            part.strip()
            for part in str(cleaned.get("txp_hidden_setup_wizard_keys") or "").split(",")
            if part.strip()
        ],
        "show_first_run_zero_state_on_v3": bool(
            cleaned.get("txp_show_first_run_zero_state_on_v3")
        ),
        "show_smart_action_hub_on_v3": bool(
            cleaned.get("txp_show_smart_action_hub_on_v3")
        ),
        "show_portal_chathead_on_v3": bool(
            cleaned.get("txp_show_portal_chathead_on_v3")
        ),
        "show_header_home_link_on_v3": bool(
            cleaned.get("txp_show_header_home_link_on_v3")
        ),
        "show_workspace_os_header_on_v3": bool(
            cleaned.get("txp_show_workspace_os_header_on_v3")
        ),
        "show_operator_console_strip_on_v3": bool(
            cleaned.get("txp_show_operator_console_strip_on_v3")
        ),
        "show_os_status_strip_on_v3": bool(
            cleaned.get("txp_show_os_status_strip_on_v3")
        ),
        "show_zero_click_command_strip_on_v3": bool(
            cleaned.get("txp_show_zero_click_command_strip_on_v3")
        ),
        "show_dashboard_stats_cards_on_v3": bool(
            cleaned.get("txp_show_dashboard_stats_cards_on_v3")
        ),
        "show_legacy_sidebar_user_header_on_v3": bool(
            cleaned.get("txp_show_legacy_sidebar_user_header_on_v3")
        ),
        "experience_preset": (cleaned.get("txp_experience_preset") or "custom").strip()
        or "custom",
        "role_home_experience_mode": (
            cleaned.get("txp_role_home_experience_mode") or "v3_canvas"
        ),
        "experience_score_profile_weight": cleaned.get("txp_experience_score_profile_weight")
        or 50,
        "experience_score_school_weight": cleaned.get("txp_experience_score_school_weight")
        or 50,
        "experience_score_ready_threshold": cleaned.get(
            "txp_experience_score_ready_threshold"
        )
        or 75,
        "experience_score_attention_threshold": cleaned.get(
            "txp_experience_score_attention_threshold"
        )
        or 50,
        "experience_score_country_bonus": cleaned.get("txp_experience_score_country_bonus")
        or 0,
        "role_experience_presets": {
            bucket: (cleaned.get(f"txp_role_preset_{bucket}") or "inherit").strip().lower()
            for bucket in ("ADMIN", "TEACHER", "PARENT", "STUDENT")
        },
    }
    preset = str(policy.get("experience_preset") or "custom").strip().lower()
    if preset == "custom":
        policy["experience_preset"] = detect_matching_preset(policy)
    return policy


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

    # ---- Tenant experience policy (cockpit.tenant_experience_policy.*) ----
    txp_experience_preset = forms.ChoiceField(
        required=False,
        choices=(),
        widget=forms.Select(attrs={"class": "form-select"}),
        label=_("Experience preset"),
        initial="custom",
        help_text=_("Shopify-style bundles; pick Custom to tune individual toggles."),
    )
    txp_role_home_experience_mode = forms.ChoiceField(
        required=False,
        choices=(),
        widget=forms.Select(attrs={"class": "form-select"}),
        label=_("Role-home experience mode"),
        initial="v3_canvas",
        help_text=_(
            "Persisted one-click mode for role-home landings (replaces ?simple=1 bookmarks)."
        ),
    )
    txp_role_preset_ADMIN = forms.ChoiceField(
        required=False,
        choices=(),
        widget=forms.Select(attrs={"class": "form-select"}),
        label=_("Admin / operator theme"),
        initial="inherit",
        help_text=_("Per-role Shopify theme; inherits school default when set to Inherit."),
    )
    txp_role_preset_TEACHER = forms.ChoiceField(
        required=False,
        choices=(),
        widget=forms.Select(attrs={"class": "form-select"}),
        label=_("Teacher theme"),
        initial="inherit",
    )
    txp_role_preset_PARENT = forms.ChoiceField(
        required=False,
        choices=(),
        widget=forms.Select(attrs={"class": "form-select"}),
        label=_("Parent theme"),
        initial="inherit",
    )
    txp_role_preset_STUDENT = forms.ChoiceField(
        required=False,
        choices=(),
        widget=forms.Select(attrs={"class": "form-select"}),
        label=_("Student theme"),
        initial="inherit",
    )
    txp_use_v3_shell = forms.BooleanField(
        required=False,
        initial=True,
        widget=_CHECK,
        label=_("Use v3 tenant shell canvas"),
        help_text=_("When off, the school uses the legacy portal chrome on all pages."),
    )
    txp_show_mission_strip = forms.BooleanField(
        required=False,
        initial=True,
        widget=_CHECK,
        label=_("Show mission strip (v3)"),
    )
    txp_hide_mission_strip_after_launch = forms.BooleanField(
        required=False,
        widget=_CHECK,
        label=_("Hide mission strip after go-live"),
    )
    txp_show_experience_command_strip = forms.BooleanField(
        required=False,
        initial=True,
        widget=_CHECK,
        label=_("Show experience command strip on role homes"),
    )
    txp_show_security_posture_inline = forms.BooleanField(
        required=False,
        widget=_CHECK,
        label=_("Show security posture banner on v3"),
    )
    txp_show_mfa_nudge = forms.BooleanField(
        required=False,
        widget=_CHECK,
        label=_("Show MFA enrollment nudge on v3"),
    )
    txp_show_legacy_explain_strip = forms.BooleanField(
        required=False,
        widget=_CHECK,
        label=_("Show page explain strip on v3"),
    )
    txp_show_next_action_strip = forms.BooleanField(
        required=False,
        widget=_CHECK,
        label=_("Show next-action strip on v3"),
    )
    txp_show_community_band_on_v3 = forms.BooleanField(
        required=False,
        widget=_CHECK,
        label=_("Show community band on v3"),
    )
    txp_show_newsletter_band_on_v3 = forms.BooleanField(
        required=False,
        widget=_CHECK,
        label=_("Show newsletter band on v3"),
    )
    txp_show_proactive_help_nudge = forms.BooleanField(
        required=False,
        widget=_CHECK,
        label=_("Show proactive help nudge on v3"),
    )
    txp_show_lifecycle_concierge = forms.BooleanField(
        required=False,
        widget=_CHECK,
        label=_("Show lifecycle concierge on v3"),
    )
    txp_show_kb_ai_panel = forms.BooleanField(
        required=False,
        widget=_CHECK,
        label=_("Show KB AI assistant panel on v3"),
    )
    txp_show_legacy_ai_copilot_dock = forms.BooleanField(
        required=False,
        widget=_CHECK,
        label=_("Show legacy floating AI copilot dock on v3"),
    )
    txp_ai_layer_strip_mode = forms.ChoiceField(
        required=False,
        choices=(),
        widget=forms.Select(attrs={"class": "form-select"}),
        label=_("AI system layer strip"),
        initial="inherit",
    )
    txp_ai_copilot_rail_mode = forms.ChoiceField(
        required=False,
        choices=(),
        widget=forms.Select(attrs={"class": "form-select"}),
        label=_("AI copilot rail"),
        initial="inherit",
    )
    txp_sidebar_default_width = forms.IntegerField(
        required=False,
        initial=280,
        min_value=200,
        max_value=420,
        widget=_NUMBER,
        label=_("Sidebar default width (px)"),
    )
    txp_sidebar_min_width = forms.IntegerField(
        required=False,
        initial=200,
        min_value=200,
        max_value=420,
        widget=_NUMBER,
        label=_("Sidebar minimum width (px)"),
    )
    txp_sidebar_max_width = forms.IntegerField(
        required=False,
        initial=420,
        min_value=200,
        max_value=420,
        widget=_NUMBER,
        label=_("Sidebar maximum width (px)"),
    )
    txp_mission_eyebrow = forms.CharField(
        required=False,
        widget=_TEXT,
        label=_("Mission strip eyebrow override"),
    )
    txp_mission_cta_label = forms.CharField(
        required=False,
        widget=_TEXT,
        label=_("Mission strip CTA label override"),
    )
    txp_experience_score_label = forms.CharField(
        required=False,
        widget=_TEXT,
        label=_("Experience score label override"),
    )
    txp_experience_score_profile_weight = forms.IntegerField(
        required=False,
        initial=50,
        min_value=0,
        max_value=100,
        widget=_NUMBER,
        label=_("Score weight: profile (%)"),
    )
    txp_experience_score_school_weight = forms.IntegerField(
        required=False,
        initial=50,
        min_value=0,
        max_value=100,
        widget=_NUMBER,
        label=_("Score weight: school setup (%)"),
    )
    txp_experience_score_ready_threshold = forms.IntegerField(
        required=False,
        initial=75,
        min_value=0,
        max_value=100,
        widget=_NUMBER,
        label=_("Ready threshold (%)"),
    )
    txp_experience_score_attention_threshold = forms.IntegerField(
        required=False,
        initial=50,
        min_value=0,
        max_value=100,
        widget=_NUMBER,
        label=_("Needs-attention threshold (%)"),
    )
    txp_experience_score_country_bonus = forms.IntegerField(
        required=False,
        initial=0,
        min_value=0,
        max_value=25,
        widget=_NUMBER,
        label=_("Country baseline bonus (points)"),
        help_text=_(
            "Adds to school setup score when ISO country rails are configured (250-country matrix)."
        ),
    )
    txp_setup_surface_enabled = forms.BooleanField(
        required=False,
        initial=True,
        widget=_CHECK,
        label=_("Show setup command surface during onboarding"),
    )
    txp_hidden_setup_wizard_keys = forms.CharField(
        required=False,
        widget=_TEXTAREA_SMALL,
        label=_("Hidden setup wizard keys"),
        help_text=_("Comma-separated wizard or stage keys to hide from onboarding."),
    )
    txp_show_first_run_zero_state_on_v3 = forms.BooleanField(
        required=False,
        widget=_CHECK,
        label=_("Show first-run zero state on v3"),
    )
    txp_show_smart_action_hub_on_v3 = forms.BooleanField(
        required=False,
        widget=_CHECK,
        label=_("Show smart action hub on v3"),
    )
    txp_show_portal_chathead_on_v3 = forms.BooleanField(
        required=False,
        widget=_CHECK,
        label=_("Show floating messages chathead on v3"),
    )
    txp_show_header_home_link_on_v3 = forms.BooleanField(
        required=False,
        widget=_CHECK,
        label=_("Show header Home link on v3"),
    )
    txp_show_workspace_os_header_on_v3 = forms.BooleanField(
        required=False,
        widget=_CHECK,
        label=_("Show workspace OS page header on v3"),
    )
    txp_show_operator_console_strip_on_v3 = forms.BooleanField(
        required=False,
        widget=_CHECK,
        label=_("Show operator console strip on v3"),
    )
    txp_show_os_status_strip_on_v3 = forms.BooleanField(
        required=False,
        widget=_CHECK,
        label=_("Show OS status strip on v3"),
    )
    txp_show_zero_click_command_strip_on_v3 = forms.BooleanField(
        required=False,
        widget=_CHECK,
        label=_("Show zero-click command strip on v3"),
    )
    txp_show_dashboard_stats_cards_on_v3 = forms.BooleanField(
        required=False,
        widget=_CHECK,
        label=_("Show dashboard stats cards on v3"),
    )
    txp_show_legacy_sidebar_user_header_on_v3 = forms.BooleanField(
        required=False,
        widget=_CHECK,
        label=_("Show legacy sidebar user header on v3"),
    )
    txp_sidebar_rail_width = forms.IntegerField(
        required=False,
        initial=44,
        min_value=36,
        max_value=72,
        widget=_NUMBER,
        label=_("Sidebar collapsed rail width (px)"),
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
    lwm_globe_auto_rotate = forms.BooleanField(
        required=False,
        widget=_CHECK,
        label=_("Live world map: globe auto-rotate"),
        help_text=_(
            "When enabled, the 3D globe slowly spins until the operator interacts. "
            "Honours prefers-reduced-motion in the browser."
        ),
        initial=True,
    )
    lwm_layout = forms.ChoiceField(
        required=False,
        choices=(("hero", _("Hero (full-width globe)")), ("side", _("Side-by-side"))),
        widget=forms.Select,
        label=_("Live world map: layout"),
        help_text=_("Hero layout floats the legend over the globe for maximum map presence."),
        initial="hero",
    )
    lwm_tour_enabled = forms.BooleanField(
        required=False,
        widget=_CHECK,
        label=_("Live world map: region tour"),
        help_text=_("Enable the auto-tour and Tour/Stop controls on the globe panel."),
        initial=True,
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

    # ---- v3.57.16 Rich editors (5 NEW sections — final batch) ---------
    # Closes 5 of the 7 remaining un-editorialized cockpit sections:
    # workspace_context_tenant / activity_ticker / gradebook_trend /
    # attendance_heatmap / life_event_timeline. Sibling_compare (privacy)
    # and ai_copilot_rail (complexity) remain honest deferrals. Same
    # forgiving parser contract: empty/malformed rows skipped;
    # operator-supplied empties filtered from the overlay before
    # `.update()` so `_deep_merge` preserves defaults from the helper
    # modules.

    # 22) tenant_dashboard.workspace_context_tenant
    wct_label = forms.CharField(
        required=False,
        widget=_TEXT,
        label=_("Workspace context (tenant): label"),
        help_text=_(
            "Header label shown above the child-context card "
            "(e.g. 'Active child'). Maps to "
            "cockpit.workspace_context_tenant.label."
        ),
    )
    wct_school_role = forms.CharField(
        required=False,
        max_length=160,
        widget=_TEXT,
        label=_("Workspace context (tenant): school role"),
        help_text=_(
            "Role + school subline shown under the active-child name "
            "(e.g. 'Parent · Acme Academy'). Maps to "
            "cockpit.workspace_context_tenant.child.subline."
        ),
    )
    wct_scope_chips = forms.CharField(
        required=False,
        widget=_TEXTAREA_MEDIUM,
        label=_("Workspace context (tenant): scope chips"),
        help_text=_(
            "One per line: chip_label | chip_url. URL column optional. "
            "Renders as scope shortcut chips alongside the child-context "
            "card. Rows without a label are skipped. Existing siblings/"
            "stats lists fall through to section defaults via _deep_merge."
        ),
    )

    # 23) manager_200x.activity_ticker
    atk_label = forms.CharField(
        required=False,
        widget=_TEXT,
        label=_("Activity ticker: label"),
        help_text=_(
            "Operator-published header copy for the manager landing "
            "ticker (free-form; partials that don't read it ignore the "
            "extra key cleanly). Persisted under cockpit.activity_ticker.label."
        ),
    )
    atk_scroll_seconds = forms.IntegerField(
        required=False,
        min_value=1,
        widget=_NUMBER,
        label=_("Activity ticker: scroll seconds"),
        help_text=_(
            "Animation duration in seconds (default 40). Lower = faster. "
            "30-40 reads as Bloomberg-snappy; 60+ reads as nearly static. "
            "Maps to cockpit.activity_ticker.scroll_seconds."
        ),
    )
    atk_live_badge_label = forms.CharField(
        required=False,
        max_length=24,
        widget=_TEXT,
        label=_("Activity ticker: LIVE badge label"),
        help_text=_(
            "Red pill caption shown at the ticker's left edge "
            "(e.g. 'LIVE'). Maps to cockpit.activity_ticker.live_badge_label."
        ),
    )
    atk_cards = forms.CharField(
        required=False,
        widget=_TEXTAREA_LARGE,
        label=_("Activity ticker: cards"),
        help_text=_(
            "One per line: text | timestamp | icon | severity. "
            "Severity ∈ {ok, info, warn, danger}; anything else falls "
            "back to 'info'. Icon is optional (single glyph). Rows "
            "without text are skipped. Renders as a Bloomberg-style "
            "scrolling event feed above the platform pulse strip."
        ),
    )

    # v3.58.x Wave 10 Agent Q — global ticker host-routing toggles.
    # Promotes the ticker from landing-page-only chrome to GLOBAL chrome
    # across the operator and tenant shells, with per-host enable + a
    # real-data resolver kill-switch for operators that want to ship
    # only their own published cards.
    atk_enabled_on_manager = forms.BooleanField(
        required=False,
        widget=_CHECK,
        initial=True,
        label=_("Show activity ticker on manager / operator shell"),
        help_text=_(
            "When on (default), the live activity ticker renders at the "
            "top of every /super/* page across the operator shell. Turn "
            "off to suppress the ticker globally on the manager surface "
            "(landing pages may still override via their own block)."
        ),
    )
    atk_enabled_on_tenant = forms.BooleanField(
        required=False,
        widget=_CHECK,
        initial=True,
        label=_("Show activity ticker on tenant shell"),
        help_text=_(
            "On by default — Tier 1 inline badge, Tier 2 landing marquee, and "
            "Tier 3 incident banner on authenticated tenant pages using "
            "tenant-scoped events only (never operator-platform data). Turn "
            "off to suppress the ticker on the tenant shell."
        ),
    )
    atk_realdata_enabled = forms.BooleanField(
        required=False,
        widget=_CHECK,
        initial=True,
        label=_("Populate ticker from real platform state"),
        help_text=_(
            "When on (default), the ticker auto-fills with live events "
            "from the platform audit log + provisioning + delivery "
            "streams. Operator-published cards always win. Turn off "
            "to render ONLY operator-published cards (no auto-fill)."
        ),
    )
    atk_manager_sources = forms.MultipleChoiceField(
        required=False,
        choices=(),
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
        label=_("Manager metric sources"),
        help_text=_(
            "Choose which platform-wide metrics feed the operator LIVE banner. "
            "Unchecked sources are omitted from auto-fill cards."
        ),
    )
    atk_tenant_sources = forms.MultipleChoiceField(
        required=False,
        choices=(),
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
        label=_("Tenant metric sources"),
        help_text=_(
            "Choose which tenant-scoped metrics feed the portal LIVE banner. "
            "Tenant sources never read operator-platform models."
        ),
    )
    atk_manager_announcements = forms.CharField(
        required=False,
        widget=_TEXTAREA_LARGE,
        label=_("Manager announcements"),
        help_text=_(
            "One per line: text | kind | severity | pin | starts_at | ends_at | audiences. "
            "kind ∈ {info, alert, emergency}; pin ∈ {yes, no}; audiences comma-separated "
            "(all, parent, teacher, student, staff). Pinned emergencies render first."
        ),
    )
    atk_tenant_announcements = forms.CharField(
        required=False,
        widget=_TEXTAREA_LARGE,
        label=_("Tenant announcements"),
        help_text=_(
            "Same row format as manager announcements. These render only on tenant hosts "
            "and respect audience + schedule windows."
        ),
    )

    # 24) tenant_v3_extended.gradebook_trend
    gbt_label = forms.CharField(
        required=False,
        widget=_TEXT,
        label=_("Gradebook trend: label"),
        help_text=_(
            "Title shown above the per-subject sparkline rail "
            "(e.g. 'Gradebook trend'). Maps to cockpit.gradebook_trend.title."
        ),
    )
    gbt_subjects = forms.CharField(
        required=False,
        widget=_TEXTAREA_LARGE,
        label=_("Gradebook trend: subjects"),
        help_text=_(
            "One per line: subject_name | current_grade | trend_direction "
            "| sparkline_csv. trend_direction ∈ {up, flat, down}; anything "
            "else falls back to 'flat'. sparkline_csv is comma-separated "
            "numbers (e.g. '78,80,82,85,87,90') — non-numeric tokens are "
            "skipped; polyline x-coords are 0/1/2/… (index). Rows without "
            "a subject name are skipped."
        ),
    )

    # 25) tenant_v3_extended.attendance_heatmap
    ahm_label = forms.CharField(
        required=False,
        widget=_TEXT,
        label=_("Attendance heatmap: label"),
        help_text=_(
            "Title shown above the month-grid heatmap "
            "(e.g. 'Attendance heatmap'). Maps to "
            "cockpit.attendance_heatmap.title."
        ),
    )
    ahm_present_pct = forms.CharField(
        required=False,
        max_length=16,
        widget=_TEXT,
        label=_("Attendance heatmap: present percentage"),
        help_text=_(
            "Operator-formatted attendance percentage badge "
            "(e.g. '93%'). Persisted under "
            "cockpit.attendance_heatmap.present_pct; the raw percentage "
            "is never auto-rendered from student data."
        ),
    )
    ahm_pattern = forms.CharField(
        required=False,
        widget=_TEXTAREA_LARGE,
        label=_("Attendance heatmap: pattern"),
        help_text=_(
            "One per line: day_iso | status. day_iso may be YYYY-MM-DD "
            "or MM-DD or a bare day-of-month. Status ∈ {present, absent, "
            "late, holiday}; holiday maps to the partial's 'weekend' tone. "
            "Rows without a date are skipped. Renders as a tinted "
            "month-grid (each cell is one day)."
        ),
    )

    # 26) tenant_v3_extended.life_event_timeline
    let_label = forms.CharField(
        required=False,
        widget=_TEXT,
        label=_("Life event timeline: label"),
        help_text=_(
            "Title shown above the life-event timeline "
            "(e.g. 'Life events'). Maps to "
            "cockpit.life_event_timeline.title."
        ),
    )
    let_events = forms.CharField(
        required=False,
        widget=_TEXTAREA_LARGE,
        label=_("Life event timeline: events"),
        help_text=_(
            "One per line: date | category | title | description. "
            "Description column optional. Category ∈ {milestone, "
            "achievement, transition, certificate}; anything else falls "
            "back to 'milestone'. Date may be YYYY-MM-DD (auto-formats "
            "to 'DD Mon' day_label) / MM-DD / bare label. Rows without "
            "a title are skipped."
        ),
    )

    # ---- v3.57.17 Rich editor (final cockpit editor — AI Copilot rail) ----
    # Closes the last complex-schema deferral. Multi-block textarea pattern:
    # one Textarea per nested list (messages + suggestion pills). Empty
    # fields fall through to section defaults via ``_deep_merge`` in
    # cockpit_context.py. Sibling_compare remains a privacy-gated
    # code-only section (NOT editorialised here by design).
    #
    # 27) manager_200x.ai_copilot_rail
    acr_label = forms.CharField(
        required=False,
        widget=_TEXT,
        label=_("AI Copilot rail: label"),
        help_text=_(
            "Operator-published display label for the copilot rail "
            "(free-form; partials that don't read it ignore the extra key "
            "cleanly). Persisted under cockpit.ai_copilot_rail.label."
        ),
    )
    acr_title = forms.CharField(
        required=False,
        widget=_TEXT,
        label=_("AI Copilot rail: title"),
        help_text=_(
            "Header title shown at the top of the expanded copilot panel "
            "(e.g. 'Copilot'). Maps to cockpit.ai_copilot_rail.title."
        ),
    )
    acr_subtitle = forms.CharField(
        required=False,
        widget=_TEXT,
        label=_("AI Copilot rail: subtitle (optional)"),
        help_text=_(
            "Optional subtitle/eyebrow line under the title "
            "(free-form; partials that don't read it ignore the extra key "
            "cleanly). Persisted under cockpit.ai_copilot_rail.subtitle."
        ),
    )
    acr_messages = forms.CharField(
        required=False,
        widget=_TEXTAREA_LARGE,
        label=_("AI Copilot rail: messages"),
        help_text=_(
            "One per line: role | body. role ∈ {assistant, user}; anything "
            "else falls back to 'assistant'. Renders as the persistent "
            "chat thread inside the expanded copilot panel. Rows without "
            "a body are skipped. em_text (italic serif tail per message) "
            "falls through to section defaults."
        ),
    )
    acr_suggestions = forms.CharField(
        required=False,
        widget=_TEXTAREA_MEDIUM,
        label=_("AI Copilot rail: suggestion pills"),
        help_text=_(
            "One per line: label | command. Command column is optional "
            "(reserved for a future ``data-rmc-copilot-cmd`` hook — "
            "currently discarded on write; the rendering partial reads "
            "bare label strings). Rows without a label are skipped. "
            "Renders as starter-prompt chips below the message thread."
        ),
    )
    acr_insight_icon = forms.CharField(
        required=False,
        widget=_TEXT,
        label=_("AI Copilot rail: insight icon (optional)"),
        help_text=_(
            "Optional single glyph for the top insight pill (default '💡'). "
            "Persisted under cockpit.ai_copilot_rail.insight_icon; the "
            "partial may render it inline with the insight body."
        ),
    )
    acr_insight_body = forms.CharField(
        required=False,
        widget=_TEXTAREA_SMALL,
        label=_("AI Copilot rail: insight body (optional)"),
        help_text=_(
            "Top insight pill body — lead sentence shown above the chat "
            "thread (e.g. 'Two tenants need attention this week.'). "
            "Maps to cockpit.ai_copilot_rail.insight_text. insight_em "
            "(italic serif fragment) falls through to section defaults."
        ),
    )

    # ---- v3.58.x Wave 9 — Sibling-compare operator-editable copy ------
    # PRIVACY CONTRACT (load-bearing — DO NOT relax):
    # This editor configures ONLY copy + chrome: section enable flag,
    # titles, CTA labels, consent banner copy, denied-state message.
    # It CANNOT toggle ``opt_in`` to True. There is intentionally NO
    # ``opt_in_default`` field. ``opt_in`` is sourced from a per-parent
    # consent record (outside cockpit_payload). See
    # ``cockpit_context._sibling_compare_defaults()`` docstring for the
    # full contract.
    sct_enabled = forms.BooleanField(
        required=False,
        widget=_CHECK,
        label=_("Sibling-compare: section enabled"),
        help_text=_(
            "When checked, the section CTA surfaces in family portals. "
            "Sibling data still requires per-parent consent (opt_in) "
            "before any value renders — operator enable does NOT bypass "
            "the privacy gate."
        ),
    )
    sct_title = forms.CharField(
        required=False,
        max_length=120,
        widget=_TEXT,
        label=_("Sibling-compare: title"),
        help_text=_(
            "Section title shown above the CTA "
            "(e.g. 'Compare with siblings'). Maps to "
            "cockpit.sibling_compare.title."
        ),
    )
    sct_subtitle = forms.CharField(
        required=False,
        max_length=200,
        widget=_TEXT,
        label=_("Sibling-compare: subtitle"),
        help_text=_(
            "Subline under the title "
            "(e.g. 'Side-by-side trend across your family'). Maps to "
            "cockpit.sibling_compare.subtitle."
        ),
    )
    sct_cta_label = forms.CharField(
        required=False,
        max_length=80,
        widget=_TEXT,
        label=_("Sibling-compare: CTA label"),
        help_text=_(
            "Button label that opens the consent banner "
            "(e.g. 'Compare now'). Maps to "
            "cockpit.sibling_compare.cta_label."
        ),
    )
    sct_consent_banner_title = forms.CharField(
        required=False,
        max_length=120,
        widget=_TEXT,
        label=_("Sibling-compare: consent banner title"),
        help_text=_(
            "Header shown inside the consent modal "
            "(e.g. 'Family-comparison view'). Maps to "
            "cockpit.sibling_compare.consent_banner_title."
        ),
    )
    sct_consent_banner_body = forms.CharField(
        required=False,
        max_length=600,
        widget=_TEXTAREA_MEDIUM,
        label=_("Sibling-compare: consent banner body"),
        help_text=_(
            "Plain-text consent explainer (max 600 chars). Should state "
            "what data the view shows (initials, trend, sparkline — "
            "never full names) and that consent is required. Maps to "
            "cockpit.sibling_compare.consent_banner_body."
        ),
    )
    sct_consent_grant_button_label = forms.CharField(
        required=False,
        max_length=80,
        widget=_TEXT,
        label=_("Sibling-compare: grant-consent button label"),
        help_text=_(
            "Button label that records opt-in consent "
            "(e.g. 'Show sibling view'). Maps to "
            "cockpit.sibling_compare.consent_grant_button_label."
        ),
    )
    sct_consent_decline_button_label = forms.CharField(
        required=False,
        max_length=80,
        widget=_TEXT,
        label=_("Sibling-compare: decline-consent button label"),
        help_text=_(
            "Button label that keeps the section private "
            "(e.g. 'Keep private'). Maps to "
            "cockpit.sibling_compare.consent_decline_button_label."
        ),
    )
    sct_denied_state_message = forms.CharField(
        required=False,
        max_length=400,
        widget=_TEXTAREA_SMALL,
        label=_("Sibling-compare: denied-state message"),
        help_text=_(
            "Copy shown after a parent declines or has not yet opted in. "
            "Should remind them they can opt in at any time from Family "
            "settings. Maps to "
            "cockpit.sibling_compare.denied_state_message."
        ),
    )

    # ---- v3.58.x Wave 10 Agent S — Trust Pillars Alerts (v8 200x gap) ----
    # Mirrors ``cockpit.trust_pillars_alerts.*`` emitted by
    # ``_trust_pillars_alerts_defaults()`` in cockpit_manager_200x.py.
    # Operator surfaces only — minimal enable toggle + chrome copy + the
    # 7 pillar label overrides. Per-pillar status/value come from the
    # real-data resolver; operator-authored labels survive the round-trip.
    tpa_enabled = forms.BooleanField(
        required=False,
        widget=_CHECK,
        label=_("Enable trust pillars alerts feed"),
        help_text=_(
            "Renders the 7 platform trust pillars as an alert-feed below "
            "the trust-nutrition card on the manager landing. Maps to "
            "cockpit.trust_pillars_alerts.enabled."
        ),
    )
    tpa_title = forms.CharField(
        required=False,
        max_length=120,
        widget=_TEXT,
        label=_("Trust pillars: title"),
        help_text=_(
            "Card title (h3). Default: 'Platform posture'. Maps to "
            "cockpit.trust_pillars_alerts.title."
        ),
    )
    tpa_title_em = forms.CharField(
        required=False,
        max_length=120,
        widget=_TEXT,
        label=_("Trust pillars: title italic tail"),
        help_text=_(
            "Italic serif tail rendered after the title (e.g. 'seven "
            "pillars at a glance'). Maps to "
            "cockpit.trust_pillars_alerts.title_em."
        ),
    )
    tpa_footer_text = forms.CharField(
        required=False,
        max_length=240,
        widget=_TEXT,
        label=_("Trust pillars: footer caption"),
        help_text=_(
            "Optional italic serif caption rendered below the rows. Maps "
            "to cockpit.trust_pillars_alerts.footer_text."
        ),
    )
    tpa_label_audit_chain = forms.CharField(
        required=False,
        max_length=80,
        widget=_TEXT,
        label=_("Pillar label: audit_chain"),
        help_text=_(
            "Override the displayed label for the audit-chain integrity "
            "pillar. Empty falls through to the platform default "
            "('Audit chain integrity')."
        ),
    )
    tpa_label_maa_signatures = forms.CharField(
        required=False,
        max_length=80,
        widget=_TEXT,
        label=_("Pillar label: maa_signatures"),
        help_text=_(
            "Override the displayed label for the MAA signatures pillar. "
            "Empty falls through to the platform default ('MAA signatures')."
        ),
    )
    tpa_label_encryption_at_rest = forms.CharField(
        required=False,
        max_length=80,
        widget=_TEXT,
        label=_("Pillar label: encryption_at_rest"),
        help_text=_(
            "Override the displayed label for the encryption-at-rest "
            "pillar. Empty falls through to the platform default "
            "('Encryption at rest')."
        ),
    )
    tpa_label_ferpa_retention = forms.CharField(
        required=False,
        max_length=80,
        widget=_TEXT,
        label=_("Pillar label: ferpa_retention"),
        help_text=_(
            "Override the displayed label for the FERPA retention "
            "pillar. Empty falls through to the platform default "
            "('FERPA retention')."
        ),
    )
    tpa_label_webhook_signing = forms.CharField(
        required=False,
        max_length=80,
        widget=_TEXT,
        label=_("Pillar label: webhook_signing"),
        help_text=_(
            "Override the displayed label for the webhook signing "
            "pillar. Empty falls through to the platform default "
            "('Webhook signing')."
        ),
    )
    tpa_label_mfa_enforcement = forms.CharField(
        required=False,
        max_length=80,
        widget=_TEXT,
        label=_("Pillar label: mfa_enforcement"),
        help_text=_(
            "Override the displayed label for the MFA enforcement "
            "pillar. Empty falls through to the platform default "
            "('MFA enforcement')."
        ),
    )
    tpa_label_companion_handshake = forms.CharField(
        required=False,
        max_length=80,
        widget=_TEXT,
        label=_("Pillar label: companion_handshake"),
        help_text=_(
            "Override the displayed label for the companion handshake "
            "pillar. Empty falls through to the platform default "
            "('Companion handshake')."
        ),
    )

    # ---- v3.57.18 Wave 8 — Public school-signup form ------------------
    # Mirrors ``cockpit.signup_form.*`` emitted by ``_signup_form_defaults()``
    # in cockpit_context.py. Unlike most cockpit sections (default off),
    # the signup form defaults to ``enabled=True`` — it's the public
    # front door — so operators flip individual copy/chrome fields
    # without losing the section.
    signup_form_enabled = forms.BooleanField(
        required=False,
        widget=_CHECK,
        label=_("Enable public signup form"),
        help_text=_(
            "When unchecked, the /signup/ page hides the form chrome "
            "(operators can pause acquisition during incidents)."
        ),
    )
    signup_form_heading = forms.CharField(
        required=False,
        max_length=120,
        widget=_TEXT,
        label=_("Signup form: heading"),
        help_text=_(
            "Top-of-card title (e.g. 'Start your school workspace'). "
            "Maps to cockpit.signup_form.heading."
        ),
    )
    signup_form_subheading = forms.CharField(
        required=False,
        max_length=320,
        widget=_TEXTAREA_SMALL,
        label=_("Signup form: subheading"),
        help_text=_(
            "Lead paragraph under the heading (max 320 chars). "
            "Maps to cockpit.signup_form.subheading."
        ),
    )
    signup_form_button_label = forms.CharField(
        required=False,
        max_length=80,
        widget=_TEXT,
        label=_("Signup form: button label"),
        help_text=_(
            "Submit button text (e.g. 'Create my school workspace'). "
            "Maps to cockpit.signup_form.button_label."
        ),
    )
    signup_form_show_trust_pills = forms.BooleanField(
        required=False,
        widget=_CHECK,
        label=_("Signup form: show trust pills row"),
        help_text=_(
            "Toggle the row of trust signals (SSL · FERPA · backups · "
            "billing) above the form. Maps to "
            "cockpit.signup_form.show_trust_pills."
        ),
    )
    signup_form_trust_pill_lines = forms.CharField(
        required=False,
        widget=_TEXTAREA_MEDIUM,
        label=_("Signup form: trust pill lines"),
        help_text=_(
            "One per line: icon | label. Icon defaults to ✓ when omitted. "
            "Rows without a label are skipped. Renders as a horizontal "
            "row of mini-pills above the form."
        ),
    )
    signup_form_show_calendar_cards = forms.BooleanField(
        required=False,
        widget=_CHECK,
        label=_("Signup form: show calendar picker cards"),
        help_text=_(
            "When checked, the calendar picker renders as 2 selectable "
            "cards (Default · UK) instead of a plain select. "
            "Maps to cockpit.signup_form.show_calendar_cards."
        ),
    )
    signup_form_footer_login_label = forms.CharField(
        required=False,
        max_length=80,
        widget=_TEXT,
        label=_("Signup form: footer login label"),
        help_text=_(
            "Link text shown in the 'Already have an account?' footer "
            "(e.g. 'Find your school'). Maps to "
            "cockpit.signup_form.footer_login_label."
        ),
    )
    signup_form_footer_login_url = forms.CharField(
        required=False,
        max_length=240,
        widget=_TEXT,
        label=_("Signup form: footer login URL"),
        help_text=_(
            "Optional override URL. Empty falls back to the platform's "
            "global_login_discovery view. Maps to "
            "cockpit.signup_form.footer_login_url."
        ),
    )

    # ---- Login immersive canvas (tenant portal sign-in left panel) ----
    lic_enabled = forms.BooleanField(
        required=False,
        widget=_CHECK,
        label=_("Enable login canvas"),
        help_text=_("Left-panel immersive canvas on the tenant login page."),
    )
    lic_layout_preset = forms.ChoiceField(
        required=False,
        choices=(
            ("civic_editorial", _("Civic editorial")),
            ("campus_hero", _("Campus hero")),
            ("calm_command", _("Calm command")),
            ("family_first", _("Family first")),
            ("minimal_glass", _("Minimal glass")),
        ),
        widget=forms.Select(attrs={"class": "form-select"}),
        label=_("Login canvas: layout preset"),
    )
    lic_theme_variant = forms.ChoiceField(
        required=False,
        choices=(
            ("brand", _("Brand")),
            ("dark", _("Dark")),
            ("light", _("Light")),
            ("high_contrast", _("High contrast")),
        ),
        widget=forms.Select(attrs={"class": "form-select"}),
        label=_("Login canvas: theme variant"),
    )
    lic_hero_mode = forms.ChoiceField(
        required=False,
        choices=(
            ("carousel", _("Carousel")),
            ("marquee", _("Marquee (Pro)")),
            ("static", _("Static")),
            ("hybrid", _("Hybrid (Pro)")),
        ),
        widget=forms.Select(attrs={"class": "form-select"}),
        label=_("Login canvas: hero mode"),
    )
    lic_hero_full_bleed = forms.BooleanField(
        required=False,
        widget=_CHECK,
        label=_("Login canvas: full-bleed hero banner"),
    )
    lic_hero_scroll_seconds = forms.IntegerField(
        required=False,
        min_value=8,
        max_value=120,
        widget=_NUMBER,
        label=_("Login canvas: hero scroll seconds"),
        help_text=_("Carousel interval / marquee duration (8–120)."),
    )
    lic_pro_enabled = forms.BooleanField(
        required=False,
        widget=_CHECK,
        label=_("Login canvas: Pro tier"),
        help_text=_("Unlocks multi-slide carousel, marquee, gallery, sponsored slots."),
    )
    lic_show_ticker = forms.BooleanField(
        required=False,
        widget=_CHECK,
        label=_("Login canvas: show activity ticker"),
    )
    lic_show_bento = forms.BooleanField(
        required=False,
        widget=_CHECK,
        label=_("Login canvas: show metric bento"),
    )
    lic_show_feed = forms.BooleanField(
        required=False,
        widget=_CHECK,
        label=_("Login canvas: show after-sign-in feed"),
    )
    lic_show_gallery = forms.BooleanField(
        required=False,
        widget=_CHECK,
        label=_("Login canvas: show gallery moments"),
    )
    lic_show_trust = forms.BooleanField(
        required=False,
        widget=_CHECK,
        label=_("Login canvas: show trust chips"),
    )
    lic_compact_viewport = forms.BooleanField(
        required=False,
        widget=_CHECK,
        label=_("Login canvas: compact on short viewports"),
    )
    lic_feed_section_label = forms.CharField(
        required=False,
        max_length=80,
        widget=_TEXT,
        label=_("Login canvas: feed section label"),
    )
    lic_dash_title = forms.CharField(
        required=False,
        max_length=120,
        widget=_TEXT,
        label=_("Login canvas: dash panel title"),
    )
    lic_hero_slides_lines = forms.CharField(
        required=False,
        widget=_TEXTAREA_MEDIUM,
        label=_("Login canvas: hero slides"),
        help_text=_(
            "One slide per line: eyebrow | title | body | role_hint | start_iso | end_iso. "
            "role_hint is optional (staff, parent, student). Pro unlocks more slides."
        ),
    )
    lic_gallery_lines = forms.CharField(
        required=False,
        widget=_TEXTAREA_MEDIUM,
        label=_("Login canvas: gallery moments"),
        help_text=_("One per line: url | caption | alt | link_url"),
    )
    lic_metric_tile_keys = forms.CharField(
        required=False,
        max_length=240,
        widget=_TEXT,
        label=_("Login canvas: metric tile keys"),
        help_text=_(
            "Comma-separated keys: students_active, today_date, portal_secure, "
            "support_help, events_this_week, attendance_rate_7d, staff_active, languages_count"
        ),
    )
    lic_allow_sponsored_slot = forms.BooleanField(
        required=False,
        widget=_CHECK,
        label=_("Login canvas: allow sponsored hero slots"),
    )
    lic_sponsored_lines = forms.CharField(
        required=False,
        widget=_TEXTAREA_SMALL,
        label=_("Login canvas: sponsored slots"),
        help_text=_(
            "Pro only. One per line: eyebrow | title | body | cta_label | cta_url"
        ),
    )
    lic_hide_sponsored_offline = forms.BooleanField(
        required=False,
        widget=_CHECK,
        label=_("Login canvas: hide sponsored content offline"),
        help_text=_("Recommended. Essential school notices remain visible; promotions pause until reconnection."),
    )
    lic_sponsored_max_visible = forms.IntegerField(
        required=False,
        min_value=0,
        max_value=2,
        widget=_NUMBER,
        label=_("Login canvas: maximum visible sponsored placements"),
        help_text=_("Use 0 to pause placements, 1 for the recommended restrained layout, or 2 maximum."),
    )
    lic_dash_staff_note = forms.CharField(
        required=False,
        max_length=320,
        widget=_TEXTAREA_SMALL,
        label=_("Login canvas: staff preview note"),
    )
    lic_dash_parent_note = forms.CharField(
        required=False,
        max_length=320,
        widget=_TEXTAREA_SMALL,
        label=_("Login canvas: parent preview note"),
    )
    lic_dash_student_note = forms.CharField(
        required=False,
        max_length=320,
        widget=_TEXTAREA_SMALL,
        label=_("Login canvas: student preview note"),
    )
    lic_trust_chip_lines = forms.CharField(
        required=False,
        widget=_TEXTAREA_SMALL,
        label=_("Login canvas: trust chip lines"),
        help_text=_("One label per line."),
    )
    lic_role_preview_staff = forms.CharField(
        required=False,
        max_length=60,
        widget=_TEXT,
        label=_("Login canvas: staff preview pill"),
    )
    lic_role_preview_parent = forms.CharField(
        required=False,
        max_length=60,
        widget=_TEXT,
        label=_("Login canvas: parent preview pill"),
    )
    lic_role_preview_student = forms.CharField(
        required=False,
        max_length=60,
        widget=_TEXT,
        label=_("Login canvas: student preview pill"),
    )
    lic_role_preview_default = forms.CharField(
        required=False,
        max_length=60,
        widget=_TEXT,
        label=_("Login canvas: default preview pill"),
    )

    class Meta:
        model = django_apps.get_model("siteconfig", "Site" + "Settings")
        # Phase B: cockpit_payload is no longer a SiteSettings column (it lives in
        # RuntimeDefaults.payload). Operators edit the flat fields above;
        # ``clean()`` rebuilds the nested dict into cleaned_data["cockpit_payload"]
        # and the owning view persists it via SiteSettings.set_cockpit_payload().
        fields: list[str] = []

    # ----- helpers for declarative fieldset grouping (templates / admin) ---
    TENANT_EXPERIENCE_POLICY_FIELDS: tuple[str, ...] = (
        "txp_experience_preset",
        "txp_role_home_experience_mode",
        "txp_role_preset_ADMIN",
        "txp_role_preset_TEACHER",
        "txp_role_preset_PARENT",
        "txp_role_preset_STUDENT",
        "txp_use_v3_shell",
        "txp_show_mission_strip",
        "txp_hide_mission_strip_after_launch",
        "txp_show_experience_command_strip",
        "txp_show_security_posture_inline",
        "txp_show_mfa_nudge",
        "txp_show_legacy_explain_strip",
        "txp_show_next_action_strip",
        "txp_show_community_band_on_v3",
        "txp_show_newsletter_band_on_v3",
        "txp_show_proactive_help_nudge",
        "txp_show_lifecycle_concierge",
        "txp_show_kb_ai_panel",
        "txp_show_legacy_ai_copilot_dock",
        "txp_ai_layer_strip_mode",
        "txp_ai_copilot_rail_mode",
        "txp_sidebar_default_width",
        "txp_sidebar_min_width",
        "txp_sidebar_max_width",
        "txp_mission_eyebrow",
        "txp_mission_cta_label",
        "txp_experience_score_label",
        "txp_experience_score_profile_weight",
        "txp_experience_score_school_weight",
        "txp_experience_score_ready_threshold",
        "txp_experience_score_attention_threshold",
        "txp_experience_score_country_bonus",
        "txp_setup_surface_enabled",
        "txp_hidden_setup_wizard_keys",
        "txp_show_first_run_zero_state_on_v3",
        "txp_show_smart_action_hub_on_v3",
        "txp_show_portal_chathead_on_v3",
        "txp_show_header_home_link_on_v3",
        "txp_show_workspace_os_header_on_v3",
        "txp_show_operator_console_strip_on_v3",
        "txp_show_os_status_strip_on_v3",
        "txp_show_zero_click_command_strip_on_v3",
        "txp_show_dashboard_stats_cards_on_v3",
        "txp_show_legacy_sidebar_user_header_on_v3",
        "txp_sidebar_rail_width",
    )
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
        "lwm_globe_auto_rotate",
        "lwm_layout",
        "lwm_tour_enabled",
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
    # v3.57.16 rich-editor fieldsets — 5 NEW sections (final batch).
    WORKSPACE_CONTEXT_TENANT_FIELDS: tuple[str, ...] = (
        "wct_label",
        "wct_school_role",
        "wct_scope_chips",
    )
    ACTIVITY_TICKER_FIELDS: tuple[str, ...] = (
        "atk_label",
        "atk_scroll_seconds",
        "atk_live_badge_label",
        "atk_cards",
    )
    LIVE_BANNER_STUDIO_FIELDS: tuple[str, ...] = (
        "atk_enabled_on_manager",
        "atk_enabled_on_tenant",
        "atk_realdata_enabled",
        "atk_manager_sources",
        "atk_tenant_sources",
        "atk_manager_announcements",
        "atk_tenant_announcements",
    )
    GRADEBOOK_TREND_FIELDS: tuple[str, ...] = (
        "gbt_label",
        "gbt_subjects",
    )
    ATTENDANCE_HEATMAP_FIELDS: tuple[str, ...] = (
        "ahm_label",
        "ahm_present_pct",
        "ahm_pattern",
    )
    LIFE_EVENT_TIMELINE_FIELDS: tuple[str, ...] = (
        "let_label",
        "let_events",
    )
    # v3.57.17 rich-editor fieldset — final cockpit editor (closes the
    # ai_copilot_rail complexity deferral). Sibling_compare stays
    # code-only by design (privacy gate).
    AI_COPILOT_RAIL_FIELDS: tuple[str, ...] = (
        "acr_label",
        "acr_title",
        "acr_subtitle",
        "acr_messages",
        "acr_suggestions",
        "acr_insight_icon",
        "acr_insight_body",
    )
    # v3.58.x Wave 9 rich-editor fieldset — sibling-compare operator-
    # editable copy. PRIVACY CONTRACT: this editor CANNOT toggle the
    # per-parent ``opt_in`` consent flag — there is intentionally no
    # ``opt_in_default`` field. ``opt_in`` is sourced from a per-parent
    # consent record (outside cockpit_payload). See
    # ``apps/siteconfig/cockpit_context._sibling_compare_defaults()``
    # docstring for the full contract.
    SIBLING_COMPARE_FIELDS: tuple[str, ...] = (
        "sct_enabled",
        "sct_title",
        "sct_subtitle",
        "sct_cta_label",
        "sct_consent_banner_title",
        "sct_consent_banner_body",
        "sct_consent_grant_button_label",
        "sct_consent_decline_button_label",
        "sct_denied_state_message",
    )
    # v3.58.x Wave 10 Agent S rich-editor fieldset — Trust pillars alerts.
    # Closes the v8 200x preview's alerts-feed gap. Renders the 7 platform
    # trust pillars in an alert-feed list distinct from the nutrition-label
    # `trust_nutrition` card. Defaults to enabled=False — operator opts in;
    # the real-data resolver populates per-pillar value+status so per-pillar
    # data isn't a configurable surface (avoids stale operator-pasted posture
    # masking the live verifier signal). Operator-authored pillar labels DO
    # survive the round-trip via _build_payload's overlay loop.
    TRUST_PILLARS_ALERTS_FIELDS: tuple[str, ...] = (
        "tpa_enabled",
        "tpa_title",
        "tpa_title_em",
        "tpa_footer_text",
        "tpa_label_audit_chain",
        "tpa_label_maa_signatures",
        "tpa_label_encryption_at_rest",
        "tpa_label_ferpa_retention",
        "tpa_label_webhook_signing",
        "tpa_label_mfa_enforcement",
        "tpa_label_companion_handshake",
    )
    # v3.57.18 Wave 8 rich-editor fieldset — public school-signup form.
    # Operator-configurable copy + chrome for the marketing-host
    # /signup/ page. Defaults to enabled=True (front-door section).
    SIGNUP_FORM_FIELDS: tuple[str, ...] = (
        "signup_form_enabled",
        "signup_form_heading",
        "signup_form_subheading",
        "signup_form_button_label",
        "signup_form_show_trust_pills",
        "signup_form_trust_pill_lines",
        "signup_form_show_calendar_cards",
        "signup_form_footer_login_label",
        "signup_form_footer_login_url",
    )
    LOGIN_CANVAS_FIELDS: tuple[str, ...] = (
        "lic_enabled",
        "lic_layout_preset",
        "lic_theme_variant",
        "lic_hero_mode",
        "lic_hero_full_bleed",
        "lic_hero_scroll_seconds",
        "lic_pro_enabled",
        "lic_show_ticker",
        "lic_show_bento",
        "lic_show_feed",
        "lic_show_gallery",
        "lic_show_trust",
        "lic_compact_viewport",
        "lic_feed_section_label",
        "lic_dash_title",
        "lic_hero_slides_lines",
        "lic_gallery_lines",
        "lic_metric_tile_keys",
        "lic_allow_sponsored_slot",
        "lic_sponsored_lines",
        "lic_hide_sponsored_offline",
        "lic_sponsored_max_visible",
        "lic_dash_staff_note",
        "lic_dash_parent_note",
        "lic_dash_student_note",
        "lic_trust_chip_lines",
        "lic_role_preview_staff",
        "lic_role_preview_parent",
        "lic_role_preview_student",
        "lic_role_preview_default",
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

    def __init__(self, *args: Any, configure_request: Any = None, **kwargs: Any) -> None:
        self.configure_request = configure_request
        super().__init__(*args, **kwargs)
        from apps.siteconfig.tenant_experience_policy import AI_MODE_CHOICES
        from apps.siteconfig.tenant_experience_presets import (
            EXPERIENCE_PRESET_CHOICES,
            ROLE_HOME_EXPERIENCE_MODE_CHOICES,
            ROLE_PRESET_FIELD_CHOICES,
        )

        self.fields["txp_ai_layer_strip_mode"].choices = AI_MODE_CHOICES
        self.fields["txp_ai_copilot_rail_mode"].choices = AI_MODE_CHOICES
        self.fields["txp_experience_preset"].choices = EXPERIENCE_PRESET_CHOICES
        self.fields["txp_role_home_experience_mode"].choices = (
            ROLE_HOME_EXPERIENCE_MODE_CHOICES
        )
        for bucket in ("ADMIN", "TEACHER", "PARENT", "STUDENT"):
            self.fields[f"txp_role_preset_{bucket}"].choices = ROLE_PRESET_FIELD_CHOICES
        from apps.siteconfig.cockpit_live_banner_program import (
            manager_source_choices,
            tenant_source_choices,
        )

        self.fields["atk_manager_sources"].choices = manager_source_choices()
        self.fields["atk_tenant_sources"].choices = tenant_source_choices()
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
        from apps.siteconfig.tenant_experience_policy import (
            tenant_experience_policy_defaults,
        )
        from apps.siteconfig.tenant_experience_presets import (
            ROLE_PRESET_INHERIT,
            normalize_role_experience_presets,
        )

        txp = payload.get("tenant_experience_policy") or {}
        defaults = tenant_experience_policy_defaults()
        role_presets = normalize_role_experience_presets(txp.get("role_experience_presets"))
        for key, default_value in defaults.items():
            if key == "role_experience_presets":
                continue
            field_name = f"txp_{key}"
            if field_name not in self.fields:
                continue
            stored = txp.get(key, default_value)
            if key == "hidden_setup_wizard_keys" and isinstance(stored, list):
                stored = ", ".join(str(item) for item in stored if item)
            self.fields[field_name].initial = stored
        for bucket in ("ADMIN", "TEACHER", "PARENT", "STUDENT"):
            field_name = f"txp_role_preset_{bucket}"
            if field_name in self.fields:
                self.fields[field_name].initial = role_presets.get(
                    bucket, ROLE_PRESET_INHERIT
                )

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
        self.fields["lwm_globe_auto_rotate"].initial = bool(
            world_map.get("globe_auto_rotate", True)
        )
        self.fields["lwm_layout"].initial = world_map.get("layout") or "hero"
        self.fields["lwm_tour_enabled"].initial = bool(world_map.get("tour_enabled", True))

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

        # ---- v3.57.16 rich-editor seeds (5 NEW sections — final batch) ----
        # tenant_dashboard.workspace_context_tenant
        wct = payload.get("workspace_context_tenant") or {}
        self.fields["wct_label"].initial = wct.get("label", "")
        wct_child = wct.get("child") or {}
        self.fields["wct_school_role"].initial = wct_child.get("subline", "")
        self.fields["wct_scope_chips"].initial = _serialize_scope_chips(
            wct.get("scope_chips")
        )

        # manager_200x.activity_ticker
        atk = payload.get("activity_ticker") or {}
        # ``label`` is not in the helper defaults but is operator-editable
        # here; round-trip cleanly via .get() with empty fallback.
        self.fields["atk_label"].initial = atk.get("label", "")
        self.fields["atk_scroll_seconds"].initial = atk.get("scroll_seconds")
        self.fields["atk_live_badge_label"].initial = atk.get(
            "live_badge_label", ""
        )
        self.fields["atk_cards"].initial = _serialize_activity_ticker_cards(
            atk.get("cards")
        )
        # v3.58.x Wave 10 Agent Q — global ticker host-routing toggles.
        # These persist directly under the activity_ticker section so the
        # cockpit_context orchestrator + the partial can read them via the
        # already-resolved `cockpit.activity_ticker` namespace.
        # Defaults mirror the field declarations (manager=True / tenant=True
        # / realdata=True) — first-render with no existing payload uses the
        # widget `initial=` value.
        if "enabled_on_manager" in atk:
            self.fields["atk_enabled_on_manager"].initial = bool(
                atk.get("enabled_on_manager")
            )
        if "enabled_on_tenant" in atk:
            self.fields["atk_enabled_on_tenant"].initial = bool(
                atk.get("enabled_on_tenant")
            )
        if "realdata_enabled" in atk:
            self.fields["atk_realdata_enabled"].initial = bool(
                atk.get("realdata_enabled")
            )
        tat = payload.get("tenant_activity_ticker") or {}
        nested_sources = atk.get("sources_enabled")
        # resolve_sources_enabled is imported only in __init__'s local scope, not here —
        # without this import _seed_initial_from_payload raised NameError (cockpit form 500).
        from apps.siteconfig.cockpit_live_banner_program import (
            resolve_sources_enabled,
        )

        manager_sources = resolve_sources_enabled(
            nested_sources.get("manager")
            if isinstance(nested_sources, dict)
            else nested_sources,
            "manager",
        )
        tenant_sources = resolve_sources_enabled(
            tat.get("sources_enabled")
            if tat.get("sources_enabled") is not None
            else (
                nested_sources.get("tenant")
                if isinstance(nested_sources, dict)
                else None
            ),
            "tenant",
        )
        self.fields["atk_manager_sources"].initial = sorted(manager_sources)
        self.fields["atk_tenant_sources"].initial = sorted(tenant_sources)
        self.fields["atk_manager_announcements"].initial = _serialize_live_banner_announcements(
            atk.get("announcements")
        )
        self.fields["atk_tenant_announcements"].initial = _serialize_live_banner_announcements(
            tat.get("announcements")
        )

        # tenant_v3_extended.gradebook_trend
        gbt = payload.get("gradebook_trend") or {}
        self.fields["gbt_label"].initial = gbt.get("title", "")
        self.fields["gbt_subjects"].initial = _serialize_gradebook_subjects(
            gbt.get("subjects")
        )

        # tenant_v3_extended.attendance_heatmap
        ahm = payload.get("attendance_heatmap") or {}
        self.fields["ahm_label"].initial = ahm.get("title", "")
        self.fields["ahm_present_pct"].initial = ahm.get("present_pct", "")
        self.fields["ahm_pattern"].initial = _serialize_attendance_pattern(
            ahm.get("cells")
        )

        # tenant_v3_extended.life_event_timeline
        let = payload.get("life_event_timeline") or {}
        self.fields["let_label"].initial = let.get("title", "")
        self.fields["let_events"].initial = _serialize_life_events(
            let.get("events")
        )

        # ---- v3.57.17 rich-editor seeds (final cockpit editor) ------------
        # manager_200x.ai_copilot_rail — multi-block editor (messages +
        # suggestion pills + insight pill). ``label`` and ``subtitle`` are
        # NOT in the helper defaults but are operator-editable here;
        # round-trip cleanly via .get() with empty fallback.
        acr = payload.get("ai_copilot_rail") or {}
        self.fields["acr_label"].initial = acr.get("label", "")
        self.fields["acr_title"].initial = acr.get("title", "")
        self.fields["acr_subtitle"].initial = acr.get("subtitle", "")
        self.fields["acr_messages"].initial = _serialize_copilot_messages(
            acr.get("messages")
        )
        self.fields["acr_suggestions"].initial = _serialize_copilot_suggestions(
            acr.get("suggested_actions")
        )
        self.fields["acr_insight_icon"].initial = acr.get("insight_icon", "")
        # ``insight_body`` ↔ helper's ``insight_text`` — the partial reads
        # ``insight_text`` directly so persisted payloads use that key.
        self.fields["acr_insight_body"].initial = acr.get("insight_text", "")

        # ---- v3.58.x Wave 9 sibling-compare seeds -------------------------
        # PRIVACY CONTRACT: deliberately reads ONLY the copy + chrome keys.
        # ``opt_in`` is NEVER seeded into the form — it lives on a per-parent
        # consent record outside cockpit_payload and operators cannot edit it.
        sibling_compare = payload.get("sibling_compare") or {}
        if "enabled" in sibling_compare:
            self.fields["sct_enabled"].initial = bool(
                sibling_compare.get("enabled")
            )
        else:
            self.fields["sct_enabled"].initial = False
        self.fields["sct_title"].initial = sibling_compare.get("title", "")
        self.fields["sct_subtitle"].initial = sibling_compare.get("subtitle", "")
        self.fields["sct_cta_label"].initial = sibling_compare.get(
            "cta_label", ""
        )
        self.fields["sct_consent_banner_title"].initial = sibling_compare.get(
            "consent_banner_title", ""
        )
        self.fields["sct_consent_banner_body"].initial = sibling_compare.get(
            "consent_banner_body", ""
        )
        self.fields["sct_consent_grant_button_label"].initial = (
            sibling_compare.get("consent_grant_button_label", "")
        )
        self.fields["sct_consent_decline_button_label"].initial = (
            sibling_compare.get("consent_decline_button_label", "")
        )
        self.fields["sct_denied_state_message"].initial = sibling_compare.get(
            "denied_state_message", ""
        )

        # ---- v3.58.x Wave 10 Agent S trust pillars alerts seeds -----------
        # Trust-pillars-alerts editor: enable toggle + chrome copy + 7 pillar
        # label overrides. Per-pillar value/status come from the real-data
        # resolver (or operator JSON overlay) — NOT from this form, to avoid
        # stale operator-typed posture masking the live verifier signal.
        tpa = payload.get("trust_pillars_alerts") or {}
        if "enabled" in tpa:
            self.fields["tpa_enabled"].initial = bool(tpa.get("enabled"))
        else:
            self.fields["tpa_enabled"].initial = False
        self.fields["tpa_title"].initial = tpa.get("title", "")
        self.fields["tpa_title_em"].initial = tpa.get("title_em", "")
        self.fields["tpa_footer_text"].initial = tpa.get("footer_text", "")
        # Per-pillar label seeds: walk the existing pillars list (if any) and
        # rebuild a slug->label map for the 7 known pillar slugs.
        existing_pillars = tpa.get("pillars") or []
        if isinstance(existing_pillars, list):
            label_by_slug: dict[str, str] = {}
            for entry in existing_pillars:
                if isinstance(entry, dict):
                    slug = entry.get("slug")
                    label = entry.get("label")
                    if isinstance(slug, str) and isinstance(label, str):
                        label_by_slug[slug] = label
            for slug in (
                "audit_chain",
                "maa_signatures",
                "encryption_at_rest",
                "ferpa_retention",
                "webhook_signing",
                "mfa_enforcement",
                "companion_handshake",
            ):
                field_name = f"tpa_label_{slug}"
                if field_name in self.fields:
                    self.fields[field_name].initial = label_by_slug.get(slug, "")

        # ---- v3.57.18 Wave 8 signup form seeds ----------------------------
        # Public school-signup form — copy + chrome operator-configurable
        # via cockpit.signup_form.*. Defaults to enabled=True so the
        # checkbox should reflect any explicit operator override; when the
        # payload omits ``enabled`` entirely, we honor the default (True)
        # via a present-key check rather than blind .get() fallback to False.
        signup_form = payload.get("signup_form") or {}
        if "enabled" in signup_form:
            self.fields["signup_form_enabled"].initial = bool(
                signup_form.get("enabled")
            )
        else:
            self.fields["signup_form_enabled"].initial = True
        self.fields["signup_form_heading"].initial = signup_form.get("heading", "")
        self.fields["signup_form_subheading"].initial = signup_form.get(
            "subheading", ""
        )
        self.fields["signup_form_button_label"].initial = signup_form.get(
            "button_label", ""
        )
        # ``show_trust_pills`` / ``show_calendar_cards`` default to True;
        # mirror the present-key honest-rebind pattern used by
        # ``signup_form_enabled`` above so an explicit operator unchecking
        # round-trips faithfully.
        if "show_trust_pills" in signup_form:
            self.fields["signup_form_show_trust_pills"].initial = bool(
                signup_form.get("show_trust_pills")
            )
        else:
            self.fields["signup_form_show_trust_pills"].initial = True
        self.fields["signup_form_trust_pill_lines"].initial = (
            _serialize_trust_pill_lines(signup_form.get("trust_pill_lines"))
        )
        if "show_calendar_cards" in signup_form:
            self.fields["signup_form_show_calendar_cards"].initial = bool(
                signup_form.get("show_calendar_cards")
            )
        else:
            self.fields["signup_form_show_calendar_cards"].initial = True
        self.fields["signup_form_footer_login_label"].initial = signup_form.get(
            "footer_login_label", ""
        )
        self.fields["signup_form_footer_login_url"].initial = signup_form.get(
            "footer_login_url", ""
        )

        lic = payload.get("login_immersive_canvas") or {}
        if "enabled" in lic:
            self.fields["lic_enabled"].initial = bool(lic.get("enabled"))
        else:
            self.fields["lic_enabled"].initial = True
        self.fields["lic_layout_preset"].initial = lic.get(
            "layout_preset", "civic_editorial"
        )
        self.fields["lic_theme_variant"].initial = lic.get("theme_variant", "brand")
        hero = lic.get("hero_banner") or {}
        self.fields["lic_hero_mode"].initial = hero.get("mode", "carousel")
        if "full_bleed" in hero:
            self.fields["lic_hero_full_bleed"].initial = bool(hero.get("full_bleed"))
        else:
            self.fields["lic_hero_full_bleed"].initial = True
        self.fields["lic_hero_scroll_seconds"].initial = hero.get("scroll_seconds", 32)
        if "pro_enabled" in lic:
            self.fields["lic_pro_enabled"].initial = bool(lic.get("pro_enabled"))
        zones = lic.get("zones") or {}
        for field_name, zone_key, default in (
            ("lic_show_ticker", "show_ticker", True),
            ("lic_show_bento", "show_bento", True),
            ("lic_show_feed", "show_feed", True),
            ("lic_show_gallery", "show_gallery", True),
            ("lic_show_trust", "show_trust", True),
            ("lic_compact_viewport", "compact_on_short_viewport", True),
        ):
            if zone_key in zones:
                self.fields[field_name].initial = bool(zones.get(zone_key))
            else:
                self.fields[field_name].initial = default
        feed = lic.get("feed") or {}
        self.fields["lic_feed_section_label"].initial = feed.get("section_label", "")
        self.fields["lic_dash_title"].initial = feed.get("dash_title", "")
        self.fields["lic_hero_slides_lines"].initial = _serialize_lic_hero_slides(
            hero.get("slides")
        )
        self.fields["lic_gallery_lines"].initial = _serialize_lic_gallery_lines(
            (lic.get("gallery") or {}).get("items")
        )
        self.fields["lic_metric_tile_keys"].initial = ", ".join(
            (lic.get("metrics") or {}).get("tile_keys") or []
        )
        monetization = lic.get("monetization") or {}
        if "allow_sponsored_slot" in monetization:
            self.fields["lic_allow_sponsored_slot"].initial = bool(
                monetization.get("allow_sponsored_slot")
            )
        self.fields["lic_sponsored_lines"].initial = _serialize_lic_sponsored_lines(
            monetization.get("sponsored_slots")
        )
        self.fields["lic_hide_sponsored_offline"].initial = bool(
            monetization.get("hide_when_offline", True)
        )
        self.fields["lic_sponsored_max_visible"].initial = monetization.get(
            "max_visible", 1
        )
        dash_preview = lic.get("dash_preview") or {}
        self.fields["lic_dash_staff_note"].initial = (dash_preview.get("staff") or {}).get(
            "note", ""
        )
        self.fields["lic_dash_parent_note"].initial = (
            dash_preview.get("parent") or {}
        ).get("note", "")
        self.fields["lic_dash_student_note"].initial = (
            dash_preview.get("student") or {}
        ).get("note", "")
        self.fields["lic_trust_chip_lines"].initial = _serialize_lic_trust_chip_lines(
            lic.get("trust_chips")
        )
        role_preview = lic.get("role_preview") or {}
        self.fields["lic_role_preview_staff"].initial = (role_preview.get("staff") or {}).get(
            "pill", ""
        )
        self.fields["lic_role_preview_parent"].initial = (
            role_preview.get("parent") or {}
        ).get("pill", "")
        self.fields["lic_role_preview_student"].initial = (
            role_preview.get("student") or {}
        ).get("pill", "")
        self.fields["lic_role_preview_default"].initial = (
            role_preview.get("default") or {}
        ).get("pill", "")

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
            "tenant_experience_policy": build_tenant_experience_policy_from_cleaned(
                cleaned
            ),
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
            from apps.siteconfig.world_map_geo import enrich_regional_breakdown

            world_overlay["regional_breakdown"] = enrich_regional_breakdown(lwm_regional)
        world_overlay["globe_auto_rotate"] = bool(cleaned.get("lwm_globe_auto_rotate"))
        layout = (cleaned.get("lwm_layout") or "hero").strip().lower()
        world_overlay["layout"] = layout if layout in ("hero", "side") else "hero"
        world_overlay["tour_enabled"] = bool(cleaned.get("lwm_tour_enabled"))
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

        # v3.57.16 rich-editor overlays (5 NEW sections — final batch).
        # Same pattern as the v3.57.14 overlays above: build dict from
        # operator inputs, filter empty values so `_deep_merge` preserves
        # defaults, then `.update()` onto a `setdefault()` dict so any
        # pre-existing keys survive alongside the new content.

        # 22) tenant_dashboard.workspace_context_tenant — `school_role`
        # writes into the helper's nested ``child.subline`` so the partial's
        # active-child-name + subline layout stays intact. ``scope_chips``
        # is a NEW key the partial may render alongside the existing
        # siblings/stats lists (which keep their defaults via _deep_merge).
        wct_overlay: dict[str, Any] = {}
        wct_label_v = (cleaned.get("wct_label") or "").strip()
        if wct_label_v:
            wct_overlay["label"] = wct_label_v
        wct_school_role = (cleaned.get("wct_school_role") or "").strip()
        if wct_school_role:
            wct_overlay["child"] = {"subline": wct_school_role}
        wct_chips = _parse_scope_chips(cleaned.get("wct_scope_chips") or "")
        if wct_chips:
            wct_overlay["scope_chips"] = wct_chips
        if wct_overlay:
            payload.setdefault("workspace_context_tenant", {}).update(wct_overlay)

        # 23) manager_200x.activity_ticker
        atk_overlay: dict[str, Any] = {}
        atk_label_v = (cleaned.get("atk_label") or "").strip()
        if atk_label_v:
            atk_overlay["label"] = atk_label_v
        atk_scroll = cleaned.get("atk_scroll_seconds")
        if atk_scroll is not None and atk_scroll != "":
            atk_overlay["scroll_seconds"] = atk_scroll
        atk_badge = (cleaned.get("atk_live_badge_label") or "").strip()
        if atk_badge:
            atk_overlay["live_badge_label"] = atk_badge
        atk_cards = _parse_activity_ticker_cards(cleaned.get("atk_cards") or "")
        if atk_cards:
            atk_overlay["cards"] = atk_cards
        # v3.58.x Wave 10 Agent Q — host-routing toggles persist under the
        # same activity_ticker section so a single cockpit_payload key holds
        # all ticker configuration. BooleanField is always cleaned to a real
        # bool; persist unconditionally so toggling OFF is durable (not just
        # the absence of the key falling back to the default).
        atk_overlay["enabled_on_manager"] = bool(
            cleaned.get("atk_enabled_on_manager")
        )
        atk_overlay["enabled_on_tenant"] = bool(
            cleaned.get("atk_enabled_on_tenant")
        )
        atk_overlay["realdata_enabled"] = bool(
            cleaned.get("atk_realdata_enabled")
        )
        manager_sources = list(cleaned.get("atk_manager_sources") or [])
        tenant_sources = list(cleaned.get("atk_tenant_sources") or [])
        atk_overlay["sources_enabled"] = {
            "manager": manager_sources,
            "tenant": tenant_sources,
        }
        manager_announcements = _parse_live_banner_announcements(
            cleaned.get("atk_manager_announcements") or ""
        )
        atk_overlay["announcements"] = manager_announcements
        if atk_overlay:
            payload.setdefault("activity_ticker", {}).update(atk_overlay)
        tat_overlay = payload.setdefault("tenant_activity_ticker", {})
        tat_overlay["enabled"] = bool(cleaned.get("atk_enabled_on_tenant"))
        tat_overlay["sources_enabled"] = tenant_sources
        tenant_announcements = _parse_live_banner_announcements(
            cleaned.get("atk_tenant_announcements") or ""
        )
        tat_overlay["announcements"] = tenant_announcements

        # 24) tenant_v3_extended.gradebook_trend
        gbt_overlay: dict[str, Any] = {}
        gbt_label_v = (cleaned.get("gbt_label") or "").strip()
        if gbt_label_v:
            gbt_overlay["title"] = gbt_label_v
        gbt_subjects = _parse_gradebook_subjects(cleaned.get("gbt_subjects") or "")
        if gbt_subjects:
            gbt_overlay["subjects"] = gbt_subjects
        if gbt_overlay:
            payload.setdefault("gradebook_trend", {}).update(gbt_overlay)

        # 25) tenant_v3_extended.attendance_heatmap
        ahm_overlay: dict[str, Any] = {}
        ahm_label_v = (cleaned.get("ahm_label") or "").strip()
        if ahm_label_v:
            ahm_overlay["title"] = ahm_label_v
        ahm_present_pct = (cleaned.get("ahm_present_pct") or "").strip()
        if ahm_present_pct:
            ahm_overlay["present_pct"] = ahm_present_pct
        ahm_cells = _parse_attendance_pattern(cleaned.get("ahm_pattern") or "")
        if ahm_cells:
            ahm_overlay["cells"] = ahm_cells
        if ahm_overlay:
            payload.setdefault("attendance_heatmap", {}).update(ahm_overlay)

        # 26) tenant_v3_extended.life_event_timeline
        let_overlay: dict[str, Any] = {}
        let_label_v = (cleaned.get("let_label") or "").strip()
        if let_label_v:
            let_overlay["title"] = let_label_v
        let_events = _parse_life_events(cleaned.get("let_events") or "")
        if let_events:
            let_overlay["events"] = let_events
        if let_overlay:
            payload.setdefault("life_event_timeline", {}).update(let_overlay)

        # v3.57.17 rich-editor overlay — final cockpit editor (closes the
        # ai_copilot_rail complexity deferral). Same forgiving overlay
        # pattern: build dict from operator inputs, filter empty values
        # so `_deep_merge` preserves defaults from the helper module, then
        # `.update()` onto a `setdefault()` dict so any pre-existing keys
        # (e.g. the `enabled` flag from the v3.57 cockpit fieldset's
        # `mgr_aic_enabled` toggle) survive alongside the new content.
        #
        # 27) manager_200x.ai_copilot_rail — multi-block: messages list +
        # suggestion-pill list + insight-pill fields. ``label`` and
        # ``subtitle`` are NOT in the helper defaults but are persisted
        # here for operator-editable forward-compat (partial ignores
        # unknown keys cleanly). ``insight_body`` writes into the helper's
        # ``insight_text`` key — the partial reads ``insight_text``
        # directly so the lead-sentence pill lights up.
        acr_overlay: dict[str, Any] = {}
        acr_label_v = (cleaned.get("acr_label") or "").strip()
        if acr_label_v:
            acr_overlay["label"] = acr_label_v
        acr_title_v = (cleaned.get("acr_title") or "").strip()
        if acr_title_v:
            acr_overlay["title"] = acr_title_v
        acr_subtitle_v = (cleaned.get("acr_subtitle") or "").strip()
        if acr_subtitle_v:
            acr_overlay["subtitle"] = acr_subtitle_v
        acr_messages = _parse_copilot_messages(cleaned.get("acr_messages") or "")
        if acr_messages:
            acr_overlay["messages"] = acr_messages
        acr_suggestions = _parse_copilot_suggestions(
            cleaned.get("acr_suggestions") or ""
        )
        if acr_suggestions:
            acr_overlay["suggested_actions"] = acr_suggestions
        acr_insight_icon = (cleaned.get("acr_insight_icon") or "").strip()
        if acr_insight_icon:
            acr_overlay["insight_icon"] = acr_insight_icon
        acr_insight_body = (cleaned.get("acr_insight_body") or "").strip()
        if acr_insight_body:
            acr_overlay["insight_text"] = acr_insight_body
        if acr_overlay:
            payload.setdefault("ai_copilot_rail", {}).update(acr_overlay)

        # v3.58.x Wave 9 — sibling-compare operator-editable copy overlay.
        # PRIVACY CONTRACT (load-bearing — DO NOT relax):
        #   - ``enabled`` flag IS written (operator-explicit round-trip).
        #   - Empty string fields are omitted so _deep_merge in
        #     cockpit_context.py preserves the defaults.
        #   - ``opt_in`` is NEVER written here. There is intentionally no
        #     ``opt_in_default`` field in this form. The cockpit cascade
        #     does not carry an ``opt_in`` value into the partial —
        #     ``opt_in`` is sourced from a per-parent consent record
        #     (per-family, outside cockpit_payload). Toggling ``enabled``
        #     surfaces the section CTA; parent consent is still required
        #     for any sibling data to render.
        sibling_overlay: dict[str, Any] = {
            "enabled": bool(cleaned.get("sct_enabled")),
        }
        sct_title = (cleaned.get("sct_title") or "").strip()
        if sct_title:
            sibling_overlay["title"] = sct_title
        sct_subtitle = (cleaned.get("sct_subtitle") or "").strip()
        if sct_subtitle:
            sibling_overlay["subtitle"] = sct_subtitle
        sct_cta_label = (cleaned.get("sct_cta_label") or "").strip()
        if sct_cta_label:
            sibling_overlay["cta_label"] = sct_cta_label
        sct_consent_banner_title = (
            cleaned.get("sct_consent_banner_title") or ""
        ).strip()
        if sct_consent_banner_title:
            sibling_overlay["consent_banner_title"] = sct_consent_banner_title
        sct_consent_banner_body = (
            cleaned.get("sct_consent_banner_body") or ""
        ).strip()
        if sct_consent_banner_body:
            sibling_overlay["consent_banner_body"] = sct_consent_banner_body
        sct_consent_grant = (
            cleaned.get("sct_consent_grant_button_label") or ""
        ).strip()
        if sct_consent_grant:
            sibling_overlay["consent_grant_button_label"] = sct_consent_grant
        sct_consent_decline = (
            cleaned.get("sct_consent_decline_button_label") or ""
        ).strip()
        if sct_consent_decline:
            sibling_overlay["consent_decline_button_label"] = sct_consent_decline
        sct_denied_state = (
            cleaned.get("sct_denied_state_message") or ""
        ).strip()
        if sct_denied_state:
            sibling_overlay["denied_state_message"] = sct_denied_state
        # ``sibling_compare`` may already exist from the v3.57.1 tenant_v3
        # enable-toggle loop (sets just {"enabled": ...}); .update() lets
        # this richer overlay's keys land on top while preserving any
        # forward-compatible keys that future operators add via JSON.
        payload.setdefault("sibling_compare", {}).update(sibling_overlay)

        # v3.58.x Wave 10 Agent S — trust pillars alerts overlay. Mirrors
        # cockpit.trust_pillars_alerts.* emitted by
        # ``_trust_pillars_alerts_defaults()`` in cockpit_manager_200x.py.
        # ``enabled`` is ALWAYS written so an explicit operator un-check
        # round-trips faithfully. Per-pillar label overrides land as a
        # pillars[] list of {slug,label} dicts; the orchestrator's
        # _deep_merge contract is "lists override wholesale", so we ONLY
        # publish pillars[] when at least one operator-typed label is
        # non-empty — otherwise the resolver's full 7-row defaults flow
        # through unmodified. Status/value are NEVER operator-typed (only
        # label) — those continue to come from the real-data resolver.
        tpa_overlay: dict[str, Any] = {
            "enabled": bool(cleaned.get("tpa_enabled")),
        }
        tpa_title = (cleaned.get("tpa_title") or "").strip()
        if tpa_title:
            tpa_overlay["title"] = tpa_title
        tpa_title_em = (cleaned.get("tpa_title_em") or "").strip()
        if tpa_title_em:
            tpa_overlay["title_em"] = tpa_title_em
        tpa_footer = (cleaned.get("tpa_footer_text") or "").strip()
        if tpa_footer:
            tpa_overlay["footer_text"] = tpa_footer
        pillar_label_overrides: list[dict[str, str]] = []
        for slug in (
            "audit_chain",
            "maa_signatures",
            "encryption_at_rest",
            "ferpa_retention",
            "webhook_signing",
            "mfa_enforcement",
            "companion_handshake",
        ):
            label_val = (cleaned.get(f"tpa_label_{slug}") or "").strip()
            if label_val:
                pillar_label_overrides.append({"slug": slug, "label": label_val})
        if pillar_label_overrides:
            tpa_overlay["pillars"] = pillar_label_overrides
        payload["trust_pillars_alerts"] = tpa_overlay

        # v3.57.18 Wave 8 — public school-signup form overlay. Mirrors
        # cockpit.signup_form.* emitted by ``_signup_form_defaults()`` in
        # cockpit_context.py. Unlike the other v3.57.x rich-editor overlays
        # this section's ``enabled`` flag is ALWAYS written (operator-explicit
        # round-trip), and the two ``show_*`` booleans are ALSO always
        # written so an unchecked operator state survives the round-trip
        # (otherwise _deep_merge would re-apply the True default). Empty
        # string fields are omitted so _deep_merge preserves defaults.
        signup_overlay: dict[str, Any] = {
            "enabled": bool(cleaned.get("signup_form_enabled")),
            "show_trust_pills": bool(cleaned.get("signup_form_show_trust_pills")),
            "show_calendar_cards": bool(
                cleaned.get("signup_form_show_calendar_cards")
            ),
        }
        signup_heading = (cleaned.get("signup_form_heading") or "").strip()
        if signup_heading:
            signup_overlay["heading"] = signup_heading
        signup_subheading = (cleaned.get("signup_form_subheading") or "").strip()
        if signup_subheading:
            signup_overlay["subheading"] = signup_subheading
        signup_button = (cleaned.get("signup_form_button_label") or "").strip()
        if signup_button:
            signup_overlay["button_label"] = signup_button
        signup_pills = _parse_trust_pill_lines(
            cleaned.get("signup_form_trust_pill_lines") or ""
        )
        if signup_pills:
            signup_overlay["trust_pill_lines"] = signup_pills
        signup_login_label = (
            cleaned.get("signup_form_footer_login_label") or ""
        ).strip()
        if signup_login_label:
            signup_overlay["footer_login_label"] = signup_login_label
        signup_login_url = (
            cleaned.get("signup_form_footer_login_url") or ""
        ).strip()
        if signup_login_url:
            signup_overlay["footer_login_url"] = signup_login_url
        payload["signup_form"] = signup_overlay

        lic_overlay: dict[str, Any] = {
            "enabled": bool(cleaned.get("lic_enabled")),
            "pro_enabled": bool(cleaned.get("lic_pro_enabled")),
            "zones": {
                "show_ticker": bool(cleaned.get("lic_show_ticker")),
                "show_bento": bool(cleaned.get("lic_show_bento")),
                "show_feed": bool(cleaned.get("lic_show_feed")),
                "show_gallery": bool(cleaned.get("lic_show_gallery")),
                "show_trust": bool(cleaned.get("lic_show_trust")),
                "compact_on_short_viewport": bool(cleaned.get("lic_compact_viewport")),
            },
        }
        layout = (cleaned.get("lic_layout_preset") or "").strip()
        if layout:
            lic_overlay["layout_preset"] = layout
        theme = (cleaned.get("lic_theme_variant") or "").strip()
        if theme:
            lic_overlay["theme_variant"] = theme
        hero_overlay: dict[str, Any] = {
            "mode": (cleaned.get("lic_hero_mode") or "carousel").strip(),
            "full_bleed": bool(cleaned.get("lic_hero_full_bleed")),
        }
        scroll_sec = cleaned.get("lic_hero_scroll_seconds")
        if scroll_sec is not None:
            hero_overlay["scroll_seconds"] = int(scroll_sec)
        hero_slides = _parse_lic_hero_slides(cleaned.get("lic_hero_slides_lines") or "")
        if hero_slides:
            hero_overlay["slides"] = hero_slides
        lic_overlay["hero_banner"] = hero_overlay
        gallery_items = _parse_lic_gallery_lines(cleaned.get("lic_gallery_lines") or "")
        if gallery_items:
            lic_overlay["gallery"] = {"enabled": True, "items": gallery_items}
        metric_keys_raw = (cleaned.get("lic_metric_tile_keys") or "").strip()
        if metric_keys_raw:
            lic_overlay["metrics"] = {
                "enabled": True,
                "tile_keys": [
                    k.strip()
                    for k in metric_keys_raw.replace("\n", ",").split(",")
                    if k.strip()
                ][:4],
            }
        monetization_overlay: dict[str, Any] = {
            "allow_sponsored_slot": bool(cleaned.get("lic_allow_sponsored_slot")),
            "hide_when_offline": bool(cleaned.get("lic_hide_sponsored_offline")),
            "max_visible": cleaned.get("lic_sponsored_max_visible")
            if cleaned.get("lic_sponsored_max_visible") is not None
            else 1,
        }
        sponsored = _parse_lic_sponsored_lines(cleaned.get("lic_sponsored_lines") or "")
        if sponsored:
            monetization_overlay["sponsored_slots"] = sponsored
        lic_overlay["monetization"] = monetization_overlay
        feed_label = (cleaned.get("lic_feed_section_label") or "").strip()
        dash_title = (cleaned.get("lic_dash_title") or "").strip()
        feed_overlay: dict[str, Any] = {}
        if feed_label:
            feed_overlay["section_label"] = feed_label
        if dash_title:
            feed_overlay["dash_title"] = dash_title
        if feed_overlay:
            lic_overlay["feed"] = feed_overlay
        trust_chips = _parse_lic_trust_chip_lines(
            cleaned.get("lic_trust_chip_lines") or ""
        )
        if trust_chips:
            lic_overlay["trust_chips"] = trust_chips
        role_preview_overlay: dict[str, Any] = {}
        for role_key, field_name in (
            ("staff", "lic_role_preview_staff"),
            ("parent", "lic_role_preview_parent"),
            ("student", "lic_role_preview_student"),
            ("default", "lic_role_preview_default"),
        ):
            pill = (cleaned.get(field_name) or "").strip()
            if pill:
                role_preview_overlay[role_key] = {"pill": pill}
        if role_preview_overlay:
            lic_overlay["role_preview"] = role_preview_overlay
        dash_overlay: dict[str, Any] = {}
        for role_key, field_name in (
            ("staff", "lic_dash_staff_note"),
            ("parent", "lic_dash_parent_note"),
            ("student", "lic_dash_student_note"),
        ):
            note = (cleaned.get(field_name) or "").strip()
            if note:
                dash_overlay[role_key] = {"note": note}
        if dash_overlay:
            lic_overlay["dash_preview"] = dash_overlay
        payload["login_immersive_canvas"] = lic_overlay

        return payload

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        from apps.accounts.login_immersive_canvas import login_canvas_pro_enabled

        request = getattr(self, "configure_request", None)
        pro_section = {"pro_enabled": bool(cleaned.get("lic_pro_enabled"))}
        pro_entitled = (
            login_canvas_pro_enabled(request, pro_section) if request is not None else False
        )
        hero_mode = str(cleaned.get("lic_hero_mode") or "carousel").strip().lower()
        if hero_mode in {"marquee", "hybrid"} and not pro_entitled:
            self.add_error(
                "lic_hero_mode",
                _("Marquee and hybrid hero modes require Login canvas Pro."),
            )
        if cleaned.get("lic_allow_sponsored_slot") and not pro_entitled:
            self.add_error(
                "lic_allow_sponsored_slot",
                _("Sponsored hero slots require Login canvas Pro."),
            )
        payload = self._build_payload(cleaned)
        cleaned["cockpit_payload"] = payload
        # Phase B: cockpit_payload is persisted by the owning view via
        # SiteSettings.set_cockpit_payload(cleaned_data["cockpit_payload"]);
        # the column no longer exists, so no model-instance mirror is needed.
        return cleaned


# Back-compat alias: a few callers prefer the more explicit name.
SiteSettingsCockpitForm = CockpitPayloadForm
