"""
Advancement/grant CHILD tables must carry a school column and an RLS policy.

``AdvancementGift``, ``DonorGiftAccessLink``, ``GrantMilestone`` and
``GrantReport`` reached their tenant only through a parent FK
(``donor -> AdvancementDonor.school`` / ``grant -> GrantApplication.school``).
An RLS policy is keyed on ``school_id``, so a table without that column cannot
have one -- and ``scripts/scan_rls_table_coverage.py`` skips any model without a
``school`` field, so the zero-baseline gate reported 0 findings while four
tenant-owned money/PII tables had no database backstop at all. Under
``USE_DJANGO_TENANTS=0`` (deploy/selfhost/.env.edge.example) RLS *is* the tenant
boundary, so one forgotten ``donor__school_id`` join was a cross-tenant read.

The coverage assertion below runs the REAL gate's table-literal extractor, so it
cannot pass on a table name that the gate itself would not see.
"""

import importlib.util
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

from django.test import TestCase

from apps.schools.models import (
    AdvancementDonor,
    AdvancementGift,
    DonorGiftAccessLink,
    GrantApplication,
    GrantMilestone,
    GrantReport,
    School,
)

REPO_ROOT = Path(__file__).resolve().parents[3]

CHILD_MODELS = (AdvancementGift, DonorGiftAccessLink, GrantMilestone, GrantReport)


def _enumerated_rls_tables():
    """Table literals the real coverage gate can see, via its own extractor."""
    path = REPO_ROOT / "scripts" / "scan_rls_table_coverage.py"
    spec = importlib.util.spec_from_file_location("_rls_cov_probe", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._enumerated_tables()


class AdvancementGrantChildTenantColumnTests(TestCase):
    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Adv {uid}", slug=f"adv-{uid}", subdomain=f"adv{uid}", is_active=True
        )
        self.donor = AdvancementDonor.objects.create(
            school=self.school, display_name=f"Donor {uid}"
        )
        self.grant = GrantApplication.objects.create(
            school=self.school,
            funder_name=f"Funder {uid}",
            requested_amount=Decimal("1000.00"),
        )

    def test_child_models_declare_a_school_field(self):
        missing = [
            m.__name__
            for m in CHILD_MODELS
            if "school" not in {f.name for f in m._meta.get_fields()}
        ]
        self.assertEqual(
            missing,
            [],
            "these tenant-owned tables have no school column, so they can carry "
            "no RLS policy and the coverage gate cannot even see them",
        )

    def test_child_tables_are_enumerated_in_an_rls_migration(self):
        enumerated = _enumerated_rls_tables()
        uncovered = [
            m._meta.db_table for m in CHILD_MODELS if m._meta.db_table not in enumerated
        ]
        self.assertEqual(
            uncovered,
            [],
            "no *rls* migration names these tables, so no policy is ever created "
            "for them under USE_DJANGO_TENANTS=0",
        )

    def test_gift_school_is_derived_from_its_donor(self):
        gift = AdvancementGift.objects.create(
            donor=self.donor, amount=Decimal("50.00"), received_at=date(2026, 1, 1)
        )
        self.assertEqual(gift.school_id, self.school.pk)
        gift.refresh_from_db()
        self.assertEqual(gift.school_id, self.school.pk)

    def test_access_link_school_is_derived_from_its_donor(self):
        from django.utils import timezone

        link = DonorGiftAccessLink.objects.create(
            donor=self.donor,
            expires_at=timezone.now() + timezone.timedelta(days=7),
        )
        self.assertEqual(link.school_id, self.school.pk)

    def test_milestone_and_report_school_is_derived_from_the_grant(self):
        milestone = GrantMilestone.objects.create(grant=self.grant, title="Interim")
        report = GrantReport.objects.create(grant=self.grant)
        self.assertEqual(milestone.school_id, self.school.pk)
        self.assertEqual(report.school_id, self.school.pk)

    def test_explicit_school_is_not_silently_overwritten(self):
        """An explicitly supplied school wins: the derive step only FILLS a blank."""
        other = School.objects.create(
            name="Adv other",
            slug=f"advo-{uuid.uuid4().hex[:8]}",
            subdomain=f"advo{uuid.uuid4().hex[:8]}",
            is_active=True,
        )
        gift = AdvancementGift.objects.create(
            donor=self.donor,
            school=other,
            amount=Decimal("5.00"),
            received_at=date(2026, 1, 2),
        )
        self.assertEqual(gift.school_id, other.pk)
