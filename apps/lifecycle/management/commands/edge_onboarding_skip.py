"""Record a ≥12-character skip for one Edge Onboarding infrastructure line.

The operator console POST lives on the manager host and writes THAT school's
``settings``. Go-dark and ``edge_onboarding_verify --include-gate`` run on the
box and read THIS school's overlay. A campus with no uplink still has SSH, so
the skip has to be recordable from a shell on the box — the same host that will
evaluate it.

    python manage.py edge_onboarding_skip --list
    python manage.py edge_onboarding_skip --slug gilead-tech --aspect live_sync_proof \\
        --reason "No uplink at this campus — sovereign-only box."
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        "Record a written skip (≥12 characters) for one onboarding infrastructure "
        "aspect on this school's overlay. Does not dump, restore, or probe the network."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--list",
            action="store_true",
            help="Print the waivable aspect catalog and exit.",
        )
        parser.add_argument("--slug", default="", help="School slug on THIS host.")
        parser.add_argument(
            "--aspect",
            default="",
            help="Catalog key (see --list). Example: live_sync_proof.",
        )
        parser.add_argument(
            "--reason",
            default="",
            help="Why this campus does not have that infrastructure (≥12 characters).",
        )

    def handle(self, *args, **options):
        from apps.lifecycle.edge_onboarding import set_aspect_skip_reason
        from apps.lifecycle.onboarding_waivers import WAIVABLE_ASPECTS
        from apps.schools.models import School

        if options.get("list"):
            for row in WAIVABLE_ASPECTS:
                self.stdout.write(f"{row.key}\t{row.label}\t{row.hint}")
            return

        slug = (options.get("slug") or "").strip()
        aspect = (options.get("aspect") or "").strip()
        reason = options.get("reason") or ""
        if not slug or not aspect:
            raise CommandError(
                "Provide --slug and --aspect, or pass --list to see the catalog."
            )

        school = School.objects.filter(slug=slug).first()
        if school is None:
            raise CommandError(f"School not found: {slug}")

        ok, detail = set_aspect_skip_reason(school, aspect, reason)
        if not ok:
            raise CommandError(detail)
        spec = next((row for row in WAIVABLE_ASPECTS if row.key == aspect), None)
        try:
            from apps.lifecycle.models_edge_onboarding import EdgeOnboardingRun
            from apps.lifecycle.services import _sanitize_payload

            EdgeOnboardingRun.objects.create(
                school=school,
                kind=(spec.run_kind if spec else EdgeOnboardingRun.Kind.SKIP_ASPECT),
                actor_hash="",
                payload=_sanitize_payload(
                    {
                        "reason_len": len(reason.strip()),
                        "aspect": aspect[:64],
                        "via": "cli",
                    }
                ),
            )
        except Exception as extra:  # noqa: BLE001 — overlay already persisted
            self.stderr.write(f"skip recorded; audit row not written: {extra}")
        self.stdout.write(detail)
