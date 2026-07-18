"""Wedge 32 (TVET) apprentice-hours check must not be pinned permanently GREEN.

Dead-guard backlog item 15. ``_check_wedge_32()`` index 1 ("Apprentice-hours
dual-transcript") read::

    _module_importable("apps.employer.models") or _module_importable("apps.portal.views")

There is no ``apps.employer`` app, so the intended left operand is always False --
but the right operand names *this package's own views module*, which always
imports. The ``or`` therefore pinned the operator readiness check permanently
True regardless of whether the feature exists: a false-green that "reports
success forever".
"""
from __future__ import annotations

from unittest.mock import patch

from django.test import SimpleTestCase

from apps.portal.wedge_checks import _check_wedge_32


class Wedge32ApprenticeCheckTests(SimpleTestCase):
    def test_apprentice_hours_check_not_pinned_green(self):
        # `apps.employer` does not exist in the tree, so the honest answer is
        # False. Against the dead guard this returned True via the always-import
        # `apps.portal.views` fallback.
        self.assertFalse(
            _check_wedge_32()[1],
            "wedge 32 apprentice-hours check reported ready with no apps.employer "
            "app -- the `or apps.portal.views` neighbour pinned it permanently green",
        )

    def test_check_driven_by_employer_signal_not_neighbour(self):
        # Neighbour importable, employer app absent -> must be False.
        with patch(
            "apps.portal.wedge_checks._module_importable",
            side_effect=lambda dotted: dotted == "apps.portal.views",
        ):
            self.assertFalse(_check_wedge_32()[1])
        # Employer app present -> lights up honestly.
        with patch(
            "apps.portal.wedge_checks._module_importable",
            side_effect=lambda dotted: dotted == "apps.employer.models",
        ):
            self.assertTrue(_check_wedge_32()[1])
