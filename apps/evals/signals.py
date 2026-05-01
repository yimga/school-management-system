"""Signals for automatic audit trail and grade conversion."""

import logging

from django.core.exceptions import ValidationError
from django.db import DatabaseError, IntegrityError
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from decimal import Decimal

from apps.evals.models import Evaluation, GradeAudit, OfflineMarkEntry
from apps.evals.ranking import RankingCache
from apps.evals.validators import GradeConverter, GradeValidator
from apps.platform_runtime.structured_logging import log_exception_with_context

logger = logging.getLogger(__name__)

# §2.4 Typed exceptions for audit trail paths (no broad except).
_EVALS_AUDIT_FAILURES = (
    DatabaseError,
    IntegrityError,
    ValidationError,
    AttributeError,
    TypeError,
    ValueError,
)


@receiver(pre_save, sender=Evaluation)
def capture_evaluation_before_save(sender, instance, **kwargs):
    """Store previous values before save for audit trail."""
    try:
        previous = Evaluation.objects.get(pk=instance.pk)
        instance._previous_values = {
            "seq1": previous.seq1_score,
            "seq2": previous.seq2_score,
            "exam": previous.exam_score,
            "mock": previous.mock_score,
            "practical": previous.practical_score,
            "remarks": previous.remarks,
        }
    except Evaluation.DoesNotExist:
        instance._previous_values = None


@receiver(post_save, sender=Evaluation)
def create_audit_trail_and_convert_grades(sender, instance, created, **kwargs):
    """
    1. Create GradeAudit entry
    2. Validate grade
    3. Convert numeric to letter grade
    """
    try:
        # Determine change type (allow overriding from the view)
        change_type = getattr(instance, "_audit_change_type", None)
        if not change_type:
            change_type = "create" if created else "update"
        prev = instance._previous_values or {}

        seq1_before = prev.get("seq1") if not created else None
        seq2_before = prev.get("seq2") if not created else None
        exam_before = prev.get("exam") if not created else None
        mock_before = prev.get("mock") if not created else None
        practical_before = prev.get("practical") if not created else None
        remarks_before = prev.get("remarks") if not created else None

        # Validate grade
        from apps.evals.models import AssessmentWeights

        weights = AssessmentWeights.get_for(
            instance.academic_year,
            instance.subject_assignment.classroom
            if instance.subject_assignment
            else None,
            instance.term,
        )

        validator = GradeValidator(score_scale=Decimal(weights.score_scale))
        validation_result = validator.validate_evaluation(instance, weights)

        # Update instance with validation results
        instance.validation_flags = validation_result["flags"]
        instance.last_validated_at = timezone.now()

        # Convert to letter grade
        converter = GradeConverter(weights)
        if instance.total_score:
            instance.letter_grade = converter.numeric_to_letter(instance.total_score)

        # Save validation without triggering signal again
        Evaluation.objects.filter(pk=instance.pk).update(
            validation_flags=instance.validation_flags,
            letter_grade=instance.letter_grade,
            last_validated_at=instance.last_validated_at,
        )

        # Create audit trail
        GradeAudit.objects.create(
            evaluation=instance,
            changed_by=instance.teacher.user if instance.teacher else None,
            change_type=change_type,
            seq1_before=seq1_before,
            seq1_after=instance.seq1_score,
            seq2_before=seq2_before,
            seq2_after=instance.seq2_score,
            exam_before=exam_before,
            exam_after=instance.exam_score,
            mock_before=mock_before,
            mock_after=instance.mock_score,
            practical_before=practical_before,
            practical_after=instance.practical_score,
            remarks_before=remarks_before,
            remarks_after=instance.remarks,
            validation_errors=validation_result["errors"],
        )

        logger.info(f"Audit trail created for evaluation {instance.id}")

    except _EVALS_AUDIT_FAILURES as e:
        school_id = None
        if getattr(instance, "subject_assignment", None) and getattr(
            instance.subject_assignment, "classroom", None
        ):
            school_id = str(
                getattr(instance.subject_assignment.classroom, "school_id", None)
            )
        log_exception_with_context(
            "evals.signals: create_audit_trail failed",
            school_id=school_id,
            extra={"evaluation_id": getattr(instance, "pk", None), "error": str(e)},
        )
        logger.error("Failed to create audit trail: %s", e, exc_info=True)


def _invalidate_ranking_cache(term, classroom):
    """Invalidate both class and school rankings for the provided context."""
    if not term:
        return
    RankingCache.invalidate(term, classroom)


@receiver(post_save, sender=Evaluation)
@receiver(post_delete, sender=Evaluation)
def invalidate_rankings_on_evaluation_change(sender, instance, **kwargs):
    """Ensure cached rankings reflect the latest grades."""
    classroom = getattr(instance.subject_assignment, "classroom", None)
    _invalidate_ranking_cache(instance.term, classroom)


