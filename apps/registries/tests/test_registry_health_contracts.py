import os
from datetime import datetime, timezone
from pathlib import Path

from django.test import SimpleTestCase

from apps.platform_runtime.administration_catalog import REGISTRIES
from apps.platform_runtime.registry_health import evaluate_registry_health


class RegistryHealthContractsTests(SimpleTestCase):
    def test_administration_registries_have_owner_proof_test(self):
        root = Path(__file__).resolve().parents[3]
        for row in REGISTRIES:
            self.assertTrue(row.get("owner"), msg=row.get("name"))
            self.assertTrue(row.get("proof"), msg=row.get("name"))
            test_path = str(row.get("test") or "").strip()
            self.assertTrue(test_path, msg=row.get("name"))
            full = root / test_path.replace("/", os.sep)
            self.assertTrue(full.is_file(), msg=f"{row.get('name')} -> {test_path}")

    def test_evaluate_registry_health_ok_for_catalog(self):
        now = datetime.now(timezone.utc)
        rows = [
            {
                **dict(entry),
                "generated_at": now,
            }
            for entry in REGISTRIES
        ]
        routes = {str(r.get("route") or "") for r in rows}
        result = evaluate_registry_health(rows, route_inventory=routes)
        self.assertTrue(result["ok"], msg=result["rows"])
