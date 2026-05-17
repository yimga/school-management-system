#!/usr/bin/env python3
"""Multi-tenant Phase-1 scaffold gate (batch 1267): TenantOwnedModel + Entitlement exist."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED = (
    "apps/schools/tenant_models.py",
    "apps/schools/tests/test_tenant_owned_model_contract.py",
    "apps/billing/models.py",
)


def main() -> int:
    missing = [rel for rel in REQUIRED if not (ROOT / rel).is_file()]
    tenant_models = (ROOT / "apps" / "schools" / "tenant_models.py").read_text(encoding="utf-8")
    if "class TenantOwnedModel" not in tenant_models:
        missing.append("TenantOwnedModel class in tenant_models.py")
    billing = (ROOT / "apps" / "billing" / "models.py").read_text(encoding="utf-8")
    if "class Entitlement" not in billing:
        missing.append("Entitlement model in billing/models.py")
    if missing:
        for m in missing:
            print(f"verify_tenant_owned_model_adoption_scaffold: {m}", file=sys.stderr)
        return 1
    print("verify_tenant_owned_model_adoption_scaffold: OK (Phase-1 primitives present)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
