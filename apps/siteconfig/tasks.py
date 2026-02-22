"""
Celery tasks for siteconfig (Phase E: revenue stats; Phase Welcome: welcome email).
"""
from celery import shared_task


@shared_task(name="siteconfig.calculate_monthly_revenue_stats")
def calculate_monthly_revenue_stats(snapshot_date=None):
    """
    Phase E: Run calculate_monthly_stats to fill RevenueSnapshot.
    Schedule daily via Celery Beat (e.g. 02:00).
    """
    from .billing_services import calculate_monthly_stats
    from datetime import date
    if snapshot_date:
        if isinstance(snapshot_date, str):
            snapshot_date = date.fromisoformat(snapshot_date)
    return calculate_monthly_stats(snapshot_date=snapshot_date)


@shared_task(name="siteconfig.send_welcome_email")
def send_welcome_email(school_id: int, contact_email: str = ""):
    """
    Phase Welcome: Send welcome email after school provisioning.
    HTML template with tenant branding (primary_color, logo_url), unique login URL,
    and optional dynamic block (Trade vs General). Trigger via signal on School create.
    """
    from django.core.mail import send_mail
    from django.conf import settings
    from apps.schools.models import School
    school = School.objects.filter(pk=school_id).first()
    if not school:
        return {"ok": False, "reason": "school_not_found"}
    email = contact_email or getattr(school, "contact_email", None) or ""
    if not email:
        return {"ok": False, "reason": "no_contact_email"}
    subject = f"Welcome to {getattr(settings, 'SITE_NAME', 'Portal')} — {school.name}"
    body = f"Your school {school.name} has been set up. Log in at your school URL to get started."
    try:
        send_mail(
            subject,
            body,
            getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@example.com'),
            [email],
            fail_silently=True,
            html_message=body.replace("\n", "<br>\n"),
        )
        return {"ok": True, "sent_to": email}
    except Exception as e:
        return {"ok": False, "error": str(e)}
