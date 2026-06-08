"""Activate verified signup schools stuck with is_active=False."""

from __future__ import annotations

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Run provisioning for verified signup schools that are still inactive. "
        "Use after deploy to recover stuck tenants (e.g. st-jude)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--slug",
            action="append",
            default=[],
            help="School slug/subdomain to reprovision (repeatable).",
        )
        parser.add_argument(
            "--all-verified-inactive",
            action="store_true",
            help="Reprovision every verified school with is_active=False.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List matches without running provisioning.",
        )

    def handle(self, *args, **options):
        from apps.schools.models import School, SignupVerification
        from apps.schools.tasks import complete_provisioning_for_school

        slugs = [s.strip().lower() for s in options["slug"] if (s or "").strip()]
        qs = School.objects.filter(is_active=False)
        if slugs:
            from django.db.models import Q

            q = Q()
            for slug in slugs:
                q |= Q(slug__iexact=slug) | Q(subdomain__iexact=slug)
            qs = qs.filter(q)
        elif options["all_verified_inactive"]:
            verified_ids = SignupVerification.objects.filter(
                verified_at__isnull=False
            ).values_list("school_id", flat=True)
            qs = qs.filter(pk__in=verified_ids)
        else:
            self.stderr.write("Pass --slug=<slug> and/or --all-verified-inactive.")
            return

        schools = list(qs.order_by("created_at"))
        if not schools:
            self.stdout.write("No matching inactive schools.")
            return

        for school in schools:
            verif = (
                SignupVerification.objects.filter(
                    school=school, verified_at__isnull=False
                )
                .order_by("-verified_at")
                .first()
            )
            email = (verif.email if verif else "") or ""
            label = f"{school.slug} ({school.pk})"
            if options["dry_run"]:
                self.stdout.write(f"DRY-RUN would provision {label}")
                continue
            result = complete_provisioning_for_school(
                str(school.pk), contact_email=email
            )
            school.refresh_from_db(fields=["is_active"])
            self.stdout.write(
                f"{label}: active={school.is_active} sync={result.get('sync_completed')} "
                f"queued={result.get('queued')}"
            )
