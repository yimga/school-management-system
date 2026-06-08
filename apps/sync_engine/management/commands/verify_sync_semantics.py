from django.core.management.base import BaseCommand, CommandError

from apps.sync_engine.conflict_resolver import ResolutionStrategy, resolve_one
from apps.sync_engine.crdt_wire_protocol import (
    GCounterOp,
    ORSetOp,
    gcounter_merge,
    orset_materialize,
    orset_merge,
)
from apps.sync_engine.policy_registry import POLICY_VERSION


class Command(BaseCommand):
    help = "Verify governed conflict policies and replay-safe CRDT convergence."

    def handle(self, *args, **options):
        grade = resolve_one(
            {"entity": "grade_entry"},
            strategy=ResolutionStrategy.SERVER_AUTHORITATIVE,
        )
        if grade["action"] != "manual_review" or not grade["override_blocked"]:
            raise CommandError("protected grade policy was weakened")

        counter_op = GCounterOp(
            kind="GCOUNTER",
            counter_key="telemetry_counter:test",
            actor_id="device-a",
            value=5,
        )
        counter = gcounter_merge(gcounter_merge({}, counter_op), counter_op)
        if counter != {"device-a": 5}:
            raise CommandError("G-counter replay is not idempotent")

        remove = ORSetOp(
            kind="ORSET-REMOVE",
            set_key="lesson_plan_tags:test",
            element="exam",
            tag="",
            observed_tags=("tag-1",),
        )
        add = ORSetOp(
            kind="ORSET-ADD",
            set_key="lesson_plan_tags:test",
            element="exam",
            tag="tag-1",
        )
        left = orset_merge(orset_merge({}, remove), add)
        right = orset_merge(orset_merge({}, add), remove)
        if left != right or orset_materialize(left):
            raise CommandError("OR-set remove/add ordering diverged")

        self.stdout.write(
            self.style.SUCCESS(
                f"SYNC_SEMANTICS_PASS policy_version={POLICY_VERSION}"
            )
        )
