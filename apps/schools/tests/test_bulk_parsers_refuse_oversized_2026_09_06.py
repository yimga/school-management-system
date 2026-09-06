"""Every bulk parser refuses an oversized selection instead of trimming it.

The same defect shipped in four modules, which is what a copied idiom does. It
was fixed first in apps/people/bulk_staff_actions.py; a scan for the shape --
``if len(out) >= MAX: break`` reached from a request body -- found three more,
all of them feeding WRITES.

Trimming a bulk write is the bad kind of wrong: it applies to the first N,
reports success, and leaves the remainder untouched with nothing in the response
naming what was skipped. Nobody discovers it until a school that was supposed to
be offboarded is still live, or an operator who was supposed to be demoted still
has the tier.
"""

import uuid

from django.test import TestCase

from apps.schools.bulk_operator_actions import MAX_BULK_IDS as SCHOOL_MAX
from apps.schools.bulk_operator_actions import parse_school_id_list
from apps.schools.bulk_operator_team_actions import MAX_BULK_IDS as TEAM_MAX
from apps.schools.bulk_operator_team_actions import parse_operator_user_id_list


class OperatorBulkParsersRefuseRatherThanTrimTests(TestCase):
    def test_school_ids_within_the_cap_are_returned_whole(self):
        ids = [uuid.uuid4() for _ in range(SCHOOL_MAX)]
        self.assertEqual(parse_school_id_list(ids), ids)

    def test_too_many_schools_is_refused(self):
        ids = [uuid.uuid4() for _ in range(SCHOOL_MAX + 1)]
        with self.assertRaises(ValueError) as ctx:
            parse_school_id_list(ids)
        self.assertIn("Nothing was changed", str(ctx.exception))

    def test_operator_ids_within_the_cap_are_returned_whole(self):
        ids = list(range(1, TEAM_MAX + 1))
        self.assertEqual(parse_operator_user_id_list(ids), ids)

    def test_too_many_operators_is_refused(self):
        with self.assertRaises(ValueError) as ctx:
            parse_operator_user_id_list(list(range(1, TEAM_MAX + 50)))
        self.assertIn("Nothing was changed", str(ctx.exception))

    def test_the_boundary_is_not_off_by_one(self):
        """Exactly MAX is allowed; MAX+1 is not.

        Worth pinning because the replacement changed both the operator and the
        position: the old loop appended and then broke on ``len(out) >= MAX``,
        returning exactly MAX silently, while the new check runs once after the
        loop on ``> MAX`` and raises. An off-by-one here would either refuse a
        selection the UI permits or re-open the silent trim by one row.
        """
        self.assertEqual(len(parse_operator_user_id_list(list(range(1, TEAM_MAX + 1)))), TEAM_MAX)
        with self.assertRaises(ValueError):
            parse_operator_user_id_list(list(range(1, TEAM_MAX + 2)))
