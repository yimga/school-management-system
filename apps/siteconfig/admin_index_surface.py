"""
Live context for manager /admin/ index surface previews (changelist, changeform sidecar).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.contrib.admin.models import LogEntry
from django.contrib.contenttypes.models import ContentType
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


def _rev(url_name: str, *args) -> str | None:
    try:
        return reverse(url_name, args=args)
    except NoReverseMatch:
        return None


def _compute_nps_window(*, since, until) -> dict[str, Any]:
    from apps.feedback.models import SurveyResponse

    # tenant-isolation-allow: operator-platform-wide-nps-aggregation-cross-tenant-by-design
    qs = SurveyResponse.objects.filter(
        survey_type=SurveyResponse.SurveyType.NPS,
        created_at__gte=since,
        created_at__lt=until,
    )
    total = qs.count()
    if not total:
        return {
            "total": 0,
            "nps": None,
            "promoters": 0,
            "passives": 0,
            "detractors": 0,
        }
    promoters = qs.filter(score__gte=9).count()
    passives = qs.filter(score__gte=7, score__lte=8).count()
    detractors = qs.filter(score__lte=6).count()
    nps = round(100.0 * (promoters - detractors) / total)
    return {
        "total": total,
        "nps": nps,
        "promoters": promoters,
        "passives": passives,
        "detractors": detractors,
    }


def build_admin_preview_nps_metric() -> dict[str, Any]:
    """Rolling 30d parent NPS — same shape operators see on school change-form sidecars."""
    now = timezone.now()
    current_start = now - timedelta(days=30)
    prior_start = now - timedelta(days=60)
    try:
        current = _compute_nps_window(since=current_start, until=now)
        prior = _compute_nps_window(since=prior_start, until=current_start)
    except Exception:
        return {
            "eyebrow": str(_("Parent NPS · rolling 30d")),
            "score_display": "—",
            "score_tone": "muted",
            "delta_text": "",
            "delta_tone": "flat",
            "response_count": 0,
            "breakdown": [],
            "sparkline": [],
            "caption": str(_("Survey data unavailable.")),
        }

    total = current["total"]
    breakdown: list[dict[str, str]] = []
    if total:
        for label, key, kind in (
            (_("Promoters"), "promoters", "promoters"),
            (_("Passives"), "passives", "passives"),
            (_("Detractors"), "detractors", "detractors"),
        ):
            count = current[key]
            pct = round(100.0 * count / total)
            breakdown.append(
                {
                    "label": str(label),
                    "count": str(count),
                    "pct": f"{pct}%",
                    "kind": kind,
                }
            )

    nps = current["nps"]
    score_display = str(nps) if nps is not None else "—"
    if nps is None:
        score_tone = "muted"
    elif nps >= 50:
        score_tone = "success"
    elif nps >= 0:
        score_tone = "warn"
    else:
        score_tone = "danger"

    delta_text = ""
    delta_tone = "flat"
    if nps is not None and prior["nps"] is not None:
        delta = nps - prior["nps"]
        if delta > 0:
            delta_tone = "up"
            delta_text = str(_("+%(delta)s vs prior 30d") % {"delta": delta})
        elif delta < 0:
            delta_tone = "down"
            delta_text = str(_("%(delta)s vs prior 30d") % {"delta": delta})
        else:
            delta_text = str(_("Flat vs prior 30d"))

    sparkline: list[dict[str, Any]] = []
    if total:
        try:
            from apps.feedback.models import SurveyResponse

            for day_offset in range(6, -1, -1):
                day_end = (now - timedelta(days=day_offset)).replace(
                    hour=23, minute=59, second=59, microsecond=999999
                )
                day_start = day_end.replace(hour=0, minute=0, second=0, microsecond=0)
                # tenant-isolation-allow: operator-platform-wide-nps-sparkline-cross-tenant-by-design
                count = SurveyResponse.objects.filter(
                    survey_type=SurveyResponse.SurveyType.NPS,
                    created_at__gte=day_start,
                    created_at__lte=day_end,
                ).count()
                sparkline.append({"label": day_start.strftime("%a"), "count": count})
            peak = max((b["count"] for b in sparkline), default=1) or 1
            for bar in sparkline:
                bar["height_pct"] = max(8, round(100.0 * bar["count"] / peak))
        except Exception:
            sparkline = []

    caption = (
        str(
            _("%(count)s parent responses in the last 30 days — platform aggregate.")
            % {"count": total}
        )
        if total
        else str(
            _(
                "Sparklines and trend deltas appear when parents submit portal surveys."
            )
        )
    )

    return {
        "eyebrow": str(_("Parent NPS · rolling 30d")),
        "score_display": score_display,
        "score_tone": score_tone,
        "delta_text": delta_text,
        "delta_tone": delta_tone,
        "response_count": total,
        "breakdown": breakdown,
        "sparkline": sparkline,
        "caption": caption,
    }


def build_admin_preview_audit_rows(*, limit: int = 4) -> list[dict[str, str]]:
    from apps.schools.models import School

    try:
        ct = ContentType.objects.get_for_model(School)
        rows = (
            LogEntry.objects.filter(content_type=ct)
            .select_related("user")
            .order_by("-action_time")[:limit]
        )
    except Exception:
        return []

    out: list[dict[str, str]] = []
    for entry in rows:
        actor = getattr(entry.user, "username", None) or _("system")
        summary = entry.object_repr or _("School record")
        out.append(
            {
                "summary": str(summary)[:80],
                "meta": str(_("%(action)s by %(actor)s") % {"action": entry.get_action_flag_display(), "actor": actor}),
                "tone": "info" if entry.action_flag == LogEntry.CHANGE else "success",
            }
        )
    return out


def build_admin_preview_school_rows(*, limit: int = 5) -> tuple[list[dict[str, Any]], int]:
    from apps.schools.models import School

    try:
        qs = School.objects.order_by("-created_at").only(
            "id", "name", "slug", "is_active", "created_at"
        )
        total = qs.count()
        rows: list[dict[str, Any]] = []
        for school in qs[:limit]:
            change_url = _rev("admin:schools_school_change", str(school.pk))
            rows.append(
                {
                    "name": school.name,
                    "slug": school.slug,
                    "status_label": _("Active") if school.is_active else _("Inactive"),
                    "status_tone": "success" if school.is_active else "muted",
                    "change_url": change_url,
                }
            )
        return rows, total
    except Exception:
        return [], 0


def build_admin_preview_related_links() -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    pairs = [
        ("siteconfig:console_domains_hub", _("Site settings"), None),
        ("super:dashboard", _("Control plane"), None),
        ("migration_cloud_super:migration_cloud_command_center", _("Migration runs"), None),
    ]
    for url_name, label, count in pairs:
        url = _rev(url_name)
        if url:
            links.append({"label": str(label), "url": url, "count": count})

    try:
        from apps.migration_cloud.models import MigrationCloudBundle

        migration_url = _rev("migration_cloud_super:migration_cloud_command_center")
        if migration_url:
            run_count = MigrationCloudBundle.objects.count()
            links = [l for l in links if l["label"] != str(_("Migration runs"))]
            links.append(
                {
                    "label": str(_("Migration runs")),
                    "url": migration_url,
                    "count": run_count if run_count else None,
                }
            )
    except Exception:
        pass

    return links


def empty_admin_index_surface() -> dict[str, Any]:
    return {
        "school_count": 0,
        "school_rows": [],
        "school_total": 0,
        "sample_school": None,
        "nps_metric": build_admin_preview_nps_metric(),
        "audit_rows": [],
        "related_links": build_admin_preview_related_links(),
        "changelist_pager_label": str(_("1–25 of N")),
    }


def build_admin_index_surface_context() -> dict[str, Any]:
    """Bundle for admin/index_superadmin.html surface preview sections."""
    schools, school_total = build_admin_preview_school_rows(limit=5)
    sample = schools[0] if schools else None
    nps = build_admin_preview_nps_metric()
    audit = build_admin_preview_audit_rows()
    if not audit and sample:
        audit = [
            {
                "summary": str(_("Sample school ready for edit")),
                "meta": str(_("Open changelist for full audit trail")),
                "tone": "info",
            }
        ]

    return {
        "school_count": school_total,
        "school_rows": schools,
        "school_total": school_total,
        "sample_school": sample,
        "nps_metric": nps,
        "audit_rows": audit,
        "related_links": build_admin_preview_related_links(),
        "changelist_pager_label": (
            str(_("1–%(shown)s of %(total)s") % {"shown": min(25, school_total), "total": school_total})
            if school_total
            else str(_("1–25 of N"))
        ),
    }
