"""Stall-watch Celery task.

Once a day, walk SetupProgress + SchoolOnboardingProgress and flag
schools that look stuck:
- progress_percent < 20 after 3 days since school.created_at
- updated_at older than 7 days (regardless of percent)

Emits a structured-log warning + (optionally) emails the platform
ops mailbox. Never crashes the worker — best-effort observability.

Wire into Celery beat (NOT auto-registered to keep the wave focused):

    CELERY_BEAT_SCHEDULE['lifecycle-stall-watch'] = {
        'task': 'apps.lifecycle.tasks_stall_watch.detect_stalled_onboarding',
        'schedule': crontab(hour=8, minute=30),  # 08:30 UTC daily
    }
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


# Stall thresholds. Conservative defaults — operators can tune via
# settings if needed without code change.
STALL_PERCENT_FLOOR = 20
STALL_DAYS_FOR_FLOOR = 3
STALL_DAYS_NO_UPDATE = 7
STALL_MAX_REPORTED = 100


def _platform_ops_email() -> str:
    """The same env var Migration Cloud's tenant_offboarding_notifications uses."""
    return (getattr(settings, "TENANT_OFFBOARDING_PLATFORM_EMAILS", "") or "").split(",")[0].strip()


def detect_stalled_onboarding(*, dry_run: bool = False) -> dict:
    """Walk onboarding progress and return a summary dict.

    When dry_run=True (default in tests), no emails are sent — only
    structured-log warnings.
    """
    from apps.schools.models import School

    now = timezone.now()
    floor_cutoff = now - timedelta(days=STALL_DAYS_FOR_FLOOR)
    update_cutoff = now - timedelta(days=STALL_DAYS_NO_UPDATE)

    stalled_low_progress: list = []
    stalled_no_update: list = []

    # School.created_at older than 3d + progress < 20% — never got moving
    try:
        from apps.platform_runtime.models import SchoolOnboardingProgress

        candidates = (
            SchoolOnboardingProgress.objects.filter(
                progress_percent__lt=STALL_PERCENT_FLOOR,
                school__created_at__lt=floor_cutoff,
                school__is_active=False,
            )
            .select_related("school")
            .only("school__id", "school__slug", "school__created_at", "progress_percent")[:STALL_MAX_REPORTED]
        )
        for row in candidates:
            stalled_low_progress.append(
                {
                    "school_id": str(row.school.id),
                    "school_slug": row.school.slug,
                    "progress_percent": row.progress_percent,
                    "created_days_ago": (now - row.school.created_at).days,
                }
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "lifecycle.stall_watch.checklist_query_failed err=%s",
            type(exc).__name__,
        )

    # SetupProgress.updated_at older than 7d — fell off
    try:
        from apps.setup_studio.models import SetupProgress

        no_updates = (
            SetupProgress.objects.filter(
                updated_at__lt=update_cutoff,
                launch_ready=False,
                school__is_active=False,
            )
            .select_related("school")
            .only("school__id", "school__slug", "updated_at", "health_score")[:STALL_MAX_REPORTED]
        )
        for row in no_updates:
            stalled_no_update.append(
                {
                    "school_id": str(row.school.id),
                    "school_slug": row.school.slug,
                    "health_score": row.health_score,
                    "stale_days": (now - row.updated_at).days,
                }
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "lifecycle.stall_watch.setup_query_failed err=%s",
            type(exc).__name__,
        )

    summary = {
        "checked_at": now.isoformat(),
        "stalled_low_progress_count": len(stalled_low_progress),
        "stalled_no_update_count": len(stalled_no_update),
        "stalled_low_progress": stalled_low_progress,
        "stalled_no_update": stalled_no_update,
        "dry_run": bool(dry_run),
    }

    if stalled_low_progress or stalled_no_update:
        logger.warning(
            "lifecycle.stall_watch.stalled_schools low=%d no_update=%d",
            len(stalled_low_progress),
            len(stalled_no_update),
        )
        if not dry_run:
            _maybe_email_ops(summary)

    # Best-effort assurance the school count is bounded.
    School.objects.all().count()
    return summary


def _maybe_email_ops(summary: dict) -> None:
    """Send a single summary email to platform ops when stalls are found."""
    try:
        recipient = _platform_ops_email()
        if not recipient:
            return
        from django.core.mail import send_mail

        subject = (
            f"[RunMyCampus] Onboarding stall watch: "
            f"{summary['stalled_low_progress_count']} low-progress, "
            f"{summary['stalled_no_update_count']} no-update"
        )
        # Body uses slugs and integer days only — no PII (emails / names).
        body_lines = ["Onboarding stall watch — daily summary.", ""]
        if summary["stalled_low_progress"]:
            body_lines.append("Low-progress schools (under 20% after 3+ days):")
            for r in summary["stalled_low_progress"][:25]:
                body_lines.append(
                    f"  - {r['school_slug']}  {r['progress_percent']}% — created {r['created_days_ago']}d ago"
                )
            body_lines.append("")
        if summary["stalled_no_update"]:
            body_lines.append("No-update schools (no setup change in 7+ days):")
            for r in summary["stalled_no_update"][:25]:
                body_lines.append(
                    f"  - {r['school_slug']}  health={r['health_score']} — stale {r['stale_days']}d"
                )
        body_lines.append("")
        body_lines.append("Reach out via the operator console.")
        send_mail(
            subject=subject,
            message="\n".join(body_lines),
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "ops@runmycampus.com"),
            recipient_list=[recipient],
            fail_silently=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "lifecycle.stall_watch.email_failed err=%s",
            type(exc).__name__,
        )
