"""
Provisioning task: after School row is created, create admin user, school_members, seed terms/subjects, logo path.
Can be run as Celery task or synchronously.
"""
import logging
import secrets
from django.contrib.auth import get_user_model
from django.db import transaction

logger = logging.getLogger(__name__)

User = get_user_model()


def provision_school_sync(school_id: str, contact_email: str = "", **kwargs):
    """Run provisioning synchronously (no Celery)."""
    with transaction.atomic():
        _do_provision(school_id, contact_email=contact_email, **kwargs)


def _do_provision(school_id: str, contact_email: str = "", **kwargs):
    from .models import School, SchoolMembership
    from apps.academics.models import AcademicYear, Term, Subject
    from django.utils import timezone
    from datetime import date

    school = School.objects.filter(id=school_id).first()
    if not school:
        logger.warning("School %s not found for provisioning", school_id)
        return
    if school.is_active:
        logger.info("School %s already active, skip provisioning", school_id)
        return

    # Create default admin user if contact_email provided and no user exists
    admin_user = None
    if contact_email:
        admin_user = User.objects.filter(email=contact_email).first()
        if not admin_user:
            username = contact_email.split("@")[0][:150] or f"admin_{school.slug}"
            if User.objects.filter(username=username).exists():
                username = f"{username}_{school.slug}"[:150]
            admin_user = User.objects.create_user(
                username=username,
                email=contact_email,
                # Keep a strong random value even though we disable password login.
                password=secrets.token_urlsafe(32),
                role=User.Role.ADMIN,
            )
            admin_user.set_unusable_password()
            admin_user.save()
            logger.info("Created admin user %s for school %s", admin_user.username, school_id)
        SchoolMembership.objects.get_or_create(
            user=admin_user,
            school=school,
            defaults={"role": User.Role.ADMIN, "is_primary": True},
        )

    # Seed academic year and terms from school's region or defaults
    region = school.default_region
    term_count = 3
    if region:
        term_count = getattr(region, "term_count_per_year", 3) or 3
    start_month = 9
    if region:
        start_month = getattr(region, "academic_year_start_month", 9) or 9

    now = timezone.now().date()
    year_start = date(now.year, start_month, 1)
    if now.month < start_month:
        year_start = date(now.year - 1, start_month, 1)
    year_end = date(year_start.year + 1, start_month, 1)
    from datetime import timedelta
    year_end = year_end - timedelta(days=1)

    ay, created = AcademicYear.objects.get_or_create(
        school=school,
        name=f"{year_start.year}/{year_end.year}",
        defaults={
            "start_date": year_start,
            "end_date": year_end,
            "is_active": True,
        },
    )
    if created:
        # Create terms
        months_per_term = 12 // term_count
        for i in range(term_count):
            t_start = date(year_start.year, year_start.month + i * months_per_term, 1)
            t_end_month = year_start.month + (i + 1) * months_per_term
            if t_end_month > 12:
                t_end_month -= 12
                t_end_year = year_start.year + 1
            else:
                t_end_year = year_start.year
            from calendar import monthrange
            _, last_day = monthrange(t_end_year, t_end_month)
            t_end = date(t_end_year, t_end_month, last_day)
            Term.objects.get_or_create(
                school=school,
                academic_year=ay,
                name=f"Term {i + 1}",
                defaults={
                    "position": i + 1,
                    "start_date": t_start,
                    "end_date": t_end,
                    "is_active": i == 0,
                },
            )
        logger.info("Seeded academic year and %s terms for school %s", term_count, school_id)

    # Optional: seed default subjects. Subject name is unique per school (school_id, name).
    if not Subject.objects.filter(school=school).exists():
        for name, cat in [
            ("Mathematics", Subject.Category.GENERAL),
            ("English", Subject.Category.GENERAL),
            ("French", Subject.Category.GENERAL),
            ("Science", Subject.Category.GENERAL),
        ]:
            Subject.objects.get_or_create(
                school=school,
                name=name,
                defaults={"category": cat},
            )
        logger.info("Seeded default subjects for school %s", school_id)

    school.is_active = True
    school.save(update_fields=["is_active", "updated_at"])
    logger.info("School %s provisioning complete", school_id)


# Celery task (optional)
try:
    from celery import shared_task

    @shared_task(bind=True, max_retries=3)
    def provision_school_task(self, school_id: str, contact_email: str = "", **kwargs):
        try:
            with transaction.atomic():
                _do_provision(school_id, contact_email=contact_email, **kwargs)
        except Exception as exc:
            logger.exception("Provisioning failed for %s", school_id)
            raise self.retry(exc=exc)
except ImportError:
    def provision_school_task(*args, **kwargs):
        provision_school_sync(*args, **kwargs)
