"""Edge sync backlog — the runner could never drain a box that was far behind.

Three defects in ``sync_runner.run_sync_cycle``, all provable by running it:

1. **The push deadlock.** The runner built ONE bundle with ``since=None`` — every row
   the school has — and POSTed it whole. ``SyncBundleUploadView`` caps a bundle at
   ``RMC_SYNC_BUNDLE_MAX_ROWS`` (default 500) and rejects an oversized one with
   ``400 bundle_too_large``, applying NOTHING. So the more changes a box had to send,
   the more certain the push was to fail — and it failed IDENTICALLY every cycle,
   forever. A box that had never synced could essentially never start.

2. **No cursor.** ``since=None`` in both directions and the ``X-RMC-Sync-High-Water``
   response header (which the download endpoint already stamps, and which
   ``pull_bundle`` already returns) was discarded into ``_high_water``. Every 180s
   auto-sync tick therefore re-scanned and re-shipped the ENTIRE corpus. The
   ``edge_scheduler`` docstring claimed "the underlying cycle is cursor-based"; that
   was true of the ``post_edge_outbox``/``pull_edge_inbox`` COMMANDS (which keep file
   cursors) and false of the runner the button and the scheduler actually call.

3. **Paging must not split an insert's dependency group.** ``apply_edge_inserts``
   remaps a new-references-new FK using an IN-BUNDLE ``(entity_type, local_pk) ->
   operator_pk`` map, and DROPS the FK when the referent "isn't in the bundle". So
   naively chunking rows would silently unlink offline-created children from their
   parents. Updates are keyed by pk and are order-independent, so they page freely;
   inserts must stay whole.

These tests fail before the fix: 1 and 2 by asserting the observable outcome of a
cycle, 3 by asserting inserts are never split across pages.
"""
from __future__ import annotations

import datetime as dt
from unittest import mock

from django.test import TestCase, override_settings
from django.utils import timezone

from django.contrib.auth import get_user_model

from apps.academics.models import AcademicYear
from apps.schools.models import School

_POST = "apps.sync_engine.edge_outbox.post_bundle"
_PULL = "apps.sync_engine.edge_outbox.pull_bundle"


class _Receiver:
    """Stands in for ``SyncBundleUploadView``, enforcing its REAL contract.

    Mirrors the two behaviours that matter: the row cap with a whole-bundle
    ``400 bundle_too_large`` rejection, and a 200 that reports what it applied. Every
    page it accepts is recorded so a test can assert how the runner chunked the work.
    """

    def __init__(self, max_rows):
        self.max_rows = max_rows
        self.pages: list[list[dict]] = []
        self.rejected: list[int] = []

    def post_bundle(self, endpoint, token, data, *, timeout=30.0):
        from apps.sync_engine.delta_bundle import iter_bundle_lines

        rows = [r for r in iter_bundle_lines(data) if "entity_type" in r]
        if len(rows) > self.max_rows:
            self.rejected.append(len(rows))
            return 400, {"ok": False, "errors": ["bundle_too_large"], "max_rows": self.max_rows}
        self.pages.append(rows)
        return 200, {"ok": True, "received": len(rows), "applied": len(rows), "conflicts": 0}

    @property
    def accepted_row_count(self):
        return sum(len(p) for p in self.pages)


def _empty_pull_for(school):
    """A reachable cloud with nothing to send down (isolates the push direction).

    The bundle must be signed for THIS school — ``verify_and_parse_bundle`` enforces the
    school binding, so a stub bound to anything else reads as ``school_mismatch``.

    ``**_kw`` is load-bearing, not laziness. ``pull_bundle`` gains ADDITIVE keyword
    arguments over time (``collect=`` for the directive, ``parity=`` for the G8 digest),
    and each one is optional at the real call site. A stub that pins the signature turns
    every such addition into a suite-wide failure that looks like a product regression:
    the TypeError is swallowed by ``run_sync_cycle``'s never-raise wrapper and surfaces
    as ``pull failed: ... unexpected keyword argument``, i.e. an assertion about cursors
    failing for reasons that have nothing to do with cursors. Accept and ignore.
    """

    def _pull(endpoint, token, *, since=None, entities=None, timeout=30.0, collect=None, **_kw):
        from apps.sync_engine.delta_bundle import export_delta_bundle

        return 200, export_delta_bundle(
            school_id=str(school.id), rows=[], device_id="cloud"
        ), None

    return _pull


