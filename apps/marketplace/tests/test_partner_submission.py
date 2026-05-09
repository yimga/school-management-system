"""Tests for the partner-app submission lifecycle."""

from __future__ import annotations

from django.test import TestCase

from apps.marketplace.models import MarketplaceApp, MarketplaceListing, MarketplaceReview
from apps.marketplace.partner_submission import (
    PartnerSubmissionError,
    approve_partner_submission,
    list_pending_for_governance,
    reject_partner_submission,
    request_changes,
    submit_for_review,
)


def _make_app(**overrides):
    base = {
        "slug": overrides.pop("slug", "partner-app-test"),
        "app_key": overrides.pop("app_key", "partner-app-test"),
        "name": "Partner App Test",
        "description": "fixture",
        "kind": MarketplaceApp.AppKind.THIRD_PARTY,
        "version": "1.0.0",
        "manifest": {
            "scopes": ["accounts:read"],
            "widgets": [],
            "events_consumed": [],
            "events_emitted": [],
        },
        "is_intentionally_free": True,
    }
    base.update(overrides)
    return MarketplaceApp.objects.create(**base)


def _make_listing(app: MarketplaceApp) -> MarketplaceListing:
    return MarketplaceListing.objects.create(
        app=app,
        category="test",
        short_description="fixture",
    )


class SubmitForReviewTests(TestCase):
    def test_creates_pending_review_and_flips_listing(self):
        app = _make_app()
        listing = _make_listing(app)

        review = submit_for_review(app)

        self.assertIsNotNone(review.pk)
        self.assertEqual(review.status, MarketplaceReview.Status.PENDING)
        self.assertEqual(review.review_type, MarketplaceReview.ReviewType.SECURITY)
        listing.refresh_from_db()
        self.assertEqual(
            listing.security_review_status, MarketplaceListing.ReviewStatus.PENDING
        )
        self.assertEqual(listing.status, MarketplaceListing.Status.PENDING_REVIEW)

    def test_idempotent_returns_existing_open_review(self):
        app = _make_app()
        _make_listing(app)
        first = submit_for_review(app)
        second = submit_for_review(app)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(
            MarketplaceReview.objects.filter(listing__app=app).count(), 1
        )

    def test_raises_when_listing_missing(self):
        app = _make_app()
        with self.assertRaises(PartnerSubmissionError):
            submit_for_review(app)


class GovernanceQueueTests(TestCase):
    def test_list_pending_returns_only_open_reviews(self):
        app1 = _make_app(slug="a1", app_key="a1")
        app2 = _make_app(slug="a2", app_key="a2")
        _make_listing(app1)
        _make_listing(app2)
        review_open = submit_for_review(app1)
        review_to_approve = submit_for_review(app2)
        approve_partner_submission(review_to_approve)

        pending = list_pending_for_governance()
        self.assertIn(review_open, pending)
        self.assertNotIn(review_to_approve, pending)


class ApproveTests(TestCase):
    def test_approve_flips_listing_to_approved(self):
        app = _make_app()
        listing = _make_listing(app)
        review = submit_for_review(app)

        approve_partner_submission(review, notes="LGTM")

        review.refresh_from_db()
        listing.refresh_from_db()
        self.assertEqual(review.status, MarketplaceReview.Status.APPROVED)
        self.assertEqual(
            listing.security_review_status, MarketplaceListing.ReviewStatus.APPROVED
        )
        self.assertEqual(listing.status, MarketplaceListing.Status.APPROVED)
        self.assertIsNotNone(listing.approved_at)

    def test_approve_rejects_non_security_review(self):
        app = _make_app()
        listing = _make_listing(app)
        review = MarketplaceReview.objects.create(
            listing=listing,
            review_type=MarketplaceReview.ReviewType.LISTING,
            status=MarketplaceReview.Status.PENDING,
        )
        with self.assertRaises(PartnerSubmissionError):
            approve_partner_submission(review)


class RejectTests(TestCase):
    def test_reject_flips_listing_back_to_draft(self):
        app = _make_app()
        listing = _make_listing(app)
        review = submit_for_review(app)

        reject_partner_submission(
            review,
            notes="manifest invalid",
            findings={"manifest_errors": ["missing scope"]},
        )

        review.refresh_from_db()
        listing.refresh_from_db()
        self.assertEqual(review.status, MarketplaceReview.Status.REJECTED)
        self.assertEqual(
            listing.security_review_status, MarketplaceListing.ReviewStatus.REJECTED
        )
        self.assertEqual(listing.status, MarketplaceListing.Status.DRAFT)
        self.assertEqual(
            review.findings_json, {"manifest_errors": ["missing scope"]}
        )


class ChangesRequiredTests(TestCase):
    def test_request_changes_keeps_review_actionable(self):
        app = _make_app()
        listing = _make_listing(app)
        review = submit_for_review(app)

        request_changes(
            review,
            notes="Please add screenshots",
            findings={"missing_assets": ["screenshots"]},
        )

        review.refresh_from_db()
        listing.refresh_from_db()
        self.assertEqual(
            review.status, MarketplaceReview.Status.CHANGES_REQUIRED
        )
        self.assertEqual(
            listing.security_review_status,
            MarketplaceListing.ReviewStatus.CHANGES_REQUIRED,
        )
