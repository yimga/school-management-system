"""The SignupVerification reverse accessor is ``signup_verification``.

``apps/schools/models.py`` declares ``related_name="signup_verification"``. Two
platform_runtime call sites asked for ``signupverification`` -- the accessor
Django would generate with NO related_name -- and both did so with a ``getattr``
default of None. So they never raised: the verification row was simply always
absent, and the branch that depends on it never ran.

That is why a typo survived here and not in, say, an import: the failure has no
symptom. ``apps/lifecycle`` carried the same typo and was fixed; these two were
missed because nothing links them.

The table is ``schools_signupverification`` (Django's default table naming has no
underscore), so the string without the underscore is CORRECT in migrations and in
raw-SQL table lists -- which is exactly why a blanket search-and-replace would be
wrong and why this test scopes itself to attribute access.
"""

from __future__ import annotations

import pathlib
import re

from django.test import SimpleTestCase

_APP = pathlib.Path(__file__).resolve().parent.parent

# `getattr(x, "signupverification"...)` or `x.signupverification` -- attribute
# access only. Never a bare occurrence, which would also match the table name.
_BAD_ATTR = re.compile(r'(?:getattr\s*\(\s*[^,]+,\s*["\']signupverification["\']|\.signupverification\b)')


class SignupVerificationAccessorTests(SimpleTestCase):
    def test_the_model_still_declares_the_underscored_related_name(self):
        # Calibration: if related_name ever changes, the assertion below is
        # enforcing a name that no longer exists.
        from apps.schools.models import School

        self.assertTrue(
            hasattr(School, "signup_verification"),
            "School lost its `signup_verification` reverse accessor",
        )

    def test_no_platform_runtime_module_uses_the_wrong_accessor(self):
        offenders = []
        for path in _APP.rglob("*.py"):
            if "tests" in path.parts:
                continue
            if _BAD_ATTR.search(path.read_text(encoding="utf-8", errors="replace")):
                offenders.append(str(path.relative_to(_APP)))
        self.assertEqual(
            offenders,
            [],
            "these read `signupverification`, which is not the reverse accessor; "
            f"with a getattr default they fail silently forever: {offenders}",
        )

    def test_the_detector_would_catch_the_real_shapes(self):
        """A regex that matches nothing would make the sweep above vacuous."""
        self.assertTrue(_BAD_ATTR.search('getattr(school, "signupverification", None)'))
        self.assertTrue(_BAD_ATTR.search("school.signupverification"))
        # ...and must NOT match the table name, which is spelled this way on purpose.
        self.assertIsNone(_BAD_ATTR.search('"schools_signupverification",'))
