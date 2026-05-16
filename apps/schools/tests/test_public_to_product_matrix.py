"""Wave 6 (v2.77): every `status=shipped` promise must resolve to a real route.

The point: marketing claims `Trust Center`, `Help Center`, `Release Notes`,
`Data Quality Center`, etc. If the route disappears (rename, accidental
removal), this test fails — keeping the public-to-product surface honest.
"""

from __future__ import annotations

from django.test import SimpleTestCase, override_settings
from django.urls import NoReverseMatch, reverse

from apps.schools.public_product_promise_matrix import (
    PUBLIC_TO_PRODUCT_PROMISES,
    all_promises,
    status_counts,
)


class PublicToProductMatrixTests(SimpleTestCase):
    def test_registry_is_not_empty(self):
        self.assertGreater(len(PUBLIC_TO_PRODUCT_PROMISES), 5)

    def test_every_promise_has_unique_slug(self):
        slugs = [p.promise_slug for p in PUBLIC_TO_PRODUCT_PROMISES]
        self.assertEqual(
            len(slugs),
            len(set(slugs)),
            "Promise slugs must be unique — they're stored in dashboards.",
        )

    def test_every_shipped_public_route_resolves(self):
        broken = []
        for promise in PUBLIC_TO_PRODUCT_PROMISES:
            if promise.status != "shipped":
                continue
            try:
                reverse(promise.public_route_name)
            except NoReverseMatch as e:
                broken.append((promise.promise_slug, promise.public_route_name, str(e)))
        self.assertEqual(
            broken,
            [],
            f"Shipped promises with broken PUBLIC routes — marketing claims that point nowhere: {broken!r}",
        )

    def test_every_shipped_product_route_resolves(self):
        broken = []
        for promise in PUBLIC_TO_PRODUCT_PROMISES:
            if promise.status != "shipped" or promise.product_route_name is None:
                continue
            try:
                reverse(
                    promise.product_route_name,
                    kwargs=promise.product_route_kwargs or {},
                )
            except NoReverseMatch as e:
                broken.append(
                    (promise.promise_slug, promise.product_route_name, str(e))
                )
        self.assertEqual(
            broken,
            [],
            f"Shipped promises with broken PRODUCT routes — feature isn't actually wired: {broken!r}",
        )

    def test_all_promises_serializable(self):
        data = all_promises()
        self.assertEqual(len(data), len(PUBLIC_TO_PRODUCT_PROMISES))
        for row in data:
            self.assertIn("promise_slug", row)
            self.assertIn("promise", row)
            self.assertIn("status", row)
            self.assertIn(row["status"], {"shipped", "in-flight", "planned"})

    def test_status_counts_sum_to_total(self):
        counts = status_counts()
        self.assertEqual(
            counts["shipped"] + counts["in-flight"] + counts["planned"],
            counts["total"],
        )
        self.assertEqual(counts["total"], len(PUBLIC_TO_PRODUCT_PROMISES))
