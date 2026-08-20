"""Run the convergence scenarios against THIS deployment and print a verdict (G7).

"The appliance converges with the cloud" is a claim about sequences — dark for two weeks
with writes on both sides, a bundle that dies half-applied, a power cut between the apply
and the cursor advance, a clock ten minutes out, the same bundle delivered twice. The
suite proves those against fixtures. This command proves them against the data a real
deployment is actually holding, which is where the surprises live.

SAFE BY CONSTRUCTION: everything runs inside a transaction that is ALWAYS rolled back, so
it can be pointed at a live box or a live cloud without changing a row. It is a
read-with-a-scratchpad, not a migration.

    python manage.py verify_edge_sync_convergence
    python manage.py verify_edge_sync_convergence --school gilead-tech
    python manage.py verify_edge_sync_convergence --entities department,classroom

Exit code is 0 when every scenario converged, 1 otherwise — so it can gate a deploy.
"""
from __future__ import annotations

import sys

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone


class _Rollback(Exception):
    """Raised to unwind the scratchpad transaction once the verdicts are collected."""


class Command(BaseCommand):
    help = "Run the edge<->cloud convergence scenarios against this deployment (read-only)."

    def add_arguments(self, parser):
        parser.add_argument("--school", default="", help="School id, slug or subdomain")
        parser.add_argument("--entities", default="", help="Comma-separated entity filter")
        parser.add_argument("--quiet", action="store_true", help="Only print the summary")

    def handle(self, *args, **options):
        from apps.sync_engine.convergence_harness import ConvergenceHarness

        school = self._resolve_school(options.get("school") or "")
        if school is None:
            self.stderr.write(self.style.ERROR("no school resolved; pass --school"))
            sys.exit(1)
        user = self._principal(school)
        if user is None:
            self.stderr.write(self.style.ERROR("no admin principal to run as"))
            sys.exit(1)
        entities = {
            e.strip().lower()
            for e in (options.get("entities") or "department,classroom,student").split(",")
            if e.strip()
        }

        verdicts = []
        try:
            with transaction.atomic():
                harness = ConvergenceHarness(school, user, entities=entities)
                verdicts.append(harness.clean_sync())
                verdicts.append(harness.midbundle_drop())
                verdicts.append(harness.power_cut_before_cursor())
                verdicts.append(harness.clock_skew())
                verdicts.append(harness.duplicate_bundle())
                verdicts.append(harness.authority_invariants())
                verdicts.append(self._outage(harness, school, entities))
                # Always unwound: this command must never leave a row behind on a box an
                # operator pointed it at in production.
                raise _Rollback()
        except _Rollback:
            pass

        failed = [v for v in verdicts if not v["converged"]]
        if not options.get("quiet"):
            for verdict in verdicts:
                mark = "PASS" if verdict["converged"] else "FAIL"
                style = self.style.SUCCESS if verdict["converged"] else self.style.ERROR
                self.stdout.write(style(f"[{mark}] {verdict['scenario']} — {verdict['note']}"))
                for diff in verdict["differences"][:5]:
                    self.stdout.write(f"        {diff}")
        summary = (
            f"{len(verdicts) - len(failed)}/{len(verdicts)} scenario(s) converged "
            f"for {getattr(school, 'slug', school.pk)} at {timezone.now().isoformat(timespec='seconds')}"
        )
        self.stdout.write((self.style.SUCCESS if not failed else self.style.ERROR)(summary))
        if failed:
            sys.exit(1)

    def _outage(self, harness, school, entities):
        """A 14-day outage using a scratch row on each side, inside the rolled-back block."""
        from apps.academics.models import Department

        stamp = timezone.now().strftime("%H%M%S")
        remote_pk = (
            (Department.objects.order_by("-pk").values_list("pk", flat=True).first() or 0) + 9_000
        )

        def seed_local():
            if "department" in entities:
                Department.objects.create(
                    school=school, name=f"harness-local-{stamp}", code=f"HL-{stamp}"
                )

        def seed_remote():
            if "department" not in entities:
                return []
            return [{
                "entity_type": "department", "id": remote_pk, "client_offline_id": "",
                "changes": {"name": f"harness-remote-{stamp}", "code": f"HR-{stamp}"},
                "updated_at": timezone.now().isoformat(),
            }]

        return harness.outage_both_sides(seed_local, seed_remote)

    def _resolve_school(self, hint):
        from apps.schools.models import School

        qs = School.objects.all()
        if hint:
            return (
                qs.filter(subdomain=hint).first()
                or qs.filter(slug=hint).first()
                or qs.filter(pk=hint).first()
            )
        return qs.first() if qs.count() == 1 else None

    def _principal(self, school):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        try:
            from apps.schools.models import SchoolMembership

            owner = (
                SchoolMembership.objects.filter(school=school, role__in=["owner", "ADMIN"])
                .select_related("user")
                .first()
            )
            if owner is not None and getattr(owner, "user", None) is not None:
                return owner.user
        except Exception:  # noqa: BLE001 — membership shape varies; fall through
            pass
        return User.objects.filter(is_superuser=True).order_by("pk").first()
