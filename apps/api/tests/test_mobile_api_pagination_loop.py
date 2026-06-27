"""No-DB pagination contract tests for apps/api/mobile_api.py list endpoints.

Audit #20 (api-pagination-contracts). Companion to
``test_entity_api_pagination_loop.py``; same rationale (the global
``CursorPagination(ordering="-created")`` default 500s on models without a
``created`` field). These run without a database.

Extra contract pinned here: ``PushNotificationViewSet.get_queryset`` must
NOT return a sliced queryset. CursorPagination calls ``.filter()`` on the
queryset, and Django raises ``Cannot filter a query once a slice has been
taken``; the old ``[:50]`` slice would therefore 500 once pagination was
active. The 50-item window is now expressed via the pagination class's
``page_size`` instead.
"""

from __future__ import annotations

import inspect

from django.test import SimpleTestCase
from rest_framework.pagination import CursorPagination
from rest_framework.test import APIRequestFactory

from apps.api import mobile_api


# (ViewSet class, expected pagination class, model, expected ordering)
PAGINATED_LIST_VIEWSETS = [
    (
        mobile_api.MobileDeviceViewSet,
        mobile_api.MobileDeviceCursorPagination,
        mobile_api.MobileDevice,
        "-last_active",
    ),
    (
        mobile_api.PushNotificationViewSet,
        mobile_api.PushNotificationCursorPagination,
        mobile_api.PushNotification,
        "-created_at",
    ),
    (
        mobile_api.OfflineSyncViewSet,
        mobile_api.OfflineSyncCursorPagination,
        mobile_api.OfflineSyncQueue,
        "-created_at",
    ),
]


def _field_resolves(model, ordering: str) -> bool:
    name = ordering.lstrip("-")
    if name == "pk":
        return True
    try:
        model._meta.get_field(name)
        return True
    except Exception:  # FieldDoesNotExist
        return False


class MobileListPaginationContractTests(SimpleTestCase):
    def test_every_list_viewset_declares_explicit_pagination(self):
        for view_cls, pagination_cls, _model, _ordering in PAGINATED_LIST_VIEWSETS:
            with self.subTest(view=view_cls.__name__):
                self.assertIs(view_cls.pagination_class, pagination_cls)
                self.assertTrue(issubclass(pagination_cls, CursorPagination))

    def test_pagination_ordering_resolves_to_real_field(self):
        for view_cls, pagination_cls, model, ordering in PAGINATED_LIST_VIEWSETS:
            with self.subTest(view=view_cls.__name__):
                self.assertEqual(pagination_cls.ordering, ordering)
                self.assertTrue(
                    _field_resolves(model, ordering),
                    f"{pagination_cls.__name__}.ordering={ordering!r} "
                    f"does not resolve on {model.__name__}",
                )

    def test_mobile_device_global_default_would_500(self):
        """MobileDevice has no 'created' field -> the global default is invalid."""
        self.assertFalse(_field_resolves(mobile_api.MobileDevice, "-created"))

    def test_client_page_size_is_capped(self):
        for _view_cls, pagination_cls, _model, _ordering in PAGINATED_LIST_VIEWSETS:
            with self.subTest(pagination=pagination_cls.__name__):
                self.assertEqual(pagination_cls.page_size_query_param, "page_size")
                self.assertIsNotNone(pagination_cls.max_page_size)
                self.assertGreater(pagination_cls.max_page_size, 0)

    def test_push_notification_page_size_preserves_50_window(self):
        """The historical 'most recent 50' window is now the default page_size."""
        self.assertEqual(mobile_api.PushNotificationCursorPagination.page_size, 50)

    def test_push_notification_queryset_is_not_sliced(self):
        """A sliced queryset can't be filtered by CursorPagination -> would 500.

        We can't execute the ORM here (no DB), but we can assert the source
        no longer applies a ``[:N]`` slice in get_queryset, which is the
        defect that pagination would have triggered.
        """
        source = inspect.getsource(mobile_api.PushNotificationViewSet.get_queryset)
        self.assertNotIn("[:50]", source)
        self.assertNotIn("][:", source)

    def test_get_ordering_returns_configured_field(self):
        factory = APIRequestFactory()
        for _view_cls, pagination_cls, _model, ordering in PAGINATED_LIST_VIEWSETS:
            with self.subTest(pagination=pagination_cls.__name__):
                paginator = pagination_cls()
                request = factory.get("/api/mobile/list/")
                result = paginator.get_ordering(request, None, None)
                self.assertEqual(tuple(result), (ordering,))

    def test_envelope_shape_is_cursor_paginated(self):
        factory = APIRequestFactory()
        paginator = mobile_api.OfflineSyncCursorPagination()
        paginator.request = factory.get("/api/mobile/list/")
        paginator.page = [1, 2, 3]
        paginator.has_next = False
        paginator.has_previous = False
        payload = paginator.get_paginated_response([1, 2, 3]).data
        self.assertEqual(set(payload.keys()), {"next", "previous", "results"})
        self.assertEqual(payload["results"], [1, 2, 3])
