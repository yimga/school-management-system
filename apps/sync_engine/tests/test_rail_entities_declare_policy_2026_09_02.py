"""Every entity on the edge rail must be CLASSIFIED, in one of the two places (2026-09-02).

An entity's conflict behaviour is decided by ``sync_services._sync_conflict_policy``, and
it resolves in three tiers, not two:

  1. declared in ``policy_registry.POLICIES``  -> that policy;
  2. else listed in ``sync_services._LWW_SAFE_ENTITIES`` -> ``CAUSAL_LWW``, NOT protected;
  3. else ``get_policy``'s fail-closed default -> ``MANUAL_REVIEW`` + ``protected``.

Tier 2 is the one that is easy to miss, and missing it inverts the picture completely.
Reading ``get_policy`` alone says 13 of the 17 registered entities have "no policy" and
therefore fail closed to protected manual review. That is wrong. They are deliberately
listed as LWW-safe, each with its own rationale comment, and the rail's real shape is the
opposite of what the registry alone suggests:

    MEASURED 2026-09-02, through _sync_conflict_policy (the function the apply path uses):
      15 of 17 entities are causal_lww, NOT protected  -- they merge two way
       2 of 17 are protected: `evaluation` (marks) and `invoice` (money)
       0 of 17 are unclassified

So offline edits to student, classroom, applicant, subject, term, the teaching grid and
the staff roster already converge; they do not queue for a human. Safety on the rail is
concentrated where it belongs (grades and money) plus PER-FIELD direction rules for the
teacher entity, rather than smeared across everything as entity-level protection.

WHAT THIS FILE SEALS. Tier 3 is a safety net, not a destination. An entity that reaches it
has had its behaviour chosen by a default rather than by a person -- and the cost runs in
BOTH directions: benign master data that lands there turns every offline correction into a
manual conflict, and sensitive data that lands there is protected only by an accident that
a future edit to the fallback could undo. Either way nobody decided. Today nothing is in
tier 3, and this file makes adding something a failing test rather than a discovery later.

It deliberately does NOT assert which tier an entity belongs in. That is a product
decision about what should happen to a school's data during an outage, and a test that
demanded a particular answer would be asserting a judgement it cannot make.
"""
from __future__ import annotations

from django.test import SimpleTestCase

from apps.api.sync_services import (
    _LWW_SAFE_ENTITIES,
    _conflict_decision,
    _get_entity_config,
    _sync_conflict_policy,
)
from apps.sync_engine.policy_registry import POLICIES, get_policy, normalize_entity

# The only entities the rail protects at ENTITY level, measured 2026-09-02. Marks and
# money -- the two things a stale appliance must never silently overwrite on the cloud.
PROTECTED_ENTITIES = frozenset({"evaluation", "invoice"})


def _registered():
    return set(_get_entity_config(include_derived=True))


def _classification(entity):
    """Which tier decides this entity: ``"POLICIES"``, ``"_LWW_SAFE"``, or ``None``."""
    norm = normalize_entity(entity)
    if norm in POLICIES:
        return "POLICIES"
    if entity in _LWW_SAFE_ENTITIES or norm in _LWW_SAFE_ENTITIES:
        return "_LWW_SAFE"
    return None


def _unclassified():
    return {e for e in _registered() if _classification(e) is None}


