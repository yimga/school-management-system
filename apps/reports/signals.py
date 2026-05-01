"""Report lifecycle hooks (conversion funnel, first-result markers)."""

from __future__ import annotations

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.reports.models import ReportCard

logger = logging.getLogger(__name__)


@receiver(post_save, sender=ReportCard)
def conversion_first_action_on_report_generated(sender, instance, **kwargs):
    """When a PDF-backed report card exists, treat as explicit report output."""
    try:
        if not instance.pdf_file:
            return
        school = instance.school
        if school is None and getattr(instance, "student_id", None):
            st = getattr(instance, "student", None)
            school = getattr(st, "school", None) if st else None
        if not school:
            return
        from apps.schools.conversion_lock_state import record_conversion_first_action

        record_conversion_first_action(
            school, source="report_generated", request=None, user=None
        )
    except Exception as exc:
        logger.debug("conversion_first_action_on_report_generated: %s", exc)


@receiver(post_save, sender=ReportCard)
def funnel_first_result_on_report_output(sender, instance, **kwargs):
    if not instance.pdf_file:
        return
    school = instance.school
    if school is None and getattr(instance, "student_id", None):
        st = getattr(instance, "student", None)
        school = getattr(st, "school", None) if st else None
    if not school:
        return
    try:
        from apps.schools.funnel_events import try_record_first_result_report_output

        try_record_first_result_report_output(
            school, report_card_id=getattr(instance, "pk", None)
        )
    except Exception as exc:
        logger.debug("funnel_first_result_on_report_output: %s", exc)


@receiver(post_save, sender=ReportCard)
def emit_report_generated_platform_event(sender, instance, **kwargs):
    """Platform event bus when a PDF-backed report card row exists."""
    if not instance.pdf_file:
        return
    school = instance.school
    if school is None and getattr(instance, "student_id", None):
        st = getattr(instance, "student", None)
        school = getattr(st, "school", None) if st else None
    if not school:
        return
    try:
        from apps.platform_runtime.event_bus import publish_event

        tid = str(school.pk)
        publish_event(
            "report_generated",
            {
                "report_card_id": instance.pk,
                "school_id": tid,
                "student_id": str(instance.student_id),
                "source": "report_card_pdf",
            },
            tenant_id=tid,
            school_id=school.pk,
            idempotency_key=f"report_generated:{instance.pk}"[:128],
        )
    except Exception as exc:
        logger.debug("emit_report_generated_platform_event: %s", exc)
