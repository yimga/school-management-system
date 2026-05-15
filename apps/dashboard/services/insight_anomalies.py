"""
Actionable insight anomaly cards for backend dashboard (rules-based; LLM optional later).
Prioritizes combined grade + attendance signals before single-factor cards.
All user-facing strings use gettext for i18n.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.db.models import Count
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.utils.translation import gettext as _


def build_insight_anomaly_cards(
    request: Any, *, limit: int = 6
) -> list[dict[str, Any]]:
    school = getattr(request, "school", None)
    if not school:
        return []
    school_id = school.id
    cards: list[dict[str, Any]] = []

    at_risk_rows: list[dict[str, Any]] = []
    try:
        from apps.analytics.services import AdvancedAnalyticsService

        at_risk_rows = list(
            AdvancedAnalyticsService.identify_at_risk_students(
                threshold=55, school=school
            )[: max(8, limit * 2)]
        )
    except Exception:
        pass

    at_risk_by_id: dict[int, dict[str, Any]] = {}
    for row in at_risk_rows:
        sid = row.get("id")
        if sid:
            at_risk_by_id[int(sid)] = row

    absence_by_sid: dict[int, int] = {}
    try:
        from apps.academics.models import Attendance

        since = timezone.localdate() - timedelta(days=14)
        for row in (
            Attendance.objects.filter(
                school_id=school_id,
                date__gte=since,
                status=Attendance.Status.ABSENT,
            )
            .values("student_id")
            .annotate(n=Count("id"))
            .filter(n__gte=4)
            .order_by("-n")[:12]
        ):
            absence_by_sid[row["student_id"]] = row["n"]
    except Exception:
        pass

    correlated_ids = set(at_risk_by_id.keys()) & set(absence_by_sid.keys())
    used_student_ids: set[int] = set()
    low_avg = _("Low recent average")

    try:
        from apps.people.models import StudentProfile

        for sid in sorted(
            correlated_ids,
            key=lambda x: absence_by_sid.get(x, 0),
            reverse=True,
        ):
            if len(cards) >= limit:
                break
            row = at_risk_by_id.get(sid)
            if not row:
                continue
            n_abs = absence_by_sid[sid]
            name = str(row.get("student", _("Student")))
            summary = row.get("risk_reason_summary") or low_avg
            try:
                action_url = reverse(
                    "accounts:backend_student_detail", kwargs={"student_id": sid}
                )
            except NoReverseMatch:
                action_url = reverse("admin:people_studentprofile_change", args=[sid])
            cards.append(
                {
                    "id": f"correlation-{sid}",
                    "title": _("Grade drop + attendance correlation"),
                    "detail": _(
                        "%(name)s: at-risk academics (%(summary)s) and %(n)d absences "
                        "in 14 days — review holistically."
                    )
                    % {"name": name, "summary": summary, "n": n_abs},
                    "insight_line": _(
                        "Suggested next step: align attendance outreach with academic support."
                    ),
                    "severity": "danger" if n_abs >= 7 else "warn",
                    "action_url": action_url,
                    "action_label": _("Open Student 360"),
                }
            )
            used_student_ids.add(sid)

        for sid, row in list(at_risk_by_id.items()):
            if sid in used_student_ids or len(cards) >= limit:
                continue
            try:
                action_url = reverse(
                    "accounts:backend_student_detail", kwargs={"student_id": sid}
                )
            except NoReverseMatch:
                action_url = reverse("admin:people_studentprofile_change", args=[sid])
            stu = str(row.get("student", _("Student")))
            summ = row.get("risk_reason_summary") or low_avg
            cards.append(
                {
                    "id": f"academic-risk-{sid}",
                    "title": _("Academic risk signal"),
                    "detail": _("%(student)s: %(reason)s.")
                    % {"student": stu, "reason": summ},
                    "insight_line": _("Review recent marks and intervention history."),
                    "severity": "warn",
                    "action_url": action_url,
                    "action_label": _("Open Student 360"),
                }
            )
            used_student_ids.add(sid)

        for sid, n_abs in sorted(
            absence_by_sid.items(), key=lambda x: x[1], reverse=True
        ):
            if sid in used_student_ids or len(cards) >= limit:
                continue
            st = StudentProfile.objects.filter(pk=sid, school_id=school_id).first()
            if not st:
                continue
            name = f"{st.first_name} {st.last_name}".strip()
            try:
                action_url = reverse(
                    "accounts:backend_student_detail", kwargs={"student_id": sid}
                )
            except NoReverseMatch:
                continue
            cards.append(
                {
                    "id": f"attendance-{sid}",
                    "title": _("Attendance pattern"),
                    "detail": _(
                        "%(name)s: %(n)d absences in the last 14 days — cross-check with grades."
                    )
                    % {"name": name, "n": n_abs},
                    "insight_line": _(
                        "Check guardian contact and excused vs unexcused."
                    ),
                    "severity": "danger" if n_abs >= 7 else "warn",
                    "action_url": action_url,
                    "action_label": _("Review Student 360"),
                }
            )
            used_student_ids.add(sid)
    except Exception:
        pass

    try:
        from apps.finance.models import Invoice

        overdue = Invoice.objects.filter(
            school_id=school_id, status=Invoice.Status.OVERDUE
        ).select_related("student")[:5]
        for inv in overdue:
            if len(cards) >= limit:
                break
            st = inv.student
            label = (
                f"{st.first_name} {st.last_name}".strip()
                if st
                else (inv.reference or str(inv.pk))
            )
            try:
                action_url = reverse("finance:invoice_detail", args=[inv.pk])
            except NoReverseMatch:
                action_url = reverse("finance:invoices")
            cards.append(
                {
                    "id": f"overdue-inv-{inv.pk}",
                    "title": _("Overdue invoice"),
                    "detail": _(
                        "%(label)s: balance outstanding — follow up or adjust terms."
                    )
                    % {"label": label},
                    "insight_line": _(
                        "Escalate to bursar if balance aged beyond policy."
                    ),
                    "severity": "warn",
                    "action_url": action_url,
                    "action_label": _("Open invoice"),
                }
            )
    except Exception:
        pass

    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for c in cards:
        if c["id"] in seen:
            continue
        seen.add(c["id"])
        out.append(c)
        if len(out) >= limit:
            break

    # Best-effort AI narrative enrichment: when AI is enabled for this
    # tenant, attach a one-sentence model-generated suggestion to each card.
    # Always safe — silent when AI is disabled.
    _enrich_with_ai_narrative(out, school)
    return out


def _enrich_with_ai_narrative(cards: list[dict[str, Any]], school: Any) -> None:
    """Add an `ai_suggestion` line to each card via services.ai_helpers.

    Pure enhancement: rules-based detail+insight_line stay unchanged. The
    UI shows ai_suggestion when present as an additional whisper line
    below insight_line.
    """
    if not cards:
        return
    try:
        from services.ai_helpers import invoke_task
    except Exception:  # noqa: BLE001
        return

    bullet_lines = "\n".join(
        f"- ({c['id']}) {c.get('title', '')}: {c.get('detail', '')}"
        for c in cards
    )
    prompt = (
        "You are a school operations co-pilot. For each anomaly bullet "
        "below, respond with ONE short next-step suggestion (max 14 "
        "words). Tone: calm, actionable, no hedging. Output one line per "
        "input bullet, formatted as `<id>: <suggestion>`.\n\n"
        f"{bullet_lines}"
    )
    result = invoke_task(
        school=school,
        task_type_name="NARRATIVE",
        prompt=prompt,
        prompt_type="dashboard.anomaly_nudge",
        content_sensitivity="standard",
    )
    if result is None:
        return
    text, _meta = result
    by_id = {}
    for line in (text or "").splitlines():
        line = line.strip()
        if ":" not in line:
            continue
        cid, _, body = line.partition(":")
        by_id[cid.strip().lstrip("-").strip()] = body.strip()
    for c in cards:
        suggestion = by_id.get(c["id"])
        if suggestion:
            c["ai_suggestion"] = suggestion[:200]
