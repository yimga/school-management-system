"""The two canonical vocabularies must stay reconcilable, not drift into a break.

Migration Cloud has two column-vocabularies that look divergent:

  * ``platform_runtime.migration_center.MIGRATION_TEMPLATES`` — the human-facing
    PREVIEW contract the connector wizard shows ("teachers" needs staff_number,
    first_name, last_name). Friendly labels.
  * ``accelerators.runmycampus_canonical`` — the internal LANDING vocabulary the
    23-domain classifier + landers speak (``staff``, ``staff_external_id`` …).

They are NOT supposed to be identical (preview label vs landing schema). What
keeps them from becoming a real break is that the connector path re-ingests its
staged rows as ``<entity>.csv`` through the SAME intelligent pipeline, and
``CANONICAL_FILENAME_TO_DOMAIN`` resolves that filename to a real landing domain
(``teachers.csv -> staff``). So a connector "teachers" export lands on the staff
lander by design.

This test pins that contract: EVERY migration_center preview entity must resolve
— via its ``<entity>.csv`` staging filename — to a valid, landable canonical
domain. If someone adds a preview entity with no canonical landing (the way
``receipts`` briefly had none), this fails instead of silently quarantining a
tenant's data.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.migration_cloud.accelerators.runmycampus_canonical import (
    CANONICAL_FILENAME_TO_DOMAIN,
    is_valid_canonical_domain,
)
from apps.platform_runtime.migration_center import MIGRATION_TEMPLATES


class MigrationCenterCanonicalConsistencyTests(SimpleTestCase):
    def test_every_preview_entity_resolves_to_a_landable_domain(self):
        unresolved = []
        for entity in MIGRATION_TEMPLATES:
            staged_filename = f"{entity}.csv"
            domain = CANONICAL_FILENAME_TO_DOMAIN.get(staged_filename)
            if domain is None:
                unresolved.append(
                    f"{entity!r}: staged as {staged_filename!r} but that filename "
                    f"has no entry in CANONICAL_FILENAME_TO_DOMAIN → connector import "
                    f"of this entity has no deterministic landing domain."
                )
                continue
            if not is_valid_canonical_domain(domain):
                unresolved.append(
                    f"{entity!r}: {staged_filename!r} maps to {domain!r}, which is "
                    f"not a valid canonical domain (no lander)."
                )
        self.assertEqual(
            unresolved,
            [],
            "migration_center preview entities that don't reconcile to a landing "
            "domain:\n  " + "\n  ".join(unresolved),
        )

    def test_teachers_alias_lands_on_staff(self):
        """The headline divergence (teachers vs staff) is absorbed by the map."""
        self.assertIn("teachers", MIGRATION_TEMPLATES)
        self.assertEqual(CANONICAL_FILENAME_TO_DOMAIN.get("teachers.csv"), "staff")

    def test_receipts_now_resolves(self):
        """receipts had no mapping (fell to content-classification/quarantine)."""
        self.assertIn("receipts", MIGRATION_TEMPLATES)
        self.assertEqual(CANONICAL_FILENAME_TO_DOMAIN.get("receipts.csv"), "finance")
