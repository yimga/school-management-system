"""The number a school is GIVEN must be a number that school can SAVE.

``render_admission_number`` builds an admission number from the school's
``admission_number_template`` (or its strategy). ``StudentProfile.clean`` validated it
against a hardcoded regex that assumed the FULL strategy whenever the school had set no
explicit ``admission_number_pattern``. Every other shape was therefore rejected by the
platform that had just issued it, and the admin form's own promise -- "Leave blank to
auto-generate" -- could not be kept.

Measured on a live school (template ``{year_2digit}{school_code}{seq_4digit}``): the
platform issued ``25GS0001`` and then refused to save it with "Admission number must
match the required format".

The property under test is a round trip, not a regex: for every shape the renderer can
produce, the validator must accept the result.
"""

from __future__ import annotations

import re

from django.test import SimpleTestCase

from apps.siteconfig.identifier_policy_service import (
    admission_number_pattern_for,
    render_admission_number,
)

RENDER_KWARGS = dict(
    year_2digit="25",
    school_code="GS",
    seq_4digit="0001",
    spec_code="XX",
    class_segment="F6",
    node_code="",
)


def _policy(**over):
    base = {
        "admission_number_strategy": "FULL",
        "admission_number_template": "",
        "admission_number_pattern": "",
    }
    base.update(over)
    return base


class RenderedNumberIsAlwaysValidTests(SimpleTestCase):
    """Whatever the renderer emits, the validator must accept."""

    def test_every_builtin_strategy_round_trips(self) -> None:
        for strategy in ("FULL", "YEAR_SEQ", "SEQ_ONLY"):
            with self.subTest(strategy=strategy):
                policy = _policy(admission_number_strategy=strategy)
                issued = render_admission_number(policy, **RENDER_KWARGS)
                pattern = admission_number_pattern_for(policy)
                self.assertTrue(
                    re.match(pattern, issued),
                    f"{strategy} issued {issued!r} which its own validator rejects",
                )

    def test_the_live_school_template_round_trips(self) -> None:
        """The exact shape that failed in production."""
        policy = _policy(
            admission_number_strategy="TEMPLATE",
            admission_number_template="{year_2digit}{school_code}{seq_4digit}",
        )
        issued = render_admission_number(policy, **RENDER_KWARGS)
        self.assertEqual(issued, "25GS0001")
        self.assertTrue(re.match(admission_number_pattern_for(policy), issued))

    def test_a_dashed_template_round_trips(self) -> None:
        policy = _policy(
            admission_number_strategy="TEMPLATE",
            admission_number_template="{year_2digit}-{school_code}-{seq_4digit}",
        )
        issued = render_admission_number(policy, **RENDER_KWARGS)
        self.assertEqual(issued, "25-GS-0001")
        self.assertTrue(re.match(admission_number_pattern_for(policy), issued))

    def test_node_code_and_empty_segments_round_trip(self) -> None:
        """node_code and spec/class are legitimately EMPTY on many schools."""
        policy = _policy(admission_number_strategy="FULL")
        kwargs = dict(RENDER_KWARGS, node_code="N2", spec_code="", class_segment="")
        issued = render_admission_number(policy, **kwargs)
        self.assertTrue(re.match(admission_number_pattern_for(policy), issued))


class ExplicitAndLegacyTests(SimpleTestCase):
    def test_an_explicit_pattern_wins(self) -> None:
        """A school that has written a pattern has decided; we do not override it."""
        policy = _policy(admission_number_pattern=r"^ABC\d{3}$")
        self.assertEqual(admission_number_pattern_for(policy), r"^ABC\d{3}$")

    def test_legacy_dashed_numbers_still_validate(self) -> None:
        """Re-saving a student holding a number this platform issued must not fail."""
        pattern = admission_number_pattern_for(_policy())
        self.assertTrue(re.match(pattern, "25-GS-0001-SCI-F6"))

    def test_an_unknown_placeholder_falls_through_like_the_renderer(self) -> None:
        """render_admission_number ignores a template it cannot format and uses the
        strategy; the pattern has to fall through at exactly the same point."""
        policy = _policy(
            admission_number_strategy="YEAR_SEQ",
            admission_number_template="{year_2digit}{not_a_placeholder}",
        )
        issued = render_admission_number(policy, **RENDER_KWARGS)
        self.assertEqual(issued, "25GS0001")
        self.assertTrue(re.match(admission_number_pattern_for(policy), issued))

    def test_the_validator_still_rejects_a_wrong_shape(self) -> None:
        """The fix must not turn the gate into a rubber stamp."""
        policy = _policy(
            admission_number_strategy="TEMPLATE",
            admission_number_template="{year_2digit}{school_code}{seq_4digit}",
        )
        pattern = admission_number_pattern_for(policy)
        for bad in ("hello", "25GS", "GS250001", "25GS0001!!"):
            with self.subTest(bad=bad):
                self.assertIsNone(re.match(pattern, bad), f"{bad!r} should be rejected")
