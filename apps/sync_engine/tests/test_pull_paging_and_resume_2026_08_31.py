"""G2: the cloud->box PULL leg was unpaged and unresumable.

The push leg has paged at ``RMC_SYNC_BUNDLE_MAX_ROWS`` since the backlog work
(``test_edge_sync_backlog_paging_2026_08_17``). The pull leg did not, and the asymmetry
was an omission rather than a design:

* ``run_sync_cycle`` issued ONE ``GET`` with ``entities=None`` and no limit;
* ``SyncBundleDownloadView`` called ``build_edge_delta_bundle`` and streamed the WHOLE
  delta as a single body — on a first sync (``since=None``) that is the entire corpus,
  built and sorted in memory on the operator. A real box applied 31,043 rows this way;
* a link that dropped at 90% restarted from zero, forever. ``file_sync`` was given
  resumable byte ranges for exactly this reason and says so in its module docstring;
  rows had nothing equivalent.

THE CORRECTNESS CONSTRAINT THESE TESTS EXIST FOR. The cursor is a wall-clock
``updated_at``. ``get_sync_cursor_for_request`` documents the tie-at-a-page-boundary hole
and closes it, for a whole CYCLE, with a 120-second overlap. Paging WITHIN a cycle would
reopen it far wider than that overlap can close: a first sync pages across years of
history in one cycle, so by the time the cycle ends its cursor is not 120 seconds past a
split tie group — it is months past it, and the twin is not delayed, it is lost. So a
page boundary may never fall inside a group of rows sharing one ``updated_at``, and that
is asserted directly below rather than assumed.

Failing-first shapes, all behavioural rather than "the symbol does not exist":
  * the download serves every row it has despite being asked for a page (wrong count);
  * the response says nothing about whether more remain, and stamps the CORPUS
    high-water on a partial page — a cursor position past rows it did not send;
  * the runner pulls once and stops, leaving the box behind while reporting success.
"""
from __future__ import annotations

import datetime as dt
import uuid
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.academics.models import AcademicYear
from apps.api.sync_bundle_api import SyncBundleDownloadView
from apps.schools.models import School
from apps.sync_engine.delta_bundle import export_delta_bundle, verify_and_parse_bundle

_PULL = "apps.sync_engine.edge_outbox.pull_bundle"
_POST = "apps.sync_engine.edge_outbox.post_bundle"
_MORE_HEADER = "X-RMC-Sync-More"
_HIGH_WATER_HEADER = "X-RMC-Sync-High-Water"


def _academic_year_entity() -> str:
    """The registry's own name for ``AcademicYear``.

    Looked up rather than hard-coded: the entity key is registry data, and a test that
    spells it out fails for the wrong reason the day the registry is renamed.
    """
    from apps.api.sync_services import _get_entity_config

    for entity_type, (model, _allowed) in _get_entity_config(include_derived=True).items():
        if model is AcademicYear:
            return entity_type
    raise AssertionError("AcademicYear is not on the delta rail; this test needs a new entity")


def _bundle_rows(payload, school_id, entity_type=None):
    rows, errors = verify_and_parse_bundle(payload, expected_school_id=school_id)
    assert not errors, errors
    if entity_type:
        rows = [r for r in rows if r.get("entity_type") == entity_type]
    return rows


def _position(row):
    parsed = parse_datetime(str(row.get("updated_at") or ""))
    if parsed is not None and timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