class EveryRailEntityIsClassifiedTests(SimpleTestCase):
    """The ratchet. Nothing may reach the fail-closed default by omission."""

    def test_nothing_falls_through_to_the_default(self):
        missing = _unclassified()
        self.assertEqual(
            missing, set(),
            "Registered on the edge rail but classified nowhere, so conflict behaviour "
            "comes from get_policy's fallback for UNKNOWN entities rather than from a "
            "decision: %s. Put each in policy_registry.POLICIES (with a rationale) or in "
            "sync_services._LWW_SAFE_ENTITIES (with a comment saying why converging by "
            "timestamp is safe for it)." % sorted(missing),
        )

    def test_the_detector_can_actually_report_something(self):
        # PROVE THE ZERO. A ratchet that reports "0 unclassified" is worthless until it is
        # shown capable of reporting more than zero -- a broken lookup and a clean tree
        # produce the identical green. An entity nobody registered is classified nowhere.
        self.assertIsNone(_classification("an_entity_that_was_never_classified"))
        self.assertIsNotNone(_classification("invoice"))
        self.assertIsNotNone(_classification("student"))

    def test_an_unclassified_entity_really_does_fail_closed(self):
        # And that the consequence is what the docstring claims, so the ratchet is
        # protecting against a real outcome rather than a supposed one.
        strategy, protected = _sync_conflict_policy("an_entity_that_was_never_classified")
        self.assertEqual(strategy, "manual_review")
        self.assertTrue(protected)


class OnlyMarksAndMoneyAreProtectedTests(SimpleTestCase):
    """Pins the SHAPE of the rail's safety, which is easy to erode one entity at a time."""

    def test_the_protected_set_is_exactly_marks_and_money(self):
        actual = {e for e in _registered() if _sync_conflict_policy(e)[1]}
        self.assertEqual(
            actual, set(PROTECTED_ENTITIES),
            "The set of entity-level protected rail entities changed. Widening it makes "
            "offline edits queue for a human; narrowing it lets a stale box overwrite the "
            "cloud. Either may be right, but it must be deliberate.",
        )

    def test_a_box_may_not_push_marks_or_money_upward(self):
        for entity in sorted(PROTECTED_ENTITIES):
            with self.subTest(entity=entity):
                self.assertEqual(
                    _conflict_decision(entity, "edge-push", None, None), "conflict"
                )

    def test_the_cloud_may_still_send_them_down(self):
        # Protected means cloud-authoritative, NOT blocked. A bursar has to be able to see
        # what is owed while the link is down.
        for entity in sorted(PROTECTED_ENTITIES):
            with self.subTest(entity=entity):
                self.assertEqual(
                    _conflict_decision(entity, "cloud-pull", None, None), "apply"
                )


class TheRestGenuinelyMergeTests(SimpleTestCase):
    """CONTROLS. The everyday case -- a school working through an outage.

    These pass on today's tree and would have passed before this file existed; they are
    here because the claim "offline edits land" is the one an operator relies on, and it
    should be asserted rather than inferred from a policy table.
    """

    def test_ordinary_school_data_converges_two_way(self):
        for entity in ("student", "classroom", "applicant", "subject", "term",
                       "subject_assignment", "teacher", "attendance"):
            with self.subTest(entity=entity):
                strategy, protected = _sync_conflict_policy(entity)
                self.assertFalse(
                    protected,
                    "%s is protected, so every edit made on a box during an outage "
                    "becomes a manual conflict." % entity,
                )
                self.assertEqual(strategy, "causal_lww")

    def test_the_fail_closed_default_still_exists(self):
        # It must stay. Deleting it would turn every future unregistered entity into a
        # silent two-way merge, which is the failure this whole tiering guards against.
        p = get_policy("an_entity_that_does_not_exist")
        self.assertTrue(p.protected)
        self.assertEqual(p.strategy, "manual_review")

    def test_teacher_is_lww_at_entity_level_and_guarded_per_field(self):
        # The one entity that is both: benign roster data merges, while pay, authorization
        # and offboarding columns are down-only. Entity-level protection would have made
        # every offline phone-number correction a conflict for no gain.
        from apps.api.sync_services import _DOWN_ONLY_FIELDS_PER_ENTITY

        self.assertFalse(_sync_conflict_policy("teacher")[1])
        self.assertIn("salary_amount", _DOWN_ONLY_FIELDS_PER_ENTITY["teacher"])
        self.assertIn("allow_finance_panel", _DOWN_ONLY_FIELDS_PER_ENTITY["teacher"])
