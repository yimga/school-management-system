"""The default paginator must order by a column the model actually has.

Found from a live self-hosted box, in the gunicorn log::

    GET /api/attendance/ HTTP/1.1" 500
    django.core.exceptions.FieldError: Cannot resolve keyword 'created' into
    field. Choices are: classroom, ..., created_at, date, id, remarks, ...

``REST_FRAMEWORK["DEFAULT_PAGINATION_CLASS"]`` was DRF's raw ``CursorPagination``,
whose ``ordering`` default is ``"-created"``. One of this project's 794 models has
a ``created`` field; the convention is ``created_at`` (570 models). So every list
endpoint falling back to the default was an unconditional 500.

The defect had been found twice before and fixed only where it was noticed —
``apps/api/entity_api.py`` and ``apps/api/mobile_api.py`` each grew a local
paginator, and each carries a comment describing this exact failure. The cause,
the DEFAULT, was left in place. These tests pin the cause, not the symptom.
"""

from django.apps import apps as dj_apps
from django.test import SimpleTestCase
from rest_framework.pagination import CursorPagination
from rest_framework.settings import api_settings

from apps.api.pagination import FALLBACK_ORDERING, RMCCursorPagination, resolve_ordering


def _field_names(model):
    return {f.name for f in model._meta.get_fields()} | {"pk"}


class DefaultPaginatorIsWiredTests(SimpleTestCase):
    def test_project_default_is_the_resolving_paginator(self):
        self.assertIs(api_settings.DEFAULT_PAGINATION_CLASS, RMCCursorPagination)

    def test_it_is_still_cursor_pagination(self):
        # The opaque-cursor property is the reason this project chose cursor
        # pagination; the fix must not quietly downgrade to page numbers.
        self.assertTrue(issubclass(RMCCursorPagination, CursorPagination))

    def test_page_size_is_client_settable_but_bounded(self):
        self.assertEqual(RMCCursorPagination.page_size_query_param, "page_size")
        self.assertGreater(RMCCursorPagination.max_page_size, 0)


class OrderingResolutionTests(SimpleTestCase):
    def test_the_field_that_broke_production_now_resolves(self):
        attendance = dj_apps.get_model("academics", "Attendance")
        self.assertNotIn("created", _field_names(attendance))
        self.assertEqual(resolve_ordering(attendance, "-created"), ("-created_at",))

    def test_a_valid_declared_ordering_is_left_alone(self):
        # entity_api's paginators declare "-updated_at"; resolution must not
        # override a deliberate choice that already works.
        attendance = dj_apps.get_model("academics", "Attendance")
        self.assertEqual(resolve_ordering(attendance, "-updated_at"), ("-updated_at",))

    def test_related_traversal_is_judged_on_its_first_segment(self):
        attendance = dj_apps.get_model("academics", "Attendance")
        self.assertEqual(
            resolve_ordering(attendance, "-student__id"), ("-student__id",)
        )

    def test_tuple_orderings_are_preserved_when_every_term_resolves(self):
        attendance = dj_apps.get_model("academics", "Attendance")
        self.assertEqual(
            resolve_ordering(attendance, ("-created_at", "-pk")),
            ("-created_at", "-pk"),
        )

    def test_a_tuple_with_one_bad_term_falls_back_rather_than_half_applying(self):
        attendance = dj_apps.get_model("academics", "Attendance")
        self.assertEqual(
            resolve_ordering(attendance, ("-created_at", "-nonexistent")),
            ("-created_at",),
        )

    def test_pk_is_the_last_resort_and_always_available(self):
        # 218 models have no created_at/created/timestamp at all. A cursor needs
        # a non-null unique column; pk is the only universal one.
        self.assertEqual(FALLBACK_ORDERING[-1], "-pk")

    def test_an_unknown_model_declaration_is_trusted_rather_than_guessed(self):
        # No model to check against (e.g. a queryset-less view): do not silently
        # reorder someone's data on a guess.
        self.assertEqual(resolve_ordering(None, "-whatever"), ("-whatever",))


class EveryModelResolvesTests(SimpleTestCase):
    """The seal: no registered model may produce an unresolvable ordering."""

    def test_no_model_resolves_to_a_column_it_does_not_have(self):
        offenders = []
        for model in dj_apps.get_models():
            resolved = resolve_ordering(model, RMCCursorPagination.ordering)
            names = _field_names(model)
            for term in resolved:
                if term.lstrip("-").split("__", 1)[0] not in names:
                    offenders.append((model._meta.label, resolved))
        self.assertEqual(offenders, [], msg=f"{len(offenders)} model(s) unresolvable")

    def test_the_raw_drf_default_would_still_break_almost_everything(self):
        # Documents WHY the default had to change: if someone reverts
        # DEFAULT_PAGINATION_CLASS to rest_framework's CursorPagination, this is
        # the blast radius they are re-arming.
        self.assertEqual(CursorPagination.ordering, "-created")
        have_created = [
            m for m in dj_apps.get_models() if "created" in _field_names(m)
        ]
        total = len(dj_apps.get_models())
        self.assertLess(
            len(have_created),
            total * 0.05,
            msg="'-created' is not this project's convention; do not restore it",
        )


class ExistingLocalPaginatorsStayValidTests(SimpleTestCase):
    """The two modules that hand-rolled a fix must keep working unchanged."""

    def test_entity_and_mobile_paginators_declare_resolvable_orderings(self):
        from apps.api import entity_api, mobile_api

        pairs = [
            (entity_api.StudentProfileCursorPagination, ("people", "StudentProfile")),
            (entity_api.TeacherProfileCursorPagination, ("people", "TeacherProfile")),
            (entity_api.ClassroomCursorPagination, ("academics", "Classroom")),
            (mobile_api.MobileDeviceCursorPagination, None),
            (mobile_api.PushNotificationCursorPagination, None),
            (mobile_api.OfflineSyncCursorPagination, None),
        ]
        for paginator, label in pairs:
            with self.subTest(paginator=paginator.__name__):
                self.assertIsNotNone(
                    getattr(paginator, "ordering", None),
                    msg="must declare an explicit ordering",
                )
                if label is None:
                    continue
                model = dj_apps.get_model(*label)
                self.assertEqual(
                    resolve_ordering(model, paginator.ordering),
                    (paginator.ordering,),
                    msg=f"{paginator.__name__} ordering does not resolve on {model}",
                )
