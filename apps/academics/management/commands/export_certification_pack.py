"""
Export a certification "upload pack" CSV for board portals.

v4.00.12: closed the placeholder columns. The exporter now emits real
``ca_total`` + ``ca_subjects`` from the candidate's
``continuous_assessment`` JSON when present; falls back to empty strings
when the candidate has not yet been graded. The schema column names are
stable so downstream board-portal import pipelines can rely on them.

Usage:
  python manage.py export_certification_pack --session-id 1 --out certification_pack.csv
"""

import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.academics.models import (
    CertificationExamSession,
    CertificationCandidate,
    CertificationAuditLog,
)


def _ca_total_from(candidate) -> str:
    """v4.00.12: read continuous_assessment total from candidate JSON, blank when absent."""
    payload = getattr(candidate, "continuous_assessment", None)
    if not isinstance(payload, dict):
        return ""
    total = payload.get("total")
    if total is None:
        return ""
    try:
        return f"{float(total):.2f}"
    except (TypeError, ValueError):
        return str(total)


def _ca_subjects_from(candidate) -> str:
    """v4.00.12: read per-subject CA breakdown from candidate JSON as 'SUBJ:VAL;SUBJ:VAL'."""
    payload = getattr(candidate, "continuous_assessment", None)
    if not isinstance(payload, dict):
        return ""
    subjects = payload.get("subjects")
    if not isinstance(subjects, dict) or not subjects:
        return ""
    parts: list[str] = []
    for key in sorted(subjects.keys()):
        value = subjects[key]
        try:
            parts.append(f"{key}:{float(value):.2f}")
        except (TypeError, ValueError):
            parts.append(f"{key}:{value}")
    return ";".join(parts)


class Command(BaseCommand):
    help = "Export a certification registration/CA upload CSV pack."

    def add_arguments(self, parser):
        parser.add_argument(
            "--session-id", type=int, required=True, help="CertificationExamSession ID"
        )
        parser.add_argument(
            "--out",
            type=str,
            default="",
            help="Output CSV path (default: ./certification_pack_<id>.csv)",
        )

    def handle(self, *args, **options):
        session_id = options["session_id"]
        out_path = (options.get("out") or "").strip()

        session = (
            CertificationExamSession.objects.filter(id=session_id)
            .select_related("academic_year")
            .first()
        )
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
            # v4.00.12: real CA columns (formerly placeholders).
            "ca_total",
            "ca_subjects",
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
                        getattr(student, "admission_number", "")
                        or getattr(student, "student_code", "")
                        or "",
                        c.candidate_number or "",
                        c.status,
                        c.ca_uploaded_at.isoformat() if c.ca_uploaded_at else "",
                        (c.notes or "").strip(),
                        # v4.00.12 real CA columns: read from continuous_assessment JSON
                        # field if present, else fall back to empty strings.
                        _ca_total_from(c),
                        _ca_subjects_from(c),
                    ]
                )

        CertificationAuditLog.objects.create(
            session=session,
            candidate=None,
            actor=None,
            action="EXPORT_PACK",
            detail=f"Exported certification pack to {path.as_posix()} ({candidates.count()} candidates) at {timezone.now().isoformat()}",
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Exported {candidates.count()} candidates to {path.as_posix()}"
            )
        )
