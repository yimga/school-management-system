from django.core.management.base import BaseCommand, CommandError

from apps.academics.models import Term, SubjectAssignment
from apps.evals.services import completion_for_assignment


class Command(BaseCommand):
    """
    Quick CLI helper to see mark completion stats for a subject assignment and term.

    Usage:
        python manage.py mark_completion --assignment <id> --term <id>
    """

    help = "Show mark completion stats for a subject assignment/term."

    def add_arguments(self, parser):
        parser.add_argument(
            "--assignment", type=int, required=True, help="SubjectAssignment ID"
        )
        parser.add_argument("--term", type=int, required=True, help="Term ID")

    def handle(self, *args, **options):
        try:
            sa = SubjectAssignment.objects.get(id=options["assignment"])
        except SubjectAssignment.DoesNotExist:
            raise CommandError(f"SubjectAssignment not found: {options['assignment']}")

        try:
            term = Term.objects.get(id=options["term"])
        except Term.DoesNotExist:
            raise CommandError(f"Term not found: {options['term']}")

        stats = completion_for_assignment(sa, term)
        self.stdout.write(
            f"Assignment: {sa} | Term: {term}\n"
            f"Total students: {stats.total}\n"
            f"Completed: {stats.completed}\n"
            f"Pending: {stats.pending}\n"
            f"Completion: {stats.completion_pct}%"
        )
