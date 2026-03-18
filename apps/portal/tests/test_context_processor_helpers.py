from unittest.mock import patch

from django.db import DatabaseError
from django.test import RequestFactory, SimpleTestCase

from apps.portal.context_processors import _reset_db_state


class PortalContextProcessorHelperTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_reset_db_state_swallows_database_errors(self):
        with patch("apps.portal.context_processors.connection.in_atomic_block", False):
            with patch(
                "apps.portal.context_processors.connection.rollback",
                side_effect=DatabaseError,
            ):
                _reset_db_state()