@receiver(post_save, sender=OfflineMarkEntry)
def invalidate_rankings_for_offline_entry(sender, instance, created, **kwargs):
    """Invalidate rankings when offline marks sync."""
    classroom = getattr(instance.subject_assignment, "classroom", None)
    _invalidate_ranking_cache(instance.term, classroom)


@receiver(post_save, sender=OfflineMarkEntry)
def handle_offline_sync_complete(sender, instance, created, **kwargs):
    """When offline entry synced, flag in audit trail."""
    if instance.status == "synced" and instance.synced_at:
        try:
            eval_obj = (
                instance.conflict_with_evaluation
                if instance.conflict_with_evaluation
                else None
            )
            if not eval_obj:
                # Try to find evaluation created from this offline entry
                try:
                    eval_obj = Evaluation.objects.get(
                        academic_year=instance.academic_year,
                        term=instance.term,
                        subject_assignment=instance.subject_assignment,
                        student=instance.student,
                    )
                except Evaluation.DoesNotExist:
                    return

            GradeAudit.objects.create(
                evaluation=eval_obj,
                changed_by=instance.synced_by,
                change_type="offline_sync",
                offline_conflict_resolved=instance.offline_conflict_resolved,
                conflict_resolution_note=instance.conflict_resolution_note,
            )
        except _EVALS_AUDIT_FAILURES as e:
            log_exception_with_context(
                e,
                logger,
                "evals.signals.handle_offline_sync_complete",
                offline_entry_id=getattr(instance, "pk", None),
            )


def _evaluation_has_substantive_scores(instance: Evaluation) -> bool:
    for fname in (
        "seq1_score",
        "seq2_score",
        "exam_score",
        "mock_score",
        "practical_score",
        "internship_score",
        "test1",
        "test2",
    ):
        if getattr(instance, fname, None) is not None:
            return True
    return False


@receiver(post_save, sender=Evaluation)
def conversion_first_action_on_marks_saved(sender, instance, **kwargs):
    if not _evaluation_has_substantive_scores(instance):
        return
    school = getattr(instance, "school", None)
    if school is None:
        classroom = getattr(
            getattr(instance, "subject_assignment", None), "classroom", None
        )
        school = getattr(classroom, "school", None)
    if not school:
        return
    try:
        from apps.schools.conversion_lock_state import record_conversion_first_action

        record_conversion_first_action(
            school, source="marks_saved", request=None, user=None
        )
    except _EVALS_AUDIT_FAILURES as exc:
        logger.debug("conversion_first_action_on_marks_saved: %s", exc)


@receiver(post_save, sender=Evaluation)
def dispatch_grade_submitted_workflows(sender, instance, created, **kwargs):
    """School automation: grade_submitted trigger (non-blocking)."""
    classroom = getattr(
        getattr(instance, "subject_assignment", None), "classroom", None
    )
    school = getattr(classroom, "school", None) if classroom else None
    if not school:
        return
    try:
        from apps.siteconfig.workflow_triggers import dispatch_domain_triggers_safe

        payload = {
            "evaluation_id": instance.pk,
            "student_id": getattr(instance, "student_id", None),
            "subject_assignment_id": getattr(instance, "subject_assignment_id", None),
            "created": created,
            "total_score": str(instance.total_score)
            if getattr(instance, "total_score", None) is not None
            else None,
        }
        dispatch_domain_triggers_safe(school, "grade_submitted", payload)
        dispatch_domain_triggers_safe(school, "marks_submitted", payload)
    except ImportError:
        pass


@receiver(post_save, sender=Evaluation)
def emit_marks_submitted_platform_event(sender, instance, **kwargs):
    """Platform event bus: marks_submitted for workflows, webhooks, analytics."""
    if not _evaluation_has_substantive_scores(instance):
        return
    classroom = getattr(
        getattr(instance, "subject_assignment", None), "classroom", None
    )
    school = getattr(instance, "school", None) or (
        getattr(classroom, "school", None) if classroom else None
    )
    if not school:
        return
    try:
        from apps.platform_runtime.event_bus import publish_event

        tid = str(school.pk)
        publish_event(
            "marks_submitted",
            {
                "evaluation_id": instance.pk,
                "student_id": str(instance.student_id),
                "school_id": tid,
                "subject_assignment_id": instance.subject_assignment_id,
                "term_id": instance.term_id,
                "source": "evals.signals",
            },
            tenant_id=tid,
            school_id=school.pk,
            idempotency_key=(
                f"marks_submitted:{instance.pk}:{instance.updated_at.isoformat()}"
            )[:128],
        )
    except (_EVALS_AUDIT_FAILURES + (ImportError,)) as exc:
        logger.debug("emit_marks_submitted_platform_event: %s", exc)
