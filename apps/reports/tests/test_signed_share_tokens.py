from django.test import SimpleTestCase

from apps.reports.services import build_share_token, parse_share_token


class ReportShareSignedTokenTests(SimpleTestCase):
    def test_tampered_report_share_token_is_rejected(self):
        token = build_share_token("term", student_id=1, academic_year_id=2, term_id=3)
        tampered = token.replace("term:1:2:3", "term:999:2:3", 1)

        self.assertIsNone(parse_share_token(tampered))

    def test_unsigned_report_share_payload_is_rejected(self):
        self.assertIsNone(parse_share_token("term:1:2:3:not-a-valid-signature"))