@override_settings(RMC_EDGE_SYNC_ENABLED=True, RMC_EDGE_OPERATOR_BASE="https://hub.test")
class PushBacklogPagingTests(TestCase):
    """Defect 1: a backlog bigger than the receiver's cap must still drain."""

    def setUp(self):
        # apply_pulled_bundle needs a local principal; without one the pull leg
        # reports "no local principal to apply as" and the whole cycle reads not-ok.
        get_user_model().objects.filter(is_superuser=True).delete()
        get_user_model().objects.create_superuser(
            username=f"edge-principal-{self.__class__.__name__.lower()}",
            email="edge@example.test",
            password="x",
        )
        School.objects.update(is_active=False)
        self.school = School.objects.create(
            name="Backlog Box", slug="backlog-box", subdomain="backlog-box", is_active=True
        )
        # 7 changed rows against a cap of 3 -> the old runner posts one 7-row bundle.
        for i in range(7):
            AcademicYear.objects.create(
                school=self.school,
                name=f"Year {i}",
                start_date=dt.date(2020 + i, 9, 1),
                end_date=dt.date(2021 + i, 6, 30),
            )

    def _run(self, cap=3):
        from apps.sync_engine import sync_runner

        receiver = _Receiver(max_rows=cap)
        with override_settings(RMC_SYNC_BUNDLE_MAX_ROWS=cap), mock.patch(
            _POST, side_effect=receiver.post_bundle
        ), mock.patch(_PULL, side_effect=_empty_pull_for(self.school)):
            result = sync_runner.run_sync_cycle(self.school, mode="live")
        return result, receiver

    def test_backlog_larger_than_the_cap_is_pushed_in_pages_not_rejected(self):
        result, receiver = self._run(cap=3)
        self.assertEqual(
            receiver.rejected,
            [],
            "the runner sent an oversized bundle the receiver had to reject whole — "
            "this is the deadlock: a bigger backlog is MORE certain to fail",
        )
        self.assertTrue(result["ok"], result.get("error"))
        self.assertGreaterEqual(len(receiver.pages), 3, "7 rows at cap 3 needs >= 3 pages")
        self.assertEqual(receiver.accepted_row_count, 7)

    def test_no_page_ever_exceeds_the_receiver_cap(self):
        _result, receiver = self._run(cap=3)
        oversized = [len(p) for p in receiver.pages if len(p) > 3]
        self.assertEqual(oversized, [], f"pages over cap: {oversized}")

    def test_every_row_is_pushed_exactly_once(self):
        _result, receiver = self._run(cap=3)
        keys = [(r["entity_type"], r["id"]) for p in receiver.pages for r in p]
        self.assertEqual(len(keys), len(set(keys)), "a row was sent on more than one page")


@override_settings(RMC_EDGE_SYNC_ENABLED=True, RMC_EDGE_OPERATOR_BASE="https://hub.test")
class PushCursorTests(TestCase):
    """Defect 2 (push half): a drained backlog must not be re-sent every cycle."""

    def setUp(self):
        # apply_pulled_bundle needs a local principal; without one the pull leg
        # reports "no local principal to apply as" and the whole cycle reads not-ok.
        get_user_model().objects.filter(is_superuser=True).delete()
        get_user_model().objects.create_superuser(
            username=f"edge-principal-{self.__class__.__name__.lower()}",
            email="edge@example.test",
            password="x",
        )
        School.objects.update(is_active=False)
        self.school = School.objects.create(
            name="Cursor Box", slug="cursor-box", subdomain="cursor-box", is_active=True
        )
        for i in range(4):
            AcademicYear.objects.create(
                school=self.school,
                name=f"Y{i}",
                start_date=dt.date(2020 + i, 9, 1),
                end_date=dt.date(2021 + i, 6, 30),
            )

    def _cycle(self, cap=100):
        from apps.sync_engine import sync_runner

        receiver = _Receiver(max_rows=cap)
        with override_settings(RMC_SYNC_BUNDLE_MAX_ROWS=cap), mock.patch(
            _POST, side_effect=receiver.post_bundle
        ), mock.patch(_PULL, side_effect=_empty_pull_for(self.school)):
            result = sync_runner.run_sync_cycle(self.school, mode="live")
        return result, receiver

    def test_second_cycle_with_no_local_change_pushes_nothing(self):
        first, r1 = self._cycle()
        self.assertTrue(first["ok"], first.get("error"))
        self.assertEqual(r1.accepted_row_count, 4)

        second, r2 = self._cycle()
        self.assertTrue(second["ok"], second.get("error"))
        self.assertEqual(
            r2.accepted_row_count,
            0,
            "the push cursor did not advance — every cycle re-ships the whole corpus",
        )

    def test_a_later_local_edit_still_ships_after_the_cursor_advanced(self):
        self._cycle()
        year = AcademicYear.objects.filter(school=self.school).first()
        year.name = "Renamed after sync"
        year.save(update_fields=["name", "updated_at"])

        third, r3 = self._cycle()
        self.assertTrue(third["ok"], third.get("error"))
        self.assertEqual(
            r3.accepted_row_count, 1, "a genuine post-cursor edit must still be pushed"
        )

    def test_a_failed_push_does_not_advance_the_cursor(self):
        """Durability: a rejected page must be retried, never silently skipped."""
        from apps.sync_engine import sync_runner

        def _reject(endpoint, token, data, *, timeout=30.0):
            return 503, {"ok": False}

        with mock.patch(_POST, side_effect=_reject), mock.patch(_PULL, side_effect=_empty_pull_for(self.school)):
            failed = sync_runner.run_sync_cycle(self.school, mode="live")
        self.assertFalse(failed["ok"])

        _retry, receiver = self._cycle()
        self.assertEqual(
            receiver.accepted_row_count, 4, "rows lost after a failed push — cursor advanced anyway"
        )


