"""Produce a whole class's / term's report cards — the verb schools were missing.

A ``ReportCard`` row could previously only be created by a PARENT hitting the
download URL, so a 200-student term ended up with 3 report cards. This command
lets the school generate them, honouring the same gates as the parent path and
reporting every skip with its reason.

    python manage.py generate_term_report_cards --school buea-gilead-tech
    python manage.py generate_term_report_cards --school buea-gilead-tech --classroom F1-GEN
    python manage.py generate_term_report_cards --school buea-gilead-tech --term 2 --dry-run

Under ``USE_DJANGO_TENANTS=1`` the academic tables live in the tenant SCHEMA, not
in ``public``, so this must run inside tenant context or it will not find the
academic year::

    python manage.py tenant_command generate_term_report_cards \
        --schema=s_<tenant> --school buea-gilead-tech

By default a student blocked on fees is SKIPPED, not silently issued a card —
run with ``--ignore-fee-clearance`` when a school wants records produced for
archival regardless of balance. The skip breakdown is the point as much as the
output: a run reporting ``fee_blocked = 197`` of 200 is telling you no parent can
download one either.
"""
from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Generate term report cards for a class (or a whole academic year)."

    def add_arguments(self, parser):
        parser.add_argument("--school", required=True, help="School slug or id.")
        parser.add_argument(
            "--term",
            default="",
            help="Term position (1/2/3). Defaults to the active term.",
        )
        parser.add_argument(
            "--year",
            default="",
            help="Academic year name (e.g. 2025/2026). Defaults to the active year.",
        )
        parser.add_argument(
            "--classroom", default="", help="Classroom code. Omit for every class."
        )
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--ignore-fee-clearance",
            action="store_true",
            help="Generate even for students with an outstanding balance.",
        )
        parser.add_argument(
            "--ignore-publish",
            action="store_true",
            help="Generate even when the term is not published.",
        )
        parser.add_argument("--json", action="store_true", help="Emit JSON.")

    def handle(self, *args, **options):
        from apps.academics.models import AcademicYear, Classroom, Term
        from apps.reports.bulk_generation import generate_term_report_cards
        from apps.schools.school_cli_resolution import resolve_school_arg

        school = resolve_school_arg(options["school"])
        if school is None:
            raise CommandError(f"No school for --school={options['school']!r}.")

        year_name = (options.get("year") or "").strip()
        years = AcademicYear.objects.filter(school=school)
        year = (
            years.filter(name=year_name).first()
            if year_name
            else years.filter(is_active=True).first()
        )
        if year is None:
            raise CommandError(
                f"No {'matching' if year_name else 'active'} academic year for {school.slug}."
            )

        term_pos = (options.get("term") or "").strip()
        terms = Term.objects.filter(academic_year=year)
        term = (
            terms.filter(position=int(term_pos)).first()
            if term_pos.isdigit()
            else terms.filter(is_active=True).first()
        )
        if term is None:
            raise CommandError(
                f"No {'matching' if term_pos else 'active'} term in {year.name}."
            )

        classroom = None
        code = (options.get("classroom") or "").strip()
        if code:
            classroom = Classroom.objects.filter(
                academic_year=year, code=code
            ).first()
            if classroom is None:
                raise CommandError(f"No classroom {code!r} in {year.name}.")

        result = generate_term_report_cards(
            school=school,
            academic_year=year,
            term=term,
            classroom=classroom,
            enforce_publish=not options.get("ignore_publish"),
            enforce_fee_clearance=not options.get("ignore_fee_clearance"),
            dry_run=bool(options.get("dry_run")),
        )
        payload = result.as_dict()

        if options.get("json"):
            self.stdout.write(json.dumps(payload, indent=2, default=str))
            return

        scope = classroom.name if classroom is not None else "all classes"
        prefix = "[dry-run] " if options.get("dry_run") else ""
        self.stdout.write(
            f"{prefix}{school.slug} — {year.name} {term.label} ({scope}): "
            f"{payload['generated']} generated, {payload['skipped']} skipped "
            f"of {payload['students']} students."
        )
        for reason, count in sorted(payload["reasons"].items()):
            self.stdout.write(f"  skipped[{reason}] = {count}")
        if payload["skipped"] and not payload["generated"]:
            self.stdout.write(
                self.style.WARNING(
                    "No report cards produced. If everyone is fee_blocked, the school's "
                    "debt gate is on and no parent can download one either."
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS("Done."))
