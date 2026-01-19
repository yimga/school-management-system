from django import template
from django.db import connections
from django.db.migrations.loader import MigrationLoader
from django.utils import timezone

from apps.reports.models import TermPublishStatus
from apps.finance.models import Invoice, PaymentReminder
from apps.siteconfig.models import SiteSettings


register = template.Library()


@register.simple_tag
def admin_health():
    """Return a small dict of system health metrics for the admin hero/cards."""
    metrics = {
        "pending_migrations": "N/A",
        "unpublished_terms": 0,
        "overdue_invoices": 0,
        "draft_invoices": 0,
        "active_reminders": 0,
        "reminders_due": 0,
        "portal_parent_enabled": True,
        "portal_teacher_enabled": True,
    }

    # Migrations pending
    try:
        loader = MigrationLoader(connections["default"])
        graph = loader.graph
        applied = set(loader.applied_migrations)
        unapplied = [
            node for node in graph.nodes
            if node not in applied and not graph.node_map[node].replaces
        ]
        metrics["pending_migrations"] = len(unapplied)
    except Exception:
        # If anything fails (e.g., no DB), leave as "N/A"
        pass

    # Term publish status
    metrics["unpublished_terms"] = TermPublishStatus.objects.filter(is_published=False).count()

    # Finance overdue invoices
    metrics["overdue_invoices"] = Invoice.objects.filter(status=Invoice.Status.OVERDUE).count()
    metrics["draft_invoices"] = Invoice.objects.filter(status=Invoice.Status.DRAFT).count()

    # Payment reminders
    now = timezone.now()
    reminders = PaymentReminder.objects.filter(is_active=True)
    metrics["active_reminders"] = reminders.count()
    metrics["reminders_due"] = reminders.filter(next_send_at__lte=now).count()

    # Portal toggles
    try:
        site = SiteSettings.get_solo()
        metrics["portal_parent_enabled"] = getattr(site, "enable_parent_portal", True)
        metrics["portal_teacher_enabled"] = getattr(site, "enable_teacher_portal", True)
    except Exception:
        pass

    return metrics
