"""
Publishing / listing rules for public marketplace installs (developer platform).

Install enforcement lives in ``services._assert_app_installable``; these helpers expose
the same rules for API/UI and tests.
"""

from __future__ import annotations

from apps.apicenter.models import MarketplaceExtensionSubmission
from apps.marketplace.models import MarketplaceListing


def listing_allows_public_catalog_install(listing: MarketplaceListing | None) -> bool:
    """
    A tenant may install from the public catalog only when the listing is approved
    and not kill-switched (third-party also requires security review — see
    ``_assert_app_installable``).
    """
    if listing is None:
        return False
    if getattr(listing, "kill_switch_active", False):
        return False
    return listing.status == MarketplaceListing.Status.APPROVED


def extension_submission_shows_in_directory(
    row: MarketplaceExtensionSubmission,
) -> bool:
    """Directory / discovery surfaces should only list published (non-deprecated) work."""
    return row.state in {
        MarketplaceExtensionSubmission.State.PUBLISHED,
    }


def extension_submission_allows_new_version_review(
    row: MarketplaceExtensionSubmission,
) -> bool:
    """Operators can publish a new version from an approved or published row."""
    return row.state in {
        MarketplaceExtensionSubmission.State.APPROVED,
        MarketplaceExtensionSubmission.State.PUBLISHED,
    }
