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

        return {
            "footer": footer,
            "community_band": community,
            "newsletter_band": newsletter,
        }

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
