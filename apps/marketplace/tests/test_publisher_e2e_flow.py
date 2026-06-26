"""Publisher submit → review queue E2E (service layer)."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.marketplace.models import MarketplaceReview, PublisherOrganization
from apps.marketplace.partner_submission import list_pending_for_governance
from apps.marketplace.services import upsert_marketplace_submission


class PublisherSubmissionE2EFlowTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="pub@example.com",
            email="pub@example.com",
            password="Test1234!",
        )
        self.publisher = PublisherOrganization.objects.create(
            slug="acme-pub",
            name="Acme Pub",
            verified_contact_email="pub@example.com",
            verification_status=PublisherOrganization.VerificationStatus.VERIFIED,
        )

    def test_third_party_submission_enqueues_security_review(self):
        result = upsert_marketplace_submission(
            user=self.user,
            payload={
                "slug": "acme-widget",
                "name": "Acme Widget",
                "version": "1.0.0",
                "kind": "third_party",
                "manifest": {"scopes": ["students:read"]},
            },
        )
        self.assertIsNotNone(result.get("review_id"))
        pending = list_pending_for_governance()
        self.assertTrue(any(r.listing.app.slug == "acme-widget" for r in pending))
        review = MarketplaceReview.objects.get(pk=result["review_id"])
        self.assertEqual(review.review_type, MarketplaceReview.ReviewType.SECURITY)
        from apps.marketplace.models import MarketplaceListing

        listing = MarketplaceListing.objects.get(app__slug="acme-widget")
        self.assertEqual(listing.status, MarketplaceListing.Status.PENDING_REVIEW)
