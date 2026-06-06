"""Production static-files storage: content-hashed + pre-compressed + immutable-cacheable.

Why this exists
---------------
The platform ships ~200 static assets per operator page. Under the framework-default
``StaticFilesStorage`` the filenames carry no content hash, so WhiteNoise cannot mark
them ``immutable`` and the browser revalidates *every* asset on *every* navigation
(``Cache-Control: max-age=0``). That is the dominant cause of slow page loads.

WhiteNoise's ``CompressedManifestStaticFilesStorage`` fixes this — hashed filenames get
``Cache-Control: public, max-age=31536000, immutable`` (zero requests on repeat visits)
plus gzip/brotli pre-compression. But the *strict* manifest backend aborts
``collectstatic`` when a collected JS/CSS file references a sibling that isn't shipped
(e.g. vendored ``unfold/js/chart/chart.umd.js`` points at a ``chart.umd.js.map`` source
map that upstream omits). That single missing dev-only reference would break the deploy
build, which is why the hashed backend was previously left disabled.

This subclass makes reference resolution *forgiving*: a missing referenced file is left
un-hashed (served as-is) instead of raising, and ``manifest_strict = False`` keeps runtime
``{% static %}`` lookups from raising on anything that slipped through. Everything that
*can* be hashed still is — so the immutable-caching win applies to the whole real asset
set, and only stray dev source maps fall back to plain serving.

Wired in ``config/settings.py`` for production only (``DEBUG = False``); local dev/test
keep the plain backend so ``runserver`` works without a pre-built manifest.
"""
from __future__ import annotations

import logging

from whitenoise.storage import CompressedManifestStaticFilesStorage

logger = logging.getLogger("siteconfig.staticfiles")


class ForgivingCompressedManifestStaticFilesStorage(CompressedManifestStaticFilesStorage):
    """Hashed + compressed manifest storage that does not abort on missing references."""

    # Don't raise at runtime if a name isn't in the manifest — fall back to the
    # passed name. Belt-and-suspenders alongside the hashed_name override below.
    manifest_strict = False

    def hashed_name(self, name, content=None, filename=None):
        try:
            return super().hashed_name(name, content, filename)
        except ValueError as exc:
            # A referenced asset (e.g. a vendored JS source map) is missing from the
            # collected tree. Serve the referrer un-rewritten rather than failing the
            # whole collectstatic / deploy build over a dev-only file.
            logger.warning("staticfiles: leaving %r un-hashed (missing reference: %s)", name, exc)
            return name


__all__ = ["ForgivingCompressedManifestStaticFilesStorage"]
