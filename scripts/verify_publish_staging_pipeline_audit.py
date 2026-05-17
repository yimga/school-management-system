#!/usr/bin/env python
"""Program-scale publish/staging pipeline audit (repo evidence bar).

Asserts CP routes + config mutation evidence + term publish hub exist and reverse.
Does not certify hosted deploy — that remains Lane 2.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.urls import reverse

REQUIRED = (
    "siteconfig:term_publish_status_evidence",
    "siteconfig:config_mutation_audit_evidence",
    "siteconfig:metadata_operator_hub",
)


def main() -> int:
    missing = []
    for name in REQUIRED:
        try:
            reverse(name)
        except Exception:
            missing.append(name)
    if missing:
        print("[publish-staging-audit] missing URL names:", ", ".join(missing))
        return 1
    print("[publish-staging-audit] OK — term publish + mutation evidence + metadata hub reverse")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
