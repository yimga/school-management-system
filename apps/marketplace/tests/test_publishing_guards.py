"""Publishing guard helpers (listing + extension submission states)."""

from django.test import TestCase

from apps.apicenter.models import MarketplaceExtensionSubmission
from apps.marketplace.models import MarketplaceListing
from apps.marketplace.publishing_guards import (
    extension_submission_shows_in_directory,
    listing_allows_public_catalog_install,
)


class PublishingGuardsTests(TestCase):
    def test_draft_listing_not_publicly_installable(self):
        listing = MarketplaceListing(
            status=MarketplaceListing.Status.DRAFT,
        )
        self.assertFalse(listing_allows_public_catalog_install(listing))

    def test_approved_listing_public_catalog_installable(self):
        listing = MarketplaceListing(
            status=MarketplaceListing.Status.APPROVED,
            kill_switch_active=False,
        )
        self.assertTrue(listing_allows_public_catalog_install(listing))

    def test_kill_switch_blocks(self):
        listing = MarketplaceListing(
            status=MarketplaceListing.Status.APPROVED,
            kill_switch_active=True,
        )
        self.assertFalse(listing_allows_public_catalog_install(listing))

    def test_deprecated_not_in_directory(self):
        row = MarketplaceExtensionSubmission(
            title="x",
            slug="x-slug",
            state=MarketplaceExtensionSubmission.State.DEPRECATED,
        )
        self.assertFalse(extension_submission_shows_in_directory(row))

    def test_published_in_directory(self):
        row = MarketplaceExtensionSubmission(
            title="y",
            slug="y-slug",
            state=MarketplaceExtensionSubmission.State.PUBLISHED,
        )
        self.assertTrue(extension_submission_shows_in_directory(row))
