"""Markdown builder for operator fleet status reports (ODT/PDF export source)."""
from __future__ import annotations

from django.utils import timezone

from apps.schools.control_plane_lifecycle import batch_current_subscriptions
from apps.schools.fleet_status import (
    build_fleet_queryset,
    format_fleet_summary_label,
    resolve_fleet_summary,
    resolve_school_fleet_status,
)


def build_fleet_status_markdown() -> str:
    schools = list(build_fleet_queryset())
    summary = resolve_fleet_summary(schools)
    subs = batch_current_subscriptions(schools)
    now = timezone.now().strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        "# RunMyCampus Fleet Status Report",
        "",
        f"**Generated:** {now}",
        "",
        "## Fleet summary",
        "",
        f"- **Total schools:** {summary.get('total', 0)}",
        f"- **Live:** {summary.get('live', 0)}",
        f"- **Watch:** {summary.get('watch', 0)}",
        f"- **Critical:** {summary.get('critical', 0)}",
        f"- **Inactive:** {summary.get('idle', 0)}",
        "",
        f"_{format_fleet_summary_label(summary)}_",
        "",
        "## Schools",
        "",
        "| School | Slug | Fleet status | Tier | Active | Approved |",
        "| --- | --- | --- | --- | --- | --- |",
    ]

    for school in schools:
        row = resolve_school_fleet_status(school, cached_subscription=subs.get(school.pk))
        lines.append(
            "| {name} | {slug} | {status} | {tier} | {active} | {approved} |".format(
                name=(getattr(school, "name", "") or "—").replace("|", "/"),
                slug=(getattr(school, "slug", "") or "—").replace("|", "/"),
                status=row.get("fleet_state_label") or "—",
                tier=row.get("heatmap_tier") or "—",
                active="Yes" if row.get("is_active") else "No",
                approved="Yes" if row.get("is_approved") else "No",
            )
        )

    lines.extend(["", "---", "", "*RunMyCampus operator fleet monitoring export*"])
    return "\n".join(lines)
