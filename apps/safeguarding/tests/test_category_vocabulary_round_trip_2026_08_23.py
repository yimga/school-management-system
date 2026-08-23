"""The wizard must offer categories the kernel can actually resolve.

``dynamic_safeguarding_incident_medical.json`` step ``incident_categorization`` is
``required: true`` and takes its options from
``wizard_resolvers::list_incident_categories``, which returned an eleven-key
vocabulary -- medical_emergency, bullying_report, abuse_disclosure, ... -- with
ZERO overlap with the kernel's KCSIE registry (physical_abuse, neglect,
child_on_child_abuse, fgm, ...).

``apply_enabled_categories`` filters the selection to keys it knows:

    selected = [str(v) for v in _normalize_multi(payload) if str(v) in known]
    blob["enabled_categories"] = selected or list(known)

Disjoint vocabularies mean ``selected`` is ALWAYS empty, so the `or` fell through
and wrote every category. A school that deliberately narrowed its categories got
all thirteen back, silently, on every single run of a step it was forced to
complete.

WHY NO TEST CAUGHT IT: the writer's own test calls
``apply_enabled_categories`` with ["physical_abuse", "self_harm"] -- valid kernel
keys the WIZARD could never have produced. It exercises the filter with input the
real caller cannot supply, so it passes while the real path silently discards
everything. These tests go through the resolver, which is the only way to see it.
"""

from __future__ import annotations

import uuid

from django.test import TestCase

from apps.safeguarding.concern_kernel import get_category, list_categories
from apps.safeguarding.services import enabled_categories_for_school
from apps.schools.models import School


class CategoryVocabularyRoundTripTests(TestCase):
    def setUp(self):
        slug = f"sgcat-{uuid.uuid4().hex[:8]}"
        self.school = School.objects.create(
            name="Category School", slug=slug, subdomain=slug
        )

    def _offered(self):
        from apps.setup_studio.wizard_resolvers import list_incident_categories

        return [str(o["value"]) for o in list_incident_categories(
            request=None, school=self.school
        )]

    def test_the_resolver_offers_something(self):
        # Calibration: an empty option list would make the assertions below vacuous.
        self.assertGreater(len(self._offered()), 5)

    def test_every_offered_category_resolves_in_the_kernel(self):
        unknown = [key for key in self._offered() if get_category(key) is None]
        self.assertEqual(
            unknown,
            [],
            "the wizard offers categories the kernel cannot resolve, so a school's "
            f"selection is filtered to nothing and silently replaced: {unknown}",
        )

    def test_a_narrowed_selection_actually_narrows(self):
        """The point of a required configuration step."""
        from apps.setup_studio.wizard_resolvers import write_safeguarding_categories

        offered = self._offered()
        chosen = offered[:2]
        write_safeguarding_categories(
            school=self.school,
            wizard_key="dynamic_safeguarding_incident_medical",
            step_key="incident_categorization",
            payload={"value": chosen},
            actor_user_id=None,
        )
        self.school.refresh_from_db()
        resolved = [c.key for c in enabled_categories_for_school(self.school)]
        self.assertEqual(
            sorted(resolved),
            sorted(chosen),
            "the school chose two categories and got a different set back",
        )
        self.assertLess(
            len(resolved),
            len(list_categories()),
            "a narrowed selection that returns every category is not a selection",
        )