@override_settings(RMC_EDGE_SYNC_ENABLED=True, RMC_EDGE_OPERATOR_BASE="https://hub.test")
class PullCursorTests(TestCase):
    """Defect 2 (pull half): the high-water header the cloud already sends must be used."""

    def setUp(self):
        # apply_pulled_bundle needs a local principal; without one the pull leg
        # reports "no local principal to apply as" and the whole cycle reads not-ok.
        get_user_model().objects.filter(is_superuser=True).delete()
        get_user_model().objects.create_superuser(
            username=f"edge-principal-{self.__class__.__name__.lower()}",
            email="edge@example.test",
            password="x",
        )
        School.objects.update(is_active=False)
        self.school = School.objects.create(
            name="Pull Box", slug="pull-box", subdomain="pull-box", is_active=True
        )

    def test_pull_sends_no_since_on_the_very_first_cycle(self):
        from apps.sync_engine import sync_runner

        seen = {}

        def _pull(endpoint, token, *, since=None, entities=None, timeout=30.0, collect=None, **_kw):
            seen["since"] = since
            return _empty_pull_for(self.school)(endpoint, token, since=since, entities=entities)

        with mock.patch(_PULL, side_effect=_pull), mock.patch(
            _POST, return_value=(200, {"ok": True})
        ):
            sync_runner.run_sync_cycle(self.school, mode="live")
        self.assertIsNone(seen["since"], "first cycle must ask for everything")

    def test_pull_cursor_advances_from_the_high_water_header(self):
        from apps.sync_engine import sync_runner

        stamp = timezone.now().replace(microsecond=0)
        calls = []

        def _pull(endpoint, token, *, since=None, entities=None, timeout=30.0, collect=None, **_kw):
            from apps.sync_engine.delta_bundle import export_delta_bundle

            calls.append(since)
            return (
                200,
                export_delta_bundle(school_id=str(self.school.id), rows=[], device_id="cloud"),
                stamp.isoformat(),
            )

        with mock.patch(_PULL, side_effect=_pull), mock.patch(
            _POST, return_value=(200, {"ok": True})
        ):
            sync_runner.run_sync_cycle(self.school, mode="live")
            sync_runner.run_sync_cycle(self.school, mode="live")

        self.assertEqual(len(calls), 2)
        self.assertIsNone(calls[0])
        self.assertIsNotNone(
            calls[1],
            "the high-water header was discarded — every cycle re-downloads the whole corpus",
        )

    def test_a_failed_pull_does_not_advance_the_pull_cursor(self):
        from apps.sync_engine import sync_runner

        calls = []

        def _pull(endpoint, token, *, since=None, entities=None, timeout=30.0, collect=None, **_kw):
            calls.append(since)
            return 503, b"", timezone.now().isoformat()

        with mock.patch(_PULL, side_effect=_pull), mock.patch(
            _POST, return_value=(200, {"ok": True})
        ):
            sync_runner.run_sync_cycle(self.school, mode="live")
            sync_runner.run_sync_cycle(self.school, mode="live")
        self.assertEqual(calls, [None, None], "cursor advanced on a REJECTED pull")


