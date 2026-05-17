"""Offline sync conflict resolution service. §2.4: Typed exception tuple for manual resolve (no broad except)."""

import logging

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.evals.models import Evaluation, OfflineMarkEntry
from apps.siteconfig.config_service import get_effective_site_settings
from apps.platform_runtime.structured_logging import log_exception_with_context

logger = logging.getLogger(__name__)

# §2.4: Typed tuple for resolve_conflict_manually save/merge path.
_OFFLINE_SYNC_RESOLVE_ERRORS = (
    ValueError,
    TypeError,
    AttributeError,
    KeyError,
    IntegrityError,
)


class OfflineSyncService:
    """Handles conflict resolution for offline mark entries."""

    @staticmethod
    @transaction.atomic
    def sync_offline_entry(offline_entry: OfflineMarkEntry, teacher=None):
        """
        Sync offline entry to Evaluation.
        Returns (success: bool, message: str)
        """

        # Check for existing evaluation (conflict)
        try:
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            existing_eval = Evaluation.objects.get(
                academic_year=offline_entry.academic_year,
                term=offline_entry.term,
                subject_assignment=offline_entry.subject_assignment,
                student=offline_entry.student,
            )

            # CONFLICT EXISTS
            site = get_effective_site_settings(
                school=getattr(getattr(offline_entry, "student", None), "school", None)
            )
            offline_settings = (
                site.get_offline_runtime_settings()
                if callable(getattr(site, "get_offline_runtime_settings", None))
                else {
                    "offline_sync_conflict_resolution": getattr(
                        site,
                        "offline_sync_conflict_resolution",
                        "show_both",
                    )
                }
            )
            resolution_mode = str(
                offline_settings.get("offline_sync_conflict_resolution", "show_both")
                or "show_both"
            ).lower()

            if resolution_mode == "reject":
                offline_entry.status = "rejected"
                offline_entry.save()
                return False, "Conflict: Grades already entered. Entry rejected."

            elif resolution_mode == "auto_merge":
                # Keep online version
                offline_entry.status = "synced"
                offline_entry.synced_at = timezone.now()
                offline_entry.synced_by = teacher.user if teacher else None
                offline_entry.offline_conflict_resolved = True
                offline_entry.conflict_resolution_note = (
                    "Auto-merged: kept existing entry"
                )
                offline_entry.save()
                return True, "Synced (kept existing entry)"

            elif resolution_mode == "show_both":
                # Require manual resolution
                offline_entry.status = "conflict"
                offline_entry.conflict_with_evaluation = existing_eval
                offline_entry.save()
                return False, "Conflict: Two versions exist. Manual resolution needed."

        except Evaluation.DoesNotExist:
            # NO CONFLICT: Create new
            existing_eval = None

        # Create or update Evaluation
        evaluation, created = Evaluation.objects.update_or_create(
            academic_year=offline_entry.academic_year,
            term=offline_entry.term,
            subject_assignment=offline_entry.subject_assignment,
            student=offline_entry.student,
            defaults={
                "teacher": offline_entry.teacher,
                "seq1_score": offline_entry.seq1_score,
                "seq2_score": offline_entry.seq2_score,
                "exam_score": offline_entry.exam_score,
                "mock_score": offline_entry.mock_score,
                "practical_score": offline_entry.practical_score,
                "remarks": offline_entry.remarks,
            },
        )

        # Mark as synced
        offline_entry.status = "synced"
        offline_entry.synced_at = timezone.now()
        offline_entry.synced_by = teacher.user if teacher else None
        offline_entry.offline_conflict_resolved = existing_eval is not None
        if existing_eval:
            offline_entry.conflict_with_evaluation = existing_eval
            offline_entry.conflict_resolution_note = f"Merged: {existing_eval.id}"
        offline_entry.save()

        logger.info(
            f"Offline entry {offline_entry.id} synced → Evaluation {evaluation.id}"
        )
        return True, "Synced successfully"

    @staticmethod
    def resolve_conflict_manually(
        offline_entry: OfflineMarkEntry, teacher_choice: dict
    ) -> bool:
        """Teacher manually resolves conflict."""

        existing_eval = offline_entry.conflict_with_evaluation
        if not existing_eval:
            return False

        try:
            # Merge values based on teacher choice
            for field in [
                "seq1_score",
                "seq2_score",
                "exam_score",
                "mock_score",
                "practical_score",
                "remarks",
            ]:
                choice = teacher_choice.get(field, "online")

                if choice == "offline":
                    value = getattr(offline_entry, field)
                else:
                    value = getattr(existing_eval, field)

                setattr(existing_eval, field, value)

            existing_eval.save()

            # Mark offline entry as resolved
            offline_entry.status = "synced"
            offline_entry.synced_at = timezone.now()
            offline_entry.offline_conflict_resolved = True
            offline_entry.teacher_conflict_choice = teacher_choice
            offline_entry.conflict_resolution_note = "Manually resolved by teacher"
            offline_entry.save()

            logger.info("Conflict resolved for %s", offline_entry.id)
            return True

        except _OFFLINE_SYNC_RESOLVE_ERRORS as e:
            school_id = None
            if getattr(offline_entry, "student", None) and hasattr(
                offline_entry.student, "school_id"
            ):
                school_id = offline_entry.student.school_id
            log_exception_with_context(
                "resolve_conflict_manually failed",
                school_id=school_id,
                extra={"offline_entry_id": getattr(offline_entry, "id", None)},
            )
            logger.error("Failed to resolve conflict: %s", e, exc_info=True)
            return False
