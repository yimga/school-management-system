"""G7: nothing measured how far the box's clock is from the cloud's — and the README
overstated the defence against exactly that.

Every cursor in this engine is a wall-clock ``updated_at`` position compared across two
machines. ``get_sync_cursor_for_request`` documents the two races that creates and buys
back what it can with a 120-second overlap. What nothing measured is the quantity that
overlap is denominated in: an appliance in a school with no network time source drifts,
and once the drift exceeds the overlap the protection is gone. A box that is FAST asks
for rows "since" a moment the cloud has not reached; a box that is SLOW re-pulls the same
window forever. Neither shows up as an error — the cycles run and report success.

The measurement costs nothing. HTTP requires a ``Date`` on the response, so the cloud has
been telling every box its own time on every cycle since the first one; the box threw it
away.

(b) is the documentation half. ``apps/sync_engine/README.md`` claimed conflict resolution
is "by logical clock, never by wall clock" and that this is "enforced everywhere". It is
true of the CRDT rail, which ``validate_crdt_kind`` authorizes for four entities. The rail
that carries the school's data resolves by comparing ``client_updated_at < server_dt`` in
``apps.api.sync_services._conflict_decision``. The last test in this file holds the README
to describing which rail does what — in BOTH directions, because writing the delta rail
off as an unguarded wall-clock race would be its own overstatement.
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from django.utils.http import http_date

from apps.schools.models import School
from apps.sync_engine.delta_bundle import export_delta_bundle

_LOCMEM = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "g7-clock-offset",
    }
}


class _FakeResponse:
    def __init__(self, body, headers, code=200):
        self._body = body
        self.headers = headers
        self._code = code

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body

    def getcode(self):
        return self._code


@override_settings(CACHES=_LOCMEM)
class MeasurementTests(SimpleTestCase):
    """The arithmetic, in isolation."""

    def setUp(self):
        cache.clear()

    def test_a_missing_or_unparseable_date_yields_no_reading(self):
        from apps.sync_engine import clock_offset

        self.assertIsNone(clock_offset.measure(None))
        self.assertIsNone(clock_offset.measure({}))
        self.assertIsNone(clock_offset.measure({"server_date": "the day before yesterday"}))

    def test_the_offset_is_measured_against_the_round_trip_midpoint(self):
        """Otherwise a slow link reads as a skewed clock.

        The cloud is exactly right; the box is exactly right; the response simply took
        four seconds to arrive. Measuring against the moment the body finished arriving
        would report a 2-second skew that does not exist — the false positive that would
        teach an operator to ignore this number.
        """
        from apps.sync_engine import clock_offset

        server = timezone.now().replace(microsecond=0)
        reading = clock_offset.measure(
            {
                "server_date": http_date(server.timestamp()),
                "local_sent": server - dt.timedelta(seconds=2),
                "local_received": server + dt.timedelta(seconds=2),
            }
        )
        self.assertIsNotNone(reading)
        self.assertAlmostEqual(reading["offset_seconds"], 0.0, places=1)
        self.assertAlmostEqual(reading["round_trip_seconds"], 4.0, places=1)

    def test_a_fast_box_reports_a_positive_offset(self):
        from apps.sync_engine import clock_offset

        server = timezone.now().replace(microsecond=0)
        local = server + dt.timedelta(minutes=10)
        reading = clock_offset.measure(
            {
                "server_date": http_date(server.timestamp()),
                "local_sent": local,
                "local_received": local,
            }
        )
        self.assertAlmostEqual(reading["offset_seconds"], 600.0, delta=1.5)
        self.assertTrue(clock_offset.is_large(reading))
        self.assertIn("AHEAD", clock_offset.describe(reading))

    def test_a_slow_box_reports_a_negative_offset(self):
        from apps.sync_engine import clock_offset

        server = timezone.now().replace(microsecond=0)
        local = server - dt.timedelta(minutes=10)
        reading = clock_offset.measure(
            {
                "server_date": http_date(server.timestamp()),
                "local_sent": local,
                "local_received": local,
            }
        )
        self.assertAlmostEqual(reading["offset_seconds"], -600.0, delta=1.5)
        self.assertIn("BEHIND", clock_offset.describe(reading))

    def test_a_small_offset_is_recorded_but_says_nothing(self):
        from apps.sync_engine import clock_offset

        server = timezone.now().replace(microsecond=0)
        local = server + dt.timedelta(seconds=3)
        reading = clock_offset.measure(
            {
                "server_date": http_date(server.timestamp()),
                "local_sent": local,
                "local_received": local,
            }
        )
        self.assertFalse(clock_offset.is_large(reading))
        self.assertEqual(clock_offset.describe(reading), "")

    def test_the_threshold_defaults_to_the_cursor_overlap(self):
        """They are the same quantity, and the default says so.

        The overlap IS the engine's whole tolerance for wall-clock disagreement, so an
        offset at or past it has consumed the safety margin the cursors depend on. The
        link is made in ``config/settings.py`` at load (both read the same env pair), so
        this pins the two DEFAULTS together rather than asserting a runtime derivation
        that does not exist — a claim the settings module would quietly stop honouring.
        """
        from django.conf import settings as live

        self.assertEqual(
            live.RMC_EDGE_SYNC_CLOCK_SKEW_WARN_SECONDS,
            live.RMC_EDGE_SYNC_CURSOR_OVERLAP_SECONDS,
            "the skew threshold drifted away from the cursor overlap it is denominated in",
        )

    def test_the_threshold_can_be_set_independently(self):
        from apps.sync_engine import clock_offset

        with override_settings(
            RMC_EDGE_SYNC_CURSOR_OVERLAP_SECONDS=600,
            RMC_EDGE_SYNC_CLOCK_SKEW_WARN_SECONDS=45,
        ):
            self.assertEqual(clock_offset.warn_threshold_seconds(), 45)
        with override_settings(RMC_EDGE_SYNC_CLOCK_SKEW_WARN_SECONDS="nonsense"):
            self.assertEqual(clock_offset.warn_threshold_seconds(), 120)


@override_settings(CACHES=_LOCMEM)
class PullCarriesTheServerDateTests(TestCase):
    def setUp(self):
        cache.clear()
        School.objects.update(is_active=False)
        self.school = School.objects.create(
            name="Clock Box", slug="clock-box", subdomain="clock-box", is_active=True
        )

    def test_the_pull_collects_the_date_header(self):
        from apps.sync_engine import edge_outbox

        server = timezone.now() - dt.timedelta(minutes=7)
        bundle = export_delta_bundle(
            school_id=str(self.school.id), rows=[], device_id="cloud"
        )

        def _urlopen(req, timeout=None):
            return _FakeResponse(bundle, {"Date": http_date(server.timestamp())})

        collected: dict = {}
        with mock.patch("urllib.request.urlopen", side_effect=_urlopen):
            edge_outbox.pull_bundle(
                "https://hub.test/api/v1/sync/bundle/download/", "tok", collect=collected
            )

        self.assertIn(
            "clock",
            collected,
            "the pull threw away the one header that says what time the cloud thinks it is",
        )
        self.assertTrue(collected["clock"]["server_date"])
        self.assertIsNotNone(collected["clock"]["local_sent"])
        self.assertIsNotNone(collected["clock"]["local_received"])


@override_settings(
    RMC_EDGE_SYNC_ENABLED=True,
    RMC_EDGE_OPERATOR_BASE="https://hub.test",
    RMC_SYNC_BUNDLE_SIGNING_KEY="g7-clock-test-key",
    CACHES=_LOCMEM,
)
class TheRunReportsTheOffsetTests(TestCase):
    """End to end through ``run_sync_cycle``, with only the socket faked.

    ``urllib.request.urlopen`` is the seam rather than ``pull_bundle``, so the real
    header parsing, the real measurement and the real note all run.
    """

    def setUp(self):
        cache.clear()
        get_user_model().objects.filter(is_superuser=True).delete()
        get_user_model().objects.create_superuser(
            username="edge-principal-g7", email="g7@example.test", password="x"
        )
        School.objects.update(is_active=False)
        self.school = School.objects.create(
            name="Skew Box", slug="skew-box", subdomain="skew-box", is_active=True
        )

    def _cycle(self, *, server_time):
        from apps.sync_engine import sync_runner

        bundle = export_delta_bundle(
            school_id=str(self.school.id), rows=[], device_id="cloud"
        )

        def _urlopen(req, timeout=None):
            headers = {"Date": http_date(server_time.timestamp())}
            if req.get_method() == "POST":
                return _FakeResponse(b'{"ok": true, "received": 0}', headers)
            return _FakeResponse(bundle, headers)

        with mock.patch("urllib.request.urlopen", side_effect=_urlopen):
            return sync_runner.run_sync_cycle(self.school, mode="live")

    def test_a_large_offset_is_measured_and_named_on_the_run(self):
        result = self._cycle(server_time=timezone.now() - dt.timedelta(minutes=25))

        self.assertIsNotNone(
            result["clock_offset_seconds"],
            "the cycle recorded no clock offset at all; nothing on this box knows how "
            "far its clock has drifted from the side its cursors are compared against",
        )
        self.assertAlmostEqual(result["clock_offset_seconds"], 1500, delta=30)
        self.assertIn(
            "clock",
            result["message"].lower(),
            f"a 25-minute skew left no trace on the run message: {result['message']!r}",
        )
        self.assertIn("AHEAD", result["message"])

    def test_the_reading_is_kept_where_an_operator_can_find_it(self):
        from apps.sync_engine import clock_offset

        self._cycle(server_time=timezone.now() - dt.timedelta(minutes=25))
        stored = clock_offset.last_observed(self.school)
        self.assertIsNotNone(stored)
        self.assertAlmostEqual(stored["offset_seconds"], 1500, delta=30)

    def test_a_healthy_clock_records_a_number_and_says_nothing(self):
        result = self._cycle(server_time=timezone.now())
        self.assertIsNotNone(result["clock_offset_seconds"])
        self.assertLess(abs(result["clock_offset_seconds"]), 30)
        self.assertNotIn("clock is", result["message"])

    def test_a_response_with_no_date_leaves_the_cycle_intact(self):
        from apps.sync_engine import sync_runner

        bundle = export_delta_bundle(
            school_id=str(self.school.id), rows=[], device_id="cloud"
        )

        def _urlopen(req, timeout=None):
            if req.get_method() == "POST":
                return _FakeResponse(b'{"ok": true, "received": 0}', {})
            return _FakeResponse(bundle, {})

        with mock.patch("urllib.request.urlopen", side_effect=_urlopen):
            result = sync_runner.run_sync_cycle(self.school, mode="live")
        self.assertTrue(result["ok"], result.get("error"))
        self.assertIsNone(result["clock_offset_seconds"])


class ReadmeDescribesTheRightRailTests(SimpleTestCase):
    """(b) The README's wall-clock claim must match the code on BOTH rails."""

    @property
    def readme(self) -> str:
        path = Path(__file__).resolve().parents[1] / "README.md"
        return path.read_text(encoding="utf-8")

    def test_the_logical_clock_claim_is_scoped_to_the_crdt_rail(self):
        text = self.readme
        self.assertNotIn(
            "enforced everywhere: **conflict\nresolution is by logical clock",
            text,
            "the README still claims the logical-clock rule holds everywhere; it holds "
            "for the four entities validate_crdt_kind authorizes",
        )
        claim = re.search(r"conflict\s+resolution is by logical clock", text)
        self.assertIsNotNone(claim, "the CRDT rail's own guarantee must not be deleted either")
        preamble = text[max(0, claim.start() - 200) : claim.start()]
        self.assertRegex(
            preamble.lower(),
            r"crdt rail",
            "the claim is not scoped to the rail it is true of",
        )

    def test_the_delta_rail_is_named_as_resolving_by_wall_clock(self):
        text = self.readme
        self.assertIn("_conflict_decision", text)
        self.assertIn("client_updated_at", text)
        self.assertRegex(
            text,
            r"(?i)delta rail.{0,400}wall.?clock|wall.?clock.{0,400}delta rail",
            "nothing in the README says which rail actually orders by wall clock",
        )

    def test_it_does_not_overstate_in_the_other_direction_either(self):
        """The delta rail is not an unguarded LWW free-for-all, and saying so would be
        its own inaccuracy: protected domains never reach the timestamp comparison, and a
        row that cannot prove it is newer becomes a conflict rather than an overwrite."""
        text = self.readme
        self.assertIn("protected", text.lower())
        self.assertRegex(
            text,
            r"(?i)cannot prove it is newer|conflict, not an overwrite",
            "the README does not record the guards that bound the wall-clock comparison",
        )

    def test_the_claim_matches_what_the_code_actually_does(self):
        """Pin the README to the source it describes. If ``_conflict_decision`` ever
        stops comparing timestamps, this fails and the README gets revisited."""
        source = (
            Path(__file__).resolve().parents[3] / "apps" / "api" / "sync_services.py"
        ).read_text(encoding="utf-8")
        self.assertIn("client_updated_at < server_dt", source)

    def test_the_crdt_rail_is_still_only_four_entities(self):
        from apps.sync_engine.policy_registry import POLICIES

        allowed = {
            name
            for name, policy in POLICIES.items()
            if getattr(policy, "allowed_crdt_kinds", None)
        }
        self.assertEqual(
            allowed,
            {"student_note", "lesson_plan", "lesson_plan_tags", "telemetry_counter"},
            "the CRDT rail's membership changed; the README paragraph naming four "
            "entities has to change with it",
        )