# --------------------------------------------------------------------------- #
# The page cut itself
# --------------------------------------------------------------------------- #
class PageBoundaryIsACursorPositionTests(TestCase):
    """``page_delta_rows`` must never cut inside a group sharing one ``updated_at``.

    Pure function, no database. Every case here is a way a naive ``rows[:limit]`` loses
    data permanently once the cursor advances past the cut.
    """

    def _rows(self, stamps):
        return [
            {"entity_type": "e", "id": i, "changes": {}, "updated_at": (s.isoformat() if s else None)}
            for i, s in enumerate(stamps)
        ]

    def test_a_trailing_tie_group_is_left_for_the_next_page(self):
        from apps.sync_engine.edge_outbox import page_delta_rows

        base = timezone.now()
        tie = base + dt.timedelta(seconds=5)
        rows = self._rows([base, base + dt.timedelta(seconds=1), tie, tie, tie])

        page, more = page_delta_rows(rows, 3)

        self.assertTrue(more)
        self.assertEqual(
            [r["id"] for r in page],
            [0, 1],
            "the cut landed inside the group sharing one timestamp; the cursor then "
            "advances to that timestamp and `updated_at__gt` excludes the twins forever",
        )
        # And the next page picks the whole group up.
        rest, more_rest = page_delta_rows(
            [r for r in rows if _position(r) > tie - dt.timedelta(seconds=1)], 3
        )
        self.assertFalse(more_rest)
        self.assertEqual([r["id"] for r in rest], [2, 3, 4])

    def test_a_single_group_bigger_than_the_limit_ships_whole(self):
        """The only alternative is a page that is forever empty."""
        from apps.sync_engine.edge_outbox import page_delta_rows

        tie = timezone.now()
        rows = self._rows([tie] * 5)
        page, more = page_delta_rows(rows, 2)
        self.assertEqual(len(page), 5)
        self.assertFalse(more)

    def test_a_page_never_ends_on_a_positionless_row(self):
        """A null ``updated_at`` is not a place a cursor can stand.

        Positionless rows sort FIRST (``build_edge_delta_rows`` says so, so that nothing
        strands them behind an advanced cursor). If a page ENDED on them the response
        would carry no high-water, the box could not advance, and the next request would
        be identical to the last — the same page, forever.
        """
        from apps.sync_engine.edge_outbox import page_delta_rows

        base = timezone.now()
        rows = self._rows([None, None, None, base, base + dt.timedelta(seconds=1)])
        page, more = page_delta_rows(rows, 2)
        self.assertTrue(more)
        self.assertIsNotNone(
            _position(page[-1]),
            "the page ended with no position, so the box has no cursor to resume from",
        )
        self.assertEqual([r["id"] for r in page], [0, 1, 2, 3])

    def test_no_limit_and_a_short_delta_are_unchanged(self):
        from apps.sync_engine.edge_outbox import page_delta_rows

        rows = self._rows([timezone.now() + dt.timedelta(seconds=i) for i in range(3)])
        self.assertEqual(page_delta_rows(rows, None), (rows, False))
        self.assertEqual(page_delta_rows(rows, 0), (rows, False))
        self.assertEqual(page_delta_rows(rows, 99), (rows, False))

    def test_paging_the_whole_delta_loses_no_row_and_repeats_none(self):
        """The end-to-end property: page until exhausted, compare against the corpus.

        Timestamps chosen to be hostile — a positionless group, several ties, a group
        larger than the page — because those are the shapes a boundary bug survives.
        """
        from apps.sync_engine.edge_outbox import page_delta_rows

        base = timezone.now().replace(microsecond=0)
        stamps = (
            [None, None]
            + [base] * 4
            + [base + dt.timedelta(seconds=1)]
            + [base + dt.timedelta(seconds=2)] * 3
            + [base + dt.timedelta(seconds=3)]
        )
        rows = self._rows(stamps)

        seen, cursor, more, guard = [], None, True, 0
        while more and guard < 50:
            guard += 1
            remaining = [
                r
                for r in rows
                if cursor is None or (_position(r) is not None and _position(r) > cursor)
            ]
            page, more = page_delta_rows(remaining, 3)
            self.assertTrue(page, "a page came back empty while more rows remained")
            seen.extend(r["id"] for r in page)
            nxt = _position(page[-1])
            self.assertIsNotNone(nxt)
            cursor = nxt

        self.assertEqual(sorted(seen), list(range(len(rows))), "rows lost across pages")
        self.assertEqual(len(seen), len(set(seen)), "a row was served on two pages")


