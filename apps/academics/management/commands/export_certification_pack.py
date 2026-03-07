"""
Export a certification "upload pack" (CSV scaffold) for board portals.

This is intentionally generic and safe:
- Produces a CSV list of candidates for a given session
- Includes placeholders for CA marks upload pipelines (to be integrated later)

Usage:
  python manage.py export_certification_pack --session-id 1 --out certification_pack.csv
"""

import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.academics.models import CertificationExamSession, CertificationCandidate, CertificationAuditLog


class Command(BaseCommand):
    help = "Export a certification registration/CA upload CSV pack."

    def add_arguments(self, parser):
        parser.add_argument("--session-id", type=int, required=True, help="CertificationExamSession ID")
        parser.add_argument("--out", type=str, default="", help="Output CSV path (default: ./certification_pack_<id>.csv)")

    def handle(self, *args, **options):
        session_id = options["session_id"]
        out_path = (options.get("out") or "").strip()

        session = CertificationExamSession.objects.filter(id=session_id).select_related("academic_year").first()
        if not session:
            raise CommandError(f"Session not found: id={session_id}")

        candidates = (
            CertificationCandidate.objects.filter(session=session)
            .select_related("student", "student__classroom", "student__specialty")
            .order_by("student__last_name", "student__first_name")
        )

        filename = out_path or f"certification_pack_{session_id}.csv"
        path = Path(filename).resolve()

        headers = [
            "academic_year",
            "session_name",
            "board",
            "level",
            "student_id",
            "student_name",
            "classroom",
            "specialty",
            "admission_number",
            "candidate_number",
            "status",
            "ca_uploaded_at",
            "notes",
            # Placeholders for future CA export mapping
            "ca_total_placeholder",
            "ca_subjects_placeholder",
        ]

        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for c in candidates:
                student = c.student
                writer.writerow(
                    [
                        session.academic_year.name,
                        session.name,
                        session.board,
                        session.level,
                        student.id,
                        getattr(student, "get_full_name", lambda: str(student))(),
                        getattr(getattr(student, "classroom", None), "name", "") or "",
                        getattr(getattr(student, "specialty", None), "name", "") or "",
                        getattr(student, "admission_number", "") or getattr(student, "student_code", "") or "",
                        c.candidate_number or "",
                        c.status,
                        c.ca_uploaded_at.isoformat() if c.ca_uploaded_at else "",
                        (c.notes or "").strip(),
                        "",
                        "",
                    ]
                )

        CertificationAuditLog.objects.create(
            session=session,
            candidate=None,
            actor=None,
            action="EXPORT_PACK",
            detail=f"Exported certification pack to {path.as_posix()} ({candidates.count()} candidates) at {timezone.now().isoformat()}",
        )

        self.stdout.write(self.style.SUCCESS(f"Exported {candidates.count()} candidates to {path.as_posix()}"))

