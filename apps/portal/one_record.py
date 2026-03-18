"""
F3: One-record story — single student view across modules (academics, finance, attendance, communications).
Used by Student 360 backend page, global search story cards, and APIs.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db.models import Q


def _decimal_str(d: Decimal) -> str:
    return str(d.quantize(Decimal("0.01")))


def build_student_one_record_data(
    student: Any,
    school: Any,
    *,
    include_finance: bool = True,
    include_communications: bool = True,
    max_open_invoices: int = 8,
    max_recent_evaluations: int = 6,
) -> dict[str, Any]:
    """
    Aggregate DB-backed sections for one student. No URL building here.
    """
    from apps.people.models import StudentGuardian

    sid = student.pk
    school_id = getattr(school, "pk", None) or getattr(school, "id", None)

    profile = {
        "first_name": getattr(student, "first_name", "") or "",
        "last_name": getattr(student, "last_name", "") or "",
        "student_code": getattr(student, "student_code", "") or "",
        "admission_number": getattr(student, "admission_number", "") or "",
        "status": getattr(student, "status", "") or "",
        "classroom_name": "",
        "classroom_code": "",
        "academic_year_name": "",
    }
    if getattr(student, "classroom_id", None):
        cr = student.classroom
        profile["classroom_name"] = getattr(cr, "name", "") or ""
        profile["classroom_code"] = getattr(cr, "code", "") or ""
    if getattr(student, "academic_year_id", None):
        profile["academic_year_name"] = getattr(student.academic_year, "name", "") or ""

    academics: dict[str, Any] = {"recent_evaluations": []}
    try:
        from apps.evals.models import Evaluation

        ev_qs = (
            Evaluation.objects.filter(student_id=sid, school_id=school_id)
            .select_related("subject_assignment__subject", "term")
            .order_by("-id")[:max_recent_evaluations]
        )
        for ev in ev_qs:
            subj = getattr(ev.subject_assignment, "subject", None)
            subj_name = getattr(subj, "name", "") or "Subject"
            score = None
            try:
                score = float(ev.total_score) if ev.total_score is not None else None
            except (TypeError, ValueError):
                pass
            academics["recent_evaluations"].append(
                {
                    "subject": subj_name,
                    "term": getattr(ev.term, "name", "") or "",
                    "score": score,
                }
            )
    except Exception:
        pass

    attendance: dict[str, Any] = {}
    try:
        from apps.academics.models import Attendance

        att = (
            Attendance.objects.filter(student_id=sid)
            .select_related("classroom")
            .order_by("-date")
            .first()
        )
        if att:
            attendance = {
                "last_date": att.date.isoformat(),
                "last_status": att.status,
                "last_status_display": att.get_status_display(),
                "classroom": getattr(att.classroom, "name", "") or "",
            }
    except Exception:
        pass

    finance: dict[str, Any] = {
        "pending_total": "0.00",
        "currency_code": "USD",
        "open_invoices": [],
    }
    if include_finance:
        try:
            from apps.finance.models import Invoice

            inv_qs = (
                Invoice.objects.filter(student_id=sid, school_id=school_id)
                .exclude(
                    status__in=[
                        Invoice.Status.VOID,
                        Invoice.Status.DRAFT,
                        Invoice.Status.PAID,
                    ]
                )
                .prefetch_related("payments")
                .order_by("-issued_date", "-id")[: max_open_invoices * 2]
            )
            pending = Decimal("0.00")
            currency = (
                getattr(school, "default_currency", None)
                or getattr(school, "currency_code", None)
                or "USD"
            )
            open_invoices = []
            for inv in inv_qs:
                bal = inv.computed_balance
                if bal <= Decimal("0.00"):
                    continue
                pending += bal
                open_invoices.append(
                    {
                        "id": inv.pk,
                        "reference": inv.reference or str(inv.pk),
                        "balance": _decimal_str(bal),
                        "status": inv.status,
                    }
                )
                if len(open_invoices) >= max_open_invoices:
                    break
            finance["pending_total"] = _decimal_str(pending)
            finance["currency_code"] = currency
            finance["open_invoices"] = open_invoices
        except Exception:
            pass

    communications: dict[str, Any] = {"latest": None}
    if include_communications:
        try:
            from apps.communication.models import Message

            gids = list(
                StudentGuardian.objects.filter(student_id=sid)
                .exclude(guardian_user_id__isnull=True)
                .values_list("guardian_user_id", flat=True)
            )
            gids = [x for x in gids if x]
            if gids:
                msg = (
                    Message.objects.filter(school_id=school_id)
                    .filter(Q(sender_id__in=gids) | Q(recipient_id__in=gids))
                    .select_related("sender", "recipient")
                    .order_by("-created_at")
                    .first()
                )
                if msg:
                    other = msg.recipient if msg.sender_id in gids else msg.sender
                    communications["latest"] = {
                        "subject": (msg.subject or "")[:200],
                        "preview": msg.summary[:160]
                        if hasattr(msg, "summary")
                        else (msg.body or "")[:160],
                        "created_at": msg.created_at.isoformat()
                        if msg.created_at
                        else "",
                        "counterparty": other.get_full_name() or other.username
                        if other
                        else "",
                    }
        except Exception:
            pass

    return {
        "student_id": str(sid),
        "school_id": str(school_id) if school_id else "",
        "sections": ["profile", "academics", "attendance", "finance", "communications"],
        "data": {
            "profile": profile,
            "academics": academics,
            "attendance": attendance,
            "finance": finance,
            "communications": communications,
        },
    }


def build_student_story_preview(
    student: Any,
    school: Any,
    *,
    include_finance: bool = True,
    include_communications: bool = True,
) -> dict[str, Any]:
    """Compact cross-module summary for command palette / search cards."""
    full = build_student_one_record_data(
        student,
        school,
        include_finance=include_finance,
        include_communications=include_communications,
    )
    d = full["data"]
    prof = d["profile"]
    acad = d["academics"]
    fin = d["finance"]
    comm = d["communications"]
    att = d["attendance"]

    academic_line = prof["classroom_name"] or "—"
    if acad["recent_evaluations"]:
        first = acad["recent_evaluations"][0]
        sc = first.get("score")
        if sc is not None:
            academic_line = (
                f"{first['subject']}: {sc:g}"
                if isinstance(sc, float)
                else f"{first['subject']}"
            )

    finance_line = "—"
    if include_finance:
        finance_line = "No outstanding balance"
        if fin.get("open_invoices"):
            finance_line = f"{fin['currency_code']} {fin['pending_total']} pending ({len(fin['open_invoices'])} invoice(s))"

    comm_line = "—"
    if include_communications:
        comm_line = "No recent parent messages"
        if comm.get("latest"):
            lm = comm["latest"]
            comm_line = (lm.get("subject") or lm.get("preview") or "")[:120]

    attendance_line = "—"
    if att.get("last_date"):
        attendance_line = f"{att.get('last_status_display', att.get('last_status', ''))} ({att['last_date']})"

    return {
        "academic_line": academic_line,
        "finance_line": finance_line,
        "communication_line": comm_line,
        "attendance_line": attendance_line,
    }


def get_student_one_record(school_id: Any, student_id: Any) -> dict[str, Any]:
    """Legacy entry: returns structure with populated data when student exists."""
    from apps.people.models import StudentProfile

    try:
        st = StudentProfile.objects.select_related("classroom", "academic_year").get(
            pk=student_id, school_id=school_id
        )
    except StudentProfile.DoesNotExist:
        return {
            "student_id": str(student_id),
            "school_id": str(school_id),
            "sections": [
                "profile",
                "academics",
                "attendance",
                "finance",
                "communications",
            ],
            "data": {},
            "missing": True,
        }
    return build_student_one_record_data(st, st.school)