# --------------------------------------------------------------------------- #
# The download endpoint
# --------------------------------------------------------------------------- #
@override_settings(RMC_SYNC_BUNDLE_SIGNING_KEY="g2-paging-test-key")
class DownloadServesOnePageTests(TestCase):
    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        School.objects.update(is_active=False)
        self.school = School.objects.create(
            name=f"Page {uid}", slug=f"page-{uid}", subdomain=f"page{uid}", is_active=True
        )
        self.user = get_user_model().objects.create_superuser(
            username=f"page_admin_{uid}", password="Test1234", email=f"p{uid}@test.com"
        )
        self.entity = _academic_year_entity()
        self.years = [
            AcademicYear.objects.create(
                school=self.school,
                name=f"Year {i}",
                start_date=dt.date(2020 + i, 9, 1),
                end_date=dt.date(2021 + i, 6, 30),
            )
            for i in range(7)
        ]
        # Distinct, ordered positions so the page boundary is unambiguous.
        base = timezone.now().replace(microsecond=0) - dt.timedelta(hours=1)
        for i, year in enumerate(self.years):
            AcademicYear.objects.filter(pk=year.pk).update(
                updated_at=base + dt.timedelta(seconds=i)
            )
        self.rf = APIRequestFactory()

    def _download(self, query=""):
        request = self.rf.get(f"/api/v1/sync/bundle/download/{query}")
        request.school = self.school
        force_authenticate(request, user=self.user)
        return SyncBundleDownloadView.as_view()(request)

    def _payload(self, resp):
        return resp.getvalue() if hasattr(resp, "getvalue") else resp.content

    def test_limit_serves_at_most_that_many_rows(self):
        resp = self._download(f"?entities={self.entity}&limit=3")
        self.assertEqual(resp.status_code, 200)
        rows = _bundle_rows(self._payload(resp), self.school.id, self.entity)
        self.assertEqual(
            len(rows),
            3,
            "the download ignored `limit` and served the whole delta — this is the "
            "unpaged pull: on a first sync it is the entire corpus in one body",
        )

    def test_the_oldest_rows_are_served_first(self):
        """A page boundary is only a cursor position if the page is the OLDEST rows.

        ``build_edge_delta_rows`` sorts globally by ``updated_at`` for exactly this
        reason; serving the newest first would put the cursor ahead of everything the
        box has not received.
        """
        resp = self._download(f"?entities={self.entity}&limit=3")
        rows = _bundle_rows(self._payload(resp), self.school.id, self.entity)
        self.assertEqual([r["id"] for r in rows], [y.pk for y in self.years[:3]])

    def test_more_header_says_whether_rows_remain(self):
        partial = self._download(f"?entities={self.entity}&limit=3")
        self.assertEqual(
            partial.get(_MORE_HEADER),
            "1",
            "nothing told the box more rows remain, so it stops one page in",
        )
        whole = self._download(f"?entities={self.entity}&limit=50")
        self.assertEqual(whole.get(_MORE_HEADER), "0")

    def test_high_water_follows_the_page_not_the_corpus(self):
        """The header must be a position the box has actually RECEIVED everything up to.

        Stamping the corpus high-water on a partial page hands the box a cursor past
        rows it was never sent; ``updated_at__gt`` then excludes them on every future
        cycle. That is silent, permanent data loss, not a slow sync.
        """
        whole = self._download(f"?entities={self.entity}")
        corpus_high_water = whole[_HIGH_WATER_HEADER]

        resp = self._download(f"?entities={self.entity}&limit=3")
        rows = _bundle_rows(self._payload(resp), self.school.id, self.entity)
        served = max(_position(r) for r in rows)
        header = parse_datetime(resp[_HIGH_WATER_HEADER])
        if timezone.is_naive(header):
            header = timezone.make_aware(header, timezone.get_current_timezone())
        self.assertNotEqual(
            resp[_HIGH_WATER_HEADER],
            corpus_high_water,
            "the partial page carried the CORPUS high-water; the box would advance its "
            "cursor past rows it was never sent and never be offered them again",
        )
        self.assertEqual(
            header,
            served,
            "the high-water is past the last row served; the rows in between are lost",
        )

    def test_paging_the_endpoint_delivers_every_row_exactly_once(self):
        seen, cursor, guard = [], None, 0
        while guard < 20:
            guard += 1
            query = f"?entities={self.entity}&limit=2"
            if cursor:
                query += "&since=" + cursor.replace("+", "%2B")
            resp = self._download(query)
            self.assertEqual(resp.status_code, 200)
            rows = _bundle_rows(self._payload(resp), self.school.id, self.entity)
            seen.extend(r["id"] for r in rows)
            if resp.get(_MORE_HEADER) != "1":
                break
            cursor = resp[_HIGH_WATER_HEADER]
        self.assertEqual(sorted(seen), sorted(y.pk for y in self.years))
        self.assertEqual(len(seen), len(set(seen)))

    def test_an_unpaged_request_is_unchanged(self):
        """Compatibility. A box that predates paging sends no ``limit`` and must keep
        getting the whole delta: it never reads ``X-RMC-Sync-More``, so a server-side
        default page would be read as the entire delta and its cursor would advance past
        rows it never received."""
        resp = self._download(f"?entities={self.entity}")
        rows = _bundle_rows(self._payload(resp), self.school.id, self.entity)
        self.assertEqual(len(rows), 7)
        self.assertEqual(resp.get(_MORE_HEADER), "0")

    def test_a_nonsense_limit_is_rejected_rather_than_guessed(self):
        for bad in ("0", "-4", "abc"):
            resp = self._download(f"?entities={self.entity}&limit={bad}")
            self.assertEqual(resp.status_code, 400, bad)

    def test_a_limit_above_the_server_ceiling_is_capped_not_honoured(self):
        with override_settings(RMC_SYNC_PULL_PAGE_MAX_ROWS=2):
            resp = self._download(f"?entities={self.entity}&limit=1000")
        rows = _bundle_rows(self._payload(resp), self.school.id, self.entity)
        self.assertEqual(len(rows), 2)
        self.assertEqual(resp.get(_MORE_HEADER), "1")

    def test_a_tie_group_straddling_the_boundary_is_not_split_by_the_endpoint(self):
        """The constraint, end to end through the real view.

        Four rows share one timestamp. Asked for three, the endpoint must not serve
        three of them — the fourth would sit behind a cursor standing on its own
        ``updated_at`` and ``__gt`` would never offer it again.
        """
        tie = timezone.now().replace(microsecond=0)
        for year in self.years[3:]:
            AcademicYear.objects.filter(pk=year.pk).update(updated_at=tie)

        resp = self._download(f"?entities={self.entity}&limit=5")
        rows = _bundle_rows(self._payload(resp), self.school.id, self.entity)
        at_tie = [r for r in rows if _position(r) == tie]
        self.assertIn(
            len(at_tie),
            (0, 4),
            f"the page split the 4-row tie group at {tie} ({len(at_tie)} of 4 served); "
            "the rest fall behind the cursor permanently",
        )

    def test_the_parity_repair_pull_is_never_paged(self):
        """``_flush_drifted_entities`` is the one pull whose high-water the runner
        deliberately IGNORES (``since=None``, one entity, cursor left alone). A partial
        page there could never be resumed — there is no cursor and no second request —
        so the rows it left out would be the rows the repair silently failed to repair.
        """
        from apps.api.sync_services import _get_entity_config
        from apps.sync_engine import parity

        model, allowed = _get_entity_config(include_derived=True)[self.entity]
        real = parity.bucket_digests(self.school, self.entity, model, allowed)
        self.assertTrue(real.get("b"), "no non-empty buckets to disagree about")
        # Same fan-out (so the two sides ARE comparable) with every digest corrupted, so
        # every populated bucket drifts and the cloud has to serve all of them. Digests
        # that AGREE would make the endpoint serve nothing, and a test that asserts
        # "not paged" against an empty response proves nothing.
        drifted = {
            "buckets": real["buckets"],
            "b": {i: "0" * len(str(h)) for i, h in real["b"].items()},
        }
        buckets = parity.encode_buckets(drifted)

        resp = self._download(f"?entities={self.entity}&limit=2&parity_buckets={buckets}")
        self.assertEqual(resp.status_code, 200)
        rows = _bundle_rows(self._payload(resp), self.school.id, self.entity)
        self.assertEqual(
            len(rows),
            7,
            "the parity repair response was PAGED; its remainder can never be fetched "
            "because the runner does not advance a cursor on this path",
        )
        self.assertEqual(resp.get(_MORE_HEADER), "0")


