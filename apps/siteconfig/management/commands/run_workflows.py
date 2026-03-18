"""
Run workflow execution engine for a given trigger (Section 5 full execution).
Use from cron: python manage.py run_workflows --trigger=scheduled
Or: --trigger=event --context='{"event_name":"student.enrolled"}'
"""

from django.core.management.base import BaseCommand

from apps.siteconfig.workflow_engine import run_workflows_for_trigger
from apps.siteconfig.models_workflow import TenantWorkflow


class Command(BaseCommand):
    help = "Run all active TenantWorkflows for the given trigger (e.g. scheduled, event, manual)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--trigger",
            type=str,
            default="scheduled",
            help="Trigger type (scheduled, event, manual, webhook).",
        )
        parser.add_argument(
            "--context",
            type=str,
            default="{}",
            help='JSON context dict for condition evaluation (e.g. {"event_name": "student.enrolled"}).',
        )
        parser.add_argument(
            "--school-id",
            type=str,
            default=None,
            help="Optional: run only for this school UUID. Default: all schools with active workflows for this trigger.",
        )

    def handle(self, *args, **options):
        import json

        trigger = (options.get("trigger") or "scheduled").strip()
        context_str = options.get("context") or "{}"
        try:
            context = json.loads(context_str)
        except (ValueError, TypeError, json.JSONDecodeError) as e:
            self.stderr.write(self.style.ERROR(f"Invalid --context JSON: {e}"))
            return
        school_id = options.get("school_id")

        qs = TenantWorkflow.objects.filter(
            is_active=True,
            template__is_active=True,
            template__trigger=trigger,
        ).select_related("school", "template")
        if school_id:
            qs = qs.filter(school_id=school_id)
        schools = list({tw.school for tw in qs if tw.school})
        if not schools:
            self.stdout.write(f"No active workflows for trigger={trigger}")
            return

        total_runs = 0
        for school in schools:
            results = run_workflows_for_trigger(school, trigger, context)
            for r in results:
                total_runs += 1
                if r.get("ok"):
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  {school.slug} {r.get('template_code', '')} ok conditions_passed={r.get('conditions_passed')} actions={len(r.get('actions_run') or [])}"
                        )
                    )
                else:
                    self.stderr.write(
                        self.style.WARNING(
                            f"  {school.slug} {r.get('template_code', '')} error={r.get('error')}"
                        )
                    )
        self.stdout.write(
            self.style.SUCCESS(f"Run {total_runs} workflow(s) for trigger={trigger}")
        )
