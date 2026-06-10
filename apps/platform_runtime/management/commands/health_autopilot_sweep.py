"""Health self-healing sweep — propose (and, with --apply + policy, apply) remediations.

SHADOW by default: prints proposals/previews and mutates nothing. With ``--apply`` the
engine still applies only kinds an operator has enabled via ``WorkflowAutopilotPolicy``
(workflow_key="health_autopilot"); everything without a policy stays a shadow proposal.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.platform_runtime import health_autopilot as ha


class Command(BaseCommand):
    help = "Propose/apply autonomous tenant health remediations (shadow by default)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--school-id", dest="school_id", default="", help="UUID of a single school."
        )
        parser.add_argument(
            "--all-active", action="store_true", help="Sweep every active school."
        )
        parser.add_argument(
            "--platform", action="store_true", help="Also evaluate platform-scope signals."
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Allow policy-enabled kinds to apply (kinds without a policy stay shadow).",
        )

    def handle(self, *args, **options):
        from apps.schools.models import School

        school_id = (options.get("school_id") or "").strip()
        all_active = bool(options.get("all_active"))
        do_platform = bool(options.get("platform"))
        do_apply = bool(options.get("apply"))

        mode = "APPLY (policy-gated)" if do_apply else "SHADOW (no mutations)"
        self.stdout.write(f"health_autopilot_sweep — mode: {mode}")

        if do_platform:
            for sig in ha.platform_signals():
                self._handle_signal(sig, school=None, do_apply=do_apply)

        if school_id:
            schools = School.objects.filter(pk=school_id)
        elif all_active:
            schools = School.objects.filter(is_active=True).order_by("name")
        else:
            if not do_platform:
                self.stderr.write("Provide --school-id, --all-active, or --platform.")
            return

        for school in schools.iterator():
            for sig in ha.iter_school_signals(school):
                self._handle_signal(sig, school=school, do_apply=do_apply)

    def _handle_signal(self, signal, *, school, do_apply):
        slug = getattr(school, "slug", "") or "platform"
        if do_apply:
            out = ha.try_auto_apply(signal=signal, school=school)
            self.stdout.write(
                f"  [{slug}] signal={signal} kind={out.get('kind')} "
                f"source={out.get('source')} mode={out.get('mode')} "
                f"applied={out.get('applied')} reason={out.get('reason', '-')}"
            )
        else:
            prop = ha.propose_remediation(signal, school=school)
            self.stdout.write(
                f"  [{slug}] signal={signal} -> kind={prop.get('kind')} "
                f"source={prop.get('source', '-')} available={prop.get('auto_fix_available')}"
            )