# --------------------------------------------------------------------------- #
# The runner
# --------------------------------------------------------------------------- #
class _PagingCloud:
    """A cloud that serves ONE PAGE per request, using the production page cut.

    Holds a frozen snapshot of rows so applying a page on the box (the same database, in
    a test) cannot change what later pages contain.
    """

    def __init__(self, school, rows, *, always_more=False):
        self.school = school
        self.rows = rows
        self.calls: list[dict] = []
        self.always_more = always_more

    def pull(self, endpoint, token, *, since=None, entities=None, timeout=30.0,
             collect=None, limit=None, **_kw):
        from apps.sync_engine.edge_outbox import page_delta_rows

        self.calls.append({"since": since, "limit": limit})
        remaining = [
            r
            for r in self.rows
            if since is None or (_position(r) is not None and _position(r) > since)
        ]
        page, more = page_delta_rows(remaining, limit) if limit else (remaining, False)
        if self.always_more:
            more = True
        high_water = _position(page[-1]) if page else None
        if collect is not None:
            collect["more"] = bool(more)
        return (
            200,
            export_delta_bundle(
                school_id=str(self.school.id), rows=page, device_id="cloud"
            ),
            high_water.isoformat() if high_water else None,
        )


@override_settings(
    RMC_EDGE_SYNC_ENABLED=True,
    RMC_EDGE_OPERATOR_BASE="https://hub.test",
    RMC_SYNC_BUNDLE_SIGNING_KEY="g2-runner-test-key",
)
class RunnerDrainsThePullTests(TestCase):
    """The box must keep pulling until the cloud says it is caught up — but not forever."""

    def setUp(self):
        get_user_model().objects.filter(is_superuser=True).delete()
        get_user_model().objects.create_superuser(
            username="edge-principal-g2-drain", email="g2@example.test", password="x"
        )
        School.objects.update(is_active=False)
        self.school = School.objects.create(
            name="Drain Box", slug="drain-box", subdomain="drain-box", is_active=True
        )
        self.entity = _academic_year_entity()
        self.years = [
            AcademicYear.objects.create(
                school=self.school,
                name=f"Y{i}",
                start_date=dt.date(2020 + i, 9, 1),
                end_date=dt.date(2021 + i, 6, 30),
            )
            for i in range(7)
        ]
        # Future stamps so the wall-clock conflict check applies every row rather than
        # recording seven conflicts against rows this same database already holds.
        self.base = timezone.now().replace(microsecond=0) + dt.timedelta(hours=1)
        self.corpus = [
            {
                "entity_type": self.entity,
                "id": year.pk,
                "client_offline_id": "",
                "changes": {"name": f"Pulled {i}"},
                "updated_at": (self.base + dt.timedelta(seconds=i)).isoformat(),
            }
            for i, year in enumerate(self.years)
        ]

    def _cycle(self, cloud):
        from apps.sync_engine import sync_runner

        with mock.patch(_PULL, side_effect=cloud.pull), mock.patch(
            _POST, return_value=(200, {"ok": True})
        ):
            return sync_runner.run_sync_cycle(self.school, mode="live")

    def test_one_cycle_drains_every_page(self):
        cloud = _PagingCloud(self.school, self.corpus)
        with override_settings(RMC_EDGE_SYNC_PULL_PAGE_ROWS=3):
            result = self._cycle(cloud)

        self.assertTrue(result["ok"], result.get("error"))
        self.assertGreaterEqual(
            len(cloud.calls),
            3,
            "the runner pulled once and stopped: 7 rows at a 3-row page means the box "
            f"is still behind while reporting success (calls={cloud.calls})",
        )
        self.assertEqual(
            result["pulled"],
            7,
            f"rows left on the cloud after a 'successful' cycle: {result}",
        )

    def test_the_box_asks_for_a_page_at_all(self):
        cloud = _PagingCloud(self.school, self.corpus)
        with override_settings(RMC_EDGE_SYNC_PULL_PAGE_ROWS=3):
            self._cycle(cloud)
        self.assertEqual(
            cloud.calls[0]["limit"],
            3,
            "the pull requested no limit, so the cloud builds and buffers the whole "
            "corpus in memory before a byte moves",
        )

    def test_each_page_resumes_from_the_previous_page_high_water(self):
        cloud = _PagingCloud(self.school, self.corpus)
        with override_settings(RMC_EDGE_SYNC_PULL_PAGE_ROWS=3):
            self._cycle(cloud)
        sinces = [c["since"] for c in cloud.calls]
        self.assertIsNone(sinces[0], "the first page of a first sync asks for everything")
        self.assertEqual(
            sinces[1],
            self.base + dt.timedelta(seconds=2),
            f"page 2 did not resume from page 1's high-water: {sinces}",
        )
        self.assertEqual(sinces[2], self.base + dt.timedelta(seconds=5))

    def test_the_cursor_ends_on_the_last_row_actually_applied(self):
        from apps.sync_engine.models import EdgeSyncCursor, get_sync_cursor

        cloud = _PagingCloud(self.school, self.corpus)
        with override_settings(RMC_EDGE_SYNC_PULL_PAGE_ROWS=3):
            self._cycle(cloud)
        self.assertEqual(
            get_sync_cursor(self.school, EdgeSyncCursor.PULL),
            self.base + dt.timedelta(seconds=6),
        )

    def test_a_page_that_fails_leaves_the_cursor_on_the_last_page_that_landed(self):
        """Advance only on success, per page. An interrupted drain must cost the pages
        it did not get, never the ones it did."""
        from apps.sync_engine.models import EdgeSyncCursor, get_sync_cursor

        cloud = _PagingCloud(self.school, self.corpus)
        real_pull = cloud.pull
        state = {"n": 0}

        def _flaky(*args, **kwargs):
            state["n"] += 1
            if state["n"] == 2:
                return 503, b"", None
            return real_pull(*args, **kwargs)

        cloud.pull = _flaky
        with override_settings(RMC_EDGE_SYNC_PULL_PAGE_ROWS=3):
            result = self._cycle(cloud)

        self.assertFalse(result["ok"], "a dropped page must be reported, not swallowed")
        self.assertEqual(
            get_sync_cursor(self.school, EdgeSyncCursor.PULL),
            self.base + dt.timedelta(seconds=2),
            "the cursor did not stop on the last page that verified and applied",
        )
        self.assertEqual(result["pulled"], 3)

    def test_one_cycle_cannot_page_forever(self):
        """A cloud that always says 'more' must not pin the box in one cycle."""
        cloud = _PagingCloud(self.school, self.corpus, always_more=True)
        with override_settings(
            RMC_EDGE_SYNC_PULL_PAGE_ROWS=1, RMC_EDGE_SYNC_MAX_PULL_PAGES_PER_CYCLE=3
        ):
            result = self._cycle(cloud)
        self.assertEqual(len(cloud.calls), 3, f"page ceiling not enforced: {cloud.calls}")
        self.assertTrue(result["ok"], result.get("error"))
        self.assertIn("ceiling", result["message"])
        self.assertTrue(result["pull_more_pending"])

    def test_a_stalled_high_water_stops_the_drain_instead_of_looping(self):
        """The one shape in which a server-side paging bug could cost data rather than
        time: a page whose high-water does not advance makes the next request identical
        to the last."""
        cloud = _PagingCloud(self.school, self.corpus)

        def _stuck(endpoint, token, *, since=None, entities=None, timeout=30.0,
                   collect=None, limit=None, **_kw):
            cloud.calls.append({"since": since, "limit": limit})
            if collect is not None:
                collect["more"] = True
            return (
                200,
                export_delta_bundle(
                    school_id=str(self.school.id), rows=self.corpus[:1], device_id="cloud"
                ),
                self.corpus[0]["updated_at"],
            )

        cloud.pull = _stuck
        with override_settings(
            RMC_EDGE_SYNC_PULL_PAGE_ROWS=1, RMC_EDGE_SYNC_MAX_PULL_PAGES_PER_CYCLE=50
        ):
            result = self._cycle(cloud)
        self.assertLessEqual(len(cloud.calls), 3, f"looped on a stalled cursor: {len(cloud.calls)}")
        self.assertIn("did not advance", result["message"])

    def test_a_cloud_that_predates_paging_is_pulled_exactly_once(self):
        """Compatibility both ways: no ``X-RMC-Sync-More`` means 'that was everything'."""

        calls = []

        def _old_cloud(endpoint, token, *, since=None, entities=None, timeout=30.0,
                       collect=None, limit=None, **_kw):
            calls.append(since)
            return (
                200,
                export_delta_bundle(
                    school_id=str(self.school.id), rows=self.corpus, device_id="cloud"
                ),
                self.corpus[-1]["updated_at"],
            )

        cloud = _PagingCloud(self.school, self.corpus)
        cloud.pull = _old_cloud
        result = self._cycle(cloud)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["pulled"], 7)
        self.assertTrue(result["ok"], result.get("error"))
