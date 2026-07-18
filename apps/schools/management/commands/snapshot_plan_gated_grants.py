"""Grandfather every school's current premium access BEFORE plan-gating goes live.

When ``RMC_PLAN_GATING_ENFORCED`` flips ON, a plan-gated code is granted only by
an explicit plan/addon/``School.features``/Entitlement grant — the module-manifest
and policy union can no longer open it. A school that today reaches a premium
feature *through the union* (an operator toggle, a module manifest, a policy)
would silently lose it at the flip.

This command finds exactly those at-risk grants — codes a school can access today
(pure union, flag OFF) that the plan/addon/feature/Entitlement path does NOT
already cover — and records them as explicit ``School.features`` grants so the
ceiling honors them. It is a no-op for anything the plan already grants.

Usage::

    python manage.py snapshot_plan_gated_grants            # dry-run, shows what would change
    python manage.py snapshot_plan_gated_grants --apply     # write the grants
    python manage.py snapshot_plan_gated_grants --school acme-high --apply

Run this (``--apply``) BEFORE setting ``RMC_PLAN_GATING_ENFORCED=1``. The command
refuses to run while the flag is already ON, because is_feature_enabled would then
report the ceiling answer instead of the union answer and under-capture.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        "Snapshot each school's union-granted plan-gated features into explicit "
        "School.features grants (grandfathering before enabling plan gating)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Persist the grants. Without this the command is a dry-run.",
        )
        parser.add_argument(
            "--school",
            default="",
            help="Limit to a single school by slug or primary key.",
        )

    def handle(self, *args, **options):
        from apps.schools.models import School, is_feature_enabled
        from apps.schools.plan_gating import (
            clear_plan_gated_cache,
            plan_ceiling_grants,
            plan_gated_feature_codes,
            plan_gating_enforced,
        )

        if plan_gating_enforced():
            raise CommandError(
                "RMC_PLAN_GATING_ENFORCED is ON. Run this snapshot BEFORE enabling the "
                "ceiling so the current UNION grants are captured (with the flag ON, "
                "is_feature_enabled already returns the ceiling answer)."
            )

        clear_plan_gated_cache()
        gated = plan_gated_feature_codes()
        if not gated:
            self.stdout.write(
                "No plan-gated codes: no active paid plan differs from the default/free "
                "plan. Nothing to grandfather. The ceiling would be a no-op even when ON."
            )
            return

        apply = bool(options["apply"])
        schools = School.objects.all().order_by("pk")
        selector = (options.get("school") or "").strip()
        if selector:
            if selector.isdigit():
                schools = schools.filter(pk=int(selector))
            else:
                schools = schools.filter(slug=selector)

        total_grants = 0
        touched_schools = 0
        for school in schools.iterator():
            existing = {
                str(k).strip().lower()
                for k in (getattr(school, "features", None) or {})
            }
            added: list[str] = []
            for code in sorted(gated):
                if code in existing:
                    continue
                # Already survives the ceiling (plan/addon/feature/Entitlement)?
                if plan_ceiling_grants(school, code):
                    continue
                # Union grants it today but the ceiling would not -> at risk.
                if is_feature_enabled(school, code):
                    added.append(code)
            if not added:
                continue
            touched_schools += 1
            total_grants += len(added)
            label = school.slug or school.pk
            verb = "GRANT" if apply else "WOULD GRANT"
            self.stdout.write(f"{verb} {label}: {', '.join(added)}")
            if apply:
                features = dict(getattr(school, "features", None) or {})
                for code in added:
                    features[code] = True
                school.features = features
                school.save(update_fields=["features"])

        mode = "APPLIED" if apply else "DRY-RUN (no writes)"
        self.stdout.write(
            self.style.SUCCESS(
                f"Plan-gated grandfather snapshot {mode}: {total_grants} grants across "
                f"{touched_schools} school(s); {len(gated)} plan-gated code(s) considered."
            )
        )
        if not apply and total_grants:
            self.stdout.write("Re-run with --apply to persist these grants.")
