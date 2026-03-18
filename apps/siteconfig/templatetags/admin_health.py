from django import template
from django.db import connections
from django.db import DatabaseError
from django.db.migrations.loader import MigrationLoader
from django.utils import timezone
import os
from pathlib import Path

from apps.reports.models import TermPublishStatus, ReportCard
from apps.finance.models import Invoice, PaymentReminder
from apps.platform_runtime.helpers import get_effective_site_settings
from apps.siteconfig.models import ReportTemplate, ThemePack
from apps.people.models import StudentProfile, TeacherProfile, StudentGuardian
from apps.academics.models import Classroom, Subject
from apps.accounts.models import User
from apps.evals.models import Evaluation
from apps.payroll.models import PayrollEmployee, PayrollRun


register = template.Library()
OPTIONAL_ADMIN_HEALTH_ERRORS = (
    AttributeError,
    DatabaseError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
)


@register.simple_tag(takes_context=True)
def admin_health(context):
    """Return a small dict of system health metrics for the admin hero/cards."""
    request = context.get("request")
    metrics = {
        "pending_migrations": "N/A",
        "unpublished_terms": 0,
        "overdue_invoices": 0,
        "draft_invoices": 0,
        "active_reminders": 0,
        "reminders_due": 0,
        "portal_parent_enabled": True,
        "portal_teacher_enabled": True,
        "backup_status": "Not configured",
        "backup_last": "N/A",
    }

    # Migrations pending
    try:
        loader = MigrationLoader(connections["default"])
        graph = loader.graph
        applied = set(loader.applied_migrations)
        unapplied = [
            node
            for node in graph.nodes
            if node not in applied and not graph.node_map[node].replaces
        ]
        metrics["pending_migrations"] = len(unapplied)
    except OPTIONAL_ADMIN_HEALTH_ERRORS:
        # If anything fails (e.g., no DB), leave as "N/A"
        pass

    # Term publish status
    metrics["unpublished_terms"] = TermPublishStatus.objects.filter(
        is_published=False
    ).count()

    # Finance overdue invoices
    metrics["overdue_invoices"] = Invoice.objects.filter(
        status=Invoice.Status.OVERDUE
    ).count()
    metrics["draft_invoices"] = Invoice.objects.filter(
        status=Invoice.Status.DRAFT
    ).count()

    # Payment reminders
    now = timezone.now()
    reminders = PaymentReminder.objects.filter(is_active=True)
    metrics["active_reminders"] = reminders.count()
    metrics["reminders_due"] = reminders.filter(next_send_at__lte=now).count()

    # Portal toggles
    try:
        site = get_effective_site_settings(request=request)
        metrics["portal_parent_enabled"] = getattr(site, "enable_parent_portal", True)
        metrics["portal_teacher_enabled"] = getattr(site, "enable_teacher_portal", True)
    except OPTIONAL_ADMIN_HEALTH_ERRORS:
        pass

    # Backup status: check env hint or file marker
    try:
        last_env = os.getenv("BACKUP_LAST_ISO") or os.getenv("BACKUP_LAST_TS")
        marker = Path(os.getenv("BACKUP_MARKER_PATH", "backups/latest.txt"))
        if last_env:
            metrics["backup_status"] = "OK"
            metrics["backup_last"] = last_env
        elif marker.exists():
            metrics["backup_status"] = "OK"
            metrics["backup_last"] = marker.read_text().strip() or "unknown"
        else:
            metrics["backup_status"] = "Not configured"
            metrics["backup_last"] = "N/A"
    except OPTIONAL_ADMIN_HEALTH_ERRORS:
        metrics["backup_status"] = "Not configured"
        metrics["backup_last"] = "N/A"

    return metrics


@register.filter
def get_item(obj, key):
    try:
        return obj.get(key, {})
    except (AttributeError, TypeError, ValueError):
        return {}


@register.simple_tag(takes_context=True)
def admin_section_stats(context):
    """Lightweight stats per major app section."""
    request = context.get("request")
    site = get_effective_site_settings(request=request)
    # Completion: percentage of evaluations that meet required components
    eval_total = Evaluation.objects.count()
    eval_complete = Evaluation.objects.filter().count()
    try:
        eval_complete = sum(
            1 for e in Evaluation.objects.all().iterator() if e.is_complete_for_ranking
        )
    except OPTIONAL_ADMIN_HEALTH_ERRORS:
        eval_complete = 0
    completion_pct = round((eval_complete / eval_total) * 100, 2) if eval_total else 0

    return {
        "academics": {
            "Students": StudentProfile.objects.count(),
            "Classrooms": Classroom.objects.count(),
            "Subjects": Subject.objects.count(),
            "Reports generated": ReportCard.objects.count(),
        },
        "accounts": {
            "Users": User.objects.count(),
            "Teachers": TeacherProfile.objects.count(),
            "Guardians": StudentGuardian.objects.count(),
        },
        "analytics": {
            "Grading deadlines": 0,
        },
        "evals": {
            "Evaluations": Evaluation.objects.count(),
            "Report cards": ReportCard.objects.count(),
            "Completion %": completion_pct,
        },
        "finance": {
            "Invoices": Invoice.objects.count(),
            "Overdue": Invoice.objects.filter(status=Invoice.Status.OVERDUE).count(),
            "Draft": Invoice.objects.filter(status=Invoice.Status.DRAFT).count(),
        },
        "payroll": {
            "Employees": PayrollEmployee.objects.count(),
            "Runs": PayrollRun.objects.count(),
        },
        "people": {},
        "portal": {
            "Parent portal": "On" if site.enable_parent_portal else "Off",
            "Teacher portal": "On" if site.enable_teacher_portal else "Off",
        },
        "reports": {
            "Templates": ReportTemplate.objects.filter(is_active=True).count(),
        },
        "siteconfig": {
            "Theme packs": ThemePack.objects.filter(is_active=True).count(),
            "School code": site.school_code or "N/A",
        },
    }
