from unittest.mock import patch

from django.test import SimpleTestCase

from apps.api.ministry_connectors import (
    ministry_runtime_status,
    submit_cartescolaire,
    submit_dgi,
)


class MinistryConnectorTests(SimpleTestCase):
    @patch.dict("os.environ", {}, clear=True)
    def test_runtime_defaults_to_mock_mode(self):
        status = ministry_runtime_status()
        self.assertEqual(status["mode"], "mock")
        self.assertTrue(status["cartescolaire"]["ready"])
        self.assertTrue(status["dgi"]["ready"])

    @patch.dict("os.environ", {"MINISTRY_CONNECTOR_MODE": "live"}, clear=True)
    def test_live_mode_reports_missing_credentials(self):
        status = ministry_runtime_status()
        self.assertEqual(status["mode"], "live")
        self.assertFalse(status["cartescolaire"]["ready"])
        self.assertFalse(status["dgi"]["ready"])

    @patch.dict("os.environ", {"MINISTRY_CONNECTOR_MODE": "mock"}, clear=True)
    def test_submit_returns_dry_run_in_mock_mode(self):
        cart = submit_cartescolaire({"records": []})
        dgi = submit_dgi({"entries": []})
        self.assertEqual(cart["mode"], "mock")
        self.assertFalse(cart["attempted"])
        self.assertEqual(dgi["mode"], "mock")
        self.assertFalse(dgi["attempted"])
