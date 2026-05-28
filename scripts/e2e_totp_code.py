#!/usr/bin/env python3
"""Print the current 6-digit TOTP for the visual QA manager user (Playwright MFA step)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["REDIS_URL"] = ""
os.environ["RMC_FORCE_DB_SESSIONS"] = "1"
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

USERNAME = os.environ.get("VISUAL_QA_USERNAME", "visualqa_admin")
DEVICE_NAME = os.environ.get("VISUAL_QA_TOTP_DEVICE", "e2e-playwright")


def main() -> int:
    import django

    django.setup()
    from django.contrib.auth import get_user_model
    from django_otp.plugins.otp_totp.models import TOTPDevice

    user = get_user_model().objects.filter(username=USERNAME).first()
    if not user:
        print("FAIL: visual QA user missing", file=sys.stderr)
        return 1
    device = TOTPDevice.objects.filter(
        user=user, name=DEVICE_NAME, confirmed=True
    ).first()
    if not device:
        print("FAIL: E2E TOTP device missing", file=sys.stderr)
        return 1
    from django_otp.oath import totp

    code = totp(
        device.bin_key,
        step=device.step,
        t0=device.t0,
        digits=device.digits,
        drift=device.drift,
    )
    print(str(code).zfill(device.digits))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
