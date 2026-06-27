"""No-DB pagination contract tests for apps/api/entity_api.py list endpoints.

Audit #20 (api-pagination-contracts). These lock the response-envelope
and pagination configuration of the Entity ViewSets WITHOUT touching the
database, so they run under plain pytest here.

Why these matter
----------------
``config.settings`` sets the project-wide default::

    REST_FRAMEWORK["DEFAULT_PAGINATION_CLASS"] =
        "rest_framework.pagination.CursorPagination"

``CursorPagination`` orders by ``"-created"`` by default and does **not**
fall back to a model's ``Meta.ordering``. Several Entity models have no
``created`` field, so any ViewSet that relied on the global default would
raise ``FieldError`` (HTTP 500) the moment its ``list`` endpoint is hit.

These tests assert that every list ViewSet:

* declares an explicit ``pagination_class`` (no unbounded / mis-ordered
  lists), and
* the pagination ``ordering`` resolves to a real model field (or ``pk``),
  which is exactly what prevents the ``-created`` FieldError 500.

They also pin the cursor-pagination envelope shape (``next`` / ``previous``
/ ``results``) via ``APIRequestFactory`` + a stubbed paginator, so a future
regression that drops pagination or swaps the envelope is caught.
"""

from __future__ import annotations

from django.test import SimpleTestCase
from rest_framework.pagination import CursorPagination
from rest_framework.test import APIRequestFactory

from apps.api import entity_api
from apps.academics.models import Classroom
from apps.people.models import StudentGuardian, StudentProfile, TeacherProfile


# (ViewSet class, expected pagination class, model, expected ordering)
PAGINATED_LIST_VIEWSETS = [
    (
        entity_api.StudentProfileViewSet,
        entity_api.StudentProfileCursorPagination,
        StudentProfile,
        "-updated_at",
    ),
    (
        entity_api.TeacherProfileViewSet,
        entity_api.TeacherProfileCursorPagination,
        TeacherProfile,
        "-updated_at",
    ),
    (
        entity_api.StudentGuardianViewSet,
        entity_api.StudentGuardianCursorPagination,
        StudentGuardian,
        "-pk",
    ),
    (
        entity_api.ClassroomViewSet,
        entity_api.ClassroomCursorPagination,
        Classroom,
        "-pk",
    ),
]


def _field_resolves(model, ordering: str) -> bool:
    """True if ``ordering`` (a possibly ``-`` prefixed lookup) is a real field."""
    name = ordering.lstrip("-")
    if name == "pk":
        return True
    try:
        model._meta.get_field(name)
        return True
    except Exception:  # FieldDoesNotExist
        return False


class EntityListPaginationContractTests(SimpleTestCase):
    def test_every_list_viewset_declares_explicit_pagination(self):
        """No Entity list endpoint may rely on the (FieldError-prone) global default."""
        for view_cls, pagination_cls, _model, _ordering in PAGINATED_LIST_VIEWSETS:
            with self.subTest(view=view_cls.__name__):
                self.assertIs(
                    view_cls.pagination_class,
                    pagination_cls,
                    f"{view_cls.__name__} must pin {pagination_cls.__name__}",
                )
                self.assertTrue(issubclass(pagination_cls, CursorPagination))

    def test_pagination_ordering_resolves_to_real_field(self):
        """The ordering must be a real field — this is what prevents the -created 500."""
        for view_cls, pagination_cls, model, ordering in PAGINATED_LIST_VIEWSETS:
            with self.subTest(view=view_cls.__name__):
                self.assertEqual(pagination_cls.ordering, ordering)
                self.assertTrue(
                    _field_resolves(model, ordering),
                    f"{pagination_cls.__name__}.ordering={ordering!r} "
                    f"does not resolve on {model.__name__}",
                )

    def test_global_default_ordering_would_500_on_these_models(self):
        """Regression guard: prove the bug we fixed (global '-created' is invalid).

        If a model ever grows a real ``created`` field this assertion can be
        relaxed, but until then it documents WHY each view needs its own
        pagination class.
        """
        for model in (TeacherProfile, StudentGuardian, Classroom):
            with self.subTest(model=model.__name__):
                self.assertFalse(
                    _field_resolves(model, "-created"),
                    f"{model.__name__} unexpectedly has a 'created' field; "
                    "update this guard if so",
                )

    def test_client_page_size_is_capped(self):
        """Client-controlled page_size must exist but be bounded (no unbounded pulls)."""
        for _view_cls, pagination_cls, _model, _ordering in PAGINATED_LIST_VIEWSETS:
            with self.subTest(pagination=pagination_cls.__name__):
                self.assertEqual(pagination_cls.page_size_query_param, "page_size")
                self.assertIsNotNone(pagination_cls.max_page_size)
                self.assertGreater(pagination_cls.max_page_size, 0)

    def test_get_ordering_returns_configured_field(self):
        """paginator.get_ordering() (no DB) returns the configured ordering tuple."""
        factory = APIRequestFactory()
        for _view_cls, pagination_cls, _model, ordering in PAGINATED_LIST_VIEWSETS:
            with self.subTest(pagination=pagination_cls.__name__):
                paginator = pagination_cls()
                request = factory.get("/api/list/")
                # queryset=None / view=None is fine: get_ordering only reads
                # self.ordering + view.filter_backends (absent here).
                result = paginator.get_ordering(request, None, None)
                self.assertEqual(tuple(result), (ordering,))

    def test_envelope_shape_is_cursor_paginated(self):
        """get_paginated_response wraps results in the cursor envelope (no DB)."""
        factory = APIRequestFactory()
        paginator = entity_api.StudentProfileCursorPagination()
        # Simulate the post-paginate_queryset state without a DB hit.
        paginator.request = factory.get("/api/list/")
        paginator.page = ["a", "b"]
        paginator.has_next = False
        paginator.has_previous = False
        payload = paginator.get_paginated_response(["a", "b"]).data
        self.assertEqual(set(payload.keys()), {"next", "previous", "results"})
        self.assertEqual(payload["results"], ["a", "b"])
        self.assertIsNone(payload["next"])
        self.assertIsNone(payload["previous"])
