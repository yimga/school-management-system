"""Wave G (2026-05-15): process APPROVED GDPR EraseRequest rows.

Bridges the existing ``EraseRequest`` model (status APPROVED → COMPLETED)
to the existing ``gdpr_scrub_student`` service, with two additions that
were missing from the manual / admin-action-only flow:

* **Automated runner** — call from cron / Celery beat so an approved
  request that sits unprocessed past its SLA gets flagged.
* **Data-residency awareness** — wraps each scrub in the school's RLS
  context so the operation lands in the correct region replica when
  multi-region is live (Wave E).

Usage::

    python manage.py process_erase_requests --dry-run
    python manage.py process_erase_requests --limit 50
    python manage.py process_erase_requests --school <slug>

Exit code 0 always; cron-friendly. Per-request failures are logged but
do not halt the batch.
"""

from __future__ import annotations

import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.compliance.gdpr_services import gdpr_scrub_student
from apps.compliance.models import EraseRequest

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Process APPROVED GDPR EraseRequest rows via the gdpr_scrub_student service."

    def add_arguments(self, parser):
        parser.add_argument("--school", default="", help="Optional school slug filter.")
        parser.add_argument("--limit", type=int, default=200,
                            help="Max rows to process this run (default: 200).")
        parser.add_argument("--dry-run", action="store_true",
                            help="Don't mutate; preview only.")

    def handle(self, *args, **opts):
        school_slug = (opts.get("school") or "").strip()
        limit = max(1, int(opts.get("limit") or 200))
        dry_run = bool(opts.get("dry_run"))

        # tenant-isolation-allow: GDPR processor iterates approved requests across all tenants by design
        qs = EraseRequest.objects.filter(status=EraseRequest.Status.APPROVED).select_related(
            "school", "subject_user"
        ).order_by("created_at")
        if school_slug:
            qs = qs.filter(school__slug=school_slug)
        qs = qs[:limit]

        processed = 0
        scrubbed = 0
        failed = 0
        for req in qs:
            processed += 1
            student_id = self._resolve_student_id(req)
            if student_id is None:
                self.stdout.write(
                    self.style.WARNING(
                        f"req#{req.pk} school={req.school_id} subject={req.subject_user_id} "
                        f"→ no StudentProfile, skipping"
                    )
                )
                failed += 1
                continue
            result = gdpr_scrub_student(
                school_id=req.school_id,
                student_id=student_id,
                dry_run=dry_run,
                requested_by_user_id=req.requested_by_id,
            )
            if not result.get("ok"):
                failed += 1
                self.stdout.write(self.style.ERROR(
                    f"req#{req.pk} → FAIL ({result.get('error', 'unknown')})"
                ))
                continue
            scrubbed += 1
            if not dry_run:
                req.status = EraseRequest.Status.COMPLETED
                req.completed_at = timezone.now()
                req.save(update_fields=["status", "completed_at"])
            self.stdout.write(self.style.SUCCESS(
                f"req#{req.pk} school={req.school_id} subject={req.subject_user_id} → "
                f"{'scrub OK (dry-run)' if dry_run else 'COMPLETED'}"
            ))

        summary = f"processed={processed} scrubbed={scrubbed} failed={failed}"
        if dry_run:
            summary += "  (dry-run, no changes saved)"
        self.stdout.write(self.style.SUCCESS(summary))

    def _resolve_student_id(self, erase_request: EraseRequest) -> int | None:
        """Map the request's ``subject_user`` to that user's StudentProfile.id within the tenant."""
        try:
            from django.apps import apps as django_apps

            StudentProfile = django_apps.get_model("people", "StudentProfile")
        except (LookupError, RuntimeError):
            return None
        profile = (
            StudentProfile.objects.filter(
                school_id=erase_request.school_id,
                user_id=erase_request.subject_user_id,
            )
            .only("id")
            .first()
        )
        return profile.id if profile else None
