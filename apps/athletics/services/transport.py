"""Away-fixture transport linking.

Links an away fixture to a ``schoolops.Route`` via a ``FixtureTravel`` row
(upserted on the fixture OneToOne).
"""

from __future__ import annotations

import logging

from django.db import transaction

logger = logging.getLogger(__name__)


@transaction.atomic
def link_away_fixture_transport(
    *, fixture, route=None, departure_time=None, return_time=None, actor=None
):
    """Upsert the ``FixtureTravel`` linking an AWAY ``fixture`` to a route.

    Raises ``ValueError`` when the fixture is not an away fixture. ``route`` may
    be ``None`` (travel row without a route yet). ``actor`` is accepted for
    call-site parity with the other athletics services.
    """
    from apps.athletics.models import Fixture, FixtureTravel

    if fixture.fixture_type != Fixture.FixtureType.AWAY:
        raise ValueError("transport can only be linked to an away fixture")

    travel, _created = FixtureTravel.objects.update_or_create(
        fixture=fixture,
        defaults={
            "school": fixture.school,
            "route": route,
            "departure_time": departure_time,
            "return_time": return_time,
        },
    )
    return travel


__all__ = ["link_away_fixture_transport"]
