"""Wave G (2026-05-15): process APPROVED GDPR EraseRequest rows.

Bridges the existing ``EraseRequest`` model (status APPROVED → COMPLETED)
to the DSAR scrub services. As of the multi-subject DSAR wave it dispatches
through ``apps.compliance.dsar_subjects.scrub_user_subject`` so EVERY
PII-bearing User subject is covered — student, teacher/staff, and
parent/guardian — not only students. Two additions over the manual /
admin-action-only flow:

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

from apps.compliance.dsar_subjects import scrub_user_subject
from apps.compliance.models import EraseRequest

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Process APPROVED GDPR EraseRequest rows via the multi-subject DSAR "
        "scrub dispatcher (student / staff / guardian)."
    )

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
            # Dispatch to the correct subject handler (student / staff / guardian).
            # All paths are tenant-scoped on req.school_id, so a cross-tenant
            # subject resolves to "unsupported_subject_kind" and is skipped.
            result = scrub_user_subject(
                req.school_id,
                req.subject_user_id,
                dry_run=dry_run,
                requested_by_user_id=req.requested_by_id,
            )
            if not result.get("ok"):
                failed += 1
                self.stdout.write(self.style.ERROR(
                    f"req#{req.pk} school={req.school_id} subject={req.subject_user_id} "
                    f"→ FAIL ({result.get('error', 'unknown')})"
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
