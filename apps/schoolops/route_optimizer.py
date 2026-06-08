"""Offline greedy bus-route optimiser (Wave D — logistics).

Orders a route's stops with a nearest-neighbour heuristic over great-circle
(haversine) distance — 100% offline, no external map API, no extra deps. This is
the honest "greedy kernel" first cut (like academics/timetable_solver): it cuts
obvious back-tracking; a true VRP/2-opt pass can layer on later.

Stops without coordinates keep their existing sequence (graceful degradation).
See docs/GLOCAL_SOVEREIGNTY_PLAN.md (Wave D) and register row
``smart-fleet-route-optimizer``.
"""

from __future__ import annotations

import math
from typing import Any

from django.db import transaction

_EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    """Great-circle distance in km between two WGS84 points."""
    rlat1, rlon1, rlat2, rlon2 = (math.radians(float(v)) for v in (lat1, lon1, lat2, lon2))
    dlat = rlat2 - rlat1
    dlon = rlon2 - rlon1
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def _has_coords(stop) -> bool:
    return stop.latitude is not None and stop.longitude is not None


def optimize_stop_order(stops, *, start_stop=None) -> dict[str, Any]:
    """Return a nearest-neighbour ordering of `stops`.

    Result: {"ok", "ordered": [stop,...], "total_km", "optimised": bool,
    "skipped_no_coords": [stop,...]}. If <2 stops have coords, returns the input
    order unchanged with optimised=False.
    """
    stops = list(stops)
    with_coords = [s for s in stops if _has_coords(s)]
    without = [s for s in stops if not _has_coords(s)]
    if len(with_coords) < 2:
        return {
            "ok": True,
            "ordered": stops,
            "total_km": 0.0,
            "optimised": False,
            "skipped_no_coords": without,
        }

    remaining = list(with_coords)
    current = start_stop if (start_stop in remaining) else remaining[0]
    ordered = [current]
    remaining.remove(current)
    total = 0.0
    while remaining:
        nxt = min(
            remaining,
            key=lambda s: haversine_km(current.latitude, current.longitude, s.latitude, s.longitude),
        )
        total += haversine_km(current.latitude, current.longitude, nxt.latitude, nxt.longitude)
        ordered.append(nxt)
        remaining.remove(nxt)
        current = nxt

    # Coordinate-less stops are appended in their original order, after the tour.
    return {
        "ok": True,
        "ordered": ordered + without,
        "total_km": round(total, 3),
        "optimised": True,
        "skipped_no_coords": without,
    }


def optimize_route(route_id, *, persist: bool = False, start_stop_id=None) -> dict[str, Any]:
    """Optimise a Route's stops; optionally persist the new `sequence` values."""
    from apps.schoolops.models import Route, Stop

    route = Route.objects.filter(pk=route_id).first()  # tenant-isolation-allow: pk-route-lookup-view-layer-school-bind
    if route is None:
        return {"ok": False, "error": "Route not found."}
    stops = list(Stop.objects.filter(route=route).order_by("sequence", "id"))
    start = next((s for s in stops if s.pk == start_stop_id), None) if start_stop_id else None
    result = optimize_stop_order(stops, start_stop=start)

    if persist and result["optimised"]:
        # Two-phase to respect the (route, sequence) unique constraint: vacate the
        # 0..n-1 space by parking everything above the current max, then assign.
        ordered = result["ordered"]
        temp_base = max((s.sequence or 0) for s in ordered) + 1
        with transaction.atomic():
            for offset, stop in enumerate(ordered):
                stop.sequence = temp_base + offset
                stop.save(update_fields=["sequence"])
            for index, stop in enumerate(ordered):
                stop.sequence = index
                stop.save(update_fields=["sequence"])

    result["route_id"] = route_id
    result["ordered_stop_ids"] = [s.pk for s in result["ordered"]]
    return result
