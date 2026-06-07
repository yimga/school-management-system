"""Wave D — offline greedy bus-route optimiser."""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.test import TestCase

from apps.schoolops.models import Route, Stop
from apps.schoolops.route_optimizer import (
    haversine_km,
    optimize_route,
    optimize_stop_order,
)
from apps.schools.models import School


class HaversineTests(TestCase):
    def test_known_distance(self):
        # London (51.5074,-0.1278) -> Paris (48.8566,2.3522) ~ 343 km
        d = haversine_km(51.5074, -0.1278, 48.8566, 2.3522)
        self.assertTrue(330 < d < 360, d)

    def test_zero_distance(self):
        self.assertAlmostEqual(haversine_km(1, 1, 1, 1), 0.0, places=6)


class OptimizeStopOrderTests(TestCase):
    databases = {"default"}

    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"RT {uid}", slug=f"rt-{uid}", subdomain=f"rt{uid}", is_active=True
        )
        self.route = Route.objects.create(school=self.school, name=f"R {uid}")

    def _stop(self, name, seq, lat=None, lon=None):
        return Stop.objects.create(
            route=self.route,
            name=name,
            sequence=seq,
            latitude=Decimal(str(lat)) if lat is not None else None,
            longitude=Decimal(str(lon)) if lon is not None else None,
        )

    def test_nearest_neighbour_reorders(self):
        # Deliberately bad input order: A(0,0), C(0,2), B(0,1)
        a = self._stop("A", 0, 0.0, 0.0)
        c = self._stop("C", 1, 0.0, 2.0)
        b = self._stop("B", 2, 0.0, 1.0)
        res = optimize_stop_order([a, c, b], start_stop=a)
        self.assertTrue(res["optimised"])
        # nearest-neighbour from A should visit B before C
        names = [s.name for s in res["ordered"]]
        self.assertEqual(names, ["A", "B", "C"])
        self.assertGreater(res["total_km"], 0)

    def test_under_two_coords_unchanged(self):
        a = self._stop("A", 0, 0.0, 0.0)
        b = self._stop("B", 1)  # no coords
        res = optimize_stop_order([a, b])
        self.assertFalse(res["optimised"])
        self.assertEqual([s.name for s in res["ordered"]], ["A", "B"])

    def test_coordless_stops_appended(self):
        a = self._stop("A", 0, 0.0, 0.0)
        b = self._stop("B", 1, 0.0, 1.0)
        x = self._stop("X", 2)  # no coords
        res = optimize_stop_order([a, b, x], start_stop=a)
        self.assertTrue(res["optimised"])
        self.assertEqual(res["ordered"][-1].name, "X")  # coordless last

    def test_optimize_route_persists_sequence(self):
        self._stop("A", 0, 0.0, 0.0)
        self._stop("C", 1, 0.0, 2.0)
        self._stop("B", 2, 0.0, 1.0)
        res = optimize_route(self.route.id, persist=True)
        self.assertTrue(res["optimised"])
        seqs = {s.name: s.sequence for s in Stop.objects.filter(route=self.route)}
        # B (closer to A) should now precede C
        self.assertLess(seqs["B"], seqs["C"])

    def test_optimize_route_missing(self):
        self.assertFalse(optimize_route(999999)["ok"])