@override_settings(RMC_EDGE_SYNC_ENABLED=True, RMC_EDGE_OPERATOR_BASE="https://hub.test")
class InsertsAreNeverSplitTests(TestCase):
    """Defect 3: ``apply_edge_inserts`` drops an FK whose referent is not in the bundle.

    So offline-CREATED rows (the ones carrying ``client_offline_id``) must travel in one
    bundle even when the update backlog around them is paged. Splitting them would
    silently unlink a child from the parent it was created with.
    """

    def setUp(self):
        # apply_pulled_bundle needs a local principal; without one the pull leg
        # reports "no local principal to apply as" and the whole cycle reads not-ok.
        get_user_model().objects.filter(is_superuser=True).delete()
        get_user_model().objects.create_superuser(
            username=f"edge-principal-{self.__class__.__name__.lower()}",
            email="edge@example.test",
            password="x",
        )
        School.objects.update(is_active=False)
        self.school = School.objects.create(
            name="Insert Box", slug="insert-box", subdomain="insert-box", is_active=True
        )
        # 5 offline-created rows (client_offline_id set) + 5 plain updates, cap 3.
        for i in range(5):
            AcademicYear.objects.create(
                school=self.school,
                name=f"Offline {i}",
                start_date=dt.date(2000 + i, 9, 1),
                end_date=dt.date(2001 + i, 6, 30),
                client_offline_id=f"offline-year-{i}",
            )
        for i in range(5):
            AcademicYear.objects.create(
                school=self.school,
                name=f"Cloned {i}",
                start_date=dt.date(2010 + i, 9, 1),
                end_date=dt.date(2011 + i, 6, 30),
            )

    def _cycle(self, cap):
        from apps.sync_engine import sync_runner

        receiver = _Receiver(max_rows=cap)
        with override_settings(RMC_SYNC_BUNDLE_MAX_ROWS=cap), mock.patch(
            _POST, side_effect=receiver.post_bundle
        ), mock.patch(_PULL, side_effect=_empty_pull_for(self.school)):
            result = sync_runner.run_sync_cycle(self.school, mode="live")
        return result, receiver

    def _insert_pages(self, receiver):
        return [
            page
            for page in receiver.pages
            if any((r.get("client_offline_id") or "").strip() for r in page)
        ]

    def test_offline_created_rows_stay_whole_when_they_fit_the_cap(self):
        """The case that must never regress: 5 inserts, cap 5 — one intact bundle."""
        result, receiver = self._cycle(cap=5)
        self.assertTrue(result["ok"], result.get("error"))
        insert_pages = self._insert_pages(receiver)
        self.assertEqual(
            len(insert_pages),
            1,
            "offline-created rows were split even though they fit — apply_edge_inserts "
            "would drop their new-references-new FKs",
        )
        self.assertTrue(
            all((r.get("client_offline_id") or "").strip() for r in insert_pages[0]),
            "the insert page must carry ONLY inserts so its dependency map is complete",
        )
        self.assertEqual(len(insert_pages[0]), 5)

    def test_inserts_are_pushed_before_any_update_page(self):
        """Ordering is what makes an update page's high-water a safe cursor: once it
        advances, every older row — insert included — is already on the wire."""
        _result, receiver = self._cycle(cap=5)
        first_update_page = next(
            i
            for i, page in enumerate(receiver.pages)
            if not any((r.get("client_offline_id") or "").strip() for r in page)
        )
        last_insert_page = max(
            i
            for i, page in enumerate(receiver.pages)
            if any((r.get("client_offline_id") or "").strip() for r in page)
        )
        self.assertLess(last_insert_page, first_update_page)

    def test_an_unavoidable_insert_split_is_reported_never_silent(self):
        """When inserts genuinely exceed the cap they MUST still be sent — refusing to
        page would restore the deadlock — but the dropped-link risk has to be visible."""
        result, receiver = self._cycle(cap=3)
        self.assertTrue(result["ok"], result.get("error"))
        self.assertGreater(len(self._insert_pages(receiver)), 1, "cap 3 must split 5 inserts")
        self.assertIn("WARNING", result["message"])
        self.assertIn("offline-created", result["message"])

    def test_all_rows_still_arrive_when_inserts_and_updates_are_separated(self):
        result, receiver = self._cycle(cap=3)
        self.assertTrue(result["ok"], result.get("error"))
        self.assertEqual(receiver.accepted_row_count, 10)
