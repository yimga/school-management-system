"""
Phase 10 — 4.1: Seed ProcessDefinition rows for admissions, re-enrollment, fee follow-up, approval chains.
Idempotent: creates only if code does not exist.
"""

from django.core.management.base import BaseCommand

from apps.orchestration.models import ProcessDefinition


DEFAULTS = [
    {
        "code": "admissions",
        "name": "Admissions",
        "description": "Long-running admissions workflow (applicant → enrolled).",
    },
    {
        "code": "re_enrollment",
        "name": "Re-enrollment",
        "description": "Re-enrollment cycle (invites, deadlines, confirmation).",
    },
    {
        "code": "fee_follow_up",
        "name": "Fee follow-up",
        "description": "Fee reminder and follow-up sequence.",
    },
    {
        "code": "approval_chain",
        "name": "Approval chain",
        "description": "Multi-step approval workflow (e.g. waiver, policy).",
    },
    {
        "code": "migration_run",
        "name": "Migration run",
        "description": "Data migration run (parity, sync).",
    },
]


class Command(BaseCommand):
    help = "Seed ProcessDefinition rows for orchestration workbench (Phase 10 — 4.1). Idempotent."

    def handle(self, *args, **options):
        created = 0
        for d in DEFAULTS:
            _, was_created = ProcessDefinition.objects.get_or_create(
                code=d["code"],
                defaults={"name": d["name"], "description": d["description"]},
            )
            if was_created:
                created += 1
        self.stdout.write(
            self.style.SUCCESS(
                f"Process definitions: {created} created, {len(DEFAULTS) - created} already present."
            )
        )
