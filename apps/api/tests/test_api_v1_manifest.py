from django.test import TestCase


class ApiV1ManifestTests(TestCase):
    def test_manifest_json(self):
        r = self.client.get("/api/v1/manifest.json")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data.get("version"), "1.0")
        self.assertIn("oneroster_v1p1", data.get("endpoints", {}))
        self.assertIn("developer_public_api_doc", data.get("endpoints", {}))
        self.assertIn(
            "/developers/api-docs/", data["endpoints"]["developer_public_api_doc"]
        )
        self.assertIn("lti", data)
